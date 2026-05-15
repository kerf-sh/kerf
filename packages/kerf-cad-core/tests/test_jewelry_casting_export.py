"""
Tests for kerf_cad_core.jewelry.casting_export

Pure-Python: no OCC, no database, no project context required.
All tests run hermetically with no external dependencies.

Covers:
  - SHRINKAGE_PCT table completeness and per-alloy values
  - Fallback shrinkage for unknown alloys
  - apply_shrinkage_scale math (correct scale-up factor)
  - _sprue_strategy heuristic by piece volume
  - estimate_metal_grams integrates with metal_cost density table
  - estimate_pour_grams per sprue count
  - casting_export_summary: full output structure
  - casting_export_summary: gemstone exclusion list
  - casting_export_summary: unknown alloy raises ValueError
  - casting_export_summary: non-positive volume raises ValueError
  - casting_export_summary: thin wall appends caution hint
  - casting_export_summary: stl_bytes is None without OCC shape
  - LLM tool (run_jewelry_casting_export) via asyncio:
      - happy path returns ok payload
      - missing alloy returns err
      - unknown alloy returns err
      - missing volume returns err
      - non-positive volume returns err
      - gemstone_refs stored correctly
      - all alloy keys round-trip through the tool
      - platinum_950 gets higher shrinkage than 18k_yellow
      - sterling_925 has correct shrinkage
"""

from __future__ import annotations

import asyncio
import json
import math
import pytest

from kerf_cad_core.jewelry.casting_export import (
    SHRINKAGE_PCT,
    _SHRINKAGE_FALLBACK,
    _SMALL_THRESHOLD,
    _MEDIUM_THRESHOLD,
    _LARGE_THRESHOLD,
    _sprue_strategy,
    apply_shrinkage_scale,
    casting_export_summary,
    estimate_metal_grams,
    estimate_pour_grams,
    get_shrinkage_pct,
)
from kerf_cad_core.jewelry.metal_cost import METAL_DENSITY_G_CM3, METAL_LABELS


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run_tool(**kwargs) -> dict:
    from kerf_cad_core.jewelry.casting_export import run_jewelry_casting_export
    raw = asyncio.new_event_loop().run_until_complete(
        run_jewelry_casting_export(None, json.dumps(kwargs).encode())
    )
    return json.loads(raw)


def approx(expected, rel=1e-4):
    return pytest.approx(expected, rel=rel)


# ============================================================================
# 1. SHRINKAGE_PCT table
# ============================================================================

class TestShrinkagePctTable:
    def test_all_metal_keys_covered(self):
        """Every key in METAL_DENSITY_G_CM3 should have a shrinkage entry."""
        missing = [k for k in METAL_DENSITY_G_CM3 if k not in SHRINKAGE_PCT]
        assert missing == [], f"Missing shrinkage entries for: {missing}"

    def test_values_are_positive(self):
        for k, v in SHRINKAGE_PCT.items():
            assert v > 0, f"Shrinkage for {k} must be > 0"

    def test_values_within_plausible_range(self):
        """Casting shrinkage is always in (0%, 3%)."""
        for k, v in SHRINKAGE_PCT.items():
            assert 0.0 < v < 3.0, f"Shrinkage for {k}={v} outside (0, 3)"

    def test_18k_yellow_gold_value(self):
        assert SHRINKAGE_PCT["18k_yellow"] == pytest.approx(1.25)

    def test_18k_white_gold_value(self):
        assert SHRINKAGE_PCT["18k_white"] == pytest.approx(1.30)

    def test_platinum_950_value(self):
        assert SHRINKAGE_PCT["platinum_950"] == pytest.approx(1.80)

    def test_sterling_925_value(self):
        assert SHRINKAGE_PCT["sterling_925"] == pytest.approx(1.40)

    def test_platinum_higher_than_yellow_gold(self):
        assert SHRINKAGE_PCT["platinum_950"] > SHRINKAGE_PCT["18k_yellow"]

    def test_white_gold_higher_than_yellow_gold_same_karat(self):
        assert SHRINKAGE_PCT["18k_white"] > SHRINKAGE_PCT["18k_yellow"]


# ============================================================================
# 2. get_shrinkage_pct fallback
# ============================================================================

