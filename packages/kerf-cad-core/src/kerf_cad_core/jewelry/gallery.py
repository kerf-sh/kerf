"""
kerf_cad_core.jewelry.gallery
==============================

Parametric **basket / gallery / under-gallery** builder — the openwork
sub-structure beneath a ring head.  This is a core RhinoGold / MatrixGold
component absent in the base Kerf jewelry module.

Overview
--------
In fine jewellery, a *gallery* is the decorative / structural frame that
sits between a stone-setting head and the ring shank.  It gives the ring
its visual character and provides the metal rails that hold the head safely
while allowing light into the stone from below.

This module provides pure-Python geometry helpers (no OCCT required) that
return node-spec dicts consumed by the occtWorker ``opJewelryGallery``
operator.  LLM tools are registered via ``@register``.

Sub-components
--------------
basket_geometry()
    N-prong radial basket: prong wires + horizontal rail bands + optional
    diagonal strut braces.  Scallop / airline cutout curves are computed as
    a list of arc segments for the worker to sweep.

under_bezel_gallery_geometry()
    Flat-bottomed sub-collet gallery that sits directly beneath a bezel
    setting; supports a decorative punched / filigree border.

cathedral_shoulder_geometry()
    Cathedral shoulder arches that sweep from the prong base down to the
    shank; up to two arch ribs per shoulder.

trellis_shoulder_geometry()
    Interlocking cross-diagonal trellis connecting adjacent prongs to the
    shank rail.

peg_head_adapter_geometry()
    A cylindrical adapter (peg / post head) sizing the basket to a standard
    peg-head shank interface.

Estimation helpers
------------------
basket_metal_volume_mm3()
    Metal volume estimate for a basket + gallery assembly (sum of wire-segment
    cylinders / tori).

basket_surface_area_mm2()
    External surface area of the basket wires (useful for plating cost).

metal_weight_grams()
    Mass estimate given volume (mm³) and density (g/cm³).

min_wire_diameter_check()
    Structural check: returns a warning string if any wire in the basket is
    thinner than the recommended minimum for the stone carat load.

LLM tools registered
--------------------
    jewelry_build_basket_gallery     — write; full basket + gallery spec
    jewelry_build_under_bezel_gallery — write; under-bezel gallery ring
    jewelry_build_cathedral_shoulders — write; cathedral shoulder arches
    jewelry_build_trellis_shoulders   — write; trellis shoulder diagonals
    jewelry_estimate_gallery_metal    — read;  volume / weight / area estimate

Units: millimetres throughout.  Angles in degrees.
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import (
    append_feature_node,
    next_node_id,
    read_feature_content,
)

_PI = math.pi

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum prong/wire diameter (mm) per stone load bracket (carats).
# Source: industry bench practice (Gees / Wim Mees / RhinoGold docs).
_MIN_WIRE_TABLE = [
    (0.00,  0.25, 0.8),   # < 0.25 ct   → 0.8 mm minimum
    (0.25,  0.75, 0.9),   # 0.25–0.75 ct → 0.9 mm
    (0.75,  1.50, 1.0),   # 0.75–1.50 ct → 1.0 mm
    (1.50,  3.00, 1.1),   # 1.50–3.00 ct → 1.1 mm
    (3.00, 10.00, 1.2),   # > 3 ct        → 1.2 mm
]

# Supported scallop / airline cutout styles
_VALID_CUTOUT_STYLES = frozenset(["none", "scallop", "airline", "oval", "marquise"])

# Supported gallery border styles (under-bezel)
_VALID_BORDER_STYLES = frozenset(["plain", "scalloped", "milgrain", "pierced", "filigree"])

# Supported shoulder styles
_VALID_SHOULDER_STYLES = frozenset(["cathedral", "trellis", "plain", "split"])


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _pos(name: str, val) -> None:
    """Raise ValueError if *val* is not a positive number."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number; got {val!r}")
    if v <= 0:
        raise ValueError(f"{name} must be > 0; got {v}")


def _non_neg(name: str, val) -> None:
    try:
        v = float(val)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number; got {val!r}")
    if v < 0:
        raise ValueError(f"{name} must be >= 0; got {v}")


def _pos_int(name: str, val, minimum: int = 1) -> int:
    try:
        v = int(val)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer; got {val!r}")
    if v < minimum:
        raise ValueError(f"{name} must be >= {minimum}; got {v}")
    return v


# ---------------------------------------------------------------------------
# Core geometry helpers — pure Python, no OCC
# ---------------------------------------------------------------------------

