"""draft.py — LLM tools: Draft workbench operations mirroring src/lib/draft.js."""
import json, math
from typing import Any

from tools.registry import ToolSpec, err_payload, ok_payload, register

_uid_counter = 0

def _uid():
    global _uid_counter
    _uid_counter += 1
    return f"u{_uid_counter:06x}"

def _default_draft(name="Untitled"):
    return {"version": 1, "name": name, "scale": 1.0, "entities": []}

def _validate_draft(d):
    errors = []
    if not isinstance(d, dict):
        return {"ok": False, "errors": ["draft must be an object"]}
    if d.get("version") != 1:
        errors.append("version must be 1")
    if not isinstance(d.get("name", ""), str):
        errors.append("name must be a string")
    scale = d.get("scale", 1.0)
    if not isinstance(scale, (int, float)):
        errors.append("scale must be a number")
    elif scale <= 0:
        errors.append("scale must be positive")
    if not isinstance(d.get("entities", []), list):
        errors.append("entities must be an array")
    else:
        ids = set()
        for i, e in enumerate(d["entities"]):
            p = f"entities[{i}]"
            if not isinstance(e, dict):
                errors.append(f"{p}: must be an object")
                continue
            if e.get("kind") not in ("line", "polyline", "arc", "circle", "spline", "rect", "text", "dimension"):
                errors.append(f"{p}: invalid kind")
            if not e.get("id"):
                errors.append(f"{p}: id is required")
            elif e["id"] in ids:
                errors.append(f"{p}: duplicate id {e['id']}")
            ids.add(e.get("id", ""))
    return {"ok": len(errors) == 0, "errors": errors}

def _add_entity(d, entity):
    e = dict(entity)
    if not e.get("id"):
        e["id"] = _uid()
    v = _validate_draft({"version": 1, "name": d.get("name",""), "scale": 1.0, "entities": d["entities"] + [e]})
    if not v["ok"]:
        raise ValueError("; ".join(v["errors"]))
    d["entities"].append(e)
    return e

def _remove_entity(d, id):
    idx = next((i for i, e in enumerate(d["entities"]) if e["id"] == id), None)
    if idx is None:
        raise ValueError(f"entity {id} not found")
    d["entities"].pop(idx)

def _move_entity(d, id, dx, dy):
    e = next((e for e in d["entities"] if e["id"] == id), None)
    if not e:
        raise ValueError(f"entity {id} not found")
    k = e["kind"]
    if k in ("line", "dimension"):
        e["x1"] += dx; e["y1"] += dy; e["x2"] += dx; e["y2"] += dy
    elif k == "polyline":
        e["points"] = [[px + dx, py + dy] for px, py in e.get("points", [])]
    elif k in ("arc", "circle"):
        e["cx"] += dx; e["cy"] += dy
    elif k == "rect":
        e["x"] += dx; e["y"] += dy
    elif k == "text":
        e["x"] += dx; e["y"] += dy
    elif k == "spline":
        e["points"] = [[px + dx, py + dy] for px, py in e.get("points", [])]

def _hypot(x, y):
    return math.hypot(x, y)

def _norm(x, y):
    l = _hypot(x, y)
    return (0.0, 0.0) if l == 0 else (x / l, y / l)

def _dot(x1, y1, x2, y2):
    return x1 * x2 + y1 * y2

def _offset_entity(d, id, distance):
    e = next((e for e in d["entities"] if e["id"] == id), None)
    if not e:
        raise ValueError(f"entity {id} not found")
    if e["kind"] == "line":
        dx = e["x2"] - e["x1"]
        dy = e["y2"] - e["y1"]
        nx, ny = _norm(-dy, dx)
        return {**e, "id": _uid(), "x1": e["x1"] + nx * distance, "y1": e["y1"] + ny * distance,
                "x2": e["x2"] + nx * distance, "y2": e["y2"] + ny * distance}
    if e["kind"] == "polyline":
        pts = e.get("points", [])
        if len(pts) < 2:
            return None
        new_pts = []
        for i, pt in enumerate(pts):
            prev = pts[(i - 1 + len(pts)) % len(pts)]
            nxt = pts[(i + 1) % len(pts)]
            dx1, dy1 = pt[0] - prev[0], pt[1] - prev[1]
            dx2, dy2 = nxt[0] - pt[0], nxt[1] - pt[1]
            nx1, ny1 = _norm(-dy1, dx1)
            nx2, ny2 = _norm(-dy2, dx2)
            if _dot(dx1, dy1, nx2, ny2) < 0:
                nx2, ny2 = -nx2, -ny2
            nnx, nny = _norm((nx1 + nx2) / 2, (ny1 + ny2) / 2)
            new_pts.append([pt[0] + nnx * distance, pt[1] + nny * distance])
        return {**e, "id": _uid(), "points": new_pts}
    return None

