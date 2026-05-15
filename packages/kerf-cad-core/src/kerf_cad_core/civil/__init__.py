"""
kerf_cad_core.civil — Site grading and earthwork computation.

Pure-Python civil/site module: triangulated terrain surface (TIN) from survey
points, design surface (pad/platform), cut/fill volume computation, and
balance report.

Submodules:
  terrain   — TIN triangulation (fan/grid + incremental fan), barycentric z
  earthwork — cut/fill volume via grid sampling; balance report
  tools     — LLM tool wrappers registered with the Kerf tool registry
"""
from __future__ import annotations

from kerf_cad_core.civil.terrain import TIN, Triangle, Point3D
from kerf_cad_core.civil.earthwork import DesignSurface, compute_earthwork, EarthworkResult

__all__ = [
    "TIN",
    "Triangle",
    "Point3D",
    "DesignSurface",
    "compute_earthwork",
    "EarthworkResult",
]
