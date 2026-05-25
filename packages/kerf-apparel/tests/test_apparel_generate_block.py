"""
Dispatch tests for apparel_generate_block LLM tool.
"""

from __future__ import annotations

import asyncio
import json
import pytest

from kerf_apparel.tools import generate_block_spec, run_generate_block


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Ctx:
    pass


CTX = _Ctx()


def _call(args: dict) -> dict:
    return json.loads(_run(run_generate_block(CTX, json.dumps(args).encode())))


# ---------------------------------------------------------------------------
# Spec sanity
# ---------------------------------------------------------------------------

class TestSpec:
    def test_name(self):
        assert generate_block_spec.name == "apparel_generate_block"

    def test_all_blocks_in_enum(self):
        blocks = generate_block_spec.input_schema["properties"]["block"]["enum"]
        for b in ("bodice_front", "bodice_back", "sleeve", "pants_front", "pants_back"):
            assert b in blocks


# ---------------------------------------------------------------------------
# Standard size path
# ---------------------------------------------------------------------------

class TestStandardSize:
    def test_bodice_front_size_m(self):
        result = _call({"block": "bodice_front", "size": "M"})
        assert "error" not in result
        assert len(result["outline"]) >= 4
        assert result["area_cm2"] > 0
        assert result["bounding_box_cm"]["width"] > 0

    def test_sleeve_size_l(self):
        result = _call({"block": "sleeve", "size": "L"})
        assert "error" not in result
        assert result["area_cm2"] > 0

    def test_pants_front_size_s(self):
        result = _call({"block": "pants_front", "size": "S"})
        assert "error" not in result
        assert result["area_cm2"] > 0

    def test_pants_back_size_m(self):
        result = _call({"block": "pants_back", "size": "M"})
        assert "error" not in result

    def test_numeric_us_size_12(self):
        result = _call({"block": "bodice_front", "size": "12"})
        assert "error" not in result
        assert result["size"] == "12"

    def test_invalid_size_returns_error(self):
        result = _call({"block": "bodice_front", "size": "XXXL"})
        assert "error" in result

    def test_grain_line_present(self):
        result = _call({"block": "bodice_front", "size": "M"})
        assert result["grain_line"] is not None
        assert len(result["grain_line"]) == 2


# ---------------------------------------------------------------------------
# Custom measurement path
# ---------------------------------------------------------------------------

class TestCustomMeasurements:
    def test_bodice_front_custom_measurements(self):
        result = _call({
            "block": "bodice_front",
            "bust": 88.0, "waist": 70.0, "hip": 94.0, "back_length": 42.0,
        })
        assert "error" not in result
        assert result["size"] == "custom"
        assert result["labels"]["bust"] == 88.0

    def test_custom_ease_applied(self):
        result_default = _call({
            "block": "bodice_front",
            "bust": 88.0, "waist": 70.0, "hip": 94.0, "back_length": 42.0,
        })
        result_tight = _call({
            "block": "bodice_front",
            "bust": 88.0, "waist": 70.0, "hip": 94.0, "back_length": 42.0,
            "ease_bust": 0.0, "ease_waist": 0.0, "ease_hip": 0.0,
        })
        # Default ease → wider block
        assert result_default["bounding_box_cm"]["width"] > result_tight["bounding_box_cm"]["width"]

    def test_missing_measurement_returns_error(self):
        # sleeve needs sleeve_length
        result = _call({
            "block": "sleeve",
            "bust": 88.0,
            # missing sleeve_length
        })
        assert "error" in result


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestErrors:
    def test_unknown_block_returns_error(self):
        result = _call({"block": "jacket"})
        assert "error" in result

    def test_missing_block_returns_error(self):
        result = _call({"size": "M"})
        assert "error" in result
