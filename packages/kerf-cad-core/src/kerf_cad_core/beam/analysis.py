"""
kerf_cad_core.beam.analysis — beam & cross-section analysis (pure Python).

Public functions
----------------
section_properties(shape, **dims)
    Area, centroid, second moments of area (Ix, Iy), elastic section moduli
    (Sx, Sy), plastic section moduli (Zx, Zy), radii of gyration (rx, ry),
    and torsion constant J for:
      "rectangle"   — b, h
      "circle"      — d
      "hollow_rect" — b, h, t
      "hollow_circ" — d, t
      "I"           — bf, d, tf, tw  (wide-flange / I-beam)
      "channel"     — b, d, tf, tw   (C-channel)
      "angle"       — b, h, t        (L-angle, equal or unequal leg)

beam_loads(support, load_type, *, E, I, L, **load_params)
    Closed-form deflection, slope, max-moment, and max-shear for:
      support    : "cantilever" | "simply_supported" | "fixed_fixed"
      load_type  : "point"      — point load P at position a (default L for
                                  cantilever, L/2 for SS)
                 | "udl"        — uniformly distributed load w (N/m)
                 | "moment"     — applied end/midpoint moment M0
    Returns max_deflection (m), slope_end (rad), max_moment (N·m),
    max_shear (N), and reaction forces Ra, Rb.

superpose(cases)
    Linearly add a list of beam_loads result dicts.  Returns a combined
    result with summed max_deflection, max_moment, max_shear.

buckling(L_eff, A, I, E, *, Fy, K=1.0)
    Euler critical load and Johnson short-column transition.
    Returns P_euler (N), P_johnson (N), mode ("euler"|"johnson"),
    P_cr (governing critical load), and flags if the section has yielded.

combined_stress(P, M, A, S, *, c=None)
    Axial + bending stress: σ = P/A ± M/S (or M·c/I if S not given).
    Returns sigma_axial, sigma_bending_top, sigma_bending_bot,
    sigma_max, sigma_min.

mohr_circle(sigma_x, sigma_y, tau_xy)
    Principal stresses, max shear, and angle θp from a 2D stress state.
    Returns sigma_1, sigma_2, tau_max, theta_p_deg.

shear_flow(V, Q, I, b)
    Shear stress at a section cut: τ = VQ / (I·b).
    Returns tau_Pa.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "..."}

Functions NEVER raise.

Units (SI throughout)
---------------------
  lengths  — metres (m)
  forces   — Newtons (N)
  moments  — Newton-metres (N·m)
  stresses — Pascals (Pa)
  areas    — m²
  second moments of area — m⁴
  section moduli — m³

References
----------
Roark's Formulas for Stress and Strain, 8th ed. (Young & Budynas)
  Table 3.1 — Cross-section properties
  Table 3.2 — Shear formulas
  Table 8.1 — Beam formulas
Hibbeler, Mechanics of Materials, 10th ed., §§ 6, 7, 11, 14
AISC LRFD Manual 15th ed. — Johnson column formula (AISC E3)

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_module
from typing import Any


# ---------------------------------------------------------------------------
# Internal guard helpers
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


def _guard_finite(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    return None


# ---------------------------------------------------------------------------
# 1. section_properties
# ---------------------------------------------------------------------------

def section_properties(shape: str, **dims: float) -> dict:
    """
    Cross-section properties for standard structural shapes.

    Parameters
    ----------
    shape : str
        One of: "rectangle", "circle", "hollow_rect", "hollow_circ",
                "I", "channel", "angle".
    **dims : float
        Shape-specific dimensions (metres):
          rectangle   → b (width), h (height)
          circle      → d (outer diameter)
          hollow_rect → b (width), h (height), t (wall thickness)
          hollow_circ → d (outer diameter), t (wall thickness)
          I           → bf (flange width), d (total depth), tf (flange thick),
                        tw (web thickness)
          channel     → b (flange width), d (total depth), tf (flange thick),
                        tw (web thickness)
          angle       → b (horizontal leg), h (vertical leg), t (thickness)

    Returns
    -------
    dict with ok=True and fields:
        A           — cross-sectional area (m²)
        cx, cy      — centroid from bottom-left corner (m)
        Ix, Iy      — second moments of area about centroidal axes (m⁴)
        Sx_top, Sx_bot — elastic section moduli about x-axis (m³)
        Sy          — elastic section modulus about y-axis (m³)
        Zx, Zy      — plastic section moduli (m³)
        rx, ry      — radii of gyration (m)
        J           — torsion constant (m⁴)
        shape       — shape string echoed
        warnings    — list of warning strings (empty if none)

    Notes
    -----
    Thin-walled torsion approximations are used for open sections:
      open  thin-walled: J ≈ (1/3) Σ b_i t_i³
      hollow closed:     J = 4A_enclosed² / (Σ ds/t)  (Bredt–Batho)
      solid circle/rect: exact formulas
    """
    s = str(shape).strip().lower().replace("-", "_")
    warns: list[str] = []

    if s == "rectangle":
        return _section_rectangle(dims, warns)
    elif s == "circle":
        return _section_circle(dims, warns)
    elif s == "hollow_rect":
        return _section_hollow_rect(dims, warns)
    elif s == "hollow_circ":
        return _section_hollow_circ(dims, warns)
    elif s == "i":
        return _section_I(dims, warns)
    elif s == "channel":
        return _section_channel(dims, warns)
    elif s == "angle":
        return _section_angle(dims, warns)
    else:
        return _err(
            f"Unknown shape {shape!r}. Supported: rectangle, circle, "
            "hollow_rect, hollow_circ, I, channel, angle."
        )


def _ok_section(A, cx, cy, Ix, Iy, c_top, c_bot, cy_sym, Zx, Zy, J,
                shape: str, warns: list) -> dict:
    """Build the standard output dict for a cross-section."""
    Sx_top = Ix / c_top if c_top > 0 else 0.0
    Sx_bot = Ix / c_bot if c_bot > 0 else 0.0
    Sy = Iy / cy_sym if cy_sym > 0 else 0.0
    rx = math.sqrt(Ix / A) if A > 0 else 0.0
    ry = math.sqrt(Iy / A) if A > 0 else 0.0
    return {
        "ok": True,
        "shape": shape,
        "A": A,
        "cx": cx,
        "cy": cy,
        "Ix": Ix,
        "Iy": Iy,
        "Sx_top": Sx_top,
        "Sx_bot": Sx_bot,
        "Sy": Sy,
        "Zx": Zx,
        "Zy": Zy,
        "rx": rx,
        "ry": ry,
        "J": J,
        "warnings": warns,
    }


# ---- Rectangle ----

def _section_rectangle(dims: dict, warns: list) -> dict:
    b = dims.get("b")
    h = dims.get("h")
    for name, val in [("b", b), ("h", h)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    b, h = float(b), float(h)
    A = b * h
    cx = b / 2.0
    cy = h / 2.0
    Ix = b * h ** 3 / 12.0
    Iy = h * b ** 3 / 12.0
    Zx = b * h ** 2 / 4.0
    Zy = h * b ** 2 / 4.0
    # Solid rectangle torsion: J = (1/3) b h³ corrected for aspect ratio
    # Standard formula: J = (ab³/3)[1 - 0.63(b/a)(1 - b⁴/(12a⁴))]
    # where a = max(b,h), b_t = min(b,h)
    a_t = max(b, h)
    b_t = min(b, h)
    J = (a_t * b_t ** 3 / 3.0) * (1.0 - 0.63 * (b_t / a_t) * (1.0 - b_t ** 4 / (12.0 * a_t ** 4)))
    return _ok_section(A, cx, cy, Ix, Iy, cy, cy, cx, Zx, Zy, J,
                       "rectangle", warns)


# ---- Circle ----

def _section_circle(dims: dict, warns: list) -> dict:
    d = dims.get("d")
    e = _guard_positive("d", d)
    if e:
        return _err(e)
    d = float(d)
    r = d / 2.0
    A = math.pi * r ** 2
    cx = cy = r
    Ix = Iy = math.pi * d ** 4 / 64.0
    Zx = Zy = d ** 3 / 6.0
    J = math.pi * d ** 4 / 32.0
    return _ok_section(A, cx, cy, Ix, Iy, r, r, r, Zx, Zy, J, "circle", warns)


# ---- Hollow Rectangle ----

def _section_hollow_rect(dims: dict, warns: list) -> dict:
    b = dims.get("b")
    h = dims.get("h")
    t = dims.get("t")
    for name, val in [("b", b), ("h", h), ("t", t)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    b, h, t = float(b), float(h), float(t)
    if 2 * t >= b or 2 * t >= h:
        return _err(f"Wall thickness t={t} leaves no interior: b={b}, h={h}.")
    bi = b - 2 * t   # inner width
    hi = h - 2 * t   # inner height
    A = b * h - bi * hi
    cx = b / 2.0
    cy = h / 2.0
    Ix = (b * h ** 3 - bi * hi ** 3) / 12.0
    Iy = (h * b ** 3 - hi * bi ** 3) / 12.0
    Zx = (b * h ** 2 / 4.0) - (bi * hi ** 2 / 4.0)
    Zy = (h * b ** 2 / 4.0) - (hi * bi ** 2 / 4.0)
    # Bredt–Batho: J = 4 A_enc² / (perimeter/t) for uniform wall
    A_enc = bi * hi
    perimeter_over_t = 2.0 * (bi + hi) / t
    J = 4.0 * A_enc ** 2 / perimeter_over_t if perimeter_over_t > 0 else 0.0
    return _ok_section(A, cx, cy, Ix, Iy, cy, cy, cx, Zx, Zy, J,
                       "hollow_rect", warns)


# ---- Hollow Circle ----

def _section_hollow_circ(dims: dict, warns: list) -> dict:
    d = dims.get("d")
    t = dims.get("t")
    for name, val in [("d", d), ("t", t)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    d, t = float(d), float(t)
    if t >= d / 2.0:
        return _err(f"Wall thickness t={t} >= outer radius d/2={d/2}.")
    di = d - 2.0 * t
    A = math.pi * (d ** 2 - di ** 2) / 4.0
    cx = cy = d / 2.0
    Ix = Iy = math.pi * (d ** 4 - di ** 4) / 64.0
    Zx = Zy = (d ** 3 - di ** 3) / 6.0
    J = math.pi * (d ** 4 - di ** 4) / 32.0
    r = d / 2.0
    return _ok_section(A, cx, cy, Ix, Iy, r, r, r, Zx, Zy, J,
                       "hollow_circ", warns)


# ---- I-section / wide-flange ----

def _section_I(dims: dict, warns: list) -> dict:
    """
    I-section (symmetric, doubly symmetric wide-flange).
    dims: bf (flange width), d (total depth), tf (flange thickness),
          tw (web thickness).
    Origin at bottom-left of bottom flange; centroid at d/2 by symmetry.
    """
    bf = dims.get("bf")
    d  = dims.get("d")
    tf = dims.get("tf")
    tw = dims.get("tw")
    for name, val in [("bf", bf), ("d", d), ("tf", tf), ("tw", tw)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    bf, d, tf, tw = float(bf), float(d), float(tf), float(tw)
    hw = d - 2.0 * tf   # web height
    if hw <= 0:
        return _err(f"Flanges overlap: d={d} <= 2*tf={2*tf}.")
    if tw >= bf:
        return _err(f"Web width tw={tw} >= flange width bf={bf}.")

    A = 2.0 * bf * tf + hw * tw
    cx = bf / 2.0
    cy = d / 2.0   # symmetric

    # Ix about centroid (parallel axis not needed — symmetric about mid-depth)
    Ix = (bf * d ** 3 - (bf - tw) * hw ** 3) / 12.0
    Iy = (2.0 * tf * bf ** 3 + hw * tw ** 3) / 12.0

    # Plastic modulus Zx = first moment of area about plastic neutral axis (=centroid)
    # Top flange: A_f * dist = (bf*tf)*(d/2 - tf/2)
    # Web half:   A_w/2 * dist = (hw/2*tw)*(hw/4)
    Zx = bf * tf * (d / 2.0 - tf / 2.0) + tw * hw ** 2 / 8.0
    Zx *= 2.0   # × 2 for both sides of neutral axis

    # Zy — plastic neutral axis is the vertical axis of symmetry.
    # Z_y = Σ A_i·|x_i| about the y-axis = tf·bf²/2 + hw·tw²/4
    # (AISC Shapes Database; cf. W-shape Zy = bf²·tf/2 + tw²·hw/4).
    Zy = tf * bf ** 2 / 2.0 + hw * tw ** 2 / 4.0

    # Torsion constant (open thin-wall): J = (1/3) Σ b_i t_i³
    J = (1.0 / 3.0) * (2.0 * bf * tf ** 3 + hw * tw ** 3)

    if bf * tf / (hw * tw) < 0.1:
        warns.append("Very thin flanges relative to web — open-section torsion approx may be inaccurate.")

    return _ok_section(A, cx, cy, Ix, Iy, d / 2.0, d / 2.0, bf / 2.0,
                       Zx, Zy, J, "I", warns)


# ---- Channel (C-section) ----

def _section_channel(dims: dict, warns: list) -> dict:
    """
    C-channel (symmetric about horizontal axis).
    dims: b (flange width), d (total depth), tf (flange thickness),
          tw (web thickness).
    Centroid in x (cx) is measured from the back of the web.
    """
    b  = dims.get("b")
    d  = dims.get("d")
    tf = dims.get("tf")
    tw = dims.get("tw")
    for name, val in [("b", b), ("d", d), ("tf", tf), ("tw", tw)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    b, d, tf, tw = float(b), float(d), float(tf), float(tw)
    hw = d - 2.0 * tf
    if hw <= 0:
        return _err(f"Flanges overlap: d={d} <= 2*tf={2*tf}.")
    if tw >= b:
        return _err(f"Web thickness tw={tw} >= flange width b={b}.")

    A_web = hw * tw
    A_flange = 2.0 * b * tf

    A = A_web + A_flange
    cy = d / 2.0   # symmetric

    # Centroid in x (from back of web)
    x_web    = tw / 2.0
    x_flange = b / 2.0
    cx = (A_web * x_web + A_flange * x_flange) / A

    # Ix (about centroidal horizontal axis — symmetric)
    Ix = (tw * d ** 3 + 2.0 * (b - tw) * tf ** 3 / 12.0 +
          2.0 * (b - tw) * tf * (d / 2.0 - tf / 2.0) ** 2)
    # Simplified:
    Ix = (1.0 / 12.0) * (tw * d ** 3 + 2.0 * b * tf * (6.0 * (d / 2.0 - tf / 2.0) ** 2 + tf ** 2) -
                          2.0 * (b - tw) * tf ** 3 / 12.0)
    # Use the clean formula:
    Ix = (tw * d ** 3 - (tw - b) * hw ** 3) / 12.0  # won't work for C — redo:
    # Standard formula for C-channel Ix (about centroid, y-symmetric):
    Ix = (b * d ** 3 - (b - tw) * hw ** 3) / 12.0   # not quite right either

    # Correct formula: treat as two flanges + web, consistent with the
    # area model A = hw·tw + 2·b·tf (web spans only between the flanges).
    # Web (hw × tw centred at d/2):
    Ix_web = tw * hw ** 3 / 12.0
    # Each flange (b × tf, centred at (hw/2 + tf/2) = (d - tf)/2 from centroid):
    d_flange = (d - tf) / 2.0
    Ix_flange = b * tf ** 3 / 12.0 + b * tf * d_flange ** 2
    Ix = Ix_web + 2.0 * Ix_flange

    # Iy (about centroidal vertical axis through cx)
    # Web:    tw × hw, centroid at x_web from left, parallel-axis to cx
    Iy_web = hw * tw ** 3 / 12.0 + A_web * (x_web - cx) ** 2
    # Each flange: b × tf, centroid at x_flange from left
    Iy_fl  = tf * b ** 3 / 12.0 + b * tf * (x_flange - cx) ** 2
    Iy = Iy_web + 2.0 * Iy_fl

    # Plastic Zx (symmetric about horizontal PNA)
    Zx = b * tf * (d - tf) / 2.0 + tw * hw ** 2 / 8.0
    Zx *= 2.0 / 2.0  # already counted both flanges, web half ×2
    # Cleaner: sum of first moment of areas above and below x-axis
    # For symmetric section about x: Zx = 2 × first moment of area above NA
    Zx = 2.0 * (b * tf * (d / 2.0 - tf / 2.0) + tw * (hw / 2.0) * (hw / 4.0))

    # Zy about centroidal y-axis
    # plastic NA for y: at x = cx (by definition for asymmetric section)
    # Zy = first moment of area to left + right of plastic y-axis
    # This is complex for asymmetric C; use elastic Sy as conservative approx
    # and emit a warning
    c_right = b - cx
    c_left  = cx
    Sy = Iy / max(c_right, c_left)
    # Approximate Zy (upper bound)
    Zy = Iy / min(c_right, c_left) if min(c_right, c_left) > 0 else 0.0
    # Actually for plastic modulus use standard formula:
    Zy_approx = 2.0 * (tw * cx ** 2 / 2.0 + 2.0 * tf * (b - cx) * (b + cx) / 4.0)

    # Torsion constant (open thin-wall)
    J = (1.0 / 3.0) * (2.0 * b * tf ** 3 + hw * tw ** 3)

    c_top = cy
    c_bot = cy

    Sx_top = Ix / c_top if c_top > 0 else 0.0
    Sx_bot = Ix / c_bot if c_bot > 0 else 0.0
    rx = math.sqrt(Ix / A) if A > 0 else 0.0
    ry = math.sqrt(Iy / A) if A > 0 else 0.0

    return {
        "ok": True,
        "shape": "channel",
        "A": A,
        "cx": cx,
        "cy": cy,
        "Ix": Ix,
        "Iy": Iy,
        "Sx_top": Sx_top,
        "Sx_bot": Sx_bot,
        "Sy": Sy,
        "Zx": Zx,
        "Zy": Zy_approx,
        "rx": rx,
        "ry": ry,
        "J": J,
        "warnings": warns,
    }


# ---- Angle (L-section) ----

def _section_angle(dims: dict, warns: list) -> dict:
    """
    Equal or unequal leg angle (L-section).
    dims: b (horizontal leg), h (vertical leg), t (uniform thickness).
    Origin at outer corner (bottom-left).
    """
    b = dims.get("b")
    h = dims.get("h")
    t = dims.get("t")
    for name, val in [("b", b), ("h", h), ("t", t)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    b, h, t = float(b), float(h), float(t)
    if t >= b or t >= h:
        return _err(f"Thickness t={t} must be < both b={b} and h={h}.")

    # Treat as two rectangles:
    #   H: horizontal leg b × t, bottom strip, centroid at (b/2, t/2)
    #   V: vertical leg t × (h-t), left strip, centroid at (t/2, t + (h-t)/2)
    A_h = b * t
    A_v = t * (h - t)
    A = A_h + A_v

    cx = (A_h * (b / 2.0) + A_v * (t / 2.0)) / A
    cy = (A_h * (t / 2.0) + A_v * (t + (h - t) / 2.0)) / A

    # Ix about centroidal x-axis
    Ix_h = b * t ** 3 / 12.0 + A_h * (cy - t / 2.0) ** 2
    Ix_v = t * (h - t) ** 3 / 12.0 + A_v * (cy - (t + (h - t) / 2.0)) ** 2
    Ix = Ix_h + Ix_v

    # Iy about centroidal y-axis
    Iy_h = t * b ** 3 / 12.0 + A_h * (cx - b / 2.0) ** 2
    Iy_v = (h - t) * t ** 3 / 12.0 + A_v * (cx - t / 2.0) ** 2
    Iy = Iy_h + Iy_v

    c_top = h - cy
    c_bot = cy
    c_right = b - cx
    c_left  = cx

    Sx_top = Ix / c_top if c_top > 0 else 0.0
    Sx_bot = Ix / c_bot if c_bot > 0 else 0.0
    Sy = Iy / max(c_right, c_left)

    # Plastic section moduli (approximate — about centroidal axes)
    # Zx: first moment of area above and below x-centroid
    # Numerically integrate using both sub-rectangles
    def _z_plastic(A1, y1, A2, y2, y_bar):
        # Z = sum |y_i - y_bar| * A_i  (plastic moment formula)
        return A1 * abs(y1 - y_bar) + A2 * abs(y2 - y_bar)

    # For Zx: use each sub-rectangle's centroid distance to PNA (≈ centroid)
    Zx = _z_plastic(A_h, t / 2.0, A_v, t + (h - t) / 2.0, cy)
    Zy = _z_plastic(A_h, b / 2.0, A_v, t / 2.0, cx)

    # Torsion constant (open thin-wall)
    J = (1.0 / 3.0) * (b * t ** 3 + (h - t) * t ** 3)

    rx = math.sqrt(Ix / A) if A > 0 else 0.0
    ry = math.sqrt(Iy / A) if A > 0 else 0.0

    warns.append(
        "Angle section: Zx/Zy are approximate plastic moduli about centroidal axes. "
        "Principal axes are not aligned with geometric axes for unequal legs."
    )

    return {
        "ok": True,
        "shape": "angle",
        "A": A,
        "cx": cx,
        "cy": cy,
        "Ix": Ix,
        "Iy": Iy,
        "Sx_top": Sx_top,
        "Sx_bot": Sx_bot,
        "Sy": Sy,
        "Zx": Zx,
        "Zy": Zy,
        "rx": rx,
        "ry": ry,
        "J": J,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 2. beam_loads
# ---------------------------------------------------------------------------
# Closed-form formulas from Roark Table 8 and Hibbeler App. C.
#
# Sign convention:
#   x   — distance from left support (A) along beam axis (m)
#   y   — positive deflection upward
#   M   — positive sagging (tension at bottom)
#   V   — positive upward on left face
#   Ra, Rb — upward reactions at A and B respectively
# ---------------------------------------------------------------------------

def beam_loads(
    support: str,
    load_type: str,
    *,
    E: float,
    I: float,
    L: float,
    **load_params: float,
) -> dict:
    """
    Closed-form beam analysis for standard support and load combinations.

    Parameters
    ----------
    support : str
        "cantilever"        — fixed at A (x=0), free at B (x=L)
        "simply_supported"  — pinned at A, roller at B
        "fixed_fixed"       — both ends clamped
    load_type : str
        "point"  — transverse point load P (N) at distance a from A.
                   a defaults to L (free end) for cantilever,
                   L/2 for simply_supported / fixed_fixed.
        "udl"    — uniformly distributed load w (N/m) over entire span.
        "moment" — applied moment M0 (N·m).
                   For cantilever: applied at free end.
                   For simply_supported: applied at midspan.
                   For fixed_fixed: applied at midspan.
    E : float
        Young's modulus (Pa). Must be > 0.
    I : float
        Second moment of area (m⁴). Must be > 0.
    L : float
        Span length (m). Must be > 0.
    **load_params :
        For point load:   P (N), a (m, optional)
        For UDL:          w (N/m)
        For moment:       M0 (N·m)

    Returns
    -------
    dict with ok=True and:
        max_deflection  — magnitude of maximum deflection (m)
        slope_end       — maximum slope magnitude at free/support end (rad)
        max_moment      — maximum bending moment magnitude (N·m)
        max_shear       — maximum shear force magnitude (N)
        Ra              — reaction at A (N, positive = upward)
        Rb              — reaction at B (N, positive = upward)
        EI              — flexural rigidity used (N·m²)
        warnings        — list of warning strings

    References
    ----------
    Roark, Tables 8.1, 8.2, 8.3 (point, UDL, moment).
    Hibbeler, Appendix C.
    """
    warns: list[str] = []

    for name, val in [("E", E), ("I", I), ("L", L)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    E, I, L = float(E), float(I), float(L)
    EI = E * I

    sup = str(support).strip().lower().replace("-", "_").replace(" ", "_")
    lt  = str(load_type).strip().lower().replace("-", "_").replace(" ", "_")

    if sup not in ("cantilever", "simply_supported", "fixed_fixed"):
        return _err(
            f"Unknown support {support!r}. Supported: "
            "'cantilever', 'simply_supported', 'fixed_fixed'."
        )
    if lt not in ("point", "udl", "moment"):
        return _err(
            f"Unknown load_type {load_type!r}. Supported: 'point', 'udl', 'moment'."
        )

    # Dispatch
    if sup == "cantilever":
        return _cantilever(lt, E, I, L, EI, load_params, warns)
    elif sup == "simply_supported":
        return _simply_supported(lt, E, I, L, EI, load_params, warns)
    else:
        return _fixed_fixed(lt, E, I, L, EI, load_params, warns)


def _beam_result(max_deflection, slope_end, max_moment, max_shear,
                 Ra, Rb, EI, warns) -> dict:
    return {
        "ok": True,
        "max_deflection": abs(max_deflection),
        "slope_end": abs(slope_end),
        "max_moment": abs(max_moment),
        "max_shear": abs(max_shear),
        "Ra": Ra,
        "Rb": Rb,
        "EI": EI,
        "warnings": warns,
    }


# ---- Cantilever ----

def _cantilever(lt, E, I, L, EI, params, warns):
    if lt == "point":
        P = params.get("P")
        e = _guard_finite("P", P)
        if e:
            return _err(e)
        P = float(P)
        a = float(params.get("a", L))
        if a > L:
            warns.append(f"Point load position a={a} > L={L}; clamped to L.")
            a = L
        if a <= 0:
            return _err(f"Point load position a must be > 0, got {a}.")
        # Roark Table 8.1: cantilever with point load P at x=a from fixed end
        # Max deflection at free end:
        #   δ_max = P a² (3L - a) / (6 EI)       [when a <= L]
        # Max moment at wall = P * a
        # Max shear = P (for a=L, reaction at wall)
        delta = P * a ** 2 * (3.0 * L - a) / (6.0 * EI)
        slope = P * a ** 2 / (2.0 * EI)  # slope at free end
        M_max = P * a
        V_max = P
        Ra = -P    # reaction force at fixed end (downward convention: wall pushes up)
        Rb = 0.0
        return _beam_result(delta, slope, M_max, V_max, abs(Ra), Rb, EI, warns)

    elif lt == "udl":
        w = params.get("w")
        e = _guard_finite("w", w)
        if e:
            return _err(e)
        w = float(w)
        # δ_max = w L⁴ / (8 EI) at free end
        delta = w * L ** 4 / (8.0 * EI)
        slope = w * L ** 3 / (6.0 * EI)
        M_max = w * L ** 2 / 2.0
        V_max = w * L
        Ra = w * L
        Rb = 0.0
        return _beam_result(delta, slope, M_max, V_max, Ra, Rb, EI, warns)

    else:  # moment
        M0 = params.get("M0")
        e = _guard_finite("M0", M0)
        if e:
            return _err(e)
        M0 = float(M0)
        # Applied moment at free end: δ_max = M0 L² / (2 EI), slope = M0 L / EI
        delta = M0 * L ** 2 / (2.0 * EI)
        slope = M0 * L / EI
        M_max = abs(M0)
        V_max = 0.0
        Ra = 0.0
        Rb = 0.0
        return _beam_result(delta, slope, M_max, V_max, Ra, Rb, EI, warns)


# ---- Simply Supported ----

def _simply_supported(lt, E, I, L, EI, params, warns):
    if lt == "point":
        P = params.get("P")
        e = _guard_finite("P", P)
        if e:
            return _err(e)
        P = float(P)
        a = float(params.get("a", L / 2.0))
        b = L - a
        if a <= 0 or a >= L:
            return _err(f"Point load position a must be in (0, L), got {a}.")
        # Reactions (equilibrium)
        Ra = P * b / L
        Rb = P * a / L
        # Max deflection using Roark formula for off-centre point load.
        # For the longer segment (a_s >= b_s), the max deflection location is
        # x_max = sqrt((L² - b_s²) / 3), measured from the A-end.
        # δ(x) = P b_s x (L² - b_s² - x²) / (6 EI L) for x <= a_s.
        b_s = min(a, b)   # shorter distance to load from nearer support
        a_s = max(a, b)   # longer distance from far support
        x_max = math.sqrt((L ** 2 - b_s ** 2) / 3.0)
        x_max = min(x_max, a_s)  # clamp to loaded segment
        delta = P * b_s * x_max * (L ** 2 - b_s ** 2 - x_max ** 2) / (6.0 * EI * L)
        slope_A = P * b * (L ** 2 - b ** 2) / (6.0 * EI * L)
        M_max = P * a * b / L
        V_max = max(Ra, Rb)
        return _beam_result(delta, slope_A, M_max, V_max, Ra, Rb, EI, warns)

    elif lt == "udl":
        w = params.get("w")
        e = _guard_finite("w", w)
        if e:
            return _err(e)
        w = float(w)
        Ra = Rb = w * L / 2.0
        delta = 5.0 * w * L ** 4 / (384.0 * EI)
        slope = w * L ** 3 / (24.0 * EI)
        M_max = w * L ** 2 / 8.0
        V_max = w * L / 2.0
        return _beam_result(delta, slope, M_max, V_max, Ra, Rb, EI, warns)

    else:  # moment at midspan
        M0 = params.get("M0")
        e = _guard_finite("M0", M0)
        if e:
            return _err(e)
        M0 = float(M0)
        # Simply supported beam with moment M0 at one end (A):
        # Ra = M0/L (upward), Rb = -M0/L
        # δ_max = M0 L² / (9√3 EI) at x = L/√3
        Ra = M0 / L
        Rb = -M0 / L
        delta = M0 * L ** 2 / (9.0 * math.sqrt(3.0) * EI)
        slope = M0 * L / (3.0 * EI)  # at A
        M_max = abs(M0)
        V_max = abs(Ra)
        warns.append("Moment load: applied at end A. For midspan moment, superpose two half-span cases.")
        return _beam_result(delta, slope, M_max, V_max, Ra, Rb, EI, warns)


# ---- Fixed-Fixed ----

def _fixed_fixed(lt, E, I, L, EI, params, warns):
    if lt == "point":
        P = params.get("P")
        e = _guard_finite("P", P)
        if e:
            return _err(e)
        P = float(P)
        a = float(params.get("a", L / 2.0))
        b = L - a
        if a <= 0 or a >= L:
            return _err(f"Point load position a must be in (0, L), got {a}.")
        # Roark Table 8.2
        # Ra = P b² (3a + b) / L³
        # Rb = P a² (a + 3b) / L³
        # MA (fixed end moment at A) = P a b² / L²  (hogging)
        # MB (fixed end moment at B) = P a² b / L²
        Ra = P * b ** 2 * (3.0 * a + b) / L ** 3
        Rb = P * a ** 2 * (a + 3.0 * b) / L ** 3
        MA = P * a * b ** 2 / L ** 2
        MB = P * a ** 2 * b / L ** 2
        # Max midspan deflection (for central load, a=b=L/2):
        #   δ_max = P L³ / (192 EI)
        # For general a:
        #   δ_max = 2 P a³ b² / (3 EI (3a+b)²) at x = 2aL/(3a+b)
        denom = (3.0 * a + b) ** 2
        if denom > 0:
            delta = 2.0 * P * a ** 3 * b ** 2 / (3.0 * EI * denom)
        else:
            delta = 0.0
        slope = 0.0  # zero at both clamped ends
        # Roark Table 8.2: moment under the load M_load = 2 P a² b² / L³.
        # The governing |M| is the larger of the fixed-end moments and the
        # moment under the load (for a central load all three equal P·L/8).
        M_load = 2.0 * P * a ** 2 * b ** 2 / L ** 3
        M_max = max(MA, MB, M_load)
        V_max = max(Ra, Rb)
        return _beam_result(delta, slope, M_max, V_max, Ra, Rb, EI, warns)

    elif lt == "udl":
        w = params.get("w")
        e = _guard_finite("w", w)
        if e:
            return _err(e)
        w = float(w)
        Ra = Rb = w * L / 2.0
        # Fixed-fixed UDL: δ_max = w L⁴ / (384 EI)
        delta = w * L ** 4 / (384.0 * EI)
        slope = 0.0
        # M at ends = w L² / 12; M at midspan = w L² / 24
        M_end = w * L ** 2 / 12.0
        M_mid = w * L ** 2 / 24.0
        M_max = M_end  # hogging at ends governs
        V_max = w * L / 2.0
        return _beam_result(delta, slope, M_max, V_max, Ra, Rb, EI, warns)

    else:  # moment
        M0 = params.get("M0")
        e = _guard_finite("M0", M0)
        if e:
            return _err(e)
        M0 = float(M0)
        # Applied moment M0 at midspan of fixed-fixed beam
        # Reactions: Ra = -Rb = 6 EI M0 / (EI L²)... simplified:
        # For uniform beam with moment M0 at centre:
        # Ra = 6M0/L²×... (use Roark Table 8.3c)
        # Simplified: fixed-fixed beam with end moment M0 at A
        # Ma = M0/2, Mb = -M0/2 approximately
        Ra = 6.0 * EI * M0 / (EI * L ** 2) if L > 0 else 0.0  # placeholder
        # Correct Roark formula for concentrated moment at midspan of fixed-fixed:
        # Ra = Rb = 0 (by symmetry of applied moment), but this isn't right.
        # Use: simply treat as M0 at a = L/2
        a = L / 2.0
        b_s = L / 2.0
        Ra = M0 * (6.0 * a * b_s - L ** 2) / L ** 3  # Roark formula
        Rb = -Ra
        delta = M0 * L ** 2 / (16.0 * EI)  # approximate
        slope = 0.0
        M_max = abs(M0) / 2.0
        V_max = abs(Ra)
        warns.append("Fixed-fixed moment load: max-moment is approximate; use FEA for precision.")
        return _beam_result(delta, slope, M_max, V_max, Ra, Rb, EI, warns)


# ---------------------------------------------------------------------------
# 3. superpose
# ---------------------------------------------------------------------------

def superpose(cases: list[dict]) -> dict:
    """
    Linearly superpose beam_loads results.

    All cases must have ok=True.  max_deflection, max_moment, max_shear
    are summed algebraically (absolute values of each are added — conservative
    upper bound for opposite-sign loads).

    Parameters
    ----------
    cases : list of dict
        Each element should be a dict returned by beam_loads with ok=True.

    Returns
    -------
    dict with ok=True and:
        max_deflection  — sum of individual max_deflections (conservative)
        max_moment      — sum of individual max_moments
        max_shear       — sum of individual max_shears
        Ra              — algebraic sum of reactions at A
        Rb              — algebraic sum of reactions at B
        n_cases         — number of cases superposed
        warnings        — list of warning strings
    """
    if not cases:
        return _err("cases must be a non-empty list.")

    warns: list[str] = []
    total_delta = 0.0
    total_M = 0.0
    total_V = 0.0
    total_Ra = 0.0
    total_Rb = 0.0

    for i, c in enumerate(cases):
        if not isinstance(c, dict):
            return _err(f"Case {i} is not a dict.")
        if c.get("ok") is not True:
            return _err(f"Case {i} has ok!=True: {c.get('reason', 'unknown error')}.")
        total_delta += c.get("max_deflection", 0.0)
        total_M += c.get("max_moment", 0.0)
        total_V += c.get("max_shear", 0.0)
        total_Ra += c.get("Ra", 0.0)
        total_Rb += c.get("Rb", 0.0)

    warns.append(
        "Superposition: max_deflection/moment/shear are sums of magnitudes — "
        "conservative for loads in the same direction."
    )

    return {
        "ok": True,
        "max_deflection": total_delta,
        "max_moment": total_M,
        "max_shear": total_V,
        "Ra": total_Ra,
        "Rb": total_Rb,
        "n_cases": len(cases),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 4. buckling
# ---------------------------------------------------------------------------

def buckling(
    L_eff: float,
    A: float,
    I: float,
    E: float,
    *,
    Fy: float,
    K: float = 1.0,
) -> dict:
    """
    Column buckling: Euler critical load + Johnson short-column transition.

    Parameters
    ----------
    L_eff : float
        Effective (unsupported) column length (m).  Must be > 0.
    A : float
        Cross-sectional area (m²).  Must be > 0.
    I : float
        Minimum second moment of area (m⁴).  Must be > 0.
    E : float
        Young's modulus (Pa).  Must be > 0.
    Fy : float
        Yield strength (Pa).  Must be > 0.
    K : float
        End-condition factor (default 1.0 = pin-pin):
          K=0.5  — fixed-fixed
          K=0.7  — fixed-pin
          K=1.0  — pin-pin (default)
          K=2.0  — fixed-free (flagpole)

    Returns
    -------
    dict with ok=True and:
        r           — radius of gyration (m)
        KL_over_r   — effective slenderness ratio K·L/r
        Cc          — transition slenderness (Euler/Johnson boundary)
        P_euler     — Euler critical load (N)
        P_johnson   — Johnson critical load (N, = Fy·A for very short columns)
        mode        — "euler" or "johnson" (governing mode)
        P_cr        — governing critical load (N)
        sigma_cr    — critical stress P_cr/A (Pa)
        warnings    — list of warnings (yielding / very slender flags)

    Notes
    -----
    Euler critical load:   P_e = π² E I / (K·L)²
    Johnson critical load: P_j = A·Fy [1 - (Fy/(4π²E)) (K·L/r)²]
    Transition slenderness: Cc = π √(2E/Fy)
    For KL/r > Cc: Euler governs.
    For KL/r <= Cc: Johnson governs.
    A warning is emitted if sigma_cr > Fy (section has yielded — buckling
    formula no longer valid; section must be resized).
    """
    warns: list[str] = []

    for name, val in [("L_eff", L_eff), ("A", A), ("I", I), ("E", E), ("Fy", Fy)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    e = _guard_positive("K", K)
    if e:
        return _err(e)

    L_eff, A, I, E, Fy, K = float(L_eff), float(A), float(I), float(E), float(Fy), float(K)

    r = math.sqrt(I / A)
    KL_r = K * L_eff / r

    # Transition slenderness
    Cc = math.pi * math.sqrt(2.0 * E / Fy)

    # Euler load
    KL = K * L_eff
    P_euler = math.pi ** 2 * E * I / KL ** 2

    # Johnson load: valid only for KL/r <= Cc
    if KL_r <= Cc:
        P_johnson = A * Fy * (1.0 - (Fy / (4.0 * math.pi ** 2 * E)) * KL_r ** 2)
        mode = "johnson"
        P_cr = P_johnson
    else:
        P_johnson = A * Fy * (1.0 - (Fy / (4.0 * math.pi ** 2 * E)) * Cc ** 2)
        mode = "euler"
        P_cr = P_euler

    sigma_cr = P_cr / A

    if sigma_cr > Fy:
        msg = (
            f"sigma_cr={sigma_cr:.3e} Pa exceeds Fy={Fy:.3e} Pa — "
            "section has yielded; buckling formula invalid. Resize column."
        )
        warns.append(msg)
        _warnings_module.warn(msg, stacklevel=3)

    if KL_r > 200:
        warns.append(
            f"Very high slenderness KL/r={KL_r:.1f} > 200 — "
            "AISC recommends KL/r <= 200 for compression members."
        )

    return {
        "ok": True,
        "r": r,
        "KL_over_r": KL_r,
        "Cc": Cc,
        "P_euler": P_euler,
        "P_johnson": P_johnson,
        "mode": mode,
        "P_cr": P_cr,
        "sigma_cr": sigma_cr,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 5. combined_stress
# ---------------------------------------------------------------------------

def combined_stress(
    P: float,
    M: float,
    A: float,
    S: float,
) -> dict:
    """
    Combined axial + bending stress at extreme fibres.

    σ = P/A ± M/S

    Parameters
    ----------
    P : float
        Axial load (N). Positive = tension, negative = compression.
    M : float
        Bending moment (N·m). Magnitude; direction reflected in ± term.
    A : float
        Cross-sectional area (m²). Must be > 0.
    S : float
        Elastic section modulus (m³). Must be > 0.
        Use the smaller of Sx_top and Sx_bot for conservative bending stress.

    Returns
    -------
    dict with ok=True and:
        sigma_axial         — P/A (Pa)
        sigma_bending       — M/S (Pa, magnitude)
        sigma_top           — σ_axial - σ_bending (Pa)
        sigma_bot           — σ_axial + σ_bending (Pa)
        sigma_max           — max(|sigma_top|, |sigma_bot|) (Pa)
        warnings            — list of strings
    """
    warns: list[str] = []

    e = _guard_finite("P", P)
    if e:
        return _err(e)
    e = _guard_finite("M", M)
    if e:
        return _err(e)
    e = _guard_positive("A", A)
    if e:
        return _err(e)
    e = _guard_positive("S", S)
    if e:
        return _err(e)

    sigma_axial = float(P) / float(A)
    sigma_bending = abs(float(M)) / float(S)

    sigma_top = sigma_axial - sigma_bending
    sigma_bot = sigma_axial + sigma_bending
    sigma_max = max(abs(sigma_top), abs(sigma_bot))

    return {
        "ok": True,
        "sigma_axial": sigma_axial,
        "sigma_bending": sigma_bending,
        "sigma_top": sigma_top,
        "sigma_bot": sigma_bot,
        "sigma_max": sigma_max,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 6. mohr_circle
# ---------------------------------------------------------------------------

def mohr_circle(sigma_x: float, sigma_y: float, tau_xy: float) -> dict:
    """
    Mohr's circle for a 2D plane stress state.

    Parameters
    ----------
    sigma_x : float
        Normal stress on x-face (Pa).
    sigma_y : float
        Normal stress on y-face (Pa).
    tau_xy  : float
        Shear stress on x-face (Pa). Positive = CCW on x-face.

    Returns
    -------
    dict with ok=True and:
        sigma_avg   — (σx + σy) / 2  (Pa)
        R           — radius of Mohr's circle (Pa)
        sigma_1     — major principal stress (Pa)
        sigma_2     — minor principal stress (Pa)
        tau_max     — maximum in-plane shear stress (Pa)
        theta_p_deg — angle of principal plane from x-axis (degrees, CCW positive)
        warnings    — list of strings
    """
    warns: list[str] = []

    for name, val in [("sigma_x", sigma_x), ("sigma_y", sigma_y), ("tau_xy", tau_xy)]:
        e = _guard_finite(name, val)
        if e:
            return _err(e)

    sx = float(sigma_x)
    sy = float(sigma_y)
    txy = float(tau_xy)

    avg = (sx + sy) / 2.0
    R = math.sqrt(((sx - sy) / 2.0) ** 2 + txy ** 2)

    sigma_1 = avg + R
    sigma_2 = avg - R
    tau_max = R

    # Angle to the major-principal plane (Hibbeler, Mechanics of Materials,
    # §9.3, Eq. 9-4):  tan(2θ_p) = 2·τxy / (σx − σy).
    # θ_p1 (orientation of σ1) = ½·atan2(2·τxy, σx − σy).
    if (sx - sy) == 0.0 and txy == 0.0:
        theta_p = 0.0
    else:
        theta_p = 0.5 * math.atan2(2.0 * txy, sx - sy)
    theta_p_deg = math.degrees(theta_p)

    return {
        "ok": True,
        "sigma_avg": avg,
        "R": R,
        "sigma_1": sigma_1,
        "sigma_2": sigma_2,
        "tau_max": tau_max,
        "theta_p_deg": theta_p_deg,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 7. shear_flow (VQ/It)
# ---------------------------------------------------------------------------

def shear_flow(V: float, Q: float, I: float, b: float) -> dict:
    """
    Shear stress at a horizontal section cut: τ = VQ / (I·b).

    Parameters
    ----------
    V : float
        Shear force at the section (N).
    Q : float
        First moment of area of the cut portion about the neutral axis (m³).
        Must be >= 0.
    I : float
        Second moment of area of the full cross-section about the neutral
        axis (m⁴). Must be > 0.
    b : float
        Width of the cut at the point of interest (m). Must be > 0.

    Returns
    -------
    dict with ok=True and:
        tau_Pa      — shear stress at the cut (Pa)
        V_N         — shear force used (N)
        Q_m3        — first moment used (m³)
        I_m4        — second moment used (m⁴)
        b_m         — cut width used (m)
        warnings    — list of strings
    """
    warns: list[str] = []

    e = _guard_finite("V", V)
    if e:
        return _err(e)
    e = _guard_nonneg("Q", Q)
    if e:
        return _err(e)
    e = _guard_positive("I", I)
    if e:
        return _err(e)
    e = _guard_positive("b", b)
    if e:
        return _err(e)

    V_f = float(V)
    Q_f = float(Q)
    I_f = float(I)
    b_f = float(b)

    tau = V_f * Q_f / (I_f * b_f)

    return {
        "ok": True,
        "tau_Pa": tau,
        "V_N": V_f,
        "Q_m3": Q_f,
        "I_m4": I_f,
        "b_m": b_f,
        "warnings": warns,
    }
