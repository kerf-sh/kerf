"""
LLM tools for manual PCB trace routing.

Tools: route_trace_segments, delete_trace, split_trace, merge_traces,
       move_trace_vertex.

These tools accept and return `circuit_json` dicts — the caller passes the
current parsed CircuitJSON and receives the mutated copy. No database I/O
occurs inside these helpers; the executor writes the result back via
write_file / edit_file.

Does NOT replace autoroute_circuit — manual and auto routing coexist.
"""
import json
import math
import uuid
from copy import deepcopy
from typing import Any

from tools.registry import ToolSpec, err_payload, ok_payload, register

# ─── internal geometry helpers ───────────────────────────────────────────────

def _dist(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _pt_eq(a: dict, b: dict, tol: float = 1e-6) -> bool:
    return abs(a["x"] - b["x"]) <= tol and abs(a["y"] - b["y"]) <= tol


def _project_onto_segment(p: dict, a: dict, b: dict) -> float:
    """Return t in [0,1]: projection of p onto segment a→b."""
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    len_sq = dx * dx + dy * dy
    if len_sq == 0:
        return 0.0
    t = ((p["x"] - a["x"]) * dx + (p["y"] - a["y"]) * dy) / len_sq
    return max(0.0, min(1.0, t))


def _point_to_segment_dist(p: dict, a: dict, b: dict) -> float:
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    len_sq = dx * dx + dy * dy
    if len_sq == 0:
        return _dist(p, a)
    t = _project_onto_segment(p, a, b)
    closest = {"x": a["x"] + t * dx, "y": a["y"] + t * dy}
    return _dist(p, closest)


def _new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex[:8]}"


def _get_traces(circuit_json: dict) -> list:
    """Return the traces list from any of the known CircuitJSON shapes."""
    # tscircuit pcb_traces lives under circuit_json directly or under
    # circuit_json["pcb_traces"] / circuit_json["traces"]
    for key in ("pcb_traces", "traces"):
        val = circuit_json.get(key)
        if isinstance(val, list):
            return val
    return []


def _set_traces(circuit_json: dict, traces: list) -> None:
    for key in ("pcb_traces", "traces"):
        if key in circuit_json:
            circuit_json[key] = traces
            return
    circuit_json["pcb_traces"] = traces


def _trace_points(trace: dict) -> list:
    """Normalise trace point access (supports route/points/vertices)."""
    for key in ("route", "points", "vertices"):
        pts = trace.get(key)
        if pts is not None:
            return pts
    return []


def _set_trace_points(trace: dict, pts: list) -> None:
    for key in ("route", "points", "vertices"):
        if key in trace:
            trace[key] = pts
            return
    trace["route"] = pts


# ─── route_trace_segments ─────────────────────────────────────────────────────

route_trace_segments_spec = ToolSpec(
    name="route_trace_segments",
    description=(
        "Add one or more manually-routed trace segments to a CircuitJSON board. "
        "Pass the parsed circuit_json; receive the updated circuit_json with new "
        "traces appended. Each segment is {p1:{x,y}, p2:{x,y}, layer, width_mm, net_id}. "
        "For automatic net-based routing use autoroute_circuit instead."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "object",
                "description": "Parsed CircuitJSON board object.",
            },
            "segments": {
                "type": "array",
                "description": "Segments to route. Each has p1, p2, layer, width_mm, net_id.",
                "items": {
                    "type": "object",
                    "properties": {
                        "p1": {
                            "type": "object",
                            "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                            "required": ["x", "y"],
                        },
                        "p2": {
                            "type": "object",
                            "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                            "required": ["x", "y"],
                        },
                        "layer": {"type": "string"},
                        "width_mm": {"type": "number"},
                        "net_id": {"type": "string"},
                    },
                    "required": ["p1", "p2", "net_id"],
                },
                "minItems": 1,
            },
            "layer": {"type": "string", "description": "Default layer if not per-segment."},
            "width_mm": {"type": "number", "description": "Default width if not per-segment."},
            "net_id": {"type": "string", "description": "Default net_id if not per-segment."},
        },
        "required": ["circuit_json", "segments"],
    },
)


