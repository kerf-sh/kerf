"""
kerf_cad_core.tolfits.fits — ISO 286 limits & fits + Lamé press-fit analysis.

All calculations are pure Python (math module only).
Invalid inputs produce warnings via the ``warnings`` module and return
a result dict with ok=False + reason — functions never raise.

References
----------
ISO 286-1:2010 — Geometrical product specifications (GPS) —
  Limits and fits — Part 1: Bases of tolerances, deviations and fits
ISO 286-2:2010 — Part 2: Tables of standard tolerance grades and limit deviations
Shigley's Mechanical Engineering Design, 10th ed. (Budynas & Nisbett)
  §§ 2-13 to 2-14: interference fits, contact pressure, assembly force
Lamé equations for thick-walled cylinders: σ_hoop = p·r_i²/(r_o²-r_i²)·(1+r_o²/r²)

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings as _warnings
from typing import Any

# ---------------------------------------------------------------------------
# ISO 286-1 size bands (upper bounds, mm)  — Table 2 / annex A
# ---------------------------------------------------------------------------
# Each band is represented as (D_low, D_high) where D_low < nominal <= D_high.
# The geometric mean D = sqrt(D_low * D_high) is used for the tolerance unit.
# Special bands: ≤3 uses D=1, >1000 extends to 3150.
_SIZE_BANDS: list[tuple[float, float]] = [
    (0, 3),
    (3, 6),
    (6, 10),
    (10, 18),
    (18, 30),
    (30, 50),
    (50, 80),
    (80, 120),
    (120, 180),
    (180, 250),
    (250, 315),
    (315, 400),
    (400, 500),
    (500, 630),
    (630, 800),
    (800, 1000),
    (1000, 1250),
    (1250, 1600),
    (1600, 2000),
    (2000, 2500),
    (2500, 3150),
]


def _band_for(D_mm: float) -> tuple[float, float]:
    """Return the ISO 286 size band (D_low, D_high) for a nominal diameter."""
    for lo, hi in _SIZE_BANDS:
        if lo < D_mm <= hi:
            return (lo, hi)
    # D <= 0 or > 3150 — caller handles
    raise ValueError(f"nominal size {D_mm} mm is out of ISO 286 range (0 < D ≤ 3150)")


def _mean_diameter(lo: float, hi: float) -> float:
    """Geometric mean diameter for the size band, per ISO 286-1 §4.1."""
    if lo == 0:
        # For the ≤3 band the standard uses D = 1 mm for the unit formula
        return 1.0
    return math.sqrt(lo * hi)


def _tolerance_unit_i(D_mm: float) -> float:
    """
    Standard tolerance unit i (µm) for sizes ≤ 500 mm.
    ISO 286-1 eq. (1):  i = 0.45·D^(1/3) + 0.001·D     (D in mm, i in µm)
    For D > 500 mm use ISO large-size formula:
      I = 0.004·D + 2.1    (µm)
    """
    if D_mm <= 500:
        return 0.45 * (D_mm ** (1.0 / 3.0)) + 0.001 * D_mm
    else:
        return 0.004 * D_mm + 2.1


# ---------------------------------------------------------------------------
# IT tolerance grade multipliers  (ISO 286-1 Table 1)
# IT values are expressed as multiples of i (or I for > 500 mm).
# For IT01..IT1 special formulas apply.
# ---------------------------------------------------------------------------
# IT grade → multiplier of tolerance unit i  (IT5..IT18)
_IT_MULTIPLIER: dict[str, int] = {
    "IT5":  7,
    "IT6":  10,
    "IT7":  16,
    "IT8":  25,
    "IT9":  40,
    "IT10": 64,
    "IT11": 100,
    "IT12": 160,
    "IT13": 250,
    "IT14": 400,
    "IT15": 640,
    "IT16": 1000,
    "IT17": 1600,
    "IT18": 2500,
}

# Special grades (µm) — ISO 286-1 Table 1, sizes ≤ 500 mm
# These are direct values from Table 1 for each size band:
# IT01, IT0, IT1 are given as fixed values per band (µm)
# IT1 = 2i + 0 (but per standard table for common bands ≤ 500)
# For simplicity we compute per formula:
#   IT01 = 0.3 + 0.008·D  µm
#   IT0  = 0.5 + 0.012·D  µm
#   IT1  = 0.8 + 0.020·D  µm  (approximate — standard gives rounding)
# IT2 = IT1·(IT5/IT1)^(1/3)  ≈ 1.26·IT1
# IT3 ≈ 2·IT1,  IT4 ≈ 3.2·IT1  (rounding applied)

def _it_special(grade: str, D_mm: float) -> float:
    """Return IT tolerance in µm for grades IT01–IT4 and D ≤ 500 mm."""
    if grade == "IT01":
        return 0.3 + 0.008 * D_mm
    if grade == "IT0":
        return 0.5 + 0.012 * D_mm
    if grade == "IT1":
        return 0.8 + 0.020 * D_mm
    i = _tolerance_unit_i(D_mm)
    if grade == "IT2":
        it1 = 0.8 + 0.020 * D_mm
        return it1 * (7.0 / (0.8 + 0.020 * D_mm)) ** (1.0 / 3.0) if D_mm > 0 else 1.26 * it1
    if grade == "IT3":
        return 2.0 * (0.8 + 0.020 * D_mm)
    if grade == "IT4":
        return 3.2 * (0.8 + 0.020 * D_mm)
    raise ValueError(grade)


_VALID_GRADES = (
    "IT01", "IT0",
    "IT1", "IT2", "IT3", "IT4",
    "IT5", "IT6", "IT7", "IT8", "IT9",
    "IT10", "IT11", "IT12", "IT13", "IT14",
    "IT15", "IT16", "IT17", "IT18",
)


def it_tolerance(nominal_mm: float, grade: str) -> dict[str, Any]:
    """
    Return the standard IT tolerance value for a given nominal size and grade.

    Parameters
    ----------
    nominal_mm : float
        Nominal size in mm (0 < nominal_mm ≤ 3150).
    grade : str
        Tolerance grade string: 'IT01', 'IT0', 'IT1' … 'IT18'.

    Returns
    -------
    dict with keys:
        ok          : bool
        grade       : str
        nominal_mm  : float
        band_lo_mm  : float
        band_hi_mm  : float
        D_mean_mm   : float — geometric mean of band
        i_um        : float — tolerance unit in µm
        IT_um       : float — IT tolerance value in µm
        IT_mm       : float — IT tolerance value in mm
        warnings    : list[str]
    """
    warns: list[str] = []
    grade = grade.strip().upper()

    if grade not in _VALID_GRADES:
        _warnings.warn(f"tolfits: unknown grade '{grade}'")
        return {"ok": False, "reason": f"unknown grade '{grade}'; valid: {_VALID_GRADES}"}

    if not isinstance(nominal_mm, (int, float)) or nominal_mm <= 0 or nominal_mm > 3150:
        _warnings.warn(f"tolfits: nominal_mm={nominal_mm} out of range")
        return {"ok": False, "reason": "nominal_mm must be in (0, 3150]"}

    try:
        lo, hi = _band_for(nominal_mm)
    except ValueError as exc:
        _warnings.warn(str(exc))
        return {"ok": False, "reason": str(exc)}

    D = _mean_diameter(lo, hi)
    i_um = _tolerance_unit_i(D)

    if grade in ("IT01", "IT0", "IT1", "IT2", "IT3", "IT4"):
        if nominal_mm > 500:
            warns.append(
                f"Grade {grade} is not defined in ISO 286-1 for D > 500 mm; "
                "extrapolating using formula."
            )
            for w in warns:
                _warnings.warn(f"tolfits: {w}")
        IT_um = _it_special(grade, D)
    else:
        mult = _IT_MULTIPLIER[grade]
        IT_um = mult * i_um

    # ISO 286-1: all IT grades IT5 and coarser are rounded to the nearest 1 µm.
    # Only IT01–IT4 retain sub-µm precision (given as fractional µm in the standard).
    if grade not in ("IT01", "IT0", "IT1", "IT2", "IT3", "IT4"):
        IT_um = round(IT_um)
    else:
        IT_um = round(IT_um, 3)

    for w in warns:
        _warnings.warn(f"tolfits: {w}")

    return {
        "ok": True,
        "grade": grade,
        "nominal_mm": nominal_mm,
        "band_lo_mm": lo,
        "band_hi_mm": hi,
        "D_mean_mm": D,
        "i_um": round(i_um, 4),
        "IT_um": IT_um,
        "IT_mm": IT_um / 1000.0,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# Fundamental deviations  (ISO 286-1 §4.2 / Tables 3 & 4)
# ---------------------------------------------------------------------------
# Shaft designations: a b c cd d e ef f fg g h js j k m n p r s t u v x y z za zb zc
# Hole designations:  A B C CD D E EF F FG G H JS J K M N P R S T U V X Y Z ZA ZB ZC
#
# The fundamental deviation (EI for holes, es for shafts) is the limit
# closest to the zero line.
#
# Implementation strategy:
#   - Shafts a–h: upper deviation (es) is negative (shaft below zero line)
#   - Shaft h: es = 0 (reference shaft)
#   - Shafts js: ei = -IT/2, es = +IT/2
#   - Shafts j–zc: lower deviation (ei) positive (shaft above zero line)
#   - Holes A–H: EI = -es of corresponding shaft (basic hole / shaft duality)
#   - Hole H: EI = 0 (reference hole)
#   - Holes JS–ZC symmetric
#
# Deviation formulas from ISO 286-1 Annex B (µm unless otherwise noted).
# D is the geometric mean diameter of the size band (mm).

def _shaft_es(code: str, D_mm: float, IT_um: float) -> float | None:
    """
    Upper deviation (es) for shaft codes a–h (negative or zero, in µm).
    Returns None if code is not in a–h range.
    """
    c = code.lower()
    # Reference shaft
    if c == "h":
        return 0.0

    # ---- ISO 286-1 Table 3 formulas ----
    if c == "a":
        if D_mm <= 120:
            return -(265 + 1.3 * D_mm)
        else:
            return -(3.5 * D_mm)
    if c == "b":
        if D_mm <= 160:
            return -(140 + 0.85 * D_mm)
        else:
            return -(1.8 * D_mm)
    if c == "c":
        if D_mm <= 40:
            return -(52.0 * (D_mm ** 0.2))
        else:
            return -(15 + 1.2 * D_mm)
    if c == "cd":
        # geometric mean of c and d deviations (special designation)
        es_c = _shaft_es("c", D_mm, IT_um)
        es_d = _shaft_es("d", D_mm, IT_um)
        if es_c is None or es_d is None:
            return None
        return math.sqrt(abs(es_c) * abs(es_d)) * -1.0
    if c == "d":
        return -(16.0 * (D_mm ** 0.44))
    if c == "e":
        return -(11.0 * (D_mm ** 0.41))
    if c == "ef":
        es_e = _shaft_es("e", D_mm, IT_um)
        es_f = _shaft_es("f", D_mm, IT_um)
        if es_e is None or es_f is None:
            return None
        return math.sqrt(abs(es_e) * abs(es_f)) * -1.0
    if c == "f":
        return -(5.5 * (D_mm ** 0.41))
    if c == "fg":
        es_f = _shaft_es("f", D_mm, IT_um)
        es_g = _shaft_es("g", D_mm, IT_um)
        if es_f is None or es_g is None:
            return None
        return math.sqrt(abs(es_f) * abs(es_g)) * -1.0
    if c == "g":
        return -(2.5 * (D_mm ** 0.34))
    return None


# ---------------------------------------------------------------------------
# ISO 286-1:2010 fundamental deviations for shafts j..zc (lower deviation ei,
# positive, in µm).  The fundamental deviation is GRADE-INDEPENDENT — it is the
# deviation of the toleranced feature closest to the zero line and is defined
# directly per nominal-size band (ISO 286-1 §5.6, Table 8).
#
# Values below are the authoritative ISO 286-1:2010 Table 8 fundamental
# deviations (verified against ISO 286-2 limit-deviation tables, e.g.
# p6 Ø50 = +26 µm, s6 Ø50 = +43 µm, u6 Ø50 = +70 µm).
#
# Keyed by the upper bound of the nominal-size band (mm).  ei in µm.
# None = the code is not standardised for that band in ISO 286-1.
# ---------------------------------------------------------------------------

# Band upper bounds (mm) — must align with _SIZE_BANDS for D ≤ 500.
_FD_BANDS: list[float] = [3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500]

# ISO 286-1:2010 Table 8 — shaft fundamental deviation ei (µm) per band.
# Order of values matches _FD_BANDS.
_SHAFT_FD_EI: dict[str, list[float | None]] = {
    #          ≤3   ≤6  ≤10 ≤18 ≤30  ≤50  ≤80  ≤120 ≤180 ≤250 ≤315 ≤400 ≤500
    "n":   [   4,   8,  10,  12,  15,  17,  20,   23,   27,   31,   34,   37,   40],
    "p":   [   6,  12,  15,  18,  22,  26,  32,   37,   43,   50,   56,   62,   68],
    "r":   [  10,  15,  19,  23,  28,  34,  41,   51,   63,   77,   91,  101,  111],
    "s":   [  14,  19,  23,  28,  35,  43,  53,   71,   92,  117,  151,  183,  223],
    "t":   [None,None,None,None,  41,  54,  66,   91,  122,  166,  207,  251,  295],
    "u":   [  18,  23,  28,  33,  48,  70,  87,  124,  170,  236,  306,  378,  460],
    "v":   [None,None,None,  39,  47,  68,  90,  136,  188,  258,  340,  430,  524],
    "x":   [  20,  28,  34,  45,  64,  97, 144,  216,  300,  425,  590,  790, 1000],
    "y":   [None,None,None,None,  76, 122, 174,  274,  385,  550,  750,  990, 1250],
    "z":   [  26,  35,  42,  60,  88, 136, 218,  336,  468,  672,  900, 1200, 1500],
    "za":  [  32,  42,  52,  77, 118, 187, 274,  427,  608,  877, 1200, 1550, 1850],
    "zb":  [  40,  50,  67,  97, 148, 237, 369,  587,  830, 1200, 1500, 1850, 2400],
    "zc":  [  60,  80,  97, 130, 188, 297, 469,  747, 1100, 1500, 1850, 2400, 3000],
}


def _fd_band_index(D_mm: float) -> int | None:
    """Index into _FD_BANDS for the band containing D_mm (band upper bounds)."""
    for i, hi in enumerate(_FD_BANDS):
        if D_mm <= hi:
            return i
    return None


def _shaft_ei_positive(code: str, D_mm: float, IT_um: float) -> float | None:
    """
    Lower deviation (ei) for shaft codes k–zc (positive, in µm), per
    ISO 286-1:2010 Table 8.  The fundamental deviation is grade-independent.

    Shaft j / js are handled separately in shaft_limits().
    Returns None if the code is not standardised for this size band.

    References
    ----------
    ISO 286-1:2010 §5.6 and Table 8 (fundamental deviations for shafts).
    """
    c = code.lower()
    if c in ("j", "js"):
        return None  # handled separately

    idx = _fd_band_index(D_mm)
    if idx is None:
        return None

    if c == "k":
        # ISO 286-1 Table 8: k4..k7  ei = +0.6 · ∛D  (rounded).
        # For grades outside IT4..IT7, k FD = 0 (handled by caller's grade rule).
        if D_mm <= 3:
            return 0.0
        return round(0.6 * (D_mm ** (1.0 / 3.0)))
    if c == "m":
        # ISO 286-1 Table 8: m FD = +(IT7 − IT6) for the band.
        i = _tolerance_unit_i(D_mm)
        it7 = round(16.0 * i)
        it6 = round(10.0 * i)
        return float(it7 - it6)

    table = _SHAFT_FD_EI.get(c)
    if table is None:
        return None
    val = table[idx]
    if val is None:
        return None
    return float(val)


# All valid shaft letter codes (lowercase)
_SHAFT_CODES_LOWER = frozenset([
    "a", "b", "c", "cd", "d", "e", "ef", "f", "fg", "g", "h", "js", "j",
    "k", "m", "n", "p", "r", "s", "t", "u", "v", "x", "y", "z", "za", "zb", "zc",
])

# Corresponding hole codes (uppercase)
_HOLE_CODES_UPPER = frozenset(c.upper() for c in _SHAFT_CODES_LOWER)


def _parse_designation(designation: str) -> tuple[str, str]:
    """
    Parse a tolerance designation like 'H7', 'g6', 'JS5', 'zc4'.
    Returns (letter_code, grade_str).
    grade_str will be like 'IT7', 'IT6' etc.
    """
    d = designation.strip()
    # Find where the numeric part begins (first digit after the letter code)
    i = 0
    while i < len(d) and not d[i].isdigit():
        i += 1
    code = d[:i]
    grade_num = d[i:]
    if not code or not grade_num:
        raise ValueError(f"cannot parse designation '{designation}'; expected like 'H7' or 'g6'")
    # Grade 01 → IT01, 0 → IT0, 1–18 → IT1..IT18
    try:
        g = int(grade_num)
    except ValueError:
        raise ValueError(f"non-integer grade in '{designation}'")
    if g == -1:  # hack for IT01
        grade = "IT01"
    elif g == 0:
        grade = "IT0"
    else:
        grade = f"IT{g}"
    return code, grade


def shaft_limits(nominal_mm: float, designation: str) -> dict[str, Any]:
    """
    Compute upper (es) and lower (ei) shaft deviations per ISO 286-1.

    Parameters
    ----------
    nominal_mm : float  — nominal shaft diameter (mm)
    designation : str   — tolerance designation e.g. 'g6', 'h7', 'k6', 's7'

    Returns
    -------
    dict with keys:
        ok              : bool
        designation     : str
        nominal_mm      : float
        code            : str   — letter code (lowercase)
        grade           : str   — e.g. 'IT6'
        IT_um           : float — IT tolerance in µm
        IT_mm           : float
        es_um           : float — upper shaft deviation (µm)
        ei_um           : float — lower shaft deviation (µm)
        upper_limit_mm  : float — nominal + es_mm
        lower_limit_mm  : float — nominal + ei_mm
        warnings        : list[str]
    """
    warns: list[str] = []
    try:
        code, grade = _parse_designation(designation)
    except ValueError as exc:
        _warnings.warn(str(exc))
        return {"ok": False, "reason": str(exc)}

    code_lower = code.lower()
    if code_lower not in _SHAFT_CODES_LOWER:
        msg = f"unknown shaft code '{code}'; valid codes: {sorted(_SHAFT_CODES_LOWER)}"
        _warnings.warn(f"tolfits: {msg}")
        return {"ok": False, "reason": msg}

    # Check it's actually a shaft code (lowercase), not a hole code
    if code != code_lower:
        msg = f"'{designation}' appears to be a hole designation; use hole_limits() instead"
        _warnings.warn(f"tolfits: {msg}")
        return {"ok": False, "reason": msg}

    it_result = it_tolerance(nominal_mm, grade)
    if not it_result["ok"]:
        return it_result

    IT_um = it_result["IT_um"]
    D = it_result["D_mean_mm"]

    if code_lower == "js":
        # Symmetric about zero line
        es_um = IT_um / 2.0
        ei_um = -IT_um / 2.0
        # For odd IT values, ISO rounds es up
        if IT_um % 2 != 0:
            es_um = math.ceil(IT_um / 2.0)
            ei_um = -(IT_um - es_um)
    elif code_lower == "j":
        # ISO 286-1 special case: j is only defined for grades IT5..IT8.
        # Approximation: es_j is a small positive value, ei_j = es_j - IT
        # From standard tables: j5 Ø25: es=+6, ei=-4 (IT5=9µm)
        # j6 Ø25: es=+8, ei=-5 (IT6=13µm, sum=13) — actually es+|ei|=IT
        # Common approximation: es_j ≈ IT5_for_size
        IT5_um = 7.0 * _tolerance_unit_i(D)
        es_um = round(IT5_um * 0.6)
        ei_um = es_um - IT_um
        if grade not in ("IT5", "IT6", "IT7", "IT8"):
            warns.append(
                f"Shaft 'j' is only defined for IT5–IT8 in ISO 286-1; "
                f"extrapolating for {grade}."
            )
    elif code_lower in ("a", "b", "c", "cd", "d", "e", "ef", "f", "fg", "g", "h"):
        es_um_raw = _shaft_es(code_lower, D, IT_um)
        if es_um_raw is None:
            return {"ok": False, "reason": f"cannot compute es for shaft '{code}'"}
        es_um = round(es_um_raw)
        ei_um = es_um - IT_um
    elif code_lower == "k":
        # ISO 286-1 §5.6: shaft k fundamental deviation ei = +0.6·∛D applies
        # only to grades IT4..IT7.  For all other grades k FD = 0.
        grade_num = int(grade[2:])  # e.g. IT6 → 6
        if 4 <= grade_num <= 7:
            ei_um = float(_shaft_ei_positive("k", D, IT_um) or 0.0)
        else:
            ei_um = 0.0
        es_um = ei_um + IT_um
    elif code_lower == "m":
        # ISO 286-1 Table 8: shaft m fundamental deviation ei = +(IT7 − IT6).
        ei_um = float(_shaft_ei_positive("m", D, IT_um) or 0.0)
        es_um = ei_um + IT_um
    elif code_lower == "n":
        ei_um_raw = _shaft_ei_positive("n", D, IT_um)
        if ei_um_raw is None:
            return {"ok": False, "reason": f"cannot compute ei for shaft '{code}'"}
        ei_um = float(ei_um_raw)
        es_um = ei_um + IT_um
    else:
        # p, r, s, t, u, v, x, y, z, za, zb, zc
        ei_um_raw = _shaft_ei_positive(code_lower, D, IT_um)
        if ei_um_raw is None:
            return {"ok": False, "reason": f"cannot compute ei for shaft '{code}'"}
        ei_um = float(ei_um_raw)
        es_um = ei_um + IT_um

    for w in warns:
        _warnings.warn(f"tolfits: {w}")

    return {
        "ok": True,
        "designation": designation,
        "nominal_mm": nominal_mm,
        "code": code_lower,
        "grade": grade,
        "IT_um": IT_um,
        "IT_mm": IT_um / 1000.0,
        "es_um": es_um,
        "ei_um": ei_um,
        "upper_limit_mm": nominal_mm + es_um / 1000.0,
        "lower_limit_mm": nominal_mm + ei_um / 1000.0,
        "warnings": warns,
    }


def hole_limits(nominal_mm: float, designation: str) -> dict[str, Any]:
    """
    Compute upper (ES) and lower (EI) hole deviations per ISO 286-1.

    Uses the principle of duality: EI_hole = -es_shaft for most codes.
    Hole H: EI = 0, ES = +IT (reference hole system).

    Parameters
    ----------
    nominal_mm  : float — nominal hole diameter (mm)
    designation : str   — e.g. 'H7', 'F8', 'K6', 'N7', 'P6'

    Returns
    -------
    dict with keys:
        ok              : bool
        designation     : str
        nominal_mm      : float
        code            : str   — letter code (uppercase)
        grade           : str
        IT_um           : float
        IT_mm           : float
        EI_um           : float — lower hole deviation (µm)
        ES_um           : float — upper hole deviation (µm)
        upper_limit_mm  : float
        lower_limit_mm  : float
        warnings        : list[str]
    """
    warns: list[str] = []
    try:
        code, grade = _parse_designation(designation)
    except ValueError as exc:
        _warnings.warn(str(exc))
        return {"ok": False, "reason": str(exc)}

    code_upper = code.upper()
    if code_upper not in _HOLE_CODES_UPPER:
        msg = f"unknown hole code '{code}'; valid codes: {sorted(_HOLE_CODES_UPPER)}"
        _warnings.warn(f"tolfits: {msg}")
        return {"ok": False, "reason": msg}

    # Check it's actually a hole code (uppercase); lowercase → suggest shaft_limits
    if code != code_upper:
        msg = f"'{designation}' appears to be a shaft designation; use shaft_limits() instead"
        _warnings.warn(f"tolfits: {msg}")
        return {"ok": False, "reason": msg}

    it_result = it_tolerance(nominal_mm, grade)
    if not it_result["ok"]:
        return it_result

    IT_um = it_result["IT_um"]
    D = it_result["D_mean_mm"]
    code_lower = code_upper.lower()

    # Reference hole H: EI = 0
    if code_upper == "H":
        EI_um = 0.0
        ES_um = IT_um
    elif code_upper == "JS":
        ES_um = IT_um / 2.0
        EI_um = -IT_um / 2.0
        if IT_um % 2 != 0:
            ES_um = math.ceil(IT_um / 2.0)
            EI_um = -(IT_um - ES_um)
    elif code_upper in ("A", "B", "C", "CD", "D", "E", "EF", "F", "FG", "G"):
        # Hole duality: EI_hole = -es_shaft  (shaft a..g have negative es)
        es_raw = _shaft_es(code_lower, D, IT_um)
        if es_raw is None:
            return {"ok": False, "reason": f"cannot compute EI for hole '{code}'"}
        EI_um = -round(es_raw)  # es is negative → EI is positive
        ES_um = EI_um + IT_um
    elif code_upper == "J":
        # Hole J: EI and ES symmetric around zero approximately
        # Duality from shaft j
        IT5_um = 7.0 * _tolerance_unit_i(D)
        es_j = round(IT5_um * 0.6)
        ei_j = es_j - IT_um
        # Hole duality: ES_hole = -ei_shaft, EI_hole = -es_shaft
        ES_um = float(-ei_j)
        EI_um = float(-es_j)
    elif code_upper == "K":
        # Hole K: ES = 0 for IT ≤ IT8 (approximately), EI = -IT
        grade_num = int(grade[2:])
        if grade_num <= 8:
            ES_um = 0.0
        else:
            ES_um = -round(16.0 * _tolerance_unit_i(D))  # coarser grades shift negative
        EI_um = ES_um - IT_um
    elif code_upper == "M":
        # Hole M: duality from shaft m (ISO 286-1 Table 8: m ei = IT7 − IT6).
        ei_m = float(_shaft_ei_positive("m", D, IT_um) or 0.0)
        es_m = ei_m + IT_um
        # Duality: ES_hole = -ei_shaft, EI_hole = -es_shaft
        ES_um = float(-ei_m)
        EI_um = float(-es_m)
    elif code_upper == "N":
        ei_n = _shaft_ei_positive("n", D, IT_um)
        if ei_n is None:
            return {"ok": False, "reason": f"cannot compute deviations for hole '{code}'"}
        es_n = float(ei_n) + IT_um
        ES_um = -float(ei_n)
        EI_um = -es_n
    elif code_upper in ("P", "R", "S", "T", "U", "V", "X", "Y", "Z", "ZA", "ZB", "ZC"):
        # Hole–shaft duality: ES_hole = -ei_shaft, EI_hole = -es_shaft
        # But for P..ZC: ISO 286-1 §4.2.3 defines a Δ correction for holes ≥ IT7.
        # Delta = IT_grade - IT_grade_for_IT7  (i.e. difference between the
        # current grade and IT7 for the same size).  This shifts ES up slightly.
        ei_s = _shaft_ei_positive(code_lower, D, IT_um)
        if ei_s is None:
            return {"ok": False, "reason": f"cannot compute deviations for hole '{code}'"}
        es_s = float(ei_s) + IT_um

        # Apply Δ correction (ISO 286-1 §4.2.3, applies to P–ZC for holes > IT8)
        grade_num = int(grade[2:])
        if grade_num >= 8 and code_upper != "P":
            IT7_um = 16.0 * _tolerance_unit_i(D)
            delta_um = round(IT_um - IT7_um)
            delta_um = max(delta_um, 0)
        elif grade_num >= 8 and code_upper == "P":
            IT7_um = 16.0 * _tolerance_unit_i(D)
            delta_um = round(IT_um - IT7_um)
            delta_um = max(delta_um, 0)
        else:
            delta_um = 0.0

        ES_um = -float(ei_s) + delta_um
        EI_um = ES_um - IT_um
    else:
        return {"ok": False, "reason": f"unhandled hole code '{code}'"}

    for w in warns:
        _warnings.warn(f"tolfits: {w}")

    return {
        "ok": True,
        "designation": designation,
        "nominal_mm": nominal_mm,
        "code": code_upper,
        "grade": grade,
        "IT_um": IT_um,
        "IT_mm": IT_um / 1000.0,
        "EI_um": EI_um,
        "ES_um": ES_um,
        "upper_limit_mm": nominal_mm + ES_um / 1000.0,
        "lower_limit_mm": nominal_mm + EI_um / 1000.0,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# Fit analysis
# ---------------------------------------------------------------------------

def fit_analysis(
    nominal_mm: float,
    hole_desig: str,
    shaft_desig: str,
) -> dict[str, Any]:
    """
    Compute fit classification and clearance / interference limits.

    Fits are classified per ISO 286-2:
      - Clearance fit   : min_clearance >= 0  (shaft always smaller than hole)
      - Interference fit: max_clearance <= 0  (shaft always larger than hole)
      - Transition fit  : min_clearance < 0 < max_clearance

    Clearance = hole_size - shaft_size.
    Positive clearance → shaft fits inside hole with play.
    Negative clearance → interference (shaft must be pressed in).

    Parameters
    ----------
    nominal_mm  : float — nominal diameter (mm)
    hole_desig  : str   — hole designation e.g. 'H7'
    shaft_desig : str   — shaft designation e.g. 'g6', 'k6', 's6'

    Returns
    -------
    dict with keys:
        ok                      : bool
        nominal_mm              : float
        hole_designation        : str
        shaft_designation       : str
        hole_upper_limit_mm     : float
        hole_lower_limit_mm     : float
        shaft_upper_limit_mm    : float
        shaft_lower_limit_mm    : float
        max_clearance_mm        : float  (positive → clearance; negative → interference)
        min_clearance_mm        : float
        max_interference_mm     : float  (positive when there is interference)
        min_interference_mm     : float
        fit_type                : str    — 'clearance' | 'transition' | 'interference'
        warnings                : list[str]
    """
    h = hole_limits(nominal_mm, hole_desig)
    if not h["ok"]:
        return {"ok": False, "reason": f"hole error: {h['reason']}"}

    s = shaft_limits(nominal_mm, shaft_desig)
    if not s["ok"]:
        return {"ok": False, "reason": f"shaft error: {s['reason']}"}

    # max clearance = largest hole - smallest shaft
    max_clearance = h["upper_limit_mm"] - s["lower_limit_mm"]
    # min clearance = smallest hole - largest shaft
    min_clearance = h["lower_limit_mm"] - s["upper_limit_mm"]

    if min_clearance >= 0:
        fit_type = "clearance"
    elif max_clearance <= 0:
        fit_type = "interference"
    else:
        fit_type = "transition"

    max_interference = -min_clearance
    min_interference = -max_clearance

    warns = h.get("warnings", []) + s.get("warnings", [])
    return {
        "ok": True,
        "nominal_mm": nominal_mm,
        "hole_designation": hole_desig,
        "shaft_designation": shaft_desig,
        "hole_upper_limit_mm": h["upper_limit_mm"],
        "hole_lower_limit_mm": h["lower_limit_mm"],
        "shaft_upper_limit_mm": s["upper_limit_mm"],
        "shaft_lower_limit_mm": s["lower_limit_mm"],
        "max_clearance_mm": round(max_clearance, 6),
        "min_clearance_mm": round(min_clearance, 6),
        "max_interference_mm": round(max_interference, 6),
        "min_interference_mm": round(min_interference, 6),
        "fit_type": fit_type,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# Preferred fits (ISO 286-2 Table 1 — shaft-basis and hole-basis systems)
# ---------------------------------------------------------------------------

# ISO 286-2 preferred fits (hole-basis system).
# Each entry: (hole_desig, shaft_desig, fit_name, fit_type)
_PREFERRED_FITS_HOLE_BASIS: list[tuple[str, str, str, str]] = [
    ("H11", "c11", "Loose running",        "clearance"),
    ("H9",  "d9",  "Free running",          "clearance"),
    ("H8",  "f7",  "Close running",         "clearance"),
    ("H7",  "g6",  "Sliding",               "clearance"),
    ("H7",  "h6",  "Locational clearance",  "clearance"),
    ("H7",  "k6",  "Locational transition", "transition"),
    ("H7",  "n6",  "Locational transition", "transition"),
    ("H7",  "p6",  "Locational interference","interference"),
    ("H7",  "s6",  "Medium drive",          "interference"),
    ("H7",  "u6",  "Force fit",             "interference"),
]

# Shaft-basis system preferred fits
_PREFERRED_FITS_SHAFT_BASIS: list[tuple[str, str, str, str]] = [
    ("C11", "h11", "Loose running",         "clearance"),
    ("D9",  "h9",  "Free running",          "clearance"),
    ("F8",  "h7",  "Close running",         "clearance"),
    ("G7",  "h6",  "Sliding",               "clearance"),
    ("H7",  "h6",  "Locational clearance",  "clearance"),
    ("K7",  "h6",  "Locational transition", "transition"),
    ("N7",  "h6",  "Locational transition", "transition"),
    ("P7",  "h6",  "Locational interference","interference"),
    ("S7",  "h6",  "Medium drive",          "interference"),
    ("U7",  "h6",  "Force fit",             "interference"),
]


def preferred_fits(
    nominal_mm: float | None = None,
    system: str = "hole-basis",
    fit_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Return ISO 286-2 preferred fit designations with computed limits.

    Parameters
    ----------
    nominal_mm  : float | None — if provided, compute actual clearance / interference
    system      : str          — 'hole-basis' (default) or 'shaft-basis'
    fit_types   : list[str]    — filter by fit type(s): 'clearance', 'transition',
                                  'interference'; None = return all

    Returns
    -------
    dict with keys:
        ok          : bool
        system      : str
        nominal_mm  : float | None
        fits        : list[dict]  — each has hole, shaft, name, expected_type,
                                    and (if nominal provided) computed fit analysis
        warnings    : list[str]
    """
    warns: list[str] = []
    system = system.strip().lower()
    if system not in ("hole-basis", "shaft-basis"):
        return {"ok": False, "reason": "system must be 'hole-basis' or 'shaft-basis'"}

    table = (
        _PREFERRED_FITS_HOLE_BASIS
        if system == "hole-basis"
        else _PREFERRED_FITS_SHAFT_BASIS
    )

    if fit_types is not None:
        valid_types = {"clearance", "transition", "interference"}
        bad = set(fit_types) - valid_types
        if bad:
            return {"ok": False, "reason": f"unknown fit_types: {sorted(bad)}"}
        table = [r for r in table if r[3] in fit_types]

    fits = []
    for hole_d, shaft_d, name, expected_type in table:
        entry: dict[str, Any] = {
            "hole": hole_d,
            "shaft": shaft_d,
            "name": name,
            "expected_type": expected_type,
        }
        if nominal_mm is not None:
            fa = fit_analysis(nominal_mm, hole_d, shaft_d)
            entry["analysis"] = fa
            if fa.get("ok"):
                entry["fit_type_computed"] = fa["fit_type"]
                entry["max_clearance_mm"] = fa["max_clearance_mm"]
                entry["min_clearance_mm"] = fa["min_clearance_mm"]
        fits.append(entry)

    for w in warns:
        _warnings.warn(f"tolfits: {w}")

    return {
        "ok": True,
        "system": system,
        "nominal_mm": nominal_mm,
        "fits": fits,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# Lamé thick-cylinder press-fit / interference analysis
# ---------------------------------------------------------------------------

def press_fit(
    nominal_mm: float,
    interference_mm: float,
    hub_outer_mm: float,
    shaft_bore_mm: float = 0.0,
    E_hub_Pa: float = 200e9,
    E_shaft_Pa: float = 200e9,
    nu_hub: float = 0.3,
    nu_shaft: float = 0.3,
    mu_friction: float = 0.12,
    length_mm: float | None = None,
    yield_strength_hub_Pa: float | None = None,
    yield_strength_shaft_Pa: float | None = None,
    delta_T_C: float | None = None,
    alpha_hub: float = 12e-6,
    alpha_shaft: float = 12e-6,
) -> dict[str, Any]:
    """
    Lamé thick-cylinder interference / press-fit analysis.

    Computes:
      - Contact (interface) pressure p_c from the interference δ
      - Assembly (press-in) force F_a
      - Hoop stress at inner and outer radius of hub and shaft
      - Temperature differential for shrink fit (δ accommodated thermally)
      - Overstress warnings vs yield strengths

    Geometry
    --------
        shaft_bore_mm  — inner bore of the shaft (0 for solid shaft)
        nominal_mm     — nominal interface diameter (= outer shaft dia = inner hub dia)
        hub_outer_mm   — outer diameter of hub

    Sign convention: interference_mm > 0 means shaft is larger than hole
    (i.e. interference = shaft_d - hole_d > 0, typical for press fits).

    References
    ----------
    Shigley's MED 10th ed. §2-13, eq. (2-57)–(2-62)
    Lamé equations: σ_r = A - B/r², σ_θ = A + B/r²

    Parameters
    ----------
    nominal_mm          : float — interface diameter (mm)
    interference_mm     : float — total diametral interference δ (mm, must be ≥ 0)
    hub_outer_mm        : float — hub outer diameter (mm, must be > nominal_mm)
    shaft_bore_mm       : float — shaft inner bore diameter (0 = solid, default 0)
    E_hub_Pa            : float — hub Young's modulus (Pa, default 200 GPa steel)
    E_shaft_Pa          : float — shaft Young's modulus (Pa, default 200 GPa steel)
    nu_hub              : float — hub Poisson's ratio (default 0.3)
    nu_shaft            : float — shaft Poisson's ratio (default 0.3)
    mu_friction         : float — coefficient of friction (default 0.12)
    length_mm           : float | None — interface length (mm); required for force calc
    yield_strength_hub_Pa   : float | None — hub yield strength; if provided, overstress checked
    yield_strength_shaft_Pa : float | None — shaft yield strength; if provided, overstress checked
    delta_T_C           : float | None — not used as input; if None, shrink-fit temp is computed
    alpha_hub           : float — hub linear thermal expansion coefficient (1/°C, default 12e-6)
    alpha_shaft         : float — shaft linear expansion coefficient (1/°C, default 12e-6)

    Returns
    -------
    dict with keys:
        ok                          : bool
        nominal_mm                  : float
        interference_mm             : float
        contact_pressure_Pa         : float
        contact_pressure_MPa        : float
        hub_hoop_stress_inner_Pa    : float  (tensile, at interface)
        hub_hoop_stress_outer_Pa    : float  (tensile, at outer radius)
        shaft_hoop_stress_inner_Pa  : float  (compressive for solid shaft)
        shaft_hoop_stress_outer_Pa  : float  (= contact pressure for outer = interface)
        assembly_force_N            : float | None  (None if length not provided)
        shrink_fit_delta_T_C        : float   (temp differential for thermal assembly)
        hub_overstressed            : bool
        shaft_overstressed          : bool
        warnings                    : list[str]
    """
    warns: list[str] = []

    # --- Validate inputs ---
    if nominal_mm <= 0:
        _warnings.warn("tolfits: press_fit: nominal_mm must be > 0")
        return {"ok": False, "reason": "nominal_mm must be > 0"}
    if interference_mm < 0:
        _warnings.warn("tolfits: press_fit: interference_mm must be >= 0")
        return {"ok": False, "reason": "interference_mm must be >= 0"}
    if hub_outer_mm <= nominal_mm:
        _warnings.warn("tolfits: press_fit: hub_outer_mm must be > nominal_mm")
        return {"ok": False, "reason": "hub_outer_mm must be > nominal_mm"}
    if shaft_bore_mm < 0:
        _warnings.warn("tolfits: press_fit: shaft_bore_mm must be >= 0")
        return {"ok": False, "reason": "shaft_bore_mm must be >= 0"}
    if shaft_bore_mm >= nominal_mm:
        _warnings.warn("tolfits: press_fit: shaft_bore_mm must be < nominal_mm")
        return {"ok": False, "reason": "shaft_bore_mm must be < nominal_mm (shaft inner < interface dia)"}
    if E_hub_Pa <= 0 or E_shaft_Pa <= 0:
        return {"ok": False, "reason": "E_hub_Pa and E_shaft_Pa must be > 0"}
    if not (0 < nu_hub < 0.5) or not (0 < nu_shaft < 0.5):
        return {"ok": False, "reason": "Poisson ratios must be in (0, 0.5)"}

    # Interface (contact) radius and outer/inner radii (mm)
    r_i_mm = nominal_mm / 2.0       # interface radius
    r_o_mm = hub_outer_mm / 2.0     # hub outer radius
    r_b_mm = shaft_bore_mm / 2.0    # shaft inner bore radius (0 for solid)

    # Convert to metres for SI calculations
    r_i = r_i_mm * 1e-3
    r_o = r_o_mm * 1e-3
    r_b = r_b_mm * 1e-3
    delta = interference_mm * 1e-3 / 2.0  # RADIAL interference = diametral / 2

    # --- Lamé contact pressure (Shigley eq. 2-57 / 2-58) ---
    # For thick-walled hub (outer cylinder):
    #   δ_hub/r_i = p_c/E_hub * [(r_o² + r_i²)/(r_o² - r_i²) + nu_hub]
    # For shaft (inner cylinder, with bore):
    #   δ_shaft/r_i = p_c/E_shaft * [(r_i² + r_b²)/(r_i² - r_b²) - nu_shaft]
    # Total radial interference: δ = δ_hub + δ_shaft

    # Hub compliance factor C_hub (dimensionless)
    C_hub = ((r_o**2 + r_i**2) / (r_o**2 - r_i**2) + nu_hub) / E_hub_Pa

    # Shaft compliance factor C_shaft (dimensionless)
    if r_b == 0.0:
        # Solid shaft: δ_shaft/r_i = p_c/E_shaft * (1 - nu_shaft)
        C_shaft = (1.0 - nu_shaft) / E_shaft_Pa
    else:
        C_shaft = ((r_i**2 + r_b**2) / (r_i**2 - r_b**2) - nu_shaft) / E_shaft_Pa

    # Contact pressure [Pa]
    denominator = r_i * (C_hub + C_shaft)
    if denominator <= 0:
        return {"ok": False, "reason": "degenerate geometry: contact pressure denominator <= 0"}

    p_c = delta / denominator  # Pa

    if interference_mm == 0.0:
        p_c = 0.0

    # --- Hoop stresses in hub (Lamé) ---
    # σ_θ_hub(r) = p_c * r_i² / (r_o² - r_i²) * (1 + r_o²/r²)
    def hub_hoop(r: float) -> float:
        if r_o == r_i:
            return 0.0
        return p_c * r_i**2 / (r_o**2 - r_i**2) * (1.0 + r_o**2 / r**2)

    hub_hoop_inner = hub_hoop(r_i)   # max, at inner radius (tensile)
    hub_hoop_outer = hub_hoop(r_o)   # min, at outer radius (tensile)

    # --- Hoop stresses in shaft ---
    # For solid shaft: σ_θ_shaft = -p_c (uniform compression)
    # For hollow shaft: Lamé for inner cylinder loaded on outer surface:
    # σ_θ_shaft(r) = -p_c * r_i² / (r_i² - r_b²) * (1 + r_b²/r²)
    if r_b == 0.0:
        shaft_hoop_inner = -p_c   # uniform compressive
        shaft_hoop_outer = -p_c   # at interface
    else:
        def shaft_hoop(r: float) -> float:
            if r_i == r_b:
                return 0.0
            return -p_c * r_i**2 / (r_i**2 - r_b**2) * (1.0 + r_b**2 / r**2)
        shaft_hoop_inner = shaft_hoop(r_b)  # at bore (most compressive)
        shaft_hoop_outer = shaft_hoop(r_i)  # at interface

    # --- Assembly force (axial press-in force) ---
    assembly_force_N: float | None = None
    if length_mm is not None:
        if length_mm <= 0:
            warns.append("length_mm must be > 0 for assembly force calculation; skipped.")
        else:
            L = length_mm * 1e-3  # metres
            # F = p_c * π * d * L * μ  where d = nominal diameter
            assembly_force_N = p_c * math.pi * nominal_mm * 1e-3 * L * mu_friction

    # --- Shrink-fit temperature differential ---
    # δ_thermal = α_hub * D * ΔT ≥ δ_diametral + press_clearance
    # We need the hub to expand by δ_diametral (radial × 2 = full diametral interference)
    # Net expansion needed = interference_mm (diametral)
    # ΔT = δ_diametral / (α_hub * D)   — heat only the hub (standard shrink fit)
    net_alpha = alpha_hub - alpha_shaft  # relative expansion per °C
    if abs(net_alpha) < 1e-12:
        warns.append(
            "alpha_hub ≈ alpha_shaft — both parts expand equally; "
            "shrink fit by heating hub alone uses alpha_hub only."
        )
        net_alpha = alpha_hub  # heat hub only

    D_m = nominal_mm * 1e-3  # m
    if abs(net_alpha) > 0 and D_m > 0:
        shrink_delta_T = interference_mm * 1e-3 / (alpha_hub * D_m)
    else:
        shrink_delta_T = 0.0
        warns.append("Cannot compute shrink-fit temperature: degenerate alpha or diameter.")

    # Add a safety margin of ~25% to the theoretical minimum
    shrink_delta_T_practical = shrink_delta_T * 1.25

    # --- Overstress checks ---
    hub_overstressed = False
    shaft_overstressed = False

    if yield_strength_hub_Pa is not None:
        # Maximum hub stress is the inner hoop (tensile) + radial (compressive at interface)
        # Von Mises for hub inner: σ_VM ≈ sqrt(σ_θ² + p_c² - σ_θ*(-p_c))
        # Simplified: check hoop stress alone (conservative for pure interference)
        if abs(hub_hoop_inner) > yield_strength_hub_Pa:
            hub_overstressed = True
            _warnings.warn(
                f"tolfits: press_fit: hub OVERSTRESSED — hoop stress "
                f"{hub_hoop_inner/1e6:.1f} MPa > yield {yield_strength_hub_Pa/1e6:.1f} MPa"
            )

    if yield_strength_shaft_Pa is not None:
        shaft_check_stress = abs(shaft_hoop_inner)
        if shaft_check_stress > yield_strength_shaft_Pa:
            shaft_overstressed = True
            _warnings.warn(
                f"tolfits: press_fit: shaft OVERSTRESSED — hoop stress "
                f"{shaft_check_stress/1e6:.1f} MPa > yield {yield_strength_shaft_Pa/1e6:.1f} MPa"
            )

    for w in warns:
        _warnings.warn(f"tolfits: {w}")

    return {
        "ok": True,
        "nominal_mm": nominal_mm,
        "interference_mm": interference_mm,
        "contact_pressure_Pa": p_c,
        "contact_pressure_MPa": p_c / 1e6,
        "hub_hoop_stress_inner_Pa": hub_hoop_inner,
        "hub_hoop_stress_outer_Pa": hub_hoop_outer,
        "shaft_hoop_stress_inner_Pa": shaft_hoop_inner,
        "shaft_hoop_stress_outer_Pa": shaft_hoop_outer,
        "assembly_force_N": assembly_force_N,
        "shrink_fit_delta_T_C": round(shrink_delta_T_practical, 1),
        "hub_overstressed": hub_overstressed,
        "shaft_overstressed": shaft_overstressed,
        "warnings": warns,
    }
