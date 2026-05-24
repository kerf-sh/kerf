"""
kerf_cad_core.hvac.ducts — HVAC duct sizing calculations (pure Python).

Implements:

  cfm_from_sensible_load(Q_btuh, delta_T_F)
      Airflow from sensible cooling load: CFM = Q_btuh / (1.08 × ΔT).
      Reference: ASHRAE Fundamentals 2021, Chapter 17.

  round_duct_diameter(cfm, velocity_fpm)
      Round duct diameter from airflow and target velocity.

  rect_equiv_diameter(a_in, b_in)
      Huebscher (1948) equivalent diameter for a rectangular duct:
          D_e = 1.30 × (a × b)^0.625 / (a + b)^0.25   (inches)
      Reference: ASHRAE Fundamentals 2021, Ch. 21 Eq. 3.

  duct_friction_loss(cfm, diameter_in, length_ft, roughness_ft)
      Darcy-Weisbach head loss (in. w.g.) for round duct using the
      Altshul/Swamee-Jain friction factor.
      Reference: ASHRAE Fundamentals 2021, Ch. 21; Altshul (1952).

  duct_fitting_loss(cfm, diameter_in, C)
      Dynamic loss for a single fitting: ΔP = C × (V/4005)²  (in. w.g.)
      Reference: ASHRAE Fundamentals 2021, Ch. 21 Eq. 9.

  size_duct_equal_friction(cfm, friction_rate_in_wg_per_100ft, roughness_ft)
      Equal-friction method: select round duct diameter to match target
      friction rate (typically 0.08–0.12 in. w.g./100 ft).

  size_duct_velocity_reduction(cfm_list, velocity_fpm_list)
      Velocity-reduction method: size each duct section from supplied CFM
      and velocity schedules.  Returns a list of results.

  branch_static_pressure(sections)
      Total static pressure for a duct branch path.  sections is a list
      of dicts {cfm, diameter_in, length_ft, fittings: [{C, diameter_in}]}.
      Returns total static pressure (in. w.g.).

  fan_law_scale(cfm1, sp1, bhp1, cfm2)
      Fan-law scaling to a new airflow:
          CFM₂/CFM₁ = N₂/N₁
          SP₂  = SP₁  × (CFM₂/CFM₁)²
          BHP₂ = BHP₁ × (CFM₂/CFM₁)³

All functions return plain dicts:
    success → {"ok": True, ...computed fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.
Warnings (over-velocity, undersized) are accumulated in result["warnings"].

Units
-----
Airflow        — CFM (cubic feet per minute); US HVAC customary
Duct sizes     — inches (in.) for diameter; feet (ft) for length
Friction loss  — in. w.g. (inches water gauge) per 100 ft; total in in. w.g.
Velocity       — fpm (feet per minute)
Temperature    — °F
Thermal load   — BTU/h

References
----------
ASHRAE Handbook — Fundamentals (2021), Chapter 21: Duct Design
ASHRAE Handbook — Fundamentals (2021), Chapter 17: Nonresidential Cooling & Heating Load Calcs
Huebscher, R.G. (1948) "Friction equivalents for round, square, and rectangular
    ducts". ASHVE Trans. 54.
Altshul, A.D. (1952) friction-factor correlation for sheet-metal ducts.
Swamee, P.K. & Jain, A.K. (1976) explicit Moody friction approximation.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_module
from typing import Any

from kerf_cad_core.fluids.friction import darcy_friction_factor


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Air density at standard conditions (0.075 lb/ft³ @ 70 °F, sea level)
_AIR_RHO_LB_FT3 = 0.075

# Gravitational conversion constant gc = 32.174 lbm·ft/(lbf·s²).
# Required to convert ρ·V²/2 (ρ in lbm/ft³, V in ft/s — i.e. poundal-based)
# into a true force-based pressure in lbf/ft².  Omitting it inflates the
# Darcy-Weisbach pressure loss by ~32×.
_GC_LBM_FT_LBF_S2 = 32.174

# 1 in. w.g. = 5.20233 lbf/ft²  (internally consistent with the
# 1 in. w.g. = 249.089 Pa conversion used elsewhere: 249.089 / 47.880259).
_IN_WG_PER_LB_FT2 = 1.0 / 5.20233

# Sensible heat factor for standard air: Q = 1.08 × CFM × ΔT  (BTU/h)
# where 1.08 = 60 min/hr × 0.075 lb/ft³ × 0.24 BTU/(lb·°F)
_SENSIBLE_FACTOR = 1.08

# ASHRAE standard sheet-metal duct roughness (ft); smooth = 0.00015 ft
_DEFAULT_ROUGHNESS_FT = 0.00015

# Over-velocity threshold (fpm) — warn above this for supply ducts
_SUPPLY_VELOCITY_MAX_FPM = 800.0   # typical for residential / low-velocity commercial
_MAIN_VELOCITY_MAX_FPM  = 1500.0   # main trunk; offices / commercial

_EPS = 1e-12


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_positive(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _velocity_fpm(cfm: float, diameter_in: float) -> float:
    """Mean duct velocity (fpm) given CFM and round duct diameter (in.)."""
    area_ft2 = math.pi * (diameter_in / 12.0) ** 2 / 4.0
    return cfm / area_ft2 if area_ft2 > _EPS else 0.0


def _friction_factor(re: float, roughness_ft: float, diameter_ft: float) -> float:
    """Darcy friction factor for a round duct — delegates to canonical implementation."""
    eps_d = roughness_ft / max(diameter_ft, _EPS)
    re_clamped = max(re, 1.0)
    return darcy_friction_factor(re_clamped, eps_d)


# Kinematic viscosity of air at ~70 °F (ft²/s)
_AIR_NU_FT2_S = 1.6e-4


# ---------------------------------------------------------------------------
# 1. cfm_from_sensible_load
# ---------------------------------------------------------------------------

def cfm_from_sensible_load(Q_btuh: float, delta_T_F: float) -> dict:
    """Airflow from sensible cooling (or heating) load.

    ASHRAE sensible heat formula (standard air):
        Q_btuh = 1.08 × CFM × ΔT

    Solving for CFM:
        CFM = Q_btuh / (1.08 × ΔT)

    Parameters
    ----------
    Q_btuh : float
        Sensible thermal load (BTU/h). Must be > 0.
    delta_T_F : float
        Supply-air temperature difference (°F). Must be > 0.
        Typical cooling: 15–25 °F; heating: 30–70 °F.

    Returns
    -------
    dict
        ok          : True
        cfm         : required airflow (CFM)
        Q_btuh      : load used
        delta_T_F   : temperature difference used
        factor      : sensible heat factor used (1.08)
        warnings    : list of advisory strings
    """
    err = _guard_positive("Q_btuh", Q_btuh)
    if err:
        return _err(err)
    err = _guard_positive("delta_T_F", delta_T_F)
    if err:
        return _err(err)

    cfm = float(Q_btuh) / (_SENSIBLE_FACTOR * float(delta_T_F))
    warns: list[str] = []
    if delta_T_F < 10.0:
        warns.append(
            f"delta_T_F={delta_T_F:.1f} °F is unusually small; "
            "check supply-air temperature differential."
        )
    if delta_T_F > 80.0:
        warns.append(
            f"delta_T_F={delta_T_F:.1f} °F is unusually large; "
            "verify it is not a heating load entered as cooling."
        )
    return {
        "ok": True,
        "cfm": round(cfm, 2),
        "Q_btuh": float(Q_btuh),
        "delta_T_F": float(delta_T_F),
        "factor": _SENSIBLE_FACTOR,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 2. round_duct_diameter
# ---------------------------------------------------------------------------

def round_duct_diameter(cfm: float, velocity_fpm: float) -> dict:
    """Round duct diameter from airflow and target velocity.

    Area = CFM / V
    D    = 2 × √(Area / π)  [ft] → converted to inches

    Parameters
    ----------
    cfm : float
        Airflow (CFM). Must be > 0.
    velocity_fpm : float
        Target mean velocity (fpm). Must be > 0.
        Typical supply branch: 400–800 fpm; main trunk: 800–1 500 fpm.

    Returns
    -------
    dict
        ok           : True
        diameter_in  : required duct diameter (inches)
        area_ft2     : duct cross-sectional area (ft²)
        velocity_fpm : target velocity used
        cfm          : airflow used
        warnings     : list of advisory strings
    """
    err = _guard_positive("cfm", cfm)
    if err:
        return _err(err)
    err = _guard_positive("velocity_fpm", velocity_fpm)
    if err:
        return _err(err)

    area_ft2 = float(cfm) / float(velocity_fpm)
    d_ft = 2.0 * math.sqrt(area_ft2 / math.pi)
    d_in = d_ft * 12.0

    warns: list[str] = []
    if velocity_fpm > _MAIN_VELOCITY_MAX_FPM:
        warns.append(
            f"Velocity {velocity_fpm:.0f} fpm exceeds typical main-duct maximum "
            f"({_MAIN_VELOCITY_MAX_FPM:.0f} fpm); expect elevated noise and pressure loss."
        )
    elif velocity_fpm > _SUPPLY_VELOCITY_MAX_FPM:
        warns.append(
            f"Velocity {velocity_fpm:.0f} fpm exceeds typical branch-duct guideline "
            f"({_SUPPLY_VELOCITY_MAX_FPM:.0f} fpm for low-velocity systems)."
        )

    return {
        "ok": True,
        "diameter_in": round(d_in, 3),
        "area_ft2": round(area_ft2, 5),
        "velocity_fpm": float(velocity_fpm),
        "cfm": float(cfm),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 3. rect_equiv_diameter (Huebscher)
# ---------------------------------------------------------------------------

def rect_equiv_diameter(a_in: float, b_in: float) -> dict:
    """Huebscher (1948) equivalent diameter for a rectangular duct.

    The equivalent diameter D_e is the diameter of a round duct that produces
    the same friction loss per unit length at the same volumetric flow rate.

    Formula (ASHRAE Fundamentals 2021, Ch. 21, Eq. 3):
        D_e = 1.30 × (a × b)^0.625 / (a + b)^0.25      [inches]

    Parameters
    ----------
    a_in : float
        Duct width (inches). Must be > 0.
    b_in : float
        Duct height (inches). Must be > 0.

    Returns
    -------
    dict
        ok               : True
        equiv_diameter_in: equivalent round diameter (inches)
        aspect_ratio     : a/b (or b/a, always >= 1)
        a_in             : width used
        b_in             : height used
        warnings         : list of advisory strings
    """
    err = _guard_positive("a_in", a_in)
    if err:
        return _err(err)
    err = _guard_positive("b_in", b_in)
    if err:
        return _err(err)

    a, b = float(a_in), float(b_in)
    D_e = 1.30 * (a * b) ** 0.625 / (a + b) ** 0.25

    aspect = max(a, b) / min(a, b)
    warns: list[str] = []
    if aspect > 4.0:
        warns.append(
            f"Aspect ratio {aspect:.1f}:1 exceeds the ASHRAE recommended maximum of "
            "4:1; friction and fabrication penalties increase."
        )

    return {
        "ok": True,
        "equiv_diameter_in": round(D_e, 3),
        "aspect_ratio": round(aspect, 3),
        "a_in": a,
        "b_in": b,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 4. duct_friction_loss
# ---------------------------------------------------------------------------

def duct_friction_loss(
    cfm: float,
    diameter_in: float,
    length_ft: float,
    roughness_ft: float = _DEFAULT_ROUGHNESS_FT,
) -> dict:
    """Darcy-Weisbach friction pressure loss for a straight round duct.

    Formula:
        ΔP_fw = f × (L/D) × ρ × V² / (2 × g_c)

    Reported in both in. w.g. and Pa.

    The friction factor f is computed with the Colebrook-White equation
    (seeded by Swamee-Jain, 10 iterations), consistent with the Altshul
    approach widely used for HVAC sheet-metal ducts.

    Parameters
    ----------
    cfm : float
        Airflow (CFM). Must be > 0.
    diameter_in : float
        Round duct inside diameter (inches). Must be > 0.
    length_ft : float
        Duct section length (feet). Must be > 0.
    roughness_ft : float
        Absolute roughness (ft). Default 0.00015 ft (sheet metal, ASHRAE Table 2).
        Must be >= 0.

    Returns
    -------
    dict
        ok                    : True
        friction_loss_in_wg   : total friction loss (in. w.g.)
        friction_loss_Pa      : total friction loss (Pa)
        friction_rate_in_per_100ft: friction loss per 100 ft (in. w.g./100 ft)
        velocity_fpm          : mean duct velocity (fpm)
        friction_factor       : Darcy f
        reynolds_number       : Re
        diameter_in           : diameter used
        length_ft             : length used
        cfm                   : airflow used
        warnings              : list of advisory strings
    """
    err = _guard_positive("cfm", cfm)
    if err:
        return _err(err)
    err = _guard_positive("diameter_in", diameter_in)
    if err:
        return _err(err)
    err = _guard_positive("length_ft", length_ft)
    if err:
        return _err(err)
    err = _guard_nonneg("roughness_ft", roughness_ft)
    if err:
        return _err(err)

    cfm_v = float(cfm)
    d_in = float(diameter_in)
    L_ft = float(length_ft)
    eps_ft = float(roughness_ft)

    d_ft = d_in / 12.0
    area_ft2 = math.pi * d_ft ** 2 / 4.0
    v_fps = cfm_v / (area_ft2 * 60.0)   # ft/s
    v_fpm = v_fps * 60.0

    re = v_fps * d_ft / _AIR_NU_FT2_S

    f = _friction_factor(re, eps_ft, d_ft)

    # Darcy-Weisbach: ΔP = f × (L/D) × ρV² / (2·g_c)   [lbf/ft²]
    # g_c converts the poundal-based ρV²/2 term (ρ in lbm/ft³, V in ft/s)
    # to a force-based pressure in lbf/ft².
    dP_lb_ft2 = f * (L_ft / d_ft) * _AIR_RHO_LB_FT3 * v_fps ** 2 / (2.0 * _GC_LBM_FT_LBF_S2)
    dP_in_wg = dP_lb_ft2 * _IN_WG_PER_LB_FT2
    # Convert in. w.g. to Pa (1 in. w.g. = 249.089 Pa)
    dP_Pa = dP_in_wg * 249.089
    rate_per_100ft = dP_in_wg / L_ft * 100.0

    warns: list[str] = []
    if v_fpm > _MAIN_VELOCITY_MAX_FPM:
        warns.append(
            f"Velocity {v_fpm:.0f} fpm exceeds typical main-duct guideline "
            f"({_MAIN_VELOCITY_MAX_FPM:.0f} fpm); duct may be undersized."
        )
    elif v_fpm > _SUPPLY_VELOCITY_MAX_FPM:
        warns.append(
            f"Velocity {v_fpm:.0f} fpm exceeds branch-duct guideline "
            f"({_SUPPLY_VELOCITY_MAX_FPM:.0f} fpm)."
        )

    return {
        "ok": True,
        "friction_loss_in_wg": round(dP_in_wg, 5),
        "friction_loss_Pa": round(dP_Pa, 3),
        "friction_rate_in_per_100ft": round(rate_per_100ft, 5),
        "velocity_fpm": round(v_fpm, 1),
        "friction_factor": round(f, 6),
        "reynolds_number": round(re, 1),
        "diameter_in": d_in,
        "length_ft": L_ft,
        "cfm": cfm_v,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 5. duct_fitting_loss
# ---------------------------------------------------------------------------

def duct_fitting_loss(cfm: float, diameter_in: float, C: float) -> dict:
    """Dynamic pressure loss for a single duct fitting.

    Formula (ASHRAE Fundamentals 2021, Ch. 21, Eq. 9):
        ΔP = C × V_p
        V_p = (V / 4005)²   [in. w.g.] — velocity pressure for standard air

    where V is mean velocity in fpm and 4005 = √(2·g_c·ρ/1.08) is the
    unit-velocity-pressure constant for standard air at 70 °F.

    Parameters
    ----------
    cfm : float
        Airflow through the fitting (CFM). Must be > 0.
    diameter_in : float
        Round duct diameter at the fitting (inches). Must be > 0.
    C : float
        Loss coefficient (dimensionless). Must be >= 0.
        Typical values: elbow 90° = 0.20–0.60; tee branch = 0.70–1.2;
        entry bell mouth = 0.04; abrupt contraction = 0.5.

    Returns
    -------
    dict
        ok                  : True
        fitting_loss_in_wg  : dynamic pressure loss (in. w.g.)
        fitting_loss_Pa     : dynamic pressure loss (Pa)
        velocity_pressure_in_wg: velocity pressure V_p (in. w.g.)
        velocity_fpm        : mean velocity (fpm)
        C                   : loss coefficient used
        cfm                 : airflow used
        diameter_in         : diameter used
        warnings            : list of advisory strings
    """
    err = _guard_positive("cfm", cfm)
    if err:
        return _err(err)
    err = _guard_positive("diameter_in", diameter_in)
    if err:
        return _err(err)
    err = _guard_nonneg("C", C)
    if err:
        return _err(err)

    cfm_v = float(cfm)
    d_in = float(diameter_in)
    C_v = float(C)

    v_fpm = _velocity_fpm(cfm_v, d_in)
    # Velocity pressure (in. w.g.) for standard air:
    # V_p = (V/4005)²
    V_p = (v_fpm / 4005.0) ** 2
    dP_in_wg = C_v * V_p
    dP_Pa = dP_in_wg * 249.089

    warns: list[str] = []
    if v_fpm > _MAIN_VELOCITY_MAX_FPM:
        warns.append(
            f"Velocity {v_fpm:.0f} fpm at fitting exceeds main-duct guideline "
            f"({_MAIN_VELOCITY_MAX_FPM:.0f} fpm)."
        )

    return {
        "ok": True,
        "fitting_loss_in_wg": round(dP_in_wg, 6),
        "fitting_loss_Pa": round(dP_Pa, 4),
        "velocity_pressure_in_wg": round(V_p, 6),
        "velocity_fpm": round(v_fpm, 1),
        "C": C_v,
        "cfm": cfm_v,
        "diameter_in": d_in,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 6. size_duct_equal_friction
# ---------------------------------------------------------------------------

def size_duct_equal_friction(
    cfm: float,
    friction_rate_in_per_100ft: float,
    roughness_ft: float = _DEFAULT_ROUGHNESS_FT,
) -> dict:
    """Equal-friction duct sizing: find round diameter matching target friction rate.

    Iterates on diameter until the computed friction rate (in. w.g./100 ft)
    equals the target.  Bisection over diameter range 2–120 in.

    Typical design friction rates:
        Low-velocity commercial : 0.08–0.10 in. w.g./100 ft
        Medium-velocity commercial: 0.10–0.15 in. w.g./100 ft

    Parameters
    ----------
    cfm : float
        Airflow (CFM). Must be > 0.
    friction_rate_in_per_100ft : float
        Target friction rate (in. w.g. per 100 ft). Must be > 0.
    roughness_ft : float
        Absolute roughness (ft). Default 0.00015 ft (sheet metal).

    Returns
    -------
    dict
        ok                        : True
        diameter_in               : required duct diameter (inches)
        velocity_fpm              : resulting velocity at sized diameter
        actual_friction_rate_in_per_100ft: friction rate at computed diameter
        cfm                       : airflow used
        target_friction_rate_in_per_100ft: target friction rate
        warnings                  : list of advisory strings
    """
    err = _guard_positive("cfm", cfm)
    if err:
        return _err(err)
    err = _guard_positive("friction_rate_in_per_100ft", friction_rate_in_per_100ft)
    if err:
        return _err(err)
    err = _guard_nonneg("roughness_ft", roughness_ft)
    if err:
        return _err(err)

    cfm_v = float(cfm)
    target_rate = float(friction_rate_in_per_100ft)
    eps_ft = float(roughness_ft)

    def _rate_at_d(d_in: float) -> float:
        """Friction rate (in. w.g./100 ft) at diameter d_in for cfm_v."""
        d_ft = d_in / 12.0
        area_ft2 = math.pi * d_ft ** 2 / 4.0
        v_fps = cfm_v / (area_ft2 * 60.0)
        re = v_fps * d_ft / _AIR_NU_FT2_S
        f = _friction_factor(re, eps_ft, d_ft)
        # ΔP per foot = f / D × ρ × V² / (2·g_c)  [lbf/ft²/ft]
        dP_per_ft_lb = f / d_ft * _AIR_RHO_LB_FT3 * v_fps ** 2 / (2.0 * _GC_LBM_FT_LBF_S2)
        dP_per_ft_in_wg = dP_per_ft_lb * _IN_WG_PER_LB_FT2
        return dP_per_ft_in_wg * 100.0

    # Bisect on d_in over [2, 120] inches
    lo, hi = 2.0, 120.0
    # Ensure target is achievable within this range
    rate_lo = _rate_at_d(lo)
    rate_hi = _rate_at_d(hi)
    if target_rate > rate_lo:
        # Need smaller duct than 2 in. — clamp to minimum
        d_in = lo
    elif target_rate < rate_hi:
        # Need larger duct than 120 in.
        d_in = hi
    else:
        for _ in range(80):
            mid = (lo + hi) / 2.0
            if _rate_at_d(mid) > target_rate:
                lo = mid
            else:
                hi = mid
        d_in = (lo + hi) / 2.0

    v_fpm = _velocity_fpm(cfm_v, d_in)
    actual_rate = _rate_at_d(d_in)

    warns: list[str] = []
    if v_fpm > _MAIN_VELOCITY_MAX_FPM:
        warns.append(
            f"Resulting velocity {v_fpm:.0f} fpm exceeds typical main-duct "
            f"guideline ({_MAIN_VELOCITY_MAX_FPM:.0f} fpm); duct is undersized."
        )
    elif v_fpm > _SUPPLY_VELOCITY_MAX_FPM:
        warns.append(
            f"Resulting velocity {v_fpm:.0f} fpm exceeds branch-duct guideline "
            f"({_SUPPLY_VELOCITY_MAX_FPM:.0f} fpm)."
        )

    return {
        "ok": True,
        "diameter_in": round(d_in, 3),
        "velocity_fpm": round(v_fpm, 1),
        "actual_friction_rate_in_per_100ft": round(actual_rate, 5),
        "cfm": cfm_v,
        "target_friction_rate_in_per_100ft": target_rate,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 7. size_duct_velocity_reduction
# ---------------------------------------------------------------------------

def size_duct_velocity_reduction(
    cfm_list: list[float],
    velocity_fpm_list: list[float],
) -> dict:
    """Velocity-reduction method: size each duct section individually.

    Each section is sized directly from its CFM and target velocity using
    ``round_duct_diameter``.  The velocity schedule decreases from trunk to
    branches, e.g. [1200, 900, 700, 500] fpm.

    Parameters
    ----------
    cfm_list : list[float]
        Airflow for each section (CFM). Each must be > 0.
    velocity_fpm_list : list[float]
        Target velocity for each section (fpm). Each must be > 0.
        Must have the same length as cfm_list.

    Returns
    -------
    dict
        ok       : True
        sections : list of per-section results (diameter_in, area_ft2,
                   velocity_fpm, cfm, warnings)
        warnings : aggregated advisory strings across all sections
    """
    if not isinstance(cfm_list, (list, tuple)) or len(cfm_list) == 0:
        return _err("cfm_list must be a non-empty list")
    if not isinstance(velocity_fpm_list, (list, tuple)) or len(velocity_fpm_list) == 0:
        return _err("velocity_fpm_list must be a non-empty list")
    if len(cfm_list) != len(velocity_fpm_list):
        return _err(
            f"cfm_list (len={len(cfm_list)}) and velocity_fpm_list "
            f"(len={len(velocity_fpm_list)}) must have the same length"
        )

    sections = []
    all_warns: list[str] = []

    for i, (cfm, vel) in enumerate(zip(cfm_list, velocity_fpm_list)):
        res = round_duct_diameter(cfm, vel)
        if not res["ok"]:
            return _err(f"section {i}: {res['reason']}")
        all_warns.extend([f"section {i}: {w}" for w in res.get("warnings", [])])
        sections.append({
            "section_index": i,
            "cfm": res["cfm"],
            "velocity_fpm": res["velocity_fpm"],
            "diameter_in": res["diameter_in"],
            "area_ft2": res["area_ft2"],
        })

    return {
        "ok": True,
        "sections": sections,
        "warnings": all_warns,
    }


# ---------------------------------------------------------------------------
# 8. branch_static_pressure
# ---------------------------------------------------------------------------

def branch_static_pressure(sections: list[dict]) -> dict:
    """Total static pressure for a duct branch path.

    Sums friction loss (straight duct) and fitting losses for each section
    in the path.  The total is the fan static pressure requirement for that
    branch.

    Each section dict:
        cfm          : float — airflow (CFM), required
        diameter_in  : float — round duct diameter (in.), required
        length_ft    : float — straight duct length (ft), required
        fittings     : list of {C: float, diameter_in: float (optional)}
                       diameter_in defaults to section diameter_in
        roughness_ft : float — optional, default 0.00015 ft

    Parameters
    ----------
    sections : list[dict]
        Ordered list of duct sections from fan to terminal.

    Returns
    -------
    dict
        ok                       : True
        total_static_pressure_in_wg: total static pressure (in. w.g.)
        total_static_pressure_Pa : total static pressure (Pa)
        sections                 : per-section breakdown
        warnings                 : advisory strings
    """
    if not isinstance(sections, (list, tuple)) or len(sections) == 0:
        return _err("sections must be a non-empty list")

    total_in_wg = 0.0
    section_results = []
    all_warns: list[str] = []

    for i, sec in enumerate(sections):
        if not isinstance(sec, dict):
            return _err(f"sections[{i}] must be a dict")

        cfm = sec.get("cfm")
        d_in = sec.get("diameter_in")
        L_ft = sec.get("length_ft")
        if cfm is None:
            return _err(f"sections[{i}] missing 'cfm'")
        if d_in is None:
            return _err(f"sections[{i}] missing 'diameter_in'")
        if L_ft is None:
            return _err(f"sections[{i}] missing 'length_ft'")

        roughness = float(sec.get("roughness_ft", _DEFAULT_ROUGHNESS_FT))

        # Straight friction loss
        fric = duct_friction_loss(cfm, d_in, L_ft, roughness)
        if not fric["ok"]:
            return _err(f"sections[{i}] friction loss: {fric['reason']}")
        sec_loss = fric["friction_loss_in_wg"]
        all_warns.extend([f"sections[{i}] friction: {w}" for w in fric.get("warnings", [])])

        # Fitting losses
        fitting_total = 0.0
        raw_fittings = sec.get("fittings", [])
        if not isinstance(raw_fittings, (list, tuple)):
            raw_fittings = []
        for j, fit in enumerate(raw_fittings):
            if not isinstance(fit, dict):
                return _err(f"sections[{i}].fittings[{j}] must be a dict")
            C = fit.get("C")
            if C is None:
                return _err(f"sections[{i}].fittings[{j}] missing 'C'")
            fit_d_in = fit.get("diameter_in", d_in)
            fl = duct_fitting_loss(cfm, fit_d_in, C)
            if not fl["ok"]:
                return _err(f"sections[{i}].fittings[{j}]: {fl['reason']}")
            fitting_total += fl["fitting_loss_in_wg"]
            all_warns.extend(
                [f"sections[{i}].fittings[{j}]: {w}" for w in fl.get("warnings", [])]
            )

        section_total = sec_loss + fitting_total
        total_in_wg += section_total
        section_results.append({
            "section_index": i,
            "cfm": float(cfm),
            "diameter_in": float(d_in),
            "length_ft": float(L_ft),
            "friction_loss_in_wg": round(sec_loss, 5),
            "fitting_loss_in_wg": round(fitting_total, 5),
            "section_total_in_wg": round(section_total, 5),
        })

    total_Pa = total_in_wg * 249.089

    return {
        "ok": True,
        "total_static_pressure_in_wg": round(total_in_wg, 4),
        "total_static_pressure_Pa": round(total_Pa, 2),
        "sections": section_results,
        "warnings": all_warns,
    }


# ---------------------------------------------------------------------------
# 9. fan_law_scale
# ---------------------------------------------------------------------------

def fan_law_scale(
    cfm1: float,
    sp1: float,
    bhp1: float,
    cfm2: float,
) -> dict:
    """Fan-law affinity law scaling to a new airflow.

    Assumes the same fan at changed speed (or geometrically similar fan):
        CFM₂/CFM₁ = N₂/N₁     (speed ratio)
        SP₂  = SP₁  × (CFM₂/CFM₁)²
        BHP₂ = BHP₁ × (CFM₂/CFM₁)³

    Parameters
    ----------
    cfm1 : float
        Original airflow (CFM). Must be > 0.
    sp1 : float
        Original static pressure (in. w.g.). Must be > 0.
    bhp1 : float
        Original brake horsepower (BHP). Must be > 0.
    cfm2 : float
        New target airflow (CFM). Must be > 0.

    Returns
    -------
    dict
        ok        : True
        cfm2      : new airflow (CFM)
        sp2_in_wg : new static pressure (in. w.g.)
        sp2_Pa    : new static pressure (Pa)
        bhp2      : new brake horsepower
        speed_ratio: CFM₂/CFM₁ = N₂/N₁
        cfm1      : original airflow
        sp1_in_wg : original static pressure
        bhp1      : original BHP
        warnings  : advisory strings
    """
    for name, val in [("cfm1", cfm1), ("sp1", sp1), ("bhp1", bhp1), ("cfm2", cfm2)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    r = float(cfm2) / float(cfm1)
    sp2 = float(sp1) * r ** 2
    bhp2 = float(bhp1) * r ** 3
    sp2_Pa = sp2 * 249.089

    warns: list[str] = []
    if r > 1.2:
        warns.append(
            f"Speed ratio {r:.2f} exceeds 1.2; fan-law accuracy degrades above ~20% "
            "speed change for real fans; verify with manufacturer curve."
        )
    if r < 0.5:
        warns.append(
            f"Speed ratio {r:.2f} is below 0.5; motor efficiency and stability may "
            "be significantly reduced at very low speeds."
        )

    return {
        "ok": True,
        "cfm2": float(cfm2),
        "sp2_in_wg": round(sp2, 5),
        "sp2_Pa": round(sp2_Pa, 2),
        "bhp2": round(bhp2, 5),
        "speed_ratio": round(r, 6),
        "cfm1": float(cfm1),
        "sp1_in_wg": float(sp1),
        "bhp1": float(bhp1),
        "warnings": warns,
    }
