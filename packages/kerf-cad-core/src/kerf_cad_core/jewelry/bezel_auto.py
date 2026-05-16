"""
kerf_cad_core.jewelry.bezel_auto
=================================

Bezel / tube-setting **auto-from-stone** wizard — RhinoGold / MatrixGold parity.

Given any gemstone (cut + size from ``gemstones.py`` / ``gem_studio.py``),
derive a complete bezel or tube setting without the caller specifying every
dimension.  All sizing is driven by industry min-wall rules, girdle-to-table
proportions, and stone outline geometry.

Functions
---------
bezel_auto_from_stone(cut, stone_mm, style, ...)
    Full wizard: inner profile follows the girdle (circle for round/oval;
    polygon / stadium for fancy cuts with appropriate corner radii), bezel
    wall scaled by a min-wall rule, height from girdle-to-table proportion,
    outer taper / edge treatment, optional seat groove and under-gallery
    cutout.  Returns a BezelAutoSpec dict compatible with the OCCT worker's
    opJewelryBezelAuto handler.

tube_setting_auto(stone_mm, ...)
    Round-stone tube bezel shorthand: ID = girdle ø + clearance, OD = ID +
    2·wall, height proportional to stone size, lip/burnish edge spec.

Bezel styles
------------
straight       Full-height vertical bezel wall (collet).
bombe          Outward-bowing ("bombé") outer wall; OD at mid-height = peak.
scallop        Wall scalloped / notched between four opposing low points
               so light enters from the sides; each notch is a circular arc.
half_bezel     Bezel walls at the two long ends only (east–west open sides).
full_bezel     360° vertical wall, same as straight but name is canonical.
v_bezel        Inward-tapering V-form wall (collet cone).
illusion       Faceted metal plate extends beyond the stone edge to make it
               appear larger; outer rim = stone ø × illusion_factor.

Edge treatments
---------------
sharp          Top edge left as machined (fine bright-cut look).
burnished      Top edge rolled inward to grip the stone girdle.
bright_cut     Top edge faceted at 45° for maximum sparkle.

Under-gallery cutout
--------------------
When ``under_gallery_cutout=True`` the wizard computes a sub-circular or
sub-profile cutout from the bezel base.  The cutout volume is returned so
the caller can subtract it from a ring shank.  Integrates with gallery.py
conventions (same parameter names).

Seat groove
-----------
A V-groove (bearing ledge) on the inner wall at girdle_seat_z below the top
edge; depth = 0.1 mm, half-angle = 15°.  Compatible with gem_seat.py's
bezel_seat_geometry() output.

LLM-facing tools
----------------
  jewelry_bezel_auto_from_stone  — full bezel wizard (write)
  jewelry_tube_setting_auto      — tube bezel shorthand (write)

Units: millimetres throughout.  All angles in degrees.

Error convention: LLM tools never raise — they return err_payload(...) on
any error, following the exact pattern in settings.py and head_wizard.py.
"""

from __future__ import annotations

import json
import math
import uuid
import warnings
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import (
    append_feature_node,
    next_node_id,
    read_feature_content,
)
from kerf_cad_core.jewelry.gemstones import (
    GEMSTONE_CUTS,
    _CUT_DEFAULTS,
)


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

BEZEL_STYLES = frozenset([
    "straight",
    "bombe",
    "scallop",
    "half_bezel",
    "full_bezel",
    "v_bezel",
    "illusion",
])

EDGE_TREATMENTS = frozenset(["sharp", "burnished", "bright_cut"])

# Cuts where the inner bore is a circle.
_ROUND_PROFILE_CUTS = frozenset([
    "round_brilliant", "oval", "briolette", "rose_cut", "single_cut",
    "old_european", "old_mine", "cabochon",
])

# Cuts using a rectangular inner bore with chamfered corners.
_RECT_PROFILE_CUTS = frozenset([
    "emerald", "asscher", "baguette", "radiant", "square_emerald",
    "ceylon", "flanders", "tapered_baguette", "french_cut",
])

