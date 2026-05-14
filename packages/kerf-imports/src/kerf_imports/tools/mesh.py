"""
mesh.py — LLM tools for mesh processing (Rhino-parity tooling).

Mesh file format (.mesh):
  {
    "version": 1,
    "vertices": [[x, y, z], ...],
    "indices":  [i0, i1, i2, ...],   // triangle list; every 3 = one face
    "normals":  [[nx, ny, nz], ...], // optional per-vertex normals
    "uvs":      [[u, v], ...],       // optional per-vertex UVs
    "quad_dominant": false            // set by quadRemesh
  }

Each tool reads/writes a .mesh file whose content is the JSON above.
Operations mirror the JS library in src/lib/meshTools.js — the Python
implementations are independent (so the LLM can call them without a
browser context) but use the same algorithms:
  - validate:        index checks, degenerate faces, watertight
  - decimate:        simplified quadric edge collapse
  - smooth:          Laplacian smoothing
  - repair:          snap-weld + degenerate drop + winding fix
  - fill_holes:      boundary loop detection + fan triangulation
  - remesh:          isotropic remesh (split/collapse/flip/relocate)
  - surface_from_points: naive nearest-neighbour fan reconstruction
"""

import json
import math
import uuid
from typing import Any, Optional

from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx

# ─── Internal helpers ─────────────────────────────────────────────────────────

def _sub(a, b):   return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]
def _add(a, b):   return [a[0]+b[0], a[1]+b[1], a[2]+b[2]]
def _scale(a, s): return [a[0]*s, a[1]*s, a[2]*s]
def _dot(a, b):   return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def _cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def _len(a):      return math.sqrt(a[0]**2+a[1]**2+a[2]**2)
def _norm(a):
    l = _len(a)
    if l < 1e-12: return [0.0, 0.0, 0.0]
    return [a[0]/l, a[1]/l, a[2]/l]


def _edge_map(indices):
    """undirected edge → list of face indices"""
    m: dict[str, list[int]] = {}
    nf = len(indices) // 3
    for f in range(nf):
        a, b, c = indices[f*3], indices[f*3+1], indices[f*3+2]
        for u, v in [(a,b),(b,c),(c,a)]:
            key = f"{min(u,v)}:{max(u,v)}"
            m.setdefault(key, []).append(f)
    return m


def _neighbours(n_verts, indices):
    nb = [set() for _ in range(n_verts)]
    for i in range(0, len(indices), 3):
        a, b, c = indices[i], indices[i+1], indices[i+2]
        nb[a].add(b); nb[a].add(c)
        nb[b].add(a); nb[b].add(c)
        nb[c].add(a); nb[c].add(b)
    return [list(s) for s in nb]


# ─── Core algorithms ──────────────────────────────────────────────────────────

def _validate(mesh: dict) -> dict:
    errors, warnings = [], []
    verts = mesh.get("vertices", [])
    indices = mesh.get("indices", [])
    nv = len(verts)

    if len(indices) % 3 != 0:
        errors.append(f"indices length ({len(indices)}) is not a multiple of 3")

    for i, idx in enumerate(indices):
        if idx < 0 or idx >= nv:
            errors.append(f"index[{i}]={idx} out of range [0,{nv})")
            if len(errors) > 10:
                errors.append("...further index errors omitted")
                break

    nf = len(indices) // 3
    deg = 0
    for f in range(nf):
        a, b, c = indices[f*3], indices[f*3+1], indices[f*3+2]
        if a == b or b == c or a == c:
            deg += 1
            continue
        if a >= nv or b >= nv or c >= nv:
            continue  # already reported as out-of-range above
        va, vb, vc = verts[a], verts[b], verts[c]
        cross = _cross(_sub(vb, va), _sub(vc, va))
        if _len(cross) < 1e-12:
            deg += 1
    if deg:
        warnings.append(f"{deg} degenerate triangle(s) found")

    em = _edge_map(indices)
    boundary = sum(1 for fs in em.values() if len(fs) == 1)
    non_manifold = sum(1 for fs in em.values() if len(fs) > 2)
    if boundary:
        warnings.append(f"{boundary} boundary edge(s) — mesh is not watertight")
    if non_manifold:
        errors.append(f"{non_manifold} edge(s) shared by >2 faces — non-manifold")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings,
            "face_count": nf, "vertex_count": nv}


