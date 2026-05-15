"""
kerf_cad_core.jewelry.settings — Parametric stone setting generators.

Twenty-eight setting types, each with:
  1. A pure-Python geometry helper that returns a node-spec dict (no OCCT
     required — the dict is consumed by the OCCT worker's opJewelry* handlers).
  2. An LLM tool (ToolSpec + @register runner) following the exact pattern
     in kerf_cad_core.surfacing.

Setting types
-------------
prong_head   — 4-, 6-, basket, trellis, or cathedral prong head.
bezel        — full or partial bezel / collet, with optional taper.
channel      — parallel-rail channel for a row of N calibrated stones.
pave_array   — grid-project over a target region; return placement transforms.
tension      — stone held by spring pressure between two band ends.
flush        — stone set into a drilled seat flush with the metal surface.
halo         — center stone seat ringed by a pavé/accent halo.
three_stone  — center + two graduated side-stone seats on a shared base.
cluster      — N small stones grouped to read as one large stone.
bar          — stones held between parallel metal bars (no prongs between stones).
bead_grain   — stones held by raised metal beads cut up from the surface.
gypsy_pave   — flush-set stones with engraved star/bright-cut accents.
illusion     — faceted metal plate around a small stone to make it look larger.
invisible    — stones with grooved girdles held on a hidden rail.

prong_variant — double, claw, v, fishtail, split, or decorative prong wire variants.
head_gallery  — basket/peg head + decorative gallery rail (plain, scalloped,
                milgrain_edge, pierced, filigree).
under_bezel   — sub-collet that elevates a stone above the shank.
peg_setting   — post head for earrings and pendants.
coronet       — tapered crown of graduated prongs (vintage/Victorian look).

suspension_mount    — articulated dangle mount (pivot ring + stone seat) for drop
                      earrings and pendants.
vtip_protector      — protective metal V-tip caps for pointed stone corners
                      (pear, marquise, heart, trillion).
bombe_cluster       — domed multi-stone cluster on a curved surface (bombé style).
patterned_bezel     — decorative bezel collar with petal/compass/star outline cutouts.
trellis_prong       — interwoven cross-prong basket setting.
bar_channel_graduated — row of graduated stones with bar separators between each stone.

Geometry approach (shared)
--------------------------
Each helper builds a node dict that the OCCT worker evaluates via
BRepPrimAPI / BRepBuilderAPI primitives. No OCCT imports here; all
math is pure Python / optional numpy. The worker receives the node
through the same .feature JSON tree used by pad / sweep1 / boolean.

Units: millimetres throughout.
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

# Re-use helpers from the parent surfacing module.
from kerf_cad_core.surfacing import (
    next_node_id,
    read_feature_content,
    append_feature_node,
)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_VALID_PRONG_COUNTS = {4, 6}
_VALID_HEAD_STYLES = {"standard", "basket", "trellis", "cathedral"}
_VALID_BEZEL_STYLES = {"full", "partial", "collet", "tapered"}


def _positive(name: str, value) -> Optional[str]:
    """Return error string if value is not a positive number, else None."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number; got {value!r}"
    if v <= 0:
        return f"{name} must be positive; got {v}"
    return None


def _non_negative_int(name: str, value) -> Optional[str]:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return f"{name} must be an integer; got {value!r}"
    if v < 0:
        return f"{name} must be >= 0; got {v}"
    return None


# ---------------------------------------------------------------------------
# Pure-Python geometry helpers (return node-spec dicts)
# ---------------------------------------------------------------------------

def build_prong_head_node(
    node_id: str,
    stone_diameter: float,
    prong_count: int,
    prong_wire_diameter: float,
    prong_height: float,
    head_style: str,
    basket_rail_count: int,
    seat_angle_deg: float,
) -> dict:
    """
    Compute the prong-head node spec.

    The worker's opJewelryProngHead uses these parameters to build:
      - A bearing ledge cylinder of diameter = stone_diameter + 2*wall.
      - `prong_count` round prong wires (diameter = prong_wire_diameter)
        evenly distributed around the stone, each rising prong_height above
        the girdle plane.
      - A horizontal basket rail (or trellis cross-members) if requested.
      - For cathedral style: a vertical arch connecting alternate prongs to
        a lower shank seat.

    Returned dict is appended to the .feature JSON tree.
    """
    # Nominal head outer diameter: stone + one prong wire on each side.
    head_outer_diameter = stone_diameter + 2 * prong_wire_diameter

    # Seat ledge: the bearing surface the girdle of the stone rests on.
    # A 15° (default) inward chamfer holds the stone at seat_angle_deg.
    seat_depth = stone_diameter * math.tan(math.radians(seat_angle_deg)) * 0.1

    return {
        "id": node_id,
        "op": "jewelry_prong_head",
        "stone_diameter": stone_diameter,
        "prong_count": prong_count,
        "prong_wire_diameter": prong_wire_diameter,
        "prong_height": prong_height,
        "head_style": head_style,
        "basket_rail_count": basket_rail_count,
        "seat_angle_deg": seat_angle_deg,
        # Derived geometry hints consumed by the worker (avoids re-computing in JS).
        "_head_outer_diameter": round(head_outer_diameter, 4),
        "_seat_depth": round(seat_depth, 6),
    }


def build_bezel_node(
    node_id: str,
    stone_diameter: float,
    wall_thickness: float,
    bezel_height: float,
    bearing_ledge_height: float,
    bezel_style: str,
    partial_opening_deg: float,
    taper_angle_deg: float,
) -> dict:
    """
    Compute the bezel-setting node spec.

    The worker's opJewelryBezel builds:
      - An outer cylinder (or partial arc) of diameter = stone_diameter + 2*wall.
      - An inner bore to accept the stone (stone_diameter).
      - A horizontal bearing ledge at bearing_ledge_height from the base.
      - For 'partial': a gap of partial_opening_deg cut from the front face
        (common for east-west set ovals and marquise stones).
      - For 'tapered'/'collet': the outer wall inclines inward at taper_angle_deg.

    Partial openings must be in [1, 359] degrees.
    """
    inner_diameter = stone_diameter
    outer_diameter = stone_diameter + 2 * wall_thickness

    return {
        "id": node_id,
        "op": "jewelry_bezel",
        "stone_diameter": stone_diameter,
        "wall_thickness": wall_thickness,
        "bezel_height": bezel_height,
        "bearing_ledge_height": bearing_ledge_height,
        "bezel_style": bezel_style,
        "partial_opening_deg": partial_opening_deg,
        "taper_angle_deg": taper_angle_deg,
        # Worker hints.
        "_inner_diameter": round(inner_diameter, 4),
        "_outer_diameter": round(outer_diameter, 4),
    }


def build_channel_node(
    node_id: str,
    stone_diameter: float,
    stone_count: int,
    stone_spacing: float,
    rail_height: float,
    rail_thickness: float,
    floor_thickness: float,
) -> dict:
    """
    Compute the channel-setting node spec.

    The worker's opJewelryChannel builds two parallel rails separated by
    stone_diameter + rail clearance, with a floor connecting them underneath.
    The channel runs along the X-axis with stones evenly spaced at
    stone_spacing intervals.

    Returns the channel solid node.  The per-stone seat positions are
    available from `seat_positions` in the worker's evaluate result payload
    so a downstream gem-seat op can cut each seat.

    Channel total length = stone_count * stone_spacing.
    """
    channel_length = stone_count * stone_spacing
    # Rail separation: inner face-to-face = stone_diameter (no extra clearance;
    # the worker adds a configurable clearance of 0.05 mm per rail).
    rail_separation = stone_diameter

    return {
        "id": node_id,
        "op": "jewelry_channel",
        "stone_diameter": stone_diameter,
        "stone_count": stone_count,
        "stone_spacing": stone_spacing,
        "rail_height": rail_height,
        "rail_thickness": rail_thickness,
        "floor_thickness": floor_thickness,
        # Worker hints.
        "_channel_length": round(channel_length, 4),
        "_rail_separation": round(rail_separation, 4),
    }


def build_pave_array_node(
    node_id: str,
    region_width: float,
    region_height: float,
    stone_diameter: float,
    stone_spacing: float,
    edge_margin: float,
    surface_normal: list,
    surface_origin: list,
) -> dict:
    """
    Compute the pavé placement array node spec.

    The worker's opJewelryPave projects a rectangular grid onto the target
    surface region and returns a list of placement transforms (4x4 matrix,
    column-major) in the evaluate result.  Each transform positions and
    orients a stone seat so a downstream boolean can cut each seat.

    Grid algorithm (pure Python, replicated in worker for validation):
      1. Effective usable area = (region_width - 2*edge_margin) x
                                 (region_height - 2*edge_margin).
      2. Column pitch = stone_diameter + stone_spacing (centre-to-centre).
      3. Row pitch = column_pitch * sqrt(3)/2 for hex offset, or equal to
         column_pitch for square grid.  This uses square grid (simpler, matches
         calibrated rows on straight channels).
      4. Offset every other row by half a column pitch (hex-offset layout for
         tighter packing density and bead appearance).
      5. Filter any placement whose edge circle would fall outside the usable
         boundary by > 0.01 mm.

    Returns:
      - `placement_count`: integer number of stone positions.
      - `placements`: list of {u, v, row, col} dicts.  The worker converts
        these to full 4x4 world-space transforms and posts them in the result
        payload.  u,v are fractional coordinates [0,1] across the region.
    """
    placements = _compute_pave_grid(
        region_width=region_width,
        region_height=region_height,
        stone_diameter=stone_diameter,
        stone_spacing=stone_spacing,
        edge_margin=edge_margin,
    )

    return {
        "id": node_id,
        "op": "jewelry_pave",
        "region_width": region_width,
        "region_height": region_height,
        "stone_diameter": stone_diameter,
        "stone_spacing": stone_spacing,
        "edge_margin": edge_margin,
        "surface_normal": surface_normal,
        "surface_origin": surface_origin,
        # Placement grid (u,v coords) pre-computed in Python for tests.
        "placements": placements,
        "_placement_count": len(placements),
    }


def _compute_pave_grid(
    region_width: float,
    region_height: float,
    stone_diameter: float,
    stone_spacing: float,
    edge_margin: float,
) -> list:
    """
    Returns list of {u, v, row, col} dicts for all stone positions that fit
    inside the pavé region (with edge_margin clearance).

    u = normalised X position [0, 1] across region_width.
    v = normalised Y position [0, 1] across region_height.

    Uses hex-offset row layout: odd rows are shifted by half a column pitch.
    """
    usable_w = region_width - 2 * edge_margin
    usable_h = region_height - 2 * edge_margin

    if usable_w <= 0 or usable_h <= 0:
        return []

    pitch = stone_diameter + stone_spacing
    if pitch <= 0:
        return []

    # Number of columns and rows in the hex-offset grid.
    n_cols = max(1, int(math.floor(usable_w / pitch)))
    n_rows = max(1, int(math.floor(usable_h / pitch)))

    placements = []
    for row in range(n_rows):
        for col in range(n_cols):
            x = edge_margin + col * pitch + (pitch / 2 if row % 2 == 1 else 0)
            y = edge_margin + row * pitch

            # Half-pitch horizontal offset on odd rows may push the rightmost
            # stone past the usable boundary — skip it.
            if x + stone_diameter / 2 > region_width - edge_margin + 1e-9:
                continue
            if y + stone_diameter / 2 > region_height - edge_margin + 1e-9:
                continue

            u = x / region_width
            v = y / region_height
            placements.append({"u": round(u, 6), "v": round(v, 6), "row": row, "col": col})

    return placements


# ---------------------------------------------------------------------------
# LLM Tool: jewelry_create_prong_head
# ---------------------------------------------------------------------------

jewelry_prong_head_spec = ToolSpec(
    name="jewelry_create_prong_head",
    description=(
        "Append a `jewelry_prong_head` node to a `.feature` file. "
        "Generates a parametric prong-head setting (4-prong, 6-prong, basket, "
        "trellis, or cathedral style) sized to accept a stone of `stone_diameter`. "
        "The head solid includes a bearing ledge at `seat_angle_deg` to seat the "
        "gemstone girdle, `prong_count` round prong wires of `prong_wire_diameter`, "
        "and a basket rail (if `head_style` is 'basket' or 'trellis'). "
        "Output: a TopoDS_Solid head body ready for boolean fuse onto a shank."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm (e.g. 6.5 for a 1 ct round brilliant).",
            },
            "prong_count": {
                "type": "integer",
                "enum": [4, 6],
                "description": "Number of prongs. 4 (square set) or 6 (classic Tiffany).",
            },
            "prong_wire_diameter": {
                "type": "number",
                "description": "Round-wire prong diameter in mm. Typical range 0.8–1.5 mm.",
            },
            "prong_height": {
                "type": "number",
                "description": "Height the prong extends above the stone's girdle plane in mm.",
            },
            "head_style": {
                "type": "string",
                "enum": ["standard", "basket", "trellis", "cathedral"],
                "description": (
                    "Head geometry style. "
                    "'standard': plain prongs, no connecting rail. "
                    "'basket': horizontal rail band connecting alternate prong bases. "
                    "'trellis': cross-diagonal rail between adjacent prongs. "
                    "'cathedral': arch ribs rising from prong base to a lower shank seat."
                ),
            },
            "basket_rail_count": {
                "type": "integer",
                "description": "Number of horizontal basket rails (default 1). Ignored for 'standard'.",
            },
            "seat_angle_deg": {
                "type": "number",
                "description": "Angle (degrees) of the bearing ledge chamfer. Default 15°.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "prong_count", "prong_wire_diameter", "prong_height"],
    },
)


@register(jewelry_prong_head_spec, write=True)
async def run_jewelry_create_prong_head(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    prong_count = a.get("prong_count")
    prong_wire_diameter = a.get("prong_wire_diameter")
    prong_height = a.get("prong_height")
    head_style = a.get("head_style", "standard")
    basket_rail_count = a.get("basket_rail_count", 1)
    seat_angle_deg = a.get("seat_angle_deg", 15.0)
    node_id = a.get("id", "").strip()

    # Validate required fields.
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("prong_wire_diameter", prong_wire_diameter),
        ("prong_height", prong_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    if prong_count not in _VALID_PRONG_COUNTS:
        return err_payload(
            f"prong_count must be 4 or 6; got {prong_count!r}", "BAD_ARGS"
        )

    head_style_clean = (head_style or "standard").strip().lower()
    if head_style_clean not in _VALID_HEAD_STYLES:
        return err_payload(
            f"head_style must be one of {sorted(_VALID_HEAD_STYLES)}; got {head_style!r}",
            "BAD_ARGS",
        )

    err = _non_negative_int("basket_rail_count", basket_rail_count)
    if err:
        return err_payload(err, "BAD_ARGS")

    seat_err = _positive("seat_angle_deg", seat_angle_deg)
    if seat_err:
        return err_payload(seat_err, "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_prong_head")

    node = build_prong_head_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        prong_count=int(prong_count),
        prong_wire_diameter=float(prong_wire_diameter),
        prong_height=float(prong_height),
        head_style=head_style_clean,
        basket_rail_count=int(basket_rail_count),
        seat_angle_deg=float(seat_angle_deg),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_prong_head",
        "prong_count": int(prong_count),
        "head_style": head_style_clean,
        "stone_diameter": float(stone_diameter),
    })


# ---------------------------------------------------------------------------
# LLM Tool: jewelry_create_bezel
# ---------------------------------------------------------------------------