@register(route_trace_segments_spec, write=True)
async def route_trace_segments(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, dict):
        return err_payload("circuit_json must be an object", "BAD_ARGS")

    segments = a.get("segments")
    if not isinstance(segments, list) or len(segments) == 0:
        return err_payload("segments must be a non-empty array", "BAD_ARGS")

    default_layer = a.get("layer", "top_copper")
    default_width = a.get("width_mm", 0.25)
    default_net = a.get("net_id", "")

    cj = deepcopy(circuit_json)
    traces = _get_traces(cj)
    added_ids = []

    for i, seg in enumerate(segments):
        p1 = seg.get("p1")
        p2 = seg.get("p2")
        if not p1 or not p2:
            return err_payload(f"segment {i}: p1 and p2 are required", "BAD_ARGS")
        net_id = seg.get("net_id") or default_net
        if not net_id:
            return err_payload(f"segment {i}: net_id is required", "BAD_ARGS")
        layer = seg.get("layer") or default_layer
        width_mm = seg.get("width_mm") if seg.get("width_mm") is not None else default_width

        tid = _new_trace_id()
        trace = {
            "type": "pcb_trace",
            "pcb_trace_id": tid,
            "net_id": net_id,
            "route": [
                {"route_type": "wire", "x": p1["x"], "y": p1["y"], "width": width_mm, "layer": layer},
                {"route_type": "wire", "x": p2["x"], "y": p2["y"], "width": width_mm, "layer": layer},
            ],
        }
        traces.append(trace)
        added_ids.append(tid)

    _set_traces(cj, traces)
    return ok_payload({"circuit_json": cj, "added_trace_ids": added_ids})


# ─── delete_trace ─────────────────────────────────────────────────────────────

delete_trace_spec = ToolSpec(
    name="delete_trace",
    description=(
        "Delete a trace from the circuit by trace_id. "
        "Pass circuit_json; receive updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "trace_id": {"type": "string", "description": "Unique trace identifier."},
            "net_id": {"type": "string"},
            "index": {"type": "integer"},
        },
        "required": ["circuit_json"],
    },
)


@register(delete_trace_spec, write=True)
async def delete_trace(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, dict):
        return err_payload("circuit_json must be an object", "BAD_ARGS")

    trace_id = a.get("trace_id")
    net_id = a.get("net_id")
    index = a.get("index")

    has_id = bool(trace_id)
    has_net_idx = bool(net_id) and index is not None
    if not has_id and not has_net_idx:
        return err_payload(
            "provide trace_id OR (net_id + index) to identify the trace", "BAD_ARGS"
        )

    cj = deepcopy(circuit_json)
    traces = _get_traces(cj)

    if has_id:
        before = len(traces)
        traces = [
            t for t in traces
            if t.get("pcb_trace_id") != trace_id
            and t.get("id") != trace_id
            and t.get("trace_id") != trace_id
        ]
        if len(traces) == before:
            return err_payload(f"trace_id '{trace_id}' not found", "NOT_FOUND")
    else:
        # Find by net_id + index
        net_traces = [t for t in traces if t.get("net_id") == net_id]
        if index >= len(net_traces):
            return err_payload(f"index {index} out of range for net '{net_id}'", "BAD_ARGS")
        target = net_traces[index]
        traces = [t for t in traces if t is not target]

    _set_traces(cj, traces)
    return ok_payload({"circuit_json": cj, "deleted": True, "trace_id": trace_id})


# ─── split_trace ──────────────────────────────────────────────────────────────

split_trace_spec = ToolSpec(
    name="split_trace",
    description=(
        "Split a trace at a given point, inserting a new vertex and dividing "
        "the original trace into two collinear traces on the same net. "
        "Pass circuit_json; receive updated circuit_json with the split applied."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "trace_id": {"type": "string"},
            "point": {
                "type": "object",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                },
                "required": ["x", "y"],
            },
        },
        "required": ["circuit_json", "trace_id", "point"],
    },
)


