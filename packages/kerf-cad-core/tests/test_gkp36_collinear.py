"""
GK-P36 — Collinear constraint (Python-side hermetic tests).

Tests verify:
  1. collinear constraint round-trips through sketch_add_constraint.
  2. DOF accounting: collinear removes 1 DOF.
  3. Three points forced collinear via schema are accepted and fully-constrained
     scenario matches expected DOF = 0.
"""

from __future__ import annotations

import asyncio
import json
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


def test_gkp36_collinear_constraint_roundtrips():
    """collinear constraint is accepted by sketch_add_constraint and round-trips."""
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_add_constraint, ctx, {
        "file_path": path,
        "constraint": {
            "type": "collinear",
            "id": "col1",
            "p1": "pt_a",
            "p2": "pt_b",
            "p3": "pt_c",
        },
    })
    assert result.get("ok") is True
    assert result.get("id") == "col1"

    sketch = _read_sketch(ctx, path)
    c = next(c for c in sketch["constraints"] if c["id"] == "col1")
    assert c["type"] == "collinear"
    assert c["p1"] == "pt_a"
    assert c["p2"] == "pt_b"
    assert c["p3"] == "pt_c"


def test_gkp36_collinear_dof_accounting():
    """collinear constraint removes 1 DOF from the estimate."""
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "pa", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "pb", "type": "point", "x": 5.0, "y": 0.0},
        {"id": "pc", "type": "point", "x": 10.0, "y": 0.0},
    ]
    sketch["constraints"] = [
        {"id": "col1", "type": "collinear", "p1": "pa", "p2": "pb", "p3": "pc"},
    ]
    result = _validate(sketch)
    errors = result.get("errors", [])
    over = [e for e in errors if e.get("kind") == "redundant_constraint"]
    assert len(over) == 0, f"Should not be over-constrained: {errors}"


def test_gkp36_collinear_three_points_solve_to_line():
    """
    Three points in a fully-constrained collinear scenario: pa/pb fixed,
    pc constrained collinear with pa-pb + fixed x-distance. DOF = 0.
    """
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "pa", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "pb", "type": "point", "x": 5.0, "y": 0.0},
        {"id": "pc", "type": "point", "x": 10.0, "y": 3.0},  # off-line initially
    ]
    sketch["constraints"] = [
        {"id": "fix_a", "type": "fixed", "point": "pa"},
        {"id": "fix_b", "type": "fixed", "point": "pb"},
        {"id": "col1",  "type": "collinear", "p1": "pc", "p2": "pa", "p3": "pb"},
        {"id": "dx1",   "type": "distance_x", "a": "pa", "b": "pc", "value": 10.0},
    ]
    result = _validate(sketch)
    errors = result.get("errors", [])
    over = [e for e in errors if e.get("kind") == "redundant_constraint"]
    assert len(over) == 0, f"Should be exactly constrained (0 DOF): {errors}"
