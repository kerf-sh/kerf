"""
kerf_cad_core.vibration.dynamics — pure-Python mechanical vibration formulas.

Implements twelve public functions covering:

  SDOF (Single-Degree-Of-Freedom):
    sdof_natural_frequency(m, k)
        Undamped natural frequency ωn and fn.

    sdof_damped_frequency(m, k, c)
        Damped natural frequency ωd and fn_d.

    sdof_damping_ratio_log_decrement(x1, xn, n)
        Damping ratio ζ from logarithmic decrement of free-vibration peaks.

    sdof_free_response(m, k, c, x0, v0, t)
        Free-vibration displacement x(t) for underdamped (ζ<1), critically
        damped (ζ=1), or overdamped (ζ>1) systems.

    sdof_harmonic_magnification(zeta, r)
        Dynamic magnification factor M and phase angle φ for harmonic
        forced excitation; r = ω/ωn.

    sdof_harmonic_phase(zeta, r)
        Phase angle φ (rad) for harmonic forced response (convenience wrapper).

    sdof_base_transmissibility(zeta, r)
        Force/displacement transmissibility TR for base excitation.

    sdof_rotating_unbalance(m, k, c, m_u, e, omega)
        Steady-state amplitude X and non-dimensionalised MX/(m_u·e) for a
        rotating unbalance excitation.

  2-DOF (undamped):
    dof2_eigen(m1, m2, k1, k2, k3)
        Natural frequencies ω1, ω2 (rad/s) and mode shapes for an undamped
        2-DOF spring-mass system via 2×2 closed-form characteristic equation.

  Continuous systems:
    beam_natural_frequency(mode, length_m, mass_per_m, E, I, bc)
        Euler-Bernoulli beam natural frequencies (rad/s) for cantilever or
        simply-supported boundary conditions using the βL roots table.

    shaft_whirl_rayleigh(lengths_m, masses_kg, E, I)
        First whirl (lateral) critical speed of a multi-disk shaft by
        Rayleigh's energy method.

  Isolation:
    isolator_stiffness(m, omega_exc, TR_target)
        Required isolator stiffness k for a target transmissibility TR at
        excitation frequency omega_exc (undamped isolator, ζ≈0).

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Resonance proximity is flagged in the "warnings"
list using the Python `warnings` module (std-lib) as a side-effect — never
as exceptions.

Units
-----
  lengths    — metres (m)
  masses     — kilograms (kg)
  stiffness  — N/m
  damping    — N·s/m
  frequency  — rad/s (angular) or Hz (cyclic) as noted
  time       — seconds (s)

References
----------
Rao, S.S. "Mechanical Vibrations", 5th ed. (Pearson) — Chs. 2, 3, 5, 8
Inman, D.J. "Engineering Vibration", 4th ed. (Pearson) — Chs. 1, 2, 3
Thomson, W.T. "Theory of Vibration with Applications", 5th ed. — Chs. 2, 3
Genta, G. "Dynamics of Rotating Systems" (Springer) — Rayleigh's method

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_mod
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_resonance(r: float, zeta: float, warnings_list: list[str]) -> None:
    """Flag resonance proximity if r is within 5% of 1.0."""
    if abs(r - 1.0) <= 0.05 and zeta < 0.2:
        msg = (
            f"Operating at resonance proximity: frequency ratio r={r:.4f} ≈ 1.0 "
            f"with damping ratio ζ={zeta:.4f}. Magnification may be very large. "
            "Consider detuning or adding damping."
        )
        warnings_list.append(msg)
        _warnings_mod.warn(msg, UserWarning, stacklevel=4)


# ---------------------------------------------------------------------------
# Euler-Bernoulli beam βL roots table
# ---------------------------------------------------------------------------
# Cantilever (clamped-free): cos(βL)cosh(βL) = -1
#   mode 1: βL = 1.87510
#   mode 2: βL = 4.69409
#   mode 3: βL = 7.85476
#   mode 4: βL = 10.99554
#
# Simply-supported (pinned-pinned): sin(βL) = 0  → βL = n·π
#   mode n: βL = n·π

_BEAM_CANTILEVER_BL = {
    1: 1.87510407,
    2: 4.69409113,
    3: 7.85475744,
    4: 10.99554073,
}

_BEAM_SS_BL_FACTOR = math.pi  # βL = n·π for mode n


# ===========================================================================
# 1. SDOF natural frequency
# ===========================================================================

def sdof_natural_frequency(m: float, k: float) -> dict:
    """
    Undamped natural frequency of a SDOF system.

    Parameters
    ----------
    m : float
        Mass (kg). Must be > 0.
    k : float
        Spring stiffness (N/m). Must be > 0.

    Returns
    -------
    dict
        ok          : True
        omega_n     : undamped natural frequency (rad/s)
        fn_hz       : undamped natural frequency (Hz)
        m_kg        : mass used (kg)
        k_N_per_m   : stiffness used (N/m)
        warnings    : []

    Formula
    -------
    ωn = √(k/m)    fn = ωn / (2π)

    References
    ----------
    Rao §2-1; Inman §1.1
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("k", k)
    if err:
        return _err(err)

    omega_n = math.sqrt(float(k) / float(m))
    return {
        "ok": True,
        "omega_n": omega_n,
        "fn_hz": omega_n / (2.0 * math.pi),
        "m_kg": float(m),
        "k_N_per_m": float(k),
        "warnings": [],
    }


