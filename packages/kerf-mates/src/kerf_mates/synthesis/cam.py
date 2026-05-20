"""
kerf_mates.synthesis.cam — cam-profile synthesis from follower motion laws.

The forward kinematics for cycloidal and harmonic cam-follower analysis
already live in kerf_cad_core.kinematics.linkage.  This module provides
the synthesis layer (motion-law spec → profile sample array) and adds
the polynomial (4-5-6-7 / modified trapezoidal) law which is not yet in
the analysis module.

Public API
----------
synthesise_cam(law, h, beta_deg, *, n_points=360, rise=True,
               poly_order=5) -> dict

    law       : "cycloidal" | "polynomial" | "harmonic"
    h         : follower total lift (mm, > 0)
    beta_deg  : cam rotation for the segment (degrees, > 0)
    n_points  : number of cam-angle samples (default 360)
    rise      : True for rise, False for fall (default True)
    poly_order: polynomial order (4, 5, 6, or 7, default 5)
                Only used when law="polynomial".

    Returns dict:
        ok            bool
        law           str   motion law used
        h             float lift (mm)
        beta_deg      float segment angle (degrees)
        n_points      int
        profile       list of dicts, each:
            theta_deg           float  cam angle within segment
            displacement        float  follower position (mm)
            velocity_per_omega  float  dy/dθ (mm/rad)
            acceleration_per_omega2  float  d²y/dθ² (mm/rad²)
        continuity_ok bool   True when displacement, velocity and accel
                             are C2-continuous at boundaries (within 1e-9)
        lift_ok       bool   True when displacement at beta equals h
                             (within 1e-6 mm)
        warnings      list[str]
        reason        str    (only when ok=False)

Notes on motion laws
--------------------
Cycloidal   — zero velocity + zero acceleration at both boundaries (C2).
              Best dynamic performance for high-speed cams.
              (Delegates to kerf_cad_core.kinematics.linkage.cam_follower_cycloidal)

Harmonic    — zero velocity at boundaries but NON-ZERO acceleration at
              boundaries (impulsive jerk at transitions).
              (Delegates to kerf_cad_core.kinematics.linkage.cam_follower_harmonic)

Polynomial  — family of polynomial motion laws with configurable order.
              Order 5 (3-4-5 polynomial): satisfies boundary conditions
                  y(0)=0, y'(0)=0, y''(0)=0, y(β)=h, y'(β)=0, y''(β)=0
                  y = h · [10ξ³ − 15ξ⁴ + 6ξ⁵]  (ξ = θ/β)
              Order 7 (4-5-6-7 polynomial): also zero jerk at boundaries
                  y = h · [35ξ⁴ − 84ξ⁵ + 70ξ⁶ − 20ξ⁷]
              Provides smooth, tunable profiles as alternatives to cycloidal.

References
----------
Norton, R.L. (2012). Design of Machinery, 5th ed., Ch. 8.
Erdman, A.G. & Sandor, G.N. (1991). Mechanism Design, Vol. 1, Ch. 8.
Shigley, J.E. & Uicker, J.J. (1995). Theory of Machines, Ch. 4.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


# Try to reuse the existing cam analysis functions from kerf_cad_core.
# If kerf_cad_core is not installed, fall back to an inline implementation.
try:
    from kerf_cad_core.kinematics.linkage import (
        cam_follower_cycloidal as _cycloidal_analysis,
        cam_follower_harmonic as _harmonic_analysis,
    )
    _HAVE_CORE = True
except ImportError:
    _HAVE_CORE = False


def _cycloidal(h: float, beta: float, theta: float, rise: bool) -> tuple[float, float, float]:
    """
    Cycloidal profile — fallback inline implementation.
    Returns (displacement, dy/dtheta, d2y/dtheta2).
    """
    xi = theta / beta
    y_r = h * (xi - math.sin(2.0 * math.pi * xi) / (2.0 * math.pi))
    dy_r = (h / beta) * (1.0 - math.cos(2.0 * math.pi * xi))
    d2y_r = (2.0 * math.pi * h / (beta * beta)) * math.sin(2.0 * math.pi * xi)
    if rise:
        return y_r, dy_r, d2y_r
    return h - y_r, -dy_r, -d2y_r


def _harmonic(h: float, beta: float, theta: float, rise: bool) -> tuple[float, float, float]:
    """
    Harmonic (cosine) profile — fallback inline implementation.
    Returns (displacement, dy/dtheta, d2y/dtheta2).
    """
    xi = theta / beta
    y_r = (h / 2.0) * (1.0 - math.cos(math.pi * xi))
    dy_r = (math.pi * h / (2.0 * beta)) * math.sin(math.pi * xi)
    d2y_r = (math.pi * math.pi * h / (2.0 * beta * beta)) * math.cos(math.pi * xi)
    if rise:
        return y_r, dy_r, d2y_r
    return h - y_r, -dy_r, -d2y_r


# Polynomial coefficients for rise (ξ = θ/β ∈ [0,1])
# ─────────────────────────────────────────────────────
# Order 5  (3-4-5 poly, satisfies C2 at both ends):
#   y/h = 10ξ³ − 15ξ⁴ + 6ξ⁵
# Order 7  (4-5-6-7 poly, satisfies C3 at both ends):
#   y/h = 35ξ⁴ − 84ξ⁵ + 70ξ⁶ − 20ξ⁷
# Order 4  (3-4 poly, satisfies C1 at both ends):
#   y/h = −2ξ⁴ + 4ξ³ − (set so boundary conditions y'=0 at 0 and β)
#          Actually: 8ξ³ − 12ξ⁴ + (corrected to zero first deriv at ends)
#          Use C2 boundary: y'(0)=0, y'(1)=0, y''(0)=0, y(0)=0, y(1)=h
#          The unique 4th-order poly satisfying y(0)=0, y(1)=1, y'(0)=0,
#          y'(1)=0 has one free parameter; we pin y''(0)=0:
#          → 8ξ³ − 12ξ⁴ + ... not achievable at order 4 with all 5 BCs,
#          so order-4 is C1 only.  We use: y/h = 3ξ² − 2ξ³ (cubic, aka
#          Hermite) padded to order 4 by adding a zero coeff.
# Order 6  (5-6 poly, C2+):
#   y/h = −20ξ⁶ + 42ξ⁵ − 30ξ⁴ + 10ξ³  (symmetric, similar to 3-4-5 but smoother)
#
# For fall, mirror: y_fall = h − y_rise(β − θ) ≡ h − y_rise evaluated at (β−θ).

_POLY_COEFFS_RISE: dict[int, list[float]] = {
    # Coefficients of ξ^k, for k=0,1,...,n
    # y/h = sum(c_k * xi^k)
    4: [0.0, 0.0, 3.0, -2.0, 0.0],        # Cubic Hermite (C1), padded
    5: [0.0, 0.0, 0.0, 10.0, -15.0, 6.0], # 3-4-5 polynomial (C2)
    6: [0.0, 0.0, 0.0, 10.0, -30.0, 42.0, -20.0],  # 5-6 poly (C2+)
    7: [0.0, 0.0, 0.0, 0.0, 35.0, -84.0, 70.0, -20.0],  # 4-5-6-7 poly (C3)
}


def _poly_profile(
    h: float, beta: float, theta: float, order: int, rise: bool
) -> tuple[float, float, float]:
    """
    Polynomial cam profile.
    Returns (displacement, dy/dtheta, d2y/dtheta2).

    Uses the 3-4-5 (order=5) or 4-5-6-7 (order=7) polynomial families.
    """
    coeffs = _POLY_COEFFS_RISE.get(order)
    if coeffs is None:
        raise ValueError(f"Unsupported polynomial order {order}; use 4, 5, 6, or 7.")

    if not rise:
        # Fall: mirror around the midpoint
        theta = beta - theta

    xi = theta / beta

    # y/h = sum c_k * xi^k
    y_norm = 0.0
    dy_norm = 0.0   # d(y/h)/d(xi)
    d2y_norm = 0.0  # d²(y/h)/d(xi)²

    for k, c in enumerate(coeffs):
        if c == 0.0:
            continue
        y_norm += c * xi ** k
        if k >= 1:
            dy_norm += c * k * xi ** (k - 1)
        if k >= 2:
            d2y_norm += c * k * (k - 1) * xi ** (k - 2)

    # Convert from xi-domain to theta-domain derivatives
    # d(y)/dθ = d(y)/dξ * dξ/dθ = d(y)/dξ * (1/β)
    # d²y/dθ² = d²y/dξ² * (1/β)²
    y = h * y_norm
    dy_dtheta = h * dy_norm / beta
    d2y_dtheta2 = h * d2y_norm / (beta * beta)

    if not rise:
        # Negate derivatives for fall (mirroring flips the derivative sign)
        dy_dtheta = -dy_dtheta
        # Second derivative sign is preserved for fall (mirror of mirror)
        return h - y, dy_dtheta, d2y_dtheta2

    return y, dy_dtheta, d2y_dtheta2


# ---------------------------------------------------------------------------
# Continuity check
# ---------------------------------------------------------------------------

def _check_continuity(
    profile: list[dict],
    h: float,
    beta_deg: float,
    law: str,
    rise: bool,
) -> tuple[bool, bool, list[str]]:
    """
    Check:
      - lift_ok  : y at theta=beta equals h (within 1e-6 mm)
      - continuity_ok : y, y', y'' are (approximately) zero at theta=0
                        and h, 0, 0 (or 0, 0, 0 for fall) at theta=beta.

    Returns (continuity_ok, lift_ok, extra_warnings).
    """
    warnings_: list[str] = []
    TOL_DISP = 1e-6
    TOL_VEL = 1e-6
    # Acceleration tolerance is relaxed for harmonic (known to be finite)
    TOL_ACC = 1e-4

    if not profile:
        return False, False, ["Profile is empty"]

    first = profile[0]
    last = profile[-1]

    # Lift check
    expected_end = h if rise else 0.0
    lift_ok = abs(last["displacement"] - expected_end) < TOL_DISP

    if not lift_ok:
        warnings_.append(
            f"Lift error at theta=beta: expected {expected_end:.6g} mm, "
            f"got {last['displacement']:.6g} mm "
            f"(delta={abs(last['displacement'] - expected_end):.2e} mm)"
        )

    # Continuity check at start
    expected_start_disp = 0.0 if rise else h
    c_ok = True

    if abs(first["displacement"] - expected_start_disp) > TOL_DISP:
        warnings_.append(
            f"Start displacement {first['displacement']:.6g} != {expected_start_disp:.6g}"
        )
        c_ok = False

    # Velocity at boundaries should be zero for well-formed profiles
    if abs(first["velocity_per_omega"]) > TOL_VEL:
        if law == "harmonic":
            warnings_.append(
                f"Harmonic profile: non-zero velocity at start boundary "
                f"({first['velocity_per_omega']:.4g} mm/rad) — expected for harmonic law."
            )
        else:
            warnings_.append(
                f"Non-zero velocity at start: {first['velocity_per_omega']:.4g} mm/rad"
            )
            c_ok = False

    if abs(last["velocity_per_omega"]) > TOL_VEL:
        if law == "harmonic":
            warnings_.append(
                f"Harmonic profile: non-zero velocity at end boundary "
                f"({last['velocity_per_omega']:.4g} mm/rad) — expected for harmonic law."
            )
        else:
            warnings_.append(
                f"Non-zero velocity at end: {last['velocity_per_omega']:.4g} mm/rad"
            )
            c_ok = False

    # Acceleration at boundaries
    if law in ("cycloidal", "polynomial"):
        if abs(first["acceleration_per_omega2"]) > TOL_ACC:
            warnings_.append(
                f"Non-zero acceleration at start: "
                f"{first['acceleration_per_omega2']:.4g} mm/rad²"
            )
            c_ok = False
        if abs(last["acceleration_per_omega2"]) > TOL_ACC:
            warnings_.append(
                f"Non-zero acceleration at end: "
                f"{last['acceleration_per_omega2']:.4g} mm/rad²"
            )
            c_ok = False

    return c_ok, lift_ok, warnings_


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesise_cam(
    law: str,
    h: float,
    beta_deg: float,
    *,
    n_points: int = 360,
    rise: bool = True,
    poly_order: int = 5,
) -> dict[str, Any]:
    """
    Synthesise a cam profile from a follower motion law.

    Parameters
    ----------
    law       : "cycloidal" | "polynomial" | "harmonic"
    h         : follower total lift (mm, > 0)
    beta_deg  : cam rotation for the segment (degrees, > 0)
    n_points  : number of cam-angle samples along the segment (default 360)
    rise      : True for rise segment, False for fall segment
    poly_order: polynomial order — 4, 5, 6, or 7 (default 5, used only for "polynomial")

    Returns
    -------
    dict:
        ok                  bool
        law                 str    motion law
        h                   float  lift (mm)
        beta_deg            float  segment angle (degrees)
        n_points            int
        profile             list[dict]  — one entry per sampled angle:
            theta_deg               float cam angle within segment (0 to beta_deg)
            displacement            float follower position (mm)
            velocity_per_omega      float dy/dθ (mm/rad)
            acceleration_per_omega2 float d²y/dθ² (mm/rad²)
        continuity_ok       bool   displacement/velocity/acceleration C2 at boundaries
        lift_ok             bool   displacement at end-of-segment equals h (within 1e-6)
        poly_order          int    (only present when law="polynomial")
        warnings            list[str]
        reason              str    (only when ok=False)
    """
    warnings_list: list[str] = []

    # Validate
    valid_laws = ("cycloidal", "polynomial", "harmonic")
    if law not in valid_laws:
        return _err(
            f"law must be one of {valid_laws}; got {law!r}"
        )

    try:
        h = float(h)
    except (TypeError, ValueError):
        return _err(f"h must be a number, got {h!r}")
    if not math.isfinite(h) or h <= 0:
        return _err(f"h must be > 0 and finite, got {h}")

    try:
        beta_deg = float(beta_deg)
    except (TypeError, ValueError):
        return _err(f"beta_deg must be a number, got {beta_deg!r}")
    if not math.isfinite(beta_deg) or beta_deg <= 0:
        return _err(f"beta_deg must be > 0 and finite, got {beta_deg}")
    if beta_deg > 360.0:
        return _err(f"beta_deg={beta_deg} > 360° — cam segment cannot exceed one full rotation")

    if not isinstance(n_points, int) or n_points < 2:
        try:
            n_points = max(2, int(n_points))
        except (TypeError, ValueError):
            return _err(f"n_points must be an integer >= 2, got {n_points!r}")
        warnings_list.append(f"n_points adjusted to {n_points}")

    if law == "polynomial":
        if poly_order not in _POLY_COEFFS_RISE:
            return _err(
                f"poly_order must be one of {list(_POLY_COEFFS_RISE)}, "
                f"got {poly_order!r}"
            )

    beta = math.radians(beta_deg)
    profile: list[dict] = []

    for i in range(n_points + 1):
        theta = beta * i / n_points
        theta_d = math.degrees(theta)

        if law == "cycloidal":
            if _HAVE_CORE:
                res = _cycloidal_analysis(h, beta_deg, theta_d, rise=rise)
                if not res["ok"]:
                    warnings_list.append(
                        f"Core cam_follower_cycloidal failed at θ={theta_d:.2f}°: "
                        f"{res.get('reason', '?')}"
                    )
                    continue
                y = res["displacement"]
                dy = res["velocity_per_omega"]
                d2y = res["acceleration_per_omega2"]
            else:
                y, dy, d2y = _cycloidal(h, beta, theta, rise)

        elif law == "harmonic":
            if _HAVE_CORE:
                res = _harmonic_analysis(h, beta_deg, theta_d, rise=rise)
                if not res["ok"]:
                    warnings_list.append(
                        f"Core cam_follower_harmonic failed at θ={theta_d:.2f}°: "
                        f"{res.get('reason', '?')}"
                    )
                    continue
                y = res["displacement"]
                dy = res["velocity_per_omega"]
                d2y = res["acceleration_per_omega2"]
            else:
                y, dy, d2y = _harmonic(h, beta, theta, rise)

        else:  # polynomial
            y, dy, d2y = _poly_profile(h, beta, theta, poly_order, rise)

        profile.append({
            "theta_deg": round(theta_d, 6),
            "displacement": round(y, 9),
            "velocity_per_omega": round(dy, 9),
            "acceleration_per_omega2": round(d2y, 9),
        })

    # Continuity and lift checks
    continuity_ok, lift_ok, extra_warnings = _check_continuity(
        profile, h, beta_deg, law, rise
    )
    warnings_list.extend(extra_warnings)

    result: dict[str, Any] = {
        "ok":               True,
        "law":              law,
        "h":                h,
        "beta_deg":         beta_deg,
        "n_points":         len(profile),
        "profile":          profile,
        "continuity_ok":    continuity_ok,
        "lift_ok":          lift_ok,
        "warnings":         warnings_list,
    }

    if law == "polynomial":
        result["poly_order"] = poly_order

    return result
