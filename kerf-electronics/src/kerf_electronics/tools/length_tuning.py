"""
LLM tools for KiCad-style PCB trace length tuning and differential-pair skew
compensation.

CircuitJSON extensions used:
  pcb_trace.target_length_mm    — annotation for desired trace length
  board.differential_pairs      — defined by buses agent (accessed defensively)

Tools:
  set_trace_target_length   — annotate a trace with a target length
  tune_trace_to_target      — apply a meander to reach target_length_mm
  match_diff_pair           — lengthen shorter trace of a diff pair
  report_diff_pair_skew     — report current skew for a diff pair
"""

import json
import math
from copy import deepcopy
from typing import Any

from tools.registry import ToolSpec, err_payload, ok_payload, register


# ── Internal geometry helpers ─────────────────────────────────────────────────

def _dist(a: dict, b: dict) -> float:
    dx = b["x"] - a["x"]
    dy = b["y"] - a["y"]
    return math.sqrt(dx * dx + dy * dy)


def _unit(a: dict, b: dict) -> dict:
    d = _dist(a, b)
    if d < 1e-12:
        return {"x": 1.0, "y": 0.0}
    return {"x": (b["x"] - a["x"]) / d, "y": (b["y"] - a["y"]) / d}


def _perp(u: dict) -> dict:
    """CCW 90° perpendicular of a unit vector."""
    return {"x": -u["y"], "y": u["x"]}


def _lerp(a: dict, b: dict, t: float) -> dict:
    return {"x": a["x"] + (b["x"] - a["x"]) * t, "y": a["y"] + (b["y"] - a["y"]) * t}


# ── Internal CircuitJSON helpers ──────────────────────────────────────────────

def _elements(circuit_json) -> list:
    if isinstance(circuit_json, list):
        return circuit_json
    return [circuit_json]


def _get_board(elements: list) -> dict | None:
    for e in elements:
        if isinstance(e, dict) and e.get("type") == "pcb_board":
            return e
    return None


def _get_traces(elements: list) -> list:
    return [e for e in elements if isinstance(e, dict) and e.get("type") == "pcb_trace"]


# ── Core math: trace length ───────────────────────────────────────────────────

def _trace_length(trace: dict) -> float:
    pts = trace.get("points") or []
    if len(pts) < 2:
        return 0.0
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


# ── Core math: meander generation ────────────────────────────────────────────

def _generate_meander(
    start: dict,
    end: dict,
    target_length: float,
    style: str = "serpentine",
    amplitude_mm: float = 0.5,
    period_mm: float = 1.0,
) -> list:
    straight = _dist(start, end)
    if target_length < straight - 1e-9:
        raise ValueError(
            f"target_length ({target_length:.4f}) < straight distance ({straight:.4f})"
        )

    extra = target_length - straight
    if extra < 1e-9:
        return [{"x": start["x"], "y": start["y"]}, {"x": end["x"], "y": end["y"]}]

    fwd = _unit(start, end)
    side = _perp(fwd)

    if style == "trombone":
        return _trombone(start, end, target_length, fwd, side, amplitude_mm)
    if style == "accordion":
        return _accordion(start, end, target_length, fwd, side, amplitude_mm, period_mm)
    return _serpentine(start, end, target_length, fwd, side, amplitude_mm, period_mm)


def _serpentine(start, end, target_length, fwd, side, amplitude, period):
    extra = target_length - _dist(start, end)
    extra_per_tooth = 2 * amplitude
    n_teeth = max(1, math.ceil(extra / extra_per_tooth))

    points = [{"x": start["x"], "y": start["y"]}]
    side_sign = 1

    for i in range(n_teeth):
        t0 = i / n_teeth
        t2 = (i + 1) / n_teeth
        b0 = _lerp(start, end, t0)
        b2 = _lerp(start, end, t2)

        rise = {
            "x": b0["x"] + side["x"] * amplitude * side_sign,
            "y": b0["y"] + side["y"] * amplitude * side_sign,
        }
        fall = {
            "x": b2["x"] + side["x"] * amplitude * side_sign,
            "y": b2["y"] + side["y"] * amplitude * side_sign,
        }
        points.extend([rise, fall])
        side_sign = -side_sign

    points.append({"x": end["x"], "y": end["y"]})
    return points