def _line_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
    dx1, dy1 = x2 - x1, y2 - y1
    dx2, dy2 = x4 - x3, y4 - y3
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-12:
        return None
    t = ((x3 - x1) * dy2 - (y3 - y1) * dx2) / denom
    return (x1 + t * dx1, y1 + t * dy1)

def _trim_entity(d, id, boundary_id):
    target = next((e for e in d["entities"] if e["id"] == id), None)
    boundary = next((e for e in d["entities"] if e["id"] == boundary_id), None)
    if not target or not boundary:
        raise ValueError("entity not found")
    if target["kind"] != "line" or boundary["kind"] != "line":
        return target
    ix = _line_intersect(target["x1"], target["y1"], target["x2"], target["y2"],
                         boundary["x1"], boundary["y1"], boundary["x2"], boundary["y2"])
    if not ix:
        return target
    ixx, ixy = ix
    d1 = _hypot(target["x1"] - ixx, target["y1"] - ixy)
    d2 = _hypot(target["x2"] - ixx, target["y2"] - ixy)
    if d1 < d2:
        target["x1"], target["y1"] = ixx, ixy
    else:
        target["x2"], target["y2"] = ixx, ixy
    return target

def _fillet_corner(d, line1_id, line2_id, radius):
    l1 = next((e for e in d["entities"] if e["id"] == line1_id), None)
    l2 = next((e for e in d["entities"] if e["id"] == line2_id), None)
    if not l1 or not l2:
        raise ValueError("lines not found")
    if l1["kind"] != "line" or l2["kind"] != "line":
        raise ValueError("fillet requires line entities")
    dx1, dy1 = l1["x2"] - l1["x1"], l1["y2"] - l1["y1"]
    dx2, dy2 = l2["x2"] - l2["x1"], l2["y2"] - l2["y1"]
    n1x, n1y = _norm(-dy1, dx1)
    n2x, n2y = _norm(-dy2, dx2)
    dot = min(abs(_dot(n1x, n1y, n2x, n2y)), 0.9999)
    angle = math.acos(dot)
    offset_dist = radius / math.tan(angle / 2)
    p1x, p1y = l1["x1"] + n1x * offset_dist, l1["y1"] + n1y * offset_dist
    p2x, p2y = l2["x1"] + n2x * offset_dist, l2["y1"] + n2y * offset_dist
    ix = _line_intersect(p1x, p1y, p1x + dx1, p1y + dy1, p2x, p2y, p2x + dx2, p2y + dy2)
    if not ix:
        return None
    cx, cy = ix
    sp = radius / _hypot(p1x - cx, p1y - cy)
    sx1, sy1 = cx + (p1x - cx) * (1 - sp), cy + (p1y - cy) * (1 - sp)
    sx2, sy2 = cx + (p2x - cx) * (1 - sp), cy + (p2y - cy) * (1 - sp)
    a1 = math.atan2(sy1 - cy, sx1 - cx)
    a2 = math.atan2(sy2 - cy, sx2 - cx)
    if a1 < 0: a1 += math.pi * 2
    if a2 < 0: a2 += math.pi * 2
    l1["x2"], l1["y2"] = sx1, sy1
    l2["x1"], l2["y1"] = sx2, sy2
    arc = {"id": _uid(), "kind": "arc", "cx": cx, "cy": cy, "rx": radius, "ry": radius,
           "start_angle": a1 * 180 / math.pi, "end_angle": a2 * 180 / math.pi, "clockwise": False}
    d["entities"].append(arc)
    return arc

