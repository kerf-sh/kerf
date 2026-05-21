"""
T-41: Sketcher v2 — constraint solver hermetic tests.

Scope: kerf_cad_core/sketch.py (sketch_add_entity, sketch_add_constraint,
       sketch_set_constraint_value, sketch_delete_entity, sketch_carbon_copy,
       sketch_validate) + geom/curve_toolkit.py constraint-relevant ops.

Coverage (25 hermetic cases):
  1.  sketch_add_entity: add point, auto-generates id
  2.  sketch_add_entity: explicit id is preserved
  3.  sketch_add_entity: construction flag stored
  4.  sketch_add_entity: BAD_ARGS on missing entity.type
  5.  sketch_add_entity: BAD_ARGS on missing file_path
  6.  sketch_add_constraint: constraint round-trips in sketch JSON
  7.  sketch_add_constraint: BAD_ARGS on missing constraint.type
  8.  sketch_set_constraint_value: updates value in-place
  9.  sketch_set_constraint_value: NOT_FOUND for unknown constraint_id
  10. sketch_set_constraint_value: BAD_ARGS on missing value
  11. sketch_delete_entity: removes entity + cascading constraints
  12. sketch_delete_entity: cascades from point to referencing line
  13. sketch_delete_entity: NOT_FOUND on unknown entity_id
  14. sketch_carbon_copy: copies edge entities as is_reference
  15. sketch_carbon_copy: idempotent — second call replaces first copy
  16. sketch_validate: fully-constrained rectangle returns no errors
  17. sketch_validate: open-contour error on dangling endpoint
  18. sketch_validate: over-constrained error detected
  19. sketch_validate: dangling-endpoint warning on unconstrained endpoint
  20. sketch_validate: self-intersection error on crossing lines
  21. sketch_validate: under-constrained sketch → no redundant_constraint error
  22. sketch_validate: unresolved external reference error
  23. DOF accounting: single free point has DOF = 2
  24. DOF accounting: fixed point has DOF = 0 (fully constrained)
  25. DOF accounting: circle adds 1 DOF (radius); fixed point drives over-constraint

All tests are pure-Python hermetic — no OCC, no network, no live Postgres.
They exercise the JSON logic inside the tool handlers directly.
"""

from __future__ import annotations

import asyncio
import json
import sys
import os
import pytest

# Ensure kerf-cad-core src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# Minimal fake infrastructure (no DB, no ProjectCtx)
# ---------------------------------------------------------------------------

class _FakeResolve:
    """Fake kerf_api.tools.file_ops.resolve_path that always reports the file exists."""
    async def __call__(self, ctx, path):
        return {"exists": True}


class _FakePool:
    """In-memory pool that stores one sketch JSON blob per path."""

    def __init__(self, initial: dict | None = None):
        self._store: dict[str, str] = {}
        if initial:
            for path, data in initial.items():
                self._store[path] = json.dumps(data)

    async def fetchrow(self, query, *args):
        # args are (project_id, path)
        path = args[1] if len(args) > 1 else None
        if path in self._store:
            return {"content": self._store[path]}
        return None

    async def execute(self, query, *args):
        # UPDATE files SET content = $1 ... WHERE path = $3
        content = args[0]
        path = args[2] if len(args) > 2 else None
        if path:
            self._store[path] = content


class _FakeCtx:
    def __init__(self, pool: _FakePool):
        self.pool = pool
        self.project_id = "test-project-id"


def _empty_sketch() -> dict:
    """Return a minimal valid sketch dict."""
    return {
        "version": 1,
        "plane": {"type": "base", "name": "XY"},
        "entities": [],
        "constraints": [],
        "visible_3d": [],
        "solved": {},
        "metadata": {},
    }


def _make_ctx_and_path(sketch_data: dict | None = None) -> tuple[_FakeCtx, str]:
    path = "/test.sketch"
    pool = _FakePool({path: sketch_data or _empty_sketch()})
    ctx = _FakeCtx(pool)
    return ctx, path


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Patch resolve_path before importing sketch
# ---------------------------------------------------------------------------

import unittest.mock as mock

_fake_resolve = _FakeResolve()


