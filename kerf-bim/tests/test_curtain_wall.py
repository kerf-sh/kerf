"""test_curtain_wall.py — pytest suite for curtain wall LLM tools."""
import importlib.util
import sys
import types
import unittest

_ctx_stub = types.ModuleType("tools.context")
_ctx_stub.ProjectCtx = type("ProjectCtx", (), {})

_prev_context = sys.modules.get("tools.context")
sys.modules["tools.context"] = _ctx_stub

_reg_stub = types.ModuleType("tools.registry")
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: __import__("json").dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: __import__("json").dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)
_prev_registry = sys.modules.get("tools.registry")
sys.modules["tools.registry"] = _reg_stub

_spec = importlib.util.spec_from_file_location(
    "tools.curtain_wall", "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-bim/src/kerf_bim/tools/curtain_wall.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_default_curtain_wall = _mod._default_curtain_wall
_validate_curtain_wall_doc = _mod._validate_curtain_wall_doc
_set_division_scheme = _mod._set_division_scheme
_set_panel_type = _mod._set_panel_type
_set_mullion_type = _mod._set_mullion_type

if _prev_registry is not None:
    sys.modules["tools.registry"] = _prev_registry
else:
    sys.modules.pop("tools.registry", None)

if _prev_context is not None:
    sys.modules["tools.context"] = _prev_context
else:
    sys.modules.pop("tools.context", None)


class TestDefaultCurtainWall(unittest.TestCase):
    def test_version_is_1(self):
        cw = _default_curtain_wall("curve-123")
        self.assertEqual(cw["version"], 1)

    def test_height_mm_default_3000(self):
        cw = _default_curtain_wall("curve-123")
        self.assertEqual(cw["height_mm"], 3000)

    def test_u_divisions_default_count(self):
        cw = _default_curtain_wall("curve-123")
        self.assertEqual(cw["u_divisions"][0]["type"], "count")
        self.assertEqual(cw["u_divisions"][0]["value"], 4)

    def test_v_divisions_default_count(self):
        cw = _default_curtain_wall("curve-123")
        self.assertEqual(cw["v_divisions"][0]["type"], "count")
        self.assertEqual(cw["v_divisions"][0]["value"], 6)

    def test_panel_type_kind_glass(self):
        cw = _default_curtain_wall("curve-123")
        self.assertEqual(cw["panel_type"]["kind"], "glass")

    def test_mullion_type_square_50mm(self):
        cw = _default_curtain_wall("curve-123")
        self.assertEqual(cw["mullion_type"]["profile"], "square")
        self.assertEqual(cw["mullion_type"]["size_mm"], 50)


class TestValidateCurtainWallDoc(unittest.TestCase):
    def test_valid_doc_no_errors(self):
        cw = _default_curtain_wall("curve-123")
        errors = _validate_curtain_wall_doc(cw)
        self.assertEqual(errors, [])

    def test_invalid_version(self):
        cw = {**_default_curtain_wall("curve-123"), "version": 2}
        errors = _validate_curtain_wall_doc(cw)
        self.assertTrue(any("version" in e for e in errors))

    def test_invalid_height_mm(self):
        cw = {**_default_curtain_wall("curve-123"), "height_mm": -100}
        errors = _validate_curtain_wall_doc(cw)
        self.assertTrue(any("height_mm" in e for e in errors))

    def test_invalid_panel_type_kind(self):
        cw = {**_default_curtain_wall("curve-123"), "panel_type": {"kind": "invalid"}}
        errors = _validate_curtain_wall_doc(cw)
        self.assertTrue(any("panel_type" in e for e in errors))

    def test_invalid_mullion_profile(self):
        cw = {**_default_curtain_wall("curve-123"), "mullion_type": {"profile": "hex", "size_mm": 50}}
        errors = _validate_curtain_wall_doc(cw)
        self.assertTrue(any("mullion_type" in e for e in errors))

    def test_empty_u_divisions(self):
        cw = {**_default_curtain_wall("curve-123"), "u_divisions": []}
        errors = _validate_curtain_wall_doc(cw)
        self.assertTrue(any("u_divisions" in e for e in errors))

    def test_invalid_count_value(self):
        cw = {**_default_curtain_wall("curve-123"), "u_divisions": [{"type": "count", "value": 0}]}
        errors = _validate_curtain_wall_doc(cw)
        self.assertTrue(any("count" in e for e in errors))


class TestSetDivisionScheme(unittest.TestCase):
    def test_returns_new_doc(self):
        cw = _default_curtain_wall("curve-123")
        result = _set_division_scheme(cw, "u", [{"type": "count", "value": 8}])
        self.assertIsNot(result, cw)

    def test_updates_u_divisions(self):
        cw = _default_curtain_wall("curve-123")
        divs = [{"type": "spacing", "value": 500}]
        result = _set_division_scheme(cw, "u", divs)
        self.assertEqual(result["u_divisions"], divs)

    def test_updates_v_divisions(self):
        cw = _default_curtain_wall("curve-123")
        divs = [{"type": "count", "value": 10}]
        result = _set_division_scheme(cw, "v", divs)
        self.assertEqual(result["v_divisions"], divs)


class TestSetPanelType(unittest.TestCase):
    def test_returns_new_doc(self):
        cw = _default_curtain_wall("curve-123")
        result = _set_panel_type(cw, {"kind": "solid"})
        self.assertIsNot(result, cw)

    def test_updates_kind(self):
        cw = _default_curtain_wall("curve-123")
        result = _set_panel_type(cw, {"kind": "opening"})
        self.assertEqual(result["panel_type"]["kind"], "opening")

    def test_preserves_existing_fields(self):
        cw = _default_curtain_wall("curve-123")
        cw["panel_type"]["material_id"] = "mat-1"
        result = _set_panel_type(cw, {"color": "#FF0000"})
        self.assertEqual(result["panel_type"]["material_id"], "mat-1")


class TestSetMullionType(unittest.TestCase):
    def test_returns_new_doc(self):
        cw = _default_curtain_wall("curve-123")
        result = _set_mullion_type(cw, {"profile": "round", "size_mm": 75})
        self.assertIsNot(result, cw)

    def test_updates_profile(self):
        cw = _default_curtain_wall("curve-123")
        result = _set_mullion_type(cw, {"profile": "round", "size_mm": 75})
        self.assertEqual(result["mullion_type"]["profile"], "round")

    def test_updates_size_mm(self):
        cw = _default_curtain_wall("curve-123")
        result = _set_mullion_type(cw, {"profile": "square", "size_mm": 100})
        self.assertEqual(result["mullion_type"]["size_mm"], 100)


if __name__ == "__main__":
    unittest.main()
