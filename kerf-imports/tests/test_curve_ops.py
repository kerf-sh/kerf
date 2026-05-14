"""
Tests for curve_ops.py tools and pure geometry helpers.

Pure Python — no database required.  Uses the save/restore pattern from
test_feature_helix.py with a lightweight FakePool.
"""
import json
import math
import sys
import os
import uuid
import asyncio
import importlib.util

# ─── module loading (mirrors test_feature_helix.py pattern) ──────────────────

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

_curve_ops_mod = _load_plugin("curve_ops.py")

ProjectCtx = _context_mod.ProjectCtx

# Grab pure helpers and tool runners.
_vadd      = _curve_ops_mod._vadd
_vsub      = _curve_ops_mod._vsub
_vlen      = _curve_ops_mod._vlen
_vnorm     = _curve_ops_mod._vnorm
_vlerp     = _curve_ops_mod._vlerp
_uniform_knots         = _curve_ops_mod._uniform_knots
_de_boor               = _curve_ops_mod._de_boor
_entity_point_at       = _curve_ops_mod._entity_point_at
_entity_tangent_at     = _curve_ops_mod._entity_tangent_at
_discretize_entity     = _curve_ops_mod._discretize_entity
_intersect_entities    = _curve_ops_mod._intersect_entities
_douglas_peucker       = _curve_ops_mod._douglas_peucker

run_curve_project_to_surface = _curve_ops_mod.run_curve_project_to_surface
run_curve_intersect          = _curve_ops_mod.run_curve_intersect
run_curve_blend              = _curve_ops_mod.run_curve_blend
run_curve_match              = _curve_ops_mod.run_curve_match
run_curve_offset_3d          = _curve_ops_mod.run_curve_offset_3d
run_polyline_to_nurbs        = _curve_ops_mod.run_polyline_to_nurbs
run_simplify_curve           = _curve_ops_mod.run_simplify_curve


# ─── fake ctx/pool ────────────────────────────────────────────────────────────

def make_ctx(sketch: dict | None = None) -> tuple:
    """Return (ctx, store) where store['sketch'] holds the mutable sketch dict."""
    if sketch is None:
        sketch = {"version": 1, "entities": [], "constraints": []}
    store = {"sketch": sketch}
    project_id = uuid.uuid4()

    class FakePool:
        async def fetchrow(self, query, *args):
            return {"content": json.dumps(store["sketch"])}

        async def execute(self, query, *args):
            # args[0] is the new JSON content; args[1] is project_id; args[2] is path.
            store["sketch"] = json.loads(args[0])

    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, store


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ─── pure geometry: _uniform_knots ───────────────────────────────────────────

def test_uniform_knots_length():
    knots = _uniform_knots(3, 3)  # n=3, degree=3 → knot length = n + d + 2 = 8
    assert len(knots) == 3 + 3 + 2  # 8


def test_uniform_knots_clamped():
    knots = _uniform_knots(4, 3)
    assert knots[0] == 0.0
    assert knots[1] == 0.0
    assert knots[2] == 0.0
    assert knots[3] == 0.0
    assert knots[-1] == 1.0
    assert knots[-2] == 1.0
    assert knots[-3] == 1.0
    assert knots[-4] == 1.0


# ─── pure geometry: _entity_point_at ─────────────────────────────────────────

def test_entity_point_at_line_endpoints():
    line = {"type": "line", "x1": 0, "y1": 0, "z1": 0, "x2": 5, "y2": 0, "z2": 0}
    p0 = _entity_point_at(line, 0.0)
    p1 = _entity_point_at(line, 1.0)
    assert abs(p0[0]) < 1e-9
    assert abs(p1[0] - 5) < 1e-9


