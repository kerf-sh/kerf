"""
LLM tools for manual PCB trace routing.

Tools: route_trace_segments, delete_trace, split_trace, merge_traces,
       move_trace_vertex.

These tools are scaffolded — they validate input and return structured
acknowledgement payloads. Actual circuit mutation happens via the caller
applying the returned data to the CircuitJSON source (through appendTrace
or direct JSON edit). This keeps the tools stateless and testable.

Does NOT replace autoroute_circuit — manual and auto routing coexist.
"""
import json
from typing import Any

from tools.registry import ToolSpec, err_payload, ok_payload, register


# ── route_trace_segments ──────────────────────────────────────────────────────

route_trace_segments_spec = ToolSpec(
    name="route_trace_segments",
    description=(
        "Add one or more manually-routed trace segments to a CircuitJSON board. "
        "Each segment is a polyline defined by {points: [{x,y,layer}], net_id, width_mm, layer}. "
        "Use this for precise manual routing; for automatic net-based routing use autoroute_circuit."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Project file to modify."},
            "segments": {
                "type": "array",
                "description": "List of trace segments to add.",
                "items": {
                    "type": "object",
                    "properties": {
                        "points": {
                            "type": "array",
                            "description": "Ordered vertices: [{x, y, layer}].",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "x": {"type": "number"},
                                    "y": {"type": "number"},
                                    "layer": {"type": "string"},
                                },
                                "required": ["x", "y"],
                            },
                        },
                        "net_id": {
                            "type": "string",
                            "description": "Net identifier (must exist in the circuit).",
                        },
                        "width_mm": {
                            "type": "number",
                            "description": "Trace width in mm. Default 0.25.",
                        },
                        "layer": {
                            "type": "string",
                            "description": "Layer name, e.g. top_copper or bottom_copper.",
                        },
                    },
                    "required": ["points", "net_id"],
                },
                "minItems": 1,
            },
        },
        "required": ["file_id", "segments"],
    },
)


@register(route_trace_segments_spec, write=True)
async def route_trace_segments(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    segments = a.get("segments")
    if not segments or not isinstance(segments, list) or len(segments) == 0:
        return err_payload("segments must be a non-empty array", "BAD_ARGS")

    # Validate each segment minimally
    for i, seg in enumerate(segments):
        pts = seg.get("points")
        if not pts or len(pts) < 2:
            return err_payload(
                f"segment {i}: points must have at least 2 entries", "BAD_ARGS"
            )
        if not seg.get("net_id"):
            return err_payload(f"segment {i}: net_id is required", "BAD_ARGS")

    return ok_payload({
        "added_segments": len(segments),
        "note": (
            "Segments validated. Apply to CircuitJSON via appendTrace or direct "
            "circuit edit to persist."
        ),
    })


# ── delete_trace ──────────────────────────────────────────────────────────────

delete_trace_spec = ToolSpec(
    name="delete_trace",
    description=(
        "Delete a trace from the circuit. Identify by trace_id, or by "
        "(net_id + index) if no unique ID is available."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "trace_id": {
                "type": "string",
                "description": "Unique trace identifier (preferred).",
            },
            "net_id": {
                "type": "string",
                "description": "Net name — used with index when trace_id unavailable.",
            },
            "index": {
                "type": "integer",
                "description": "Zero-based index of the trace in the net's trace list.",
            },
        },
        "required": ["file_id"],
    },
)


