"""
kerf_cad_core.bearings.housing — ISO 286-1 bearing seat fits and shoulder geometry.

Two public functions:

  bearing_housing_fit(bore_mm, OD_mm, shaft_fit, housing_fit)
      Compute ISO 286-1 tolerance zones for a rolling-bearing seat.
      Returns upper/lower deviations (µm) for shaft and housing fits.

  bearing_shoulder_geometry(bore_mm, OD_mm, B_mm, bearing_type)
      Compute recommended shaft shoulder OD and housing lip ID dimensions
      per SKF catalogue guidelines.

All functions return {"ok": True, ...} on success or {"ok": False, "reason": ...}.
Functions NEVER raise.

References
----------
ISO 286-1:2010 — Geometrical product specifications — Limits and fits
SKF Bearing Catalogue, 2018 edition, §§ 7, 12

Author: imranparuk
"""

from __future__ import annotations

import math
import re
from typing import Any
from kerf_cad_core._guards import _err, _guard_positive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_IT_BANDS: list[tuple] = [
    (0,    3,    2,    3,    4,    6,    10,   14,   25,   40,   60),
    (3,    6,    2.5,  4,    5,    8,    12,   18,   30,   48,   75),
    (6,    10,   2.5,  4,    6,    9,    15,   22,   36,   58,   90),
    (10,   18,   3,    5,    8,    11,   18,   27,   43,   70,   110),
    (18,   30,   4,    6,    9,    13,   21,   33,   52,   84,   130),
    (30,   50,   4,    7,    11,   16,   25,   39,   62,   100,  160),
    (50,   80,   5,    8,    13,   19,   30,   46,   74,   120,  190),
    (80,   120,  6,    10,   15,   22,   35,   54,   87,   140,  220),
    (120,  180,  8,    12,   18,   25,   40,   63,   100,  160,  250),
    (180,  250,  10,   14,   20,   29,   46,   72,   115,  185,  290),
    (250,  315,  12,   16,   23,   32,   52,   81,   130,  210,  320),
    (315,  400,  13,   18,   25,   36,   57,   89,   140,  230,  360),
    (400,  500,  15,   20,   28,   40,   63,   97,   155,  250,  400),
]

# Column index within each row for each IT grade
_IT_GRADE_COL: dict[int, int] = {3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 8, 10: 9, 11: 10}


def _it_width(nominal_mm: float, grade: int) -> float | None:
    """Return IT grade tolerance width in µm, or None if out of range."""
    col = _IT_GRADE_COL.get(grade)
    if col is None:
        return None
    for row in _IT_BANDS:
        over, upto = row[0], row[1]
        if over < nominal_mm <= upto:
            return float(row[col])
    return None


# ---------------------------------------------------------------------------
# ISO 286-1 fundamental deviations (µm) for bearing-relevant designators
#
# Shaft designators (es = upper deviation):
#   negative es  → shaft is below zero line (clearance fits: c, d, f, g)
#   zero es      → h (zero-line shaft)
#   positive es  → shaft is above zero line (transition/interference: k, m, n, p, r, s)
#
# Hole designators (EI = lower deviation):
#   positive EI  → hole is above zero line (clearance: D, E, F, G, A, B, C)
#   zero EI      → H (basis-hole, clearance)
#   negative EI  → hole is below zero line (transition/interference: K, M, N, P)
#
# Each entry: (over_mm, upto_mm, deviation_µm)
# ---------------------------------------------------------------------------

