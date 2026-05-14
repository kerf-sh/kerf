"""
LLM tools for copper pour / ground plane management.

Tools: add_copper_pour, delete_copper_pour, set_pour_net.

These tools are scaffolded — they validate input and return structured
payloads. The actual pour fill is computed by pyworker POST /compute-pour-fill
(using shapely). Frontend triggers a rebuild via useEffect when pours/traces/
pads change.
"""
import json
from typing import Any

from tools.registry import ToolSpec, err_payload, ok_payload, register


# ── add_copper_pour ───────────────────────────────────────────────────────────

add_copper_pour_spec = ToolSpec(
    name="add_copper_pour",
    description=(
        "Add a copper pour (filled zone / ground plane) to a CircuitJSON board. "
        "A pour is a polygon on a copper layer connected to a chosen net (e.g. GND). "
        "The fill is computed by the backend: clearance around non-net traces/pads is "
        "subtracted; same-net pads get thermal-relief spokes. "
        "After calling this tool, trigger a pour rebuild via POST /compute-pour-fill."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "pour": {
                "type": "object",
                "description": "Copper pour definition.",
                "properties": {
                    "polygon": {
                        "type": "array",
                        "description": "Boundary vertices: [{x, y}]. Minimum 3 points.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                            "required": ["x", "y"],
                        },
                        "minItems": 3,
                    },
                    "layer": {
                        "type": "string",
                        "description": "Copper layer: top_copper | bottom_copper | inner_1 | ...",
                        "enum": ["top_copper", "bottom_copper", "inner_1", "inner_2"],
                    },
                    "net_id": {
                        "type": "string",
                        "description": "Net to connect the pour to (e.g. GND, VCC).",
                    },
                    "clearance_mm": {
                        "type": "number",
                        "description": "Clearance around non-net objects in mm. Default 0.25.",
                    },
                    "thermal_relief": {
                        "type": "object",
                        "description": "Thermal spoke parameters for same-net pad connections.",
                        "properties": {
                            "gap": {"type": "number"},
                            "spoke_width": {"type": "number"},
                            "spoke_count": {"type": "integer"},
                        },
                    },
                    "min_thickness_mm": {
                        "type": "number",
                        "description": "Minimum copper strip width. Narrower areas are removed. Default 0.2.",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Higher priority pours take precedence over lower ones at overlap. Default 0.",
                    },
                },
                "required": ["polygon", "layer", "net_id"],
            },
        },
        "required": ["file_id", "pour"],
    },
)


@register(add_copper_pour_spec, write=True)
async def add_copper_pour(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    if not a.get("file_id"):
        return err_payload("file_id is required", "BAD_ARGS")

    pour = a.get("pour")
    if not pour or not isinstance(pour, dict):
        return err_payload("pour object is required", "BAD_ARGS")

    polygon = pour.get("polygon", [])
    if not isinstance(polygon, list) or len(polygon) < 3:
        return err_payload("polygon must have at least 3 points", "BAD_ARGS")

    if not pour.get("layer"):
        return err_payload("layer is required (e.g. top_copper)", "BAD_ARGS")

    if not pour.get("net_id"):
        return err_payload("net_id is required (e.g. GND)", "BAD_ARGS")

    return ok_payload({
        "added": True,
        "net_id": pour.get("net_id"),
        "layer": pour.get("layer"),
        "vertex_count": len(polygon),
        "clearance_mm": pour.get("clearance_mm", 0.25),
        "note": "Pour added. Trigger POST /compute-pour-fill to compute the fill geometry.",
    })


# ── delete_copper_pour ────────────────────────────────────────────────────────

delete_copper_pour_spec = ToolSpec(
    name="delete_copper_pour",
    description=(
        "Delete a copper pour from a CircuitJSON board. "
        "Identify by pour_index (zero-based position in the copper_pours array) "
        "or by net_id + layer combination."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "pour_index": {
                "type": "integer",
                "description": "Zero-based index into the copper_pours array.",
            },
            "net_id": {
                "type": "string",
                "description": "Net name — combined with layer to identify the pour.",
            },
            "layer": {
                "type": "string",
                "description": "Layer name — combined with net_id to identify the pour.",
            },
        },
        "required": ["file_id"],
    },
)


@register(delete_copper_pour_spec, write=True)
async def delete_copper_pour(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    if not a.get("file_id"):
        return err_payload("file_id is required", "BAD_ARGS")

    has_index = a.get("pour_index") is not None
    has_net_layer = bool(a.get("net_id")) and bool(a.get("layer"))
    if not has_index and not has_net_layer:
        return err_payload(
            "provide pour_index OR (net_id + layer) to identify the pour",
            "BAD_ARGS",
        )

    return ok_payload({
        "deleted": True,
        "pour_index": a.get("pour_index"),
        "net_id": a.get("net_id"),
        "layer": a.get("layer"),
    })


# ── set_pour_net ──────────────────────────────────────────────────────────────

set_pour_net_spec = ToolSpec(
    name="set_pour_net",
    description=(
        "Change the net assignment of an existing copper pour. "
        "After updating, trigger POST /compute-pour-fill to recompute the fill "
        "with the new clearance rules."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "pour_index": {
                "type": "integer",
                "description": "Zero-based index of the pour in copper_pours.",
            },
            "net_id": {
                "type": "string",
                "description": "New net identifier (e.g. GND, VCC, NET1).",
            },
        },
        "required": ["file_id", "pour_index", "net_id"],
    },
)


@register(set_pour_net_spec, write=True)
async def set_pour_net(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    if not a.get("file_id"):
        return err_payload("file_id is required", "BAD_ARGS")
    if a.get("pour_index") is None:
        return err_payload("pour_index is required", "BAD_ARGS")
    if not a.get("net_id"):
        return err_payload("net_id is required", "BAD_ARGS")

    return ok_payload({
        "updated": True,
        "pour_index": a.get("pour_index"),
        "net_id": a.get("net_id"),
        "note": "Net updated. Trigger POST /compute-pour-fill to recompute fill.",
    })
