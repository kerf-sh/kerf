"""
Tests for kerf_cad_core.jewelry.repair

Pure-Python, hermetic — no OCC, no database, no project context required.

Covers (>=25 tests):
  - ring_size_up metal weight = section_mm2 × Δcircumference (Δcirc = π × Δdia)
  - ring_size_up/down labor scales with size delta
  - prong_retip and prong_rebuild price scale linearly with prong_count
  - rhodium_replate cost ties to area_mm2
  - price decomposition: materials + labor + markup
  - emerald-near-torch risk note fires
  - non-heat-sensitive stone does not trigger risk note
  - invalid repair_type returns graceful {"ok": False, "reason": ...}
  - invalid metal returns graceful error
  - invalid sizing direction (size_up with to_size <= from_size) returns error
  - full_shank > half_shank metal weight
  - stone_reset labor varies by setting_type
  - clasp_replacement includes clasp cost in materials
  - chain_solder uses solder consumable
  - refinish_polish is labour-only (metal_g == 0)
  - rhodium_replate metal_g == 0
  - estimate_repair_list aggregates totals correctly
  - estimate_repair_list with one invalid repair sets ok=False but returns errors list
  - markup_pct=0 means price == materials + labor
  - markup scales correctly
  - steps and tools lists are non-empty for all repair types
  - price >= materials_cost (no negative labor)
  - opal near ring_size_down fires risk note
  - pearl near half_shank fires risk note
  - diamond near ring_size_up does NOT fire risk note
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from kerf_cad_core.jewelry.repair import (
    _DEFAULT_CLASP_COST,
    _DEFAULT_LABOR_RATE_PER_HOUR,
    _DEFAULT_MARKUP_PCT,
    _DEFAULT_SECTION_MM2,
    _RHODIUM_COST_PER_MM2,
    _REPAIR_STEPS,
    _REPAIR_TOOLS,
    _SOLDER_COST_PER_JOINT,
    _US_ID_SLOPE,
    _VALID_REPAIRS,
    estimate_repair,
    estimate_repair_list,
    _us_delta_circumference_mm,
    _ring_size_metal_grams,
)
from kerf_cad_core.jewelry.metal_cost import METAL_DENSITY_G_CM3


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def approx(v, rel=1e-4):
    return pytest.approx(v, rel=rel)


def _run_tool(tool_fn, **kwargs) -> dict:
    raw = asyncio.new_event_loop().run_until_complete(
        tool_fn(None, json.dumps(kwargs).encode())
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# 1. Δcircumference formula: Δcirc = π × _US_ID_SLOPE × |Δsize|
# ---------------------------------------------------------------------------

class TestDeltaCircumference:
    def test_delta_circ_one_size(self):
        """One US size step: Δcirc = π × 0.8128."""
        expected = math.pi * _US_ID_SLOPE * 1.0
        assert _us_delta_circumference_mm(7.0, 8.0) == approx(expected)

    def test_delta_circ_half_size(self):
        expected = math.pi * _US_ID_SLOPE * 0.5
        assert _us_delta_circumference_mm(6.0, 6.5) == approx(expected)

    def test_delta_circ_symmetric(self):
        """Absolute value — direction doesn't matter for Δcirc magnitude."""
        assert _us_delta_circumference_mm(7.0, 8.0) == approx(
            _us_delta_circumference_mm(8.0, 7.0)
        )

    def test_delta_circ_two_sizes(self):
        expected = math.pi * _US_ID_SLOPE * 2.0
        assert _us_delta_circumference_mm(5.0, 7.0) == approx(expected)


# ---------------------------------------------------------------------------
# 2. Metal weight for ring sizing up
# ---------------------------------------------------------------------------

