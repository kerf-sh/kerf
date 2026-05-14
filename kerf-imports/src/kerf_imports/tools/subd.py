"""
subd.py — LLM tools for SubD (subdivision surface) modelling.

Each tool reads/writes a .subd file whose content is JSON matching:
  { version: 1, control_mesh: { vertices, faces, edges },
    subdivision_level: int, display_mesh: null|{...} }
"""

import json
import math
import uuid
from typing import Optional
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx


# ── Primitive control meshes (pure Python, mirrors subd.js) ──────────────────

def _cube_mesh():
    vertices = [
        {"id": 0, "x": -1, "y": -1, "z": -1},
        {"id": 1, "x":  1, "y": -1, "z": -1},
        {"id": 2, "x":  1, "y":  1, "z": -1},
        {"id": 3, "x": -1, "y":  1, "z": -1},
        {"id": 4, "x": -1, "y": -1, "z":  1},
        {"id": 5, "x":  1, "y": -1, "z":  1},
        {"id": 6, "x":  1, "y":  1, "z":  1},
        {"id": 7, "x": -1, "y":  1, "z":  1},
    ]
    faces = [
        {"id": 0, "vertex_ids": [0, 1, 2, 3]},
        {"id": 1, "vertex_ids": [4, 5, 6, 7]},
        {"id": 2, "vertex_ids": [0, 1, 5, 4]},
        {"id": 3, "vertex_ids": [2, 3, 7, 6]},
        {"id": 4, "vertex_ids": [0, 3, 7, 4]},
        {"id": 5, "vertex_ids": [1, 2, 6, 5]},
    ]
    edges = [
        {"v1": 0, "v2": 1, "crease_value": 0}, {"v1": 1, "v2": 2, "crease_value": 0},
        {"v1": 2, "v2": 3, "crease_value": 0}, {"v1": 3, "v2": 0, "crease_value": 0},
        {"v1": 4, "v2": 5, "crease_value": 0}, {"v1": 5, "v2": 6, "crease_value": 0},
        {"v1": 6, "v2": 7, "crease_value": 0}, {"v1": 7, "v2": 4, "crease_value": 0},
        {"v1": 0, "v2": 4, "crease_value": 0}, {"v1": 1, "v2": 5, "crease_value": 0},
        {"v1": 2, "v2": 6, "crease_value": 0}, {"v1": 3, "v2": 7, "crease_value": 0},
    ]
    return {"vertices": vertices, "faces": faces, "edges": edges}


def _sphere_mesh(rings: int = 4, segments: int = 8):
    vertices = []
    faces = []
    edges = []
    vid = 0
    for r in range(rings + 1):
        phi = math.pi * r / rings
        for s in range(segments):
            theta = 2 * math.pi * s / segments
            vertices.append({
                "id": vid,
                "x": math.sin(phi) * math.cos(theta),
                "y": math.sin(phi) * math.sin(theta),
                "z": math.cos(phi),
            })
            vid += 1

    fid = 0
    edge_set = set()

    def add_edge(a, b):
        key = (min(a, b), max(a, b))
        if key not in edge_set:
            edge_set.add(key)
            edges.append({"v1": key[0], "v2": key[1], "crease_value": 0})

    for r in range(rings):
        for s in range(segments):
            a = r * segments + s
            b = r * segments + (s + 1) % segments
            c = (r + 1) * segments + (s + 1) % segments
            d = (r + 1) * segments + s
            faces.append({"id": fid, "vertex_ids": [a, b, c, d]})
            fid += 1
            add_edge(a, b); add_edge(b, c); add_edge(c, d); add_edge(d, a)

    return {"vertices": vertices, "faces": faces, "edges": edges}


