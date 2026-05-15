"""
kerf-cad-core: involute gear generator (pure Python, no OCC).

Implements five LLM tools:

  T-1  gear_spur        — spur (external) involute gear: geometry + tooth polyline
  T-2  gear_helical     — helical extension of T-1 (normal / transverse module)
  T-3  gear_internal    — internal (ring) gear: annular geometry + polyline
  T-4  gear_rack        — linear rack: tooth geometry + linear pitch
  T-5  gear_pair_check  — mesh check: centre distance, gear ratio, contact ratio,
                          undercut / interference warning

All geometry is parametric: the 2D tooth-profile polyline is returned as a
list of [x, y] coordinate pairs (sampled involute + root fillet + tip arc).
No OCCT dependency; no external packages beyond Python's built-in `math`.

References
----------
ISO 21771:2007 — Gears: Cylindrical involute gears and gear pairs — Concepts
    and geometry (module system, ISO 21771 §§ 3–5, 8, 10).

Authored by imranparuk.
"""

from __future__ import annotations

import json
import math
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # type: ignore[import]


# ---------------------------------------------------------------------------
# Constants (ISO 21771 defaults)
# ---------------------------------------------------------------------------

# Standard addendum / dedendum coefficients (ISO 21771, Table 2)
_HA_COEFF   = 1.0   # addendum coefficient  (ha* = 1)
_HF_COEFF   = 1.25  # dedendum coefficient  (hf* = 1.25)

# Tip-fillet / root-fillet radius coefficient (ISO 21771)
_RF_COEFF   = 0.38  # standard root fillet (ISO rack)

# Pressure-angle limits (degrees)
_ALPHA_MIN  = 10.0
_ALPHA_MAX  = 30.0

# Minimum teeth below which undercut is guaranteed without profile shift
_Z_UNDERCUT = 17  # conservative: undercut threshold at α=20°


# ---------------------------------------------------------------------------
# Core involute math helpers
# ---------------------------------------------------------------------------

def _inv(phi: float) -> float:
    """Involute function: inv(φ) = tan(φ) − φ  (φ in radians, ISO 21771 Eq. 3)."""
    return math.tan(phi) - phi


def _involute_point(r_base: float, t: float) -> tuple[float, float]:
    """
    Cartesian point on the involute of a circle of radius *r_base*.

    The involute is parameterised by the roll angle *t* (radians ≥ 0).
    As *t* increases the point moves outward from the base circle.
    Formulae (ISO 21771 §5):
        x(t) = r_base · (cos t + t · sin t)
        y(t) = r_base · (sin t − t · cos t)
    """
    return (
        r_base * (math.cos(t) + t * math.sin(t)),
        r_base * (math.sin(t) - t * math.cos(t)),
    )


def _rotate(x: float, y: float, theta: float) -> tuple[float, float]:
    """Rotate (x, y) by angle *theta* (radians) CCW about origin."""
    c, s = math.cos(theta), math.sin(theta)
    return c * x - s * y, s * x + c * y


def _pitch_point_roll(alpha_rad: float) -> float:
    """
    Roll angle *t* on the involute at the pitch circle.

    The roll angle where the involute crosses the pitch circle satisfies:
        r = r_base / cos(t)  →  t = alpha  (pressure angle)
    ISO 21771 §5.2.
    """
    return alpha_rad


def _tip_roll_angle(r_base: float, r_tip: float) -> float:
    """
    Roll angle *t_a* at the tip circle (addendum circle).

    Derived from r_tip = r_base / cos(t_a), hence t_a = arccos(r_base / r_tip).
    """
    ratio = r_base / r_tip
    # clamp for numerical safety
    ratio = max(-1.0, min(1.0, ratio))
    return math.acos(ratio)


def _root_roll_angle(r_base: float, r_root: float) -> float:
    """
    Roll angle at the root circle — zero if r_root ≤ r_base
    (involute does not extend below the base circle).
    """
    if r_root <= r_base:
        return 0.0
    ratio = r_base / r_root
    ratio = max(-1.0, min(1.0, ratio))
    return math.acos(ratio)


def _tooth_half_angle_pitch(alpha_rad: float, z: int, x: float = 0.0) -> float:
    """
    Half-tooth-thickness angle at the pitch circle for a profile-shifted gear.

    Standard tooth-thickness (arc) at pitch circle (ISO 21771 §8.2):
        s = m · π/2 + 2 · x · m · tan(α)
    In angular terms (s / r_pitch = s / (m·z/2)):
        θ_s = π/z + 2 · x · tan(α) / z + 2 · inv(α)

    This returns half the angle, θ_s / 2, used when reflecting the
    right-flank involute to produce the left-flank.
    """
    inv_a = _inv(alpha_rad)
    # Half-tooth angle at pitch circle:
    half = math.pi / z + 2.0 * x * math.tan(alpha_rad) / z + inv_a
    return half


def _sample_involute(
    r_base: float,
    t_start: float,
    t_end: float,
    n: int,
) -> list[tuple[float, float]]:
    """
    Return *n* points on the involute from roll angle *t_start* to *t_end*.
    """
    pts = []
    for i in range(n):
        t = t_start + (t_end - t_start) * i / max(n - 1, 1)
        pts.append(_involute_point(r_base, t))
    return pts