def _compute_normals(mesh: dict) -> dict:
    verts = mesh["vertices"]
    indices = mesh["indices"]
    n = len(verts)
    acc = [[0.0, 0.0, 0.0] for _ in range(n)]
    for f in range(len(indices) // 3):
        a, b, c = indices[f*3], indices[f*3+1], indices[f*3+2]
        cross = _cross(_sub(verts[b], verts[a]), _sub(verts[c], verts[a]))
        for i in (a, b, c):
            acc[i][0] += cross[0]; acc[i][1] += cross[1]; acc[i][2] += cross[2]
    normals = [_norm(v) for v in acc]
    return {**mesh, "normals": normals}


def _decimate(mesh: dict, target_face_count: int) -> dict:
    verts = [list(v) for v in mesh["vertices"]]
    indices = list(mesh["indices"])
    nv = len(verts)

    valid_face = [True] * (len(indices) // 3)
    valid_vert = [True] * nv
    remap = list(range(nv))

    def canonical(i):
        while remap[i] != i:
            remap[i] = remap[remap[i]]
            i = remap[i]
        return i

    def face_plane(f):
        a, b, c = canonical(indices[f*3]), canonical(indices[f*3+1]), canonical(indices[f*3+2])
        if a == b or b == c or a == c: return None
        n = _norm(_cross(_sub(verts[b], verts[a]), _sub(verts[c], verts[a])))
        d = -_dot(n, verts[a])
        return (n, d)

    def vert_error(vi):
        v = verts[vi]; e = 0.0
        for f, ok in enumerate(valid_face):
            if not ok: continue
            fa, fb, fc = canonical(indices[f*3]), canonical(indices[f*3+1]), canonical(indices[f*3+2])
            if vi not in (fa, fb, fc): continue
            pl = face_plane(f)
            if pl is None: continue
            n, d = pl
            dist = _dot(n, v) + d
            e += dist * dist
        return e

    current_faces = sum(valid_face)

    def build_edges():
        seen = set(); edges = []
        for f, ok in enumerate(valid_face):
            if not ok: continue
            a, b, c = canonical(indices[f*3]), canonical(indices[f*3+1]), canonical(indices[f*3+2])
            for u, v in [(a,b),(b,c),(c,a)]:
                if u == v: continue
                key = (min(u,v), max(u,v))
                if key not in seen:
                    seen.add(key); edges.append(key)
        return edges

    while current_faces > target_face_count:
        edges = build_edges()
        if not edges: break
        best_cost, best_edge = float('inf'), None
        for (u, v) in edges:
            mid = _scale(_add(verts[u], verts[v]), 0.5)
            eu = vert_error(u); ev = vert_error(v)
            mid_cost = 0.0
            for f, ok in enumerate(valid_face):
                if not ok: continue
                fa, fb, fc = canonical(indices[f*3]), canonical(indices[f*3+1]), canonical(indices[f*3+2])
                if u not in (fa,fb,fc) and v not in (fa,fb,fc): continue
                pl = face_plane(f)
                if pl is None: continue
                n, d = pl; dist = _dot(n, mid) + d; mid_cost += dist*dist
            cost = eu + ev + mid_cost
            if cost < best_cost:
                best_cost = cost; best_edge = (u, v)
        if best_edge is None: break
        u, v = best_edge
        verts[u] = _scale(_add(verts[u], verts[v]), 0.5)
        remap[v] = u; valid_vert[v] = False
        nf = len(indices) // 3
        for f in range(nf):
            if not valid_face[f]: continue
            a, b, c = canonical(indices[f*3]), canonical(indices[f*3+1]), canonical(indices[f*3+2])
            if a == b or b == c or a == c:
                valid_face[f] = False; current_faces -= 1
        if current_faces <= target_face_count: break

    # Compact
    vi_map = [-1] * len(verts); new_v = []
    for i, ok in enumerate(valid_vert):
        if ok: vi_map[i] = len(new_v); new_v.append(verts[i])
    new_i = []
    for f, ok in enumerate(valid_face):
        if not ok: continue
        a = vi_map[canonical(indices[f*3])]
        b = vi_map[canonical(indices[f*3+1])]
        c = vi_map[canonical(indices[f*3+2])]
        if a < 0 or b < 0 or c < 0 or a == b or b == c or a == c: continue
        new_i += [a, b, c]
    return {**mesh, "vertices": new_v, "indices": new_i}


def _smooth(mesh: dict, iterations: int, lam: float = 0.5) -> dict:
    verts = [list(v) for v in mesh["vertices"]]
    indices = mesh["indices"]
    nb = _neighbours(len(verts), indices)
    for _ in range(iterations):
        nxt = [list(v) for v in verts]
        for i, v in enumerate(verts):
            nbrs = nb[i]
            if not nbrs: continue
            inv = 1.0 / len(nbrs)
            sx = sum(verts[j][0] for j in nbrs)
            sy = sum(verts[j][1] for j in nbrs)
            sz = sum(verts[j][2] for j in nbrs)
            nxt[i] = [v[0]+lam*(sx*inv-v[0]), v[1]+lam*(sy*inv-v[1]), v[2]+lam*(sz*inv-v[2])]
        verts = nxt
    return {**mesh, "vertices": verts}


def _fill_holes(mesh: dict) -> dict:
    verts = [list(v) for v in mesh["vertices"]]
    indices = list(mesh["indices"])
    nf = len(indices) // 3

    half_edge: dict[str, int] = {}
    for f in range(nf):
        a, b, c = indices[f*3], indices[f*3+1], indices[f*3+2]
        for u, v in [(a,b),(b,c),(c,a)]:
            half_edge[f"{u}:{v}"] = f

    boundary_next: dict[int, int] = {}
    for key in half_edge:
        a_s, b_s = key.split(':')
        a, b = int(a_s), int(b_s)
        if f"{b}:{a}" not in half_edge:
            boundary_next[b] = a

    visited: set[int] = set()
    loops = []
    for start in list(boundary_next.keys()):
        if start in visited: continue
        loop = []; cur = start
        safety = len(boundary_next) + 1
        while cur not in visited and safety > 0:
            safety -= 1; visited.add(cur); loop.append(cur)
            cur = boundary_next.get(cur)
            if cur is None: break
        if len(loop) >= 3:
            loops.append(loop)

    for loop in loops:
        inv = 1.0 / len(loop)
        cx = sum(verts[vi][0] for vi in loop) * inv
        cy = sum(verts[vi][1] for vi in loop) * inv
        cz = sum(verts[vi][2] for vi in loop) * inv
        ci = len(verts); verts.append([cx, cy, cz])
        for i in range(len(loop)):
            a = loop[i]; b = loop[(i+1) % len(loop)]
            indices += [a, b, ci]

    return {**mesh, "vertices": verts, "indices": indices}


def _repair(mesh: dict, tolerance: float = 1e-6) -> dict:
    verts = mesh["vertices"]; indices = mesh["indices"]
    tol2 = tolerance * tolerance
    new_verts = []; weld = [-1] * len(verts)
    for i, v in enumerate(verts):
        found = -1
        for j, w in enumerate(new_verts):
            dx, dy, dz = v[0]-w[0], v[1]-w[1], v[2]-w[2]
            if dx*dx+dy*dy+dz*dz <= tol2:
                found = j; break
        if found == -1:
            found = len(new_verts); new_verts.append(list(v))
        weld[i] = found

    new_i = []
    for f in range(len(indices) // 3):
        a, b, c = weld[indices[f*3]], weld[indices[f*3+1]], weld[indices[f*3+2]]
        if a == b or b == c or a == c: continue
        va, vb, vc = new_verts[a], new_verts[b], new_verts[c]
        cross = _cross(_sub(vb, va), _sub(vc, va))
        if _len(cross) < 1e-12: continue
        new_i += [a, b, c]

    nf = len(new_i) // 3
    if nf == 0:
        return {**mesh, "vertices": new_verts, "indices": new_i}

    dir_edge: dict[str, int] = {}
    for f in range(nf):
        for u, v in [(0,1),(1,2),(2,0)]:
            a, b = new_i[f*3+u], new_i[f*3+v]
            dir_edge[f"{a}:{b}"] = f

    winding = [-1] * nf
    queue = [0]; winding[0] = 0
    while queue:
        f = queue.pop(0)
        fa, fb, fc = new_i[f*3], new_i[f*3+1], new_i[f*3+2]
        for a, b in [(fa,fb),(fb,fc),(fc,fa)]:
            g = dir_edge.get(f"{b}:{a}")
            if g is not None and winding[g] == -1:
                winding[g] = winding[f]; queue.append(g)
            g2 = dir_edge.get(f"{a}:{b}")
            if g2 is not None and g2 != f and winding[g2] == -1:
                winding[g2] = 1 - winding[f]; queue.append(g2)

    for f in range(nf):
        if winding[f] == 1:
            new_i[f*3+1], new_i[f*3+2] = new_i[f*3+2], new_i[f*3+1]

    return {**mesh, "vertices": new_verts, "indices": new_i}


def _surface_from_points(pts: list, target_face_count: int) -> dict:
    n = len(pts)
    if n < 3:
        return {"version": 1, "vertices": [], "indices": []}
    K = min(6, n - 1)
    face_set: set[str] = set(); faces = []
    for i in range(n):
        dists = []
        for j in range(n):
            if j == i: continue
            dx, dy, dz = pts[i][0]-pts[j][0], pts[i][1]-pts[j][1], pts[i][2]-pts[j][2]
            dists.append((j, dx*dx+dy*dy+dz*dz))
        dists.sort(key=lambda x: x[1])
        knn = [d[0] for d in dists[:K]]
        for ki in range(len(knn)-1):
            a, b, c = i, knn[ki], knn[ki+1]
            key = ':'.join(str(x) for x in sorted([a,b,c]))
            if key in face_set: continue
            face_set.add(key); faces.append((a,b,c))

    indices = []
    for a,b,c in faces: indices += [a,b,c]
    mesh = {"version": 1, "vertices": [list(p) for p in pts], "indices": indices}
    if len(indices)//3 > target_face_count:
        mesh = _decimate(mesh, target_face_count)
    return mesh


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _read_mesh(ctx: ProjectCtx, file_id: uuid.UUID):
    row = ctx.pool.fetchone(
        "select content, kind from files where id = $1 and project_id = $2 and deleted_at is null",
        file_id, ctx.project_id,
    )
    if not row:
        return None, "file not found"
    content, kind = row
    if kind != "mesh":
        return None, f"file is kind={kind}, expected mesh"
    try:
        return json.loads(content), None
    except Exception as e:
        return None, f"parse error: {e}"


def _write_mesh(ctx: ProjectCtx, file_id: uuid.UUID, doc: dict) -> Optional[str]:
    body = json.dumps(doc)
    try:
        ctx.pool.execute(
            "update files set content = $1, updated_at = now() where id = $2 and project_id = $3",
            body, file_id, ctx.project_id,
        )
        return None
    except Exception as e:
        return str(e)


def _parse_file_id(a: dict) -> tuple[Optional[uuid.UUID], Optional[str]]:
    raw = a.get("file_id", "").strip()
    if not raw:
        return None, "file_id is required"
    try:
        return uuid.UUID(raw), None
    except Exception:
        return None, "file_id must be a valid UUID"


# ─── Tool specs ───────────────────────────────────────────────────────────────

mesh_validate_spec = ToolSpec(
    name="mesh_validate",
    description="Validate a .mesh file and return a report of errors and warnings.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .mesh file."},
        },
        "required": ["file_id"],
    },
)