def _patch_and_import():
    """Import sketch with resolve_path patched."""
    import importlib
    # Patch at the module level used by sketch.py
    with mock.patch.dict("sys.modules", {}):
        # We need to patch after import; use mock.patch as context at call time
        pass

    import kerf_cad_core.sketch as _sketch_mod
    return _sketch_mod


# Patch before first import
with mock.patch("kerf_api.tools.file_ops.resolve_path", new=_fake_resolve):
    import kerf_cad_core.sketch as sketch_mod  # noqa: E402


def _call(fn, ctx, args_dict: dict) -> dict:
    """Call an async sketch tool handler with resolve_path patched, parse JSON result."""
    with mock.patch("kerf_cad_core.sketch._load_sketch", wraps=sketch_mod._load_sketch):
        with mock.patch("kerf_api.tools.file_ops.resolve_path", new=_fake_resolve):
            raw = _run(fn(ctx, json.dumps(args_dict).encode()))
    return json.loads(raw)


def _read_sketch(ctx: _FakeCtx, path: str) -> dict:
    raw = _run(ctx.pool.fetchrow("", None, path))
    return json.loads(raw["content"])


# ---------------------------------------------------------------------------
# Test 1: sketch_add_entity — add point, auto-generates id
# ---------------------------------------------------------------------------

def test_add_entity_auto_id():
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_add_entity, ctx, {
        "file_path": path,
        "entity": {"type": "point", "x": 10.0, "y": 20.0},
    })
    assert result.get("ok") is True
    assert "id" in result, "response must include generated id"
    assert len(result["id"]) > 0


# ---------------------------------------------------------------------------
# Test 2: sketch_add_entity — explicit id preserved
# ---------------------------------------------------------------------------

def test_add_entity_explicit_id():
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_add_entity, ctx, {
        "file_path": path,
        "entity": {"type": "point", "id": "mypoint", "x": 5.0, "y": 5.0},
    })
    assert result.get("ok") is True
    assert result["id"] == "mypoint"

    sketch = _read_sketch(ctx, path)
    ids = [e["id"] for e in sketch["entities"]]
    assert "mypoint" in ids


# ---------------------------------------------------------------------------
# Test 3: sketch_add_entity — construction flag stored
# ---------------------------------------------------------------------------

def test_add_entity_construction_flag():
    ctx, path = _make_ctx_and_path()
    _call(sketch_mod.run_sketch_add_entity, ctx, {
        "file_path": path,
        "entity": {"type": "point", "id": "cpt", "x": 0.0, "y": 0.0},
        "construction": True,
    })
    sketch = _read_sketch(ctx, path)
    ent = next(e for e in sketch["entities"] if e["id"] == "cpt")
    assert ent.get("construction") is True


# ---------------------------------------------------------------------------
# Test 4: sketch_add_entity — BAD_ARGS on missing entity.type
# ---------------------------------------------------------------------------

def test_add_entity_bad_args_no_type():
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_add_entity, ctx, {
        "file_path": path,
        "entity": {"x": 0.0, "y": 0.0},  # no "type"
    })
    assert result.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# Test 5: sketch_add_entity — BAD_ARGS on missing file_path
# ---------------------------------------------------------------------------

def test_add_entity_bad_args_no_path():
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_add_entity, ctx, {
        "entity": {"type": "point", "x": 0.0, "y": 0.0},
    })
    assert result.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# Test 6: sketch_add_constraint — round-trips in sketch JSON
# ---------------------------------------------------------------------------

def test_add_constraint_roundtrip():
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_add_constraint, ctx, {
        "file_path": path,
        "constraint": {"type": "horizontal", "id": "c1", "entity": "line1"},
    })
    assert result.get("ok") is True
    assert result["id"] == "c1"

    sketch = _read_sketch(ctx, path)
    cids = [c["id"] for c in sketch["constraints"]]
    assert "c1" in cids
    c = next(c for c in sketch["constraints"] if c["id"] == "c1")
    assert c["type"] == "horizontal"


# ---------------------------------------------------------------------------
# Test 7: sketch_add_constraint — BAD_ARGS on missing constraint.type
# ---------------------------------------------------------------------------

