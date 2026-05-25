"""
Dispatch tests for the piping_pipe_spec_check LLM tool.

Calls the handler and asserts sane ASME B31.3 compliance payload.
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

from kerf_piping.tools import run_piping_pipe_spec_check


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestPipingPipeSpecCheck:
    def test_compliant_pipe(self):
        """DN100 Sch40 A106-B at 10 barg, 120°C should comply."""
        result_str = _run(run_piping_pipe_spec_check(
            {
                "dn": 100,
                "schedule": "40",
                "design_pressure_barg": 10.0,
                "design_temp_c": 120.0,
                "material_spec": "A106",
                "material_grade": "B",
            },
            ctx=None,
        ))
        result = json.loads(result_str)
        assert result.get("ok") is True
        assert result["dn"] == 100
        assert result["schedule"] == "40"
        assert result["actual_wall_mm"] > 0.0
        assert result["min_required_wall_mm"] > 0.0

    def test_noncompliant_over_pressure(self):
        """DN50 Sch40 at very high pressure should fail compliance."""
        result_str = _run(run_piping_pipe_spec_check(
            {
                "dn": 50,
                "schedule": "40",
                "design_pressure_barg": 500.0,  # way too high
                "design_temp_c": 100.0,
                "material_spec": "A106",
                "material_grade": "B",
                "class_pressure_barg": 500.0,
            },
            ctx=None,
        ))
        result = json.loads(result_str)
        assert result.get("ok") is True
        # Should not be compliant at 500 barg
        assert result["compliant"] is False
        assert len(result["violations"]) > 0

    def test_violations_field_present(self):
        result_str = _run(run_piping_pipe_spec_check(
            {"dn": 80, "schedule": "80", "design_pressure_barg": 20.0, "design_temp_c": 150.0},
            ctx=None,
        ))
        result = json.loads(result_str)
        assert result.get("ok") is True
        assert "violations" in result
        assert "warnings" in result

    def test_stainless_material(self):
        result_str = _run(run_piping_pipe_spec_check(
            {
                "dn": 50,
                "schedule": "40",
                "design_pressure_barg": 15.0,
                "design_temp_c": 200.0,
                "material_spec": "A312",
                "material_grade": "316L",
            },
            ctx=None,
        ))
        result = json.loads(result_str)
        assert result.get("ok") is True
        assert result["material_spec"] == "A312"

    def test_api5l_material(self):
        result_str = _run(run_piping_pipe_spec_check(
            {
                "dn": 200,
                "schedule": "STD",
                "design_pressure_barg": 50.0,
                "design_temp_c": 80.0,
                "material_spec": "API5L",
                "material_grade": "X52",
            },
            ctx=None,
        ))
        result = json.loads(result_str)
        assert result.get("ok") is True

    def test_bad_material_returns_error(self):
        result_str = _run(run_piping_pipe_spec_check(
            {
                "dn": 50,
                "schedule": "40",
                "design_pressure_barg": 10.0,
                "design_temp_c": 100.0,
                "material_spec": "BADSPEC",
                "material_grade": "ZZZ",
            },
            ctx=None,
        ))
        result = json.loads(result_str)
        assert "error" in result

    def test_permitted_dn_restriction(self):
        """DN50 not in permitted list [100, 150] → violation."""
        result_str = _run(run_piping_pipe_spec_check(
            {
                "dn": 50,
                "schedule": "40",
                "design_pressure_barg": 10.0,
                "design_temp_c": 120.0,
                "permitted_dn": [100, 150],
            },
            ctx=None,
        ))
        result = json.loads(result_str)
        assert result.get("ok") is True
        assert result["compliant"] is False