@register(split_trace_spec, write=True)
async def split_trace(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, dict):
        return err_payload("circuit_json must be an object", "BAD_ARGS")
    trace_id = a.get("trace_id")
    if not trace_id:
        return err_payload("trace_id is required", "BAD_ARGS")
    point = a.get("point", {})
    if point.get("x") is None or point.get("y") is None:
        return err_payload("point must have x and y", "BAD_ARGS")

    cj = deepcopy(circuit_json)
    traces = _get_traces(cj)

    # Find the target trace
    target_idx = None
    target = None
    for i, t in enumerate(traces):
        tid = t.get("pcb_trace_id") or t.get("id") or t.get("trace_id")
        if tid == trace_id:
            target_idx = i
            target = t
            break

    if target is None:
        return err_payload(f"trace_id '{trace_id}' not found", "NOT_FOUND")

    pts = _trace_points(target)
    if len(pts) < 2:
        return err_payload("trace has fewer than 2 points", "BAD_ARGS")

    p = point
    tol = 0.1

    best_seg = -1
    best_dist = float("inf")
    for i in range(len(pts) - 1):
        a_pt = pts[i]
        b_pt = pts[i + 1]
        d = _point_to_segment_dist(p, a_pt, b_pt)
        if d < best_dist:
            best_dist = d
            best_seg = i

    if best_seg == -1 or best_dist > tol:
        return err_payload(
            f"point is not within {tol}mm of any segment of trace '{trace_id}'",
            "NOT_ON_TRACE",
        )

    seg_a = pts[best_seg]
    seg_b = pts[best_seg + 1]
    t_val = _project_onto_segment(p, seg_a, seg_b)
    snap = {
        "route_type": seg_a.get("route_type", "wire"),
        "x": seg_a["x"] + t_val * (seg_b["x"] - seg_a["x"]),
        "y": seg_a["y"] + t_val * (seg_b["y"] - seg_a["y"]),
        "width": seg_a.get("width", 0.25),
        "layer": seg_a.get("layer", "top_copper"),
    }

    # Don't split at endpoints
    if _pt_eq(snap, seg_a, tol) or _pt_eq(snap, seg_b, tol):
        return err_payload("split point coincides with an existing vertex", "BAD_ARGS")

    net_id = target.get("net_id", "")
    id_a = _new_trace_id()
    id_b = _new_trace_id()

    trace_a = deepcopy(target)
    trace_a["pcb_trace_id"] = id_a
    _set_trace_points(trace_a, pts[: best_seg + 1] + [snap])

    trace_b = deepcopy(target)
    trace_b["pcb_trace_id"] = id_b
    _set_trace_points(trace_b, [snap] + pts[best_seg + 1 :])

    # Replace original with the two halves
    traces = traces[:target_idx] + [trace_a, trace_b] + traces[target_idx + 1 :]
    _set_traces(cj, traces)

    return ok_payload({
        "circuit_json": cj,
        "original_trace_id": trace_id,
        "trace_id_a": id_a,
        "trace_id_b": id_b,
        "split_point": {"x": snap["x"], "y": snap["y"]},
    })


# ─── merge_traces ─────────────────────────────────────────────────────────────

merge_traces_spec = ToolSpec(
    name="merge_traces",
    description=(
        "Merge two traces on the same net that share an endpoint into one trace, "
        "removing the duplicate vertex. Pass circuit_json; receive updated circuit_json."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "trace_ids": {
                "type": "array",
                "description": "IDs of the two traces to merge.",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2,
            },
        },
        "required": ["circuit_json", "trace_ids"],
    },
)