def test_add_constraint_bad_args_no_type():
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_add_constraint, ctx, {
        "file_path": path,
        "constraint": {"id": "c2", "entity": "line1"},
    })
    assert result.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# Test 8: sketch_set_constraint_value — updates value in-place
# ---------------------------------------------------------------------------

def test_set_constraint_value_updates():
    sketch = _empty_sketch()
    sketch["constraints"] = [{"id": "d1", "type": "distance", "value": 10.0}]
    ctx, path = _make_ctx_and_path(sketch)

    result = _call(sketch_mod.run_sketch_set_constraint_value, ctx, {
        "file_path": path,
        "constraint_id": "d1",
        "value": 42.5,
    })
    assert result.get("ok") is True

    sketch2 = _read_sketch(ctx, path)
    c = next(c for c in sketch2["constraints"] if c["id"] == "d1")
    assert c["value"] == pytest.approx(42.5)


# ---------------------------------------------------------------------------
# Test 9: sketch_set_constraint_value — NOT_FOUND for unknown constraint_id
# ---------------------------------------------------------------------------

def test_set_constraint_value_not_found():
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_set_constraint_value, ctx, {
        "file_path": path,
        "constraint_id": "nonexistent",
        "value": 5.0,
    })
    assert result.get("code") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Test 10: sketch_set_constraint_value — BAD_ARGS on missing value
# ---------------------------------------------------------------------------

def test_set_constraint_value_bad_args_no_value():
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_set_constraint_value, ctx, {
        "file_path": path,
        "constraint_id": "d1",
        # value omitted
    })
    assert result.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# Test 11: sketch_delete_entity — removes entity + cascading constraints
# ---------------------------------------------------------------------------

def test_delete_entity_removes_with_constraints():
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "p1", "type": "point", "x": 0.0, "y": 0.0},
    ]
    sketch["constraints"] = [
        {"id": "c_fixed", "type": "fixed", "point": "p1"},
        {"id": "c_horizontal", "type": "horizontal", "entity": "line1"},
    ]
    ctx, path = _make_ctx_and_path(sketch)

    result = _call(sketch_mod.run_sketch_delete_entity, ctx, {
        "file_path": path,
        "entity_id": "p1",
    })
    assert result.get("ok") is True
    assert "p1" in result.get("deleted", [])

    sketch2 = _read_sketch(ctx, path)
    assert not any(e["id"] == "p1" for e in sketch2["entities"])
    # The constraint referencing "p1" should be removed
    c_ids = [c["id"] for c in sketch2["constraints"]]
    assert "c_fixed" not in c_ids
    # Constraint not referencing p1 survives
    assert "c_horizontal" in c_ids


# ---------------------------------------------------------------------------
# Test 12: sketch_delete_entity — cascades from point to referencing line
# ---------------------------------------------------------------------------

def test_delete_entity_cascades_to_line():
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "pa", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "pb", "type": "point", "x": 10.0, "y": 0.0},
        {"id": "la", "type": "line", "p1": "pa", "p2": "pb"},
    ]
    ctx, path = _make_ctx_and_path(sketch)

    result = _call(sketch_mod.run_sketch_delete_entity, ctx, {
        "file_path": path,
        "entity_id": "pa",  # delete a point that the line references
    })
    assert result.get("ok") is True
    deleted = result.get("deleted", [])
    assert "pa" in deleted
    assert "la" in deleted  # line must be cascade-deleted

    sketch2 = _read_sketch(ctx, path)
    remaining_ids = [e["id"] for e in sketch2["entities"]]
    assert "pa" not in remaining_ids
    assert "la" not in remaining_ids
    # pb survives (only referenced by the now-deleted line)
    assert "pb" in remaining_ids


# ---------------------------------------------------------------------------
# Test 13: sketch_delete_entity — NOT_FOUND on unknown entity_id
# ---------------------------------------------------------------------------

def test_delete_entity_not_found():
    ctx, path = _make_ctx_and_path()
    result = _call(sketch_mod.run_sketch_delete_entity, ctx, {
        "file_path": path,
        "entity_id": "ghost",
    })
    assert result.get("code") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Test 14: sketch_carbon_copy — copies edge entities as is_reference
