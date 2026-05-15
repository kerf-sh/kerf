"""FreeCAD-library adapter — SCAFFOLD (fetch wired, conversion deferred).

FreeCAD-library (https://github.com/FreeCAD/FreeCAD-library) is a flat tree
of ready-made parts as ``.FCStd`` (FreeCAD native) plus exported ``.step`` /
``.stp`` / ``.brep`` files, organized by category folders.

Kerf ALREADY has a full FreeCAD importer — ``kerf_imports.freecad`` (see
``kerf_imports/tools/import_freecad.py``) — and a STEP import path. The
correct, low-duplication way to ingest this source is therefore to *reuse*
that importer per file rather than write a second parser here. Wiring that
per-file import + Parts Library write is non-trivial (it needs the OCCT
worker for geometry), so it is deferred; this adapter implements the
registry interface and enumerates the candidate files so the seam is ready.

ATTRIBUTION IS ALREADY WIRED. The future implementer builds each part with
:func:`emit_part`, which stamps the automatic embedded ``attribution``
block scoped to the originating ``.FCStd``/``.step`` file's git history via
the shared :func:`kerf_parts.provenance.attach_attribution`. There is no
code path that returns a KerfPart without attribution.

WHAT IS REAL:  manifest entry + fetch into .parts-cache/freecad-library/;
               candidate-file discovery (discover_part_files); the
               attribution seam.
WHAT IS TODO:  for each .FCStd -> kerf_imports.freecad import; for each
               .step -> kerf_imports STEP import; emit each via emit_part().
"""
from __future__ import annotations

from pathlib import Path

from ..manifest import Source
from ..model import KerfPart
from ..provenance import attach_attribution

_PART_SUFFIXES = (".fcstd", ".step", ".stp", ".brep")


def discover_part_files(src_dir) -> list[Path]:
    """Enumerate importable part files (used by tests + future impl)."""
    src = Path(src_dir)
    out: list[Path] = []
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.suffix.lower() in _PART_SUFFIXES:
            out.append(p)
    return out


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

    The future implementer iterates :func:`discover_part_files`, runs the
    geometry import, and calls this per file. ``part_file`` is the
    originating ``.FCStd``/``.step`` path RELATIVE to the clone root so
    per-file git authorship is scoped correctly. Attribution is stamped here
    — a FreeCAD-library part cannot be emitted without provenance.
    """
    part = KerfPart(name=name, category=category, **fields)
    attach_attribution(source, Path(src_dir), part, part_file)
    part.ensure_hash()
    return part


def adapt(source: Source, src_dir) -> list[KerfPart]:
    """SCAFFOLD: returns []. Reuse path = kerf_imports.freecad / STEP import.

    See module docstring. Deliberately a no-op so the heavy OCCT geometry
    path is not pulled into seed-time; the fetch + discovery + attribution
    seam are real (future parts go through :func:`emit_part`).
    """
    return []
