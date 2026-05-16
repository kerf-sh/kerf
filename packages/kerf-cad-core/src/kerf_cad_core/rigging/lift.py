"""
kerf_cad_core.rigging.lift — pure-Python lifting & rigging engineering.

Implements eleven public functions:

  sling_tension(load_kg, angle_deg, *, n_legs, design_factor)
      Sling tension from load-angle factor 1/sin θ. Returns tension per leg
      after dividing by number of effective legs.

  multi_leg_share(load_kg, sling_lengths, *, n_legs, mode, design_factor)
      Per-leg load share for 2-, 3-, or 4-leg lifts. Supports equal-leg and
      unequal-leg geometry; rigid vs flexible (statically-indeterminate) mode.

  cg_pick_loads(load_kg, cg_x, cg_y, pick_points)
      Centre-of-gravity based per-pick-point vertical load from geometry.
      pick_points is a list of (x, y) tuples in plan. Returns list of loads
      and tip-over stability flag.

  sling_wll_derate(rated_wll_kg, angle_deg, *, hardware_type, n_legs)
      Angular derating of WLL for slings, shackles, and eyebolts per
      ASME B30.9 / B30.26 tables.

  wire_rope_capacity(diameter_mm, grade, *, construction, design_factor)
      Minimum breaking force and WLL for wire rope by diameter & grade.

  chain_capacity(size_mm, grade, *, design_factor)
      WLL for alloy steel chain (Grade 80 / Grade 100) by chain size.

  synthetic_sling_capacity(width_mm, ply, *, material, hitch, design_factor)
      WLL for flat-web and round synthetic slings by width, ply, material.

  spreader_beam_check(load_kg, span_m, *, section, Fy_MPa, design_factor)
      Bending and column (compression) check for a spreader/lifting beam.
      Supports 'tube_square', 'tube_round', 'wide_flange' section types.

  padeye_check(load_kN, plate_thickness_mm, hole_diameter_mm,
               pin_diameter_mm, *, Fy_MPa, design_factor)
      Simplified padeye/lug check: tension through net section, bearing on
      pin, and double-shear-out (two shear planes).

  tip_over_two_crane(total_load_kg, crane_a_radius_m, crane_b_radius_m,
                     lift_point_a_x, lift_point_b_x, cg_x)
      Two-crane tip-over / load share. Resolves vertical reactions at two
      crane hooks from CG position. Flags if either crane is overloaded.

  crane_radius_interpolate(radius_m, chart_table)
      Interpolate (or extrapolate-conservatively) crane capacity from a
      radius–capacity chart table provided as a list of (radius_m, capacity_t).

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise. Warnings are accumulated in the "warnings" list; the
result is still marked ok=True so callers can choose how to handle them.

Warning conditions (never raise):
  - Sling angle < 30° (load-angle factor > 2.0) → SLING_ANGLE_TOO_SHALLOW
  - WLL exceeded → WLL_EXCEEDED
  - Lift is unstable (CG outside pick triangle/line) → UNSTABLE

Units
-----
Unless stated otherwise:
  mass     — kilograms (kg); weight = mass × g (g = 9.80665 m/s²)
  forces   — kilonewtons (kN) where labelled; Newtons (N) otherwise
  lengths  — metres (m) unless mm is appended to the variable name
  stress   — MPa (megapascals)
  angles   — degrees (°)

References
----------
ASME B30.9-2018  — Slings
ASME B30.26-2015 — Rigging Hardware
EN 13155:2003    — Non-fixed load lifting attachments
LEEA 001-2019    — LEEA Code of Practice
Rigging Engineering Basics, J.D. Isbester, 2013

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_G = 9.80665  # standard gravity, m/s²

# Minimum sling angle (degrees from horizontal) before warning
_MIN_SLING_ANGLE_DEG = 30.0

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


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


def _guard_range(name: str, value: Any, lo: float, hi: float) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v < lo or v > hi:
        return f"{name} must be in [{lo}, {hi}], got {v}"
    return None


# ---------------------------------------------------------------------------
# 1. sling_tension
# ---------------------------------------------------------------------------


def sling_tension(
    load_kg: float,
    angle_deg: float,
    *,
    n_legs: int = 1,
    design_factor: float = 5.0,
) -> dict:
    """
    Sling tension from load-angle factor 1/sin θ.

    The load-angle factor (LAF) amplifies the sling tension as the sling
    angle from horizontal decreases:

        T_leg = (W / n_legs) / sin(θ)
        LAF   = 1 / sin(θ)

    where W = load_kg × g (kN), θ is the angle from horizontal to the sling,
    and n_legs is the number of legs assumed to share equally.

    Parameters
    ----------
    load_kg : float
        Total suspended load (kg). Must be > 0.
    angle_deg : float
        Angle of the sling from horizontal (degrees). Must be in (0°, 90°].
        Values < 30° trigger the SLING_ANGLE_TOO_SHALLOW warning.
    n_legs : int
        Number of equal-share sling legs (default 1). Must be 1–8.
    design_factor : float
        Design factor (safety factor) applied to find the required WLL:
        required_wll_kg = tension_kg / design_factor ... this is informational.
        Default 5 (typical rigging factor).

    Returns
    -------
    dict
        ok                 : True
        tension_per_leg_kN : sling tension per leg (kN)
        tension_per_leg_kg : sling tension per leg expressed as mass (kg)
        load_angle_factor  : 1/sin(θ)
        angle_deg          : angle used (°)
        n_legs             : number of legs
        design_factor      : design factor used
        required_wll_kg    : minimum WLL required per sling (kg)
        warnings           : list of warning strings
    """
    err = _guard_positive("load_kg", load_kg)
    if err:
        return _err(err)
    err = _guard_range("angle_deg", angle_deg, 0.0 + 1e-9, 90.0)
    if err:
        return _err(err)
    if not isinstance(n_legs, int) or n_legs < 1 or n_legs > 8:
        return _err(f"n_legs must be an integer in [1, 8], got {n_legs!r}")
    err = _guard_positive("design_factor", design_factor)
    if err:
        return _err(err)

    warnings: list[str] = []

    theta_rad = math.radians(float(angle_deg))
    sin_theta = math.sin(theta_rad)

    laf = 1.0 / sin_theta  # load-angle factor
    W_kN = float(load_kg) * _G / 1000.0  # total weight in kN

    tension_kN = (W_kN / float(n_legs)) * laf
    tension_kg = tension_kN * 1000.0 / _G
    required_wll_kg = tension_kg / float(design_factor)

    if float(angle_deg) < _MIN_SLING_ANGLE_DEG:
        warnings.append(
            f"SLING_ANGLE_TOO_SHALLOW: sling angle {angle_deg:.1f}° < 30°; "
            f"load-angle factor is {laf:.2f}x — excessive sling tension."
        )

    return {
        "ok": True,
        "tension_per_leg_kN": tension_kN,
        "tension_per_leg_kg": tension_kg,
        "load_angle_factor": laf,
        "angle_deg": float(angle_deg),
        "n_legs": n_legs,
        "total_load_kg": float(load_kg),
        "design_factor": float(design_factor),
        "required_wll_kg": required_wll_kg,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. multi_leg_share
# ---------------------------------------------------------------------------


def multi_leg_share(
    load_kg: float,
    sling_lengths: list[float],
    *,
    n_legs: int | None = None,
    mode: str = "flexible",
    design_factor: float = 5.0,
) -> dict:
    """
    Per-leg load share for 2, 3, or 4-leg lifts.

    Flexible mode (default, statically-determinate approximation):
        A flexible rigging system with unequal leg lengths is treated as if
        the load distributes inversely proportional to each leg's stiffness
        contribution. For equal-length slings, load is shared equally.
        For 4-leg flexible rigs only 3 legs are assumed statically active
        (one leg deemed slack — conservative per LEEA).

    Rigid mode (spreader-assisted, statically-determined geometry):
        Load distributes inversely proportional to the horizontal distance
        from each attachment point to the CG — this requires pick_points
        and is better handled by cg_pick_loads(); here for rigid mode
        equal-leg behaviour is forced.

    Parameters
    ----------
    load_kg : float
        Total load (kg). Must be > 0.
    sling_lengths : list[float]
        List of sling lengths (m). Length must match n_legs or be 2, 3, or 4.
        All values must be > 0.
    n_legs : int | None
        Override for number of legs. If None, inferred from sling_lengths.
    mode : str
        "flexible" (default) or "rigid".
    design_factor : float
        Design factor for required WLL computation.

    Returns
    -------
    dict
        ok               : True
        n_legs           : number of legs
        leg_loads_kg     : list of per-leg loads (kg)
        leg_loads_kN     : list of per-leg loads (kN)
        required_wll_kg  : max leg load / design_factor — minimum WLL per sling
        mode             : mode used
        warnings         : list of warning strings
    """
    err = _guard_positive("load_kg", load_kg)
    if err:
        return _err(err)

    if not isinstance(sling_lengths, (list, tuple)) or len(sling_lengths) == 0:
        return _err("sling_lengths must be a non-empty list of positive lengths (m)")

    for i, sl in enumerate(sling_lengths):
        e = _guard_positive(f"sling_lengths[{i}]", sl)
        if e:
            return _err(e)

    actual_n = len(sling_lengths)
    if n_legs is None:
        n_legs = actual_n
    else:
        if not isinstance(n_legs, int) or n_legs < 2 or n_legs > 4:
            return _err(f"n_legs must be 2, 3, or 4, got {n_legs!r}")
        if actual_n != n_legs:
            return _err(
                f"sling_lengths has {actual_n} entries but n_legs={n_legs}"
            )

    if n_legs < 2 or n_legs > 4:
        return _err(f"n_legs must be 2, 3, or 4 for multi-leg share, got {n_legs}")

    err = _guard_positive("design_factor", design_factor)
    if err:
        return _err(err)

    mode_clean = str(mode).strip().lower()
    if mode_clean not in ("flexible", "rigid"):
        return _err(f"mode must be 'flexible' or 'rigid', got {mode!r}")

    warnings: list[str] = []
    W = float(load_kg) * _G / 1000.0  # kN

    lengths = [float(sl) for sl in sling_lengths]

    if mode_clean == "rigid":
        # Rigid: equal share (geometry handled by cg_pick_loads)
        shares = [1.0 / n_legs] * n_legs

    else:
        # Flexible: unequal-leg load distribution
        # For a flexible rig the shorter slings carry more load (tighter angle).
        # Standard approximation: share inversely proportional to leg length
        # (shorter sling is steeper → higher sin θ → lower tension, but also
        # reaches the apex at a steeper angle so it carries more vertical load
        # when all apex heights are equal).
        # Rigorous treatment needs geometry; this uses the industry shorthand:
        # equal share for equal lengths, conservative equal-share for 4-leg
        # (treat as 3-leg active, one leg slack).

        if n_legs == 4:
            # 4-leg flexible: only 3 legs assumed active (LEEA / ASME B30.9)
            # Identify the 3 most-loaded (shortest) legs
            sorted_idx = sorted(range(4), key=lambda i: lengths[i])
            active_idx = sorted(sorted_idx[:3])  # 3 shortest = most loaded
            slack_idx = sorted_idx[3]
            warnings.append(
                f"FLEXIBLE_4LEG: leg {slack_idx + 1} (longest, "
                f"{lengths[slack_idx]:.3f} m) treated as slack; "
                "load distributed over 3 active legs."
            )
            active_lengths = [lengths[i] for i in active_idx]
            inv = [1.0 / l for l in active_lengths]
            total_inv = sum(inv)
            raw_shares_active = [v / total_inv for v in inv]
            shares = [0.0] * 4
            for pos, idx in enumerate(active_idx):
                shares[idx] = raw_shares_active[pos]
        else:
            # 2-leg or 3-leg: distribute inversely proportional to length
            inv = [1.0 / l for l in lengths]
            total_inv = sum(inv)
            shares = [v / total_inv for v in inv]

    leg_loads_kN = [W * s for s in shares]
    leg_loads_kg = [f * 1000.0 / _G for f in leg_loads_kN]
    required_wll_kg = max(leg_loads_kg) / float(design_factor)

    return {
        "ok": True,
        "n_legs": n_legs,
        "leg_loads_kg": leg_loads_kg,
        "leg_loads_kN": leg_loads_kN,
        "required_wll_kg": required_wll_kg,
        "mode": mode_clean,
        "total_load_kg": float(load_kg),
        "design_factor": float(design_factor),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. cg_pick_loads
# ---------------------------------------------------------------------------


def cg_pick_loads(
    load_kg: float,
    cg_x: float,
    cg_y: float,
    pick_points: list[tuple[float, float]],
) -> dict:
    """
    Per-pick-point vertical load from centre-of-gravity geometry.

    Distributes the total load to each pick point based on plan-view CG
    position using virtual-work / moment equilibrium.

    For 2 pick points (collinear), the load distributes by lever-arm ratio.
    For 3 pick points (triangle), a planar moment equilibrium is solved.
    For 4 pick points (quadrilateral), the load is split into two triangles
    and contributions summed (flexible assumption).

    The function also checks whether the CG lies inside the pick polygon
    (convex hull check). If the CG is outside, the lift is flagged UNSTABLE.

    Parameters
    ----------
    load_kg : float
        Total suspended load (kg). Must be > 0.
    cg_x, cg_y : float
        Centre-of-gravity position in plan (same units as pick_points, m).
    pick_points : list of (x, y)
        List of 2, 3, or 4 pick-point coordinates (m) in plan view.

    Returns
    -------
    dict
        ok               : True
        pick_loads_kg    : list of per-pick-point vertical loads (kg)
        pick_loads_kN    : list of per-pick-point vertical loads (kN)
        pick_shares      : fractional share (0–1) per pick point
        cg_inside        : True if CG lies inside the pick polygon
        warnings         : list of warning strings
    """
    err = _guard_positive("load_kg", load_kg)
    if err:
        return _err(err)
    for v in (cg_x, cg_y):
        if not math.isfinite(float(v)):
            return _err(f"cg_x and cg_y must be finite numbers")

    if not isinstance(pick_points, (list, tuple)) or len(pick_points) < 2:
        return _err("pick_points must be a list of 2, 3, or 4 (x, y) tuples")
    if len(pick_points) > 4:
        return _err("pick_points supports at most 4 points")

    pts = []
    for i, p in enumerate(pick_points):
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            return _err(f"pick_points[{i}] must be a (x, y) tuple of numbers")
        if not (math.isfinite(x) and math.isfinite(y)):
            return _err(f"pick_points[{i}] coordinates must be finite")
        pts.append((x, y))

    n = len(pts)
    cg = (float(cg_x), float(cg_y))
    W = float(load_kg)
    warnings: list[str] = []

    # ---- Stability check: CG inside pick polygon ---------------------------
    cg_inside = _point_in_polygon(cg, pts)
    if not cg_inside:
        warnings.append(
            "UNSTABLE: centre of gravity lies outside the pick-point polygon; "
            "load will tip toward the near edge."
        )

    # ---- Load distribution -------------------------------------------------
    if n == 2:
        # 1-D lever arm: project CG onto the line between P0 and P1
        p0, p1 = pts[0], pts[1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        span = math.hypot(dx, dy)
        if span < 1e-12:
            return _err("pick_points[0] and pick_points[1] are coincident")
        # Parameter t along the line
        t = ((cg[0] - p0[0]) * dx + (cg[1] - p0[1]) * dy) / (span ** 2)
        # Clamp to [0,1] for safety (outside the span → one leg goes to zero/negative)
        t = max(0.0, min(1.0, t))
        shares = [1.0 - t, t]

    elif n == 3:
        # Barycentric coordinates in the triangle
        shares = _barycentric(cg, pts[0], pts[1], pts[2])
        # Clamp negatives (CG outside)
        shares = [max(0.0, s) for s in shares]
        total = sum(shares)
        if total < 1e-12:
            shares = [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
        else:
            shares = [s / total for s in shares]

    else:
        # 4 points: average of both diagonal decompositions to avoid bias.
        # Decomposition A: triangles (0-1-2) and (0-2-3)
        # Decomposition B: triangles (0-1-3) and (1-2-3)
        # Average the two to get a symmetric result for symmetric inputs.
        def _quad_shares_via_diagonal(cg_, p_, i0, i1, i2, i3):
            """Return 4-element share list using diagonal i0-i2."""
            bA = _barycentric(cg_, p_[i0], p_[i1], p_[i2])
            bB = _barycentric(cg_, p_[i0], p_[i2], p_[i3])
            aA = abs(_triangle_area(p_[i0], p_[i1], p_[i2]))
            aB = abs(_triangle_area(p_[i0], p_[i2], p_[i3]))
            tot = aA + aB if (aA + aB) > 1e-12 else 1.0
            wA, wB = aA / tot, aB / tot
            c_ = [0.0] * 4
            # Triangle A contributions: indices i0, i1, i2
            c_[i0] += wA * bA[0]
            c_[i1] += wA * bA[1]
            c_[i2] += wA * bA[2]
            # Triangle B contributions: indices i0, i2, i3
            c_[i0] += wB * bB[0]
            c_[i2] += wB * bB[1]
            c_[i3] += wB * bB[2]
            return c_

        c1 = _quad_shares_via_diagonal(cg, pts, 0, 1, 2, 3)
        c2 = _quad_shares_via_diagonal(cg, pts, 1, 2, 3, 0)
        # Average both decompositions
        c_avg = [(c1[k] + c2[k]) / 2.0 for k in range(4)]
        shares_raw = [max(0.0, v) for v in c_avg]
        total = sum(shares_raw)
        shares = [v / total for v in shares_raw] if total > 1e-12 else [0.25] * 4

    pick_loads_kg = [W * s for s in shares]
    pick_loads_kN = [f * _G / 1000.0 for f in pick_loads_kg]

    return {
        "ok": True,
        "pick_loads_kg": pick_loads_kg,
        "pick_loads_kN": pick_loads_kN,
        "pick_shares": shares,
        "cg_inside": cg_inside,
        "total_load_kg": W,
        "warnings": warnings,
    }


def _triangle_area(p0: tuple, p1: tuple, p2: tuple) -> float:
    """Signed area of a triangle (positive = CCW)."""
    return 0.5 * (
        (p1[0] - p0[0]) * (p2[1] - p0[1])
        - (p2[0] - p0[0]) * (p1[1] - p0[1])
    )


def _barycentric(p: tuple, a: tuple, b: tuple, c: tuple) -> list[float]:
    """Barycentric coordinates of point p in triangle (a, b, c)."""
    denom = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(denom) < 1e-15:
        return [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
    u = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / denom
    v = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / denom
    w = 1.0 - u - v
    return [u, v, w]


def _point_in_polygon(p: tuple, poly: list[tuple]) -> bool:
    """
    Ray-casting point-in-polygon test. Returns True if p is inside poly
    (or on the boundary). Works for convex and concave polygons.
    """
    n = len(poly)
    inside = False
    px, py = p
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# 4. sling_wll_derate
# ---------------------------------------------------------------------------

# ASME B30.9 angular derating factors for slings (vertical = 1.00)
# Angle from vertical (0° = vertical, 90° = horizontal)
# Tabulated as (angle_from_vertical_deg, derate_factor)
_SLING_DERATE_TABLE: list[tuple[float, float]] = [
    (0,   1.000),
    (30,  0.866),  # sin 60°
    (45,  0.707),  # sin 45°
    (60,  0.500),  # sin 30°
]

# Eyebolt angular derate per ASME B30.26 (angle from axial = 0° = on-axis)
_EYEBOLT_DERATE_TABLE: list[tuple[float, float]] = [
    (0,  1.000),
    (15, 0.500),
    (30, 0.333),
    (45, 0.250),
    (90, 0.100),  # lateral load — severe derate
]

# Shackle: minimal angular sensitivity (designed for angular loads)
# ASME B30.26: full WLL in any direction along the pin axis plane.
# Off-plane loading reduces WLL by ~25% at 45°.
_SHACKLE_DERATE_TABLE: list[tuple[float, float]] = [
    (0,  1.000),
    (45, 0.750),
    (90, 0.500),
]


def _interpolate_table(
    angle_deg: float, table: list[tuple[float, float]]
) -> float:
    """Linear interpolation / clamped extrapolation on a monotone table."""
    if angle_deg <= table[0][0]:
        return table[0][1]
    if angle_deg >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        a0, f0 = table[i]
        a1, f1 = table[i + 1]
        if a0 <= angle_deg <= a1:
            t = (angle_deg - a0) / (a1 - a0)
            return f0 + t * (f1 - f0)
    return table[-1][1]


def sling_wll_derate(
    rated_wll_kg: float,
    angle_deg: float,
    *,
    hardware_type: str = "sling",
    n_legs: int = 1,
) -> dict:
    """
    Angular derating of WLL for slings, shackles, and eyebolts.

    For slings, angle_deg is the angle from vertical (0° = straight vertical
    pull, 90° = horizontal — which is not a valid rigging configuration).
    For eyebolts, angle_deg is the angle from the bolt axis.
    For shackles, angle_deg is the off-plane angle.

    Parameters
    ----------
    rated_wll_kg : float
        Rated working load limit (kg) at the reference angle (0° = on-axis).
    angle_deg : float
        Loading angle (degrees). For slings: angle from vertical [0, 90).
        For eyebolts: angle from bolt axis [0, 90].
        For shackles: off-plane angle [0, 90].
    hardware_type : str
        "sling" (default), "eyebolt", or "shackle".
    n_legs : int
        Number of legs (1–8) — multiplies the derated WLL for multi-leg.

    Returns
    -------
    dict
        ok                 : True
        derated_wll_kg     : effective WLL after angular derating (kg)
        total_wll_kg       : derated_wll_kg × n_legs
        derate_factor      : multiplier applied
        hardware_type      : type used
        angle_deg          : angle used
        warnings           : list of warning strings
    """
    err = _guard_positive("rated_wll_kg", rated_wll_kg)
    if err:
        return _err(err)
    err = _guard_range("angle_deg", angle_deg, 0.0, 90.0)
    if err:
        return _err(err)
    if not isinstance(n_legs, int) or n_legs < 1 or n_legs > 8:
        return _err(f"n_legs must be an integer in [1, 8], got {n_legs!r}")

    hw = str(hardware_type).strip().lower()
    if hw == "sling":
        table = _SLING_DERATE_TABLE
    elif hw == "eyebolt":
        table = _EYEBOLT_DERATE_TABLE
    elif hw == "shackle":
        table = _SHACKLE_DERATE_TABLE
    else:
        return _err(f"hardware_type must be 'sling', 'eyebolt', or 'shackle', got {hardware_type!r}")

    warnings: list[str] = []

    derate = _interpolate_table(float(angle_deg), table)
    derated = float(rated_wll_kg) * derate
    total_wll = derated * float(n_legs)

    if float(angle_deg) > 60.0 and hw == "sling":
        warnings.append(
            f"SLING_ANGLE_TOO_SHALLOW: sling from-vertical angle {angle_deg:.1f}° > 60° "
            f"(from-horizontal < 30°); derate factor is {derate:.3f}."
        )

    return {
        "ok": True,
        "derated_wll_kg": derated,
        "total_wll_kg": total_wll,
        "derate_factor": derate,
        "hardware_type": hw,
        "rated_wll_kg": float(rated_wll_kg),
        "angle_deg": float(angle_deg),
        "n_legs": n_legs,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. wire_rope_capacity
# ---------------------------------------------------------------------------

# Wire rope minimum breaking force (MBF) tables (kN) keyed by:
#   (diameter_mm, grade) → MBF_kN
# Grades: "6x19_iwrc_1570" (standard), "6x19_iwrc_1770", "6x37_iwrc_1570",
#         "6x36_ws_1770", "8x19_iwrc_1570"
# Source: Wire Rope Technical Board (WRTB) catalogue, approximate values.
_WIRE_ROPE_MBF: dict[tuple[float, str], float] = {
    # diameter_mm, grade-string → MBF (kN)
    (8,  "6x19_iwrc_1570"):  38.1,
    (8,  "6x19_iwrc_1770"):  43.1,
    (10, "6x19_iwrc_1570"):  59.7,
    (10, "6x19_iwrc_1770"):  67.4,
    (12, "6x19_iwrc_1570"):  86.0,
    (12, "6x19_iwrc_1770"):  97.1,
    (13, "6x19_iwrc_1570"): 100.5,
    (13, "6x19_iwrc_1770"): 113.5,
    (16, "6x19_iwrc_1570"): 153.0,
    (16, "6x19_iwrc_1770"): 172.5,
    (18, "6x19_iwrc_1570"): 193.0,
    (18, "6x19_iwrc_1770"): 218.0,
    (20, "6x19_iwrc_1570"): 238.0,
    (20, "6x19_iwrc_1770"): 269.0,
    (22, "6x19_iwrc_1570"): 288.0,
    (22, "6x19_iwrc_1770"): 325.0,
    (24, "6x19_iwrc_1570"): 343.0,
    (24, "6x19_iwrc_1770"): 387.0,
    (26, "6x19_iwrc_1570"): 402.0,
    (26, "6x19_iwrc_1770"): 454.0,
    (28, "6x19_iwrc_1570"): 467.0,
    (28, "6x19_iwrc_1770"): 527.0,
    (32, "6x19_iwrc_1570"): 609.0,
    (32, "6x19_iwrc_1770"): 688.0,
    (36, "6x19_iwrc_1570"): 771.0,
    (36, "6x19_iwrc_1770"): 870.0,
    (40, "6x19_iwrc_1570"): 952.0,
    (40, "6x19_iwrc_1770"): 1075.0,
    # 6×37 IWRC
    (16, "6x37_iwrc_1570"): 145.0,
    (20, "6x37_iwrc_1570"): 226.0,
    (24, "6x37_iwrc_1570"): 326.0,
    (32, "6x37_iwrc_1570"): 577.0,
    # 6×36 WS (Warrington-Seale) 1770
    (20, "6x36_ws_1770"):   271.0,
    (24, "6x36_ws_1770"):   389.0,
    (32, "6x36_ws_1770"):   690.0,
}

_WIRE_ROPE_GRADES = sorted({g for (_, g) in _WIRE_ROPE_MBF})


def wire_rope_capacity(
    diameter_mm: float,
    grade: str = "6x19_iwrc_1570",
    *,
    construction: str | None = None,
    design_factor: float = 5.0,
) -> dict:
    """
    WLL for wire rope by diameter and grade.

    Parameters
    ----------
    diameter_mm : float
        Nominal wire rope diameter (mm). Must be in the built-in table.
        Available: 8, 10, 12, 13, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40 mm
        (not all grades cover all sizes; see grade notes).
    grade : str
        Wire rope grade / construction string. Valid values:
          "6x19_iwrc_1570" (default) — 6×19 IWRC, 1570 MPa wire
          "6x19_iwrc_1770"           — 6×19 IWRC, 1770 MPa wire
          "6x37_iwrc_1570"           — 6×37 IWRC, 1570 MPa wire
          "6x36_ws_1770"             — 6×36 Warrington-Seale, 1770 MPa wire
    construction : str | None
        Ignored (included in grade string). Present for API completeness.
    design_factor : float
        Design (safety) factor to derive WLL from MBF. Default 5.0 per
        AS 3569 / ASME B30.9 for standard lifting service.

    Returns
    -------
    dict
        ok                : True
        diameter_mm       : diameter used
        grade             : grade used
        mbf_kN            : minimum breaking force (kN)
        wll_kN            : working load limit = MBF / design_factor (kN)
        wll_kg            : working load limit (kg)
        design_factor     : design factor used
        warnings          : list
    """
    err = _guard_positive("diameter_mm", diameter_mm)
    if err:
        return _err(err)
    err = _guard_positive("design_factor", design_factor)
    if err:
        return _err(err)

    g = str(grade).strip().lower()
    d = float(diameter_mm)

    key = (d, g)
    if key not in _WIRE_ROPE_MBF:
        # Try to give a helpful error
        available_d = sorted({dd for (dd, _) in _WIRE_ROPE_MBF})
        available_g = sorted({gg for (_, gg) in _WIRE_ROPE_MBF})
        return _err(
            f"No data for diameter={diameter_mm} mm, grade='{grade}'. "
            f"Available diameters: {available_d}. Available grades: {available_g}."
        )

    mbf_kN = _WIRE_ROPE_MBF[key]
    wll_kN = mbf_kN / float(design_factor)
    wll_kg = wll_kN * 1000.0 / _G

    return {
        "ok": True,
        "diameter_mm": d,
        "grade": g,
        "mbf_kN": mbf_kN,
        "wll_kN": wll_kN,
        "wll_kg": wll_kg,
        "design_factor": float(design_factor),
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 6. chain_capacity
# ---------------------------------------------------------------------------

# Grade 80 and Grade 100 alloy chain WLL (tonnes) by chain size (mm, link diameter)
# Source: LEEA / manufacturer data (representative values)
# Stored as (size_mm, grade) → wll_t (metric tonnes)
_CHAIN_WLL: dict[tuple[float, str], float] = {
    # Grade 80
    (6,  "grade_80"):  1.12,
    (7,  "grade_80"):  1.50,
    (8,  "grade_80"):  2.00,
    (10, "grade_80"):  3.15,
    (13, "grade_80"):  5.30,
    (16, "grade_80"):  8.00,
    (19, "grade_80"): 11.2,
    (22, "grade_80"): 15.0,
    (26, "grade_80"): 21.2,
    (32, "grade_80"): 31.5,
    # Grade 100
    (6,  "grade_100"):  1.40,
    (7,  "grade_100"):  1.90,
    (8,  "grade_100"):  2.50,
    (10, "grade_100"):  4.00,
    (13, "grade_100"):  6.70,
    (16, "grade_100"): 10.0,
    (19, "grade_100"): 14.0,
    (22, "grade_100"): 19.0,
    (26, "grade_100"): 26.5,
    (32, "grade_100"): 40.0,
}


def chain_capacity(
    size_mm: float,
    grade: str = "grade_80",
    *,
    design_factor: float = 4.0,
) -> dict:
    """
    WLL for alloy steel chain by chain size and grade.

    Parameters
    ----------
    size_mm : float
        Chain link diameter (mm). Must be in the built-in table.
        Available: 6, 7, 8, 10, 13, 16, 19, 22, 26, 32 mm.
    grade : str
        Chain grade: "grade_80" (default) or "grade_100".
    design_factor : float
        Design factor. Default 4.0 per EN 818 / ASME B30.9 for chain.
        The WLL is already reduced from the proof load; design_factor here
        is applied as an additional service factor when specifying for lift.

    Returns
    -------
    dict
        ok            : True
        size_mm       : chain size used
        grade         : grade used
        wll_t         : catalogue working load limit (metric tonnes)
        wll_kg        : catalogue WLL (kg)
        wll_kN        : catalogue WLL (kN)
        effective_wll_kg : wll_kg / design_factor (if design_factor > 1)
        design_factor : design factor used
        warnings      : list
    """
    err = _guard_positive("size_mm", size_mm)
    if err:
        return _err(err)
    err = _guard_positive("design_factor", design_factor)
    if err:
        return _err(err)

    g = str(grade).strip().lower().replace(" ", "_").replace("-", "_")
    s = float(size_mm)

    key = (s, g)
    if key not in _CHAIN_WLL:
        available_s = sorted({ss for (ss, _) in _CHAIN_WLL})
        available_g = sorted({gg for (_, gg) in _CHAIN_WLL})
        return _err(
            f"No data for size={size_mm} mm, grade='{grade}'. "
            f"Available sizes: {available_s}. Grades: {available_g}."
        )

    wll_t = _CHAIN_WLL[key]
    wll_kg = wll_t * 1000.0
    wll_kN = wll_kg * _G / 1000.0
    effective_wll_kg = wll_kg / float(design_factor)

    return {
        "ok": True,
        "size_mm": s,
        "grade": g,
        "wll_t": wll_t,
        "wll_kg": wll_kg,
        "wll_kN": wll_kN,
        "effective_wll_kg": effective_wll_kg,
        "design_factor": float(design_factor),
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 7. synthetic_sling_capacity
# ---------------------------------------------------------------------------

# Flat-web sling WLL (kg) for single vertical hitch, by (width_mm, ply, material)
# Source: EN 1492-1 / ASME B30.9 representative values.
# material: "polyester" or "nylon"
_SYNTHETIC_WLL: dict[tuple[float, int, str], float] = {
    # (width_mm, ply, material) → WLL_kg (single vertical hitch)
    (25,  1, "polyester"):   1000,
    (25,  2, "polyester"):   2000,
    (50,  1, "polyester"):   2000,
    (50,  2, "polyester"):   4000,
    (75,  1, "polyester"):   3000,
    (75,  2, "polyester"):   6000,
    (100, 1, "polyester"):   4000,
    (100, 2, "polyester"):   8000,
    (150, 1, "polyester"):   6000,
    (150, 2, "polyester"):  12000,
    (200, 1, "polyester"):   8000,
    (200, 2, "polyester"):  16000,
    # Nylon: slightly higher elongation, approx same WLL (per EN 1492-1)
    (25,  1, "nylon"):   1000,
    (25,  2, "nylon"):   2000,
    (50,  1, "nylon"):   2000,
    (50,  2, "nylon"):   4000,
    (75,  1, "nylon"):   3200,
    (75,  2, "nylon"):   6300,
    (100, 1, "nylon"):   4000,
    (100, 2, "nylon"):   8000,
    (150, 1, "nylon"):   6300,
    (150, 2, "nylon"):  12500,
    (200, 1, "nylon"):   8000,
    (200, 2, "nylon"):  16000,
}

# Hitch mode factors (applied to the single-vertical WLL)
_HITCH_FACTORS: dict[str, float] = {
    "vertical":        1.00,
    "choker":          0.80,  # EN 1492-1: 75–80% depending on choker angle
    "basket":          2.00,  # basket doubles (straight path)
    "basket_45deg":    1.41,  # basket at 45° from vertical
    "basket_60deg":    1.00,  # basket at 60° from vertical (= 30° horizontal)
}


def synthetic_sling_capacity(
    width_mm: float,
    ply: int,
    *,
    material: str = "polyester",
    hitch: str = "vertical",
    design_factor: float = 7.0,
) -> dict:
    """
    WLL for flat-web synthetic slings by width, ply, and hitch type.

    Parameters
    ----------
    width_mm : float
        Sling width (mm). Available: 25, 50, 75, 100, 150, 200 mm.
    ply : int
        Number of plies (1 or 2).
    material : str
        "polyester" (default) or "nylon".
    hitch : str
        Hitch configuration:
          "vertical" (default) — straight pull, factor 1.0
          "choker"             — choker hitch, factor 0.80
          "basket"             — basket (double) hitch, factor 2.0
          "basket_45deg"       — basket at 45°, factor ~1.41
          "basket_60deg"       — basket at 60°, factor ~1.00
    design_factor : float
        Design factor. ASME B30.9 uses min. 5:1 for synthetic slings;
        default 7.0 is a commonly used value.

    Returns
    -------
    dict
        ok                : True
        width_mm          : width used
        ply               : ply used
        material          : material used
        hitch             : hitch type used
        hitch_factor      : multiplier applied
        base_wll_kg       : single-vertical WLL (kg)
        adjusted_wll_kg   : base_wll × hitch_factor
        effective_wll_kg  : adjusted_wll / design_factor
        design_factor     : design factor used
        warnings          : list
    """
    if not isinstance(ply, int) or ply not in (1, 2):
        return _err(f"ply must be 1 or 2, got {ply!r}")
    err = _guard_positive("width_mm", width_mm)
    if err:
        return _err(err)
    err = _guard_positive("design_factor", design_factor)
    if err:
        return _err(err)

    mat = str(material).strip().lower()
    h = str(hitch).strip().lower()

    if mat not in ("polyester", "nylon"):
        return _err(f"material must be 'polyester' or 'nylon', got {material!r}")
    if h not in _HITCH_FACTORS:
        valid = list(_HITCH_FACTORS.keys())
        return _err(f"hitch must be one of {valid}, got {hitch!r}")

    w = float(width_mm)
    key = (w, ply, mat)
    if key not in _SYNTHETIC_WLL:
        available_w = sorted({ww for (ww, _, _) in _SYNTHETIC_WLL})
        return _err(
            f"No data for width={width_mm} mm, ply={ply}, material='{mat}'. "
            f"Available widths: {available_w}."
        )

    base_wll = _SYNTHETIC_WLL[key]
    hf = _HITCH_FACTORS[h]
    adjusted_wll = base_wll * hf
    effective_wll = adjusted_wll / float(design_factor)

    return {
        "ok": True,
        "width_mm": w,
        "ply": ply,
        "material": mat,
        "hitch": h,
        "hitch_factor": hf,
        "base_wll_kg": base_wll,
        "adjusted_wll_kg": adjusted_wll,
        "effective_wll_kg": effective_wll,
        "design_factor": float(design_factor),
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 8. spreader_beam_check
# ---------------------------------------------------------------------------

# Minimum section properties (placeholder, actual from section)
# section_type → (A_m2, I_m4, Z_m3, r_m) lookup for common sizes
# These are representative; real design would use full section tables.

def spreader_beam_check(
    load_kg: float,
    span_m: float,
    *,
    section: str = "tube_square_200x200x10",
    Fy_MPa: float = 350.0,
    design_factor: float = 3.0,
) -> dict:
    """
    Bending and column (compression) check for a spreader / lifting beam.

    The spreader beam is modelled as a simply-supported beam carrying a
    central point load equal to the rigged load. The beam is also in
    compression along its length (equal to the horizontal component of the
    sling force when slings are not vertical — for this function a pure
    axial compression equal to half the total vertical load is assumed as
    a conservative estimate).

    Section is specified as a string of the form:
      "tube_square_<d>x<d>x<t>"  — square hollow section, d = outer size (mm), t = wall (mm)
      "tube_round_<d>x<t>"       — circular hollow section, d = OD (mm), t = wall (mm)
      "wide_flange_<d>x<b>x<tw>x<tf>" — wide-flange, d=depth, b=flange width,
                                          tw=web thickness, tf=flange thickness (all mm)

    Parameters
    ----------
    load_kg : float
        Total load (kg).
    span_m : float
        Spreader beam span (m).
    section : str
        Section string (see above).
    Fy_MPa : float
        Steel yield strength (MPa). Default 350 MPa (Gr 350 / A572 Gr 50).
    design_factor : float
        Design factor on yield. Default 3.0 for lifting equipment per most
        national standards.

    Returns
    -------
    dict
        ok                  : True
        section             : section string
        bending_moment_Nm   : midspan bending moment (N·m)
        bending_stress_MPa  : extreme fibre bending stress (MPa)
        axial_stress_MPa    : estimated compressive stress (MPa)
        combined_stress_MPa : bending + axial (conservative linear sum)
        allowable_stress_MPa: Fy / design_factor
        utilisation         : combined / allowable (1.0 = 100%)
        pass_bending        : True if utilisation <= 1.0
        area_mm2            : cross-section area (mm²)
        I_mm4               : second moment of area (mm⁴)
        S_mm3               : section modulus (mm³)
        warnings            : list
    """
    err = _guard_positive("load_kg", load_kg)
    if err:
        return _err(err)
    err = _guard_positive("span_m", span_m)
    if err:
        return _err(err)
    err = _guard_positive("Fy_MPa", Fy_MPa)
    if err:
        return _err(err)
    err = _guard_positive("design_factor", design_factor)
    if err:
        return _err(err)

    # Parse section string
    sec_result = _parse_section(str(section).strip().lower())
    if sec_result is None:
        return _err(
            f"Cannot parse section '{section}'. Use format: "
            "'tube_square_200x200x10', 'tube_round_219x10', or "
            "'wide_flange_300x150x8x12'."
        )

    A_mm2, I_mm4, S_mm3 = sec_result
    warnings: list[str] = []

    W_N = float(load_kg) * _G
    L = float(span_m)

    # Simply-supported central point load: M = WL/4
    M_Nm = W_N * L / 4.0
    bending_stress = M_Nm * 1e3 / S_mm3  # MPa

    # Conservative axial (compression): P_axial ≈ W/2 (slings at 45°)
    P_axial_N = W_N / 2.0
    axial_stress = P_axial_N / A_mm2 * 1e-3  # MPa (N/mm² = MPa)

    combined = bending_stress + axial_stress
    allow = float(Fy_MPa) / float(design_factor)
    utilisation = combined / allow

    pass_bending = utilisation <= 1.0
    if not pass_bending:
        warnings.append(
            f"WLL_EXCEEDED: combined stress {combined:.1f} MPa > allowable "
            f"{allow:.1f} MPa (utilisation {utilisation:.3f})."
        )

    return {
        "ok": True,
        "section": str(section),
        "bending_moment_Nm": M_Nm,
        "bending_stress_MPa": bending_stress,
        "axial_stress_MPa": axial_stress,
        "combined_stress_MPa": combined,
        "allowable_stress_MPa": allow,
        "utilisation": utilisation,
        "pass_bending": pass_bending,
        "area_mm2": A_mm2,
        "I_mm4": I_mm4,
        "S_mm3": S_mm3,
        "Fy_MPa": float(Fy_MPa),
        "design_factor": float(design_factor),
        "warnings": warnings,
    }


def _parse_section(sec: str) -> tuple[float, float, float] | None:
    """
    Parse a section string and return (A_mm2, I_mm4, S_mm3).
    Returns None on parse failure.
    """
    import re
    # tube_square_DxDxT
    m = re.match(r"tube_square_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", sec)
    if m:
        d_o = float(m.group(1))   # outer size
        # d_o2 = float(m.group(2)) — must match d_o; we ignore
        t = float(m.group(3))
        d_i = d_o - 2 * t
        if d_i <= 0:
            return None
        A = d_o ** 2 - d_i ** 2
        I = (d_o ** 4 - d_i ** 4) / 12.0
        S = I / (d_o / 2.0)
        return A, I, S

    # tube_round_DxT
    m = re.match(r"tube_round_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", sec)
    if m:
        d_o = float(m.group(1))
        t = float(m.group(2))
        d_i = d_o - 2 * t
        if d_i <= 0:
            return None
        A = math.pi / 4.0 * (d_o ** 2 - d_i ** 2)
        I = math.pi / 64.0 * (d_o ** 4 - d_i ** 4)
        S = I / (d_o / 2.0)
        return A, I, S

    # wide_flange_DxBxTwxTf
    m = re.match(
        r"wide_flange_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)",
        sec,
    )
    if m:
        d = float(m.group(1))   # total depth
        b = float(m.group(2))   # flange width
        tw = float(m.group(3))  # web thickness
        tf = float(m.group(4))  # flange thickness
        # Two flanges + web
        A = 2 * b * tf + (d - 2 * tf) * tw
        # I about strong axis
        d_web = d - 2 * tf
        I_flanges = 2 * (b * tf ** 3 / 12.0 + b * tf * ((d - tf) / 2.0) ** 2)
        I_web = tw * d_web ** 3 / 12.0
        I = I_flanges + I_web
        S = I / (d / 2.0)
        return A, I, S

    return None


# ---------------------------------------------------------------------------
# 9. padeye_check
# ---------------------------------------------------------------------------


def padeye_check(
    load_kN: float,
    plate_thickness_mm: float,
    hole_diameter_mm: float,
    pin_diameter_mm: float,
    *,
    Fy_MPa: float = 350.0,
    Fu_MPa: float = 480.0,
    design_factor: float = 3.0,
) -> dict:
    """
    Simplified padeye / lifting lug check.

    Checks three failure modes:
      1. Tension through net section (across the hole at the plate centreline)
      2. Bearing on the pin hole (direct bearing stress)
      3. Shear-out (double shear planes parallel to load direction)

    The padeye is assumed to be a flat plate with a circular hole for the pin.
    The check is per-plate (one plate thickness). For cheek plates add them.

    Parameters
    ----------
    load_kN : float
        Applied load (kN).
    plate_thickness_mm : float
        Plate thickness (mm).
    hole_diameter_mm : float
        Pin-hole diameter (mm). Must be > pin_diameter_mm.
    pin_diameter_mm : float
        Pin diameter (mm). Must be < hole_diameter_mm.
    Fy_MPa : float
        Yield strength of plate material (MPa). Default 350 MPa.
    Fu_MPa : float
        Ultimate tensile strength (MPa). Default 480 MPa (Grade 350 steel).
    design_factor : float
        Design factor. Default 3.0 for lifting hardware.

    Returns
    -------
    dict
        ok                       : True
        tension_net_stress_MPa   : net-section tension stress (MPa)
        bearing_stress_MPa       : bearing stress on pin hole (MPa)
        shearout_stress_MPa      : shear-out stress (MPa) — double shear
        tension_allow_MPa        : allowable net tension (Fu/design_factor)
        bearing_allow_MPa        : allowable bearing (1.5*Fy/design_factor typical)
        shearout_allow_MPa       : allowable shear-out (0.6*Fy/design_factor)
        tension_pass             : True if tension_net <= tension_allow
        bearing_pass             : True if bearing <= bearing_allow
        shearout_pass            : True if shearout <= shearout_allow
        utilisation_tension      : ratio
        utilisation_bearing      : ratio
        utilisation_shearout     : ratio
        governing_utilisation    : max of three utilisations
        warnings                 : list
    """
    err = _guard_positive("load_kN", load_kN)
    if err:
        return _err(err)
    err = _guard_positive("plate_thickness_mm", plate_thickness_mm)
    if err:
        return _err(err)
    err = _guard_positive("hole_diameter_mm", hole_diameter_mm)
    if err:
        return _err(err)
    err = _guard_positive("pin_diameter_mm", pin_diameter_mm)
    if err:
        return _err(err)
    if float(pin_diameter_mm) >= float(hole_diameter_mm):
        return _err(
            f"pin_diameter_mm ({pin_diameter_mm}) must be < hole_diameter_mm ({hole_diameter_mm})"
        )
    err = _guard_positive("Fy_MPa", Fy_MPa)
    if err:
        return _err(err)
    err = _guard_positive("Fu_MPa", Fu_MPa)
    if err:
        return _err(err)
    err = _guard_positive("design_factor", design_factor)
    if err:
        return _err(err)

    warnings: list[str] = []
    P = float(load_kN) * 1000.0  # N
    t = float(plate_thickness_mm)
    d_hole = float(hole_diameter_mm)
    d_pin = float(pin_diameter_mm)
    Fy = float(Fy_MPa)
    Fu = float(Fu_MPa)
    df = float(design_factor)

    # 1. Net section tension:
    #    Assume padeye width W ≈ 3 × d_hole (rule of thumb for adequate edge distance)
    W = 3.0 * d_hole  # mm
    net_area = (W - d_hole) * t  # mm²
    tension_stress = P / net_area  # MPa

    # 2. Bearing stress on pin hole:
    bearing_area = d_pin * t  # mm²
    bearing_stress = P / bearing_area  # MPa

    # 3. Shear-out (double shear planes):
    #    Edge distance e ≈ 1.5 × d_hole (standard rule)
    e = 1.5 * d_hole
    shear_area = 2.0 * (e - d_hole / 2.0) * t  # mm² (two planes)
    if shear_area <= 0:
        shear_area = t * d_hole  # fallback
    shearout_stress = P / shear_area  # MPa

    # Allowables
    tension_allow = Fu / df
    bearing_allow = 1.5 * Fy / df
    shearout_allow = 0.6 * Fy / df

    ut = tension_stress / tension_allow if tension_allow > 0 else float("inf")
    ub = bearing_stress / bearing_allow if bearing_allow > 0 else float("inf")
    us = shearout_stress / shearout_allow if shearout_allow > 0 else float("inf")
    gov = max(ut, ub, us)

    for label, util in [("tension", ut), ("bearing", ub), ("shear-out", us)]:
        if util > 1.0:
            warnings.append(
                f"WLL_EXCEEDED: {label} utilisation {util:.3f} > 1.0 — padeye overstressed."
            )

    return {
        "ok": True,
        "load_kN": float(load_kN),
        "plate_thickness_mm": t,
        "hole_diameter_mm": d_hole,
        "pin_diameter_mm": d_pin,
        "tension_net_stress_MPa": tension_stress,
        "bearing_stress_MPa": bearing_stress,
        "shearout_stress_MPa": shearout_stress,
        "tension_allow_MPa": tension_allow,
        "bearing_allow_MPa": bearing_allow,
        "shearout_allow_MPa": shearout_allow,
        "tension_pass": ut <= 1.0,
        "bearing_pass": ub <= 1.0,
        "shearout_pass": us <= 1.0,
        "utilisation_tension": ut,
        "utilisation_bearing": ub,
        "utilisation_shearout": us,
        "governing_utilisation": gov,
        "Fy_MPa": Fy,
        "Fu_MPa": Fu,
        "design_factor": df,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 10. tip_over_two_crane
# ---------------------------------------------------------------------------


def tip_over_two_crane(
    total_load_kg: float,
    crane_a_capacity_t: float,
    crane_b_capacity_t: float,
    lift_point_a_x: float,
    lift_point_b_x: float,
    cg_x: float,
) -> dict:
    """
    Two-crane lift: load share and tip-over check.

    Resolves the vertical reaction at each crane hook by taking moments
    about the other crane's lift point. Checks whether either crane is
    overloaded.

    Parameters
    ----------
    total_load_kg : float
        Total load (kg).
    crane_a_capacity_t : float
        Crane A rated capacity at its working radius (metric tonnes). Must be > 0.
    crane_b_capacity_t : float
        Crane B rated capacity at its working radius (metric tonnes).
    lift_point_a_x : float
        X-position of Crane A lift point (m). Arbitrary datum.
    lift_point_b_x : float
        X-position of Crane B lift point (m). Must differ from lift_point_a_x.
    cg_x : float
        Centre-of-gravity X-position (m).

    Returns
    -------
    dict
        ok                   : True
        crane_a_load_kg      : load on Crane A (kg)
        crane_b_load_kg      : load on Crane B (kg)
        crane_a_capacity_kg  : capacity of Crane A (kg)
        crane_b_capacity_kg  : capacity of Crane B (kg)
        crane_a_utilisation  : load / capacity for Crane A
        crane_b_utilisation  : load / capacity for Crane B
        crane_a_ok           : True if Crane A load <= capacity
        crane_b_ok           : True if Crane B load <= capacity
        cg_between_hooks     : True if CG is between the two lift points
        warnings             : list
    """
    err = _guard_positive("total_load_kg", total_load_kg)
    if err:
        return _err(err)
    err = _guard_positive("crane_a_capacity_t", crane_a_capacity_t)
    if err:
        return _err(err)
    err = _guard_positive("crane_b_capacity_t", crane_b_capacity_t)
    if err:
        return _err(err)

    xa = float(lift_point_a_x)
    xb = float(lift_point_b_x)
    xg = float(cg_x)

    if abs(xa - xb) < 1e-9:
        return _err("lift_point_a_x and lift_point_b_x must differ (non-zero span)")

    span = xb - xa  # can be negative if A is to the right of B
    W = float(total_load_kg)
    warnings: list[str] = []

    # Moments about B for reaction at A, and about A for reaction at B
    # R_A × span = W × (xb - xg)
    R_A = W * (xb - xg) / span
    R_B = W - R_A

    cap_a_kg = float(crane_a_capacity_t) * 1000.0
    cap_b_kg = float(crane_b_capacity_t) * 1000.0

    util_a = R_A / cap_a_kg if cap_a_kg > 0 else float("inf")
    util_b = R_B / cap_b_kg if cap_b_kg > 0 else float("inf")

    a_ok = util_a <= 1.0
    b_ok = util_b <= 1.0

    # CG between hooks
    x_min = min(xa, xb)
    x_max = max(xa, xb)
    cg_between = x_min <= xg <= x_max

    if not cg_between:
        warnings.append(
            "UNSTABLE: CG is outside the two lift points — one crane will go "
            "into tension (upward reaction). Reconfigure lift points."
        )
    if not a_ok:
        warnings.append(
            f"WLL_EXCEEDED: Crane A load {R_A:.0f} kg exceeds capacity "
            f"{cap_a_kg:.0f} kg (utilisation {util_a:.3f})."
        )
    if not b_ok:
        warnings.append(
            f"WLL_EXCEEDED: Crane B load {R_B:.0f} kg exceeds capacity "
            f"{cap_b_kg:.0f} kg (utilisation {util_b:.3f})."
        )

    return {
        "ok": True,
        "total_load_kg": W,
        "crane_a_load_kg": R_A,
        "crane_b_load_kg": R_B,
        "crane_a_capacity_kg": cap_a_kg,
        "crane_b_capacity_kg": cap_b_kg,
        "crane_a_utilisation": util_a,
        "crane_b_utilisation": util_b,
        "crane_a_ok": a_ok,
        "crane_b_ok": b_ok,
        "cg_between_hooks": cg_between,
        "lift_point_a_x": xa,
        "lift_point_b_x": xb,
        "cg_x": xg,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 11. crane_radius_interpolate
# ---------------------------------------------------------------------------


def crane_radius_interpolate(
    radius_m: float,
    chart_table: list[tuple[float, float]],
) -> dict:
    """
    Interpolate (or conservatively extrapolate) crane capacity from a
    radius–capacity chart table.

    The table must be a list of (radius_m, capacity_t) pairs, sorted by
    ascending radius. Capacity decreases with radius.

    Interpolation: linear between the two bounding table entries.
    Extrapolation beyond the maximum radius: uses the minimum table
    capacity (conservative: do not extrapolate upward).
    Extrapolation below the minimum radius: uses the minimum table radius
    entry capacity (crane at its closest reach).

    Parameters
    ----------
    radius_m : float
        Operating radius (m). Must be > 0.
    chart_table : list of (radius_m, capacity_t)
        At least 2 entries, each (radius_m, capacity_t) with capacity_t > 0.
        Must be sorted by ascending radius_m. Capacity must be monotonically
        non-increasing (typical crane charts).

    Returns
    -------
    dict
        ok                   : True
        radius_m             : radius queried
        capacity_t           : interpolated capacity (metric tonnes)
        capacity_kg          : interpolated capacity (kg)
        interpolated         : True if between table entries; False if extrapolated
        warnings             : list
    """
    err = _guard_positive("radius_m", radius_m)
    if err:
        return _err(err)

    if not isinstance(chart_table, (list, tuple)) or len(chart_table) < 2:
        return _err("chart_table must be a list of at least 2 (radius_m, capacity_t) pairs")

    table: list[tuple[float, float]] = []
    for i, row in enumerate(chart_table):
        try:
            r, c = float(row[0]), float(row[1])
        except (TypeError, ValueError, IndexError):
            return _err(f"chart_table[{i}] must be a (radius_m, capacity_t) tuple of numbers")
        if not (math.isfinite(r) and math.isfinite(c)):
            return _err(f"chart_table[{i}] values must be finite")
        if c <= 0:
            return _err(f"chart_table[{i}] capacity_t must be > 0")
        table.append((r, c))

    # Sort by radius
    table.sort(key=lambda x: x[0])

    r_query = float(radius_m)
    warnings: list[str] = []
    interpolated = True

    if r_query <= table[0][0]:
        capacity_t = table[0][1]
        interpolated = False
        if r_query < table[0][0]:
            warnings.append(
                f"Radius {r_query:.1f} m < table minimum {table[0][0]:.1f} m; "
                "using minimum-radius capacity (conservative)."
            )
    elif r_query >= table[-1][0]:
        capacity_t = table[-1][1]
        interpolated = False
        warnings.append(
            f"Radius {r_query:.1f} m > table maximum {table[-1][0]:.1f} m; "
            "using maximum-radius (minimum) capacity — DO NOT extrapolate beyond chart."
        )
    else:
        # Linear interpolation
        for i in range(len(table) - 1):
            r0, c0 = table[i]
            r1, c1 = table[i + 1]
            if r0 <= r_query <= r1:
                t = (r_query - r0) / (r1 - r0)
                capacity_t = c0 + t * (c1 - c0)
                break
        else:
            capacity_t = table[-1][1]

    return {
        "ok": True,
        "radius_m": r_query,
        "capacity_t": capacity_t,
        "capacity_kg": capacity_t * 1000.0,
        "interpolated": interpolated,
        "warnings": warnings,
    }
