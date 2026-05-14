"""test_view.py — pytest suite for view.py pure logic (no DB required)."""
import importlib.util
import sys
import types
import json

_TOOLS = "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-bim/src/kerf_bim/tools"


# ── minimal stubs ──────────────────────────────────────────────────────────────

_reg_stub = types.ModuleType("tools.registry")
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: json.dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: json.dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)
sys.modules.setdefault("tools.registry", _reg_stub)

_ctx_stub = types.ModuleType("tools.context")
_ctx_stub.ProjectCtx = type("ProjectCtx", (), {})
sys.modules.setdefault("tools.context", _ctx_stub)

_bim_stub = types.ModuleType("tools.bim")
_bim_stub.ensure_folders = None
_bim_stub.record_revision_for_file = None
_bim_stub.resolve_path = None
sys.modules.setdefault("tools.bim", _bim_stub)

# Load view.py via importlib
_spec = importlib.util.spec_from_file_location("tools.view", f"{_TOOLS}/view.py")
_mod = types.ModuleType("tools.view")
sys.modules["tools.view"] = _mod
_spec.loader.exec_module(_mod)

_default_view = _mod._default_view
_validate_view = _mod._validate_view
_eval_expr = _mod._eval_expr
run_view_filters = _mod.run_view_filters
VALID_KINDS = _mod.VALID_KINDS


# ── fixtures ───────────────────────────────────────────────────────────────────

BIM_DOC = {
    "elements": [
        {"id": "w1", "category": "wall",   "fire_rating": "2hr", "thickness": 200},
        {"id": "w2", "category": "wall",   "fire_rating": "1hr", "thickness": 150},
        {"id": "d1", "category": "door",   "fire_rating": "1hr", "width": 900},
        {"id": "c1", "category": "column", "height": 3000},
    ]
}


# ── _default_view ──────────────────────────────────────────────────────────────

class TestDefaultView:
    def test_plan_returns_correct_kind(self):
        v = _default_view("Level 1", "plan", "bim-1")
        assert v["kind"] == "plan"
        assert v["version"] == 1
        assert v["bim_file_id"] == "bim-1"

    def test_filters_and_annotations_empty(self):
        v = _default_view("Sec A", "section", "bim-2")
        assert v["filters"] == []
        assert v["annotations"] == []

    def test_crop_box_null_by_default(self):
        v = _default_view("3D", "3d", "bim-3")
        assert v["crop_box"] is None


# ── _validate_view ─────────────────────────────────────────────────────────────

class TestValidateView:
    def test_passes_valid_plan(self):
        v = _default_view("L1", "plan", "bim-1")
        assert _validate_view(v) == []

    def test_all_valid_kinds_pass(self):
        for kind in VALID_KINDS:
            v = _default_view("X", kind, "bim-x")
            assert _validate_view(v) == [], f"kind={kind} should pass"

    def test_rejects_bad_kind(self):
        v = _default_view("X", "ortho", "bim-1")
        errs = _validate_view(v)
        assert any("kind" in e for e in errs)

    def test_rejects_missing_bim_file_id(self):
        v = _default_view("X", "plan", "")
        errs = _validate_view(v)
        assert any("bim_file_id" in e for e in errs)

    def test_rejects_wrong_version(self):
        v = {**_default_view("X", "plan", "bim-1"), "version": 2}
        errs = _validate_view(v)
        assert any("version" in e for e in errs)


# ── _eval_expr ─────────────────────────────────────────────────────────────────

class TestEvalExpr:
    def test_equality_match(self):
        assert _eval_expr("category=='wall'", {"category": "wall"}) is True

    def test_equality_miss(self):
        assert _eval_expr("category=='wall'", {"category": "door"}) is False

    def test_numeric_gt(self):
        assert _eval_expr("thickness>150", {"thickness": 200}) is True
        assert _eval_expr("thickness>150", {"thickness": 150}) is False

    def test_and_both_true(self):
        el = {"category": "wall", "fire_rating": "2hr"}
        assert _eval_expr("category=='wall' AND fire_rating=='2hr'", el) is True

    def test_and_one_false(self):
        el = {"category": "wall", "fire_rating": "1hr"}
        assert _eval_expr("category=='wall' AND fire_rating=='2hr'", el) is False

    def test_or_one_true(self):
        el = {"category": "door"}
        assert _eval_expr("category=='wall' OR category=='door'", el) is True

    def test_missing_field_returns_false(self):
        assert _eval_expr("nonexistent=='x'", {}) is False


# ── run_view_filters ───────────────────────────────────────────────────────────

class TestRunViewFilters:
    def test_no_filters_returns_all(self):
        v = _default_view("L1", "plan", "bim-1")
        result = run_view_filters(v, BIM_DOC)
        assert len(result) == 4

    def test_filter_by_category(self):
        v = {**_default_view("L1", "plan", "bim-1"),
             "filters": [{"expr": "category=='wall'"}]}
        result = run_view_filters(v, BIM_DOC)
        assert len(result) == 2
        assert all(e["category"] == "wall" for e in result)

    def test_filter_with_and(self):
        v = {**_default_view("L1", "plan", "bim-1"),
             "filters": [{"expr": "category=='wall' AND fire_rating=='2hr'"}]}
        result = run_view_filters(v, BIM_DOC)
        assert len(result) == 1
        assert result[0]["id"] == "w1"

    def test_null_bim_returns_empty(self):
        v = _default_view("L1", "plan", "bim-1")
        assert run_view_filters(v, None) == []

    def test_string_filter_expression(self):
        # filters can also be plain strings
        v = {**_default_view("L1", "plan", "bim-1"),
             "filters": ["category=='column'"]}
        result = run_view_filters(v, BIM_DOC)
        assert len(result) == 1
        assert result[0]["id"] == "c1"