# Cuts using a polygonal inner bore.
_POLY_PROFILE_CUTS = frozenset([
    "princess", "trillion", "lozenge", "kite", "shield",
])

# Cuts with pointed-end profiles (stadium / lens).
_POINTED_PROFILE_CUTS = frozenset([
    "marquise", "pear", "heart", "bullet", "calf_head", "half_moon",
    "trapezoid", "portuguese",
])

# ---------------------------------------------------------------------------
# Industry min-wall rule (mm) — scales with stone size.
# Sources: RhinoGold design manual; industry bench practice for fine jewellery.
# Bracket: (stone_mm_min, stone_mm_max, min_wall_mm)
# ---------------------------------------------------------------------------

_MIN_WALL_TABLE: list[tuple[float, float, float]] = [
    (0.0,   3.0,  0.30),   # < 3 mm stone   → 0.30 mm min wall
    (3.0,   5.0,  0.35),
    (5.0,   8.0,  0.40),
    (8.0,  12.0,  0.50),
    (12.0, 20.0,  0.60),
    (20.0, 999.9, 0.70),
]

# Height as a fraction of stone long-axis (girdle-to-table proportion).
# Value is (bezel_height / stone_mm).
_HEIGHT_FACTOR = 0.40   # 40% of stone primary dimension; industry consensus


def _min_wall_for_stone(stone_mm: float) -> float:
    """Return minimum bezel wall thickness (mm) for a given stone primary dim."""
    for lo, hi, wall in _MIN_WALL_TABLE:
        if lo <= stone_mm < hi:
            return wall
    return _MIN_WALL_TABLE[-1][2]


def _girdle_profile_shape(cut: str) -> str:
    """Return the inner profile shape string for the OCCT worker."""
    if cut in _ROUND_PROFILE_CUTS:
        return "circle"
    if cut in _RECT_PROFILE_CUTS:
        return "rect_chamfer"
    if cut in _POLY_PROFILE_CUTS:
        if cut == "trillion":
            return "triangle"
        return "polygon"
    if cut in _POINTED_PROFILE_CUTS:
        if cut == "pear":
            return "pear"
        return "stadium"
    # Fallback
    return "ellipse"


def _scallop_notch_positions(n_notches: int) -> list[dict]:
    """Return n_notches evenly spaced angular positions (degrees) for scallop arcs."""
    step = 360.0 / n_notches
    return [{"angle_deg": round(i * step, 3)} for i in range(n_notches)]


# ---------------------------------------------------------------------------
# Core pure-Python geometry helpers
# ---------------------------------------------------------------------------

