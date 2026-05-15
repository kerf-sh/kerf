"""
Automated gem-seat boolean.

Algorithm
---------
A gem seat (setting/bearing) is the void cut into a host solid (ring shank,
bezel) so the gemstone can be set.  The cutter geometry is:

  1. Bearing cone  — a truncated cone whose upper radius = (girdle_mm/2 +
     girdle_clearance) and whose half-angle = pavilion_angle_deg.  Depth =
     pavilion_depth_mm + culet_clearance.
  2. Girdle ledge  — a thin cylinder of height = girdle_mm + seat_allowance
     at radius = girdle_mm/2 + girdle_clearance, forming the bearing ledge
     the girdle rests on.
  3. Culet hole    — optional through-hole (radius = culet_radius) for light
     ingress and setting tool access (through-set or bead-set).  For flush /
     gypsy settings, omit.
  4. Crown relief  — a slight countersink taper at the top of the seat to
     allow the girdle to seat flush; half-angle = crown_angle_deg / 2.

The resulting cutter solid is emitted as a `gem_seat` feature node.  The
caller is expected to follow with a `feature_boolean` cut (A=host, B=seat_id,
kind="cut") to subtract the seat from the host.  The tool optionally emits
both the seat node AND the boolean cut node in one call when
`auto_cut_host_id` is provided.

Coordinate system
-----------------
The seat is generated centred at `position` (default [0,0,0]) with the table
(top) of the gemstone facing +Z.  Rotate via `orientation_deg` if the stone
is tipped (e.g. a tilted princess in a bypass ring).

Geometry dimensions (pure Python, no OCC required)
---------------------------------------------------
seat_geometry() returns a dict that can be used by the OCCT worker's
opGemSeat to build the actual TopoDS_Shape, OR used directly by tests to
validate clearance math without OCC.

LLM-facing tools
----------------
  jewelry_cut_gem_seat  — emit a gem_seat node (+ optional boolean cut)
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import (
    read_feature_content,
    append_feature_node,
    next_node_id,
)
from kerf_cad_core.jewelry.gemstones import (
    GEMSTONE_CUTS,
    gemstone_proportions,
    carat_from_mm,
    mm_from_carat,
)


# ---------------------------------------------------------------------------
# Seat geometry calculator (pure Python — no OCC dependency)
# ---------------------------------------------------------------------------

def seat_geometry(
    cut: str,
    diameter_mm: float,
    *,
    pavilion_angle_deg: float,
    pavilion_depth_pct: float,
    girdle_pct: float,
    crown_angle_deg: float,
    # Clearances (mm)
    girdle_clearance_mm: float = 0.05,
    culet_clearance_mm: float  = 0.1,
    seat_allowance_mm: float   = 0.02,
    crown_relief_mm: float     = 0.3,
    # Optional through-hole
    through_hole: bool = False,
    through_hole_radius_mm: Optional[float] = None,
) -> dict:
    """Return a pure-Python dict describing the gem-seat cutter geometry.

    Parameters
    ----------
    cut                : gemstone cut name (for aspect-ratio awareness)
    diameter_mm        : girdle diameter (or long axis for non-round)
    pavilion_angle_deg : pavilion half-angle (degrees from vertical)
    pavilion_depth_pct : pavilion depth as % of diameter_mm
    girdle_pct         : girdle thickness as % of diameter_mm
    crown_angle_deg    : crown angle (used for relief taper)
    girdle_clearance_mm: radial clearance around girdle for setting movement
    culet_clearance_mm : extra depth below pavilion tip for culet/tool room
    seat_allowance_mm  : axial allowance on girdle ledge height
    crown_relief_mm    : depth of crown-relief countersink above girdle
    through_hole       : if True, add a cylindrical through-hole
    through_hole_radius_mm: radius of through-hole (default = culet estimate)

    Returns
    -------
    dict with keys:
        girdle_radius_mm          — outer radius of girdle ledge (diameter/2 + clearance)
        pavilion_depth_mm         — pavilion depth absolute
        pavilion_angle_deg        — passed-through
        girdle_height_mm          — axial height of the girdle ledge
        bearing_cone_half_angle   — half-angle of bearing cone (= pavilion_angle_deg)
        bearing_cone_top_radius   — top radius of bearing cone
        bearing_cone_bottom_radius— bottom (culet) radius of bearing cone
        culet_depth_mm            — extra depth below pavilion tip
        crown_relief_depth_mm     — depth of crown countersink
        crown_relief_half_angle   — half-angle of crown countersink taper
        through_hole              — bool
        through_hole_radius_mm    — radius of through-hole (0 if not enabled)
        total_cutter_depth_mm     — total axial depth of cutter solid
    """
    r_girdle = diameter_mm / 2.0 + girdle_clearance_mm
    pav_depth = diameter_mm * pavilion_depth_pct / 100.0
    gird_height = diameter_mm * girdle_pct / 100.0 + seat_allowance_mm

    # Bearing cone
    # The cone apex is at the culet; half-angle = pavilion_angle_deg from vertical.
    # top_radius at the girdle plane:
    bearing_top_r = r_girdle
    # bottom (culet) radius; for brilliant cuts culet is a point or tiny flat
    culet_r = diameter_mm * 0.005   # ~0.5% = tiny flat

    crown_relief_half_angle = crown_angle_deg / 2.0

    if through_hole:
        thr = through_hole_radius_mm if through_hole_radius_mm else max(0.3, culet_r)
    else:
        thr = 0.0

    total_depth = pav_depth + culet_clearance_mm + gird_height + crown_relief_mm

    return {
        "girdle_radius_mm":           round(r_girdle, 4),
        "pavilion_depth_mm":          round(pav_depth, 4),
        "pavilion_angle_deg":         round(pavilion_angle_deg, 3),
        "girdle_height_mm":           round(gird_height, 4),
        "bearing_cone_half_angle":    round(pavilion_angle_deg, 3),
        "bearing_cone_top_radius":    round(bearing_top_r, 4),
        "bearing_cone_bottom_radius": round(culet_r, 4),
        "culet_depth_mm":             round(culet_clearance_mm, 4),
        "crown_relief_depth_mm":      round(crown_relief_mm, 4),
        "crown_relief_half_angle":    round(crown_relief_half_angle, 3),
        "through_hole":               through_hole,
        "through_hole_radius_mm":     round(thr, 4),
        "total_cutter_depth_mm":      round(total_depth, 4),
    }


# ---------------------------------------------------------------------------
# LLM tool: jewelry_cut_gem_seat
# ---------------------------------------------------------------------------

jewelry_cut_gem_seat_spec = ToolSpec(
    name="jewelry_cut_gem_seat",
    description=(
        "Append a `gem_seat` node to a `.feature` file. "
        "Generates a gem-seat cutter solid (bearing cone + girdle ledge + optional "
        "through-hole for light) parameterised from the gemstone's cut and size. "
        "The seat cutter is positioned at `position` with `orientation_deg` rotation. "
        "If `auto_cut_host_id` is provided, a `boolean` cut node is also appended "
        "so the seat is immediately subtracted from the host solid — this is the "
        "most common single-step workflow. "
        "Without auto_cut_host_id, call feature_boolean manually: "
        "  feature_boolean(file_id, target_a_id=<host>, target_b_id=<seat_id>, kind='cut'). "
        "Seat geometry algorithm: "
        "  1. Bearing cone  — truncated cone, half-angle = pavilion_angle, "
        "     top_radius = girdle_radius + girdle_clearance, depth = pavilion_depth + culet_clearance. "
        "  2. Girdle ledge  — thin cylinder of height = girdle_mm + seat_allowance. "
        "  3. Crown relief  — countersink taper (crown_angle/2) of depth crown_relief_mm. "
        "  4. Optional through-hole for light ingress (through_hole=true). "
        "The OCCT worker's opGemSeat assembles these primitives into a single closed "
        "TopoDS_Solid cutter."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "cut": {
                "type": "string",
                "enum": sorted(GEMSTONE_CUTS),
                "description": "Gemstone cut to match. Used for default proportions.",
            },
            "carat": {
                "type": "number",
                "description": "Stone weight in carats (converted to mm). Provide carat OR diameter_mm.",
            },
            "diameter_mm": {
                "type": "number",
                "description": "Primary dimension in mm. Provide diameter_mm OR carat.",
            },
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y, z] seat centre in model space (mm). Default [0,0,0].",
            },
            "orientation_deg": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[rx, ry, rz] Euler angles (degrees). Default [0,0,0].",
            },
            "girdle_clearance_mm": {
                "type": "number",
                "description": "Radial clearance around girdle (mm). Default 0.05.",
            },
            "culet_clearance_mm": {
                "type": "number",
                "description": "Extra depth below pavilion tip (mm). Default 0.10.",
            },
            "seat_allowance_mm": {
                "type": "number",
                "description": "Axial allowance on girdle ledge height (mm). Default 0.02.",
            },
            "crown_relief_mm": {
                "type": "number",
                "description": "Depth of crown-relief countersink above girdle (mm). Default 0.30.",
            },
            "through_hole": {
                "type": "boolean",
                "description": "Add a cylindrical through-hole for light ingress. Default false.",
            },
            "through_hole_radius_mm": {
                "type": "number",
                "description": "Through-hole radius (mm). Default: culet estimate. Requires through_hole=true.",
            },
            "auto_cut_host_id": {
                "type": "string",
                "description": (
                    "If set, append a boolean cut node subtracting the seat from this "
                    "host feature node id immediately after the seat node. "
                    "Equivalent to running feature_boolean(kind='cut', "
                    "target_a_id=auto_cut_host_id, target_b_id=<new_seat_id>)."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id for the gem_seat node.",
            },
        },
        "required": ["file_id", "cut"],
    },
)


@register(jewelry_cut_gem_seat_spec, write=True)
async def run_jewelry_cut_gem_seat(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str          = a.get("file_id", "").strip()
    cut                  = a.get("cut", "").strip()
    carat                = a.get("carat", None)
    diameter_mm          = a.get("diameter_mm", None)
    position             = a.get("position", None)
    orientation_deg      = a.get("orientation_deg", None)
    girdle_clearance_mm  = a.get("girdle_clearance_mm", 0.05)
    culet_clearance_mm   = a.get("culet_clearance_mm", 0.10)
    seat_allowance_mm    = a.get("seat_allowance_mm", 0.02)
    crown_relief_mm      = a.get("crown_relief_mm", 0.30)
    through_hole         = a.get("through_hole", False)
    through_hole_radius  = a.get("through_hole_radius_mm", None)
    auto_cut_host_id     = a.get("auto_cut_host_id", "").strip()
    node_id              = a.get("id", "").strip()

    # --- Validation ---
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if not cut:
        return err_payload("cut is required", "BAD_ARGS")
    if cut not in GEMSTONE_CUTS:
        return err_payload(
            f"Unknown cut {cut!r}. Valid cuts: {sorted(GEMSTONE_CUTS)}", "BAD_ARGS"
        )

    if carat is not None and diameter_mm is not None:
        return err_payload("Provide carat OR diameter_mm, not both", "BAD_ARGS")
    if carat is None and diameter_mm is None:
        return err_payload("One of carat or diameter_mm is required", "BAD_ARGS")

    if carat is not None:
        try:
            carat = float(carat)
        except Exception:
            return err_payload("carat must be a number", "BAD_ARGS")
        if carat <= 0:
            return err_payload("carat must be positive", "BAD_ARGS")

    if diameter_mm is not None:
        try:
            diameter_mm = float(diameter_mm)
        except Exception:
            return err_payload("diameter_mm must be a number", "BAD_ARGS")
        if diameter_mm <= 0:
            return err_payload("diameter_mm must be positive", "BAD_ARGS")

    for name, val in [
        ("girdle_clearance_mm", girdle_clearance_mm),
        ("culet_clearance_mm",  culet_clearance_mm),
        ("seat_allowance_mm",   seat_allowance_mm),
        ("crown_relief_mm",     crown_relief_mm),
    ]:
        try:
            val = float(val)
        except Exception:
            return err_payload(f"{name} must be a number", "BAD_ARGS")
        if val < 0:
            return err_payload(f"{name} must be >= 0", "BAD_ARGS")

    if through_hole_radius is not None:
        try:
            through_hole_radius = float(through_hole_radius)
        except Exception:
            return err_payload("through_hole_radius_mm must be a number", "BAD_ARGS")
        if through_hole_radius <= 0:
            return err_payload("through_hole_radius_mm must be positive", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    # Resolve proportions
    try:
        props = gemstone_proportions(cut, diameter_mm=diameter_mm, carat=carat)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    # Compute seat geometry
    geom = seat_geometry(
        cut=cut,
        diameter_mm=props.diameter_mm,
        pavilion_angle_deg=props.pavilion_angle_deg,
        pavilion_depth_pct=props.pavilion_depth_pct,
        girdle_pct=props.girdle_pct,
        crown_angle_deg=props.crown_angle_deg,
        girdle_clearance_mm=float(girdle_clearance_mm),
        culet_clearance_mm=float(culet_clearance_mm),
        seat_allowance_mm=float(seat_allowance_mm),
        crown_relief_mm=float(crown_relief_mm),
        through_hole=bool(through_hole),
        through_hole_radius_mm=through_hole_radius,
    )

    if not node_id:
        node_id = next_node_id(content, "gem_seat")

    seat_node: dict = {
        "id": node_id,
        "op": "gem_seat",
        "cut": cut,
        "diameter_mm": props.diameter_mm,
        **geom,
    }
    if position is not None:
        seat_node["position"] = position
    if orientation_deg is not None:
        seat_node["orientation_deg"] = orientation_deg

    # Re-read latest content before first append (content may have changed
    # if caller already added nodes this request; use the fetched copy).
    _name, seat_nid, err2 = append_feature_node(ctx, fid, seat_node)
    if err2:
        return err_payload(err2, "ERROR")

    result: dict = {
        "file_id": file_id_str,
        "seat_id": seat_nid,
        "op": "gem_seat",
        "cut": cut,
        "diameter_mm": props.diameter_mm,
        "total_cutter_depth_mm": geom["total_cutter_depth_mm"],
    }

    # Auto-cut boolean
    if auto_cut_host_id:
        # Re-read after seat node was written
        content2, err3 = read_feature_content(ctx, fid)
        if err3:
            # Seat was written but boolean can't be chained; surface warning
            result["warning"] = f"seat written but auto_cut failed: {err3}"
            return ok_payload(result)

        bool_node_id = next_node_id(content2, "boolean")
        bool_node = {
            "id": bool_node_id,
            "op": "boolean",
            "target_a_id": auto_cut_host_id,
            "target_b_id": seat_nid,
            "kind": "cut",
        }
        _bname, bool_nid, err4 = append_feature_node(ctx, fid, bool_node)
        if err4:
            result["warning"] = f"seat written but auto_cut boolean failed: {err4}"
        else:
            result["boolean_id"] = bool_nid

    return ok_payload(result)
