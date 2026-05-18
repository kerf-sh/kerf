"""
tests/test_ld_routes.py — endpoint tests for POST /lint-ld and POST /export-ld.

Uses FastAPI TestClient; does not require MATIEC or a real database.
"""
from __future__ import annotations

import pytest


VALID_LD = {
    "program": "RouteTest",
    "variables": [
        {"name": "pb", "type": "BOOL", "dir": "input"},
        {"name": "y",  "type": "BOOL", "dir": "output"},
    ],
    "rungs": [
        {
            "branches": [[{"type": "contact_no", "var": "pb"}]],
            "output": {"type": "coil", "var": "y"},
        }
    ],
}


# ---------------------------------------------------------------------------
# Fixtures
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
# T1 — /lint-ld
# ---------------------------------------------------------------------------

class TestLintLDRoute:
    def test_valid_program_returns_200(self, client, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-ld", json={"program": VALID_LD})
        assert resp.status_code == 200

    def test_valid_program_has_diagnostics_and_warnings_keys(self, client, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-ld", json={"program": VALID_LD})
        body = resp.json()
        assert "diagnostics" in body
        assert "warnings" in body

    def test_valid_program_no_structural_errors(self, client, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-ld", json={"program": VALID_LD})
        body = resp.json()
        errors = [d for d in body["diagnostics"] if d["severity"] == "error"]
        assert errors == []

    def test_non_dict_program_returns_warning(self, client, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-ld", json={"program": "not a dict"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["warnings"]

    def test_missing_program_key_returns_warning(self, client, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-ld", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["warnings"]

    def test_matiec_absent_advisory_in_warnings_not_errors(self, client, monkeypatch):
        monkeypatch.setattr("kerf_plc.matiec_lint._matiec_binary", lambda: None)
        resp = client.post("/lint-ld", json={"program": VALID_LD})
        body = resp.json()
        # MATIEC-absent advisory → warnings bucket, not diagnostics
        assert any("MATIEC" in w for w in body["warnings"])
        errors = [d for d in body["diagnostics"] if d["severity"] == "error"]
        assert errors == []


# ---------------------------------------------------------------------------
# T2 — /export-ld
# ---------------------------------------------------------------------------

class TestExportLDRoute:
    def test_valid_program_returns_200(self, client):
        resp = client.post("/export-ld", json={"program": VALID_LD})
        assert resp.status_code == 200

    def test_response_has_xml_key(self, client):
        resp = client.post("/export-ld", json={"program": VALID_LD})
        body = resp.json()
        assert "xml" in body

    def test_xml_is_non_empty_string(self, client):
        resp = client.post("/export-ld", json={"program": VALID_LD})
        body = resp.json()
        assert isinstance(body["xml"], str)
        assert len(body["xml"]) > 0

    def test_xml_contains_program_name(self, client):
        resp = client.post("/export-ld", json={"program": VALID_LD})
        body = resp.json()
        assert "RouteTest" in body["xml"]

    def test_xml_contains_plcopen_ns(self, client):
        resp = client.post("/export-ld", json={"program": VALID_LD})
        body = resp.json()
        assert "plcopen.org" in body["xml"]

    def test_non_dict_program_returns_error_key(self, client):
        resp = client.post("/export-ld", json={"program": "bad"})
        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body or body.get("xml") == ""

    def test_invalid_program_validation_error_returns_error_key(self, client):
        bad = {**VALID_LD, "program": ""}   # empty name → validation error
        resp = client.post("/export-ld", json={"program": bad})
        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body