def _cylinder_mesh(segments: int = 8):
    vertices = []
    faces = []
    edges = []
    vid = 0
    bottom_ids = []
    top_ids = []
    for s in range(segments):
        theta = 2 * math.pi * s / segments
        x, y = math.cos(theta), math.sin(theta)
        vertices.append({"id": vid, "x": x, "y": y, "z": -1}); bottom_ids.append(vid); vid += 1
        vertices.append({"id": vid, "x": x, "y": y, "z":  1}); top_ids.append(vid); vid += 1

    edge_set = set()

    def add_edge(a, b, c=0):
        key = (min(a, b), max(a, b))
        if key not in edge_set:
            edge_set.add(key)
            edges.append({"v1": key[0], "v2": key[1], "crease_value": c})

    fid = 0
    for s in range(segments):
        ns = (s + 1) % segments
        a, b, c, d = bottom_ids[s], bottom_ids[ns], top_ids[ns], top_ids[s]
        faces.append({"id": fid, "vertex_ids": [a, b, c, d]}); fid += 1
        add_edge(a, b); add_edge(b, c); add_edge(c, d); add_edge(d, a)

    faces.append({"id": fid, "vertex_ids": list(reversed(bottom_ids))}); fid += 1
    faces.append({"id": fid, "vertex_ids": list(top_ids)}); fid += 1
    for s in range(segments):
        add_edge(bottom_ids[s], bottom_ids[(s + 1) % segments])
        add_edge(top_ids[s], top_ids[(s + 1) % segments])

    return {"vertices": vertices, "faces": faces, "edges": edges}


PRIMITIVES = {
    "cube": _cube_mesh,
    "sphere": _sphere_mesh,
    "cylinder": _cylinder_mesh,
}


# ── Catmull-Clark (Python mirror for server-side display_mesh generation) ──────

def _edge_key(a: int, b: int) -> tuple:
    return (min(a, b), max(a, b))


def _avg_verts(verts: list) -> dict:
    n = len(verts)
    if n == 0:
        return {"x": 0.0, "y": 0.0, "z": 0.0}
    return {
        "x": sum(v["x"] for v in verts) / n,
        "y": sum(v["y"] for v in verts) / n,
        "z": sum(v["z"] for v in verts) / n,
    }


def _lerp3(a: dict, b: dict, t: float) -> dict:
    return {
        "x": a["x"] + (b["x"] - a["x"]) * t,
        "y": a["y"] + (b["y"] - a["y"]) * t,
        "z": a["z"] + (b["z"] - a["z"]) * t,
    }


