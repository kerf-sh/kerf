"""
tests/test_ld_lint.py — IEC 61131-3 Ladder Diagram lint tests.

DoD checks:
  - MATIEC lint passes on a valid rung (structural phase always, MATIEC
    gracefully degrades when absent)
  - Wiring errors are caught (coil inside branch, contact as output, etc.)
"""
from __future__ import annotations

import pytest

from kerf_plc.ld.schema import load
from kerf_plc.ld.lint import lint_ld, _structural_lint, _prog_to_st


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_LD = {
    "program": "ValidProg",
    "variables": [
        {"name": "pb_start", "type": "BOOL", "dir": "input"},
        {"name": "pb_stop",  "type": "BOOL", "dir": "input"},
        {"name": "motor",    "type": "BOOL", "dir": "output"},
    ],
    "rungs": [
        {
            "label": "Rung 0",
            "branches": [
                [
                    {"type": "contact_no", "var": "pb_start"},
                    {"type": "contact_nc", "var": "pb_stop"},
                ]
            ],
            "output": {"type": "coil", "var": "motor"},
        }
    ],
}

TIMER_LD = {
    "program": "TimerProg",
    "variables": [
        {"name": "enable", "type": "BOOL", "dir": "input"},
    ],
    "rungs": [
        {
            "branches": [[{"type": "contact_no", "var": "enable"}]],
            "output": {
                "type": "fb_call",
                "fb_type": "TON",
                "fb_instance": "T1",
                "fb_inputs": {"PT": "T#5s"},
            },
        }
    ],
}


# ---------------------------------------------------------------------------
# T1 — structural lint: valid program has no errors
# ---------------------------------------------------------------------------

class TestStructuralLintValid:
    def test_valid_program_no_structural_errors(self):
        prog = load(VALID_LD)
        diags = _structural_lint(prog)
        errors = [d for d in diags if d.severity == "error"]
        assert errors == []

    def test_valid_timer_program_no_structural_errors(self):
        prog = load(TIMER_LD)
        diags = _structural_lint(prog)
        errors = [d for d in diags if d.severity == "error"]
        assert errors == []


# ---------------------------------------------------------------------------
# T2 — structural lint: catches wiring errors
# ---------------------------------------------------------------------------

class TestStructuralLintErrors:
    def _build_bad_rung_coil_in_branch(self):
        """Construct a bad program directly (bypass load() validation)."""
        from kerf_plc.ld.schema import LadderProgram, Rung, Element
        prog = LadderProgram(program="Bad")
        bad_elem = Element(type="coil", var="y")
        rung = Rung(
            label="Bad rung",
            branches=[[bad_elem]],
            output=Element(type="coil", var="z"),
        )
        prog.rungs.append(rung)
        return prog

    def _build_bad_rung_contact_as_output(self):
        from kerf_plc.ld.schema import LadderProgram, Rung, Element
        prog = LadderProgram(program="Bad")
        rung = Rung(
            branches=[[Element(type="contact_no", var="a")]],
            output=Element(type="contact_no", var="b"),  # wrong
        )
        prog.rungs.append(rung)
        return prog

    def _build_bad_rung_no_output(self):
        from kerf_plc.ld.schema import LadderProgram, Rung, Element
        prog = LadderProgram(program="NoOut")
        rung = Rung(
            branches=[[Element(type="contact_no", var="x")]],
            output=None,
        )
        prog.rungs.append(rung)
        return prog

    def _build_bad_rung_empty_branch(self):
        from kerf_plc.ld.schema import LadderProgram, Rung, Element
        prog = LadderProgram(program="EmptyBranch")
        rung = Rung(
            branches=[[]],   # empty branch
            output=Element(type="coil", var="y"),
        )
        prog.rungs.append(rung)
        return prog

    def test_coil_in_branch_produces_error(self):
        prog = self._build_bad_rung_coil_in_branch()
        diags = _structural_lint(prog)
        errors = [d for d in diags if d.severity == "error"]
        assert any("not a contact" in e.message for e in errors)

    def test_contact_as_output_produces_error(self):
        prog = self._build_bad_rung_contact_as_output()
        diags = _structural_lint(prog)
        errors = [d for d in diags if d.severity == "error"]
        assert any("not a coil" in e.message or "contact" in e.message for e in errors)

    def test_no_output_produces_warning(self):
        prog = self._build_bad_rung_no_output()
        diags = _structural_lint(prog)
        warnings = [d for d in diags if d.severity == "warning"]
        assert any("no output" in w.message for w in warnings)

    def test_empty_branch_produces_error(self):
        prog = self._build_bad_rung_empty_branch()
        diags = _structural_lint(prog)
        errors = [d for d in diags if d.severity == "error"]
        assert any("empty" in e.message for e in errors)

    def test_undeclared_var_produces_warning_when_vars_declared(self):
        """When variables are declared, using an undeclared var should warn."""
        from kerf_plc.ld.schema import LadderProgram, Rung, Element, VariableDecl
        prog = LadderProgram(
            program="VarCheck",
            variables=[VariableDecl(name="declared_var", type="BOOL")],
        )
        rung = Rung(
            branches=[[Element(type="contact_no", var="undeclared_var")]],
            output=Element(type="coil", var="declared_var"),
        )
        prog.rungs.append(rung)
        diags = _structural_lint(prog)
        warnings = [d for d in diags if d.severity == "warning"]
        assert any("undeclared_var" in w.message for w in warnings)


