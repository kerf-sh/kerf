"""
kerf_cad_core.surveying.tools — LLM tool wrappers for land surveying / COGO.

Registers tools with the Kerf tool registry:

  surveying_forward           — compute new point from azimuth + distance
  surveying_inverse           — azimuth + distance between two points
  surveying_traverse          — closed-traverse misclosure report
  surveying_traverse_adjust   — Compass/Transit traverse adjustment
  surveying_area_coordinates  — area from coordinate list (Shoelace)
  surveying_area_dmd          — area from Double Meridian Distance method
  surveying_dms_to_dd         — DMS → decimal degrees
  surveying_dd_to_dms         — decimal degrees → DMS
  surveying_bearing_azimuth   — bearing ↔ azimuth conversion
  surveying_poi               — point of intersection from two azimuth rays
  surveying_resection         — three-point resection (Tienstra)
  surveying_level_loop        — level-loop adjustment

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Wolf & Ghilani, "Elementary Surveying", 14th ed.
Bannister, Raymond, Baker, "Surveying", 7th ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.surveying.cogo import (
    dms_to_dd,
    dd_to_dms,
    bearing_to_azimuth,
    azimuth_to_bearing,
    forward,
    inverse,
    traverse_misclosure,
    traverse_adjust,
    area_by_coordinates,
    area_by_dmd,
    line_line_intersection,
    line_circle_intersection,
    point_of_intersection,
    resection,
    level_loop_adjust,
)


# ---------------------------------------------------------------------------
# Tool: surveying_dms_to_dd
# ---------------------------------------------------------------------------

_dms_to_dd_spec = ToolSpec(
    name="surveying_dms_to_dd",
    description=(
        "Convert a degrees-minutes-seconds angle to decimal degrees.\n"
        "\n"
        "Useful for entering survey angles in DMS notation and converting\n"
        "to the decimal form required by other surveying tools.\n"
        "\n"
        "Errors: {ok:false, reason} for out-of-range minutes/seconds. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "degrees": {
                "type": "number",
                "description": "Degrees component (may be negative for south/west).",
            },
            "minutes": {
                "type": "number",
                "description": "Minutes component. Must be in [0, 60).",
            },
            "seconds": {
                "type": "number",
                "description": "Seconds component. Must be in [0, 60).",
            },
        },
        "required": ["degrees", "minutes", "seconds"],
    },
)


@register(_dms_to_dd_spec, write=False)
async def run_dms_to_dd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("degrees", "minutes", "seconds"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = dms_to_dd(a["degrees"], a["minutes"], a["seconds"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_dd_to_dms
# ---------------------------------------------------------------------------

_dd_to_dms_spec = ToolSpec(
    name="surveying_dd_to_dms",
    description=(
        "Convert a decimal-degrees angle to degrees-minutes-seconds.\n"
        "\n"
        "Errors: {ok:false, reason} for non-finite input. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dd": {
                "type": "number",
                "description": "Angle in decimal degrees.",
            },
        },
        "required": ["dd"],
    },
)


@register(_dd_to_dms_spec, write=False)
async def run_dd_to_dms(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("dd") is None:
        return json.dumps({"ok": False, "reason": "dd is required"})
    result = dd_to_dms(a["dd"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_bearing_azimuth
# ---------------------------------------------------------------------------

_bearing_azimuth_spec = ToolSpec(
    name="surveying_bearing_azimuth",
    description=(
        "Convert between reduced bearing and whole-circle azimuth.\n"
        "\n"
        "Mode 'to_azimuth': supply quadrant ('NE'/'SE'/'SW'/'NW') and\n"
        "bearing_dd (0, 90] → returns azimuth_dd in [0, 360).\n"
        "\n"
        "Mode 'to_bearing': supply azimuth_dd → returns quadrant and\n"
        "bearing_dd plus a formatted string like 'N45°30\\'00\"E'.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["to_azimuth", "to_bearing"],
                "description": "Conversion direction.",
            },
            "quadrant": {
                "type": "string",
                "enum": ["NE", "SE", "SW", "NW"],
                "description": "Required when mode='to_azimuth'.",
            },
            "bearing_dd": {
                "type": "number",
                "description": "Bearing in (0, 90]. Required when mode='to_azimuth'.",
            },
            "azimuth_dd": {
                "type": "number",
                "description": "Whole-circle azimuth [0, 360). Required when mode='to_bearing'.",
            },
        },
        "required": ["mode"],
    },
)


@register(_bearing_azimuth_spec, write=False)
async def run_bearing_azimuth(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    mode = a.get("mode")
    if mode not in ("to_azimuth", "to_bearing"):
        return json.dumps({"ok": False, "reason": "mode must be 'to_azimuth' or 'to_bearing'"})
    if mode == "to_azimuth":
        q = a.get("quadrant")
        b = a.get("bearing_dd")
        if q is None:
            return json.dumps({"ok": False, "reason": "quadrant is required for mode='to_azimuth'"})
        if b is None:
            return json.dumps({"ok": False, "reason": "bearing_dd is required for mode='to_azimuth'"})
        result = bearing_to_azimuth(q, b)
    else:
        az = a.get("azimuth_dd")
        if az is None:
            return json.dumps({"ok": False, "reason": "azimuth_dd is required for mode='to_bearing'"})
        result = azimuth_to_bearing(az)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_forward
# ---------------------------------------------------------------------------

_forward_spec = ToolSpec(
    name="surveying_forward",
    description=(
        "Compute the coordinates of a new point given a starting point,\n"
        "whole-circle azimuth, and horizontal distance (polar → rectangular).\n"
        "\n"
        "Returns northing, easting, delta_N, delta_E.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "northing": {
                "type": "number",
                "description": "Starting point northing (m).",
            },
            "easting": {
                "type": "number",
                "description": "Starting point easting (m).",
            },
            "azimuth_dd": {
                "type": "number",
                "description": "Whole-circle azimuth in decimal degrees.",
            },
            "distance": {
                "type": "number",
                "description": "Horizontal distance (m). Must be >= 0.",
            },
        },
        "required": ["northing", "easting", "azimuth_dd", "distance"],
    },
)


@register(_forward_spec, write=False)
async def run_forward(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("northing", "easting", "azimuth_dd", "distance"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = forward(a["northing"], a["easting"], a["azimuth_dd"], a["distance"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_inverse
# ---------------------------------------------------------------------------

_inverse_spec = ToolSpec(
    name="surveying_inverse",
    description=(
        "Compute the azimuth and horizontal distance between two points\n"
        "(rectangular → polar conversion).\n"
        "\n"
        "Returns azimuth_dd, distance, delta_N, delta_E, quadrant, bearing_str.\n"
        "\n"
        "Errors: {ok:false, reason} if points are coincident. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "n1": {"type": "number", "description": "From-point northing (m)."},
            "e1": {"type": "number", "description": "From-point easting (m)."},
            "n2": {"type": "number", "description": "To-point northing (m)."},
            "e2": {"type": "number", "description": "To-point easting (m)."},
        },
        "required": ["n1", "e1", "n2", "e2"],
    },
)


@register(_inverse_spec, write=False)
async def run_inverse(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("n1", "e1", "n2", "e2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = inverse(a["n1"], a["e1"], a["n2"], a["e2"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_traverse
# ---------------------------------------------------------------------------

_traverse_spec = ToolSpec(
    name="surveying_traverse",
    description=(
        "Compute the linear misclosure and precision ratio for a closed\n"
        "traverse.\n"
        "\n"
        "Each leg requires 'azimuth_dd' (decimal degrees) and 'distance' (m).\n"
        "A UserWarning is issued (not raised) if precision is worse than\n"
        "the tolerance ratio.\n"
        "\n"
        "Returns closure_N, closure_E, linear_misclosure, traverse_length,\n"
        "precision_ratio, precision_ok, and per-leg delta_N / delta_E.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "legs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "azimuth_dd": {"type": "number"},
                        "distance": {"type": "number"},
                    },
                    "required": ["azimuth_dd", "distance"],
                },
                "description": "List of traverse legs.",
            },
            "tolerance": {
                "type": "number",
                "description": (
                    "Acceptable precision ratio (default 1/5000 = 0.0002). "
                    "A warning is issued if exceeded."
                ),
            },
        },
        "required": ["legs"],
    },
)


@register(_traverse_spec, write=False)
async def run_traverse(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    legs = a.get("legs")
    if not legs:
        return json.dumps({"ok": False, "reason": "legs is required and must not be empty"})
    kwargs: dict = {}
    if "tolerance" in a:
        kwargs["tolerance"] = a["tolerance"]
    result = traverse_misclosure(legs, **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_traverse_adjust
# ---------------------------------------------------------------------------

_traverse_adjust_spec = ToolSpec(
    name="surveying_traverse_adjust",
    description=(
        "Adjust a closed traverse using the Compass (Bowditch) or Transit rule.\n"
        "\n"
        "Each leg requires 'azimuth_dd' and 'distance'.\n"
        "\n"
        "method='compass' (default): corrections proportional to leg distance.\n"
        "method='transit':           corrections proportional to |latitude|/|departure|.\n"
        "\n"
        "Returns adjusted_legs (with corrected delta_N/delta_E), cumulative\n"
        "station coordinates, and closure before/after adjustment.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "legs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "azimuth_dd": {"type": "number"},
                        "distance": {"type": "number"},
                    },
                    "required": ["azimuth_dd", "distance"],
                },
                "description": "List of traverse legs.",
            },
            "method": {
                "type": "string",
                "enum": ["compass", "transit"],
                "description": "Adjustment method (default 'compass').",
            },
            "tolerance": {
                "type": "number",
                "description": "Precision warning threshold (default 1/5000).",
            },
        },
        "required": ["legs"],
    },
)


@register(_traverse_adjust_spec, write=False)
async def run_traverse_adjust(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    legs = a.get("legs")
    if not legs:
        return json.dumps({"ok": False, "reason": "legs is required and must not be empty"})
    kwargs: dict = {}
    if "method" in a:
        kwargs["method"] = a["method"]
    if "tolerance" in a:
        kwargs["tolerance"] = a["tolerance"]
    result = traverse_adjust(legs, **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_area_coordinates
# ---------------------------------------------------------------------------

_area_coords_spec = ToolSpec(
    name="surveying_area_coordinates",
    description=(
        "Compute the area of a closed polygon using the coordinate (Shoelace /\n"
        "Gauss) formula.\n"
        "\n"
        "Each point requires 'northing' and 'easting' (m).\n"
        "Minimum 3 points required.\n"
        "\n"
        "Returns area_m2 in square metres.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "northing": {"type": "number"},
                        "easting": {"type": "number"},
                    },
                    "required": ["northing", "easting"],
                },
                "description": "Polygon vertices (at least 3).",
            },
        },
        "required": ["points"],
    },
)


@register(_area_coords_spec, write=False)
async def run_area_coordinates(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    points = a.get("points")
    if not points:
        return json.dumps({"ok": False, "reason": "points is required"})
    result = area_by_coordinates(points)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_area_dmd
# ---------------------------------------------------------------------------

_area_dmd_spec = ToolSpec(
    name="surveying_area_dmd",
    description=(
        "Compute the area of a closed traverse polygon using the Double\n"
        "Meridian Distance (DMD) method.\n"
        "\n"
        "Each point requires 'northing' and 'easting' (m).\n"
        "Minimum 3 points required.\n"
        "\n"
        "Returns area_m2 and per-leg DMD contributions.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "northing": {"type": "number"},
                        "easting": {"type": "number"},
                    },
                    "required": ["northing", "easting"],
                },
                "description": "Polygon vertices (at least 3).",
            },
        },
        "required": ["points"],
    },
)


@register(_area_dmd_spec, write=False)
async def run_area_dmd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    points = a.get("points")
    if not points:
        return json.dumps({"ok": False, "reason": "points is required"})
    result = area_by_dmd(points)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_poi
# ---------------------------------------------------------------------------

_poi_spec = ToolSpec(
    name="surveying_poi",
    description=(
        "Compute the point of intersection of two azimuth rays, each emitted\n"
        "from a known station.\n"
        "\n"
        "Provide azimuth1_dd, n1, e1 for station 1 and azimuth2_dd, n2, e2\n"
        "for station 2.\n"
        "\n"
        "Returns northing, easting, distance_from_1, distance_from_2.\n"
        "\n"
        "Errors: {ok:false, reason} if rays are parallel. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "azimuth1_dd": {"type": "number", "description": "Azimuth from station 1 (decimal degrees)."},
            "n1": {"type": "number", "description": "Station 1 northing (m)."},
            "e1": {"type": "number", "description": "Station 1 easting (m)."},
            "azimuth2_dd": {"type": "number", "description": "Azimuth from station 2 (decimal degrees)."},
            "n2": {"type": "number", "description": "Station 2 northing (m)."},
            "e2": {"type": "number", "description": "Station 2 easting (m)."},
        },
        "required": ["azimuth1_dd", "n1", "e1", "azimuth2_dd", "n2", "e2"],
    },
)


@register(_poi_spec, write=False)
async def run_poi(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("azimuth1_dd", "n1", "e1", "azimuth2_dd", "n2", "e2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = point_of_intersection(
        a["azimuth1_dd"], a["n1"], a["e1"],
        a["azimuth2_dd"], a["n2"], a["e2"],
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_resection
# ---------------------------------------------------------------------------

_resection_spec = ToolSpec(
    name="surveying_resection",
    description=(
        "Compute the position of an unknown instrument station from horizontal\n"
        "angle observations to three known control points (Tienstra method).\n"
        "\n"
        "p_known: list of 3 dicts with 'northing' and 'easting' (m).\n"
        "obs_angles: [alpha, beta] in decimal degrees:\n"
        "  alpha = horizontal angle A→instrument→B\n"
        "  beta  = horizontal angle B→instrument→C\n"
        "\n"
        "Returns northing and easting of the instrument station.\n"
        "\n"
        "Errors: {ok:false, reason} for degenerate geometry (danger circle).\n"
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_known": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "northing": {"type": "number"},
                        "easting": {"type": "number"},
                    },
                    "required": ["northing", "easting"],
                },
                "description": "Exactly 3 known control points [A, B, C].",
            },
            "obs_angles": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Exactly 2 observed angles [alpha, beta] in decimal degrees.",
            },
        },
        "required": ["p_known", "obs_angles"],
    },
)


@register(_resection_spec, write=False)
async def run_resection(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    p_known = a.get("p_known")
    obs_angles = a.get("obs_angles")
    if not p_known:
        return json.dumps({"ok": False, "reason": "p_known is required"})
    if not obs_angles:
        return json.dumps({"ok": False, "reason": "obs_angles is required"})
    result = resection(p_known, obs_angles)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: surveying_level_loop
# ---------------------------------------------------------------------------

_level_loop_spec = ToolSpec(
    name="surveying_level_loop",
    description=(
        "Adjust a closed level loop by distributing the elevation misclosure\n"
        "proportionally to each leg's sight distance.\n"
        "\n"
        "Each observation requires 'distance' (m) and 'delta_h' (m, +ve = rise).\n"
        "known_elev is the benchmark elevation in metres.\n"
        "\n"
        "Returns misclosure, adjusted elevations at each station, and\n"
        "per-observation corrections.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "distance": {"type": "number"},
                        "delta_h": {"type": "number"},
                    },
                    "required": ["distance", "delta_h"],
                },
                "description": "Level loop observations.",
            },
            "known_elev": {
                "type": "number",
                "description": "Starting benchmark elevation (m).",
            },
        },
        "required": ["observations", "known_elev"],
    },
)


@register(_level_loop_spec, write=False)
async def run_level_loop(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    observations = a.get("observations")
    known_elev = a.get("known_elev")
    if not observations:
        return json.dumps({"ok": False, "reason": "observations is required"})
    if known_elev is None:
        return json.dumps({"ok": False, "reason": "known_elev is required"})
    result = level_loop_adjust(observations, known_elev)
    return ok_payload(result) if result.get("ok") else json.dumps(result)
