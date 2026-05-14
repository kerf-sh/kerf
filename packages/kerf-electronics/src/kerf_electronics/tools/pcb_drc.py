"""
LLM tools for PCB Design Rule Check (DRC).

Tools:
  run_pcb_drc     — execute all DRC checks on a CircuitJSON board array.
  set_drc_rule    — update a DRC rule value on board.drc_rules.

The DRC logic mirrors the frontend pcbDRC.js implementation exactly so
that both JS (overlay rendering) and Python (LLM tool) produce identical
results given the same board data.
"""
import json
import math
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register


# ---------------------------------------------------------------------------
# Default rules — must stay in sync with DEFAULT_RULES in pcbDRC.js
# ---------------------------------------------------------------------------
_DEFAULT_RULES = {
    "min_trace_width_mm": 0.15,
    "min_via_clearance_mm": 0.10,
    "min_drill_spacing_mm": 0.20,
    "min_copper_to_edge_mm": 0.30,
    "silk_on_pad_tolerance": 0.05,
}

_VALID_RULE_NAMES = set(_DEFAULT_RULES.keys())


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _dist2d(ax, ay, bx, by):
    return math.sqrt((bx - ax) ** 2 + (by - ay) ** 2)


def _midpoint(points):
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return points[0].get("x", 0.0), points[0].get("y", 0.0)
    mid = len(points) // 2
    return (
        (points[mid - 1].get("x", 0.0) + points[mid].get("x", 0.0)) / 2,
        (points[mid - 1].get("y", 0.0) + points[mid].get("y", 0.0)) / 2,
    )


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _check_trace_width(traces, rules):
    errors = []
    min_w = rules["min_trace_width_mm"]
    for trace in traces:
        w = (
            trace.get("route_thickness_mm")
            or trace.get("width_mm")
            or trace.get("stroke_width")
        )
        if w is not None and w < min_w:
            pts = trace.get("route") or trace.get("points") or []
            fallback = [{"x": trace.get("x", 0), "y": trace.get("y", 0)}]
            mx, my = _midpoint(pts if pts else fallback)
            errors.append({
                "kind": "trace_too_narrow",
                "severity": "error",
                "message": f"Trace width {w:.3f} mm is below minimum {min_w} mm",
                "x": mx,
                "y": my,
                "trace_id": trace.get("pcb_trace_id") or trace.get("id"),
            })
    return errors


def _check_via_clearance(vias, rules):
    errors = []
    min_clear = rules["min_via_clearance_mm"]
    for i in range(len(vias)):
        for j in range(i + 1, len(vias)):
            a, b = vias[i], vias[j]
            ax, ay = a.get("x", 0), a.get("y", 0)
            bx, by = b.get("x", 0), b.get("y", 0)
            a_outer = (a.get("outer_diameter") or a.get("pad_diameter") or 0.6) / 2
            b_outer = (b.get("outer_diameter") or b.get("pad_diameter") or 0.6) / 2
            center_dist = _dist2d(ax, ay, bx, by)
            gap = center_dist - a_outer - b_outer
            if gap < min_clear:
                errors.append({
                    "kind": "via_clearance",
                    "severity": "error",
                    "message": f"Via clearance {gap:.3f} mm is below minimum {min_clear} mm",
                    "x": (ax + bx) / 2,
                    "y": (ay + by) / 2,
                })
    return errors


def _check_drill_spacing(vias, rules):
    errors = []
    min_space = rules["min_drill_spacing_mm"]
    for i in range(len(vias)):
        for j in range(i + 1, len(vias)):
            a, b = vias[i], vias[j]
            ax, ay = a.get("x", 0), a.get("y", 0)
            bx, by = b.get("x", 0), b.get("y", 0)
            a_drill = (a.get("hole_diameter") or a.get("drill_diameter") or 0.3) / 2
            b_drill = (b.get("hole_diameter") or b.get("drill_diameter") or 0.3) / 2
            edge_to_edge = _dist2d(ax, ay, bx, by) - a_drill - b_drill
            if edge_to_edge < min_space:
                errors.append({
                    "kind": "drill_spacing",
                    "severity": "error",
                    "message": f"Drill hole spacing {edge_to_edge:.3f} mm is below minimum {min_space} mm",
                    "x": (ax + bx) / 2,
                    "y": (ay + by) / 2,
                })
    return errors


def _check_silk_on_pad(silk_texts, pads, rules):
    warnings = []
    tol = rules["silk_on_pad_tolerance"]
    for text in silk_texts:
        tx = text.get("anchor_x") or text.get("x") or 0
        ty = text.get("anchor_y") or text.get("y") or 0
        for pad in pads:
            px, py = pad.get("x", 0), pad.get("y", 0)
            pr = (pad.get("width") or pad.get("pad_diameter") or 1.5) / 2
            if _dist2d(tx, ty, px, py) < pr - tol:
                warnings.append({
                    "kind": "silk_on_pad",
                    "severity": "warning",
                    "message": f"Silkscreen text may overlap pad at ({px:.2f}, {py:.2f})",
                    "x": tx,
                    "y": ty,
                })
                break  # one warning per silk element
    return warnings


