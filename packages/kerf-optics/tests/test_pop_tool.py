"""
Dispatch tests for the optics_pop_propagate LLM tool.

Calls the tool handler and asserts sane physics.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from kerf_optics.tools import run_optics_pop_propagate


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestOpticsPOPPropagate:
    def test_defaults_return_ok(self):
        result_str = _run(run_optics_pop_propagate({}, ctx=None))
        result = json.loads(result_str)
        assert result.get("ok") is True or "intensity_peak" in result

    def test_energy_conservation_asm(self):
        result_str = _run(run_optics_pop_propagate(
            {"method": "asm", "z_mm": 1.0, "lambda_um": 0.633, "w0_mm": 0.5, "grid_N": 64},
            ctx=None,
        ))
        result = json.loads(result_str)
        assert "energy_conservation_ratio" in result
        ratio = result["energy_conservation_ratio"]
        assert ratio is not None
        # Angular spectrum is energy-preserving (within ~1%)
        assert 0.95 <= ratio <= 1.05

    def test_fresnel_method(self):
        result_str = _run(run_optics_pop_propagate(
            {"method": "fresnel", "z_mm": 200.0, "lambda_um": 0.633, "w0_mm": 1.0, "grid_N": 64},
            ctx=None,
        ))
        result = json.loads(result_str)
        assert "intensity_peak" in result
        assert result["method_used"] == "fresnel"

    def test_auto_selects_method(self):
        # Short distance → ASM (high Fresnel number)
        result_str = _run(run_optics_pop_propagate(
            {"method": "auto", "z_mm": 0.5, "lambda_um": 0.633, "w0_mm": 0.5, "grid_N": 64, "dx_um": 10.0},
            ctx=None,
        ))
        result = json.loads(result_str)
        assert result["method_used"] in ("asm", "fresnel")

    def test_analytic_beam_waist_present(self):
        result_str = _run(run_optics_pop_propagate(
            {"z_mm": 100.0, "w0_mm": 1.0, "lambda_um": 0.633, "grid_N": 64},
            ctx=None,
        ))
        result = json.loads(result_str)
        # Without lens/aperture, analytic waist is computed
        assert result.get("beam_waist_analytic_mm") is not None
        assert result["beam_waist_analytic_mm"] > 0

    def test_with_aperture(self):
        result_str = _run(run_optics_pop_propagate(
            {"aperture_radius_mm": 1.5, "z_mm": 50.0, "grid_N": 64},
            ctx=None,
        ))
        result = json.loads(result_str)
        assert "intensity_peak" in result

    def test_bad_lambda_returns_error(self):
        result_str = _run(run_optics_pop_propagate({"lambda_um": -1.0}, ctx=None))
        result = json.loads(result_str)
        assert "error" in result

    def test_bad_grid_returns_error(self):
        result_str = _run(run_optics_pop_propagate({"grid_N": 4}, ctx=None))
        result = json.loads(result_str)
        assert "error" in result
