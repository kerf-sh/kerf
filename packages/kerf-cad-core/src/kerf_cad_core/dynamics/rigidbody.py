"""
kerf_cad_core.dynamics.rigidbody — pure-Python rigid-body dynamics formulas.

Implements functions covering:

  PARTICLE & RIGID-BODY KINEMATICS:
    rectilinear_kinematics(v0, a, t, s0)        — s, v, a for constant acceleration
    projectile_motion(v0, theta_deg, t, g)       — x, y, vx, vy for projectile
    rotational_kinematics(omega0, alpha, t)       — omega, theta for const. angular accel.
    relative_motion_velocity(v_A, v_B_A)         — absolute velocity via relative motion

  NEWTON-EULER EQUATIONS OF MOTION:
    newton_translation(F_net, m)                 — acceleration from ΣF = ma
    euler_rotation(M_net, I, alpha0)             — angular acceleration from ΣM = I·α
    general_plane_motion(F_x, F_y, M_G, m, I_G) — combined translation + rotation

  WORK-ENERGY & POWER:
    kinetic_energy(m, v, I, omega)               — translational + rotational KE
    work_energy_theorem(KE1, KE2, W_nc)          — energy balance check
    spring_potential_energy(k, x)                — V_s = ½ k x²
    power_from_torque(M, omega)                  — P = M·ω
    power_from_force(F, v)                       — P = F·v

  IMPULSE-MOMENTUM:
    linear_impulse(F, dt, mv1)                   — mv2 from impulse-momentum
    angular_impulse(M, dt, L1)                   — L2 from angular impulse-momentum

  IMPACT:
    direct_impact(m1, v1, m2, v2, e)             — post-impact velocities (central)
    oblique_impact(m1, v1x, v1y, m2, v2x, v2y, e) — 2-D oblique impact

  MASS MOMENT OF INERTIA:
    moi_solid_cylinder(m, r)                     — I = ½ m r²
    moi_hollow_cylinder(m, r_o, r_i)             — I = ½ m (r_o² + r_i²)
    moi_solid_sphere(m, r)                       — I = 2/5 m r²
    moi_thin_rod(m, L, axis)                     — about centroid or end
    moi_rectangular_plate(m, a, b)               — I = 1/12 m (a² + b²)
    parallel_axis(I_cm, m, d)                    — Steiner's theorem

  FLYWHEEL SIZING:
    flywheel_sizing(E_fluctuation, omega_mean, Cs) — required I from energy fluctuation
    flywheel_rim(I_required, rho, r_mean, b)      — rim cross-section from I

  ROTATING-MASS BALANCING:
    static_balance(masses, radii, angles_deg)     — resultant unbalance force + correction
    dynamic_balance_two_plane(masses, radii, angles_deg, axial_positions,
                               plane_a_pos, plane_b_pos)
                                                  — two-plane balance correction masses
    residual_unbalance(m, e)                      — U = m·e (g·mm)
    iso1940_grade(U, m_rotor, omega, grade)       — ISO 1940 grade check

  RECIPROCATING BALANCE:
    shaking_force_primary(m_recip, r, omega, theta_deg)   — primary shaking force
    shaking_force_secondary(m_recip, r, omega, n, theta_deg) — secondary shaking force

  GYROSCOPIC REACTION:
    gyroscopic_moment(I_spin, omega_spin, omega_precession) — M_gyro = I·ωs × ωp

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Out-of-tolerance conditions are flagged in the
"warnings" list via the Python `warnings` module — never as exceptions.

Units
-----
  lengths     — metres (m) unless noted in mm
  masses      — kilograms (kg)
  forces      — Newtons (N)
  moments     — Newton-metres (N·m)
  angles      — degrees (user-facing) / radians (internal)
  angular vel — rad/s
  time        — seconds (s)
  energy      — Joules (J)
  power       — Watts (W)
  inertia     — kg·m²
  unbalance   — g·mm (ISO 1940 convention)

References
----------
Hibbeler, R.C. "Engineering Mechanics: Dynamics", 14th ed. (Pearson)
Beer, F.P. & Johnston, E.R. "Vector Mechanics for Engineers: Dynamics",
    12th ed. (McGraw-Hill)
ISO 1940-1:2003 — Mechanical vibration — Balance quality requirements
    for rotors in a constant (rigid) state

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_mod
from typing import Any
from kerf_cad_core._guards import _err, _guard_finite, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _warn(msg: str, warnings_list: list) -> None:
    warnings_list.append(msg)
    _warnings_mod.warn(msg, UserWarning, stacklevel=4)


# ===========================================================================
# 1. PARTICLE / RIGID-BODY KINEMATICS
# ===========================================================================

def rectilinear_kinematics(
    v0: float,
    a: float,
    t: float,
    s0: float = 0.0,
) -> dict:
    """
    Constant-acceleration rectilinear kinematics.

    Parameters
    ----------
    v0 : float
        Initial velocity (m/s). Any finite value.
    a : float
        Constant acceleration (m/s²). Any finite value.
    t : float
        Time elapsed (s). Must be >= 0.
    s0 : float
        Initial position (m). Default 0.

    Returns
    -------
    dict
        ok      : True
        s       : position s(t) = s0 + v0·t + ½·a·t² (m)
        v       : velocity v(t) = v0 + a·t (m/s)
        v_sq    : v² = v0² + 2·a·(s - s0)  (m²/s²)
        warnings : []

    References
    ----------
    Hibbeler §12-2; Beer §11.2
    """
    for name, val in (("v0", v0), ("a", a), ("s0", s0)):
        err = _guard_finite(name, val)
        if err:
            return _err(err)
    err = _guard_nonneg("t", t)
    if err:
        return _err(err)

    v0_f = float(v0)
    a_f = float(a)
    t_f = float(t)
    s0_f = float(s0)

    s = s0_f + v0_f * t_f + 0.5 * a_f * t_f ** 2
    v = v0_f + a_f * t_f
    v_sq = v0_f ** 2 + 2.0 * a_f * (s - s0_f)

    return {"ok": True, "s": s, "v": v, "v_sq": v_sq, "warnings": []}


def projectile_motion(
    v0: float,
    theta_deg: float,
    t: float,
    g: float = 9.80665,
) -> dict:
    """
    Projectile motion (no air resistance).

    Parameters
    ----------
    v0 : float
        Initial speed (m/s). Must be > 0.
    theta_deg : float
        Launch angle above horizontal (degrees). -90 <= theta <= 90.
    t : float
        Time elapsed (s). Must be >= 0.
    g : float
        Gravitational acceleration (m/s²). Default 9.80665.

    Returns
    -------
    dict
        ok      : True
        x       : horizontal position (m)
        y       : vertical position (m)
        vx      : horizontal velocity (m/s)
        vy      : vertical velocity (m/s)
        v_mag   : speed at time t (m/s)
        t_peak  : time to peak (s)
        range_m : horizontal range for symmetric landing (m)
        warnings : []

    References
    ----------
    Hibbeler §12-6; Beer §11.3
    """
    err = _guard_positive("v0", v0)
    if err:
        return _err(err)
    err = _guard_nonneg("t", t)
    if err:
        return _err(err)
    err = _guard_positive("g", g)
    if err:
        return _err(err)

    try:
        theta_f = float(theta_deg)
    except (TypeError, ValueError):
        return _err(f"theta_deg must be a number, got {theta_deg!r}")
    if not (-90.0 <= theta_f <= 90.0):
        return _err(f"theta_deg must be between -90 and 90, got {theta_f}")

    v0_f = float(v0)
    t_f = float(t)
    g_f = float(g)
    theta_rad = math.radians(theta_f)

    vx = v0_f * math.cos(theta_rad)
    vy0 = v0_f * math.sin(theta_rad)

    x = vx * t_f
    y = vy0 * t_f - 0.5 * g_f * t_f ** 2
    vy = vy0 - g_f * t_f
    v_mag = math.hypot(vx, vy)

    t_peak = vy0 / g_f if g_f > 0 else 0.0
    range_m = 2.0 * vx * t_peak  # symmetric parabolic range

    return {
        "ok": True,
        "x": x,
        "y": y,
        "vx": vx,
        "vy": vy,
        "v_mag": v_mag,
        "t_peak": t_peak,
        "range_m": range_m,
        "warnings": [],
    }


def rotational_kinematics(
    omega0: float,
    alpha: float,
    t: float,
    theta0: float = 0.0,
) -> dict:
    """
    Constant angular-acceleration rotational kinematics.

    Parameters
    ----------
    omega0 : float
        Initial angular velocity (rad/s). Any finite value.
    alpha : float
        Constant angular acceleration (rad/s²). Any finite value.
    t : float
        Time elapsed (s). Must be >= 0.
    theta0 : float
        Initial angular position (rad). Default 0.

    Returns
    -------
    dict
        ok      : True
        theta   : angular position θ(t) = θ0 + ω0·t + ½·α·t² (rad)
        omega   : angular velocity ω(t) = ω0 + α·t (rad/s)
        omega_sq: ω² = ω0² + 2·α·(θ - θ0)  (rad²/s²)
        warnings : []

    References
    ----------
    Hibbeler §16-3; Beer §15.2
    """
    for name, val in (("omega0", omega0), ("alpha", alpha), ("theta0", theta0)):
        err = _guard_finite(name, val)
        if err:
            return _err(err)
    err = _guard_nonneg("t", t)
    if err:
        return _err(err)

    omega0_f = float(omega0)
    alpha_f = float(alpha)
    t_f = float(t)
    theta0_f = float(theta0)

    theta = theta0_f + omega0_f * t_f + 0.5 * alpha_f * t_f ** 2
    omega = omega0_f + alpha_f * t_f
    omega_sq = omega0_f ** 2 + 2.0 * alpha_f * (theta - theta0_f)

    return {"ok": True, "theta": theta, "omega": omega, "omega_sq": omega_sq, "warnings": []}


def relative_motion_velocity(
    v_A: list[float],
    v_B_A: list[float],
) -> dict:
    """
    Absolute velocity of B from relative motion: v_B = v_A + v_B/A.

    Parameters
    ----------
    v_A : [vx, vy] or [vx, vy, vz]
        Absolute velocity of reference point A (m/s).
    v_B_A : [vx, vy] or [vx, vy, vz]
        Velocity of B relative to A (m/s).

    Returns
    -------
    dict
        ok      : True
        v_B     : absolute velocity of B (m/s)
        v_mag   : magnitude of v_B (m/s)
        warnings : []

    References
    ----------
    Hibbeler §16-5; Beer §15.5
    """
    try:
        vA = [float(x) for x in v_A]
        vBA = [float(x) for x in v_B_A]
    except (TypeError, ValueError) as exc:
        return _err(f"v_A and v_B_A must be lists of numbers: {exc}")

    if len(vA) not in (2, 3):
        return _err("v_A must have 2 or 3 components.")
    if len(vBA) not in (2, 3):
        return _err("v_B_A must have 2 or 3 components.")
    if len(vA) != len(vBA):
        return _err("v_A and v_B_A must have the same number of components.")

    vB = [a + b for a, b in zip(vA, vBA)]
    v_mag = math.sqrt(sum(c ** 2 for c in vB))

    return {"ok": True, "v_B": vB, "v_mag": v_mag, "warnings": []}


# ===========================================================================
# 2. NEWTON-EULER EQUATIONS OF MOTION
# ===========================================================================

def newton_translation(
    F_net: float,
    m: float,
) -> dict:
    """
    Linear acceleration from Newton's second law: ΣF = m·a.

    Parameters
    ----------
    F_net : float
        Net force (N). Any finite value.
    m : float
        Mass (kg). Must be > 0.

    Returns
    -------
    dict
        ok  : True
        a   : acceleration (m/s²)
        warnings : []

    References
    ----------
    Hibbeler §13-2; Beer §12.2
    """
    err = _guard_finite("F_net", F_net)
    if err:
        return _err(err)
    err = _guard_positive("m", m)
    if err:
        return _err(err)

    a = float(F_net) / float(m)
    return {"ok": True, "a": a, "warnings": []}


def euler_rotation(
    M_net: float,
    I: float,
) -> dict:
    """
    Angular acceleration from Euler's equation: ΣM = I·α.

    Parameters
    ----------
    M_net : float
        Net moment about axis of rotation (N·m). Any finite value.
    I : float
        Mass moment of inertia about rotation axis (kg·m²). Must be > 0.

    Returns
    -------
    dict
        ok    : True
        alpha : angular acceleration (rad/s²)
        warnings : []

    References
    ----------
    Hibbeler §17-3; Beer §16.3
    """
    err = _guard_finite("M_net", M_net)
    if err:
        return _err(err)
    err = _guard_positive("I", I)
    if err:
        return _err(err)

    alpha = float(M_net) / float(I)
    return {"ok": True, "alpha": alpha, "warnings": []}


def general_plane_motion(
    F_x: float,
    F_y: float,
    M_G: float,
    m: float,
    I_G: float,
) -> dict:
    """
    General plane motion: simultaneous translation and rotation.

    Equations:
        ΣFx = m·ax
        ΣFy = m·ay
        ΣM_G = I_G·α

    Parameters
    ----------
    F_x : float
        Net force in x-direction (N).
    F_y : float
        Net force in y-direction (N).
    M_G : float
        Net moment about mass centre G (N·m).
    m : float
        Mass (kg). Must be > 0.
    I_G : float
        Mass moment of inertia about G (kg·m²). Must be > 0.

    Returns
    -------
    dict
        ok    : True
        ax    : linear acceleration in x (m/s²)
        ay    : linear acceleration in y (m/s²)
        alpha : angular acceleration (rad/s²)
        warnings : []

    References
    ----------
    Hibbeler §17-5; Beer §16.2
    """
    for name, val in (("F_x", F_x), ("F_y", F_y), ("M_G", M_G)):
        err = _guard_finite(name, val)
        if err:
            return _err(err)
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("I_G", I_G)
    if err:
        return _err(err)

    ax = float(F_x) / float(m)
    ay = float(F_y) / float(m)
    alpha = float(M_G) / float(I_G)

    return {"ok": True, "ax": ax, "ay": ay, "alpha": alpha, "warnings": []}


# ===========================================================================
# 3. WORK-ENERGY & POWER
# ===========================================================================

def kinetic_energy(
    m: float,
    v: float,
    I: float = 0.0,
    omega: float = 0.0,
) -> dict:
    """
    Total kinetic energy: translational + rotational.

    T = ½·m·v² + ½·I·ω²

    Parameters
    ----------
    m : float
        Mass (kg). Must be > 0.
    v : float
        Speed (m/s). Must be >= 0.
    I : float
        Mass moment of inertia (kg·m²). Default 0. Must be >= 0.
    omega : float
        Angular velocity (rad/s). Default 0. Must be >= 0.

    Returns
    -------
    dict
        ok          : True
        T_trans     : translational KE (J)
        T_rot       : rotational KE (J)
        T_total     : total KE (J)
        warnings    : []

    References
    ----------
    Hibbeler §18-2; Beer §17.1
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_nonneg("v", v)
    if err:
        return _err(err)
    err = _guard_nonneg("I", I)
    if err:
        return _err(err)
    err = _guard_nonneg("omega", omega)
    if err:
        return _err(err)

    T_trans = 0.5 * float(m) * float(v) ** 2
    T_rot = 0.5 * float(I) * float(omega) ** 2
    T_total = T_trans + T_rot

    return {"ok": True, "T_trans": T_trans, "T_rot": T_rot, "T_total": T_total, "warnings": []}