def _check_copper_to_edge(traces, pads, vias, board, rules):
    warnings = []
    min_edge = rules["min_copper_to_edge_mm"]
    if not board:
        return warnings
    bw = board.get("width", 0)
    bh = board.get("height", 0)
    if bw <= 0 or bh <= 0:
        return warnings

    def check(x, y, label):
        min_d = min(x, bw - x, y, bh - y)
        if min_d < min_edge:
            warnings.append({
                "kind": "copper_to_edge",
                "severity": "warning",
                "message": f"{label} is {min_d:.3f} mm from board edge (min {min_edge} mm)",
                "x": x,
                "y": y,
            })

    for trace in traces:
        for pt in (trace.get("route") or trace.get("points") or []):
            check(pt.get("x", 0), pt.get("y", 0), "Trace")
    for pad in pads:
        check(pad.get("x", 0), pad.get("y", 0), "Pad")
    for via in vias:
        check(via.get("x", 0), via.get("y", 0), "Via")
    return warnings


def _check_dangling_traces(traces, pads):
    errors = []
    EPS = 1e-4

    pad_positions = [{"x": p.get("x", 0), "y": p.get("y", 0)} for p in pads]

    endpoints = []
    for trace in traces:
        pts = trace.get("route") or trace.get("points") or []
        if len(pts) < 2:
            continue
        endpoints.append({"x": pts[0].get("x", 0), "y": pts[0].get("y", 0), "trace": id(trace)})
        endpoints.append({"x": pts[-1].get("x", 0), "y": pts[-1].get("y", 0), "trace": id(trace)})

    def on_pad(x, y):
        return any(
            abs(p["x"] - x) < EPS and abs(p["y"] - y) < EPS
            for p in pad_positions
        )

    def connected_to_other(x, y, self_trace_id):
        return any(
            ep["trace"] != self_trace_id and
            abs(ep["x"] - x) < EPS and abs(ep["y"] - y) < EPS
            for ep in endpoints
        )

    for trace in traces:
        pts = trace.get("route") or trace.get("points") or []
        if len(pts) < 2:
            continue
        tid = id(trace)
        trace_id = trace.get("pcb_trace_id") or trace.get("id")

        for pt, label in [(pts[0], "start"), (pts[-1], "end")]:
            x, y = pt.get("x", 0), pt.get("y", 0)
            if not on_pad(x, y) and not connected_to_other(x, y, tid):
                errors.append({
                    "kind": "dangling_trace",
                    "severity": "error",
                    "message": f"Trace {label} endpoint ({x:.3f}, {y:.3f}) is not connected to a pad or another trace",
                    "x": x,
                    "y": y,
                    "trace_id": trace_id,
                })
    return errors