# ===========================================================================
# 2. SDOF damped natural frequency
# ===========================================================================

def sdof_damped_frequency(m: float, k: float, c: float) -> dict:
    """
    Damped natural frequency of a SDOF system.

    Parameters
    ----------
    m : float
        Mass (kg). Must be > 0.
    k : float
        Spring stiffness (N/m). Must be > 0.
    c : float
        Viscous damping coefficient (N·s/m). Must be >= 0.

    Returns
    -------
    dict
        ok          : True
        omega_n     : undamped natural frequency (rad/s)
        omega_d     : damped natural frequency (rad/s)  — 0 if ζ >= 1
        fn_d_hz     : damped natural frequency (Hz)
        zeta        : damping ratio c / c_cr
        c_cr        : critical damping coefficient (N·s/m)
        regime      : "underdamped" | "critically_damped" | "overdamped"
        warnings    : list of warning strings

    Formula
    -------
    c_cr = 2√(km)    ζ = c / c_cr
    ωd   = ωn √(1 - ζ²)   [underdamped only; 0 for ζ >= 1]

    References
    ----------
    Rao §2-3; Inman §1.3
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("k", k)
    if err:
        return _err(err)
    err = _guard_nonneg("c", c)
    if err:
        return _err(err)

    m_f = float(m)
    k_f = float(k)
    c_f = float(c)

    omega_n = math.sqrt(k_f / m_f)
    c_cr = 2.0 * math.sqrt(k_f * m_f)
    zeta = c_f / c_cr if c_cr > 0 else 0.0

    warnings: list[str] = []

    if zeta < 1.0:
        omega_d = omega_n * math.sqrt(1.0 - zeta ** 2)
        regime = "underdamped"
    elif abs(zeta - 1.0) < 1e-12:
        omega_d = 0.0
        regime = "critically_damped"
    else:
        omega_d = 0.0
        regime = "overdamped"
        warnings.append(
            f"System is overdamped (ζ={zeta:.4f} > 1); no oscillatory response."
        )

    return {
        "ok": True,
        "omega_n": omega_n,
        "omega_d": omega_d,
        "fn_d_hz": omega_d / (2.0 * math.pi),
        "zeta": zeta,
        "c_cr": c_cr,
        "regime": regime,
        "warnings": warnings,
    }


# ===========================================================================
# 3. Damping ratio from logarithmic decrement
# ===========================================================================

def sdof_damping_ratio_log_decrement(x1: float, xn: float, n: int) -> dict:
    """
    Estimate damping ratio ζ from n consecutive free-vibration peaks.

    Parameters
    ----------
    x1 : float
        Amplitude of first peak. Must be > 0.
    xn : float
        Amplitude of the n-th peak. Must be > 0 and < x1.
    n : int
        Number of cycles between x1 and xn. Must be >= 1.

    Returns
    -------
    dict
        ok              : True
        delta           : logarithmic decrement δ = (1/n) ln(x1/xn)
        zeta            : damping ratio ζ = δ / √(4π² + δ²)
        zeta_approx     : approximate damping ratio ζ ≈ δ/(2π) (valid for δ<<1)
        warnings        : list of warning strings

    Formula
    -------
    δ = (1/n) ln(x1/xn)
    ζ = δ / √(4π² + δ²)

    The approximate form ζ ≈ δ/(2π) is accurate to within 1% for ζ < 0.1.

    References
    ----------
    Rao §2-7; Inman §1.5
    """
    err = _guard_positive("x1", x1)
    if err:
        return _err(err)
    err = _guard_positive("xn", xn)
    if err:
        return _err(err)

    try:
        n_i = int(n)
    except (TypeError, ValueError):
        return _err(f"n must be a positive integer, got {n!r}")
    if n_i < 1:
        return _err(f"n must be >= 1, got {n_i}")

    x1_f = float(x1)
    xn_f = float(xn)

    if xn_f >= x1_f:
        return _err(
            f"xn ({xn_f}) must be < x1 ({x1_f}); amplitudes must be decreasing."
        )

    delta = (1.0 / n_i) * math.log(x1_f / xn_f)
    zeta = delta / math.sqrt(4.0 * math.pi ** 2 + delta ** 2)
    zeta_approx = delta / (2.0 * math.pi)

    warnings: list[str] = []
    if delta > 1.0:
        warnings.append(
            f"Logarithmic decrement δ={delta:.4f} > 1; approximate formula "
            "ζ ≈ δ/(2π) may be inaccurate — use exact ζ value."
        )

    return {
        "ok": True,
        "delta": delta,
        "zeta": zeta,
        "zeta_approx": zeta_approx,
        "warnings": warnings,
    }


# ===========================================================================
# 4. SDOF free-vibration response x(t)
# ===========================================================================

def sdof_free_response(
    m: float,
    k: float,
    c: float,
    x0: float,
    v0: float,
    t: float,
) -> dict:
    """
    Free-vibration displacement x(t) for a SDOF system.

    Parameters
    ----------
    m : float
        Mass (kg). Must be > 0.
    k : float
        Spring stiffness (N/m). Must be > 0.
    c : float
        Viscous damping (N·s/m). Must be >= 0.
    x0 : float
        Initial displacement (m). May be any finite value.
    v0 : float
        Initial velocity (m/s). May be any finite value.
    t : float
        Time at which to evaluate x(t) (s). Must be >= 0.

    Returns
    -------
    dict
        ok          : True
        x_t         : displacement x(t) (m)
        t_s         : time used (s)
        zeta        : damping ratio
        omega_n     : undamped natural frequency (rad/s)
        regime      : "underdamped" | "critically_damped" | "overdamped"
        warnings    : list of warning strings

    Formulas
    --------
    Underdamped (ζ < 1):
        x(t) = e^(-ζ ωn t) [x0 cos(ωd t) + (v0 + ζ ωn x0)/ωd × sin(ωd t)]

    Critically damped (ζ = 1):
        x(t) = (x0 + (v0 + ωn x0) t) e^(-ωn t)

    Overdamped (ζ > 1):
        x(t) = e^(-ζ ωn t) [A cosh(ωd_od t) + B sinh(ωd_od t)]
        where ωd_od = ωn √(ζ² - 1),
              A = x0,
              B = (v0 + ζ ωn x0) / ωd_od

    References
    ----------
    Rao §2-4; Inman §1.2
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("k", k)
    if err:
        return _err(err)
    err = _guard_nonneg("c", c)
    if err:
        return _err(err)
    err = _guard_nonneg("t", t)
    if err:
        return _err(err)

    try:
        x0_f = float(x0)
        v0_f = float(v0)
    except (TypeError, ValueError):
        return _err("x0 and v0 must be numbers")

    if not math.isfinite(x0_f):
        return _err(f"x0 must be finite, got {x0_f}")
    if not math.isfinite(v0_f):
        return _err(f"v0 must be finite, got {v0_f}")

    m_f = float(m)
    k_f = float(k)
    c_f = float(c)
    t_f = float(t)

    omega_n = math.sqrt(k_f / m_f)
    c_cr = 2.0 * math.sqrt(k_f * m_f)
    zeta = c_f / c_cr if c_cr > 0 else 0.0

    warnings: list[str] = []

    if zeta < 1.0 - 1e-12:
        # Underdamped
        omega_d = omega_n * math.sqrt(1.0 - zeta ** 2)
        decay = math.exp(-zeta * omega_n * t_f)
        x_t = decay * (
            x0_f * math.cos(omega_d * t_f)
            + (v0_f + zeta * omega_n * x0_f) / omega_d * math.sin(omega_d * t_f)
        )
        regime = "underdamped"
    elif abs(zeta - 1.0) < 1e-12 or (zeta >= 1.0 - 1e-12 and zeta <= 1.0 + 1e-12):
        # Critically damped
        decay = math.exp(-omega_n * t_f)
        x_t = (x0_f + (v0_f + omega_n * x0_f) * t_f) * decay
        regime = "critically_damped"
    else:
        # Overdamped
        omega_d_od = omega_n * math.sqrt(zeta ** 2 - 1.0)
        A = x0_f
        B = (v0_f + zeta * omega_n * x0_f) / omega_d_od
        decay = math.exp(-zeta * omega_n * t_f)
        x_t = decay * (A * math.cosh(omega_d_od * t_f) + B * math.sinh(omega_d_od * t_f))
        regime = "overdamped"
        warnings.append(
            f"System is overdamped (ζ={zeta:.4f} > 1); response decays without oscillation."
        )

    return {
        "ok": True,
        "x_t": x_t,
        "t_s": t_f,
        "zeta": zeta,
        "omega_n": omega_n,
        "regime": regime,
        "warnings": warnings,
    }