def basket_geometry(
    prong_count: int,
    stone_diameter_mm: float,
    wire_diameter_mm: float,
    basket_height_mm: float,
    *,
    rail_count: int = 1,
    taper_ratio: float = 0.0,
    splay_angle_deg: float = 5.0,
    cutout_style: str = "scallop",
    scallop_count: Optional[int] = None,
    diagonal_struts: bool = False,
    strut_count: int = 0,
) -> dict:
    """Compute a full N-prong basket / gallery geometry spec.

    Parameters
    ----------
    prong_count        : number of prongs (3–8 supported; 4 and 6 most common)
    stone_diameter_mm  : girdle diameter of the centre stone (mm)
    wire_diameter_mm   : round-wire prong / rail diameter (mm)
    basket_height_mm   : overall height from basket base to stone seat plane
    rail_count         : number of horizontal gallery rails (1–4)
    taper_ratio        : how much the basket tapers toward the base (0 = no
                         taper; 1 = base radius = 50% of head radius)
    splay_angle_deg    : outward splay of each prong from vertical (degrees)
    cutout_style       : one of "none", "scallop", "airline", "oval", "marquise"
    scallop_count      : number of scallop arcs per inter-prong bay; if None,
                         defaults to (prong_count // 2)
    diagonal_struts    : if True, add cross-brace struts between adjacent prongs
    strut_count        : number of diagonal struts per bay (0 = auto = 1)

    Returns
    -------
    dict with keys:
        op                 — "jewelry_gallery_basket"
        prong_count        — int
        stone_diameter_mm  — float, passed through
        wire_diameter_mm   — float
        basket_height_mm   — float
        head_outer_radius_mm — outer radius at head (stone_diameter/2 + wire)
        base_outer_radius_mm — outer radius at base (after taper)
        rail_count         — int
        rail_positions_mm  — list[float] — height of each rail above base
        total_rail_length_mm — float — sum of all rail circumferences
        prong_positions_deg — list[float] — angular positions of prong centres
        prong_length_mm     — float — total prong wire length per prong
        strut_count_per_bay — int
        cutout_style        — str
        scallop_count_per_bay — int
        diagonal_struts     — bool
        splay_angle_deg     — float
    """
    prong_count = _pos_int("prong_count", prong_count, minimum=3)
    if prong_count > 12:
        raise ValueError(f"prong_count must be <= 12; got {prong_count}")
    _pos("stone_diameter_mm", stone_diameter_mm)
    _pos("wire_diameter_mm", wire_diameter_mm)
    _pos("basket_height_mm", basket_height_mm)
    rail_count = _pos_int("rail_count", rail_count)
    if rail_count > 6:
        raise ValueError(f"rail_count must be <= 6; got {rail_count}")
    _non_neg("taper_ratio", taper_ratio)
    if taper_ratio >= 1.0:
        raise ValueError(f"taper_ratio must be < 1.0; got {taper_ratio}")
    cutout_style = str(cutout_style).strip().lower()
    if cutout_style not in _VALID_CUTOUT_STYLES:
        raise ValueError(
            f"cutout_style {cutout_style!r} not valid; "
            f"choose from {sorted(_VALID_CUTOUT_STYLES)}"
        )

    # Head outer radius at stone-seat plane
    head_outer_r = stone_diameter_mm / 2.0 + wire_diameter_mm

    # Base outer radius after taper
    base_outer_r = head_outer_r * (1.0 - taper_ratio * 0.5)

    # Prong angular positions (evenly spaced, first at 0 degrees)
    prong_positions = [round(i * 360.0 / prong_count, 4) for i in range(prong_count)]

    # Rail heights: evenly spaced inside basket_height (leave room at top)
    # Top rail = 85% of basket_height, bottom rail = 15%
    if rail_count == 1:
        rail_positions = [round(basket_height_mm * 0.5, 4)]
    else:
        step = basket_height_mm * 0.7 / max(rail_count - 1, 1)
        bottom = basket_height_mm * 0.15
        rail_positions = [round(bottom + i * step, 4) for i in range(rail_count)]

    # Rail circumference at mid-height (interpolate between head and base)
    mid_r = (head_outer_r + base_outer_r) / 2.0
    total_rail_len = sum(2 * _PI * mid_r for _ in rail_positions)

    # Prong wire length: straight wire from base to slightly above seat plane
    # The splay increases effective wire length
    splay_rad = math.radians(splay_angle_deg)
    prong_length = basket_height_mm / math.cos(splay_rad) if splay_rad < _PI / 2.0 else basket_height_mm
    prong_length = round(prong_length, 4)

    # Scallop / cutout count per bay
    n_bays = prong_count
    if scallop_count is None:
        sc = max(1, prong_count // 2)
    else:
        sc = _pos_int("scallop_count", scallop_count)
    sc_per_bay = sc

    # Struts
    actual_struts = strut_count if diagonal_struts else 0
    if diagonal_struts and actual_struts == 0:
        actual_struts = 1

    return {
        "op": "jewelry_gallery_basket",
        "prong_count": prong_count,
        "stone_diameter_mm": round(stone_diameter_mm, 4),
        "wire_diameter_mm": round(wire_diameter_mm, 4),
        "basket_height_mm": round(basket_height_mm, 4),
        "head_outer_radius_mm": round(head_outer_r, 4),
        "base_outer_radius_mm": round(base_outer_r, 4),
        "rail_count": rail_count,
        "rail_positions_mm": rail_positions,
        "total_rail_length_mm": round(total_rail_len, 4),
        "prong_positions_deg": prong_positions,
        "prong_length_mm": prong_length,
        "strut_count_per_bay": actual_struts,
        "cutout_style": cutout_style,
        "scallop_count_per_bay": sc_per_bay,
        "diagonal_struts": diagonal_struts,
        "splay_angle_deg": round(splay_angle_deg, 4),
        "taper_ratio": round(taper_ratio, 4),
    }


def under_bezel_gallery_geometry(
    stone_diameter_mm: float,
    wall_thickness_mm: float,
    gallery_height_mm: float,
    *,
    border_style: str = "scalloped",
    scallop_count: int = 12,
    piercing_diameter_mm: float = 0.0,
    piercing_count: int = 0,
) -> dict:
    """Compute an under-bezel gallery ring geometry spec.

    The under-bezel gallery is a flat-bottomed collar that sits directly below
    a bezel collet.  It widens slightly below the stone for structural support
    and carries a decorative border.

    Parameters
    ----------
    stone_diameter_mm  : stone girdle diameter (mm)
    wall_thickness_mm  : gallery wall thickness (mm)
    gallery_height_mm  : axial height of the gallery collar (mm)
    border_style       : decorative treatment; one of _VALID_BORDER_STYLES
    scallop_count      : number of scallop arcs on "scalloped" border
    piercing_diameter_mm : diameter of round piercings for "pierced" style (mm)
    piercing_count     : number of piercings around circumference

    Returns
    -------
    dict with keys:
        op                    — "jewelry_gallery_under_bezel"
        stone_diameter_mm     — float
        inner_radius_mm       — float = stone_diameter/2
        outer_radius_mm       — float = inner_radius + wall_thickness
        gallery_height_mm     — float
        border_style          — str
        scallop_count         — int
        piercing_diameter_mm  — float
        piercing_count        — int
        circumference_mm      — float of the outer wall
    """
    _pos("stone_diameter_mm", stone_diameter_mm)
    _pos("wall_thickness_mm", wall_thickness_mm)
    _pos("gallery_height_mm", gallery_height_mm)
    border_style = str(border_style).strip().lower()
    if border_style not in _VALID_BORDER_STYLES:
        raise ValueError(
            f"border_style {border_style!r} not valid; "
            f"choose from {sorted(_VALID_BORDER_STYLES)}"
        )
    scallop_count = _pos_int("scallop_count", scallop_count)
    _non_neg("piercing_diameter_mm", piercing_diameter_mm)
    _non_neg("piercing_count", piercing_count)

    inner_r = stone_diameter_mm / 2.0
    outer_r = inner_r + wall_thickness_mm
    circ = 2 * _PI * outer_r

    return {
        "op": "jewelry_gallery_under_bezel",
        "stone_diameter_mm": round(stone_diameter_mm, 4),
        "inner_radius_mm": round(inner_r, 4),
        "outer_radius_mm": round(outer_r, 4),
        "gallery_height_mm": round(gallery_height_mm, 4),
        "border_style": border_style,
        "scallop_count": scallop_count,
        "piercing_diameter_mm": round(piercing_diameter_mm, 4),
        "piercing_count": int(piercing_count),
        "circumference_mm": round(circ, 4),
    }


def cathedral_shoulder_geometry(
    prong_count: int,
    stone_diameter_mm: float,
    wire_diameter_mm: float,
    basket_height_mm: float,
    shank_width_mm: float,
    *,
    arch_rib_count: int = 1,
    arch_rise_mm: Optional[float] = None,
) -> dict:
    """Compute cathedral shoulder arch geometry.

    Cathedral shoulders sweep an arch rib from the prong base down to the
    shank.  The arch spans from the basket base outward to where the shoulder
    meets the shank top.

    Parameters
    ----------
    prong_count        : prong count of the head (determines which prongs carry arches)
    stone_diameter_mm  : stone diameter (mm)
    wire_diameter_mm   : arch-rib wire diameter (mm)
    basket_height_mm   : height of the basket above shank (mm)
    shank_width_mm     : shank band width at the shoulder junction (mm)
    arch_rib_count     : number of arch ribs per shoulder (1–2)
    arch_rise_mm       : height of arch above shank; defaults to basket_height * 0.6

    Returns
    -------
    dict with keys:
        op                   — "jewelry_gallery_cathedral"
        prong_count          — int
        stone_diameter_mm    — float
        wire_diameter_mm     — float
        arch_rib_count       — int  (per shoulder)
        arch_span_mm         — float  horizontal span of each arch at shank level
        arch_rise_mm         — float
        arch_length_mm       — float  approximate arc length of each rib
        shoulder_pair_count  — int    always 2 (left/right)
    """
    prong_count = _pos_int("prong_count", prong_count, minimum=3)
    _pos("stone_diameter_mm", stone_diameter_mm)
    _pos("wire_diameter_mm", wire_diameter_mm)
    _pos("basket_height_mm", basket_height_mm)
    _pos("shank_width_mm", shank_width_mm)
    arch_rib_count = _pos_int("arch_rib_count", arch_rib_count)
    if arch_rib_count > 2:
        raise ValueError(f"arch_rib_count must be 1 or 2; got {arch_rib_count}")

    if arch_rise_mm is None:
        arch_rise_mm = basket_height_mm * 0.6
    else:
        _pos("arch_rise_mm", arch_rise_mm)

    # Approximate arch span: horizontal distance from head base to shank edge
    head_base_r = stone_diameter_mm / 2.0 + wire_diameter_mm
    arch_span = max(head_base_r, shank_width_mm / 2.0)

    # Arc length of a circular arch: approximate via semi-ellipse perimeter
    # half-ellipse with a=arch_span, b=arch_rise
    a = arch_span
    b = arch_rise_mm
    # Ramanujan approximation for semi-ellipse perimeter
    arch_length = _PI * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b))) / 2.0

    return {
        "op": "jewelry_gallery_cathedral",
        "prong_count": prong_count,
        "stone_diameter_mm": round(stone_diameter_mm, 4),
        "wire_diameter_mm": round(wire_diameter_mm, 4),
        "arch_rib_count": arch_rib_count,
        "arch_span_mm": round(arch_span, 4),
        "arch_rise_mm": round(arch_rise_mm, 4),
        "arch_length_mm": round(arch_length, 4),
        "shoulder_pair_count": 2,
        "shank_width_mm": round(shank_width_mm, 4),
        "basket_height_mm": round(basket_height_mm, 4),
    }