def work_energy_theorem(
    KE1: float,
    KE2: float,
    W_nc: float,
) -> dict:
    """
    Work-energy principle: T1 + W_nc = T2.

    Checks energy balance; returns residual (should be ≈ 0).

    Parameters
    ----------
    KE1 : float
        Initial kinetic energy (J). Must be >= 0.
    KE2 : float
        Final kinetic energy (J). Must be >= 0.
    W_nc : float
        Net work done by all non-conservative forces/couples (J).
        Gravity and spring work are conservative and should be
        included in a separate potential energy bookkeeping.

    Returns
    -------
    dict
        ok          : True
        balance     : T2 - (T1 + W_nc); should be 0
        satisfied   : True if |balance| < 1e-9
        warnings    : []

    References
    ----------
    Hibbeler §18-3; Beer §17.2
    """
    for name, val in (("W_nc", W_nc),):
        err = _guard_finite(name, val)
        if err:
            return _err(err)
    err = _guard_nonneg("KE1", KE1)
    if err:
        return _err(err)
    err = _guard_nonneg("KE2", KE2)
    if err:
        return _err(err)

    balance = float(KE2) - (float(KE1) + float(W_nc))
    return {"ok": True, "balance": balance, "satisfied": abs(balance) < 1e-9, "warnings": []}


