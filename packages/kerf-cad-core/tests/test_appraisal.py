"""
Hermetic tests for kerf_cad_core.jewelry.appraisal.

Coverage:
  - total = stones + metal + labor (base value identity)
  - replacement >= fair_market >= liquidation
  - per-stone value scales with carat × grade
  - metal_value = weight × (spot + fab)
  - certificate_md has all required sections
  - metal-only piece (no stones) works correctly
  - bad input is handled gracefully (no raise)
  - value_summary returns correct fields
  - AppraisalConfig multiplier clamping / ordering
  - explicit price_per_carat is honoured
  - catalog fallback price used when explicit price absent
  - grade multiplier effect on value
  - carat size premium applied (catalog path)
  - zero-carat stone recorded with value 0
  - negative labor_value clamped to 0
  - replacement_multiplier != 1.0 applied correctly
  - fair_market ≤ replacement; liquidation ≤ fair_market post-rounding
  - unknown stone type produces 0 value with warning
  - unknown alloy produces 0 metal value with warning
  - piece_type not in known types records warning
  - missing carat field records warning, stone included with 0 value
  - value_summary invariant on zero-value appraisal
  - multi-stone piece totals consistent
  - piece with no metal dict handled gracefully

All tests are pure-Python and hermetic: no OCC, no DB, no network.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from kerf_cad_core.jewelry.appraisal import (
    AppraisalConfig,
    _build_metal_schedule,
    _build_stone_schedule,
    _catalog_mid_price,
    _grade_multiplier,
    _carat_size_premium,
    appraise,
    value_summary,
    run_jewelry_appraise,
    run_jewelry_value_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx():
    """Minimal async context stub."""

    class _Ctx:
        project_id = "test-proj"

    return _Ctx()


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _diamond_ring_piece(
    carat: float = 1.0,
    color_grade: str = "G",
    clarity_grade: str = "VS1",
    price_per_carat: float | None = None,
    weight_grams: float = 5.5,
    spot: float = 48.0,
    fab: float = 2.0,
    labor: float = 150.0,
) -> dict:
    stone = {
        "stone_type": "diamond",
        "cut": "round_brilliant",
        "carat": carat,
        "color_grade": color_grade,
        "clarity_grade": clarity_grade,
        "measurements_mm": {"length": 6.5, "width": 6.5, "depth": 4.0},
        "cert_ref": "GIA#1234567890",
        "setting_type": "prong",
    }
    if price_per_carat is not None:
        stone["price_per_carat"] = price_per_carat

    return {
        "id": "ring-001",
        "description": "18k Yellow Gold Diamond Solitaire Ring",
        "piece_type": "ring",
        "metal": {
            "alloy": "18k_yellow",
            "weight_grams": weight_grams,
            "spot_price_per_gram": spot,
            "fabrication_per_gram": fab,
        },
        "stones": [stone],
        "labor_value": labor,
    }


def _metal_only_piece(
    alloy: str = "sterling_925",
    weight_grams: float = 12.0,
    spot: float = 0.80,
    fab: float = 0.05,
    labor: float = 80.0,
) -> dict:
    return {
        "description": "Sterling Silver Bangle",
        "piece_type": "bangle",
        "metal": {
            "alloy": alloy,
            "weight_grams": weight_grams,
            "spot_price_per_gram": spot,
            "fabrication_per_gram": fab,
        },
        "stones": [],
        "labor_value": labor,
    }


# ---------------------------------------------------------------------------
# Test 1: base_value = total_stone_value + metal_value + labor_value
# ---------------------------------------------------------------------------

def test_base_value_is_sum_of_components():
    piece = _diamond_ring_piece()
    result = appraise(piece)

    stone_sum = sum(s["stone_value"] for s in result["stones_schedule"])
    metal_val = result["metal_schedule"]["metal_value"]
    labor = result["labor_value"]
    expected_base = round(stone_sum + metal_val + labor, 4)

    assert abs(result["base_value"] - expected_base) < 1e-3
    assert abs(result["total_stone_value"] - stone_sum) < 1e-3


# ---------------------------------------------------------------------------
# Test 2: replacement >= fair_market >= liquidation
# ---------------------------------------------------------------------------

def test_valuation_ordering():
    piece = _diamond_ring_piece()
    result = appraise(piece)
    assert result["replacement_value"] >= result["fair_market_value"]
    assert result["fair_market_value"] >= result["liquidation_value"]
    assert result["liquidation_value"] >= 0.0


# ---------------------------------------------------------------------------
# Test 3: per-stone value scales with carat (higher carat → more value)
# ---------------------------------------------------------------------------

def test_stone_value_scales_with_carat():
    result_1ct = appraise(_diamond_ring_piece(carat=1.0, price_per_carat=10000.0))
    result_2ct = appraise(_diamond_ring_piece(carat=2.0, price_per_carat=10000.0))

    val_1 = result_1ct["stones_schedule"][0]["stone_value"]
    val_2 = result_2ct["stones_schedule"][0]["stone_value"]
    # 2 ct × same explicit price → exactly double
    assert abs(val_2 - 2.0 * val_1) < 1e-3


# ---------------------------------------------------------------------------
# Test 4: per-stone value scales with grade (better grade → higher value)
# ---------------------------------------------------------------------------

def test_stone_value_scales_with_grade():
    """D FL (top grade) should have a higher per-carat price than J SI2."""
    result_top = appraise(_diamond_ring_piece(color_grade="D", clarity_grade="FL"))
    result_low = appraise(_diamond_ring_piece(color_grade="J", clarity_grade="SI2"))

    ppc_top = result_top["stones_schedule"][0]["price_per_carat"]
    ppc_low = result_low["stones_schedule"][0]["price_per_carat"]
    assert ppc_top > ppc_low


# ---------------------------------------------------------------------------
# Test 5: metal_value = weight × (spot + fab)
# ---------------------------------------------------------------------------

def test_metal_value_equals_weight_times_effective_price():
    weight = 7.3
    spot = 48.0
    fab = 2.5
    expected = weight * (spot + fab)
    piece = _metal_only_piece(weight_grams=weight, spot=spot, fab=fab, labor=0.0)
    result = appraise(piece)
    metal_val = result["metal_schedule"]["metal_value"]
    assert abs(metal_val - expected) < 1e-4


# ---------------------------------------------------------------------------
# Test 6: certificate_md has required sections
# ---------------------------------------------------------------------------

def test_certificate_md_has_required_sections():
    result = appraise(_diamond_ring_piece())
    md = result["certificate_md"]
    assert "JEWELRY APPRAISAL CERTIFICATE" in md
    assert "Gemstone Schedule" in md
    assert "Metal Schedule" in md
    assert "Value Summary" in md
    assert "Methodology" in md
    assert "Appraiser Statement" in md


# ---------------------------------------------------------------------------
# Test 7: metal-only piece (no stones) works correctly
# ---------------------------------------------------------------------------

def test_metal_only_piece():
    piece = _metal_only_piece()
    result = appraise(piece)
    assert result["total_stone_value"] == 0.0
    assert result["stones_schedule"] == []
    assert result["metal_schedule"]["metal_value"] > 0
    assert result["base_value"] > 0
    assert result["replacement_value"] >= result["fair_market_value"] >= result["liquidation_value"] >= 0


# ---------------------------------------------------------------------------
# Test 8: bad input — non-dict piece — graceful, no raise
# ---------------------------------------------------------------------------

def test_bad_input_non_dict_piece():
    result = appraise(None)
    assert isinstance(result, dict)
    assert result["replacement_value"] == 0.0
    assert len(result["warnings"]) > 0
    assert "certificate_md" in result


# ---------------------------------------------------------------------------
# Test 9: bad input — unknown stone type → value 0 (catalog miss)
# ---------------------------------------------------------------------------

def test_unknown_stone_type_value_zero_no_explicit_price():
    piece = {
        "description": "Test",
        "metal": {"alloy": "14k_yellow", "weight_grams": 4.0, "spot_price_per_gram": 37.0},
        "stones": [
            {
                "stone_type": "unobtainium",
                "cut": "oval",
                "carat": 1.5,
            }
        ],
        "labor_value": 0.0,
    }
    result = appraise(piece)
    # catalog price is 0 for unknown type
    assert result["stones_schedule"][0]["stone_value"] == 0.0


# ---------------------------------------------------------------------------
# Test 10: explicit price_per_carat is honoured (takes priority over catalog)
# ---------------------------------------------------------------------------

def test_explicit_price_per_carat_honoured():
    explicit_ppc = 5000.0
    piece = _diamond_ring_piece(carat=1.0, price_per_carat=explicit_ppc)
    result = appraise(piece)
    stone = result["stones_schedule"][0]
    assert stone["source"] == "explicit"
    assert abs(stone["price_per_carat"] - explicit_ppc) < 1e-4
    assert abs(stone["stone_value"] - explicit_ppc * 1.0) < 1e-4


# ---------------------------------------------------------------------------
# Test 11: catalog price used when no explicit price
# ---------------------------------------------------------------------------

def test_catalog_price_used_when_no_explicit_price():
    piece = _diamond_ring_piece(carat=1.0, price_per_carat=None)
    result = appraise(piece)
    stone = result["stones_schedule"][0]
    assert stone["source"] == "catalog_grade_adjusted"
    assert stone["price_per_carat"] > 0.0


# ---------------------------------------------------------------------------
# Test 12: replacement_multiplier != 1.0 applied correctly
# ---------------------------------------------------------------------------

def test_replacement_multiplier_applied():
    piece = _diamond_ring_piece()
    cfg = AppraisalConfig(replacement_multiplier=1.20)
    result = appraise(piece, cfg)
    expected = round(result["base_value"] * 1.20, 4)
    assert abs(result["replacement_value"] - expected) < 1e-3


# ---------------------------------------------------------------------------
# Test 13: fair_market ≤ replacement and liquidation ≤ fair_market
# ---------------------------------------------------------------------------

def test_valuation_invariant_custom_multipliers():
    cfg = AppraisalConfig(
        replacement_multiplier=1.3,
        fair_market_multiplier=0.65,
        liquidation_multiplier=0.35,
    )
    result = appraise(_diamond_ring_piece(), cfg)
    assert result["replacement_value"] >= result["fair_market_value"]
    assert result["fair_market_value"] >= result["liquidation_value"]


# ---------------------------------------------------------------------------
# Test 14: fair_market_multiplier > replacement_multiplier gets clamped
# ---------------------------------------------------------------------------

def test_fair_market_mult_clamped_when_above_replacement():
    cfg = AppraisalConfig(
        replacement_multiplier=0.80,
        fair_market_multiplier=1.20,  # invalid: fm > replacement
        liquidation_multiplier=0.30,
    )
    result = appraise(_diamond_ring_piece(), cfg)
    assert result["fair_market_value"] <= result["replacement_value"]
    assert any("clamped" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Test 15: missing carat field → stone included with value 0 + warning
# ---------------------------------------------------------------------------

def test_missing_carat_field():
    piece = {
        "description": "Test",
        "metal": {"alloy": "14k_yellow", "weight_grams": 3.5, "spot_price_per_gram": 37.0},
        "stones": [
            {"stone_type": "diamond", "cut": "princess"}  # no carat
        ],
        "labor_value": 0.0,
    }
    result = appraise(piece)
    assert len(result["stones_schedule"]) == 1
    assert result["stones_schedule"][0]["stone_value"] == 0.0
    assert any("carat" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Test 16: negative labor_value clamped to 0
# ---------------------------------------------------------------------------

def test_negative_labor_clamped():
    piece = _diamond_ring_piece(labor=-100.0)
    result = appraise(piece)
    assert result["labor_value"] == 0.0
    assert any("labor" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Test 17: unknown alloy → metal value 0 with warning
# ---------------------------------------------------------------------------

def test_unknown_alloy_warning():
    piece = {
        "description": "Mystery",
        "metal": {"alloy": "unobtainium_gold", "weight_grams": 5.0, "spot_price_per_gram": 99.0},
        "stones": [],
        "labor_value": 0.0,
    }
    result = appraise(piece)
    assert result["metal_schedule"]["metal_value"] == 0.0
    assert any("Unknown metal alloy" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Test 18: piece_type not in known types → warning but recorded as-is
# ---------------------------------------------------------------------------

def test_unknown_piece_type_records_warning():
    piece = dict(_diamond_ring_piece())
    piece["piece_type"] = "spaceship"
    result = appraise(piece)
    assert result["piece_type"] == "spaceship"
    assert any("piece_type" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Test 19: multi-stone piece totals consistent
# ---------------------------------------------------------------------------

def test_multi_stone_piece_totals():
    stones = [
        {
            "stone_type": "diamond", "cut": "round_brilliant",
            "carat": 0.50, "price_per_carat": 5000.0,
        },
        {
            "stone_type": "ruby", "cut": "oval",
            "carat": 0.75, "price_per_carat": 3000.0,
        },
        {
            "stone_type": "sapphire", "cut": "cushion",
            "carat": 0.40, "price_per_carat": 1500.0,
        },
    ]
    piece = {
        "description": "Multi-stone ring",
        "piece_type": "ring",
        "metal": {"alloy": "18k_yellow", "weight_grams": 6.0, "spot_price_per_gram": 48.0},
        "stones": stones,
        "labor_value": 200.0,
    }
    result = appraise(piece)

    # Verify each stone value
    assert abs(result["stones_schedule"][0]["stone_value"] - 0.50 * 5000.0) < 1e-3
    assert abs(result["stones_schedule"][1]["stone_value"] - 0.75 * 3000.0) < 1e-3
    assert abs(result["stones_schedule"][2]["stone_value"] - 0.40 * 1500.0) < 1e-3

    expected_stone_total = 0.50 * 5000.0 + 0.75 * 3000.0 + 0.40 * 1500.0
    assert abs(result["total_stone_value"] - expected_stone_total) < 1e-3

    metal_val = result["metal_schedule"]["metal_value"]
    expected_base = round(expected_stone_total + metal_val + 200.0, 4)
    assert abs(result["base_value"] - expected_base) < 1e-3


# ---------------------------------------------------------------------------
# Test 20: piece with no metal dict handled gracefully
# ---------------------------------------------------------------------------

def test_piece_with_no_metal_dict():
    piece = {
        "description": "Stones only",
        "piece_type": "pendant",
        "stones": [
            {"stone_type": "diamond", "cut": "pear", "carat": 0.5, "price_per_carat": 6000.0}
        ],
        "labor_value": 50.0,
    }
    result = appraise(piece)
    assert result["metal_schedule"]["metal_value"] == 0.0
    # base = stone + 0 metal + labor
    expected = round(0.5 * 6000.0 + 50.0, 4)
    assert abs(result["base_value"] - expected) < 1e-3


# ---------------------------------------------------------------------------
# Test 21: value_summary returns correct keys and ordering
# ---------------------------------------------------------------------------

def test_value_summary_fields_and_ordering():
    result = appraise(_diamond_ring_piece())
    summary = value_summary(result)
    assert set(summary.keys()) == {"replacement", "fair_market", "liquidation", "base", "currency"}
    assert summary["replacement"] >= summary["fair_market"] >= summary["liquidation"] >= 0
    assert summary["currency"] == "USD"
    assert abs(summary["replacement"] - result["replacement_value"]) < 1e-4


# ---------------------------------------------------------------------------
# Test 22: value_summary on non-dict input returns zeros, no raise
# ---------------------------------------------------------------------------

def test_value_summary_non_dict_input():
    summary = value_summary("not_a_dict")
    assert summary["replacement"] == 0.0
    assert summary["fair_market"] == 0.0
    assert summary["liquidation"] == 0.0


# ---------------------------------------------------------------------------
# Test 23: carat size premium > 1.0 for large stones (catalog path)
# ---------------------------------------------------------------------------

def test_carat_size_premium_applied_to_large_stone():
    result_small = appraise(_diamond_ring_piece(carat=0.30, price_per_carat=None))
    result_large = appraise(_diamond_ring_piece(carat=3.00, price_per_carat=None))

    ppc_small = result_small["stones_schedule"][0]["price_per_carat"]
    ppc_large = result_large["stones_schedule"][0]["price_per_carat"]
    # Large stone gets size premium on catalog price
    assert ppc_large > ppc_small


# ---------------------------------------------------------------------------
# Test 24: grade_multiplier returns > 1 for top grades, < 1 for low grades
# ---------------------------------------------------------------------------

def test_grade_multiplier_ordering():
    mult_top = _grade_multiplier("diamond", "D", "FL")
    mult_mid = _grade_multiplier("diamond", "G", "VS1")
    mult_low = _grade_multiplier("diamond", "J", "SI2")
    assert mult_top > mult_mid > mult_low


# ---------------------------------------------------------------------------
# Test 25: LLM tool run_jewelry_appraise returns ok payload
# ---------------------------------------------------------------------------

def test_llm_tool_appraise_ok():
    piece = _diamond_ring_piece()
    args = json.dumps({"piece": piece}).encode()
    ctx = make_ctx()
    resp_str = run(run_jewelry_appraise(ctx, args))
    resp = json.loads(resp_str)
    # ok_payload unwraps directly — no "ok" wrapper key
    assert "error" not in resp, f"Unexpected error: {resp}"
    assert "replacement_value" in resp
    assert "certificate_md" in resp
    assert resp["replacement_value"] >= resp["fair_market_value"] >= resp["liquidation_value"] >= 0


# ---------------------------------------------------------------------------
# Test 26: LLM tool run_jewelry_value_summary returns ok payload
# ---------------------------------------------------------------------------

def test_llm_tool_value_summary_ok():
    appraisal_result = appraise(_diamond_ring_piece())
    args = json.dumps({"appraisal": appraisal_result}).encode()
    ctx = make_ctx()
    resp_str = run(run_jewelry_value_summary(ctx, args))
    resp = json.loads(resp_str)
    # ok_payload unwraps directly
    assert "error" not in resp, f"Unexpected error: {resp}"
    assert "replacement" in resp
    assert "fair_market" in resp
    assert "liquidation" in resp


# ---------------------------------------------------------------------------
# Test 27: LLM tool bad args — missing piece
# ---------------------------------------------------------------------------

def test_llm_tool_appraise_missing_piece():
    args = json.dumps({}).encode()
    ctx = make_ctx()
    resp_str = run(run_jewelry_appraise(ctx, args))
    resp = json.loads(resp_str)
    # err_payload returns {"error": ..., "code": ...}
    assert resp.get("code") == "BAD_ARGS"
    assert "error" in resp


# ---------------------------------------------------------------------------
# Test 28: zero-carat stone produces zero value, no raise
# ---------------------------------------------------------------------------

def test_zero_carat_stone_value_zero():
    piece = {
        "description": "Zero carat test",
        "metal": {"alloy": "14k_yellow", "weight_grams": 3.0, "spot_price_per_gram": 37.0},
        "stones": [
            {"stone_type": "diamond", "cut": "round_brilliant", "carat": 0.0, "price_per_carat": 10000.0}
        ],
        "labor_value": 0.0,
    }
    result = appraise(piece)
    assert result["stones_schedule"][0]["stone_value"] == 0.0
    assert any("carat" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Test 29: catalog_mid_price returns positive for known gem types
# ---------------------------------------------------------------------------

def test_catalog_mid_price_known_gems():
    for gem in ("diamond", "ruby", "sapphire", "emerald"):
        mid = _catalog_mid_price(gem)
        assert mid > 0.0, f"Expected positive catalog price for {gem}"


# ---------------------------------------------------------------------------
# Test 30: appraise with liquidation_multiplier clamping when > fair_market
# ---------------------------------------------------------------------------

def test_liquidation_mult_clamped_above_fair_market():
    cfg = AppraisalConfig(
        replacement_multiplier=1.0,
        fair_market_multiplier=0.50,
        liquidation_multiplier=0.80,  # higher than fair_market → should be clamped
    )
    result = appraise(_diamond_ring_piece(), cfg)
    assert result["liquidation_value"] <= result["fair_market_value"]
    assert any("liquidation" in w for w in result["warnings"])