def _pattern_linear(d, id, count, dx, dy):
    src = next((e for e in d["entities"] if e["id"] == id), None)
    if not src:
        raise ValueError(f"entity {id} not found")
    if count < 2:
        return []
    copies = []
    for i in range(1, count):
        import copy
        c = copy.deepcopy(src)
        c["id"] = _uid()
        _doc = {"entities": [c]}
        _move_entity(_doc, c["id"], dx * i, dy * i)
        d["entities"].append(c)
        copies.append(c)
    return copies

def _pattern_polar(d, id, count, center, total_angle_deg):
    src = next((e for e in d["entities"] if e["id"] == id), None)
    if not src:
        raise ValueError(f"entity {id} not found")
    if count < 2:
        return []
    cx, cy = center if isinstance(center, (list, tuple)) else (0.0, 0.0)
    angle_step = total_angle_deg / count * math.pi / 180
    copies = []
    for i in range(1, count):
        import copy
        c = copy.deepcopy(src)
        c["id"] = _uid()
        a = angle_step * i
        cos, sin = math.cos(a), math.sin(a)
        k = c["kind"]
        if k in ("line", "dimension"):
            mx1 = cx + (c["x1"] - cx) * cos - (c["y1"] - cy) * sin
            my1 = cy + (c["x1"] - cx) * sin + (c["y1"] - cy) * cos
            mx2 = cx + (c["x2"] - cx) * cos - (c["y2"] - cy) * sin
            my2 = cy + (c["x2"] - cx) * sin + (c["y2"] - cy) * cos
            c["x1"], c["y1"], c["x2"], c["y2"] = mx1, my1, mx2, my2
        elif k in ("circle", "arc"):
            ncx = cx + (c["cx"] - cx) * cos - (c["cy"] - cy) * sin
            ncy = cy + (c["cx"] - cx) * sin + (c["cy"] - cy) * cos
            c["cx"], c["cy"] = ncx, ncy
        elif k == "rect":
            nrx = cx + (c["x"] - cx) * cos - (c["y"] - cy) * sin
            nry = cy + (c["x"] - cx) * sin + (c["y"] - cy) * cos
            c["x"], c["y"] = nrx, nry
            c["rotation"] = c.get("rotation", 0) + angle_step * i
        elif k == "text":
            ntx = cx + (c["x"] - cx) * cos - (c["y"] - cy) * sin
            nty = cy + (c["x"] - cx) * sin + (c["y"] - cy) * cos
            c["x"], c["y"] = ntx, nty
            c["rotation"] = c.get("rotation", 0) + angle_step * i
        elif k in ("polyline", "spline"):
            c["points"] = [[cx + (px - cx) * cos - (py - cy) * sin,
                           cy + (px - cx) * sin + (py - cy) * cos] for px, py in c.get("points", [])]
        d["entities"].append(c)
        copies.append(c)
    return copies

def _export_dxf(d):
    lines = []
    def ln(*args):
        lines.append("\n".join(str(x) for x in args))
    ln(0, "SECTION", 2, "HEADER")
    ln(9, "$ACADVER", 1, "AC1009")
    ln(0, "ENDSEC")
    ln(0, "SECTION", 2, "ENTITIES")
    for e in d.get("entities", []):
        if e["kind"] == "line":
            ln(0, "LINE", 8, "0", 10, e["x1"], 20, e["y1"], 30, 0, 11, e["x2"], 21, e["y2"], 31, 0)
        elif e["kind"] == "circle":
            ln(0, "CIRCLE", 8, "0", 10, e["cx"], 20, e["cy"], 30, 0, 40, e["r"])
        elif e["kind"] == "arc":
            ln(0, "ARC", 8, "0", 10, e["cx"], 20, e["cy"], 30, 0, 40, e["rx"], 50, e["start_angle"], 51, e["end_angle"])
        elif e["kind"] == "polyline":
            pts = e.get("points", [])
            ln(0, "POLYLINE", 8, "0", 66, 1, 70, 1 if e.get("closed") else 0)
            for px, py in pts:
                ln(0, "VERTEX", 8, "0", 10, px, 20, py, 30, 0)
            ln(0, "SEQEND", 8, "0")
        elif e["kind"] == "text":
            ln(0, "TEXT", 8, "0", 10, e["x"], 20, e["y"], 30, 0, 40, e.get("size", 12), 1, str(e["value"])[:250])
    ln(0, "ENDSEC")
    ln(0, "EOF")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Tool specs
