"""test_draft.py — pytest suite for the Draft workbench engine and LLM tools."""
import importlib.util, sys, types, unittest

_spec = importlib.util.spec_from_file_location("tools.draft", "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-imports/src/kerf_imports/tools/draft.py")
_mod = types.ModuleType("tools.draft")

_reg_stub = types.ModuleType("tools.registry")
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: __import__("json").dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: __import__("json").dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)
_prev = sys.modules.get("tools.registry")
sys.modules["tools.registry"] = _reg_stub
_spec.loader.exec_module(_mod)

_default_draft = _mod._default_draft
_validate_draft = _mod._validate_draft
_add_entity = _mod._add_entity
_remove_entity = _mod._remove_entity
_move_entity = _mod._move_entity
_offset_entity = _mod._offset_entity
_trim_entity = _mod._trim_entity
_fillet_corner = _mod._fillet_corner
_pattern_linear = _mod._pattern_linear
_pattern_polar = _mod._pattern_polar
_export_dxf = _mod._export_dxf

if _prev is not None:
    sys.modules["tools.registry"] = _prev
else:
    del sys.modules["tools.registry"]


class TestDefaultDraft(unittest.TestCase):
    def test_returns_version_1(self):
        d = _default_draft("Test")
        self.assertEqual(d["version"], 1)
        self.assertEqual(d["name"], "Test")
        self.assertEqual(d["scale"], 1.0)
        self.assertEqual(d["entities"], [])


class TestValidateDraft(unittest.TestCase):
    def test_accepts_valid_draft(self):
        d = _default_draft("Test")
        _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0})
        r = _validate_draft(d)
        self.assertTrue(r["ok"])

    def test_rejects_non_object(self):
        r = _validate_draft(None)
        self.assertFalse(r["ok"])

    def test_rejects_wrong_version(self):
        d = _default_draft(); d["version"] = 2
        r = _validate_draft(d)
        self.assertFalse(r["ok"])

    def test_rejects_negative_scale(self):
        d = _default_draft(); d["scale"] = -1
        r = _validate_draft(d)
        self.assertFalse(r["ok"])

    def test_rejects_duplicate_ids(self):
        d = {"version": 1, "name": "Test", "scale": 1.0, "entities": [
            {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1},
            {"id": "l1", "kind": "line", "x1": 2, "y1": 2, "x2": 3, "y2": 3},
        ]}
        r = _validate_draft(d)
        self.assertFalse(r["ok"])


class TestAddRemoveEntity(unittest.TestCase):
    def test_add_entity_generates_id(self):
        d = _default_draft()
        e = _add_entity(d, {"kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1})
        self.assertIsNotNone(e["id"])

    def test_remove_entity(self):
        d = _default_draft()
        e = _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1})
        _remove_entity(d, "l1")
        self.assertEqual(len(d["entities"]), 0)

    def test_remove_unknown_raises(self):
        d = _default_draft()
        with self.assertRaises(ValueError):
            _remove_entity(d, "nope")


class TestMoveEntity(unittest.TestCase):
    def test_moves_line(self):
        d = _default_draft()
        _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0})
        _move_entity(d, "l1", 5, 3)
        l = d["entities"][0]
        self.assertEqual(l["x1"], 5); self.assertEqual(l["y1"], 3)
        self.assertEqual(l["x2"], 15); self.assertEqual(l["y2"], 3)

    def test_moves_circle(self):
        d = _default_draft()
        _add_entity(d, {"id": "c1", "kind": "circle", "cx": 10, "cy": 20, "r": 5})
        _move_entity(d, "c1", -3, 4)
        self.assertEqual(d["entities"][0]["cx"], 7)
        self.assertEqual(d["entities"][0]["cy"], 24)

    def test_unknown_raises(self):
        d = _default_draft()
        with self.assertRaises(ValueError):
            _move_entity(d, "nope", 1, 1)