def _cc_once(mesh: dict) -> dict:
    vertices = mesh["vertices"]
    faces = mesh["faces"]
    mesh_edges = mesh.get("edges", [])

    vert_map = {v["id"]: v for v in vertices}
    crease_map = {_edge_key(e["v1"], e["v2"]): e.get("crease_value", 0) for e in mesh_edges}

    def get_crease(a, b):
        return crease_map.get(_edge_key(a, b), 0)

    # 1. Face points
    face_points = {f["id"]: _avg_verts([vert_map[vid] for vid in f["vertex_ids"]]) for f in faces}

    # 2. Edge adjacency
    edge_faces: dict = {}
    all_edge_keys = set()
    for f in faces:
        ids = f["vertex_ids"]
        n = len(ids)
        for i in range(n):
            key = _edge_key(ids[i], ids[(i + 1) % n])
            all_edge_keys.add(key)
            edge_faces.setdefault(key, []).append(f["id"])

    # 3. Edge points
    edge_point_map = {}
    for key in all_edge_keys:
        a, b = key
        va, vb = vert_map[a], vert_map[b]
        adj = edge_faces.get(key, [])
        crease = get_crease(a, b)
        mid = {"x": (va["x"] + vb["x"]) / 2, "y": (va["y"] + vb["y"]) / 2, "z": (va["z"] + vb["z"]) / 2}
        if crease >= 1 or len(adj) != 2:
            edge_point_map[key] = mid
        else:
            fp1, fp2 = face_points[adj[0]], face_points[adj[1]]
            fa = _avg_verts([fp1, fp2])
            smooth = {
                "x": (va["x"] + vb["x"] + fa["x"] * 2) / 4,
                "y": (va["y"] + vb["y"] + fa["y"] * 2) / 4,
                "z": (va["z"] + vb["z"] + fa["z"] * 2) / 4,
            }
            edge_point_map[key] = _lerp3(smooth, mid, crease)

    # Vertex adjacency
    vert_faces: dict = {}
    vert_edges: dict = {}
    for f in faces:
        for vid in f["vertex_ids"]:
            vert_faces.setdefault(vid, []).append(f)
    for key in all_edge_keys:
        a, b = key
        vert_edges.setdefault(a, []).append(b)
        vert_edges.setdefault(b, []).append(a)

    # 4. Updated vertex positions
    new_vert_pos = {}
    for v in vertices:
        adj_faces = vert_faces.get(v["id"], [])
        adj_neighbors = vert_edges.get(v["id"], [])
        n = len(adj_faces)
        creased = [nb for nb in adj_neighbors if get_crease(v["id"], nb) >= 1]
        if len(creased) >= 2:
            new_vert_pos[v["id"]] = {"x": v["x"], "y": v["y"], "z": v["z"]}
        elif len(creased) == 1 or len(adj_faces) < len(adj_neighbors):
            mids = [{"x": (v["x"] + vert_map[nb]["x"]) / 2,
                     "y": (v["y"] + vert_map[nb]["y"]) / 2,
                     "z": (v["z"] + vert_map[nb]["z"]) / 2} for nb in adj_neighbors]
            avg_mid = _avg_verts(mids)
            new_vert_pos[v["id"]] = {
                "x": (v["x"] * 6 + avg_mid["x"] * 2) / 8,
                "y": (v["y"] * 6 + avg_mid["y"] * 2) / 8,
                "z": (v["z"] * 6 + avg_mid["z"] * 2) / 8,
            }
        else:
            F = _avg_verts([face_points[f["id"]] for f in adj_faces])
            mids = [{"x": (v["x"] + vert_map[nb]["x"]) / 2,
                     "y": (v["y"] + vert_map[nb]["y"]) / 2,
                     "z": (v["z"] + vert_map[nb]["z"]) / 2} for nb in adj_neighbors]
            R = _avg_verts(mids)
            new_vert_pos[v["id"]] = {
                "x": (F["x"] + 2 * R["x"] + (n - 3) * v["x"]) / n,
                "y": (F["y"] + 2 * R["y"] + (n - 3) * v["y"]) / n,
                "z": (F["z"] + 2 * R["z"] + (n - 3) * v["z"]) / n,
            }

    # 5. Build new mesh
    next_id = [0]

    def nid():
        i = next_id[0]; next_id[0] += 1; return i

    new_vertices = []
    orig_new_id = {}
    for v in vertices:
        new_i = nid()
        pos = new_vert_pos.get(v["id"], v)
        new_vertices.append({"id": new_i, "x": pos["x"], "y": pos["y"], "z": pos["z"]})
        orig_new_id[v["id"]] = new_i

    face_point_new_id = {}
    for f in faces:
        new_i = nid()
        fp = face_points[f["id"]]
        new_vertices.append({"id": new_i, "x": fp["x"], "y": fp["y"], "z": fp["z"]})
        face_point_new_id[f["id"]] = new_i

    edge_point_new_id = {}
    for key, ep in edge_point_map.items():
        new_i = nid()
        new_vertices.append({"id": new_i, "x": ep["x"], "y": ep["y"], "z": ep["z"]})
        edge_point_new_id[key] = new_i

    new_faces = []
    new_edge_set: dict = {}
    face_next_id = [0]

    def add_edge_new(a, b, crease=0):
        key = _edge_key(a, b)
        if key not in new_edge_set:
            new_edge_set[key] = crease

    for f in faces:
        ids = f["vertex_ids"]
        n = len(ids)
        fp_id = face_point_new_id[f["id"]]
        for i in range(n):
            va = ids[i]
            vb = ids[(i + 1) % n]
            vc = ids[(i - 1) % n]
            ep_ab = edge_point_new_id[_edge_key(va, vb)]
            ep_ca = edge_point_new_id[_edge_key(vc, va)]
            quad = [orig_new_id[va], ep_ab, fp_id, ep_ca]
            new_faces.append({"id": face_next_id[0], "vertex_ids": quad})
            face_next_id[0] += 1
            c_ab = get_crease(va, vb)
            c_ca = get_crease(vc, va)
            add_edge_new(orig_new_id[va], ep_ab, c_ab)
            add_edge_new(ep_ab, fp_id, 0)
            add_edge_new(fp_id, ep_ca, 0)
            add_edge_new(ep_ca, orig_new_id[va], c_ca)

    new_edges = [{"v1": k[0], "v2": k[1], "crease_value": c} for k, c in new_edge_set.items()]
    return {"vertices": new_vertices, "faces": new_faces, "edges": new_edges}


def _subdivide_mesh(mesh: dict, levels: int) -> dict:
    for _ in range(max(0, levels)):
        mesh = _cc_once(mesh)
    return mesh


