"""
kerf_cad_core.gdt.it_grades — Canonical ISO 286-1 IT-grade tolerance system.

Reference: ISO 286-1:2010 "Geometrical product specifications (GPS) — ISO code
system for tolerances on linear sizes — Part 1: Basis of tolerances, deviations
and fits".

The standard tolerance unit i (µm) for a size band is:

    i = 0.45 · D^(1/3) + 0.001 · D        (D in mm, D = geometric-mean diameter
                                              of the ISO 286-1 size range)

IT-grade multipliers k (tolerance = k · i µm):

    IT01: 0.3   IT0: 0.5    IT1: 0.8    IT2: 1.2    IT3: 2.0    IT4: 3.0
    IT5:  7.0   IT6: 10.0   IT7: 16.0   IT8: 25.0   IT9: 40.0   IT10: 64.0
    IT11: 100.0 IT12: 160.0 IT13: 250.0 IT14: 400.0 IT15: 640.0 IT16: 1000.0
    IT17: 1600.0 IT18: 2500.0

ISO 286-1 Table 1 size bands (mm):
    (0, 3], (3, 6], (6, 10], (10, 18], (18, 30], (30, 50], (50, 80],
    (80, 120], (120, 180], (180, 250], (250, 315], (315, 400], (400, 500]

For sizes > 500 mm the formula is extrapolated using the last range.
"""
from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# ISO 286-1 size bands: (lower_exclusive, upper_inclusive) in mm
# ---------------------------------------------------------------------------

_DIM_RANGES: list[tuple[float, float]] = [
    (0.0,   3.0),
    (3.0,   6.0),
    (6.0,  10.0),
    (10.0, 18.0),
    (18.0, 30.0),
    (30.0, 50.0),
    (50.0, 80.0),
    (80.0, 120.0),
    (120.0, 180.0),
    (180.0, 250.0),
    (250.0, 315.0),
    (315.0, 400.0),
    (400.0, 500.0),
]

# ---------------------------------------------------------------------------
# IT-grade multipliers k (units of i)
# ---------------------------------------------------------------------------

#: Map of IT grade name → multiplier k; tolerance = k · i (µm).
IT_GRADE_MULTIPLIERS: dict[str, float] = {
    "IT01": 0.3,
    "IT0":  0.5,
    "IT1":  0.8,
    "IT2":  1.2,
    "IT3":  2.0,
    "IT4":  3.0,
    "IT5":  7.0,
    "IT6":  10.0,
    "IT7":  16.0,
    "IT8":  25.0,
    "IT9":  40.0,
    "IT10": 64.0,
    "IT11": 100.0,
    "IT12": 160.0,
    "IT13": 250.0,
    "IT14": 400.0,
    "IT15": 640.0,
    "IT16": 1000.0,
    "IT17": 1600.0,
    "IT18": 2500.0,
}

#: Ordered list of grades from finest to coarsest.
GRADE_ORDER: list[str] = [
    "IT01", "IT0", "IT1", "IT2", "IT3", "IT4",
    "IT5",  "IT6", "IT7", "IT8", "IT9", "IT10",
    "IT11", "IT12", "IT13", "IT14", "IT15", "IT16", "IT17", "IT18",
]

VALID_GRADES: frozenset[str] = frozenset(IT_GRADE_MULTIPLIERS.keys())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_dim_range(nominal_mm: float) -> tuple[float, float]:
    """
    Return the ISO 286-1 size band containing *nominal_mm*.

    Sizes ≤ 0 map to the first band; sizes > 500 extrapolate with the last.
    """
    if nominal_mm <= 0.0:
        return _DIM_RANGES[0]
    for low, high in _DIM_RANGES:
        if nominal_mm <= high:
            return (low, high)
    return _DIM_RANGES[-1]


def _geometric_mean_diameter(low: float, high: float) -> float:
    """Geometric mean D of the size-band boundary values (mm)."""
    # Special case: the (0, 3] band uses D = 1.5 per ISO convention.
    if low == 0.0:
        return 1.5
    return math.sqrt(low * high)


def _tolerance_unit_i(D_mm: float) -> float:
    """
    Standard tolerance unit i (µm) for geometric-mean diameter D (mm).

    Formula: i = 0.45 · D^(1/3) + 0.001 · D  (ISO 286-1 §5.2)
    """
    return 0.45 * (D_mm ** (1.0 / 3.0)) + 0.001 * D_mm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def it_tolerance_mm(grade: str, nominal_mm: float) -> float:
    """
    Return the ISO 286-1 IT-grade tolerance in millimetres.

    Parameters
    ----------
    grade:
        IT grade string, e.g. ``'IT7'`` (case-insensitive).
    nominal_mm:
        Nominal feature dimension in mm (e.g. bore diameter).

    Returns
    -------
    float
        Tolerance value in mm (always > 0).

    Raises
    ------
    ValueError
        If *grade* is not a known IT grade.

    Examples
    --------
    >>> it_tolerance_mm('IT7', 50.0)   # ≈ 0.025 mm (25 µm per ISO 286-1)
    0.024979...
    >>> it_tolerance_mm('IT6', 50.0)   # ≈ 0.016 mm (16 µm per ISO 286-1)
    0.015612...
    """
    grade_upper = grade.upper()
    if grade_upper not in IT_GRADE_MULTIPLIERS:
        raise ValueError(
            f"Unknown IT grade '{grade}'. "
            f"Valid grades: {sorted(IT_GRADE_MULTIPLIERS)}"
        )
    k = IT_GRADE_MULTIPLIERS[grade_upper]
    low, high = _find_dim_range(max(nominal_mm, 0.001))
    D = _geometric_mean_diameter(low, high)
    i_um = _tolerance_unit_i(D)
    tol_um = k * i_um
    return round(tol_um / 1000.0, 6)  # µm → mm
