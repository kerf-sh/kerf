"""BOLTS adapter — parses .blt / YAML collection files into native parts.

BOLTS (https://github.com/boltsparts/BOLTS, LGPL) is a library of
*parametric* standard mechanical parts (ISO/DIN/EN bolts, nuts, washers,
profiles...). Each "class" is described by YAML/`.blt` collection files plus
parametric backends (FreeCAD `.py`, OpenSCAD `.scad`). A collection file
contains a ``classes`` list; each class has a ``parameters.tables`` block
that maps a discrete index column to rows of dimensional values (one row
= one concrete standard size).

This adapter:
  1. Discovers all ``.blt`` / ``.yaml`` files under ``data/`` (the standard
     BOLTS repo layout; also works with synthetic fixture trees).
  2. Parses each file with PyYAML (stdlib-adjacent; no native extensions).
  3. Expands every parameter table into one :class:`~kerf_parts.model.KerfPart`
     per row via :func:`emit_part`, which stamps automatic attribution.
  4. Returns parts in deterministic (file, class-id, row-key) order.

ATTRIBUTION IS WIRED: every part goes through :func:`emit_part` → the
shared :func:`~kerf_parts.provenance.attach_attribution` helper guarantees
a non-empty attribution block. No part can be emitted without provenance.

MISSING SOURCE: if ``src_dir`` does not exist or is empty,
:func:`adapt` returns an ``{ok: False, reason: ...}``-style result — in
practice it returns an empty list and the caller can detect absence via
:func:`adapt` returns an empty list and the caller can detect absence via
:func:`source_present`.

WHAT IS NOT HERE: OpenSCAD / FreeCAD parametric geometry evaluation.
The adapter enumerates dimensional metadata (name, standard, size index, raw
dimensions as metadata) without running any CAD backend. Geometry generation
is a future extension that calls into the OCCT / scad workers.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

try:
    import yaml as _yaml  # PyYAML — optional but expected in the dev env
    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False

from ..manifest import Source
from ..model import KerfPart
from ..provenance import attach_attribution

log = logging.getLogger(__name__)

# Standard layout: collections live under data/ with .blt or .yaml extension.
_COLLECTION_GLOBS = ("data/**/*.blt", "data/**/*.yaml")

# How BOLTS labels the index column across different collections.
_INDEX_KEYS = ("index", "key", "id")


# ---------------------------------------------------------------------------
# Public helpers (also used by tests)
# ---------------------------------------------------------------------------

def source_present(src_dir) -> bool:
    """True if *src_dir* exists and contains at least one collection file."""
    src = Path(src_dir)
    if not src.is_dir():
        return False
    return bool(discover_collections(src_dir))


def discover_collections(src_dir) -> list[Path]:
    """Locate BOLTS collection definition files under *src_dir*.

    Searches ``data/**/*.blt`` and ``data/**/*.yaml`` — the standard BOLTS
    repo layout. Works equally on a real checkout and a synthetic fixture
    tree built by tests.
    """
    src = Path(src_dir)
    found: list[Path] = []
    for pattern in _COLLECTION_GLOBS:
        found.extend(sorted(src.glob(pattern)))
    # Stable deterministic order (file path).
    return sorted(set(found))


# ---------------------------------------------------------------------------
# .blt / YAML parsing helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Optional[Any]:
    """Load a YAML / .blt file; return None on parse failure."""
    if not _YAML_AVAILABLE:
        log.warning("PyYAML not installed — BOLTS collections will not be converted")
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return _yaml.safe_load(text)
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("BOLTS: failed to parse %s: %s", path, exc)
        return None


def _iter_classes(doc: Any) -> list[dict]:
    """Extract the ``classes`` list from a collection document."""
    if not isinstance(doc, dict):
        return []
    classes = doc.get("classes") or []
    if not isinstance(classes, list):
        return []
    return [c for c in classes if isinstance(c, dict)]


def _collection_meta(doc: Any) -> dict:
    """Extract top-level collection metadata (name, description, id)."""
    if not isinstance(doc, dict):
        return {}
    meta = doc.get("collection") or {}
    if not isinstance(meta, dict):
        return {}
    return meta


def _expand_tables(params: dict) -> list[tuple[str, dict]]:
    """Expand BOLTS ``parameters.tables`` into (row_key, dimensions) pairs.

    Returns a list of (index_value, {col: value, ...}) sorted by index_value
    for deterministic ordering.  Handles both the legacy ``tables:`` (list)
    and single ``table:`` (dict) forms that appear across BOLTS versions.
    """
    if not isinstance(params, dict):
        return []

    tables_raw = params.get("tables") or params.get("table")
    if not tables_raw:
        return []

    # Normalise to a list of table dicts.
    if isinstance(tables_raw, dict):
        tables_raw = [tables_raw]
    if not isinstance(tables_raw, list):
        return []

    # Merge all tables into a single {row_key: {col: val}} map.
    merged: dict[str, dict[str, Any]] = {}
    for tbl in tables_raw:
        if not isinstance(tbl, dict):
            continue
        # Detect the index column name.
        index_col = None
        for k in _INDEX_KEYS:
            if k in tbl:
                index_col = k
                break
        if index_col is None:
            continue
        columns = tbl.get("columns") or []
        data = tbl.get("data") or {}
        if not isinstance(data, dict):
            continue
        for row_key, row_vals in data.items():
            str_key = str(row_key)
            if str_key not in merged:
                merged[str_key] = {}
            if isinstance(row_vals, list):
                for i, col in enumerate(columns):
                    if i < len(row_vals):
                        merged[str_key][str(col)] = row_vals[i]
            elif isinstance(row_vals, dict):
                merged[str_key].update({str(k): v for k, v in row_vals.items()})

    return sorted(merged.items())  # deterministic: sorted by row_key


def _class_description(cls: dict, collection_meta: dict) -> str:
    """Best-effort human description for a BOLTS class."""
    # Prefer the class-level name/description, fall back to collection.
    desc = cls.get("description") or cls.get("name") or ""
    if not desc:
        desc = collection_meta.get("description") or collection_meta.get("name") or ""
    return str(desc).strip()


def _standards_for(cls: dict) -> list[str]:
    """Return list of standard numbers the class satisfies (e.g. ['ISO 4014'])."""
    standards = cls.get("standard") or cls.get("standards") or []
    if isinstance(standards, str):
        standards = [standards]
    return [str(s) for s in standards if s]


def _category_for(collection_meta: dict, cls: dict) -> str:
    """Derive a Kerf category string from the collection."""
    # BOLTS groups by class-id prefix or collection name.
    cname = (
        collection_meta.get("name") or
        collection_meta.get("id") or
        cls.get("id") or
        "mechanical"
    )
    cname_lower = str(cname).lower()
    if any(w in cname_lower for w in ("bolt", "screw", "hex")):
        return "fastener/bolt"
    if any(w in cname_lower for w in ("nut",)):
        return "fastener/nut"
    if any(w in cname_lower for w in ("washer",)):
        return "fastener/washer"
    if any(w in cname_lower for w in ("profile", "extrusion", "beam")):
        return "structural/profile"
    if any(w in cname_lower for w in ("bearing",)):
        return "mechanical/bearing"
    return "mechanical"


def _rel_path_for(source: Source, class_id: str, row_key: str) -> str:
    """Stable in-library path: <source>/<class_id>/<row_key>.part"""
    safe_key = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in row_key)
    safe_id = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in class_id)
    return f"{source.name}/{safe_id}/{safe_key}.part"


def _stable_hash(fields: dict) -> str:
    """SHA-256 of deterministic JSON-serialized *fields*."""
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public emit_part — attribution is wired here, never bypassed
# ---------------------------------------------------------------------------

def emit_part(
    source: Source,
    src_dir,
    *,
    name: str,
    category: str,
    collection_file: str,
    **fields,
) -> KerfPart:
    """Build ONE BOLTS part with automatic embedded attribution.

    *collection_file* is the originating ``.blt``/``.yaml`` path RELATIVE
    to the clone root so per-file git authorship is scoped correctly. The
    attribution block is stamped here — it is impossible to emit a BOLTS
    part without provenance.

    The content hash is derived from stable structural fields (name, category,
    mpn, source, collection_file) so it is deterministic across runs regardless
    of the ``retrieved_at`` timestamp embedded in the attribution block.
    """
    part = KerfPart(name=name, category=category, **fields)
    # Pre-compute a deterministic hash from stable identity fields BEFORE the
    # time-varying attribution block is attached.  ensure_hash() will return
    # this value without re-computing from the full (timestamped) metadata.
    part.content_hash = _stable_hash({
        "name": name,
        "category": category,
        "mpn": fields.get("mpn", ""),
        "source": source.name,
        "source_ref": source.ref,
        "collection_file": collection_file,
    })
    attach_attribution(source, Path(src_dir), part, collection_file)
    return part


# ---------------------------------------------------------------------------
# Main adapter entry point
# ---------------------------------------------------------------------------

def adapt(source: Source, src_dir) -> list[KerfPart]:
    """Convert a BOLTS checkout at *src_dir* into canonical Kerf parts.

    Returns a deterministically ordered list of :class:`~kerf_parts.model.KerfPart`
    — one per concrete standard size found in every collection's parameter
    tables. If *src_dir* is absent or empty, returns ``[]`` immediately
    (no network access; the caller can check :func:`source_present`).

    PyYAML is required. If it is not installed, logs a warning and returns
    ``[]`` (graceful degradation so the seed pipeline does not crash on a
    missing optional dep).
    """
    src = Path(src_dir)
    if not src.is_dir():
        log.info("BOLTS source not present at %s — skipping (run fetch first)", src)
        return []

    if not _YAML_AVAILABLE:
        log.warning(
            "PyYAML not installed; BOLTS collections at %s will not be converted. "
            "Install: pip install pyyaml",
            src,
        )
        return []

    parts: list[KerfPart] = []
    for coll_path in discover_collections(src):
        rel = coll_path.relative_to(src).as_posix()
        doc = _load_yaml(coll_path)
        if doc is None:
            continue
        coll_meta = _collection_meta(doc)
        for cls in _iter_classes(doc):
            class_id = str(cls.get("id") or cls.get("name") or "unknown")
            description = _class_description(cls, coll_meta)
            standards = _standards_for(cls)
            category = _category_for(coll_meta, cls)

            params = cls.get("parameters") or {}
            rows = _expand_tables(params)

            if not rows:
                # Class has no table (e.g. it relies purely on free parameters
                # with defaults). Emit a single placeholder part so discovery
                # still surfaces it with provenance.
                name = f"{class_id}" if not standards else f"{standards[0]} {class_id}"
                part = emit_part(
                    source, src,
                    name=name,
                    category=category,
                    collection_file=rel,
                    description=description,
                    metadata={
                        "bolts_class_id": class_id,
                        "bolts_standards": standards,
                        "bolts_collection": coll_meta.get("name") or "",
                    },
                )
                part.rel_path = _rel_path_for(source, class_id, class_id)
                parts.append(part)
                continue

            for row_key, dims in rows:
                std_prefix = f"{standards[0]} " if standards else ""
                name = f"{std_prefix}{class_id} {row_key}".strip()
                mpn = row_key
                part = emit_part(
                    source, src,
                    name=name,
                    category=category,
                    collection_file=rel,
                    description=description,
                    mpn=mpn,
                    metadata={
                        "bolts_class_id": class_id,
                        "bolts_standards": standards,
                        "bolts_collection": coll_meta.get("name") or "",
                        "bolts_size": row_key,
                        "bolts_dimensions": dims,
                    },
                )
                part.rel_path = _rel_path_for(source, class_id, row_key)
                parts.append(part)

    return parts
