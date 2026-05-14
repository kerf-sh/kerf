"""
Tests for feature_helix tool and helix_polyline helper.

Pure-Python: no database, no ProjectCtx needed for the geometry tests.
The tool-registration tests use a lightweight fake pool/ctx.
"""
import json
import math
import sys
import os
import uuid
import asyncio
import importlib.util

# Load modules directly to avoid tools/__init__.py triggering the db chain.
# backend/ for registry, context, surfacing; plugin src/ for moved tools
_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "backend")
_PLUGIN_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "kerf_imports", "tools")


def _load(rel):
    path = os.path.join(_BACKEND, rel)
    spec = importlib.util.spec_from_file_location(rel.replace("/", ".").replace(".py", ""), path)
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


# registry and context have no upstream imports beyond stdlib.
# Use setdefault so we don't clobber the real module when the full suite runs.
_registry_mod = sys.modules.get("tools.registry") or _load("tools/registry.py")
_context_mod  = sys.modules.get("tools.context")  or _load("tools/context.py")

# Patch sys.modules so that 'tools.registry' and 'tools.context' resolve correctly
sys.modules.setdefault("tools.registry", _registry_mod)
sys.modules.setdefault("tools.context",  _context_mod)

# Load surfacing (needed by feature_helix for helpers)
_surfacing_mod = sys.modules.get("tools.surfacing") or _load("tools/surfacing.py")
sys.modules.setdefault("tools.surfacing", _surfacing_mod)

# Now load feature_helix itself (now in kerf-imports plugin)
_helix_mod = _load_plugin("feature_helix.py")

helix_polyline    = _helix_mod.helix_polyline
feature_helix_spec = _helix_mod.feature_helix_spec
run_feature_helix  = _helix_mod.run_feature_helix

ProjectCtx = _context_mod.ProjectCtx


# ── helpers ───────────────────────────────────────────────────────────────────

def make_ctx(initial_content: str = "") -> tuple[ProjectCtx, dict]:
    """Return a (ctx, store) pair where store['content'] tracks the current file content."""
    store = {
        "content": initial_content or json.dumps({"version": 1, "features": []}),
        "kind": "feature",
    }
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            # args: (new_content, file_id, project_id)
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


def run_tool(ctx, file_id, **kwargs):
    args = {"file_id": str(file_id), **kwargs}
    raw = asyncio.new_event_loop().run_until_complete(
        run_feature_helix(ctx, json.dumps(args).encode())
    )
    return json.loads(raw)


# ── helix_polyline geometry tests ─────────────────────────────────────────────

def test_polyline_returns_points():
    pts = helix_polyline(pitch=5, height=10, radius=3)
    assert len(pts) >= 2


def test_polyline_one_full_turn_z_range():
    """One turn: z goes from 0 to pitch."""
    pitch = 4.0
    pts = helix_polyline(pitch=pitch, height=pitch, radius=1.0, segments=128)
    zs = [p[2] for p in pts]
    assert abs(zs[0]) < 1e-9
    assert abs(zs[-1] - pitch) < 1e-6


def test_polyline_one_turn_radial_distance():
    """For a cylindrical helix, every point lies at the given radius (xy-plane)."""
    radius = 5.0
    pts = helix_polyline(pitch=3.0, height=3.0, radius=radius, segments=256)
    for x, y, _ in pts:
        r = math.sqrt(x * x + y * y)
        assert abs(r - radius) < 1e-4, f"radius deviation {abs(r - radius)}"


def test_polyline_direction_right_vs_left():
    """Right and left helices start at the same point but diverge in angle."""
    pts_r = helix_polyline(pitch=5, height=5, radius=1, direction="right", segments=64)
    pts_l = helix_polyline(pitch=5, height=5, radius=1, direction="left", segments=64)
    # Both should have the same number of points
    assert len(pts_r) == len(pts_l)
    # At z = 0 they start at the same x,y (angle=0 → (radius, 0, 0))
    assert abs(pts_r[0][0] - pts_l[0][0]) < 1e-9
    # Midpoint y-coords should be mirrored (opposite sign for opposite rotation)
    mid = len(pts_r) // 2
    assert pts_r[mid][1] * pts_l[mid][1] <= 0  # opposite signs (or one is near zero)


def test_polyline_conical_radius_grows():
    """With cone_angle > 0 the radius should increase monotonically with z."""
    pts = helix_polyline(pitch=5, height=10, radius=2, cone_angle=10, segments=64)
    radii = [math.sqrt(x * x + y * y) for x, y, z in pts]
    for i in range(1, len(radii)):
        assert radii[i] >= radii[i - 1] - 1e-9


