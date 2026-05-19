"""Hermetic tests for POST /api/silicon/synth (Yosys RTL synthesis).

The tests cover:
  - Route shape: 200 on success, 503 if Yosys absent, 422 on bad input.
  - When Yosys is absent the route returns {status:"pending"} with 503.
  - When Yosys is present, a minimal AND gate synthesises correctly.

No DB, no network.
"""
from __future__ import annotations

import shutil
import unittest.mock as mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kerf_api.routes_silicon_synth import router


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


SIMPLE_AND_VERILOG = """\
module and2(input a, input b, output y);
  assign y = a & b;
endmodule
"""

SIMPLE_COUNTER_VERILOG = """\
module counter4(
  input  clk,
  input  rst,
  output reg [3:0] count
);
  always @(posedge clk or posedge rst) begin
    if (rst)
      count <= 4'b0000;
    else
      count <= count + 1;
  end
endmodule
"""


# ===========================================================================
# Tests when Yosys is NOT installed (expected on CI without Yosys)
# ===========================================================================

class TestSiliconSynthNoYosys:

    def test_pending_503_when_yosys_absent(self, client):
        """When yosys binary not found → 503 with status=pending."""
        with mock.patch("kerf_api.routes_silicon_synth._yosys_binary", return_value=None):
            r = client.post("/api/silicon/synth", json={"verilog": SIMPLE_AND_VERILOG})
        assert r.status_code == 503
        body = r.json()
        assert body.get("status") == "pending"
        assert "reason" in body

    def test_pending_reason_mentions_yosys(self, client):
        """Pending reason message mentions yosys."""
        with mock.patch("kerf_api.routes_silicon_synth._yosys_binary", return_value=None):
            r = client.post("/api/silicon/synth", json={"verilog": SIMPLE_AND_VERILOG})
        body = r.json()
        reason = body.get("reason", "").lower()
        assert "yosys" in reason

    def test_missing_verilog_returns_422(self, client):
        """Missing 'verilog' field → 422 (Pydantic validation)."""
        r = client.post("/api/silicon/synth", json={})
        assert r.status_code == 422

    def test_empty_verilog_returns_422(self, client):
        """Empty string verilog → 422 (min_length=1 constraint)."""
        r = client.post("/api/silicon/synth", json={"verilog": ""})
        assert r.status_code == 422

    def test_optional_top_field_accepted(self, client):
        """top parameter is optional; can be omitted."""
        with mock.patch("kerf_api.routes_silicon_synth._yosys_binary", return_value=None):
            r = client.post("/api/silicon/synth", json={
                "verilog": SIMPLE_AND_VERILOG,
                # top omitted
            })
        # Either 503 (no yosys) or 200 (yosys present) — not a 422
        assert r.status_code in (200, 503)

    def test_optional_top_field_accepted_when_set(self, client):
        """top parameter is accepted when explicitly set."""
        with mock.patch("kerf_api.routes_silicon_synth._yosys_binary", return_value=None):
            r = client.post("/api/silicon/synth", json={
                "verilog": SIMPLE_AND_VERILOG,
                "top": "and2",
            })
        assert r.status_code in (200, 503)

    def test_flatten_flag_accepted(self, client):
        """flatten:false is a valid request."""
        with mock.patch("kerf_api.routes_silicon_synth._yosys_binary", return_value=None):
            r = client.post("/api/silicon/synth", json={
                "verilog": SIMPLE_AND_VERILOG,
                "flatten": False,
            })
        assert r.status_code in (200, 503)


# ===========================================================================
# Tests when Yosys IS installed (skipped if absent)
# ===========================================================================

@pytest.mark.skipif(
    shutil.which("yosys") is None,
    reason="yosys binary not in PATH — skipping live synthesis tests",
)
class TestSiliconSynthWithYosys:

    def test_and_gate_synthesises_200(self, client):
        """Simple AND gate synthesises without error."""
        r = client.post("/api/silicon/synth", json={
            "verilog": SIMPLE_AND_VERILOG,
            "top": "and2",
        })
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True

    def test_gate_count_present(self, client):
        """gate_count dict is included in the response."""
        r = client.post("/api/silicon/synth", json={
            "verilog": SIMPLE_AND_VERILOG,
            "top": "and2",
        })
        body = r.json()
        assert "gate_count" in body
        assert isinstance(body["gate_count"], dict)

    def test_netlist_present(self, client):
        """netlist field is a dict."""
        r = client.post("/api/silicon/synth", json={
            "verilog": SIMPLE_AND_VERILOG,
            "top": "and2",
        })
        body = r.json()
        assert "netlist" in body
        assert isinstance(body["netlist"], dict)

    def test_liberty_mapped_false_without_liberty(self, client):
        """liberty_mapped=False when no liberty provided."""
        r = client.post("/api/silicon/synth", json={
            "verilog": SIMPLE_AND_VERILOG,
            "top": "and2",
        })
        body = r.json()
        assert body.get("liberty_mapped") is False

    def test_counter_synthesises_200(self, client):
        """4-bit counter synthesises successfully."""
        r = client.post("/api/silicon/synth", json={
            "verilog": SIMPLE_COUNTER_VERILOG,
            "top": "counter4",
        })
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_invalid_verilog_returns_422(self, client):
        """Syntactically invalid Verilog → 422."""
        r = client.post("/api/silicon/synth", json={
            "verilog": "this is not valid verilog !!@#$",
        })
        assert r.status_code == 422
        body = r.json()
        assert body.get("ok") is False
