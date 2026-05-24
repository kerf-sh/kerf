"""
kerf_cad_core.kinematics.linkage — planar mechanism/linkage kinematics.

Implements five public solver families:

  four_bar_position(r1, r2, r3, r4, theta2_deg, *, branch)
      Closed-form (Freudenstein) four-bar linkage position analysis.
      Returns coupler angle theta3 and output-link angle theta4.

  four_bar_grashof(r1, r2, r3, r4)
      Grashof classification: "Grashof" vs "non-Grashof", plus type
      (crank-rocker, double-crank, rocker-crank, double-rocker).

  four_bar_transmission_angle(r1, r2, r3, r4, theta2_deg)
      Transmission angle mu at the coupler-to-output joint; in degrees.

  four_bar_coupler_curve(r1, r2, r3, r4, px, py, *, n_points, branch)
      Sample the coupler-point path (x, y) over a full 360° crank rotation.

  slider_crank(r, l, theta_deg, *, omega_rad_s, alpha_rad_s2)
      Slider-crank position, velocity, and acceleration analysis for any
      crank angle theta.

  cam_follower_cycloidal(h, beta_deg, theta_deg, *, rise)
      Displacement, velocity, and acceleration of a cycloidal rise/fall cam
      profile.

  cam_follower_harmonic(h, beta_deg, theta_deg, *, rise)
      Displacement, velocity, and acceleration of a harmonic (cosine) rise/fall
      cam profile.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
  lengths    — arbitrary consistent units (metres recommended)
  angles     — degrees for inputs, degrees for output joint angles
  velocities — rad/s for omega inputs, m/s or rad/s outputs
  cam        — h in any length unit; theta must be within [0, beta]

References
----------
Norton, R.L. "Design of Machinery", 5th ed.
Shigley, J.E. & Uicker, J.J. "Theory of Machines & Mechanisms", 4th ed.
Freudenstein, F. (1955). "An Analytical Approach to the Design of Four-Link Mechanisms"
Erdman, A.G. & Sandor, G.N. "Mechanism Design: Analysis and Synthesis", Vol. 1.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_number(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    return None


# ---------------------------------------------------------------------------
# 1. Grashof classification
# ---------------------------------------------------------------------------

def four_bar_grashof(
    r1: float,
    r2: float,
    r3: float,
    r4: float,
) -> dict:
    """
    Grashof classification of a four-bar linkage.

    Labelling convention (Norton §2.15):
        r1 = ground / frame link (d)
        r2 = crank (a) — input link
        r3 = coupler (b)
        r4 = output / rocker (c)

    Grashof condition: S + L <= P + Q
        S = shortest link length
        L = longest link length
        P, Q = the other two

    Parameters
    ----------
    r1, r2, r3, r4 : float
        Link lengths (any consistent units, all > 0).

    Returns
    -------
    dict
        ok           : True
        grashof      : True if Grashof condition satisfied (S+L <= P+Q)
        special      : True if S+L == P+Q exactly (change-point / special Grashof)
        type         : one of:
                       "crank-rocker"   — Grashof, shortest = crank (r2)
                       "double-crank"   — Grashof, shortest = ground (r1)
                       "rocker-crank"   — Grashof, shortest = output (r4)
                       "double-rocker"  — Grashof, shortest = coupler (r3)
                       "non-Grashof"    — non-Grashof (all links rock only)
                       "change-point"   — special Grashof (S+L == P+Q)
        S, L, P, Q   : sorted link lengths used for classification
        warnings     : list of warning strings

    References
    ----------
    Norton "Design of Machinery", 5th ed., §2.15
    """
    warnings: list[str] = []

    for name, val in (("r1", r1), ("r2", r2), ("r3", r3), ("r4", r4)):
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    links = [float(r1), float(r2), float(r3), float(r4)]
    S = min(links)
    L = max(links)
    others = sorted(links)
    # Remove one occurrence of S and one of L to get P, Q
    tmp = others[:]
    tmp.remove(S)
    tmp.remove(L)
    P, Q = tmp

    grashof = S + L <= P + Q + 1e-12 * max(links)
    special = abs((S + L) - (P + Q)) < 1e-9 * max(links)

    if special:
        link_type = "change-point"
        warnings.append(
            "Change-point (special Grashof): S+L == P+Q. "
            "Mechanism has uncertainty at dead-centre positions."
        )
    elif not grashof:
        link_type = "non-Grashof"
    else:
        # Identify which link is shortest to name the type
        # Position of S in the original [r1, r2, r3, r4] list
        idx = links.index(S)
        _type_map = {
            0: "double-crank",   # ground is shortest
            1: "crank-rocker",   # crank (input) is shortest
            2: "double-rocker",  # coupler is shortest
            3: "rocker-crank",   # output is shortest
        }
        link_type = _type_map[idx]

    return {
        "ok": True,
        "grashof": grashof or special,
        "special": special,
        "type": link_type,
        "S": S,
        "L": L,
        "P": P,
        "Q": Q,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. Four-bar position analysis (Freudenstein / vector-loop)
# ---------------------------------------------------------------------------

def four_bar_position(
    r1: float,
    r2: float,
    r3: float,
    r4: float,
    theta2_deg: float,
    *,
    branch: int = 1,
) -> dict:
    """
    Four-bar linkage position analysis using the Freudenstein equation.

    Finds coupler angle theta3 and output-link angle theta4 for a given
    crank angle theta2.

    Vector-loop equation:
        r2·exp(jθ2) + r3·exp(jθ3) = r1 + r4·exp(jθ4)

    Freudenstein equation:
        K1·cos(θ4) - K2·cos(θ2) + K3 = cos(θ2 - θ4)

    Derived from the vector-loop closure equation by squaring to eliminate θ3:
        r3² = r1² + r4² + r2² + 2·r1·r4·cos(θ4) − 2·r1·r2·cos(θ2) − 2·r2·r4·cos(θ2−θ4)
    Dividing through by 2·r2·r4 gives the Freudenstein constants:
        K1 = r1/r2,  K2 = r1/r4,  K3 = (r1² + r4² + r2² − r3²) / (2·r2·r4)

    The equation is solved for θ4 using the half-angle substitution
    (Weierstrass / t-substitution), yielding up to two branches.

    Parameters
    ----------
    r1 : float  Ground link length (> 0).
    r2 : float  Crank (input) link length (> 0).
    r3 : float  Coupler link length (> 0).
    r4 : float  Output link length (> 0).
    theta2_deg : float  Crank angle measured from positive x-axis (degrees).
    branch : int  1 (default) or -1 — selects open (+) or crossed (-) assembly.

    Returns
    -------
    dict
        ok            : True
        theta2_deg    : crank angle (degrees, as supplied)
        theta3_deg    : coupler angle (degrees)
        theta4_deg    : output-link angle (degrees)
        branch        : branch used (1 or -1)
        warnings      : list of warning strings

    Notes
    -----
    Singular/locked configurations (discriminant <= 0) are reported in
    warnings and the function returns the nearest valid value (limiting case).
    """
    warnings: list[str] = []

    for name, val in (("r1", r1), ("r2", r2), ("r3", r3), ("r4", r4)):
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    e = _guard_number("theta2_deg", theta2_deg)
    if e:
        return _err(e)
    if branch not in (1, -1):
        return _err(f"branch must be 1 or -1, got {branch!r}")

    r1, r2, r3, r4 = float(r1), float(r2), float(r3), float(r4)
    theta2 = math.radians(theta2_deg)

    # Freudenstein coefficients — derived from vector-loop squaring (Freudenstein 1955)
    # K1*cos(t4) - K2*cos(t2) + K3 = cos(t2 - t4)
    K1 = r1 / r2
    K2 = r1 / r4
    K3 = (r1 * r1 + r4 * r4 + r2 * r2 - r3 * r3) / (2.0 * r2 * r4)

    # Expand cos(t2-t4) = cos(t2)*cos(t4) + sin(t2)*sin(t4)
    # => (K1 - cos(t2))*cos(t4) - sin(t2)*sin(t4) + (K3 - K2*cos(t2)) = 0
    # Half-angle substitution t = tan(t4/2):
    #   cos(t4) = (1-t²)/(1+t²), sin(t4) = 2t/(1+t²)
    # Multiply through by (1+t²):
    #   B*(1-t²) - 2*sin(t2)*t + A*(1+t²) = 0
    # => (A-B)*t² - 2*sin(t2)*t + (A+B) = 0
    # where A = K3 - K2*cos(t2),  B = K1 - cos(t2)

    cos2 = math.cos(theta2)
    sin2 = math.sin(theta2)

    A_f = K3 - K2 * cos2
    B_f = K1 - cos2

    aa = A_f - B_f
    bb = -2.0 * sin2
    cc = A_f + B_f

    # Solve aa·t² + bb·t + cc = 0
    if abs(aa) < 1e-14:
        # Linear case
        if abs(bb) < 1e-14:
            warnings.append(
                "Singular configuration: linkage is locked (aa=bb=0 in Freudenstein solve). "
                "Returning theta4=0."
            )
            theta4 = 0.0
        else:
            t = -cc / bb
            theta4 = 2.0 * math.atan(t)
    else:
        discriminant = bb * bb - 4.0 * aa * cc
        if discriminant < 0:
            if discriminant > -1e-9:
                discriminant = 0.0
                warnings.append(
                    "Near-singular configuration: linkage at a limiting (dead-centre) position. "
                    "Discriminant clamped to zero."
                )
            else:
                warnings.append(
                    f"Singular/locked configuration: discriminant={discriminant:.6g} < 0. "
                    "Linkage cannot reach this crank angle. Returning closest valid position."
                )
                discriminant = 0.0

        sqrt_d = math.sqrt(max(discriminant, 0.0))
        t = (-bb + branch * sqrt_d) / (2.0 * aa)
        theta4 = 2.0 * math.atan(t)

    # Recover theta3 from the vector-loop closure
    # r2·cos(θ2) + r3·cos(θ3) = r1 + r4·cos(θ4)
    # r2·sin(θ2) + r3·sin(θ3) = r4·sin(θ4)
    ex = r1 + r4 * math.cos(theta4) - r2 * cos2
    ey = r4 * math.sin(theta4) - r2 * sin2
    theta3 = math.atan2(ey, ex)

    # Verify closure (residual should be near zero)
    res_x = r2 * cos2 + r3 * math.cos(theta3) - r1 - r4 * math.cos(theta4)
    res_y = r2 * sin2 + r3 * math.sin(theta3) - r4 * math.sin(theta4)
    residual = math.sqrt(res_x * res_x + res_y * res_y)
    if residual > 1e-6 * max(r1, r2, r3, r4):
        warnings.append(
            f"Closure residual={residual:.3e}; numerical precision may be reduced."
        )

    return {
        "ok": True,
        "theta2_deg": theta2_deg,
        "theta3_deg": math.degrees(theta3),
        "theta4_deg": math.degrees(theta4),
        "branch": branch,
        "closure_residual": residual,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. Transmission angle
# ---------------------------------------------------------------------------

def four_bar_transmission_angle(
    r1: float,
    r2: float,
    r3: float,
    r4: float,
    theta2_deg: float,
) -> dict:
    """
    Transmission angle for a four-bar linkage.

    The transmission angle mu is the angle between the coupler link (r3)
    and the output link (r4) at their joint (B').  It measures the
    quality of force transmission to the output link.

    The rule of thumb is: mu should stay between 40° and 140° for
    acceptable transmission (|deviation from 90°| < 50°).

    Formula (Norton §3.4, after finding θ3, θ4):
        mu = theta3 - theta4   (angle at the coupler-output joint)
    or equivalently (law of cosines on the linkage polygon):

        cos(mu) = (r3² + r4² - BD²) / (2·r3·r4)

    where BD² = r1² + r2² - 2·r1·r2·cos(θ2)   (diagonal BD of the quadrilateral).

    Parameters
    ----------
    r1, r2, r3, r4 : float  Link lengths (> 0).
    theta2_deg : float       Crank angle (degrees).

    Returns
    -------
    dict
        ok                   : True
        theta2_deg           : as supplied
        mu_deg               : transmission angle (degrees)
        mu_deviation_from_90 : |mu - 90| (degrees); lower is better
        acceptable           : True if 40° <= mu <= 140°
        warnings             : list of warning strings
    """
    warnings: list[str] = []

    for name, val in (("r1", r1), ("r2", r2), ("r3", r3), ("r4", r4)):
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    e = _guard_number("theta2_deg", theta2_deg)
    if e:
        return _err(e)

    r1, r2, r3, r4 = float(r1), float(r2), float(r3), float(r4)
    theta2 = math.radians(theta2_deg)

    # Diagonal BD² (law of cosines on triangle O2-A-O4 or the ground-crank triangle)
    BD2 = r1 * r1 + r2 * r2 - 2.0 * r1 * r2 * math.cos(theta2)

    # Law of cosines: mu at the coupler-output joint
    # (triangle with sides r3, r4, and BD)
    denom = 2.0 * r3 * r4
    if denom < 1e-14:
        return _err("r3 and/or r4 are effectively zero.")

    numerator = r3 * r3 + r4 * r4 - BD2
    cos_mu = numerator / denom

    # Clamp for numerical safety
    cos_mu = max(-1.0, min(1.0, cos_mu))
    mu = math.degrees(math.acos(cos_mu))

    deviation = abs(mu - 90.0)
    acceptable = 40.0 <= mu <= 140.0

    if not acceptable:
        warnings.append(
            f"Transmission angle mu={mu:.1f}° is outside the recommended [40°, 140°] range. "
            "Force transmission quality is poor; consider resynthesising the linkage."
        )

    return {
        "ok": True,
        "theta2_deg": theta2_deg,
        "mu_deg": mu,
        "mu_deviation_from_90": deviation,
        "acceptable": acceptable,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. Coupler-curve sampling
# ---------------------------------------------------------------------------

def four_bar_coupler_curve(
    r1: float,
    r2: float,
    r3: float,
    r4: float,
    px: float,
    py: float,
    *,
    n_points: int = 72,
    branch: int = 1,
) -> dict:
    """
    Sample the coupler-point curve for a four-bar linkage.

    The coupler point P is defined in the coupler frame:
        P = A + (px·e_3 + py·e_3_perp)
    where e_3 = unit vector along the coupler, A is the coupler-crank joint.

    Parameters
    ----------
    r1, r2, r3, r4 : float  Link lengths (> 0).
    px : float  Coupler-point x-offset along the coupler from joint A.
    py : float  Coupler-point y-offset perpendicular to coupler from joint A.
    n_points : int  Number of crank-angle samples in [0°, 360°) (default 72).
    branch : int  1 or -1 — linkage branch/assembly to trace.

    Returns
    -------
    dict
        ok       : True
        points   : list of {"theta2_deg": ..., "x": ..., "y": ...} dicts
        n_points : number of points returned (may be < n_points if singularities hit)
        branch   : branch used
        warnings : list of warning strings
    """
    warnings: list[str] = []

    for name, val in (("r1", r1), ("r2", r2), ("r3", r3), ("r4", r4)):
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    for name, val in (("px", px), ("py", py)):
        e = _guard_number(name, val)
        if e:
            return _err(e)
    if not isinstance(n_points, int) or n_points < 2:
        n_points = max(2, int(n_points)) if n_points else 2
        warnings.append(f"n_points adjusted to {n_points}.")
    if branch not in (1, -1):
        return _err(f"branch must be 1 or -1, got {branch!r}")

    r1, r2, r3, r4 = float(r1), float(r2), float(r3), float(r4)
    px, py = float(px), float(py)

    points: list[dict] = []
    singular_count = 0

    for i in range(n_points):
        theta2_deg = 360.0 * i / n_points
        pos = four_bar_position(r1, r2, r3, r4, theta2_deg, branch=branch)
        if not pos["ok"]:
            singular_count += 1
            continue

        theta2 = math.radians(theta2_deg)
        theta3 = math.radians(pos["theta3_deg"])

        # Crank-coupler joint A position (ground pivot O2 at origin)
        Ax = r2 * math.cos(theta2)
        Ay = r2 * math.sin(theta2)

        # Coupler unit vector
        cos3 = math.cos(theta3)
        sin3 = math.sin(theta3)

        # Coupler point P = A + px*e3 + py*e3_perp
        Px = Ax + px * cos3 - py * sin3
        Py = Ay + px * sin3 + py * cos3

        points.append({"theta2_deg": theta2_deg, "x": Px, "y": Py})

        if pos["warnings"]:
            singular_count += 1

    if singular_count > 0:
        warnings.append(
            f"{singular_count} singular/near-singular configurations encountered; "
            "those points were skipped."
        )

    return {
        "ok": True,
        "points": points,
        "n_points": len(points),
        "branch": branch,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. Slider-crank kinematics
# ---------------------------------------------------------------------------

def slider_crank(
    r: float,
    l: float,
    theta_deg: float,
    *,
    omega_rad_s: float = 0.0,
    alpha_rad_s2: float = 0.0,
) -> dict:
    """
    Slider-crank position, velocity, and acceleration analysis.

    Assumes the standard in-line slider-crank (no eccentricity):
        - Crank pivot O at origin
        - Slider axis along positive x-axis

    Position (exact closed-form):
        x_B = r·cos(θ) + √(l² - r²·sin²(θ))

    Velocity (differentiating w.r.t. time, ω = dθ/dt):
        v_B = -r·ω·sin(θ) · [1 + r·cos(θ) / √(l² - r²·sin²(θ))]

    Acceleration (differentiating again):
        a_B = ... (full expression below)

    Parameters
    ----------
    r : float  Crank radius (> 0).
    l : float  Connecting-rod length (> 0). Must be > r for non-singular motion.
    theta_deg : float  Crank angle from TDC (degrees, measured from positive x-axis).
    omega_rad_s : float  Crank angular velocity (rad/s, default 0).
    alpha_rad_s2 : float  Crank angular acceleration (rad/s², default 0).

    Returns
    -------
    dict
        ok           : True
        theta_deg    : crank angle (degrees, as supplied)
        x_B          : slider position (same units as r, l)
        v_B          : slider velocity (units/s)  — 0 if omega=0
        a_B          : slider acceleration (units/s²) — 0 if omega=alpha=0
        phi_deg      : connecting-rod angle from x-axis (degrees)
        warnings     : list of warning strings

    References
    ----------
    Norton "Design of Machinery", 5th ed., §13.4
    Shigley & Uicker "Theory of Machines & Mechanisms", §2.4
    """
    warnings: list[str] = []

    e = _guard_positive("r", r)
    if e:
        return _err(e)
    e = _guard_positive("l", l)
    if e:
        return _err(e)
    e = _guard_number("theta_deg", theta_deg)
    if e:
        return _err(e)
    e = _guard_number("omega_rad_s", omega_rad_s)
    if e:
        return _err(e)
    e = _guard_number("alpha_rad_s2", alpha_rad_s2)
    if e:
        return _err(e)

    r, l = float(r), float(l)
    theta = math.radians(theta_deg)
    omega = float(omega_rad_s)
    alpha = float(alpha_rad_s2)

    if l <= r:
        warnings.append(
            f"Connecting-rod length l={l} <= crank radius r={r}. "
            "The slider will not complete a full revolution without jamming. "
            "Results may be unreliable near theta where sin(theta) = ±l/r."
        )

    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)

    radical_sq = l * l - r * r * sin_theta * sin_theta
    if radical_sq < 0:
        # Linkage cannot reach this angle
        radical_sq = 0.0
        warnings.append(
            "Slider-crank singular: r·sin(θ) > l. "
            "Linkage locked at this crank angle; returning limiting position."
        )
    radical = math.sqrt(radical_sq)

    # Position
    x_B = r * cos_theta + radical

    # Connecting-rod angle
    if l > 0:
        sin_phi = r * sin_theta / l
        sin_phi = max(-1.0, min(1.0, sin_phi))
        phi = math.asin(sin_phi)
    else:
        phi = 0.0
    phi_deg = math.degrees(phi)

    # Velocity
    if omega == 0.0 and alpha == 0.0:
        v_B = 0.0
        a_B = 0.0
    else:
        # v_B = dx_B/dt = -r·ω·sin(θ) - r²·ω·sin(θ)·cos(θ) / radical   (if radical > 0)
        if radical > 1e-14:
            v_B = -r * omega * sin_theta - (r * r * omega * sin_theta * cos_theta) / radical
        else:
            v_B = -r * omega * sin_theta
            warnings.append("Near-singular position: velocity approximated (radical~0).")

        # Acceleration — exact closed form.
        #
        #   x_B = r·cosθ + R,            R = √(l² − r²·sin²θ)
        #   v_B = ẋ_B = −r·ω·sinθ − r²·ω·sinθ·cosθ / R
        #
        # Differentiating v_B w.r.t. time (θ̇ = ω, θ̈ = α):
        #
        #   a_B = −r·α·sinθ − r·ω²·cosθ
        #         − r² · d/dt( g / R )
        #
        # with g(t) = ω·sinθ·cosθ = ½·ω·sin2θ, so by the quotient rule
        #
        #   d/dt(g/R) = (ġ·R − g·Ṙ) / R²
        #   ġ  = α·sinθ·cosθ + ω²·cos2θ          (chain rule on ω·f, f=sinθcosθ)
        #   Ṙ  = −r²·ω·sinθ·cosθ / R
        #
        # This reduces to the standard Shigley/Norton slider-crank
        # acceleration; for large n = l/r it agrees with the classical
        # approximation a_B ≈ −r·ω²·[cosθ + cos2θ/n].
        # References: Norton "Design of Machinery" §13.4;
        #             Shigley & Uicker "Theory of Machines & Mechanisms" §2.4.
        if radical > 1e-14:
            f = sin_theta * cos_theta
            g = omega * f
            g_dot = alpha * f + omega * math.cos(2.0 * theta) * omega
            R_dot = -r * r * sin_theta * cos_theta * omega / radical
            term2 = -r * r * (g_dot * radical - g * R_dot) / (radical * radical)
            a_B = (
                -r * alpha * sin_theta
                - r * omega * omega * cos_theta
                + term2
            )
        else:
            a_B = -r * alpha * sin_theta - r * omega * omega * cos_theta
            warnings.append("Near-singular position: acceleration approximated (radical~0).")

    return {
        "ok": True,
        "theta_deg": theta_deg,
        "x_B": x_B,
        "v_B": v_B,
        "a_B": a_B,
        "phi_deg": phi_deg,
        "r": r,
        "l": l,
        "omega_rad_s": omega,
        "alpha_rad_s2": alpha,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. Cam-follower — cycloidal profile
# ---------------------------------------------------------------------------

def cam_follower_cycloidal(
    h: float,
    beta_deg: float,
    theta_deg: float,
    *,
    rise: bool = True,
) -> dict:
    """
    Cycloidal cam-follower displacement, velocity, and acceleration.

    The cycloidal profile satisfies the boundary conditions:
        y(0) = 0, y'(0) = 0, y''(0) = 0  (smooth start)
        y(β) = h, y'(β) = 0, y''(β) = 0  (smooth end)

    Displacement (rise, Norton §8.3):
        y = h · [θ/β - (1/2π)·sin(2π·θ/β)]

    Velocity (w.r.t. cam angle, per unit omega):
        y' = (h/β) · [1 - cos(2π·θ/β)]

    Acceleration (w.r.t. cam angle squared, per unit omega²):
        y'' = (2π·h/β²) · sin(2π·θ/β)

    For fall (rise=False), the output is mirrored:
        y_fall = h - y_rise(β - θ)

    Parameters
    ----------
    h : float          Total follower lift/stroke (any consistent length unit, > 0).
    beta_deg : float   Total cam rotation for the rise/fall segment (degrees, > 0).
    theta_deg : float  Current cam angle within the segment (degrees, in [0, beta_deg]).
    rise : bool        True (default) for rise; False for fall.

    Returns
    -------
    dict
        ok              : True
        theta_deg       : as supplied
        displacement    : follower displacement (same units as h)
        velocity_per_omega    : dy/dθ · (1/ω) — multiply by ω (rad/s) for actual velocity
        acceleration_per_omega2 : d²y/dθ² · (1/ω²) — multiply by ω² for actual acceleration
        profile         : "cycloidal"
        rise            : bool, as supplied
        warnings        : list of warning strings
    """
    warnings: list[str] = []

    e = _guard_positive("h", h)
    if e:
        return _err(e)
    e = _guard_positive("beta_deg", beta_deg)
    if e:
        return _err(e)
    e = _guard_nonneg("theta_deg", theta_deg)
    if e:
        return _err(e)

    h, beta_deg = float(h), float(beta_deg)
    theta_deg = float(theta_deg)

    if theta_deg > beta_deg + 1e-9:
        warnings.append(
            f"theta_deg={theta_deg:.4g} exceeds beta_deg={beta_deg:.4g}; "
            "clamping to beta_deg."
        )
        theta_deg = beta_deg

    beta = math.radians(beta_deg)
    theta = math.radians(theta_deg)
    xi = theta / beta  # normalised cam angle [0, 1]

    # Rise formulas (y goes 0 → h as theta goes 0 → beta)
    y_r = h * (xi - math.sin(2.0 * math.pi * xi) / (2.0 * math.pi))
    dy_r = (h / beta) * (1.0 - math.cos(2.0 * math.pi * xi))
    d2y_r = (2.0 * math.pi * h / (beta * beta)) * math.sin(2.0 * math.pi * xi)

    if rise:
        y = y_r
        dy_dtheta = dy_r
        d2y_dtheta2 = d2y_r
    else:
        # Fall: y goes h → 0 as theta goes 0 → beta
        # y_fall(theta) = h - y_rise(theta)
        y = h - y_r
        dy_dtheta = -dy_r
        d2y_dtheta2 = -d2y_r

    return {
        "ok": True,
        "theta_deg": theta_deg,
        "displacement": y,
        "velocity_per_omega": dy_dtheta,
        "acceleration_per_omega2": d2y_dtheta2,
        "profile": "cycloidal",
        "rise": rise,
        "h": h,
        "beta_deg": beta_deg,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. Cam-follower — harmonic (cosine) profile
# ---------------------------------------------------------------------------

def cam_follower_harmonic(
    h: float,
    beta_deg: float,
    theta_deg: float,
    *,
    rise: bool = True,
) -> dict:
    """
    Harmonic (cosine) cam-follower displacement, velocity, and acceleration.

    The harmonic (simple harmonic motion / SHM) profile:
        y = (h/2) · [1 - cos(π·θ/β)]

    Velocity (per unit omega):
        y' = (π·h / (2·β)) · sin(π·θ/β)

    Acceleration (per unit omega²):
        y'' = (π²·h / (2·β²)) · cos(π·θ/β)

    Note: harmonic profiles have finite acceleration at start/end (NOT zero),
    which causes impulsive loads unless follower dwell is avoided.  A warning
    is always issued.

    For fall (rise=False), the output is mirrored.

    Parameters
    ----------
    h : float          Total follower lift/stroke (> 0).
    beta_deg : float   Total cam rotation for the segment (degrees, > 0).
    theta_deg : float  Current cam angle within segment (degrees, in [0, beta_deg]).
    rise : bool        True (default) for rise; False for fall.

    Returns
    -------
    dict
        ok              : True
        theta_deg       : as supplied (clamped if > beta_deg)
        displacement    : follower displacement
        velocity_per_omega    : dy/dθ · (1/ω)
        acceleration_per_omega2 : d²y/dθ² · (1/ω²)
        profile         : "harmonic"
        rise            : bool
        warnings        : list of warning strings
    """
    warnings: list[str] = []

    e = _guard_positive("h", h)
    if e:
        return _err(e)
    e = _guard_positive("beta_deg", beta_deg)
    if e:
        return _err(e)
    e = _guard_nonneg("theta_deg", theta_deg)
    if e:
        return _err(e)

    h, beta_deg = float(h), float(beta_deg)
    theta_deg = float(theta_deg)

    if theta_deg > beta_deg + 1e-9:
        warnings.append(
            f"theta_deg={theta_deg:.4g} exceeds beta_deg={beta_deg:.4g}; "
            "clamping to beta_deg."
        )
        theta_deg = beta_deg

    warnings.append(
        "Harmonic profile has non-zero acceleration at boundaries (theta=0 and theta=beta). "
        "This causes a jump discontinuity in acceleration (infinite jerk) at dwell transitions. "
        "Consider cycloidal or modified trapezoidal profiles for high-speed cams."
    )

    beta = math.radians(beta_deg)
    theta = math.radians(theta_deg)
    xi = theta / beta  # in [0, 1]

    # Rise formulas (y goes 0 → h as theta goes 0 → beta)
    y_r = (h / 2.0) * (1.0 - math.cos(math.pi * xi))
    dy_r = (math.pi * h / (2.0 * beta)) * math.sin(math.pi * xi)
    d2y_r = (math.pi * math.pi * h / (2.0 * beta * beta)) * math.cos(math.pi * xi)

    if rise:
        y = y_r
        dy_dtheta = dy_r
        d2y_dtheta2 = d2y_r
    else:
        # Fall: y goes h → 0 as theta goes 0 → beta
        # y_fall(theta) = h - y_rise(theta)
        y = h - y_r
        dy_dtheta = -dy_r
        d2y_dtheta2 = -d2y_r

    return {
        "ok": True,
        "theta_deg": theta_deg,
        "displacement": y,
        "velocity_per_omega": dy_dtheta,
        "acceleration_per_omega2": d2y_dtheta2,
        "profile": "harmonic",
        "rise": rise,
        "h": h,
        "beta_deg": beta_deg,
        "warnings": warnings,
    }