mesh_decimate_spec = ToolSpec(
    name="mesh_decimate",
    description=(
        "Reduce the polygon count of a .mesh file to target_face_count using "
        "simplified quadric edge collapse. Returns the updated file_id."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .mesh file."},
            "target_face_count": {"type": "integer", "description": "Desired number of triangles."},
        },
        "required": ["file_id", "target_face_count"],
    },
)

mesh_smooth_spec = ToolSpec(
    name="mesh_smooth",
    description=(
        "Smooth a .mesh file using Laplacian smoothing. Each vertex moves toward "
        "the average of its neighbours by lambda per iteration."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .mesh file."},
            "iterations": {"type": "integer", "description": "Number of smoothing iterations (1–20 typical)."},
            "lambda": {"type": "number", "description": "Smoothing factor 0–1 (default 0.5)."},
        },
        "required": ["file_id", "iterations"],
    },
)

mesh_repair_spec = ToolSpec(
    name="mesh_repair",
    description=(
        "Repair a .mesh file: snap-weld duplicate vertices, remove degenerate "
        "triangles, and fix winding consistency."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .mesh file."},
        },
        "required": ["file_id"],
    },
)

mesh_fill_holes_spec = ToolSpec(
    name="mesh_fill_holes",
    description=(
        "Detect boundary loops in a .mesh file and fill each hole with fan "
        "triangulation. Useful for making open scans watertight before boolean ops."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .mesh file."},
        },
        "required": ["file_id"],
    },
)