def spring_potential_energy(
    k: float,
    x: float,
) -> dict:
    """
    Spring potential energy: V_s = ½·k·x².

    Parameters
    ----------
    k : float
        Spring stiffness (N/m). Must be > 0.
    x : float
        Spring deformation from natural length (m). Any finite value.

    Returns
    -------
    dict
        ok  : True
        V_s : spring potential energy (J)
        warnings : []

    References
    ----------
    Hibbeler §18-4
    """
    err = _guard_positive("k", k)
    if err:
        return _err(err)
    err = _guard_finite("x", x)
    if err:
        return _err(err)

    V_s = 0.5 * float(k) * float(x) ** 2
    return {"ok": True, "V_s": V_s, "warnings": []}


def power_from_torque(
    M: float,
    omega: float,
) -> dict:
    """
    Mechanical power from torque and angular velocity: P = M·ω.

    Parameters
    ----------
    M : float
        Torque (N·m). Any finite value.
    omega : float
        Angular velocity (rad/s). Any finite value.

    Returns
    -------
    dict
        ok  : True
        P_W : power (W)
        warnings : []

    References
    ----------
    Hibbeler §18-5; Beer §17.4
    """
    err = _guard_finite("M", M)
    if err:
        return _err(err)
    err = _guard_finite("omega", omega)
    if err:
        return _err(err)

    P_W = float(M) * float(omega)
    return {"ok": True, "P_W": P_W, "warnings": []}


def power_from_force(
    F: float,
    v: float,
) -> dict:
    """
    Mechanical power from force and velocity: P = F·v.

    Parameters
    ----------
    F : float
        Force (N). Any finite value.
    v : float
        Velocity (m/s). Any finite value.

    Returns
    -------
    dict
        ok  : True
        P_W : power (W)
        warnings : []

    References
    ----------
    Hibbeler §14-4; Beer §13.5
    """
    err = _guard_finite("F", F)
    if err:
        return _err(err)
    err = _guard_finite("v", v)
    if err:
        return _err(err)

    P_W = float(F) * float(v)
    return {"ok": True, "P_W": P_W, "warnings": []}


# ===========================================================================
# 4. IMPULSE-MOMENTUM
# ===========================================================================

def linear_impulse(
    F: float,
    dt: float,
    mv1: float = 0.0,
) -> dict:
    """
    Linear impulse-momentum: m·v2 = m·v1 + F·Δt.

    Parameters
    ----------
    F : float
        Average net force (N). Any finite value.
    dt : float
        Time interval (s). Must be > 0.
    mv1 : float
        Initial linear momentum m·v1 (kg·m/s). Default 0.

    Returns
    -------
    dict
        ok      : True
        impulse : F·Δt (N·s)
        mv2     : final momentum (kg·m/s)
        warnings : []

    References
    ----------
    Hibbeler §15-1; Beer §13.3
    """
    err = _guard_finite("F", F)
    if err:
        return _err(err)
    err = _guard_positive("dt", dt)
    if err:
        return _err(err)
    err = _guard_finite("mv1", mv1)
    if err:
        return _err(err)

    impulse = float(F) * float(dt)
    mv2 = float(mv1) + impulse

    return {"ok": True, "impulse": impulse, "mv2": mv2, "warnings": []}