def _accordion(start, end, target_length, fwd, side, amplitude, period):
    straight = _dist(start, end)
    extra = target_length - straight
    half_period = period / 2
    leg_len = math.sqrt(half_period ** 2 + amplitude ** 2)
    extra_per_tooth = 2 * leg_len - period

    if extra_per_tooth <= 1e-9:
        return _serpentine(start, end, target_length, fwd, side, amplitude, period)

    n_teeth = max(1, math.ceil(extra / extra_per_tooth))
    points = [{"x": start["x"], "y": start["y"]}]
    side_sign = 1

    for i in range(n_teeth):
        t_peak = (i + 0.5) / n_teeth
        base_peak = _lerp(start, end, t_peak)
        peak = {
            "x": base_peak["x"] + side["x"] * amplitude * side_sign,
            "y": base_peak["y"] + side["y"] * amplitude * side_sign,
        }
        points.append(peak)
        side_sign = -side_sign

    points.append({"x": end["x"], "y": end["y"]})
    return points


def _trombone(start, end, target_length, fwd, side, amplitude):
    extra = target_length - _dist(start, end)
    amp = amplitude
    run = (extra - 4 * amp) / 2
    if run < 0:
        amp = extra / 4
        run = 0

    entry = _lerp(start, end, 0.25)
    exit_ = _lerp(start, end, 0.75)
    half_run = run / 2

    def off(pt):
        return {"x": pt["x"] + side["x"] * amp, "y": pt["y"] + side["y"] * amp}

    tip1 = {"x": off(entry)["x"] + fwd["x"] * half_run, "y": off(entry)["y"] + fwd["y"] * half_run}
    tip2 = {"x": off(exit_)["x"] + fwd["x"] * half_run, "y": off(exit_)["y"] + fwd["y"] * half_run}

    return [
        {"x": start["x"], "y": start["y"]},
        {"x": entry["x"], "y": entry["y"]},
        off(entry),
        tip1,
        tip2,
        off(exit_),
        {"x": exit_["x"], "y": exit_["y"]},
        {"x": end["x"], "y": end["y"]},
    ]


# ── Core logic: apply meander ─────────────────────────────────────────────────

def _apply_meander(trace: dict, seg_idx: int, style: str, amplitude_mm: float) -> dict:
    pts = trace.get("points") or []
    n_segs = len(pts) - 1

    if n_segs < 1:
        raise ValueError("trace must have at least 2 points")
    if seg_idx < 0 or seg_idx >= n_segs:
        raise ValueError(f"seg_idx {seg_idx} out of range [0, {n_segs - 1}]")

    target = trace.get("target_length_mm")
    if not isinstance(target, (int, float)) or target <= 0:
        raise ValueError("trace.target_length_mm must be a positive number")

    current_len = _trace_length(trace)
    seg_len = _dist(pts[seg_idx], pts[seg_idx + 1])
    needed = target - current_len

    if needed < -1e-9:
        raise ValueError(
            f"target_length_mm ({target}) < current length ({current_len:.4f}) — cannot shorten a trace"
        )

    meander_target = seg_len + needed
    meander_pts = _generate_meander(
        pts[seg_idx], pts[seg_idx + 1], meander_target, style, amplitude_mm
    )

    new_pts = pts[:seg_idx] + meander_pts + pts[seg_idx + 2:]
    result = dict(trace)
    result["points"] = new_pts
    return result


# ── Core logic: differential skew ────────────────────────────────────────────

def _differential_skew(elements: list, pair_name: str) -> dict:
    board = _get_board(elements)
    pairs = (board.get("differential_pairs") or []) if board else []

    if not isinstance(pairs, list):
        return {"error": "board.differential_pairs not defined"}

    pair_def = next((p for p in pairs if p.get("name") == pair_name), None)
    if pair_def is None:
        return {"error": f"differential pair '{pair_name}' not found"}

    net_p = pair_def.get("net_p_id", "")
    net_n = pair_def.get("net_n_id", "")
    traces = _get_traces(elements)

    len_p = sum(_trace_length(t) for t in traces if t.get("net_id") == net_p)
    len_n = sum(_trace_length(t) for t in traces if t.get("net_id") == net_n)

    return {
        "length_p": len_p,
        "length_n": len_n,
        "delta_mm": abs(len_p - len_n),
    }


# ── Tool: set_trace_target_length ─────────────────────────────────────────────

set_trace_target_length_spec = ToolSpec(
    name="set_trace_target_length",
    description=(
        "Annotate a trace with a target length in mm.  The length-tuning tools "
        "use this annotation to determine how much meander to add.  "
        "Overwrites any existing target_length_mm on the trace."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "oneOf": [{"type": "object"}, {"type": "array"}],
                "description": "CircuitJSON board or element list.",
            },
            "trace_id": {"type": "string", "description": "id of the pcb_trace to annotate"},
            "target_length_mm": {"type": "number", "description": "Desired trace length in mm"},
        },
        "required": ["circuit_json", "trace_id", "target_length_mm"],
    },
)