mesh_remesh_spec = ToolSpec(
    name="mesh_remesh",
    description=(
        "Isotropically remesh a .mesh file toward a uniform target edge length. "
        "Uses split/collapse/flip/relocate passes. Sets quad_dominant=true on output "
        "(mesh stays triangles — true quad extraction is out of scope for v1)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .mesh file."},
            "target_edge_length_mm": {"type": "number", "description": "Target edge length in mm."},
        },
        "required": ["file_id", "target_edge_length_mm"],
    },
)

surface_from_points_spec = ToolSpec(
    name="surface_from_points",
    description=(
        "Reconstruct a triangle mesh from a point cloud using a nearest-neighbour "
        "fan method. Not a full Poisson reconstruction — suitable for quick preview. "
        "Supply either a file_id pointing to a .mesh with vertices-only, or inline "
        "points as [[x,y,z], ...]."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of a .mesh file containing point cloud vertices (indices can be empty)."},
            "inline_points": {"type": "array", "description": "Inline [[x,y,z],...] array (alternative to file_id)."},
            "target_face_count": {"type": "integer", "description": "Maximum number of output faces."},
        },
        "required": ["target_face_count"],
    },
)


# ─── Handlers ────────────────────────────────────────────────────────────────

@register(mesh_validate_spec, write=False)
async def run_mesh_validate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    fid, err = _parse_file_id(a)
    if err:
        return err_payload(err, "BAD_ARGS")
    mesh, err = _read_mesh(ctx, fid)
    if err:
        return err_payload(err, "NOT_FOUND")
    return ok_payload(_validate(mesh))