def trellis_shoulder_geometry(
    prong_count: int,
    stone_diameter_mm: float,
    wire_diameter_mm: float,
    basket_height_mm: float,
    *,
    cross_count: int = 2,
) -> dict:
    """Compute trellis shoulder geometry.

    A trellis connects adjacent prongs with cross-diagonal wires, creating an
    interwoven X-pattern.

    Parameters
    ----------
    prong_count        : prong count of the head
    stone_diameter_mm  : stone diameter (mm)
    wire_diameter_mm   : trellis wire diameter (mm)
    basket_height_mm   : height of basket (mm)
    cross_count        : number of crossing diagonals per bay pair (1 or 2)

    Returns
    -------
    dict with keys:
        op                   — "jewelry_gallery_trellis"
        prong_count          — int
        stone_diameter_mm    — float
        wire_diameter_mm     — float
        cross_count          — int
        bay_count            — int  (= prong_count for full trellis)
        diagonal_length_mm   — float  chord length between adjacent prong roots
        total_trellis_wire_mm — float  total trellis wire length
    """
    prong_count = _pos_int("prong_count", prong_count, minimum=3)
    _pos("stone_diameter_mm", stone_diameter_mm)
    _pos("wire_diameter_mm", wire_diameter_mm)
    _pos("basket_height_mm", basket_height_mm)
    cross_count = _pos_int("cross_count", cross_count)
    if cross_count > 4:
        raise ValueError(f"cross_count must be <= 4; got {cross_count}")

    # Chord between adjacent prong roots on the head circle
    head_r = stone_diameter_mm / 2.0 + wire_diameter_mm
    angle_between = 2 * _PI / prong_count
    chord = 2 * head_r * math.sin(angle_between / 2.0)

    # Diagonal length: hypotenuse of chord × basket_height (rough slant)
    diag_len = math.sqrt(chord ** 2 + basket_height_mm ** 2)

    # Total trellis wire: each bay has cross_count diagonals; N bays
    total_trellis = diag_len * cross_count * prong_count

    return {
        "op": "jewelry_gallery_trellis",
        "prong_count": prong_count,
        "stone_diameter_mm": round(stone_diameter_mm, 4),
        "wire_diameter_mm": round(wire_diameter_mm, 4),
        "cross_count": cross_count,
        "bay_count": prong_count,
        "diagonal_length_mm": round(diag_len, 4),
        "total_trellis_wire_mm": round(total_trellis, 4),
        "basket_height_mm": round(basket_height_mm, 4),
    }


