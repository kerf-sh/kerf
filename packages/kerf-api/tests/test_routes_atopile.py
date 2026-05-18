"""Tests for POST /atopile/compile (T-196).

All tests are hermetic — no DB, no external processes.  We mount only the
atopile router on a bare FastAPI app and exercise the compile endpoint
directly via TestClient.

Run:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-electronics/src:packages/kerf-api/src \\
        python3 -m pytest packages/kerf-api/tests/test_routes_atopile.py -x
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# sys.path bootstrap (mirrors conftest.py so we can also run standalone)
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).parent
_PACKAGES_ROOT = _HERE.parent.parent

for _entry in _PACKAGES_ROOT.iterdir():
    if not _entry.name.startswith("kerf-"):
        continue
    _src = _entry / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

# ---------------------------------------------------------------------------
# Test app — bare FastAPI with only the atopile router
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    from kerf_api.routes_atopile import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture(scope="module")
def client():
    app = _build_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Sample .ato source — a simple LED driver with a resistor
# ---------------------------------------------------------------------------

SAMPLE_ATO = """
module LedDriver:
    r1 = new Resistor
    d1 = new LED

    r1.A ~ d1.A
    r1.B ~ d1.B

    signal VCC
    signal GND
"""

MINIMAL_ATO = """
module Blinker:
    r1 = new Resistor
"""

COMPONENT_WITH_VALUES_ATO = """
component Resistor:
    signal A
    signal B
    resistance = 10kohm

module TopLevel:
    r1 = new Resistor
    r2 = new Resistor
    r1.A ~ r2.A
"""

MULTI_MODULE_ATO = """
component Cap:
    signal pos
    signal neg
    capacitance = 100nF

module Filter:
    c1 = new Cap
    c2 = new Cap

module Amp:
    r1 = new Resistor
"""


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestCompileHappyPath:
    def test_compile_sample_returns_ok(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert isinstance(body["circuit"], list)

    def test_compile_returns_source_components(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        assert r.status_code == 200
        circuit = r.json()["circuit"]
        types = {el["type"] for el in circuit}
        assert "source_component" in types, f"no source_component in {types}"

    def test_compile_returns_source_ports(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        types = {el["type"] for el in circuit}
        assert "source_port" in types, f"no source_port in {types}"

    def test_compile_connections_become_source_traces(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        traces = [el for el in circuit if el["type"] == "source_trace"]
        assert len(traces) >= 1, "expected at least one source_trace from r1.A ~ d1.A"

    def test_compile_signals_become_source_nets(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        nets = [el for el in circuit if el["type"] == "source_net"]
        # SAMPLE_ATO has `signal VCC` and `signal GND`
        assert len(nets) >= 2, f"expected VCC/GND nets, got {nets}"

    def test_compile_minimal_module(self, client):
        r = client.post("/atopile/compile", json={"source": MINIMAL_ATO})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        circuit = body["circuit"]
        comps = [el for el in circuit if el["type"] == "source_component"]
        assert len(comps) == 1
        assert comps[0]["name"] == "r1"

    def test_compile_with_explicit_top_module(self, client):
        r = client.post(
            "/atopile/compile",
            json={"source": MULTI_MODULE_ATO, "module": "Filter"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        circuit = body["circuit"]
        # Only Filter's instances should be emitted
        comps = [el for el in circuit if el["type"] == "source_component"]
        names = [c["name"] for c in comps]
        assert "c1" in names and "c2" in names, f"unexpected comps: {names}"
        # r1 from Amp must NOT be in this compile run
        assert "r1" not in names, f"Amp's r1 leaked into Filter compile: {names}"

    def test_compile_component_values_propagated(self, client):
        r = client.post("/atopile/compile", json={"source": COMPONENT_WITH_VALUES_ATO})
        assert r.status_code == 200
        circuit = r.json()["circuit"]
        # r1 should be a source_component with resistance = 10000 (10kohm)
        comps = [el for el in circuit if el["type"] == "source_component"]
        r1 = next((c for c in comps if c["name"] == "r1"), None)
        assert r1 is not None, f"r1 not found in comps: {comps}"
        assert r1.get("resistance") == pytest.approx(10000.0), (
            f"r1.resistance should be 10000 (10kohm), got {r1.get('resistance')}"
        )

    def test_compile_source_trace_references_valid_port_ids(self, client):
        r = client.post("/atopile/compile", json={"source": COMPONENT_WITH_VALUES_ATO})
        circuit = r.json()["circuit"]
        port_ids = {el["source_port_id"] for el in circuit if el["type"] == "source_port"}
        for trace in circuit:
            if trace["type"] != "source_trace":
                continue
            for pid in trace["connected_source_port_ids"]:
                assert pid in port_ids, (
                    f"source_trace references unknown port_id {pid}; "
                    f"known ids: {sorted(port_ids)}"
                )

    def test_compile_circuit_json_is_serialisable(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        # If we can round-trip via JSON it's valid for the frontend
        assert json.loads(json.dumps(circuit)) == circuit

    def test_compile_warnings_field_is_list(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        body = r.json()
        assert isinstance(body.get("warnings"), list)

    def test_compile_unknown_top_module_falls_back_with_warning(self, client):
        r = client.post(
            "/atopile/compile",
            json={"source": SAMPLE_ATO, "module": "NonExistent"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # Should have a warning about the fallback
        assert any("NonExistent" in w for w in body.get("warnings", [])), (
            f"expected fallback warning in {body.get('warnings')}"
        )


# ---------------------------------------------------------------------------
# Error / validation tests
# ---------------------------------------------------------------------------

class TestCompileErrors:
    def test_missing_source_returns_422(self, client):
        r = client.post("/atopile/compile", json={})
        assert r.status_code == 422

    def test_empty_source_returns_400(self, client):
        r = client.post("/atopile/compile", json={"source": ""})
        assert r.status_code == 400

    def test_whitespace_only_source_returns_400(self, client):
        r = client.post("/atopile/compile", json={"source": "   \n  "})
        assert r.status_code == 400

    def test_no_module_declaration_returns_error(self, client):
        # Valid Python-ish text but no atopile module/component keyword
        r = client.post(
            "/atopile/compile",
            json={"source": "x = 1\ny = 2\n"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert isinstance(body.get("errors"), list)
        assert len(body["errors"]) >= 1


# ---------------------------------------------------------------------------
# Circuit JSON shape contract tests
# ---------------------------------------------------------------------------

class TestCircuitJsonShape:
    def test_source_component_has_required_fields(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        for el in circuit:
            if el["type"] == "source_component":
                assert "source_component_id" in el
                assert "name" in el
                assert "ftype" in el

    def test_source_port_has_required_fields(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        for el in circuit:
            if el["type"] == "source_port":
                assert "source_port_id" in el
                assert "source_component_id" in el
                assert "name" in el
                assert "pin_type" in el

    def test_source_trace_has_connected_port_ids(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        for el in circuit:
            if el["type"] == "source_trace":
                assert "source_trace_id" in el
                assert "connected_source_port_ids" in el
                assert isinstance(el["connected_source_port_ids"], list)

    def test_source_net_has_required_fields(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        for el in circuit:
            if el["type"] == "source_net":
                assert "source_net_id" in el
                assert "name" in el
                assert "member_source_port_ids" in el

    def test_led_guessed_as_simple_led(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        comps = [el for el in circuit if el["type"] == "source_component"]
        d1 = next((c for c in comps if c["name"] == "d1"), None)
        assert d1 is not None
        assert d1["ftype"] == "simple_led"

    def test_resistor_guessed_as_simple_resistor(self, client):
        r = client.post("/atopile/compile", json={"source": SAMPLE_ATO})
        circuit = r.json()["circuit"]
        comps = [el for el in circuit if el["type"] == "source_component"]
        r1 = next((c for c in comps if c["name"] == "r1"), None)
        assert r1 is not None
        assert r1["ftype"] == "simple_resistor"

    def test_capacitor_guessed_as_simple_capacitor(self, client):
        source = "module T:\n    c1 = new Capacitor\n"
        r = client.post("/atopile/compile", json={"source": source})
        circuit = r.json()["circuit"]
        comps = [el for el in circuit if el["type"] == "source_component"]
        c1 = next((c for c in comps if c["name"] == "c1"), None)
        assert c1 is not None
        assert c1["ftype"] == "simple_capacitor"


# ---------------------------------------------------------------------------
# Comments and edge-case source parsing
# ---------------------------------------------------------------------------

class TestSourceEdgeCases:
    def test_comments_are_ignored(self, client):
        source = """