class TestGetShrinkagePct:
    def test_known_alloy(self):
        assert get_shrinkage_pct("18k_yellow") == pytest.approx(1.25)

    def test_unknown_alloy_returns_fallback(self):
        result = get_shrinkage_pct("unobtanium_999")
        assert result == pytest.approx(_SHRINKAGE_FALLBACK)

    def test_case_insensitive(self):
        assert get_shrinkage_pct("18K_YELLOW") == get_shrinkage_pct("18k_yellow")

    def test_fallback_is_1_25(self):
        assert _SHRINKAGE_FALLBACK == pytest.approx(1.25)


# ============================================================================
# 3. apply_shrinkage_scale
# ============================================================================

class TestApplyShrinkageScale:
    def test_zero_shrinkage_returns_unchanged(self):
        assert apply_shrinkage_scale(10.0, 0.0) == pytest.approx(10.0)

    def test_1_25_pct_scale_factor(self):
        """Scale = 1 / (1 - 0.0125) = 1.012658..."""
        expected = 10.0 / (1.0 - 0.0125)
        assert apply_shrinkage_scale(10.0, 1.25) == approx(expected)

    def test_platinum_scale_factor(self):
        """Platinum 950 shrinkage = 1.80%; scale = 1 / (1 - 0.018)."""
        expected = 20.0 / (1.0 - 0.018)
        assert apply_shrinkage_scale(20.0, 1.80) == approx(expected)

    def test_result_larger_than_input(self):
        """Wax pattern must always be larger than finished dimension."""
        assert apply_shrinkage_scale(5.0, 1.25) > 5.0

    def test_negative_dimension_raises(self):
        with pytest.raises(ValueError):
            apply_shrinkage_scale(-1.0, 1.25)

    def test_zero_dimension_raises(self):
        with pytest.raises(ValueError):
            apply_shrinkage_scale(0.0, 1.25)

    def test_negative_shrinkage_raises(self):
        with pytest.raises(ValueError):
            apply_shrinkage_scale(10.0, -0.5)

    def test_linearity_with_dimension(self):
        """Scale factor is independent of dimension size."""
        s1 = apply_shrinkage_scale(5.0, 1.40) / 5.0
        s2 = apply_shrinkage_scale(50.0, 1.40) / 50.0
        assert s1 == approx(s2)


# ============================================================================
# 4. _sprue_strategy heuristic
# ============================================================================

class TestSprueStrategy:
    def test_small_piece_1_sprue(self):
        s = _sprue_strategy(200.0, 1.0)
        assert s["sprue_count"] == 1

    def test_small_piece_orientation_z_up(self):
        s = _sprue_strategy(200.0, 1.0)
        assert "+Z up" in s["recommended_orientation"]

    def test_medium_piece_1_sprue(self):
        s = _sprue_strategy(1000.0, 1.5)
        assert s["sprue_count"] == 1

    def test_large_piece_2_sprues(self):
        s = _sprue_strategy(3000.0, 1.5)
        assert s["sprue_count"] == 2

    def test_very_large_piece_3_sprues(self):
        s = _sprue_strategy(8000.0, 2.0)
        assert s["sprue_count"] == 3

    def test_sprue_strategy_has_required_keys(self):
        s = _sprue_strategy(1000.0, 1.0)
        for key in ("sprue_count", "sprue_location", "support_hint", "recommended_orientation"):
            assert key in s, f"Missing key: {key}"

    def test_thin_wall_caution_appended(self):
        s = _sprue_strategy(1000.0, 0.4)
        assert "thin wall" in s["support_hint"].lower() or "0.6 mm" in s["support_hint"]

    def test_normal_wall_no_thin_wall_warning(self):
        s = _sprue_strategy(1000.0, 1.5)
        assert "CAUTION" not in s["support_hint"]

    def test_boundary_small_threshold(self):
        """Volume exactly at _SMALL_THRESHOLD goes to medium bucket."""
        s_below = _sprue_strategy(_SMALL_THRESHOLD - 1, 1.0)
        s_at = _sprue_strategy(_SMALL_THRESHOLD, 1.0)
        assert s_below["sprue_count"] == 1
        # At boundary: medium bucket → still 1 sprue
        assert s_at["sprue_count"] == 1


# ============================================================================
# 5. estimate_metal_grams
# ============================================================================

