"""GK-128 — Gear tooth profile generator (involute + cycloid).

Pure-Python, no OCCT dependency.

Public API
----------
involute_gear(module, teeth, pressure_angle_deg=20) -> dict
    2-D tooth profile + full wheel outline for a standard external spur gear.
    Returns:
        tooth_curve  : list[[x, y]] — one tooth flank pair (base→tip on right, tip→base on left)
        wheel_curve  : list[[x, y]] — closed polygon with exactly `teeth` tooth periods
        pitch_radius : float        — r_p = module * teeth / 2
        base_radius  : float        — r_b = r_p * cos(pressure_angle_rad)

cycloid_gear(module, teeth) -> dict
    2-D tooth profile for an epicycloid/hypocycloid gear (equal-addendum / equal-dedendum
    convention: r_rolling = module / 2).
    Returns:
        tooth_curve  : list[[x, y]] — one tooth (flank pair)
        wheel_curve  : list[[x, y]] — closed polygon with exactly `teeth` tooth periods
        pitch_radius : float
        base_radius  : float        — same as pitch_radius (no base circle for cycloid)

Both wheel_curve arrays contain exactly `teeth` repetitions of the respective tooth
pattern (verified by oracle tests).

References
----------
- ISO 21771:2007 spur / helical gear geometry
- Shigley's Mechanical Engineering Design §13
- Buckingham, "Analytical Mechanics of Gears", cycloidal profile equations
"""

from __future__ import annotations

import math
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Internal helpers — involute
# ---------------------------------------------------------------------------

def _involute_xy(r_base: float, t: float) -> Tuple[float, float]:
    """Point on involute of a circle of radius *r_base* at roll angle *t* (rad).

    The involute starting from angle 0 on the base circle:
        x = r_b * (cos(t) + t*sin(t))
        y = r_b * (sin(t) - t*cos(t))
    """
    x = r_base * (math.cos(t) + t * math.sin(t))
    y = r_base * (math.sin(t) - t * math.cos(t))
    return x, y


def _rotate_xy(x: float, y: float, angle: float) -> Tuple[float, float]:
    """Rotate point (x, y) by *angle* radians CCW about the origin."""
    c, s = math.cos(angle), math.sin(angle)
    return c * x - s * y, s * x + c * y