def bezel_auto_node(
    node_id: str,
    cut: str,
    stone_mm: float,
    style: str,
    *,
    wall_thickness: Optional[float] = None,
    bezel_height: Optional[float] = None,
    edge_treatment: str = "bright_cut",
    seat_groove: bool = True,
    under_gallery_cutout: bool = False,
    gallery_cutout_height: Optional[float] = None,
    scallop_count: int = 4,
    bombe_bulge_factor: float = 1.15,
    illusion_factor: float = 1.25,
    taper_angle_deg: float = 5.0,
    aspect_ratio: Optional[float] = None,
    corner_radius_pct: Optional[float] = None,
    girdle_clearance_mm: float = 0.05,
) -> dict:
    """
    Compute the full bezel-auto node spec dict (pure Python, no OCC).

    Parameters
    ----------
    node_id           : feature node UUID string
    cut               : gemstone cut name (from GEMSTONE_CUTS)
    stone_mm          : primary dimension in mm (girdle ø for round; long-axis for others)
    style             : one of BEZEL_STYLES
    wall_thickness    : override; None = use min-wall rule (recommended)
    bezel_height      : override; None = derive from _HEIGHT_FACTOR × stone_mm
    edge_treatment    : "sharp" | "burnished" | "bright_cut"
    seat_groove       : if True, compute seat-groove dimensions
    under_gallery_cutout : if True, compute cutout volume for sub-bezel gallery ring
    gallery_cutout_height : height of the cutout cylinder; None = 0.5 × bezel_height
    scallop_count     : number of scallop notches for "scallop" style
    bombe_bulge_factor: OD peak factor at mid-height for "bombe" style (>= 1.0)
    illusion_factor   : OD / stone_mm for "illusion" style
    taper_angle_deg   : outer wall taper for "v_bezel" style
    aspect_ratio      : override the cut's default aspect ratio
    corner_radius_pct : override corner radius (% of short axis); None = cut default
    girdle_clearance_mm : radial clearance between stone girdle and inner bore
    """
    defaults = _CUT_DEFAULTS.get(cut, {})
    ar = aspect_ratio if aspect_ratio is not None else defaults.get("aspect_ratio", 1.0)

    # Inner bore sizing (girdle outline + clearance).
    inner_long = stone_mm + 2.0 * girdle_clearance_mm
    inner_short = stone_mm * ar + 2.0 * girdle_clearance_mm

    # Wall thickness
    min_wall = _min_wall_for_stone(stone_mm)
    if wall_thickness is None:
        # Scale wall slightly above minimum: 0.4 mm + 2% of stone_mm (capped at min).
        computed_wall = max(min_wall, 0.4 + 0.02 * stone_mm)
        wall = round(computed_wall, 3)
    else:
        wall = float(wall_thickness)
        if wall < min_wall:
            warnings.warn(
                f"bezel wall {wall:.3f} mm is below recommended minimum "
                f"{min_wall:.3f} mm for a {stone_mm:.2f} mm stone",
                stacklevel=3,
            )

    # Outer bore (long-axis OD)
    outer_long = inner_long + 2.0 * wall
    outer_short = inner_short + 2.0 * wall

    # Bezel height
    if bezel_height is None:
        height = round(max(0.5, _HEIGHT_FACTOR * stone_mm), 4)
    else:
        height = float(bezel_height)

    # Profile shape for inner bore
    profile_shape = _girdle_profile_shape(cut)

    # Corner radius on the inner bore
    if corner_radius_pct is not None:
        cr_mm = inner_short * corner_radius_pct / 100.0
    else:
        extras = defaults.get("extras", {})
        cr_pct = extras.get("corner_radius_pct", extras.get("corner_cut_ratio", 0.0) * 100)
        cr_mm = inner_short * cr_pct / 100.0

    # Seat groove (inner V-groove for girdle bearing)
    seat_groove_z = height - (stone_mm * 0.10)   # 10% of stone_mm below top
    seat_groove_z = round(max(0.1, seat_groove_z), 4)
    seat_groove_depth = 0.10   # mm
    seat_groove_half_angle_deg = 15.0

    # Under-gallery cutout
    if under_gallery_cutout:
        gch = gallery_cutout_height if gallery_cutout_height else round(height * 0.5, 4)
        gch = round(float(gch), 4)
        # Cutout is a cylinder / profile-matched void below the bezel base.
        cutout_radius = inner_long / 2.0 - wall * 0.5
        cutout_volume_mm3 = round(
            math.pi * cutout_radius ** 2 * gch, 6
        )
    else:
        gch = 0.0
        cutout_volume_mm3 = 0.0

    # Style-specific derived geometry
    style_params: dict = {}
    if style == "bombe":
        style_params["bombe_peak_od"] = round(outer_long * bombe_bulge_factor, 4)
        style_params["bombe_bulge_factor"] = bombe_bulge_factor
    elif style == "scallop":
        style_params["scallop_count"] = scallop_count
        style_params["scallop_notch_depth_mm"] = round(height * 0.45, 4)
        style_params["scallop_positions"] = _scallop_notch_positions(scallop_count)
    elif style == "half_bezel":
        # East-west bezel: two arc walls at the pointed/round ends.
        style_params["opening_arc_deg"] = 180.0  # open 180° on each of N/S sides
    elif style == "v_bezel":
        style_params["taper_angle_deg"] = round(float(taper_angle_deg), 3)
        # Inner diameter widens from base to top by taper geometry.
        style_params["base_outer_long"] = round(outer_long + 2.0 * height * math.tan(math.radians(taper_angle_deg)), 4)
    elif style == "illusion":
        illusion_outer_long = round(stone_mm * illusion_factor, 4)
        style_params["illusion_outer_long"] = illusion_outer_long
        style_params["illusion_factor"] = illusion_factor
        style_params["illusion_plate_height"] = round(height * 0.5, 4)

    # Prong/tab anchors where required (half-bezel needs two side prongs).
    tab_anchors: list[dict] = []
    if style == "half_bezel":
        # Two side prongs 90° from the open ends.
        tab_anchors = [
            {"angle_deg": 90.0,  "tab_width_mm": round(wall * 0.8, 3)},
            {"angle_deg": 270.0, "tab_width_mm": round(wall * 0.8, 3)},
        ]

    # Volume estimate: (OD_long × OD_short - ID_long × ID_short) × π/4 × height
    # (uses elliptical cross-section approximation).
    vol_outer = math.pi / 4.0 * outer_long * outer_short
    vol_inner = math.pi / 4.0 * inner_long * inner_short
    volume_mm3 = round((vol_outer - vol_inner) * height, 6)
    if under_gallery_cutout and cutout_volume_mm3 > 0.0:
        volume_mm3 = round(volume_mm3 - cutout_volume_mm3, 6)

    # Seat cutter spec compatible with gem_seat.py's bezel_seat_geometry().
    seat_cutter = {
        "op": "bezel_seat_cutter",
        "inner_long_mm": round(inner_long, 4),
        "inner_short_mm": round(inner_short, 4),
        "corner_radius_mm": round(cr_mm, 4),
        "profile_shape": profile_shape,
        "girdle_clearance_mm": round(girdle_clearance_mm, 4),
        "bearing_ledge_z": round(seat_groove_z, 4),
    }

    node: dict = {
        "id": node_id,
        "op": "jewelry_bezel_auto",
        # Stone description
        "cut": cut,
        "stone_mm": round(stone_mm, 4),
        "aspect_ratio": round(ar, 4),
        # Bezel style + edge
        "style": style,
        "edge_treatment": edge_treatment,
        # Inner bore
        "inner_long_mm": round(inner_long, 4),
        "inner_short_mm": round(inner_short, 4),
        "inner_profile_shape": profile_shape,
        "inner_corner_radius_mm": round(cr_mm, 4),
        # Wall + outer bore
        "wall_thickness_mm": round(wall, 4),
        "min_wall_mm": round(min_wall, 4),
        "outer_long_mm": round(outer_long, 4),
        "outer_short_mm": round(outer_short, 4),
        # Height
        "bezel_height_mm": round(height, 4),
        # Seat groove
        "seat_groove": seat_groove,
        "seat_groove_z_mm": round(seat_groove_z, 4),
        "seat_groove_depth_mm": seat_groove_depth,
        "seat_groove_half_angle_deg": seat_groove_half_angle_deg,
        # Under-gallery cutout
        "under_gallery_cutout": under_gallery_cutout,
        "gallery_cutout_height_mm": round(gch, 4),
        "gallery_cutout_volume_mm3": cutout_volume_mm3,
        # Tab anchors
        "tab_anchors": tab_anchors,
        # Style-specific params
        **style_params,
        # Volume estimate
        "_volume_mm3": volume_mm3,
        # Compatible seat cutter for gem_seat.py
        "_seat_cutter": seat_cutter,
    }
    return node