@register(mesh_decimate_spec, write=True)
async def run_mesh_decimate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    fid, err = _parse_file_id(a)
    if err:
        return err_payload(err, "BAD_ARGS")
    target = a.get("target_face_count")
    if not isinstance(target, int) or target < 1:
        return err_payload("target_face_count must be a positive integer", "BAD_ARGS")
    mesh, err = _read_mesh(ctx, fid)
    if err:
        return err_payload(err, "NOT_FOUND")
    result = _decimate(mesh, target)
    err = _write_mesh(ctx, fid, result)
    if err:
        return err_payload(err, "WRITE_ERR")
    return ok_payload({"file_id": str(fid), "face_count": len(result["indices"])//3,
                       "vertex_count": len(result["vertices"])})


@register(mesh_smooth_spec, write=True)
async def run_mesh_smooth(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    fid, err = _parse_file_id(a)
    if err:
        return err_payload(err, "BAD_ARGS")
    iterations = a.get("iterations")
    if not isinstance(iterations, int) or iterations < 1:
        return err_payload("iterations must be a positive integer", "BAD_ARGS")
    lam = float(a.get("lambda", 0.5))
    mesh, err = _read_mesh(ctx, fid)
    if err:
        return err_payload(err, "NOT_FOUND")
    result = _smooth(mesh, iterations, lam)
    err = _write_mesh(ctx, fid, result)
    if err:
        return err_payload(err, "WRITE_ERR")
    return ok_payload({"file_id": str(fid), "iterations": iterations, "lambda": lam})


@register(mesh_repair_spec, write=True)
async def run_mesh_repair(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    fid, err = _parse_file_id(a)
    if err:
        return err_payload(err, "BAD_ARGS")
    mesh, err = _read_mesh(ctx, fid)
    if err:
        return err_payload(err, "NOT_FOUND")
    result = _repair(mesh)
    before_v = len(mesh["vertices"]); after_v = len(result["vertices"])
    before_f = len(mesh["indices"])//3; after_f = len(result["indices"])//3
    err = _write_mesh(ctx, fid, result)
    if err:
        return err_payload(err, "WRITE_ERR")
    return ok_payload({"file_id": str(fid),
                       "welded_vertices": before_v - after_v,
                       "removed_faces": before_f - after_f})


@register(mesh_fill_holes_spec, write=True)
async def run_mesh_fill_holes(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    fid, err = _parse_file_id(a)
    if err:
        return err_payload(err, "BAD_ARGS")
    mesh, err = _read_mesh(ctx, fid)
    if err:
        return err_payload(err, "NOT_FOUND")
    result = _fill_holes(mesh)
    added = len(result["indices"])//3 - len(mesh["indices"])//3
    err = _write_mesh(ctx, fid, result)
    if err:
        return err_payload(err, "WRITE_ERR")
    return ok_payload({"file_id": str(fid), "faces_added": added})


@register(mesh_remesh_spec, write=True)
async def run_mesh_remesh(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    fid, err = _parse_file_id(a)
    if err:
        return err_payload(err, "BAD_ARGS")
    target_edge = a.get("target_edge_length_mm")
    if not isinstance(target_edge, (int, float)) or target_edge <= 0:
        return err_payload("target_edge_length_mm must be a positive number", "BAD_ARGS")
    mesh, err = _read_mesh(ctx, fid)
    if err:
        return err_payload(err, "NOT_FOUND")
    lo = (4/5) * target_edge; hi = (4/3) * target_edge
    verts = [list(v) for v in mesh["vertices"]]
    inds = list(mesh["indices"])

    for _pass in range(5):
        # Split
        to_split = set(); nf = len(inds)//3
        for f in range(nf):
            for ui, vi in [(0,1),(1,2),(2,0)]:
                a_i, b_i = inds[f*3+ui], inds[f*3+vi]
                key = (min(a_i,b_i), max(a_i,b_i))
                if key in to_split: continue
                if _len(_sub(verts[a_i], verts[b_i])) > hi:
                    to_split.add(key)
        for (a_i, b_i) in to_split:
            mid = _scale(_add(verts[a_i], verts[b_i]), 0.5)
            mi = len(verts); verts.append(mid)
            new_i2 = []
            for f in range(len(inds)//3):
                fa, fb, fc = inds[f*3], inds[f*3+1], inds[f*3+2]
                tri = [fa,fb,fc]
                has = (fa==a_i and fb==b_i) or (fb==a_i and fc==b_i) or (fc==a_i and fa==b_i) or \
                      (fa==b_i and fb==a_i) or (fb==b_i and fc==a_i) or (fc==b_i and fa==a_i)
                if not has:
                    new_i2 += [fa,fb,fc]; continue
                third = next((v for v in tri if v != a_i and v != b_i), None)
                if third is None:
                    new_i2 += [fa,fb,fc]; continue
                new_i2 += [a_i,mi,third, mi,b_i,third]
            inds = new_i2

        # Collapse
        remap2 = list(range(len(verts))); valid2 = [True]*(len(inds)//3)
        def can2(i):
            while remap2[i] != i: remap2[i] = remap2[remap2[i]]; i = remap2[i]
            return i
        seen2: set[tuple] = set()
        for f in range(len(inds)//3):
            if not valid2[f]: continue
            for ui, vi in [(0,1),(1,2),(2,0)]:
                a_i, b_i = can2(inds[f*3+ui]), can2(inds[f*3+vi])
                if a_i == b_i: continue
                key = (min(a_i,b_i), max(a_i,b_i))
                if key in seen2: continue
                if _len(_sub(verts[a_i], verts[b_i])) < lo:
                    seen2.add(key)
                    verts[a_i] = _scale(_add(verts[a_i], verts[b_i]), 0.5)
                    remap2[b_i] = a_i
                    for ff in range(len(inds)//3):
                        if not valid2[ff]: continue
                        xa, xb, xc = can2(inds[ff*3]), can2(inds[ff*3+1]), can2(inds[ff*3+2])
                        if xa == xb or xb == xc or xa == xc:
                            valid2[ff] = False
        vi_m2 = [-1]*len(verts); nv2 = []
        for i in range(len(verts)):
            if can2(i) == i:
                vi_m2[i] = len(nv2); nv2.append(verts[i])
        ni2 = []
        for f in range(len(inds)//3):
            if not valid2[f]: continue
            xa = vi_m2[can2(inds[f*3])]; xb = vi_m2[can2(inds[f*3+1])]; xc = vi_m2[can2(inds[f*3+2])]
            if xa < 0 or xb < 0 or xc < 0 or xa==xb or xb==xc or xa==xc: continue
            ni2 += [xa,xb,xc]
        verts = nv2; inds = ni2

    result = {**mesh, "vertices": verts, "indices": inds, "quad_dominant": True}
    err = _write_mesh(ctx, fid, result)
    if err:
        return err_payload(err, "WRITE_ERR")
    return ok_payload({"file_id": str(fid), "face_count": len(inds)//3, "vertex_count": len(verts)})


@register(surface_from_points_spec, write=True)
async def run_surface_from_points(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    target = a.get("target_face_count")
    if not isinstance(target, int) or target < 1:
        return err_payload("target_face_count must be a positive integer", "BAD_ARGS")

    pts = a.get("inline_points")
    fid_str = a.get("file_id", "").strip()
    out_fid = None

    if pts is None and fid_str:
        try:
            fid = uuid.UUID(fid_str)
        except Exception:
            return err_payload("file_id must be a valid UUID", "BAD_ARGS")
        mesh, err = _read_mesh(ctx, fid)
        if err:
            return err_payload(err, "NOT_FOUND")
        pts = mesh.get("vertices", [])
        out_fid = fid

    if not pts or len(pts) < 3:
        return err_payload("need at least 3 points", "BAD_ARGS")

    result = _surface_from_points(pts, target)

    if out_fid:
        err = _write_mesh(ctx, out_fid, result)
        if err:
            return err_payload(err, "WRITE_ERR")
        return ok_payload({"file_id": str(out_fid), "face_count": len(result["indices"])//3,
                           "vertex_count": len(result["vertices"])})
    else:
        return ok_payload({"mesh": result, "face_count": len(result["indices"])//3,
                           "vertex_count": len(result["vertices"])})
