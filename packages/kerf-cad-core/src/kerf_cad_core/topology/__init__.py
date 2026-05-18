"""
kerf_cad_core.topology — production-grade topology-optimisation extensions.

Sub-modules
-----------
manufacturing_constraints
    Density filter (min-feature-size), draw-direction (casting / milling),
    symmetry-plane enforcement, and AM overhang checks — all as standalone,
    stateless functions that operate on raw density arrays.

multi_load
    Compliance-weighted multi-load-case aggregation, per-load sensitivity
    accumulation, and a two-load Pareto-front sketch utility.

All calculations are pure-Python (``math`` only); no OCC, no numpy, no scipy.
"""
from __future__ import annotations

__all__ = ["manufacturing_constraints", "multi_load"]
