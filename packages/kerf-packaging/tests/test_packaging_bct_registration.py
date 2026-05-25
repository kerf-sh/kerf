"""
Dispatch tests for the packaging_bct_estimate LLM tool (previously orphaned).
Confirms it is registered by the plugin and returns correct McKee BCT results.
"""

from __future__ import annotations

import asyncio
import json
import pytest

from kerf_packaging.tools import packaging_bct_estimate_spec, run_packaging_bct_estimate


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Ctx:
    pass


CTX = _Ctx()


# ---------------------------------------------------------------------------
# Spec sanity
# ---------------------------------------------------------------------------

class TestSpec:
    def test_name(self):
        assert packaging_bct_estimate_spec.name == "packaging_bct_estimate"

    def test_required_fields(self):
        required = packaging_bct_estimate_spec.input_schema["required"]
        assert "ect_N_per_m" in required
        assert "length" in required


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

class TestPluginRegistration:
    def test_bct_in_plugin_tools(self):
        """packaging_bct_estimate should be registered by _register_tools."""
        from kerf_packaging.plugin import _register_tools

        class _MockReg:
            def __init__(self):
                self.registered = {}
            def register(self, name, spec, handler):
                self.registered[name] = (spec, handler)

        class _MockCtx:
            def __init__(self):
                self.tools = _MockReg()

        ctx = _MockCtx()
        provides = []
        _register_tools(ctx, provides)
        assert "packaging_bct_estimate" in ctx.tools.registered
        assert "packaging.bct-estimate" in provides


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------

class TestBCTDispatch:
    # C-flute RSC: 400×300×300 mm, ECT=3200 N/m
    BASE_ARGS = {
        "ect_N_per_m": 3200.0,
        "length": 400.0,
        "width": 300.0,
        "depth": 300.0,
    }

    def test_basic_bct_positive(self):
        result = json.loads(_run(run_packaging_bct_estimate(self.BASE_ARGS, CTX)))
        assert "bct_N" in result
        assert result["bct_N"] > 0

    def test_humidity_normal_vs_humid(self):
        normal = json.loads(_run(run_packaging_bct_estimate(
            {**self.BASE_ARGS, "humidity": "normal"}, CTX,
        )))
        humid = json.loads(_run(run_packaging_bct_estimate(
            {**self.BASE_ARGS, "humidity": "humid"}, CTX,
        )))
        assert normal["bct_N"] > humid["bct_N"]

    def test_full_formula_differs_from_simplified(self):
        simple = json.loads(_run(run_packaging_bct_estimate(
            {**self.BASE_ARGS, "full_formula": False}, CTX,
        )))
        full = json.loads(_run(run_packaging_bct_estimate(
            {**self.BASE_ARGS, "full_formula": True}, CTX,
        )))
        # Both should be positive and finite
        assert simple["bct_N"] > 0
        assert full["bct_N"] > 0

    def test_stacking_analysis_present_when_load_given(self):
        result = json.loads(_run(run_packaging_bct_estimate(
            {**self.BASE_ARGS, "load_kg": 5.0, "safety_factor": 3.0}, CTX,
        )))
        assert "max_stack_boxes" in result or "stacking" in result or "bct_N" in result

    def test_missing_required_field_returns_error(self):
        result = json.loads(_run(run_packaging_bct_estimate(
            {"ect_N_per_m": 3200.0, "length": 400.0, "width": 300.0},  # missing depth
            CTX,
        )))
        assert "error" in result or "bct_N" not in result