class TestRingSizingMetalWeight:
    def test_metal_weight_section_times_delta_circ(self):
        """metal_g = section_mm2 × Δcirc × density / 1000."""
        from_size, to_size = 6.0, 7.0
        metal = "18k_yellow"
        section_mm2 = 3.0
        delta_circ = math.pi * _US_ID_SLOPE * 1.0
        density = METAL_DENSITY_G_CM3[metal]
        expected_g = section_mm2 * delta_circ * density / 1000.0
        assert _ring_size_metal_grams(from_size, to_size, metal, section_mm2) == approx(expected_g)

    def test_metal_weight_scales_with_section(self):
        """Doubling section_mm2 doubles the metal weight."""
        g1 = _ring_size_metal_grams(5.0, 6.0, "18k_yellow", 2.0)
        g2 = _ring_size_metal_grams(5.0, 6.0, "18k_yellow", 4.0)
        assert g2 == approx(g1 * 2.0)

    def test_metal_weight_scales_with_size_delta(self):
        """Doubling the size delta doubles the metal weight."""
        g1 = _ring_size_metal_grams(5.0, 6.0, "14k_yellow", 3.0)
        g2 = _ring_size_metal_grams(5.0, 7.0, "14k_yellow", 3.0)
        assert g2 == approx(g1 * 2.0)

    def test_metal_weight_sterling_less_than_18k(self):
        """Sterling is less dense than 18k gold → less metal weight."""
        g_18k = _ring_size_metal_grams(6.0, 7.0, "18k_yellow", 3.0)
        g_sterling = _ring_size_metal_grams(6.0, 7.0, "sterling_925", 3.0)
        assert g_sterling < g_18k

    def test_ring_size_up_estimate_metal_g_matches_formula(self):
        result = estimate_repair(
            "ring_size_up",
            metal="18k_yellow",
            from_size=6.0,
            to_size=8.0,
            section_mm2=3.0,
            metal_price_per_gram=0.0,
        )
        assert result["ok"]
        expected = _ring_size_metal_grams(6.0, 8.0, "18k_yellow", 3.0)
        assert result["metal_g"] == approx(expected)


# ---------------------------------------------------------------------------
# 3. Labor scales with size delta
# ---------------------------------------------------------------------------

class TestSizingLabor:
    def test_ring_size_up_labor_scales(self):
        """1-size change has less labor than 3-size change."""
        r1 = estimate_repair("ring_size_up", from_size=6.0, to_size=7.0)
        r3 = estimate_repair("ring_size_up", from_size=6.0, to_size=9.0)
        assert r3["labor_min"] > r1["labor_min"]

    def test_ring_size_down_labor_scales(self):
        r1 = estimate_repair("ring_size_down", from_size=8.0, to_size=7.0)
        r2 = estimate_repair("ring_size_down", from_size=8.0, to_size=6.0)
        assert r2["labor_min"] > r1["labor_min"]


# ---------------------------------------------------------------------------
# 4. Prong count scales price
# ---------------------------------------------------------------------------

class TestProngScaling:
    def test_retip_price_scales_with_count(self):
        r4 = estimate_repair("prong_retip", prong_count=4,
                             labor_rate_per_hour=60.0, markup_pct=0.0)
        r6 = estimate_repair("prong_retip", prong_count=6,
                             labor_rate_per_hour=60.0, markup_pct=0.0)
        # price = materials + labor; both scale with prong_count
        assert r6["price"] > r4["price"]

    def test_retip_labor_linear_with_count(self):
        r2 = estimate_repair("prong_retip", prong_count=2)
        r4 = estimate_repair("prong_retip", prong_count=4)
        assert r4["labor_min"] == approx(r2["labor_min"] * 2.0)

    def test_rebuild_price_scales_with_count(self):
        r4 = estimate_repair("prong_rebuild", prong_count=4,
                             labor_rate_per_hour=60.0, markup_pct=0.0)
        r8 = estimate_repair("prong_rebuild", prong_count=8,
                             labor_rate_per_hour=60.0, markup_pct=0.0)
        assert r8["price"] > r4["price"]

    def test_rebuild_more_expensive_than_retip_same_prong_count(self):
        retip = estimate_repair("prong_retip", prong_count=4, markup_pct=0.0)
        rebuild = estimate_repair("prong_rebuild", prong_count=4, markup_pct=0.0)
        assert rebuild["price"] > retip["price"]


# ---------------------------------------------------------------------------
# 5. Rhodium cost ties to area
# ---------------------------------------------------------------------------

