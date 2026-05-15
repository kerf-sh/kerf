"""
tests/test_route.py — endpoint shape tests for POST /lint-plc.

Uses FastAPI TestClient; does not require MATIEC or a real database.
"""
from __future__ import annotations

import unittest.mock as mock

import pytest


# ---------------------------------------------------------------------------
# Test app setup
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from kerf_plc.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# T1 — response shape
# ---------------------------------------------------------------------------

class TestLintPLCEndpoint:
    def test_returns_200_with_diagnostics_and_warnings_keys(self, client, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-plc", json={"source": "PROGRAM x END_PROGRAM"})
        assert resp.status_code == 200
        body = resp.json()
        assert "diagnostics" in body
        assert "warnings" in body
        assert isinstance(body["diagnostics"], list)
        assert isinstance(body["warnings"], list)

    def test_matiec_absent_populates_warnings_not_diagnostics(self, client, monkeypatch):
        """When MATIEC is absent the advisory goes to 'warnings', not 'diagnostics'."""
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-plc", json={"source": "PROGRAM x END_PROGRAM"})
        body = resp.json()
        assert len(body["diagnostics"]) == 0
        assert len(body["warnings"]) == 1
        assert "MATIEC not installed" in body["warnings"][0]

    def test_error_diagnostic_has_required_fields(self, client, monkeypatch):
        """Diagnostics returned for lint errors have all required shape keys."""
        from kerf_plc.matiec_lint import Diagnostic

        fake_diags = [
            Diagnostic(severity="error", message="syntax error", line=3, column=1)
        ]
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: "/usr/bin/iec2c")
        monkeypatch.setattr("kerf_plc.matiec_lint.lint_st_source", lambda _src: fake_diags)

        resp = client.post("/lint-plc", json={"source": "PROGRAM x END_PROGRAM"})
        body = resp.json()
        assert len(body["diagnostics"]) == 1
        d = body["diagnostics"][0]
        assert d["severity"] == "error"
        assert d["line"] == 3
        assert d["column"] == 1
        assert "syntax error" in d["message"]
        assert d["source"] == "matiec"

    def test_non_string_source_returns_warning(self, client, monkeypatch):
        """Non-string 'source' field is rejected with a warning (not a 500)."""
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-plc", json={"source": 12345})
        assert resp.status_code == 200
        body = resp.json()
        assert any("string" in w for w in body["warnings"])

    def test_missing_source_field_returns_200(self, client, monkeypatch):
        """Missing 'source' field is tolerated — treated as empty string."""
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-plc", json={})
        assert resp.status_code == 200

    def test_empty_source_returns_empty_diagnostics(self, client, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: "/usr/bin/iec2c")

        import subprocess as sp
        fake_result = mock.MagicMock()
        fake_result.stderr = b""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_result)

        resp = client.post("/lint-plc", json={"source": ""})
        body = resp.json()
        assert body["diagnostics"] == []
