"""test_sheet.py — pytest suite for sheet.py pure logic (no DB required)."""
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

# Load sheet.py via importlib
_spec = importlib.util.spec_from_file_location("tools.sheet", f"{_TOOLS}/sheet.py")
_mod = types.ModuleType("tools.sheet")
sys.modules["tools.sheet"] = _mod
_spec.loader.exec_module(_mod)

_default_sheet = _mod._default_sheet
_validate_sheet = _mod._validate_sheet
SHEET_SIZES_MM = _mod.SHEET_SIZES_MM
VALID_SIZES = _mod.VALID_SIZES
VALID_ORIENTATIONS = _mod.VALID_ORIENTATIONS


# ── _default_sheet ─────────────────────────────────────────────────────────────

class TestDefaultSheet:
    def test_fields_populated(self):
        s = _default_sheet("A-101 Floor Plans", "A-101", "A1")
        assert s["version"] == 1
        assert s["name"] == "A-101 Floor Plans"
        assert s["sheet_number"] == "A-101"
        assert s["size"] == "A1"
        assert s["orientation"] == "landscape"

    def test_viewports_and_clouds_empty(self):
        s = _default_sheet("S", "S-001", "A3")
        assert s["viewports"] == []
        assert s["revision_clouds"] == []

    def test_titleblock_present(self):
        s = _default_sheet("S", "S-001", "A3")
        assert "project_name" in s["titleblock"]
        assert "issue_date" in s["titleblock"]


# ── SHEET_SIZES_MM ─────────────────────────────────────────────────────────────

class TestSheetSizes:
    def test_a0(self):
        assert SHEET_SIZES_MM["A0"] == [841, 1189]

    def test_a4(self):
        assert SHEET_SIZES_MM["A4"] == [210, 297]

    def test_ansi_a(self):
        assert SHEET_SIZES_MM["ANSI_A"] == [216, 279]

    def test_ansi_e(self):
        assert SHEET_SIZES_MM["ANSI_E"] == [864, 1118]

    def test_all_valid_sizes_present(self):
        for sz in VALID_SIZES:
            assert sz in SHEET_SIZES_MM


# ── _validate_sheet ────────────────────────────────────────────────────────────

class TestValidateSheet:
    def test_valid_sheet_passes(self):
        s = _default_sheet("Plans", "A-100", "A1")
        assert _validate_sheet(s) == []

    def test_all_valid_sizes_pass(self):
        for sz in VALID_SIZES:
            s = _default_sheet("X", "X-001", sz)
            assert _validate_sheet(s) == [], f"size={sz} should pass"

    def test_rejects_bad_size(self):
        s = {**_default_sheet("X", "X-001", "A1"), "size": "B5"}
        errs = _validate_sheet(s)
        assert any("size" in e for e in errs)

    def test_rejects_bad_orientation(self):
        s = {**_default_sheet("X", "X-001", "A1"), "orientation": "diagonal"}
        errs = _validate_sheet(s)
        assert any("orientation" in e for e in errs)

    def test_rejects_missing_name(self):
        s = {**_default_sheet("X", "X-001", "A1"), "name": ""}
        errs = _validate_sheet(s)
        assert any("name" in e for e in errs)

    def test_rejects_missing_sheet_number(self):
        s = {**_default_sheet("X", "X-001", "A1"), "sheet_number": ""}
        errs = _validate_sheet(s)
        assert any("sheet_number" in e for e in errs)

    def test_rejects_wrong_version(self):
        s = {**_default_sheet("X", "X-001", "A1"), "version": 2}
        errs = _validate_sheet(s)
        assert any("version" in e for e in errs)
