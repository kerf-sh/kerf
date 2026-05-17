"""
Tests for kerf_bim/tools/stairs.py — pure logic, no database required.

Uses importlib to load the module directly, bypassing the package init chain.
"""
import importlib.util
import json
import os
import sys
import uuid
import asyncio


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Ensure canonical registry + context packages are importable as stubs before
# the module under test imports them.
from kerf_chat.tools.registry import ToolSpec, register, ok_payload, err_payload  # noqa: E402
from kerf_core.utils.context import ProjectCtx  # noqa: E402

_plugin_tools = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "kerf_bim", "tools",
)

_stairs_mod = _load_module(
    "kerf_bim.tools.stairs",
    os.path.join(_plugin_tools, "stairs.py"),
)

_default_stair = _stairs_mod._default_stair
validate_stair_doc = _stairs_mod.validate_stair_doc
run_create_stair = _stairs_mod.run_create_stair
run_add_stair_flight = _stairs_mod.run_add_stair_flight
run_add_stair_landing = _stairs_mod.run_add_stair_landing
run_validate_stair = _stairs_mod.run_validate_stair


# ── fake ctx ───────────────────────────────────────────────────────────────────

def make_ctx(kind: str = "stair"):
    store = {"content": None, "kind": kind}
    project_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            if store["content"] is None:
                return None
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            q = query.strip().lower()
            if q.startswith("insert"):
                store["content"] = args[2]
            elif q.startswith("update"):
                store["content"] = args[0]

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


# ── _default_stair ─────────────────────────────────────────────────────────────

def test_default_stair_version():
    doc = _default_stair(2800, 3360)
    assert doc["version"] == 1


def test_default_stair_dimensions():
    doc = _default_stair(2100, 3000)
    assert doc["total_rise_mm"] == 2100
    assert doc["total_run_mm"] == 3000
    assert doc["tread_depth_mm"] == 280
    assert doc["riser_height_mm"] == 175


# ── validate_stair_doc ─────────────────────────────────────────────────────────

def test_validate_accepts_valid():
    doc = _default_stair(2800, 3360)
    # 2×175 + 280 = 630 — passes
    errors = validate_stair_doc(doc)
    assert errors == []


def test_validate_rejects_low_riser():
    doc = {**_default_stair(2800, 3360), "riser_height_mm": 80}
    errors = validate_stair_doc(doc)
    assert any("riser_height_mm" in e for e in errors)


def test_validate_rejects_high_riser():
    doc = {**_default_stair(2800, 3360), "riser_height_mm": 230}
    errors = validate_stair_doc(doc)
    assert any("riser_height_mm" in e for e in errors)


def test_validate_rejects_low_tread():
    doc = {**_default_stair(2800, 3360), "tread_depth_mm": 180}
    errors = validate_stair_doc(doc)
    assert any("tread_depth_mm" in e for e in errors)


def test_validate_rejects_high_tread():
    doc = {**_default_stair(2800, 3360), "tread_depth_mm": 360}
    errors = validate_stair_doc(doc)
    assert any("tread_depth_mm" in e for e in errors)


def test_validate_rejects_formula_below_550():
    # 2×100 + 340 = 540
    doc = {**_default_stair(2800, 3360), "riser_height_mm": 100, "tread_depth_mm": 340}
    errors = validate_stair_doc(doc)
    assert any("2R+T" in e for e in errors)


def test_validate_rejects_formula_above_700():
    # 2×220 + 280 = 720
    doc = {**_default_stair(2800, 3360), "riser_height_mm": 220, "tread_depth_mm": 280}
    errors = validate_stair_doc(doc)
    assert any("2R+T" in e for e in errors)


def test_validate_accepts_boundary_550():
    # 2×150 + 250 = 550
    doc = {**_default_stair(2800, 3360), "riser_height_mm": 150, "tread_depth_mm": 250}
    errors = validate_stair_doc(doc)
    assert errors == []


def test_validate_accepts_boundary_700():
    # 2×200 + 300 = 700
    doc = {**_default_stair(2800, 3360), "riser_height_mm": 200, "tread_depth_mm": 300}
    errors = validate_stair_doc(doc)
    assert errors == []