def angular_impulse(
    M: float,
    dt: float,
    L1: float = 0.0,
) -> dict:
    """
    Angular impulse-momentum: L2 = L1 + M·Δt.

    Parameters
    ----------
    M : float
        Average net moment (N·m). Any finite value.
    dt : float
        Time interval (s). Must be > 0.
    L1 : float
        Initial angular momentum (kg·m²/s). Default 0.

    Returns
    -------
    dict
        ok              : True
        angular_impulse : M·Δt (N·m·s)
        L2              : final angular momentum (kg·m²/s)
        warnings        : []

    References
    ----------
    Hibbeler §19-3; Beer §17.3
    """
    err = _guard_finite("M", M)
    if err:
        return _err(err)
    err = _guard_positive("dt", dt)
    if err:
        return _err(err)
    err = _guard_finite("L1", L1)
    if err:
        return _err(err)

    ang_imp = float(M) * float(dt)
    L2 = float(L1) + ang_imp

    return {"ok": True, "angular_impulse": ang_imp, "L2": L2, "warnings": []}


# ===========================================================================
# 5. IMPACT
# ===========================================================================

def direct_impact(
    m1: float,
    v1: float,
    m2: float,
    v2: float,
    e: float,
) -> dict:
    """
    Direct central impact: post-impact velocities.

    Uses conservation of momentum + coefficient of restitution.

    Parameters
    ----------
    m1 : float
        Mass of body 1 (kg). Must be > 0.
    v1 : float
        Pre-impact velocity of body 1 (m/s, positive = right).
    m2 : float
        Mass of body 2 (kg). Must be > 0.
    v2 : float
        Pre-impact velocity of body 2 (m/s).
    e : float
        Coefficient of restitution [0, 1].
        e = 0: perfectly plastic; e = 1: perfectly elastic.

    Returns
    -------
    dict
        ok      : True
        v1_prime : post-impact velocity of body 1 (m/s)
        v2_prime : post-impact velocity of body 2 (m/s)
        e       : coefficient of restitution used
        energy_loss : kinetic energy lost (J, >= 0)
        warnings : list (flags e outside [0,1])

    References
    ----------
    Hibbeler §15-4; Beer §13.13
    """
    err = _guard_positive("m1", m1)
    if err:
        return _err(err)
    err = _guard_positive("m2", m2)
    if err:
        return _err(err)
    err = _guard_finite("v1", v1)
    if err:
        return _err(err)
    err = _guard_finite("v2", v2)
    if err:
        return _err(err)
    err = _guard_nonneg("e", e)
    if err:
        return _err(err)

    warnings: list[str] = []
    e_f = float(e)
    if e_f > 1.0:
        _warn(
            f"Coefficient of restitution e={e_f} > 1: physically impossible; "
            "clamping to 1.0.",
            warnings,
        )
        e_f = 1.0

    m1_f, m2_f = float(m1), float(m2)
    v1_f, v2_f = float(v1), float(v2)
    M = m1_f + m2_f

    # v1' = [m1 v1 + m2 v2 - m2 e (v1 - v2)] / M
    # v2' = [m1 v1 + m2 v2 + m1 e (v1 - v2)] / M
    sep = v1_f - v2_f
    v1_prime = (m1_f * v1_f + m2_f * v2_f - m2_f * e_f * sep) / M
    v2_prime = (m1_f * v1_f + m2_f * v2_f + m1_f * e_f * sep) / M

    KE_before = 0.5 * m1_f * v1_f ** 2 + 0.5 * m2_f * v2_f ** 2
    KE_after = 0.5 * m1_f * v1_prime ** 2 + 0.5 * m2_f * v2_prime ** 2
    energy_loss = KE_before - KE_after

    return {
        "ok": True,
        "v1_prime": v1_prime,
        "v2_prime": v2_prime,
        "e": e_f,
        "energy_loss": energy_loss,
        "warnings": warnings,
    }


def oblique_impact(
    m1: float,
    v1x: float,
    v1y: float,
    m2: float,
    v2x: float,
    v2y: float,
    e: float,
) -> dict:
    """
    Oblique impact in 2-D. Line of impact is along x-axis.

    Normal (x) components: COR + momentum conservation.
    Tangential (y) components: unchanged (no friction assumed).

    Parameters
    ----------
    m1, m2 : float
        Masses (kg). Must be > 0.
    v1x, v1y : float
        Pre-impact velocity components of body 1 (m/s).
    v2x, v2y : float
        Pre-impact velocity components of body 2 (m/s).
    e : float
        Coefficient of restitution [0, 1].

    Returns
    -------
    dict
        ok      : True
        v1x_prime, v1y_prime : post-impact velocity of body 1 (m/s)
        v2x_prime, v2y_prime : post-impact velocity of body 2 (m/s)
        energy_loss : KE lost (J)
        warnings : list

    References
    ----------
    Hibbeler §15-5; Beer §13.14
    """
    err = _guard_positive("m1", m1)
    if err:
        return _err(err)
    err = _guard_positive("m2", m2)
    if err:
        return _err(err)
    err = _guard_nonneg("e", e)
    if err:
        return _err(err)
    for name, val in (("v1x", v1x), ("v1y", v1y), ("v2x", v2x), ("v2y", v2y)):
        err = _guard_finite(name, val)
        if err:
            return _err(err)

    warnings: list[str] = []
    e_f = float(e)
    if e_f > 1.0:
        _warn(
            f"Coefficient of restitution e={e_f} > 1: physically impossible; "
            "clamping to 1.0.",
            warnings,
        )
        e_f = 1.0

    m1_f, m2_f = float(m1), float(m2)
    v1x_f, v1y_f = float(v1x), float(v1y)
    v2x_f, v2y_f = float(v2x), float(v2y)
    M = m1_f + m2_f

    # Normal (x) direction — apply direct-impact formulas
    sep_x = v1x_f - v2x_f
    v1x_prime = (m1_f * v1x_f + m2_f * v2x_f - m2_f * e_f * sep_x) / M
    v2x_prime = (m1_f * v1x_f + m2_f * v2x_f + m1_f * e_f * sep_x) / M

    # Tangential (y) direction — unchanged
    v1y_prime = v1y_f
    v2y_prime = v2y_f

    KE_before = 0.5 * m1_f * (v1x_f ** 2 + v1y_f ** 2) + 0.5 * m2_f * (v2x_f ** 2 + v2y_f ** 2)
    KE_after = (
        0.5 * m1_f * (v1x_prime ** 2 + v1y_prime ** 2)
        + 0.5 * m2_f * (v2x_prime ** 2 + v2y_prime ** 2)
    )
    energy_loss = KE_before - KE_after

    return {
        "ok": True,
        "v1x_prime": v1x_prime,
        "v1y_prime": v1y_prime,
        "v2x_prime": v2x_prime,
        "v2y_prime": v2y_prime,
        "energy_loss": energy_loss,
        "warnings": warnings,
    }


