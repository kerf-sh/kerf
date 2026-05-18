"""
kerf_cad_core.marine — Marine hull design: parametric offsets, fairing, hydrostatics.

Pure-Python module for NURBS-reachable hull surface construction from a table of
half-breadths (station offsets), fairing quality metrics, and basic hydrostatic
calculations via Simpson's rule.

Submodules
----------
  hull   — HullOffsetTable, HullControlNet, lofted control-net recipe from offsets
  tools  — LLM tool wrappers registered with the Kerf tool registry

Public API
----------
  HullOffsetTable     — validated table of (station, waterline, half_breadth) triples
  HullControlNet      — parametric lofted control-net recipe (pure data, no OCCT)
  hull_from_offsets   — build HullControlNet from raw offset table
  fairing_report      — curvature monotonicity, batten energy, roughness metrics
  hydrostatics        — waterplane area, displaced volume, LCB via Simpson's rule

Author: imranparuk
"""
from __future__ import annotations

from kerf_cad_core.marine.hull import (
    HullOffsetTable,
    HullControlNet,
    hull_from_offsets,
    fairing_report,
    hydrostatics,
    faired_hull_surface,
)

__all__ = [
    "HullOffsetTable",
    "HullControlNet",
    "hull_from_offsets",
    "fairing_report",
    "hydrostatics",
    "faired_hull_surface",
]