def tube_setting_node(
    node_id: str,
    stone_mm: float,
    *,
    wall_thickness: Optional[float] = None,
    tube_height: Optional[float] = None,
    lip_height_mm: float = 0.20,
    burnish_edge: bool = True,
    girdle_clearance_mm: float = 0.05,
) -> dict:
    """
    Compute the tube-bezel node spec (pure Python, no OCC).

    A tube setting is a plain cylinder: ID = girdle_ø + clearance,
    OD = ID + 2·wall, height proportional to stone.

    Parameters
    ----------
    node_id            : feature node UUID string
    stone_mm           : round stone girdle diameter (mm)
    wall_thickness     : override; None = min-wall rule
    tube_height        : override; None = 0.55 × stone_mm
    lip_height_mm      : height of the burnish lip at the tube top
    burnish_edge       : if True, the top lip is rolled inward (burnish)
    girdle_clearance_mm: radial clearance between girdle and inner bore
    """
    min_wall = _min_wall_for_stone(stone_mm)
    if wall_thickness is None:
        wall = round(max(min_wall, 0.4 + 0.015 * stone_mm), 3)
    else:
        wall = float(wall_thickness)
        if wall < min_wall:
            warnings.warn(
                f"tube wall {wall:.3f} mm is below recommended minimum "
                f"{min_wall:.3f} mm for a {stone_mm:.2f} mm stone",
                stacklevel=3,
            )

    id_mm = round(stone_mm + 2.0 * girdle_clearance_mm, 4)
    od_mm = round(id_mm + 2.0 * wall, 4)

    if tube_height is None:
        height = round(max(0.5, 0.55 * stone_mm), 4)
    else:
        height = round(float(tube_height), 4)

    # Seat groove (same as bezel_auto)
    seat_groove_z = round(max(0.1, height - stone_mm * 0.10), 4)

    # Volume: annular cylinder = (OD² - ID²) × π/4 × height
    volume_mm3 = round(
        (od_mm ** 2 - id_mm ** 2) * math.pi / 4.0 * height, 6
    )

    # Seat cutter compatible with gem_seat.py bezel_seat_geometry()
    seat_cutter = {
        "op": "bezel_seat_cutter",
        "inner_long_mm": id_mm,
        "inner_short_mm": id_mm,
        "corner_radius_mm": 0.0,
        "profile_shape": "circle",
        "girdle_clearance_mm": round(girdle_clearance_mm, 4),
        "bearing_ledge_z": seat_groove_z,
    }

    return {
        "id": node_id,
        "op": "jewelry_tube_setting_auto",
        "stone_mm": round(stone_mm, 4),
        "girdle_clearance_mm": round(girdle_clearance_mm, 4),
        "id_mm": id_mm,
        "od_mm": od_mm,
        "wall_thickness_mm": round(wall, 4),
        "min_wall_mm": round(min_wall, 4),
        "tube_height_mm": height,
        "lip_height_mm": round(lip_height_mm, 4),
        "burnish_edge": burnish_edge,
        "seat_groove_z_mm": seat_groove_z,
        # Volume = (OD² − ID²) × π/4 × h
        "_volume_mm3": volume_mm3,
        "_seat_cutter": seat_cutter,
    }


