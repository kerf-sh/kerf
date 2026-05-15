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
    CARATS_PER_GRAM,
    DEFAULT_FINISHING_COST,
    DEFAULT_SETTING_FEE_PER_STONE,
    FINISHING_TYPES,
    GRAMS_PER_DWT,
    GRAMS_PER_OZT,
    METAL_DENSITY_G_CM3,
    METAL_FINENESS_LABEL,
    METAL_HALLMARK,
    METAL_LABELS,
    METAL_PRICE_PRESETS,
    MM3_PER_CM3,
    SETTING_TYPES,
    casting_cost,
    casting_weight,
    dwt_to_grams,
    grams_to_dwt,
    grams_to_ozt,
    jewelry_quote,
    labour_cost,
    metal_weight,
    mm_to_carat,
    multi_metal_compare,
    ozt_to_grams,
    resolve_density,
    stone_cost_line_items,
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


# ── Extended alloys + hallmarks ───────────────────────────────────────────────

class TestExtendedAlloys:
    def test_22k_white_present(self):
        assert "22k_white" in METAL_DENSITY_G_CM3
        assert METAL_DENSITY_G_CM3["22k_white"] > 17.0

    def test_22k_rose_present(self):
        assert "22k_rose" in METAL_DENSITY_G_CM3
        assert METAL_DENSITY_G_CM3["22k_rose"] > 17.0

    def test_platinum_900_present(self):
        assert "platinum_900" in METAL_DENSITY_G_CM3
        assert 21.0 <= METAL_DENSITY_G_CM3["platinum_900"] <= 22.0
        # Pt900 lighter than Pt950 (less platinum, more iridium)
        assert METAL_DENSITY_G_CM3["platinum_900"] <= METAL_DENSITY_G_CM3["platinum_950"]

    def test_palladium_500_present(self):
        assert "palladium_500" in METAL_DENSITY_G_CM3
        assert 10.0 <= METAL_DENSITY_G_CM3["palladium_500"] <= 11.5

    def test_argentium_935_present(self):
        assert "argentium_935" in METAL_DENSITY_G_CM3
        assert 10.0 <= METAL_DENSITY_G_CM3["argentium_935"] <= 11.0

    def test_all_new_alloys_have_labels(self):
        for k in ["22k_white", "22k_rose", "platinum_900", "palladium_500", "argentium_935"]:
            assert k in METAL_LABELS, f"Missing label for {k}"
            assert METAL_LABELS[k]  # non-empty

    def test_all_new_alloys_have_hallmarks(self):
        for k in ["22k_white", "22k_rose", "platinum_900", "palladium_500", "argentium_935"]:
            assert k in METAL_HALLMARK, f"Missing hallmark for {k}"

    def test_hallmark_values_correct(self):
        assert METAL_HALLMARK["10k_yellow"] == 417
        assert METAL_HALLMARK["14k_yellow"] == 583
        assert METAL_HALLMARK["18k_yellow"] == 750
        assert METAL_HALLMARK["22k_yellow"] == 917
        assert METAL_HALLMARK["24k_yellow"] == 999
        assert METAL_HALLMARK["platinum_950"] == 950
        assert METAL_HALLMARK["platinum_900"] == 900
        assert METAL_HALLMARK["palladium_950"] == 950
        assert METAL_HALLMARK["palladium_500"] == 500
        assert METAL_HALLMARK["sterling_925"] == 925
        assert METAL_HALLMARK["fine_silver"] == 999
        assert METAL_HALLMARK["argentium_935"] == 935

    def test_non_precious_hallmark_none(self):
        for k in ["titanium", "brass", "bronze"]:
            assert METAL_HALLMARK[k] is None

    def test_fineness_label_matches_hallmark(self):
        assert METAL_FINENESS_LABEL["18k_yellow"] == "750"
        assert METAL_FINENESS_LABEL["platinum_950"] == "950"
        assert METAL_FINENESS_LABEL["titanium"] == "—"

    def test_all_metals_have_hallmark_entry(self):
        for k in METAL_DENSITY_G_CM3:
            assert k in METAL_HALLMARK, f"Missing METAL_HALLMARK entry for '{k}'"

    def test_price_presets_structure(self):
        assert "usd_2024_approx" in METAL_PRICE_PRESETS
        preset = METAL_PRICE_PRESETS["usd_2024_approx"]
        # Every metal should have a price in the preset
        for k in METAL_DENSITY_G_CM3:
            assert k in preset, f"Preset missing price for '{k}'"
            assert preset[k] >= 0.0