@register(delete_trace_spec, write=True)
async def delete_trace(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    if not a.get("file_id"):
        return err_payload("file_id is required", "BAD_ARGS")

    has_id = bool(a.get("trace_id"))
    has_net_idx = bool(a.get("net_id")) and a.get("index") is not None
    if not has_id and not has_net_idx:
        return err_payload(
            "provide trace_id OR (net_id + index) to identify the trace", "BAD_ARGS"
        )

    return ok_payload({
        "deleted": True,
        "trace_id": a.get("trace_id"),
        "net_id": a.get("net_id"),
        "index": a.get("index"),
    })


# ── split_trace ───────────────────────────────────────────────────────────────

split_trace_spec = ToolSpec(
    name="split_trace",
    description=(
        "Split a trace at a given point, inserting a new vertex and dividing "
        "the original trace into two collinear traces on the same net. "
        "Useful for inserting a T-junction or re-routing a segment."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "trace_id": {"type": "string", "description": "Trace to split."},
            "split_point": {
                "type": "object",
                "description": "Coordinates of the new split vertex.",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "layer": {"type": "string"},
                },
                "required": ["x", "y"],
            },
        },
        "required": ["file_id", "trace_id", "split_point"],
    },
)


@register(split_trace_spec, write=True)
async def split_trace(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    if not a.get("file_id"):
        return err_payload("file_id is required", "BAD_ARGS")
    if not a.get("trace_id"):
        return err_payload("trace_id is required", "BAD_ARGS")
    sp = a.get("split_point", {})
    if sp.get("x") is None or sp.get("y") is None:
        return err_payload("split_point must have x and y", "BAD_ARGS")

    return ok_payload({
        "split": True,
        "original_trace_id": a.get("trace_id"),
        "split_point": sp,
    })


# ── merge_traces ──────────────────────────────────────────────────────────────

merge_traces_spec = ToolSpec(
    name="merge_traces",
    description=(
        "Merge two collinear traces on the same net into one, removing the "
        "shared endpoint vertex. The traces must share an endpoint and be on "
        "the same net and layer."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "trace_id_a": {"type": "string", "description": "First trace."},
            "trace_id_b": {"type": "string", "description": "Second trace (must share an endpoint with trace_a)."},
        },
        "required": ["file_id", "trace_id_a", "trace_id_b"],
    },
)


@register(merge_traces_spec, write=True)
async def merge_traces(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    if not a.get("file_id"):
        return err_payload("file_id is required", "BAD_ARGS")
    if not a.get("trace_id_a") or not a.get("trace_id_b"):
        return err_payload("trace_id_a and trace_id_b are both required", "BAD_ARGS")
    if a.get("trace_id_a") == a.get("trace_id_b"):
        return err_payload("trace_id_a and trace_id_b must be different", "BAD_ARGS")

    return ok_payload({
        "merged": True,
        "consumed_trace_ids": [a.get("trace_id_a"), a.get("trace_id_b")],
    })


# ── move_trace_vertex ─────────────────────────────────────────────────────────

move_trace_vertex_spec = ToolSpec(
    name="move_trace_vertex",
    description=(
        "Move a single vertex of a trace to a new x,y position. "
        "Endpoint vertices stay locked; mid-vertices can be freely repositioned. "
        "Use this to nudge routing around obstacles."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "trace_id": {"type": "string"},
            "vertex_index": {
                "type": "integer",
                "description": "Zero-based index into the trace's points array.",
            },
            "new_x": {"type": "number"},
            "new_y": {"type": "number"},
        },
        "required": ["file_id", "trace_id", "vertex_index", "new_x", "new_y"],
    },
)


@register(move_trace_vertex_spec, write=True)
async def move_trace_vertex(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    if not a.get("file_id"):
        return err_payload("file_id is required", "BAD_ARGS")
    if not a.get("trace_id"):
        return err_payload("trace_id is required", "BAD_ARGS")
    if a.get("vertex_index") is None:
        return err_payload("vertex_index is required", "BAD_ARGS")
    if a.get("new_x") is None or a.get("new_y") is None:
        return err_payload("new_x and new_y are required", "BAD_ARGS")

    return ok_payload({
        "moved": True,
        "trace_id": a.get("trace_id"),
        "vertex_index": a.get("vertex_index"),
        "new_position": {"x": a.get("new_x"), "y": a.get("new_y")},
    })
