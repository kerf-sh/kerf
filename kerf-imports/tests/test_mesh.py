"""
test_mesh.py — pytest suite for mesh.py LLM tools.

Uses importlib.util.spec_from_file_location to avoid tools/__init__.py
db-import chain (same pattern as test_subd.py, test_erc.py).
"""

import asyncio
import importlib.util
import json
import math
import os
import sys
import types
import uuid

_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend")
_PLUGIN_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "kerf_imports", "tools")


def _load(rel):
    path = os.path.join(_BACKEND, rel)
    spec = importlib.util.spec_from_file_location(
        rel.replace("/", ".").replace(".py", ""), path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_plugin(filename):
    path = os.path.join(_PLUGIN_TOOLS, filename)
    name = "tools." + filename.replace(".py", "")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_registry_mod = sys.modules.get("tools.registry") or _load("tools/registry.py")
_context_mod  = sys.modules.get("tools.context")  or _load("tools/context.py")
sys.modules.setdefault("tools.registry", _registry_mod)
sys.modules.setdefault("tools.context",  _context_mod)

_mesh_mod = _load_plugin("mesh.py")

# Expose private helpers
_validate           = _mesh_mod._validate
_compute_normals    = _mesh_mod._compute_normals
_decimate           = _mesh_mod._decimate
_smooth             = _mesh_mod._smooth
_fill_holes         = _mesh_mod._fill_holes
_repair             = _mesh_mod._repair
_surface_from_points = _mesh_mod._surface_from_points

run_mesh_validate       = _mesh_mod.run_mesh_validate
run_mesh_decimate       = _mesh_mod.run_mesh_decimate
run_mesh_smooth         = _mesh_mod.run_mesh_smooth
run_mesh_repair         = _mesh_mod.run_mesh_repair
run_mesh_fill_holes     = _mesh_mod.run_mesh_fill_holes
run_mesh_remesh         = _mesh_mod.run_mesh_remesh
run_surface_from_points = _mesh_mod.run_surface_from_points

ProjectCtx = _context_mod.ProjectCtx


# ─── Mesh builders ────────────────────────────────────────────────────────────

def make_cube():
    v = [
        [0,0,0],[1,0,0],[1,1,0],[0,1,0],
        [0,0,1],[1,0,1],[1,1,1],[0,1,1],
    ]
    i = [
        0,1,2, 0,2,3,
        4,6,5, 4,7,6,
        0,5,1, 0,4,5,
        2,6,7, 2,7,3,
        0,3,7, 0,7,4,
        1,5,6, 1,6,2,
    ]
    return {"version":1,"vertices":v,"indices":i}


def make_cube_with_hole():
    c = make_cube()
    return {"version":1,"vertices":c["vertices"],"indices":c["indices"][6:]}


def make_tet():
    v = [[0,0,0],[1,0,0],[0.5,1,0],[0.5,0.5,1]]
    i = [0,1,2, 0,1,3, 0,2,3, 1,2,3]
    return {"version":1,"vertices":v,"indices":i}


def make_sphere(rings=6, segs=8):
    verts = []
    for r in range(rings+1):
        phi = math.pi * r / rings
        for s in range(segs):
            theta = 2*math.pi*s/segs
            verts.append([math.sin(phi)*math.cos(theta),
                          math.sin(phi)*math.sin(theta),
                          math.cos(phi)])
    inds = []
    for r in range(rings):
        for s in range(segs):
            a = r*segs+s; b = r*segs+(s+1)%segs
            c = (r+1)*segs+(s+1)%segs; d = (r+1)*segs+s
            inds += [a,b,c, a,c,d]
    return {"version":1,"vertices":verts,"indices":inds}


# ─── FakePool / ctx factory ───────────────────────────────────────────────────

def make_ctx(initial_doc=None, kind="mesh"):
    store = {
        "content": json.dumps(initial_doc) if initial_doc else None,
        "kind": kind,
    }
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            if store["content"] is None:
                return None
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            if "insert into files" in query.lower():
                store["content"] = args[3]
                store["kind"] = "mesh"
            else:
                store["content"] = args[0]

    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="editor",
        http_client=None,
    )
    return ctx, file_id, store


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ─── _validate ────────────────────────────────────────────────────────────────

def test_validate_valid_cube():
    r = _validate(make_cube())
    assert r["ok"] is True
    assert r["errors"] == []


def test_validate_indices_not_multiple_of_3():
    m = {"version":1,"vertices":[[0,0,0],[1,0,0],[0,1,0]],"indices":[0,1]}
    r = _validate(m)
    assert r["ok"] is False
    assert any("multiple of 3" in e for e in r["errors"])


def test_validate_out_of_range_index():
    m = {"version":1,"vertices":[[0,0,0],[1,0,0],[0,1,0]],"indices":[0,1,99]}
    r = _validate(m)
    assert r["ok"] is False
    assert any("out of range" in e for e in r["errors"])


def test_validate_degenerate_warns():
    m = {"version":1,"vertices":[[0,0,0],[1,0,0],[0,1,0]],"indices":[0,0,2]}
    r = _validate(m)
    assert any("degenerate" in w for w in r["warnings"])


def test_validate_open_mesh_warns():
    r = _validate(make_cube_with_hole())
    assert any("boundary" in w for w in r["warnings"])


# ─── _compute_normals ─────────────────────────────────────────────────────────

def test_compute_normals_length():
    m = _compute_normals(make_cube())
    assert len(m["normals"]) == len(m["vertices"])