# ---------------------------------------------------------------------------
# Public Python API (no feature file I/O — returns spec dicts directly)
# ---------------------------------------------------------------------------

def bezel_auto_from_stone(
    cut: str,
    stone_mm: float,
    style: str,
    *,
    wall_thickness: Optional[float] = None,
    bezel_height: Optional[float] = None,
    edge_treatment: str = "bright_cut",
    seat_groove: bool = True,
    under_gallery_cutout: bool = False,
    gallery_cutout_height: Optional[float] = None,
    scallop_count: int = 4,
    bombe_bulge_factor: float = 1.15,
    illusion_factor: float = 1.25,
    taper_angle_deg: float = 5.0,
    aspect_ratio: Optional[float] = None,
    corner_radius_pct: Optional[float] = None,
    girdle_clearance_mm: float = 0.05,
) -> dict:
    """
    Derive a full bezel/tube-setting spec from stone cut and primary dimension.

    Returns a BezelAutoSpec dict (no feature file written).  Never raises;
    returns a dict with ``"error"`` key on invalid input.
    """
    # Validate without raising
    if cut not in GEMSTONE_CUTS:
        return {"error": f"Unknown cut {cut!r}. Valid: {sorted(GEMSTONE_CUTS)}"}
    try:
        stone_mm = float(stone_mm)
    except (TypeError, ValueError):
        return {"error": f"stone_mm must be a number; got {stone_mm!r}"}
    if stone_mm <= 0:
        return {"error": f"stone_mm must be positive; got {stone_mm}"}
    if style not in BEZEL_STYLES:
        return {"error": f"style must be one of {sorted(BEZEL_STYLES)}; got {style!r}"}
    if edge_treatment not in EDGE_TREATMENTS:
        return {"error": f"edge_treatment must be one of {sorted(EDGE_TREATMENTS)}; got {edge_treatment!r}"}

    node_id = str(uuid.uuid4())
    return bezel_auto_node(
        node_id=node_id,
        cut=cut,
        stone_mm=stone_mm,
        style=style,
        wall_thickness=wall_thickness,
        bezel_height=bezel_height,
        edge_treatment=edge_treatment,
        seat_groove=seat_groove,
        under_gallery_cutout=under_gallery_cutout,
        gallery_cutout_height=gallery_cutout_height,
        scallop_count=scallop_count,
        bombe_bulge_factor=bombe_bulge_factor,
        illusion_factor=illusion_factor,
        taper_angle_deg=taper_angle_deg,
        aspect_ratio=aspect_ratio,
        corner_radius_pct=corner_radius_pct,
        girdle_clearance_mm=girdle_clearance_mm,
    )