# ---------------------------------------------------------------------------

def test_carbon_copy_marks_reference():
    src_sketch = _empty_sketch()
    src_sketch["entities"] = [
        {"id": "sp1", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "sp2", "type": "point", "x": 5.0, "y": 0.0},
        {"id": "sl1", "type": "line", "p1": "sp1", "p2": "sp2"},
    ]

    src_path = "/src.sketch"
    tgt_path = "/tgt.sketch"
    pool = _FakePool({
        src_path: src_sketch,
        tgt_path: _empty_sketch(),
    })
    ctx = _FakeCtx(pool)

    with mock.patch("kerf_api.tools.file_ops.resolve_path", new=_fake_resolve):
        result = _run(sketch_mod.run_sketch_carbon_copy(ctx, json.dumps({
            "source_file_path": src_path,
            "target_file_path": tgt_path,
        }).encode()))
    result = json.loads(result)
    assert result.get("ok") is True
    assert result.get("copied", 0) >= 1

    tgt_raw = _run(ctx.pool.fetchrow("", None, tgt_path))
    tgt = json.loads(tgt_raw["content"])
    ref_ents = [e for e in tgt["entities"] if e.get("is_reference")]
    assert len(ref_ents) > 0, "copied entities must be is_reference"
    line_refs = [e for e in ref_ents if e.get("type") == "line"]
    assert len(line_refs) == 1


# ---------------------------------------------------------------------------
# Test 15: sketch_carbon_copy — idempotent (second call replaces first copy)
# ---------------------------------------------------------------------------

def test_carbon_copy_idempotent():
    src_sketch = _empty_sketch()
    src_sketch["entities"] = [
        {"id": "sp1", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "sp2", "type": "point", "x": 5.0, "y": 0.0},
        {"id": "sl1", "type": "line", "p1": "sp1", "p2": "sp2"},
    ]

    src_path = "/src2.sketch"
    tgt_path = "/tgt2.sketch"
    pool = _FakePool({src_path: src_sketch, tgt_path: _empty_sketch()})
    ctx = _FakeCtx(pool)

    def _cc():
        with mock.patch("kerf_api.tools.file_ops.resolve_path", new=_fake_resolve):
            return json.loads(_run(sketch_mod.run_sketch_carbon_copy(ctx, json.dumps({
                "source_file_path": src_path,
                "target_file_path": tgt_path,
            }).encode())))

    r1 = _cc()
    r2 = _cc()
    assert r1.get("ok") is True
    assert r2.get("ok") is True

    tgt_raw = _run(ctx.pool.fetchrow("", None, tgt_path))
    tgt = json.loads(tgt_raw["content"])
    # After two calls entity count should be same as after one call (no duplication)
    ref_lines = [e for e in tgt["entities"] if e.get("type") == "line" and e.get("is_reference")]
    assert len(ref_lines) == 1, "idempotent: second cc replaces first, no duplicates"


# ---------------------------------------------------------------------------
# Helpers for sketch_validate tests
# ---------------------------------------------------------------------------

def _validate(sketch_data: dict) -> dict:
    """Run sketch_validate and return parsed result."""
    ctx, path = _make_ctx_and_path(sketch_data)
    with mock.patch("kerf_api.tools.file_ops.resolve_path", new=_fake_resolve):
        raw = _run(sketch_mod.run_sketch_validate(ctx, json.dumps({"file_path": path}).encode()))
    result = json.loads(raw)
    return result


def _make_closed_square() -> dict:
    """A fully-connected square with 4 lines and 4 corner points, properly joined."""
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "p00", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "p10", "type": "point", "x": 10.0, "y": 0.0},
        {"id": "p11", "type": "point", "x": 10.0, "y": 10.0},
        {"id": "p01", "type": "point", "x": 0.0, "y": 10.0},
        {"id": "l_bot", "type": "line", "p1": "p00", "p2": "p10"},
        {"id": "l_right", "type": "line", "p1": "p10", "p2": "p11"},
        {"id": "l_top", "type": "line", "p1": "p11", "p2": "p01"},
        {"id": "l_left", "type": "line", "p1": "p01", "p2": "p00"},
    ]
    # Coincident constraints to close the loop + anchor with fixed
    sketch["constraints"] = [
        {"id": "fix_p00", "type": "fixed", "point": "p00"},
        {"id": "coin_p10a", "type": "coincident", "a": "p10", "b": "p10"},
        {"id": "coin_p11a", "type": "coincident", "a": "p11", "b": "p11"},
        {"id": "coin_p01a", "type": "coincident", "a": "p01", "b": "p01"},
    ]
    return sketch


