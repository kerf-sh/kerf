"""
curve_ops.py — LLM tools for Rhino-parity curve operations.

All geometry is pure Python; no OCCT calls.  The tools read/write sketch JSON
from the database via the standard _load_sketch / _save_sketch helpers cloned
from sketch.py (no import of that module to avoid circular deps).
"""
import json
import math
import uuid
from typing import Any

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


# ─── internal sketch I/O (mirrors sketch.py) ─────────────────────────────────

def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


async def _load_sketch(ctx: ProjectCtx, file_path: str) -> tuple[dict, Any]:
    row = await ctx.pool.fetchrow(
        "SELECT content FROM files WHERE project_id = $1 AND path = $2 AND deleted_at IS NULL",
        ctx.project_id,
        file_path,
    )
    if not row:
        return {}, err_payload(f"file not found: {file_path}", "NOT_FOUND")
    try:
        sketch = json.loads(row["content"])
    except Exception as e:
        return {}, err_payload(f"invalid JSON: {e}", "BAD_CONTENT")
    return sketch, None


async def _save_sketch(ctx: ProjectCtx, file_path: str, sketch: dict) -> None:
    content = json.dumps(sketch, indent=2)
    await ctx.pool.execute(
        "UPDATE files SET content = $1, updated_at = now() "
        "WHERE project_id = $2 AND path = $3 AND deleted_at IS NULL",
        content,
        ctx.project_id,
        file_path,
    )


def _find_entity(sketch: dict, entity_id: str) -> dict | None:
    for e in sketch.get("entities", []):
        if e.get("id") == entity_id:
            return e
    return None


# ─── pure geometry helpers ────────────────────────────────────────────────────

def _vadd(a, b):   return [a[0]+b[0], a[1]+b[1], a[2]+b[2]]
def _vsub(a, b):   return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]
def _vscale(v, s): return [v[0]*s, v[1]*s, v[2]*s]
def _vdot(a, b):   return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def _vlen(v):      return math.sqrt(_vdot(v, v))
def _vnorm(v):
    l = _vlen(v)
    return _vscale(v, 1/l) if l > 1e-15 else [0.0, 0.0, 0.0]
def _vcross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def _vlerp(a, b, t): return _vadd(_vscale(a, 1-t), _vscale(b, t))


def _uniform_knots(n: int, d: int) -> list[float]:
    m = n + d + 1
    knots = []
    for i in range(m + 1):
        if i <= d:
            knots.append(0.0)
        elif i >= m - d:
            knots.append(1.0)
        else:
            knots.append((i - d) / (n - d + 1))
    return knots


def _de_boor(degree, control_points, knots, u):
    n = len(control_points) - 1
    u_min = knots[degree]
    u_max = knots[n + 1]
    uu = u_min + u * (u_max - u_min)

    k = degree
    for i in range(degree, n + 1):
        if knots[i] <= uu < knots[i + 1]:
            k = i
            break
        if uu >= knots[n + 1]:
            k = n
            break

    d = [list(p) for p in control_points[k - degree: k + 1]]
    for r in range(1, degree + 1):
        for j in range(degree, r - 1, -1):
            denom = knots[k - degree + j + r] - knots[k - degree + j]
            alpha = 0.0 if denom < 1e-15 else (uu - knots[k - degree + j]) / denom
            d[j] = _vlerp(d[j-1], d[j], alpha)
    return d[degree]


