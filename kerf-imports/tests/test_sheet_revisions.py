"""test_sheet_revisions.py — pytest suite for sheet_revisions LLM tools."""
import importlib.util
import sys
import types
import unittest

_TOOLS = "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-imports/src/kerf_imports/tools"
_SPEC = importlib.util.spec_from_file_location("tools.sheet_revisions", f"{_TOOLS}/sheet_revisions.py")

_REG_STUB = types.ModuleType("tools.registry")
_REG_STUB.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_REG_STUB.err_payload = lambda msg, code: __import__("json").dumps({"error": msg, "code": code})
_REG_STUB.ok_payload = lambda v: __import__("json").dumps(v)
_REG_STUB.register = lambda spec, write=False: (lambda fn: fn)
_PREV_REGISTRY = sys.modules.get("tools.registry")
sys.modules["tools.registry"] = _REG_STUB

_CTX_STUB = types.ModuleType("tools.context")
_CTX_STUB.ProjectCtx = type("ProjectCtx", (), {})
sys.modules["tools.context"] = _CTX_STUB

sys.modules["tools.sheet_revisions"] = _mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)
_mod = sys.modules["tools.sheet_revisions"]

if _PREV_REGISTRY is not None:
    sys.modules["tools.registry"] = _PREV_REGISTRY
else:
    del sys.modules["tools.registry"]
del sys.modules["tools.context"]


import json
import os
import tempfile

_TEMP_DIR = tempfile.mkdtemp()

def _make_ctx(temp_file_content: str | None = None):
    _written = False
    class _FakeCtx:
        def resolve_file_id(self, fid):
            nonlocal _written
            path = os.path.join(_TEMP_DIR, f"sheet_{fid}.json")
            if temp_file_content is not None and not _written:
                with open(path, "w") as f:
                    json.dump(temp_file_content, f)
                _written = True
            return path
    return _FakeCtx()


class TestNextLetterPure(unittest.TestCase):
    def test_A_to_B(self):
        self.assertEqual(self._fn("A"), "B")

    def test_Z_to_AA(self):
        self.assertEqual(self._fn("Z"), "AA")

    def test_AA_to_AB(self):
        self.assertEqual(self._fn("AA"), "AB")

    def test_AZ_to_BA(self):
        self.assertEqual(self._fn("AZ"), "BA")

    def test_ZZZ_to_AAAA(self):
        self.assertEqual(self._fn("ZZZ"), "AAAA")

    def _fn(self, letter):
        from kerf_imports.tools.sheet_revisions import _next_letter
        return _next_letter(letter)


class TestNextRevisionLetterForSheet(unittest.TestCase):
    def test_empty_sheet_returns_A(self):
        from kerf_imports.tools.sheet_revisions import _next_revision_letter_for_sheet
        self.assertEqual(_next_revision_letter_for_sheet({}), "A")

    def test_single_revision_returns_B(self):
        from kerf_imports.tools.sheet_revisions import _next_revision_letter_for_sheet
        self.assertEqual(_next_revision_letter_for_sheet({"revisions": [{"letter": "A"}]}), "B")

    def test_Z_returns_AA(self):
        from kerf_imports.tools.sheet_revisions import _next_revision_letter_for_sheet
        self.assertEqual(_next_revision_letter_for_sheet({"revisions": [{"letter": "Z"}]}), "AA")

    def test_multiple_sorted_returns_next(self):
        from kerf_imports.tools.sheet_revisions import _next_revision_letter_for_sheet
        sheet = {"revisions": [{"letter": "A"}, {"letter": "B"}, {"letter": "C"}]}
        self.assertEqual(_next_revision_letter_for_sheet(sheet), "D")


class TestAddSheetRevisionTool(unittest.TestCase):
    def setUp(self):
        self.fid = "revtest001"
        self.ctx = _make_ctx({"version": 1, "titleblock": {}, "revisions": [], "viewports": []})

    def test_creates_revisions_array(self):
        import json, os
        result = _mod.add_sheet_revision(self.ctx, file_id=self.fid, description="Initial issue", by="Jane", set_active=True)
        payload = json.loads(result)
        self.assertNotIn("error", payload)
        path = os.path.join(_TEMP_DIR, f"sheet_{self.fid}.json")
        sheet = json.load(open(path))
        self.assertIn("revisions", sheet)
        self.assertEqual(sheet["revisions"][0]["letter"], "A")

    def test_auto_letter_increments(self):
        import json, os
        _mod.add_sheet_revision(self.ctx, file_id=self.fid, description="First", set_active=False)
        result2 = _mod.add_sheet_revision(self.ctx, file_id=self.fid, description="Second", set_active=False)
        payload2 = json.loads(result2)
        self.assertEqual(payload2["letter"], "B")

    def test_sets_active_revision_when_requested(self):
        import json, os
        _mod.add_sheet_revision(self.ctx, file_id=self.fid, description="Only", set_active=True)
        path = os.path.join(_TEMP_DIR, f"sheet_{self.fid}.json")
        sheet = json.load(open(path))
        self.assertEqual(sheet["titleblock"]["revision"], "A")

    def test_rejects_missing_sheet(self):
        ctx_bad = _make_ctx()
        result = _mod.add_sheet_revision(ctx_bad, file_id="nonexistent", description="Bad")
        self.assertIn("error", result)


