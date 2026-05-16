"""
kerf_cad_core.geotech — geotechnical and foundation engineering calculators.

Pure-Python module; no OCC dependency.  Distinct from civil/ submodules
(alignment = road geometry, hydraulics = open-channel/pipe flow).

Submodules
----------
foundation  — bearing capacity, settlement, earth pressure, retaining-wall
              stability, slope stability, pile capacity (pure Python / math only)
tools       — LLM tool wrappers registered with the Kerf tool registry

Public API (re-exported for convenience)
-----------------------------------------
    from kerf_cad_core.geotech import (
        bearing_capacity,
        settlement,
        lateral_earth_pressure,
        retaining_wall_stability,
        slope_stability_infinite,
        pile_axial_capacity,
    )

References
----------
Das, B.M. "Principles of Geotechnical Engineering", 9th ed.
Bowles, J.E. "Foundation Analysis and Design", 5th ed.
Terzaghi, K. "Theoretical Soil Mechanics" (1943).
Meyerhof, G.G. "The Ultimate Bearing Capacity of Foundations" (1951).
Rankine, W.J.M. (1857); Coulomb, C.-A. (1776).

Author: imranparuk
"""
from __future__ import annotations

from kerf_cad_core.geotech.foundation import (
    bearing_capacity,
    settlement,
    lateral_earth_pressure,
    retaining_wall_stability,
    slope_stability_infinite,
    pile_axial_capacity,
)

__all__ = [
    "bearing_capacity",
    "settlement",
    "lateral_earth_pressure",
    "retaining_wall_stability",
    "slope_stability_infinite",
    "pile_axial_capacity",
]