def peg_head_adapter_geometry(
    stone_diameter_mm: float,
    wire_diameter_mm: float,
    adapter_height_mm: float,
    shank_bore_diameter_mm: float,
) -> dict:
    """Compute peg/post head adapter geometry.

    A cylindrical peg that aligns the basket to the shank bore.

    Parameters
    ----------
    stone_diameter_mm       : stone girdle diameter (mm)
    wire_diameter_mm        : wall wire/thickness (mm)
    adapter_height_mm       : axial length of the peg adapter (mm)
    shank_bore_diameter_mm  : inner bore of the shank's peg socket (mm)

    Returns
    -------
    dict with keys:
        op                      — "jewelry_gallery_peg_adapter"
        peg_outer_diameter_mm   — float (= shank_bore_diameter)
        peg_inner_diameter_mm   — float (hollow for light ingress)
        adapter_height_mm       — float
    """
    _pos("stone_diameter_mm", stone_diameter_mm)
    _pos("wire_diameter_mm", wire_diameter_mm)
    _pos("adapter_height_mm", adapter_height_mm)
    _pos("shank_bore_diameter_mm", shank_bore_diameter_mm)

    peg_outer = shank_bore_diameter_mm
    # Inner bore = shank bore minus 2×wall, minimum 0.5 mm
    peg_inner = max(0.5, peg_outer - 2 * wire_diameter_mm)

    return {
        "op": "jewelry_gallery_peg_adapter",
        "stone_diameter_mm": round(stone_diameter_mm, 4),
        "peg_outer_diameter_mm": round(peg_outer, 4),
        "peg_inner_diameter_mm": round(peg_inner, 4),
        "adapter_height_mm": round(adapter_height_mm, 4),
        "wall_thickness_mm": round(wire_diameter_mm, 4),
    }


# ---------------------------------------------------------------------------
# Estimation helpers
# ---------------------------------------------------------------------------

def _cylinder_volume_mm3(diameter_mm: float, length_mm: float) -> float:
    """Volume of a cylinder (mm³)."""
    r = diameter_mm / 2.0
    return _PI * r * r * length_mm


def _cylinder_surface_mm2(diameter_mm: float, length_mm: float) -> float:
    """Lateral surface area of a cylinder (mm²), excluding caps."""
    return _PI * diameter_mm * length_mm