# ===========================================================================
# 6. MASS MOMENT OF INERTIA
# ===========================================================================

def moi_solid_cylinder(m: float, r: float) -> dict:
    """
    Mass moment of inertia of a solid cylinder about its longitudinal axis.

    I = ½·m·r²

    Parameters
    ----------
    m : float
        Mass (kg). Must be > 0.
    r : float
        Radius (m). Must be > 0.

    Returns
    -------
    dict
        ok  : True
        I   : moment of inertia (kg·m²)
        warnings : []

    References
    ----------
    Hibbeler App. B; Beer App. B
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("r", r)
    if err:
        return _err(err)

    I = 0.5 * float(m) * float(r) ** 2
    return {"ok": True, "I": I, "warnings": []}


def moi_hollow_cylinder(m: float, r_o: float, r_i: float) -> dict:
    """
    Mass moment of inertia of a hollow cylinder about its longitudinal axis.

    I = ½·m·(r_o² + r_i²)

    Parameters
    ----------
    m : float
        Mass (kg). Must be > 0.
    r_o : float
        Outer radius (m). Must be > 0.
    r_i : float
        Inner radius (m). Must be >= 0 and < r_o.

    Returns
    -------
    dict
        ok  : True
        I   : moment of inertia (kg·m²)
        warnings : []

    References
    ----------
    Hibbeler App. B
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("r_o", r_o)
    if err:
        return _err(err)
    err = _guard_nonneg("r_i", r_i)
    if err:
        return _err(err)

    r_o_f = float(r_o)
    r_i_f = float(r_i)
    if r_i_f >= r_o_f:
        return _err(f"r_i ({r_i_f}) must be < r_o ({r_o_f}).")

    I = 0.5 * float(m) * (r_o_f ** 2 + r_i_f ** 2)
    return {"ok": True, "I": I, "warnings": []}


def moi_solid_sphere(m: float, r: float) -> dict:
    """
    Mass moment of inertia of a solid sphere about a diameter.

    I = 2/5·m·r²

    Parameters
    ----------
    m : float
        Mass (kg). Must be > 0.
    r : float
        Radius (m). Must be > 0.

    Returns
    -------
    dict
        ok  : True
        I   : moment of inertia (kg·m²)
        warnings : []

    References
    ----------
    Hibbeler App. B
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("r", r)
    if err:
        return _err(err)

    I = 0.4 * float(m) * float(r) ** 2
    return {"ok": True, "I": I, "warnings": []}


def moi_thin_rod(m: float, L: float, axis: str = "centroid") -> dict:
    """
    Mass moment of inertia of a thin rod about an axis perpendicular to its length.

    Parameters
    ----------
    m : float
        Mass (kg). Must be > 0.
    L : float
        Length (m). Must be > 0.
    axis : str
        'centroid' (default): I = 1/12·m·L²
        'end':                 I = 1/3·m·L²

    Returns
    -------
    dict
        ok   : True
        I    : moment of inertia (kg·m²)
        axis : axis label used
        warnings : []

    References
    ----------
    Hibbeler App. B
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("L", L)
    if err:
        return _err(err)

    m_f, L_f = float(m), float(L)
    ax = str(axis).strip().lower()
    if ax == "centroid":
        I = m_f * L_f ** 2 / 12.0
    elif ax == "end":
        I = m_f * L_f ** 2 / 3.0
    else:
        return _err(f"axis must be 'centroid' or 'end', got {axis!r}.")

    return {"ok": True, "I": I, "axis": ax, "warnings": []}


def moi_rectangular_plate(m: float, a: float, b: float) -> dict:
    """
    Mass moment of inertia of a thin rectangular plate about an axis through
    its centroid perpendicular to the plate (polar MOI).

    I_z = 1/12·m·(a² + b²)

    Parameters
    ----------
    m : float
        Mass (kg). Must be > 0.
    a : float
        Width (m). Must be > 0.
    b : float
        Height (m). Must be > 0.

    Returns
    -------
    dict
        ok  : True
        I_z : polar MOI about z-axis through centroid (kg·m²)
        I_x : MOI about x-axis through centroid = 1/12·m·b² (kg·m²)
        I_y : MOI about y-axis through centroid = 1/12·m·a² (kg·m²)
        warnings : []

    References
    ----------
    Hibbeler App. B
    """
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_positive("a", a)
    if err:
        return _err(err)
    err = _guard_positive("b", b)
    if err:
        return _err(err)

    m_f, a_f, b_f = float(m), float(a), float(b)
    I_x = m_f * b_f ** 2 / 12.0
    I_y = m_f * a_f ** 2 / 12.0
    I_z = I_x + I_y

    return {"ok": True, "I_z": I_z, "I_x": I_x, "I_y": I_y, "warnings": []}


def parallel_axis(
    I_cm: float,
    m: float,
    d: float,
) -> dict:
    """
    Parallel-axis theorem (Steiner's theorem): I = I_cm + m·d².

    Parameters
    ----------
    I_cm : float
        MOI about centroidal axis (kg·m²). Must be >= 0.
    m : float
        Mass (kg). Must be > 0.
    d : float
        Distance between parallel axes (m). Must be >= 0.

    Returns
    -------
    dict
        ok  : True
        I   : moment of inertia about parallel axis (kg·m²)
        warnings : []

    References
    ----------
    Hibbeler §17-1; Beer §9.11
    """
    err = _guard_nonneg("I_cm", I_cm)
    if err:
        return _err(err)
    err = _guard_positive("m", m)
    if err:
        return _err(err)
    err = _guard_nonneg("d", d)
    if err:
        return _err(err)

    I = float(I_cm) + float(m) * float(d) ** 2
    return {"ok": True, "I": I, "warnings": []}


# ===========================================================================
# 7. FLYWHEEL SIZING
# ===========================================================================