class TestOffsetEntity(unittest.TestCase):
    def test_line_offset_perpendicular(self):
        d = _default_draft()
        _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0})
        r = _offset_entity(d, "l1", 1)
        self.assertEqual(r["kind"], "line")
        self.assertAlmostEqual(r["y1"], 1, places=5)
        self.assertAlmostEqual(r["y2"], 1, places=5)

    def test_returns_null_for_circle(self):
        d = _default_draft()
        _add_entity(d, {"id": "c1", "kind": "circle", "cx": 0, "cy": 0, "r": 5})
        r = _offset_entity(d, "c1", 1)
        self.assertIsNone(r)


class TestFilletCorner(unittest.TestCase):
    def test_produces_tangent_arc(self):
        d = _default_draft()
        _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0})
        _add_entity(d, {"id": "l2", "kind": "line", "x1": 0, "y1": 0, "x2": 0, "y2": 10})
        arc = _fillet_corner(d, "l1", "l2", 2)
        self.assertIsNotNone(arc)
        self.assertEqual(arc["kind"], "arc")
        self.assertEqual(arc["rx"], 2)
        self.assertEqual(arc["ry"], 2)

    def test_returns_null_for_parallel_lines(self):
        d = _default_draft()
        _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0})
        _add_entity(d, {"id": "l2", "kind": "line", "x1": 0, "y1": 1, "x2": 10, "y2": 1})
        arc = _fillet_corner(d, "l1", "l2", 2)
        self.assertIsNone(arc)


class TestPatternLinear(unittest.TestCase):
    def test_count_copies(self):
        d = _default_draft()
        _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 0})
        copies = _pattern_linear(d, "l1", 3, 10, 0)
        self.assertEqual(len(copies), 2)
        self.assertEqual(len(d["entities"]), 3)

    def test_empty_for_count_1(self):
        d = _default_draft()
        _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 0})
        copies = _pattern_linear(d, "l1", 1, 10, 0)
        self.assertEqual(len(copies), 0)


class TestPatternPolar(unittest.TestCase):
    def test_copies_around_center(self):
        d = _default_draft()
        _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 0})
        copies = _pattern_polar(d, "l1", 4, [0, 0], 360)
        self.assertEqual(len(copies), 3)


class TestExportDXF(unittest.TestCase):
    def test_has_required_sections(self):
        d = _default_draft()
        _add_entity(d, {"id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0})
        txt = _export_dxf(d)
        self.assertIn("SECTION", txt)
        self.assertIn("HEADER", txt)
        self.assertIn("ENTITIES", txt)
        self.assertIn("EOF", txt)
        self.assertIn("LINE", txt)

    def test_emits_circle(self):
        d = _default_draft()
        _add_entity(d, {"id": "c1", "kind": "circle", "cx": 5, "cy": 5, "r": 2})
        txt = _export_dxf(d)
        self.assertIn("CIRCLE", txt)

    def test_emits_arc(self):
        d = _default_draft()
        _add_entity(d, {"id": "a1", "kind": "arc", "cx": 0, "cy": 0, "rx": 5, "ry": 5, "start_angle": 0, "end_angle": 90})
        txt = _export_dxf(d)
        self.assertIn("ARC", txt)

    def test_emits_polyline(self):
        d = _default_draft()
        _add_entity(d, {"id": "p1", "kind": "polyline", "points": [[0, 0], [10, 0], [10, 10]]})
        txt = _export_dxf(d)
        self.assertIn("POLYLINE", txt)
        self.assertIn("VERTEX", txt)
        self.assertIn("SEQEND", txt)

    def test_emits_text(self):
        d = _default_draft()
        _add_entity(d, {"id": "t1", "kind": "text", "x": 0, "y": 0, "value": "Hello"})
        txt = _export_dxf(d)
        self.assertIn("TEXT", txt)
        self.assertIn("Hello", txt)


if __name__ == "__main__":
    unittest.main()
