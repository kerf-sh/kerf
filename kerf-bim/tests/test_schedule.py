"""test_schedule.py — pytest suite for the schedule DSL and LLM tool."""
import importlib.util
import sys
import types

_TOOLS = "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-bim/src/kerf_bim/tools"

_spec = importlib.util.spec_from_file_location(
    "tools.schedule", f"{_TOOLS}/schedule.py"
)
_mod = types.ModuleType("tools.schedule")
sys.modules["tools.schedule"] = _mod

_reg_stub = types.ModuleType("tools.registry")
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: __import__("json").dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: __import__("json").dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)
_prev_reg = sys.modules.get("tools.registry")
sys.modules["tools.registry"] = _reg_stub

_ctx_stub = types.ModuleType("tools.context")
_ctx_stub.ProjectCtx = type("ProjectCtx", (), {})
_prev_ctx = sys.modules.get("tools.context")
sys.modules["tools.context"] = _ctx_stub

_spec.loader.exec_module(_mod)

# Restore real modules so subsequent test files see the proper implementations.
if _prev_reg is not None:
    sys.modules["tools.registry"] = _prev_reg
else:
    del sys.modules["tools.registry"]
if _prev_ctx is not None:
    sys.modules["tools.context"] = _prev_ctx
else:
    del sys.modules["tools.context"]
_run_schedule_py = _mod.run_schedule_py


BIM_DOC = {
    "elements": [
        {"type": "Wall", "name": "W1", "height": 3000, "thickness": 200, "material": "Concrete"},
        {"type": "Wall", "name": "W2", "height": 3000, "thickness": 150, "material": "Brick"},
        {"type": "Wall", "name": "W3", "height": 4000, "thickness": 200, "material": "Concrete"},
        {"type": "Door", "name": "D1", "width": 900, "height": 2100},
        {"type": "Door", "name": "D2", "width": 800, "height": 2100},
    ],
}


class TestRunSchedule:
    def test_empty_for_null_inputs(self):
        r = _run_schedule_py(None, None)
        assert r["columns"] == []
        assert r["rows"] == []

    def test_filters_by_category(self):
        sched = {
            "version": 1,
            "name": "Walls",
            "target_category": "Wall",
            "filters": [],
            "columns": [{"field": "name"}],
        }
        r = _run_schedule_py(sched, BIM_DOC)
        assert len(r["rows"]) == 3

    def test_filter_eq(self):
        sched = {
            "version": 1, "name": "Test", "target_category": "Wall",
            "filters": [{"field": "material", "op": "eq", "value": "Brick"}],
            "columns": [{"field": "name"}],
        }
        r = _run_schedule_py(sched, BIM_DOC)
        assert len(r["rows"]) == 1
        assert r["rows"][0][0]["name"] == "W2"

    def test_filter_gt(self):
        sched = {
            "version": 1, "name": "Tall", "target_category": "Wall",
            "filters": [{"field": "height", "op": "gt", "value": 3000}],
            "columns": [{"field": "name"}, {"field": "height"}],
        }
        r = _run_schedule_py(sched, BIM_DOC)
        assert len(r["rows"]) == 1
        assert r["rows"][0][0]["height"] == 4000

    def test_filter_in(self):
        sched = {
            "version": 1, "name": "Test", "target_category": "Wall",
            "filters": [{"field": "thickness", "op": "in", "value": [150, 200]}],
            "columns": [{"field": "name"}],
        }
        r = _run_schedule_py(sched, BIM_DOC)
        assert len(r["rows"]) == 3

    def test_filter_ne(self):
        sched = {
            "version": 1, "name": "Test", "target_category": "Wall",
            "filters": [{"field": "material", "op": "ne", "value": "Concrete"}],
            "columns": [{"field": "name"}],
        }
        r = _run_schedule_py(sched, BIM_DOC)
        assert len(r["rows"]) == 1
        assert r["rows"][0][0]["name"] == "W2"

    def test_filter_contains(self):
        sched = {
            "version": 1, "name": "Test", "target_category": "Wall",
            "filters": [{"field": "material", "op": "contains", "value": "Brick"}],
            "columns": [{"field": "name"}],
        }
        r = _run_schedule_py(sched, BIM_DOC)
        assert len(r["rows"]) == 1
        assert r["rows"][0][0]["name"] == "W2"

    def test_sort_ascending(self):
        sched = {
            "version": 1, "name": "Sorted", "target_category": "Wall",
            "filters": [],
            "columns": [{"field": "name"}, {"field": "thickness"}],
            "sort_by": "thickness",
        }
        r = _run_schedule_py(sched, BIM_DOC)
        thicknesses = [row[0]["thickness"] for row in r["rows"]]
        assert thicknesses == [150, 200, 200]

    def test_sort_descending(self):
        sched = {
            "version": 1, "name": "Sorted", "target_category": "Wall",
            "filters": [],
            "columns": [{"field": "name"}, {"field": "thickness"}],
            "sort_by": "thickness:desc",
        }
        r = _run_schedule_py(sched, BIM_DOC)
        thicknesses = [row[0]["thickness"] for row in r["rows"]]
        assert thicknesses == [200, 200, 150]

    def test_group_by(self):
        sched = {
            "version": 1, "name": "Grouped", "target_category": "Wall",
            "filters": [],
            "columns": [{"field": "name"}, {"field": "material"}],
            "group_by": "material",
        }
        r = _run_schedule_py(sched, BIM_DOC)
        assert len(r["rows"]) == 2

    def test_missing_field_returns_null(self):
        bim = {"elements": [{"type": "Wall", "name": "W1"}]}
        sched = {
            "version": 1, "name": "Test", "target_category": "Wall",
            "filters": [],
            "columns": [{"field": "height"}],
        }
        r = _run_schedule_py(sched, bim)
        assert r["rows"][0][0]["height"] is None

    def test_nested_field_path(self):
        bim = {"elements": [{"type": "Wall", "name": "W1", "geometry": {"area": 15}}]}
        sched = {
            "version": 1, "name": "Test", "target_category": "Wall",
            "filters": [],
            "columns": [{"field": "geometry.area"}],
        }
        r = _run_schedule_py(sched, bim)
        assert r["rows"][0][0]["geometry.area"] == 15

    def test_column_label_default(self):
        sched = {
            "version": 1, "name": "Test", "target_category": "Wall",
            "filters": [],
            "columns": [{"field": "name"}],
        }
        r = _run_schedule_py(sched, BIM_DOC)
        assert r["columns"][0]["label"] == "name"

    def test_column_label_custom(self):
        sched = {
            "version": 1, "name": "Test", "target_category": "Wall",
            "filters": [],
            "columns": [{"field": "name", "label": "Wall Name"}],
        }
        r = _run_schedule_py(sched, BIM_DOC)
        assert r["columns"][0]["label"] == "Wall Name"


if __name__ == "__main__":
    import unittest
    unittest.main()