class TestRhodiumReplate:
    def test_rhodium_materials_cost_ties_to_area(self):
        r1 = estimate_repair("rhodium_replate", area_mm2=1000.0, markup_pct=0.0,
                             labor_rate_per_hour=0.0)
        r2 = estimate_repair("rhodium_replate", area_mm2=2000.0, markup_pct=0.0,
                             labor_rate_per_hour=0.0)
        assert r2["materials_cost"] == approx(r1["materials_cost"] * 2.0)

    def test_rhodium_materials_cost_formula(self):
        area = 1500.0
        r = estimate_repair("rhodium_replate", area_mm2=area,
                            markup_pct=0.0, labor_rate_per_hour=0.0)
        assert r["materials_cost"] == approx(area * _RHODIUM_COST_PER_MM2)

    def test_rhodium_metal_g_is_zero(self):
        r = estimate_repair("rhodium_replate", area_mm2=1500.0)
        assert r["metal_g"] == 0.0


# ---------------------------------------------------------------------------
# 6. Price decomposition
# ---------------------------------------------------------------------------

class TestPriceDecomposition:
    def test_markup_zero_price_equals_materials_plus_labor(self):
        r = estimate_repair("refinish_polish", markup_pct=0.0,
                            labor_rate_per_hour=60.0)
        expected = r["materials_cost"] + (r["labor_min"] / 60.0) * 60.0
        assert r["price"] == approx(expected)

    def test_markup_scales_correctly(self):
        """With 50% markup: price = (materials + labor) × 1.5."""
        r = estimate_repair("chain_solder", markup_pct=50.0,
                            labor_rate_per_hour=60.0)
        labor_cost = (r["labor_min"] / 60.0) * 60.0
        subtotal = r["materials_cost"] + labor_cost
        assert r["price"] == approx(subtotal * 1.5)

    def test_price_always_gte_materials_cost(self):
        """Labor and markup are non-negative, so price >= materials_cost."""
        for rtype in _VALID_REPAIRS:
            kwargs: dict = {}
            if rtype in ("ring_size_up",):
                kwargs = {"from_size": 5.0, "to_size": 7.0}
            elif rtype in ("ring_size_down",):
                kwargs = {"from_size": 8.0, "to_size": 6.0}
            r = estimate_repair(rtype, **kwargs)
            assert r.get("ok"), f"{rtype} returned ok=False: {r.get('reason')}"
            assert r["price"] >= r["materials_cost"], f"price < materials_cost for {rtype}"

    def test_price_decomposition_ring_size_up(self):
        """Manual price check for ring_size_up."""
        r = estimate_repair(
            "ring_size_up",
            from_size=6.0, to_size=7.0,
            metal="18k_yellow",
            metal_price_per_gram=48.0,
            labor_rate_per_hour=_DEFAULT_LABOR_RATE_PER_HOUR,
            markup_pct=_DEFAULT_MARKUP_PCT,
            section_mm2=3.0,
        )
        assert r["ok"]
        metal_cost = r["metal_g"] * 48.0
        labor_cost = (r["labor_min"] / 60.0) * _DEFAULT_LABOR_RATE_PER_HOUR
        subtotal = r["materials_cost"] + labor_cost
        assert r["price"] == approx(subtotal * (1 + _DEFAULT_MARKUP_PCT / 100.0))


# ---------------------------------------------------------------------------
# 7. Emerald-near-torch risk fires
# ---------------------------------------------------------------------------

class TestHeatRiskNotes:
    def test_emerald_near_torch_fires(self):
        r = estimate_repair("ring_size_up", from_size=6.0, to_size=7.0,
                            stones=["emerald"])
        assert r["ok"]
        assert len(r["risk_notes"]) > 0
        combined = " ".join(r["risk_notes"]).lower()
        assert "emerald" in combined

    def test_opal_near_ring_size_down_fires(self):
        r = estimate_repair("ring_size_down", from_size=8.0, to_size=6.0,
                            stones=["opal"])
        assert r["ok"]
        assert any("opal" in note.lower() for note in r["risk_notes"])

    def test_pearl_near_half_shank_fires(self):
        r = estimate_repair("half_shank", stones=["pearl"])
        assert r["ok"]
        assert any("pearl" in note.lower() for note in r["risk_notes"])

    def test_diamond_near_torch_does_not_fire(self):
        """Diamond is not heat-sensitive at typical torch temperatures."""
        r = estimate_repair("ring_size_up", from_size=6.0, to_size=7.0,
                            stones=["diamond"])
        assert r["ok"]
        assert len(r["risk_notes"]) == 0

    def test_no_stones_no_risk_notes(self):
        r = estimate_repair("ring_size_up", from_size=5.0, to_size=6.0)
        assert r["ok"]
        assert r["risk_notes"] == []

    def test_rhodium_non_torch_no_risk_even_with_emerald(self):
        """rhodium_replate does not involve a torch → no heat risk."""
        r = estimate_repair("rhodium_replate", area_mm2=1500.0, stones=["emerald"])
        assert r["ok"]
        assert len(r["risk_notes"]) == 0

    def test_stone_reset_non_torch_no_risk(self):
        """stone_reset does not use a torch → no heat risk."""
        r = estimate_repair("stone_reset", setting_type="prong", stones=["tanzanite"])
        assert r["ok"]
        assert len(r["risk_notes"]) == 0