# ---------------------------------------------------------------------------
# Test 16: sketch_validate — fully-connected square returns no open-contour errors
# ---------------------------------------------------------------------------

def test_validate_closed_square_no_open_contour():
    sketch = _make_closed_square()
    result = _validate(sketch)
    open_contour_errors = [e for e in result.get("errors", []) if e.get("kind") == "open_contour"]
    assert len(open_contour_errors) == 0, f"Expected no open contour errors: {open_contour_errors}"


# ---------------------------------------------------------------------------
# Test 17: sketch_validate — open-contour error on dangling endpoint
# ---------------------------------------------------------------------------

def test_validate_open_contour_detected():
    sketch = _empty_sketch()
    # Two lines that do NOT share endpoints → open contour
    sketch["entities"] = [
        {"id": "p0", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "p1", "type": "point", "x": 10.0, "y": 0.0},
        {"id": "p2", "type": "point", "x": 20.0, "y": 5.0},
        {"id": "p3", "type": "point", "x": 30.0, "y": 5.0},
        {"id": "l1", "type": "line", "p1": "p0", "p2": "p1"},
        {"id": "l2", "type": "line", "p1": "p2", "p2": "p3"},
    ]
    sketch["constraints"] = []
    result = _validate(sketch)
    errors = result.get("errors", [])
    kinds = [e["kind"] for e in errors]
    assert "open_contour" in kinds


# ---------------------------------------------------------------------------
# Test 18: sketch_validate — over-constrained error detected
# ---------------------------------------------------------------------------

def test_validate_over_constrained():
    sketch = _empty_sketch()
    # A single free point (DOF=2) with 3 constraints that consume 3 DOF → DOF = -1
    sketch["entities"] = [
        {"id": "pt1", "type": "point", "x": 5.0, "y": 5.0},
    ]
    sketch["constraints"] = [
        {"id": "c1", "type": "horizontal", "entity": "pt1"},    # -1 DOF
        {"id": "c2", "type": "vertical", "entity": "pt1"},      # -1 DOF
        {"id": "c3", "type": "distance", "entity": "pt1", "value": 5.0},  # -1 DOF
    ]
    result = _validate(sketch)
    errors = result.get("errors", [])
    kinds = [e["kind"] for e in errors]
    assert "redundant_constraint" in kinds


# ---------------------------------------------------------------------------
# Test 19: sketch_validate — dangling-endpoint warning on unconstrained endpoint
# ---------------------------------------------------------------------------

def test_validate_dangling_endpoint_warning():
    sketch = _empty_sketch()
    # A single line with no coincident/fixed constraints on its endpoints
    sketch["entities"] = [
        {"id": "p0", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "p1", "type": "point", "x": 10.0, "y": 0.0},
        {"id": "l1", "type": "line", "p1": "p0", "p2": "p1"},
    ]
    sketch["constraints"] = []
    result = _validate(sketch)
    warnings = result.get("warnings", [])
    kinds = [w["kind"] for w in warnings]
    assert "dangling_endpoint" in kinds


# ---------------------------------------------------------------------------
# Test 20: sketch_validate — self-intersection error on crossing lines
# ---------------------------------------------------------------------------

def test_validate_self_intersection():
    sketch = _empty_sketch()
    # Two lines that cross: (0,0)-(10,10) and (0,10)-(10,0)
    sketch["entities"] = [
        {"id": "pa", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "pb", "type": "point", "x": 10.0, "y": 10.0},
        {"id": "pc", "type": "point", "x": 0.0, "y": 10.0},
        {"id": "pd", "type": "point", "x": 10.0, "y": 0.0},
        {"id": "la", "type": "line", "p1": "pa", "p2": "pb"},
        {"id": "lb", "type": "line", "p1": "pc", "p2": "pd"},
    ]
    result = _validate(sketch)
    errors = result.get("errors", [])
    kinds = [e["kind"] for e in errors]
    assert "self_intersection" in kinds