# ── mm_to_carat ───────────────────────────────────────────────────────────────

class TestMmToCarat:
    def test_round_brilliant_1ct_approx_6_5mm(self):
        # Standard: 1 ct round brilliant ≈ 6.5 mm diameter
        ct = mm_to_carat(6.5, "round_brilliant")
        # Roughly 0.9–1.1 ct
        assert 0.85 <= ct <= 1.15

    def test_0_5ct_round_brilliant_approx_5mm(self):
        ct = mm_to_carat(5.0, "round_brilliant")
        # 5 mm round brilliant ≈ 0.46 ct
        assert 0.40 <= ct <= 0.60

    def test_different_cuts_give_different_values(self):
        round_ct = mm_to_carat(6.0, "round_brilliant")
        marquise_ct = mm_to_carat(6.0, "marquise")
        # Marquise is shallower → different carat for same mm
        assert round_ct != marquise_ct

    def test_negative_mm_raises(self):
        with pytest.raises(ValueError):
            mm_to_carat(-1.0)

    def test_zero_mm_raises(self):
        with pytest.raises(ValueError):
            mm_to_carat(0.0)

    def test_unknown_cut_falls_back_to_round_brilliant(self):
        ct_known = mm_to_carat(6.0, "round_brilliant")
        ct_unknown = mm_to_carat(6.0, "unknown_fantasy_cut")
        assert ct_known == approx(ct_unknown)

    def test_larger_stone_heavier(self):
        small = mm_to_carat(3.0)
        large = mm_to_carat(6.0)
        assert large > small


# ── stone_cost_line_items ─────────────────────────────────────────────────────

class TestStoneCostLineItems:
    def test_single_stone_explicit_carat(self):
        result = stone_cost_line_items([
            {"cut": "round_brilliant", "carat": 0.5, "price_per_carat": 2000.0}
        ])
        assert result["total_cost"] == approx(1000.0)
        assert result["total_carats"] == approx(0.5)
        assert result["total_stones"] == 1
        assert len(result["line_items"]) == 1

    def test_multiple_stones_same_spec(self):
        result = stone_cost_line_items([
            {"cut": "round_brilliant", "carat": 0.1, "price_per_carat": 500.0, "count": 4}
        ])
        assert result["total_cost"] == approx(200.0)
        assert result["total_carats"] == approx(0.4)
        assert result["total_stones"] == 4

    def test_multiple_stone_specs(self):
        stones = [
            {"carat": 1.0, "price_per_carat": 5000.0, "cut": "round_brilliant"},
            {"carat": 0.2, "price_per_carat": 300.0, "cut": "pave", "count": 10},
        ]
        result = stone_cost_line_items(stones)
        expected_total = 1.0 * 5000.0 + 0.2 * 300.0 * 10
        assert result["total_cost"] == approx(expected_total)
        assert result["total_stones"] == 11

    def test_stone_with_mm_instead_of_carat(self):
        result = stone_cost_line_items([
            {"cut": "round_brilliant", "mm": 6.5, "price_per_carat": 2000.0}
        ])
        # mm→carat ≈ 1 ct for 6.5mm round; total cost ~$2000
        assert result["total_cost"] >= 1500.0
        assert result["total_cost"] <= 2500.0

    def test_empty_list_returns_zeros(self):
        result = stone_cost_line_items([])
        assert result["total_cost"] == 0.0
        assert result["total_carats"] == 0.0
        assert result["total_stones"] == 0
        assert result["line_items"] == []

    def test_note_preserved(self):
        result = stone_cost_line_items([
            {"carat": 0.5, "price_per_carat": 2000.0, "note": "VS1 G colour"}
        ])
        assert result["line_items"][0]["note"] == "VS1 G colour"

    def test_missing_price_per_carat_raises(self):
        with pytest.raises(ValueError, match="price_per_carat"):
            stone_cost_line_items([{"carat": 0.5}])

    def test_negative_carat_raises(self):
        with pytest.raises(ValueError):
            stone_cost_line_items([{"carat": -0.5, "price_per_carat": 100.0}])

    def test_negative_price_raises(self):
        with pytest.raises(ValueError):
            stone_cost_line_items([{"carat": 0.5, "price_per_carat": -1.0}])

    def test_zero_count_raises(self):
        with pytest.raises(ValueError):
            stone_cost_line_items([{"carat": 0.5, "price_per_carat": 100.0, "count": 0}])

    def test_neither_carat_nor_mm_raises(self):
        with pytest.raises(ValueError):
            stone_cost_line_items([{"price_per_carat": 100.0}])

    def test_not_a_list_raises(self):
        with pytest.raises(ValueError):
            stone_cost_line_items("not a list")


