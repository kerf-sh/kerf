"""
Tests for railings.py — pure logic, no database required.

Uses importlib to load the module directly, bypassing the package init chain.
"""
import importlib.util
import json
import os
import sys
import uuid
import asyncio
import math


def _load_module(name: str, rel_path: str):
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(base, rel_path)
    spec = importlib.util.spec_from_file_location(name, full_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backend")
_tools_dir = os.path.join(_base, "tools")
_plugin_tools = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "kerf_bim", "tools")

if "tools.registry" not in sys.modules:
    _load_module("tools.registry", os.path.join(_tools_dir, "registry.py"))
if "tools.context" not in sys.modules:
    _load_module("tools.context", os.path.join(_tools_dir, "context.py"))

_railings_mod = _load_module(
    "tools.railings",
    os.path.join(_plugin_tools, "railings.py"),
)

_default_railing = _railings_mod._default_railing
validate_railing_doc = _railings_mod.validate_railing_doc
compute_post_positions = _railings_mod.compute_post_positions
compute_baluster_positions = _railings_mod.compute_baluster_positions
_stair_edge_path = _railings_mod._stair_edge_path
run_create_railing = _railings_mod.run_create_railing
run_railing_from_stair = _railings_mod.run_railing_from_stair
run_set_baluster_spacing = _railings_mod.run_set_baluster_spacing
run_validate_railing = _railings_mod.run_validate_railing

ProjectCtx = sys.modules["tools.context"].ProjectCtx


# ── fake ctx ───────────────────────────────────────────────────────────────────

def make_ctx(kind: str = "railing"):
    store: dict = {"content": None, "kind": kind}
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


def make_path(n: int = 3, length: float = 1000):
    step = length / (n - 1) if n > 1 else 0
    return [{"x": i * step, "y": 0, "z": 0} for i in range(n)]


# ── _default_railing ───────────────────────────────────────────────────────────

def test_default_railing_version():
    r = _default_railing(make_path())
    assert r["version"] == 1


def test_default_railing_stores_path():
    path = make_path(4)
    r = _default_railing(path)
    assert len(r["path"]) == 4


def test_default_railing_height_mm():
    r = _default_railing(make_path(), height_mm=900)
    assert r["height_mm"] == 900


def test_default_railing_sub_objects():
    r = _default_railing(make_path())
    assert "top_rail" in r
    assert "posts" in r
    assert "balusters" in r


# ── validate_railing_doc ───────────────────────────────────────────────────────

def test_validate_valid_railing():
    r = _default_railing(make_path())
    errors = validate_railing_doc(r)
    assert errors == []


def test_validate_rejects_short_path():
    r = {**_default_railing(make_path()), "path": [{"x": 0, "y": 0, "z": 0}]}
    errors = validate_railing_doc(r)
    assert any("path" in e for e in errors)


def test_validate_rejects_low_height():
    r = {**_default_railing(make_path()), "height_mm": 400}
    errors = validate_railing_doc(r)
    assert any("height_mm" in e for e in errors)


def test_validate_rejects_high_height():
    r = {**_default_railing(make_path()), "height_mm": 1500}
    errors = validate_railing_doc(r)
    assert any("height_mm" in e for e in errors)


def test_validate_rejects_invalid_profile():
    r = _default_railing(make_path())
    r["top_rail"] = {**r["top_rail"], "profile": "oval"}
    errors = validate_railing_doc(r)
    assert any("top_rail.profile" in e for e in errors)


# ── compute_post_positions ─────────────────────────────────────────────────────

def test_post_positions_at_least_two():
    path = [{"x": 0, "y": 0, "z": 0}, {"x": 1000, "y": 0, "z": 0}]
    posts = compute_post_positions(path, 1200)
    assert len(posts) >= 2


def test_post_positions_first_at_start():
    path = [{"x": 100, "y": 0, "z": 0}, {"x": 1100, "y": 0, "z": 0}]
    posts = compute_post_positions(path, 1200)
    assert abs(posts[0]["x"] - 100) < 1e-4


def test_post_positions_last_at_end():
    path = [{"x": 0, "y": 0, "z": 0}, {"x": 2400, "y": 0, "z": 0}]
    posts = compute_post_positions(path, 1200)
    assert abs(posts[-1]["x"] - 2400) < 1e-3


def test_post_spacing_not_exceeded():
    path = [{"x": 0, "y": 0, "z": 0}, {"x": 5000, "y": 0, "z": 0}]
    posts = compute_post_positions(path, 1200)
    for i in range(1, len(posts)):
        dx = posts[i]["x"] - posts[i - 1]["x"]
        dist = abs(dx)
        assert dist <= 1200 + 1


# ── compute_baluster_positions ─────────────────────────────────────────────────

def test_baluster_positions_between_ends():
    path = [{"x": 0, "y": 0, "z": 0}, {"x": 1000, "y": 0, "z": 0}]
    bals = compute_baluster_positions(path, 120)
    assert len(bals) > 0
    for b in bals:
        assert b["x"] > 0
        assert b["x"] < 1000


def test_baluster_empty_for_short_path():
    path = [{"x": 0, "y": 0, "z": 0}, {"x": 50, "y": 0, "z": 0}]
    bals = compute_baluster_positions(path, 120)
    assert bals == []


# ── create_railing tool ────────────────────────────────────────────────────────

def test_create_railing_ok():
    ctx, store = make_ctx()
    raw = run(run_create_railing(ctx, json.dumps({
        "path": [{"x": 0, "y": 0, "z": 0}, {"x": 2400, "y": 0, "z": 0}],
        "height_mm": 1000,
    }).encode()))
    result = json.loads(raw)
    assert "error" not in result
    assert result["points"] == 2
    doc = json.loads(store["content"])
    assert doc["version"] == 1


def test_create_railing_rejects_single_point():
    ctx, _ = make_ctx()
    result = json.loads(run(run_create_railing(ctx, json.dumps({
        "path": [{"x": 0, "y": 0, "z": 0}],
    }).encode())))
    assert "error" in result


# ── set_baluster_spacing tool ──────────────────────────────────────────────────

def test_set_baluster_spacing():
    ctx, store = make_ctx()
    raw = run(run_create_railing(ctx, json.dumps({
        "path": [{"x": 0, "y": 0, "z": 0}, {"x": 2400, "y": 0, "z": 0}],
        "file_id": str(uuid.uuid4()),
    }).encode()))
    fid = json.loads(raw)["file_id"]

    upd = json.loads(run(run_set_baluster_spacing(ctx, json.dumps({
        "file_id": fid,
        "spacing_mm": 100,
    }).encode())))
    assert "error" not in upd
    doc = json.loads(store["content"])
    assert doc["balusters"]["spacing_mm"] == 100.0


# ── validate_railing tool ──────────────────────────────────────────────────────

def test_validate_railing_tool_ok():
    ctx, store = make_ctx()
    raw = run(run_create_railing(ctx, json.dumps({
        "path": [{"x": 0, "y": 0, "z": 0}, {"x": 2400, "y": 0, "z": 0}],
        "height_mm": 1000,
        "file_id": str(uuid.uuid4()),
    }).encode()))
    fid = json.loads(raw)["file_id"]

    val = json.loads(run(run_validate_railing(ctx, json.dumps({"file_id": fid}).encode())))
    assert val["ok"] is True
    assert val["errors"] == []


def test_validate_railing_tool_not_found():
    ctx, _ = make_ctx()
    result = json.loads(run(run_validate_railing(ctx, json.dumps({"file_id": str(uuid.uuid4())}).encode())))
    assert "error" in result


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