# ── create_stair tool ──────────────────────────────────────────────────────────

def test_create_straight_stair():
    ctx, store = make_ctx()
    result = json.loads(run(run_create_stair(ctx, json.dumps({
        "total_rise_mm": 2800,
        "total_run_mm": 3360,
        "kind": "straight",
        "start_point": [0, 0, 0],
    }).encode())))
    assert "error" not in result
    assert result["flights"] == 1
    doc = json.loads(store["content"])
    assert len(doc["flights"]) == 1


def test_create_l_stair():
    ctx, store = make_ctx()
    result = json.loads(run(run_create_stair(ctx, json.dumps({
        "total_rise_mm": 2100,
        "total_run_mm": 3360,
        "kind": "L",
        "start_point": [0, 0, 0],
    }).encode())))
    assert "error" not in result
    assert result["flights"] == 2
    doc = json.loads(store["content"])
    assert len(doc["landings"]) == 1


def test_create_u_stair():
    ctx, store = make_ctx()
    result = json.loads(run(run_create_stair(ctx, json.dumps({
        "total_rise_mm": 2100,
        "total_run_mm": 3360,
        "kind": "U",
        "start_point": [0, 0, 0],
    }).encode())))
    assert "error" not in result
    assert result["flights"] == 2


def test_create_stair_missing_required():
    ctx, store = make_ctx()
    result = json.loads(run(run_create_stair(ctx, json.dumps({
        "total_run_mm": 3360,
        "kind": "straight",
        "start_point": [0, 0, 0],
    }).encode())))
    assert "error" in result


def test_create_stair_invalid_kind():
    ctx, store = make_ctx()
    result = json.loads(run(run_create_stair(ctx, json.dumps({
        "total_rise_mm": 2800,
        "total_run_mm": 3360,
        "kind": "spiral",
        "start_point": [0, 0, 0],
    }).encode())))
    assert "error" in result


# ── add_stair_flight tool ──────────────────────────────────────────────────────

def test_add_flight():
    ctx, store = make_ctx()
    # First create a stair
    run(run_create_stair(ctx, json.dumps({
        "total_rise_mm": 2800,
        "total_run_mm": 3360,
        "kind": "straight",
        "start_point": [0, 0, 0],
    }).encode()))
    fid = json.loads(store["content"])  # read doc
    # We need the file_id from the create result — create fresh
    ctx2, store2 = make_ctx()
    raw = run(run_create_stair(ctx2, json.dumps({
        "total_rise_mm": 2800,
        "total_run_mm": 3360,
        "kind": "straight",
        "start_point": [0, 0, 0],
        "file_id": str(uuid.uuid4()),
    }).encode()))
    result = json.loads(raw)
    file_id = result["file_id"]

    add_result = json.loads(run(run_add_stair_flight(ctx2, json.dumps({
        "file_id": file_id,
        "start": [3360, 0, 2800],
        "direction": [0, 1, 0],
        "step_count": 6,
    }).encode())))
    assert "error" not in add_result
    doc = json.loads(store2["content"])
    assert len(doc["flights"]) == 2


# ── validate_stair tool ────────────────────────────────────────────────────────

def test_validate_tool_ok():
    ctx, store = make_ctx()
    raw = run(run_create_stair(ctx, json.dumps({
        "total_rise_mm": 2800,
        "total_run_mm": 3360,
        "kind": "straight",
        "start_point": [0, 0, 0],
        "file_id": str(uuid.uuid4()),
    }).encode()))
    file_id = json.loads(raw)["file_id"]

    val = json.loads(run(run_validate_stair(ctx, json.dumps({"file_id": file_id}).encode())))
    assert "error" not in val
    assert val["ok"] is True
    assert val["errors"] == []


def test_validate_tool_not_found():
    ctx, _ = make_ctx()
    result = json.loads(run(run_validate_stair(ctx, json.dumps({"file_id": str(uuid.uuid4())}).encode())))
    assert "error" in result


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
