"""
kerf_cad_core.turbo.stage — pure-Python turbomachinery blade/stage design.

Implements blade-level velocity-triangle analysis for both axial and
centrifugal turbomachinery.  Distinct from pumpsys (system-curve / pump
selection) and aero (external aerodynamics).

Public functions
----------------
euler_work(U, dCtheta)
    Euler turbomachine equation: specific work = U · ΔCθ.

velocity_triangles_axial(U, Ca, alpha1, alpha2)
    Velocity triangles for an axial stage (compressor or turbine).
    Returns blade angles, relative velocities, absolute velocities,
    and whirl (swirl) components.

velocity_triangles_centrifugal(U2, Cr2, *, beta2_deg, slip_factor)
    Velocity triangles at the exit of a centrifugal impeller.
    Slip factor (Stanitz or provided) corrects ideal whirl velocity.

dimensionless_groups(U, Ca, dCtheta, *, rho, blade_speed_sound)
    Flow coefficient φ, work/head coefficient ψ, power coefficient,
    blade Mach number.

specific_speed_diameter(Q, gH, omega)
    Dimensionless specific speed Ω_s and specific diameter Δ_s.

cordier_optimum(Omega_s)
    Cordier-line optimum specific diameter Δ_s_opt from Ω_s.

degree_of_reaction(C_theta1, C_theta2, U)
    Stage degree of reaction R = 1 − (Cθ1 + Cθ2) / (2U).

axial_stage(U, Ca, alpha1_deg, alpha2_deg, *, rho, is_compressor,
            chord, span, nu)
    Full axial compressor/turbine stage analysis: velocity triangles,
    degree of reaction, work, diffusion factor (compressor) or blade
    loading (turbine), de Haller number (compressor).

centrifugal_impeller(n_rpm, D2_m, b2_m, *, D1_tip_m, D1_hub_m,
                     beta2_deg, Z, rho, g, slip_model)
    Centrifugal pump/compressor impeller: Euler head with slip,
    NPSH inception estimate, flow-rate.

fan_affinity(Q1, H1, P1, n1, n2, *, D1, D2)
    Fan / pump affinity laws: speed change and/or impeller-trim.
    Includes all three affinity relations.

stage_efficiency(W_actual, W_isentropic, *, polytropic_n,
                 gamma, stage_type)
    Isentropic and polytropic efficiency; small-stage (preheat/reheat)
    factor.

surge_choke_margin(phi_op, phi_surge, phi_choke)
    Surge margin and choke margin as fractions.  Flags insufficient
    margins via warnings.

All functions return a plain dict:
    success → {"ok": True, ...fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "..."}

Functions NEVER raise.

Units
-----
Unless stated otherwise:
  lengths   — metres (m)
  angles    — degrees (°) for user-facing inputs; radians internal
  speeds    — m/s (velocity), rad/s (angular), rpm (rotational)
  pressure  — Pascals (Pa)
  density   — kg/m³
  work      — J/kg (specific work)
  head      — metres (m) of fluid

References
----------
Dixon, S.L. & Hall, C.A. "Fluid Mechanics and Thermodynamics of
  Turbomachinery", 7th ed., Butterworth-Heinemann (2014). [Dixon]
Saravanamuttoo, H.I.H. et al. "Gas Turbine Theory", 7th ed.,
  Pearson (2017). [Sara]
Cumpsty, N.A. "Compressor Aerodynamics", 2nd ed., Krieger (2004).
White, F.M. "Fluid Mechanics", 8th ed., McGraw-Hill (2016).

Author: imranparuk
"""

from __future__ import annotations

import math
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
# 1. euler_work
# ---------------------------------------------------------------------------