def _check_net_shorts(traces, pads):
    errors = []
    EPS = 1e-4

    netted = [p for p in pads if p.get("net_id") or p.get("net")]
    if len(netted) < 2:
        return errors

    nodes = [
        {
            "id": i,
            "x": p.get("x", 0),
            "y": p.get("y", 0),
            "net": p.get("net_id") or p.get("net"),
            "parent": i,
        }
        for i, p in enumerate(netted)
    ]

    def find(nid):
        while nodes[nid]["parent"] != nid:
            nodes[nid]["parent"] = nodes[nodes[nid]["parent"]]["parent"]
            nid = nodes[nid]["parent"]
        return nid

    def unite(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            nodes[ra]["parent"] = rb

    # Co-located pads
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if abs(nodes[i]["x"] - nodes[j]["x"]) < EPS and abs(nodes[i]["y"] - nodes[j]["y"]) < EPS:
                unite(i, j)

    # Trace connections
    for trace in traces:
        pts = trace.get("route") or trace.get("points") or []
        if len(pts) < 2:
            continue
        sx, sy = pts[0].get("x", 0), pts[0].get("y", 0)
        ex, ey = pts[-1].get("x", 0), pts[-1].get("y", 0)
        start_hits = [i for i, n in enumerate(nodes) if abs(n["x"] - sx) < EPS and abs(n["y"] - sy) < EPS]
        end_hits = [i for i, n in enumerate(nodes) if abs(n["x"] - ex) < EPS and abs(n["y"] - ey) < EPS]
        for s in start_hits:
            for e in end_hits:
                unite(s, e)

    # Detect mixed-net clusters
    clusters: dict = {}
    for i in range(len(nodes)):
        root = find(i)
        clusters.setdefault(root, []).append(nodes[i])

    reported = set()
    for members in clusters.values():
        nets = sorted(set(m["net"] for m in members))
        if len(nets) > 1:
            key = "|".join(nets)
            if key not in reported:
                reported.add(key)
                cx = sum(m["x"] for m in members) / len(members)
                cy = sum(m["y"] for m in members) / len(members)
                errors.append({
                    "kind": "net_short",
                    "severity": "error",
                    "message": f"Net short: copper connects nets {', '.join(nets)}",
                    "x": cx,
                    "y": cy,
                })
    return errors


# ---------------------------------------------------------------------------
# Core DRC runner (used by both tools)
# ---------------------------------------------------------------------------

def _run_drc_on_circuit(circuit_json: list) -> dict:
    if not isinstance(circuit_json, list) or not circuit_json:
        return {"errors": [], "warnings": []}

    board = next((e for e in circuit_json if isinstance(e, dict) and e.get("type") == "pcb_board"), None)
    traces = [e for e in circuit_json if isinstance(e, dict) and e.get("type") == "pcb_trace"]
    vias = [e for e in circuit_json if isinstance(e, dict) and e.get("type") in ("pcb_via", "pcb_hole")]
    pads = [e for e in circuit_json if isinstance(e, dict) and e.get("type") in ("pcb_smtpad", "pcb_plated_hole")]
    silk = [e for e in circuit_json if isinstance(e, dict) and e.get("type") in ("pcb_silkscreen_text", "pcb_text")]

    rules = {**_DEFAULT_RULES, **(board.get("drc_rules", {}) if board else {})}

    errors = (
        _check_trace_width(traces, rules)
        + _check_via_clearance(vias, rules)
        + _check_drill_spacing(vias, rules)
        + _check_dangling_traces(traces, pads)
        + _check_net_shorts(traces, pads)
    )

    warnings = (
        _check_silk_on_pad(silk, pads, rules)
        + _check_copper_to_edge(traces, pads, vias, board, rules)
    )

    return {"errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Tool: run_pcb_drc
# ---------------------------------------------------------------------------

run_pcb_drc_spec = ToolSpec(
    name="run_pcb_drc",
    description=(
        "Run all PCB design-rule checks (DRC) on a CircuitJSON board. "
        "Returns errors (must-fix violations) and warnings (advisory issues) "
        "with coordinates and kind tags, plus a summary count. "
        "Checks: trace_width_min, via_clearance, drill_spacing, silk_on_pad, "
        "copper_to_edge, dangling_trace, net_short."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": (
                    "Flat AnyCircuitElement[] array from CircuitJSON. Must include "
                    "a pcb_board element plus traces, vias, pads as needed."
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["circuit_json"],
    },
)


@register(run_pcb_drc_spec, write=False)
async def run_pcb_drc(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    result = _run_drc_on_circuit(circuit_json)
    result["summary"] = {
        "error_count": len(result["errors"]),
        "warning_count": len(result["warnings"]),
    }
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: set_drc_rule
# ---------------------------------------------------------------------------

set_drc_rule_spec = ToolSpec(
    name="set_drc_rule",
    description=(
        "Update a single DRC rule on the pcb_board element inside circuit_json. "
        "Returns the modified circuit_json with the rule applied. "
        f"Valid rule names: {', '.join(sorted(_VALID_RULE_NAMES))}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "The CircuitJSON array to modify.",
                "items": {"type": "object"},
            },
            "rule_name": {
                "type": "string",
                "description": (
                    "DRC rule key to set. One of: "
                    + ", ".join(sorted(_VALID_RULE_NAMES))
                ),
            },
            "value": {
                "type": "number",
                "description": "New value for the rule (in mm for distance rules).",
            },
        },
        "required": ["circuit_json", "rule_name", "value"],
    },
)


@register(set_drc_rule_spec, write=True)
async def set_drc_rule(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    rule_name = a.get("rule_name", "")
    if rule_name not in _VALID_RULE_NAMES:
        return err_payload(
            f"unknown rule '{rule_name}'. Valid: {sorted(_VALID_RULE_NAMES)}",
            "BAD_ARGS",
        )

    value = a.get("value")
    if value is None or not isinstance(value, (int, float)):
        return err_payload("value must be a number", "BAD_ARGS")
    if value < 0:
        return err_payload("value must be >= 0", "BAD_ARGS")

    # Mutate a copy — find or create the pcb_board
    updated = [dict(e) for e in circuit_json]
    board = next((e for e in updated if e.get("type") == "pcb_board"), None)
    if board is None:
        board = {"type": "pcb_board", "drc_rules": {}}
        updated.append(board)

    board.setdefault("drc_rules", {})
    board["drc_rules"][rule_name] = value

    return ok_payload({
        "rule_name": rule_name,
        "value": value,
        "circuit_json": updated,
    })