def _triangulate_display_mesh(mesh: dict) -> dict:
    """Build display_mesh: vertices as [[x,y,z]], indices as flat triangle list."""
    positions = [[v["x"], v["y"], v["z"]] for v in mesh["vertices"]]
    indices = []
    for f in mesh["faces"]:
        vids = f["vertex_ids"]
        for i in range(1, len(vids) - 1):
            indices.extend([vids[0], vids[i], vids[i + 1]])
    return {"vertices": positions, "faces": mesh["faces"], "indices": indices}


# ── File helpers ───────────────────────────────────────────────────────────────

def _read_subd(ctx: ProjectCtx, file_id: uuid.UUID) -> tuple[Optional[dict], Optional[str]]:
    try:
        row = ctx.pool.fetchone(
            "select content, kind from files where id = $1 and project_id = $2 and deleted_at is null",
            file_id, ctx.project_id,
        )
    except Exception as e:
        return None, str(e)
    if not row:
        return None, "NOT_FOUND"
    content, kind = row
    if kind != "subd":
        return None, f"expected kind=subd, got {kind!r}"
    try:
        return json.loads(content), None
    except Exception as e:
        return None, f"parse error: {e}"


def _write_subd(ctx: ProjectCtx, file_id: uuid.UUID, doc: dict) -> Optional[str]:
    try:
        body = json.dumps(doc, indent=2)
        ctx.pool.execute(
            "update files set content = $1, updated_at = now() where id = $2 and project_id = $3",
            body, file_id, ctx.project_id,
        )
        return None
    except Exception as e:
        return str(e)


def _new_subd_file(ctx: ProjectCtx, doc: dict, name: str) -> tuple[Optional[uuid.UUID], Optional[str]]:
    fid = uuid.uuid4()
    body = json.dumps(doc, indent=2)
    try:
        ctx.pool.execute(
            "insert into files (id, project_id, name, kind, content, created_at, updated_at) "
            "values ($1, $2, $3, 'subd', $4, now(), now())",
            fid, ctx.project_id, name, body,
        )
        return fid, None
    except Exception as e:
        return None, str(e)


# ── Tool specs ─────────────────────────────────────────────────────────────────

create_subd_spec = ToolSpec(
    name="create_subd",
    description=(
        "Create a new .subd file with a primitive control mesh. "
        "Returns the new file_id. Use file_id in subsequent subd tools."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Optional explicit UUID for the new file. Auto-generated if omitted.",
            },
            "primitive": {
                "type": "string",
                "enum": ["cube", "sphere", "cylinder"],
                "description": "Which primitive control mesh to start with. Default: 'cube'.",
            },
            "subdivision_level": {
                "type": "integer",
                "description": "Number of Catmull-Clark subdivision levels to apply. Default: 2.",
            },
            "name": {
                "type": "string",
                "description": "File name. Default: 'Untitled SubD'.",
            },
        },
        "required": [],
    },
)

subdivide_subd_spec = ToolSpec(
    name="subdivide_subd",
    description="Apply Catmull-Clark subdivision to an existing .subd file and update its display_mesh.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the target .subd file."},
        },
        "required": ["file_id"],
    },
)

extrude_face_subd_spec = ToolSpec(
    name="extrude_face_subd",
    description=(
        "Extrude a face of the SubD control mesh outward by `distance`. "
        "Adds new top-face vertices and N side quads."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .subd file."},
            "face_id": {"type": "integer", "description": "Integer id of the face to extrude."},
            "distance": {"type": "number", "description": "Extrusion distance along face normal."},
        },
        "required": ["file_id", "face_id", "distance"],
    },
)

bevel_edge_subd_spec = ToolSpec(
    name="bevel_edge_subd",
    description="Bevel (split) an edge of the SubD control mesh by inserting two new vertices.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .subd file."},
            "v1_id": {"type": "integer", "description": "First vertex id of the edge."},
            "v2_id": {"type": "integer", "description": "Second vertex id of the edge."},
            "width": {"type": "number", "description": "Bevel width (distance along edge from each end)."},
        },
        "required": ["file_id", "v1_id", "v2_id", "width"],
    },
)