class TestSetActiveSheetRevisionTool(unittest.TestCase):
    def setUp(self):
        self.fid = "activetest001"
        self.ctx = _make_ctx({
            "version": 1,
            "titleblock": {"revision": "A"},
            "revisions": [{"letter": "A", "date": "2026-05-14", "description": "Init", "by": "Jane"}],
            "viewports": [],
        })

    def test_sets_active_revision(self):
        import json, os
        result = _mod.set_active_sheet_revision(self.ctx, file_id=self.fid, letter="A")
        payload = json.loads(result)
        self.assertNotIn("error", payload)
        path = os.path.join(_TEMP_DIR, f"sheet_{self.fid}.json")
        sheet = json.load(open(path))
        self.assertEqual(sheet["titleblock"]["revision"], "A")

    def test_rejects_unknown_letter(self):
        result = _mod.set_active_sheet_revision(self.ctx, file_id=self.fid, letter="Z")
        self.assertIn("error", result)


class TestListSheetRevisionsTool(unittest.TestCase):
    def setUp(self):
        self.fid = "listtest001"
        self.ctx = _make_ctx({
            "version": 1,
            "titleblock": {"revision": "B"},
            "revisions": [
                {"letter": "B", "date": "2026-05-14", "description": "Second", "by": "Bob"},
                {"letter": "A", "date": "2026-05-01", "description": "First", "by": "Jane"},
            ],
            "viewports": [],
        })

    def test_returns_sorted_revisions(self):
        result = _mod.list_sheet_revisions(self.ctx, file_id=self.fid)
        payload = json.loads(result)
        self.assertNotIn("error", payload)
        letters = [r["letter"] for r in payload["revisions"]]
        self.assertEqual(letters, ["A", "B"])

    def test_returns_active_revision(self):
        result = _mod.list_sheet_revisions(self.ctx, file_id=self.fid)
        payload = json.loads(result)
        self.assertEqual(payload["active_revision"], "B")


class TestUpdateTitleBlockFieldTool(unittest.TestCase):
    def setUp(self):
        self.fid = "tbt001"
        self.ctx = _make_ctx({
            "version": 1,
            "titleblock": {"project_name": "Old Project"},
            "revisions": [],
            "viewports": [],
        })

    def test_updates_valid_field(self):
        import json, os
        result = _mod.update_title_block_field(self.ctx, file_id=self.fid, field="project_name", value="New Project")
        payload = json.loads(result)
        self.assertNotIn("error", payload)
        path = os.path.join(_TEMP_DIR, f"sheet_{self.fid}.json")
        sheet = json.load(open(path))
        self.assertEqual(sheet["titleblock"]["project_name"], "New Project")

    def test_rejects_invalid_field(self):
        result = _mod.update_title_block_field(self.ctx, file_id=self.fid, field="not_a_field", value="X")
        self.assertIn("error", result)

    def test_updates_issue_date(self):
        import json, os
        result = _mod.update_title_block_field(self.ctx, file_id=self.fid, field="issue_date", value="2026-06-01")
        payload = json.loads(result)
        self.assertNotIn("error", payload)
        path = os.path.join(_TEMP_DIR, f"sheet_{self.fid}.json")
        sheet = json.load(open(path))
        self.assertEqual(sheet["titleblock"]["issue_date"], "2026-06-01")

    def test_updates_drawn_by(self):
        import json, os
        result = _mod.update_title_block_field(self.ctx, file_id=self.fid, field="drawn_by", value="Alice")
        payload = json.loads(result)
        self.assertNotIn("error", payload)
        path = os.path.join(_TEMP_DIR, f"sheet_{self.fid}.json")
        sheet = json.load(open(path))
        self.assertEqual(sheet["titleblock"]["drawn_by"], "Alice")


if __name__ == "__main__":
    unittest.main()
