"""tools.py — LLM-callable tool surface for kerf-woodworking.

Exposes the following tools to the Kerf LLM agent:

    woodworking_mortise_tenon   — design a mortise-and-tenon joint
    woodworking_dovetail        — design a dovetail joint
    woodworking_finger_joint    — design a box / finger joint
    woodworking_dowel           — design a dowel joint
    woodworking_biscuit         — design a biscuit / plate joint
    woodworking_pocket_screw    — design a pocket-screw joint
    woodworking_cut_list        — generate an optimised cut list
    woodworking_grain_check     — check grain direction on a joint descriptor
"""

from __future__ import annotations

import json
from typing import Any

from kerf_woodworking._compat import ToolSpec, err_payload, ok_payload, register
from kerf_woodworking.joinery import (
    biscuit,
    dovetail,
    dowel,
    finger_joint,
    mortise_tenon,
    pocket_screw,
)
from kerf_woodworking.cut_list import (
    BoardPiece,
    StockBoard,
    cut_list_to_dict,
    optimise_cut_list,
)
from kerf_woodworking.grain import add_grain_meta, check_grain


# ---------------------------------------------------------------------------
# Tool: woodworking_mortise_tenon
# ---------------------------------------------------------------------------

_mortise_tenon_spec = ToolSpec(
    name="woodworking_mortise_tenon",
    description=(
        "Design a mortise-and-tenon joint. Returns geometry, engaged volumes, "
        "and any grain warnings. Tenon and mortise volumes are equal when "
        "shoulder_gap_mm is 0."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tenon_width_mm":  {"type": "number", "description": "Tenon cheek width (mm)"},
            "tenon_height_mm": {"type": "number", "description": "Tenon height (mm)"},
            "tenon_depth_mm":  {"type": "number", "description": "Tenon engagement depth (mm)"},
            "shoulder_gap_mm": {"type": "number", "description": "Clearance per cheek face (mm, default 0.2)"},
            "shoulder_grain":  {"type": "string", "enum": ["along", "across", "diagonal", "any"],
                                "description": "Grain direction at tenon shoulder"},
        },
        "required": ["tenon_width_mm", "tenon_height_mm", "tenon_depth_mm"],
    },
)


@register(_mortise_tenon_spec, write=False)
async def woodworking_mortise_tenon(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    try:
        joint = mortise_tenon(
            tenon_width_mm=float(a["tenon_width_mm"]),
            tenon_height_mm=float(a["tenon_height_mm"]),
            tenon_depth_mm=float(a["tenon_depth_mm"]),
            shoulder_gap_mm=float(a.get("shoulder_gap_mm", 0.2)),
        )
        if "shoulder_grain" in a:
            add_grain_meta(joint, shoulder_grain=a["shoulder_grain"])
    except (KeyError, TypeError, ValueError) as e:
        return err_payload(str(e), "BAD_ARGS")
    return ok_payload(joint)


# ---------------------------------------------------------------------------
# Tool: woodworking_dovetail
# ---------------------------------------------------------------------------

_dovetail_spec = ToolSpec(
    name="woodworking_dovetail",
    description=(
        "Design a through or half-blind dovetail joint. Returns tail geometry "
        "and engagement depth."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "board_thickness_mm": {"type": "number"},
            "tail_count":         {"type": "integer", "description": "Number of tails (default 4)"},
            "tail_angle_deg":     {"type": "number",  "description": "Splay angle in degrees (default 8)"},
            "baseline_offset_mm": {"type": "number",  "description": "Baseline distance from face (default 3)"},
            "half_blind":         {"type": "boolean", "description": "Half-blind dovetail (default false)"},
            "lap_mm":             {"type": "number",  "description": "Front lap thickness (half-blind only)"},
            "board_grain":        {"type": "string",  "enum": ["along", "across", "diagonal", "any"]},
        },
        "required": ["board_thickness_mm"],
    },
)