# ===========================================================================
# 5. SDOF harmonic forced-response magnification & phase
# ===========================================================================

def sdof_harmonic_magnification(zeta: float, r: float) -> dict:
    """
    Dynamic magnification factor M and phase angle φ for harmonic excitation.

    Parameters
    ----------
    zeta : float
        Damping ratio ζ. Must be >= 0.
    r : float
        Frequency ratio r = ω / ωn. Must be > 0.

    Returns
    -------
    dict
        ok          : True
        M           : dynamic magnification factor X / (F0/k)
        phi_rad     : phase angle φ (rad)  — lag of response behind excitation
        phi_deg     : phase angle φ (degrees)
        r           : frequency ratio used
        zeta        : damping ratio used
        warnings    : list of warning strings (resonance proximity)

    Formula
    -------
    M   = 1 / √[(1 - r²)² + (2ζr)²]
    φ   = arctan[2ζr / (1 - r²)]

    References
    ----------
    Rao §3-4; Inman §2.1
    """
    err = _guard_nonneg("zeta", zeta)
    if err:
        return _err(err)
    err = _guard_positive("r", r)
    if err:
        return _err(err)

    zeta_f = float(zeta)
    r_f = float(r)

    warnings: list[str] = []
    _check_resonance(r_f, zeta_f, warnings)

    denom_sq = (1.0 - r_f ** 2) ** 2 + (2.0 * zeta_f * r_f) ** 2
    if denom_sq <= 0:
        return _err("Denominator is zero (undamped resonance); magnification is unbounded.")

    M = 1.0 / math.sqrt(denom_sq)
    phi_rad = math.atan2(2.0 * zeta_f * r_f, 1.0 - r_f ** 2)
    # atan2 can return negative; phase lag is [0, π] by convention
    if phi_rad < 0:
        phi_rad += math.pi

    return {
        "ok": True,
        "M": M,
        "phi_rad": phi_rad,
        "phi_deg": math.degrees(phi_rad),
        "r": r_f,
        "zeta": zeta_f,
        "warnings": warnings,
    }