def euler_work(U: float, dCtheta: float) -> dict:
    """
    Euler turbomachine equation: specific work = U · ΔCθ.

    For a compressor/pump stage with a single blade row pair:
        W = U · (Cθ2 - Cθ1)   [J/kg]

    For a turbine stage (work is extracted):
        W = U · (Cθ1 - Cθ2)   [J/kg, positive = work extracted]

    Parameters
    ----------
    U : float
        Blade (peripheral) speed (m/s). Must be > 0.
    dCtheta : float
        Change in whirl (tangential) velocity ΔCθ = Cθ2 − Cθ1 (m/s).
        Positive → work input (compressor/pump convention).
        Negative → work extraction (turbine convention).

    Returns
    -------
    dict
        ok            : True
        W_specific    : specific work U·ΔCθ (J/kg)
        U_m_s         : blade speed (m/s)
        dCtheta_m_s   : ΔCθ (m/s)
        warnings      : list[str]

    References
    ----------
    Dixon §1.3
    """
    err = _guard_positive("U", U)
    if err:
        return _err(err)
    err = _guard_finite("dCtheta", dCtheta)
    if err:
        return _err(err)

    U_val = float(U)
    dCt = float(dCtheta)
    W = U_val * dCt

    warnings: list[str] = []
    if abs(W) == 0.0:
        warnings.append("Specific work is zero — no energy transfer occurs.")

    return {
        "ok": True,
        "W_specific": W,
        "U_m_s": U_val,
        "dCtheta_m_s": dCt,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. velocity_triangles_axial
# ---------------------------------------------------------------------------

def velocity_triangles_axial(
    U: float,
    Ca: float,
    alpha1_deg: float,
    alpha2_deg: float,
) -> dict:
    """
    Velocity triangles for an axial turbomachinery stage.

    Assumes constant axial velocity Ca through the stage.

    Convention (compressor, positive whirl in direction of rotation):
        α1, α2 = absolute flow angles from axial (degrees)
        β1, β2 = relative flow angles from axial (degrees)
        Whirl (swirl) components:
            Cθ1 = Ca · tan(α1),  Cθ2 = Ca · tan(α2)
            Wθ1 = Cθ1 − U,       Wθ2 = Cθ2 − U

    Parameters
    ----------
    U : float
        Blade speed (m/s). Must be > 0.
    Ca : float
        Axial velocity component (m/s). Must be > 0.
    alpha1_deg : float
        Absolute inlet flow angle from axial (degrees). Range ±89°.
    alpha2_deg : float
        Absolute exit flow angle from axial (degrees). Range ±89°.

    Returns
    -------
    dict
        ok             : True
        U_m_s          : blade speed (m/s)
        Ca_m_s         : axial velocity (m/s)
        alpha1_deg     : absolute inlet angle (°)
        alpha2_deg     : absolute exit angle (°)
        beta1_deg      : relative inlet angle (°)
        beta2_deg      : relative exit angle (°)
        C1_m_s         : absolute inlet velocity magnitude (m/s)
        C2_m_s         : absolute exit velocity magnitude (m/s)
        W1_m_s         : relative inlet velocity magnitude (m/s)
        W2_m_s         : relative exit velocity magnitude (m/s)
        Ctheta1_m_s    : absolute inlet whirl velocity (m/s)
        Ctheta2_m_s    : absolute exit whirl velocity (m/s)
        dCtheta_m_s    : ΔCθ = Cθ2 − Cθ1 (m/s)
        W_specific     : Euler work U·ΔCθ (J/kg)
        warnings       : list[str]

    References
    ----------
    Dixon §3.2, §3.3
    """
    err = _guard_positive("U", U)
    if err:
        return _err(err)
    err = _guard_positive("Ca", Ca)
    if err:
        return _err(err)

    for name, val in (("alpha1_deg", alpha1_deg), ("alpha2_deg", alpha2_deg)):
        err = _guard_finite(name, val)
        if err:
            return _err(err)
        if abs(float(val)) >= 89.0:
            return _err(f"{name}={val}° is outside ±89° (axial velocity component would vanish).")

    U_val = float(U)
    Ca_val = float(Ca)
    a1 = _deg2rad(float(alpha1_deg))
    a2 = _deg2rad(float(alpha2_deg))

    # Absolute whirl components
    Ct1 = Ca_val * math.tan(a1)
    Ct2 = Ca_val * math.tan(a2)

    # Relative whirl components (rotating frame)
    Wt1 = Ct1 - U_val
    Wt2 = Ct2 - U_val

    # Relative flow angles
    b1 = math.atan2(Wt1, Ca_val)
    b2 = math.atan2(Wt2, Ca_val)

    # Velocity magnitudes
    C1 = math.sqrt(Ca_val**2 + Ct1**2)
    C2 = math.sqrt(Ca_val**2 + Ct2**2)
    W1 = math.sqrt(Ca_val**2 + Wt1**2)
    W2 = math.sqrt(Ca_val**2 + Wt2**2)

    dCt = Ct2 - Ct1
    W_specific = U_val * dCt

    warnings: list[str] = []
    if W_specific < 0.0:
        warnings.append(
            "Negative specific work: the stage is extracting work (turbine). "
            "Use compressor sign convention (dCtheta > 0) for compressor analysis."
        )
    return {
        "ok": True,
        "U_m_s": U_val,
        "Ca_m_s": Ca_val,
        "alpha1_deg": float(alpha1_deg),
        "alpha2_deg": float(alpha2_deg),
        "beta1_deg": _rad2deg(b1),
        "beta2_deg": _rad2deg(b2),
        "C1_m_s": C1,
        "C2_m_s": C2,
        "W1_m_s": W1,
        "W2_m_s": W2,
        "Ctheta1_m_s": Ct1,
        "Ctheta2_m_s": Ct2,
        "dCtheta_m_s": dCt,
        "W_specific": W_specific,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. velocity_triangles_centrifugal
# ---------------------------------------------------------------------------

def velocity_triangles_centrifugal(
    U2: float,
    Cr2: float,
    *,
    beta2_deg: float = -30.0,
    slip_factor: float | None = None,
) -> dict:
    """
    Velocity triangles at the exit of a centrifugal impeller.

    Slip factor σ reduces the ideal whirl velocity due to the finite
    number of blades.  If not provided, the Stanitz approximation is
    used (requires blade count Z; default sigma=0.9 for Z=∞ proxy).

    Parameters
    ----------
    U2 : float
        Tip blade speed at impeller exit (m/s). Must be > 0.
    Cr2 : float
        Radial velocity component at impeller exit (m/s). Must be > 0.
    beta2_deg : float
        Backward-swept blade angle from radial at exit (degrees).
        Negative = backward sweep (most pumps/compressors). Default −30°.
        Forward sweep > 0 (less common).
    slip_factor : float | None
        Slip factor σ (0 < σ ≤ 1). If None, uses σ = 0.9 (approximate
        Stanitz for ~10 blades with backward-swept exit).

    Returns
    -------
    dict
        ok                : True
        U2_m_s            : tip blade speed (m/s)
        Cr2_m_s           : radial exit velocity (m/s)
        beta2_deg         : blade angle at exit (°)
        slip_factor       : slip factor σ used
        Ctheta2_ideal_m_s : ideal whirl velocity (no slip) (m/s)
        Ctheta2_actual_m_s: actual whirl velocity with slip (m/s)
        C2_m_s            : absolute exit velocity (m/s)
        alpha2_deg        : absolute exit flow angle from radial (°)
        W2_m_s            : relative exit velocity (m/s)
        W_specific_ideal  : ideal Euler work U2·Cθ2_ideal (J/kg)
        W_specific_actual : actual Euler work U2·Cθ2_actual·σ factor (J/kg)
        warnings          : list[str]

    Notes
    -----
    Ideal (no-slip) exit whirl: Cθ2_ideal = U2 − Cr2·tan(|β2|)
      for backward-swept blades (β2 < 0).
    Actual: Cθ2_actual = σ · U2 − Cr2·tan(|β2|) ... or equivalently
      W_actual = σ · U2 · Cθ2_ideal / U2 ... the Stanitz form used here is:
      Cθ2_actual = U2 − Cr2 / tan(|β2_rad|)   then multiplied by σ
      (see Dixon §7.4 for the precise form).

    The formula applied (Dixon §7.2):
        Cθ2_ideal = U2 + Cr2 · tan(β2_rad)
      where β2_rad is the signed angle from radial (negative for backward sweep).
    Then:
        Cθ2_actual = σ · Cθ2_ideal

    References
    ----------
    Dixon §7.2–7.5; Stanitz (1952) slip factor approximation.
    """
    err = _guard_positive("U2", U2)
    if err:
        return _err(err)
    err = _guard_positive("Cr2", Cr2)
    if err:
        return _err(err)
    err = _guard_finite("beta2_deg", beta2_deg)
    if err:
        return _err(err)
    if abs(float(beta2_deg)) >= 89.0:
        return _err("beta2_deg magnitude must be < 89°.")

    if slip_factor is not None:
        err = _guard_positive("slip_factor", slip_factor)
        if err:
            return _err(err)
        if float(slip_factor) > 1.0:
            return _err(f"slip_factor must be <= 1.0, got {slip_factor}.")
        sigma = float(slip_factor)
    else:
        sigma = 0.9  # reasonable default for ~10 backward-swept blades

    U2_val = float(U2)
    Cr2_val = float(Cr2)
    b2_rad = _deg2rad(float(beta2_deg))

    # Ideal whirl velocity (Dixon §7.2)
    # In the rotating frame: Wθ2 = Cr2 · tan(β2)  (signed)
    # Absolute: Cθ2 = U2 + Wθ2 = U2 + Cr2 · tan(β2)
    Ct2_ideal = U2_val + Cr2_val * math.tan(b2_rad)

    # With slip
    Ct2_actual = sigma * Ct2_ideal

    # Absolute exit velocity
    C2 = math.sqrt(Cr2_val**2 + Ct2_actual**2)

    # Absolute exit flow angle from radial
    alpha2_rad = math.atan2(Ct2_actual, Cr2_val)

    # Relative exit velocity
    W2 = math.sqrt(Cr2_val**2 + (U2_val - Ct2_actual)**2)

    # Euler work
    W_specific_ideal = U2_val * Ct2_ideal
    W_specific_actual = U2_val * Ct2_actual

    warnings: list[str] = []
    if Ct2_ideal < 0:
        warnings.append(
            "Ideal whirl velocity is negative: forward-swept blade or "
            "radial velocity too high relative to blade speed."
        )
    if Ct2_actual < 0:
        warnings.append(
            "Actual whirl velocity (with slip) is negative — unusual operating condition."
        )

    return {
        "ok": True,
        "U2_m_s": U2_val,
        "Cr2_m_s": Cr2_val,
        "beta2_deg": float(beta2_deg),
        "slip_factor": sigma,
        "Ctheta2_ideal_m_s": Ct2_ideal,
        "Ctheta2_actual_m_s": Ct2_actual,
        "C2_m_s": C2,
        "alpha2_deg": _rad2deg(alpha2_rad),
        "W2_m_s": W2,
        "W_specific_ideal": W_specific_ideal,
        "W_specific_actual": W_specific_actual,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. dimensionless_groups
# ---------------------------------------------------------------------------

def dimensionless_groups(
    U: float,
    Ca: float,
    dCtheta: float,
    *,
    rho: float = 1.225,
    blade_speed_sound: float | None = None,
) -> dict:
    """
    Dimensionless turbomachinery performance groups.

    Parameters
    ----------
    U : float
        Blade (tip) speed (m/s). Must be > 0.
    Ca : float
        Axial (or meridional) velocity (m/s). Must be > 0.
    dCtheta : float
        Change in whirl velocity ΔCθ = Cθ2 − Cθ1 (m/s). May be negative.
    rho : float
        Fluid density (kg/m³). Default 1.225 (ISA sea-level air).
        Must be > 0.
    blade_speed_sound : float | None
        Speed of sound at blade tip (m/s). If provided, computes blade
        Mach number M_U = U / a. Must be > 0 if provided.

    Returns
    -------
    dict
        ok               : True
        phi              : flow coefficient φ = Ca / U
        psi              : work/head coefficient ψ = W / U² = ΔCθ / U
        psi_h            : head coefficient ψ_H = g·H / U² (uses W = g·H)
        power_coeff      : power coefficient C_P = rho·W / (rho·U³) = ψ·φ
        blade_mach       : blade Mach number M_U (None if not computable)
        warnings         : list[str]

    Notes
    -----
    φ = Ca / U  (flow coefficient)
    ψ = ΔCθ / U  (Euler work coefficient, also called loading coefficient)
    For incompressible: gH = W → ψ_H = g·H / U² = W / U²
    Power coefficient C_P = ψ · φ (for constant Ca through stage)

    References
    ----------
    Dixon §1.6
    """
    err = _guard_positive("U", U)
    if err:
        return _err(err)
    err = _guard_positive("Ca", Ca)
    if err:
        return _err(err)
    err = _guard_finite("dCtheta", dCtheta)
    if err:
        return _err(err)
    err = _guard_positive("rho", rho)
    if err:
        return _err(err)

    if blade_speed_sound is not None:
        err = _guard_positive("blade_speed_sound", blade_speed_sound)
        if err:
            return _err(err)

    U_val = float(U)
    Ca_val = float(Ca)
    dCt = float(dCtheta)

    phi = Ca_val / U_val
    psi = dCt / U_val
    # psi_h = W / U^2 = ψ (numerically equal for incompressible)
    psi_h = psi
    power_coeff = psi * phi

    blade_mach: float | None = None
    if blade_speed_sound is not None:
        blade_mach = U_val / float(blade_speed_sound)

    warnings: list[str] = []
    if phi > 0.8:
        warnings.append(
            f"Flow coefficient φ={phi:.3f} > 0.8: very high axial velocity "
            "relative to blade speed — check for excessive tip Mach number."
        )
    if abs(psi) > 0.5:
        warnings.append(
            f"Loading coefficient |ψ|={abs(psi):.3f} > 0.5: high stage loading; "
            "check for flow separation and excessive diffusion."
        )
    if blade_mach is not None and blade_mach > 1.0:
        warnings.append(
            f"Blade tip Mach number M_U={blade_mach:.3f} > 1.0: transonic/supersonic "
            "blade tip — compressibility effects are significant."
        )

    return {
        "ok": True,
        "phi": phi,
        "psi": psi,
        "psi_h": psi_h,
        "power_coeff": power_coeff,
        "blade_mach": blade_mach,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. specific_speed_diameter
# ---------------------------------------------------------------------------

def specific_speed_diameter(
    Q: float,
    gH: float,
    omega: float,
    *,
    D: float | None = None,
) -> dict:
    """
    Dimensionless specific speed Ω_s and specific diameter Δ_s.

    Parameters
    ----------
    Q : float
        Volume flow rate (m³/s). Must be > 0.
    gH : float
        Specific energy rise g·H (J/kg). Must be > 0.
    omega : float
        Shaft angular velocity (rad/s). Must be > 0.
    D : float | None
        Impeller diameter (m). If provided, computes Δ_s. Must be > 0.

    Returns
    -------
    dict
        ok           : True
        Omega_s      : dimensionless specific speed Ω_s = ω·√Q / (gH)^(3/4)
        Delta_s      : dimensionless specific diameter Δ_s = D·(gH)^(1/4) / √Q
                       (None if D not provided)
        machine_type : guidance string ("radial"/"mixed-flow"/"axial")
        warnings     : list[str]

    Notes
    -----
    Dimensionless form (Dixon §1.5):
        Ω_s = ω · √Q / (g·H)^(3/4)
        Δ_s = D · (g·H)^(1/4) / √Q

    Type guidance (approximate, from Cordier diagram):
        Ω_s < 1.0  → radial (centrifugal)
        1.0–3.0    → mixed-flow
        Ω_s > 3.0  → axial

    References
    ----------
    Dixon §1.5; Cordier (1953).
    """
    err = _guard_positive("Q", Q)
    if err:
        return _err(err)
    err = _guard_positive("gH", gH)
    if err:
        return _err(err)
    err = _guard_positive("omega", omega)
    if err:
        return _err(err)

    Q_val = float(Q)
    gH_val = float(gH)
    omega_val = float(omega)

    Omega_s = omega_val * math.sqrt(Q_val) / gH_val**0.75

    Delta_s: float | None = None
    if D is not None:
        err = _guard_positive("D", D)
        if err:
            return _err(err)
        D_val = float(D)
        Delta_s = D_val * gH_val**0.25 / math.sqrt(Q_val)

    if Omega_s < 1.0:
        machine_type = "radial (centrifugal)"
    elif Omega_s < 3.0:
        machine_type = "mixed-flow"
    else:
        machine_type = "axial"

    warnings: list[str] = []

    return {
        "ok": True,
        "Omega_s": Omega_s,
        "Delta_s": Delta_s,
        "machine_type": machine_type,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. cordier_optimum
# ---------------------------------------------------------------------------

# Cordier line fit constants (from Dixon Fig 1.5 polynomial approximation)
# Δ_s_opt ≈ exp(a0 + a1·ln(Ω_s) + a2·(ln(Ω_s))²)
# Approximate fit to Cordier diagram (Ω_s range ~0.1–10)
_CORDIER_A0 = 1.093
_CORDIER_A1 = -0.478
_CORDIER_A2 = -0.042


def cordier_optimum(Omega_s: float) -> dict:
    """
    Cordier-line optimum specific diameter Δ_s_opt from Ω_s.

    The Cordier diagram shows that the highest-efficiency machines lie
    on a characteristic curve relating Ω_s and Δ_s.  This function
    returns the optimum Δ_s for a given Ω_s using a log-polynomial
    approximation.

    Parameters
    ----------
    Omega_s : float
        Dimensionless specific speed. Must be > 0.

    Returns
    -------
    dict
        ok           : True
        Omega_s      : specific speed used
        Delta_s_opt  : optimum specific diameter from Cordier line
        machine_type : "radial" / "mixed-flow" / "axial" guidance
        warnings     : list[str]

    References
    ----------
    Dixon §1.6; Cordier (1953).
    """
    err = _guard_positive("Omega_s", Omega_s)
    if err:
        return _err(err)

    Os = float(Omega_s)
    ln_Os = math.log(Os)
    Delta_s_opt = math.exp(
        _CORDIER_A0 + _CORDIER_A1 * ln_Os + _CORDIER_A2 * ln_Os**2
    )

    if Os < 1.0:
        machine_type = "radial (centrifugal)"
    elif Os < 3.0:
        machine_type = "mixed-flow"
    else:
        machine_type = "axial"

    warnings: list[str] = []
    if Os < 0.2 or Os > 10.0:
        warnings.append(
            f"Ω_s={Os:.3f} is outside the reliable Cordier-fit range [0.2, 10.0]. "
            "Result is an extrapolation."
        )

    return {
        "ok": True,
        "Omega_s": Os,
        "Delta_s_opt": Delta_s_opt,
        "machine_type": machine_type,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. degree_of_reaction
# ---------------------------------------------------------------------------

def degree_of_reaction(
    Ctheta1: float,
    Ctheta2: float,
    U: float,
) -> dict:
    """
    Stage degree of reaction R.

    For an axial stage with constant axial velocity:
        R = 1 − (Cθ1 + Cθ2) / (2·U)

    A 50% reaction (R=0.5) stage has symmetric velocity triangles.
    R < 0 indicates a stage with whirl velocities exceeding blade speed
    (unusual; may indicate impulse-exceeded turbine or mismatch).
    R > 1 indicates very low whirl velocities — also unusual for a
    turbine.

    Parameters
    ----------
    Ctheta1 : float
        Absolute whirl velocity at rotor inlet (m/s). Finite number.
    Ctheta2 : float
        Absolute whirl velocity at rotor exit (m/s). Finite number.
    U : float
        Blade speed (m/s). Must be > 0.

    Returns
    -------
    dict
        ok         : True
        R          : degree of reaction (dimensionless)
        Ctheta1    : inlet whirl velocity (m/s)
        Ctheta2    : exit whirl velocity (m/s)
        U_m_s      : blade speed (m/s)
        warnings   : list[str]

    References
    ----------
    Dixon §3.5
    """
    err = _guard_finite("Ctheta1", Ctheta1)
    if err:
        return _err(err)
    err = _guard_finite("Ctheta2", Ctheta2)
    if err:
        return _err(err)
    err = _guard_positive("U", U)
    if err:
        return _err(err)

    Ct1 = float(Ctheta1)
    Ct2 = float(Ctheta2)
    U_val = float(U)

    R = 1.0 - (Ct1 + Ct2) / (2.0 * U_val)

    warnings: list[str] = []
    if R < 0.0:
        warnings.append(
            f"Degree of reaction R={R:.3f} < 0: negative reaction stage. "
            "Unusual — check velocity triangle inputs."
        )
    if R > 1.0:
        warnings.append(
            f"Degree of reaction R={R:.3f} > 1: reaction exceeds unity. "
            "Unusual — check inputs."
        )

    return {
        "ok": True,
        "R": R,
        "Ctheta1": Ct1,
        "Ctheta2": Ct2,
        "U_m_s": U_val,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. axial_stage
# ---------------------------------------------------------------------------

def axial_stage(
    U: float,
    Ca: float,
    alpha1_deg: float,
    alpha2_deg: float,
    *,
    rho: float = 1.225,
    is_compressor: bool = True,
    chord: float | None = None,
    span: float | None = None,
    nu: float = 1.46e-5,
) -> dict:
    """
    Full axial compressor or turbine stage analysis.

    Computes velocity triangles, stage work, degree of reaction,
    diffusion factor / de Haller number (compressor) or blade loading
    coefficient (turbine).

    Parameters
    ----------
    U : float
        Blade (mean radius) speed (m/s). Must be > 0.
    Ca : float
        Axial velocity component (m/s). Assumed constant. Must be > 0.
    alpha1_deg : float
        Absolute inlet flow angle from axial (degrees). Range ±89°.
    alpha2_deg : float
        Absolute exit flow angle from axial (degrees). Range ±89°.
    rho : float
        Fluid density (kg/m³). Default 1.225. Must be > 0.
    is_compressor : bool
        True for compressor/fan (default), False for turbine.
    chord : float | None
        Blade chord (m). If provided with span, computes aspect ratio
        and blade Reynolds number. Must be > 0.
    span : float | None
        Blade span / height (m). Must be > 0 if provided.
    nu : float
        Kinematic viscosity (m²/s). Default 1.46e-5 (air at 15°C).

    Returns
    -------
    dict
        ok                : True
        velocity_triangles: sub-dict with all triangle quantities
        R                 : degree of reaction
        W_specific        : specific stage work (J/kg)
        diffusion_factor  : DF (compressor; None for turbine)
        de_haller         : W2/W1 (compressor only; None for turbine)
        blade_loading     : ΔCθ/U (both; key diagnostic)
        aspect_ratio      : span/chord (None if not provided)
        Re_blade          : blade chord Reynolds number (None if not provided)
        warnings          : list[str]

    Diffusion factor (Lieblein, compressor):
        DF = 1 − W2/W1 + |ΔWθ| / (2·σ·W1)
    where σ = chord/pitch is the solidity. If chord/span not provided,
    solidity is assumed = 1.0 for the DF formula.

    de Haller criterion: W2/W1 should be ≥ 0.72 to avoid stall.

    References
    ----------
    Dixon §5.5 (diffusion factor), §5.3 (de Haller).
    Saravanamuttoo §5.4.
    """
    # Compute velocity triangles
    vt = velocity_triangles_axial(U, Ca, alpha1_deg, alpha2_deg)
    if not vt["ok"]:
        return vt

    err = _guard_positive("rho", rho)
    if err:
        return _err(err)

    for nm, vl in (("chord", chord), ("span", span)):
        if vl is not None:
            e = _guard_positive(nm, vl)
            if e:
                return _err(e)

    W1 = vt["W1_m_s"]
    W2 = vt["W2_m_s"]
    Ct1 = vt["Ctheta1_m_s"]
    Ct2 = vt["Ctheta2_m_s"]
    dCt = vt["dCtheta_m_s"]
    U_val = float(U)
    Ca_val = float(Ca)

    # Degree of reaction
    R_res = degree_of_reaction(Ct1, Ct2, U_val)
    R = R_res["R"]

    W_specific = vt["W_specific"]
    blade_loading = dCt / U_val

    # Compressor-specific metrics
    diffusion_factor: float | None = None
    de_haller: float | None = None
    if is_compressor and W1 > 0:
        de_haller = W2 / W1
        # Diffusion factor (Lieblein) with solidity=1 (conservative)
        # DF = 1 - W2/W1 + |ΔWθ| / (2·σ·W1)  where σ=1
        dWt = abs((Ct2 - U_val) - (Ct1 - U_val))  # = |Ct2 - Ct1| = |dCt|
        diffusion_factor = 1.0 - de_haller + dWt / (2.0 * 1.0 * W1)

    # Aspect ratio and Reynolds number
    aspect_ratio: float | None = None
    Re_blade: float | None = None
    if chord is not None and span is not None:
        aspect_ratio = float(span) / float(chord)
        # Use W1 as representative velocity for Re
        if float(nu) > 0:
            Re_blade = W1 * float(chord) / float(nu)

    warnings: list[str] = R_res["warnings"][:]
    warnings.extend(vt["warnings"])

    if is_compressor:
        if de_haller is not None and de_haller < 0.72:
            warnings.append(
                f"de Haller number W2/W1={de_haller:.3f} < 0.72: "
                "risk of stall / blade boundary-layer separation (Dixon §5.3)."
            )
        if diffusion_factor is not None and diffusion_factor > 0.6:
            warnings.append(
                f"Diffusion factor DF={diffusion_factor:.3f} > 0.6: "
                "high blade loading — risk of stall (Lieblein criterion)."
            )
        if abs(blade_loading) > 0.5:
            warnings.append(
                f"Blade loading ΔCθ/U={blade_loading:.3f}: |value| > 0.5 "
                "is considered high for axial compressors."
            )
    else:
        # Turbine
        if abs(blade_loading) > 1.8:
            warnings.append(
                f"Turbine blade loading ΔCθ/U={blade_loading:.3f}: |value| > 1.8 "
                "is very high — check for flow separation."
            )

    return {
        "ok": True,
        "velocity_triangles": vt,
        "R": R,
        "W_specific": W_specific,
        "diffusion_factor": diffusion_factor,
        "de_haller": de_haller,
        "blade_loading": blade_loading,
        "aspect_ratio": aspect_ratio,
        "Re_blade": Re_blade,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. centrifugal_impeller
# ---------------------------------------------------------------------------

_G = 9.80665  # standard gravity (m/s²)


def centrifugal_impeller(
    n_rpm: float,
    D2_m: float,
    b2_m: float,
    *,
    D1_tip_m: float,
    D1_hub_m: float,
    beta2_deg: float = -30.0,
    Z: int = 8,
    rho: float = 1000.0,
    g: float = _G,
    slip_model: str = "stanitz",
) -> dict:
    """
    Centrifugal pump/compressor impeller design point analysis.

    Computes:
    - Blade tip speed U2 and inlet tip speed U1_tip
    - Volume flow rate Q from continuity at inlet
    - Exit velocity triangles with slip factor
    - Euler head (theoretical) H_euler = σ·U2·Cθ2 / g
    - NPSH inception estimate (suction-side cavitation inception)

    Parameters
    ----------
    n_rpm : float
        Rotational speed (rpm). Must be > 0.
    D2_m : float
        Impeller exit (outer) diameter (m). Must be > 0.
    b2_m : float
        Impeller exit blade width (m). Must be > 0.
    D1_tip_m : float
        Impeller inlet tip diameter (m). Must be > 0.
    D1_hub_m : float
        Impeller inlet hub diameter (m). Must be >= 0 (0 for open eye).
    beta2_deg : float
        Backward-swept blade angle at exit from radial (°). Default −30°.
    Z : int
        Number of impeller blades. Must be >= 2.
    rho : float
        Fluid density (kg/m³). Default 1000 (water). Must be > 0.
    g : float
        Gravitational acceleration (m/s²). Default 9.80665.
    slip_model : str
        Slip model: "stanitz" (default) or "wiesner" or "provided".
        With β2 measured from the radial (meridional) direction:
        "stanitz": σ = 1 − 0.63·π / Z   (Stanitz 1952; Dixon 7th ed.
                   Eq. 7.21b — radial-bladed approximation, weak β
                   dependence, valid −80° ≤ β2 ≤ 0).
        "wiesner": σ = 1 − √(cos|β2|) / Z^0.7  (Wiesner 1967; Dixon
                   7th ed. Eq. 7.21 — β2 from radial, so the blade angle
                   from the tangent is 90°−|β2| and the standard
                   √(sin β_tangent) becomes √(cos|β2_radial|)).
        (Negative beta2 denotes backward sweep; |β2| used.)

    Returns
    -------
    dict
        ok                : True
        n_rpm             : shaft speed (rpm)
        omega_rad_s       : angular velocity (rad/s)
        U2_m_s            : tip blade speed (m/s)
        U1_tip_m_s        : inlet tip blade speed (m/s)
        Cr2_m_s           : exit radial velocity (m/s) from continuity
        Q_m3_s            : volume flow rate (m³/s)
        slip_factor       : σ used
        Ctheta2_m_s       : exit whirl velocity (m/s) with slip
        H_euler_m         : Euler (theoretical) head (m)
        W_specific        : specific work = σ·U2·Cθ2 (J/kg)
        NPSH_inception_m  : NPSH inception estimate (m)
        warnings          : list[str]

    Notes
    -----
    NPSH inception (simplified Pfleiderer/Kaplan estimate):
        NPSHi ≈ 0.3 · U1_tip² / (2g)
    This is a rough first estimate; proper NPSH requires cavitation
    number analysis and empirical correction.

    Slip factor (Stanitz, Dixon 7th ed. Eq. 7.21b):
        σ = 1 − 0.63·π / Z
    Approximately independent of blade angle; valid −80° ≤ β2 ≤ 0
    (β2 from radial).  Wiesner (Eq. 7.21): σ = 1 − √(cos|β2|)/Z^0.7.

    Continuity at exit:
        Q = π · D2 · b2 · Cr2
    with Cr2 obtained from inlet continuity (assuming no pre-swirl):
        Q = π/4 · (D1_tip² − D1_hub²) · Ca1
    We iterate for consistency; here Ca1 = Cr2 (meridional velocity assumed
    equal at inlet and exit as a first estimate).

    References
    ----------
    Dixon §7.2–7.5; White §11.4; Pfleiderer (1932).
    """
    err = _guard_positive("n_rpm", n_rpm)
    if err:
        return _err(err)
    err = _guard_positive("D2_m", D2_m)
    if err:
        return _err(err)
    err = _guard_positive("b2_m", b2_m)
    if err:
        return _err(err)
    err = _guard_positive("D1_tip_m", D1_tip_m)
    if err:
        return _err(err)
    err = _guard_nonneg("D1_hub_m", D1_hub_m)
    if err:
        return _err(err)
    if float(D1_hub_m) >= float(D1_tip_m):
        return _err("D1_hub_m must be < D1_tip_m.")
    if float(D1_tip_m) > float(D2_m):
        return _err("D1_tip_m must be <= D2_m (inlet tip cannot exceed impeller OD).")

    err = _guard_finite("beta2_deg", beta2_deg)
    if err:
        return _err(err)
    if abs(float(beta2_deg)) >= 89.0:
        return _err("beta2_deg magnitude must be < 89°.")

    try:
        Z_int = int(Z)
    except (TypeError, ValueError):
        return _err(f"Z must be an integer, got {Z!r}.")
    if Z_int < 2:
        return _err(f"Z (blade count) must be >= 2, got {Z_int}.")

    err = _guard_positive("rho", rho)
    if err:
        return _err(err)
    err = _guard_positive("g", g)
    if err:
        return _err(err)

    slip_model_s = str(slip_model).strip().lower()
    if slip_model_s not in ("stanitz", "wiesner", "provided"):
        return _err(f"slip_model must be 'stanitz', 'wiesner', or 'provided'; got {slip_model!r}.")

    n = float(n_rpm)
    omega = n * 2.0 * math.pi / 60.0
    D2 = float(D2_m)
    b2 = float(b2_m)
    D1t = float(D1_tip_m)
    D1h = float(D1_hub_m)
    b2_rad = abs(_deg2rad(float(beta2_deg)))  # magnitude for slip

    U2 = omega * D2 / 2.0
    U1_tip = omega * D1t / 2.0

    # Slip factor (β2 measured from radial; b2_rad = |β2| in radians)
    if slip_model_s == "stanitz":
        # Stanitz 1952 / Dixon 7th ed. Eq. 7.21b: σ = 1 − 0.63π/Z
        # (radial-bladed approximation, weak blade-angle dependence)
        sigma = 1.0 - 0.63 * math.pi / Z_int
    elif slip_model_s == "wiesner":
        # Wiesner 1967 / Dixon Eq. 7.21: σ = 1 − √(sin β2_tangent)/Z^0.7.
        # β2 here is from radial, so β2_tangent = 90°−|β2| and
        # sin(β2_tangent) = cos|β2|.
        sigma = 1.0 - math.sqrt(math.cos(b2_rad)) / Z_int**0.7
    else:
        sigma = 0.9  # 'provided' uses a placeholder — user should use velocity_triangles_centrifugal

    sigma = max(0.0, min(sigma, 1.0))  # clamp to [0,1]

    # Inlet annulus area (no pre-swirl assumed → axial inlet)
    A1 = math.pi / 4.0 * (D1t**2 - D1h**2)
    # Exit annulus area
    A2 = math.pi * D2 * b2

    # Meridional (radial at exit, axial at inlet) velocity from continuity
    # Q = A1 * Ca1 = A2 * Cr2  → Ca1 = Cr2 * A2/A1
    # Exit blade angle: Cr2 = (U2 - Ctheta2_ideal) / tan(|beta2|)
    # But Ctheta2_ideal = U2 - Cr2 * tan(|beta2|)
    # Ctheta2_actual = sigma * Ctheta2_ideal = sigma * (U2 - Cr2 * tan|beta2|)
    # This is the standard centrifugal impeller exit relation (Dixon §7.2)
    #
    # We estimate Cr2 from geometry + flow rate. Since we don't have
    # an independent Q to start, we solve using A2:
    # Q = A2 * Cr2
    # Exit: Ctheta2 = sigma * (U2 + Cr2 * tan(beta2_signed))
    # For backward sweep beta2 < 0: tan(beta2_signed) < 0
    # → Ctheta2 = sigma * (U2 - Cr2 * tan|beta2|)
    # Specific work W = U2 * Ctheta2 = sigma * U2 * (U2 - Cr2 * tan|beta2|)
    #
    # Without specifying Q independently, we use a simple estimate:
    # Assume Ca1 = Cr2 (meridional velocity equal at inlet and exit),
    # then Q = A2 * Cr2 = A1 * Ca1 → Cr2 = Q/A2 (circular)
    # We break circularity by choosing Cr2 from inlet flow capacity:
    # Ca1 = design axial velocity at inlet — typical Ca1 ~ 0.4 * U1_tip
    # for a well-designed impeller (Dixon §7.1 guidance).
    Ca1_design = 0.4 * U1_tip
    Q = A1 * Ca1_design
    Cr2 = Q / A2 if A2 > 0 else Ca1_design

    # Exit velocity triangle
    b2_signed_rad = _deg2rad(float(beta2_deg))  # signed
    Ct2_ideal = U2 + Cr2 * math.tan(b2_signed_rad)
    Ct2_actual = sigma * Ct2_ideal

    W_specific = U2 * Ct2_actual
    H_euler = W_specific / float(g)

    # NPSH inception estimate (Pfleiderer/Kaplan)
    # NPSHi ≈ 0.3 * U1_tip² / (2g)  — conservative lower-bound
    NPSH_i = 0.3 * U1_tip**2 / (2.0 * float(g))

    warnings: list[str] = []
    if sigma < 0.85:
        warnings.append(
            f"Slip factor σ={sigma:.3f} < 0.85: significant slip; consider "
            "increasing blade count Z or adjusting blade geometry."
        )
    if H_euler < 0:
        warnings.append(
            f"Euler head H_euler={H_euler:.2f} m is negative: the impeller "
            "is absorbing no useful head. Check geometry and speed."
        )
    if Ct2_ideal < 0:
        warnings.append(
            "Ideal whirl velocity is negative: strongly forward-swept blade "
            "or excessive radial velocity."
        )

    return {
        "ok": True,
        "n_rpm": n,
        "omega_rad_s": omega,
        "U2_m_s": U2,
        "U1_tip_m_s": U1_tip,
        "Cr2_m_s": Cr2,
        "Q_m3_s": Q,
        "slip_factor": sigma,
        "Ctheta2_m_s": Ct2_actual,
        "H_euler_m": H_euler,
        "W_specific": W_specific,
        "NPSH_inception_m": NPSH_i,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 10. fan_affinity
# ---------------------------------------------------------------------------

def fan_affinity(
    Q1: float,
    H1: float,
    P1: float,
    n1: float,
    n2: float,
    *,
    D1: float | None = None,
    D2: float | None = None,
) -> dict:
    """
    Fan / pump affinity laws: speed change and/or impeller-trim.

    Affinity laws (constant geometry):
        Q2/Q1 = (n2/n1)
        H2/H1 = (n2/n1)²
        P2/P1 = (n2/n1)³

    Impeller-trim laws (constant speed, changing diameter):
        Q2/Q1 = (D2/D1)
        H2/H1 = (D2/D1)²
        P2/P1 = (D2/D1)³

    Combined (both speed and diameter change):
        Q2/Q1 = (n2/n1)·(D2/D1)
        H2/H1 = (n2/n1)²·(D2/D1)²
        P2/P1 = (n2/n1)³·(D2/D1)³

    Parameters
    ----------
    Q1 : float
        Reference flow rate (m³/s). Must be > 0.
    H1 : float
        Reference head or pressure rise (m). Must be > 0.
    P1 : float
        Reference shaft power (W). Must be > 0.
    n1 : float
        Reference speed (rpm). Must be > 0.
    n2 : float
        New speed (rpm). Must be > 0.
    D1 : float | None
        Reference impeller diameter (m). Required if D2 provided.
    D2 : float | None
        New impeller diameter (m). Must be > 0 and <= D1.

    Returns
    -------
    dict
        ok          : True
        Q2          : new flow rate (m³/s)
        H2          : new head (m)
        P2          : new shaft power (W)
        speed_ratio : n2/n1
        diam_ratio  : D2/D1 (1.0 if no trim)
        combined_ratio: speed_ratio × diam_ratio
        warnings    : list[str]

    References
    ----------
    Dixon §1.4; HI (Hydraulic Institute) Standards 9.6.8.
    """
    err = _guard_positive("Q1", Q1)
    if err:
        return _err(err)
    err = _guard_positive("H1", H1)
    if err:
        return _err(err)
    err = _guard_positive("P1", P1)
    if err:
        return _err(err)
    err = _guard_positive("n1", n1)
    if err:
        return _err(err)
    err = _guard_positive("n2", n2)
    if err:
        return _err(err)

    diam_ratio = 1.0
    if D2 is not None:
        if D1 is None:
            return _err("D1 must be provided when D2 is specified.")
        err = _guard_positive("D1", D1)
        if err:
            return _err(err)
        err = _guard_positive("D2", D2)
        if err:
            return _err(err)
        diam_ratio = float(D2) / float(D1)

    speed_ratio = float(n2) / float(n1)
    combined = speed_ratio * diam_ratio

    Q2 = float(Q1) * combined
    H2 = float(H1) * combined**2
    P2 = float(P1) * combined**3

    warnings: list[str] = []
    if diam_ratio < 0.7:
        warnings.append(
            f"Impeller trim ratio D2/D1={diam_ratio:.3f} < 0.70: "
            "affinity law accuracy degrades significantly below 70% trim "
            "(HI Standards 9.6.8)."
        )
    if speed_ratio > 1.2:
        warnings.append(
            f"Speed ratio n2/n1={speed_ratio:.3f} > 1.20: motor overload risk "
            "— verify power available at new speed P2={P2:.0f} W."
        )
    if speed_ratio < 0.5:
        warnings.append(
            f"Speed ratio n2/n1={speed_ratio:.3f} < 0.50: very low speed "
            "— pump/fan may fall below minimum self-priming or stable-operation speed."
        )

    return {
        "ok": True,
        "Q2": Q2,
        "H2": H2,
        "P2": P2,
        "speed_ratio": speed_ratio,
        "diam_ratio": diam_ratio,
        "combined_ratio": combined,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 11. stage_efficiency
# ---------------------------------------------------------------------------

def stage_efficiency(
    W_actual: float,
    W_isentropic: float,
    *,
    polytropic_n: float | None = None,
    gamma: float = 1.4,
    stage_type: str = "compressor",
) -> dict:
    """
    Isentropic and polytropic efficiency; small-stage reheat/preheat factor.

    Parameters
    ----------
    W_actual : float
        Actual specific work (J/kg). Must be > 0.
    W_isentropic : float
        Isentropic specific work for the same pressure ratio (J/kg).
        Must be > 0.
    polytropic_n : float | None
        Polytropic index n. If provided, polytropic efficiency is
        computed from η_p = (n−1)/n × γ/(γ−1) for compression.
    gamma : float
        Ratio of specific heats cp/cv. Default 1.4 (air). Must be > 1.
    stage_type : str
        "compressor" (default) or "turbine".

    Returns
    -------
    dict
        ok                   : True
        eta_isentropic       : isentropic efficiency η_is
        eta_polytropic       : polytropic efficiency η_p (None if not computable)
        small_stage_factor   : preheat/reheat factor f_r (approximate)
        stage_type           : type string
        warnings             : list[str]

    Notes
    -----
    Isentropic efficiency:
        Compressor: η_is = W_isentropic / W_actual  (< 1 for real compressor)
        Turbine:    η_is = W_actual / W_isentropic  (< 1 for real turbine)

    Polytropic efficiency (from polytropic index n, Dixon §2.3):
        Compressor: η_p = [(γ−1)/γ] / [(n−1)/n]
        Turbine:    η_p = [(n−1)/n] / [(γ−1)/γ]

    Small-stage reheat factor (Dixon §2.6 approximate):
        For compressor: f_r ≈ 1 + (1 − η_is) × (γ−1) / (2γ)
        This accounts for the sequential heating effect across stages.

    References
    ----------
    Dixon §2.3–2.6; Sara §3.4.
    """
    err = _guard_positive("W_actual", W_actual)
    if err:
        return _err(err)
    err = _guard_positive("W_isentropic", W_isentropic)
    if err:
        return _err(err)

    if float(gamma) <= 1.0:
        return _err(f"gamma must be > 1.0, got {gamma}.")

    stage_s = str(stage_type).strip().lower()
    if stage_s not in ("compressor", "turbine"):
        return _err(f"stage_type must be 'compressor' or 'turbine', got {stage_type!r}.")

    W_a = float(W_actual)
    W_is = float(W_isentropic)
    gam = float(gamma)

    if stage_s == "compressor":
        eta_is = W_is / W_a
    else:
        eta_is = W_a / W_is

    # Polytropic efficiency
    eta_p: float | None = None
    if polytropic_n is not None:
        err = _guard_positive("polytropic_n", polytropic_n)
        if err:
            return _err(err)
        n = float(polytropic_n)
        if n == 1.0:
            return _err("polytropic_n cannot be exactly 1.0 (isothermal limit).")
        ratio_n = (n - 1.0) / n
        ratio_gam = (gam - 1.0) / gam
        if stage_s == "compressor":
            eta_p = ratio_gam / ratio_n
        else:
            eta_p = ratio_n / ratio_gam

    # Small-stage reheat factor (approximate, compressor preheat or turbine reheat)
    # f_r ≈ 1 + (1 − η_is) * (γ−1) / (2γ)  Dixon §2.6
    f_r = 1.0 + (1.0 - eta_is) * (gam - 1.0) / (2.0 * gam)

    warnings: list[str] = []
    if eta_is > 1.0:
        warnings.append(
            f"Isentropic efficiency η_is={eta_is:.4f} > 1.0: "
            "W_isentropic > W_actual for a compressor (or vice-versa for turbine) — "
            "check inputs."
        )
    if eta_is < 0.5:
        warnings.append(
            f"Isentropic efficiency η_is={eta_is:.4f} < 0.5: very low — "
            "check if actual and isentropic work are in consistent units/sign."
        )
    if eta_p is not None and eta_p > 1.0:
        warnings.append(
            f"Polytropic efficiency η_p={eta_p:.4f} > 1.0 — check polytropic_n value."
        )

    return {
        "ok": True,
        "eta_isentropic": eta_is,
        "eta_polytropic": eta_p,
        "small_stage_factor": f_r,
        "stage_type": stage_s,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 12. surge_choke_margin
# ---------------------------------------------------------------------------

def surge_choke_margin(
    phi_op: float,
    phi_surge: float,
    phi_choke: float,
    *,
    min_surge_margin: float = 0.15,
    min_choke_margin: float = 0.10,
) -> dict:
    """
    Surge margin and choke margin for a compressor/fan stage.

    Surge margin (SM) = (phi_op − phi_surge) / phi_op
    Choke margin (CM) = (phi_choke − phi_op) / phi_op

    A positive surge margin means the operating point is to the right of
    the surge line (safer for compressors).  A positive choke margin means
    the operating point is to the left of choke.

    Parameters
    ----------
    phi_op : float
        Operating flow coefficient. Must be > 0.
    phi_surge : float
        Flow coefficient at surge line. Must be >= 0.
    phi_choke : float
        Flow coefficient at choke. Must be > phi_op.
    min_surge_margin : float
        Minimum acceptable surge margin (default 0.15 = 15%).
    min_choke_margin : float
        Minimum acceptable choke margin (default 0.10 = 10%).

    Returns
    -------
    dict
        ok              : True
        surge_margin    : SM (dimensionless)
        choke_margin    : CM (dimensionless)
        surge_risk      : True if SM < min_surge_margin
        choke_risk      : True if CM < min_choke_margin
        phi_op          : operating flow coefficient
        phi_surge       : surge flow coefficient
        phi_choke       : choke flow coefficient
        warnings        : list[str]

    Notes
    -----
    For a turbine the "surge" / "choke" concept maps to stall and choking of
    the turbine nozzle; the same margin definition applies.

    References
    ----------
    Dixon §5.9; Sara §4.7.
    """
    err = _guard_positive("phi_op", phi_op)
    if err:
        return _err(err)
    err = _guard_nonneg("phi_surge", phi_surge)
    if err:
        return _err(err)
    err = _guard_positive("phi_choke", phi_choke)
    if err:
        return _err(err)

    if float(phi_choke) <= float(phi_op):
        return _err(
            f"phi_choke={phi_choke} must be > phi_op={phi_op}."
        )

    phi_o = float(phi_op)
    phi_s = float(phi_surge)
    phi_c = float(phi_choke)

    SM = (phi_o - phi_s) / phi_o
    CM = (phi_c - phi_o) / phi_o

    min_SM = float(min_surge_margin)
    min_CM = float(min_choke_margin)

    surge_risk = SM < min_SM
    choke_risk = CM < min_CM

    warnings: list[str] = []
    if SM < 0:
        warnings.append(
            f"SURGE: operating point is left of surge line "
            f"(SM={SM:.3f} < 0) — compressor/fan is in surge."
        )
    elif surge_risk:
        warnings.append(
            f"Low surge margin SM={SM:.3f} < {min_SM:.2f}: "
            "operating point is close to surge line."
        )
    if choke_risk:
        warnings.append(
            f"Low choke margin CM={CM:.3f} < {min_CM:.2f}: "
            "operating point is close to choke."
        )

    return {
        "ok": True,
        "surge_margin": SM,
        "choke_margin": CM,
        "surge_risk": surge_risk,
        "choke_risk": choke_risk,
        "phi_op": phi_o,
        "phi_surge": phi_s,
        "phi_choke": phi_c,
        "warnings": warnings,
    }