set_edge_crease_spec = ToolSpec(
    name="set_edge_crease",
    description=(
        "Set the crease value on an edge of the SubD control mesh. "
        "0 = fully smooth, 1 = fully creased (sharp). Values in between blend."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "UUID of the .subd file."},
            "v1_id": {"type": "integer", "description": "First vertex id of the edge."},
            "v2_id": {"type": "integer", "description": "Second vertex id of the edge."},
            "crease": {"type": "number", "description": "Crease value 0..1."},
        },
        "required": ["file_id", "v1_id", "v2_id", "crease"],
    },
)


# ── Tool implementations ───────────────────────────────────────────────────────

@register(create_subd_spec, write=True)
async def run_create_subd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    primitive = a.get("primitive", "cube")
    if primitive not in PRIMITIVES:
        return err_payload(f"primitive must be one of {list(PRIMITIVES)}", "BAD_ARGS")

    level = a.get("subdivision_level", 2)
    if not isinstance(level, int) or level < 0:
        return err_payload("subdivision_level must be a non-negative integer", "BAD_ARGS")

    name = a.get("name", "Untitled SubD").strip() or "Untitled SubD"

    control_mesh = PRIMITIVES[primitive]()
    doc = {
        "version": 1,
        "control_mesh": control_mesh,
        "subdivision_level": level,
        "display_mesh": None,
    }

    # Apply subdivision to populate display_mesh immediately
    subdivided = _subdivide_mesh(dict(control_mesh), level)
    doc["display_mesh"] = _triangulate_display_mesh(subdivided)

    fid, err = _new_subd_file(ctx, doc, name)
    if err:
        return err_payload(f"could not create file: {err}", "ERROR")

    return ok_payload({
        "file_id": str(fid),
        "primitive": primitive,
        "subdivision_level": level,
        "face_count": len(doc["display_mesh"]["faces"]),
    })


@register(subdivide_subd_spec, write=True)
async def run_subdivide_subd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    doc, err = _read_subd(ctx, fid)
    if err:
        return err_payload(f"file error: {err}", "NOT_FOUND")

    level = doc.get("subdivision_level", 1)
    mesh = _subdivide_mesh(dict(doc["control_mesh"]), level)
    doc["display_mesh"] = _triangulate_display_mesh(mesh)

    err = _write_subd(ctx, fid, doc)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "subdivision_level": level,
        "face_count": len(doc["display_mesh"]["faces"]),
        "vertex_count": len(doc["display_mesh"]["vertices"]),
    })


@register(extrude_face_subd_spec, write=True)
async def run_extrude_face_subd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    face_id = a.get("face_id")
    distance = a.get("distance")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if face_id is None:
        return err_payload("face_id is required", "BAD_ARGS")
    if distance is None:
        return err_payload("distance is required", "BAD_ARGS")
    if not isinstance(distance, (int, float)):
        return err_payload("distance must be a number", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    doc, err = _read_subd(ctx, fid)
    if err:
        return err_payload(f"file error: {err}", "NOT_FOUND")

    mesh = doc["control_mesh"]
    face = next((f for f in mesh["faces"] if f["id"] == face_id), None)
    if face is None:
        return err_payload(f"face_id {face_id} not found", "NOT_FOUND")

    vert_map = {v["id"]: v for v in mesh["vertices"]}

    # Newell normal
    ids = face["vertex_ids"]
    nx = ny = nz = 0.0
    for i in range(len(ids)):
        curr = vert_map[ids[i]]
        nxt = vert_map[ids[(i + 1) % len(ids)]]
        nx += (curr["y"] - nxt["y"]) * (curr["z"] + nxt["z"])
        ny += (curr["z"] - nxt["z"]) * (curr["x"] + nxt["x"])
        nz += (curr["x"] - nxt["x"]) * (curr["y"] + nxt["y"])
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1
    nx /= length; ny /= length; nz /= length

    max_vid = max(v["id"] for v in mesh["vertices"])
    max_fid = max(f["id"] for f in mesh["faces"])

    new_top_ids = []
    for vid in ids:
        v = vert_map[vid]
        max_vid += 1
        mesh["vertices"].append({
            "id": max_vid,
            "x": v["x"] + nx * distance,
            "y": v["y"] + ny * distance,
            "z": v["z"] + nz * distance,
        })
        new_top_ids.append(max_vid)

    # Replace original face with top
    for f in mesh["faces"]:
        if f["id"] == face_id:
            f["vertex_ids"] = new_top_ids
            break

    # Side faces
    for i in range(len(ids)):
        a_bot, b_bot = ids[i], ids[(i + 1) % len(ids)]
        a_top, b_top = new_top_ids[i], new_top_ids[(i + 1) % len(ids)]
        max_fid += 1
        mesh["faces"].append({"id": max_fid, "vertex_ids": [a_bot, b_bot, b_top, a_top]})
        mesh["edges"].append({"v1": a_top, "v2": b_top, "crease_value": 0})
        mesh["edges"].append({"v1": a_bot, "v2": a_top, "crease_value": 0})

    err = _write_subd(ctx, fid, doc)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "face_id": face_id,
        "new_faces": len(ids),
        "new_vertices": len(ids),
    })