jewelry_bezel_spec = ToolSpec(
    name="jewelry_create_bezel",
    description=(
        "Append a `jewelry_bezel` node to a `.feature` file. "
        "Generates a parametric bezel setting — a full or partial metal collar "
        "surrounding a gemstone, with a horizontal bearing ledge on which the "
        "stone's girdle seats. "
        "Styles: 'full' (360° collar), 'partial' (gap of `partial_opening_deg`), "
        "'collet' (tube bezel, minimal wall), 'tapered' (outer wall angled inward "
        "at `taper_angle_deg` for a rub-over look). "
        "Output: a TopoDS_Solid bezel body ready for boolean fuse onto a shank."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "wall_thickness": {
                "type": "number",
                "description": "Bezel wall thickness in mm. Typical: 0.3–0.8 mm.",
            },
            "bezel_height": {
                "type": "number",
                "description": "Total height of the bezel collar in mm (from base to top).",
            },
            "bearing_ledge_height": {
                "type": "number",
                "description": (
                    "Height of the bearing ledge from the base. "
                    "The stone girdle rests here. Must be < bezel_height."
                ),
            },
            "bezel_style": {
                "type": "string",
                "enum": ["full", "partial", "collet", "tapered"],
                "description": "Bezel geometry style.",
            },
            "partial_opening_deg": {
                "type": "number",
                "description": "Gap angle (degrees) for 'partial' style. Range [1, 359]. Ignored for 'full'/'collet'/'tapered'.",
            },
            "taper_angle_deg": {
                "type": "number",
                "description": "Outer wall inward taper angle in degrees (0 = straight). Used for 'tapered'/'collet' styles.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "wall_thickness", "bezel_height", "bearing_ledge_height"],
    },
)


@register(jewelry_bezel_spec, write=True)
async def run_jewelry_create_bezel(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    wall_thickness = a.get("wall_thickness")
    bezel_height = a.get("bezel_height")
    bearing_ledge_height = a.get("bearing_ledge_height")
    bezel_style = a.get("bezel_style", "full")
    partial_opening_deg = a.get("partial_opening_deg", 60.0)
    taper_angle_deg = a.get("taper_angle_deg", 0.0)
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("wall_thickness", wall_thickness),
        ("bezel_height", bezel_height),
        ("bearing_ledge_height", bearing_ledge_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        bh = float(bezel_height)
        blh = float(bearing_ledge_height)
    except (TypeError, ValueError):
        return err_payload("bezel_height and bearing_ledge_height must be numbers", "BAD_ARGS")

    if blh >= bh:
        return err_payload(
            f"bearing_ledge_height ({blh}) must be less than bezel_height ({bh})",
            "BAD_ARGS",
        )

    bezel_style_clean = (bezel_style or "full").strip().lower()
    if bezel_style_clean not in _VALID_BEZEL_STYLES:
        return err_payload(
            f"bezel_style must be one of {sorted(_VALID_BEZEL_STYLES)}; got {bezel_style!r}",
            "BAD_ARGS",
        )

    try:
        pod = float(partial_opening_deg)
    except (TypeError, ValueError):
        pod = 60.0

    if bezel_style_clean == "partial" and not (1.0 <= pod <= 359.0):
        return err_payload(
            f"partial_opening_deg must be in [1, 359] for partial style; got {pod}",
            "BAD_ARGS",
        )

    try:
        tap = float(taper_angle_deg)
    except (TypeError, ValueError):
        tap = 0.0

    if tap < 0:
        return err_payload(
            f"taper_angle_deg must be >= 0; got {tap}", "BAD_ARGS"
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_bezel")

    node = build_bezel_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        wall_thickness=float(wall_thickness),
        bezel_height=bh,
        bearing_ledge_height=blh,
        bezel_style=bezel_style_clean,
        partial_opening_deg=pod,
        taper_angle_deg=tap,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_bezel",
        "bezel_style": bezel_style_clean,
        "stone_diameter": float(stone_diameter),
    })


# ---------------------------------------------------------------------------
# LLM Tool: jewelry_create_channel
# ---------------------------------------------------------------------------

jewelry_channel_spec = ToolSpec(
    name="jewelry_create_channel",
    description=(
        "Append a `jewelry_channel` node to a `.feature` file. "
        "Generates a parametric channel setting — two parallel metal rails "
        "with a floor, sized to hold a row of `stone_count` calibrated stones "
        "of `stone_diameter` at `stone_spacing` centre-to-centre intervals. "
        "The channel runs along the X-axis. The worker's evaluate result includes "
        "`seat_positions` — a list of per-stone XYZ positions relative to the "
        "channel's local origin — so a downstream gem-seat op can cut each seat. "
        "Output: a TopoDS_Solid channel body."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Stone girdle diameter (width) in mm.",
            },
            "stone_count": {
                "type": "integer",
                "description": "Number of stones in the channel row. Must be >= 1.",
            },
            "stone_spacing": {
                "type": "number",
                "description": "Centre-to-centre spacing between adjacent stones in mm. Must be > stone_diameter.",
            },
            "rail_height": {
                "type": "number",
                "description": "Height of the channel rails above the stone seat in mm.",
            },
            "rail_thickness": {
                "type": "number",
                "description": "Thickness of each rail wall in mm.",
            },
            "floor_thickness": {
                "type": "number",
                "description": "Thickness of the channel floor in mm.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "stone_count", "stone_spacing", "rail_height", "rail_thickness", "floor_thickness"],
    },
)


@register(jewelry_channel_spec, write=True)
async def run_jewelry_create_channel(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    stone_count = a.get("stone_count")
    stone_spacing = a.get("stone_spacing")
    rail_height = a.get("rail_height")
    rail_thickness = a.get("rail_thickness")
    floor_thickness = a.get("floor_thickness")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("stone_spacing", stone_spacing),
        ("rail_height", rail_height),
        ("rail_thickness", rail_thickness),
        ("floor_thickness", floor_thickness),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        sc = int(stone_count)
    except (TypeError, ValueError):
        return err_payload("stone_count must be an integer", "BAD_ARGS")
    if sc < 1:
        return err_payload(f"stone_count must be >= 1; got {sc}", "BAD_ARGS")

    try:
        sd = float(stone_diameter)
        ss = float(stone_spacing)
    except (TypeError, ValueError):
        return err_payload("stone_diameter and stone_spacing must be numbers", "BAD_ARGS")

    if ss <= sd:
        return err_payload(
            f"stone_spacing ({ss}) must be greater than stone_diameter ({sd}) to prevent overlap",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_channel")

    node = build_channel_node(
        node_id=node_id,
        stone_diameter=sd,
        stone_count=sc,
        stone_spacing=ss,
        rail_height=float(rail_height),
        rail_thickness=float(rail_thickness),
        floor_thickness=float(floor_thickness),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_channel",
        "stone_count": sc,
        "channel_length": round(sc * ss, 4),
    })


# ---------------------------------------------------------------------------
# LLM Tool: jewelry_pave_array
# ---------------------------------------------------------------------------

jewelry_pave_spec = ToolSpec(
    name="jewelry_pave_array",
    description=(
        "Append a `jewelry_pave` node to a `.feature` file. "
        "Distributes stone placements across a rectangular target surface region "
        "using a hex-offset grid layout. Returns the array of placement transforms "
        "(u,v fractional coordinates on the region surface) so a downstream "
        "gem-seat op can cut individual stone seats. "
        "The operation does NOT cut seats itself — it only records the placement "
        "grid. Pair with a boolean-cut loop or a future gem_seat op to produce "
        "actual seats. "
        "Parameters control stone diameter, centre-to-centre spacing, and an "
        "edge margin that keeps the outermost stones' edges inside the region "
        "boundary. Odd rows are shifted by half a column pitch (hex offset) "
        "for tighter packing and the characteristic pavé bead appearance."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "region_width": {
                "type": "number",
                "description": "Width (X-extent) of the target region in mm.",
            },
            "region_height": {
                "type": "number",
                "description": "Height (Y-extent) of the target region in mm.",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Stone girdle diameter in mm.",
            },
            "stone_spacing": {
                "type": "number",
                "description": "Gap between adjacent stone edges in mm (centre-to-centre = stone_diameter + stone_spacing).",
            },
            "edge_margin": {
                "type": "number",
                "description": "Minimum margin from the region boundary to the outermost stone edge in mm.",
            },
            "surface_normal": {
                "type": "array",
                "items": {"type": "number"},
                "description": "World-space normal of the target surface plane [nx, ny, nz]. Default [0, 0, 1].",
            },
            "surface_origin": {
                "type": "array",
                "items": {"type": "number"},
                "description": "World-space origin of the region [x, y, z]. Default [0, 0, 0].",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "region_width", "region_height", "stone_diameter", "stone_spacing", "edge_margin"],
    },
)


@register(jewelry_pave_spec, write=True)
async def run_jewelry_pave_array(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    region_width = a.get("region_width")
    region_height = a.get("region_height")
    stone_diameter = a.get("stone_diameter")
    stone_spacing = a.get("stone_spacing")
    edge_margin = a.get("edge_margin")
    surface_normal = a.get("surface_normal", [0, 0, 1])
    surface_origin = a.get("surface_origin", [0, 0, 0])
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("region_width", region_width),
        ("region_height", region_height),
        ("stone_diameter", stone_diameter),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        ss = float(stone_spacing)
    except (TypeError, ValueError):
        return err_payload("stone_spacing must be a number", "BAD_ARGS")
    if ss < 0:
        return err_payload(f"stone_spacing must be >= 0; got {ss}", "BAD_ARGS")

    try:
        em = float(edge_margin)
    except (TypeError, ValueError):
        return err_payload("edge_margin must be a number", "BAD_ARGS")
    if em < 0:
        return err_payload(f"edge_margin must be >= 0; got {em}", "BAD_ARGS")

    # Validate surface_normal and surface_origin are 3-element lists.
    if not isinstance(surface_normal, list) or len(surface_normal) != 3:
        return err_payload("surface_normal must be a 3-element list [nx, ny, nz]", "BAD_ARGS")
    if not isinstance(surface_origin, list) or len(surface_origin) != 3:
        return err_payload("surface_origin must be a 3-element list [x, y, z]", "BAD_ARGS")

    try:
        sn = [float(v) for v in surface_normal]
        so = [float(v) for v in surface_origin]
    except (TypeError, ValueError):
        return err_payload("surface_normal and surface_origin elements must be numbers", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_pave")

    node = build_pave_array_node(
        node_id=node_id,
        region_width=float(region_width),
        region_height=float(region_height),
        stone_diameter=float(stone_diameter),
        stone_spacing=ss,
        edge_margin=em,
        surface_normal=sn,
        surface_origin=so,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    placement_count = node.get("_placement_count", 0)

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_pave",
        "placement_count": placement_count,
        "region_width": float(region_width),
        "region_height": float(region_height),
    })


# ---------------------------------------------------------------------------
# Tension setting
# ---------------------------------------------------------------------------

def build_tension_node(
    node_id: str,
    stone_diameter: float,
    band_thickness: float,
    gap: float,
    rail_width: float,
    rail_depth: float,
) -> dict:
    """
    Compute the tension-setting node spec.

    The worker's opJewelryTension builds:
      - Two band-end bodies of thickness `band_thickness`, each with a curved
        inward face that cradles the stone girdle.  The gap between the two
        facing surfaces equals `gap` (the stone is captured by spring tension).
      - A horizontal tension rail on each side of width `rail_width` and
        depth `rail_depth` that forms the bearing shelf gripping the girdle.

    The stone is NOT set into a drilled seat — it is suspended between the two
    opposing rails, held only by the metal's spring tension.

    Derived hints:
      _seat_radius  — radius of the bearing cradle = stone_diameter / 2.
      _band_spread  — total spread of the two band ends = stone_diameter + gap.
    """
    seat_radius = stone_diameter / 2.0
    band_spread = stone_diameter + gap

    return {
        "id": node_id,
        "op": "jewelry_tension",
        "stone_diameter": stone_diameter,
        "band_thickness": band_thickness,
        "gap": gap,
        "rail_width": rail_width,
        "rail_depth": rail_depth,
        "_seat_radius": round(seat_radius, 4),
        "_band_spread": round(band_spread, 4),
    }


jewelry_tension_spec = ToolSpec(
    name="jewelry_create_tension",
    description=(
        "Append a `jewelry_tension` node to a `.feature` file. "
        "Generates a tension setting where the stone is held purely by the "
        "spring pressure of two opposing band ends. "
        "The stone floats in a gap between the band ends; each end has an "
        "inward-curved bearing rail that grips the stone's girdle. "
        "Output: a node spec consumed by the OCCT worker's opJewelryTension "
        "handler to produce two TopoDS_Solid band-end bodies."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "band_thickness": {
                "type": "number",
                "description": "Thickness of the band metal at the setting point in mm (typical 2.0–4.0).",
            },
            "gap": {
                "type": "number",
                "description": (
                    "Gap between the two band-end faces in mm. "
                    "Must be < stone_diameter so the stone is retained."
                ),
            },
            "rail_width": {
                "type": "number",
                "description": "Width of the bearing rail that grips the girdle in mm (typical 0.3–0.8).",
            },
            "rail_depth": {
                "type": "number",
                "description": "Depth of the bearing rail notch in mm (typical 0.2–0.5).",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "band_thickness", "gap", "rail_width", "rail_depth"],
    },
)


@register(jewelry_tension_spec, write=True)
async def run_jewelry_create_tension(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    band_thickness = a.get("band_thickness")
    gap = a.get("gap")
    rail_width = a.get("rail_width")
    rail_depth = a.get("rail_depth")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("band_thickness", band_thickness),
        ("gap", gap),
        ("rail_width", rail_width),
        ("rail_depth", rail_depth),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        sd = float(stone_diameter)
        gp = float(gap)
    except (TypeError, ValueError):
        return err_payload("stone_diameter and gap must be numbers", "BAD_ARGS")

    if gp >= sd:
        return err_payload(
            f"gap ({gp}) must be less than stone_diameter ({sd}) so the stone is retained",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_tension")

    node = build_tension_node(
        node_id=node_id,
        stone_diameter=sd,
        band_thickness=float(band_thickness),
        gap=gp,
        rail_width=float(rail_width),
        rail_depth=float(rail_depth),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_tension",
        "stone_diameter": sd,
        "gap": gp,
        "_band_spread": node["_band_spread"],
    })


# ---------------------------------------------------------------------------
# Flush / gypsy setting
# ---------------------------------------------------------------------------

def build_flush_node(
    node_id: str,
    stone_diameter: float,
    seat_depth: float,
    bevel_width: float,
    bevel_angle_deg: float,
) -> dict:
    """
    Compute the flush-setting node spec.

    The worker's opJewelryFlush builds a drilled cylindrical seat of diameter
    `stone_diameter` and depth `seat_depth` sunk into the metal surface.  A
    chamfer of width `bevel_width` at `bevel_angle_deg` trims the opening edge
    so that the stone's crown is flush with or just proud of the metal.

    Derived hints:
      _seat_volume_approx  — π r² h (mm³) for material-removal estimate.
      _opening_diameter    — stone_diameter + 2 * bevel_width * tan(bevel_angle).
    """
    r = stone_diameter / 2.0
    seat_volume = math.pi * r * r * seat_depth
    opening_diameter = stone_diameter + 2.0 * bevel_width * math.tan(
        math.radians(bevel_angle_deg)
    )

    return {
        "id": node_id,
        "op": "jewelry_flush",
        "stone_diameter": stone_diameter,
        "seat_depth": seat_depth,
        "bevel_width": bevel_width,
        "bevel_angle_deg": bevel_angle_deg,
        "_seat_volume_approx": round(seat_volume, 4),
        "_opening_diameter": round(opening_diameter, 4),
    }


jewelry_flush_spec = ToolSpec(
    name="jewelry_create_flush",
    description=(
        "Append a `jewelry_flush` node to a `.feature` file. "
        "Generates a flush (gypsy) setting where the stone is set into a "
        "drilled seat so its table sits level with — or just proud of — the "
        "surrounding metal surface. "
        "The worker's opJewelryFlush handler drills a cylindrical pocket of "
        "`stone_diameter` × `seat_depth` and adds a chamfered opening edge "
        "(bevel) to ease the stone in and catch light. "
        "Output: a boolean-cut node spec. Pair with the parent metal body "
        "using a `feature_boolean` cut."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "seat_depth": {
                "type": "number",
                "description": "Depth of the drilled seat in mm (typically 60–80% of stone depth).",
            },
            "bevel_width": {
                "type": "number",
                "description": "Width of the opening bevel/chamfer in mm (typical 0.1–0.3).",
            },
            "bevel_angle_deg": {
                "type": "number",
                "description": "Angle of the bevel chamfer in degrees (typical 30–60°).",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "seat_depth", "bevel_width", "bevel_angle_deg"],
    },
)


@register(jewelry_flush_spec, write=True)
async def run_jewelry_create_flush(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    seat_depth = a.get("seat_depth")
    bevel_width = a.get("bevel_width")
    bevel_angle_deg = a.get("bevel_angle_deg")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("seat_depth", seat_depth),
        ("bevel_width", bevel_width),
        ("bevel_angle_deg", bevel_angle_deg),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        ba = float(bevel_angle_deg)
    except (TypeError, ValueError):
        return err_payload("bevel_angle_deg must be a number", "BAD_ARGS")

    if ba >= 90.0:
        return err_payload(
            f"bevel_angle_deg must be < 90°; got {ba}", "BAD_ARGS"
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_flush")

    node = build_flush_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        seat_depth=float(seat_depth),
        bevel_width=float(bevel_width),
        bevel_angle_deg=ba,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_flush",
        "stone_diameter": float(stone_diameter),
        "_opening_diameter": node["_opening_diameter"],
    })


# ---------------------------------------------------------------------------
# Halo setting
# ---------------------------------------------------------------------------

def build_halo_node(
    node_id: str,
    center_diameter: float,
    halo_stone_size: float,
    halo_stone_count: int,
    halo_gap: float,
    halo_metal_width: float,
) -> dict:
    """
    Compute the halo-setting node spec.

    The worker's opJewelryHalo builds:
      - A center stone seat of diameter `center_diameter` (same as a prong head
        or bezel — the caller adds their preferred center setting separately).
      - A ring of `halo_stone_count` accent stones of diameter `halo_stone_size`
        placed evenly around the center stone, separated by `halo_gap` from
        the center stone edge.
      - A metal halo frame of width `halo_metal_width` around the accent ring.

    Derived hints:
      _halo_radius      — centre-to-centre radius of the accent stone ring.
      _halo_outer_diameter — outer extent of the halo frame.
      _accent_pitch_deg — angular pitch between adjacent accent stones.
    """
    # Radial centre of the halo accent stones.
    # Each accent stone sits gap + center_radius + accent_radius from the origin.
    halo_radius = center_diameter / 2.0 + halo_gap + halo_stone_size / 2.0
    halo_outer_diameter = 2.0 * (halo_radius + halo_stone_size / 2.0 + halo_metal_width)
    accent_pitch_deg = 360.0 / halo_stone_count if halo_stone_count > 0 else 0.0

    return {
        "id": node_id,
        "op": "jewelry_halo",
        "center_diameter": center_diameter,
        "halo_stone_size": halo_stone_size,
        "halo_stone_count": halo_stone_count,
        "halo_gap": halo_gap,
        "halo_metal_width": halo_metal_width,
        "_halo_radius": round(halo_radius, 4),
        "_halo_outer_diameter": round(halo_outer_diameter, 4),
        "_accent_pitch_deg": round(accent_pitch_deg, 4),
    }


jewelry_halo_spec = ToolSpec(
    name="jewelry_create_halo",
    description=(
        "Append a `jewelry_halo` node to a `.feature` file. "
        "Generates a halo setting — a ring of small accent/pavé stones "
        "surrounding a center stone seat. "
        "The `halo_stone_count` accent stones of `halo_stone_size` are placed "
        "evenly around the center stone at a radial distance of `halo_gap` from "
        "the center stone edge. A metal halo frame of `halo_metal_width` "
        "surrounds the accent ring. "
        "The center stone seat is NOT generated by this tool — add a "
        "`jewelry_create_prong_head` or `jewelry_create_bezel` node separately "
        "for the center stone. "
        "Output: node spec consumed by the OCCT worker's opJewelryHalo handler."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "center_diameter": {
                "type": "number",
                "description": "Girdle diameter of the center stone in mm.",
            },
            "halo_stone_size": {
                "type": "number",
                "description": "Diameter of each individual halo accent stone in mm (typical 1.0–1.8).",
            },
            "halo_stone_count": {
                "type": "integer",
                "description": "Number of accent stones in the halo ring (typical 14–32). Must be >= 3.",
            },
            "halo_gap": {
                "type": "number",
                "description": "Radial gap between the center stone edge and the nearest halo stone edge in mm (typical 0.1–0.3).",
            },
            "halo_metal_width": {
                "type": "number",
                "description": "Width of the metal frame surrounding the halo accent ring in mm (typical 0.3–0.6).",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "center_diameter", "halo_stone_size", "halo_stone_count", "halo_gap", "halo_metal_width"],
    },
)


@register(jewelry_halo_spec, write=True)
async def run_jewelry_create_halo(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    center_diameter = a.get("center_diameter")
    halo_stone_size = a.get("halo_stone_size")
    halo_stone_count = a.get("halo_stone_count")
    halo_gap = a.get("halo_gap")
    halo_metal_width = a.get("halo_metal_width")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("center_diameter", center_diameter),
        ("halo_stone_size", halo_stone_size),
        ("halo_gap", halo_gap),
        ("halo_metal_width", halo_metal_width),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        hsc = int(halo_stone_count)
    except (TypeError, ValueError):
        return err_payload("halo_stone_count must be an integer", "BAD_ARGS")
    if hsc < 3:
        return err_payload(
            f"halo_stone_count must be >= 3; got {hsc}", "BAD_ARGS"
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_halo")

    node = build_halo_node(
        node_id=node_id,
        center_diameter=float(center_diameter),
        halo_stone_size=float(halo_stone_size),
        halo_stone_count=hsc,
        halo_gap=float(halo_gap),
        halo_metal_width=float(halo_metal_width),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_halo",
        "center_diameter": float(center_diameter),
        "halo_stone_count": hsc,
        "_halo_outer_diameter": node["_halo_outer_diameter"],
    })


# ---------------------------------------------------------------------------
# Three-stone setting
# ---------------------------------------------------------------------------

def build_three_stone_node(
    node_id: str,
    center_diameter: float,
    side_diameter: float,
    stone_spacing: float,
    base_height: float,
) -> dict:
    """
    Compute the three-stone setting node spec.

    The worker's opJewelryThreeStone builds:
      - A center stone seat of diameter `center_diameter`.
      - Two side stone seats of diameter `side_diameter`, each offset along
        the X-axis by (center_diameter / 2 + stone_spacing + side_diameter / 2).
      - A shared base/gallery of height `base_height` connecting all three seats.

    Derived hints:
      _side_offset_x — X-axis offset of each side stone centre from the origin.
      _total_width   — overall width of the three-stone cluster.
    """
    side_offset_x = center_diameter / 2.0 + stone_spacing + side_diameter / 2.0
    total_width = 2.0 * side_offset_x + side_diameter

    return {
        "id": node_id,
        "op": "jewelry_three_stone",
        "center_diameter": center_diameter,
        "side_diameter": side_diameter,
        "stone_spacing": stone_spacing,
        "base_height": base_height,
        "_side_offset_x": round(side_offset_x, 4),
        "_total_width": round(total_width, 4),
    }


jewelry_three_stone_spec = ToolSpec(
    name="jewelry_create_three_stone",
    description=(
        "Append a `jewelry_three_stone` node to a `.feature` file. "
        "Generates a three-stone setting — a center stone flanked by two "
        "graduated side stones on a shared base/gallery. "
        "The center stone seat has diameter `center_diameter`; the two side "
        "stone seats have diameter `side_diameter` (typically 60–75% of center). "
        "All three seats share a common base of height `base_height`. "
        "Output: node spec consumed by the OCCT worker's opJewelryThreeStone "
        "handler to produce a combined base solid with three seat positions "
        "posted in the evaluate result."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "center_diameter": {
                "type": "number",
                "description": "Girdle diameter of the center stone in mm.",
            },
            "side_diameter": {
                "type": "number",
                "description": "Girdle diameter of each side stone in mm. Typically 60–75% of center_diameter.",
            },
            "stone_spacing": {
                "type": "number",
                "description": "Gap between adjacent stone edges in mm (typical 0.1–0.3).",
            },
            "base_height": {
                "type": "number",
                "description": "Height of the shared gallery base in mm.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "center_diameter", "side_diameter", "stone_spacing", "base_height"],
    },
)


@register(jewelry_three_stone_spec, write=True)
async def run_jewelry_create_three_stone(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    center_diameter = a.get("center_diameter")
    side_diameter = a.get("side_diameter")
    stone_spacing = a.get("stone_spacing")
    base_height = a.get("base_height")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("center_diameter", center_diameter),
        ("side_diameter", side_diameter),
        ("stone_spacing", stone_spacing),
        ("base_height", base_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_three_stone")

    node = build_three_stone_node(
        node_id=node_id,
        center_diameter=float(center_diameter),
        side_diameter=float(side_diameter),
        stone_spacing=float(stone_spacing),
        base_height=float(base_height),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_three_stone",
        "center_diameter": float(center_diameter),
        "side_diameter": float(side_diameter),
        "_total_width": node["_total_width"],
    })


# ---------------------------------------------------------------------------
# Cluster setting
# ---------------------------------------------------------------------------

def _compute_cluster_positions(
    cluster_diameter: float,
    stone_size: float,
    stone_count: int,
) -> list:
    """
    Distribute `stone_count` stones of `stone_size` in a circular cluster of
    overall diameter `cluster_diameter`.

    Uses a simple annular ring layout: all stones are placed on a circle of
    radius = (cluster_diameter / 2) - (stone_size / 2).  When stone_count == 1
    the single stone is placed at the origin.

    Returns a list of {"x": float, "y": float, "angle_deg": float} dicts
    representing stone centre positions in the cluster's local XY plane.
    """
    if stone_count == 1:
        return [{"x": 0.0, "y": 0.0, "angle_deg": 0.0}]

    placement_radius = cluster_diameter / 2.0 - stone_size / 2.0
    if placement_radius <= 0:
        # Stones too large for the cluster diameter — pack all at origin.
        placement_radius = 0.0

    positions = []
    for i in range(stone_count):
        angle_deg = 360.0 * i / stone_count
        angle_rad = math.radians(angle_deg)
        x = placement_radius * math.cos(angle_rad)
        y = placement_radius * math.sin(angle_rad)
        positions.append({
            "x": round(x, 4),
            "y": round(y, 4),
            "angle_deg": round(angle_deg, 4),
        })
    return positions


def build_cluster_node(
    node_id: str,
    cluster_diameter: float,
    stone_size: float,
    stone_count: int,
    dome_height: float,
) -> dict:
    """
    Compute the cluster-setting node spec.

    The worker's opJewelryCluster builds:
      - A domed base (shallow spherical cap) of diameter `cluster_diameter`
        and height `dome_height`, representing the metal platform.
      - `stone_count` stone seats of diameter `stone_size` distributed across
        the dome surface according to `positions`.

    Derived hints:
      _placement_radius  — radial distance of stone centres from the cluster axis.
      positions          — list of per-stone {x, y, angle_deg} dicts.
    """
    placement_radius = max(0.0, cluster_diameter / 2.0 - stone_size / 2.0)
    positions = _compute_cluster_positions(
        cluster_diameter=cluster_diameter,
        stone_size=stone_size,
        stone_count=stone_count,
    )

    return {
        "id": node_id,
        "op": "jewelry_cluster",
        "cluster_diameter": cluster_diameter,
        "stone_size": stone_size,
        "stone_count": stone_count,
        "dome_height": dome_height,
        "positions": positions,
        "_placement_radius": round(placement_radius, 4),
        "_actual_count": len(positions),
    }


jewelry_cluster_spec = ToolSpec(
    name="jewelry_create_cluster",
    description=(
        "Append a `jewelry_cluster` node to a `.feature` file. "
        "Generates a cluster setting where `stone_count` small stones are "
        "grouped together on a domed base to read visually as one large stone. "
        "Stones of `stone_size` are arranged on a circular platform of "
        "`cluster_diameter`. The dome curvature is controlled by `dome_height` "
        "(the height of the domed base profile). "
        "Output: node spec consumed by the OCCT worker's opJewelryCluster "
        "handler. The evaluate result includes `seat_positions` — per-stone "
        "XYZ positions on the dome surface — for downstream seat-cutting."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "cluster_diameter": {
                "type": "number",
                "description": "Overall diameter of the cluster platform in mm.",
            },
            "stone_size": {
                "type": "number",
                "description": "Girdle diameter of each individual stone in the cluster in mm.",
            },
            "stone_count": {
                "type": "integer",
                "description": "Number of stones in the cluster. Must be >= 1.",
            },
            "dome_height": {
                "type": "number",
                "description": "Height of the dome profile above the base plane in mm. Use 0.0 for a flat cluster.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "cluster_diameter", "stone_size", "stone_count", "dome_height"],
    },
)


@register(jewelry_cluster_spec, write=True)
async def run_jewelry_create_cluster(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    cluster_diameter = a.get("cluster_diameter")
    stone_size = a.get("stone_size")
    stone_count = a.get("stone_count")
    dome_height = a.get("dome_height")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("cluster_diameter", cluster_diameter),
        ("stone_size", stone_size),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    # dome_height may be 0.0 (flat cluster) — only check it's a non-negative number.
    try:
        dh = float(dome_height)
    except (TypeError, ValueError):
        return err_payload("dome_height must be a number", "BAD_ARGS")
    if dh < 0:
        return err_payload(f"dome_height must be >= 0; got {dh}", "BAD_ARGS")

    try:
        sc = int(stone_count)
    except (TypeError, ValueError):
        return err_payload("stone_count must be an integer", "BAD_ARGS")
    if sc < 1:
        return err_payload(f"stone_count must be >= 1; got {sc}", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_cluster")

    node = build_cluster_node(
        node_id=node_id,
        cluster_diameter=float(cluster_diameter),
        stone_size=float(stone_size),
        stone_count=sc,
        dome_height=dh,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_cluster",
        "stone_count": sc,
        "cluster_diameter": float(cluster_diameter),
        "_placement_radius": node["_placement_radius"],
    })


# ---------------------------------------------------------------------------
# Bar setting
# ---------------------------------------------------------------------------

_VALID_BAR_LAYOUTS = {"linear", "arc"}


def build_bar_node(
    node_id: str,
    stone_diameter: float,
    bar_width: float,
    bar_height: float,
    stone_count: int,
    pitch: float,
) -> dict:
    """
    Compute the bar-setting node spec.

    The worker's opJewelryBar builds:
      - `stone_count` stone seats of diameter `stone_diameter` spaced at
        `pitch` centre-to-centre along the X-axis.
      - Two parallel metal bars of width `bar_width` and height `bar_height`
        running along either side of the stone row (no prongs between stones).
        The bars grip each stone's girdle at the sides; the stone faces remain
        fully exposed.

    Derived hints:
      _bar_length   — total length of each bar = stone_count * pitch.
      _bar_separation — inner face-to-face separation = stone_diameter (bars
                         just clear the stone girdle; the worker adds 0.05 mm
                         per side for fit clearance).
    """
    bar_length = stone_count * pitch
    bar_separation = stone_diameter

    return {
        "id": node_id,
        "op": "jewelry_bar",
        "stone_diameter": stone_diameter,
        "bar_width": bar_width,
        "bar_height": bar_height,
        "stone_count": stone_count,
        "pitch": pitch,
        "_bar_length": round(bar_length, 4),
        "_bar_separation": round(bar_separation, 4),
    }


jewelry_bar_spec = ToolSpec(
    name="jewelry_create_bar",
    description=(
        "Append a `jewelry_bar` node to a `.feature` file. "
        "Generates a bar setting — two parallel metal bars running along either "
        "side of a row of `stone_count` calibrated stones of `stone_diameter`, "
        "spaced at `pitch` centre-to-centre. "
        "Unlike a channel setting there are NO prongs between stones: each stone "
        "is gripped along its full girdle by the bars alone, creating a clean "
        "uninterrupted look popular in men's bands and eternity rings. "
        "The bars have cross-section `bar_width` × `bar_height`. "
        "Constraint: pitch must be greater than stone_diameter. "
        "Output: a TopoDS_Solid pair of bars with stone seat cutouts."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of each stone in mm.",
            },
            "bar_width": {
                "type": "number",
                "description": "Width of each metal bar in mm (typical 0.4–1.0).",
            },
            "bar_height": {
                "type": "number",
                "description": "Height of each metal bar above the stone seat in mm (typical 0.5–1.2).",
            },
            "stone_count": {
                "type": "integer",
                "description": "Number of stones in the bar row. Must be >= 1.",
            },
            "pitch": {
                "type": "number",
                "description": (
                    "Centre-to-centre distance between adjacent stones in mm. "
                    "Must be > stone_diameter."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "bar_width", "bar_height", "stone_count", "pitch"],
    },
)


@register(jewelry_bar_spec, write=True)
async def run_jewelry_create_bar(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    bar_width = a.get("bar_width")
    bar_height = a.get("bar_height")
    stone_count = a.get("stone_count")
    pitch = a.get("pitch")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("bar_width", bar_width),
        ("bar_height", bar_height),
        ("pitch", pitch),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        sc = int(stone_count)
    except (TypeError, ValueError):
        return err_payload("stone_count must be an integer", "BAD_ARGS")
    if sc < 1:
        return err_payload(f"stone_count must be >= 1; got {sc}", "BAD_ARGS")

    try:
        sd = float(stone_diameter)
        pt = float(pitch)
    except (TypeError, ValueError):
        return err_payload("stone_diameter and pitch must be numbers", "BAD_ARGS")

    if pt <= sd:
        return err_payload(
            f"pitch ({pt}) must be greater than stone_diameter ({sd}) to prevent overlap",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_bar")

    node = build_bar_node(
        node_id=node_id,
        stone_diameter=sd,
        bar_width=float(bar_width),
        bar_height=float(bar_height),
        stone_count=sc,
        pitch=pt,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_bar",
        "stone_count": sc,
        "stone_diameter": sd,
        "_bar_length": node["_bar_length"],
    })


# ---------------------------------------------------------------------------
# Bead / grain setting
# ---------------------------------------------------------------------------

_VALID_BEAD_LAYOUTS = {"line", "grid"}


def build_bead_grain_node(
    node_id: str,
    stone_diameter: float,
    bead_count_per_stone: int,
    bead_diameter: float,
    field_layout: str,
) -> dict:
    """
    Compute the bead/grain-setting node spec.

    The worker's opJewelryBeadGrain builds:
      - A drilled stone seat of diameter `stone_diameter` sunk into the metal
        surface (similar to a flush seat).
      - `bead_count_per_stone` raised metal beads of diameter `bead_diameter`
        cut up from the surrounding surface and pushed over the stone's girdle
        to retain it.  Beads are spaced evenly around the stone.
      - For `field_layout='line'`: stones are arranged in a single row.
      - For `field_layout='grid'`: stones are arranged in a rectangular grid;
        pitch is derived from stone_diameter and bead geometry.

    Derived hints:
      _bead_pitch_deg   — angular pitch between adjacent beads around one stone.
      _bead_ring_radius — radius of the bead circle around the stone = stone_diameter/2.
    """
    bead_pitch_deg = 360.0 / bead_count_per_stone if bead_count_per_stone > 0 else 0.0
    bead_ring_radius = stone_diameter / 2.0

    return {
        "id": node_id,
        "op": "jewelry_bead_grain",
        "stone_diameter": stone_diameter,
        "bead_count_per_stone": bead_count_per_stone,
        "bead_diameter": bead_diameter,
        "field_layout": field_layout,
        "_bead_pitch_deg": round(bead_pitch_deg, 4),
        "_bead_ring_radius": round(bead_ring_radius, 4),
    }


jewelry_bead_grain_spec = ToolSpec(
    name="jewelry_create_bead_grain",
    description=(
        "Append a `jewelry_bead_grain` node to a `.feature` file. "
        "Generates a bead (grain) setting where each stone is held by small "
        "raised metal beads that are cut up from the surrounding metal surface "
        "and pushed over the stone's girdle. "
        "Parameters control the stone diameter, the number of beads per stone "
        "(`bead_count_per_stone`, minimum 2), the bead diameter, and the "
        "overall field layout (`line` for a single row or `grid` for a "
        "rectangular array). "
        "Output: node spec consumed by opJewelryBeadGrain. Combines with a "
        "gem-seat boolean cut for the stone pocket."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of each stone in mm.",
            },
            "bead_count_per_stone": {
                "type": "integer",
                "description": (
                    "Number of raised beads retaining each stone. Must be >= 2. "
                    "Typical values: 2 (tight inline), 3, 4."
                ),
            },
            "bead_diameter": {
                "type": "number",
                "description": "Diameter of each raised bead in mm (typical 0.3–0.8).",
            },
            "field_layout": {
                "type": "string",
                "enum": ["line", "grid"],
                "description": (
                    "'line' — single row of stones. "
                    "'grid' — rectangular array of stones."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "bead_count_per_stone", "bead_diameter", "field_layout"],
    },
)


@register(jewelry_bead_grain_spec, write=True)
async def run_jewelry_create_bead_grain(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    bead_count_per_stone = a.get("bead_count_per_stone")
    bead_diameter = a.get("bead_diameter")
    field_layout = a.get("field_layout", "line")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("bead_diameter", bead_diameter),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        bcp = int(bead_count_per_stone)
    except (TypeError, ValueError):
        return err_payload("bead_count_per_stone must be an integer", "BAD_ARGS")
    if bcp < 2:
        return err_payload(
            f"bead_count_per_stone must be >= 2; got {bcp}", "BAD_ARGS"
        )

    field_layout_clean = (field_layout or "line").strip().lower()
    if field_layout_clean not in _VALID_BEAD_LAYOUTS:
        return err_payload(
            f"field_layout must be one of {sorted(_VALID_BEAD_LAYOUTS)}; got {field_layout!r}",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_bead_grain")

    node = build_bead_grain_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        bead_count_per_stone=bcp,
        bead_diameter=float(bead_diameter),
        field_layout=field_layout_clean,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_bead_grain",
        "stone_diameter": float(stone_diameter),
        "bead_count_per_stone": bcp,
        "field_layout": field_layout_clean,
        "_bead_pitch_deg": node["_bead_pitch_deg"],
    })


# ---------------------------------------------------------------------------
# Gypsy-pavé / star setting
# ---------------------------------------------------------------------------

_STAR_RAY_MIN = 4


def build_gypsy_pave_node(
    node_id: str,
    stone_diameter: float,
    seat_depth: float,
    star_ray_count: int,
) -> dict:
    """
    Compute the gypsy-pavé (star setting) node spec.

    The worker's opJewelryGypsyPave builds:
      - A flush-set stone seat of diameter `stone_diameter` and depth
        `seat_depth` (the stone sits flush with the metal surface, as in a
        standard flush/gypsy setting).
      - `star_ray_count` bright-cut engraved rays radiating from the stone's
        girdle edge outward across the surrounding metal, creating a decorative
        star or sunburst pattern that catches light and visually enlarges the
        stone.

    This is also called a "star setting" or "bright-cut star" in the trade.

    Derived hints:
      _ray_pitch_deg — angular pitch between adjacent rays = 360 / star_ray_count.
      _seat_radius   — stone_diameter / 2.
    """
    ray_pitch_deg = 360.0 / star_ray_count if star_ray_count > 0 else 0.0
    seat_radius = stone_diameter / 2.0

    return {
        "id": node_id,
        "op": "jewelry_gypsy_pave",
        "stone_diameter": stone_diameter,
        "seat_depth": seat_depth,
        "star_ray_count": star_ray_count,
        "_ray_pitch_deg": round(ray_pitch_deg, 4),
        "_seat_radius": round(seat_radius, 4),
    }


jewelry_gypsy_pave_spec = ToolSpec(
    name="jewelry_create_gypsy_pave",
    description=(
        "Append a `jewelry_gypsy_pave` node to a `.feature` file. "
        "Generates a gypsy-pavé (star setting) — a flush-set stone with "
        "bright-cut engraved rays radiating outward from the stone's edge "
        "across the surrounding metal surface. "
        "The stone sits flush (its table level with the metal) and the "
        "`star_ray_count` V-cut rays create a decorative star or sunburst "
        "halo that catches light. Also called 'star setting' or 'bright-cut "
        "star'. Minimum ray count: 4. "
        "Output: node spec consumed by opJewelryGypsyPave."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "seat_depth": {
                "type": "number",
                "description": "Depth of the flush seat in mm (typically 60–80% of stone depth).",
            },
            "star_ray_count": {
                "type": "integer",
                "description": (
                    "Number of engraved star rays radiating from the stone. "
                    "Must be >= 4. Typical: 6, 8, 12."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "seat_depth", "star_ray_count"],
    },
)


@register(jewelry_gypsy_pave_spec, write=True)
async def run_jewelry_create_gypsy_pave(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    seat_depth = a.get("seat_depth")
    star_ray_count = a.get("star_ray_count")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("seat_depth", seat_depth),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        src = int(star_ray_count)
    except (TypeError, ValueError):
        return err_payload("star_ray_count must be an integer", "BAD_ARGS")
    if src < _STAR_RAY_MIN:
        return err_payload(
            f"star_ray_count must be >= {_STAR_RAY_MIN}; got {src}", "BAD_ARGS"
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_gypsy_pave")

    node = build_gypsy_pave_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        seat_depth=float(seat_depth),
        star_ray_count=src,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_gypsy_pave",
        "stone_diameter": float(stone_diameter),
        "star_ray_count": src,
        "_ray_pitch_deg": node["_ray_pitch_deg"],
    })


# ---------------------------------------------------------------------------
# Illusion / miracle-plate setting
# ---------------------------------------------------------------------------

_ILLUSION_FACET_MIN = 4


def build_illusion_node(
    node_id: str,
    stone_diameter: float,
    plate_diameter: float,
    facet_count: int,
) -> dict:
    """
    Compute the illusion-setting node spec.

    The worker's opJewelryIllusion builds:
      - A stone seat of diameter `stone_diameter` at the centre.
      - A polished metal "miracle plate" of diameter `plate_diameter`
        surrounding the stone.  The plate is faceted with `facet_count` flat
        mirror-polished faces arranged radially so they reflect light similarly
        to the stone's own facets, making the small stone appear larger.

    The plate_diameter must be > stone_diameter.

    Derived hints:
      _plate_wall_width — radial width of the plate surround =
                          (plate_diameter - stone_diameter) / 2.
      _facet_pitch_deg  — angular pitch between adjacent plate facets =
                          360 / facet_count.
    """
    plate_wall_width = (plate_diameter - stone_diameter) / 2.0
    facet_pitch_deg = 360.0 / facet_count if facet_count > 0 else 0.0

    return {
        "id": node_id,
        "op": "jewelry_illusion",
        "stone_diameter": stone_diameter,
        "plate_diameter": plate_diameter,
        "facet_count": facet_count,
        "_plate_wall_width": round(plate_wall_width, 4),
        "_facet_pitch_deg": round(facet_pitch_deg, 4),
    }


jewelry_illusion_spec = ToolSpec(
    name="jewelry_create_illusion",
    description=(
        "Append a `jewelry_illusion` node to a `.feature` file. "
        "Generates an illusion (miracle-plate) setting — a small stone set at "
        "the centre of a larger polished metal plate whose faceted surface "
        "reflects light like the stone itself, creating the visual illusion that "
        "the stone is the size of the plate. "
        "The plate (`plate_diameter`) must be larger than `stone_diameter`. "
        "The plate surface is divided into `facet_count` radial mirror-polished "
        "faces (minimum 4). "
        "Output: node spec consumed by opJewelryIllusion."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the actual stone in mm.",
            },
            "plate_diameter": {
                "type": "number",
                "description": (
                    "Outer diameter of the illusion plate in mm. "
                    "Must be > stone_diameter."
                ),
            },
            "facet_count": {
                "type": "integer",
                "description": (
                    "Number of radial mirror facets on the plate surround. "
                    "Must be >= 4. Typical: 8, 12, 16."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "plate_diameter", "facet_count"],
    },
)


@register(jewelry_illusion_spec, write=True)
async def run_jewelry_create_illusion(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    plate_diameter = a.get("plate_diameter")
    facet_count = a.get("facet_count")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("plate_diameter", plate_diameter),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        fc = int(facet_count)
    except (TypeError, ValueError):
        return err_payload("facet_count must be an integer", "BAD_ARGS")
    if fc < _ILLUSION_FACET_MIN:
        return err_payload(
            f"facet_count must be >= {_ILLUSION_FACET_MIN}; got {fc}", "BAD_ARGS"
        )

    try:
        sd = float(stone_diameter)
        pd = float(plate_diameter)
    except (TypeError, ValueError):
        return err_payload("stone_diameter and plate_diameter must be numbers", "BAD_ARGS")

    if pd <= sd:
        return err_payload(
            f"plate_diameter ({pd}) must be greater than stone_diameter ({sd})",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_illusion")

    node = build_illusion_node(
        node_id=node_id,
        stone_diameter=sd,
        plate_diameter=pd,
        facet_count=fc,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_illusion",
        "stone_diameter": sd,
        "plate_diameter": pd,
        "facet_count": fc,
        "_plate_wall_width": node["_plate_wall_width"],
    })


# ---------------------------------------------------------------------------
# Invisible setting
# ---------------------------------------------------------------------------

_INVISIBLE_ROWS_MIN = 1
_INVISIBLE_COLS_MIN = 1


def build_invisible_node(
    node_id: str,
    stone_size: float,
    rail_width: float,
    rail_height: float,
    grid_rows: int,
    grid_cols: int,
) -> dict:
    """
    Compute the invisible-setting node spec.

    The worker's opJewelryInvisible builds:
      - A hidden rail framework (a grid of crossed metal rails) sized for a
        `grid_rows` × `grid_cols` array of princess/square-cut stones of
        `stone_size`.  Rail cross-section is `rail_width` × `rail_height`.
      - Each stone has a grooved girdle that slides onto the rails; no metal
        is visible between adjacent stones from above (hence "invisible").
      - The evaluate result includes `seat_positions` — a list of {row, col,
        x, y} dicts for downstream boolean-cut stone pockets.

    Derived hints:
      _total_width  — overall X extent of the setting = grid_cols * stone_size.
      _total_height — overall Y extent = grid_rows * stone_size.
      _stone_count  — grid_rows * grid_cols.
    """
    total_width = grid_cols * stone_size
    total_height = grid_rows * stone_size
    stone_count = grid_rows * grid_cols

    # Build seat position grid in the local XY plane.
    seats = []
    for r in range(grid_rows):
        for c in range(grid_cols):
            x = c * stone_size + stone_size / 2.0
            y = r * stone_size + stone_size / 2.0
            seats.append({"row": r, "col": c, "x": round(x, 4), "y": round(y, 4)})

    return {
        "id": node_id,
        "op": "jewelry_invisible",
        "stone_size": stone_size,
        "rail_width": rail_width,
        "rail_height": rail_height,
        "grid_rows": grid_rows,
        "grid_cols": grid_cols,
        "seat_positions": seats,
        "_total_width": round(total_width, 4),
        "_total_height": round(total_height, 4),
        "_stone_count": stone_count,
    }


jewelry_invisible_spec = ToolSpec(
    name="jewelry_create_invisible",
    description=(
        "Append a `jewelry_invisible` node to a `.feature` file. "
        "Generates an invisible setting — a `grid_rows` × `grid_cols` array of "
        "princess (square) or calibrated stones held on a concealed rail "
        "framework with no visible metal between adjacent stones. "
        "Each stone's girdle has a groove that fits over the crossed rails; from "
        "above the stones appear as a continuous, metal-free surface. "
        "Rail geometry is defined by `rail_width` and `rail_height`. "
        "The evaluate result includes `seat_positions` for downstream boolean "
        "stone-pocket cutting. "
        "Output: node spec consumed by opJewelryInvisible."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_size": {
                "type": "number",
                "description": "Side length (diameter) of each square stone in mm.",
            },
            "rail_width": {
                "type": "number",
                "description": "Width of each hidden rail in mm (typical 0.2–0.5).",
            },
            "rail_height": {
                "type": "number",
                "description": "Height (thickness) of each rail in mm (typical 0.5–1.5).",
            },
            "grid_rows": {
                "type": "integer",
                "description": "Number of stone rows in the grid. Must be >= 1.",
            },
            "grid_cols": {
                "type": "integer",
                "description": "Number of stone columns in the grid. Must be >= 1.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_size", "rail_width", "rail_height", "grid_rows", "grid_cols"],
    },
)


@register(jewelry_invisible_spec, write=True)
async def run_jewelry_create_invisible(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_size = a.get("stone_size")
    rail_width = a.get("rail_width")
    rail_height = a.get("rail_height")
    grid_rows = a.get("grid_rows")
    grid_cols = a.get("grid_cols")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_size", stone_size),
        ("rail_width", rail_width),
        ("rail_height", rail_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        rows = int(grid_rows)
    except (TypeError, ValueError):
        return err_payload("grid_rows must be an integer", "BAD_ARGS")
    if rows < _INVISIBLE_ROWS_MIN:
        return err_payload(
            f"grid_rows must be >= {_INVISIBLE_ROWS_MIN}; got {rows}", "BAD_ARGS"
        )

    try:
        cols = int(grid_cols)
    except (TypeError, ValueError):
        return err_payload("grid_cols must be an integer", "BAD_ARGS")
    if cols < _INVISIBLE_COLS_MIN:
        return err_payload(
            f"grid_cols must be >= {_INVISIBLE_COLS_MIN}; got {cols}", "BAD_ARGS"
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_invisible")

    node = build_invisible_node(
        node_id=node_id,
        stone_size=float(stone_size),
        rail_width=float(rail_width),
        rail_height=float(rail_height),
        grid_rows=rows,
        grid_cols=cols,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_invisible",
        "stone_size": float(stone_size),
        "grid_rows": rows,
        "grid_cols": cols,
        "_stone_count": node["_stone_count"],
        "_total_width": node["_total_width"],
        "_total_height": node["_total_height"],
    })


# ===========================================================================
# PRONG / HEAD VARIANT LIBRARY
# ===========================================================================
#
# Six additional prong-wire variants: double_prong, claw_prong, v_prong,
# fishtail_prong, split_prong, decorative_prong.
# Each shares the same parametric core (stone_diameter, prong_count,
# wire_gauge, prong_height) and adds a variant-specific parameter.
# ---------------------------------------------------------------------------

_VALID_PRONG_VARIANTS = {
    "double_prong",
    "claw_prong",
    "v_prong",
    "fishtail_prong",
    "split_prong",
    "decorative_prong",
}

_VALID_DECORATIVE_PROFILES = {"round", "tapered", "filigree", "star", "leaf"}


def build_prong_variant_node(
    node_id: str,
    variant: str,
    stone_diameter: float,
    prong_count: int,
    wire_gauge: float,
    prong_height: float,
    *,
    # variant-specific optional param — meaning depends on variant
    variant_param: float = 0.0,
    variant_profile: str = "round",
) -> dict:
    """
    Compute a prong-variant node spec.

    Variants
    --------
    double_prong
        Two parallel wires of `wire_gauge` run side-by-side per prong
        position (doubles the grip area).  `variant_param` = gap between the
        two wires in mm (default 0.3 mm).

    claw_prong
        A single wire with a curved claw tip that hooks over the stone's
        girdle; provides maximum security.  `variant_param` = claw hook depth
        in mm (default 0.4 mm).

    v_prong
        A V-shaped prong with a sharp internal corner that cradles a pointed
        culet (marquise, pear, princess corners).  `variant_param` = half-
        angle of the V in degrees (default 45°).  Best used with 4-prong.

    fishtail_prong
        The prong tip is split into two curved tines that spread over the
        girdle like a fishtail; this is the most decorative option.
        `variant_param` = fishtail spread width in mm (default 0.8 mm).

    split_prong
        The prong is split through most of its height into two tines;
        common in bypass / two-tone rings.  `variant_param` = split start
        height above the bearing seat as a fraction of `prong_height`
        (default 0.5, i.e. split begins halfway up).

    decorative_prong
        A prong with a decorative cross-section profile.  `variant_param`
        is unused; instead `variant_profile` selects the profile:
        `round`, `tapered`, `filigree`, `star`, `leaf`.

    Derived hints
    -------------
    _head_outer_diameter — same formula as jewelry_prong_head:
                           stone_diameter + 2 * wire_gauge.
    _prong_pitch_deg     — angular pitch between adjacent prongs =
                           360 / prong_count.
    """
    head_outer_diameter = stone_diameter + 2.0 * wire_gauge
    prong_pitch_deg = 360.0 / prong_count if prong_count > 0 else 0.0

    return {
        "id": node_id,
        "op": "jewelry_prong_variant",
        "variant": variant,
        "stone_diameter": stone_diameter,
        "prong_count": prong_count,
        "wire_gauge": wire_gauge,
        "prong_height": prong_height,
        "variant_param": variant_param,
        "variant_profile": variant_profile,
        "_head_outer_diameter": round(head_outer_diameter, 4),
        "_prong_pitch_deg": round(prong_pitch_deg, 4),
    }


jewelry_prong_variant_spec = ToolSpec(
    name="jewelry_create_prong_variant",
    description=(
        "Append a `jewelry_prong_variant` node to a `.feature` file. "
        "Generates one of six specialised prong-wire variants (double, claw, "
        "V, fishtail, split, decorative) sized to the stone. "
        "All variants share `stone_diameter`, `prong_count`, `wire_gauge`, and "
        "`prong_height`; each adds a variant-specific parameter. "
        "\n\nVariants:\n"
        "- **`double_prong`** — two side-by-side wires per prong position. "
        "`variant_param` = gap between wires in mm (default 0.3).\n"
        "- **`claw_prong`** — curved claw tip hooks over the girdle. "
        "`variant_param` = claw hook depth in mm (default 0.4).\n"
        "- **`v_prong`** — V-shaped prong for pointed stones (marquise/pear/princess). "
        "`variant_param` = V half-angle in degrees (default 45).\n"
        "- **`fishtail_prong`** — split fishtail tip for decorative look. "
        "`variant_param` = fishtail spread width in mm (default 0.8).\n"
        "- **`split_prong`** — prong split into two tines from mid-height. "
        "`variant_param` = split start as fraction of prong_height (default 0.5).\n"
        "- **`decorative_prong`** — custom cross-section profile. "
        "`variant_profile` selects profile: `round`, `tapered`, `filigree`, `star`, `leaf`.\n"
        "\nOutput: node spec consumed by the OCCT worker's opJewelryProngVariant handler."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "variant": {
                "type": "string",
                "enum": sorted(_VALID_PRONG_VARIANTS),
                "description": "Prong variant type.",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "prong_count": {
                "type": "integer",
                "description": "Number of prong positions around the stone (typically 4 or 6).",
            },
            "wire_gauge": {
                "type": "number",
                "description": "Prong wire diameter in mm (typical 0.8–1.5).",
            },
            "prong_height": {
                "type": "number",
                "description": "Height the prong extends above the stone's girdle plane in mm.",
            },
            "variant_param": {
                "type": "number",
                "description": (
                    "Variant-specific numeric parameter (see variant descriptions above). "
                    "Default 0.0 (worker uses built-in default for each variant)."
                ),
            },
            "variant_profile": {
                "type": "string",
                "enum": sorted(_VALID_DECORATIVE_PROFILES),
                "description": (
                    "Profile for `decorative_prong` variant. "
                    "One of: round, tapered, filigree, star, leaf. "
                    "Ignored for all other variants."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "variant", "stone_diameter", "prong_count", "wire_gauge", "prong_height"],
    },
)


@register(jewelry_prong_variant_spec, write=True)
async def run_jewelry_create_prong_variant(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    variant = a.get("variant", "").strip().lower()
    stone_diameter = a.get("stone_diameter")
    prong_count = a.get("prong_count")
    wire_gauge = a.get("wire_gauge")
    prong_height = a.get("prong_height")
    variant_param = a.get("variant_param", 0.0)
    variant_profile = a.get("variant_profile", "round")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    if variant not in _VALID_PRONG_VARIANTS:
        return err_payload(
            f"variant must be one of {sorted(_VALID_PRONG_VARIANTS)}; got {variant!r}",
            "BAD_ARGS",
        )

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("wire_gauge", wire_gauge),
        ("prong_height", prong_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        pc = int(prong_count)
    except (TypeError, ValueError):
        return err_payload("prong_count must be an integer", "BAD_ARGS")
    if pc < 2:
        return err_payload(f"prong_count must be >= 2; got {pc}", "BAD_ARGS")

    try:
        vp = float(variant_param)
    except (TypeError, ValueError):
        vp = 0.0
    if vp < 0:
        return err_payload(f"variant_param must be >= 0; got {vp}", "BAD_ARGS")

    vprofile = (variant_profile or "round").strip().lower()
    if vprofile not in _VALID_DECORATIVE_PROFILES:
        return err_payload(
            f"variant_profile must be one of {sorted(_VALID_DECORATIVE_PROFILES)}; got {variant_profile!r}",
            "BAD_ARGS",
        )

    # v_prong half-angle must be < 90.
    if variant == "v_prong" and vp > 0 and vp >= 90.0:
        return err_payload(
            f"v_prong variant_param (half-angle) must be < 90°; got {vp}", "BAD_ARGS"
        )

    # split_prong fraction must be in (0, 1].
    if variant == "split_prong" and vp > 0 and vp > 1.0:
        return err_payload(
            f"split_prong variant_param (split fraction) must be in (0, 1]; got {vp}",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_prong_variant")

    node = build_prong_variant_node(
        node_id=node_id,
        variant=variant,
        stone_diameter=float(stone_diameter),
        prong_count=pc,
        wire_gauge=float(wire_gauge),
        prong_height=float(prong_height),
        variant_param=vp,
        variant_profile=vprofile,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_prong_variant",
        "variant": variant,
        "stone_diameter": float(stone_diameter),
        "prong_count": pc,
        "_head_outer_diameter": node["_head_outer_diameter"],
    })


# ===========================================================================
# HEAD + GALLERY BUILDER
# ===========================================================================
#
# A basket/peg head (accepts a stone seat) combined with a decorative gallery
# rail (the ornamental wire band that runs under the head and above the shank).
# Gallery styles: plain, scalloped, milgrain_edge, pierced, filigree.
# ---------------------------------------------------------------------------

_VALID_GALLERY_STYLES = {"plain", "scalloped", "milgrain_edge", "pierced", "filigree"}


def build_head_gallery_node(
    node_id: str,
    head_diameter: float,
    head_height: float,
    gallery_height: float,
    gallery_style: str,
    motif_pitch: float,
) -> dict:
    """
    Compute the head + gallery builder node spec.

    The worker's opJewelryHeadGallery builds:
      - A basket/peg head (open framework) of outer diameter `head_diameter`
        and height `head_height`.  The head provides the stone seat: the
        caller places a prong or bezel node with a matching `stone_diameter`
        to complete the assembly.
      - A gallery rail band of height `gallery_height` attached below the
        head.  The style controls how the rail is decorated:

        plain          — a plain round-wire or rectangular gallery strip.
        scalloped      — a series of U-shaped scallops cut from the lower
                         edge of the rail.  `motif_pitch` controls the
                         scallop centre-to-centre distance in mm.
        milgrain_edge  — a row of tiny raised beads (milgrain) along both
                         edges of the rail produced by the worker's
                         knurling op.  `motif_pitch` = bead diameter in mm.
        pierced        — open pierced (sawn) decorative motifs repeated at
                         `motif_pitch` intervals.
        filigree       — a filigree wire-work lattice; `motif_pitch`
                         controls the cell size.

    Derived hints:
      _gallery_outer_diameter — same as head_diameter (the gallery wraps at
                                the head's base diameter).
      _gallery_circumference  — π × head_diameter (arc length of one full
                                revolution; used by the worker to tile motifs).
      _motif_count            — floor(circumference / motif_pitch), or 0 if
                                motif_pitch is 0 (plain style ignores it).
    """
    gallery_circumference = math.pi * head_diameter
    motif_count = (
        max(1, int(math.floor(gallery_circumference / motif_pitch)))
        if motif_pitch > 0
        else 0
    )

    return {
        "id": node_id,
        "op": "jewelry_head_gallery",
        "head_diameter": head_diameter,
        "head_height": head_height,
        "gallery_height": gallery_height,
        "gallery_style": gallery_style,
        "motif_pitch": motif_pitch,
        "_gallery_outer_diameter": round(head_diameter, 4),
        "_gallery_circumference": round(gallery_circumference, 4),
        "_motif_count": motif_count,
    }


jewelry_head_gallery_spec = ToolSpec(
    name="jewelry_create_head_gallery",
    description=(
        "Append a `jewelry_head_gallery` node to a `.feature` file. "
        "Generates a basket/peg head (open framework that accepts a stone seat) "
        "combined with a decorative gallery rail running below the head. "
        "The head's `head_diameter` should match the stone-setting diameter "
        "of a companion `jewelry_create_prong_head` or `jewelry_create_bezel` node. "
        "\n\nGallery styles:\n"
        "- **`plain`** — a plain round-wire or rectangular strip.\n"
        "- **`scalloped`** — U-shaped scallops cut from the lower rail edge at "
        "`motif_pitch` intervals.\n"
        "- **`milgrain_edge`** — rows of tiny raised milgrain beads along both "
        "edges; `motif_pitch` = bead diameter.\n"
        "- **`pierced`** — open pierced motifs repeating at `motif_pitch` intervals.\n"
        "- **`filigree`** — filigree wire-work lattice; `motif_pitch` = cell size.\n"
        "\nOutput: node spec consumed by the OCCT worker's opJewelryHeadGallery handler."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "head_diameter": {
                "type": "number",
                "description": "Outer diameter of the head basket in mm.",
            },
            "head_height": {
                "type": "number",
                "description": "Height of the head basket in mm.",
            },
            "gallery_height": {
                "type": "number",
                "description": "Height of the gallery rail band below the head in mm.",
            },
            "gallery_style": {
                "type": "string",
                "enum": sorted(_VALID_GALLERY_STYLES),
                "description": "Decorative style of the gallery rail.",
            },
            "motif_pitch": {
                "type": "number",
                "description": (
                    "Motif repeat pitch in mm (scallop c-c, milgrain bead diameter, "
                    "pierced motif c-c, or filigree cell size). "
                    "Set to 0 for `plain` style. Must be >= 0."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "head_diameter", "head_height", "gallery_height", "gallery_style", "motif_pitch"],
    },
)


@register(jewelry_head_gallery_spec, write=True)
async def run_jewelry_create_head_gallery(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    head_diameter = a.get("head_diameter")
    head_height = a.get("head_height")
    gallery_height = a.get("gallery_height")
    gallery_style = a.get("gallery_style", "plain")
    motif_pitch = a.get("motif_pitch", 0.0)
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("head_diameter", head_diameter),
        ("head_height", head_height),
        ("gallery_height", gallery_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    gallery_style_clean = (gallery_style or "plain").strip().lower()
    if gallery_style_clean not in _VALID_GALLERY_STYLES:
        return err_payload(
            f"gallery_style must be one of {sorted(_VALID_GALLERY_STYLES)}; got {gallery_style!r}",
            "BAD_ARGS",
        )

    try:
        mp = float(motif_pitch)
    except (TypeError, ValueError):
        return err_payload("motif_pitch must be a number", "BAD_ARGS")
    if mp < 0:
        return err_payload(f"motif_pitch must be >= 0; got {mp}", "BAD_ARGS")

    if gallery_style_clean != "plain" and mp == 0.0:
        return err_payload(
            f"motif_pitch must be > 0 for gallery_style '{gallery_style_clean}'",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_head_gallery")

    node = build_head_gallery_node(
        node_id=node_id,
        head_diameter=float(head_diameter),
        head_height=float(head_height),
        gallery_height=float(gallery_height),
        gallery_style=gallery_style_clean,
        motif_pitch=mp,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_head_gallery",
        "gallery_style": gallery_style_clean,
        "head_diameter": float(head_diameter),
        "_motif_count": node["_motif_count"],
    })


# ===========================================================================
# UNDER-BEZEL / PEG SETTINGS
# ===========================================================================

def build_under_bezel_node(
    node_id: str,
    stone_diameter: float,
    wall_thickness: float,
    collet_height: float,
    base_diameter: float,
    base_thickness: float,
) -> dict:
    """
    Compute the under-bezel (sub-collet) node spec.

    The worker's opJewelryUnderBezel builds a low collet that sits under the
    stone, providing an elevated bearing surface so the stone is raised above
    the shank.  Useful as a secondary support beneath a bezel or halo setting.

    Geometry:
      - Inner bore = stone_diameter.
      - Outer wall = stone_diameter + 2 × wall_thickness.
      - The collet rises to `collet_height`.
      - A circular base plate of diameter `base_diameter` and thickness
        `base_thickness` extends outward at the bottom to fuse onto the shank.

    Derived hints:
      _outer_diameter    — stone_diameter + 2 * wall_thickness.
      _collet_volume_approx — approximate material volume (mm³) of the
                              annular collet (excluding base plate).
    """
    outer_diameter = stone_diameter + 2.0 * wall_thickness
    r_outer = outer_diameter / 2.0
    r_inner = stone_diameter / 2.0
    collet_volume = math.pi * (r_outer ** 2 - r_inner ** 2) * collet_height

    return {
        "id": node_id,
        "op": "jewelry_under_bezel",
        "stone_diameter": stone_diameter,
        "wall_thickness": wall_thickness,
        "collet_height": collet_height,
        "base_diameter": base_diameter,
        "base_thickness": base_thickness,
        "_outer_diameter": round(outer_diameter, 4),
        "_collet_volume_approx": round(collet_volume, 4),
    }


jewelry_under_bezel_spec = ToolSpec(
    name="jewelry_create_under_bezel",
    description=(
        "Append a `jewelry_under_bezel` node to a `.feature` file. "
        "Generates a sub-collet (under-bezel) — a short metal collar that sits "
        "beneath the stone and raises it above the shank. "
        "Used as a secondary support under bezels, halos, or other settings "
        "where the stone needs to be elevated. "
        "The collet has inner bore = `stone_diameter`, outer wall = "
        "`stone_diameter + 2 × wall_thickness`, and height = `collet_height`. "
        "A flat base plate of `base_diameter` × `base_thickness` extends below "
        "the collet for fusing onto a shank. "
        "Output: a TopoDS_Solid consumed by opJewelryUnderBezel."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "wall_thickness": {
                "type": "number",
                "description": "Wall thickness of the collet in mm (typical 0.3–0.8).",
            },
            "collet_height": {
                "type": "number",
                "description": "Height of the collet tube in mm.",
            },
            "base_diameter": {
                "type": "number",
                "description": (
                    "Diameter of the flat base plate in mm. "
                    "Must be >= stone_diameter + 2 × wall_thickness."
                ),
            },
            "base_thickness": {
                "type": "number",
                "description": "Thickness of the base plate in mm.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "wall_thickness", "collet_height", "base_diameter", "base_thickness"],
    },
)


@register(jewelry_under_bezel_spec, write=True)
async def run_jewelry_create_under_bezel(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    wall_thickness = a.get("wall_thickness")
    collet_height = a.get("collet_height")
    base_diameter = a.get("base_diameter")
    base_thickness = a.get("base_thickness")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("wall_thickness", wall_thickness),
        ("collet_height", collet_height),
        ("base_diameter", base_diameter),
        ("base_thickness", base_thickness),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        sd = float(stone_diameter)
        wt = float(wall_thickness)
        bd = float(base_diameter)
    except (TypeError, ValueError):
        return err_payload("stone_diameter, wall_thickness, base_diameter must be numbers", "BAD_ARGS")

    min_base = sd + 2.0 * wt
    if bd < min_base:
        return err_payload(
            f"base_diameter ({bd}) must be >= stone_diameter + 2×wall_thickness ({min_base:.4f})",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_under_bezel")

    node = build_under_bezel_node(
        node_id=node_id,
        stone_diameter=sd,
        wall_thickness=wt,
        collet_height=float(collet_height),
        base_diameter=bd,
        base_thickness=float(base_thickness),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_under_bezel",
        "stone_diameter": sd,
        "_outer_diameter": node["_outer_diameter"],
    })


# ---------------------------------------------------------------------------
# Peg setting (post head for earrings / pendants)
# ---------------------------------------------------------------------------

def build_peg_setting_node(
    node_id: str,
    stone_diameter: float,
    peg_diameter: float,
    peg_length: float,
    base_diameter: float,
    base_thickness: float,
) -> dict:
    """
    Compute the peg-setting node spec.

    The worker's opJewelryPegSetting builds:
      - A cylindrical peg (post) of diameter `peg_diameter` and length
        `peg_length` extending downward from a head cup.
      - A shallow cup / seat at the top of the peg sized to accept the stone
        (inner diameter = stone_diameter; the stone rests in the cup and may
        be secured with adhesive or a small retaining ledge).
      - An optional base disc of `base_diameter` × `base_thickness` at the
        foot of the peg for soldering onto a finding or ear-post socket.

    Typical use: drops, briolette hangers, stud-earring settings, and
    pendant bezels where the stone hangs below the setting.

    Derived hints:
      _cup_depth        — default cup depth = stone_diameter × 0.2.
      _peg_aspect_ratio — peg_length / peg_diameter.
    """
    cup_depth = stone_diameter * 0.2
    peg_aspect_ratio = peg_length / peg_diameter if peg_diameter > 0 else 0.0

    return {
        "id": node_id,
        "op": "jewelry_peg_setting",
        "stone_diameter": stone_diameter,
        "peg_diameter": peg_diameter,
        "peg_length": peg_length,
        "base_diameter": base_diameter,
        "base_thickness": base_thickness,
        "_cup_depth": round(cup_depth, 4),
        "_peg_aspect_ratio": round(peg_aspect_ratio, 4),
    }


jewelry_peg_setting_spec = ToolSpec(
    name="jewelry_create_peg_setting",
    description=(
        "Append a `jewelry_peg_setting` node to a `.feature` file. "
        "Generates a peg (post) setting for earrings and pendants — a cylindrical "
        "post with a shallow stone-cup at the top and an optional base disc. "
        "The stone sits in the cup (held by adhesive or a small retaining ledge); "
        "the peg solders into an earring back or pendant finding. "
        "Parameters: `stone_diameter` for the cup seat, `peg_diameter` / "
        "`peg_length` for the post, and `base_diameter` / `base_thickness` for "
        "the soldering foot. "
        "Output: a TopoDS_Solid consumed by opJewelryPegSetting."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm (sets the cup seat size).",
            },
            "peg_diameter": {
                "type": "number",
                "description": "Diameter of the cylindrical post in mm.",
            },
            "peg_length": {
                "type": "number",
                "description": "Length (height) of the post in mm.",
            },
            "base_diameter": {
                "type": "number",
                "description": "Diameter of the soldering base disc in mm. Must be >= peg_diameter.",
            },
            "base_thickness": {
                "type": "number",
                "description": "Thickness of the base disc in mm.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "peg_diameter", "peg_length", "base_diameter", "base_thickness"],
    },
)


@register(jewelry_peg_setting_spec, write=True)
async def run_jewelry_create_peg_setting(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    peg_diameter = a.get("peg_diameter")
    peg_length = a.get("peg_length")
    base_diameter = a.get("base_diameter")
    base_thickness = a.get("base_thickness")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("peg_diameter", peg_diameter),
        ("peg_length", peg_length),
        ("base_diameter", base_diameter),
        ("base_thickness", base_thickness),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        pd = float(peg_diameter)
        bd = float(base_diameter)
    except (TypeError, ValueError):
        return err_payload("peg_diameter and base_diameter must be numbers", "BAD_ARGS")

    if bd < pd:
        return err_payload(
            f"base_diameter ({bd}) must be >= peg_diameter ({pd})",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_peg_setting")

    node = build_peg_setting_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        peg_diameter=pd,
        peg_length=float(peg_length),
        base_diameter=bd,
        base_thickness=float(base_thickness),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_peg_setting",
        "stone_diameter": float(stone_diameter),
        "peg_diameter": pd,
        "_cup_depth": node["_cup_depth"],
    })


# ===========================================================================
# CROWN / CORONET SETTING
# ===========================================================================
#
# A tapered crown of graduated prongs — a vintage look typical of antique
# and Victorian jewellery where the prongs form a regal coronet silhouette.
# ---------------------------------------------------------------------------

def build_coronet_node(
    node_id: str,
    stone_diameter: float,
    prong_count: int,
    crown_height: float,
    taper: float,
    wire_gauge: float,
) -> dict:
    """
    Compute the crown / coronet setting node spec.

    The worker's opJewelryCoronet builds:
      - `prong_count` prong wires of `wire_gauge` arranged evenly around the
        stone and rising to `crown_height` above the girdle plane.
      - Each prong tapers inward by `taper` mm over its full height (positive
        taper = prong leans over the stone; negative = flares outward).
        Typical values: 0.2–0.6 mm (subtle inward lean gives the classic
        coronet dome).
      - The base of the crown is a low cylinder (height = crown_height × 0.25)
        with the prong wire footings, which the caller boolean-fuses onto a
        shank.

    The coronet produces a narrower, more upright silhouette than a basket
    head because the prongs converge toward the stone's table rather than
    being parallel.

    Derived hints:
      _base_diameter     — stone_diameter + 2 × wire_gauge (same as prong head).
      _tip_diameter      — base_diameter - 2 × taper (reduced diameter at tip).
      _prong_pitch_deg   — 360 / prong_count.
    """
    base_diameter = stone_diameter + 2.0 * wire_gauge
    tip_diameter = max(stone_diameter, base_diameter - 2.0 * taper)
    prong_pitch_deg = 360.0 / prong_count if prong_count > 0 else 0.0

    return {
        "id": node_id,
        "op": "jewelry_coronet",
        "stone_diameter": stone_diameter,
        "prong_count": prong_count,
        "crown_height": crown_height,
        "taper": taper,
        "wire_gauge": wire_gauge,
        "_base_diameter": round(base_diameter, 4),
        "_tip_diameter": round(tip_diameter, 4),
        "_prong_pitch_deg": round(prong_pitch_deg, 4),
    }


jewelry_coronet_spec = ToolSpec(
    name="jewelry_create_coronet",
    description=(
        "Append a `jewelry_coronet` node to a `.feature` file. "
        "Generates a crown (coronet) setting — a tapered arrangement of "
        "`prong_count` graduated prong wires that lean inward toward the stone "
        "and form a regal coronet silhouette typical of antique and Victorian "
        "jewellery. "
        "Each prong wire has diameter `wire_gauge` and rises to `crown_height` "
        "above the girdle plane, tapering inward by `taper` mm (0 = straight; "
        "typical 0.2–0.6 mm for the classic dome effect). "
        "The setting base is a short cylinder fused onto a shank. "
        "Output: node spec consumed by the OCCT worker's opJewelryCoronet handler."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "prong_count": {
                "type": "integer",
                "description": "Number of prongs in the coronet (typically 6, 8, or 10).",
            },
            "crown_height": {
                "type": "number",
                "description": "Height the prongs rise above the girdle plane in mm.",
            },
            "taper": {
                "type": "number",
                "description": (
                    "Inward lean of each prong tip relative to its base in mm. "
                    "0 = straight prongs. Positive = lean inward (coronet dome); "
                    "must be < wire_gauge so tips remain solid."
                ),
            },
            "wire_gauge": {
                "type": "number",
                "description": "Prong wire diameter in mm (typical 0.8–1.5).",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "stone_diameter", "prong_count", "crown_height", "taper", "wire_gauge"],
    },
)


@register(jewelry_coronet_spec, write=True)
async def run_jewelry_create_coronet(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    prong_count = a.get("prong_count")
    crown_height = a.get("crown_height")
    taper = a.get("taper")
    wire_gauge = a.get("wire_gauge")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("crown_height", crown_height),
        ("wire_gauge", wire_gauge),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    # taper may be 0 (straight prongs); only forbid negative taper.
    try:
        tap = float(taper)
    except (TypeError, ValueError):
        return err_payload("taper must be a number", "BAD_ARGS")
    if tap < 0:
        return err_payload(f"taper must be >= 0; got {tap}", "BAD_ARGS")

    try:
        pc = int(prong_count)
    except (TypeError, ValueError):
        return err_payload("prong_count must be an integer", "BAD_ARGS")
    if pc < 3:
        return err_payload(f"prong_count must be >= 3; got {pc}", "BAD_ARGS")

    try:
        wg = float(wire_gauge)
    except (TypeError, ValueError):
        return err_payload("wire_gauge must be a number", "BAD_ARGS")

    if tap >= wg:
        return err_payload(
            f"taper ({tap}) must be < wire_gauge ({wg}) so prong tips remain solid",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_coronet")

    node = build_coronet_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        prong_count=pc,
        crown_height=float(crown_height),
        taper=tap,
        wire_gauge=wg,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_coronet",
        "stone_diameter": float(stone_diameter),
        "prong_count": pc,
        "_base_diameter": node["_base_diameter"],
        "_tip_diameter": node["_tip_diameter"],
    })


# ===========================================================================
# SUSPENSION / DANGLE MOUNT
# ===========================================================================
#
# An articulated stone mount that swings — used for drop earrings and
# pendants.  Consists of a jump-ring-style pivot loop attached to a stone
# seat (bezel cup or prong cup).
# ---------------------------------------------------------------------------

_VALID_SEAT_STYLES = {"bezel_cup", "prong_cup", "claw_cup"}


def build_suspension_mount_node(
    node_id: str,
    stone_diameter: float,
    seat_style: str,
    seat_depth: float,
    ring_wire_diameter: float,
    ring_inner_diameter: float,
    bail_height: float,
) -> dict:
    """
    Compute the suspension / dangle mount node spec.

    The worker's opJewelrySuspensionMount builds:
      - A stone seat of `seat_style` ('bezel_cup', 'prong_cup', or 'claw_cup')
        sized to `stone_diameter`, with a seating depth of `seat_depth`.
      - A jump-ring-style pivot loop of wire diameter `ring_wire_diameter`
        and inner diameter `ring_inner_diameter` soldered to the top of the
        seat.  The loop passes through a finding (ear wire or pendant bail) and
        allows the mount to swing freely.
      - A short bail cylinder of height `bail_height` that connects the seat
        body to the pivot ring; provides extra metal above the stone for
        structural strength.

    The ring's outer diameter = ring_inner_diameter + 2 × ring_wire_diameter.
    The total assembly height = seat_depth + bail_height + ring_wire_diameter.

    Derived hints:
      _ring_outer_diameter — ring_inner_diameter + 2 * ring_wire_diameter.
      _total_height        — seat_depth + bail_height + ring_wire_diameter.
      _seat_radius         — stone_diameter / 2.
    """
    ring_outer_diameter = ring_inner_diameter + 2.0 * ring_wire_diameter
    total_height = seat_depth + bail_height + ring_wire_diameter
    seat_radius = stone_diameter / 2.0

    return {
        "id": node_id,
        "op": "jewelry_suspension_mount",
        "stone_diameter": stone_diameter,
        "seat_style": seat_style,
        "seat_depth": seat_depth,
        "ring_wire_diameter": ring_wire_diameter,
        "ring_inner_diameter": ring_inner_diameter,
        "bail_height": bail_height,
        "_ring_outer_diameter": round(ring_outer_diameter, 4),
        "_total_height": round(total_height, 4),
        "_seat_radius": round(seat_radius, 4),
    }


jewelry_suspension_mount_spec = ToolSpec(
    name="jewelry_create_suspension_mount",
    description=(
        "Append a `jewelry_suspension_mount` node to a `.feature` file. "
        "Generates an articulated dangle mount for drop earrings and pendants — "
        "a stone seat attached to a jump-ring-style pivot loop that lets the "
        "setting swing freely on an ear wire or pendant bail. "
        "\n\nSeat styles:\n"
        "- **`bezel_cup`** — a full bezel collar seat.\n"
        "- **`prong_cup`** — an open prong-head cup (typically 4 prongs).\n"
        "- **`claw_cup`** — a claw-tip prong cup for maximum stone visibility.\n"
        "\nThe pivot ring is sized by `ring_inner_diameter` (the passage diameter "
        "through which the ear wire or bail slides) and `ring_wire_diameter` "
        "(the ring cross-section). A short `bail_height` cylinder connects the "
        "seat to the ring. "
        "Output: node spec consumed by opJewelrySuspensionMount."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "seat_style": {
                "type": "string",
                "enum": sorted(_VALID_SEAT_STYLES),
                "description": (
                    "Stone seat type. "
                    "'bezel_cup': full bezel collar. "
                    "'prong_cup': open 4-prong cup. "
                    "'claw_cup': claw-tip prong cup."
                ),
            },
            "seat_depth": {
                "type": "number",
                "description": "Depth of the stone seat in mm (typically 40–60% of stone depth).",
            },
            "ring_wire_diameter": {
                "type": "number",
                "description": "Wire cross-section diameter of the pivot jump ring in mm (typical 0.7–1.2).",
            },
            "ring_inner_diameter": {
                "type": "number",
                "description": "Inner passage diameter of the pivot ring in mm. Must be > ring_wire_diameter.",
            },
            "bail_height": {
                "type": "number",
                "description": "Height of the bail cylinder connecting seat to pivot ring in mm (typical 1.0–3.0).",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": [
            "file_id", "stone_diameter", "seat_style", "seat_depth",
            "ring_wire_diameter", "ring_inner_diameter", "bail_height",
        ],
    },
)


@register(jewelry_suspension_mount_spec, write=True)
async def run_jewelry_create_suspension_mount(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    seat_style = a.get("seat_style", "bezel_cup")
    seat_depth = a.get("seat_depth")
    ring_wire_diameter = a.get("ring_wire_diameter")
    ring_inner_diameter = a.get("ring_inner_diameter")
    bail_height = a.get("bail_height")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("seat_depth", seat_depth),
        ("ring_wire_diameter", ring_wire_diameter),
        ("ring_inner_diameter", ring_inner_diameter),
        ("bail_height", bail_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    seat_style_clean = (seat_style or "bezel_cup").strip().lower()
    if seat_style_clean not in _VALID_SEAT_STYLES:
        return err_payload(
            f"seat_style must be one of {sorted(_VALID_SEAT_STYLES)}; got {seat_style!r}",
            "BAD_ARGS",
        )

    try:
        rwd = float(ring_wire_diameter)
        rid = float(ring_inner_diameter)
    except (TypeError, ValueError):
        return err_payload("ring_wire_diameter and ring_inner_diameter must be numbers", "BAD_ARGS")

    if rid <= rwd:
        return err_payload(
            f"ring_inner_diameter ({rid}) must be > ring_wire_diameter ({rwd})",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_suspension_mount")

    node = build_suspension_mount_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        seat_style=seat_style_clean,
        seat_depth=float(seat_depth),
        ring_wire_diameter=rwd,
        ring_inner_diameter=rid,
        bail_height=float(bail_height),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_suspension_mount",
        "stone_diameter": float(stone_diameter),
        "seat_style": seat_style_clean,
        "_ring_outer_diameter": node["_ring_outer_diameter"],
        "_total_height": node["_total_height"],
    })


# ===========================================================================
# TRILLIANT / FANCY-SHAPED V-TIP PROTECTOR SETTING
# ===========================================================================
#
# Protective metal V-tip caps placed over each pointed corner of a fancy-cut
# stone (pear, marquise, heart, trillion).  Each cap is a thin channel-like
# metal sleeve that wraps around the stone's sharp corner to protect it from
# chipping.
# ---------------------------------------------------------------------------

_VALID_STONE_SHAPES = {"pear", "marquise", "heart", "trillion"}


def build_vtip_protector_node(
    node_id: str,
    stone_shape: str,
    tip_count: int,
    tip_width: float,
    tip_length: float,
    wall_thickness: float,
    seat_angle_deg: float,
) -> dict:
    """
    Compute the V-tip protector setting node spec.

    The worker's opJewelryVtipProtector builds:
      - `tip_count` V-channel caps evenly distributed at the stone's pointed
        corners.  For 'pear' and 'marquise': typically 1 or 2 tips; for
        'trillion': 3 tips; for 'heart': 2 tips.
      - Each cap is an open V-channel of width `tip_width` at the base and
        length `tip_length` along the stone's edge from the corner, with wall
        thickness `wall_thickness`.
      - The internal angle of the V-channel is `seat_angle_deg` — this should
        match the included angle of the stone's pointed corner for a snug fit
        (typical 40–70° for pear/marquise, 60° for trillion).

    Derived hints:
      _tip_opening_width — width at the open end of the V = 2 × tip_length ×
                           tan(seat_angle_deg / 2).
      _cap_area_approx   — approximate cross-sectional area of each cap
                           (triangular section) = 0.5 × tip_width × tip_length.
    """
    half_angle_rad = math.radians(seat_angle_deg / 2.0)
    tip_opening_width = 2.0 * tip_length * math.tan(half_angle_rad)
    cap_area_approx = 0.5 * tip_width * tip_length

    return {
        "id": node_id,
        "op": "jewelry_vtip_protector",
        "stone_shape": stone_shape,
        "tip_count": tip_count,
        "tip_width": tip_width,
        "tip_length": tip_length,
        "wall_thickness": wall_thickness,
        "seat_angle_deg": seat_angle_deg,
        "_tip_opening_width": round(tip_opening_width, 4),
        "_cap_area_approx": round(cap_area_approx, 4),
    }


jewelry_vtip_protector_spec = ToolSpec(
    name="jewelry_create_vtip_protector",
    description=(
        "Append a `jewelry_vtip_protector` node to a `.feature` file. "
        "Generates protective V-tip metal caps for the pointed corners of "
        "fancy-cut stones (pear, marquise, heart, trillion). "
        "Each cap is a V-channel sleeve that wraps snugly around the stone's "
        "sharp corner to prevent chipping during wear. "
        "\n\nStone shapes supported:\n"
        "- **`pear`** — 1 pointed tip (bottom culet) or 2 (top and bottom).\n"
        "- **`marquise`** — 2 pointed tips (both ends of the oval).\n"
        "- **`heart`** — 2 tips (the two lower lobes of the cleft).\n"
        "- **`trillion`** — 3 tips (one per corner of the triangular stone).\n"
        "\nThe V-channel internal angle `seat_angle_deg` must match the stone's "
        "corner included angle for a snug fit (typical 40–70° pear/marquise; "
        "60° trillion). "
        "`tip_count` overrides the default count if you need custom cap placement. "
        "Output: node spec consumed by opJewelryVtipProtector."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_shape": {
                "type": "string",
                "enum": sorted(_VALID_STONE_SHAPES),
                "description": "Shape of the fancy-cut stone. One of: pear, marquise, heart, trillion.",
            },
            "tip_count": {
                "type": "integer",
                "description": (
                    "Number of V-tip caps to generate. "
                    "Default per shape: pear=1, marquise=2, heart=2, trillion=3. "
                    "Must be >= 1."
                ),
            },
            "tip_width": {
                "type": "number",
                "description": "Width of the V-channel opening at the base in mm (typical 0.4–1.0).",
            },
            "tip_length": {
                "type": "number",
                "description": "Length of the cap along the stone edge from the corner in mm (typical 0.5–1.5).",
            },
            "wall_thickness": {
                "type": "number",
                "description": "Wall thickness of the V-channel cap in mm (typical 0.2–0.5).",
            },
            "seat_angle_deg": {
                "type": "number",
                "description": (
                    "Internal angle of the V-channel in degrees — must match the "
                    "stone's corner included angle. Typical: 40–70° (pear/marquise), "
                    "60° (trillion). Must be in (0, 180)."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": [
            "file_id", "stone_shape", "tip_count", "tip_width",
            "tip_length", "wall_thickness", "seat_angle_deg",
        ],
    },
)


@register(jewelry_vtip_protector_spec, write=True)
async def run_jewelry_create_vtip_protector(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_shape = a.get("stone_shape", "pear")
    tip_count = a.get("tip_count")
    tip_width = a.get("tip_width")
    tip_length = a.get("tip_length")
    wall_thickness = a.get("wall_thickness")
    seat_angle_deg = a.get("seat_angle_deg")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    stone_shape_clean = (stone_shape or "pear").strip().lower()
    if stone_shape_clean not in _VALID_STONE_SHAPES:
        return err_payload(
            f"stone_shape must be one of {sorted(_VALID_STONE_SHAPES)}; got {stone_shape!r}",
            "BAD_ARGS",
        )

    for fname, fval in [
        ("tip_width", tip_width),
        ("tip_length", tip_length),
        ("wall_thickness", wall_thickness),
        ("seat_angle_deg", seat_angle_deg),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        sa = float(seat_angle_deg)
    except (TypeError, ValueError):
        return err_payload("seat_angle_deg must be a number", "BAD_ARGS")
    if sa >= 180.0:
        return err_payload(
            f"seat_angle_deg must be < 180°; got {sa}", "BAD_ARGS"
        )

    try:
        tc = int(tip_count)
    except (TypeError, ValueError):
        return err_payload("tip_count must be an integer", "BAD_ARGS")
    if tc < 1:
        return err_payload(f"tip_count must be >= 1; got {tc}", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_vtip_protector")

    node = build_vtip_protector_node(
        node_id=node_id,
        stone_shape=stone_shape_clean,
        tip_count=tc,
        tip_width=float(tip_width),
        tip_length=float(tip_length),
        wall_thickness=float(wall_thickness),
        seat_angle_deg=sa,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_vtip_protector",
        "stone_shape": stone_shape_clean,
        "tip_count": tc,
        "_tip_opening_width": node["_tip_opening_width"],
    })


# ===========================================================================
# BOMBÉ / DOME CLUSTER SETTING
# ===========================================================================
#
# A multi-stone cluster on a strongly curved (bombé / domed) surface.
# Distinct from the flat cluster setting: stones are projected onto a
# spherical cap of given radius, not onto a shallow dome.
# ---------------------------------------------------------------------------

def _compute_bombe_positions(
    dome_radius: float,
    stone_size: float,
    stone_count: int,
) -> list:
    """
    Distribute `stone_count` stones of `stone_size` on a spherical cap of
    radius `dome_radius`.

    Uses a sunflower (Fibonacci) spiral on the sphere to distribute stones
    evenly across the visible hemisphere.  Each position is expressed as
    (polar_angle_deg, azimuth_deg) and the corresponding Cartesian (x, y, z)
    on the sphere surface.

    Returns list of {"x": float, "y": float, "z": float,
                      "polar_deg": float, "azimuth_deg": float}.
    """
    positions = []
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))  # ~137.5°

    for i in range(stone_count):
        # Uniformly sample the upper hemisphere (z in [0, 1]).
        # For a single stone, place it at the pole.
        if stone_count == 1:
            t = 0.0
        else:
            t = i / (stone_count - 1) if stone_count > 1 else 0.0

        # Map t from 0 (pole) to a maximum polar angle limited to 80° so
        # stones stay on the visible front face of the dome.
        polar_deg = t * 80.0
        polar_rad = math.radians(polar_deg)
        azimuth_rad = i * golden_angle
        azimuth_deg = math.degrees(azimuth_rad) % 360.0

        x = dome_radius * math.sin(polar_rad) * math.cos(azimuth_rad)
        y = dome_radius * math.sin(polar_rad) * math.sin(azimuth_rad)
        z = dome_radius * math.cos(polar_rad)
        positions.append({
            "x": round(x, 4),
            "y": round(y, 4),
            "z": round(z, 4),
            "polar_deg": round(polar_deg, 4),
            "azimuth_deg": round(azimuth_deg, 4),
        })
    return positions


def build_bombe_cluster_node(
    node_id: str,
    dome_radius: float,
    stone_size: float,
    stone_count: int,
    cap_half_angle_deg: float,
    base_height: float,
) -> dict:
    """
    Compute the bombé cluster setting node spec.

    The worker's opJewelryBombeCluster builds:
      - A spherical cap of radius `dome_radius`, subtending a half-angle of
        `cap_half_angle_deg` at the pole (this is the visible curved face).
      - `stone_count` stone seats of diameter `stone_size` distributed across
        the dome surface according to `positions` (Fibonacci-spiral layout).
      - A flat base ring of height `base_height` at the equator of the cap
        for fusing onto a shank or gallery.

    Derived hints:
      _cap_arc_length   — arc length from pole to equator = dome_radius × cap_half_angle_rad.
      _base_diameter    — diameter at the equator of the cap = 2 × dome_radius × sin(cap_half_angle).
      positions         — per-stone Cartesian + polar positions on the sphere surface.
    """
    cap_half_angle_rad = math.radians(cap_half_angle_deg)
    cap_arc_length = dome_radius * cap_half_angle_rad
    base_diameter = 2.0 * dome_radius * math.sin(cap_half_angle_rad)
    positions = _compute_bombe_positions(
        dome_radius=dome_radius,
        stone_size=stone_size,
        stone_count=stone_count,
    )

    return {
        "id": node_id,
        "op": "jewelry_bombe_cluster",
        "dome_radius": dome_radius,
        "stone_size": stone_size,
        "stone_count": stone_count,
        "cap_half_angle_deg": cap_half_angle_deg,
        "base_height": base_height,
        "positions": positions,
        "_cap_arc_length": round(cap_arc_length, 4),
        "_base_diameter": round(base_diameter, 4),
        "_actual_count": len(positions),
    }


jewelry_bombe_cluster_spec = ToolSpec(
    name="jewelry_create_bombe_cluster",
    description=(
        "Append a `jewelry_bombe_cluster` node to a `.feature` file. "
        "Generates a bombé (dome) cluster setting — a strongly domed multi-stone "
        "cluster where stone seats are distributed across a spherical cap surface. "
        "Unlike the flat `jewelry_cluster`, the bombé uses a full spherical-cap "
        "dome geometry described by `dome_radius` and `cap_half_angle_deg`. "
        "Stones are placed using a Fibonacci-spiral layout for even coverage. "
        "`stone_count` stones of `stone_size` are distributed across the dome; "
        "a flat base ring of `base_height` closes the bottom for shank attachment. "
        "Output: node spec consumed by opJewelryBombeCluster. The evaluate result "
        "includes `seat_positions` — per-stone world-space transforms on the dome."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "dome_radius": {
                "type": "number",
                "description": "Radius of the spherical dome in mm (typical 4–15 mm).",
            },
            "stone_size": {
                "type": "number",
                "description": "Girdle diameter of each stone in the cluster in mm.",
            },
            "stone_count": {
                "type": "integer",
                "description": "Number of stones distributed across the dome. Must be >= 1.",
            },
            "cap_half_angle_deg": {
                "type": "number",
                "description": (
                    "Half-angle subtended by the dome cap at the sphere centre, in degrees. "
                    "Controls how much of the sphere is visible. "
                    "Typical range: 45–80°. Must be in (0, 90)."
                ),
            },
            "base_height": {
                "type": "number",
                "description": "Height of the flat base ring at the cap equator in mm.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "dome_radius", "stone_size", "stone_count", "cap_half_angle_deg", "base_height"],
    },
)


@register(jewelry_bombe_cluster_spec, write=True)
async def run_jewelry_create_bombe_cluster(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    dome_radius = a.get("dome_radius")
    stone_size = a.get("stone_size")
    stone_count = a.get("stone_count")
    cap_half_angle_deg = a.get("cap_half_angle_deg")
    base_height = a.get("base_height")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("dome_radius", dome_radius),
        ("stone_size", stone_size),
        ("cap_half_angle_deg", cap_half_angle_deg),
        ("base_height", base_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        cha = float(cap_half_angle_deg)
    except (TypeError, ValueError):
        return err_payload("cap_half_angle_deg must be a number", "BAD_ARGS")
    if cha >= 90.0:
        return err_payload(
            f"cap_half_angle_deg must be < 90°; got {cha}", "BAD_ARGS"
        )

    try:
        sc = int(stone_count)
    except (TypeError, ValueError):
        return err_payload("stone_count must be an integer", "BAD_ARGS")
    if sc < 1:
        return err_payload(f"stone_count must be >= 1; got {sc}", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_bombe_cluster")

    node = build_bombe_cluster_node(
        node_id=node_id,
        dome_radius=float(dome_radius),
        stone_size=float(stone_size),
        stone_count=sc,
        cap_half_angle_deg=cha,
        base_height=float(base_height),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_bombe_cluster",
        "stone_count": sc,
        "dome_radius": float(dome_radius),
        "_base_diameter": node["_base_diameter"],
        "_actual_count": node["_actual_count"],
    })


# ===========================================================================
# LOTUS / COMPASS / STAR PATTERNED BEZEL
# ===========================================================================
#
# A decorative bezel collar whose wall is pierced or shaped into a repeating
# petal, compass-point, or star-outline pattern.
# ---------------------------------------------------------------------------

_VALID_BEZEL_PATTERNS = {"lotus", "compass", "star", "plain"}


def build_patterned_bezel_node(
    node_id: str,
    stone_diameter: float,
    wall_thickness: float,
    bezel_height: float,
    bearing_ledge_height: float,
    pattern: str,
    petal_count: int,
) -> dict:
    """
    Compute the patterned bezel (lotus/compass/star) node spec.

    The worker's opJewelryPatternedBezel builds:
      - A full 360° bezel collar of inner diameter = `stone_diameter` and
        outer diameter = `stone_diameter + 2 × wall_thickness`, extruded
        to `bezel_height` with a bearing ledge at `bearing_ledge_height`.
      - The bezel wall is then pierced or shaped with `petal_count` repeating
        decorative motifs controlled by `pattern`:

        'lotus'   — rounded petal cutouts alternating inward from the top
                    edge; each petal is a semicircle of diameter ≈ wall_thickness.
        'compass' — pointed compass-rose projections extending outward at
                    `petal_count` cardinal / inter-cardinal directions.
        'star'    — V-notch star outline cut into the top edge, creating
                    alternating peaks and valleys around the collar.
        'plain'   — no decorative cutouts (standard full bezel).

    Derived hints:
      _outer_diameter   — stone_diameter + 2 * wall_thickness.
      _petal_pitch_deg  — 360 / petal_count (angular pitch between motifs).
    """
    outer_diameter = stone_diameter + 2.0 * wall_thickness
    petal_pitch_deg = 360.0 / petal_count if petal_count > 0 else 0.0

    return {
        "id": node_id,
        "op": "jewelry_patterned_bezel",
        "stone_diameter": stone_diameter,
        "wall_thickness": wall_thickness,
        "bezel_height": bezel_height,
        "bearing_ledge_height": bearing_ledge_height,
        "pattern": pattern,
        "petal_count": petal_count,
        "_outer_diameter": round(outer_diameter, 4),
        "_petal_pitch_deg": round(petal_pitch_deg, 4),
    }


jewelry_patterned_bezel_spec = ToolSpec(
    name="jewelry_create_patterned_bezel",
    description=(
        "Append a `jewelry_patterned_bezel` node to a `.feature` file. "
        "Generates a decorative bezel collar with a repeating patterned outline "
        "— lotus petal, compass point, or star-notch — cut into the bezel wall. "
        "\n\nPatterns:\n"
        "- **`lotus`** — rounded petal cutouts from the top edge; classic floral "
        "look popular in Indian and Art Nouveau jewellery.\n"
        "- **`compass`** — pointed projections at `petal_count` compass directions "
        "extending outward beyond the stone (compass rose / sun-ray bezel).\n"
        "- **`star`** — V-notch star outline along the top edge, creating "
        "alternating peaks and valleys (star bezel).\n"
        "- **`plain`** — a standard full bezel with no decorative cutouts.\n"
        "\n`petal_count` controls the number of repeating motif units (typical 6–16). "
        "The `bearing_ledge_height` stone seat is unaffected by the pattern. "
        "Output: node spec consumed by opJewelryPatternedBezel."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "wall_thickness": {
                "type": "number",
                "description": "Bezel wall thickness in mm (typical 0.3–0.8).",
            },
            "bezel_height": {
                "type": "number",
                "description": "Total height of the bezel collar in mm.",
            },
            "bearing_ledge_height": {
                "type": "number",
                "description": "Height of the bearing ledge from base in mm. Must be < bezel_height.",
            },
            "pattern": {
                "type": "string",
                "enum": sorted(_VALID_BEZEL_PATTERNS),
                "description": "Decorative pattern for the bezel collar. One of: lotus, compass, star, plain.",
            },
            "petal_count": {
                "type": "integer",
                "description": (
                    "Number of repeating decorative motif units around the collar. "
                    "Must be >= 3. Typical: 6, 8, 12, 16. Ignored for 'plain' pattern."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": [
            "file_id", "stone_diameter", "wall_thickness", "bezel_height",
            "bearing_ledge_height", "pattern", "petal_count",
        ],
    },
)


@register(jewelry_patterned_bezel_spec, write=True)
async def run_jewelry_create_patterned_bezel(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    wall_thickness = a.get("wall_thickness")
    bezel_height = a.get("bezel_height")
    bearing_ledge_height = a.get("bearing_ledge_height")
    pattern = a.get("pattern", "lotus")
    petal_count = a.get("petal_count")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("wall_thickness", wall_thickness),
        ("bezel_height", bezel_height),
        ("bearing_ledge_height", bearing_ledge_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        bh = float(bezel_height)
        blh = float(bearing_ledge_height)
    except (TypeError, ValueError):
        return err_payload("bezel_height and bearing_ledge_height must be numbers", "BAD_ARGS")

    if blh >= bh:
        return err_payload(
            f"bearing_ledge_height ({blh}) must be less than bezel_height ({bh})",
            "BAD_ARGS",
        )

    pattern_clean = (pattern or "lotus").strip().lower()
    if pattern_clean not in _VALID_BEZEL_PATTERNS:
        return err_payload(
            f"pattern must be one of {sorted(_VALID_BEZEL_PATTERNS)}; got {pattern!r}",
            "BAD_ARGS",
        )

    try:
        pc = int(petal_count)
    except (TypeError, ValueError):
        return err_payload("petal_count must be an integer", "BAD_ARGS")
    if pc < 3:
        return err_payload(f"petal_count must be >= 3; got {pc}", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_patterned_bezel")

    node = build_patterned_bezel_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        wall_thickness=float(wall_thickness),
        bezel_height=bh,
        bearing_ledge_height=blh,
        pattern=pattern_clean,
        petal_count=pc,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_patterned_bezel",
        "pattern": pattern_clean,
        "stone_diameter": float(stone_diameter),
        "petal_count": pc,
        "_outer_diameter": node["_outer_diameter"],
        "_petal_pitch_deg": node["_petal_pitch_deg"],
    })


# ===========================================================================
# TRELLIS / CROSS-PRONG SETTING
# ===========================================================================
#
# An interwoven prong basket where adjacent prong wires cross each other in
# an X-pattern, creating a trellis or cross-prong cage around the stone.
# Different from the trellis style of prong_head (which uses the same wires)
# in that each crossing point is explicitly parametrised and the wires actually
# interleave in 3D.
# ---------------------------------------------------------------------------

_VALID_TRELLIS_WEAVES = {"x_cross", "diagonal", "square"}


def build_trellis_prong_node(
    node_id: str,
    stone_diameter: float,
    prong_count: int,
    wire_gauge: float,
    prong_height: float,
    weave_style: str,
    cross_height: float,
) -> dict:
    """
    Compute the trellis / cross-prong basket node spec.

    The worker's opJewelryTrellisProng builds:
      - `prong_count` prong wires (must be even) of diameter `wire_gauge`
        arranged in pairs.  Each pair crosses its neighbour at `cross_height`
        above the bearing seat (measured from the girdle plane).
      - Weave styles control the crossing geometry:

        'x_cross'   — adjacent prong pairs form a clean X; wires pass over/under
                      alternately (plain weave).
        'diagonal'  — all crossing wires slant in the same direction (twill-
                      style), creating a diagonal hatching.
        'square'    — prongs run straight up but are connected at `cross_height`
                      by short cross-bars (square lattice — similar to cathedral
                      but horizontal).

    The base ring (below the bearing ledge) is a standard collet cylinder of
    outer diameter = `stone_diameter + 2 × wire_gauge`.

    Derived hints:
      _outer_diameter  — stone_diameter + 2 * wire_gauge.
      _cross_clearance — wire_gauge × 2 (minimum metal thickness at the cross
                         point before wires would merge).
      _prong_pitch_deg — 360 / prong_count.
    """
    outer_diameter = stone_diameter + 2.0 * wire_gauge
    cross_clearance = wire_gauge * 2.0
    prong_pitch_deg = 360.0 / prong_count if prong_count > 0 else 0.0

    return {
        "id": node_id,
        "op": "jewelry_trellis_prong",
        "stone_diameter": stone_diameter,
        "prong_count": prong_count,
        "wire_gauge": wire_gauge,
        "prong_height": prong_height,
        "weave_style": weave_style,
        "cross_height": cross_height,
        "_outer_diameter": round(outer_diameter, 4),
        "_cross_clearance": round(cross_clearance, 4),
        "_prong_pitch_deg": round(prong_pitch_deg, 4),
    }


jewelry_trellis_prong_spec = ToolSpec(
    name="jewelry_create_trellis_prong",
    description=(
        "Append a `jewelry_trellis_prong` node to a `.feature` file. "
        "Generates a trellis (cross-prong) basket setting — prong wires that "
        "cross each other in an interwoven pattern, forming a decorative cage "
        "around the stone. "
        "\n\nWeave styles:\n"
        "- **`x_cross`** — adjacent prong pairs form a clean X; wires pass "
        "over/under alternately (plain weave).\n"
        "- **`diagonal`** — all crossing wires slant the same direction (twill "
        "style), creating diagonal hatching.\n"
        "- **`square`** — straight prongs connected by horizontal cross-bars at "
        "`cross_height` (square lattice look).\n"
        "\n`prong_count` must be even (pairs cross each other). "
        "`cross_height` sets the height above the girdle plane where wires cross. "
        "Output: node spec consumed by opJewelryTrellisProng."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_diameter": {
                "type": "number",
                "description": "Girdle diameter of the stone in mm.",
            },
            "prong_count": {
                "type": "integer",
                "description": (
                    "Number of prong wires. Must be even (>= 4) so wires pair for crossing. "
                    "Typical: 4, 6, 8."
                ),
            },
            "wire_gauge": {
                "type": "number",
                "description": "Prong wire diameter in mm (typical 0.8–1.5).",
            },
            "prong_height": {
                "type": "number",
                "description": "Height the prong extends above the stone's girdle plane in mm.",
            },
            "weave_style": {
                "type": "string",
                "enum": sorted(_VALID_TRELLIS_WEAVES),
                "description": "Crossing/weave pattern. One of: diagonal, square, x_cross.",
            },
            "cross_height": {
                "type": "number",
                "description": (
                    "Height above the girdle plane at which adjacent prong wires cross, "
                    "in mm. Must be > 0 and < prong_height."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": [
            "file_id", "stone_diameter", "prong_count", "wire_gauge",
            "prong_height", "weave_style", "cross_height",
        ],
    },
)


@register(jewelry_trellis_prong_spec, write=True)
async def run_jewelry_create_trellis_prong(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_diameter = a.get("stone_diameter")
    prong_count = a.get("prong_count")
    wire_gauge = a.get("wire_gauge")
    prong_height = a.get("prong_height")
    weave_style = a.get("weave_style", "x_cross")
    cross_height = a.get("cross_height")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("stone_diameter", stone_diameter),
        ("wire_gauge", wire_gauge),
        ("prong_height", prong_height),
        ("cross_height", cross_height),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    try:
        pc = int(prong_count)
    except (TypeError, ValueError):
        return err_payload("prong_count must be an integer", "BAD_ARGS")
    if pc < 4:
        return err_payload(f"prong_count must be >= 4; got {pc}", "BAD_ARGS")
    if pc % 2 != 0:
        return err_payload(
            f"prong_count must be even for trellis crossing; got {pc}", "BAD_ARGS"
        )

    weave_style_clean = (weave_style or "x_cross").strip().lower()
    if weave_style_clean not in _VALID_TRELLIS_WEAVES:
        return err_payload(
            f"weave_style must be one of {sorted(_VALID_TRELLIS_WEAVES)}; got {weave_style!r}",
            "BAD_ARGS",
        )

    try:
        ph = float(prong_height)
        ch = float(cross_height)
    except (TypeError, ValueError):
        return err_payload("prong_height and cross_height must be numbers", "BAD_ARGS")

    if ch >= ph:
        return err_payload(
            f"cross_height ({ch}) must be less than prong_height ({ph})",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_trellis_prong")

    node = build_trellis_prong_node(
        node_id=node_id,
        stone_diameter=float(stone_diameter),
        prong_count=pc,
        wire_gauge=float(wire_gauge),
        prong_height=ph,
        weave_style=weave_style_clean,
        cross_height=ch,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_trellis_prong",
        "stone_diameter": float(stone_diameter),
        "prong_count": pc,
        "weave_style": weave_style_clean,
        "_outer_diameter": node["_outer_diameter"],
    })


# ===========================================================================
# BAR-CHANNEL HYBRID & GRADUATED ROW SETTING
# ===========================================================================
#
# A row of graduated (decreasing-size) stones held between pairs of vertical
# metal bars between each stone.  Combines the bar setting's clean look with
# a channel floor and supports a graduated stone sequence for tapered bands
# and eternity rings.
# ---------------------------------------------------------------------------

def _compute_graduated_row(
    stone_count: int,
    largest_diameter: float,
    smallest_diameter: float,
    stone_spacing: float,
) -> list:
    """
    Compute per-stone centre positions and diameters for a graduated row.

    Stones are arranged linearly along the X-axis.  Stone 0 is the largest,
    stone (stone_count - 1) is the smallest.  Sizes decrease linearly from
    `largest_diameter` to `smallest_diameter`.

    Returns a list of {"index": int, "diameter": float, "x_center": float}
    dicts.  x_center is measured from the left edge of the first stone (x=0).
    """
    if stone_count == 1:
        return [{"index": 0, "diameter": round(largest_diameter, 4), "x_center": round(largest_diameter / 2.0, 4)}]

    stones = []
    x = 0.0
    for i in range(stone_count):
        t = i / (stone_count - 1)  # 0 at first, 1 at last
        diameter = largest_diameter + t * (smallest_diameter - largest_diameter)
        radius = diameter / 2.0
        if i == 0:
            x_center = radius
        else:
            prev_radius = stones[-1]["diameter"] / 2.0
            x = stones[-1]["x_center"] + prev_radius + stone_spacing + radius
            x_center = x
        stones.append({
            "index": i,
            "diameter": round(diameter, 4),
            "x_center": round(x_center, 4),
        })
        x = x_center
    return stones


def build_bar_channel_graduated_node(
    node_id: str,
    stone_count: int,
    largest_diameter: float,
    smallest_diameter: float,
    stone_spacing: float,
    bar_width: float,
    bar_height: float,
    floor_thickness: float,
) -> dict:
    """
    Compute the bar-channel graduated-row node spec.

    The worker's opJewelryBarChannelGraduated builds:
      - A row of `stone_count` graduated stones.  Stone diameters decrease
        linearly from `largest_diameter` (first / centre stone) to
        `smallest_diameter` (last / end stone).
      - A pair of vertical metal bars between each adjacent stone pair (not
        rails running the full length; each bar is a separate pillar of width
        `bar_width` and height `bar_height`).  This gives individual framing
        between stones while preserving the bar look.
      - A channel floor of thickness `floor_thickness` running the full row
        length.

    The total row spans from x = 0 to x = last stone centre + last stone radius.

    Derived hints:
      _total_row_length  — overall X-extent of the graduated row.
      _bar_count         — (stone_count - 1) pairs of bars between stones.
      stones             — per-stone {index, diameter, x_center} list.
    """
    stones = _compute_graduated_row(
        stone_count=stone_count,
        largest_diameter=largest_diameter,
        smallest_diameter=smallest_diameter,
        stone_spacing=stone_spacing,
    )
    if stones:
        last = stones[-1]
        total_row_length = last["x_center"] + last["diameter"] / 2.0
    else:
        total_row_length = 0.0

    bar_count = max(0, stone_count - 1)

    return {
        "id": node_id,
        "op": "jewelry_bar_channel_graduated",
        "stone_count": stone_count,
        "largest_diameter": largest_diameter,
        "smallest_diameter": smallest_diameter,
        "stone_spacing": stone_spacing,
        "bar_width": bar_width,
        "bar_height": bar_height,
        "floor_thickness": floor_thickness,
        "stones": stones,
        "_total_row_length": round(total_row_length, 4),
        "_bar_count": bar_count,
        "_actual_stone_count": len(stones),
    }


jewelry_bar_channel_graduated_spec = ToolSpec(
    name="jewelry_create_bar_channel_graduated",
    description=(
        "Append a `jewelry_bar_channel_graduated` node to a `.feature` file. "
        "Generates a graduated-row setting combining bar separators and a channel "
        "floor — a row of stones that decreases in size from largest (centre) to "
        "smallest (ends), with a pair of metal bar pillars between each adjacent "
        "stone pair. "
        "Useful for tapered eternity bands, graduated diamond rows, and bypass rings "
        "where the stone sizes follow the ring taper. "
        "`stone_count` stones are sized linearly from `largest_diameter` to "
        "`smallest_diameter`; bars of `bar_width` × `bar_height` stand between "
        "each adjacent pair; a `floor_thickness` floor closes the bottom. "
        "The evaluate result includes `stones` — per-stone {index, diameter, "
        "x_center} for downstream boolean seat cutting. "
        "Output: node spec consumed by opJewelryBarChannelGraduated."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "stone_count": {
                "type": "integer",
                "description": "Number of stones in the graduated row. Must be >= 1.",
            },
            "largest_diameter": {
                "type": "number",
                "description": "Girdle diameter of the largest (first/centre) stone in mm.",
            },
            "smallest_diameter": {
                "type": "number",
                "description": (
                    "Girdle diameter of the smallest (last/end) stone in mm. "
                    "Must be <= largest_diameter."
                ),
            },
            "stone_spacing": {
                "type": "number",
                "description": "Edge-to-edge gap between adjacent stones in mm (typical 0.1–0.3).",
            },
            "bar_width": {
                "type": "number",
                "description": "Width (thickness) of each bar pillar between stones in mm (typical 0.4–1.0).",
            },
            "bar_height": {
                "type": "number",
                "description": "Height of the bar pillars above the stone seat in mm (typical 0.5–1.5).",
            },
            "floor_thickness": {
                "type": "number",
                "description": "Thickness of the channel floor in mm.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": [
            "file_id", "stone_count", "largest_diameter", "smallest_diameter",
            "stone_spacing", "bar_width", "bar_height", "floor_thickness",
        ],
    },
)


@register(jewelry_bar_channel_graduated_spec, write=True)
async def run_jewelry_create_bar_channel_graduated(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    stone_count = a.get("stone_count")
    largest_diameter = a.get("largest_diameter")
    smallest_diameter = a.get("smallest_diameter")
    stone_spacing = a.get("stone_spacing")
    bar_width = a.get("bar_width")
    bar_height = a.get("bar_height")
    floor_thickness = a.get("floor_thickness")
    node_id = a.get("id", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    for fname, fval in [
        ("largest_diameter", largest_diameter),
        ("bar_width", bar_width),
        ("bar_height", bar_height),
        ("floor_thickness", floor_thickness),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    # stone_spacing may be 0 (stones touching) — only forbid negative.
    try:
        ss = float(stone_spacing)
    except (TypeError, ValueError):
        return err_payload("stone_spacing must be a number", "BAD_ARGS")
    if ss < 0:
        return err_payload(f"stone_spacing must be >= 0; got {ss}", "BAD_ARGS")

    # smallest_diameter must be positive.
    err = _positive("smallest_diameter", smallest_diameter)
    if err:
        return err_payload(err, "BAD_ARGS")

    try:
        ld = float(largest_diameter)
        sd = float(smallest_diameter)
    except (TypeError, ValueError):
        return err_payload("largest_diameter and smallest_diameter must be numbers", "BAD_ARGS")

    if sd > ld:
        return err_payload(
            f"smallest_diameter ({sd}) must be <= largest_diameter ({ld})",
            "BAD_ARGS",
        )

    try:
        sc = int(stone_count)
    except (TypeError, ValueError):
        return err_payload("stone_count must be an integer", "BAD_ARGS")
    if sc < 1:
        return err_payload(f"stone_count must be >= 1; got {sc}", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_bar_channel_graduated")

    node = build_bar_channel_graduated_node(
        node_id=node_id,
        stone_count=sc,
        largest_diameter=ld,
        smallest_diameter=sd,
        stone_spacing=ss,
        bar_width=float(bar_width),
        bar_height=float(bar_height),
        floor_thickness=float(floor_thickness),
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_bar_channel_graduated",
        "stone_count": sc,
        "largest_diameter": ld,
        "smallest_diameter": sd,
        "_total_row_length": node["_total_row_length"],
        "_bar_count": node["_bar_count"],
    })