# ── labour_cost ───────────────────────────────────────────────────────────────

class TestLabourCost:
    def test_basic_bench_hours(self):
        result = labour_cost(bench_hours=4.0, hourly_rate=75.0)
        assert result["bench_labour_cost"] == approx(300.0)
        assert result["setting_cost"] == approx(0.0)  # no stones
        assert result["finishing_cost"] == approx(0.0)
        assert result["total_labour"] == approx(300.0)

    def test_setting_cost_prong_default(self):
        stones = [{"carat": 0.5, "price_per_carat": 2000.0, "count": 1}]
        result = labour_cost(setting_type="prong", stones=stones)
        expected = DEFAULT_SETTING_FEE_PER_STONE["prong"] * 1
        assert result["setting_cost"] == approx(expected)

    def test_setting_cost_pave_multi_stone(self):
        stones = [{"carat": 0.05, "price_per_carat": 200.0, "count": 20}]
        result = labour_cost(setting_type="pave", stones=stones)
        expected = DEFAULT_SETTING_FEE_PER_STONE["pave"] * 20
        assert result["setting_cost"] == approx(expected)

    def test_custom_setting_fee_override(self):
        stones = [{"carat": 0.5, "price_per_carat": 2000.0, "count": 3}]
        result = labour_cost(setting_fee_per_stone=25.0, stones=stones)
        assert result["setting_cost"] == approx(75.0)

    def test_finishing_type_rhodium(self):
        result = labour_cost(finishing_type="rhodium")
        assert result["finishing_cost"] == approx(DEFAULT_FINISHING_COST["rhodium"])
        assert result["finishing_type"] == "rhodium"

    def test_finishing_cost_explicit_override(self):
        result = labour_cost(finishing_cost=50.0)
        assert result["finishing_cost"] == approx(50.0)

    def test_total_is_sum(self):
        stones = [{"carat": 0.5, "price_per_carat": 2000.0, "count": 2}]
        result = labour_cost(
            bench_hours=3.0, hourly_rate=80.0,
            stones=stones, setting_type="bezel",
            finishing_type="rhodium",
        )
        expected = (3.0 * 80.0
                    + DEFAULT_SETTING_FEE_PER_STONE["bezel"] * 2
                    + DEFAULT_FINISHING_COST["rhodium"])
        assert result["total_labour"] == approx(expected)

    def test_negative_bench_hours_raises(self):
        with pytest.raises(ValueError):
            labour_cost(bench_hours=-1.0)

    def test_negative_hourly_rate_raises(self):
        with pytest.raises(ValueError):
            labour_cost(hourly_rate=-10.0)

    def test_unknown_setting_type_raises(self):
        with pytest.raises(ValueError, match="setting_type"):
            labour_cost(setting_type="telekinesis")

    def test_unknown_finishing_type_raises(self):
        with pytest.raises(ValueError, match="finishing_type"):
            labour_cost(finishing_type="unicorn_sheen")

    def test_all_setting_types_have_defaults(self):
        for stype in SETTING_TYPES:
            result = labour_cost(setting_type=stype)
            assert result["setting_cost"] == 0.0  # no stones
            assert result["setting_type"] == stype

    def test_no_stones_zero_setting_cost(self):
        result = labour_cost(setting_type="prong", stones=[])
        assert result["stone_count"] == 0
        assert result["setting_cost"] == 0.0