def flywheel_sizing(
    E_fluctuation: float,
    omega_mean: float,
    Cs: float,
) -> dict:
    """
    Required flywheel mass moment of inertia from energy fluctuation.

    ΔE = I·ω_mean²·Cs   →   I = ΔE / (ω_mean²·Cs)

    Parameters
    ----------
    E_fluctuation : float
        Energy fluctuation per cycle ΔE (J). Must be > 0.
    omega_mean : float
        Mean angular velocity of the flywheel (rad/s). Must be > 0.
    Cs : float
        Coefficient of fluctuation of speed Cs = (ω_max - ω_min) / ω_mean.
        Must be > 0. Typical: 0.01–0.20.

    Returns
    -------
    dict
        ok          : True
        I_required  : required mass moment of inertia (kg·m²)
        omega_mean  : mean speed used (rad/s)
        Cs          : fluctuation coefficient used
        warnings    : []

    References
    ----------
    Shigley §16-6; Mabie & Reinholtz §9
    """
    err = _guard_positive("E_fluctuation", E_fluctuation)
    if err:
        return _err(err)
    err = _guard_positive("omega_mean", omega_mean)
    if err:
        return _err(err)
    err = _guard_positive("Cs", Cs)
    if err:
        return _err(err)

    I = float(E_fluctuation) / (float(omega_mean) ** 2 * float(Cs))

    warnings: list[str] = []
    if float(Cs) > 0.2:
        _warn(
            f"Cs={Cs} > 0.2 is unusually large; typical values are 0.01–0.20.",
            warnings,
        )

    return {
        "ok": True,
        "I_required": I,
        "omega_mean": float(omega_mean),
        "Cs": float(Cs),
        "warnings": warnings,
    }


def flywheel_rim(
    I_required: float,
    rho: float,
    r_mean: float,
    b: float,
) -> dict:
    """
    Required rim cross-sectional area for a rim-type flywheel.

    For a thin rim: I ≈ m_rim·r_mean²  and  m_rim = ρ·A_cs·(2π·r_mean)

    Solving for cross-sectional area:
        A_cs = I_required / (2π·ρ·r_mean³)

    The function also returns the rim thickness t = A_cs / b (rectangular
    cross-section with width b in the axial direction).

    Parameters
    ----------
    I_required : float
        Required mass moment of inertia (kg·m²). Must be > 0.
    rho : float
        Material density (kg/m³). Must be > 0. Cast iron ≈ 7200 kg/m³.
    r_mean : float
        Mean radius of the rim (m). Must be > 0.
    b : float
        Rim axial width (m). Must be > 0.

    Returns
    -------
    dict
        ok      : True
        A_cs_m2 : cross-sectional area (m²)
        t_m     : radial thickness = A_cs / b (m)
        m_rim   : rim mass (kg)
        warnings : []

    References
    ----------
    Shigley §16-7
    """
    err = _guard_positive("I_required", I_required)
    if err:
        return _err(err)
    err = _guard_positive("rho", rho)
    if err:
        return _err(err)
    err = _guard_positive("r_mean", r_mean)
    if err:
        return _err(err)
    err = _guard_positive("b", b)
    if err:
        return _err(err)

    A_cs = float(I_required) / (2.0 * math.pi * float(rho) * float(r_mean) ** 3)
    t = A_cs / float(b)
    m_rim = float(rho) * A_cs * 2.0 * math.pi * float(r_mean)

    return {
        "ok": True,
        "A_cs_m2": A_cs,
        "t_m": t,
        "m_rim": m_rim,
        "warnings": [],
    }


# ===========================================================================
# 8. ROTATING-MASS STATIC & DYNAMIC BALANCING
# ===========================================================================

def static_balance(
    masses: list[float],
    radii: list[float],
    angles_deg: list[float],
) -> dict:
    """
    Static balancing of rotating masses in a single plane.

    Computes the resultant unbalance force (m·r) vector and the required
    correction mass·radius product (opposite to resultant) at each angle.

    Parameters
    ----------
    masses : list[float]
        Mass of each counterweight or unbalance mass (kg). All must be > 0.
    radii : list[float]
        Radius of each mass from rotation axis (m). All must be > 0.
    angles_deg : list[float]
        Angular position of each mass (degrees from reference). Any finite value.

    Returns
    -------
    dict
        ok                  : True
        resultant_mr        : magnitude of Σmᵢrᵢ (kg·m)
        resultant_angle_deg : angle of resultant (degrees)
        correction_mr       : required balance mass·radius = resultant_mr (kg·m)
        correction_angle_deg: angle for correction mass (degrees, opposite resultant)
        unbalance_force_at  : unbalance centrifugal force factor = resultant_mr (kg·m)
        warnings            : []

    References
    ----------
    Rattan "Theory of Machines" §20.2; Hibbeler §22
    """
    try:
        m_list = [float(x) for x in masses]
        r_list = [float(x) for x in radii]
        a_list = [float(x) for x in angles_deg]
    except (TypeError, ValueError) as exc:
        return _err(f"masses, radii, and angles_deg must be lists of numbers: {exc}")

    n = len(m_list)
    if n == 0:
        return _err("masses must not be empty.")
    if len(r_list) != n or len(a_list) != n:
        return _err("masses, radii, and angles_deg must all have the same length.")

    for i, (m_i, r_i) in enumerate(zip(m_list, r_list)):
        if m_i <= 0:
            return _err(f"masses[{i}] must be > 0, got {m_i}.")
        if r_i <= 0:
            return _err(f"radii[{i}] must be > 0, got {r_i}.")

    # Compute Σmᵢrᵢ as a 2-D vector sum
    sum_x = sum(m * r * math.cos(math.radians(a)) for m, r, a in zip(m_list, r_list, a_list))
    sum_y = sum(m * r * math.sin(math.radians(a)) for m, r, a in zip(m_list, r_list, a_list))

    resultant_mr = math.hypot(sum_x, sum_y)
    resultant_angle = math.degrees(math.atan2(sum_y, sum_x))
    correction_angle = (resultant_angle + 180.0) % 360.0

    return {
        "ok": True,
        "resultant_mr": resultant_mr,
        "resultant_angle_deg": resultant_angle,
        "correction_mr": resultant_mr,
        "correction_angle_deg": correction_angle,
        "warnings": [],
    }