def basket_metal_volume_mm3(
    basket: dict,
) -> float:
    """Estimate total metal volume (mm³) for a basket spec.

    Uses the basket_geometry() output.  Computes volumes of:
      - All prong wires (cylinders with prong_length × wire_diameter)
      - All rails (tori approximated as cylinders of rail circumference)

    Parameters
    ----------
    basket : dict from basket_geometry()

    Returns
    -------
    float — total metal volume in mm³
    """
    wd = basket["wire_diameter_mm"]
    prong_count = basket["prong_count"]
    prong_len = basket["prong_length_mm"]
    rail_count = basket["rail_count"]
    rail_r = (basket["head_outer_radius_mm"] + basket["base_outer_radius_mm"]) / 2.0
    rail_circ = 2 * _PI * rail_r

    prong_vol = prong_count * _cylinder_volume_mm3(wd, prong_len)
    rail_vol = rail_count * _cylinder_volume_mm3(wd, rail_circ)

    # Diagonal struts (if any)
    strut_count_total = basket["strut_count_per_bay"] * prong_count
    # Rough diagonal length per strut: half basket height / cos(30)
    strut_len = basket["basket_height_mm"] / math.cos(math.radians(30))
    strut_vol = strut_count_total * _cylinder_volume_mm3(wd, strut_len)

    return prong_vol + rail_vol + strut_vol


def basket_surface_area_mm2(
    basket: dict,
) -> float:
    """Estimate total external surface area (mm²) of basket wires."""
    wd = basket["wire_diameter_mm"]
    prong_count = basket["prong_count"]
    prong_len = basket["prong_length_mm"]
    rail_count = basket["rail_count"]
    rail_r = (basket["head_outer_radius_mm"] + basket["base_outer_radius_mm"]) / 2.0
    rail_circ = 2 * _PI * rail_r

    prong_sa = prong_count * _cylinder_surface_mm2(wd, prong_len)
    rail_sa = rail_count * _cylinder_surface_mm2(wd, rail_circ)
    return prong_sa + rail_sa


def metal_weight_grams(volume_mm3: float, density_g_cm3: float) -> float:
    """Convert volume (mm³) to mass (grams).

    Parameters
    ----------
    volume_mm3      : volume in cubic millimetres
    density_g_cm3   : alloy density in g/cm³ (1 cm³ = 1000 mm³)

    Returns
    -------
    float — mass in grams
    """
    if volume_mm3 < 0:
        raise ValueError(f"volume_mm3 must be >= 0; got {volume_mm3}")
    if density_g_cm3 <= 0:
        raise ValueError(f"density_g_cm3 must be > 0; got {density_g_cm3}")
    return (volume_mm3 / 1000.0) * density_g_cm3


def min_wire_diameter_check(
    wire_diameter_mm: float,
    stone_carat: float,
) -> Optional[str]:
    """Check whether wire_diameter_mm meets the structural minimum for stone_carat.

    Parameters
    ----------
    wire_diameter_mm : actual wire diameter used
    stone_carat      : stone weight in carats

    Returns
    -------
    None   — wire is adequate
    str    — warning message if wire is below the recommended minimum
    """
    if wire_diameter_mm <= 0:
        raise ValueError(f"wire_diameter_mm must be > 0; got {wire_diameter_mm}")
    if stone_carat < 0:
        raise ValueError(f"stone_carat must be >= 0; got {stone_carat}")

    recommended = 0.8  # default fallback
    for lo, hi, min_d in _MIN_WIRE_TABLE:
        if lo <= stone_carat < hi:
            recommended = min_d
            break
    else:
        # Above highest threshold
        recommended = _MIN_WIRE_TABLE[-1][2]

    if wire_diameter_mm < recommended:
        return (
            f"Wire diameter {wire_diameter_mm:.2f} mm is below the recommended "
            f"minimum of {recommended:.2f} mm for a {stone_carat:.2f} ct stone. "
            f"Consider increasing wire_diameter_mm to at least {recommended:.2f} mm."
        )
    return None


# ---------------------------------------------------------------------------
# LLM tool: jewelry_build_basket_gallery  (write)
# ---------------------------------------------------------------------------

