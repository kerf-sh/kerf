"""
kerf_cad_core.arch — Parametric architectural BIM primitives.

Pure-Python parametric model layer for architectural elements.  No OCC
dependency.  All units are millimetres throughout.

Submodules:
  primitives  — Wall, Door, Window, Slab, Opening dataclasses + builders
  tools       — LLM tool wrappers registered with the tool registry
"""
from __future__ import annotations

from kerf_cad_core.arch.primitives import (
    WallLayer,
    WallSpec,
    DoorSpec,
    WindowSpec,
    SlabSpec,
    OpeningSpec,
    build_wall,
    build_door,
    build_window,
    build_slab,
    build_opening,
)

__all__ = [
    "WallLayer",
    "WallSpec",
    "DoorSpec",
    "WindowSpec",
    "SlabSpec",
    "OpeningSpec",
    "build_wall",
    "build_door",
    "build_window",
    "build_slab",
    "build_opening",
]