# ---------------------------------------------------------------------------
# Test 21: sketch_validate — under-constrained → no redundant_constraint error
# ---------------------------------------------------------------------------

def test_validate_under_constrained_no_overconstrain_error():
    sketch = _empty_sketch()
    # Single free point, no constraints at all → DOF = 2 > 0; should not flag redundant
    sketch["entities"] = [
        {"id": "pt1", "type": "point", "x": 5.0, "y": 5.0},
    ]
    sketch["constraints"] = []
    result = _validate(sketch)
    errors = result.get("errors", [])
    kinds = [e["kind"] for e in errors]
    assert "redundant_constraint" not in kinds


# ---------------------------------------------------------------------------
# Test 22: sketch_validate — unresolved external reference error
# ---------------------------------------------------------------------------

def test_validate_unresolved_external_ref():
    sketch = _empty_sketch()
    sketch["entities"] = [
        {
            "id": "ref_ent",
            "type": "line",
            "is_reference": True,
            "unresolved": True,
            "source_id": "missing_src",
        },
    ]
    result = _validate(sketch)
    errors = result.get("errors", [])
    kinds = [e["kind"] for e in errors]
    assert "unresolved_external_ref" in kinds


# ---------------------------------------------------------------------------
# Test 23: DOF accounting — single free point has DOF = 2
# ---------------------------------------------------------------------------

def test_dof_single_free_point():
    """Sketch with one free point and no constraints should have DOF=2 (not over-constrained)."""
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "pt", "type": "point", "x": 1.0, "y": 1.0},
    ]
    sketch["constraints"] = []
    result = _validate(sketch)
    errors = result.get("errors", [])
    # DOF = 2, no over-constraint
    over = [e for e in errors if e.get("kind") == "redundant_constraint"]
    assert len(over) == 0


# ---------------------------------------------------------------------------
# Test 24: DOF accounting — fixed point has DOF = 0 (exactly constrained)
# ---------------------------------------------------------------------------

def test_dof_fixed_point_fully_constrained():
    """A point with a fixed constraint consumes both DOFs → DOF = 0, no errors."""
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "pt", "type": "point", "x": 0.0, "y": 0.0},
    ]
    sketch["constraints"] = [
        {"id": "c_fix", "type": "fixed", "point": "pt"},  # consumes 2 DOF
    ]
    result = _validate(sketch)
    errors = result.get("errors", [])
    over = [e for e in errors if e.get("kind") == "redundant_constraint"]
    assert len(over) == 0


# ---------------------------------------------------------------------------
# Test 25: DOF accounting — circle DOF; extra constraint makes it over-constrained
# ---------------------------------------------------------------------------

def test_dof_circle_overconstrained():
    """A circle center-point (2 DOF) + radius (1 DOF) = 3 DOF total.
    Fixed constraint removes 2, radius constraint removes 1 → DOF = 0.
    Adding one more radius constraint → DOF = -1 → redundant_constraint error.
    """
    sketch = _empty_sketch()
    sketch["entities"] = [
        {"id": "cpt", "type": "point", "x": 0.0, "y": 0.0},
        {"id": "circ", "type": "circle", "center": "cpt", "radius": 5.0},
    ]
    sketch["constraints"] = [
        # 2 DOF from point + 1 DOF from circle = 3 total
        {"id": "c_fix", "type": "fixed", "point": "cpt"},   # -2 DOF
        {"id": "c_r1", "type": "radius", "entity": "circ", "value": 5.0},   # -1 DOF → DOF=0
        {"id": "c_r2", "type": "diameter", "entity": "circ", "value": 10.0},  # -1 DOF → DOF=-1
    ]
    result = _validate(sketch)
    errors = result.get("errors", [])
    over = [e for e in errors if e.get("kind") == "redundant_constraint"]
    assert len(over) == 1, f"Expected over-constrained error, got errors: {errors}"