jewelry_build_basket_gallery_spec = ToolSpec(
    name="jewelry_build_basket_gallery",
    description=(
        "Append a ``jewelry_gallery_basket`` node to a ``.feature`` file.\n\n"
        "Generates a parametric N-prong basket/gallery sub-structure: prong wires, "
        "horizontal rail bands, optional scallop/airline openwork cutouts, and "
        "diagonal strut braces.  This is the foundational open-work sub-structure "
        "beneath a ring head — equivalent to RhinoGold's Gallery tool.\n\n"
        "Required: ``file_id``, ``prong_count``, ``stone_diameter_mm``, "
        "``wire_diameter_mm``, ``basket_height_mm``.\n\n"
        "The node is consumed by the occtWorker ``opJewelryGallery`` operator."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "prong_count": {
                "type": "integer",
                "description": "Number of prongs (3–12; typical 4 or 6).",
            },
            "stone_diameter_mm": {
                "type": "number",
                "description": "Stone girdle diameter in mm (e.g. 6.5 for 1 ct round brilliant).",
            },
            "wire_diameter_mm": {
                "type": "number",
                "description": "Round-wire prong/rail diameter in mm. Typical range 0.8–1.5 mm.",
            },
            "basket_height_mm": {
                "type": "number",
                "description": "Overall basket height from base to stone-seat plane (mm).",
            },
            "rail_count": {
                "type": "integer",
                "description": "Number of horizontal gallery rails (1–6, default 1).",
            },
            "taper_ratio": {
                "type": "number",
                "description": (
                    "How much the basket tapers toward the base (0 = no taper, "
                    "0.5 = base radius is 75% of head radius). Default 0."
                ),
            },
            "splay_angle_deg": {
                "type": "number",
                "description": "Outward prong splay from vertical, degrees (default 5).",
            },
            "cutout_style": {
                "type": "string",
                "enum": sorted(_VALID_CUTOUT_STYLES),
                "description": (
                    "Openwork cutout style between prongs. "
                    "'none': solid walls. 'scallop': arched cutouts. "
                    "'airline': teardrop openings. 'oval'/'marquise': shaped cutouts."
                ),
            },
            "scallop_count": {
                "type": "integer",
                "description": (
                    "Number of scallop arcs per inter-prong bay. "
                    "Default = prong_count // 2."
                ),
            },
            "diagonal_struts": {
                "type": "boolean",
                "description": "Add cross-brace diagonal struts between adjacent prongs (default false).",
            },
            "strut_count": {
                "type": "integer",
                "description": "Number of diagonal struts per bay when diagonal_struts=true (default 1).",
            },
            "stone_carat": {
                "type": "number",
                "description": (
                    "Optional stone weight in carats — used to emit a structural "
                    "warning if wire_diameter_mm is too thin for the stone load."
                ),
            },
        },
        "required": [
            "file_id",
            "prong_count",
            "stone_diameter_mm",
            "wire_diameter_mm",
            "basket_height_mm",
        ],
    },
)


@register(jewelry_build_basket_gallery_spec, write=True)
async def run_jewelry_build_basket_gallery(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "")
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        file_id = uuid.UUID(str(file_id_str))
    except ValueError:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    # Validate required numeric fields
    for field in ("prong_count", "stone_diameter_mm", "wire_diameter_mm", "basket_height_mm"):
        if a.get(field) is None:
            return err_payload(f"{field} is required", "BAD_ARGS")

    try:
        geom = basket_geometry(
            prong_count=int(a["prong_count"]),
            stone_diameter_mm=float(a["stone_diameter_mm"]),
            wire_diameter_mm=float(a["wire_diameter_mm"]),
            basket_height_mm=float(a["basket_height_mm"]),
            rail_count=int(a.get("rail_count", 1)),
            taper_ratio=float(a.get("taper_ratio", 0.0)),
            splay_angle_deg=float(a.get("splay_angle_deg", 5.0)),
            cutout_style=str(a.get("cutout_style", "scallop")),
            scallop_count=int(a["scallop_count"]) if a.get("scallop_count") is not None else None,
            diagonal_struts=bool(a.get("diagonal_struts", False)),
            strut_count=int(a.get("strut_count", 0)),
        )
    except (ValueError, TypeError) as e:
        return err_payload(str(e), "BAD_ARGS")

    # Optional structural warning
    warnings = []
    stone_carat = a.get("stone_carat")
    if stone_carat is not None:
        try:
            warn = min_wire_diameter_check(
                float(a["wire_diameter_mm"]),
                float(stone_carat),
            )
            if warn:
                warnings.append(warn)
        except (ValueError, TypeError):
            pass

    content, err = read_feature_content(ctx, file_id)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = next_node_id(content, "gallery_basket")
    node = {"id": node_id, **geom}

    _, nid, err2 = append_feature_node(ctx, file_id, node)
    if err2:
        return err_payload(err2, "ERROR")

    result = {"node_id": nid, "basket": geom}
    if warnings:
        result["warnings"] = warnings
    return ok_payload(result)


# ---------------------------------------------------------------------------
# LLM tool: jewelry_build_under_bezel_gallery  (write)
# ---------------------------------------------------------------------------

jewelry_build_under_bezel_gallery_spec = ToolSpec(
    name="jewelry_build_under_bezel_gallery",
    description=(
        "Append a ``jewelry_gallery_under_bezel`` node to a ``.feature`` file.\n\n"
        "Generates an under-bezel gallery ring — the flat-bottomed sub-collet "
        "collar beneath a bezel setting with decorative border treatment.\n\n"
        "Required: ``file_id``, ``stone_diameter_mm``, ``wall_thickness_mm``, "
        "``gallery_height_mm``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter_mm": {
                "type": "number",
                "description": "Stone girdle diameter in mm.",
            },
            "wall_thickness_mm": {
                "type": "number",
                "description": "Gallery wall thickness in mm (typical 0.5–1.5 mm).",
            },
            "gallery_height_mm": {
                "type": "number",
                "description": "Axial height of gallery collar in mm (typical 1.5–4 mm).",
            },
            "border_style": {
                "type": "string",
                "enum": sorted(_VALID_BORDER_STYLES),
                "description": (
                    "Decorative border treatment. "
                    "'plain': smooth. 'scalloped': arched cut-outs. "
                    "'milgrain': bead-rolled edge. 'pierced': round holes. "
                    "'filigree': fine wire lace pattern."
                ),
            },
            "scallop_count": {
                "type": "integer",
                "description": "Number of scallop arcs (border_style='scalloped', default 12).",
            },
            "piercing_diameter_mm": {
                "type": "number",
                "description": "Piercing hole diameter mm (border_style='pierced').",
            },
            "piercing_count": {
                "type": "integer",
                "description": "Number of piercings around circumference.",
            },
        },
        "required": [
            "file_id",
            "stone_diameter_mm",
            "wall_thickness_mm",
            "gallery_height_mm",
        ],
    },
)


