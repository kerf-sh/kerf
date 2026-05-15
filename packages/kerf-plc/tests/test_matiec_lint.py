"""
tests/test_matiec_lint.py — hermetic tests for matiec_lint.py.

Strategy:
  - When MATIEC / iec2c is not installed (CI default), tests assert
    graceful-degradation behaviour.
  - When iec2c *is* installed (optional), the real parser is exercised.
  - subprocess calls are monkey-patched in unit tests so CI passes without
    MATIEC installed.
"""
from __future__ import annotations

import shutil
import subprocess
import types
import unittest.mock as mock

import pytest

from kerf_plc.matiec_lint import (
    Diagnostic,
    _parse_stderr,
    lint_st_source,
)

# ---------------------------------------------------------------------------
# Sample ST programs
# ---------------------------------------------------------------------------

VALID_ST = """\
PROGRAM TestProg
VAR
  x : INT;
  y : BOOL;
END_VAR
x := 42;
y := TRUE;
END_PROGRAM
"""

SYNTAX_ERROR_ST = """\
PROGRAM BrokenProg
VAR
  x : INT
END_VAR
IF x = THEN
  x := 1;
END_IF
END_PROGRAM
"""

# ---------------------------------------------------------------------------
# T1 — graceful degradation when MATIEC is absent
# ---------------------------------------------------------------------------

class TestNoMATIEC:
    def test_missing_binary_returns_warning_not_crash(self, monkeypatch):
        """When iec2c is not on PATH, lint_st_source returns a warning, not an error."""
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        result = lint_st_source(VALID_ST)
        assert len(result) == 1
        d = result[0]
        assert d.severity == "warning"
        assert "MATIEC not installed" in d.message

    def test_missing_binary_warning_has_install_hint(self, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        result = lint_st_source(VALID_ST)
        assert "apt install matiec" in result[0].message

    def test_empty_source_returns_empty_list(self, monkeypatch):
        """Empty source is a no-op even when MATIEC is present."""
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: "/usr/bin/iec2c")
        result = lint_st_source("")
        assert result == []

    def test_whitespace_only_source_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: "/usr/bin/iec2c")
        result = lint_st_source("   \n\t  ")
        assert result == []


# ---------------------------------------------------------------------------
# T2 — stderr parser (no subprocess needed)
# ---------------------------------------------------------------------------

class TestParseStderr:
    def test_parses_error_line(self):
        stderr = "input.st:5:3: error: missing semicolon after expression"
        diags = _parse_stderr(stderr, "input.st")
        assert len(diags) == 1
        d = diags[0]
        assert d.severity == "error"
        assert d.line == 5
        assert d.column == 3
        assert "missing semicolon" in d.message

    def test_parses_warning_line(self):
        stderr = "input.st:12:1: warning: unused variable 'x'"
        diags = _parse_stderr(stderr, "input.st")
        assert len(diags) == 1
        assert diags[0].severity == "warning"
        assert diags[0].line == 12

    def test_parses_bare_error_line(self):
        """MATIEC also emits bare 'error: ...' lines without location."""
        stderr = "error: could not open include file"
        diags = _parse_stderr(stderr, "input.st")
        assert len(diags) == 1
        assert diags[0].severity == "error"
        assert diags[0].line is None

    def test_note_mapped_to_info(self):
        stderr = "input.st:3:2: note: implicit conversion from INT to BOOL"
        diags = _parse_stderr(stderr, "input.st")
        assert diags[0].severity == "info"

    def test_irrelevant_lines_skipped(self):
        """Banner/info lines that don't match the pattern are dropped."""
        stderr = (
            "MATIEC - IEC 61131-3 compiler\n"
            "Copyright (C) ...\n"
            "input.st:7:4: error: syntax error\n"
        )
        diags = _parse_stderr(stderr, "input.st")
        assert len(diags) == 1

    def test_empty_stderr_returns_empty(self):
        assert _parse_stderr("", "input.st") == []

    def test_multiple_diagnostics(self):
        stderr = (
            "input.st:5:3: error: undeclared identifier 'foo'\n"
            "input.st:10:1: warning: variable 'bar' assigned but never read\n"
            "input.st:15:5: error: type mismatch: expected BOOL, got INT\n"
        )
        diags = _parse_stderr(stderr, "input.st")
        assert len(diags) == 3
        assert diags[0].severity == "error"
        assert diags[1].severity == "warning"
        assert diags[2].severity == "error"

    def test_bytes_decoded_to_str(self, monkeypatch):
        """lint_st_source decodes bytes stderr before parsing."""
        fake_result = mock.MagicMock()
        fake_result.stderr = b"input.st:3:1: error: decode test\n"

        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: "/usr/bin/iec2c")
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_result)

        result = lint_st_source(VALID_ST)
        assert any("decode test" in d.message for d in result)


# ---------------------------------------------------------------------------
# T3 — subprocess mock: valid ST → no errors
# ---------------------------------------------------------------------------

class TestWithMockedSubprocess:
    @pytest.fixture(autouse=True)
    def mock_binary(self, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: "/usr/bin/iec2c")

    def test_valid_st_produces_no_errors(self, monkeypatch):
        """When MATIEC returns empty stderr, no diagnostics are emitted."""
        fake = mock.MagicMock()
        fake.stderr = b""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake)

        result = lint_st_source(VALID_ST)
        assert result == []

    def test_syntax_error_produces_diagnostics(self, monkeypatch):
        """MATIEC stderr with an error line → Diagnostic with severity=error."""
        fake = mock.MagicMock()
        fake.stderr = b"input.st:5:8: error: syntax error near 'THEN'\n"
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake)

        result = lint_st_source(SYNTAX_ERROR_ST)
        assert len(result) >= 1
        assert any(d.severity == "error" for d in result)
        assert any(d.line == 5 for d in result)

    def test_timeout_returns_warning(self, monkeypatch):
        """subprocess.TimeoutExpired → single warning diagnostic."""
        def _timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="iec2c", timeout=5)

        monkeypatch.setattr("subprocess.run", _timeout)
        result = lint_st_source(VALID_ST)
        assert len(result) == 1
        assert result[0].severity == "warning"
        assert "timed out" in result[0].message

    def test_oserror_returns_warning(self, monkeypatch):
        """OSError on exec (e.g. binary gone) → single warning diagnostic."""
        def _oserr(*a, **kw):
            raise OSError("No such file or directory: iec2c")

        monkeypatch.setattr("subprocess.run", _oserr)
        result = lint_st_source(VALID_ST)
        assert len(result) == 1
        assert result[0].severity == "warning"
        assert "could not be executed" in result[0].message


# ---------------------------------------------------------------------------
# T4 — real MATIEC integration (skipped when iec2c absent)
# ---------------------------------------------------------------------------

class TestRealMATIEC:
    @pytest.fixture(autouse=True)
    def require_matiec(self):
        if shutil.which("iec2c") is None:
            pytest.skip("iec2c not installed")

    def test_valid_st_no_errors(self):
        result = lint_st_source(VALID_ST)
        errors = [d for d in result if d.severity == "error"]
        assert errors == []

    def test_syntax_error_produces_diagnostic(self):
        result = lint_st_source(SYNTAX_ERROR_ST)
        assert any(d.severity == "error" for d in result)
