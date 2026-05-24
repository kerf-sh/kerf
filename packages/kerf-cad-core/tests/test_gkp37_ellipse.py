"""
GK-P37 — Ellipse entity (center + semi-axes + angle, 5 DOF) — Python-side tests.

Tests verify:
  1. Ellipse entity with center/rx/ry/rotation round-trips through sketch_add_entity.
  2. DOF = 5 total (center point 2 + rx 1 + ry 1 + rotation 1).
  3. point_on_ellipse constraint removes 1 DOF.
  4. Fully-constrained ellipse: fixed center + 3 dimensional + point_on_ellipse + distance → DOF=0.
  5. Deleting the center point cascades to the ellipse entity.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import os
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class _FakeResolve:
    async def __call__(self, ctx, path):
        return {"exists": True}


class _FakePool:
    def __init__(self, initial: dict | None = None):
        self._store: dict[str, str] = {}
        if initial:
            for path, data in initial.items():
                self._store[path] = json.dumps(data)

    async def fetchrow(self, query, *args):
        path = args[1] if len(args) > 1 else None
        if path in self._store:
            return {"content": self._store[path]}
        return None

    async def execute(self, query, *args):
        content = args[0]
        path = args[2] if len(args) > 2 else None
        if path:
            self._store[path] = content


class _FakeCtx:
    def __init__(self, pool):
        self.pool = pool
        self.project_id = "test-project-id"


def _empty_sketch() -> dict:
    return {
        "version": 1,
        "plane": {"type": "base", "name": "XY"},
        "entities": [],
        "constraints": [],
        "visible_3d": [],
        "solved": {},
        "metadata": {},
    }


def _make_ctx_and_path(sketch_data: dict | None = None):
    path = "/test.sketch"
    pool = _FakePool({path: sketch_data or _empty_sketch()})
    ctx = _FakeCtx(pool)
    return ctx, path


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


_fake_resolve = _FakeResolve()

with mock.patch("kerf_api.tools.file_ops.resolve_path", new=_fake_resolve):
    import kerf_cad_core.sketch as sketch_mod


def _call(fn, ctx, args_dict: dict) -> dict:
    with mock.patch("kerf_api.tools.file_ops.resolve_path", new=_fake_resolve):
        raw = _run(fn(ctx, json.dumps(args_dict).encode()))
    return json.loads(raw)


def _read_sketch(ctx: _FakeCtx, path: str) -> dict:
    raw = _run(ctx.pool.fetchrow("", None, path))
    return json.loads(raw["content"])


def _validate(sketch_data: dict) -> dict:
    ctx, path = _make_ctx_and_path(sketch_data)
    with mock.patch("kerf_api.tools.file_ops.resolve_path", new=_fake_resolve):
        raw = _run(sketch_mod.run_sketch_validate(ctx, json.dumps({"file_path": path}).encode()))
    return json.loads(raw)


def test_gkp37_ellipse_entity_roundtrips():
    """Ellipse entity with center, rx, ry, rotation round-trips through sketch tools."""
    ctx, path = _make_ctx_and_path()
    _call(sketch_mod.run_sketch_add_entity, ctx, {
        "file_path": path,
        "entity": {"type": "point", "id": "el_center", "x": 0.0, "y": 0.0},
    })
    result = _call(sketch_mod.run_sketch_add_entity, ctx, {
        "file_path": path,
        "entity": {
            "type": "ellipse",
            "id": "el1",
            "center": "el_center",
            "rx": 8.0,
            "ry": 4.0,
            "rotation": math.pi / 6,
        },
    })
    assert result.get("ok") is True
    assert result.get("id") == "el1"

    sketch = _read_sketch(ctx, path)
    el = next(e for e in sketch["entities"] if e["id"] == "el1")
    assert el["type"] == "ellipse"
    assert el["center"] == "el_center"
    assert el["rx"] == pytest.approx(8.0)
    assert el["ry"] == pytest.approx(4.0)
    assert el["rotation"] == pytest.approx(math.pi / 6, rel=1e-6)


def test_gkp37_ellipse_has_5_dof():
    """Ellipse contributes 5 DOF: center(2) + rx(1) + ry(1) + rotation(1)."""
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "ec", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "el1", "type": "ellipse", "center": "ec", "rx": 5.0, "ry": 3.0, "rotation": 0.0},
    ]
    sketch["constraints"] = []
    result = _validate(sketch)
    errors = result.get("errors", [])
    over = [e for e in errors if e.get("kind") == "redundant_constraint"]
    assert len(over) == 0, "Ellipse with 5 DOF and no constraints should not be over-constrained"


def test_gkp37_point_on_ellipse_reduces_dof():
    """point_on_ellipse constraint reduces DOF by 1."""
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "ec",  "type": "point", "x": 0.0, "y": 0.0},
        {"id": "el1", "type": "ellipse", "center": "ec", "rx": 5.0, "ry": 3.0, "rotation": 0.0},
        {"id": "pt1", "type": "point", "x": 5.0, "y": 0.0},
    ]
    sketch["constraints"] = [
        {"id": "poe1", "type": "point_on_ellipse", "point": "pt1", "ellipse": "el1"},
    ]
    result = _validate(sketch)
    errors = result.get("errors", [])
    over = [e for e in errors if e.get("kind") == "redundant_constraint"]
    assert len(over) == 0, "6 DOF remaining should not be over-constrained"


def test_gkp37_ellipse_fully_constrained():
    """
    Fully-constrained ellipse: fixed center(-2) + semi_major(-1) + semi_minor(-1)
    + rotation(-1) + point_on_ellipse(-1) + distance_x(-1) = -7 constraints
    on 7 DOF → DOF = 0.
    """
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "ec",  "type": "point", "x": 0.0, "y": 0.0},
        {"id": "el1", "type": "ellipse", "center": "ec", "rx": 5.0, "ry": 3.0, "rotation": 0.0},
        {"id": "pt1", "type": "point", "x": 5.0, "y": 0.0},
    ]
    sketch["constraints"] = [
        {"id": "fix_ec", "type": "fixed",             "point": "ec"},
        {"id": "smaj",   "type": "ellipse_semi_major", "ellipse": "el1", "value": 5.0},
        {"id": "smin",   "type": "ellipse_semi_minor", "ellipse": "el1", "value": 3.0},
        {"id": "rot",    "type": "ellipse_rotation",   "ellipse": "el1", "value": 0.0},
        {"id": "poe1",   "type": "point_on_ellipse",   "point": "pt1", "ellipse": "el1"},
        {"id": "dx1",    "type": "distance_x",         "a": "ec", "b": "pt1", "value": 5.0},
    ]
    result = _validate(sketch)
    errors = result.get("errors", [])
    over = [e for e in errors if e.get("kind") == "redundant_constraint"]
    assert len(over) == 0, f"Should be fully constrained (DOF=0): {errors}"


def test_gkp37_delete_ellipse_cascades_from_center():
    """Deleting the center point of an ellipse cascades deletion to the ellipse entity."""
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "ec",  "type": "point", "x": 0.0, "y": 0.0},
        {"id": "el1", "type": "ellipse", "center": "ec", "rx": 4.0, "ry": 2.0, "rotation": 0.0},
    ]
    ctx, path = _make_ctx_and_path(sketch)
    result = _call(sketch_mod.run_sketch_delete_entity, ctx, {
        "file_path": path,
        "entity_id": "ec",
    })
    assert result.get("ok") is True
    deleted = result.get("deleted", [])
    assert "ec"  in deleted
    assert "el1" in deleted

    s2 = _read_sketch(ctx, path)
    ids = [e["id"] for e in s2["entities"]]
    assert "ec"  not in ids
    assert "el1" not in ids