def dynamic_balance_two_plane(
    masses: list[float],
    radii: list[float],
    angles_deg: list[float],
    axial_positions: list[float],
    plane_a_pos: float,
    plane_b_pos: float,
) -> dict:
    """
    Two-plane (dynamic) balancing of rotating masses.

    Solves for the correction mass·radius products in planes A and B using
    force and moment equilibrium.

    Parameters
    ----------
    masses : list[float]
        Unbalance mass at each axial station (kg).
    radii : list[float]
        Radial distance of each mass from axis (m).
    angles_deg : list[float]
        Angular position of each mass (degrees).
    axial_positions : list[float]
        Axial position of each mass along the rotor axis (m).
    plane_a_pos : float
        Axial position of correction plane A (m).
    plane_b_pos : float
        Axial position of correction plane B (m). Must differ from plane_a_pos.

    Returns
    -------
    dict
        ok                  : True
        correction_A_mr     : correction m·r for plane A (kg·m)
        correction_A_angle  : correction angle in plane A (degrees)
        correction_B_mr     : correction m·r for plane B (kg·m)
        correction_B_angle  : correction angle in plane B (degrees)
        warnings            : []

    Method
    ------
    Take moments about plane B to find plane A correction; then use force
    balance to find plane B correction.

    References
    ----------
    Rattan §20.5; Norton "Machine Design" §Ch.13
    """
    try:
        m_list = [float(x) for x in masses]
        r_list = [float(x) for x in radii]
        a_list = [float(x) for x in angles_deg]
        z_list = [float(x) for x in axial_positions]
    except (TypeError, ValueError) as exc:
        return _err(f"Input lists must contain numbers: {exc}")

    n = len(m_list)
    if n == 0:
        return _err("masses must not be empty.")
    if len(r_list) != n or len(a_list) != n or len(z_list) != n:
        return _err("masses, radii, angles_deg, and axial_positions must all have the same length.")

    for i, (m_i, r_i) in enumerate(zip(m_list, r_list)):
        if m_i <= 0:
            return _err(f"masses[{i}] must be > 0, got {m_i}.")
        if r_i <= 0:
            return _err(f"radii[{i}] must be > 0, got {r_i}.")

    err = _guard_finite("plane_a_pos", plane_a_pos)
    if err:
        return _err(err)
    err = _guard_finite("plane_b_pos", plane_b_pos)
    if err:
        return _err(err)

    zA = float(plane_a_pos)
    zB = float(plane_b_pos)
    if abs(zA - zB) < 1e-12:
        return _err("plane_a_pos and plane_b_pos must be different.")

    # Moment about plane B to solve for plane A correction
    # ΣMB_x = 0: correction_A_mr·cos(θA)·(zA - zB) + Σ mᵢrᵢcos(αᵢ)(zᵢ - zB) = 0
    # ΣMB_y = 0: correction_A_mr·sin(θA)·(zA - zB) + Σ mᵢrᵢsin(αᵢ)(zᵢ - zB) = 0
    sum_moment_x = sum(
        m * r * math.cos(math.radians(a)) * (z - zB)
        for m, r, a, z in zip(m_list, r_list, a_list, z_list)
    )
    sum_moment_y = sum(
        m * r * math.sin(math.radians(a)) * (z - zB)
        for m, r, a, z in zip(m_list, r_list, a_list, z_list)
    )

    # correction_A · (zA - zB) = -sum_moment
    dAB = zA - zB
    cA_x = -sum_moment_x / dAB
    cA_y = -sum_moment_y / dAB

    correction_A_mr = math.hypot(cA_x, cA_y)
    correction_A_angle = math.degrees(math.atan2(cA_y, cA_x)) % 360.0

    # Force balance for plane B
    # ΣF_x = 0: cA_x + cB_x + Σ mᵢrᵢcos(αᵢ) = 0
    sum_force_x = sum(m * r * math.cos(math.radians(a)) for m, r, a in zip(m_list, r_list, a_list))
    sum_force_y = sum(m * r * math.sin(math.radians(a)) for m, r, a in zip(m_list, r_list, a_list))

    cB_x = -(cA_x + sum_force_x)
    cB_y = -(cA_y + sum_force_y)

    correction_B_mr = math.hypot(cB_x, cB_y)
    correction_B_angle = math.degrees(math.atan2(cB_y, cB_x)) % 360.0

    return {
        "ok": True,
        "correction_A_mr": correction_A_mr,
        "correction_A_angle": correction_A_angle,
        "correction_B_mr": correction_B_mr,
        "correction_B_angle": correction_B_angle,
        "warnings": [],
    }


def residual_unbalance(
    m_correction: float,
    e: float,
) -> dict:
    """
    Residual specific unbalance U = m·e (expressed in g·mm for ISO 1940).

    Parameters
    ----------
    m_correction : float
        Correction mass (g). Must be > 0.
    e : float
        Eccentricity distance from axis (mm). Must be > 0.

    Returns
    -------
    dict
        ok      : True
        U_g_mm  : specific unbalance m·e (g·mm)
        warnings : []

    References
    ----------
    ISO 1940-1:2003 §3
    """
    err = _guard_positive("m_correction", m_correction)
    if err:
        return _err(err)
    err = _guard_positive("e", e)
    if err:
        return _err(err)

    U = float(m_correction) * float(e)
    return {"ok": True, "U_g_mm": U, "warnings": []}


# ISO 1940-1 balance grade G values: G × 1000 = eper_mm_s (specific unbalance × ω) in mm/s
# G = eper × ω  [mm/s]; eper in mm, ω in rad/s
# Balance grade table: G number = max permissible eper × ω in mm/s
_ISO1940_GRADES = {
    "G0.4": 0.4,
    "G1": 1.0,
    "G2.5": 2.5,
    "G6.3": 6.3,
    "G16": 16.0,
    "G40": 40.0,
    "G100": 100.0,
    "G250": 250.0,
    "G630": 630.0,
    "G1600": 1600.0,
    "G4000": 4000.0,
}


