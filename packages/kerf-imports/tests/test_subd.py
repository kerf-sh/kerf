"""
Tests for subd.py LLM tools.

Uses importlib.util.spec_from_file_location to avoid the tools/__init__.py
db-import chain (same pattern as test_feature_helix.py, test_project_layers.py).
"""
import json
import math
import sys
import os
import uuid
import asyncio
import importlib.util

_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "backend")
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
_context_mod = sys.modules.get("tools.context") or _load("tools/context.py")
sys.modules.setdefault("tools.registry", _registry_mod)
sys.modules.setdefault("tools.context", _context_mod)

_subd_mod = _load_plugin("subd.py")

# Expose helpers
_cube_mesh = _subd_mod._cube_mesh
_sphere_mesh = _subd_mod._sphere_mesh
_cylinder_mesh = _subd_mod._cylinder_mesh
_cc_once = _subd_mod._cc_once
_subdivide_mesh = _subd_mod._subdivide_mesh
_triangulate_display_mesh = _subd_mod._triangulate_display_mesh
_edge_key = _subd_mod._edge_key

run_create_subd = _subd_mod.run_create_subd
run_subdivide_subd = _subd_mod.run_subdivide_subd
run_extrude_face_subd = _subd_mod.run_extrude_face_subd
run_bevel_edge_subd = _subd_mod.run_bevel_edge_subd
run_set_edge_crease = _subd_mod.run_set_edge_crease

ProjectCtx = _context_mod.ProjectCtx


# ── FakePool / ctx factory ────────────────────────────────────────────────────

def make_ctx(initial_doc=None, kind="subd"):
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
            # Both UPDATE (content, fid, pid) and INSERT (fid, pid, name, content) patterns
            # For insert: args = (fid, project_id, name, body)
            # For update: args = (body, fid, pid)
            if "insert into files" in query.lower():
                # args: (fid, project_id, name, body)
                store["content"] = args[3]
                store["kind"] = "subd"
            else:
                # args: (body, fid, pid)
                store["content"] = args[0]

    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, store, file_id


def run_tool(coro):
    return json.loads(asyncio.run(coro))


# ── Primitive mesh tests ───────────────────────────────────────────────────────

def test_cube_mesh_structure():
    m = _cube_mesh()
    assert len(m["vertices"]) == 8
    assert len(m["faces"]) == 6
    assert len(m["edges"]) == 12


def test_sphere_mesh_structure():
    m = _sphere_mesh(rings=4, segments=8)
    assert len(m["faces"]) == 32   # 4 rings × 8 segments
    assert all(len(f["vertex_ids"]) == 4 for f in m["faces"])


def test_cylinder_mesh_structure():
    m = _cylinder_mesh(segments=8)
    # 8 side faces + 2 caps = 10
    assert len(m["faces"]) == 10


# ── Catmull-Clark one level ───────────────────────────────────────────────────

def test_cc_once_cube_face_count():
    m = _cube_mesh()
    result = _cc_once(m)
    # 6 faces × 4 = 24
    assert len(result["faces"]) == 24


def test_cc_once_cube_vertex_count():
    m = _cube_mesh()
    result = _cc_once(m)
    # 8 orig + 12 edge points + 6 face points = 26
    assert len(result["vertices"]) == 26


def test_subdivide_mesh_two_levels():
    m = _cube_mesh()
    result = _subdivide_mesh(m, 2)
    assert len(result["faces"]) == 96  # 6 × 4² = 96


def test_triangulate_display_mesh():
    m = _subdivide_mesh(_cube_mesh(), 1)
    dm = _triangulate_display_mesh(m)
    assert len(dm["vertices"]) == 26
    # 24 quads × 2 triangles × 3 = 144 indices
    assert len(dm["indices"]) == 144
    assert len(dm["indices"]) % 3 == 0


# ── Crease preservation ───────────────────────────────────────────────────────

def test_crease_edge_midpoint_stays_on_edge():
    """Fully creased edge: edge point must be the midpoint of the two endpoints."""
    m = _cube_mesh()
    # Crease edge 0-1 fully
    for e in m["edges"]:
        if _edge_key(e["v1"], e["v2"]) == _edge_key(0, 1):
            e["crease_value"] = 1.0
    result = _cc_once(m)
    vert_map = {v["id"]: v for v in result["vertices"]}
    # Find the edge point for 0-1 — it should be at (0,−1,−1) avg of v0=(−1,−1,−1) and v1=(1,−1,−1)
    # The edge-point vertex is newly inserted; check it appears at (0, -1, -1)
    found = any(
        abs(v["x"] - 0) < 1e-9 and abs(v["y"] - (-1)) < 1e-9 and abs(v["z"] - (-1)) < 1e-9
        for v in result["vertices"]
    )
    assert found, "Creased edge midpoint not found at expected position"


# ── create_subd tool ──────────────────────────────────────────────────────────

def test_create_subd_cube():
    ctx, store, _ = make_ctx()
    result = run_tool(run_create_subd(ctx, json.dumps({"primitive": "cube", "subdivision_level": 1}).encode()))
    assert "error" not in result
    assert result["primitive"] == "cube"
    assert result["face_count"] == 24
    assert "file_id" in result