def _entity_point_at(entity: dict, t: float) -> list[float]:
    """Evaluate a sketch entity at parameter t ∈ [0,1]. Returns [x,y,z]."""
    kind = entity.get("type") or entity.get("kind", "")
    t = max(0.0, min(1.0, t))

    if kind == "line":
        x1, y1 = entity.get("x1", 0), entity.get("y1", 0)
        x2, y2 = entity.get("x2", 0), entity.get("y2", 0)
        z1, z2 = entity.get("z1", 0), entity.get("z2", 0)
        # Support sketch entities that use p1/p2 point-ids resolved elsewhere.
        return _vlerp([x1, y1, z1], [x2, y2, z2], t)

    if kind in ("arc", "circle"):
        cx, cy, cz = entity.get("cx", 0), entity.get("cy", 0), entity.get("cz", 0)
        r = entity.get("radius", 1)
        if kind == "circle":
            theta = t * 2 * math.pi
        else:
            start = entity.get("startAngle", 0)
            end   = entity.get("endAngle", math.pi / 2)
            sweep = end - start
            while sweep <= 0:
                sweep += 2 * math.pi
            theta = start + sweep * t
        return [cx + r * math.cos(theta), cy + r * math.sin(theta), cz]

    if kind in ("bspline", "nurbs"):
        cp_raw = entity.get("controlPoints", [])
        cp = []
        for p in cp_raw:
            if isinstance(p, (list, tuple)):
                cp.append([float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0])
            else:
                cp.append([float(p.get("x", 0)), float(p.get("y", 0)), float(p.get("z", 0))])
        degree = entity.get("degree", 3)
        knots = entity.get("knots") or _uniform_knots(len(cp) - 1, degree)
        return _de_boor(degree, cp, knots, t)

    if kind == "polyline":
        pts_raw = entity.get("points", [])
        pts = []
        for p in pts_raw:
            if isinstance(p, (list, tuple)):
                pts.append([float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0])
            else:
                pts.append([float(p.get("x", 0)), float(p.get("y", 0)), float(p.get("z", 0))])
        if len(pts) < 2:
            return pts[0] if pts else [0, 0, 0]
        total = len(pts) - 1
        scaled = t * total
        seg = min(int(scaled), total - 1)
        local = scaled - seg
        return _vlerp(pts[seg], pts[seg + 1], local)

    return [0.0, 0.0, 0.0]


def _entity_tangent_at(entity: dict, t: float) -> list[float]:
    """Unit tangent at parameter t."""
    kind = entity.get("type") or entity.get("kind", "")
    t = max(0.0, min(1.0, t))

    if kind == "line":
        d = _vsub(
            [entity.get("x2", 0), entity.get("y2", 0), entity.get("z2", 0)],
            [entity.get("x1", 0), entity.get("y1", 0), entity.get("z1", 0)],
        )
        return _vnorm(d)

    if kind in ("arc", "circle"):
        if kind == "circle":
            theta = t * 2 * math.pi
        else:
            start = entity.get("startAngle", 0)
            end   = entity.get("endAngle", math.pi / 2)
            sweep = end - start
            while sweep <= 0:
                sweep += 2 * math.pi
            theta = start + sweep * t
        return _vnorm([-math.sin(theta), math.cos(theta), 0.0])

    # Finite-difference tangent for anything else.
    eps = 1e-4
    p1 = _entity_point_at(entity, max(0.0, t - eps))
    p2 = _entity_point_at(entity, min(1.0, t + eps))
    return _vnorm(_vsub(p2, p1))


def _discretize_entity(entity: dict, n: int = 64) -> list[list[float]]:
    return [_entity_point_at(entity, i / n) for i in range(n + 1)]


def _intersect_entities(entity_a: dict, entity_b: dict, tolerance: float = 0.01) -> list[dict]:
    N = 128
    pts_a = _discretize_entity(entity_a, N)
    pts_b = _discretize_entity(entity_b, N)
    tol2 = tolerance * tolerance
    results = []

    for i in range(N):
        a0, a1 = pts_a[i], pts_a[i + 1]
        for j in range(N):
            b0, b1 = pts_b[j], pts_b[j + 1]
            u = _vsub(a1, a0)
            v = _vsub(b1, b0)
            r = _vsub(a0, b0)
            a_dot = _vdot(u, u)
            e_dot = _vdot(v, v)
            if a_dot < 1e-15 or e_dot < 1e-15:
                continue
            f = _vdot(v, r)
            b = _vdot(u, v)
            denom = a_dot * e_dot - b * b
            if abs(denom) < 1e-15:
                s, tt = 0.0, f / e_dot
            else:
                c = _vdot(u, r)
                s  = (b * f - c * e_dot) / denom
                tt = (a_dot * f - b * c) / denom
            s  = max(0.0, min(1.0, s))
            tt = max(0.0, min(1.0, tt))

            pA = _vadd(a0, _vscale(u, s))
            pB = _vadd(b0, _vscale(v, tt))
            dist2 = _vdot(_vsub(pA, pB), _vsub(pA, pB))
            if dist2 <= tol2:
                mid = _vlerp(pA, pB, 0.5)
                if not any(
                    _vdot(_vsub([r2["x"], r2["y"], r2["z"]], mid),
                          _vsub([r2["x"], r2["y"], r2["z"]], mid)) <= tol2
                    for r2 in results
                ):
                    results.append({
                        "x": mid[0], "y": mid[1], "z": mid[2],
                        "tA": (i + s) / N, "tB": (j + tt) / N,
                    })
    return results