@register(_dovetail_spec, write=False)
async def woodworking_dovetail(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    try:
        joint = dovetail(
            board_thickness_mm=float(a["board_thickness_mm"]),
            tail_count=int(a.get("tail_count", 4)),
            tail_angle_deg=float(a.get("tail_angle_deg", 8.0)),
            baseline_offset_mm=float(a.get("baseline_offset_mm", 3.0)),
            half_blind=bool(a.get("half_blind", False)),
            lap_mm=float(a["lap_mm"]) if "lap_mm" in a else None,
        )
        if "board_grain" in a:
            add_grain_meta(joint, board_grain=a["board_grain"])
    except (KeyError, TypeError, ValueError) as e:
        return err_payload(str(e), "BAD_ARGS")
    return ok_payload(joint)


# ---------------------------------------------------------------------------
# Tool: woodworking_finger_joint
# ---------------------------------------------------------------------------

_finger_joint_spec = ToolSpec(
    name="woodworking_finger_joint",
    description="Design a box / finger joint for a given board thickness.",
    input_schema={
        "type": "object",
        "properties": {
            "board_thickness_mm": {"type": "number"},
            "finger_width_mm":    {"type": "number", "description": "Finger width (default 10 mm)"},
            "kerf_mm":            {"type": "number", "description": "Router/saw kerf (default 3.175 mm)"},
        },
        "required": ["board_thickness_mm"],
    },
)


@register(_finger_joint_spec, write=False)
async def woodworking_finger_joint(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    try:
        joint = finger_joint(
            board_thickness_mm=float(a["board_thickness_mm"]),
            finger_width_mm=float(a.get("finger_width_mm", 10.0)),
            kerf_mm=float(a.get("kerf_mm", 3.175)),
        )
    except (KeyError, TypeError, ValueError) as e:
        return err_payload(str(e), "BAD_ARGS")
    return ok_payload(joint)


# ---------------------------------------------------------------------------
# Tool: woodworking_dowel
# ---------------------------------------------------------------------------

_dowel_spec = ToolSpec(
    name="woodworking_dowel",
    description="Design a dowel joint.",
    input_schema={
        "type": "object",
        "properties": {
            "diameter_mm": {"type": "number", "description": "Dowel diameter (default 8 mm)"},
            "length_mm":   {"type": "number", "description": "Total dowel length (default 40 mm)"},
            "count":       {"type": "integer", "description": "Number of dowels (default 2)"},
            "spacing_mm":  {"type": "number", "description": "Centre-to-centre spacing"},
        },
    },
)


@register(_dowel_spec, write=False)
async def woodworking_dowel(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    try:
        joint = dowel(
            diameter_mm=float(a.get("diameter_mm", 8.0)),
            length_mm=float(a.get("length_mm", 40.0)),
            count=int(a.get("count", 2)),
            spacing_mm=float(a["spacing_mm"]) if "spacing_mm" in a else None,
        )
    except (KeyError, TypeError, ValueError) as e:
        return err_payload(str(e), "BAD_ARGS")
    return ok_payload(joint)


# ---------------------------------------------------------------------------
# Tool: woodworking_biscuit
# ---------------------------------------------------------------------------

_biscuit_spec = ToolSpec(
    name="woodworking_biscuit",
    description="Design a biscuit (plate) joint. Standard sizes: #0, #10, #20.",
    input_schema={
        "type": "object",
        "properties": {
            "size":       {"type": "string", "enum": ["#0", "#10", "#20"],
                           "description": "Biscuit size (default #20)"},
            "count":      {"type": "integer", "description": "Number of biscuits (default 3)"},
            "spacing_mm": {"type": "number",  "description": "Centre-to-centre spacing"},
        },
    },
)


@register(_biscuit_spec, write=False)
async def woodworking_biscuit(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    try:
        joint = biscuit(
            size=a.get("size", "#20"),
            count=int(a.get("count", 3)),
            spacing_mm=float(a["spacing_mm"]) if "spacing_mm" in a else None,
        )
    except (KeyError, TypeError, ValueError) as e:
        return err_payload(str(e), "BAD_ARGS")
    return ok_payload(joint)


# ---------------------------------------------------------------------------
# Tool: woodworking_pocket_screw
# ---------------------------------------------------------------------------

_pocket_screw_spec = ToolSpec(
    name="woodworking_pocket_screw",
    description="Design a pocket-screw (Kreg-style) joint.",
    input_schema={
        "type": "object",
        "properties": {
            "board_thickness_mm": {"type": "number", "description": "Pocket board thickness (default 19 mm)"},
            "screw_diameter_mm":  {"type": "number", "description": "Screw diameter (default 4.5 mm)"},
            "screw_length_mm":    {"type": "number", "description": "Total screw length (default 32 mm)"},
            "count":              {"type": "integer", "description": "Number of screws (default 2)"},
            "spacing_mm":         {"type": "number",  "description": "Centre-to-centre spacing"},
            "target_grain":       {"type": "string",  "enum": ["along", "across", "end", "any"],
                                   "description": "Grain direction of the receiving board"},
        },
    },
)


@register(_pocket_screw_spec, write=False)
async def woodworking_pocket_screw(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    try:
        joint = pocket_screw(
            board_thickness_mm=float(a.get("board_thickness_mm", 19.0)),
            screw_diameter_mm=float(a.get("screw_diameter_mm", 4.5)),
            screw_length_mm=float(a.get("screw_length_mm", 32.0)),
            count=int(a.get("count", 2)),
            spacing_mm=float(a["spacing_mm"]) if "spacing_mm" in a else None,
        )
        if "target_grain" in a:
            add_grain_meta(joint, target_grain=a["target_grain"])
    except (KeyError, TypeError, ValueError) as e:
        return err_payload(str(e), "BAD_ARGS")
    return ok_payload(joint)


# ---------------------------------------------------------------------------
# Tool: woodworking_cut_list
# ---------------------------------------------------------------------------

_cut_list_spec = ToolSpec(
    name="woodworking_cut_list",
    description=(
        "Generate an optimised cut list (1-D guillotine bin-packing) from a "
        "bill-of-boards and stock size. Returns piece assignments, waste, "
        "utilisation percentage, and off-cut lengths."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pieces": {
                "type": "array",
                "description": "List of required pieces",
                "items": {
                    "type": "object",
                    "properties": {
                        "label":           {"type": "string"},
                        "length_mm":       {"type": "number"},
                        "quantity":        {"type": "integer"},
                        "grain_direction": {"type": "string"},
                    },
                    "required": ["label", "length_mm"],
                },
            },
            "stock_length_mm": {"type": "number", "description": "Uniform stock board length (mm)"},
            "kerf_mm":         {"type": "number", "description": "Saw kerf (default 3.175 mm)"},
            "allow_grain_mismatch": {"type": "boolean"},
        },
        "required": ["pieces", "stock_length_mm"],
    },
)


@register(_cut_list_spec, write=False)
async def woodworking_cut_list(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    try:
        pieces_raw = a.get("pieces", [])
        if not isinstance(pieces_raw, list):
            return err_payload("pieces must be an array", "BAD_ARGS")

        pieces = [
            BoardPiece(
                label=p["label"],
                length_mm=float(p["length_mm"]),
                quantity=int(p.get("quantity", 1)),
                grain_direction=p.get("grain_direction", "along"),
            )
            for p in pieces_raw
        ]

        result = optimise_cut_list(
            pieces,
            stock_length_mm=float(a["stock_length_mm"]),
            kerf_mm=float(a.get("kerf_mm", 3.175)),
            allow_grain_mismatch=bool(a.get("allow_grain_mismatch", False)),
        )
    except (KeyError, TypeError, ValueError) as e:
        return err_payload(str(e), "BAD_ARGS")
    return ok_payload(cut_list_to_dict(result))


# ---------------------------------------------------------------------------
# Tool: woodworking_grain_check
# ---------------------------------------------------------------------------

_grain_check_spec = ToolSpec(
    name="woodworking_grain_check",
    description=(
        "Check grain-direction metadata on a joint descriptor dict. "
        "Returns a list of grain warnings."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "joint": {
                "type": "object",
                "description": "Joint descriptor as returned by any woodworking joint tool",
            },
        },
        "required": ["joint"],
    },
)


@register(_grain_check_spec, write=False)
async def woodworking_grain_check(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    joint = a.get("joint")
    if not isinstance(joint, dict):
        return err_payload("joint must be an object", "BAD_ARGS")
    warnings = check_grain(joint)
    return ok_payload({"warnings": warnings})