@register(merge_traces_spec, write=True)
async def merge_traces(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, dict):
        return err_payload("circuit_json must be an object", "BAD_ARGS")

    trace_ids = a.get("trace_ids")
    if not isinstance(trace_ids, list) or len(trace_ids) != 2:
        return err_payload("trace_ids must be an array of exactly 2 ids", "BAD_ARGS")

    id_a, id_b = trace_ids
    if id_a == id_b:
        return err_payload("trace_ids must be different", "BAD_ARGS")

    cj = deepcopy(circuit_json)
    traces = _get_traces(cj)

    def find_trace(tid):
        for i, t in enumerate(traces):
            key = t.get("pcb_trace_id") or t.get("id") or t.get("trace_id")
            if key == tid:
                return i, t
        return None, None

    idx_a, tr_a = find_trace(id_a)
    idx_b, tr_b = find_trace(id_b)

    if tr_a is None:
        return err_payload(f"trace '{id_a}' not found", "NOT_FOUND")
    if tr_b is None:
        return err_payload(f"trace '{id_b}' not found", "NOT_FOUND")

    if tr_a.get("net_id") != tr_b.get("net_id"):
        return err_payload("traces are on different nets — cannot merge", "NET_MISMATCH")

    pts_a = _trace_points(tr_a)
    pts_b = _trace_points(tr_b)

    if len(pts_a) < 2 or len(pts_b) < 2:
        return err_payload("both traces need at least 2 points", "BAD_ARGS")

    tol = 0.1
    merged_pts = None

    if _pt_eq(pts_a[-1], pts_b[0], tol):
        merged_pts = pts_a + pts_b[1:]
    elif _pt_eq(pts_a[0], pts_b[-1], tol):
        merged_pts = pts_b + pts_a[1:]
    elif _pt_eq(pts_a[-1], pts_b[-1], tol):
        merged_pts = pts_a + list(reversed(pts_b))[1:]
    elif _pt_eq(pts_a[0], pts_b[0], tol):
        merged_pts = list(reversed(pts_a)) + pts_b[1:]
    else:
        return err_payload("traces do not share an endpoint", "NO_SHARED_ENDPOINT")

    new_id = _new_trace_id()
    merged_trace = deepcopy(tr_a)
    merged_trace["pcb_trace_id"] = new_id
    _set_trace_points(merged_trace, merged_pts)

    # Remove both originals, append merged
    keep = [t for t in traces if t is not tr_a and t is not tr_b]
    keep.append(merged_trace)
    _set_traces(cj, keep)

    return ok_payload({
        "circuit_json": cj,
        "merged_trace_id": new_id,
        "consumed_trace_ids": [id_a, id_b],
    })


# ─── move_trace_vertex ────────────────────────────────────────────────────────

move_trace_vertex_spec = ToolSpec(
    name="move_trace_vertex",
    description=(
        "Move a single vertex of a trace to a new x,y position. "
        "Pass circuit_json; receive updated circuit_json with the vertex repositioned."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "trace_id": {"type": "string"},
            "vertex_index": {
                "type": "integer",
                "description": "Zero-based index into the trace's route/points array.",
            },
            "new_point": {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"],
            },
        },
        "required": ["circuit_json", "trace_id", "vertex_index", "new_point"],
    },
)


@register(move_trace_vertex_spec, write=True)
async def move_trace_vertex(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, dict):
        return err_payload("circuit_json must be an object", "BAD_ARGS")
    trace_id = a.get("trace_id")
    if not trace_id:
        return err_payload("trace_id is required", "BAD_ARGS")
    vertex_index = a.get("vertex_index")
    if vertex_index is None:
        return err_payload("vertex_index is required", "BAD_ARGS")
    new_point = a.get("new_point", {})
    if new_point.get("x") is None or new_point.get("y") is None:
        return err_payload("new_point must have x and y", "BAD_ARGS")

    cj = deepcopy(circuit_json)
    traces = _get_traces(cj)

    target = None
    for t in traces:
        tid = t.get("pcb_trace_id") or t.get("id") or t.get("trace_id")
        if tid == trace_id:
            target = t
            break

    if target is None:
        return err_payload(f"trace_id '{trace_id}' not found", "NOT_FOUND")

    pts = _trace_points(target)
    if vertex_index < 0 or vertex_index >= len(pts):
        return err_payload(
            f"vertex_index {vertex_index} out of range (trace has {len(pts)} points)",
            "BAD_ARGS",
        )

    pts = list(pts)  # copy
    pts[vertex_index] = {
        **pts[vertex_index],
        "x": new_point["x"],
        "y": new_point["y"],
    }
    _set_trace_points(target, pts)
    _set_traces(cj, traces)

    return ok_payload({
        "circuit_json": cj,
        "moved": True,
        "trace_id": trace_id,
        "vertex_index": vertex_index,
        "new_position": {"x": new_point["x"], "y": new_point["y"]},
    })
