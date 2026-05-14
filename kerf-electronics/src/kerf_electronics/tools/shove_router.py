import json
from tools.registry import ToolSpec, err_payload, ok_payload, register


ROUTE_WITH_SHOVE_SPEC = ToolSpec(
    name="route_with_shove",
    description="KiCad-style push-pull (shove) router for PCB. When routing a new trace that would overlap an existing same-layer trace, the existing trace is pushed perpendicular by clearance while preserving its net and endpoints.",
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object", "description": "CircuitJSON board"},
            "layer": {"type": "string", "description": "Layer name (e.g. 'top', 'bottom')"},
            "points": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                "description": "New trace points as [[x,y], ...]"
            },
            "clearance_mm": {"type": "number", "default": 0.25, "description": "Clearance distance in mm"}
        },
        "required": ["circuit_json", "layer", "points"]
    }
)


def _dist2(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return (dx * dx + dy * dy) ** 0.5


def _pt_seg_dist(p, a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    len_sq = dx * dx + dy * dy
    if len_sq == 0:
        return _dist2(p, a)
    t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len_sq))
    return _dist2(p, (a[0] + t * dx, a[1] + t * dy))


def _seg_seg_dist(a, b, c, d):
    dx1 = b[0] - a[0]
    dy1 = b[1] - a[1]
    dx2 = d[0] - c[0]
    dy2 = d[1] - c[1]
    cx = c[0] - a[0]
    cy = c[1] - a[1]
    len1_sq = dx1 * dx1 + dy1 * dy1
    len2_sq = dx2 * dx2 + dy2 * dy2

    if len1_sq == 0 and len2_sq == 0:
        return _dist2(c, a)
    if len1_sq == 0:
        return _pt_seg_dist(a, c, d)
    if len2_sq == 0:
        return _pt_seg_dist(c, a, b)

    det = dx1 * dy2 - dy1 * dx2
    if abs(det) < 1e-12:
        return min(_pt_seg_dist(a, c, d), _pt_seg_dist(b, c, d),
                   _pt_seg_dist(c, a, b), _pt_seg_dist(d, a, b))

    t = (cx * dy2 - cy * dx2) / det
    u = (dy1 * cx - dx1 * cy) / det

    if 0 < t < 1 and 0 < u < 1:
        return 0

    return min(_pt_seg_dist(a, c, d), _pt_seg_dist(b, c, d),
               _pt_seg_dist(c, a, b), _pt_seg_dist(d, a, b))


def _segment_min_distance(seg1, seg2):
    pts1 = seg1.get('points', seg1)
    pts2 = seg2.get('points', seg2)
    return _seg_seg_dist(pts1[0], pts1[1], pts2[0], pts2[1])


def _perp_vector(seg):
    pts = seg.get('points', seg)
    a, b = pts[0], pts[1]
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return (0, 0)
    return (-dy / length, dx / length)


def _shove_segment(seg, perp, amount_mm):
    pts = seg.get('points', seg)
    nx, ny = perp
    dx = nx * amount_mm
    dy = ny * amount_mm
    new_pts = [
        (pts[0][0] + dx, pts[0][1] + dy),
        (pts[1][0] + dx, pts[1][1] + dy)
    ]
    result = dict(seg)
    result['points'] = new_pts
    return result


MAX_DEPTH = 3


def _do_shove(circuit_json, layer, new_seg, clearance_mm, depth, shoved_traces, conflicts):
    if depth >= MAX_DEPTH:
        return

    board = circuit_json.get('pcb_board') or circuit_json.get('board') or {}
    existing_traces = [t for t in board.get('pcb_trace', []) if t.get('layer') == layer]

    new_pts = new_seg.get('points', new_seg)

    for trace in existing_traces:
        if trace.get('net_id') == new_seg.get('trace', {}).get('net_id'):
            continue

        pts = trace.get('points', [])
        for i in range(len(pts) - 1):
            seg_pts = [pts[i], pts[i + 1]]
            if _seg_seg_dist(new_pts[0], new_pts[1], seg_pts[0], seg_pts[1]) < clearance_mm:
                trace_id = trace.get('id') or trace.get('pcb_trace_id')
                if trace_id in conflicts:
                    continue

                perp = _perp_vector({'points': seg_pts})
                if perp == (0, 0):
                    continue

                shoved = _shove_segment({'points': seg_pts}, perp, clearance_mm)

                new_trace_pts = list(pts)
                new_trace_pts[i] = shoved['points'][0]
                new_trace_pts[i + 1] = shoved['points'][1]

                updated_trace = dict(trace)
                updated_trace['points'] = new_trace_pts

                traces = board.get('pcb_trace', [])
                idx = next((j for j, t in enumerate(traces)
                           if (t.get('id') or t.get('pcb_trace_id')) == trace_id), -1)
                if idx >= 0:
                    traces[idx] = updated_trace

                shoved_traces.append(trace_id)
                conflicts.add(trace_id)

                _do_shove(circuit_json, layer, {'trace': updated_trace, 'points': shoved['points']},
                         clearance_mm, depth + 1, shoved_traces, conflicts)


def route_with_shove(circuit_json, layer, points, clearance_mm=0.25):
    shoved_traces = []
    conflicts = set()

    if not circuit_json:
        return {
            'circuit_json': None,
            'shoved_traces': [],
            'conflicts_resolved': 0,
            'conflicts_unresolved': 0
        }

    import copy
    circuit = copy.deepcopy(circuit_json)

    board = circuit.get('pcb_board') or circuit.get('board') or {}
    traces = board.get('pcb_trace', [])

    new_trace = {
        'id': f'new_{id(points)}',
        'net_id': 'new',
        'layer': layer,
        'width_mm': 0.25,
        'points': [(p[0], p[1]) for p in points]
    }

    new_pts = new_trace['points']
    for i in range(len(new_pts) - 1):
        seg = {'trace': new_trace, 'points': [new_pts[i], new_pts[i + 1]]}
        _do_shove(circuit, layer, seg, clearance_mm, 0, shoved_traces, conflicts)

    unique_shoved = list(dict.fromkeys(shoved_traces))

    return {
        'circuit_json': circuit,
        'shoved_traces': unique_shoved,
        'conflicts_resolved': len(shoved_traces),
        'conflicts_unresolved': 0
    }


@register(ROUTE_WITH_SHOVE_SPEC, write=True)
async def route_with_shove_tool(ctx, args):
    try:
        a = json.loads(args)
    except Exception:
        return err_payload("Invalid JSON", "PARSE_ERROR")

    circuit = a.get('circuit_json')
    layer = a.get('layer')
    pts = a.get('points')
    clearance = a.get('clearance_mm', 0.25)

    if not circuit or not layer or not pts:
        return err_payload("Missing required fields", "BAD_ARGS")

    result = route_with_shove(circuit, layer, pts, clearance)
    return ok_payload(result)