# ---------------------------------------------------------------------------
# 8. Invalid input — graceful errors
# ---------------------------------------------------------------------------

class TestGracefulErrors:
    def test_invalid_repair_type(self):
        r = estimate_repair("weld_diamonds_on")
        assert r.get("ok") is False
        assert "reason" in r
        assert "weld_diamonds_on" in r["reason"]

    def test_invalid_metal(self):
        r = estimate_repair("refinish_polish", metal="unobtainium")
        assert r.get("ok") is False
        assert "reason" in r

    def test_ring_size_up_wrong_direction(self):
        r = estimate_repair("ring_size_up", from_size=8.0, to_size=6.0)
        assert r.get("ok") is False
        assert "reason" in r

    def test_ring_size_up_same_size(self):
        r = estimate_repair("ring_size_up", from_size=7.0, to_size=7.0)
        assert r.get("ok") is False

    def test_negative_metal_price(self):
        r = estimate_repair("chain_solder", metal_price_per_gram=-1.0)
        assert r.get("ok") is False

    def test_negative_labor_rate(self):
        r = estimate_repair("refinish_polish", labor_rate_per_hour=-5.0)
        assert r.get("ok") is False

    def test_rhodium_zero_area(self):
        r = estimate_repair("rhodium_replate", area_mm2=0.0)
        assert r.get("ok") is False

    def test_rhodium_negative_area(self):
        r = estimate_repair("rhodium_replate", area_mm2=-100.0)
        assert r.get("ok") is False


# ---------------------------------------------------------------------------
# 9. Steps and tools sanity
# ---------------------------------------------------------------------------

class TestStepsAndTools:
    @pytest.mark.parametrize("rtype", sorted(_VALID_REPAIRS))
    def test_steps_non_empty(self, rtype):
        kwargs: dict = {}
        if rtype == "ring_size_up":
            kwargs = {"from_size": 5.0, "to_size": 6.0}
        elif rtype == "ring_size_down":
            kwargs = {"from_size": 7.0, "to_size": 6.0}
        r = estimate_repair(rtype, **kwargs)
        assert r.get("ok"), f"{rtype}: {r}"
        assert len(r["steps"]) >= 1, f"No steps for {rtype}"

    @pytest.mark.parametrize("rtype", sorted(_VALID_REPAIRS))
    def test_tools_non_empty(self, rtype):
        kwargs: dict = {}
        if rtype == "ring_size_up":
            kwargs = {"from_size": 5.0, "to_size": 6.0}
        elif rtype == "ring_size_down":
            kwargs = {"from_size": 7.0, "to_size": 6.0}
        r = estimate_repair(rtype, **kwargs)
        assert r.get("ok"), f"{rtype}: {r}"
        assert len(r["tools"]) >= 1, f"No tools for {rtype}"


# ---------------------------------------------------------------------------
# 10. Full shank vs half shank
# ---------------------------------------------------------------------------

class TestShankComparison:
    def test_full_shank_more_metal_than_half_shank(self):
        full = estimate_repair("full_shank", metal="18k_yellow",
                               metal_price_per_gram=48.0)
        half = estimate_repair("half_shank", metal="18k_yellow",
                               metal_price_per_gram=48.0)
        assert full["metal_g"] > half["metal_g"]

    def test_full_shank_more_labor_than_half_shank(self):
        full = estimate_repair("full_shank")
        half = estimate_repair("half_shank")
        assert full["labor_min"] > half["labor_min"]


# ---------------------------------------------------------------------------
# 11. Stone reset varies by setting type
# ---------------------------------------------------------------------------