def test_compute_normals_unit_length():
    m = _compute_normals(make_sphere())
    for n in m["normals"]:
        l = math.sqrt(n[0]**2+n[1]**2+n[2]**2)
        if l > 0.01:
            assert abs(l - 1.0) < 1e-4, f"normal not unit: {l}"


# ─── _decimate ────────────────────────────────────────────────────────────────

def test_decimate_reduces_face_count():
    sp = make_sphere(8, 12)
    orig = len(sp["indices"])//3
    target = orig//2
    dec = _decimate(sp, target)
    assert len(dec["indices"])//3 <= target + 2


def test_decimate_valid_indices():
    dec = _decimate(make_sphere(), 20)
    r = _validate(dec)
    assert r["errors"] == []


# ─── _smooth ─────────────────────────────────────────────────────────────────

def test_smooth_preserves_vertex_count():
    m = make_sphere()
    s = _smooth(m, 3)
    assert len(s["vertices"]) == len(m["vertices"])


def test_smooth_does_not_mutate():
    m = make_cube()
    orig = json.dumps(m)
    _smooth(m, 2)
    assert json.dumps(m) == orig


# ─── _fill_holes ─────────────────────────────────────────────────────────────

def test_fill_holes_closes_open_mesh():
    open_m = make_cube_with_hole()
    filled = _fill_holes(open_m)
    r = _validate(filled)
    assert not any("boundary" in w for w in r["warnings"])


def test_fill_holes_adds_faces():
    open_m = make_cube_with_hole()
    filled = _fill_holes(open_m)
    assert len(filled["indices"]) > len(open_m["indices"])


def test_fill_holes_leaves_closed_mesh_unchanged():
    cube = make_cube()
    filled = _fill_holes(cube)
    assert len(filled["indices"]) == len(cube["indices"])


# ─── _repair ─────────────────────────────────────────────────────────────────

def test_repair_welds_duplicates():
    tet = make_tet()
    dup_v = tet["vertices"] + tet["vertices"]
    dup_i = tet["indices"] + [i + len(tet["vertices"]) for i in tet["indices"]]
    m = {"version":1,"vertices":dup_v,"indices":dup_i}
    rep = _repair(m, 1e-6)
    assert len(rep["vertices"]) < len(dup_v)


def test_repair_removes_degenerate():
    tet = make_tet()
    m = {"version":1,"vertices":tet["vertices"],
         "indices":tet["indices"]+[0,0,1]}
    rep = _repair(m)
    r = _validate(rep)
    assert not any("degenerate" in w for w in r["warnings"])


# ─── _surface_from_points ────────────────────────────────────────────────────

def test_surface_from_points_returns_valid_mesh():
    pts = [[math.cos(i/10*math.pi*2), math.sin(i/10*math.pi*2), i*0.1] for i in range(20)]
    m = _surface_from_points(pts, 30)
    assert isinstance(m["vertices"], list)
    assert len(m["indices"]) % 3 == 0


def test_surface_from_points_respects_target():
    pts = [[math.cos(i/25*math.pi*2), math.sin(i/25*math.pi*2), i*0.05] for i in range(50)]
    m = _surface_from_points(pts, 10)
    assert len(m["indices"])//3 <= 12


def test_surface_from_points_too_few_returns_empty():
    m = _surface_from_points([[0,0,0],[1,0,0]], 10)
    assert m["vertices"] == []


# ─── LLM tool handlers ───────────────────────────────────────────────────────

def test_tool_validate_ok():
    ctx, fid, _ = make_ctx(make_cube())
    result = json.loads(run(run_mesh_validate(ctx, json.dumps({"file_id": str(fid)}).encode())))
    assert result.get("ok") is True


def test_tool_validate_missing_file():
    ctx, fid, _ = make_ctx(None)
    result = json.loads(run(run_mesh_validate(ctx, json.dumps({"file_id": str(fid)}).encode())))
    assert "error" in result


def test_tool_decimate_reduces_faces():
    sp = make_sphere(6, 8)
    orig_f = len(sp["indices"])//3
    ctx, fid, store = make_ctx(sp)
    target = orig_f // 2
    result = json.loads(run(run_mesh_decimate(ctx, json.dumps({"file_id": str(fid), "target_face_count": target}).encode())))
    assert "face_count" in result
    assert result["face_count"] <= target + 2


def test_tool_smooth_runs():
    ctx, fid, store = make_ctx(make_cube())
    result = json.loads(run(run_mesh_smooth(ctx, json.dumps({"file_id": str(fid), "iterations": 2}).encode())))
    assert result.get("file_id") == str(fid)


def test_tool_repair_returns_stats():
    tet = make_tet()
    dup_v = tet["vertices"] + tet["vertices"]
    dup_i = tet["indices"] + [i+4 for i in tet["indices"]]
    ctx, fid, _ = make_ctx({"version":1,"vertices":dup_v,"indices":dup_i})
    result = json.loads(run(run_mesh_repair(ctx, json.dumps({"file_id": str(fid)}).encode())))
    assert "welded_vertices" in result
    assert result["welded_vertices"] > 0


def test_tool_fill_holes_closes():
    ctx, fid, store = make_ctx(make_cube_with_hole())
    result = json.loads(run(run_mesh_fill_holes(ctx, json.dumps({"file_id": str(fid)}).encode())))
    assert result.get("faces_added", 0) > 0
    saved = json.loads(store["content"])
    r = _validate(saved)
    assert not any("boundary" in w for w in r["warnings"])