class TestEstimateMetalGrams:
    def test_18k_yellow_1000mm3(self):
        """18k yellow density = 15.58 g/cm³; 1000 mm³ = 1 cm³ → 15.58 g."""
        result = estimate_metal_grams(1000.0, "18k_yellow")
        assert result == approx(15.58)

    def test_platinum_950_1000mm3(self):
        """Platinum 950 density = 21.40 g/cm³."""
        result = estimate_metal_grams(1000.0, "platinum_950")
        assert result == approx(21.40)

    def test_sterling_925_1000mm3(self):
        """Sterling 925 density = 10.36 g/cm³."""
        result = estimate_metal_grams(1000.0, "sterling_925")
        assert result == approx(10.36)

    def test_weight_proportional_to_volume(self):
        g1 = estimate_metal_grams(500.0, "14k_yellow")
        g2 = estimate_metal_grams(1000.0, "14k_yellow")
        assert g2 == approx(g1 * 2.0)


# ============================================================================
# 6. estimate_pour_grams
# ============================================================================

class TestEstimatePourGrams:
    def test_1_sprue_12_pct_overhead(self):
        result = estimate_pour_grams(10.0, 1)
        assert result == approx(10.0 * 1.12)

    def test_2_sprues_16_pct_overhead(self):
        result = estimate_pour_grams(10.0, 2)
        assert result == approx(10.0 * 1.16)

    def test_3_sprues_20_pct_overhead(self):
        result = estimate_pour_grams(10.0, 3)
        assert result == approx(10.0 * 1.20)

    def test_pour_greater_than_net(self):
        net = 5.0
        pour = estimate_pour_grams(net, 1)
        assert pour > net

    def test_negative_net_grams_raises(self):
        with pytest.raises(ValueError):
            estimate_pour_grams(-1.0, 1)

    def test_zero_net_grams_raises(self):
        with pytest.raises(ValueError):
            estimate_pour_grams(0.0, 1)

    def test_sprue_count_zero_raises(self):
        with pytest.raises(ValueError):
            estimate_pour_grams(10.0, 0)


# ============================================================================
# 7. casting_export_summary
# ============================================================================

class TestCastingExportSummary:
    def _summary(self, **kwargs):
        defaults = {"alloy": "18k_yellow", "volume_mm3": 1000.0}
        defaults.update(kwargs)
        return casting_export_summary(**defaults)

    def test_returns_dict(self):
        assert isinstance(self._summary(), dict)

    def test_required_keys_present(self):
        s = self._summary()
        for key in (
            "alloy", "alloy_label", "shrinkage_pct", "volume_mm3", "thickness_mm",
            "gemstones_excluded", "est_metal_grams", "est_pour_grams_with_sprue",
            "sprue_count", "sprue_location", "recommended_orientation",
            "support_hint", "stl_bytes", "occ_available",
        ):
            assert key in s, f"Missing key: {key}"

    def test_alloy_key_stored(self):
        s = self._summary(alloy="18k_yellow")
        assert s["alloy"] == "18k_yellow"

    def test_alloy_label_populated(self):
        s = self._summary(alloy="18k_yellow")
        assert s["alloy_label"] == METAL_LABELS["18k_yellow"]

    def test_shrinkage_pct_correct_for_platinum(self):
        s = self._summary(alloy="platinum_950")
        assert s["shrinkage_pct"] == pytest.approx(1.80)

    def test_stl_bytes_none_without_occ(self):
        s = self._summary()
        assert s["stl_bytes"] is None

    def test_occ_available_false_without_shape(self):
        s = self._summary()
        assert s["occ_available"] is False

    def test_gemstones_excluded_default_empty(self):
        s = self._summary()
        assert s["gemstones_excluded"] == []

    def test_gemstones_excluded_stored(self):
        gems = ["diamond_centre", "ruby_1", "ruby_2"]
        s = casting_export_summary(
            alloy="18k_yellow",
            volume_mm3=1000.0,
            gemstone_refs=gems,
        )
        assert s["gemstones_excluded"] == gems

    def test_gems_excluded_does_not_affect_weight(self):
        """Gemstone exclusion list is informational — weight unchanged."""
        s_no_gems = self._summary(volume_mm3=1500.0)
        s_with_gems = casting_export_summary(
            alloy="18k_yellow",
            volume_mm3=1500.0,
            gemstone_refs=["diamond_1"],
        )
        assert s_no_gems["est_metal_grams"] == approx(s_with_gems["est_metal_grams"])

    def test_unknown_alloy_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown alloy"):
            casting_export_summary(alloy="unobtanium_999", volume_mm3=1000.0)

    def test_non_positive_volume_raises(self):
        with pytest.raises(ValueError):
            casting_export_summary(alloy="18k_yellow", volume_mm3=0.0)

    def test_negative_volume_raises(self):
        with pytest.raises(ValueError):
            casting_export_summary(alloy="18k_yellow", volume_mm3=-100.0)

    def test_thickness_stored(self):
        s = casting_export_summary(alloy="18k_yellow", volume_mm3=1000.0, thickness_mm=0.5)
        assert s["thickness_mm"] == pytest.approx(0.5)

    def test_thin_wall_caution_in_support_hint(self):
        s = casting_export_summary(alloy="18k_yellow", volume_mm3=1000.0, thickness_mm=0.4)
        assert "CAUTION" in s["support_hint"] or "thin wall" in s["support_hint"].lower()

    def test_est_metal_grams_matches_density(self):
        """1000 mm³ of 18k yellow = 15.58 g (density 15.58 g/cm³)."""
        s = self._summary(alloy="18k_yellow", volume_mm3=1000.0)
        assert s["est_metal_grams"] == approx(15.58)

    def test_pour_grams_greater_than_metal_grams(self):
        s = self._summary()
        assert s["est_pour_grams_with_sprue"] > s["est_metal_grams"]


