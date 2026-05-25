"""
Dispatch tests for the textiles_cloth_drape LLM tool.

Calls the tool handler directly and asserts a sane payload.
"""

from __future__ import annotations

import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from kerf_textiles.tools import run_textiles_cloth_drape


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestTextilesDrapeTool:
    def test_sphere_mode_defaults(self):
        result = _run(run_textiles_cloth_drape({"mode": "sphere", "steps": 500}))
        assert result.get("ok") is True
        assert result["mode"] == "sphere"
        assert isinstance(result["no_penetration"], bool)
        assert isinstance(result["energy_plateau"], bool)
        assert result["steps_taken"] > 0

    def test_disc_mode(self):
        result = _run(run_textiles_cloth_drape({"mode": "disc", "steps": 400}))
        assert result.get("ok") is True
        assert result["mode"] == "disc"
        dc = result.get("drape_coefficient")
        # DC is either None or in [0, 1]
        if dc is not None:
            assert 0.0 <= dc <= 1.0
        assert result["max_sag_m"] >= 0.0

    def test_free_mode(self):
        result = _run(run_textiles_cloth_drape({"mode": "free", "cloth_size": 0.5, "steps": 300}))
        assert result.get("ok") is True
        assert result["mode"] == "free"
        assert result["max_sag_m"] >= 0.0

    def test_bad_mode_returns_error(self):
        result = _run(run_textiles_cloth_drape({"mode": "parachute"}))
        assert result.get("ok") is False
        assert "error" in result

    def test_default_mode_is_sphere(self):
        result = _run(run_textiles_cloth_drape({"steps": 200}))
        assert result.get("ok") is True
        assert result["mode"] == "sphere"