# ===========================================================================
# 6. SDOF harmonic phase (convenience)
# ===========================================================================

def sdof_harmonic_phase(zeta: float, r: float) -> dict:
    """
    Phase angle φ for harmonic forced response (convenience wrapper).

    Returns the same fields as sdof_harmonic_magnification but named for
    phase-focused use cases.

    Parameters
    ----------
    zeta : float
        Damping ratio ζ. Must be >= 0.
    r : float
        Frequency ratio r = ω / ωn. Must be > 0.

    Returns
    -------
    dict
        ok          : True
        phi_rad     : phase angle (rad)
        phi_deg     : phase angle (degrees)
        M           : magnification factor (included for completeness)
        r           : frequency ratio
        zeta        : damping ratio
        warnings    : list

    References
    ----------
    Rao §3-4; Inman §2.1
    """
    return sdof_harmonic_magnification(zeta, r)


# ===========================================================================
# 7. SDOF base-excitation transmissibility
# ===========================================================================

def sdof_base_transmissibility(zeta: float, r: float) -> dict:
    """
    Force / displacement transmissibility TR for base excitation.

    Parameters
    ----------
    zeta : float
        Damping ratio ζ. Must be >= 0.
    r : float
        Frequency ratio r = ω / ωn. Must be > 0.

    Returns
    -------
    dict
        ok          : True
        TR          : transmissibility ratio X_abs / Y  (dimensionless)
        TR_dB       : transmissibility in dB  20·log10(TR)
        r           : frequency ratio
        zeta        : damping ratio
        isolating   : True if TR < 1 (r > √2 with this damping)
        warnings    : list of warning strings

    Formula
    -------
    TR = √[(1 + (2ζr)²) / ((1 - r²)² + (2ζr)²)]

    Isolation begins when TR < 1, i.e., approximately r > √2.

    References
    ----------
    Rao §3-6; Inman §2.4
    """
    err = _guard_nonneg("zeta", zeta)
    if err:
        return _err(err)
    err = _guard_positive("r", r)
    if err:
        return _err(err)

    zeta_f = float(zeta)
    r_f = float(r)

    warnings: list[str] = []
    _check_resonance(r_f, zeta_f, warnings)

    num = 1.0 + (2.0 * zeta_f * r_f) ** 2
    denom = (1.0 - r_f ** 2) ** 2 + (2.0 * zeta_f * r_f) ** 2

    if denom <= 0:
        return _err("Denominator is zero (undamped resonance); TR is unbounded.")

    TR = math.sqrt(num / denom)
    TR_dB = 20.0 * math.log10(TR) if TR > 0 else float("-inf")

    if r_f < math.sqrt(2.0):
        warnings.append(
            f"r={r_f:.4f} < √2 ≈ 1.414: transmissibility TR={TR:.4f} >= 1 "
            "(amplification region; not in isolation zone)."
        )

    return {
        "ok": True,
        "TR": TR,
        "TR_dB": TR_dB,
        "r": r_f,
        "zeta": zeta_f,
        "isolating": TR < 1.0,
        "warnings": warnings,
    }


# ===========================================================================
# 8. SDOF rotating unbalance response
# ===========================================================================