def test_create_subd_sphere():
    ctx, store, _ = make_ctx()
    result = run_tool(run_create_subd(ctx, json.dumps({"primitive": "sphere", "subdivision_level": 1}).encode()))
    assert "error" not in result
    assert result["face_count"] == 128  # 32 faces × 4


def test_create_subd_cylinder():
    ctx, store, _ = make_ctx()
    result = run_tool(run_create_subd(ctx, json.dumps({"primitive": "cylinder", "subdivision_level": 1}).encode()))
    assert "error" not in result
    # 8 side quads × 4 + 2 caps (each 8-gon) × 8 = 32 + 16 = 48
    assert result["face_count"] == 48


def test_create_subd_invalid_primitive():
    ctx, store, _ = make_ctx()
    result = run_tool(run_create_subd(ctx, json.dumps({"primitive": "torus"}).encode()))
    assert "error" in result


def test_create_subd_invalid_level():
    ctx, store, _ = make_ctx()
    result = run_tool(run_create_subd(ctx, json.dumps({"primitive": "cube", "subdivision_level": -1}).encode()))
    assert "error" in result


# ── subdivide_subd tool ────────────────────────────────────────────────────────

def test_subdivide_subd_tool():
    initial_doc = {
        "version": 1,
        "control_mesh": _cube_mesh(),
        "subdivision_level": 1,
        "display_mesh": None,
    }
    ctx, store, fid = make_ctx(initial_doc)
    result = run_tool(run_subdivide_subd(ctx, json.dumps({"file_id": str(fid)}).encode()))
    assert "error" not in result
    assert result["face_count"] == 24


def test_subdivide_subd_missing_file_id():
    ctx, store, _ = make_ctx()
    result = run_tool(run_subdivide_subd(ctx, json.dumps({}).encode()))
    assert "error" in result


def test_subdivide_subd_invalid_uuid():
    ctx, store, _ = make_ctx()
    result = run_tool(run_subdivide_subd(ctx, json.dumps({"file_id": "not-a-uuid"}).encode()))
    assert "error" in result


# ── extrude_face_subd tool ────────────────────────────────────────────────────

def test_extrude_face_subd_tool():
    initial_doc = {
        "version": 1,
        "control_mesh": _cube_mesh(),
        "subdivision_level": 1,
        "display_mesh": None,
    }
    ctx, store, fid = make_ctx(initial_doc)
    result = run_tool(run_extrude_face_subd(ctx, json.dumps({"file_id": str(fid), "face_id": 0, "distance": 1.0}).encode()))
    assert "error" not in result
    assert result["new_faces"] == 4  # quad face → 4 side faces

    # Verify content updated
    doc = json.loads(store["content"])
    assert len(doc["control_mesh"]["faces"]) == 10  # 6 + 4


def test_extrude_face_missing_face():
    initial_doc = {
        "version": 1,
        "control_mesh": _cube_mesh(),
        "subdivision_level": 1,
        "display_mesh": None,
    }
    ctx, store, fid = make_ctx(initial_doc)
    result = run_tool(run_extrude_face_subd(ctx, json.dumps({"file_id": str(fid), "face_id": 999, "distance": 1.0}).encode()))
    assert "error" in result


# ── bevel_edge_subd tool ──────────────────────────────────────────────────────

def test_bevel_edge_tool():
    initial_doc = {
        "version": 1,
        "control_mesh": _cube_mesh(),
        "subdivision_level": 1,
        "display_mesh": None,
    }
    ctx, store, fid = make_ctx(initial_doc)
    result = run_tool(run_bevel_edge_subd(ctx, json.dumps({"file_id": str(fid), "v1_id": 0, "v2_id": 1, "width": 0.2}).encode()))
    assert "error" not in result
    assert len(result["new_vertex_ids"]) == 2

    doc = json.loads(store["content"])
    assert len(doc["control_mesh"]["vertices"]) == 10  # 8 + 2


# ── set_edge_crease tool ──────────────────────────────────────────────────────

def test_set_edge_crease_tool():
    initial_doc = {
        "version": 1,
        "control_mesh": _cube_mesh(),
        "subdivision_level": 1,
        "display_mesh": None,
    }
    ctx, store, fid = make_ctx(initial_doc)
    result = run_tool(run_set_edge_crease(ctx, json.dumps({"file_id": str(fid), "v1_id": 0, "v2_id": 1, "crease": 0.8}).encode()))
    assert "error" not in result
    assert result["crease"] == 0.8

    doc = json.loads(store["content"])
    edges = doc["control_mesh"]["edges"]
    matching = [e for e in edges if _edge_key(e["v1"], e["v2"]) == _edge_key(0, 1)]
    assert matching
    assert matching[0]["crease_value"] == 0.8


def test_set_edge_crease_out_of_range():
    initial_doc = {
        "version": 1,
        "control_mesh": _cube_mesh(),
        "subdivision_level": 1,
        "display_mesh": None,
    }
    ctx, store, fid = make_ctx(initial_doc)
    result = run_tool(run_set_edge_crease(ctx, json.dumps({"file_id": str(fid), "v1_id": 0, "v2_id": 1, "crease": 1.5}).encode()))
    assert "error" in result


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