def test_entity_point_at_arc():
    arc = {"type": "arc", "cx": 0, "cy": 0, "cz": 0, "radius": 3,
           "startAngle": 0, "endAngle": math.pi / 2}
    p0 = _entity_point_at(arc, 0.0)
    p1 = _entity_point_at(arc, 1.0)
    assert abs(p0[0] - 3) < 1e-6
    assert abs(p0[1]) < 1e-6
    assert abs(p1[0]) < 1e-6
    assert abs(p1[1] - 3) < 1e-6


def test_entity_point_at_bspline_endpoints():
    cp = [{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 1, "z": 0},
          {"x": 2, "y": 1, "z": 0}, {"x": 3, "y": 0, "z": 0}]
    bs = {"type": "bspline", "degree": 3, "controlPoints": cp}
    p0 = _entity_point_at(bs, 0.0)
    p1 = _entity_point_at(bs, 1.0)
    assert abs(p0[0]) < 1e-6
    assert abs(p1[0] - 3) < 1e-6


def test_entity_tangent_unit_length_line():
    line = {"type": "line", "x1": 0, "y1": 0, "z1": 0, "x2": 3, "y2": 4, "z2": 0}
    t = _entity_tangent_at(line, 0.5)
    assert abs(_vlen(t) - 1.0) < 1e-9


# ─── pure geometry: _intersect_entities ──────────────────────────────────────

def test_intersect_crossing_lines():
    a = {"type": "line", "x1": -1, "y1": 0, "z1": 0, "x2": 1, "y2": 0, "z2": 0}
    b = {"type": "line", "x1": 0, "y1": -1, "z1": 0, "x2": 0, "y2": 1, "z2": 0}
    hits = _intersect_entities(a, b, 0.05)
    assert len(hits) == 1
    assert abs(hits[0]["x"]) < 0.05
    assert abs(hits[0]["y"]) < 0.05


def test_intersect_parallel_lines_no_hits():
    a = {"type": "line", "x1": 0, "y1": 0, "z1": 0, "x2": 5, "y2": 0, "z2": 0}
    b = {"type": "line", "x1": 0, "y1": 1, "z1": 0, "x2": 5, "y2": 1, "z2": 0}
    hits = _intersect_entities(a, b, 0.05)
    assert len(hits) == 0


# ─── pure geometry: _douglas_peucker ─────────────────────────────────────────

def test_douglas_peucker_collinear_reduces_to_2():
    pts = [[float(i), 0.0, 0.0] for i in range(20)]
    result = _douglas_peucker(pts, 0.01)
    assert len(result) == 2


def test_douglas_peucker_preserves_zigzag():
    pts = [[float(i), float(i % 2), 0.0] for i in range(10)]
    result = _douglas_peucker(pts, 0.01)
    assert len(result) == len(pts)


# ─── tool: curve_project_to_surface ──────────────────────────────────────────

def test_project_xy_drops_z():
    line = {"id": "e1", "type": "line", "x1": 1, "y1": 2, "z1": 10, "x2": 3, "y2": 4, "z2": 20}
    ctx, store = make_ctx({"version": 1, "entities": [line]})
    result = run(run_curve_project_to_surface(
        ctx, json.dumps({"sketch_file_id": "dummy.sketch", "entity_id": "e1", "target_plane": "XY"}).encode()
    ))
    r = json.loads(result)
    assert r["ok"] is True
    new_eid = r["id"]
    new_entity = next(e for e in store["sketch"]["entities"] if e["id"] == new_eid)
    for p in new_entity["points"]:
        assert abs(p["z"]) < 1e-9


def test_project_missing_entity_returns_error():
    ctx, store = make_ctx()
    result = run(run_curve_project_to_surface(
        ctx, json.dumps({"sketch_file_id": "f.sketch", "entity_id": "nope", "target_plane": "XY"}).encode()
    ))
    r = json.loads(result)
    assert "error" in r


# ─── tool: curve_intersect ───────────────────────────────────────────────────

