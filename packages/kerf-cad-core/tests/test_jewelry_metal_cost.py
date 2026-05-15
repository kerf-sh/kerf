"""
Tests for kerf_cad_core.jewelry.metal_cost

Pure-Python: no OCC, no database, no project context required.

Covers:
  - Density table lookups
  - metal_weight math (g, dwt, ozt)
  - casting_weight with allowance
  - casting_cost itemised breakdown
  - multi_metal_compare sorted output
  - Unit conversions (dwt ↔ g, ozt ↔ g)
  - Validation errors (unknown metal, negative inputs)
  - LLM tool (run_jewelry_metal_cost) via asyncio
"""

from __future__ import annotations

import asyncio
import json
import math
import pytest

from kerf_cad_core.jewelry.metal_cost import (
    GRAMS_PER_DWT,
    GRAMS_PER_OZT,
    METAL_DENSITY_G_CM3,
    METAL_LABELS,
    MM3_PER_CM3,
    casting_cost,
    casting_weight,
    dwt_to_grams,
    grams_to_dwt,
    grams_to_ozt,
    metal_weight,
    multi_metal_compare,
    ozt_to_grams,
    resolve_density,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def approx(expected, rel=1e-4):
    """pytest.approx wrapper with relative tolerance."""
    return pytest.approx(expected, rel=rel)


def run_tool(**kwargs) -> dict:
    from kerf_cad_core.jewelry.tool_metal_cost import run_jewelry_metal_cost
    raw = asyncio.new_event_loop().run_until_complete(
        run_jewelry_metal_cost(None, json.dumps(kwargs).encode())
    )
    return json.loads(raw)


# ── Unit conversion constants ─────────────────────────────────────────────────

class TestUnitConstants:
    def test_grams_per_dwt_nist(self):
        assert GRAMS_PER_DWT == pytest.approx(1.55517384, rel=1e-6)

    def test_grams_per_ozt_nist(self):
        assert GRAMS_PER_OZT == pytest.approx(31.1034768, rel=1e-6)

    def test_mm3_per_cm3(self):
        assert MM3_PER_CM3 == 1000.0

    def test_20_dwt_equals_1_ozt(self):
        """20 pennyweights = 1 troy ounce (defining relationship)."""
        assert dwt_to_grams(20) == approx(GRAMS_PER_OZT)

    def test_grams_to_dwt_roundtrip(self):
        for g in [1.0, 5.0, 31.1034768, 100.0]:
            assert dwt_to_grams(grams_to_dwt(g)) == approx(g)

    def test_grams_to_ozt_roundtrip(self):
        for g in [1.0, 15.55, 31.1034768, 200.0]:
            assert ozt_to_grams(grams_to_ozt(g)) == approx(g)

    def test_1_ozt_in_grams(self):
        assert ozt_to_grams(1.0) == approx(31.1034768)

    def test_1_dwt_in_grams(self):
        assert dwt_to_grams(1.0) == approx(1.55517384)


# ── Density table ─────────────────────────────────────────────────────────────

class TestDensityTable:
    def test_all_keys_have_positive_density(self):
        for k, v in METAL_DENSITY_G_CM3.items():
            assert v > 0, f"{k} density must be positive"

    def test_gold_alloys_present(self):
        for k in ["10k_yellow", "14k_yellow", "18k_yellow", "22k_yellow", "24k_yellow"]:
            assert k in METAL_DENSITY_G_CM3

    def test_white_gold_present(self):
        for k in ["10k_white", "14k_white", "18k_white"]:
            assert k in METAL_DENSITY_G_CM3

    def test_rose_gold_present(self):
        for k in ["10k_rose", "14k_rose", "18k_rose"]:
            assert k in METAL_DENSITY_G_CM3

    def test_platinum_950(self):
        assert "platinum_950" in METAL_DENSITY_G_CM3
        # Should be ~21.4 g/cm³
        assert 21.0 <= METAL_DENSITY_G_CM3["platinum_950"] <= 22.0

    def test_palladium_950(self):
        assert "palladium_950" in METAL_DENSITY_G_CM3
        assert 10.0 <= METAL_DENSITY_G_CM3["palladium_950"] <= 12.0

    def test_sterling_silver(self):
        assert "sterling_925" in METAL_DENSITY_G_CM3
        assert 10.0 <= METAL_DENSITY_G_CM3["sterling_925"] <= 11.0

    def test_fine_silver(self):
        assert "fine_silver" in METAL_DENSITY_G_CM3
        assert 10.0 <= METAL_DENSITY_G_CM3["fine_silver"] <= 11.0

    def test_titanium(self):
        assert "titanium" in METAL_DENSITY_G_CM3
        assert 4.0 <= METAL_DENSITY_G_CM3["titanium"] <= 5.0

    def test_brass_bronze(self):
        for k in ["brass", "bronze"]:
            assert k in METAL_DENSITY_G_CM3
            assert 8.0 <= METAL_DENSITY_G_CM3[k] <= 9.5

    def test_24k_is_pure_gold_density(self):
        # Pure gold = 19.32 g/cm³ (NIST)
        assert METAL_DENSITY_G_CM3["24k_yellow"] == approx(19.32, rel=0.01)

    def test_karat_density_increases_with_gold_content(self):
        """Higher karat = more gold = higher density (for yellow gold)."""
        d10 = METAL_DENSITY_G_CM3["10k_yellow"]
        d14 = METAL_DENSITY_G_CM3["14k_yellow"]
        d18 = METAL_DENSITY_G_CM3["18k_yellow"]
        d22 = METAL_DENSITY_G_CM3["22k_yellow"]
        d24 = METAL_DENSITY_G_CM3["24k_yellow"]
        assert d10 < d14 < d18 < d22 < d24

    def test_all_keys_have_label(self):
        for k in METAL_DENSITY_G_CM3:
            assert k in METAL_LABELS, f"No label for metal key '{k}'"


# ── resolve_density ───────────────────────────────────────────────────────────

class TestResolveDensity:
    def test_resolve_by_metal_key(self):
        d = resolve_density(metal="14k_yellow")
        assert d == METAL_DENSITY_G_CM3["14k_yellow"]

    def test_resolve_explicit_density_overrides_metal(self):
        d = resolve_density(metal="14k_yellow", density_g_cm3=10.0)
        assert d == 10.0

    def test_resolve_explicit_density_no_metal(self):
        d = resolve_density(density_g_cm3=8.5)
        assert d == 8.5

    def test_unknown_metal_raises(self):
        with pytest.raises(ValueError, match="Unknown metal"):
            resolve_density(metal="unobtanium")

    def test_zero_density_raises(self):
        with pytest.raises(ValueError):
            resolve_density(density_g_cm3=0.0)

    def test_negative_density_raises(self):
        with pytest.raises(ValueError):
            resolve_density(density_g_cm3=-1.0)

    def test_no_args_raises(self):
        with pytest.raises(ValueError):
            resolve_density()

    def test_metal_key_case_insensitive(self):
        d = resolve_density(metal="14K_Yellow")
        assert d == METAL_DENSITY_G_CM3["14k_yellow"]


# ── metal_weight ─────────────────────────────────────────────────────────────

class TestMetalWeight:
    def test_1cm3_of_14k_yellow(self):
        """1 cm³ = 1000 mm³ of 14k yellow gold."""
        result = metal_weight(1000.0, metal="14k_yellow")
        expected_g = METAL_DENSITY_G_CM3["14k_yellow"]  # density × 1 cm³
        assert result["grams"] == approx(expected_g)

    def test_dwt_from_grams_consistent(self):
        result = metal_weight(500.0, metal="sterling_925")
        assert result["dwt"] == approx(result["grams"] / GRAMS_PER_DWT)

    def test_ozt_from_grams_consistent(self):
        result = metal_weight(500.0, metal="sterling_925")
        assert result["ozt"] == approx(result["grams"] / GRAMS_PER_OZT)

    def test_explicit_density_override(self):
        # 1 cm³ of custom 8.0 g/cm³ material
        result = metal_weight(1000.0, density_g_cm3=8.0)
        assert result["grams"] == approx(8.0)
        assert result["metal"] is None

    def test_zero_volume_raises(self):
        with pytest.raises(ValueError):
            metal_weight(0.0, metal="14k_yellow")

    def test_negative_volume_raises(self):
        with pytest.raises(ValueError):
            metal_weight(-100.0, metal="14k_yellow")

    def test_unknown_metal_raises(self):
        with pytest.raises(ValueError):
            metal_weight(1000.0, metal="kryptonite")

    def test_typical_ring_18k_yellow(self):
        """
        A typical plain 2mm band in 18k yellow gold weighs ~2–5 g depending
        on ring size. 300 mm³ volume ≈ 4.67 g.
        """
        result = metal_weight(300.0, metal="18k_yellow")
        expected = METAL_DENSITY_G_CM3["18k_yellow"] * (300.0 / 1000.0)
        assert result["grams"] == approx(expected)
        assert result["grams"] == approx(4.674, rel=0.01)

    def test_platinum_heavier_than_gold_for_same_volume(self):
        pt = metal_weight(1000.0, metal="platinum_950")
        au18 = metal_weight(1000.0, metal="18k_yellow")
        assert pt["grams"] > au18["grams"]


# ── casting_weight ────────────────────────────────────────────────────────────

class TestCastingWeight:
    def test_default_15_pct_allowance(self):
        result = casting_weight(10.0)
        assert result["gross_grams"] == approx(10.0 * 1.15)
        assert result["allowance_grams"] == approx(1.5)
        assert result["allowance_pct"] == 15.0

    def test_zero_allowance(self):
        result = casting_weight(10.0, casting_allowance_pct=0.0)
        assert result["gross_grams"] == approx(10.0)
        assert result["allowance_grams"] == approx(0.0)

    def test_20_pct_allowance(self):
        result = casting_weight(10.0, casting_allowance_pct=20.0)
        assert result["gross_grams"] == approx(12.0)

    def test_gross_dwt_consistent(self):
        result = casting_weight(10.0)
        assert result["gross_dwt"] == approx(result["gross_grams"] / GRAMS_PER_DWT)

    def test_gross_ozt_consistent(self):
        result = casting_weight(10.0)
        assert result["gross_ozt"] == approx(result["gross_grams"] / GRAMS_PER_OZT)

    def test_zero_net_grams_raises(self):
        with pytest.raises(ValueError):
            casting_weight(0.0)

    def test_negative_net_grams_raises(self):
        with pytest.raises(ValueError):
            casting_weight(-5.0)

    def test_negative_allowance_raises(self):
        with pytest.raises(ValueError):
            casting_weight(10.0, casting_allowance_pct=-1.0)


# ── casting_cost ─────────────────────────────────────────────────────────────

class TestCastingCost:
    def test_all_keys_present(self):
        result = casting_cost(1000.0, metal="14k_yellow", metal_price_per_gram=30.0,
                              labor=50.0, finishing=20.0)
        for key in ["net_grams", "net_dwt", "net_ozt", "gross_grams", "gross_dwt",
                    "gross_ozt", "metal_cost", "labor", "finishing", "total_cost",
                    "allowance_pct", "metal_price_per_gram"]:
            assert key in result, f"Missing key: {key}"

    def test_total_equals_sum_of_parts(self):
        result = casting_cost(1000.0, metal="sterling_925",
                              metal_price_per_gram=1.0, labor=40.0, finishing=10.0)
        expected = result["metal_cost"] + result["labor"] + result["finishing"]
        assert result["total_cost"] == approx(expected)

    def test_metal_cost_equals_gross_times_price(self):
        result = casting_cost(1000.0, metal="18k_yellow", metal_price_per_gram=38.0)
        assert result["metal_cost"] == approx(result["gross_grams"] * 38.0)

    def test_zero_price_gives_zero_metal_cost(self):
        result = casting_cost(1000.0, metal="platinum_950", metal_price_per_gram=0.0)
        assert result["metal_cost"] == 0.0

    def test_zero_volume_raises(self):
        with pytest.raises(ValueError):
            casting_cost(0.0, metal="14k_yellow")

    def test_negative_price_raises(self):
        with pytest.raises(ValueError):
            casting_cost(1000.0, metal="14k_yellow", metal_price_per_gram=-1.0)

    def test_negative_labor_raises(self):
        with pytest.raises(ValueError):
            casting_cost(1000.0, metal="14k_yellow", labor=-10.0)

    def test_negative_finishing_raises(self):
        with pytest.raises(ValueError):
            casting_cost(1000.0, metal="14k_yellow", finishing=-5.0)

    def test_explicit_density_accepted(self):
        result = casting_cost(1000.0, density_g_cm3=8.9, metal_price_per_gram=5.0)
        assert result["gross_grams"] > 0
        assert result["metal"] is None

    def test_casting_allowance_propagates(self):
        r10 = casting_cost(1000.0, metal="14k_yellow", casting_allowance_pct=10.0)
        r20 = casting_cost(1000.0, metal="14k_yellow", casting_allowance_pct=20.0)
        assert r20["gross_grams"] > r10["gross_grams"]

    def test_worked_example_ring_18k_yellow(self):
        """
        Example: 300 mm³ 18k yellow gold ring at $38/g, $80 labor, $20 finish.
        Net weight ≈ 4.674 g → gross ≈ 5.375 g → metal cost ≈ $204.26.
        Total ≈ $304.26.
        """
        result = casting_cost(300.0, metal="18k_yellow",
                              metal_price_per_gram=38.0, labor=80.0, finishing=20.0)
        assert result["net_grams"] == approx(4.674, rel=0.01)
        assert result["gross_grams"] == approx(4.674 * 1.15, rel=0.01)
        assert result["metal_cost"] == approx(result["gross_grams"] * 38.0, rel=1e-4)
        assert result["total_cost"] == approx(result["metal_cost"] + 80.0 + 20.0, rel=1e-4)


# ── multi_metal_compare ───────────────────────────────────────────────────────

class TestMultiMetalCompare:
    def test_returns_list(self):
        result = multi_metal_compare(1000.0)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_default_set_has_common_metals(self):
        result = multi_metal_compare(1000.0)
        metals = {r["metal"] for r in result}
        assert "14k_yellow" in metals
        assert "sterling_925" in metals
        assert "platinum_950" in metals

    def test_sorted_by_total_cost_ascending(self):
        prices = {
            "14k_yellow": 30.0, "18k_yellow": 38.0, "sterling_925": 1.0,
            "platinum_950": 55.0, "palladium_950": 20.0,
        }
        result = multi_metal_compare(1000.0, metal_prices=prices)
        costs = [r["total_cost"] for r in result]
        assert costs == sorted(costs)

    def test_custom_metal_list(self):
        result = multi_metal_compare(1000.0, metals=["brass", "bronze"])
        assert len(result) == 2
        keys = {r["metal"] for r in result}
        assert keys == {"brass", "bronze"}

    def test_each_row_has_label(self):
        result = multi_metal_compare(1000.0)
        for row in result:
            assert "label" in row
            assert row["label"]

    def test_higher_density_metal_heavier(self):
        result = multi_metal_compare(1000.0, metals=["sterling_925", "platinum_950"])
        by_metal = {r["metal"]: r for r in result}
        assert by_metal["platinum_950"]["net_grams"] > by_metal["sterling_925"]["net_grams"]

    def test_compare_prices_applied(self):
        prices = {"14k_yellow": 30.0, "sterling_925": 0.9}
        result = multi_metal_compare(
            1000.0, metals=["14k_yellow", "sterling_925"],
            metal_prices=prices,
        )
        by_metal = {r["metal"]: r for r in result}
        assert by_metal["14k_yellow"]["metal_price_per_gram"] == 30.0
        assert by_metal["sterling_925"]["metal_price_per_gram"] == 0.9

    def test_same_volume_all_rows(self):
        result = multi_metal_compare(500.0)
        for row in result:
            assert row["volume_mm3"] == 500.0


# ── LLM tool (run_jewelry_metal_cost) ────────────────────────────────────────

class TestRunJewelryMetalCost:
    def test_basic_success(self):
        result = run_tool(volume_mm3=1000.0, metal="14k_yellow")
        assert "error" not in result
        assert "estimate" in result
        assert result["estimate"]["metal"] == "14k_yellow"

    def test_estimate_net_grams_correct(self):
        result = run_tool(volume_mm3=1000.0, metal="sterling_925")
        expected = METAL_DENSITY_G_CM3["sterling_925"]  # 1 cm³
        assert result["estimate"]["net_grams"] == approx(expected)

    def test_comparison_table_returned(self):
        result = run_tool(
            volume_mm3=1000.0, metal="14k_yellow",
            compare_metals=["sterling_925", "platinum_950"],
        )
        assert "error" not in result
        assert "comparison" in result
        assert len(result["comparison"]) == 2

    def test_missing_volume_returns_bad_args(self):
        result = run_tool(metal="14k_yellow")
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_missing_metal_and_density_returns_bad_args(self):
        result = run_tool(volume_mm3=1000.0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_unknown_metal_returns_bad_args(self):
        result = run_tool(volume_mm3=1000.0, metal="unobtanium")
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_negative_volume_returns_bad_args(self):
        result = run_tool(volume_mm3=-100.0, metal="14k_yellow")
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_negative_price_returns_bad_args(self):
        result = run_tool(volume_mm3=1000.0, metal="14k_yellow",
                          metal_price_per_gram=-1.0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_negative_labor_returns_bad_args(self):
        result = run_tool(volume_mm3=1000.0, metal="14k_yellow", labor=-10.0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_explicit_density_accepted(self):
        result = run_tool(volume_mm3=1000.0, density_g_cm3=8.9)
        assert "error" not in result
        assert result["estimate"]["density_g_cm3"] == approx(8.9)

    def test_explicit_density_zero_returns_bad_args(self):
        result = run_tool(volume_mm3=1000.0, density_g_cm3=0.0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_total_cost_math(self):
        result = run_tool(
            volume_mm3=1000.0, metal="18k_yellow",
            metal_price_per_gram=38.0, labor=80.0, finishing=20.0,
        )
        est = result["estimate"]
        expected_total = est["metal_cost"] + est["labor"] + est["finishing"]
        assert est["total_cost"] == approx(expected_total)

    def test_unknown_compare_metal_returns_bad_args(self):
        result = run_tool(
            volume_mm3=1000.0, metal="14k_yellow",
            compare_metals=["xyzzy"],
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_label_in_estimate(self):
        result = run_tool(volume_mm3=1000.0, metal="18k_yellow")
        assert "label" in result["estimate"]
        assert "18k" in result["estimate"]["label"].lower() or "yellow" in result["estimate"]["label"].lower()

    def test_invalid_json_returns_bad_args(self):
        from kerf_cad_core.jewelry.tool_metal_cost import run_jewelry_metal_cost
        raw = asyncio.new_event_loop().run_until_complete(
            run_jewelry_metal_cost(None, b"not-json{{{")
        )
        r = json.loads(raw)
        assert "error" in r
        assert r.get("code") == "BAD_ARGS"

    def test_plugin_registers_module(self):
        """plugin._TOOL_MODULES includes jewelry tool."""
        import importlib.util
        spec_path = (
            "/Users/pc/code/exo/kerf/packages/kerf-cad-core/src/kerf_cad_core/plugin.py"
        )
        spec = importlib.util.spec_from_file_location("plugin_check", spec_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert "kerf_cad_core.jewelry.tool_metal_cost" in mod._TOOL_MODULES
