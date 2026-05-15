"""KiCad adapter.

We do NOT reimplement any KiCad sym/mod parsing. ``kerf_imports`` already
ships a directory scanner (``kerf_imports.kicad_library._parse_sym_files`` /
``_parse_mod_files``) that walks ``*.kicad_sym`` / ``*.kicad_mod`` via
kiutils and returns part dicts with ``schematic_symbol`` / ``pcb_footprint``
/ ``model_3d_paths`` / ``content_hash``. That dict shape is *already* the
electronic-part JSON Kerf stores inside ``kind='part'`` files (see
:mod:`kerf_parts.model`), so the adapter just calls the scanner and wraps
each dict in a :class:`KerfPart`, adding the automatic, embedded
``attribution`` provenance block (see :mod:`kerf_parts.provenance`) + a sane
in-library path.

Attribution is NOT optional and NOT manual: for every emitted part the
adapter resolves the exact upstream file it came from
(``<lib>.kicad_sym`` for a symbol, ``<lib>.pretty/<entry>.kicad_mod`` for a
footprint) and asks the shared provenance helper for that file's git
authorship. The helper guarantees a non-empty ``original_author`` /
``source_url`` via its fallback chain — a blank attribution is a bug.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..manifest import Source
from ..model import KerfPart, part_filename
from ..provenance import build_attribution


class KiCadUnavailable(RuntimeError):
    """kiutils (and hence kerf_imports' KiCad scanner) is not installed."""


def _scan(src_dir: Path) -> list[dict]:
    """Run kerf_imports' existing KiCad directory scanner over *src_dir*."""
    try:
        from kerf_imports.kicad_library import _parse_mod_files, _parse_sym_files
    except ImportError as exc:  # kerf_imports not importable
        raise KiCadUnavailable(f"kerf_imports unavailable: {exc}") from exc
    try:
        import kiutils  # noqa: F401
    except ImportError as exc:
        raise KiCadUnavailable(
            "kiutils not installed; `pip install kiutils` to convert KiCad libraries"
        ) from exc

    parts: list[dict] = []
    sym_w, sym_e = _parse_sym_files(src_dir, parts)
    mod_w, mod_e = _parse_mod_files(src_dir, parts)
    # Parser-level warnings/errors are non-fatal here; the seeder logs counts.
    _scan.last_warnings = sym_w + mod_w  # type: ignore[attr-defined]
    _scan.last_errors = sym_e + mod_e  # type: ignore[attr-defined]
    return parts


def _rel_path(source: Source, raw: dict) -> str:
    """Stable in-library path: <Source>/<Symbols|Footprints>/<lib>/<name>.part"""
    if raw.get("schematic_symbol"):
        sym = raw["schematic_symbol"]
        lib = sym.get("library", "misc")
        leaf = part_filename(sym.get("entry_name") or raw["name"])
        return f"{source.name}/Symbols/{lib}/{leaf}"
    if raw.get("pcb_footprint"):
        fp = raw["pcb_footprint"]
        lib = fp.get("library", "misc")
        leaf = part_filename(fp.get("entry_name") or raw["name"])
        return f"{source.name}/Footprints/{lib}/{leaf}"
    return f"{source.name}/{part_filename(raw['name'])}"


def _upstream_source_file(src_dir: Path, raw: dict) -> str:
    """The part's *originating* file, RELATIVE to the clone root.

    The kerf_imports scanner records the library only (``sym_file.stem`` for
    symbols, ``mod_file.parent.stem`` for footprints). KiCad's on-disk layout
    is deterministic, so we reconstruct the exact path the part came from so
    git history can be scoped to it:

      * symbol    -> ``<lib>.kicad_sym``  (somewhere under the clone)
      * footprint -> ``<lib>.pretty/<entry>.kicad_mod``

    We confirm against the real tree (handles upstreams that nest libraries
    in subdirs); if the file is not found we return the canonical guess so
    the provenance helper still records *a* source_file (and its chain falls
    back to repo/manifest authorship rather than emitting nothing).
    """
    sym = raw.get("schematic_symbol") or {}
    fp = raw.get("pcb_footprint") or {}
    src_dir = Path(src_dir)

    if sym:
        lib = sym.get("library") or ""
        if lib:
            cand = f"{lib}.kicad_sym"
            hit = next(iter(src_dir.rglob(cand)), None)
            if hit is not None:
                return hit.relative_to(src_dir).as_posix()
            return cand
    if fp:
        lib = fp.get("library") or ""
        entry = fp.get("entry_name") or raw.get("name") or ""
        if lib and entry:
            cand = f"{lib}.pretty/{entry}.kicad_mod"
            hit = next(iter(src_dir.rglob(f"{entry}.kicad_mod")), None)
            if hit is not None:
                # Prefer the one inside the matching .pretty dir if present.
                for h in src_dir.rglob(f"{entry}.kicad_mod"):
                    if h.parent.stem == lib:
                        return h.relative_to(src_dir).as_posix()
                return hit.relative_to(src_dir).as_posix()
            return cand
    return ""


_GENERATOR_RE = re.compile(r"\(generator\s+\"?([^)\"]+)\"?")
_GEN_VERSION_RE = re.compile(r"\(generator_version\s+\"?([^)\"]+)\"?")


def _in_file_metadata(src_dir: Path, source_file_rel: str) -> Optional[dict]:
    """Extra (never sole) author signal: KiCad's in-file ``(generator ...)``.

    KiCad ``.kicad_sym`` / ``.kicad_mod`` carry a ``(generator ...)`` and
    sometimes ``(generator_version ...)`` token near the top. We record it
    as an additional provenance signal only; it is NEVER used as the author.
    """
    if not source_file_rel:
        return None
    p = Path(src_dir) / source_file_rel
    if not p.is_file():
        return None
    try:
        head = p.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return None
    meta: dict = {}
    g = _GENERATOR_RE.search(head)
    if g:
        meta["generator"] = g.group(1).strip()
    gv = _GEN_VERSION_RE.search(head)
    if gv:
        meta["generator_version"] = gv.group(1).strip()
    return meta or None


def _to_kerf_part(source: Source, src_dir: Path, raw: dict) -> KerfPart:
    kp = KerfPart(
        name=raw.get("name", ""),
        category=raw.get("category", "electronic"),
        schematic_symbol=raw.get("schematic_symbol"),
        pcb_footprint=raw.get("pcb_footprint"),
        model_3d_paths=list(raw.get("model_3d_paths") or []),
        content_hash=raw.get("content_hash", ""),
    )
    sym = raw.get("schematic_symbol") or {}
    if sym.get("description"):
        kp.description = sym["description"]
        kp.datasheet_url = sym.get("datasheet_url", "")
    fp = raw.get("pcb_footprint") or {}
    if fp.get("description") and not kp.description:
        kp.description = fp["description"]

    # ---- automatic embedded attribution (the key requirement) ---------
    source_file_rel = _upstream_source_file(src_dir, raw)
    in_file_meta = _in_file_metadata(src_dir, source_file_rel)
    attribution = build_attribution(
        source, src_dir, source_file_rel, in_file_meta=in_file_meta
    )

    kp.metadata = {
        # Legacy flat keys kept for back-compat with anything already
        # reading them; the structured block is the canonical home.
        "source": source.name,
        "upstream_url": source.git_url,
        "upstream_ref": source.ref,
        "upstream_license": source.license,
        # Structured, travels-with-the-part attribution. Never empty.
        "attribution": attribution,
        "attribution_text": attribution["attribution_text"],
    }
    kp.rel_path = _rel_path(source, raw)
    kp.ensure_hash()
    return kp


def adapt(source: Source, src_dir) -> list[KerfPart]:
    """Convert a cloned KiCad symbols/footprints repo into Kerf parts."""
    src = Path(src_dir)
    return [_to_kerf_part(source, src, raw) for raw in _scan(src)]


def adapt_packages3d(source: Source, src_dir) -> list[KerfPart]:
    """kicad-packages3D is multi-GB STEP/WRL geometry with no sym/mod files.

    We do not bulk-import binary 3D bodies into the library here. The 3D
    model *references* already travel with each footprint
    (``model_3d_paths``) via the footprints adapter; resolving them to real
    geometry is an on-demand import (kerf_imports STEP/3dm path), not a
    seed-time bulk conversion. Returning [] keeps the heavy source opt-in
    and side-effect free while still letting the fetch be wired/tested.
    """
    return []