def test_intersect_tool_crossing_lines():
    a = {"id": "a", "type": "line", "x1": -2, "y1": 0, "z1": 0, "x2": 2, "y2": 0, "z2": 0}
    b = {"id": "b", "type": "line", "x1": 0, "y1": -2, "z1": 0, "x2": 0, "y2": 2, "z2": 0}
    ctx, store = make_ctx({"version": 1, "entities": [a, b]})
    result = run(run_curve_intersect(
        ctx, json.dumps({"sketch_file_id": "f.sketch", "entity_a_id": "a", "entity_b_id": "b"}).encode()
    ))
    r = json.loads(result)
    assert r["ok"] is True
    assert r["count"] >= 1


def test_intersect_tool_no_args_error():
    ctx, store = make_ctx()
    result = run(run_curve_intersect(ctx, b"{}"))
    r = json.loads(result)
    assert "error" in r


# ─── tool: curve_blend ───────────────────────────────────────────────────────

def test_blend_g1_appends_bspline():
    a = {"id": "a", "type": "line", "x1": 0, "y1": 0, "z1": 0, "x2": 3, "y2": 0, "z2": 0}
    b = {"id": "b", "type": "line", "x1": 5, "y1": 2, "z1": 0, "x2": 8, "y2": 2, "z2": 0}
    ctx, store = make_ctx({"version": 1, "entities": [a, b]})
    result = run(run_curve_blend(
        ctx, json.dumps({
            "sketch_file_id": "f.sketch",
            "entity_a_id": "a", "end_a": "end",
            "entity_b_id": "b", "end_b": "start",
            "continuity": "G1",
        }).encode()
    ))
    r = json.loads(result)
    assert r["ok"] is True
    entities = store["sketch"]["entities"]
    blend = next(e for e in entities if e["id"] == r["id"])
    assert blend["type"] == "bspline"
    assert len(blend["controlPoints"]) == 4


def test_blend_g0_degree_1():
    a = {"id": "a", "type": "line", "x1": 0, "y1": 0, "z1": 0, "x2": 1, "y2": 0, "z2": 0}
    b = {"id": "b", "type": "line", "x1": 3, "y1": 1, "z1": 0, "x2": 5, "y2": 1, "z2": 0}
    ctx, store = make_ctx({"version": 1, "entities": [a, b]})
    result = run(run_curve_blend(
        ctx, json.dumps({
            "sketch_file_id": "f.sketch",
            "entity_a_id": "a", "end_a": "end",
            "entity_b_id": "b", "end_b": "start",
            "continuity": "G0",
        }).encode()
    ))
    r = json.loads(result)
    entities = store["sketch"]["entities"]
    blend = next(e for e in entities if e["id"] == r["id"])
    assert blend["degree"] == 1


def test_blend_bad_continuity_error():
    ctx, store = make_ctx()
    result = run(run_curve_blend(
        ctx, json.dumps({
            "sketch_file_id": "f.sketch",
            "entity_a_id": "a", "end_a": "end",
            "entity_b_id": "b", "end_b": "start",
            "continuity": "G99",
        }).encode()
    ))
    r = json.loads(result)
    assert "error" in r


# ─── tool: curve_match ───────────────────────────────────────────────────────

def test_match_moves_bspline_start():
    src = {"id": "src", "type": "line", "x1": 0, "y1": 0, "z1": 0, "x2": 5, "y2": 0, "z2": 0}
    tgt = {
        "id": "tgt", "type": "bspline", "degree": 3,
        "controlPoints": [
            {"x": 10, "y": 10, "z": 0}, {"x": 11, "y": 10, "z": 0},
            {"x": 12, "y": 11, "z": 0}, {"x": 13, "y": 11, "z": 0},
        ],
    }
    ctx, store = make_ctx({"version": 1, "entities": [src, tgt]})
    result = run(run_curve_match(
        ctx, json.dumps({
            "sketch_file_id": "f.sketch",
            "source_entity_id": "src",
            "target_entity_id": "tgt",
            "continuity": "G0",
        }).encode()
    ))
    r = json.loads(result)
    assert r["ok"] is True
    updated_tgt = next(e for e in store["sketch"]["entities"] if e["id"] == "tgt")
    cp0 = updated_tgt["controlPoints"][0]
    assert abs(cp0["x"] - 5) < 1e-6
    assert abs(cp0["y"]) < 1e-6


