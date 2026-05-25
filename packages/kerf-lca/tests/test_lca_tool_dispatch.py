"""
test_lca_tool_dispatch.py — dispatch tests for the lifecycle_phases and multi_impact LLM tools.

Verifies that the two tools that were previously orphaned (not registered in
plugin.py) have their ToolSpec + async handler wired and callable.

No network / DB I/O — all calculation is pure Python.
"""
from __future__ import annotations

import asyncio
import json
import types
import uuid

import pytest


def run(coro):
    return asyncio.run(coro)


def _make_ctx():
    ctx = types.SimpleNamespace()
    ctx.project_id = uuid.uuid4()
    ctx.pool = None
    ctx.storage = None
    return ctx


# ---------------------------------------------------------------------------
# lifecycle_phases tool
# ---------------------------------------------------------------------------

class TestLifecyclePhasesToolDispatch:
    def _get(self):
        try:
            from kerf_lca.tools.lifecycle_phases import lifecycle_phases_spec, run_lifecycle_phases
            return lifecycle_phases_spec, run_lifecycle_phases
        except ImportError:
            pytest.skip("kerf_chat unavailable")

    def test_spec_name(self):
        spec, _ = self._get()
        assert spec.name == "lifecycle_phases"

    def test_missing_product_returns_error(self):
        spec, handler = self._get()
        ctx = _make_ctx()
        result = run(handler(ctx, b"{}"))
        data = json.loads(result)
        assert data.get("ok") is not True

    def test_product_only_returns_ok(self):
        """With only 'product' provided (no use_phase/transport/eol), should still succeed."""
        spec, handler = self._get()
        ctx = _make_ctx()
        payload = json.dumps({"product": "bracket", "cradle_to_gate_gwp": 5.0}).encode()
        result = run(handler(ctx, payload))
        data = json.loads(result)
        # ok_payload wraps in {"ok": True, "result": ...} (kerf_chat) or returns dict directly (_compat)
        assert data.get("ok") is not False, f"unexpected error: {data}"
        assert "error" not in data or data.get("ok") is True
        inner = data.get("result", data)
        assert "total_gwp_kg_co2_eq" in inner

    def test_full_lifecycle_returns_phases(self):
        spec, handler = self._get()
        ctx = _make_ctx()
        payload = json.dumps({
            "product": "bracket",
            "cradle_to_gate_gwp": 5.0,
            "use_phase": {"lifetime_years": 10, "annual_energy_kWh": 100, "region": "EU"},
            "transport": {"mass_kg": 2.0, "distance_km": 500, "mode": "truck"},
            "eol": {"mass_kg": 2.0, "scenario": "recycle"},
        }).encode()
        result = run(handler(ctx, payload))
        data = json.loads(result)
        assert data.get("ok") is not False, f"unexpected error: {data}"
        inner = data.get("result", data)
        assert "phases" in inner
        assert inner["total_gwp_kg_co2_eq"] > 0


# ---------------------------------------------------------------------------
# multi_impact tool
# ---------------------------------------------------------------------------

class TestMultiImpactToolDispatch:
    def _get(self):
        try:
            from kerf_lca.tools.multi_impact import multi_impact_spec, run_multi_impact
            return multi_impact_spec, run_multi_impact
        except ImportError:
            pytest.skip("kerf_chat unavailable")

    def test_spec_name(self):
        spec, _ = self._get()
        assert spec.name == "multi_impact"

    def test_missing_breakdown_returns_error(self):
        spec, handler = self._get()
        ctx = _make_ctx()
        result = run(handler(ctx, b"{}"))
        data = json.loads(result)
        assert data.get("ok") is not True

    def test_steel_breakdown_returns_impacts(self):
        spec, handler = self._get()
        ctx = _make_ctx()
        payload = json.dumps({
            "product_breakdown": [
                {"material_id": "steel_generic", "mass_kg": 10.0},
            ]
        }).encode()
        result = run(handler(ctx, payload))
        data = json.loads(result)
        # ok_payload returns {"ok": True, "result": ...} or raw dict depending on shim
        assert data.get("ok") is not False, f"unexpected error: {data}"
        inner = data.get("result", data)
        assert "impacts" in inner
        assert "gwp100" in inner["impacts"]