_SHAFT_FD: dict[str, list[tuple[float, float, float]]] = {
    "c": [
        (0, 3, -60), (3, 6, -70), (6, 10, -80), (10, 18, -95), (18, 30, -110),
        (30, 50, -120), (50, 80, -130), (80, 120, -140), (120, 180, -145),
        (180, 250, -170), (250, 315, -190), (315, 400, -210), (400, 500, -230),
    ],
    "d": [
        (0, 3, -20), (3, 6, -30), (6, 10, -40), (10, 18, -50), (18, 30, -65),
        (30, 50, -80), (50, 80, -100), (80, 120, -120), (120, 180, -145),
        (180, 250, -170), (250, 315, -190), (315, 400, -210), (400, 500, -230),
    ],
    "f": [
        (0, 3, -6), (3, 6, -10), (6, 10, -13), (10, 18, -16), (18, 30, -20),
        (30, 50, -25), (50, 80, -30), (80, 120, -36), (120, 180, -43),
        (180, 250, -50), (250, 315, -56), (315, 400, -62), (400, 500, -68),
    ],
    "g": [
        (0, 3, -2), (3, 6, -4), (6, 10, -5), (10, 18, -6), (18, 30, -7),
        (30, 50, -9), (50, 80, -10), (80, 120, -12), (120, 180, -14),
        (180, 250, -15), (250, 315, -17), (315, 400, -18), (400, 500, -20),
    ],
    # h: es = 0 — handled specially
    "k": [
        (0, 3, 0), (3, 6, 1), (6, 10, 1), (10, 18, 1), (18, 30, 2),
        (30, 50, 2), (50, 80, 2), (80, 120, 3), (120, 180, 3),
        (180, 250, 4), (250, 315, 4), (315, 400, 4), (400, 500, 5),
    ],
    "m": [
        (0, 3, 2), (3, 6, 4), (6, 10, 6), (10, 18, 7), (18, 30, 8),
        (30, 50, 9), (50, 80, 11), (80, 120, 13), (120, 180, 15),
        (180, 250, 17), (250, 315, 20), (315, 400, 21), (400, 500, 23),
    ],
    "n": [
        (0, 3, 4), (3, 6, 8), (6, 10, 10), (10, 18, 12), (18, 30, 15),
        (30, 50, 17), (50, 80, 20), (80, 120, 23), (120, 180, 27),
        (180, 250, 31), (250, 315, 34), (315, 400, 37), (400, 500, 40),
    ],
    "p": [
        (0, 3, 6), (3, 6, 12), (6, 10, 15), (10, 18, 18), (18, 30, 22),
        (30, 50, 26), (50, 80, 32), (80, 120, 37), (120, 180, 43),
        (180, 250, 50), (250, 315, 56), (315, 400, 62), (400, 500, 68),
    ],
    "r": [
        (0, 3, 10), (3, 6, 15), (6, 10, 19), (10, 18, 23), (18, 30, 28),
        (30, 50, 34), (50, 80, 41), (80, 120, 48), (120, 180, 54),
        (180, 250, 63), (250, 315, 72), (315, 400, 78), (400, 500, 86),
    ],
    "s": [
        (0, 3, 14), (3, 6, 19), (6, 10, 23), (10, 18, 28), (18, 30, 35),
        (30, 50, 43), (50, 80, 53), (80, 120, 59), (120, 180, 71),
        (180, 250, 79), (250, 315, 92), (315, 400, 100), (400, 500, 108),
    ],
}

_HOLE_FD: dict[str, list[tuple[float, float, float]]] = {
    "A": [
        (0, 3, 270), (3, 6, 270), (6, 10, 280), (10, 18, 290), (18, 30, 300),
        (30, 50, 310), (50, 80, 320), (80, 120, 340), (120, 180, 360),
        (180, 250, 380), (250, 315, 420), (315, 400, 440), (400, 500, 480),
    ],
    "B": [
        (0, 3, 140), (3, 6, 140), (6, 10, 150), (10, 18, 150), (18, 30, 160),
        (30, 50, 170), (50, 80, 180), (80, 120, 200), (120, 180, 210),
        (180, 250, 230), (250, 315, 240), (315, 400, 260), (400, 500, 280),
    ],
    "C": [
        (0, 3, 60), (3, 6, 70), (6, 10, 80), (10, 18, 95), (18, 30, 110),
        (30, 50, 120), (50, 80, 130), (80, 120, 140), (120, 180, 145),
        (180, 250, 170), (250, 315, 190), (315, 400, 210), (400, 500, 230),
    ],
    "D": [
        (0, 3, 20), (3, 6, 30), (6, 10, 40), (10, 18, 50), (18, 30, 65),
        (30, 50, 80), (50, 80, 100), (80, 120, 120), (120, 180, 145),
        (180, 250, 170), (250, 315, 190), (315, 400, 210), (400, 500, 230),
    ],
    "E": [
        (0, 3, 14), (3, 6, 20), (6, 10, 25), (10, 18, 32), (18, 30, 40),
        (30, 50, 50), (50, 80, 60), (80, 120, 72), (120, 180, 85),
        (180, 250, 100), (250, 315, 110), (315, 400, 125), (400, 500, 135),
    ],
    "F": [
        (0, 3, 6), (3, 6, 10), (6, 10, 13), (10, 18, 16), (18, 30, 20),
        (30, 50, 25), (50, 80, 30), (80, 120, 36), (120, 180, 43),
        (180, 250, 50), (250, 315, 56), (315, 400, 62), (400, 500, 68),
    ],
    "G": [
        (0, 3, 2), (3, 6, 4), (6, 10, 5), (10, 18, 6), (18, 30, 7),
        (30, 50, 9), (50, 80, 10), (80, 120, 12), (120, 180, 14),
        (180, 250, 15), (250, 315, 17), (315, 400, 18), (400, 500, 20),
    ],
    # H: EI = 0 — handled specially
    "K": [
        (0, 3, -2), (3, 6, -2), (6, 10, -2), (10, 18, -2), (18, 30, -2),
        (30, 50, -2), (50, 80, -2), (80, 120, -3), (120, 180, -3),
        (180, 250, -4), (250, 315, -4), (315, 400, -4), (400, 500, -5),
    ],
    "M": [
        (0, 3, -2), (3, 6, -4), (6, 10, -6), (10, 18, -7), (18, 30, -8),
        (30, 50, -9), (50, 80, -11), (80, 120, -13), (120, 180, -15),
        (180, 250, -17), (250, 315, -20), (315, 400, -21), (400, 500, -23),
    ],
    "N": [
        (0, 3, -4), (3, 6, -8), (6, 10, -10), (10, 18, -12), (18, 30, -15),
        (30, 50, -17), (50, 80, -20), (80, 120, -23), (120, 180, -27),
        (180, 250, -31), (250, 315, -34), (315, 400, -37), (400, 500, -40),
    ],
    "P": [
        (0, 3, -6), (3, 6, -12), (6, 10, -15), (10, 18, -18), (18, 30, -22),
        (30, 50, -26), (50, 80, -32), (80, 120, -37), (120, 180, -43),
        (180, 250, -50), (250, 315, -56), (315, 400, -62), (400, 500, -68),
    ],
}


