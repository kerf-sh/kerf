"""BOLTS adapter — SCAFFOLD (fetch wired, conversion is a documented TODO).

BOLTS (https://github.com/boltsparts/BOLTS, LGPL) is a library of
*parametric* standard mechanical parts (ISO/DIN/EN bolts, nuts, washers,
profiles...). Each "class" is described by YAML/`.blt` collection files plus
parametric backends (FreeCAD `.py`, OpenSCAD `.scad`). Faithfully turning
those into Kerf parts means evaluating the parameter tables to enumerate
concrete sizes — that is a sizeable piece of work, so it is intentionally
left as a TODO. The fetch IS fully wired (the manifest entry clones the
repo into the cache), and this adapter implements the registry interface so
the pipeline runs end to end (it just yields zero parts today).

ATTRIBUTION IS ALREADY WIRED. The future implementer does not get to bypass
provenance: build each part with :func:`emit_part`, which stamps the
automatic embedded ``attribution`` block (scoped to the originating
collection file's git history) via the shared
:func:`kerf_parts.provenance.attach_attribution`. There is intentionally no
code path that returns a KerfPart without attribution.

WHAT IS REAL:  manifest entry + fetch into .parts-cache/bolts/;
               collection discovery; the attribution seam.
WHAT IS TODO:  parse blt/YAML collections, expand parameter tables into
               concrete .part rows (one per standard size) via emit_part().
"""
from __future__ import annotations

from pathlib import Path

from ..manifest import Source
from ..model import KerfPart
from ..provenance import attach_attribution

# Where BOLTS keeps its collection definitions, for the future implementer.
_COLLECTION_GLOBS = ("data/**/*.blt", "data/**/*.yaml")


def discover_collections(src_dir) -> list[Path]:
    """Locate BOLTS collection definition files (used by tests + future impl)."""
    src = Path(src_dir)
    found: list[Path] = []
    for pattern in _COLLECTION_GLOBS:
        found.extend(sorted(src.glob(pattern)))
    return found


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

    The future implementer iterates :func:`discover_collections`, expands a
    collection's parameter table, and calls this per concrete size.
    ``collection_file`` is the originating ``.blt``/``.yaml`` path RELATIVE
    to the clone root so per-file git authorship is scoped correctly. The
    attribution block is stamped here — it is impossible to emit a BOLTS
    part without provenance.
    """
    part = KerfPart(name=name, category=category, **fields)
    attach_attribution(source, Path(src_dir), part, collection_file)
    part.ensure_hash()
    return part


def adapt(source: Source, src_dir) -> list[KerfPart]:
    """SCAFFOLD: returns []. See module docstring for the conversion TODO.

    The conversion is a no-op TODAY, but the attribution seam is live: the
    future implementer builds parts via :func:`emit_part`, which guarantees
    every BOLTS part carries an automatic ``attribution`` block.
    """
    return []