def tube_setting_auto(
    stone_mm: float,
    *,
    wall_thickness: Optional[float] = None,
    tube_height: Optional[float] = None,
    lip_height_mm: float = 0.20,
    burnish_edge: bool = True,
    girdle_clearance_mm: float = 0.05,
) -> dict:
    """
    Derive a tube-bezel spec for a round stone.  Never raises.

    ID = girdle_ø + clearance.  OD = ID + 2·wall.
    Volume = (OD² − ID²) × π/4 × height (exact for a perfect annular cylinder).
    """
    try:
        stone_mm = float(stone_mm)
    except (TypeError, ValueError):
        return {"error": f"stone_mm must be a number; got {stone_mm!r}"}
    if stone_mm <= 0:
        return {"error": f"stone_mm must be positive; got {stone_mm}"}

    node_id = str(uuid.uuid4())
    return tube_setting_node(
        node_id=node_id,
        stone_mm=stone_mm,
        wall_thickness=wall_thickness,
        tube_height=tube_height,
        lip_height_mm=lip_height_mm,
        burnish_edge=burnish_edge,
        girdle_clearance_mm=girdle_clearance_mm,
    )


# ---------------------------------------------------------------------------
# LLM tool specs
# ---------------------------------------------------------------------------

jewelry_bezel_auto_spec = ToolSpec(
    name="jewelry_bezel_auto_from_stone",
    description=(
        "Derive a complete bezel / tube-setting geometry from a stone cut and "
        "primary dimension.  Wizard computes inner profile, wall thickness, "
        "height, edge treatment, seat groove and optional under-gallery cutout "
        "automatically.  Outputs a BezelAutoSpec node appended to a .feature file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id":        {"type": "string", "description": "Target .feature file UUID"},
            "cut":            {"type": "string", "description": "Gemstone cut name (e.g. 'round_brilliant', 'oval', 'emerald')"},
            "stone_mm":       {"type": "number", "description": "Stone primary dimension in mm (girdle ø for round; long-axis for others)"},
            "style":          {"type": "string", "enum": sorted(BEZEL_STYLES), "description": "Bezel style"},
            "wall_thickness": {"type": "number", "description": "Wall thickness override in mm; omit to use min-wall rule"},
            "bezel_height":   {"type": "number", "description": "Bezel height override in mm; omit to derive from stone size"},
            "edge_treatment": {"type": "string", "enum": sorted(EDGE_TREATMENTS), "description": "Top-edge treatment", "default": "bright_cut"},
            "seat_groove":    {"type": "boolean", "description": "Include inner V-groove seat for girdle bearing", "default": True},
            "under_gallery_cutout": {"type": "boolean", "description": "Add under-gallery cutout from bezel base", "default": False},
            "gallery_cutout_height": {"type": "number", "description": "Gallery cutout height in mm (default 0.5 × bezel_height)"},
            "scallop_count":  {"type": "integer", "description": "Number of scallop notches (style='scallop' only)", "default": 4},
            "bombe_bulge_factor": {"type": "number", "description": "Outer OD peak factor at mid-height (style='bombe' only)", "default": 1.15},
            "illusion_factor":    {"type": "number", "description": "OD / stone_mm for illusion plate (style='illusion' only)", "default": 1.25},
            "taper_angle_deg":    {"type": "number", "description": "Outer wall taper angle in degrees (style='v_bezel' only)", "default": 5.0},
            "girdle_clearance_mm": {"type": "number", "description": "Radial clearance mm between stone and inner bore", "default": 0.05},
        },
        "required": ["file_id", "cut", "stone_mm", "style"],
    },
)

