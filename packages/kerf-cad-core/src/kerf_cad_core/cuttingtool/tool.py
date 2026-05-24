"""
kerf_cad_core.cuttingtool.tool — cutting-tool geometry, mechanics & tool-life economics.

Implements the following public functions:

  orthogonal_to_normal(gamma_o, alpha_o, lambda_s)
      Convert orthogonal rake/clearance/inclination to normal-plane angles.

  normal_to_orthogonal(gamma_n, alpha_n, lambda_s)
      Inverse transform: normal-plane angles → orthogonal-plane angles.

  merchant_orthogonal(gamma_o, tau_s, mu, t1, vc)
      Merchant orthogonal cutting model — shear angle, forces, chip ratio,
      velocities (Boothroyd/Shaw hand-calc formulation).

  specific_cutting_energy(Fc, b, t1, vc)
      Specific cutting energy u [J/mm³] and specific power.

  cutting_power(Fc, vc)
      Cutting power from tangential force and cutting speed.

  taylor_tool_life(V, C, n)
      Taylor VTⁿ = C → tool life T for speed V.

  taylor_extended_tool_life(V, C, n, f, a_f, d, a_d, *, f_ref, d_ref)
      Extended Taylor VTⁿ fᵃ dᵇ = C → tool life.

  economic_cutting_speed(C_tool, t_ct, t_c, C_m, n, C_e, *, C_ref, n_ref)
      Economic (minimum-cost) cutting speed V_opt per Boothroyd §9.

  max_production_rate_speed(t_ct, t_c, n, C, *, C_ref, n_ref)
      Maximum-production-rate cutting speed V_mpr.

  break_even_speed(C_tool, t_ct, t_c, C_m, n, C, *, C_ref, n_ref)
      Break-even speed between min-cost and max-production-rate.

  machinability_rating(V_material, V_reference)
      Machinability index as percentage of reference material.

  nose_radius_roughness(f, r_n)
      Theoretical peak-to-valley (Rt) and arithmetic mean (Ra) surface
      finish from feed and nose radius (ideal turning formula).

All functions return a plain dict:
    success → {"ok": True, ...computed fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Stability or range warnings are issued via the
``warnings`` module (``warnings.warn``), never via exceptions.

Units
-----
Angles      — degrees (inputs/outputs) unless stated
Forces      — Newtons (N)
Stress      — Pascals (Pa)
Speed/vel   — m/min (cutting speed)
Feed        — mm/rev
Depth       — mm
Length      — mm
Power       — Watts (W)
Energy      — J/mm³
Time        — minutes
Cost        — dimensionless (same currency unit as inputs)

References
----------
Boothroyd, G. & Knight, W.A. "Fundamentals of Machining and Machine Tools",
  3rd ed. (2006), Chapters 2, 8, 9.
Shaw, M.C. "Metal Cutting Principles", 2nd ed. (2005), Chapters 3, 7.
Merchant, M.E. (1945) J. Appl. Phys. 16, 267–275.
Taylor, F.W. (1907) Trans. ASME 28, 31–350.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
from typing import Any
from kerf_cad_core._guards import _err, _guard_finite, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deg2rad(deg: float) -> float:
    return deg * math.pi / 180.0


def _rad2deg(rad: float) -> float:
    return rad * 180.0 / math.pi


# ---------------------------------------------------------------------------
# 1. Angle system transforms: orthogonal ↔ normal
# ---------------------------------------------------------------------------

def orthogonal_to_normal(
    gamma_o: float,
    alpha_o: float,
    lambda_s: float,
) -> dict:
    """
    Convert orthogonal-plane tool angles to normal-plane angles.

    Parameters
    ----------
    gamma_o : float
        Orthogonal rake angle (degrees). Finite; negative values are valid.
    alpha_o : float
        Orthogonal clearance angle (degrees). Should be > 0 in practice.
    lambda_s : float
        Inclination angle (degrees). Finite; negative values are valid.

    Returns
    -------
    dict
        ok          : True
        gamma_n_deg : normal rake angle (degrees)
        alpha_n_deg : normal clearance angle (degrees)
        lambda_s_deg: inclination angle (degrees) — echo of input

    Formulas (Boothroyd §2.3 / Shaw §3.2):
        tan(γ_n) = tan(γ_o) · cos(λ_s)
        tan(α_n) = tan(α_o) · cos(λ_s)

    Notes
    -----
    A large negative rake angle (γ_o < −60°) may indicate negative-rake
    instability (BUE tendency); a warning is issued but the result is still
    returned.
    """
    for name, val in [("gamma_o", gamma_o), ("alpha_o", alpha_o), ("lambda_s", lambda_s)]:
        err = _guard_finite(name, val)
        if err:
            return _err(err)

    go = _deg2rad(float(gamma_o))
    ao = _deg2rad(float(alpha_o))
    ls = _deg2rad(float(lambda_s))

    cos_ls = math.cos(ls)

    tan_gn = math.tan(go) * cos_ls
    tan_an = math.tan(ao) * cos_ls

    gamma_n = _rad2deg(math.atan(tan_gn))
    alpha_n = _rad2deg(math.atan(tan_an))

    if float(gamma_o) < -60.0:
        warnings.warn(
            f"orthogonal_to_normal: gamma_o={gamma_o}° is strongly negative — "
            "high BUE/instability risk at moderate cutting speeds.",
            stacklevel=2,
        )

    return {
        "ok": True,
        "gamma_n_deg": gamma_n,
        "alpha_n_deg": alpha_n,
        "lambda_s_deg": float(lambda_s),
    }


def normal_to_orthogonal(
    gamma_n: float,
    alpha_n: float,
    lambda_s: float,
) -> dict:
    """
    Convert normal-plane tool angles to orthogonal-plane angles.

    Parameters
    ----------
    gamma_n : float
        Normal rake angle (degrees). Finite.
    alpha_n : float
        Normal clearance angle (degrees). Finite.
    lambda_s : float
        Inclination angle (degrees). Finite.

    Returns
    -------
    dict
        ok          : True
        gamma_o_deg : orthogonal rake angle (degrees)
        alpha_o_deg : orthogonal clearance angle (degrees)
        lambda_s_deg: inclination angle (degrees)

    Formulas (inverse of orthogonal_to_normal):
        tan(γ_o) = tan(γ_n) / cos(λ_s)
        tan(α_o) = tan(α_n) / cos(λ_s)
    """
    for name, val in [("gamma_n", gamma_n), ("alpha_n", alpha_n), ("lambda_s", lambda_s)]:
        err = _guard_finite(name, val)
        if err:
            return _err(err)

    gn = _deg2rad(float(gamma_n))
    an = _deg2rad(float(alpha_n))
    ls = _deg2rad(float(lambda_s))

    cos_ls = math.cos(ls)
    if abs(cos_ls) < 1e-12:
        return _err("lambda_s is ±90°; cos(λ_s)=0 makes the inverse transform singular.")

    gamma_o = _rad2deg(math.atan(math.tan(gn) / cos_ls))
    alpha_o = _rad2deg(math.atan(math.tan(an) / cos_ls))

    return {
        "ok": True,
        "gamma_o_deg": gamma_o,
        "alpha_o_deg": alpha_o,
        "lambda_s_deg": float(lambda_s),
    }


# ---------------------------------------------------------------------------
# 2. Merchant orthogonal cutting model
# ---------------------------------------------------------------------------

def merchant_orthogonal(
    gamma_o: float,
    tau_s: float,
    mu: float,
    t1: float,
    vc: float,
    *,
    width_b: float = 1.0,
) -> dict:
    """
    Merchant orthogonal cutting model (2D).

    Computes the shear angle (Merchant's minimum-energy solution), cutting
    and thrust forces, shear and friction forces, chip-thickness ratio,
    chip velocity and shear velocity.

    Parameters
    ----------
    gamma_o : float
        Orthogonal rake angle (degrees). Finite; negative values valid.
    tau_s : float
        Shear strength of the workpiece material (Pa). Must be > 0.
        Approximate: τ_s ≈ 0.577 × σ_y (von Mises) or obtained from
        quick-stop specimens.
    mu : float
        Friction coefficient at chip–tool interface. Must be > 0.
        Typical range: 0.3–1.0 for steel on carbide.
    t1 : float
        Uncut chip thickness (mm). Must be > 0.  Equal to feed for
        orthogonal cutting.
    vc : float
        Cutting speed (m/min). Must be > 0.
    width_b : float
        Width of cut (mm). Default 1.0 mm. Must be > 0.

    Returns
    -------
    dict
        ok             : True
        phi_deg        : shear angle φ (degrees)
        r_c            : chip-thickness ratio t1/t2
        t2_mm          : chip thickness (mm)
        Fc_N           : cutting (tangential) force (N)
        Ft_N           : thrust (feed) force (N)
        Fs_N           : shear force on shear plane (N)
        Fn_N           : normal force on shear plane (N)
        F_friction_N   : friction force on rake face (N)
        N_normal_N     : normal force on rake face (N)
        beta_deg       : friction angle β = arctan(μ) (degrees)
        vs_m_min       : shear velocity (m/min)
        vchip_m_min    : chip velocity (m/min)
        gamma_o_deg    : rake angle used (degrees)
        tau_s_Pa       : shear strength used (Pa)
        mu             : friction coefficient used

    Formulas (Merchant 1945 / Boothroyd §2):
        β  = arctan(μ)
        φ  = 45° + γ_o/2 − β/2     (Merchant's minimum-energy solution)
        r_c = sin(φ) / cos(φ − γ_o)
        t2  = t1 / r_c
        Fs  = τ_s × b × t1 / sin(φ)
        F_c = Fs × cos(β − γ_o) / cos(φ + β − γ_o)
        F_t = Fs × sin(β − γ_o) / cos(φ + β − γ_o)
        vs  = vc × cos(γ_o) / cos(φ − γ_o)
        v_chip = vc × sin(φ) / cos(φ − γ_o)

    Warnings
    --------
    • φ ≤ 0° → non-physical shear angle (negative rake too large or μ too high).
    • φ > 50° → outside typical range; solution may be approximate.
    • γ_o < −15° → negative-rake instability (BUE) note.
    """
    for name, val in [("gamma_o", gamma_o)]:
        err = _guard_finite(name, val)
        if err:
            return _err(err)
    for name, val in [("tau_s", tau_s), ("mu", mu), ("t1", t1), ("vc", vc), ("width_b", width_b)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    go_rad = _deg2rad(float(gamma_o))
    beta_rad = math.atan(float(mu))
    beta_deg = _rad2deg(beta_rad)

    # Merchant shear angle
    phi_rad = math.pi / 4.0 + go_rad / 2.0 - beta_rad / 2.0
    phi_deg = _rad2deg(phi_rad)

    if phi_deg <= 0.0:
        warnings.warn(
            f"merchant_orthogonal: shear angle φ={phi_deg:.2f}° ≤ 0 — "
            "non-physical result: rake angle too negative or friction too high.",
            stacklevel=2,
        )

    if phi_deg > 50.0:
        warnings.warn(
            f"merchant_orthogonal: shear angle φ={phi_deg:.2f}° > 50° — "
            "outside typical experimental range; interpret with caution.",
            stacklevel=2,
        )

    if float(gamma_o) < -15.0:
        warnings.warn(
            f"merchant_orthogonal: gamma_o={gamma_o}° < −15° — "
            "negative-rake territory; BUE and elevated temperatures likely.",
            stacklevel=2,
        )

    t1_m = float(t1) * 1e-3  # convert mm → m
    b_m = float(width_b) * 1e-3

    sin_phi = math.sin(phi_rad)
    cos_phi = math.cos(phi_rad)
    sin_phi_m_go = math.sin(phi_rad - go_rad)
    cos_phi_m_go = math.cos(phi_rad - go_rad)
    cos_phi_p_beta_m_go = math.cos(phi_rad + beta_rad - go_rad)
    cos_go = math.cos(go_rad)

    # Chip-thickness ratio
    if abs(cos_phi_m_go) < 1e-15:
        return _err("cos(φ − γ_o) ≈ 0; degenerate geometry.")
    r_c = sin_phi / cos_phi_m_go
    t2_mm = float(t1) / r_c

    # Shear force (acts along shear plane)
    Fs = float(tau_s) * b_m * t1_m / sin_phi

    # Normal force on shear plane
    # From force circle: Fn = Fs × tan(φ + β − γ_o)? Use direct:
    # Fn = Fs × cos(β − γ_o + 2φ − 90°) ... standard decomposition:
    # More directly from Boothroyd Eq 2.11:
    # Fc = Fs cos(β − γ_o) / cos(φ + β − γ_o)
    # Ft = Fs sin(β − γ_o) / cos(φ + β − γ_o)
    beta_m_go_rad = beta_rad - go_rad
    if abs(cos_phi_p_beta_m_go) < 1e-15:
        return _err("cos(φ + β − γ_o) ≈ 0; degenerate force geometry.")

    Fc = Fs * math.cos(beta_m_go_rad) / cos_phi_p_beta_m_go
    Ft = Fs * math.sin(beta_m_go_rad) / cos_phi_p_beta_m_go

    # Normal force on shear plane (from shear-plane force circle)
    Fn_shear = Fs * math.cos(phi_rad) / sin_phi if sin_phi > 1e-15 else 0.0

    # Friction and normal force on rake face
    # F_friction = Fc sin(γ_o) + Ft cos(γ_o)
    # N_rake     = Fc cos(γ_o) − Ft sin(γ_o)
    sin_go = math.sin(go_rad)
    F_friction = Fc * sin_go + Ft * cos_go
    N_rake = Fc * cos_go - Ft * sin_go

    # Velocities
    vc_val = float(vc)
    vs = vc_val * cos_go / cos_phi_m_go  # shear velocity
    v_chip = vc_val * sin_phi / cos_phi_m_go  # chip velocity

    return {
        "ok": True,
        "phi_deg": phi_deg,
        "r_c": r_c,
        "t2_mm": t2_mm,
        "Fc_N": Fc,
        "Ft_N": Ft,
        "Fs_N": Fs,
        "Fn_shear_N": Fn_shear,
        "F_friction_N": F_friction,
        "N_normal_N": N_rake,
        "beta_deg": beta_deg,
        "vs_m_min": vs,
        "vchip_m_min": v_chip,
        "gamma_o_deg": float(gamma_o),
        "tau_s_Pa": float(tau_s),
        "mu": float(mu),
    }


# ---------------------------------------------------------------------------
# 3. Specific cutting energy and power
# ---------------------------------------------------------------------------

def specific_cutting_energy(
    Fc: float,
    b: float,
    t1: float,
    vc: float,
) -> dict:
    """
    Specific cutting energy (unit power) from tangential force and geometry.

    Parameters
    ----------
    Fc : float
        Cutting (tangential) force (N). Must be > 0.
    b : float
        Width of cut (mm). Must be > 0.
    t1 : float
        Uncut chip thickness (feed) (mm). Must be > 0.
    vc : float
        Cutting speed (m/min). Must be > 0.

    Returns
    -------
    dict
        ok              : True
        u_J_per_mm3     : specific cutting energy (J/mm³)
        power_W         : cutting power (W)
        MRR_mm3_per_min : material removal rate (mm³/min)
        Fc_N            : cutting force echo

    Formulas:
        MRR = b × t1 × vc × 1000   [mm³/min]  (vc in m/min → ×1000 for mm/min)
        P   = Fc × vc / 60          [W]        (vc in m/min → /60 for m/s)
        u   = P / (MRR / 60000)     [J/mm³]
            = Fc × vc / (b × t1 × vc × 1000 / 60)
            = Fc × 60 / (b × t1 × 1000)
            = Fc / (b × t1) × 0.06   [simplified]

    Note: u [J/mm³] = u [N/mm²] = u [MPa]. Typical values:
        aluminium: 0.4–1.0,  steel: 1.5–5.0,  titanium: 3.0–6.0.
    """
    for name, val in [("Fc", Fc), ("b", b), ("t1", t1), ("vc", vc)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    Fc_val = float(Fc)
    b_val = float(b)
    t1_val = float(t1)
    vc_val = float(vc)

    # Power in Watts: vc in m/min → m/s = vc/60
    power_W = Fc_val * vc_val / 60.0

    # MRR in mm³/min: vc m/min = 1000 mm/min
    MRR = b_val * t1_val * vc_val * 1000.0  # mm³/min

    # Specific energy in J/mm³ = W / (mm³/s) = power_W / (MRR/60)
    MRR_per_s = MRR / 60.0  # mm³/s
    u = power_W / MRR_per_s  # J/mm³

    return {
        "ok": True,
        "u_J_per_mm3": u,
        "power_W": power_W,
        "MRR_mm3_per_min": MRR,
        "Fc_N": Fc_val,
    }


def cutting_power(
    Fc: float,
    vc: float,
) -> dict:
    """
    Cutting power from tangential force and cutting speed.

    Parameters
    ----------
    Fc : float
        Cutting (tangential) force (N). Must be > 0.
    vc : float
        Cutting speed (m/min). Must be > 0.

    Returns
    -------
    dict
        ok      : True
        power_W : cutting power (W)
        power_kW: cutting power (kW)
        Fc_N    : force echo (N)
        vc_m_min: speed echo (m/min)
    """
    for name, val in [("Fc", Fc), ("vc", vc)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    P = float(Fc) * float(vc) / 60.0
    return {
        "ok": True,
        "power_W": P,
        "power_kW": P / 1000.0,
        "Fc_N": float(Fc),
        "vc_m_min": float(vc),
    }


# ---------------------------------------------------------------------------
# 4. Taylor tool-life equation
# ---------------------------------------------------------------------------

def taylor_tool_life(
    V: float,
    C: float,
    n: float,
    *,
    VB_actual: float | None = None,
    VB_reference: float | None = None,
) -> dict:
    """
    Taylor tool-life from the equation V × T^n = C.

    Parameters
    ----------
    V : float
        Cutting speed (m/min). Must be > 0.
    C : float
        Taylor constant (m/min) — speed for T=1 min. Must be > 0.
    n : float
        Taylor exponent. Must be > 0.  Typical: 0.1–0.5.
    VB_actual : float | None
        Actual flank wear (mm). Optional; if provided alongside
        VB_reference, a wear-corrected life is noted.
    VB_reference : float | None
        Reference flank-wear criterion (mm) for which C was measured.

    Returns
    -------
    dict
        ok          : True
        T_min       : tool life (min) at speed V for standard wear VB_reference
        C_m_min     : Taylor C constant used (m/min)
        n           : Taylor n used
        V_m_min     : speed used (m/min)
        warn_range  : True if V/C ratio is outside [0.01, 10] (Taylor range caution)

    Formula:
        T = (C / V)^(1/n)

    Warnings
    --------
    • V/C > 10 or V/C < 0.01 → outside normal Taylor applicability range.
    • n < 0.05 → unusually small Taylor exponent (tool-life very speed-sensitive).
    • n > 0.5  → unusually high exponent (uncommon except ceramics/CBN).
    """
    for name, val in [("V", V), ("C", C), ("n", n)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    V_val = float(V)
    C_val = float(C)
    n_val = float(n)

    ratio = V_val / C_val
    warn_range = (ratio < 0.01) or (ratio > 10.0)
    if warn_range:
        warnings.warn(
            f"taylor_tool_life: V/C={ratio:.4f} is outside [0.01, 10] — "
            "Taylor equation extrapolation; accuracy may be low.",
            stacklevel=2,
        )

    if n_val < 0.05:
        warnings.warn(
            f"taylor_tool_life: n={n_val} < 0.05 — unusually small Taylor exponent.",
            stacklevel=2,
        )
    if n_val > 0.5:
        warnings.warn(
            f"taylor_tool_life: n={n_val} > 0.5 — unusually large Taylor exponent "
            "(typical for ceramics/CBN; verify material data).",
            stacklevel=2,
        )

    T = (C_val / V_val) ** (1.0 / n_val)

    result: dict = {
        "ok": True,
        "T_min": T,
        "C_m_min": C_val,
        "n": n_val,
        "V_m_min": V_val,
        "warn_range": warn_range,
    }

    # Optional: life scaled for a different wear criterion (simple ratio)
    if VB_actual is not None and VB_reference is not None:
        vb_err = _guard_positive("VB_actual", VB_actual) or _guard_positive("VB_reference", VB_reference)
        if vb_err:
            result["VB_warn"] = vb_err
        else:
            # Linear approximation: T_actual ≈ T × (VB_actual / VB_reference)
            # (conservative approximation; more accurate models use power law)
            result["T_at_VB_actual_min"] = T * (float(VB_actual) / float(VB_reference))

    return result


def taylor_extended_tool_life(
    V: float,
    C: float,
    n: float,
    f: float,
    a_f: float,
    d: float,
    a_d: float,
    *,
    f_ref: float = 1.0,
    d_ref: float = 1.0,
) -> dict:
    """
    Extended Taylor equation: V T^n f^a_f d^a_d = C_eff.

    This form (Boothroyd §9.2, Shaw §7) accounts for the effect of feed
    and depth of cut on tool life.

    Parameters
    ----------
    V : float
        Cutting speed (m/min). Must be > 0.
    C : float
        Extended Taylor constant (calibrated at f_ref, d_ref). Must be > 0.
    n : float
        Speed exponent (Taylor n). Must be > 0.
    f : float
        Feed (mm/rev). Must be > 0.
    a_f : float
        Feed exponent. Must be >= 0. Typical: 0.3–0.7.
    d : float
        Depth of cut (mm). Must be > 0.
    a_d : float
        Depth-of-cut exponent. Must be >= 0. Typical: 0.1–0.3.
    f_ref : float
        Reference feed for which C was calibrated (mm/rev). Default 1.0.
    d_ref : float
        Reference depth for which C was calibrated (mm). Default 1.0.

    Returns
    -------
    dict
        ok      : True
        T_min   : tool life (min)
        C_eff   : effective Taylor constant at given f, d

    Formula:
        C_eff = C × (f_ref / f)^(a_f/n) × (d_ref / d)^(a_d/n)
        T     = (C_eff / V)^(1/n)

    Alternatively written:
        V T^n = C / (f/f_ref)^a_f / (d/d_ref)^a_d  =  C_eff
    """
    for name, val in [("V", V), ("C", C), ("n", n), ("f", f), ("d", d)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    for name, val in [("a_f", a_f), ("a_d", a_d)]:
        err = _guard_nonneg(name, val)
        if err:
            return _err(err)
    for name, val in [("f_ref", f_ref), ("d_ref", d_ref)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    V_val = float(V)
    C_val = float(C)
    n_val = float(n)
    f_val = float(f)
    a_f_val = float(a_f)
    d_val = float(d)
    a_d_val = float(a_d)
    fr = float(f_ref)
    dr = float(d_ref)

    # Effective constant at given f, d:
    # V T^n = C × (fr/f)^a_f × (dr/d)^a_d  →  T = (C_eff / V)^(1/n)
    C_eff = C_val * (fr / f_val) ** a_f_val * (dr / d_val) ** a_d_val
    T = (C_eff / V_val) ** (1.0 / n_val)

    return {
        "ok": True,
        "T_min": T,
        "C_eff": C_eff,
        "C_m_min": C_val,
        "n": n_val,
        "V_m_min": V_val,
        "f_mm_rev": f_val,
        "d_mm": d_val,
        "a_f": a_f_val,
        "a_d": a_d_val,
    }


# ---------------------------------------------------------------------------
# 5. Economic and maximum-production-rate cutting speeds
# ---------------------------------------------------------------------------

def economic_cutting_speed(
    C_tool: float,
    t_ct: float,
    t_c: float,
    C_m: float,
    n: float,
    C: float,
    *,
    C_ref: float | None = None,
    n_ref: float | None = None,
) -> dict:
    """
    Economic (minimum-cost) cutting speed V_e (Boothroyd §9.3).

    Parameters
    ----------
    C_tool : float
        Tool cost per edge (same currency unit as C_m). Must be > 0.
        Includes insert cost and tool-change labour.
    t_ct : float
        Tool-change time per edge (min). Must be > 0.
    t_c : float
        Time to produce one component without tool change (min). Must be > 0.
    C_m : float
        Machine + operator cost rate ($/min or equivalent). Must be > 0.
    n : float
        Taylor exponent. Must be > 0.
    C : float
        Taylor constant (m/min). Must be > 0.
    C_ref : float | None
        Optional reference Taylor constant for range check.
    n_ref : float | None
        Optional reference Taylor n for range check.

    Returns
    -------
    dict
        ok         : True
        V_e_m_min  : economic cutting speed (m/min)
        T_e_min    : economic tool life (min) at V_e
        cost_per_piece_at_Ve : relative cost per piece (same units as C_m × t_c)

    Formulas (Boothroyd §9.3):
        T_e = (1/n − 1) × (t_ct + C_tool/C_m)
        V_e = C / T_e^n

    The economic tool life T_e balances tool-change cost against machining
    cost; it is independent of the component geometry (t_c enters only
    through total cost-per-piece calculation).

    Warnings
    --------
    • T_e ≤ 0 → n ≥ 1 makes the formula degenerate (Taylor law breaks down).
    • V_e outside [1, 2000] m/min → unusual; issued as a warning.
    """
    for name, val in [("C_tool", C_tool), ("t_ct", t_ct), ("t_c", t_c), ("C_m", C_m), ("n", n), ("C", C)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    n_val = float(n)
    t_ct_val = float(t_ct)
    C_tool_val = float(C_tool)
    C_m_val = float(C_m)
    C_val = float(C)
    t_c_val = float(t_c)

    if n_val >= 1.0:
        warnings.warn(
            f"economic_cutting_speed: n={n_val} ≥ 1 — Taylor equation is degenerate "
            "(no finite economic optimum); V_e → ∞.",
            stacklevel=2,
        )
        return _err(f"n={n_val} >= 1; economic speed formula requires n < 1.")

    # Economic tool life
    T_e = (1.0 / n_val - 1.0) * (t_ct_val + C_tool_val / C_m_val)

    if T_e <= 0:
        return _err(
            f"Economic tool life T_e={T_e:.4f} ≤ 0; check n, t_ct, C_tool, C_m inputs."
        )

    V_e = C_val / (T_e ** n_val)

    if not (1.0 <= V_e <= 2000.0):
        warnings.warn(
            f"economic_cutting_speed: V_e={V_e:.2f} m/min outside [1, 2000] — "
            "verify Taylor constants and cost inputs.",
            stacklevel=2,
        )

    # Total cost per piece (machining + tool + change) at V_e
    # C_piece = C_m × (t_c + t_ct × t_c / T_e) + C_tool × t_c / T_e
    n_tools_per_piece = t_c_val / T_e
    C_piece = C_m_val * t_c_val + (C_m_val * t_ct_val + C_tool_val) * n_tools_per_piece

    return {
        "ok": True,
        "V_e_m_min": V_e,
        "T_e_min": T_e,
        "cost_per_piece_at_Ve": C_piece,
        "n": n_val,
        "C_m_min": C_val,
    }


def max_production_rate_speed(
    t_ct: float,
    t_c: float,
    n: float,
    C: float,
    *,
    C_ref: float | None = None,
    n_ref: float | None = None,
) -> dict:
    """
    Maximum-production-rate cutting speed V_mpr (Boothroyd §9.3).

    Parameters
    ----------
    t_ct : float
        Tool-change time per edge (min). Must be > 0.
    t_c : float
        Time to produce one component (min). Must be > 0.
    n : float
        Taylor exponent. Must be > 0.
    C : float
        Taylor constant (m/min). Must be > 0.

    Returns
    -------
    dict
        ok           : True
        V_mpr_m_min  : maximum-production-rate speed (m/min)
        T_mpr_min    : tool life at V_mpr (min)
        cycle_time_s : cycle time at V_mpr including tool-change fraction (s)

    Formulas (Boothroyd §9.3):
        T_mpr = (1/n − 1) × t_ct
        V_mpr = C / T_mpr^n

    This minimises total cycle time per component, ignoring tool cost.
    V_mpr ≥ V_e always (max-production speed is higher than economic speed).
    """
    for name, val in [("t_ct", t_ct), ("t_c", t_c), ("n", n), ("C", C)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    n_val = float(n)
    t_ct_val = float(t_ct)
    t_c_val = float(t_c)
    C_val = float(C)

    if n_val >= 1.0:
        return _err(f"n={n_val} >= 1; max-production-rate speed formula requires n < 1.")

    T_mpr = (1.0 / n_val - 1.0) * t_ct_val
    if T_mpr <= 0:
        return _err(f"T_mpr={T_mpr:.4f} ≤ 0; check n and t_ct inputs.")

    V_mpr = C_val / (T_mpr ** n_val)

    # Cycle time at V_mpr (machining time + fractional tool-change time)
    cycle_min = t_c_val + t_ct_val * t_c_val / T_mpr
    cycle_s = cycle_min * 60.0

    return {
        "ok": True,
        "V_mpr_m_min": V_mpr,
        "T_mpr_min": T_mpr,
        "cycle_time_s": cycle_s,
        "n": n_val,
        "C_m_min": C_val,
    }


def break_even_speed(
    C_tool: float,
    t_ct: float,
    t_c: float,
    C_m: float,
    n: float,
    C: float,
) -> dict:
    """
    Break-even cutting speed between minimum-cost and maximum-production-rate.

    Returns V_e (min-cost), V_mpr (max-production-rate), and the
    break-even (crossover) speed where cost-per-piece at V_mpr equals
    that at V_e.  V_mpr is always >= V_e; if equal the break-even is V_e.

    Parameters
    ----------
    (same as economic_cutting_speed + max_production_rate_speed)

    Returns
    -------
    dict
        ok              : True
        V_e_m_min       : economic (min-cost) speed (m/min)
        V_mpr_m_min     : max-production-rate speed (m/min)
        T_e_min         : economic tool life (min)
        T_mpr_min       : max-rate tool life (min)
        cost_ratio_mpr_to_e : cost at V_mpr / cost at V_e
    """
    res_e = economic_cutting_speed(C_tool, t_ct, t_c, C_m, n, C)
    if not res_e.get("ok"):
        return res_e

    res_mpr = max_production_rate_speed(t_ct, t_c, n, C)
    if not res_mpr.get("ok"):
        return res_mpr

    V_e = res_e["V_e_m_min"]
    T_e = res_e["T_e_min"]
    V_mpr = res_mpr["V_mpr_m_min"]
    T_mpr = res_mpr["T_mpr_min"]

    n_val = float(n)
    t_c_val = float(t_c)
    C_m_val = float(C_m)
    t_ct_val = float(t_ct)
    C_tool_val = float(C_tool)

    def _cost(T_life: float) -> float:
        """Cost per piece for tool life T_life."""
        n_tpc = t_c_val / T_life
        return C_m_val * t_c_val + (C_m_val * t_ct_val + C_tool_val) * n_tpc

    cost_e = _cost(T_e)
    cost_mpr = _cost(T_mpr)
    cost_ratio = cost_mpr / cost_e if cost_e > 0 else float("inf")

    return {
        "ok": True,
        "V_e_m_min": V_e,
        "V_mpr_m_min": V_mpr,
        "T_e_min": T_e,
        "T_mpr_min": T_mpr,
        "cost_per_piece_at_Ve": cost_e,
        "cost_per_piece_at_Vmpr": cost_mpr,
        "cost_ratio_mpr_to_e": cost_ratio,
    }


# ---------------------------------------------------------------------------
# 6. Machinability rating
# ---------------------------------------------------------------------------

def machinability_rating(
    V_material: float,
    V_reference: float,
) -> dict:
    """
    Machinability rating of a material relative to a reference.

    Parameters
    ----------
    V_material : float
        Cutting speed of the material under test to achieve a standard
        tool life (e.g. 60 min at VB=0.3 mm). Must be > 0. Units: m/min.
    V_reference : float
        Same for the reference material (AISI B1112 free-cutting steel
        at 100% or user-specified). Must be > 0. Units: m/min.

    Returns
    -------
    dict
        ok                : True
        rating_pct        : machinability rating (%)
        V_material_m_min  : material speed echo
        V_reference_m_min : reference speed echo

    Formula:
        rating = (V_material / V_reference) × 100 %
    """
    for name, val in [("V_material", V_material), ("V_reference", V_reference)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    rating = (float(V_material) / float(V_reference)) * 100.0
    return {
        "ok": True,
        "rating_pct": rating,
        "V_material_m_min": float(V_material),
        "V_reference_m_min": float(V_reference),
    }


# ---------------------------------------------------------------------------
# 7. Nose-radius surface finish
# ---------------------------------------------------------------------------

def nose_radius_roughness(
    f: float,
    r_n: float,
) -> dict:
    """
    Theoretical surface finish from feed and nose radius (ideal turning).

    Parameters
    ----------
    f : float
        Feed per revolution (mm/rev). Must be > 0.
    r_n : float
        Tool nose radius (mm). Must be > 0.

    Returns
    -------
    dict
        ok       : True
        Rt_um    : peak-to-valley height Rt (μm)
        Ra_um    : arithmetic mean roughness Ra (μm)

    Formulas (Boothroyd §8.4 / standard turning theory):
        Rt = f² / (8 r_n)     [mm]  →  × 1000 for μm
        Ra ≈ Rt / 4            (for the ideal sinusoidal profile approximation)

    The actual Ra is typically 0.2–0.5 × Rt due to side-flow and BUE;
    these formulas give the geometric minimum.
    """
    for name, val in [("f", f), ("r_n", r_n)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    f_val = float(f)
    r_n_val = float(r_n)

    Rt_mm = (f_val ** 2) / (8.0 * r_n_val)
    Ra_mm = Rt_mm / 4.0

    Rt_um = Rt_mm * 1000.0
    Ra_um = Ra_mm * 1000.0

    return {
        "ok": True,
        "Rt_um": Rt_um,
        "Ra_um": Ra_um,
        "f_mm_rev": f_val,
        "r_n_mm": r_n_val,
    }