def sdof_rotating_unbalance(
    m: float,
    k: float,
    c: float,
    m_u: float,
    e: float,
    omega: float,
) -> dict:
    """
    Steady-state response amplitude for a rotating-unbalance excitation.

    Parameters
    ----------
    m : float
        Total mass of the machine including unbalance mass (kg). Must be > 0.
    k : float
        Support stiffness (N/m). Must be > 0.
    c : float
        Viscous damping (N·s/m). Must be >= 0.
    m_u : float
        Unbalance mass (kg). Must be > 0.
    e : float
        Eccentricity (m). Must be > 0.
    omega : float
        Excitation angular frequency (rad/s). Must be > 0.

    Returns
    -------
    dict
        ok          : True
        X_m         : steady-state amplitude X (m)
        MX_over_mue : non-dimensional amplitude MX / (m_u · e) = M · r²
        r           : frequency ratio ω / ωn
        zeta        : damping ratio
        omega_n     : undamped natural frequency (rad/s)
        warnings    : list

    Formula
    -------
    r = ω / ωn
    X = (m_u e / m) × r² / √[(1 - r²)² + (2ζr)²]

    Non-dimensional form: MX / (m_u e) = r² / √[(1-r²)² + (2ζr)²]

    References
    ----------
    Rao §3-7; Inman §2.3
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("k", k)
    if err:
        return _err(err)
    err = _guard_nonneg("c", c)
    if err:
        return _err(err)
    err = _guard_positive("m_u", m_u)
    if err:
        return _err(err)
    err = _guard_positive("e", e)
    if err:
        return _err(err)
    err = _guard_positive("omega", omega)
    if err:
        return _err(err)

    m_f = float(m)
    k_f = float(k)
    c_f = float(c)
    m_u_f = float(m_u)
    e_f = float(e)
    omega_f = float(omega)

    omega_n = math.sqrt(k_f / m_f)
    c_cr = 2.0 * math.sqrt(k_f * m_f)
    zeta = c_f / c_cr if c_cr > 0 else 0.0
    r = omega_f / omega_n

    warnings: list[str] = []
    _check_resonance(r, zeta, warnings)

    denom_sq = (1.0 - r ** 2) ** 2 + (2.0 * zeta * r) ** 2
    if denom_sq <= 0:
        return _err("Denominator is zero (undamped resonance); amplitude is unbounded.")

    nondim = r ** 2 / math.sqrt(denom_sq)
    X = (m_u_f * e_f / m_f) * nondim

    return {
        "ok": True,
        "X_m": X,
        "MX_over_mue": nondim,
        "r": r,
        "zeta": zeta,
        "omega_n": omega_n,
        "warnings": warnings,
    }


# ===========================================================================
# 9. 2-DOF undamped eigenfrequencies & mode shapes
# ===========================================================================

def dof2_eigen(
    m1: float,
    m2: float,
    k1: float,
    k2: float,
    k3: float = 0.0,
) -> dict:
    """
    Natural frequencies and mode shapes for an undamped 2-DOF spring-mass system.

    The system is:
        m1 ẍ1 + (k1 + k2) x1 - k2 x2 = 0
        m2 ẍ2 - k2 x1 + (k2 + k3) x2 = 0

    i.e., a chain of three springs k1, k2, k3 with two masses m1, m2.
    k3 = 0 gives an ungrounded second mass (free-free chain).

    Parameters
    ----------
    m1 : float
        First mass (kg). Must be > 0.
    m2 : float
        Second mass (kg). Must be > 0.
    k1 : float
        Stiffness of spring 1 (ground to m1) (N/m). Must be > 0.
    k2 : float
        Stiffness of coupling spring (m1 to m2) (N/m). Must be > 0.
    k3 : float
        Stiffness of spring 3 (m2 to ground) (N/m). Must be >= 0.
        Default 0 (m2 end is free).

    Returns
    -------
    dict
        ok              : True
        omega_1         : first natural frequency (rad/s)
        omega_2         : second natural frequency (rad/s)
        fn_1_hz         : first natural frequency (Hz)
        fn_2_hz         : second natural frequency (Hz)
        mode_shape_1    : [1.0, u2_1] normalised to first DOF = 1
        mode_shape_2    : [1.0, u2_2] normalised to first DOF = 1
        warnings        : list

    Method
    ------
    The characteristic equation det(K - ω²M) = 0 reduces to a quadratic
    in λ = ω² (2×2 system, exact closed form):

        m1·m2·λ² - [(k1+k2)m2 + (k2+k3)m1]·λ + [(k1+k2)(k2+k3) - k2²] = 0

    Solved by the quadratic formula.  Mode shapes from the eigenvectors.

    References
    ----------
    Rao §5-3; Inman §4.1
    """
    err = _guard_positive("m1", m1)
    if err:
        return _err(err)
    err = _guard_positive("m2", m2)
    if err:
        return _err(err)
    err = _guard_positive("k1", k1)
    if err:
        return _err(err)
    err = _guard_positive("k2", k2)
    if err:
        return _err(err)
    err = _guard_nonneg("k3", k3)
    if err:
        return _err(err)

    m1_f = float(m1)
    m2_f = float(m2)
    k1_f = float(k1)
    k2_f = float(k2)
    k3_f = float(k3)

    # Stiffness matrix entries
    K11 = k1_f + k2_f
    K12 = -k2_f
    K22 = k2_f + k3_f

    # Characteristic equation: m1 m2 λ² - [K11 m2 + K22 m1] λ + [K11 K22 - K12²] = 0
    a_coeff = m1_f * m2_f
    b_coeff = -(K11 * m2_f + K22 * m1_f)
    c_coeff = K11 * K22 - K12 ** 2

    disc = b_coeff ** 2 - 4.0 * a_coeff * c_coeff
    if disc < 0:
        return _err(
            f"Discriminant is negative ({disc:.6g}); system has complex eigenvalues "
            "(check stiffness values)."
        )

    sqrt_disc = math.sqrt(disc)
    lam1 = (-b_coeff - sqrt_disc) / (2.0 * a_coeff)
    lam2 = (-b_coeff + sqrt_disc) / (2.0 * a_coeff)

    if lam1 < 0 or lam2 < 0:
        return _err(
            f"Negative eigenvalue(s): λ1={lam1:.6g}, λ2={lam2:.6g}. "
            "Check that stiffnesses are non-negative and masses are positive."
        )

    omega_1 = math.sqrt(lam1)
    omega_2 = math.sqrt(lam2)

    # Mode shapes: from (K - λ M) u = 0 → u2/u1 = (K11 - λ m1) / k2
    def _mode_shape_ratio(lam: float) -> float:
        num = K11 - lam * m1_f
        # u2/u1 = num / k2  (from first row: K11 u1 + K12 u2 = λ m1 u1)
        # K12 = -k2, so k2 u2 = (K11 - λ m1) u1
        return num / k2_f

    u2_1 = _mode_shape_ratio(lam1)
    u2_2 = _mode_shape_ratio(lam2)

    warnings: list[str] = []

    return {
        "ok": True,
        "omega_1": omega_1,
        "omega_2": omega_2,
        "fn_1_hz": omega_1 / (2.0 * math.pi),
        "fn_2_hz": omega_2 / (2.0 * math.pi),
        "mode_shape_1": [1.0, u2_1],
        "mode_shape_2": [1.0, u2_2],
        "warnings": warnings,
    }


# ===========================================================================
# 10. Euler-Bernoulli beam natural frequencies
# ===========================================================================

def beam_natural_frequency(
    mode: int,
    length_m: float,
    mass_per_m: float,
    E: float,
    I: float,
    bc: str = "simply-supported",
) -> dict:
    """
    Euler-Bernoulli beam natural frequencies for cantilever or simply-supported
    boundary conditions.

    Parameters
    ----------
    mode : int
        Mode number (1 = fundamental, 2 = second, ...). Must be >= 1.
        For cantilever: modes 1–4 use tabulated βL roots; mode > 4 uses
        the asymptotic formula βL ≈ (2n-1)π/2.
        For simply-supported: βL = n·π (exact for all n).
    length_m : float
        Beam length (m). Must be > 0.
    mass_per_m : float
        Mass per unit length μ = ρA (kg/m). Must be > 0.
    E : float
        Young's modulus (Pa). Must be > 0.
    I : float
        Second moment of area (m⁴). Must be > 0.
    bc : str
        Boundary condition:
          "simply-supported" (default) — pinned-pinned; βL = n·π
          "cantilever"                  — clamped-free; tabulated βL roots

    Returns
    -------
    dict
        ok          : True
        omega_n     : natural frequency (rad/s)
        fn_hz       : natural frequency (Hz)
        beta_L      : βL eigenvalue used
        mode        : mode number
        bc          : boundary condition label
        EI          : flexural rigidity EI (N·m²)
        warnings    : list

    Formula
    -------
    ωn = (βL)² × √(EI / (μ L⁴))

    where βL is the eigenvalue of the characteristic equation for the
    given boundary condition and mode number.

    References
    ----------
    Rao §8-6; Thomson §8.6
    """
    try:
        mode_i = int(mode)
    except (TypeError, ValueError):
        return _err(f"mode must be a positive integer, got {mode!r}")
    if mode_i < 1:
        return _err(f"mode must be >= 1, got {mode_i}")

    err = _guard_positive("length_m", length_m)
    if err:
        return _err(err)
    err = _guard_positive("mass_per_m", mass_per_m)
    if err:
        return _err(err)
    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_positive("I", I)
    if err:
        return _err(err)

    bc_clean = str(bc).strip().lower().replace("-", "").replace("_", "").replace(" ", "")

    if bc_clean in ("simplysupported", "pinnedpinned", "pinned", "ss"):
        beta_L = mode_i * math.pi
        bc_label = "simply-supported"
    elif bc_clean in ("cantilever", "clampedfree", "fixed", "cf"):
        if mode_i in _BEAM_CANTILEVER_BL:
            beta_L = _BEAM_CANTILEVER_BL[mode_i]
        else:
            # Asymptotic: βL ≈ (2n-1)π/2 for higher modes
            beta_L = (2.0 * mode_i - 1.0) * math.pi / 2.0
        bc_label = "cantilever"
    else:
        return _err(
            f"Unknown bc {bc!r}. Supported: 'simply-supported', 'cantilever'."
        )

    L = float(length_m)
    mu = float(mass_per_m)
    E_f = float(E)
    I_f = float(I)
    EI = E_f * I_f

    # ωn = (βL)² × √(EI / (μ L⁴))
    omega_n = (beta_L ** 2) * math.sqrt(EI / (mu * L ** 4))

    return {
        "ok": True,
        "omega_n": omega_n,
        "fn_hz": omega_n / (2.0 * math.pi),
        "beta_L": beta_L,
        "mode": mode_i,
        "bc": bc_label,
        "EI": EI,
        "warnings": [],
    }


# ===========================================================================
# 11. Shaft whirl — Rayleigh's method
# ===========================================================================

def shaft_whirl_rayleigh(
    lengths_m: list[float],
    masses_kg: list[float],
    E: float,
    I: float,
    span_m: float | None = None,
) -> dict:
    """
    First whirl (lateral) critical speed of a multi-disk shaft by Rayleigh's
    energy method.

    The shaft is modelled as a simply-supported uniform beam with concentrated
    disk masses.  The static deflection under gravity loads is used as the
    assumed mode shape.

    Parameters
    ----------
    lengths_m : list[float]
        Positions along the shaft of each disk, measured from the left bearing
        (m).  All positions must be strictly between 0 and the shaft span L.
    masses_kg : list[float]
        Mass of each disk at the corresponding position (kg).
        Must have the same length as lengths_m.
    E : float
        Young's modulus (Pa). Must be > 0.
    I : float
        Second moment of area of the shaft cross-section (m⁴). Must be > 0.
    span_m : float | None
        Total shaft span between bearings (m).  If None (default), the span is
        taken as the maximum disk position in lengths_m — which requires at
        least one disk to define the span.  Provide span_m explicitly when all
        disk positions are strictly interior and the bearing-to-bearing distance
        is larger than max(lengths_m).

    Returns
    -------
    dict
        ok              : True
        omega_cr        : first critical speed (rad/s) — Rayleigh upper bound
        n_cr_rpm        : first critical speed (rpm)
        deflections_m   : list of static deflections yi at each disk position (m)
        EI              : flexural rigidity EI (N·m²)
        warnings        : list

    Method (Rayleigh quotient for simply-supported beam)
    ------------------------------------------------------
    For a simply-supported uniform beam of span L, the static deflection at
    position a from the left support due to a concentrated load F at position a:

        y(a, a) = F a (L - a) [2L² - (L-a)² - a²] / (6 E I L)
                = F a² (L - a)² / (3 E I L)

    For multiple loads, superposition applies.

    Rayleigh frequency:

        ω² = g Σ(mi yi) / Σ(mi yi²)

    where g = 9.81 m/s² and yi is the total deflection at position i under all
    disk weights.

    References
    ----------
    Genta §3.2; Rao §8-8; Thomson §4.5 (Rayleigh's method)
    """
    # Validate lists
    try:
        pos_list = [float(x) for x in lengths_m]
        mass_list = [float(x) for x in masses_kg]
    except (TypeError, ValueError) as exc:
        return _err(f"lengths_m and masses_kg must be lists of numbers: {exc}")

    if len(pos_list) == 0:
        return _err("lengths_m must not be empty.")
    if len(pos_list) != len(mass_list):
        return _err(
            f"lengths_m and masses_kg must have the same length "
            f"(got {len(pos_list)} vs {len(mass_list)})."
        )

    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_positive("I", I)
    if err:
        return _err(err)

    for i, m_i in enumerate(mass_list):
        if m_i <= 0:
            return _err(f"masses_kg[{i}] must be > 0, got {m_i}")

    E_f = float(E)
    I_f = float(I)
    EI = E_f * I_f

    # Determine shaft span
    if span_m is not None:
        err_s = _guard_positive("span_m", span_m)
        if err_s:
            return _err(err_s)
        L = float(span_m)
    else:
        L = max(pos_list)  # fallback: span = farthest disk position
    if L <= 0:
        return _err("Shaft span must be > 0.")

    for i, a_i in enumerate(pos_list):
        if a_i <= 0 or a_i >= L:
            return _err(
                f"lengths_m[{i}]={a_i} must be strictly between 0 and "
                f"shaft span L={L}."
            )

    warnings: list[str] = []

    # Compute deflection at each disk position using superposition.
    # For a simply-supported beam of span L, deflection at x due to load W at a:
    #   y(x, a) = W b x (L² - b² - x²) / (6 E I L)  for x <= a
    #   where b = L - a
    # By symmetry for x >= a swap a and x then use above.
    # Equivalently: y(a, a) = W a² b² / (3 E I L)  for the point of load application.
    # For x != a we use the general formula.

    g = 9.80665  # m/s²

    def _deflection_at_x_due_to_load(x: float, a: float, W: float) -> float:
        """
        Static deflection at x due to concentrated load W at position a
        on a simply-supported beam of span L.
        """
        b = L - a
        EIL6 = 6.0 * EI * L
        if x <= a:
            return W * b * x * (L ** 2 - b ** 2 - x ** 2) / EIL6
        else:
            # Swap: load at a, evaluation at x > a → use symmetry: y(x, a) = y(a, x)
            # General form for x > a: y = W a (L-x) (2Lx - x² - a²) / (6EIL)
            return W * a * (L - x) * (2.0 * L * x - x ** 2 - a ** 2) / EIL6

    # Static deflections at each disk position under all disk weights
    deflections = []
    for i, (x_i, m_i) in enumerate(zip(pos_list, mass_list)):
        W_i = m_i * g  # weight
        # Sum contributions from all loads
        y_i = sum(
            _deflection_at_x_due_to_load(x_i, a_j, mass_list[j] * g)
            for j, a_j in enumerate(pos_list)
        )
        deflections.append(y_i)

    # Rayleigh quotient: ω² = g Σ(mi yi) / Σ(mi yi²)
    sum_miy = sum(m * y for m, y in zip(mass_list, deflections))
    sum_miyi2 = sum(m * y ** 2 for m, y in zip(mass_list, deflections))

    if sum_miyi2 <= 0:
        return _err("Σ(mi yi²) ≤ 0; check inputs.")
    if sum_miy <= 0:
        return _err("Σ(mi yi) ≤ 0; deflections must be positive.")

    omega_cr = math.sqrt(g * sum_miy / sum_miyi2)
    n_cr_rpm = omega_cr * 60.0 / (2.0 * math.pi)

    return {
        "ok": True,
        "omega_cr": omega_cr,
        "n_cr_rpm": n_cr_rpm,
        "deflections_m": deflections,
        "EI": EI,
        "warnings": warnings,
    }


# ===========================================================================
# 12. Isolation: required isolator stiffness
# ===========================================================================

def isolator_stiffness(
    m: float,
    omega_exc: float,
    TR_target: float,
) -> dict:
    """
    Required undamped isolator stiffness for a target transmissibility TR.

    For an undamped isolator (ζ = 0) operating above resonance (r > √2),
    the transmissibility is:

        TR = 1 / (r² - 1)    for r > √2  (isolation zone)

    Solving for r:  r² = 1 + 1/TR  →  r = √(1 + 1/TR)
    Then:           ωn = ω_exc / r   →  k = m ωn²

    Parameters
    ----------
    m : float
        Isolated mass (kg). Must be > 0.
    omega_exc : float
        Excitation angular frequency (rad/s). Must be > 0.
    TR_target : float
        Target transmissibility (dimensionless, 0 < TR < 1 for isolation).
        Must be > 0 and < 1.

    Returns
    -------
    dict
        ok          : True
        k_N_per_m   : required isolator stiffness (N/m)
        omega_n     : required system natural frequency (rad/s)
        fn_hz       : required natural frequency (Hz)
        r           : frequency ratio ω_exc / ωn
        TR_actual   : actual transmissibility at this r and ζ=0
        static_deflection_m : static deflection under mass weight = mg/k (m)
        warnings    : list

    References
    ----------
    Rao §3-8; Inman §2.5
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("omega_exc", omega_exc)
    if err:
        return _err(err)

    try:
        TR_f = float(TR_target)
    except (TypeError, ValueError):
        return _err(f"TR_target must be a number, got {TR_target!r}")

    if not math.isfinite(TR_f):
        return _err(f"TR_target must be finite, got {TR_f}")
    if TR_f <= 0:
        return _err(f"TR_target must be > 0, got {TR_f}")
    if TR_f >= 1.0:
        return _err(
            f"TR_target must be < 1.0 for isolation (got {TR_f}); "
            "use values such as 0.1 for 90% isolation."
        )

    m_f = float(m)
    omega_exc_f = float(omega_exc)

    # r = √(1 + 1/TR)  (from TR = 1/(r²-1) → r² = 1 + 1/TR)
    r_sq = 1.0 + 1.0 / TR_f
    r = math.sqrt(r_sq)

    # ωn = ω_exc / r
    omega_n = omega_exc_f / r
    k = m_f * omega_n ** 2

    # Verify: TR_actual = 1/(r²-1) for ζ=0
    TR_actual = 1.0 / (r_sq - 1.0)

    # Static deflection
    g = 9.80665
    delta_st = m_f * g / k if k > 0 else float("inf")

    warnings: list[str] = []
    if r < math.sqrt(2.0) + 0.05:
        warnings.append(
            f"r={r:.4f} is close to √2: verify isolator works in isolation zone."
        )

    return {
        "ok": True,
        "k_N_per_m": k,
        "omega_n": omega_n,
        "fn_hz": omega_n / (2.0 * math.pi),
        "r": r,
        "TR_actual": TR_actual,
        "static_deflection_m": delta_st,
        "warnings": warnings,
    }