@register(set_trace_target_length_spec, write=True)
async def set_trace_target_length(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    trace_id = (a.get("trace_id") or "").strip()
    target = a.get("target_length_mm")

    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not trace_id:
        return err_payload("trace_id is required", "BAD_ARGS")
    if not isinstance(target, (int, float)) or target <= 0:
        return err_payload("target_length_mm must be a positive number", "BAD_ARGS")

    cloned = deepcopy(circuit_json)
    elements = cloned if isinstance(cloned, list) else [cloned]

    trace = next(
        (e for e in elements if isinstance(e, dict) and e.get("type") == "pcb_trace"
         and (e.get("id") == trace_id or e.get("pcb_trace_id") == trace_id)),
        None,
    )
    if trace is None:
        return err_payload(f"trace '{trace_id}' not found", "NOT_FOUND")

    trace["target_length_mm"] = target
    return ok_payload({"circuit_json": cloned, "trace_id": trace_id, "target_length_mm": target})


# ── Tool: tune_trace_to_target ────────────────────────────────────────────────

tune_trace_to_target_spec = ToolSpec(
    name="tune_trace_to_target",
    description=(
        "Apply a meander to the longest straight segment of a trace so its total "
        "length reaches target_length_mm.  The trace must already have "
        "target_length_mm set (use set_trace_target_length first).  "
        "style: 'serpentine' (default) | 'accordion' | 'trombone'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"oneOf": [{"type": "object"}, {"type": "array"}]},
            "trace_id": {"type": "string"},
            "style": {
                "type": "string",
                "enum": ["serpentine", "accordion", "trombone"],
                "description": "Meander style (default: serpentine)",
            },
            "amplitude_mm": {
                "type": "number",
                "description": "Half-amplitude of meander teeth in mm (default: 0.5)",
            },
        },
        "required": ["circuit_json", "trace_id"],
    },
)


@register(tune_trace_to_target_spec, write=True)
async def tune_trace_to_target(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    trace_id = (a.get("trace_id") or "").strip()
    style = a.get("style") or "serpentine"
    amplitude_mm = a.get("amplitude_mm") or 0.5

    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not trace_id:
        return err_payload("trace_id is required", "BAD_ARGS")
    if style not in ("serpentine", "accordion", "trombone"):
        return err_payload("style must be serpentine, accordion, or trombone", "BAD_ARGS")

    cloned = deepcopy(circuit_json)
    elements = cloned if isinstance(cloned, list) else [cloned]

    trace_idx = next(
        (i for i, e in enumerate(elements)
         if isinstance(e, dict) and e.get("type") == "pcb_trace"
         and (e.get("id") == trace_id or e.get("pcb_trace_id") == trace_id)),
        None,
    )
    if trace_idx is None:
        return err_payload(f"trace '{trace_id}' not found", "NOT_FOUND")

    trace = elements[trace_idx]
    if not isinstance(trace.get("target_length_mm"), (int, float)):
        return err_payload(
            f"trace '{trace_id}' has no target_length_mm — call set_trace_target_length first",
            "BAD_ARGS",
        )

    pts = trace.get("points") or []
    if len(pts) < 2:
        return err_payload("trace has fewer than 2 points", "BAD_ARGS")

    # Pick longest segment
    max_len = -1
    max_idx = 0
    for i in range(len(pts) - 1):
        sl = _dist(pts[i], pts[i + 1])
        if sl > max_len:
            max_len = sl
            max_idx = i

    try:
        tuned = _apply_meander(trace, max_idx, style, amplitude_mm)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    elements[trace_idx] = tuned
    new_len = _trace_length(tuned)

    return ok_payload({"circuit_json": cloned, "trace_id": trace_id, "new_length_mm": new_len})


# ── Tool: report_diff_pair_skew ───────────────────────────────────────────────

report_diff_pair_skew_spec = ToolSpec(
    name="report_diff_pair_skew",
    description=(
        "Report the current propagation-skew between the positive and negative "
        "traces of a named differential pair.  Returns length_p, length_n, and "
        "delta_mm.  Requires board.differential_pairs to be defined."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"oneOf": [{"type": "object"}, {"type": "array"}]},
            "pair_name": {"type": "string", "description": "Name of the differential pair"},
        },
        "required": ["circuit_json", "pair_name"],
    },
)