# ---------------------------------------------------------------------------

create_draft_spec = ToolSpec(
    name="create_draft",
    description="Create a new empty .draft document.",
    input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
)

add_draft_entity_spec = ToolSpec(
    name="add_draft_entity",
    description="Add an entity to a .draft document.",
    input_schema={"type": "object", "properties": {
        "draft": {"type": "object"}, "entity": {"type": "object"}
    }, "required": ["draft", "entity"]},
)

offset_draft_entity_spec = ToolSpec(
    name="offset_draft_entity",
    description="Offset a line or polyline entity perpendicularly.",
    input_schema={"type": "object", "properties": {
        "draft": {"type": "object"}, "id": {"type": "string"}, "distance": {"type": "number"}
    }, "required": ["draft", "id", "distance"]},
)

fillet_draft_corner_spec = ToolSpec(
    name="fillet_draft_corner",
    description="Fillet (round) the corner between two lines with a given radius.",
    input_schema={"type": "object", "properties": {
        "draft": {"type": "object"}, "line1_id": {"type": "string"}, "line2_id": {"type": "string"}, "radius": {"type": "number"}
    }, "required": ["draft", "line1_id", "line2_id", "radius"]},
)

pattern_linear_draft_spec = ToolSpec(
    name="pattern_linear_draft",
    description="Array-copy an entity in a linear pattern.",
    input_schema={"type": "object", "properties": {
        "draft": {"type": "object"}, "id": {"type": "string"}, "count": {"type": "integer"}, "dx": {"type": "number"}, "dy": {"type": "number"}
    }, "required": ["draft", "id", "count", "dx", "dy"]},
)

export_draft_dxf_spec = ToolSpec(
    name="export_draft_dxf",
    description="Export a .draft document to DXF R12 text.",
    input_schema={"type": "object", "properties": {"draft": {"type": "object"}}, "required": ["draft"]},
)

@register(create_draft_spec, write=False)
async def create_draft(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    draft = _default_draft(a.get("name", "Untitled"))
    return ok_payload(draft)

@register(add_draft_entity_spec, write=False)
async def add_draft_entity(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    draft = a.get("draft")
    entity = a.get("entity")
    if not draft or not entity:
        return err_payload("draft and entity are required", "BAD_ARGS")
    try:
        result = _add_entity(draft, entity)
        return ok_payload({"draft": draft, "entity": result})
    except Exception as e:
        return err_payload(str(e), "VALIDATION_ERROR")

@register(offset_draft_entity_spec, write=False)
async def offset_draft_entity(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    draft = a.get("draft")
    if not draft:
        return err_payload("draft is required", "BAD_ARGS")
    try:
        result = _offset_entity(draft, a.get("id"), a.get("distance", 1.0))
        return ok_payload(result)
    except Exception as e:
        return err_payload(str(e), "OP_ERROR")

@register(fillet_draft_corner_spec, write=False)
async def fillet_draft_corner(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    draft = a.get("draft")
    if not draft:
        return err_payload("draft is required", "BAD_ARGS")
    try:
        result = _fillet_corner(draft, a.get("line1_id"), a.get("line2_id"), a.get("radius", 1.0))
        return ok_payload({"draft": draft, "arc": result})
    except Exception as e:
        return err_payload(str(e), "OP_ERROR")

@register(pattern_linear_draft_spec, write=False)
async def pattern_linear_draft(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    draft = a.get("draft")
    if not draft:
        return err_payload("draft is required", "BAD_ARGS")
    try:
        result = _pattern_linear(draft, a.get("id"), a.get("count", 2), a.get("dx", 0), a.get("dy", 0))
        return ok_payload({"draft": draft, "copies": result})
    except Exception as e:
        return err_payload(str(e), "OP_ERROR")

@register(export_draft_dxf_spec, write=False)
async def export_draft_dxf(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    draft = a.get("draft")
    if not draft:
        return err_payload("draft is required", "BAD_ARGS")
    try:
        result = _export_dxf(draft)
        return ok_payload({"dxf": result})
    except Exception as e:
        return err_payload(str(e), "OP_ERROR")