jewelry_tube_setting_auto_spec = ToolSpec(
    name="jewelry_tube_setting_auto",
    description=(
        "Tube-bezel shorthand for round stones: ID = girdle_ø + clearance, "
        "OD = ID + 2·wall, height proportional, burnish lip.  "
        "Appends a tube-bezel node to a .feature file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id":         {"type": "string", "description": "Target .feature file UUID"},
            "stone_mm":        {"type": "number", "description": "Round stone girdle diameter in mm"},
            "wall_thickness":  {"type": "number", "description": "Wall thickness override in mm; omit for auto"},
            "tube_height":     {"type": "number", "description": "Tube height override in mm; omit to derive"},
            "lip_height_mm":   {"type": "number", "description": "Burnish-lip height in mm", "default": 0.20},
            "burnish_edge":    {"type": "boolean", "description": "Roll top edge inward (burnish)", "default": True},
            "girdle_clearance_mm": {"type": "number", "description": "Radial clearance mm", "default": 0.05},
        },
        "required": ["file_id", "stone_mm"],
    },
)


# ---------------------------------------------------------------------------
# LLM tool runners
# ---------------------------------------------------------------------------

@register(jewelry_bezel_auto_spec)
async def run_jewelry_bezel_auto_from_stone(params: dict, ctx: ProjectCtx) -> str:
    file_id = params.get("file_id", "")
    cut = params.get("cut", "")
    stone_mm = params.get("stone_mm")
    style = params.get("style", "")
    wall_thickness = params.get("wall_thickness")
    bezel_height = params.get("bezel_height")
    edge_treatment = params.get("edge_treatment", "bright_cut")
    seat_groove = params.get("seat_groove", True)
    under_gallery_cutout = params.get("under_gallery_cutout", False)
    gallery_cutout_height = params.get("gallery_cutout_height")
    scallop_count = params.get("scallop_count", 4)
    bombe_bulge_factor = params.get("bombe_bulge_factor", 1.15)
    illusion_factor = params.get("illusion_factor", 1.25)
    taper_angle_deg = params.get("taper_angle_deg", 5.0)
    girdle_clearance_mm = params.get("girdle_clearance_mm", 0.05)

    # Validate required fields
    if not file_id:
        return err_payload("file_id is required", code="BAD_ARGS")
    if not cut:
        return err_payload("cut is required", code="BAD_ARGS")
    if stone_mm is None:
        return err_payload("stone_mm is required", code="BAD_ARGS")
    if not style:
        return err_payload("style is required", code="BAD_ARGS")
    if cut not in GEMSTONE_CUTS:
        return err_payload(f"Unknown cut {cut!r}", code="BAD_ARGS")
    if style not in BEZEL_STYLES:
        return err_payload(f"style must be one of {sorted(BEZEL_STYLES)}; got {style!r}", code="BAD_ARGS")
    if edge_treatment not in EDGE_TREATMENTS:
        return err_payload(f"edge_treatment must be one of {sorted(EDGE_TREATMENTS)}; got {edge_treatment!r}", code="BAD_ARGS")
    try:
        stone_mm_f = float(stone_mm)
    except (TypeError, ValueError):
        return err_payload(f"stone_mm must be a number; got {stone_mm!r}", code="BAD_ARGS")
    if stone_mm_f <= 0:
        return err_payload(f"stone_mm must be positive; got {stone_mm_f}", code="BAD_ARGS")

    # Read + validate feature file
    content, err = read_feature_content(ctx, file_id)
    if err:
        return err_payload(f"File {file_id!r} not found", code="NOT_FOUND")

    node_id = next_node_id(content, "bezel_auto")
    node = bezel_auto_node(
        node_id=node_id,
        cut=cut,
        stone_mm=stone_mm_f,
        style=style,
        wall_thickness=wall_thickness,
        bezel_height=bezel_height,
        edge_treatment=edge_treatment,
        seat_groove=bool(seat_groove),
        under_gallery_cutout=bool(under_gallery_cutout),
        gallery_cutout_height=gallery_cutout_height,
        scallop_count=int(scallop_count),
        bombe_bulge_factor=float(bombe_bulge_factor),
        illusion_factor=float(illusion_factor),
        taper_angle_deg=float(taper_angle_deg),
        girdle_clearance_mm=float(girdle_clearance_mm),
    )

    _, _, append_err = append_feature_node(ctx, file_id, node)
    if append_err:
        return err_payload(f"append failed: {append_err}", code="INTERNAL")

    return ok_payload({"node_id": node_id, "bezel": node})


