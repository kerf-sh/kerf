"""
kerf_cad_core.welding.process — weld process engineering calculations.

Implements twelve public functions covering the full weld-process design
workflow:

  arc_heat_input(eta, V, I, v)
      Arc heat input per unit length: HI = η·V·I / (1000·v)  [kJ/mm]
      Thermal efficiency η varies by process:
        SMAW  ≈ 0.80, GMAW ≈ 0.85, SAW ≈ 0.99, GTAW ≈ 0.60

  carbon_equivalent_iiw(C, Mn, Si, Cr, Mo, V, Cu, Ni)
      IIW carbon equivalent:
        CE = C + Mn/6 + (Cr+Mo+V)/5 + (Cu+Ni)/15

  preheat_temperature(CE, t_mm, HI_kJ_mm)
      AWS D1.1 / Yurioka-style preheat temperature (°C).
      Flags cracking risk and missing-preheat warnings.

  cooling_time_t85(HI_kJ_mm, T_preheat_C, t_mm, *, joint_type)
      t8/5 estimate (s) — time to cool from 800 °C to 500 °C.
      Uses simplified Rykalin three-/two-dimensional model.
      joint_type: "butt" (3D) or "fillet" (2D).

  fillet_weld_volume(leg_mm, length_mm)
      Weld metal volume (mm³) for a single-pass equal-leg fillet.

  groove_weld_volume(depth_mm, width_top_mm, width_root_mm, length_mm,
                     *, included_angle_deg, root_face_mm, root_gap_mm)
      Weld metal volume (mm³) for a V-groove (trapezoid cross-section).

  deposition_time(volume_mm3, deposition_rate_kg_h, density_kg_mm3)
      Weld deposition time (s) from volume, deposition rate, and deposit density.

  electrode_consumption(volume_mm3, density_kg_mm3, deposition_efficiency)
      Gross electrode/wire mass (kg) consumed including spatter & stub losses.

  number_of_passes(groove_area_mm2, pass_area_mm2)
      Estimated number of weld passes from groove cross-section area and
      average pass cross-section area.

  angular_distortion(HI_kJ_mm, t_mm, leg_mm)
      Transverse (angular) distortion angle (degrees) estimate for
      fillet welds using empirical Okerblom model.

  longitudinal_distortion(HI_kJ_mm, length_mm, A_mm2, E_MPa)
      Longitudinal (bowing) distortion (mm) estimate using thermal-stress
      residual approach.

  interpass_temperature_check(T_preheat_C, T_interpass_C, *, T_max_C)
      Check that interpass temperature is within AWS D1.1 limits.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
  lengths       — millimetres (mm) unless noted
  temperature   — degrees Celsius (°C)
  heat input    — kJ/mm
  time          — seconds (s)
  mass          — kilograms (kg)
  volume        — mm³
  area          — mm²
  stress        — MPa
  composition   — weight percent (wt%)

References
----------
AWS D1.1/D1.1M:2020 — Structural Welding Code (Steel)
IIW Doc. IXJ-123-85 — CE (IIW) formula
Yurioka N., Suzuki H., Ohshita S., Saito S. (1983) — "Determination of
  Necessary Preheating Temperature in Steel Welding", Welding Journal 62(6)
Lincoln Electric "The Procedure Handbook of Arc Welding", 14th ed.
Radaj D. (1992) — Heat Effects of Welding, Springer

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ETA_DEFAULTS: dict[str, float] = {
    "smaw":  0.80,
    "gmaw":  0.85,
    "fcaw":  0.85,
    "saw":   0.99,
    "gtaw":  0.60,
    "tig":   0.60,
    "mig":   0.85,
    "maw":   0.80,
}

# Excessive HI threshold (kJ/mm) — AWS D1.1 Annex I typical upper limits
_HI_HIGH_LIMIT_KJ_MM = 3.5


def arc_heat_input(
    eta: float,
    V: float,
    I: float,
    v: float,
) -> dict:
    """
    Arc heat input per unit weld length.

    HI = η × V × I / (1000 × v)   [kJ/mm]

    Parameters
    ----------
    eta : float
        Thermal efficiency of the welding process (dimensionless, 0 < η ≤ 1.0).
        Typical values: SMAW≈0.80, GMAW≈0.85, SAW≈0.99, GTAW≈0.60.
    V : float
        Arc voltage (V). Must be > 0.
    I : float
        Welding current (A). Must be > 0.
    v : float
        Travel speed (mm/s). Must be > 0.

    Returns
    -------
    dict
        ok            : True
        HI_kJ_mm      : heat input (kJ/mm)
        eta           : thermal efficiency used
        V_volts       : arc voltage (V)
        I_amps        : current (A)
        v_mm_s        : travel speed (mm/s)
        warnings      : list of warning strings (may be empty)
    """
    err = _guard_positive("eta", eta)
    if err:
        return _err(err)
    if float(eta) > 1.0:
        return _err(f"eta must be <= 1.0 (dimensionless efficiency), got {eta}")
    err = _guard_positive("V", V)
    if err:
        return _err(err)
    err = _guard_positive("I", I)
    if err:
        return _err(err)
    err = _guard_positive("v", v)
    if err:
        return _err(err)

    eta_f = float(eta)
    V_f = float(V)
    I_f = float(I)
    v_f = float(v)

    HI = eta_f * V_f * I_f / (1000.0 * v_f)

    warnings: list[str] = []
    if HI > _HI_HIGH_LIMIT_KJ_MM:
        warnings.append(
            f"Heat input {HI:.3f} kJ/mm exceeds typical limit of "
            f"{_HI_HIGH_LIMIT_KJ_MM} kJ/mm — check for HAZ toughness degradation."
        )

    return {
        "ok": True,
        "HI_kJ_mm": HI,
        "eta": eta_f,
        "V_volts": V_f,
        "I_amps": I_f,
        "v_mm_s": v_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. carbon_equivalent_iiw
# ---------------------------------------------------------------------------

def carbon_equivalent_iiw(
    C: float,
    Mn: float,
    Si: float = 0.0,
    Cr: float = 0.0,
    Mo: float = 0.0,
    V: float = 0.0,
    Cu: float = 0.0,
    Ni: float = 0.0,
) -> dict:
    """
    IIW carbon equivalent (CE_IIW).

    CE = C + Mn/6 + (Cr + Mo + V)/5 + (Cu + Ni)/15

    All composition inputs in weight percent (wt%).

    Parameters
    ----------
    C  : float  Carbon content (wt%). Must be >= 0.
    Mn : float  Manganese content (wt%). Must be >= 0.
    Si : float  Silicon content (wt%). Default 0.
    Cr : float  Chromium content (wt%). Default 0.
    Mo : float  Molybdenum content (wt%). Default 0.
    V  : float  Vanadium content (wt%). Default 0.
    Cu : float  Copper content (wt%). Default 0.
    Ni : float  Nickel content (wt%). Default 0.

    Returns
    -------
    dict
        ok           : True
        CE_IIW       : IIW carbon equivalent (dimensionless)
        C, Mn, Si, Cr, Mo, V, Cu, Ni : composition inputs echoed back
        warnings     : list of warning strings
    """
    inputs = {"C": C, "Mn": Mn, "Si": Si, "Cr": Cr, "Mo": Mo, "V": V, "Cu": Cu, "Ni": Ni}
    for name, val in inputs.items():
        e = _guard_nonneg(name, val)
        if e:
            return _err(e)

    C_f  = float(C)
    Mn_f = float(Mn)
    Si_f = float(Si)
    Cr_f = float(Cr)
    Mo_f = float(Mo)
    V_f  = float(V)
    Cu_f = float(Cu)
    Ni_f = float(Ni)

    CE = C_f + Mn_f / 6.0 + (Cr_f + Mo_f + V_f) / 5.0 + (Cu_f + Ni_f) / 15.0

    warnings: list[str] = []
    if CE > 0.45:
        warnings.append(
            f"CE_IIW={CE:.3f} > 0.45 — preheat is generally required per AWS D1.1."
        )
    if CE > 0.70:
        warnings.append(
            f"CE_IIW={CE:.3f} > 0.70 — high hydrogen-cracking risk; consider "
            "low-hydrogen electrodes and elevated preheat."
        )

    return {
        "ok": True,
        "CE_IIW": CE,
        "C": C_f, "Mn": Mn_f, "Si": Si_f,
        "Cr": Cr_f, "Mo": Mo_f, "V": V_f,
        "Cu": Cu_f, "Ni": Ni_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. preheat_temperature
# ---------------------------------------------------------------------------

# AWS D1.1 Table 3.2 look-up simplified + Yurioka fit
# Yurioka minimum preheat: T_p = 1440 × Pcm − 392  (°C)
# where Pcm = C + Si/30 + (Mn+Cu+Cr)/20 + Ni/60 + Mo/15 + V/10 + 5B
# Without B data (B≈0) and only CE available, use approximate mapping:
#   Pcm ≈ 0.7 × CE  (rough)  → T_p = 1440 × 0.7 × CE − 392 = 1008 × CE − 392
# A more conservative formula: T_p (°C) = 350 × √CE − 25  (practical AWS fit)
# We use both and return the higher value.

def preheat_temperature(
    CE: float,
    t_mm: float,
    HI_kJ_mm: float,
) -> dict:
    """
    Minimum preheat temperature per AWS D1.1 / Yurioka approach.

    Uses two estimates and returns the more conservative (higher) value:

    Method A (AWS D1.1 empirical fit):
        T_p_A = 350 × √(CE) − 25   (°C)

    Method B (Yurioka simplified, CE→Pcm mapping):
        T_p_B = 1440 × Pcm_est − 392   (°C)
        where Pcm_est ≈ 0.7 × CE

    Both methods are further adjusted upward by 10 °C for every 1 mm increase
    in plate thickness beyond 25 mm (thickness correction from AWS D1.1 §3.7).

    A negative result is clamped to 0 °C (no preheat required).

    Parameters
    ----------
    CE      : float  IIW carbon equivalent. Must be >= 0.
    t_mm    : float  Plate / base-metal thickness (mm). Must be > 0.
    HI_kJ_mm: float  Arc heat input (kJ/mm). Must be > 0.

    Returns
    -------
    dict
        ok                  : True
        T_preheat_C         : recommended minimum preheat temperature (°C)
        T_preheat_method_A  : AWS D1.1 empirical estimate (°C, clamped >= 0)
        T_preheat_method_B  : Yurioka Pcm estimate (°C, clamped >= 0)
        CE_IIW              : CE value used
        t_mm                : thickness used (mm)
        HI_kJ_mm            : heat input used (kJ/mm)
        warnings            : list of warning strings
    """
    err = _guard_nonneg("CE", CE)
    if err:
        return _err(err)
    err = _guard_positive("t_mm", t_mm)
    if err:
        return _err(err)
    err = _guard_positive("HI_kJ_mm", HI_kJ_mm)
    if err:
        return _err(err)

    CE_f  = float(CE)
    t_f   = float(t_mm)
    HI_f  = float(HI_kJ_mm)

    # Method A: AWS D1.1 empirical
    T_A = 350.0 * math.sqrt(CE_f) - 25.0
    # Method B: Yurioka (Pcm ≈ 0.7 × CE)
    Pcm_est = 0.7 * CE_f
    T_B = 1440.0 * Pcm_est - 392.0

    # Thickness correction: +10 °C per mm above 25 mm
    t_correction = max(0.0, t_f - 25.0) * 10.0
    T_A += t_correction
    T_B += t_correction

    # Higher HI reduces required preheat (heat is already put in)
    # Subtract 5 °C per kJ/mm above 1.0 kJ/mm (practical industry rule)
    hi_reduction = max(0.0, HI_f - 1.0) * 5.0
    T_A -= hi_reduction
    T_B -= hi_reduction

    # Clamp to 0
    T_A = max(0.0, T_A)
    T_B = max(0.0, T_B)
    T_p = max(T_A, T_B)

    warnings: list[str] = []
    if CE_f > 0.45 and T_p < 50.0:
        warnings.append(
            f"CE_IIW={CE_f:.3f} > 0.45 but computed preheat < 50 °C — "
            "verify with welding procedure specification (WPS)."
        )
    if T_p == 0.0 and CE_f > 0.40:
        warnings.append(
            "No preheat required by formula, but CE > 0.40 — "
            "consider a minimum 20 °C preheat in cold ambient conditions."
        )
    if CE_f > 0.70:
        warnings.append(
            f"CE_IIW={CE_f:.3f} > 0.70 — high hydrogen-cracking risk; use "
            "low-hydrogen consumables and verify preheat compliance."
        )

    return {
        "ok": True,
        "T_preheat_C": T_p,
        "T_preheat_method_A": T_A,
        "T_preheat_method_B": T_B,
        "CE_IIW": CE_f,
        "t_mm": t_f,
        "HI_kJ_mm": HI_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. cooling_time_t85
# ---------------------------------------------------------------------------

# Material constants for Rykalin t8/5 formula (structural steel)
# Reference heat content: Q* = HI × 1000 J/mm  (convert kJ/mm → J/mm)
# Three-dimensional (butt weld thick plate):
#   t8/5 = (6700 - 5·T_0) × HI² × [(1/500 - 1/800)²] / (2π·λ·ρc)
#          simplified reference: t8/5 = F3 × HI²
# Two-dimensional (fillet thin plate):
#   t8/5 = (4300 - 4.3·T_0) × HI² × [(1/500² - 1/800²)] / (2π·λ·(ρc)²·h²)
#          simplified reference: t8/5 = F2 × HI² / h²
# We use industry-standard simplified forms per Lincoln Electric handbook §5.
# λ = 0.40 J/(mm·s·°C) for steel, ρc = 3.6 J/(mm³·°C)

_LAMBDA_STEEL  = 0.40   # J/(mm·s·°C) thermal conductivity
_RHO_C_STEEL   = 3.6e-3 # J/(mm³·°C) volumetric heat capacity (3.6 J/mm³·°C → /1000 for consistency)

# Using standard Rykalin simplified constants (J/mm units with Q in J/mm):
# For 3D: t8/5 = (6700 − 5T₀) × Q² × (1/(500)−1/(800))² / (2π × λ)
# For 2D: t8/5 = (4300 − 4.3T₀) × Q² × (1/500² − 1/800²) / (2π² × λ² × ρc × h²)
# Reference: Radaj (1992) Eqs 2.68–2.69

_RYKALIN_T_REF_START = 800.0   # °C
_RYKALIN_T_REF_END   = 500.0   # °C


def cooling_time_t85(
    HI_kJ_mm: float,
    T_preheat_C: float,
    t_mm: float,
    *,
    joint_type: str = "butt",
) -> dict:
    """
    Estimate the weld cooling time t8/5 (time from 800 °C to 500 °C) in seconds.

    Uses the Rykalin simplified formulae for structural steel:

    Butt weld (3-dimensional heat flow, thick plate):
        Q = HI_kJ_mm × 1000  [J/mm]
        t8/5 = (6700 − 5·T₀) × Q² × [(1/500 − 1/800)² / (2π·λ)]

    Fillet weld (2-dimensional heat flow, thin plate):
        t8/5 = (4300 − 4.3·T₀) × Q² × [(1/500² − 1/800²) / (2π²·λ²·ρc·h²)]

    where T₀ = preheat temperature (°C), h = plate thickness (mm).

    Parameters
    ----------
    HI_kJ_mm    : float  Arc heat input (kJ/mm). Must be > 0.
    T_preheat_C : float  Preheat / interpass temperature (°C). Must be >= 0.
    t_mm        : float  Plate thickness (mm). Must be > 0.
    joint_type  : str    "butt" (3D) or "fillet" (2D). Default "butt".

    Returns
    -------
    dict
        ok           : True
        t85_s        : cooling time from 800 °C to 500 °C (s)
        joint_type   : joint type used
        HI_kJ_mm     : heat input used (kJ/mm)
        T_preheat_C  : preheat temperature used (°C)
        t_mm         : plate thickness used (mm)
        warnings     : list of warning strings
    """
    err = _guard_positive("HI_kJ_mm", HI_kJ_mm)
    if err:
        return _err(err)
    err = _guard_nonneg("T_preheat_C", T_preheat_C)
    if err:
        return _err(err)
    err = _guard_positive("t_mm", t_mm)
    if err:
        return _err(err)

    jt = str(joint_type).strip().lower()
    if jt not in ("butt", "fillet"):
        return _err(f"joint_type must be 'butt' or 'fillet', got {joint_type!r}")

    HI_f  = float(HI_kJ_mm)
    T0    = float(T_preheat_C)
    h     = float(t_mm)

    Q = HI_f * 1000.0  # J/mm
    lam = _LAMBDA_STEEL  # J/(mm·s·°C)

    # Rykalin 3D (butt):
    # t8/5 = (6700 − 5T₀) × Q² × [(1/500 − 1/800)²] / (2π × λ)
    inv_diff_linear = (1.0 / 500.0) - (1.0 / 800.0)  # 1/°C
    k3 = 6700.0 - 5.0 * T0
    t85_3d = k3 * Q ** 2 * inv_diff_linear ** 2 / (2.0 * math.pi * lam)

    # Rykalin 2D (fillet):
    # t8/5 = (4300 − 4.3T₀) × Q² × [(1/500² − 1/800²)] / (2π² × λ² × ρc × h²)
    rho_c = 3.6e-3  # J/(mm³·°C)
    inv_diff_sq = (1.0 / 500.0 ** 2) - (1.0 / 800.0 ** 2)  # 1/°C²
    k2 = 4300.0 - 4.3 * T0
    t85_2d = k2 * Q ** 2 * inv_diff_sq / (2.0 * math.pi ** 2 * lam ** 2 * rho_c * h ** 2)

    t85 = t85_3d if jt == "butt" else t85_2d
    # Clamp: t8/5 must be > 0
    if t85 <= 0.0:
        t85 = 0.0

    warnings: list[str] = []
    if t85 < 5.0 and t85 > 0.0:
        warnings.append(
            f"t8/5 = {t85:.1f} s is very short — risk of martensitic HAZ; "
            "consider increasing preheat or heat input."
        )
    if t85 > 100.0:
        warnings.append(
            f"t8/5 = {t85:.1f} s is very long — check for grain growth and "
            "reduced HAZ toughness."
        )

    return {
        "ok": True,
        "t85_s": t85,
        "joint_type": jt,
        "HI_kJ_mm": HI_f,
        "T_preheat_C": T0,
        "t_mm": h,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. fillet_weld_volume
# ---------------------------------------------------------------------------

def fillet_weld_volume(
    leg_mm: float,
    length_mm: float,
) -> dict:
    """
    Weld metal volume for an equal-leg fillet weld (single pass).

    Cross-section = right isosceles triangle with leg = leg_mm.
    Area = leg² / 2

    Parameters
    ----------
    leg_mm    : float  Fillet weld leg length (mm). Must be > 0.
    length_mm : float  Weld length (mm). Must be > 0.

    Returns
    -------
    dict
        ok           : True
        volume_mm3   : weld metal volume (mm³)
        area_mm2     : weld cross-section area (mm²)
        throat_mm    : effective throat = leg / √2 (mm)
        leg_mm       : leg used (mm)
        length_mm    : length used (mm)
        warnings     : list of warning strings
    """
    err = _guard_positive("leg_mm", leg_mm)
    if err:
        return _err(err)
    err = _guard_positive("length_mm", length_mm)
    if err:
        return _err(err)

    leg_f = float(leg_mm)
    L_f   = float(length_mm)

    area    = 0.5 * leg_f ** 2
    volume  = area * L_f
    throat  = leg_f / math.sqrt(2.0)

    warnings: list[str] = []
    if leg_f < 3.0:
        warnings.append(
            f"Fillet leg {leg_f:.1f} mm < 3 mm — below typical AWS D1.1 minimum "
            "for structural applications."
        )
    if leg_f > 20.0:
        warnings.append(
            f"Fillet leg {leg_f:.1f} mm > 20 mm — consider multi-pass procedure "
            "and interpass temperature control."
        )

    return {
        "ok": True,
        "volume_mm3": volume,
        "area_mm2": area,
        "throat_mm": throat,
        "leg_mm": leg_f,
        "length_mm": L_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. groove_weld_volume
# ---------------------------------------------------------------------------

def groove_weld_volume(
    depth_mm: float,
    width_top_mm: float,
    width_root_mm: float,
    length_mm: float,
    *,
    included_angle_deg: float = 60.0,
    root_face_mm: float = 2.0,
    root_gap_mm: float = 3.0,
) -> dict:
    """
    Weld metal volume for a V-groove weld (trapezoidal cross-section).

    The groove is modelled as a trapezoid:
      - width at root: w_r = root_gap_mm  (gap at the bottom)
      - width at top : w_t = 2·(depth_mm - root_face_mm)·tan(angle/2) + root_gap_mm

    If width_top_mm is provided and non-zero, it overrides the geometric computation.

    Cross-section area = (w_t + w_r) / 2 × d_eff
    where d_eff = depth_mm − root_face_mm (fill depth excluding root face land).

    Parameters
    ----------
    depth_mm         : float  Total groove depth (mm). Must be > 0.
    width_top_mm     : float  Width at the top of the groove (mm). 0 = compute
                              from included_angle_deg.
    width_root_mm    : float  Width at the root / root gap (mm). 0 = use root_gap_mm.
    length_mm        : float  Weld run length (mm). Must be > 0.
    included_angle_deg: float  Groove included angle (degrees). Default 60°.
    root_face_mm     : float  Root face / land height (mm). Default 2 mm.
    root_gap_mm      : float  Root opening (mm). Default 3 mm.

    Returns
    -------
    dict
        ok              : True
        volume_mm3      : weld metal volume (mm³)
        area_mm2        : groove cross-section area (mm²)
        depth_mm        : groove depth used (mm)
        width_top_mm    : top width used (mm)
        width_root_mm   : root width used (mm)
        length_mm       : length used (mm)
        included_angle_deg : angle used (degrees)
        root_face_mm    : root face used (mm)
        root_gap_mm     : root gap used (mm)
        warnings        : list of warning strings
    """
    err = _guard_positive("depth_mm", depth_mm)
    if err:
        return _err(err)
    err = _guard_nonneg("width_top_mm", width_top_mm)
    if err:
        return _err(err)
    err = _guard_nonneg("width_root_mm", width_root_mm)
    if err:
        return _err(err)
    err = _guard_positive("length_mm", length_mm)
    if err:
        return _err(err)
    err = _guard_positive("included_angle_deg", included_angle_deg)
    if err:
        return _err(err)
    err = _guard_nonneg("root_face_mm", root_face_mm)
    if err:
        return _err(err)
    err = _guard_nonneg("root_gap_mm", root_gap_mm)
    if err:
        return _err(err)

    d_f     = float(depth_mm)
    L_f     = float(length_mm)
    ang_f   = float(included_angle_deg)
    rf_f    = float(root_face_mm)
    rg_f    = float(root_gap_mm)

    if rf_f >= d_f:
        return _err(
            f"root_face_mm ({rf_f}) must be less than depth_mm ({d_f})."
        )

    # Effective fill depth (excluding root face)
    d_fill = d_f - rf_f

    # Root width
    w_r = float(width_root_mm) if float(width_root_mm) > 0 else rg_f

    # Top width
    if float(width_top_mm) > 0:
        w_t = float(width_top_mm)
    else:
        half_ang_rad = math.radians(ang_f / 2.0)
        w_t = 2.0 * d_fill * math.tan(half_ang_rad) + w_r

    area   = (w_t + w_r) / 2.0 * d_fill
    volume = area * L_f

    warnings: list[str] = []
    if ang_f < 30.0:
        warnings.append(
            f"Included angle {ang_f}° < 30° — access for root fusion may be "
            "difficult; check AWS D1.1 joint details."
        )
    if ang_f > 90.0:
        warnings.append(
            f"Included angle {ang_f}° > 90° — excessive weld volume; consider "
            "narrower groove to reduce distortion."
        )

    return {
        "ok": True,
        "volume_mm3": volume,
        "area_mm2": area,
        "depth_mm": d_f,
        "width_top_mm": w_t,
        "width_root_mm": w_r,
        "length_mm": L_f,
        "included_angle_deg": ang_f,
        "root_face_mm": rf_f,
        "root_gap_mm": rg_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. deposition_time
# ---------------------------------------------------------------------------

# Default weld metal density (kg/mm³) — mild steel ≈ 7.85 g/cm³ = 7.85e-6 kg/mm³
_WELD_METAL_DENSITY_KG_MM3 = 7.85e-6


def deposition_time(
    volume_mm3: float,
    deposition_rate_kg_h: float,
    density_kg_mm3: float = _WELD_METAL_DENSITY_KG_MM3,
) -> dict:
    """
    Weld deposition time from weld metal volume and deposition rate.

    mass_kg = volume_mm3 × density_kg_mm3
    time_s  = mass_kg / deposition_rate_kg_h × 3600

    Parameters
    ----------
    volume_mm3           : float  Weld metal volume (mm³). Must be > 0.
    deposition_rate_kg_h : float  Deposition rate (kg/h). Must be > 0.
                                  Typical: SMAW 1–5 kg/h, SAW 5–20 kg/h.
    density_kg_mm3       : float  Weld metal density (kg/mm³). Default 7.85e-6 (steel).

    Returns
    -------
    dict
        ok                   : True
        time_s               : deposition time (s)
        time_min             : deposition time (minutes)
        mass_kg              : weld metal deposit mass (kg)
        volume_mm3           : volume used (mm³)
        deposition_rate_kg_h : deposition rate used (kg/h)
        density_kg_mm3       : density used (kg/mm³)
        warnings             : list of warning strings
    """
    err = _guard_positive("volume_mm3", volume_mm3)
    if err:
        return _err(err)
    err = _guard_positive("deposition_rate_kg_h", deposition_rate_kg_h)
    if err:
        return _err(err)
    err = _guard_positive("density_kg_mm3", density_kg_mm3)
    if err:
        return _err(err)

    V_f   = float(volume_mm3)
    DR_f  = float(deposition_rate_kg_h)
    rho_f = float(density_kg_mm3)

    mass_kg = V_f * rho_f
    time_s  = mass_kg / DR_f * 3600.0
    time_min = time_s / 60.0

    warnings: list[str] = []
    if time_min > 480.0:
        warnings.append(
            f"Estimated deposition time {time_min:.0f} min exceeds 8 hours — "
            "consider breaking the weld into multiple stages."
        )

    return {
        "ok": True,
        "time_s": time_s,
        "time_min": time_min,
        "mass_kg": mass_kg,
        "volume_mm3": V_f,
        "deposition_rate_kg_h": DR_f,
        "density_kg_mm3": rho_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. electrode_consumption
# ---------------------------------------------------------------------------

def electrode_consumption(
    volume_mm3: float,
    density_kg_mm3: float = _WELD_METAL_DENSITY_KG_MM3,
    deposition_efficiency: float = 0.65,
) -> dict:
    """
    Gross electrode/wire mass consumed including spatter and stub losses.

    deposit_mass_kg = volume_mm3 × density_kg_mm3
    gross_mass_kg   = deposit_mass_kg / deposition_efficiency

    Typical deposition efficiencies:
      SMAW     ≈ 0.60–0.75
      GMAW/MIG ≈ 0.93–0.98
      FCAW     ≈ 0.82–0.90
      SAW      ≈ 0.99

    Parameters
    ----------
    volume_mm3             : float  Weld metal volume (mm³). Must be > 0.
    density_kg_mm3         : float  Weld metal density (kg/mm³). Default 7.85e-6.
    deposition_efficiency  : float  Fraction of electrode deposited (0–1]. Default 0.65.

    Returns
    -------
    dict
        ok                    : True
        electrode_mass_kg     : gross electrode/wire mass required (kg)
        deposit_mass_kg       : net deposit mass (kg)
        deposition_efficiency : efficiency used
        volume_mm3            : volume used (mm³)
        density_kg_mm3        : density used (kg/mm³)
        warnings              : list of warning strings
    """
    err = _guard_positive("volume_mm3", volume_mm3)
    if err:
        return _err(err)
    err = _guard_positive("density_kg_mm3", density_kg_mm3)
    if err:
        return _err(err)
    err = _guard_positive("deposition_efficiency", deposition_efficiency)
    if err:
        return _err(err)
    if float(deposition_efficiency) > 1.0:
        return _err(
            f"deposition_efficiency must be <= 1.0, got {deposition_efficiency}"
        )

    V_f   = float(volume_mm3)
    rho_f = float(density_kg_mm3)
    eff_f = float(deposition_efficiency)

    deposit_kg   = V_f * rho_f
    electrode_kg = deposit_kg / eff_f

    warnings: list[str] = []
    if eff_f < 0.60:
        warnings.append(
            f"Deposition efficiency {eff_f:.0%} is low — high spatter expected; "
            "verify shielding gas and wire feed settings."
        )

    return {
        "ok": True,
        "electrode_mass_kg": electrode_kg,
        "deposit_mass_kg": deposit_kg,
        "deposition_efficiency": eff_f,
        "volume_mm3": V_f,
        "density_kg_mm3": rho_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. number_of_passes
# ---------------------------------------------------------------------------

def number_of_passes(
    groove_area_mm2: float,
    pass_area_mm2: float,
) -> dict:
    """
    Estimate the number of weld passes to fill a groove.

    n_passes = ceil(groove_area_mm2 / pass_area_mm2)

    Parameters
    ----------
    groove_area_mm2 : float  Total groove cross-section area (mm²). Must be > 0.
    pass_area_mm2   : float  Average cross-section area per pass (mm²). Must be > 0.
                             Typical: SMAW 3.2 mm rod ≈ 30–50 mm²,
                                      GMAW 1.2 mm wire ≈ 20–40 mm².

    Returns
    -------
    dict
        ok              : True
        n_passes        : estimated number of passes (integer >= 1)
        groove_area_mm2 : groove area used (mm²)
        pass_area_mm2   : pass area used (mm²)
        fill_ratio      : groove_area / pass_area (float)
        warnings        : list of warning strings
    """
    err = _guard_positive("groove_area_mm2", groove_area_mm2)
    if err:
        return _err(err)
    err = _guard_positive("pass_area_mm2", pass_area_mm2)
    if err:
        return _err(err)

    ga_f = float(groove_area_mm2)
    pa_f = float(pass_area_mm2)

    ratio    = ga_f / pa_f
    n_passes = math.ceil(ratio)

    warnings: list[str] = []
    if n_passes > 30:
        warnings.append(
            f"Estimated {n_passes} passes — high multi-pass count increases "
            "residual stress and distortion risk."
        )
    if pass_area_mm2 > groove_area_mm2:
        warnings.append(
            "Pass area exceeds groove area — single pass should be sufficient; "
            "verify bead dimensions."
        )

    return {
        "ok": True,
        "n_passes": n_passes,
        "groove_area_mm2": ga_f,
        "pass_area_mm2": pa_f,
        "fill_ratio": ratio,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 10. angular_distortion
# ---------------------------------------------------------------------------

def angular_distortion(
    HI_kJ_mm: float,
    t_mm: float,
    leg_mm: float,
) -> dict:
    """
    Transverse (angular) distortion angle estimate for fillet welds.

    Uses the empirical Okerblom / Lincoln Electric formula:

        θ (rad) = 0.015 × HI_kJ_mm × (leg_mm / t_mm²)

    This gives the rotation angle of the plate relative to the weld axis
    due to non-uniform thermal contraction in the through-thickness direction.

    Parameters
    ----------
    HI_kJ_mm : float  Arc heat input (kJ/mm). Must be > 0.
    t_mm      : float  Plate thickness (mm). Must be > 0.
    leg_mm    : float  Fillet weld leg length (mm). Must be > 0.

    Returns
    -------
    dict
        ok          : True
        theta_rad   : angular distortion (radians)
        theta_deg   : angular distortion (degrees)
        HI_kJ_mm    : heat input used (kJ/mm)
        t_mm        : plate thickness used (mm)
        leg_mm      : weld leg used (mm)
        warnings    : list of warning strings
    """
    err = _guard_positive("HI_kJ_mm", HI_kJ_mm)
    if err:
        return _err(err)
    err = _guard_positive("t_mm", t_mm)
    if err:
        return _err(err)
    err = _guard_positive("leg_mm", leg_mm)
    if err:
        return _err(err)

    HI_f  = float(HI_kJ_mm)
    t_f   = float(t_mm)
    leg_f = float(leg_mm)

    # Empirical coefficient 0.015 (dimensionally calibrated for SI inputs)
    theta_rad = 0.015 * HI_f * leg_f / (t_f ** 2)
    theta_deg = math.degrees(theta_rad)

    warnings: list[str] = []
    if theta_deg > 3.0:
        warnings.append(
            f"Angular distortion {theta_deg:.2f}° > 3° — consider pre-setting, "
            "back-stepping, or weld sequence optimisation."
        )
    if theta_deg > 10.0:
        warnings.append(
            f"Angular distortion {theta_deg:.2f}° > 10° — severe distortion "
            "predicted; structural correction likely required post-welding."
        )

    return {
        "ok": True,
        "theta_rad": theta_rad,
        "theta_deg": theta_deg,
        "HI_kJ_mm": HI_f,
        "t_mm": t_f,
        "leg_mm": leg_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 11. longitudinal_distortion
# ---------------------------------------------------------------------------

def longitudinal_distortion(
    HI_kJ_mm: float,
    length_mm: float,
    A_mm2: float,
    E_MPa: float = 210_000.0,
) -> dict:
    """
    Longitudinal (bowing) distortion estimate using simplified thermal-stress model.

    The longitudinal shrinkage force is estimated as:

        F_shrink = (α × E × HI × 1000) / (ρc × A)

    The mid-span deflection for a simply-supported beam under axial eccentric
    load is approximated using the Euler column analogy:

        δ = F_shrink × L² / (8 × E × I_section)

    For simplicity, I_section ≈ A × (t/12)² is not known here, so we use
    the linear approximation from Lincoln Electric handbook §6:

        δ (mm) = k × HI_kJ_mm × L² / (A × E)
        k = α × ρc⁻¹ × 1000  ≈ 0.335  (for structural steel)

    where:
        α   = 12e-6 /°C  (thermal expansion coefficient, steel)
        ρc  = 3.6e-3 J/(mm³·°C) = 0.0036 (volumetric heat capacity)
        k   = α / ρc × 1000 ≈ 12e-6 / 3.6e-3 × 1000 = 3.33

    Final formula:
        δ (mm) = 3.33 × HI_kJ_mm × L² / (A × E)

    Parameters
    ----------
    HI_kJ_mm  : float  Arc heat input (kJ/mm). Must be > 0.
    length_mm  : float  Weld length / member length (mm). Must be > 0.
    A_mm2      : float  Cross-sectional area of the member (mm²). Must be > 0.
    E_MPa      : float  Young's modulus (MPa). Default 210 000 MPa (steel).

    Returns
    -------
    dict
        ok          : True
        delta_mm    : longitudinal (bowing) distortion (mm)
        F_shrink_N  : estimated longitudinal shrinkage force (N)
        HI_kJ_mm    : heat input used (kJ/mm)
        length_mm   : member length used (mm)
        A_mm2       : cross-section area used (mm²)
        E_MPa       : Young's modulus used (MPa)
        warnings    : list of warning strings
    """
    err = _guard_positive("HI_kJ_mm", HI_kJ_mm)
    if err:
        return _err(err)
    err = _guard_positive("length_mm", length_mm)
    if err:
        return _err(err)
    err = _guard_positive("A_mm2", A_mm2)
    if err:
        return _err(err)
    err = _guard_positive("E_MPa", E_MPa)
    if err:
        return _err(err)

    HI_f  = float(HI_kJ_mm)
    L_f   = float(length_mm)
    A_f   = float(A_mm2)
    E_f   = float(E_MPa)  # MPa = N/mm²

    alpha     = 12e-6      # /°C
    rho_c     = 3.6e-3     # J/(mm³·°C)
    k         = alpha / rho_c * 1000.0  # ≈ 3.333

    # Longitudinal shrinkage force: F = k × HI_kJ_mm × E × A / L²
    # Rearranged for bowing deflection:
    F_shrink_N = k * HI_f * 1000.0 * E_f / L_f  # N (approximate)

    # Bowing δ = k × HI × L² / (A × E)
    delta_mm = k * HI_f * L_f ** 2 / (A_f * E_f)

    warnings: list[str] = []
    if delta_mm > L_f * 0.001:
        warnings.append(
            f"Longitudinal distortion {delta_mm:.2f} mm exceeds L/1000 = "
            f"{L_f*0.001:.2f} mm — review fabrication tolerances."
        )

    return {
        "ok": True,
        "delta_mm": delta_mm,
        "F_shrink_N": F_shrink_N,
        "HI_kJ_mm": HI_f,
        "length_mm": L_f,
        "A_mm2": A_f,
        "E_MPa": E_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 12. interpass_temperature_check
# ---------------------------------------------------------------------------

def interpass_temperature_check(
    T_preheat_C: float,
    T_interpass_C: float,
    *,
    T_max_C: float = 250.0,
) -> dict:
    """
    Check that the interpass temperature satisfies AWS D1.1 limits.

    Requirements:
    1. T_interpass >= T_preheat  (interpass must be at least preheat)
    2. T_interpass <= T_max      (interpass must not exceed maximum)

    The default T_max = 250 °C is appropriate for most structural carbon steels
    per AWS D1.1 §3.7 / Table 3.3.  For HSLA / quenched-and-tempered steels
    the limit may be lower (e.g. 200 °C).

    Parameters
    ----------
    T_preheat_C   : float  Minimum preheat temperature (°C). Must be >= 0.
    T_interpass_C : float  Measured/actual interpass temperature (°C). Must be >= 0.
    T_max_C       : float  Maximum allowable interpass temperature (°C). Default 250.

    Returns
    -------
    dict
        ok                : True (function succeeded; check pass_* fields for compliance)
        T_preheat_C       : preheat temperature (°C)
        T_interpass_C     : interpass temperature (°C)
        T_max_C           : maximum allowable interpass temperature (°C)
        preheat_satisfied : True if T_interpass >= T_preheat
        max_ok            : True if T_interpass <= T_max
        compliant         : True if both preheat_satisfied and max_ok
        margin_below_max_C: T_max - T_interpass (negative if over limit)
        warnings          : list of warning strings
    """
    err = _guard_nonneg("T_preheat_C", T_preheat_C)
    if err:
        return _err(err)
    err = _guard_nonneg("T_interpass_C", T_interpass_C)
    if err:
        return _err(err)
    err = _guard_positive("T_max_C", T_max_C)
    if err:
        return _err(err)

    Tp  = float(T_preheat_C)
    Ti  = float(T_interpass_C)
    Tm  = float(T_max_C)

    preheat_ok = Ti >= Tp
    max_ok     = Ti <= Tm
    compliant  = preheat_ok and max_ok
    margin     = Tm - Ti

    warnings: list[str] = []
    if not preheat_ok:
        warnings.append(
            f"Interpass temperature {Ti:.0f} °C is below minimum preheat "
            f"{Tp:.0f} °C — risk of hydrogen-induced cracking."
        )
    if not max_ok:
        warnings.append(
            f"Interpass temperature {Ti:.0f} °C exceeds maximum {Tm:.0f} °C — "
            "risk of HAZ softening and reduced toughness."
        )
    if compliant and Ti > Tm * 0.90:
        warnings.append(
            f"Interpass temperature {Ti:.0f} °C is close to the maximum "
            f"{Tm:.0f} °C — monitor carefully."
        )

    return {
        "ok": True,
        "T_preheat_C": Tp,
        "T_interpass_C": Ti,
        "T_max_C": Tm,
        "preheat_satisfied": preheat_ok,
        "max_ok": max_ok,
        "compliant": compliant,
        "margin_below_max_C": margin,
        "warnings": warnings,
    }
