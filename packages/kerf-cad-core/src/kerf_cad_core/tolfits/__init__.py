"""
kerf_cad_core.tolfits — ISO 286 limits & fits + press-fit analysis.

Implements:
  - ISO 286-1 tolerance grades IT01 through IT18 for nominal sizes up to 3150 mm
  - Fundamental deviations for shaft letter codes a–zc and hole codes A–ZC
  - Upper/lower limits for designations like H7, g6, p6, k5, etc.
  - Fit classification (clearance / transition / interference) with min/max
    clearance or interference
  - Preferred-fit lookup table (ISO 286-2 preferred fits)
  - Lamé thick-cylinder interference / press-fit analysis:
    contact pressure, assembly force, hoop stresses, shrink-fit temperature

This module is distinct from tolstack/ (statistical 1D assembly stack-up).
Pure Python — no OCC dependency.

Public API:

    from kerf_cad_core.tolfits import (
        it_tolerance,
        hole_limits,
        shaft_limits,
        fit_analysis,
        preferred_fits,
        press_fit,
    )

References
----------
ISO 286-1:2010 — Geometrical product specifications — Part 1: Limits and fits
ISO 286-2:2010 — Part 2: Tables of standard tolerance grades and limit deviations
Shigley's Mechanical Engineering Design (10th ed.) — thick-cylinder / press-fit
Spotts, M.F. — Mechanical Design Analysis

Author: imranparuk
"""

from kerf_cad_core.tolfits.fits import (
    it_tolerance,
    hole_limits,
    shaft_limits,
    fit_analysis,
    preferred_fits,
    press_fit,
)

__all__ = [
    "it_tolerance",
    "hole_limits",
    "shaft_limits",
    "fit_analysis",
    "preferred_fits",
    "press_fit",
]