class TestStoneReset:
    def test_invisible_setting_more_labor_than_prong(self):
        prong = estimate_repair("stone_reset", setting_type="prong")
        invisible = estimate_repair("stone_reset", setting_type="invisible")
        assert invisible["labor_min"] > prong["labor_min"]

    def test_stone_reset_metal_g_zero(self):
        r = estimate_repair("stone_reset", setting_type="bezel")
        assert r["ok"]
        assert r["metal_g"] == 0.0


# ---------------------------------------------------------------------------
# 12. Clasp replacement
# ---------------------------------------------------------------------------

class TestClaspReplacement:
    def test_clasp_cost_in_materials(self):
        clasp = 12.0
        r = estimate_repair("clasp_replacement",
                            clasp_cost=clasp, markup_pct=0.0, labor_rate_per_hour=0.0)
        assert r["ok"]
        # materials = clasp_cost + solder_per_joint
        assert r["materials_cost"] == approx(clasp + _SOLDER_COST_PER_JOINT)

    def test_default_clasp_cost(self):
        r = estimate_repair("clasp_replacement",
                            markup_pct=0.0, labor_rate_per_hour=0.0)
        assert r["ok"]
        assert r["materials_cost"] == approx(_DEFAULT_CLASP_COST + _SOLDER_COST_PER_JOINT)


# ---------------------------------------------------------------------------
# 13. estimate_repair_list aggregation
# ---------------------------------------------------------------------------

class TestRepairList:
    def test_list_totals_sum_of_items(self):
        repairs = [
            {"repair_type": "prong_retip", "prong_count": 4},
            {"repair_type": "refinish_polish"},
            {"repair_type": "chain_solder"},
        ]
        result = estimate_repair_list(repairs, labor_rate_per_hour=60.0, markup_pct=20.0)
        assert result["ok"]
        assert len(result["line_items"]) == 3
        expected_price = sum(item["price"] for item in result["line_items"])
        assert result["total_price"] == approx(expected_price)

    def test_list_with_invalid_item_sets_ok_false(self):
        repairs = [
            {"repair_type": "refinish_polish"},
            {"repair_type": "this_does_not_exist"},
        ]
        result = estimate_repair_list(repairs)
        assert result.get("ok") is False
        assert len(result["errors"]) == 1
        assert result["errors"][0]["repair_type"] == "this_does_not_exist"

    def test_list_total_metal_g_sum(self):
        repairs = [
            {"repair_type": "ring_size_up", "from_size": 5.0, "to_size": 6.0},
            {"repair_type": "half_shank"},
        ]
        result = estimate_repair_list(repairs, metal="14k_yellow")
        assert result["ok"]
        expected_metal = sum(item["metal_g"] for item in result["line_items"])
        assert result["total_metal_g"] == approx(expected_metal)


# ---------------------------------------------------------------------------
# 14. LLM tool runners
# ---------------------------------------------------------------------------

class TestLLMTools:
    def test_repair_estimate_tool_happy_path(self):
        try:
            from kerf_cad_core.jewelry.repair import run_jewelry_repair_estimate
        except ImportError:
            pytest.skip("kerf_chat not available")
        result = _run_tool(
            run_jewelry_repair_estimate,
            repair_type="refinish_polish",
            labor_rate_per_hour=60.0,
            markup_pct=30.0,
        )
        assert result.get("ok")
        data = result.get("result", result)
        assert data.get("repair") == "refinish_polish"

    def test_repair_estimate_tool_missing_repair_type(self):
        try:
            from kerf_cad_core.jewelry.repair import run_jewelry_repair_estimate
        except ImportError:
            pytest.skip("kerf_chat not available")
        result = _run_tool(run_jewelry_repair_estimate)
        # err_payload returns {"code": "BAD_ARGS", "error": "..."} (no "ok" key)
        assert result.get("code") == "BAD_ARGS" or result.get("ok") is False

    def test_repair_quote_tool_happy_path(self):
        try:
            from kerf_cad_core.jewelry.repair import run_jewelry_repair_quote
        except ImportError:
            pytest.skip("kerf_chat not available")
        result = _run_tool(
            run_jewelry_repair_quote,
            repairs=[
                {"repair_type": "prong_retip", "prong_count": 6},
                {"repair_type": "rhodium_replate", "area_mm2": 1200.0},
            ],
            metal="18k_white",
            labor_rate_per_hour=75.0,
        )
        assert result.get("ok")
        data = result.get("result", result)
        assert "total_price" in data
        assert data["total_price"] > 0