# ============================================================================
# 8. LLM tool (run_jewelry_casting_export)
# ============================================================================

class TestLLMTool:
    def test_happy_path_no_error_key(self):
        """Successful response has no 'error' key."""
        result = _run_tool(alloy="18k_yellow", volume_mm3=1000.0)
        assert "error" not in result

    def test_happy_path_summary_in_result(self):
        result = _run_tool(alloy="18k_yellow", volume_mm3=1000.0)
        assert "casting_summary" in result

    def test_missing_alloy_returns_err(self):
        result = _run_tool(volume_mm3=1000.0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_unknown_alloy_returns_err(self):
        result = _run_tool(alloy="unobtanium_999", volume_mm3=1000.0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_missing_volume_returns_err(self):
        result = _run_tool(alloy="18k_yellow")
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_zero_volume_returns_err(self):
        result = _run_tool(alloy="18k_yellow", volume_mm3=0.0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_negative_volume_returns_err(self):
        result = _run_tool(alloy="18k_yellow", volume_mm3=-500.0)
        assert "error" in result

    def test_gemstone_refs_stored_in_summary(self):
        refs = ["diamond_centre", "ruby_side"]
        result = _run_tool(alloy="18k_yellow", volume_mm3=1000.0, gemstone_refs=refs)
        summary = result["casting_summary"]
        assert summary["gemstones_excluded"] == refs

    def test_stl_available_false_in_tool_path(self):
        result = _run_tool(alloy="18k_yellow", volume_mm3=1000.0)
        summary = result["casting_summary"]
        assert summary["stl_available"] is False

    def test_platinum_950_shrinkage_in_tool(self):
        result = _run_tool(alloy="platinum_950", volume_mm3=500.0)
        summary = result["casting_summary"]
        assert summary["shrinkage_pct"] == pytest.approx(1.80)

    def test_sterling_925_shrinkage_in_tool(self):
        result = _run_tool(alloy="sterling_925", volume_mm3=500.0)
        summary = result["casting_summary"]
        assert summary["shrinkage_pct"] == pytest.approx(1.40)

    def test_all_known_alloys_round_trip(self):
        """Every alloy in METAL_DENSITY_G_CM3 should succeed via the tool."""
        failures = []
        for alloy_key in METAL_DENSITY_G_CM3:
            result = _run_tool(alloy=alloy_key, volume_mm3=1000.0)
            if "error" in result:
                failures.append(alloy_key)
        assert failures == [], f"Tool failed for alloys: {failures}"

    def test_invalid_json_returns_err(self):
        from kerf_cad_core.jewelry.casting_export import run_jewelry_casting_export
        raw = asyncio.new_event_loop().run_until_complete(
            run_jewelry_casting_export(None, b"not-valid-json{{{")
        )
        result = json.loads(raw)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"