def iso1940_grade(
    U_g_mm: float,
    m_rotor_kg: float,
    omega_rad_s: float,
    grade: str = "G6.3",
) -> dict:
    """
    ISO 1940-1 balance quality grade check.

    Computes the permissible residual unbalance and compares to actual.

    Parameters
    ----------
    U_g_mm : float
        Actual residual unbalance (g·mm). Must be >= 0.
    m_rotor_kg : float
        Rotor mass (kg). Must be > 0.
    omega_rad_s : float
        Maximum operating angular velocity (rad/s). Must be > 0.
    grade : str
        ISO 1940 balance grade string, e.g. 'G6.3' (default), 'G2.5', 'G1'.
        See ISO 1940-1 Table 1.

    Returns
    -------
    dict
        ok                  : True
        grade               : grade label used
        G_value             : grade value (mm/s)
        eper_mm             : actual specific unbalance = U / m_rotor (mm)
        eper_permissible_mm : permissible specific unbalance = G / ω (mm)
        U_permissible_g_mm  : permissible residual unbalance (g·mm)
        within_grade        : True if eper_mm <= eper_permissible_mm
        warnings            : list — flagged if unbalance exceeds grade

    References
    ----------
    ISO 1940-1:2003 §4
    """
    err = _guard_nonneg("U_g_mm", U_g_mm)
    if err:
        return _err(err)
    err = _guard_positive("m_rotor_kg", m_rotor_kg)
    if err:
        return _err(err)
    err = _guard_positive("omega_rad_s", omega_rad_s)
    if err:
        return _err(err)

    grade_key = str(grade).strip()
    if grade_key not in _ISO1940_GRADES:
        return _err(
            f"Unknown grade '{grade_key}'. "
            f"Supported: {sorted(_ISO1940_GRADES.keys())}"
        )

    G = _ISO1940_GRADES[grade_key]  # mm/s
    # m_rotor in grams (convert from kg × 1000)
    m_rotor_g = float(m_rotor_kg) * 1000.0
    omega_f = float(omega_rad_s)

    # eper_permissible = G / ω  [mm]
    eper_perm = G / omega_f
    # U_permissible = eper_perm × m_rotor  [g·mm]
    U_perm = eper_perm * m_rotor_g

    # Actual specific unbalance
    eper_actual = float(U_g_mm) / m_rotor_g

    within_grade = eper_actual <= eper_perm + 1e-12

    warnings: list[str] = []
    if not within_grade:
        _warn(
            f"Unbalance exceeds ISO 1940 {grade_key}: actual eper={eper_actual:.4f} mm "
            f"> permissible {eper_perm:.4f} mm. "
            f"Actual U={U_g_mm:.2f} g·mm > permissible {U_perm:.2f} g·mm.",
            warnings,
        )

    return {
        "ok": True,
        "grade": grade_key,
        "G_value": G,
        "eper_mm": eper_actual,
        "eper_permissible_mm": eper_perm,
        "U_permissible_g_mm": U_perm,
        "within_grade": within_grade,
        "warnings": warnings,
    }


# ===========================================================================
# 9. RECIPROCATING-MASS SHAKING FORCES
# ===========================================================================

def shaking_force_primary(
    m_recip: float,
    r: float,
    omega: float,
    theta_deg: float,
) -> dict:
    """
    Primary shaking force from a reciprocating mass (single-cylinder).

    F_primary = m_recip · r · ω² · cos(θ)

    The primary force arises from the first harmonic of the piston
    acceleration approximation.

    Parameters
    ----------
    m_recip : float
        Reciprocating mass (kg). Must be > 0.
    r : float
        Crank radius (m). Must be > 0.
    omega : float
        Crank angular velocity (rad/s). Must be > 0.
    theta_deg : float
        Crank angle from TDC (degrees).

    Returns
    -------
    dict
        ok          : True
        F_primary   : primary shaking force (N)
        theta_deg   : crank angle used (degrees)
        warnings    : []

    References
    ----------
    Norton "Machine Design" §13.6; Rattan §21.4
    """
    err = _guard_positive("m_recip", m_recip)
    if err:
        return _err(err)
    err = _guard_positive("r", r)
    if err:
        return _err(err)
    err = _guard_positive("omega", omega)
    if err:
        return _err(err)
    err = _guard_finite("theta_deg", theta_deg)
    if err:
        return _err(err)

    theta = math.radians(float(theta_deg))
    F_p = float(m_recip) * float(r) * float(omega) ** 2 * math.cos(theta)

    return {"ok": True, "F_primary": F_p, "theta_deg": float(theta_deg), "warnings": []}


def shaking_force_secondary(
    m_recip: float,
    r: float,
    omega: float,
    n: float,
    theta_deg: float,
) -> dict:
    """
    Secondary shaking force from a reciprocating mass (single-cylinder).

    F_secondary = m_recip · r · ω² · (r/L) · cos(2θ)
                = m_recip · r · ω² · (1/n) · cos(2θ)

    where n = L/r is the connecting-rod ratio (L = connecting-rod length).

    Parameters
    ----------
    m_recip : float
        Reciprocating mass (kg). Must be > 0.
    r : float
        Crank radius (m). Must be > 0.
    omega : float
        Crank angular velocity (rad/s). Must be > 0.
    n : float
        Connecting-rod ratio n = L/r. Must be > 1.
    theta_deg : float
        Crank angle from TDC (degrees).

    Returns
    -------
    dict
        ok              : True
        F_secondary     : secondary shaking force (N)
        theta_deg       : crank angle used (degrees)
        n               : connecting-rod ratio used
        warnings        : []

    References
    ----------
    Norton §13.6; Rattan §21.5
    """
    err = _guard_positive("m_recip", m_recip)
    if err:
        return _err(err)
    err = _guard_positive("r", r)
    if err:
        return _err(err)
    err = _guard_positive("omega", omega)
    if err:
        return _err(err)
    err = _guard_finite("theta_deg", theta_deg)
    if err:
        return _err(err)

    try:
        n_f = float(n)
    except (TypeError, ValueError):
        return _err(f"n must be a number, got {n!r}")
    if n_f <= 1.0:
        return _err(f"n = L/r must be > 1, got {n_f}.")

    theta = math.radians(float(theta_deg))
    F_s = float(m_recip) * float(r) * float(omega) ** 2 * (1.0 / n_f) * math.cos(2.0 * theta)

    return {"ok": True, "F_secondary": F_s, "theta_deg": float(theta_deg), "n": n_f, "warnings": []}


# ===========================================================================
# 10. GYROSCOPIC REACTION MOMENT
# ===========================================================================

def gyroscopic_moment(
    I_spin: float,
    omega_spin: float,
    omega_precession: float,
) -> dict:
    """
    Gyroscopic reaction moment (scalar form for perpendicular axes).

    M_gyro = I_spin · ω_spin · ω_precession

    This is the magnitude of the gyroscopic couple when the spin axis
    and precession axis are perpendicular (steady precession).

    Parameters
    ----------
    I_spin : float
        Spin axis moment of inertia (kg·m²). Must be > 0.
    omega_spin : float
        Angular velocity about spin axis (rad/s). Must be > 0.
    omega_precession : float
        Angular velocity of precession (rad/s). Must be > 0.

    Returns
    -------
    dict
        ok      : True
        M_gyro  : gyroscopic couple (N·m)
        warnings : []

    References
    ----------
    Hibbeler §21-5; Beer §18.3
    """
    err = _guard_positive("I_spin", I_spin)
    if err:
        return _err(err)
    err = _guard_positive("omega_spin", omega_spin)
    if err:
        return _err(err)
    err = _guard_positive("omega_precession", omega_precession)
    if err:
        return _err(err)

    M = float(I_spin) * float(omega_spin) * float(omega_precession)
    return {"ok": True, "M_gyro": M, "warnings": []}