# ─── tool: curve_offset_3d ────────────────────────────────────────────────────

def test_offset_z_moves_points():
    line = {"id": "e1", "type": "line", "x1": 0, "y1": 0, "z1": 0, "x2": 5, "y2": 0, "z2": 0}
    ctx, store = make_ctx({"version": 1, "entities": [line]})
    result = run(run_curve_offset_3d(
        ctx, json.dumps({
            "sketch_file_id": "f.sketch",
            "entity_id": "e1",
            "distance": 4.0,
            "axis_or_normal": "Z",
        }).encode()
    ))
    r = json.loads(result)
    assert r["ok"] is True
    off = next(e for e in store["sketch"]["entities"] if e["id"] == r["id"])
    for p in off["points"]:
        assert abs(p["z"] - 4.0) < 1e-9


def test_offset_missing_distance_error():
    ctx, store = make_ctx()
    result = run(run_curve_offset_3d(
        ctx, json.dumps({"sketch_file_id": "f.sketch", "entity_id": "e1", "axis_or_normal": "Z"}).encode()
    ))
    r = json.loads(result)
    assert "error" in r


# ─── tool: polyline_to_nurbs ─────────────────────────────────────────────────

def test_polyline_to_nurbs_appends_bspline():
    poly = {
        "id": "p1", "type": "polyline",
        "points": [
            {"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 1, "z": 0},
            {"x": 2, "y": 0, "z": 0}, {"x": 3, "y": 1, "z": 0},
        ],
    }
    ctx, store = make_ctx({"version": 1, "entities": [poly]})
    result = run(run_polyline_to_nurbs(
        ctx, json.dumps({"sketch_file_id": "f.sketch", "polyline_entity_id": "p1", "degree": 3}).encode()
    ))
    r = json.loads(result)
    assert r["ok"] is True
    bs = next(e for e in store["sketch"]["entities"] if e["id"] == r["id"])
    assert bs["type"] == "bspline"
    assert bs["degree"] == 3


def test_polyline_to_nurbs_preserves_entity_count_without_replace():
    poly = {
        "id": "p1", "type": "polyline",
        "points": [{"x": i, "y": 0, "z": 0} for i in range(5)],
    }
    ctx, store = make_ctx({"version": 1, "entities": [poly]})
    run(run_polyline_to_nurbs(
        ctx, json.dumps({"sketch_file_id": "f.sketch", "polyline_entity_id": "p1"}).encode()
    ))
    assert len(store["sketch"]["entities"]) == 2  # original + new bspline


# ─── tool: simplify_curve ─────────────────────────────────────────────────────

def test_simplify_collinear_polyline_to_2_points():
    pts = [{"x": float(i), "y": 0.0, "z": 0.0} for i in range(20)]
    poly = {"id": "p1", "type": "polyline", "points": pts}
    ctx, store = make_ctx({"version": 1, "entities": [poly]})
    result = run(run_simplify_curve(
        ctx, json.dumps({"sketch_file_id": "f.sketch", "entity_id": "p1", "tolerance": 0.01}).encode()
    ))
    r = json.loads(result)
    assert r["ok"] is True
    assert r["new_count"] == 2
    assert r["reduction"] == 18


def test_simplify_missing_tolerance_error():
    ctx, store = make_ctx()
    result = run(run_simplify_curve(
        ctx, json.dumps({"sketch_file_id": "f.sketch", "entity_id": "e1"}).encode()
    ))
    r = json.loads(result)
    assert "error" in r


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