# ---------------------------------------------------------------------------
# T3 — LD→ST transpilation
# ---------------------------------------------------------------------------

class TestProgToST:
    def test_generates_program_block(self):
        prog = load(VALID_LD)
        st = _prog_to_st(prog)
        assert "PROGRAM ValidProg" in st
        assert "END_PROGRAM" in st

    def test_input_var_declared(self):
        prog = load(VALID_LD)
        st = _prog_to_st(prog)
        assert "pb_start" in st
        assert "VAR_INPUT" in st

    def test_output_var_declared(self):
        prog = load(VALID_LD)
        st = _prog_to_st(prog)
        assert "motor" in st
        assert "VAR_OUTPUT" in st

    def test_coil_assignment_generated(self):
        prog = load(VALID_LD)
        st = _prog_to_st(prog)
        assert "motor :=" in st

    def test_contact_no_in_condition(self):
        prog = load(VALID_LD)
        st = _prog_to_st(prog)
        # contact_no → plain var, contact_nc → NOT var
        assert "pb_start" in st
        assert "NOT" in st and "pb_stop" in st

    def test_timer_fb_call_generated(self):
        prog = load(TIMER_LD)
        st = _prog_to_st(prog)
        assert "T1(" in st
        assert "EN :=" in st


# ---------------------------------------------------------------------------
# T4 — lint_ld integration (mocked MATIEC)
# ---------------------------------------------------------------------------

class TestLintLDIntegration:
    def test_valid_program_no_errors_from_structural(self, monkeypatch):
        """Valid program: structural errors list is empty."""
        # Mock matiec to return empty (no MATIEC installed in CI)
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        prog = load(VALID_LD)
        diags = lint_ld(prog)
        errors = [d for d in diags if d.severity == "error"]
        assert errors == []

    def test_valid_program_matiec_absent_advisory_in_warnings(self, monkeypatch):
        """When MATIEC absent, a warning advisory is added (not an error)."""
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        prog = load(VALID_LD)
        diags = lint_ld(prog)
        warnings = [d for d in diags if d.severity == "warning"]
        assert any("MATIEC not installed" in w.message for w in warnings)

    def test_matiec_error_tagged_ld_st(self, monkeypatch):
        """MATIEC errors from the LD→ST path are tagged with [LD→ST]."""
        import unittest.mock as mock
        fake = mock.MagicMock()
        fake.stderr = b"input.st:3:1: error: syntax error\n"
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: "/usr/bin/iec2c")
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake)
        prog = load(VALID_LD)
        diags = lint_ld(prog)
        errors = [d for d in diags if d.severity == "error"]
        assert any("[LD→ST]" in e.message for e in errors)

    def test_matiec_clean_on_valid_st(self, monkeypatch):
        """When LD→ST produces valid ST, MATIEC returns no errors."""
        import unittest.mock as mock
        fake = mock.MagicMock()
        fake.stderr = b""   # no errors
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: "/usr/bin/iec2c")
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake)
        prog = load(VALID_LD)
        diags = lint_ld(prog)
        errors = [d for d in diags if d.severity == "error"]
        assert errors == []