def _fund_dev_shaft(des: str, nominal_mm: float) -> float | None:
    """Return shaft fundamental deviation (es, µm) for designator at nominal_mm."""
    rows = _SHAFT_FD.get(des)
    if rows is None:
        return None
    for over, upto, fd in rows:
        if over < nominal_mm <= upto:
            return float(fd)
    return None


def _fund_dev_hole(des: str, nominal_mm: float) -> float | None:
    """Return hole fundamental deviation (EI, µm) for designator at nominal_mm."""
    rows = _HOLE_FD.get(des)
    if rows is None:
        return None
    for over, upto, fd in rows:
        if over < nominal_mm <= upto:
            return float(fd)
    return None


# ---------------------------------------------------------------------------
# Public function 1: bearing_housing_fit
# ---------------------------------------------------------------------------


def bearing_housing_fit(
    bore_mm: float,
    OD_mm: float,
    shaft_fit: str = "k6",
    housing_fit: str = "H7",
) -> dict:
    """
    Compute ISO 286-1 tolerance zones for a bearing seat.

    Parameters
    ----------
    bore_mm : float
        Bearing bore diameter d (mm). Nominal shaft diameter at inner ring.
        Must be > 0 and <= 500 mm.
    OD_mm : float
        Bearing outer diameter D (mm). Nominal housing bore diameter.
        Must be > bore_mm and <= 500 mm.
    shaft_fit : str
        ISO 286 shaft tolerance (e.g. "k6", "m5", "h6", "js5").
        Default "k6" (transition fit, common for rotating inner rings).
    housing_fit : str
        ISO 286 housing bore tolerance (e.g. "H7", "K7", "N7").
        Default "H7" (clearance, common for stationary outer rings).

    Returns
    -------
    dict
        ok               : True
        bore_mm          : bearing bore (mm)
        OD_mm            : bearing OD (mm)
        shaft_fit        : designator string
        housing_fit      : designator string
        shaft_es_um      : shaft upper deviation (µm)
        shaft_ei_um      : shaft lower deviation (µm)
        shaft_IT_um      : shaft IT grade tolerance width (µm)
        housing_ES_um    : housing upper deviation (µm)
        housing_EI_um    : housing lower deviation (µm)
        housing_IT_um    : housing IT grade tolerance width (µm)
        fit_type_shaft   : "clearance" | "transition" | "interference"
        fit_type_housing : "clearance" | "transition" | "interference"
        warnings         : list of warning strings
    """
    warns: list[str] = []

    err = _guard_positive("bore_mm", bore_mm)
    if err:
        return _err(err)
    err = _guard_positive("OD_mm", OD_mm)
    if err:
        return _err(err)

    try:
        d = float(bore_mm)
        D = float(OD_mm)
    except (TypeError, ValueError) as exc:
        return _err(str(exc))

    if D <= d:
        return _err(f"OD_mm ({OD_mm}) must be > bore_mm ({bore_mm})")
    if d > 500 or D > 500:
        return _err("bore_mm and OD_mm must be <= 500 mm (ISO 286-1 range)")

    shaft_str = str(shaft_fit).strip()
    housing_str = str(housing_fit).strip()

    if not shaft_str:
        return _err("shaft_fit must not be empty")
    if not housing_str:
        return _err("housing_fit must not be empty")

    # Parse shaft fit: e.g. "k6" → designator="k", grade=6
    m = re.fullmatch(r"([a-zA-Z]{1,2})(\d+)", shaft_str)
    if not m:
        return _err(
            f"Cannot parse shaft_fit {shaft_fit!r} — expected format like 'k6', 'm5', 'js5'"
        )
    s_des = m.group(1).lower()
    s_grade = int(m.group(2))

    # Parse housing fit: e.g. "H7" → designator="H", grade=7
    m2 = re.fullmatch(r"([a-zA-Z]{1,2})(\d+)", housing_str)
    if not m2:
        return _err(
            f"Cannot parse housing_fit {housing_fit!r} — expected format like 'H7', 'K7'"
        )
    h_des = m2.group(1).upper()
    h_grade = int(m2.group(2))

    # Shaft IT width at bore_mm
    s_it = _it_width(d, s_grade)
    if s_it is None:
        return _err(
            f"IT grade {s_grade} not in supported range IT3-IT11 or nominal size out of range"
        )

    # Shaft deviations
    if s_des == "js":
        s_es = s_it / 2.0
        s_ei = -s_it / 2.0
    elif s_des == "h":
        s_es = 0.0
        s_ei = -s_it
    else:
        fd_s = _fund_dev_shaft(s_des, d)
        if fd_s is None:
            return _err(
                f"Shaft designator {s_des!r} not supported. "
                "Supported: c d f g h js k m n p r s"
            )
        s_es = fd_s
        s_ei = s_es - s_it

    # Housing IT width at OD_mm
    h_it = _it_width(D, h_grade)
    if h_it is None:
        return _err(
            f"IT grade {h_grade} not in supported range IT3-IT11 or nominal size out of range"
        )

    # Housing deviations
    if h_des == "JS":
        h_EI = -h_it / 2.0
        h_ES = h_it / 2.0
    elif h_des == "H":
        h_EI = 0.0
        h_ES = h_it
    else:
        fd_h = _fund_dev_hole(h_des, D)
        if fd_h is None:
            return _err(
                f"Housing designator {h_des!r} not supported. "
                "Supported: A B C D E F G H JS K M N P"
            )
        h_EI = fd_h
        h_ES = h_EI + h_it

    # Fit type classification
    # Shaft seat: es <= 0 → clearance (h has es=0 and is always clearance);
    # ei > 0 → interference; else transition
    if s_es <= 0:
        fit_type_shaft = "clearance"
    elif s_ei > 0:
        fit_type_shaft = "interference"
    else:
        fit_type_shaft = "transition"

    # Housing: EI >= 0 → clearance; ES <= 0 → interference; else transition
    if h_EI >= 0:
        fit_type_housing = "clearance"
    elif h_ES <= 0:
        fit_type_housing = "interference"
    else:
        fit_type_housing = "transition"

    if s_grade > 8:
        warns.append(
            f"Shaft IT{s_grade} is coarser than IT8 — bearing seats normally use IT5-IT7."
        )
    if h_grade > 8:
        warns.append(
            f"Housing IT{h_grade} is coarser than IT8 — bearing seats normally use IT6-IT8."
        )

    return {
        "ok": True,
        "bore_mm": d,
        "OD_mm": D,
        "shaft_fit": shaft_str,
        "housing_fit": housing_str,
        "shaft_es_um": s_es,
        "shaft_ei_um": s_ei,
        "shaft_IT_um": s_it,
        "housing_ES_um": h_ES,
        "housing_EI_um": h_EI,
        "housing_IT_um": h_it,
        "fit_type_shaft": fit_type_shaft,
        "fit_type_housing": fit_type_housing,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# Public function 2: bearing_shoulder_geometry
# ---------------------------------------------------------------------------


def bearing_shoulder_geometry(
    bore_mm: float,
    OD_mm: float,
    B_mm: float,
    bearing_type: str = "ball",
) -> dict:
    """
    Compute recommended shaft shoulder OD and housing lip ID for a bearing seat.

    SKF empirical rules:
      Shaft shoulder height  h_s = max(0.20 * d, r_inner + 0.5)   [ball]
                                   max(0.25 * d, r_inner + 0.5)   [roller]
      Shaft shoulder OD      d_s = d + 2 * h_s
      Housing lip height     h_H = max(0.15 * D, r_outer + 0.5)
      Housing lip ID         D_H = D - 2 * h_H

    Chamfer radii r_min per bore/OD size (SKF catalogue table, simplified).

    Parameters
    ----------
    bore_mm : float
        Bearing bore diameter d (mm). Must be > 0.
    OD_mm : float
        Bearing outer diameter D (mm). Must be > bore_mm.
    B_mm : float
        Bearing width (mm). Must be > 0.
    bearing_type : str
        "ball" (default) or "roller".

    Returns
    -------
    dict
        ok                    : True
        bore_mm               : bearing bore (mm)
        OD_mm                 : bearing OD (mm)
        B_mm                  : bearing width (mm)
        shaft_shoulder_OD_mm  : recommended shaft shoulder outer diameter (mm)
        shaft_shoulder_h_mm   : shaft shoulder height from bore surface (mm)
        housing_lip_ID_mm     : recommended housing lip inner diameter (mm)
        housing_lip_h_mm      : housing lip height inward from OD (mm)
        r_min_inner_mm        : minimum shaft fillet radius (mm)
        r_min_outer_mm        : minimum housing fillet radius (mm)
        bearing_type          : type string used
        warnings              : list of warning strings
    """
    warns: list[str] = []

    err = _guard_positive("bore_mm", bore_mm)
    if err:
        return _err(err)
    err = _guard_positive("OD_mm", OD_mm)
    if err:
        return _err(err)
    err = _guard_positive("B_mm", B_mm)
    if err:
        return _err(err)

    try:
        d = float(bore_mm)
        D = float(OD_mm)
        B = float(B_mm)
    except (TypeError, ValueError) as exc:
        return _err(str(exc))

    if D <= d:
        return _err(f"OD_mm ({OD_mm}) must be > bore_mm ({bore_mm})")

    bt = str(bearing_type).strip().lower()

    # Fillet/chamfer radii (inner = shaft side, outer = housing side)
    if d <= 10:
        r_inner = 0.3
    elif d <= 17:
        r_inner = 0.5
    elif d <= 30:
        r_inner = 1.0
    elif d <= 80:
        r_inner = 1.5
    elif d <= 120:
        r_inner = 2.0
    else:
        r_inner = 2.5

    if D <= 30:
        r_outer = 0.5
    elif D <= 50:
        r_outer = 1.0
    elif D <= 80:
        r_outer = 1.5
    elif D <= 120:
        r_outer = 2.0
    elif D <= 180:
        r_outer = 2.5
    else:
        r_outer = 3.0

    # Shoulder heights
    if bt == "roller":
        h_shaft = max(0.25 * d, r_inner + 0.5)
    elif bt == "ball":
        h_shaft = max(0.20 * d, r_inner + 0.5)
    else:
        warns.append(
            f"bearing_type {bearing_type!r} not recognized — using ball-bearing geometry rules."
        )
        h_shaft = max(0.20 * d, r_inner + 0.5)
        bt = "ball"

    h_housing = max(0.15 * D, r_outer + 0.5)

    # Clamp to physical limits
    if h_shaft > d / 2.0:
        warns.append(
            f"Shaft shoulder height {h_shaft:.2f} mm exceeds bore radius {d / 2:.2f} mm — "
            "geometry inconsistency; check bearing dimensions."
        )
        h_shaft = d / 2.0

    if h_housing > (D - d) / 2.0:
        warns.append(
            f"Housing lip height {h_housing:.2f} mm exceeds wall half-width "
            f"{(D - d) / 2:.2f} mm — geometry inconsistency."
        )
        h_housing = (D - d) / 2.0

    d_shoulder = d + 2.0 * h_shaft
    D_lip = D - 2.0 * h_housing

    if D_lip <= d_shoulder:
        warns.append(
            "Housing lip ID is less than or equal to shaft shoulder OD — "
            "bearing may be inaccessible for assembly/disassembly."
        )

    return {
        "ok": True,
        "bore_mm": d,
        "OD_mm": D,
        "B_mm": B,
        "shaft_shoulder_OD_mm": d_shoulder,
        "shaft_shoulder_h_mm": h_shaft,
        "housing_lip_ID_mm": D_lip,
        "housing_lip_h_mm": h_housing,
        "r_min_inner_mm": r_inner,
        "r_min_outer_mm": r_outer,
        "bearing_type": bt,
        "warnings": warns,
    }