@register(bevel_edge_subd_spec, write=True)
async def run_bevel_edge_subd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    v1_id = a.get("v1_id")
    v2_id = a.get("v2_id")
    width = a.get("width")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if v1_id is None or v2_id is None:
        return err_payload("v1_id and v2_id are required", "BAD_ARGS")
    if width is None:
        return err_payload("width is required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    doc, err = _read_subd(ctx, fid)
    if err:
        return err_payload(f"file error: {err}", "NOT_FOUND")

    mesh = doc["control_mesh"]
    vert_map = {v["id"]: v for v in mesh["vertices"]}

    va, vb = vert_map.get(v1_id), vert_map.get(v2_id)
    if va is None or vb is None:
        return err_payload("vertex ids not found", "NOT_FOUND")

    edge_len = math.sqrt((vb["x"] - va["x"])**2 + (vb["y"] - va["y"])**2 + (vb["z"] - va["z"])**2)
    if edge_len < 1e-9:
        return err_payload("edge has zero length", "BAD_ARGS")

    t = min(0.5, abs(width) / (2 * edge_len))

    def lerp(a, b, t_):
        return {"x": a["x"] + (b["x"] - a["x"]) * t_,
                "y": a["y"] + (b["y"] - a["y"]) * t_,
                "z": a["z"] + (b["z"] - a["z"]) * t_}

    p1 = lerp(va, vb, t)
    p2 = lerp(va, vb, 1 - t)

    max_vid = max(v["id"] for v in mesh["vertices"])
    id1 = max_vid + 1
    id2 = max_vid + 2
    mesh["vertices"].append({"id": id1, "x": p1["x"], "y": p1["y"], "z": p1["z"]})
    mesh["vertices"].append({"id": id2, "x": p2["x"], "y": p2["y"], "z": p2["z"]})

    mesh["edges"].append({"v1": id1, "v2": id2, "crease_value": 0})
    old_key = _edge_key(v1_id, v2_id)
    mesh["edges"] = [e for e in mesh["edges"] if _edge_key(e["v1"], e["v2"]) != old_key]

    # Update faces
    for f in mesh["faces"]:
        ids = f["vertex_ids"]
        n = len(ids)
        for i in range(n):
            a, b = ids[i], ids[(i + 1) % n]
            if _edge_key(a, b) == old_key:
                if a == v1_id:
                    ids[i + 1:i + 1] = [id1, id2]
                else:
                    ids[i + 1:i + 1] = [id2, id1]
                break

    err = _write_subd(ctx, fid, doc)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({"file_id": file_id, "new_vertex_ids": [id1, id2]})


@register(set_edge_crease_spec, write=True)
async def run_set_edge_crease(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    v1_id = a.get("v1_id")
    v2_id = a.get("v2_id")
    crease = a.get("crease")

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if v1_id is None or v2_id is None:
        return err_payload("v1_id and v2_id are required", "BAD_ARGS")
    if crease is None:
        return err_payload("crease is required", "BAD_ARGS")
    if not isinstance(crease, (int, float)) or crease < 0 or crease > 1:
        return err_payload("crease must be a number 0..1", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    doc, err = _read_subd(ctx, fid)
    if err:
        return err_payload(f"file error: {err}", "NOT_FOUND")

    mesh = doc["control_mesh"]
    key = _edge_key(v1_id, v2_id)
    found = False
    for e in mesh["edges"]:
        if _edge_key(e["v1"], e["v2"]) == key:
            e["crease_value"] = crease
            found = True
            break
    if not found:
        mesh["edges"].append({"v1": v1_id, "v2": v2_id, "crease_value": crease})

    err = _write_subd(ctx, fid, doc)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({"file_id": file_id, "v1_id": v1_id, "v2_id": v2_id, "crease": crease})