# ─── tool: curve_project_to_surface ─────────────────────────────────────────

curve_project_to_surface_spec = ToolSpec(
    name="curve_project_to_surface",
    description=(
        "Project a curve entity from a sketch onto a plane (XY, XZ, YZ, or "
        "an arbitrary plane given as {origin, normal}), returning a new 2D "
        "polyline entity appended to the sketch."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sketch_file_id": {
                "type": "string",
                "description": "File path (or UUID) of the .sketch JSON file.",
            },
            "entity_id": {
                "type": "string",
                "description": "ID of the entity to project.",
            },
            "target_plane": {
                "description": "'XY', 'XZ', 'YZ', or {origin:{x,y,z}, normal:{x,y,z}}.",
            },
        },
        "required": ["sketch_file_id", "entity_id", "target_plane"],
    },
)


@register(curve_project_to_surface_spec, write=True)
async def run_curve_project_to_surface(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path      = a.get("sketch_file_id", "")
    entity_id = a.get("entity_id", "")
    plane     = a.get("target_plane")

    if not path:
        return err_payload("sketch_file_id is required", "BAD_ARGS")
    if not entity_id:
        return err_payload("entity_id is required", "BAD_ARGS")
    if not plane:
        return err_payload("target_plane is required", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    entity = _find_entity(sketch, entity_id)
    if entity is None:
        return err_payload(f"entity '{entity_id}' not found", "NOT_FOUND")

    # Build projection axes.
    if plane == "XY":
        origin = [0, 0, 0]; normal = [0, 0, 1]
        u_axis = [1, 0, 0]; v_axis = [0, 1, 0]
    elif plane == "XZ":
        origin = [0, 0, 0]; normal = [0, 1, 0]
        u_axis = [1, 0, 0]; v_axis = [0, 0, 1]
    elif plane == "YZ":
        origin = [0, 0, 0]; normal = [1, 0, 0]
        u_axis = [0, 1, 0]; v_axis = [0, 0, 1]
    else:
        try:
            o = plane["origin"]; n = plane["normal"]
            origin = [o["x"], o["y"], o["z"]]
            normal = _vnorm([n["x"], n["y"], n["z"]])
        except (KeyError, TypeError) as e:
            return err_payload(f"invalid target_plane: {e}", "BAD_ARGS")
        ref = [1, 0, 0] if abs(normal[0]) < 0.9 else [0, 1, 0]
        u_axis = _vnorm(_vcross(ref, normal))
        v_axis = _vcross(normal, u_axis)

    pts3d = _discretize_entity(entity, 64)
    projected = []
    for p in pts3d:
        rel = _vsub(p, origin)
        d   = _vdot(rel, normal)
        ip  = _vsub(rel, _vscale(normal, d))
        projected.append({"x": _vdot(ip, u_axis), "y": _vdot(ip, v_axis), "z": 0.0})

    new_entity = {
        "id": _gen_id(),
        "type": "polyline",
        "points": projected,
        "source_projection": {"entity_id": entity_id, "plane": str(plane)},
    }
    sketch.setdefault("entities", []).append(new_entity)
    await _save_sketch(ctx, path, sketch)
    return ok_payload({"ok": True, "id": new_entity["id"], "point_count": len(projected)})


# ─── tool: curve_intersect ───────────────────────────────────────────────────

curve_intersect_spec = ToolSpec(
    name="curve_intersect",
    description="Find intersection points between two curve entities in a sketch.",
    input_schema={
        "type": "object",
        "properties": {
            "sketch_file_id": {"type": "string"},
            "entity_a_id":    {"type": "string"},
            "entity_b_id":    {"type": "string"},
            "tolerance":      {"type": "number", "description": "Default 0.01."},
        },
        "required": ["sketch_file_id", "entity_a_id", "entity_b_id"],
    },
)


@register(curve_intersect_spec, write=False)
async def run_curve_intersect(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path   = a.get("sketch_file_id", "")
    ea_id  = a.get("entity_a_id", "")
    eb_id  = a.get("entity_b_id", "")
    tol    = float(a.get("tolerance", 0.01))

    for label, val in [("sketch_file_id", path), ("entity_a_id", ea_id), ("entity_b_id", eb_id)]:
        if not val:
            return err_payload(f"{label} is required", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    ea = _find_entity(sketch, ea_id)
    if ea is None:
        return err_payload(f"entity '{ea_id}' not found", "NOT_FOUND")
    eb = _find_entity(sketch, eb_id)
    if eb is None:
        return err_payload(f"entity '{eb_id}' not found", "NOT_FOUND")

    hits = _intersect_entities(ea, eb, tol)
    return ok_payload({"ok": True, "intersections": hits, "count": len(hits)})


# ─── tool: curve_blend ───────────────────────────────────────────────────────

curve_blend_spec = ToolSpec(
    name="curve_blend",
    description=(
        "Create a smooth B-spline blend curve connecting the end of entity_a "
        "to the end of entity_b with the requested G0/G1/G2 continuity.  "
        "The new blend curve is appended to the sketch as a 'bspline' entity."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sketch_file_id": {"type": "string"},
            "entity_a_id":    {"type": "string"},
            "end_a":          {"type": "string", "enum": ["start", "end"], "description": "Which end of entity_a to use."},
            "entity_b_id":    {"type": "string"},
            "end_b":          {"type": "string", "enum": ["start", "end"], "description": "Which end of entity_b to use."},
            "continuity":     {"type": "string", "enum": ["G0", "G1", "G2"], "description": "Default G1."},
        },
        "required": ["sketch_file_id", "entity_a_id", "end_a", "entity_b_id", "end_b"],
    },
)


@register(curve_blend_spec, write=True)
async def run_curve_blend(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path        = a.get("sketch_file_id", "")
    ea_id       = a.get("entity_a_id", "")
    end_a       = a.get("end_a", "end")
    eb_id       = a.get("entity_b_id", "")
    end_b       = a.get("end_b", "start")
    continuity  = a.get("continuity", "G1")

    if not path:
        return err_payload("sketch_file_id is required", "BAD_ARGS")
    if continuity not in ("G0", "G1", "G2"):
        return err_payload("continuity must be G0, G1, or G2", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    ea = _find_entity(sketch, ea_id)
    if ea is None:
        return err_payload(f"entity '{ea_id}' not found", "NOT_FOUND")
    eb = _find_entity(sketch, eb_id)
    if eb is None:
        return err_payload(f"entity '{eb_id}' not found", "NOT_FOUND")

    t_a = 1.0 if end_a == "end" else 0.0
    t_b = 0.0 if end_b == "start" else 1.0

    pA = _entity_point_at(ea, t_a)
    pB = _entity_point_at(eb, t_b)
    tA = _entity_tangent_at(ea, t_a)
    tB = _entity_tangent_at(eb, t_b)

    dist = _vlen(_vsub(pB, pA))
    scale = max(dist / 3, 1e-3)

    if continuity == "G0":
        cp = [
            {"x": pA[0], "y": pA[1], "z": pA[2]},
            {"x": pB[0], "y": pB[1], "z": pB[2]},
        ]
        degree = 1
        knots = [0, 0, 1, 1]
    elif continuity == "G1":
        h1 = _vadd(pA, _vscale(tA, scale))
        h2 = _vsub(pB, _vscale(tB, scale))
        cp = [
            {"x": pA[0], "y": pA[1], "z": pA[2]},
            {"x": h1[0], "y": h1[1], "z": h1[2]},
            {"x": h2[0], "y": h2[1], "z": h2[2]},
            {"x": pB[0], "y": pB[1], "z": pB[2]},
        ]
        degree = 3
        knots = [0, 0, 0, 0, 1, 1, 1, 1]
    else:  # G2
        eps = 1e-4
        tA2 = _entity_tangent_at(ea, max(0.0, t_a - eps))
        tB2 = _entity_tangent_at(eb, min(1.0, t_b + eps))
        kA = _vscale(_vsub(tA, tA2), 1.0 / eps)
        kB = _vscale(_vsub(tB2, tB), 1.0 / eps)
        h1 = _vadd(pA, _vscale(tA, scale))
        h2 = _vadd(h1, _vscale(_vadd(tA, _vscale(kA, scale * 0.5)), scale * 0.5))
        h5 = _vsub(pB, _vscale(tB, scale))
        h4 = _vsub(h5, _vscale(_vadd(tB, _vscale(kB, scale * 0.5)), scale * 0.5))
        h3 = _vlerp(h2, h4, 0.5)
        raw_cp = [pA, h1, h2, h3, h4, h5, pB]
        cp = [{"x": p[0], "y": p[1], "z": p[2]} for p in raw_cp]
        degree = 5
        knots = _uniform_knots(len(cp) - 1, degree)

    new_entity = {
        "id": _gen_id(),
        "type": "bspline",
        "degree": degree,
        "controlPoints": cp,
        "knots": knots,
        "blend_meta": {
            "entity_a": ea_id, "end_a": end_a,
            "entity_b": eb_id, "end_b": end_b,
            "continuity": continuity,
        },
    }
    sketch.setdefault("entities", []).append(new_entity)
    await _save_sketch(ctx, path, sketch)
    return ok_payload({"ok": True, "id": new_entity["id"]})


# ─── tool: curve_match ───────────────────────────────────────────────────────

curve_match_spec = ToolSpec(
    name="curve_match",
    description=(
        "Adjust the start of target_entity so that it meets the end of "
        "source_entity with the requested G0/G1/G2 continuity. "
        "Modifies target_entity in place (bspline control points adjusted). "
        "Returns the updated entity id."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sketch_file_id":     {"type": "string"},
            "source_entity_id":   {"type": "string"},
            "target_entity_id":   {"type": "string"},
            "continuity":         {"type": "string", "enum": ["G0", "G1", "G2"], "description": "Default G1."},
        },
        "required": ["sketch_file_id", "source_entity_id", "target_entity_id"],
    },
)


@register(curve_match_spec, write=True)
async def run_curve_match(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path      = a.get("sketch_file_id", "")
    src_id    = a.get("source_entity_id", "")
    tgt_id    = a.get("target_entity_id", "")
    cont      = a.get("continuity", "G1")

    if not path:
        return err_payload("sketch_file_id is required", "BAD_ARGS")
    if cont not in ("G0", "G1", "G2"):
        return err_payload("continuity must be G0, G1, or G2", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    src = _find_entity(sketch, src_id)
    if src is None:
        return err_payload(f"source entity '{src_id}' not found", "NOT_FOUND")
    tgt = _find_entity(sketch, tgt_id)
    if tgt is None:
        return err_payload(f"target entity '{tgt_id}' not found", "NOT_FOUND")

    pA = _entity_point_at(src, 1.0)
    tA = _entity_tangent_at(src, 1.0)

    if tgt.get("type") == "bspline":
        cp = [list(p.values()) if isinstance(p, dict) else list(p)
              for p in tgt.get("controlPoints", [])]
        cp_dicts = tgt["controlPoints"]
        if cp_dicts:
            cp_dicts[0] = {"x": pA[0], "y": pA[1], "z": pA[2]}
        if cont != "G0" and len(cp_dicts) >= 2:
            d = _vlen(_vsub(
                [cp_dicts[1].get("x", 0), cp_dicts[1].get("y", 0), cp_dicts[1].get("z", 0)],
                [cp_dicts[0].get("x", 0), cp_dicts[0].get("y", 0), cp_dicts[0].get("z", 0)],
            )) or 1.0
            p2 = _vadd(pA, _vscale(tA, d))
            cp_dicts[1] = {"x": p2[0], "y": p2[1], "z": p2[2]}
        if cont == "G2" and len(cp_dicts) >= 3:
            eps = 1e-4
            tA2 = _entity_tangent_at(src, max(0.0, 1.0 - eps))
            kA  = _vscale(_vsub(tA, tA2), 1.0 / eps)
            d1 = _vlen(_vsub(
                [cp_dicts[1].get("x", 0), cp_dicts[1].get("y", 0), cp_dicts[1].get("z", 0)],
                [cp_dicts[0].get("x", 0), cp_dicts[0].get("y", 0), cp_dicts[0].get("z", 0)],
            )) or 1.0
            p3 = _vadd(
                [cp_dicts[1]["x"], cp_dicts[1]["y"], cp_dicts[1]["z"]],
                _vadd(_vscale(tA, d1), _vscale(kA, d1 * d1 * 0.5)),
            )
            cp_dicts[2] = {"x": p3[0], "y": p3[1], "z": p3[2]}
    elif tgt.get("type") == "line":
        tgt["x1"] = pA[0]; tgt["y1"] = pA[1]; tgt["z1"] = pA[2]
    elif tgt.get("type") == "polyline":
        pts = tgt.get("points", [])
        if pts:
            if isinstance(pts[0], dict):
                pts[0] = {"x": pA[0], "y": pA[1], "z": pA[2]}
            else:
                pts[0] = [pA[0], pA[1], pA[2]]

    await _save_sketch(ctx, path, sketch)
    return ok_payload({"ok": True, "id": tgt_id})


# ─── tool: curve_offset_3d ───────────────────────────────────────────────────

curve_offset_3d_spec = ToolSpec(
    name="curve_offset_3d",
    description=(
        "Offset a curve entity in 3D space by moving every point by `distance` "
        "along a given axis or normal vector ('X', 'Y', 'Z', or "
        "{x,y,z} dict).  Appends a new polyline entity to the sketch."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sketch_file_id": {"type": "string"},
            "entity_id":      {"type": "string"},
            "distance":       {"type": "number"},
            "axis_or_normal": {
                "description": "'X', 'Y', 'Z', or {x:float, y:float, z:float}.",
            },
        },
        "required": ["sketch_file_id", "entity_id", "distance", "axis_or_normal"],
    },
)


@register(curve_offset_3d_spec, write=True)
async def run_curve_offset_3d(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path     = a.get("sketch_file_id", "")
    eid      = a.get("entity_id", "")
    distance = a.get("distance")
    axis     = a.get("axis_or_normal")

    if not path:
        return err_payload("sketch_file_id is required", "BAD_ARGS")
    if not eid:
        return err_payload("entity_id is required", "BAD_ARGS")
    if distance is None:
        return err_payload("distance is required", "BAD_ARGS")
    if axis is None:
        return err_payload("axis_or_normal is required", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    entity = _find_entity(sketch, eid)
    if entity is None:
        return err_payload(f"entity '{eid}' not found", "NOT_FOUND")

    if axis == "X":
        dir_vec = [1.0, 0.0, 0.0]
    elif axis == "Y":
        dir_vec = [0.0, 1.0, 0.0]
    elif axis == "Z":
        dir_vec = [0.0, 0.0, 1.0]
    else:
        try:
            dir_vec = _vnorm([float(axis["x"]), float(axis["y"]), float(axis["z"])])
        except (KeyError, TypeError) as e:
            return err_payload(f"invalid axis_or_normal: {e}", "BAD_ARGS")

    offset = _vscale(dir_vec, float(distance))
    pts3d = _discretize_entity(entity, 64)
    new_points = [{"x": p[0] + offset[0], "y": p[1] + offset[1], "z": p[2] + offset[2]} for p in pts3d]

    new_entity = {
        "id": _gen_id(),
        "type": "polyline",
        "points": new_points,
        "offset_meta": {"source_entity_id": eid, "distance": distance, "axis": str(axis)},
    }
    sketch.setdefault("entities", []).append(new_entity)
    await _save_sketch(ctx, path, sketch)
    return ok_payload({"ok": True, "id": new_entity["id"]})


# ─── tool: polyline_to_nurbs ─────────────────────────────────────────────────

polyline_to_nurbs_spec = ToolSpec(
    name="polyline_to_nurbs",
    description=(
        "Fit a B-spline (NURBS) of given degree to a polyline entity.  "
        "Appends the resulting bspline entity; optionally removes the source polyline."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sketch_file_id":   {"type": "string"},
            "polyline_entity_id": {"type": "string"},
            "degree":           {"type": "integer", "description": "B-spline degree (default 3)."},
            "replace":          {"type": "boolean", "description": "Remove the source polyline (default false)."},
        },
        "required": ["sketch_file_id", "polyline_entity_id"],
    },
)


@register(polyline_to_nurbs_spec, write=True)
async def run_polyline_to_nurbs(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path    = a.get("sketch_file_id", "")
    poly_id = a.get("polyline_entity_id", "")
    degree  = int(a.get("degree", 3))
    replace = bool(a.get("replace", False))

    if not path:
        return err_payload("sketch_file_id is required", "BAD_ARGS")
    if not poly_id:
        return err_payload("polyline_entity_id is required", "BAD_ARGS")

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    entity = _find_entity(sketch, poly_id)
    if entity is None:
        return err_payload(f"entity '{poly_id}' not found", "NOT_FOUND")
    if entity.get("type") not in ("polyline",):
        return err_payload("entity must be a polyline", "BAD_ARGS")

    pts_raw = entity.get("points", [])
    pts = []
    for p in pts_raw:
        if isinstance(p, dict):
            pts.append({"x": float(p.get("x", 0)), "y": float(p.get("y", 0)), "z": float(p.get("z", 0))})
        else:
            pts.append({"x": float(p[0]), "y": float(p[1]), "z": float(p[2]) if len(p) > 2 else 0.0})

    if len(pts) < 2:
        return err_payload("polyline must have at least 2 points", "BAD_ARGS")

    n = len(pts) - 1
    d = min(degree, n)
    knots = _uniform_knots(n, d)

    new_entity = {
        "id": _gen_id(),
        "type": "bspline",
        "degree": d,
        "controlPoints": pts,
        "knots": knots,
        "nurbs_source": poly_id,
    }

    entities = sketch.setdefault("entities", [])
    if replace:
        sketch["entities"] = [e for e in entities if e.get("id") != poly_id]
    sketch["entities"].append(new_entity)

    await _save_sketch(ctx, path, sketch)
    return ok_payload({"ok": True, "id": new_entity["id"], "degree": d, "control_points": len(pts)})


# ─── tool: simplify_curve ────────────────────────────────────────────────────

simplify_curve_spec = ToolSpec(
    name="simplify_curve",
    description=(
        "Reduce the complexity of a curve entity in place: "
        "Douglas-Peucker for polylines, knot removal for B-splines. "
        "Modifies the entity in the sketch file and returns the new point count."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sketch_file_id": {"type": "string"},
            "entity_id":      {"type": "string"},
            "tolerance":      {"type": "number", "description": "Max deviation allowed (mm)."},
        },
        "required": ["sketch_file_id", "entity_id", "tolerance"],
    },
)


def _douglas_peucker(pts: list, tol: float) -> list:
    if len(pts) <= 2:
        return pts
    first, last = pts[0], pts[-1]
    line = [last[i] - first[i] for i in range(3)]
    line_len = math.sqrt(sum(x * x for x in line))

    max_dist, max_idx = -1.0, 0
    for i in range(1, len(pts) - 1):
        if line_len < 1e-15:
            dist = math.sqrt(sum((pts[i][j] - first[j]) ** 2 for j in range(3)))
        else:
            diff = [pts[i][j] - first[j] for j in range(3)]
            t = max(0.0, min(1.0, sum(diff[j] * line[j] for j in range(3)) / (line_len * line_len)))
            proj = [first[j] + line[j] * t for j in range(3)]
            dist = math.sqrt(sum((pts[i][j] - proj[j]) ** 2 for j in range(3)))
        if dist > max_dist:
            max_dist, max_idx = dist, i

    if max_dist <= tol:
        return [first, last]
    left  = _douglas_peucker(pts[:max_idx + 1], tol)
    right = _douglas_peucker(pts[max_idx:], tol)
    return left[:-1] + right


@register(simplify_curve_spec, write=True)
async def run_simplify_curve(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    path  = a.get("sketch_file_id", "")
    eid   = a.get("entity_id", "")
    tol   = a.get("tolerance")

    if not path:
        return err_payload("sketch_file_id is required", "BAD_ARGS")
    if not eid:
        return err_payload("entity_id is required", "BAD_ARGS")
    if tol is None:
        return err_payload("tolerance is required", "BAD_ARGS")
    tol = float(tol)

    sketch, err = await _load_sketch(ctx, path)
    if err:
        return err

    entity = _find_entity(sketch, eid)
    if entity is None:
        return err_payload(f"entity '{eid}' not found", "NOT_FOUND")

    kind = entity.get("type", "")
    original_count = 0
    new_count = 0

    if kind == "polyline":
        pts_raw = entity.get("points", [])
        pts = []
        for p in pts_raw:
            if isinstance(p, dict):
                pts.append([p.get("x", 0), p.get("y", 0), p.get("z", 0)])
            else:
                pts.append([p[0], p[1], p[2] if len(p) > 2 else 0.0])
        original_count = len(pts)
        simplified = _douglas_peucker(pts, tol)
        new_count = len(simplified)
        entity["points"] = [{"x": p[0], "y": p[1], "z": p[2]} for p in simplified]

    elif kind == "bspline":
        cp = entity.get("controlPoints", [])
        original_count = len(cp)
        degree = entity.get("degree", 3)
        knots = entity.get("knots") or _uniform_knots(len(cp) - 1, degree)

        # Sample original for deviation checking.
        N = 128
        orig_pts = [_de_boor(degree, [
            [p.get("x", 0), p.get("y", 0), p.get("z", 0)] if isinstance(p, dict) else list(p)
            for p in cp
        ], knots, i / N) for i in range(N + 1)]

        changed = True
        while changed:
            changed = False
            int_start = degree + 1
            int_end = len(knots) - degree - 2
            for ki in range(int_start, int_end + 1):
                if ki >= len(knots) - degree - 1:
                    break
                new_knots = knots[:ki] + knots[ki + 1:]
                if len(new_knots) < 2 * (degree + 1):
                    break
                mid_idx = max(1, min(len(cp) - 2, round(
                    (ki - degree - 1) * len(cp) / max(1, len(knots) - 2 * (degree + 1) + 1)
                )))
                cp_flat = [
                    [p.get("x", 0), p.get("y", 0), p.get("z", 0)] if isinstance(p, dict) else list(p)
                    for p in cp
                ]
                new_cp_flat = cp_flat[:mid_idx] + cp_flat[mid_idx + 1:]
                if len(new_cp_flat) < degree + 1:
                    break
                max_dev = 0.0
                for i in range(N + 1):
                    cpt = _de_boor(degree, new_cp_flat, new_knots, i / N)
                    dev = math.sqrt(sum((cpt[j] - orig_pts[i][j]) ** 2 for j in range(3)))
                    max_dev = max(max_dev, dev)
                if max_dev <= tol:
                    cp = [{"x": p[0], "y": p[1], "z": p[2]} for p in new_cp_flat]
                    knots = new_knots
                    changed = True
                    break

        new_count = len(cp)
        entity["controlPoints"] = cp
        entity["knots"] = knots
    else:
        return ok_payload({"ok": True, "id": eid, "message": "entity type not simplifiable", "original_count": 0, "new_count": 0})

    await _save_sketch(ctx, path, sketch)
    return ok_payload({
        "ok": True,
        "id": eid,
        "original_count": original_count,
        "new_count": new_count,
        "reduction": original_count - new_count,
    })
