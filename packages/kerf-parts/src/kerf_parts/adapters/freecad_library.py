"""FreeCAD-library adapter — enumerates part files into canonical metadata parts.

FreeCAD-library (https://github.com/FreeCAD/FreeCAD-library) is a flat tree
of ready-made parts as ``.FCStd`` (FreeCAD native) plus exported ``.step`` /
``.stp`` / ``.brep`` files, organized by category folders.

This adapter:
  1. Discovers all importable files (``.fcstd``, ``.step``, ``.stp``, ``.brep``)
     under *src_dir* via :func:`discover_part_files`.
  2. Derives part name and Kerf category from the file's path within the
     library tree (parent folder = category, stem = name).
  3. Emits one :class:`~kerf_parts.model.KerfPart` per file via
     :func:`emit_part`, which stamps automatic attribution.
  4. Returns parts in deterministic (relative file path) order.

GEOMETRY IMPORT IS DEFERRED. The adapter records the originating file path
(``metadata.freecad_file``) so the on-demand geometry import path in
``kerf_imports`` can resolve it later. No OCCT / FreeCAD binary is required
at seed time — only filesystem enumeration happens here.

ATTRIBUTION IS WIRED: every part goes through :func:`emit_part` → the
shared :func:`~kerf_parts.provenance.attach_attribution` helper guarantees
a non-empty attribution block.

MISSING SOURCE: if *src_dir* does not exist or is empty, :func:`adapt`
returns ``[]`` immediately with a log message. Check :func:`source_present`.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from ..manifest import Source
from ..model import KerfPart, part_filename
from ..provenance import attach_attribution

log = logging.getLogger(__name__)

# All file suffixes the FreeCAD library ships in (case-insensitive check).
_PART_SUFFIXES = frozenset((".fcstd", ".step", ".stp", ".brep"))

# Folders commonly used in the FreeCAD-library that map to Kerf category names.
_FOLDER_CATEGORY: dict[str, str] = {
    "mechanical": "mechanical",
    "fastener": "fastener",
    "fasteners": "fastener",
    "bolt": "fastener/bolt",
    "bolts": "fastener/bolt",
    "screw": "fastener/screw",
    "screws": "fastener/screw",
    "nut": "fastener/nut",
    "nuts": "fastener/nut",
    "washer": "fastener/washer",
    "washers": "fastener/washer",
    "bearing": "mechanical/bearing",
    "bearings": "mechanical/bearing",
    "gear": "mechanical/gear",
    "gears": "mechanical/gear",
    "electronics": "electronic",
    "electrical": "electronic",
    "structural": "structural",
    "profile": "structural/profile",
    "profiles": "structural/profile",
    "pipe": "structural/pipe",
    "pipes": "structural/pipe",
    "flange": "structural/flange",
    "flanges": "structural/flange",
    "architecture": "architecture",
    "furniture": "furniture",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def source_present(src_dir) -> bool:
    """True if *src_dir* exists and contains at least one importable file."""
    src = Path(src_dir)
    if not src.is_dir():
        return False
    return bool(discover_part_files(src_dir))


def discover_part_files(src_dir) -> list[Path]:
    """Enumerate importable part files under *src_dir*.

    Returns only ``.fcstd``, ``.step``, ``.stp``, ``.brep`` files
    (case-insensitive), sorted deterministically by relative path.
    Hidden directories and ``__MACOSX`` artifacts are skipped.
    """
    src = Path(src_dir)
    out: list[Path] = []
    for p in sorted(src.rglob("*")):
        # Skip hidden entries and macOS archive noise.
        if any(part.startswith(".") or part == "__MACOSX" for part in p.parts[len(src.parts):]):
            continue
        if p.is_file() and p.suffix.lower() in _PART_SUFFIXES:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Name / category derivation
# ---------------------------------------------------------------------------

def _name_from_path(p: Path, src: Path) -> str:
    """Human-readable part name derived from the file's path.

    Uses the file stem (without extension), with underscores/hyphens
    replaced by spaces and the result title-cased. If the immediate parent
    folder provides extra context (and differs from the stem), it is
    prepended.
    replaced by spaces for readability.

    Examples::
        Mechanical/FlangeM12.step  -> "FlangeM12"
        Fasteners/Bolts/HexM8x20.FCStd -> "HexM8x20"
    """
    stem = p.stem.strip()
    if not stem:
        stem = "part"
    # Replace underscores and hyphens with spaces for readability.
    readable = stem.replace("_", " ").replace("-", " ").strip()
    return readable or stem


def _category_from_path(p: Path, src: Path) -> str:
    """Derive a Kerf category from the folder hierarchy above the file.

    Walks the path components from closest-parent upward; returns the first
    match against :data:`_FOLDER_CATEGORY`, or ``"mechanical"`` as default.
    """
    rel_parts = p.relative_to(src).parts
    # Inspect parent folders (closest first, excluding the filename itself).
    for part in reversed(rel_parts[:-1]):
        key = part.lower().strip()
        if key in _FOLDER_CATEGORY:
            return _FOLDER_CATEGORY[key]
    return "mechanical"


def _rel_path_for(source: Source, file_path: Path, src: Path) -> str:
    """Stable in-library path: <source>/<relative-dir>/<name>.part

    Mirrors the upstream folder structure so two files with the same name
    in different folders get distinct library paths.
    """
    rel = file_path.relative_to(src)
    # Replace the extension with .part while keeping the directory structure.
    parts = list(rel.parent.parts) + [part_filename(rel.stem)]
    return "/".join([source.name] + parts)


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
    part_file: str,
    **fields,
) -> KerfPart:
    """Build ONE FreeCAD-library part with automatic embedded attribution.

    *part_file* is the originating ``.FCStd``/``.step`` path RELATIVE to
    the clone root so per-file git authorship is scoped correctly. Attribution
    is stamped here — a FreeCAD-library part cannot be emitted without
    provenance.

    The content hash is derived from stable structural fields (name, category,
    source, part_file) so it is deterministic across runs regardless of the
    ``retrieved_at`` timestamp embedded in the attribution block.
    """
    part = KerfPart(name=name, category=category, **fields)
    # Pre-compute a deterministic hash from stable identity fields BEFORE the
    # time-varying attribution block is attached.  ensure_hash() will return
    # this cached value without re-computing from the timestamped metadata.
    part.content_hash = _stable_hash({
        "name": name,
        "category": category,
        "source": source.name,
        "source_ref": source.ref,
        "part_file": part_file,
    })
    attach_attribution(source, Path(src_dir), part, part_file)
    return part


# ---------------------------------------------------------------------------
# Main adapter entry point
# ---------------------------------------------------------------------------

def adapt(source: Source, src_dir) -> list[KerfPart]:
    """Convert a FreeCAD-library checkout at *src_dir* into canonical Kerf parts.

    Returns one :class:`~kerf_parts.model.KerfPart` per importable file,
    ordered deterministically by relative path. Each part carries:

    * ``name`` — derived from the filename stem
    * ``category`` — derived from the enclosing folder hierarchy
    * ``metadata.freecad_file`` — the relative path for deferred geometry import
    * ``metadata.freecad_format`` — the file extension (``fcstd``/``step``/etc.)
    * A full embedded ``attribution`` block (never empty)

    Geometry is NOT imported here. The ``freecad_file`` path is the seam for
    a future ``kerf_imports.freecad`` / STEP import pass.

    If *src_dir* is absent, returns ``[]`` immediately.
    """
    src = Path(src_dir)
    if not src.is_dir():
        log.info("FreeCAD-library source not present at %s — skipping", src)
        return []

    parts: list[KerfPart] = []
    for file_path in discover_part_files(src):
        rel = file_path.relative_to(src).as_posix()
        name = _name_from_path(file_path, src)
        category = _category_from_path(file_path, src)
        fmt = file_path.suffix.lower().lstrip(".")

        part = emit_part(
            source, src,
            name=name,
            category=category,
            part_file=rel,
            metadata={
                "freecad_file": rel,
                "freecad_format": fmt,
                "freecad_library_path": rel,
            },
        )
        part.rel_path = _rel_path_for(source, file_path, src)
        # Merge the flat legacy keys alongside the attribution the helper set.
        # Ensure flat legacy keys are present alongside the attribution block.
        part.metadata.setdefault("source", source.name)
        part.metadata.setdefault("upstream_url", source.git_url)
        part.metadata.setdefault("upstream_ref", source.ref)
        part.metadata.setdefault("upstream_license", source.license)
        parts.append(part)

    return parts