# ── jewelry_quote ─────────────────────────────────────────────────────────────

class TestJewelryQuote:
    """Full quote combines metal + stones + labour + markup correctly."""

    def _basic_quote(self, **kwargs):
        defaults = dict(
            volume_mm3=300.0,
            metal="18k_yellow",
            metal_price_per_gram=48.0,
        )
        defaults.update(kwargs)
        return jewelry_quote(**defaults)

    def test_keys_present(self):
        q = self._basic_quote()
        for k in [
            "metal", "label", "hallmark", "density_g_cm3", "volume_mm3",
            "net_grams", "net_dwt", "net_ozt", "allowance_pct", "gross_grams",
            "metal_price_per_gram", "metal_cost", "casting_cost",
            "stones", "stone_cost", "labour", "labour_total",
            "subtotal", "markup_pct", "markup_amount", "total",
        ]:
            assert k in q, f"Missing key: {k}"

    def test_no_stones_no_labour_total_equals_metal_cost(self):
        q = self._basic_quote(markup_pct=0.0)
        assert q["subtotal"] == approx(q["metal_cost"])
        assert q["total"] == approx(q["metal_cost"])

    def test_subtotal_is_sum_of_parts(self):
        stones = [{"carat": 0.5, "price_per_carat": 2000.0}]
        q = jewelry_quote(
            volume_mm3=300.0, metal="18k_yellow",
            metal_price_per_gram=48.0,
            stones=stones,
            bench_hours=4.0, hourly_rate=75.0,
            setting_type="prong",
            finishing_type="rhodium",
            markup_pct=0.0,
        )
        expected_subtotal = q["metal_cost"] + q["stone_cost"] + q["labour_total"]
        assert q["subtotal"] == approx(expected_subtotal)

    def test_total_with_markup(self):
        q = self._basic_quote(markup_pct=20.0)
        expected_markup = q["subtotal"] * 0.20
        expected_total = q["subtotal"] + expected_markup
        assert q["markup_amount"] == approx(expected_markup, rel=1e-4)
        assert q["total"] == approx(expected_total, rel=1e-4)

    def test_full_example_18k_ring_with_stones(self):
        """
        18k yellow gold ring, 300 mm³:
          metal cost: gross_grams(5.375) × $48 ≈ $258.00
          stone: 0.5 ct × $2000 = $1000
          labour: 4h × $75 = $300
          setting: 1 prong × $12 = $12
          finishing: rhodium $35
          subtotal ≈ $1605
          markup 20% ≈ $321
          total ≈ $1926
        """
        q = jewelry_quote(
            volume_mm3=300.0,
            metal="18k_yellow",
            metal_price_per_gram=48.0,
            stones=[{"carat": 0.5, "price_per_carat": 2000.0, "count": 1}],
            bench_hours=4.0,
            hourly_rate=75.0,
            setting_type="prong",
            finishing_type="rhodium",
            markup_pct=20.0,
        )
        # Metal cost check
        assert q["net_grams"] == approx(4.674, rel=0.01)
        assert q["gross_grams"] == approx(4.674 * 1.15, rel=0.01)
        assert q["metal_cost"] == approx(q["gross_grams"] * 48.0, rel=1e-4)
        # Stone cost check
        assert q["stone_cost"] == approx(1000.0)
        # Labour + setting + finishing
        expected_labour = (4.0 * 75.0
                           + DEFAULT_SETTING_FEE_PER_STONE["prong"] * 1
                           + DEFAULT_FINISHING_COST["rhodium"])
        assert q["labour_total"] == approx(expected_labour)
        # Subtotal / total
        expected_sub = q["metal_cost"] + q["stone_cost"] + q["labour_total"]
        assert q["subtotal"] == approx(expected_sub, rel=1e-4)
        assert q["total"] == approx(expected_sub * 1.20, rel=1e-4)

    def test_hallmark_included(self):
        q = self._basic_quote()
        assert q["hallmark"] == 750  # 18k = 750

    def test_hallmark_platinum_950(self):
        q = jewelry_quote(volume_mm3=300.0, metal="platinum_950",
                          metal_price_per_gram=32.0)
        assert q["hallmark"] == 950

    def test_casting_cost_alias_equals_metal_cost(self):
        q = self._basic_quote()
        assert q["casting_cost"] == q["metal_cost"]

    def test_negative_markup_raises(self):
        with pytest.raises(ValueError, match="markup_pct"):
            self._basic_quote(markup_pct=-5.0)

    def test_zero_markup_no_extra_cost(self):
        q = self._basic_quote(markup_pct=0.0)
        assert q["markup_amount"] == 0.0
        assert q["total"] == approx(q["subtotal"])

    def test_price_preset_used_when_price_zero(self):
        q = jewelry_quote(
            volume_mm3=300.0,
            metal="18k_yellow",
            metal_price_per_gram=0.0,
            price_preset="usd_2024_approx",
        )
        preset_price = METAL_PRICE_PRESETS["usd_2024_approx"]["18k_yellow"]
        assert q["metal_price_per_gram"] == approx(preset_price)
        assert q["metal_cost"] > 0.0

    def test_explicit_price_overrides_preset(self):
        explicit_price = 99.0
        q = jewelry_quote(
            volume_mm3=300.0,
            metal="18k_yellow",
            metal_price_per_gram=explicit_price,
            price_preset="usd_2024_approx",
        )
        assert q["metal_price_per_gram"] == approx(explicit_price)

    def test_unknown_price_preset_raises(self):
        with pytest.raises(ValueError, match="price_preset"):
            jewelry_quote(volume_mm3=300.0, metal="18k_yellow",
                          price_preset="nonexistent_preset")

    def test_multi_stone_types_sum_correctly(self):
        stones = [
            {"carat": 1.0, "price_per_carat": 5000.0},
            {"carat": 0.05, "price_per_carat": 100.0, "count": 8},
        ]
        q = jewelry_quote(
            volume_mm3=300.0, metal="18k_yellow",
            metal_price_per_gram=48.0, stones=stones,
        )
        expected_stone_cost = 1.0 * 5000.0 + 0.05 * 100.0 * 8
        assert q["stone_cost"] == approx(expected_stone_cost)
        assert q["stones"]["total_stones"] == 9

    def test_explicit_density_accepted(self):
        q = jewelry_quote(volume_mm3=300.0, density_g_cm3=15.0,
                          metal_price_per_gram=40.0)
        assert q["net_grams"] == approx(15.0 * 0.3)

    def test_pave_setting_many_stones(self):
        stones = [{"carat": 0.03, "price_per_carat": 150.0, "count": 30}]
        q = jewelry_quote(
            volume_mm3=300.0, metal="18k_white",
            metal_price_per_gram=49.0,
            stones=stones,
            setting_type="pave",
            bench_hours=3.0, hourly_rate=85.0,
            markup_pct=25.0,
        )
        expected_stone_cost = 0.03 * 150.0 * 30
        assert q["stone_cost"] == approx(expected_stone_cost)
        expected_setting = DEFAULT_SETTING_FEE_PER_STONE["pave"] * 30
        assert q["labour"]["setting_cost"] == approx(expected_setting)
        assert q["total"] == approx(q["subtotal"] * 1.25, rel=1e-4)

    def test_backwards_compat_existing_casting_cost_unchanged(self):
        """jewelry_quote with no stones/labour/markup = same as casting_cost."""
        q = jewelry_quote(
            volume_mm3=1000.0, metal="14k_yellow",
            metal_price_per_gram=30.0,
        )
        c = casting_cost(
            volume_mm3=1000.0, metal="14k_yellow",
            metal_price_per_gram=30.0,
        )
        assert q["net_grams"] == approx(c["net_grams"])
        assert q["gross_grams"] == approx(c["gross_grams"])
        assert q["metal_cost"] == approx(c["metal_cost"])
        assert q["total"] == approx(c["total_cost"])