@register(report_diff_pair_skew_spec, write=False)
async def report_diff_pair_skew(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    pair_name = (a.get("pair_name") or "").strip()

    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not pair_name:
        return err_payload("pair_name is required", "BAD_ARGS")

    elements = circuit_json if isinstance(circuit_json, list) else [circuit_json]
    result = _differential_skew(elements, pair_name)

    if "error" in result:
        return err_payload(result["error"], "NOT_FOUND")

    return ok_payload({
        "pair_name": pair_name,
        "length_p": result["length_p"],
        "length_n": result["length_n"],
        "delta_mm": result["delta_mm"],
    })


# ── Tool: match_diff_pair ─────────────────────────────────────────────────────

match_diff_pair_spec = ToolSpec(
    name="match_diff_pair",
    description=(
        "Bring the shorter trace of a differential pair within skew_max_mm of "
        "the longer trace by inserting a meander.  "
        "skew_max_mm defaults to the pair definition value, then 0.05 mm.  "
        "Returns updated circuit_json plus the tuned net name and final delta."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"oneOf": [{"type": "object"}, {"type": "array"}]},
            "pair_name": {"type": "string"},
            "style": {
                "type": "string",
                "enum": ["serpentine", "accordion", "trombone"],
            },
            "amplitude_mm": {"type": "number"},
            "skew_max_mm": {
                "type": "number",
                "description": "Override pair's skew_max_mm threshold",
            },
        },
        "required": ["circuit_json", "pair_name"],
    },
)


@register(match_diff_pair_spec, write=True)
async def match_diff_pair(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    pair_name = (a.get("pair_name") or "").strip()
    style = a.get("style") or "serpentine"
    amplitude_mm = a.get("amplitude_mm") or 0.5
    skew_max_mm_arg = a.get("skew_max_mm")

    if not circuit_json:
        return err_payload("circuit_json is required", "BAD_ARGS")
    if not pair_name:
        return err_payload("pair_name is required", "BAD_ARGS")
    if style not in ("serpentine", "accordion", "trombone"):
        return err_payload("style must be serpentine, accordion, or trombone", "BAD_ARGS")

    elements = deepcopy(circuit_json if isinstance(circuit_json, list) else [circuit_json])

    skew_info = _differential_skew(elements, pair_name)
    if "error" in skew_info:
        return err_payload(skew_info["error"], "NOT_FOUND")

    board = _get_board(elements)
    pairs = (board.get("differential_pairs") or []) if board else []
    pair_def = next((p for p in pairs if p.get("name") == pair_name), {})

    skew_max = skew_max_mm_arg
    if skew_max is None:
        skew_max = pair_def.get("skew_max_mm", 0.05)

    len_p = skew_info["length_p"]
    len_n = skew_info["length_n"]
    delta = skew_info["delta_mm"]

    if delta <= skew_max:
        return ok_payload({
            "circuit_json": circuit_json,
            "tuned_net": None,
            "delta_mm": delta,
        })

    is_p_shorter = len_p < len_n
    shorter_net = pair_def.get("net_p_id") if is_p_shorter else pair_def.get("net_n_id")
    longer_length = len_n if is_p_shorter else len_p

    # Find all trace indices for shorter net
    short_trace_entries = [
        (i, e) for i, e in enumerate(elements)
        if isinstance(e, dict) and e.get("type") == "pcb_trace" and e.get("net_id") == shorter_net
    ]

    if not short_trace_entries:
        return err_payload(f"no traces found for net '{shorter_net}'", "NOT_FOUND")

    # Pick trace with longest segment
    best_idx = None
    best_seg = 0
    best_seg_len = -1

    for elem_idx, trace in short_trace_entries:
        pts = trace.get("points") or []
        for si in range(len(pts) - 1):
            sl = _dist(pts[si], pts[si + 1])
            if sl > best_seg_len:
                best_seg_len = sl
                best_seg = si
                best_idx = elem_idx

    if best_idx is None:
        return err_payload("no suitable segment found in shorter trace", "BAD_ARGS")

    current_short_total = sum(
        _trace_length(e) for _, e in short_trace_entries
    )
    target_for_this_trace = (
        _trace_length(elements[best_idx]) + (longer_length - current_short_total)
    )

    annotated = dict(elements[best_idx])
    annotated["target_length_mm"] = target_for_this_trace

    try:
        tuned = _apply_meander(annotated, best_seg, style, amplitude_mm)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    elements[best_idx] = tuned

    final_skew = _differential_skew(elements, pair_name)

    return ok_payload({
        "circuit_json": elements,
        "tuned_net": shorter_net,
        "delta_mm": final_skew.get("delta_mm", 0),
    })
