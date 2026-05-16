"""
kerf_cad_core.ergonomics.human — pure-Python human-factors engineering formulas.

Implements:

  anthropometric_percentile   — body dimension at given percentile (z-score)
  design_for_range            — 5th–95th percentile clearance vs reach analysis
  niosh_rwl                   — NIOSH Revised Lifting Equation (RWL)
  lifting_index               — Lifting Index = L / RWL
  snook_push_pull             — Snook (1991) max acceptable push/pull/carry forces
  grip_strength_percentile    — grip strength at given percentile (male/female)
  pinch_strength_percentile   — pinch (lateral) strength at given percentile
  rula_score                  — RULA grand score from joint angles (upper-limb)
  reba_score                  — REBA grand score from body-segment angles
  workstation_heights         — seated/standing optimal workstation & display heights
  visual_angle                — visual angle (arcmin) and adequacy check
  min_character_size          — minimum legible character height from viewing distance
  metabolic_expenditure       — metabolic energy expenditure (W) + rest allowance
  rest_allowance              — rest allowance fraction from metabolic demand
  reach_envelope              — functional reach envelope radius

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Ergonomic hazards are flagged in "warnings" list.

Units
-----
  lengths       — mm or cm as documented per function
  forces        — N or kg as documented per function
  angles        — degrees
  mass          — kg
  distance      — m for visual/reach; mm for anthropometric
  energy        — W (watts) for metabolic
  time          — minutes

References
----------
NIOSH (1994) — Revised NIOSH Lifting Equation, DHHS (NIOSH) Publication 94-110.
Waters TR et al. (1993) — Ergonomics 36(7):749-776.
Snook & Ciriello (1991) — Ergonomics 34(9):1197-1213.
McAtamney & Corlett (1993) — Applied Ergonomics 24(2):91-99.
Hignett & McAtamney (2000) — Applied Ergonomics 31(2):201-205.
Chaffin, Andersson, Martin (2006) — Occupational Biomechanics, 4th ed.
NASA-STD-3001 Vol. 2 (2011).
ANSI/HFES 100-2007.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _guard_finite(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    return None


def _guard_positive(name: str, value: Any) -> str | None:
    e = _guard_finite(name, value)
    if e:
        return e
    if float(value) <= 0:
        return f"{name} must be > 0, got {value}"
    return None


def _guard_nonneg(name: str, value: Any) -> str | None:
    e = _guard_finite(name, value)
    if e:
        return e
    if float(value) < 0:
        return f"{name} must be >= 0, got {value}"
    return None


def _guard_range(name: str, value: Any, lo: float, hi: float) -> str | None:
    e = _guard_finite(name, value)
    if e:
        return e
    v = float(value)
    if not (lo <= v <= hi):
        return f"{name} must be in [{lo}, {hi}], got {v}"
    return None


def _z_from_pctile(pctile: float) -> float:
    """Rational approximation of inverse normal CDF (Abramowitz & Stegun 26.2.17).

    Accurate to ~0.0005 for 0.0005 < p < 0.9995.
    """
    p = float(pctile)
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"percentile must be in (0, 1), got {p}")
    if p < 0.5:
        sign = -1.0
        q = p
    else:
        sign = 1.0
        q = 1.0 - p
    t = math.sqrt(-2.0 * math.log(q))
    c = (2.515517, 0.802853, 0.010328)
    d = (1.432788, 0.189269, 0.001308)
    x = t - (c[0] + c[1] * t + c[2] * t * t) / (
        1.0 + d[0] * t + d[1] * t * t + d[2] * t * t * t
    )
    return sign * x


# ---------------------------------------------------------------------------
# Anthropometric data tables (mean ± SD in mm, standing adult civilians)
# Source: Kroemer & Grandjean; NASA-STD-3001 Vol.2 App B; ANSUR II.
#
# Keys match common body-dimension identifiers.
# Values: (male_mean_mm, male_sd_mm, female_mean_mm, female_sd_mm)
# ---------------------------------------------------------------------------

_ANTHROPOMETRIC_TABLE: dict[str, tuple[float, float, float, float]] = {
    # Standing heights
    "stature":                  (1755.0, 71.0, 1621.0, 64.0),
    "eye_height_standing":      (1645.0, 70.0, 1515.0, 62.0),
    "shoulder_height_standing": (1437.0, 64.0, 1326.0, 58.0),
    "elbow_height_standing":    (1079.0, 53.0, 1000.0, 47.0),
    "hip_height_standing":      ( 920.0, 45.0,  869.0, 41.0),
    "knuckle_height_standing":  ( 757.0, 38.0,  718.0, 34.0),
    "reach_height_standing":    (2060.0, 89.0, 1906.0, 83.0),

    # Seated heights (floor to seat = 0 reference, seat surface ref)
    "sitting_height":           ( 914.0, 36.0,  856.0, 33.0),
    "eye_height_sitting":       ( 797.0, 34.0,  745.0, 32.0),
    "shoulder_height_sitting":  ( 600.0, 30.0,  557.0, 28.0),
    "elbow_height_sitting":     ( 243.0, 28.0,  232.0, 26.0),

    # Body breadths / depths
    "shoulder_breadth":         ( 465.0, 26.0,  427.0, 23.0),
    "hip_breadth_sitting":      ( 371.0, 31.0,  394.0, 34.0),
    "chest_depth":              ( 238.0, 25.0,  238.0, 28.0),
    "abdominal_depth_sitting":  ( 233.0, 37.0,  238.0, 40.0),

    # Reach
    "functional_reach_forward": ( 720.0, 46.0,  650.0, 42.0),
    "functional_reach_side":    ( 680.0, 44.0,  618.0, 40.0),

    # Hand / foot
    "hand_length":              ( 192.0, 11.0,  174.0, 10.0),
    "hand_breadth":             (  85.0,  6.0,   74.0,  5.0),
    "foot_length":              ( 269.0, 14.0,  240.0, 13.0),
    "foot_breadth":             (  98.0,  7.0,   86.0,  6.0),

    # Head
    "head_length":              ( 196.0,  8.0,  187.0,  7.0),
    "head_breadth":             ( 153.0,  7.0,  146.0,  6.0),
    "head_circumference":       ( 570.0, 17.0,  551.0, 16.0),

    # Leg lengths
    "popliteal_height":         ( 438.0, 27.0,  404.0, 25.0),
    "thigh_clearance":          ( 156.0, 15.0,  147.0, 16.0),
    "knee_height_sitting":      ( 546.0, 30.0,  504.0, 28.0),
    "buttock_popliteal_length": ( 491.0, 30.0,  483.0, 30.0),
}


def anthropometric_percentile(
    dimension: str,
    percentile: float,
    sex: str = "male",
) -> dict:
    """
    Body dimension at a given percentile using z-score scaling.

    Parameters
    ----------
    dimension : str
        Body dimension name from the built-in table (e.g. 'stature',
        'shoulder_height_standing').
    percentile : float
        Percentile in [0.01, 0.99] (e.g. 0.05 for 5th, 0.95 for 95th).
    sex : str
        'male' or 'female'.

    Returns
    -------
    dict
        dimension_mm : body dimension at requested percentile (mm)
        mean_mm      : population mean (mm)
        sd_mm        : population standard deviation (mm)
        z_score      : z-score used
        percentile   : percentile used
        sex          : sex used
    """
    e = _guard_range("percentile", percentile, 0.001, 0.999)
    if e:
        return _err(e)

    sex_clean = str(sex).strip().lower()
    if sex_clean not in ("male", "female"):
        return _err(f"sex must be 'male' or 'female', got {sex!r}")

    dim_clean = str(dimension).strip().lower().replace(" ", "_")
    if dim_clean not in _ANTHROPOMETRIC_TABLE:
        available = sorted(_ANTHROPOMETRIC_TABLE.keys())
        return _err(
            f"Unknown dimension {dimension!r}. Available: {available}"
        )

    row = _ANTHROPOMETRIC_TABLE[dim_clean]
    if sex_clean == "male":
        mean_mm, sd_mm = row[0], row[1]
    else:
        mean_mm, sd_mm = row[2], row[3]

    try:
        z = _z_from_pctile(float(percentile))
    except ValueError as exc:
        return _err(str(exc))

    dim_mm = mean_mm + z * sd_mm

    warnings: list[str] = []
    if float(percentile) <= 0.05 or float(percentile) >= 0.95:
        warnings.append(
            f"Designing for the {float(percentile)*100:.0f}th percentile; "
            "consider design-for-range (5th–95th) per ISO 9241-5."
        )

    return {
        "ok": True,
        "dimension": dim_clean,
        "dimension_mm": round(dim_mm, 1),
        "mean_mm": mean_mm,
        "sd_mm": sd_mm,
        "z_score": round(z, 4),
        "percentile": float(percentile),
        "sex": sex_clean,
        "warnings": warnings,
    }


def design_for_range(
    dimension: str,
    application: str = "clearance",
    lo_pctile: float = 0.05,
    hi_pctile: float = 0.95,
    include_both_sexes: bool = True,
) -> dict:
    """
    5th–95th percentile design-for-range clearance vs reach analysis.

    Clearance (e.g. doorway width):  must accommodate the LARGEST user —
        use 95th-percentile of the relevant population.
    Reach (e.g. shelf height):       must accommodate the SMALLEST user —
        use 5th-percentile of the relevant population.

    Parameters
    ----------
    dimension : str
        Body dimension name (see anthropometric_percentile for list).
    application : str
        'clearance' or 'reach'.  Determines which percentile is critical.
    lo_pctile : float
        Lower design percentile (default 0.05 for 5th).
    hi_pctile : float
        Upper design percentile (default 0.95 for 95th).
    include_both_sexes : bool
        If True, critical value spans both male and female populations.

    Returns
    -------
    dict
        critical_mm     : design-critical dimension (mm)
        lo_male_mm      : lo_pctile for males (mm)
        hi_male_mm      : hi_pctile for males (mm)
        lo_female_mm    : lo_pctile for females (mm)
        hi_female_mm    : hi_pctile for females (mm)
        application     : 'clearance' or 'reach'
        warnings        : advisory list
    """
    e = _guard_range("lo_pctile", lo_pctile, 0.001, 0.499)
    if e:
        return _err(e)
    e = _guard_range("hi_pctile", hi_pctile, 0.501, 0.999)
    if e:
        return _err(e)

    app = str(application).strip().lower()
    if app not in ("clearance", "reach"):
        return _err(f"application must be 'clearance' or 'reach', got {application!r}")

    # Gather percentile values for male and female
    results = {}
    for sex in ("male", "female"):
        r_lo = anthropometric_percentile(dimension, lo_pctile, sex=sex)
        r_hi = anthropometric_percentile(dimension, hi_pctile, sex=sex)
        if not r_lo["ok"]:
            return r_lo
        if not r_hi["ok"]:
            return r_hi
        results[sex] = (r_lo["dimension_mm"], r_hi["dimension_mm"])

    male_lo, male_hi = results["male"]
    female_lo, female_hi = results["female"]

    warnings: list[str] = []
    if app == "clearance":
        # Accommodate the largest — use highest hi_pctile across sexes
        if include_both_sexes:
            critical_mm = max(male_hi, female_hi)
        else:
            critical_mm = male_hi
        warnings.append(
            "Clearance: design for the largest user "
            f"({hi_pctile*100:.0f}th percentile)."
        )
    else:  # reach
        # Accommodate the smallest — use lowest lo_pctile across sexes
        if include_both_sexes:
            critical_mm = min(male_lo, female_lo)
        else:
            critical_mm = female_lo
        warnings.append(
            "Reach: design for the smallest user "
            f"({lo_pctile*100:.0f}th percentile)."
        )

    return {
        "ok": True,
        "dimension": str(dimension).strip().lower().replace(" ", "_"),
        "critical_mm": round(critical_mm, 1),
        "lo_male_mm": male_lo,
        "hi_male_mm": male_hi,
        "lo_female_mm": female_lo,
        "hi_female_mm": female_hi,
        "application": app,
        "lo_pctile": lo_pctile,
        "hi_pctile": hi_pctile,
        "include_both_sexes": include_both_sexes,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# NIOSH Revised Lifting Equation (1994)
# RWL = LC × HM × VM × DM × AM × FM × CM
# Lifting Index (LI) = Load weight / RWL
# ---------------------------------------------------------------------------

# Load Constant (kg) per NIOSH 1994
_NIOSH_LC = 23.0  # kg

# Multiplier computation helpers
def _niosh_HM(H_cm: float) -> float:
    """Horizontal multiplier: HM = 25/H (H in cm, range 25–63 cm)."""
    H = float(H_cm)
    if H < 25.0:
        H = 25.0  # optimum: H≤25 → HM=1
    return min(1.0, 25.0 / H)


def _niosh_VM(V_cm: float) -> float:
    """Vertical multiplier: VM = 1 - 0.003 × |V - 75| (V in cm)."""
    V = float(V_cm)
    return max(0.0, 1.0 - 0.003 * abs(V - 75.0))


def _niosh_DM(D_cm: float) -> float:
    """Distance multiplier: DM = 0.82 + 4.5/D (D in cm, range 25–175 cm)."""
    D = float(D_cm)
    if D < 25.0:
        D = 25.0
    if D > 175.0:
        D = 175.0
    return 0.82 + 4.5 / D


def _niosh_AM(A_deg: float) -> float:
    """Asymmetry multiplier: AM = 1 - 0.0032 × A (A in degrees, 0–135°)."""
    A = float(A_deg)
    A = max(0.0, min(135.0, A))
    return max(0.0, 1.0 - 0.0032 * A)


# Frequency multiplier tables (lifts/min, duration, V<75 vs V≥75)
# (lifts_per_min, FM_V_lt75, FM_V_ge75)
# Duration: 1=≤1h, 2=1-2h, 3=2-8h
_NIOSH_FM_TABLE: dict[str, list[tuple[float, float, float]]] = {
    "short": [   # ≤1 hour
        (0.2, 1.00, 1.00),
        (0.5, 0.97, 0.97),
        (1.0, 0.94, 0.94),
        (2.0, 0.91, 0.91),
        (3.0, 0.88, 0.88),
        (4.0, 0.84, 0.84),
        (5.0, 0.80, 0.80),
        (6.0, 0.75, 0.75),
        (7.0, 0.70, 0.70),
        (8.0, 0.60, 0.60),
        (9.0, 0.52, 0.52),
        (10.0, 0.45, 0.45),
        (11.0, 0.41, 0.41),
        (12.0, 0.37, 0.37),
        (13.0, 0.00, 0.34),
        (14.0, 0.00, 0.31),
        (15.0, 0.00, 0.28),
    ],
    "moderate": [  # 1–2 hours
        (0.2, 0.95, 0.95),
        (0.5, 0.92, 0.92),
        (1.0, 0.88, 0.88),
        (2.0, 0.84, 0.84),
        (3.0, 0.79, 0.79),
        (4.0, 0.72, 0.72),
        (5.0, 0.60, 0.60),
        (6.0, 0.50, 0.50),
        (7.0, 0.42, 0.42),
        (8.0, 0.35, 0.35),
        (9.0, 0.30, 0.30),
        (10.0, 0.26, 0.26),
        (11.0, 0.00, 0.23),
        (12.0, 0.00, 0.21),
    ],
    "long": [  # 2–8 hours
        (0.2, 0.85, 0.85),
        (0.5, 0.81, 0.81),
        (1.0, 0.75, 0.75),
        (2.0, 0.65, 0.65),
        (3.0, 0.55, 0.55),
        (4.0, 0.45, 0.45),
        (5.0, 0.35, 0.35),
        (6.0, 0.27, 0.27),
        (7.0, 0.22, 0.22),
        (8.0, 0.18, 0.18),
        (9.0, 0.00, 0.15),
        (10.0, 0.00, 0.13),
    ],
}

# Coupling multiplier: 'good', 'fair', 'poor'  ×  (V<75, V≥75)
_NIOSH_CM: dict[str, tuple[float, float]] = {
    "good": (1.00, 1.00),
    "fair": (0.95, 1.00),
    "poor": (0.90, 0.90),
}


def _niosh_FM(freq_per_min: float, duration: str, V_cm: float) -> float:
    """Look up frequency multiplier from NIOSH 1994 Table 5."""
    dur = str(duration).strip().lower()
    if dur not in _NIOSH_FM_TABLE:
        dur = "long"
    table = _NIOSH_FM_TABLE[dur]
    v_idx = 1 if float(V_cm) < 75.0 else 2
    # find best matching row (highest freq_per_min ≤ requested)
    fm = 0.0
    for row in table:
        if freq_per_min <= row[0]:
            fm = row[v_idx]
            break
    else:
        fm = 0.0  # exceeds max frequency
    return fm


def niosh_rwl(
    L_kg: float,
    H_cm: float,
    V_cm: float,
    D_cm: float,
    A_deg: float = 0.0,
    freq_per_min: float = 0.2,
    duration: str = "long",
    coupling: str = "good",
) -> dict:
    """
    NIOSH Revised Lifting Equation (1994): Recommended Weight Limit.

    RWL = LC × HM × VM × DM × AM × FM × CM

    Parameters
    ----------
    L_kg : float
        Actual load weight (kg). Must be >= 0.
    H_cm : float
        Horizontal distance from body mid-point to hands (cm). Must be > 0.
        Optimal ≤ 25 cm; ≥ 63 cm → RWL → 0.
    V_cm : float
        Vertical height of hands at origin of lift (cm). Range 0–175 cm.
    D_cm : float
        Vertical travel distance during lift (cm). Must be > 0.
        Minimum 25 cm applied; maximum 175 cm.
    A_deg : float
        Asymmetry angle: degrees of body twist from sagittal plane (0–135°).
        Default 0 (symmetric).
    freq_per_min : float
        Average lifting frequency (lifts/min). Default 0.2 (infrequent).
    duration : str
        Work duration: 'short' (≤1 h), 'moderate' (1–2 h), 'long' (2–8 h).
    coupling : str
        Hand-to-object coupling quality: 'good', 'fair', or 'poor'.

    Returns
    -------
    dict
        RWL_kg        : Recommended Weight Limit (kg)
        LI            : Lifting Index = L_kg / RWL_kg
        LC            : Load Constant (23 kg)
        HM, VM, DM, AM, FM, CM : individual multipliers
        warnings      : list — LI>1 flagged, multiplier advice
    """
    e = _guard_nonneg("L_kg", L_kg)
    if e:
        return _err(e)
    e = _guard_positive("H_cm", H_cm)
    if e:
        return _err(e)
    e = _guard_range("V_cm", V_cm, 0.0, 175.0)
    if e:
        return _err(e)
    e = _guard_positive("D_cm", D_cm)
    if e:
        return _err(e)
    e = _guard_range("A_deg", A_deg, 0.0, 135.0)
    if e:
        return _err(e)
    e = _guard_nonneg("freq_per_min", freq_per_min)
    if e:
        return _err(e)

    coupling_clean = str(coupling).strip().lower()
    if coupling_clean not in _NIOSH_CM:
        return _err(f"coupling must be 'good', 'fair', or 'poor', got {coupling!r}")

    HM = _niosh_HM(H_cm)
    VM = _niosh_VM(V_cm)
    DM = _niosh_DM(D_cm)
    AM = _niosh_AM(A_deg)
    FM = _niosh_FM(freq_per_min, duration, V_cm)
    cm_vals = _NIOSH_CM[coupling_clean]
    CM = cm_vals[0] if float(V_cm) < 75.0 else cm_vals[1]

    RWL = _NIOSH_LC * HM * VM * DM * AM * FM * CM
    LI = float(L_kg) / RWL if RWL > 0 else float("inf")

    warnings: list[str] = []
    if LI > 3.0:
        warnings.append(
            f"LI={LI:.2f} > 3.0: HIGH risk — immediate engineering redesign required."
        )
    elif LI > 1.0:
        warnings.append(
            f"LI={LI:.2f} > 1.0: Increased risk of low-back disorder; "
            "redesign task to reduce load or improve geometry."
        )
    if HM < 0.63:
        warnings.append(f"HM={HM:.2f}: horizontal reach excessive (H > 40 cm).")
    if VM < 0.78:
        warnings.append(f"VM={VM:.2f}: vertical height unfavourable.")
    if AM < 0.84:
        warnings.append(f"AM={AM:.2f}: significant asymmetric twist (A > 45°).")
    if FM < 0.50:
        warnings.append(f"FM={FM:.2f}: high lifting frequency or long duration.")
    if CM < 1.00:
        warnings.append(f"CM={CM:.2f}: coupling quality is {coupling_clean}.")
    if RWL <= 0:
        warnings.append("RWL=0: lift is not recommended under these conditions.")

    return {
        "ok": True,
        "RWL_kg": round(RWL, 3),
        "LI": round(LI, 3),
        "L_kg": float(L_kg),
        "LC": _NIOSH_LC,
        "HM": round(HM, 4),
        "VM": round(VM, 4),
        "DM": round(DM, 4),
        "AM": round(AM, 4),
        "FM": round(FM, 4),
        "CM": round(CM, 4),
        "H_cm": float(H_cm),
        "V_cm": float(V_cm),
        "D_cm": float(D_cm),
        "A_deg": float(A_deg),
        "freq_per_min": float(freq_per_min),
        "duration": duration,
        "coupling": coupling_clean,
        "warnings": warnings,
    }


def lifting_index(
    L_kg: float,
    H_cm: float,
    V_cm: float,
    D_cm: float,
    A_deg: float = 0.0,
    freq_per_min: float = 0.2,
    duration: str = "long",
    coupling: str = "good",
) -> dict:
    """
    Lifting Index = actual load / RWL.

    Same parameters as niosh_rwl; returns LI and risk classification.
    LI ≤ 1.0 acceptable; 1.0 < LI ≤ 3.0 elevated risk; LI > 3.0 high risk.
    """
    result = niosh_rwl(L_kg, H_cm, V_cm, D_cm, A_deg, freq_per_min, duration, coupling)
    if not result["ok"]:
        return result

    LI = result["LI"]
    if LI <= 1.0:
        risk = "acceptable"
    elif LI <= 3.0:
        risk = "elevated_risk"
    else:
        risk = "high_risk"

    return {
        "ok": True,
        "LI": LI,
        "RWL_kg": result["RWL_kg"],
        "L_kg": float(L_kg),
        "risk_level": risk,
        "warnings": result["warnings"],
    }


# ---------------------------------------------------------------------------
# Snook & Ciriello (1991) push/pull/carry force tables
#
# Tables encoded as: (frequency_per_min, distance_m or duration_min,
#                      male_90th_N, female_90th_N,
#                      male_75th_N, female_75th_N,
#                      male_50th_N, female_50th_N)
# For simplicity we store mean and sd for each sex and task type.
# Data from Snook & Ciriello (1991), Table 2-5, common representative values.
# ---------------------------------------------------------------------------

# Snook tables: keyed (task, sex, percentile_band)
# Values are dictionaries of {(freq_per_min, dist_m_or_dur_min): force_N}
#
# Push (initial) — Snook 1991, male 90th percentile (10% population can just exceed)
# i.e., 90th percentile = force that 90% of the population can exert ≥ (capacity).
# We store "maximum acceptable force" = force that can be sustained by given % of pop.

# Simplified representative table (initial peak push force, N):
# columns: freq (per min), 2 m, 7.5 m, 15 m, 30 m, 60 m
_SNOOK_PUSH_INITIAL: dict[str, dict[float, dict[float, float]]] = {
    "male": {
        # freq/min: {distance_m: force_N}
        0.2:  {2: 360, 7.5: 345, 15: 330, 30: 310, 60: 290},
        1.0:  {2: 300, 7.5: 285, 15: 270, 30: 255, 60: 235},
        2.0:  {2: 265, 7.5: 250, 15: 240, 30: 225, 60: 210},
        4.0:  {2: 225, 7.5: 215, 15: 205, 30: 195, 60: 180},
        6.0:  {2: 200, 7.5: 190, 15: 180, 30: 170, 60: 158},
        12.0: {2: 170, 7.5: 162, 15: 155, 30: 146, 60: 135},
    },
    "female": {
        0.2:  {2: 210, 7.5: 200, 15: 190, 30: 178, 60: 165},
        1.0:  {2: 175, 7.5: 165, 15: 157, 30: 148, 60: 138},
        2.0:  {2: 155, 7.5: 147, 15: 140, 30: 132, 60: 123},
        4.0:  {2: 132, 7.5: 126, 15: 120, 30: 113, 60: 105},
        6.0:  {2: 118, 7.5: 112, 15: 107, 30: 101, 60:  94},
        12.0: {2:  99, 7.5:  95, 15:  90, 30:  85, 60:  79},
    },
}

# Carry (force equivalent in N from kg × g):
# Max acceptable carry weight (kg) for given conditions
_SNOOK_CARRY: dict[str, dict[float, dict[float, float]]] = {
    "male": {
        # freq/min: {distance_m: max_acceptable_kg}
        1.0:  {2: 29, 7.5: 26, 15: 24, 30: 22, 60: 20},
        2.0:  {2: 25, 7.5: 23, 15: 21, 30: 19, 60: 17},
        4.0:  {2: 21, 7.5: 19, 15: 18, 30: 16, 60: 15},
        6.0:  {2: 18, 7.5: 17, 15: 16, 30: 14, 60: 13},
        12.0: {2: 15, 7.5: 14, 15: 13, 30: 12, 60: 11},
    },
    "female": {
        1.0:  {2: 18, 7.5: 16, 15: 15, 30: 14, 60: 12},
        2.0:  {2: 15, 7.5: 14, 15: 13, 30: 12, 60: 11},
        4.0:  {2: 13, 7.5: 12, 15: 11, 30: 10, 60:  9},
        6.0:  {2: 11, 7.5: 10, 15:  9, 30:  8, 60:  7},
        12.0: {2:  9, 7.5:  9, 15:  8, 30:  7, 60:  7},
    },
}


def _snook_lookup(
    table: dict,
    sex: str,
    freq: float,
    dist: float,
) -> float | None:
    """Nearest-neighbour lookup from a Snook-style table."""
    sex_table = table.get(sex)
    if sex_table is None:
        return None
    # find closest frequency
    best_freq = min(sex_table.keys(), key=lambda f: abs(f - freq))
    dist_table = sex_table[best_freq]
    # find closest distance
    best_dist = min(dist_table.keys(), key=lambda d: abs(d - dist))
    return float(dist_table[best_dist])


def snook_push_pull(
    task: str,
    sex: str,
    freq_per_min: float,
    distance_m: float,
    force_applied_N: float | None = None,
) -> dict:
    """
    Snook & Ciriello (1991) maximum acceptable push/pull/carry forces.

    Parameters
    ----------
    task : str
        'push', 'pull', or 'carry'.
    sex : str
        'male' or 'female'.
    freq_per_min : float
        Task frequency (per minute). Must be > 0.
    distance_m : float
        Distance per task cycle (m). Must be > 0.
    force_applied_N : float or None
        If provided, compare against the table limit and flag if exceeded.
        For 'carry', provide the carried weight in kg converted to N (W × 9.81).

    Returns
    -------
    dict
        max_acceptable_N : maximum acceptable force/weight (N)
        force_applied_N  : actual force if provided
        exceeds_limit    : True if force_applied_N > max_acceptable_N
        task, sex        : echo inputs
        warnings         : list
    """
    e = _guard_positive("freq_per_min", freq_per_min)
    if e:
        return _err(e)
    e = _guard_positive("distance_m", distance_m)
    if e:
        return _err(e)

    task_clean = str(task).strip().lower()
    if task_clean not in ("push", "pull", "carry"):
        return _err(f"task must be 'push', 'pull', or 'carry', got {task!r}")

    sex_clean = str(sex).strip().lower()
    if sex_clean not in ("male", "female"):
        return _err(f"sex must be 'male' or 'female', got {sex!r}")

    if task_clean in ("push", "pull"):
        limit_N = _snook_lookup(_SNOOK_PUSH_INITIAL, sex_clean, freq_per_min, distance_m)
    else:  # carry
        limit_kg = _snook_lookup(_SNOOK_CARRY, sex_clean, freq_per_min, distance_m)
        limit_N = limit_kg * 9.81 if limit_kg is not None else None

    if limit_N is None:
        return _err("Could not look up Snook table for given parameters.")

    warnings: list[str] = []
    exceeds = False
    if force_applied_N is not None:
        fa = float(force_applied_N)
        exceeds = fa > limit_N
        if exceeds:
            warnings.append(
                f"Applied force {fa:.1f} N exceeds Snook limit "
                f"{limit_N:.1f} N for {task_clean} task ({sex_clean}). "
                "Redesign task, use mechanical assist, or rotate workers."
            )

    return {
        "ok": True,
        "task": task_clean,
        "sex": sex_clean,
        "max_acceptable_N": round(limit_N, 1),
        "force_applied_N": force_applied_N,
        "exceeds_limit": exceeds,
        "freq_per_min": float(freq_per_min),
        "distance_m": float(distance_m),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Grip and pinch strength (N) by percentile
# Source: Mathiowetz et al. (1985), Crosby & Wehbe (1994), Matheson (1999)
# Male/Female mean ± SD in Newtons
# ---------------------------------------------------------------------------

_GRIP_STRENGTH: dict[str, tuple[float, float]] = {
    "male":   (476.0, 100.0),  # dominant hand, mean ± SD (N)
    "female": (285.0,  65.0),
}

_PINCH_LATERAL_STRENGTH: dict[str, tuple[float, float]] = {
    "male":   (100.0, 22.0),   # lateral (key) pinch mean ± SD (N)
    "female": (65.0,  15.0),
}


def grip_strength_percentile(
    percentile: float,
    sex: str = "male",
) -> dict:
    """
    Grip strength at given percentile (dominant hand, adults 20–44 years).

    Parameters
    ----------
    percentile : float
        Percentile in (0, 1). E.g. 0.05 for 5th percentile.
    sex : str
        'male' or 'female'.

    Returns
    -------
    dict
        grip_strength_N : grip strength at percentile (N)
        mean_N, sd_N    : population statistics
        z_score         : z-score used
        warnings        : if control resistance exceeds grip strength
    """
    e = _guard_range("percentile", percentile, 0.001, 0.999)
    if e:
        return _err(e)
    sex_clean = str(sex).strip().lower()
    if sex_clean not in _GRIP_STRENGTH:
        return _err(f"sex must be 'male' or 'female', got {sex!r}")

    mean_N, sd_N = _GRIP_STRENGTH[sex_clean]
    z = _z_from_pctile(float(percentile))
    gs_N = mean_N + z * sd_N

    warnings: list[str] = []
    if float(percentile) <= 0.05:
        warnings.append(
            f"Designing for {percentile*100:.1f}th percentile grip strength "
            f"({gs_N:.1f} N). Control resistance must not exceed this value."
        )
    # Typical handle force recommendation: < 50 N for precision, < 100 N for power
    if gs_N < 100.0:
        warnings.append(
            f"Grip strength at this percentile ({gs_N:.1f} N) is low; "
            "limit grip-type control resistance to < 50% of this value."
        )

    return {
        "ok": True,
        "grip_strength_N": round(gs_N, 1),
        "mean_N": mean_N,
        "sd_N": sd_N,
        "z_score": round(z, 4),
        "percentile": float(percentile),
        "sex": sex_clean,
        "warnings": warnings,
    }


def pinch_strength_percentile(
    percentile: float,
    sex: str = "male",
) -> dict:
    """
    Lateral (key) pinch strength at given percentile.

    Parameters
    ----------
    percentile : float
        Percentile in (0, 1).
    sex : str
        'male' or 'female'.

    Returns
    -------
    dict
        pinch_strength_N : lateral pinch strength at percentile (N)
        mean_N, sd_N     : population statistics
    """
    e = _guard_range("percentile", percentile, 0.001, 0.999)
    if e:
        return _err(e)
    sex_clean = str(sex).strip().lower()
    if sex_clean not in _PINCH_LATERAL_STRENGTH:
        return _err(f"sex must be 'male' or 'female', got {sex!r}")

    mean_N, sd_N = _PINCH_LATERAL_STRENGTH[sex_clean]
    z = _z_from_pctile(float(percentile))
    ps_N = mean_N + z * sd_N

    warnings: list[str] = []
    if float(percentile) <= 0.05:
        warnings.append(
            f"5th-percentile pinch strength ({ps_N:.1f} N) is design limit. "
            "Limit pinch-type control force to ≤ 50% of this value."
        )

    return {
        "ok": True,
        "pinch_strength_N": round(ps_N, 1),
        "mean_N": mean_N,
        "sd_N": sd_N,
        "z_score": round(z, 4),
        "percentile": float(percentile),
        "sex": sex_clean,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# RULA — Rapid Upper Limb Assessment (McAtamney & Corlett 1993)
# Grand score from individual joint angles (simplified coding table)
# ---------------------------------------------------------------------------

def _rula_upper_arm_score(angle_deg: float, abducted: bool, shoulder_raised: bool) -> int:
    """Score upper arm posture (1–6)."""
    a = float(angle_deg)
    if -20 <= a <= 20:
        s = 1
    elif a < -20 or (20 < a <= 45):
        s = 2
    elif 45 < a <= 90:
        s = 3
    else:
        s = 4
    if abducted:
        s += 1
    if shoulder_raised:
        s += 1
    return max(1, min(6, s))


def _rula_lower_arm_score(angle_deg: float) -> int:
    """Score lower arm posture (1–3)."""
    a = float(angle_deg)
    if 60 <= a <= 100:
        return 1
    else:
        return 2


def _rula_wrist_score(angle_deg: float, wrist_twisted: bool) -> int:
    """Score wrist posture (1–4)."""
    a = abs(float(angle_deg))
    if a <= 15:
        s = 1
    elif a <= 30:
        s = 2
    else:
        s = 3
    if wrist_twisted:
        s += 1
    return max(1, min(4, s))


# RULA wrist/arm table lookup (Table A in McAtamney & Corlett 1993)
# Index: upper_arm_score (1-6), lower_arm_score (1-2), wrist_score (1-4)
# Value: posture score A
_RULA_TABLE_A: dict[tuple[int, int, int], int] = {
    # (upper_arm, lower_arm, wrist) -> score_A
    (1,1,1):1,(1,1,2):2,(1,1,3):2,(1,1,4):3,
    (1,2,1):2,(1,2,2):2,(1,2,3):3,(1,2,4):3,
    (2,1,1):2,(2,1,2):2,(2,1,3):3,(2,1,4):3,
    (2,2,1):2,(2,2,2):3,(2,2,3):3,(2,2,4):4,
    (3,1,1):2,(3,1,2):3,(3,1,3):3,(3,1,4):4,
    (3,2,1):2,(3,2,2):3,(3,2,3):3,(3,2,4):4,
    (4,1,1):3,(4,1,2):3,(4,1,3):4,(4,1,4):5,
    (4,2,1):3,(4,2,2):4,(4,2,3):4,(4,2,4):5,
    (5,1,1):3,(5,1,2):4,(5,1,3):4,(5,1,4):5,
    (5,2,1):3,(5,2,2):4,(5,2,3):4,(5,2,4):5,
    (6,1,1):3,(6,1,2):4,(6,1,3):5,(6,1,4):6,
    (6,2,1):4,(6,2,2):4,(6,2,3):5,(6,2,4):6,
}

# RULA Table C: final score from score_A + score_B -> grand score
_RULA_TABLE_C: dict[tuple[int, int], int] = {
    (1,1):1,(1,2):2,(1,3):3,(1,4):3,(1,5):4,(1,6):5,(1,7):5,
    (2,1):2,(2,2):2,(2,3):3,(2,4):4,(2,5):4,(2,6):5,(2,7):5,
    (3,1):3,(3,2):3,(3,3):3,(3,4):4,(3,5):4,(3,6):5,(3,7):6,
    (4,1):3,(4,2):3,(4,3):3,(4,4):4,(4,5):5,(4,6):6,(4,7):6,
    (5,1):4,(5,2):4,(5,3):4,(5,4):5,(5,5):6,(5,6):7,(5,7):7,
    (6,1):4,(6,2):4,(6,3):5,(6,4):6,(6,5):6,(6,6):7,(6,7):7,
    (7,1):5,(7,2):5,(7,3):6,(7,4):6,(7,5):7,(7,6):7,(7,7):7,
    (8,1):5,(8,2):5,(8,3):6,(8,4):7,(8,5):7,(8,6):7,(8,7):7,
}


def _rula_grand_score(score_a: int, muscle_use_A: int, force_A: int,
                      score_b: int, muscle_use_B: int, force_B: int) -> int:
    """Compute RULA grand score from posture scores A and B plus adjustments."""
    sa = score_a + muscle_use_A + force_A
    sb = score_b + muscle_use_B + force_B
    sa = max(1, min(8, sa))
    sb = max(1, min(7, sb))
    return _RULA_TABLE_C.get((sa, sb), 7)


def rula_score(
    upper_arm_angle_deg: float,
    lower_arm_angle_deg: float,
    wrist_angle_deg: float,
    neck_angle_deg: float,
    trunk_angle_deg: float,
    *,
    wrist_twisted: bool = False,
    shoulder_raised: bool = False,
    upper_arm_abducted: bool = False,
    static_or_repeated: bool = False,
    force_kg: float = 0.0,
) -> dict:
    """
    RULA (Rapid Upper Limb Assessment) grand score.

    Parameters
    ----------
    upper_arm_angle_deg : float
        Upper arm flexion/extension from neutral (degrees).
        Negative = extension, positive = flexion.
    lower_arm_angle_deg : float
        Lower arm (elbow) flexion from full extension (degrees). 0–140°.
    wrist_angle_deg : float
        Wrist deviation from neutral (degrees). 0 = neutral.
    neck_angle_deg : float
        Neck flexion from neutral (degrees). 0 = neutral, positive = forward.
    trunk_angle_deg : float
        Trunk flexion from upright (degrees). 0 = upright.
    wrist_twisted : bool
        Wrist rotated significantly from mid-range.
    shoulder_raised : bool
        Shoulder elevated/raised.
    upper_arm_abducted : bool
        Upper arm abducted (arm out to side).
    static_or_repeated : bool
        True if posture is static (>1 min) or repeated (>4×/min).
    force_kg : float
        Force/load exerted (kg). > 10 kg = score adjustment.

    Returns
    -------
    dict
        grand_score      : RULA grand score (1–7)
        action_level     : 1–4 (1=acceptable, 4=immediate action)
        action_text      : human-readable recommendation
        score_a, score_b : intermediate posture scores
        warnings         : list
    """
    e = _guard_finite("upper_arm_angle_deg", upper_arm_angle_deg)
    if e:
        return _err(e)
    e = _guard_finite("lower_arm_angle_deg", lower_arm_angle_deg)
    if e:
        return _err(e)
    e = _guard_finite("wrist_angle_deg", wrist_angle_deg)
    if e:
        return _err(e)
    e = _guard_finite("neck_angle_deg", neck_angle_deg)
    if e:
        return _err(e)
    e = _guard_finite("trunk_angle_deg", trunk_angle_deg)
    if e:
        return _err(e)
    e = _guard_nonneg("force_kg", force_kg)
    if e:
        return _err(e)

    ua = _rula_upper_arm_score(
        upper_arm_angle_deg, upper_arm_abducted, shoulder_raised
    )
    la = _rula_lower_arm_score(lower_arm_angle_deg)
    ws = _rula_wrist_score(wrist_angle_deg, wrist_twisted)

    score_a = _RULA_TABLE_A.get((min(ua, 6), min(la, 2), min(ws, 4)), 4)

    # Muscle use adjustment A
    muse_a = 1 if static_or_repeated else 0
    # Force/load adjustment A
    fkg = float(force_kg)
    if fkg < 2:
        force_a = 0
    elif fkg <= 10:
        force_a = 1
    else:
        force_a = 2

    # Neck score
    n = float(neck_angle_deg)
    if 0 <= n <= 10:
        neck_s = 1
    elif 10 < n <= 20:
        neck_s = 2
    elif n > 20:
        neck_s = 3
    else:  # negative (extension)
        neck_s = 4

    # Trunk score
    t = float(trunk_angle_deg)
    if abs(t) <= 10:
        trunk_s = 1
    elif abs(t) <= 20:
        trunk_s = 2
    elif abs(t) <= 60:
        trunk_s = 3
    else:
        trunk_s = 4

    # Simplified score_b: neck + trunk combination (simplified from Table B)
    score_b = min(7, neck_s + trunk_s)
    muse_b = 1 if static_or_repeated else 0
    force_b = force_a

    grand = _rula_grand_score(score_a, muse_a, force_a, score_b, muse_b, force_b)
    grand = max(1, min(7, grand))

    if grand <= 2:
        action_level = 1
        action_text = "Acceptable posture. Further evaluation may not be required."
    elif grand <= 4:
        action_level = 2
        action_text = "Further investigation required; changes may be needed."
    elif grand <= 6:
        action_level = 3
        action_text = "Prompt investigation and changes required."
    else:
        action_level = 4
        action_text = "Immediate investigation and changes required."

    warnings: list[str] = []
    if action_level >= 3:
        warnings.append(
            f"RULA score {grand} (action level {action_level}): "
            + action_text
        )
    if abs(float(neck_angle_deg)) > 20:
        warnings.append(
            f"Neck angle {neck_angle_deg}° exceeds 20° — cervical strain risk."
        )
    if float(trunk_angle_deg) > 20:
        warnings.append(
            f"Trunk flexion {trunk_angle_deg}° exceeds 20° — lumbar strain risk."
        )

    return {
        "ok": True,
        "grand_score": grand,
        "action_level": action_level,
        "action_text": action_text,
        "score_a": score_a,
        "score_b": score_b,
        "upper_arm_score": ua,
        "lower_arm_score": la,
        "wrist_score": ws,
        "neck_score": neck_s,
        "trunk_score": trunk_s,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# REBA — Rapid Entire Body Assessment (Hignett & McAtamney 2000)
# ---------------------------------------------------------------------------

def reba_score(
    trunk_angle_deg: float,
    neck_angle_deg: float,
    leg_angle_deg: float,
    upper_arm_angle_deg: float,
    lower_arm_angle_deg: float,
    wrist_angle_deg: float,
    *,
    load_kg: float = 0.0,
    coupling: str = "good",
    activity_score: int = 0,
) -> dict:
    """
    REBA (Rapid Entire Body Assessment) grand score.

    Parameters
    ----------
    trunk_angle_deg : float
        Trunk flexion from upright (degrees). 0=upright, >90=severely bent.
    neck_angle_deg : float
        Neck flexion (degrees). 0=neutral.
    leg_angle_deg : float
        Knee flexion from standing (degrees). 0=standing, >60=deep squat.
    upper_arm_angle_deg : float
        Upper arm flexion/extension (degrees).
    lower_arm_angle_deg : float
        Lower arm (elbow) angle (degrees).
    wrist_angle_deg : float
        Wrist deviation (degrees).
    load_kg : float
        Load/force (kg). Adds 0 (≤5), 1 (5–10), or 2 (>10) to Table A.
    coupling : str
        'good', 'fair', or 'poor'.
    activity_score : int
        Additional activity adjustment: 0 (none), 1 (repetitive), 2 (rapid change).

    Returns
    -------
    dict
        reba_score      : REBA grand score (1–15)
        action_level    : 1–5
        risk_level      : 'negligible' to 'very_high'
        warnings        : list
    """
    for nm, val in [
        ("trunk_angle_deg", trunk_angle_deg),
        ("neck_angle_deg", neck_angle_deg),
        ("leg_angle_deg", leg_angle_deg),
        ("upper_arm_angle_deg", upper_arm_angle_deg),
        ("lower_arm_angle_deg", lower_arm_angle_deg),
        ("wrist_angle_deg", wrist_angle_deg),
    ]:
        e = _guard_finite(nm, val)
        if e:
            return _err(e)

    e = _guard_nonneg("load_kg", load_kg)
    if e:
        return _err(e)

    coupling_clean = str(coupling).strip().lower()
    if coupling_clean not in ("good", "fair", "poor"):
        return _err(f"coupling must be 'good', 'fair', or 'poor', got {coupling!r}")

    # --- Group A: trunk, neck, legs ---
    t = abs(float(trunk_angle_deg))
    if t <= 5:
        ts = 1
    elif t <= 20:
        ts = 2
    elif t <= 60:
        ts = 3
    else:
        ts = 4

    n = abs(float(neck_angle_deg))
    if n <= 20:
        ns = 1
    else:
        ns = 2

    lk = float(leg_angle_deg)
    if abs(lk) <= 5:
        ls = 1
    elif abs(lk) <= 30:
        ls = 2
    else:
        ls = 3

    # Simplified Table A score
    table_a_raw = ts + ns + ls
    if float(load_kg) <= 5:
        load_adj = 0
    elif float(load_kg) <= 10:
        load_adj = 1
    else:
        load_adj = 2

    score_a = table_a_raw + load_adj

    # --- Group B: upper arm, lower arm, wrist ---
    ua = abs(float(upper_arm_angle_deg))
    if ua <= 20:
        uas = 1
    elif ua <= 45:
        uas = 2
    elif ua <= 90:
        uas = 3
    else:
        uas = 4

    la = float(lower_arm_angle_deg)
    if 60 <= la <= 100:
        las = 1
    else:
        las = 2

    wa = abs(float(wrist_angle_deg))
    if wa <= 15:
        ws = 1
    else:
        ws = 2

    coupling_adj = {"good": 0, "fair": 1, "poor": 2}[coupling_clean]
    score_b = uas + las + ws + coupling_adj

    # --- Table C: combine A and B ---
    grand = int(round((score_a + score_b) / 2.0 + activity_score))
    grand = max(1, min(15, grand))

    if grand == 1:
        risk = "negligible"; al = 1; at = "No action required."
    elif grand <= 3:
        risk = "low"; al = 2; at = "Change may be needed."
    elif grand <= 7:
        risk = "medium"; al = 3; at = "Further investigation; changes soon."
    elif grand <= 10:
        risk = "high"; al = 4; at = "Investigate and implement changes."
    else:
        risk = "very_high"; al = 5; at = "Implement changes immediately."

    warnings: list[str] = []
    if al >= 4:
        warnings.append(f"REBA score {grand} ({risk} risk): {at}")
    if float(trunk_angle_deg) > 60:
        warnings.append(
            f"Trunk angle {trunk_angle_deg}° > 60°: severe bending — high injury risk."
        )
    if float(load_kg) > 10:
        warnings.append(
            f"Load {load_kg} kg > 10 kg increases REBA score."
        )

    return {
        "ok": True,
        "reba_score": grand,
        "action_level": al,
        "risk_level": risk,
        "action_text": at,
        "score_a": score_a,
        "score_b": score_b,
        "trunk_score": ts,
        "neck_score": ns,
        "leg_score": ls,
        "upper_arm_score": uas,
        "lower_arm_score": las,
        "wrist_score": ws,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Workstation heights — seated and standing
# Source: ANSI/HFES 100-2007, Kroemer & Grandjean, NIOSH 1997 workstation guide
# ---------------------------------------------------------------------------

def workstation_heights(
    stature_mm: float | None = None,
    popliteal_height_mm: float | None = None,
    elbow_height_standing_mm: float | None = None,
    elbow_height_sitting_mm: float | None = None,
    eye_height_sitting_mm: float | None = None,
    sex: str = "male",
    percentile: float = 0.50,
    task_type: str = "light_assembly",
) -> dict:
    """
    Recommended workstation heights for seated and standing postures.

    If individual measurements are not provided, population percentile data
    is used automatically.

    Parameters
    ----------
    stature_mm : float, optional
        Individual stature (mm).
    popliteal_height_mm : float, optional
        Popliteal height (floor to back of bent knee, mm).
    elbow_height_standing_mm : float, optional
        Elbow height standing (mm).
    elbow_height_sitting_mm : float, optional
        Elbow height seated above seat surface (mm).
    eye_height_sitting_mm : float, optional
        Eye height seated above seat surface (mm).
    sex : str
        'male' or 'female' (used for population defaults).
    percentile : float
        Population percentile for defaults (0.05–0.95).
    task_type : str
        'light_assembly', 'precision', 'heavy_work', or 'keyboard'.

    Returns
    -------
    dict
        seat_height_mm        : recommended seat height range (mm)
        work_surface_seated_mm: recommended seated work surface height (mm)
        work_surface_standing_mm: recommended standing work surface height (mm)
        display_height_mm     : recommended monitor top height (mm) from floor
        display_distance_mm   : recommended viewing distance (mm)
        warnings              : list
    """
    e = _guard_range("percentile", percentile, 0.001, 0.999)
    if e:
        return _err(e)

    sex_clean = str(sex).strip().lower()
    if sex_clean not in ("male", "female"):
        return _err(f"sex must be 'male' or 'female', got {sex!r}")

    task_clean = str(task_type).strip().lower().replace(" ", "_").replace("-", "_")
    valid_tasks = ("light_assembly", "precision", "heavy_work", "keyboard")
    if task_clean not in valid_tasks:
        return _err(
            f"task_type must be one of {valid_tasks}, got {task_type!r}"
        )

    def _get_dim(name: str, provided: float | None) -> float:
        if provided is not None:
            return float(provided)
        row = _ANTHROPOMETRIC_TABLE[name]
        mean, sd = (row[0], row[1]) if sex_clean == "male" else (row[2], row[3])
        z = _z_from_pctile(float(percentile))
        return mean + z * sd

    popliteal = _get_dim("popliteal_height", popliteal_height_mm)
    elbow_st = _get_dim("elbow_height_standing", elbow_height_standing_mm)
    elbow_si = _get_dim("elbow_height_sitting", elbow_height_sitting_mm)
    eye_si = _get_dim("eye_height_sitting", eye_height_sitting_mm)

    # Seat height: popliteal height + 25–40 mm clearance
    seat_lo = popliteal + 25.0
    seat_hi = popliteal + 40.0

    # Seated work surface height = seat height + elbow_height_sitting
    # Adjustments by task type (relative to neutral elbow):
    #   light_assembly: 0–50 mm below elbow
    #   precision:      100–150 mm above elbow
    #   heavy_work:     100–200 mm below elbow
    #   keyboard:       0–30 mm below elbow
    seat_mid = (seat_lo + seat_hi) / 2.0
    elbow_from_floor_seated = seat_mid + elbow_si

    task_adj = {
        "light_assembly": -25.0,
        "precision":     +125.0,
        "heavy_work":    -150.0,
        "keyboard":      -15.0,
    }[task_clean]
    work_surface_seated = elbow_from_floor_seated + task_adj

    # Standing work surface: elbow height + task adjustment
    work_surface_standing = elbow_st + task_adj

    # Display height: top of monitor at eye level or 0–30° below horizontal
    # Eye height seated = floor to seat + elbow_height_sitting + eye_height_sitting
    # Actually eye_height_sitting is measured from seat surface
    floor_to_eye_seated = seat_mid + eye_si

    # Top of screen at eye level; centre of screen 15° below (ANSI/HFES 100-2007)
    display_top_mm = floor_to_eye_seated
    display_distance_mm = 600.0  # standard 600 mm for offices

    warnings: list[str] = []
    if task_clean == "heavy_work" and work_surface_standing < 700:
        warnings.append(
            "Standing work surface < 700 mm — verify floor-level work is appropriate."
        )
    if task_clean == "precision" and work_surface_seated > 900:
        warnings.append(
            "Precision seated surface > 900 mm — verify adequate visual access."
        )

    return {
        "ok": True,
        "seat_height_lo_mm": round(seat_lo, 1),
        "seat_height_hi_mm": round(seat_hi, 1),
        "work_surface_seated_mm": round(work_surface_seated, 1),
        "work_surface_standing_mm": round(work_surface_standing, 1),
        "display_top_height_mm": round(display_top_mm, 1),
        "display_distance_mm": display_distance_mm,
        "task_type": task_clean,
        "sex": sex_clean,
        "percentile": float(percentile),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Visual angle and minimum character size
# Source: ANSI/HFES 100-2007, MIL-STD-1472G
# ---------------------------------------------------------------------------

def visual_angle(
    object_height_mm: float,
    viewing_distance_mm: float,
) -> dict:
    """
    Visual angle subtended by an object at a given viewing distance.

    Parameters
    ----------
    object_height_mm : float
        Height of the object (mm). Must be > 0.
    viewing_distance_mm : float
        Viewing distance from eye to object (mm). Must be > 0.

    Returns
    -------
    dict
        visual_angle_deg    : visual angle (degrees)
        visual_angle_arcmin : visual angle (arc-minutes)
        adequate_for_reading: True if >= 20 arcmin (MIL-STD-1472 minimum)
        warnings            : list
    """
    e = _guard_positive("object_height_mm", object_height_mm)
    if e:
        return _err(e)
    e = _guard_positive("viewing_distance_mm", viewing_distance_mm)
    if e:
        return _err(e)

    h = float(object_height_mm)
    d = float(viewing_distance_mm)

    # tan(alpha/2) = (h/2) / d → alpha = 2 * arctan(h / (2d))
    angle_rad = 2.0 * math.atan2(h / 2.0, d)
    angle_deg = math.degrees(angle_rad)
    angle_arcmin = angle_deg * 60.0

    adequate = angle_arcmin >= 20.0  # MIL-STD-1472G minimum 20 arcmin

    warnings: list[str] = []
    if not adequate:
        warnings.append(
            f"Visual angle {angle_arcmin:.1f} arcmin < 20 arcmin minimum "
            "(MIL-STD-1472G). Increase character size or reduce viewing distance."
        )
    if angle_arcmin < 15.0:
        warnings.append(
            f"Visual angle {angle_arcmin:.1f} arcmin is very small — "
            "object may be undetectable without optical aids."
        )

    return {
        "ok": True,
        "visual_angle_deg": round(angle_deg, 4),
        "visual_angle_arcmin": round(angle_arcmin, 2),
        "object_height_mm": h,
        "viewing_distance_mm": d,
        "adequate_for_reading": adequate,
        "warnings": warnings,
    }


def min_character_size(
    viewing_distance_mm: float,
    min_arcmin: float = 20.0,
    preferred_arcmin: float = 30.0,
) -> dict:
    """
    Minimum legible character height from viewing distance.

    Uses: h = 2 × d × tan(alpha/2) where alpha is visual angle.

    Parameters
    ----------
    viewing_distance_mm : float
        Viewing distance (mm). Must be > 0.
    min_arcmin : float
        Minimum visual angle (arcmin). Default 20 arcmin (MIL-STD-1472G).
    preferred_arcmin : float
        Preferred visual angle (arcmin). Default 30 arcmin.

    Returns
    -------
    dict
        min_char_height_mm      : minimum character height (mm)
        preferred_char_height_mm: preferred character height (mm)
        viewing_distance_mm     : viewing distance (mm)
        warnings                : list
    """
    e = _guard_positive("viewing_distance_mm", viewing_distance_mm)
    if e:
        return _err(e)
    e = _guard_positive("min_arcmin", min_arcmin)
    if e:
        return _err(e)
    e = _guard_positive("preferred_arcmin", preferred_arcmin)
    if e:
        return _err(e)

    d = float(viewing_distance_mm)

    def _char_h(arcmin: float) -> float:
        alpha_rad = math.radians(arcmin / 60.0)
        return 2.0 * d * math.tan(alpha_rad / 2.0)

    min_h = _char_h(min_arcmin)
    pref_h = _char_h(preferred_arcmin)

    warnings: list[str] = []
    if min_arcmin < 15.0:
        warnings.append(
            f"min_arcmin={min_arcmin} < 15 — below comfortable acuity threshold."
        )

    return {
        "ok": True,
        "min_char_height_mm": round(min_h, 2),
        "preferred_char_height_mm": round(pref_h, 2),
        "viewing_distance_mm": d,
        "min_arcmin": min_arcmin,
        "preferred_arcmin": preferred_arcmin,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Metabolic energy expenditure and rest allowance
# Source: Garg, Chaffin, Herrin (1978); Murrell (1965); MIL-HDBK-759C
# ---------------------------------------------------------------------------

# Metabolic rate (W) by activity classification
_METABOLIC_RATES: dict[str, float] = {
    "rest":              80.0,   # sitting quietly
    "very_light":       175.0,   # office/lab work, seated
    "light":            280.0,   # light assembly, standing light work
    "moderate":         450.0,   # general assembly, slow walking
    "heavy":            600.0,   # heavy assembly, fast walking
    "very_heavy":       800.0,   # intense manual labour
    "extremely_heavy": 1000.0,   # peak sustained effort
}

# Recommended metabolic ceiling for 8-hour workday (W)
_METABOLIC_8H_CEILING = 350.0


def metabolic_expenditure(
    activity: str = "moderate",
    body_mass_kg: float = 75.0,
    duration_min: float = 60.0,
) -> dict:
    """
    Metabolic energy expenditure and rest requirement.

    Parameters
    ----------
    activity : str
        Activity level: 'rest', 'very_light', 'light', 'moderate',
        'heavy', 'very_heavy', or 'extremely_heavy'.
    body_mass_kg : float
        Worker body mass (kg). Used for mass-normalised output. Default 75 kg.
    duration_min : float
        Task duration (minutes). Must be > 0.

    Returns
    -------
    dict
        metabolic_rate_W     : metabolic rate (W)
        total_energy_kJ      : total energy expended (kJ)
        metabolic_W_per_kg   : mass-normalised rate (W/kg)
        exceeds_8h_ceiling   : True if rate > 350 W ceiling for sustained work
        rest_allowance_min   : recommended rest (min) per duration_min worked
        warnings             : list
    """
    e = _guard_positive("body_mass_kg", body_mass_kg)
    if e:
        return _err(e)
    e = _guard_positive("duration_min", duration_min)
    if e:
        return _err(e)

    act = str(activity).strip().lower().replace(" ", "_").replace("-", "_")
    if act not in _METABOLIC_RATES:
        return _err(
            f"activity must be one of {list(_METABOLIC_RATES.keys())}, got {activity!r}"
        )

    M_W = _METABOLIC_RATES[act]
    dur_s = float(duration_min) * 60.0
    total_kJ = M_W * dur_s / 1000.0
    M_per_kg = M_W / float(body_mass_kg)

    exceeds = M_W > _METABOLIC_8H_CEILING

    # Rest allowance — Murrell (1965) formula:
    # R = T × (M - S) / (M - 1.5)
    # where S = 4.0 W/kg (8h average metabolic standard per Murrell)
    #       1.5 W/kg = seated rest metabolic rate (basal constant)
    S = 4.0   # W/kg — 8-hour sustained work metabolic standard
    _BASAL = 1.5  # W/kg — seated rest / basal metabolic rate
    M_nrm = M_per_kg
    if M_nrm > S:
        denom = M_nrm - _BASAL
        rest_fraction = (M_nrm - S) / denom if denom > 1e-9 else 0.0
        rest_fraction = max(0.0, min(1.0, rest_fraction))
        rest_min = float(duration_min) * rest_fraction
    else:
        rest_fraction = 0.0
        rest_min = 0.0

    warnings: list[str] = []
    if exceeds:
        warnings.append(
            f"Metabolic rate {M_W:.0f} W > {_METABOLIC_8H_CEILING:.0f} W ceiling "
            "for 8-hour sustained work. Task rotation or rest breaks required."
        )
    if rest_min > float(duration_min) * 0.5:
        warnings.append(
            f"Rest allowance {rest_min:.1f} min / {duration_min:.1f} min worked "
            "is > 50% — task is physiologically demanding."
        )

    return {
        "ok": True,
        "activity": act,
        "metabolic_rate_W": M_W,
        "total_energy_kJ": round(total_kJ, 2),
        "metabolic_W_per_kg": round(M_per_kg, 3),
        "exceeds_8h_ceiling": exceeds,
        "rest_allowance_min": round(rest_min, 2),
        "rest_fraction": round(rest_fraction, 4),
        "duration_min": float(duration_min),
        "body_mass_kg": float(body_mass_kg),
        "warnings": warnings,
    }


def rest_allowance(
    metabolic_rate_W: float,
    body_mass_kg: float = 75.0,
    task_duration_min: float = 60.0,
) -> dict:
    """
    Rest allowance from metabolic demand (Murrell 1965 formula).

    Parameters
    ----------
    metabolic_rate_W : float
        Task metabolic rate (W). Must be > 0.
    body_mass_kg : float
        Worker body mass (kg). Default 75 kg.
    task_duration_min : float
        Task duration (minutes). Must be > 0.

    Returns
    -------
    dict
        rest_min         : required rest time (minutes per task_duration_min)
        rest_fraction    : fraction of task time spent resting
        metabolic_W_per_kg : normalised metabolic rate
        warnings         : list
    """
    e = _guard_positive("metabolic_rate_W", metabolic_rate_W)
    if e:
        return _err(e)
    e = _guard_positive("body_mass_kg", body_mass_kg)
    if e:
        return _err(e)
    e = _guard_positive("task_duration_min", task_duration_min)
    if e:
        return _err(e)

    M_nrm = float(metabolic_rate_W) / float(body_mass_kg)
    S = 4.0       # W/kg — 8-hour sustained work metabolic standard (Murrell 1965)
    _BASAL = 1.5  # W/kg — seated rest / basal metabolic rate

    if M_nrm > S:
        denom = M_nrm - _BASAL
        if denom > 1e-9:
            rest_fraction = (M_nrm - S) / denom
        else:
            rest_fraction = 0.0
        rest_fraction = max(0.0, min(1.0, rest_fraction))
        rest_min = float(task_duration_min) * rest_fraction
    else:
        rest_fraction = 0.0
        rest_min = 0.0

    warnings: list[str] = []
    if float(metabolic_rate_W) > _METABOLIC_8H_CEILING:
        warnings.append(
            f"Metabolic rate {metabolic_rate_W:.0f} W exceeds sustained 8h ceiling "
            f"{_METABOLIC_8H_CEILING:.0f} W."
        )

    return {
        "ok": True,
        "rest_min": round(rest_min, 2),
        "rest_fraction": round(rest_fraction, 4),
        "metabolic_W_per_kg": round(M_nrm, 3),
        "metabolic_rate_W": float(metabolic_rate_W),
        "task_duration_min": float(task_duration_min),
        "body_mass_kg": float(body_mass_kg),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Reach envelope radius
# Source: NASA-STD-3001 Vol.2, §4.7; Chaffin et al. Occupational Biomechanics
# ---------------------------------------------------------------------------

def reach_envelope(
    sex: str = "male",
    percentile: float = 0.05,
    posture: str = "standing",
    reach_type: str = "functional",
) -> dict:
    """
    Functional reach envelope radius.

    Returns the reach distance (mm) achievable by the given percentile of
    the population in the specified posture.

    Parameters
    ----------
    sex : str
        'male' or 'female'.
    percentile : float
        Design percentile (0.05 = 5th percentile for reach design — smallest).
    posture : str
        'standing' or 'seated'.
    reach_type : str
        'functional' (arm extended + shoulder rotation) or
        'maximum' (fully extended arm + body lean).

    Returns
    -------
    dict
        reach_radius_mm : reach envelope radius (mm)
        dim_name        : body dimension used
        warnings        : list
    """
    e = _guard_range("percentile", percentile, 0.001, 0.999)
    if e:
        return _err(e)

    sex_clean = str(sex).strip().lower()
    if sex_clean not in ("male", "female"):
        return _err(f"sex must be 'male' or 'female', got {sex!r}")

    posture_clean = str(posture).strip().lower()
    if posture_clean not in ("standing", "seated"):
        return _err(f"posture must be 'standing' or 'seated', got {posture!r}")

    reach_type_clean = str(reach_type).strip().lower().replace("-", "_")
    if reach_type_clean not in ("functional", "maximum"):
        return _err(f"reach_type must be 'functional' or 'maximum', got {reach_type!r}")

    if posture_clean == "standing":
        dim_name = "functional_reach_forward"
    else:
        dim_name = "functional_reach_side"

    result = anthropometric_percentile(dim_name, percentile, sex=sex_clean)
    if not result["ok"]:
        return result

    reach_mm = result["dimension_mm"]

    # Maximum reach: add ~20% for body lean and shoulder extension
    if reach_type_clean == "maximum":
        reach_mm *= 1.20

    warnings: list[str] = []
    if float(percentile) <= 0.05:
        warnings.append(
            f"Reach envelope designed for {percentile*100:.0f}th percentile "
            f"({reach_mm:.0f} mm). All controls must be within this radius."
        )
    if reach_mm < 500:
        warnings.append(
            "Reach radius < 500 mm — verify primary controls are within "
            "immediate reach zone (< 300 mm from body)."
        )

    return {
        "ok": True,
        "reach_radius_mm": round(reach_mm, 1),
        "dim_name": dim_name,
        "sex": sex_clean,
        "percentile": float(percentile),
        "posture": posture_clean,
        "reach_type": reach_type_clean,
        "warnings": warnings,
    }