@register(jewelry_build_under_bezel_gallery_spec, write=True)
async def run_jewelry_build_under_bezel_gallery(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "")
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        file_id = uuid.UUID(str(file_id_str))
    except ValueError:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    for field in ("stone_diameter_mm", "wall_thickness_mm", "gallery_height_mm"):
        if a.get(field) is None:
            return err_payload(f"{field} is required", "BAD_ARGS")

    try:
        geom = under_bezel_gallery_geometry(
            stone_diameter_mm=float(a["stone_diameter_mm"]),
            wall_thickness_mm=float(a["wall_thickness_mm"]),
            gallery_height_mm=float(a["gallery_height_mm"]),
            border_style=str(a.get("border_style", "scalloped")),
            scallop_count=int(a.get("scallop_count", 12)),
            piercing_diameter_mm=float(a.get("piercing_diameter_mm", 0.0)),
            piercing_count=int(a.get("piercing_count", 0)),
        )
    except (ValueError, TypeError) as e:
        return err_payload(str(e), "BAD_ARGS")

    content, err = read_feature_content(ctx, file_id)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = next_node_id(content, "gallery_under_bezel")
    node = {"id": node_id, **geom}

    _, nid, err2 = append_feature_node(ctx, file_id, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({"node_id": nid, "under_bezel": geom})


# ---------------------------------------------------------------------------
# LLM tool: jewelry_build_cathedral_shoulders  (write)
# ---------------------------------------------------------------------------

jewelry_build_cathedral_shoulders_spec = ToolSpec(
    name="jewelry_build_cathedral_shoulders",
    description=(
        "Append a ``jewelry_gallery_cathedral`` node to a ``.feature`` file.\n\n"
        "Generates cathedral shoulder arches that sweep from the prong base "
        "down to the shank, merging the ring head into the band.\n\n"
        "Required: ``file_id``, ``prong_count``, ``stone_diameter_mm``, "
        "``wire_diameter_mm``, ``basket_height_mm``, ``shank_width_mm``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "prong_count": {"type": "integer"},
            "stone_diameter_mm": {"type": "number"},
            "wire_diameter_mm": {"type": "number"},
            "basket_height_mm": {"type": "number"},
            "shank_width_mm": {"type": "number"},
            "arch_rib_count": {
                "type": "integer",
                "description": "Arch ribs per shoulder (1 or 2, default 1).",
            },
            "arch_rise_mm": {
                "type": "number",
                "description": "Height of arch above shank (default = basket_height * 0.6).",
            },
        },
        "required": [
            "file_id",
            "prong_count",
            "stone_diameter_mm",
            "wire_diameter_mm",
            "basket_height_mm",
            "shank_width_mm",
        ],
    },
)


@register(jewelry_build_cathedral_shoulders_spec, write=True)
async def run_jewelry_build_cathedral_shoulders(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "")
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        file_id = uuid.UUID(str(file_id_str))
    except ValueError:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    for field in ("prong_count", "stone_diameter_mm", "wire_diameter_mm",
                  "basket_height_mm", "shank_width_mm"):
        if a.get(field) is None:
            return err_payload(f"{field} is required", "BAD_ARGS")

    try:
        geom = cathedral_shoulder_geometry(
            prong_count=int(a["prong_count"]),
            stone_diameter_mm=float(a["stone_diameter_mm"]),
            wire_diameter_mm=float(a["wire_diameter_mm"]),
            basket_height_mm=float(a["basket_height_mm"]),
            shank_width_mm=float(a["shank_width_mm"]),
            arch_rib_count=int(a.get("arch_rib_count", 1)),
            arch_rise_mm=float(a["arch_rise_mm"]) if a.get("arch_rise_mm") is not None else None,
        )
    except (ValueError, TypeError) as e:
        return err_payload(str(e), "BAD_ARGS")

    content, err = read_feature_content(ctx, file_id)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = next_node_id(content, "gallery_cathedral")
    node = {"id": node_id, **geom}

    _, nid, err2 = append_feature_node(ctx, file_id, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({"node_id": nid, "cathedral": geom})


# ---------------------------------------------------------------------------
# LLM tool: jewelry_build_trellis_shoulders  (write)
# ---------------------------------------------------------------------------

jewelry_build_trellis_shoulders_spec = ToolSpec(
    name="jewelry_build_trellis_shoulders",
    description=(
        "Append a ``jewelry_gallery_trellis`` node to a ``.feature`` file.\n\n"
        "Generates an interlocking cross-diagonal trellis connecting adjacent "
        "prongs to the shank rail — a classic RhinoGold trellis head design.\n\n"
        "Required: ``file_id``, ``prong_count``, ``stone_diameter_mm``, "
        "``wire_diameter_mm``, ``basket_height_mm``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "prong_count": {"type": "integer"},
            "stone_diameter_mm": {"type": "number"},
            "wire_diameter_mm": {"type": "number"},
            "basket_height_mm": {"type": "number"},
            "cross_count": {
                "type": "integer",
                "description": "Number of crossing diagonals per bay pair (1–4, default 2).",
            },
        },
        "required": [
            "file_id",
            "prong_count",
            "stone_diameter_mm",
            "wire_diameter_mm",
            "basket_height_mm",
        ],
    },
)