def _involute_tooth_profile(
    r_base: float,
    r_pitch: float,
    r_tip: float,
    r_root: float,
    half_tooth_angle: float,
    n_pts: int = 32,
) -> List[List[float]]:
    """Build one closed tooth polygon (right-flank involute, tip arc, left-flank involute,
    root arc).

    The tooth is centred on the +X axis.  The polygon starts at the right-root
    transition, climbs the right involute to the tip, crosses the tip arc (single
    point here — symmetric), descends the left involute (mirror), and closes at
    the left-root transition.  A straight segment along the root circle closes
    the loop.

    Parameters
    ----------
    r_base            : base circle radius
    r_pitch           : pitch radius
    r_tip             : tip (addendum) radius
    r_root            : root (dedendum) radius
    half_tooth_angle  : half the angular pitch of one tooth space at the pitch circle
                        (i.e. the angular half-width of the tooth at r_pitch, in rad)
    n_pts             : number of sample points on each involute flank

    Returns
    -------
    Closed polygon: list of [x, y] pairs where first == last.
    """
    # ------------------------------------------------------------------
    # Compute roll-angle range for the involute.
    # At the base circle, t_base = 0 (involute point is (r_b, 0) before rotation).
    # At r_tip: r_b * sqrt(1 + t^2) = r_tip  →  t_tip = sqrt((r_tip/r_b)^2 - 1)
    # ------------------------------------------------------------------
    t_tip = math.sqrt(max((r_tip / r_base) ** 2 - 1.0, 0.0))

    # At the pitch circle the involute has roll angle:
    #   t_pitch = sqrt((r_pitch/r_b)^2 - 1)
    t_pitch = math.sqrt(max((r_pitch / r_base) ** 2 - 1.0, 0.0))

    # The involute function inv(φ) = tan(φ) − φ
    # The angular position of the involute on the pitch circle (from the base
    # circle tangent-point) equals inv(alpha) where alpha = pressure angle.
    # We want the involute flank to be symmetric about the tooth centreline.
    # The total half-tooth angle at the pitch circle is half_tooth_angle.
    # The involute departs the base circle at angle (half_tooth_angle - inv(alpha))
    # from the tooth centreline (positive x axis).
    alpha_pitch = math.acos(r_base / r_pitch) if r_pitch > 0 else 0.0
    inv_alpha = math.tan(alpha_pitch) - alpha_pitch

    # Rotation so that at t = t_pitch the involute lands at angle half_tooth_angle
    # from the tooth axis.
    # Involute point at t has argument angle  atan2(y, x) = t (by construction of
    # the _involute_xy parameterisation above: atan2 of that point = t).
    # So we rotate the whole flank by:
    base_rotation = half_tooth_angle - t_pitch + inv_alpha

    # Sample right-flank involute: t from 0 to t_tip
    # Start from t = 0 (base circle) but clamp if root is larger than base.
    t_root_eff = math.sqrt(max((max(r_root, r_base) / r_base) ** 2 - 1.0, 0.0))
    # If root < base (undercut region), clamp to t=0
    t_start = 0.0 if r_root <= r_base else t_root_eff

    ts = [t_start + (t_tip - t_start) * i / (n_pts - 1) for i in range(n_pts)]
    right_flank: List[Tuple[float, float]] = []
    for t in ts:
        px, py = _involute_xy(r_base, t)
        px, py = _rotate_xy(px, py, base_rotation)
        right_flank.append((px, py))

    # Left flank = mirror of right flank about the x-axis (negate y)
    # traversed in reverse (from tip down to base)
    left_flank: List[Tuple[float, float]] = [
        (px, -py) for px, py in reversed(right_flank)
    ]

    # Root arc: a few points connecting left-root to right-root
    # (just a line segment at r_root angle for a spur tooth)
    r0x, r0y = right_flank[0]
    l0x, l0y = left_flank[-1]
    ang_r = math.atan2(r0y, r0x)
    ang_l = math.atan2(l0y, l0x)
    # Sweep from left end to right end of root (going clockwise means decreasing angle)
    # Build a short arc with a few points
    n_root = max(4, n_pts // 4)
    root_arc: List[Tuple[float, float]] = []
    for i in range(n_root + 1):
        a = ang_l + (ang_r - ang_l) * i / n_root
        root_arc.append((r_root * math.cos(a), r_root * math.sin(a)))

    # Assemble: root_arc[0..n] + right_flank[0..n-1] + left_flank[0..n-1] + root_arc[-1]
    # But root_arc[-1] == root_arc[0] after closing, so:
    # Start at root_arc[0] (left-root end), go around tooth, close back.
    pts: List[Tuple[float, float]] = []
    pts.extend(root_arc)          # left root → right root (across valley)
    pts.extend(right_flank)       # right root → right tip
    pts.extend(left_flank)        # left tip → left root
    # close
    pts.append(pts[0])
    return [[x, y] for x, y in pts]


# ---------------------------------------------------------------------------
# Internal helpers — cycloid
# ---------------------------------------------------------------------------

def _epicycloid_point(r_pitch: float, r_rolling: float, t: float) -> Tuple[float, float]:
    """Point on an epicycloid (rolling circle outside the pitch circle).

    x = (R+r)*cos(t) - r*cos((R+r)/r * t)
    y = (R+r)*sin(t) - r*sin((R+r)/r * t)
    """
    R, r = r_pitch, r_rolling
    x = (R + r) * math.cos(t) - r * math.cos((R + r) / r * t)
    y = (R + r) * math.sin(t) - r * math.sin((R + r) / r * t)
    return x, y


def _hypocycloid_point(r_pitch: float, r_rolling: float, t: float) -> Tuple[float, float]:
    """Point on a hypocycloid (rolling circle inside the pitch circle).

    x = (R-r)*cos(t) + r*cos((R-r)/r * t)
    y = (R-r)*sin(t) - r*sin((R-r)/r * t)
    """
    R, r = r_pitch, r_rolling
    x = (R - r) * math.cos(t) + r * math.cos((R - r) / r * t)
    y = (R - r) * math.sin(t) - r * math.sin((R - r) / r * t)
    return x, y


def _cycloid_tooth_profile(
    r_pitch: float,
    r_addendum: float,
    r_dedendum: float,
    half_tooth_angle: float,
    r_rolling: float,
    n_pts: int = 32,
) -> List[List[float]]:
    """Single cycloid tooth polygon centred on the +X axis.

    The face (above pitch circle) is an epicycloid arc; the flank (below pitch
    circle) is a hypocycloid arc.
    """
    # Epicycloid: starts at pitch circle (t=0) and sweeps to tip
    # We parameterise t from 0 to t_max where the epicycloid reaches r_addendum.
    # At t=0 the epicycloid starts at (r_pitch+r_rolling - r_rolling, 0) = (r_pitch, 0)
    # which is on the pitch circle — correct.

    # Find t_max for epicycloid reaching r_addendum
    # |epicycloid(t)| = r_addendum
    def epi_r(t: float) -> float:
        x, y = _epicycloid_point(r_pitch, r_rolling, t)
        return math.hypot(x, y)

    # Binary search for t_max
    lo, hi = 0.0, math.pi / 2
    for _ in range(64):
        mid = (lo + hi) / 2
        if epi_r(mid) < r_addendum:
            lo = mid
        else:
            hi = mid
    t_tip = (lo + hi) / 2

    # Hypocycloid: starts at pitch circle (t=0) and sweeps to root
    def hypo_r(t: float) -> float:
        x, y = _hypocycloid_point(r_pitch, r_rolling, t)
        return math.hypot(x, y)

    lo2, hi2 = 0.0, math.pi / 2
    for _ in range(64):
        mid = (lo2 + hi2) / 2
        if hypo_r(mid) > r_dedendum:
            lo2 = mid
        else:
            hi2 = mid
    t_root = (lo2 + hi2) / 2

    # Build right face (epicycloid, above pitch circle)
    # The epicycloid starts at (r_pitch, 0); we want the tooth centred on +X
    # The angular offset of the epi arc at its start is 0 (on the +X axis).
    # Rotate so the tooth centre aligns with +X by applying half_tooth_angle offset.
    right_face: List[Tuple[float, float]] = []
    for i in range(n_pts):
        t = t_tip * i / (n_pts - 1)
        x, y = _epicycloid_point(r_pitch, r_rolling, t)
        # rotate by half_tooth_angle so the flank root is at half_tooth_angle from axis
        x2, y2 = _rotate_xy(x, y, half_tooth_angle)
        right_face.append((x2, y2))

    # Build right flank (hypocycloid, below pitch circle)
    right_flank: List[Tuple[float, float]] = []
    for i in range(n_pts):
        t = t_root * i / (n_pts - 1)
        x, y = _hypocycloid_point(r_pitch, r_rolling, t)
        x2, y2 = _rotate_xy(x, y, half_tooth_angle)
        right_flank.append((x2, y2))

    # Full right side: flank (root to pitch) reversed + face (pitch to tip)
    right_side = list(reversed(right_flank)) + right_face[1:]  # avoid duplicate at pitch

    # Left side = mirror of right_side about x-axis, reversed
    left_side = [(x, -y) for x, y in reversed(right_side)]

    # Root arc connecting left root to right root
    r_root_pt = right_flank[-1]   # rightmost root point
    l_root_pt = left_side[-1]     # leftmost root point
    ang_r = math.atan2(r_root_pt[1], r_root_pt[0])
    ang_l = math.atan2(l_root_pt[1], l_root_pt[0])
    n_root = max(4, n_pts // 4)
    root_arc: List[Tuple[float, float]] = []
    for i in range(n_root + 1):
        a = ang_l + (ang_r - ang_l) * i / n_root
        root_arc.append((r_dedendum * math.cos(a), r_dedendum * math.sin(a)))

    pts: List[Tuple[float, float]] = []
    pts.extend(root_arc)
    pts.extend(right_side)
    pts.extend(left_side)
    pts.append(pts[0])
    return [[x, y] for x, y in pts]


# ---------------------------------------------------------------------------
# Wheel assembly: tile a single tooth around the full circle
# ---------------------------------------------------------------------------

def _tile_tooth(tooth_poly: List[List[float]], teeth: int) -> List[List[float]]:
    """Assemble a full wheel polygon by rotating *tooth_poly* by `teeth` equally
    spaced angular steps (2π/teeth each), concatenating them into one closed loop.

    The resulting polygon contains exactly `teeth` tooth periods.
    """
    angular_pitch = 2.0 * math.pi / teeth
    wheel: List[List[float]] = []
    for k in range(teeth):
        angle = k * angular_pitch
        for pt in tooth_poly[:-1]:  # skip closing duplicate inside each tooth
            x, y = _rotate_xy(pt[0], pt[1], angle)
            wheel.append([x, y])
    # close the polygon
    wheel.append(wheel[0][:])
    return wheel


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def involute_gear(
    module: float,
    teeth: int,
    pressure_angle_deg: float = 20.0,
    n_pts: int = 32,
) -> dict:
    """Generate a 2-D involute spur gear profile.

    Parameters
    ----------
    module             : gear module (mm or any consistent unit)
    teeth              : number of teeth (integer ≥ 3)
    pressure_angle_deg : standard pressure angle in degrees (default 20°)
    n_pts              : number of sample points per involute flank

    Returns
    -------
    dict with keys:
        tooth_curve  : list[[x, y]] — one tooth polygon (closed)
        wheel_curve  : list[[x, y]] — full wheel polygon (closed), exactly `teeth` periods
        pitch_radius : float  — r_p = module * teeth / 2
        base_radius  : float  — r_b = pitch_radius * cos(pressure_angle_rad)
    """
    if module <= 0:
        raise ValueError(f"module must be positive, got {module!r}")
    if not isinstance(teeth, int) or teeth < 3:
        raise ValueError(f"teeth must be an integer >= 3, got {teeth!r}")
    if not (10.0 < pressure_angle_deg < 30.0):
        raise ValueError(
            f"pressure_angle_deg must be in (10, 30), got {pressure_angle_deg!r}"
        )

    alpha = math.radians(pressure_angle_deg)
    r_pitch = module * teeth / 2.0
    r_base  = r_pitch * math.cos(alpha)

    # Standard addendum / dedendum (ISO 21771)
    r_tip  = r_pitch + 1.0 * module          # addendum coefficient ha* = 1
    r_root = r_pitch - 1.25 * module         # dedendum coefficient hf* = 1.25

    # Angular half-width of one tooth at the pitch circle
    # (half of the circular pitch = π*m, expressed as angle = π/z)
    half_tooth_angle = math.pi / teeth

    tooth_curve = _involute_tooth_profile(
        r_base=r_base,
        r_pitch=r_pitch,
        r_tip=r_tip,
        r_root=r_root,
        half_tooth_angle=half_tooth_angle,
        n_pts=n_pts,
    )
    wheel_curve = _tile_tooth(tooth_curve, teeth)

    return {
        "tooth_curve":  tooth_curve,
        "wheel_curve":  wheel_curve,
        "pitch_radius": r_pitch,
        "base_radius":  r_base,
    }


def cycloid_gear(
    module: float,
    teeth: int,
    n_pts: int = 32,
) -> dict:
    """Generate a 2-D cycloidal gear tooth profile.

    Uses the equal-addendum / equal-dedendum convention with rolling circle radius
    r_rolling = module / 2 (so rolling circle diameter = module).

    Parameters
    ----------
    module : gear module
    teeth  : number of teeth (integer ≥ 3)
    n_pts  : sample points per epicycloid/hypocycloid arc

    Returns
    -------
    dict with keys:
        tooth_curve  : list[[x, y]] — one tooth polygon (closed)
        wheel_curve  : list[[x, y]] — full wheel polygon, exactly `teeth` periods
        pitch_radius : float
        base_radius  : float — equals pitch_radius (cycloidal gears have no base circle)
    """
    if module <= 0:
        raise ValueError(f"module must be positive, got {module!r}")
    if not isinstance(teeth, int) or teeth < 3:
        raise ValueError(f"teeth must be an integer >= 3, got {teeth!r}")

    r_pitch   = module * teeth / 2.0
    r_rolling = module / 2.0                  # standard equal-addendum convention
    r_tip     = r_pitch + r_rolling            # addendum = r_rolling
    r_root    = r_pitch - r_rolling            # dedendum = r_rolling

    half_tooth_angle = math.pi / teeth

    tooth_curve = _cycloid_tooth_profile(
        r_pitch=r_pitch,
        r_addendum=r_tip,
        r_dedendum=max(r_root, r_pitch * 0.05),  # clamp for tiny gears
        half_tooth_angle=half_tooth_angle,
        r_rolling=r_rolling,
        n_pts=n_pts,
    )
    wheel_curve = _tile_tooth(tooth_curve, teeth)

    return {
        "tooth_curve":  tooth_curve,
        "wheel_curve":  wheel_curve,
        "pitch_radius": r_pitch,
        "base_radius":  r_pitch,   # cycloidal gears have no separate base circle
    }