# ── Tool — full quote path ────────────────────────────────────────────────────

class TestRunJewelryMetalCostFullQuote:
    """Tests for the new full-quote code path in the LLM tool."""

    def test_quote_with_stones_returns_full_quote_mode(self):
        result = run_tool(
            volume_mm3=300.0,
            metal="18k_yellow",
            metal_price_per_gram=48.0,
            stones=[{"carat": 0.5, "price_per_carat": 2000.0}],
        )
        assert "error" not in result
        assert result.get("mode") == "full_quote"
        est = result["estimate"]
        assert "stone_cost" in est
        assert est["stone_cost"] == approx(1000.0)

    def test_quote_with_markup(self):
        result = run_tool(
            volume_mm3=300.0,
            metal="18k_yellow",
            metal_price_per_gram=48.0,
            markup_pct=20.0,
        )
        assert "error" not in result
        est = result["estimate"]
        assert est["markup_pct"] == approx(20.0)
        assert est["total"] == approx(est["subtotal"] * 1.20, rel=1e-4)

    def test_quote_with_price_preset(self):
        result = run_tool(
            volume_mm3=300.0,
            metal="18k_yellow",
            price_preset="usd_2024_approx",
        )
        assert "error" not in result
        est = result["estimate"]
        assert est["metal_cost"] > 0.0

    def test_invalid_price_preset_returns_bad_args(self):
        result = run_tool(
            volume_mm3=300.0,
            metal="18k_yellow",
            price_preset="made_up_preset",
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_quote_stones_bad_spec_returns_bad_args(self):
        result = run_tool(
            volume_mm3=300.0,
            metal="18k_yellow",
            metal_price_per_gram=48.0,
            stones=[{"carat": 0.5}],  # missing price_per_carat
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_quote_negative_markup_returns_bad_args(self):
        result = run_tool(
            volume_mm3=300.0,
            metal="18k_yellow",
            metal_price_per_gram=48.0,
            markup_pct=-10.0,
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_quote_with_setting_and_finishing(self):
        result = run_tool(
            volume_mm3=300.0,
            metal="18k_white",
            metal_price_per_gram=49.0,
            stones=[{"carat": 0.5, "price_per_carat": 2000.0, "count": 1}],
            bench_hours=4.0,
            hourly_rate=75.0,
            setting_type="bezel",
            finishing_type="rhodium",
        )
        assert "error" not in result
        est = result["estimate"]
        assert est["labour"]["setting_type"] == "bezel"
        assert est["labour"]["finishing_type"] == "rhodium"

    def test_legacy_casting_cost_path_unchanged(self):
        """Calls without new params still use legacy casting_cost path."""
        result = run_tool(
            volume_mm3=1000.0,
            metal="14k_yellow",
            metal_price_per_gram=30.0,
            labor=50.0,
            finishing=20.0,
        )
        assert "error" not in result
        assert result.get("mode") == "casting_cost"
        est = result["estimate"]
        assert est["total_cost"] == approx(est["metal_cost"] + 50.0 + 20.0)

    def test_hallmark_in_full_quote(self):
        result = run_tool(
            volume_mm3=300.0,
            metal="18k_yellow",
            metal_price_per_gram=48.0,
            markup_pct=20.0,  # markup triggers full_quote path
        )
        assert "error" not in result
        assert result.get("mode") == "full_quote"
        est = result["estimate"]
        assert est.get("hallmark") == 750