def _arc_points(r: float, a_start: float, a_end: float, n: int) -> list[tuple[float, float]]:
    """
    Sample *n* points on a circle of radius *r* from angle *a_start* to
    *a_end* (radians). Used for root-fillet and tip arc segments.
    """
    pts = []
    for i in range(n):
        a = a_start + (a_end - a_start) * i / max(n - 1, 1)
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_basic(m: float, z: int, alpha_deg: float) -> list[str]:
    """Return a list of error strings for the three fundamental parameters."""
    errors: list[str] = []
    if m <= 0:
        errors.append(f"module m must be > 0; got {m}")
    if z < 3:
        errors.append(f"tooth count z must be ≥ 3; got {z}")
    if not (_ALPHA_MIN < alpha_deg < _ALPHA_MAX):
        errors.append(
            f"pressure angle α must be in ({_ALPHA_MIN}°, {_ALPHA_MAX}°); got {alpha_deg}°"
        )
    return errors


# ---------------------------------------------------------------------------
# Gear geometry computation (shared core)
# ---------------------------------------------------------------------------

def _spur_geometry(
    m: float,
    z: int,
    alpha_deg: float,
    x: float = 0.0,
    n_pts: int = 32,
) -> dict[str, Any]:
    """
    Compute full geometry for a standard external spur gear.

    Parameters
    ----------
    m         : module (mm)
    z         : number of teeth
    alpha_deg : pressure angle (degrees)
    x         : profile-shift coefficient (dimensionless, ISO 21771 §8)
    n_pts     : number of involute sample points per flank

    Returns
    -------
    dict with ISO 21771 gear data + tooth polyline.
    """
    alpha = math.radians(alpha_deg)

    # --- Basic diameters (ISO 21771 §4) ---
    d       = m * z                                    # pitch diameter
    d_b     = d * math.cos(alpha)                      # base diameter
    d_a     = d + 2.0 * m * (_HA_COEFF + x)           # tip (addendum) diameter
    d_f     = d - 2.0 * m * (_HF_COEFF - x)           # root (dedendum) diameter
    h_a     = m * (_HA_COEFF + x)                      # addendum height
    h_f     = m * (_HF_COEFF - x)                      # dedendum height
    h       = h_a + h_f                                # whole depth
    p       = math.pi * m                              # circular pitch (ISO 21771 §3.7)
    s       = p / 2 + 2 * x * m * math.tan(alpha)     # tooth thickness at pitch circle

    r       = d / 2.0
    r_b     = d_b / 2.0
    r_a     = d_a / 2.0
    r_f     = d_f / 2.0

    # --- Undercut check (ISO 21771 §10, simplified Wildhaber criterion) ---
    # Undercut occurs when r_f < r_b (root circle inside base circle)
    undercut = r_f < r_b

    # --- Involute tooth profile polyline (one complete tooth, centred on +X) ---
    #
    # Strategy (right-flank in 1st quadrant, mirrored to left-flank):
    #
    #  1. The right involute starts at the base circle (t = t_root) and ends
    #     at the tip circle (t = t_tip).
    #  2. The tooth is centred on the positive X axis, meaning the pitch
    #     point is at angle 0 on the pitch circle.
    #  3. The half-tooth angle θ at the pitch circle:
    #        θ = π/z + 2·x·tan(α)/z + 2·inv(α)   (ISO 21771 §8.2)
    #     is used to rotate the right involute so the tooth is symmetric
    #     about the X axis.
    #  4. The left flank is a reflection (x → x, y → -y) of the right flank.
    #  5. Root and tip arcs join the flanks.

    t_tip  = _tip_roll_angle(r_b, r_a)
    t_root = _root_roll_angle(r_b, r_f)

    # Half-tooth angle at pitch circle (used to orient the tooth)
    half_theta = _tooth_half_angle_pitch(alpha, z, x)

    # Angular offset so the involute at the pitch-circle lies at +half_theta
    # The involute point at t=alpha is at angle alpha - inv(alpha) from the
    # base-circle reference (standard involute polar angle, ISO 21771 §5.3):
    #   φ(t) = t − inv(α)  ← angle of involute point from the base circle datum
    # We want φ(t_pitch) = half_theta, so the datum offset is:
    offset_angle = half_theta - (alpha - _inv(alpha))

    # Build right-flank points (rotated so tooth is centred on +X)
    right_inv = _sample_involute(r_b, t_root, t_tip, n_pts)
    right_flank = [
        _rotate(px, py, offset_angle) for px, py in right_inv
    ]

    # Left-flank: mirror y → -y (tooth is symmetric about X axis)
    left_flank = [(px, -py) for px, py in reversed(right_flank)]

    # Tip arc: between top of right flank and top of left flank
    # The angle at the tip for the right flank:
    rx_tip, ry_tip = right_flank[-1]
    a_right_tip = math.atan2(ry_tip, rx_tip)
    rx_ltip, ry_ltip = left_flank[0]
    a_left_tip = math.atan2(ry_ltip, rx_ltip)
    tip_arc = _arc_points(r_a, a_right_tip, a_left_tip, max(4, n_pts // 8))

    # Root arc: from bottom of left flank to bottom of right flank
    # (we describe ONE tooth; root arc spans the root space gap to next tooth)
    # For a single-tooth profile: root arc from left-flank base → right-flank base
    # through the tooth valley (below).
    rx_root, ry_root = right_flank[0]
    a_right_root = math.atan2(ry_root, rx_root)
    rx_lroot, ry_lroot = left_flank[-1]
    a_left_root = math.atan2(ry_lroot, rx_lroot)
    # Root arc sweeps through the valley (going downward = more negative angles)
    # Span the root arc going clockwise (i.e. from right-flank root down to
    # the bottom, then back up to left-flank root).
    a_valley = a_right_root - math.pi / z  # midpoint of the root space
    root_arc_lo  = _arc_points(r_f, a_right_root, a_valley, max(3, n_pts // 8))
    root_arc_hi  = _arc_points(r_f, a_valley, a_left_root, max(3, n_pts // 8))

    # Assemble the tooth polyline: CW from tip, closing at root
    # Order: right-flank (tip→root) tip-arc left-flank (tip→root at other side)
    # then root arc back to start.
    polyline: list[list[float]] = []
    # Right flank: from root to tip
    for px, py in right_flank:
        polyline.append([round(px, 8), round(py, 8)])
    # Tip arc
    for px, py in tip_arc[1:]:
        polyline.append([round(px, 8), round(py, 8)])
    # Left flank: from tip to root
    for px, py in left_flank[1:]:
        polyline.append([round(px, 8), round(py, 8)])
    # Root arc (back to start of right flank)
    for px, py in root_arc_lo[1:] + root_arc_hi[1:]:
        polyline.append([round(px, 8), round(py, 8)])

    # Close the polyline (first == last)
    if polyline and polyline[0] != polyline[-1]:
        polyline.append(polyline[0])

    return {
        # ISO 21771 §4 nomenclature
        "module": round(m, 8),
        "teeth": z,
        "pressure_angle_deg": round(alpha_deg, 6),
        "profile_shift": round(x, 6),
        # Diameters (mm)
        "pitch_diameter":    round(d,   8),
        "base_diameter":     round(d_b, 8),
        "tip_diameter":      round(d_a, 8),
        "root_diameter":     round(d_f, 8),
        # Heights (mm)
        "addendum":          round(h_a, 8),
        "dedendum":          round(h_f, 8),
        "whole_depth":       round(h,   8),
        # Pitch / thickness (mm)
        "circular_pitch":    round(p,   8),
        "tooth_thickness":   round(s,   8),
        # Flags
        "undercut_risk":     undercut,
        # Tooth profile polyline (sampled, mm)
        "tooth_polyline":    polyline,
        "polyline_points":   len(polyline),
        "polyline_note": (
            "Single-tooth 2D profile in the transverse plane, centred on +X axis. "
            "Sampled involute flanks + tip arc + root arc. "
            "Units mm. Closed polygon (first == last). "
            "Reference: ISO 21771."
        ),
    }


def _contact_ratio(
    r_a1: float, r_b1: float,
    r_a2: float, r_b2: float,
    a_w: float,
    alpha_w: float,
    p_bt: float,
) -> float:
    """
    Transverse contact ratio εα (ISO 21771 §10.2).

        εα = (√(r_a1²−r_b1²) + √(r_a2²−r_b2²) − a_w·sin(α_w)) / p_bt

    where p_bt = π·m·cos(α) is the base-circle pitch.
    """
    ga = math.sqrt(max(0.0, r_a1**2 - r_b1**2))
    gb = math.sqrt(max(0.0, r_a2**2 - r_b2**2))
    eps = (ga + gb - a_w * math.sin(alpha_w)) / p_bt
    return eps


# ---------------------------------------------------------------------------
# T-1: gear_spur
# ---------------------------------------------------------------------------

_gear_spur_spec = ToolSpec(
    name="gear_spur",
    description=(
        "Generate a 2D involute spur gear profile (external, module system). "
        "Returns ISO 21771 gear data: pitch / base / root / tip diameters, "
        "addendum, dedendum, whole depth, circular pitch, tooth thickness, "
        "profile-shift coefficient, and a closed 2D tooth-profile polyline "
        "(sampled involute flanks + tip arc + root arc) for one tooth "
        "centred on the +X axis. "
        "Undercut risk is flagged when r_f < r_b. "
        "Pure-Python; no OCCT required — emit this as a parametric recipe / "
        "polyline ref for downstream solid modelling. "
        "Units: mm, degrees. "
        "Validation: m ≤ 0, z < 3, or α ∉ (10°, 30°) → {ok:false, errors:[...]}. "
        "Reference: ISO 21771:2007."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "module": {
                "type": "number",
                "description": "Module m (mm). Standard ISO values: 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12. Must be > 0.",
            },
            "teeth": {
                "type": "integer",
                "description": "Number of teeth z. Must be ≥ 3.",
            },
            "pressure_angle_deg": {
                "type": "number",
                "description": "Pressure angle α in degrees. Must be in (10°, 30°). Standard: 20°.",
            },
            "profile_shift": {
                "type": "number",
                "description": "Profile-shift coefficient x (dimensionless). Default 0. Use ≥ 0.5 for z < 17 to avoid undercut. ISO 21771 §8.",
            },
            "face_width": {
                "type": "number",
                "description": "Face width b (mm, axial length). Stored for reference; does not affect the 2D tooth profile. Must be > 0 if provided.",
            },
            "profile_points": {
                "type": "integer",
                "description": "Number of sample points per involute flank. Default 32. Min 4, max 256.",
            },
        },
        "required": ["module", "teeth"],
    },
)


@register(_gear_spur_spec, write=False)
async def run_gear_spur(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    try:
        m         = float(a.get("module", 0))
        z         = int(a.get("teeth", 0))
        alpha_deg = float(a.get("pressure_angle_deg", 20.0))
        x         = float(a.get("profile_shift", 0.0))
        face_w    = a.get("face_width")
        n_pts     = int(a.get("profile_points", 32))
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric argument required: {e}", "BAD_ARGS")

    errors = _validate_basic(m, z, alpha_deg)
    if face_w is not None:
        face_w = float(face_w)
        if face_w <= 0:
            errors.append(f"face_width must be > 0; got {face_w}")
    n_pts = max(4, min(256, n_pts))

    if errors:
        return ok_payload({"ok": False, "errors": errors})

    geom = _spur_geometry(m, z, alpha_deg, x, n_pts)
    result: dict[str, Any] = {"ok": True, **geom}
    if face_w is not None:
        result["face_width"] = round(face_w, 6)
    result["gear_type"] = "spur_external"
    result["recipe"] = {
        "op": "gear_spur",
        "module": m, "teeth": z,
        "pressure_angle_deg": alpha_deg,
        "profile_shift": x,
    }
    return ok_payload(result)


# ---------------------------------------------------------------------------
# T-2: gear_helical
# ---------------------------------------------------------------------------

_gear_helical_spec = ToolSpec(
    name="gear_helical",
    description=(
        "Generate a 2D involute helical gear profile. "
        "Extends gear_spur with a helix angle β. "
        "The transverse module m_t = m_n / cos(β), transverse pressure angle "
        "α_t from tan(α_t) = tan(α_n) / cos(β), and axial pitch p_x = π·m_n / sin(β). "
        "The tooth profile polyline is computed in the transverse plane (as for spur). "
        "Returns ISO 21771 helical gear data: normal module m_n, transverse module m_t, "
        "helix angle β, axial pitch p_x, normal / transverse pressure angles, "
        "and all spur-equivalent diameters. "
        "Validation: β ∉ (0°, 90°) exclusive, plus basic m/z/α validation. "
        "Units: mm, degrees. Reference: ISO 21771:2007 §3."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "module": {
                "type": "number",
                "description": "Normal module m_n (mm). Must be > 0.",
            },
            "teeth": {
                "type": "integer",
                "description": "Number of teeth z. Must be ≥ 3.",
            },
            "helix_angle_deg": {
                "type": "number",
                "description": "Helix angle β in degrees, in (0°, 90°). Typical: 15°–35°.",
            },
            "pressure_angle_deg": {
                "type": "number",
                "description": "Normal pressure angle α_n in degrees, in (10°, 30°). Standard: 20°.",
            },
            "profile_shift": {
                "type": "number",
                "description": "Profile-shift coefficient x. Default 0.",
            },
            "face_width": {
                "type": "number",
                "description": "Face width b (mm). Stored for reference. Must be > 0 if provided.",
            },
            "profile_points": {
                "type": "integer",
                "description": "Involute sample points per flank. Default 32.",
            },
        },
        "required": ["module", "teeth", "helix_angle_deg"],
    },
)


@register(_gear_helical_spec, write=False)
async def run_gear_helical(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    try:
        m_n       = float(a.get("module", 0))
        z         = int(a.get("teeth", 0))
        beta_deg  = float(a.get("helix_angle_deg", 0))
        alpha_n_deg = float(a.get("pressure_angle_deg", 20.0))
        x         = float(a.get("profile_shift", 0.0))
        face_w    = a.get("face_width")
        n_pts     = int(a.get("profile_points", 32))
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric argument required: {e}", "BAD_ARGS")

    errors = _validate_basic(m_n, z, alpha_n_deg)
    if not (0.0 < beta_deg < 90.0):
        errors.append(f"helix_angle_deg must be in (0°, 90°); got {beta_deg}")
    if face_w is not None:
        face_w = float(face_w)
        if face_w <= 0:
            errors.append(f"face_width must be > 0; got {face_w}")
    n_pts = max(4, min(256, n_pts))

    if errors:
        return ok_payload({"ok": False, "errors": errors})

    beta   = math.radians(beta_deg)
    alpha_n = math.radians(alpha_n_deg)

    # Transverse module and pressure angle (ISO 21771 §3.4)
    m_t = m_n / math.cos(beta)
    # tan(α_t) = tan(α_n) / cos(β)
    alpha_t = math.atan(math.tan(alpha_n) / math.cos(beta))
    alpha_t_deg = math.degrees(alpha_t)

    # Axial pitch (ISO 21771 §3.8)
    p_x = math.pi * m_n / math.sin(beta)

    # Compute transverse-plane geometry (using transverse module + angle)
    geom = _spur_geometry(m_t, z, alpha_t_deg, x, n_pts)

    # Overlap ratio (face contact ratio) εβ = b·sin(β) / (π·m_n)
    face_b = face_w if face_w is not None else 0.0
    eps_beta = face_b * math.sin(beta) / (math.pi * m_n) if face_b > 0 else None

    result: dict[str, Any] = {
        "ok": True,
        "gear_type": "helical_external",
        "normal_module": round(m_n, 8),
        "transverse_module": round(m_t, 8),
        "helix_angle_deg": round(beta_deg, 6),
        "normal_pressure_angle_deg": round(alpha_n_deg, 6),
        "transverse_pressure_angle_deg": round(alpha_t_deg, 6),
        "axial_pitch": round(p_x, 8),
        **geom,
    }
    if face_w is not None:
        result["face_width"] = round(face_w, 6)
    if eps_beta is not None:
        result["face_contact_ratio"] = round(eps_beta, 6)
    result["recipe"] = {
        "op": "gear_helical",
        "module": m_n, "teeth": z,
        "helix_angle_deg": beta_deg,
        "pressure_angle_deg": alpha_n_deg,
        "profile_shift": x,
    }
    return ok_payload(result)


# ---------------------------------------------------------------------------
# T-3: gear_internal  (ring gear)
# ---------------------------------------------------------------------------

def _internal_geometry(
    m: float,
    z: int,
    alpha_deg: float,
    x: float = 0.0,
    n_pts: int = 32,
) -> dict[str, Any]:
    """
    Internal (ring) gear geometry.

    For an internal gear the tooth form is concave (cut into the ring):
    - Pitch diameter   d   = m · z  (same formula)
    - Tip diameter     d_a = d − 2·m·(ha* − x)   (teeth point inward)
    - Root diameter    d_f = d + 2·m·(hf* + x)
    ISO 21771 §4 (internal gear sign conventions, §4.3).
    """
    alpha = math.radians(alpha_deg)

    d   = m * z
    d_b = d * math.cos(alpha)
    # Internal gear: addendum reduces the tip circle inward
    d_a = d - 2.0 * m * (_HA_COEFF - x)
    d_f = d + 2.0 * m * (_HF_COEFF + x)
    h_a = m * (_HA_COEFF - x)
    h_f = m * (_HF_COEFF + x)
    h   = h_a + h_f
    p   = math.pi * m
    s   = p / 2 + 2.0 * x * m * math.tan(alpha)

    r   = d / 2.0
    r_b = d_b / 2.0
    r_a = d_a / 2.0
    r_f = d_f / 2.0

    # Interference check: tip of pinion must not reach root of ring
    # (simple flag: r_a < r_b means internal geometry degenerate)
    degenerate = r_a <= r_b

    # Tooth polyline — same involute basis, but tip/root swapped (inner tooth)
    # For an internal gear, the involute still originates at r_b but the
    # tip is at r_a < r (pointing inward).  We parameterise using the
    # same approach but note r_a < r_b is possible for small shift or large z.
    t_tip  = _tip_roll_angle(r_b, max(r_a, r_b + 1e-9))
    t_root = _root_roll_angle(r_b, r_f)

    half_theta = _tooth_half_angle_pitch(alpha, z, x)
    offset_angle = half_theta - (alpha - _inv(alpha))

    right_inv = _sample_involute(r_b, t_root, t_tip, n_pts)
    right_flank = [_rotate(px, py, offset_angle) for px, py in right_inv]
    left_flank  = [(px, -py) for px, py in reversed(right_flank)]

    rx_tip, ry_tip = right_flank[-1]
    a_right_tip = math.atan2(ry_tip, rx_tip)
    rx_ltip, ry_ltip = left_flank[0]
    a_left_tip = math.atan2(ry_ltip, rx_ltip)
    tip_arc = _arc_points(max(r_a, r_b + 1e-9), a_right_tip, a_left_tip, max(4, n_pts // 8))

    rx_root, ry_root = right_flank[0]
    a_right_root = math.atan2(ry_root, rx_root)
    rx_lroot, ry_lroot = left_flank[-1]
    a_left_root = math.atan2(ry_lroot, rx_lroot)
    a_valley = a_right_root - math.pi / z
    root_arc_lo = _arc_points(r_f, a_right_root, a_valley, max(3, n_pts // 8))
    root_arc_hi = _arc_points(r_f, a_valley, a_left_root, max(3, n_pts // 8))

    polyline: list[list[float]] = []
    for px, py in right_flank:
        polyline.append([round(px, 8), round(py, 8)])
    for px, py in tip_arc[1:]:
        polyline.append([round(px, 8), round(py, 8)])
    for px, py in left_flank[1:]:
        polyline.append([round(px, 8), round(py, 8)])
    for px, py in root_arc_lo[1:] + root_arc_hi[1:]:
        polyline.append([round(px, 8), round(py, 8)])
    if polyline and polyline[0] != polyline[-1]:
        polyline.append(polyline[0])

    return {
        "module": round(m, 8),
        "teeth": z,
        "pressure_angle_deg": round(alpha_deg, 6),
        "profile_shift": round(x, 6),
        "pitch_diameter":  round(d,   8),
        "base_diameter":   round(d_b, 8),
        "tip_diameter":    round(d_a, 8),   # inner tip (smaller)
        "root_diameter":   round(d_f, 8),   # outer root (larger)
        "addendum":        round(h_a, 8),
        "dedendum":        round(h_f, 8),
        "whole_depth":     round(h,   8),
        "circular_pitch":  round(p,   8),
        "tooth_thickness": round(s,   8),
        "degenerate":      degenerate,
        "tooth_polyline":  polyline,
        "polyline_points": len(polyline),
        "polyline_note": (
            "Single-tooth 2D profile for internal (ring) gear, transverse plane, "
            "centred on +X axis. Tip diameter is the inner (smaller) circle. "
            "Reference: ISO 21771 §4.3."
        ),
    }


_gear_internal_spec = ToolSpec(
    name="gear_internal",
    description=(
        "Generate a 2D involute internal (ring/annular) gear profile. "
        "For an internal gear the teeth point inward: "
        "  tip diameter   d_a = d − 2·m·(ha*−x)  (inner, smaller than pitch circle) "
        "  root diameter  d_f = d + 2·m·(hf*+x)  (outer, larger than pitch circle). "
        "Returns ISO 21771 ring-gear data + closed tooth polyline. "
        "Validation: m ≤ 0, z < 3, α ∉ (10°, 30°) → {ok:false, errors:[...]}. "
        "Units: mm, degrees. Reference: ISO 21771:2007 §4.3."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "module": {
                "type": "number",
                "description": "Module m (mm). Must be > 0.",
            },
            "teeth": {
                "type": "integer",
                "description": "Number of teeth z (ring). Must be ≥ 3.",
            },
            "pressure_angle_deg": {
                "type": "number",
                "description": "Pressure angle α in degrees, in (10°, 30°). Standard: 20°.",
            },
            "profile_shift": {
                "type": "number",
                "description": "Profile-shift coefficient x. Default 0.",
            },
            "profile_points": {
                "type": "integer",
                "description": "Involute sample points per flank. Default 32.",
            },
        },
        "required": ["module", "teeth"],
    },
)


@register(_gear_internal_spec, write=False)
async def run_gear_internal(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    try:
        m         = float(a.get("module", 0))
        z         = int(a.get("teeth", 0))
        alpha_deg = float(a.get("pressure_angle_deg", 20.0))
        x         = float(a.get("profile_shift", 0.0))
        n_pts     = int(a.get("profile_points", 32))
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric argument required: {e}", "BAD_ARGS")

    errors = _validate_basic(m, z, alpha_deg)
    n_pts = max(4, min(256, n_pts))

    if errors:
        return ok_payload({"ok": False, "errors": errors})

    geom = _internal_geometry(m, z, alpha_deg, x, n_pts)
    result: dict[str, Any] = {
        "ok": True,
        "gear_type": "internal_ring",
        **geom,
        "recipe": {
            "op": "gear_internal",
            "module": m, "teeth": z,
            "pressure_angle_deg": alpha_deg,
            "profile_shift": x,
        },
    }
    return ok_payload(result)


# ---------------------------------------------------------------------------
# T-4: gear_rack
# ---------------------------------------------------------------------------

def _rack_geometry(
    m: float,
    alpha_deg: float,
    n_teeth: int = 6,
) -> dict[str, Any]:
    """
    Linear rack geometry.

    A rack is a gear with infinite radius.  One tooth profile:
        - Tooth height  h = (ha* + hf*) · m  (addendum + dedendum)
        - Linear pitch  p = π · m             (ISO 21771 §3.7)
        - Tooth spacing (half-pitch) = p/2
        - Flank is a straight line at pressure angle α from the pitch line
    ISO 21771 §4.4.
    """
    alpha = math.radians(alpha_deg)
    p     = math.pi * m
    h_a   = _HA_COEFF * m
    h_f   = _HF_COEFF * m
    h     = h_a + h_f
    s     = p / 2.0   # tooth thickness at pitch line

    # Build tooth polyline for one rack tooth (centred at x=0, y=0 on pitch line)
    # Points (going CCW): root-left → flank-left → tip-left → tip-right → flank-right → root-right
    half_s_tip = h_a * math.tan(alpha)   # half tooth width at tip (ISO 21771)
    half_s_root = half_s_tip + h * math.tan(alpha)  # half tooth width at root

    # One tooth centred at pitch-line origin x=0
    pts: list[list[float]] = [
        [-half_s_root, -h_f],            # root left
        [-s / 2.0, -h_f],                 # root left (flat root)
        [-(s / 2.0 - h * math.tan(alpha)), h_a],  # tip left (flank)
        [(s / 2.0 - h * math.tan(alpha)), h_a],   # tip right (flat tip)
        [s / 2.0, -h_f],                  # root right (flank)
        [half_s_root, -h_f],              # root right
        [-half_s_root, -h_f],            # close
    ]

    # Build a multi-tooth rack outline (n_teeth centred)
    rack_pts: list[list[float]] = []
    offset_x = -(n_teeth // 2) * p
    for i in range(n_teeth):
        cx = offset_x + i * p
        for pt in pts[:-1]:  # skip close repeat per tooth
            rack_pts.append([round(cx + pt[0], 8), round(pt[1], 8)])
    rack_pts.append(rack_pts[0])  # close

    return {
        "module": round(m, 8),
        "pressure_angle_deg": round(alpha_deg, 6),
        "linear_pitch": round(p, 8),
        "addendum": round(h_a, 8),
        "dedendum": round(h_f, 8),
        "whole_depth": round(h, 8),
        "tooth_thickness": round(s, 8),
        "n_teeth_shown": n_teeth,
        "tooth_polyline": [[round(pt[0], 8), round(pt[1], 8)] for pt in pts],
        "rack_polyline":  rack_pts,
        "polyline_note": (
            "tooth_polyline: one tooth centred at x=0 on the pitch line (y=0). "
            "rack_polyline: n_teeth_shown teeth centred around origin. "
            "Reference: ISO 21771 §4.4."
        ),
    }


_gear_rack_spec = ToolSpec(
    name="gear_rack",
    description=(
        "Generate a 2D involute rack tooth profile (linear gear). "
        "A rack is a gear with infinite radius; the tooth flanks are straight "
        "lines at the pressure angle α from the pitch line. "
        "Returns: linear_pitch p = π·m, addendum, dedendum, whole depth, "
        "tooth thickness, a single-tooth polyline, and an n-tooth rack outline. "
        "Validation: m ≤ 0, α ∉ (10°, 30°) → {ok:false, errors:[...]}. "
        "Units: mm, degrees. Reference: ISO 21771:2007 §4.4."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "module": {
                "type": "number",
                "description": "Module m (mm). Must be > 0.",
            },
            "pressure_angle_deg": {
                "type": "number",
                "description": "Pressure angle α in degrees, in (10°, 30°). Standard: 20°.",
            },
            "n_teeth": {
                "type": "integer",
                "description": "Number of teeth to include in the rack outline. Default 6. Range [2, 50].",
            },
        },
        "required": ["module"],
    },
)


@register(_gear_rack_spec, write=False)
async def run_gear_rack(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    try:
        m         = float(a.get("module", 0))
        alpha_deg = float(a.get("pressure_angle_deg", 20.0))
        n_teeth   = int(a.get("n_teeth", 6))
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric argument required: {e}", "BAD_ARGS")

    errors: list[str] = []
    if m <= 0:
        errors.append(f"module m must be > 0; got {m}")
    if not (_ALPHA_MIN < alpha_deg < _ALPHA_MAX):
        errors.append(
            f"pressure angle α must be in ({_ALPHA_MIN}°, {_ALPHA_MAX}°); got {alpha_deg}°"
        )
    n_teeth = max(2, min(50, n_teeth))

    if errors:
        return ok_payload({"ok": False, "errors": errors})

    geom = _rack_geometry(m, alpha_deg, n_teeth)
    result: dict[str, Any] = {
        "ok": True,
        "gear_type": "rack_linear",
        **geom,
        "recipe": {
            "op": "gear_rack",
            "module": m,
            "pressure_angle_deg": alpha_deg,
        },
    }
    return ok_payload(result)


# ---------------------------------------------------------------------------
# T-5: gear_pair_check
# ---------------------------------------------------------------------------

_gear_pair_check_spec = ToolSpec(
    name="gear_pair_check",
    description=(
        "Mesh-check two external spur gears: compute centre distance, gear ratio, "
        "transverse contact ratio εα, and flag undercut / interference risk. "
        "For a standard (x1=x2=0) mesh: a_w = (d1+d2)/2 = m·(z1+z2)/2. "
        "For a profile-shifted mesh: operating pressure angle α_w is solved from "
        "  inv(α_w) = inv(α) + 2·(x1+x2)·tan(α)/(z1+z2). "
        "Contact ratio εα > 1.2 is recommended for smooth transmission. "
        "Interference warning when z < 17 and no profile shift. "
        "Returns: {ok, gear_ratio, centre_distance, contact_ratio, "
        "alpha_w_deg, warnings:[...]}. "
        "Validation: m mismatch (gears must share the same module), "
        "α mismatch, basic z/m/α checks → {ok:false, errors:[...]}. "
        "Units: mm, degrees. Reference: ISO 21771:2007 §10."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "module": {
                "type": "number",
                "description": "Shared module m (mm). Both gears must use the same module.",
            },
            "teeth_1": {
                "type": "integer",
                "description": "Tooth count of gear 1 (driver). Must be ≥ 3.",
            },
            "teeth_2": {
                "type": "integer",
                "description": "Tooth count of gear 2 (driven). Must be ≥ 3.",
            },
            "pressure_angle_deg": {
                "type": "number",
                "description": "Pressure angle α in degrees, in (10°, 30°). Standard: 20°.",
            },
            "profile_shift_1": {
                "type": "number",
                "description": "Profile-shift coefficient x1 for gear 1. Default 0.",
            },
            "profile_shift_2": {
                "type": "number",
                "description": "Profile-shift coefficient x2 for gear 2. Default 0.",
            },
        },
        "required": ["module", "teeth_1", "teeth_2"],
    },
)


@register(_gear_pair_check_spec, write=False)
async def run_gear_pair_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    try:
        m         = float(a.get("module", 0))
        z1        = int(a.get("teeth_1", 0))
        z2        = int(a.get("teeth_2", 0))
        alpha_deg = float(a.get("pressure_angle_deg", 20.0))
        x1        = float(a.get("profile_shift_1", 0.0))
        x2        = float(a.get("profile_shift_2", 0.0))
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric argument required: {e}", "BAD_ARGS")

    errors: list[str] = []
    if m <= 0:
        errors.append(f"module m must be > 0; got {m}")
    if z1 < 3:
        errors.append(f"teeth_1 must be ≥ 3; got {z1}")
    if z2 < 3:
        errors.append(f"teeth_2 must be ≥ 3; got {z2}")
    if not (_ALPHA_MIN < alpha_deg < _ALPHA_MAX):
        errors.append(
            f"pressure angle α must be in ({_ALPHA_MIN}°, {_ALPHA_MAX}°); got {alpha_deg}°"
        )
    if errors:
        return ok_payload({"ok": False, "errors": errors})

    alpha = math.radians(alpha_deg)

    # Basic gear geometry
    d1, d2 = m * z1, m * z2
    d_b1, d_b2 = d1 * math.cos(alpha), d2 * math.cos(alpha)
    d_a1 = d1 + 2.0 * m * (_HA_COEFF + x1)
    d_a2 = d2 + 2.0 * m * (_HA_COEFF + x2)
    d_f1 = d1 - 2.0 * m * (_HF_COEFF - x1)
    d_f2 = d2 - 2.0 * m * (_HF_COEFF - x2)

    r1, r2       = d1 / 2, d2 / 2
    r_b1, r_b2   = d_b1 / 2, d_b2 / 2
    r_a1, r_a2   = d_a1 / 2, d_a2 / 2
    r_f1, r_f2   = d_f1 / 2, d_f2 / 2

    # Gear ratio (ISO 21771 §3.12)
    gear_ratio = z2 / z1

    # --- Operating pressure angle α_w (ISO 21771 §10.1) ---
    # inv(α_w) = inv(α) + 2·(x1+x2)·tan(α) / (z1+z2)
    inv_alpha = _inv(alpha)
    inv_alpha_w = inv_alpha + 2.0 * (x1 + x2) * math.tan(alpha) / (z1 + z2)
    # Solve α_w by Newton iteration: inv(t) - inv_alpha_w = 0
    # Starting guess: α (if x_sum = 0 then α_w = α)
    alpha_w = alpha
    for _ in range(40):
        f  = _inv(alpha_w) - inv_alpha_w
        # derivative of inv(t) = d/dt(tan t - t) = tan²(t) = sec²(t)-1
        df = math.tan(alpha_w) ** 2
        if abs(df) < 1e-14:
            break
        delta = f / df
        alpha_w -= delta
        if abs(delta) < 1e-14:
            break
    alpha_w = max(0.001, alpha_w)   # guard against degenerate
    alpha_w_deg = math.degrees(alpha_w)

    # --- Centre distance (ISO 21771 §10.1) ---
    # a_w = (r_b1 + r_b2) / cos(α_w)
    a_w = (r_b1 + r_b2) / math.cos(alpha_w)
    a_std = (r1 + r2)   # standard centre distance (x1=x2=0)

    # --- Base-circle pitch ---
    p_bt = math.pi * m * math.cos(alpha)

    # --- Contact ratio εα (ISO 21771 §10.2) ---
    eps_alpha = _contact_ratio(r_a1, r_b1, r_a2, r_b2, a_w, alpha_w, p_bt)

    # --- Warnings ---
    warnings: list[str] = []

    if r_f1 < r_b1:
        warnings.append(
            f"Gear 1: undercut risk — root circle (r_f={r_f1:.3f}) inside base circle "
            f"(r_b={r_b1:.3f}). Consider profile shift x1 ≥ "
            f"{round((17 - z1) / 17, 3)} (Wildhaber)."
        )
    if r_f2 < r_b2:
        warnings.append(
            f"Gear 2: undercut risk — root circle (r_f={r_f2:.3f}) inside base circle "
            f"(r_b={r_b2:.3f}). Consider profile shift x2 ≥ "
            f"{round((17 - z2) / 17, 3)} (Wildhaber)."
        )

    # Minimum tooth count undercut check (ISO 21771 §10.3)
    if z1 < _Z_UNDERCUT and abs(x1) < 0.01:
        warnings.append(
            f"Gear 1: z={z1} < {_Z_UNDERCUT} at α={alpha_deg}° with no profile shift — "
            "undercut likely. Apply positive profile shift."
        )
    if z2 < _Z_UNDERCUT and abs(x2) < 0.01:
        warnings.append(
            f"Gear 2: z={z2} < {_Z_UNDERCUT} at α={alpha_deg}° with no profile shift — "
            "undercut likely. Apply positive profile shift."
        )

    if eps_alpha < 1.0:
        warnings.append(
            f"Contact ratio εα = {eps_alpha:.3f} < 1.0 — gears will not transmit "
            "continuous motion (tooth loss between contacts)."
        )
    elif eps_alpha < 1.2:
        warnings.append(
            f"Contact ratio εα = {eps_alpha:.3f} < 1.2 — acceptable but low; "
            "consider increasing addendum or reducing centre distance."
        )

    # Tip interference: tip of one gear reaching root of the other
    # (r_a1 - a_w) > r_b2 ← tip of 1 exceeds tangent of base circle of 2
    tangent_len_1 = math.sqrt(max(0.0, r_a1**2 - r_b1**2))
    tangent_len_2 = math.sqrt(max(0.0, r_a2**2 - r_b2**2))
    line_of_action = a_w * math.sin(alpha_w)
    if tangent_len_1 > line_of_action + 1e-6:
        warnings.append(
            "Tip interference: tip of gear 1 extends beyond the interference point "
            "of gear 2. Reduce addendum of gear 1 or increase profile shift."
        )
    if tangent_len_2 > line_of_action + 1e-6:
        warnings.append(
            "Tip interference: tip of gear 2 extends beyond the interference point "
            "of gear 1. Reduce addendum of gear 2 or increase profile shift."
        )

    result: dict[str, Any] = {
        "ok": True,
        "gear_ratio": round(gear_ratio, 8),
        "centre_distance": round(a_w, 8),
        "standard_centre_distance": round(a_std, 8),
        "centre_distance_offset": round(a_w - a_std, 8),
        "operating_pressure_angle_deg": round(alpha_w_deg, 6),
        "contact_ratio": round(eps_alpha, 6),
        "warnings": warnings,
        "gear_1": {
            "teeth": z1, "profile_shift": x1,
            "pitch_diameter": round(d1, 6),
            "base_diameter": round(d_b1, 6),
            "tip_diameter": round(d_a1, 6),
            "root_diameter": round(d_f1, 6),
        },
        "gear_2": {
            "teeth": z2, "profile_shift": x2,
            "pitch_diameter": round(d2, 6),
            "base_diameter": round(d_b2, 6),
            "tip_diameter": round(d_a2, 6),
            "root_diameter": round(d_f2, 6),
        },
    }
    return ok_payload(result)