# This is a top-level comment
module Commented:
    # r1 is the bias resistor
    r1 = new Resistor  # inline comment
    signal A  # net A
"""
        r = client.post("/atopile/compile", json={"source": source})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        comps = [el for el in body["circuit"] if el["type"] == "source_component"]
        assert len(comps) == 1
        assert comps[0]["name"] == "r1"

    def test_import_statement_does_not_crash_parser(self, client):
        source = """
import Resistor from "generics/resistors.ato"

module WithImport:
    r1 = new Resistor
"""
        r = client.post("/atopile/compile", json={"source": source})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True

    def test_value_assignment_with_nf_unit(self, client):
        source = """
component MyCapacitor:
    signal pos
    signal neg
    capacitance = 100nF

module Test:
    c1 = new MyCapacitor
"""
        r = client.post("/atopile/compile", json={"source": source})
        assert r.status_code == 200
        circuit = r.json()["circuit"]
        comps = [el for el in circuit if el["type"] == "source_component"]
        c1 = next((c for c in comps if c["name"] == "c1"), None)
        assert c1 is not None
        # 100nF = 100e-9 = 1e-7
        assert c1.get("capacitance") == pytest.approx(1e-7, rel=1e-3)

    def test_multiple_connections(self, client):
        source = """
module Chain:
    r1 = new Resistor
    r2 = new Resistor
    r3 = new Resistor
    r1.B ~ r2.A
    r2.B ~ r3.A
    signal IN
    signal OUT
"""
        r = client.post("/atopile/compile", json={"source": source})
        assert r.status_code == 200
        circuit = r.json()["circuit"]
        traces = [el for el in circuit if el["type"] == "source_trace"]
        # r1.B ~ r2.A and r2.B ~ r3.A → 2 traces (r1/r2/r3 have standard A/B pins)
        assert len(traces) >= 2, f"expected 2+ traces, got {len(traces)}"