@register(jewelry_build_trellis_shoulders_spec, write=True)
async def run_jewelry_build_trellis_shoulders(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "")
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        file_id = uuid.UUID(str(file_id_str))
    except ValueError:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    for field in ("prong_count", "stone_diameter_mm", "wire_diameter_mm", "basket_height_mm"):
        if a.get(field) is None:
            return err_payload(f"{field} is required", "BAD_ARGS")

    try:
        geom = trellis_shoulder_geometry(
            prong_count=int(a["prong_count"]),
            stone_diameter_mm=float(a["stone_diameter_mm"]),
            wire_diameter_mm=float(a["wire_diameter_mm"]),
            basket_height_mm=float(a["basket_height_mm"]),
            cross_count=int(a.get("cross_count", 2)),
        )
    except (ValueError, TypeError) as e:
        return err_payload(str(e), "BAD_ARGS")

    content, err = read_feature_content(ctx, file_id)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = next_node_id(content, "gallery_trellis")
    node = {"id": node_id, **geom}

    _, nid, err2 = append_feature_node(ctx, file_id, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({"node_id": nid, "trellis": geom})


# ---------------------------------------------------------------------------
# LLM tool: jewelry_estimate_gallery_metal  (read — no write)
# ---------------------------------------------------------------------------

jewelry_estimate_gallery_metal_spec = ToolSpec(
    name="jewelry_estimate_gallery_metal",
    description=(
        "Read-only estimator: compute metal volume (mm³), surface area (mm²), "
        "and weight (grams) for a basket gallery spec.\n\n"
        "Also emits a structural warning if wire_diameter_mm is below the "
        "recommended minimum for the stone carat weight.\n\n"
        "Pass the same parameters as ``jewelry_build_basket_gallery`` plus "
        "``density_g_cm3`` (alloy density) and ``stone_carat``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "prong_count": {"type": "integer"},
            "stone_diameter_mm": {"type": "number"},
            "wire_diameter_mm": {"type": "number"},
            "basket_height_mm": {"type": "number"},
            "rail_count": {"type": "integer"},
            "taper_ratio": {"type": "number"},
            "splay_angle_deg": {"type": "number"},
            "cutout_style": {"type": "string", "enum": sorted(_VALID_CUTOUT_STYLES)},
            "diagonal_struts": {"type": "boolean"},
            "strut_count": {"type": "integer"},
            "density_g_cm3": {
                "type": "number",
                "description": (
                    "Alloy density in g/cm³. "
                    "18k yellow gold ≈ 15.53, platinum 950 ≈ 21.40, "
                    "sterling silver 925 ≈ 10.36."
                ),
            },
            "stone_carat": {
                "type": "number",
                "description": "Stone weight in carats for structural wire check.",
            },
        },
        "required": [
            "prong_count",
            "stone_diameter_mm",
            "wire_diameter_mm",
            "basket_height_mm",
        ],
    },
)


@register(jewelry_estimate_gallery_metal_spec, write=False)
async def run_jewelry_estimate_gallery_metal(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    for field in ("prong_count", "stone_diameter_mm", "wire_diameter_mm", "basket_height_mm"):
        if a.get(field) is None:
            return err_payload(f"{field} is required", "BAD_ARGS")

    try:
        geom = basket_geometry(
            prong_count=int(a["prong_count"]),
            stone_diameter_mm=float(a["stone_diameter_mm"]),
            wire_diameter_mm=float(a["wire_diameter_mm"]),
            basket_height_mm=float(a["basket_height_mm"]),
            rail_count=int(a.get("rail_count", 1)),
            taper_ratio=float(a.get("taper_ratio", 0.0)),
            splay_angle_deg=float(a.get("splay_angle_deg", 5.0)),
            cutout_style=str(a.get("cutout_style", "scallop")),
            diagonal_struts=bool(a.get("diagonal_struts", False)),
            strut_count=int(a.get("strut_count", 0)),
        )
    except (ValueError, TypeError) as e:
        return err_payload(str(e), "BAD_ARGS")

    vol = basket_metal_volume_mm3(geom)
    sa = basket_surface_area_mm2(geom)

    result: dict = {
        "volume_mm3": round(vol, 4),
        "surface_area_mm2": round(sa, 4),
    }

    density = a.get("density_g_cm3")
    if density is not None:
        try:
            wt = metal_weight_grams(vol, float(density))
            result["weight_grams"] = round(wt, 4)
        except (ValueError, TypeError) as e:
            return err_payload(str(e), "BAD_ARGS")

    stone_carat = a.get("stone_carat")
    if stone_carat is not None:
        try:
            warn = min_wire_diameter_check(
                float(a["wire_diameter_mm"]),
                float(stone_carat),
            )
            if warn:
                result["structural_warning"] = warn
        except (ValueError, TypeError):
            pass

    return ok_payload(result)