@register(jewelry_tube_setting_auto_spec)
async def run_jewelry_tube_setting_auto(params: dict, ctx: ProjectCtx) -> str:
    file_id = params.get("file_id", "")
    stone_mm = params.get("stone_mm")
    wall_thickness = params.get("wall_thickness")
    tube_height = params.get("tube_height")
    lip_height_mm = params.get("lip_height_mm", 0.20)
    burnish_edge = params.get("burnish_edge", True)
    girdle_clearance_mm = params.get("girdle_clearance_mm", 0.05)

    if not file_id:
        return err_payload("file_id is required", code="BAD_ARGS")
    if stone_mm is None:
        return err_payload("stone_mm is required", code="BAD_ARGS")
    try:
        stone_mm_f = float(stone_mm)
    except (TypeError, ValueError):
        return err_payload(f"stone_mm must be a number; got {stone_mm!r}", code="BAD_ARGS")
    if stone_mm_f <= 0:
        return err_payload(f"stone_mm must be positive; got {stone_mm_f}", code="BAD_ARGS")

    content, err = read_feature_content(ctx, file_id)
    if err:
        return err_payload(f"File {file_id!r} not found", code="NOT_FOUND")

    node_id = next_node_id(content, "tube_setting")
    node = tube_setting_node(
        node_id=node_id,
        stone_mm=stone_mm_f,
        wall_thickness=wall_thickness,
        tube_height=tube_height,
        lip_height_mm=float(lip_height_mm),
        burnish_edge=bool(burnish_edge),
        girdle_clearance_mm=float(girdle_clearance_mm),
    )

    _, _, append_err = append_feature_node(ctx, file_id, node)
    if append_err:
        return err_payload(f"append failed: {append_err}", code="INTERNAL")

    return ok_payload({"node_id": node_id, "tube_setting": node})
