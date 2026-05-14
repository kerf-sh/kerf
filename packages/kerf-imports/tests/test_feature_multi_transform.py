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


_registry_mod = sys.modules.get("tools.registry") or _load("tools/registry.py")
_context_mod  = sys.modules.get("tools.context")  or _load("tools/context.py")
sys.modules.setdefault("tools.registry", _registry_mod)
sys.modules.setdefault("tools.context",  _context_mod)

_surfacing_mod = sys.modules.get("tools.surfacing") or _load("tools/surfacing.py")
sys.modules.setdefault("tools.surfacing", _surfacing_mod)

_multi_transform_mod = _load_plugin("feature_multi_transform.py")

validate_multi_transform_args = _multi_transform_mod.validate_multi_transform_args
build_multi_transform_node = _multi_transform_mod.build_multi_transform_node
feature_multi_transform_spec = _multi_transform_mod.feature_multi_transform_spec
run_feature_multi_transform = _multi_transform_mod.run_feature_multi_transform

ProjectCtx = _context_mod.ProjectCtx


def make_ctx(initial_content: str = "") -> tuple:
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
        run_feature_multi_transform(ctx, json.dumps(args).encode())
    )
    return json.loads(raw)


def test_validate_linear_transform():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "linear", "direction": "x", "count": 4, "spacing": 10}]
    )
    assert err is None and code is None


def test_validate_polar_transform():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "polar", "axis": "z", "count": 6, "total_angle_deg": 360}]
    )
    assert err is None and code is None


def test_validate_mirror_transform():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "mirror", "plane_or_face": "XY"}]
    )
    assert err is None and code is None


def test_validate_rejects_empty_source():
    err, code = validate_multi_transform_args(
        "",
        [{"kind": "linear", "direction": "x", "count": 2, "spacing": 1}]
    )
    assert err is not None


def test_validate_rejects_empty_transforms():
    err, code = validate_multi_transform_args("pad-1", [])
    assert err is not None


def test_validate_linear_requires_direction():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "linear", "count": 4, "spacing": 10}]
    )
    assert err is not None and "direction" in err


def test_validate_linear_requires_count():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "linear", "direction": "x", "spacing": 10}]
    )
    assert err is not None and "count" in err


def test_validate_linear_requires_spacing():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "linear", "direction": "x", "count": 4}]
    )
    assert err is not None and "spacing" in err


def test_validate_linear_count_must_be_at_least_2():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "linear", "direction": "x", "count": 1, "spacing": 10}]
    )
    assert err is not None and "count" in err


def test_validate_polar_requires_axis():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "polar", "count": 6, "total_angle_deg": 360}]
    )
    assert err is not None and "axis" in err


def test_validate_polar_requires_total_angle():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "polar", "axis": "z", "count": 6}]
    )
    assert err is not None and "total_angle" in err


def test_validate_polar_total_angle_max_360():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "polar", "axis": "z", "count": 6, "total_angle_deg": 361}]
    )
    assert err is not None


def test_validate_mirror_requires_plane_or_face():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "mirror"}]
    )
    assert err is not None and "plane_or_face" in err


def test_validate_rejects_invalid_kind():
    err, code = validate_multi_transform_args(
        "pad-1",
        [{"kind": "invalid", "direction": "x"}]
    )
    assert err is not None and "kind" in err


def test_validate_rejects_too_many_transforms():
    transforms = [
        {"kind": "linear", "direction": "x", "count": 2, "spacing": 1},
        {"kind": "polar", "axis": "z", "count": 2, "total_angle_deg": 180},
        {"kind": "linear", "direction": "y", "count": 2, "spacing": 1},
        {"kind": "mirror", "plane_or_face": "XY"},
        {"kind": "linear", "direction": "z", "count": 2, "spacing": 1},
    ]
    err, code = validate_multi_transform_args("pad-1", transforms)
    assert err is not None and "maximum of 4" in err


def test_build_multi_transform_node():
    node = build_multi_transform_node(
        "multi_transform-1",
        "pad-1",
        [{"kind": "linear", "direction": "x", "count": 4, "spacing": 10}],
        "my_pattern"
    )
    assert node["id"] == "multi_transform-1"
    assert node["op"] == "multi_transform"
    assert node["params"]["source_feature_id"] == "pad-1"
    assert node["name"] == "my_pattern"
    assert len(node["params"]["transforms"]) == 1


def test_tool_appends_node():
    ctx, store, fid = make_ctx('{"version": 1, "features": [{"id": "pad-1", "op": "pad"}]}')
    result = run_tool(
        ctx, fid,
        source_feature_id="pad-1",
        transforms=[{"kind": "linear", "direction": "x", "count": 4, "spacing": 10}]
    )
    assert "error" not in result
    assert result.get("op") == "multi_transform"
    doc = json.loads(store["content"])
    assert len(doc["features"]) == 2
    node = doc["features"][1]
    assert node["op"] == "multi_transform"


def test_tool_missing_source_feature_id():
    ctx, store, fid = make_ctx('{"version": 1, "features": []}')
    result = run_tool(
        ctx, fid,
        source_feature_id="nonexistent",
        transforms=[{"kind": "linear", "direction": "x", "count": 2, "spacing": 1}]
    )
    assert "error" in result


def test_tool_source_feature_not_found():
    ctx, store, fid = make_ctx('{"version": 1, "features": []}')
    result = run_tool(
        ctx, fid,
        source_feature_id="pad-99",
        transforms=[{"kind": "linear", "direction": "x", "count": 2, "spacing": 1}]
    )
    assert "error" in result


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])