def test_polyline_total_axial_travel():
    """Total z travel equals height regardless of number of turns."""
    for n_turns in [0.5, 1, 2.5, 10]:
        pitch = 2.0
        height = pitch * n_turns
        pts = helix_polyline(pitch=pitch, height=height, radius=1.0)
        assert abs(pts[-1][2] - height) < 1e-5, f"z mismatch for {n_turns} turns"


def test_polyline_invalid_params_return_empty():
    assert helix_polyline(pitch=0, height=5, radius=1) == []
    assert helix_polyline(pitch=5, height=0, radius=1) == []
    assert helix_polyline(pitch=5, height=5, radius=0) == []
    assert helix_polyline(pitch=5, height=5, radius=1, segments=2) == []


# ── tool validation tests ─────────────────────────────────────────────────────

def test_tool_missing_required_params():
    ctx, store, fid = make_ctx()
    result = run_tool(ctx, fid, pitch_mm=1.0, height_mm=5.0)  # missing radius_mm
    assert "error" in result


def test_tool_negative_pitch():
    ctx, store, fid = make_ctx()
    result = run_tool(ctx, fid, pitch_mm=-1.0, height_mm=5.0, radius_mm=2.0)
    assert "error" in result


def test_tool_zero_height():
    ctx, store, fid = make_ctx()
    result = run_tool(ctx, fid, pitch_mm=1.0, height_mm=0, radius_mm=2.0)
    assert "error" in result


def test_tool_invalid_direction():
    ctx, store, fid = make_ctx()
    result = run_tool(ctx, fid, pitch_mm=1.0, height_mm=5.0, radius_mm=2.0, direction="upward")
    assert "error" in result


def test_tool_invalid_cone_angle():
    ctx, store, fid = make_ctx()
    result = run_tool(ctx, fid, pitch_mm=1.0, height_mm=5.0, radius_mm=2.0, cone_half_angle_deg=90)
    assert "error" in result


def test_tool_appends_node():
    ctx, store, fid = make_ctx()
    result = run_tool(ctx, fid, pitch_mm=2.0, height_mm=10.0, radius_mm=5.0)
    assert "error" not in result
    assert result.get("op") == "helix"
    doc = json.loads(store["content"])
    assert len(doc["features"]) == 1
    node = doc["features"][0]
    assert node["op"] == "helix"
    assert node["pitch_mm"] == 2.0
    assert node["height_mm"] == 10.0
    assert node["radius_mm"] == 5.0


def test_tool_turns_returned():
    ctx, store, fid = make_ctx()
    result = run_tool(ctx, fid, pitch_mm=2.5, height_mm=10.0, radius_mm=3.0)
    assert abs(result["turns"] - 4.0) < 1e-9


def test_tool_node_id_auto_increments():
    ctx, store, fid = make_ctx()
    run_tool(ctx, fid, pitch_mm=2.0, height_mm=4.0, radius_mm=1.0)
    run_tool(ctx, fid, pitch_mm=2.0, height_mm=4.0, radius_mm=1.0)
    doc = json.loads(store["content"])
    assert doc["features"][0]["id"] == "helix-1"
    assert doc["features"][1]["id"] == "helix-2"


def test_tool_explicit_node_id():
    ctx, store, fid = make_ctx()
    result = run_tool(ctx, fid, pitch_mm=2.0, height_mm=4.0, radius_mm=1.0, id="spring-coil")
    assert result["id"] == "spring-coil"
    doc = json.loads(store["content"])
    assert doc["features"][0]["id"] == "spring-coil"


def test_tool_profile_sketch_id_stored():
    ctx, store, fid = make_ctx()
    sketch_id = str(uuid.uuid4())
    run_tool(ctx, fid, pitch_mm=1.0, height_mm=6.0, radius_mm=4.0, profile_sketch_id=sketch_id)
    doc = json.loads(store["content"])
    assert doc["features"][0]["profile_sketch_id"] == sketch_id


def test_tool_invalid_file_uuid():
    ctx, store, _ = make_ctx()
    args = json.dumps({"file_id": "not-a-uuid", "pitch_mm": 1, "height_mm": 5, "radius_mm": 2})
    raw = asyncio.new_event_loop().run_until_complete(
        run_feature_helix(ctx, args.encode())
    )
    result = json.loads(raw)
    assert "error" in result


def test_tool_conical_node_stored():
    ctx, store, fid = make_ctx()
    run_tool(ctx, fid, pitch_mm=3.0, height_mm=15.0, radius_mm=5.0, cone_half_angle_deg=15.0)
    doc = json.loads(store["content"])
    node = doc["features"][0]
    assert node["cone_half_angle_deg"] == 15.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
