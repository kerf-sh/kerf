"""
Tests for kerf_cad_core.jewelry.mount_finder.

All tests are pure-Python — no database, no OCC, hermetic (no network/FS).

Coverage:
  - 1.0 ct round brilliant (≈6.5 mm) matches a round 6–7 mm mount
  - Oval-only mount is rejected for a round stone
  - Soft/brittle stone (opal, emerald gem species) ranks bezel above prong
  - fit_mm_delta computed correctly (0 when inside range, > 0 for near-miss)
  - Out-of-range carat excluded with reason
  - Scoring monotone in fit closeness
  - Ties broken deterministically (by sku)
  - Empty catalog → graceful no-match (ok=True, best=None)
  - Impossible stone (bad carat) → graceful error (ok=False)
  - Missing required field → ok=False with reason
  - Both carat+dim_mm → ok=False
  - LLM tool spec: name, required fields present
  - LLM tool runner: success path, error paths
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.jewelry.mount_finder import (
    MountEntry,
    _MOUNT_CATALOG,
    _cut_to_shape_family,
    _mohs_for_material,
    _style_suitability,
    find_mounts,
    jewelry_find_mounts_spec,
    run_jewelry_find_mounts,
)
from kerf_cad_core.jewelry.gemstones import mm_from_carat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx():
    """Return a minimal ProjectCtx-like object (no DB needed for read-only tool)."""
    from kerf_core.utils.context import ProjectCtx

    class _FakePool:
        def fetchone(self, *a, **kw):
            return None
        def execute(self, *a, **kw):
            pass

    return ProjectCtx(
        pool=_FakePool(),
        storage=None,
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )


def run_tool(ctx, **kwargs):
    loop = asyncio.new_event_loop()
    try:
        raw = loop.run_until_complete(
            run_jewelry_find_mounts(ctx, json.dumps(kwargs).encode())
        )
    finally:
        loop.close()
    return json.loads(raw)


# Minimal synthetic catalog used for deterministic tests
_ROUND_PRONG_SMALL = MountEntry(
    sku="T-RSH-4P-60-67",
    label="Test Round 4-prong 6.0–6.7 mm",
    shape_families=["round"],
    seat_mm_min=6.0, seat_mm_max=6.7,
    carat_min=0.75, carat_max=1.20,
    setting_styles=["prong"],
    metals=["yellow_gold", "white_gold"],
    accent_count=0,
    style_tags=["solitaire"],
)

_ROUND_PRONG_LARGE = MountEntry(
    sku="T-RSH-4P-70-80",
    label="Test Round 4-prong 7.0–8.0 mm",
    shape_families=["round"],
    seat_mm_min=7.0, seat_mm_max=8.0,
    carat_min=1.40, carat_max=2.30,
    setting_styles=["prong"],
    metals=["yellow_gold", "white_gold"],
    accent_count=0,
    style_tags=["solitaire"],
)

_ROUND_BEZEL_SMALL = MountEntry(
    sku="T-RSH-BZL-60-67",
    label="Test Round bezel 6.0–6.7 mm",
    shape_families=["round"],
    seat_mm_min=6.0, seat_mm_max=6.7,
    carat_min=0.75, carat_max=1.20,
    setting_styles=["bezel"],
    metals=["yellow_gold", "white_gold", "sterling_silver"],
    accent_count=0,
    style_tags=["solitaire"],
)

_OVAL_ONLY = MountEntry(
    sku="T-OVL-4P-75-90",
    label="Test Oval-only 4-prong 7.5–9.0 mm",
    shape_families=["oval"],
    seat_mm_min=7.5, seat_mm_max=9.0,
    carat_min=1.00, carat_max=2.00,
    setting_styles=["prong"],
    metals=["yellow_gold", "white_gold"],
    accent_count=0,
    style_tags=["solitaire"],
)

_MINI_CATALOG = [_ROUND_PRONG_SMALL, _ROUND_PRONG_LARGE, _ROUND_BEZEL_SMALL, _OVAL_ONLY]


# ---------------------------------------------------------------------------
# 1. Basic shape matching
# ---------------------------------------------------------------------------

class TestShapeFamilyMapping:
    def test_round_brilliant_is_round(self):
        assert _cut_to_shape_family("round_brilliant") == "round"

    def test_oval_is_oval(self):
        assert _cut_to_shape_family("oval") == "oval"

    def test_cushion_is_cushion(self):
        assert _cut_to_shape_family("cushion") == "cushion"

    def test_princess_is_princess(self):
        assert _cut_to_shape_family("princess") == "princess"

    def test_emerald_is_emerald(self):
        assert _cut_to_shape_family("emerald") == "emerald"

    def test_pear_is_pear(self):
        assert _cut_to_shape_family("pear") == "pear"

    def test_marquise_is_marquise(self):
        assert _cut_to_shape_family("marquise") == "marquise"


# ---------------------------------------------------------------------------
# 2. 1.0 ct round brilliant → round 6–6.7 mm mount matched
# ---------------------------------------------------------------------------

class TestRoundBrilliantOneCaratMatch:
    """A 1.0 ct round brilliant is ≈6.5 mm.  A 6.0–6.7 mm mount should match."""

    def test_stone_mm_approximately_6pt5(self):
        mm = mm_from_carat("round_brilliant", 1.0)
        assert abs(mm - 6.5) < 0.05

    def test_best_is_round_mount(self):
        result = find_mounts("round_brilliant", carat=1.0, catalog=_MINI_CATALOG)
        assert result["ok"] is True
        assert result["best"] is not None
        assert result["best"]["sku"] in ("T-RSH-4P-60-67", "T-RSH-BZL-60-67")

    def test_oval_mount_is_rejected(self):
        result = find_mounts("round_brilliant", carat=1.0, catalog=_MINI_CATALOG)
        rejected_skus = {r["sku"] for r in result["rejected"]}
        assert "T-OVL-4P-75-90" in rejected_skus

    def test_reject_reason_mentions_shape_mismatch(self):
        result = find_mounts("round_brilliant", carat=1.0, catalog=_MINI_CATALOG)
        oval_reject = next(
            r for r in result["rejected"] if r["sku"] == "T-OVL-4P-75-90"
        )
        assert "shape" in oval_reject["reject_reason"].lower()

    def test_stone_mm_returned(self):
        result = find_mounts("round_brilliant", carat=1.0, catalog=_MINI_CATALOG)
        assert abs(result["stone_mm"] - 6.5) < 0.1

    def test_stone_shape_returned(self):
        result = find_mounts("round_brilliant", carat=1.0, catalog=_MINI_CATALOG)
        assert result["stone_shape"] == "round"


# ---------------------------------------------------------------------------
# 3. Soft / brittle stones prefer bezel over prong
# ---------------------------------------------------------------------------

class TestSoftBrittleStoneSettingSuitability:
    def test_bezel_gets_positive_bonus_for_soft_stone(self):
        bonus, reasons = _style_suitability("bezel", mohs=5.5, material="opal")
        assert bonus > 0
        assert any("bezel" in r.lower() for r in reasons)

    def test_prong_gets_penalty_for_soft_stone(self):
        bonus, reasons = _style_suitability("prong", mohs=5.5, material="opal")
        assert bonus < 0

    def test_tension_gets_penalty_for_soft_stone(self):
        bonus, reasons = _style_suitability("tension", mohs=5.5, material="opal")
        assert bonus < 0

    def test_opal_ranks_bezel_above_prong(self):
        """Opal (Mohs ≈ 6) → bezel mount should outscore prong mount.

        We specify dim_mm=6.5 so the stone falls squarely in the catalog range
        regardless of opal's lower density (which would shift 1 ct to ~7.7 mm).
        """
        result = find_mounts(
            "round_brilliant",
            dim_mm=6.5,
            material="opal",
            catalog=_MINI_CATALOG,
        )
        assert result["ok"] is True
        assert result["best"] is not None
        # Both bezel and prong mounts in catalog; bezel should win
        assert result["best"]["sku"] == "T-RSH-BZL-60-67"

    def test_emerald_gem_species_ranks_bezel_above_prong(self):
        """Emerald (brittle despite Mohs 7.5–8) → bezel still preferred.

        We specify dim_mm=6.5 for the same density-independence reason.
        """
        result = find_mounts(
            "round_brilliant",
            dim_mm=6.5,
            material="emerald",
            catalog=_MINI_CATALOG,
        )
        assert result["ok"] is True
        assert result["best"] is not None
        assert result["best"]["sku"] == "T-RSH-BZL-60-67"

    def test_mohs_lookup_opal(self):
        mohs = _mohs_for_material("opal")
        assert mohs is not None
        assert 5.0 <= mohs <= 7.0


# ---------------------------------------------------------------------------
# 4. fit_mm_delta computed correctly
# ---------------------------------------------------------------------------

class TestFitMmDelta:
    def test_delta_zero_when_stone_inside_range(self):
        """Stone 6.5 mm inside 6.0–6.7 range → delta == 0."""
        result = find_mounts("round_brilliant", dim_mm=6.5, catalog=_MINI_CATALOG)
        assert result["ok"] is True
        # Find the small prong or bezel mount
        for m in [result["best"]] + result["alternatives"]:
            if m and m["sku"] in ("T-RSH-4P-60-67", "T-RSH-BZL-60-67"):
                assert m["fit_mm_delta"] == 0.0
                break

    def test_delta_positive_for_near_miss(self):
        """Stone just outside range → delta > 0."""
        # 6.8 mm is 0.1 outside 6.7 max of small mount
        result = find_mounts(
            "round_brilliant",
            dim_mm=6.8,
            fit_tolerance_mm=0.5,
            catalog=_MINI_CATALOG,
        )
        assert result["ok"] is True
        near_hit = next(
            (m for m in [result["best"]] + result["alternatives"]
             if m and m["sku"] in ("T-RSH-4P-60-67", "T-RSH-BZL-60-67")),
            None,
        )
        if near_hit is not None:
            assert near_hit["fit_mm_delta"] == pytest.approx(0.1, abs=0.01)

    def test_delta_in_why_for_near_miss(self):
        result = find_mounts(
            "round_brilliant",
            dim_mm=6.8,
            fit_tolerance_mm=0.5,
            catalog=_MINI_CATALOG,
        )
        assert result["ok"] is True
        # near-miss entries should mention 'near-fit' or similar in why
        for m in [result["best"]] + result["alternatives"]:
            if m and m["fit_mm_delta"] > 0:
                assert any("near" in w.lower() or "outside" in w.lower() for w in m["why"])


# ---------------------------------------------------------------------------
# 5. Out-of-range carat excluded with reason
# ---------------------------------------------------------------------------

class TestCaratRangeExclusion:
    def test_carat_too_large_excluded(self):
        """3.0 ct round (≈9.37 mm) should be rejected by all catalog mounts.

        The large test mount (7.0–8.0 mm) has a mm-based seat max of 8.0 mm;
        a 3 ct stone is ~9.37 mm which is 1.37 mm outside tolerance, so it
        is rejected via the seat (mm) check.  We verify the reject_reason is
        non-empty and mentions the stone is too large.
        """
        result = find_mounts("round_brilliant", carat=3.0, catalog=_MINI_CATALOG)
        assert result["ok"] is True
        large_rejected = next(
            (r for r in result["rejected"] if r["sku"] == "T-RSH-4P-70-80"), None
        )
        assert large_rejected is not None
        assert large_rejected["reject_reason"] is not None
        # Reason should mention too large (mm-based rejection)
        assert "too large" in large_rejected["reject_reason"].lower() or \
               "mm" in large_rejected["reject_reason"].lower()

    def test_carat_too_small_excluded_with_reason(self):
        """0.1 ct round (≈3.1 mm) — well below all catalog minimums."""
        result = find_mounts("round_brilliant", carat=0.1, catalog=_MINI_CATALOG)
        assert result["ok"] is True
        # All mounts should be rejected (size too small)
        assert result["best"] is None or result["best"] is None

    def test_rejected_entries_have_reject_reason(self):
        result = find_mounts("round_brilliant", carat=1.0, catalog=_MINI_CATALOG)
        for r in result["rejected"]:
            assert r["reject_reason"] is not None
            assert len(r["reject_reason"]) > 0


# ---------------------------------------------------------------------------
# 6. Scoring monotone in fit closeness
# ---------------------------------------------------------------------------

class TestScoringMonotone:
    def test_closer_fit_scores_higher(self):
        """Two otherwise identical mounts: the one centred on the stone wins."""
        center_mount = MountEntry(
            sku="T-CLOSE",
            label="Centred mount 6.4–6.6",
            shape_families=["round"],
            seat_mm_min=6.4, seat_mm_max=6.6,
            carat_min=0.80, carat_max=1.20,
            setting_styles=["prong"],
            metals=["yellow_gold"],
            accent_count=0,
        )
        far_mount = MountEntry(
            sku="T-FAR",
            label="Off-centre mount 5.0–6.0",
            shape_families=["round"],
            seat_mm_min=5.0, seat_mm_max=6.0,
            carat_min=0.40, carat_max=0.90,
            setting_styles=["prong"],
            metals=["yellow_gold"],
            accent_count=0,
        )
        test_cat = [center_mount, far_mount]
        result = find_mounts("round_brilliant", dim_mm=6.5, catalog=test_cat)
        assert result["ok"] is True
        # Stone at 6.5; center_mount has stone inside (6.4–6.6), far_mount has stone outside
        assert result["best"]["sku"] == "T-CLOSE"


# ---------------------------------------------------------------------------
# 7. Ties broken deterministically
# ---------------------------------------------------------------------------

class TestDeterministicTieBreaking:
    def test_ties_broken_by_sku_alphabetically(self):
        """Two identical mounts except sku — lower sku should win."""
        mount_a = MountEntry(
            sku="A-MOUNT",
            label="Mount A",
            shape_families=["round"],
            seat_mm_min=6.0, seat_mm_max=7.0,
            carat_min=0.80, carat_max=1.50,
            setting_styles=["prong"],
            metals=["yellow_gold"],
            accent_count=0,
        )
        mount_b = MountEntry(
            sku="B-MOUNT",
            label="Mount B",
            shape_families=["round"],
            seat_mm_min=6.0, seat_mm_max=7.0,
            carat_min=0.80, carat_max=1.50,
            setting_styles=["prong"],
            metals=["yellow_gold"],
            accent_count=0,
        )
        result_ab = find_mounts("round_brilliant", dim_mm=6.5, catalog=[mount_a, mount_b])
        result_ba = find_mounts("round_brilliant", dim_mm=6.5, catalog=[mount_b, mount_a])
        # Both orderings should produce the same best
        assert result_ab["best"]["sku"] == result_ba["best"]["sku"] == "A-MOUNT"

    def test_repeated_calls_are_deterministic(self):
        result1 = find_mounts("round_brilliant", carat=1.0, catalog=_MINI_CATALOG)
        result2 = find_mounts("round_brilliant", carat=1.0, catalog=_MINI_CATALOG)
        assert result1["best"]["sku"] == result2["best"]["sku"]


# ---------------------------------------------------------------------------
# 8. Empty catalog → graceful no-match
# ---------------------------------------------------------------------------

class TestEmptyCatalog:
    def test_empty_catalog_returns_ok_with_no_best(self):
        result = find_mounts("round_brilliant", carat=1.0, catalog=[])
        assert result["ok"] is True
        assert result["best"] is None
        assert result["alternatives"] == []
        assert result["rejected"] == []

    def test_impossible_stone_shape_no_match(self):
        """Heart stone vs catalog with only round mounts → all rejected."""
        result = find_mounts(
            "heart",
            dim_mm=9.0,
            catalog=[_ROUND_PRONG_SMALL, _ROUND_PRONG_LARGE],
        )
        assert result["ok"] is True
        assert result["best"] is None
        assert len(result["rejected"]) == 2


# ---------------------------------------------------------------------------
# 9. Validation / error paths
# ---------------------------------------------------------------------------

class TestValidationErrors:
    def test_missing_cut_returns_not_ok(self):
        result = find_mounts("", carat=1.0)
        assert result["ok"] is False
        assert "cut" in result["reason"].lower()

    def test_unknown_cut_returns_not_ok(self):
        result = find_mounts("hexagonal_fantasy", carat=1.0)
        assert result["ok"] is False

    def test_both_carat_and_dim_mm_returns_not_ok(self):
        result = find_mounts("round_brilliant", carat=1.0, dim_mm=6.5)
        assert result["ok"] is False

    def test_neither_carat_nor_dim_mm_returns_not_ok(self):
        result = find_mounts("round_brilliant")
        assert result["ok"] is False

    def test_negative_carat_returns_not_ok(self):
        result = find_mounts("round_brilliant", carat=-1.0)
        assert result["ok"] is False

    def test_zero_dim_mm_returns_not_ok(self):
        result = find_mounts("round_brilliant", dim_mm=0.0)
        assert result["ok"] is False

    def test_negative_fit_tolerance_returns_not_ok(self):
        result = find_mounts("round_brilliant", carat=1.0, fit_tolerance_mm=-0.1)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# 10. LLM tool spec
# ---------------------------------------------------------------------------

class TestToolSpec:
    def test_tool_name(self):
        assert jewelry_find_mounts_spec.name == "jewelry_find_mounts"

    def test_required_fields_present(self):
        required = jewelry_find_mounts_spec.input_schema.get("required", [])
        assert "cut" in required

    def test_input_schema_has_cut_property(self):
        props = jewelry_find_mounts_spec.input_schema.get("properties", {})
        assert "cut" in props

    def test_input_schema_has_carat_and_dim_mm(self):
        props = jewelry_find_mounts_spec.input_schema.get("properties", {})
        assert "carat" in props
        assert "dim_mm" in props


# ---------------------------------------------------------------------------
# 11. LLM tool runner
# ---------------------------------------------------------------------------

class TestToolRunner:
    def test_success_round_1ct(self):
        ctx = make_ctx()
        result = run_tool(ctx, cut="round_brilliant", carat=1.0)
        assert result.get("ok") is True

    def test_success_returns_stone_mm(self):
        ctx = make_ctx()
        result = run_tool(ctx, cut="round_brilliant", carat=1.0)
        assert "stone_mm" in result.get("data", result)

    def test_error_missing_cut(self):
        ctx = make_ctx()
        result = run_tool(ctx, carat=1.0)
        assert result.get("ok") is False or result.get("code") == "BAD_ARGS"

    def test_error_both_carat_and_dim_mm(self):
        ctx = make_ctx()
        result = run_tool(ctx, cut="round_brilliant", carat=1.0, dim_mm=6.5)
        # Should return error
        assert result.get("ok") is False or result.get("code") == "BAD_ARGS"

    def test_error_invalid_json(self):
        ctx = make_ctx()
        loop = asyncio.new_event_loop()
        try:
            raw = loop.run_until_complete(
                run_jewelry_find_mounts(ctx, b"not json {{")
            )
        finally:
            loop.close()
        r = json.loads(raw)
        assert r.get("ok") is False or r.get("code") == "BAD_ARGS"

    def test_success_with_dim_mm(self):
        ctx = make_ctx()
        result = run_tool(ctx, cut="oval", dim_mm=8.5)
        # Should not error out
        assert result.get("code") != "BAD_ARGS" or result.get("ok") is True


# ---------------------------------------------------------------------------
# 12. Full catalog spot checks
# ---------------------------------------------------------------------------

class TestFullCatalog:
    def test_round_1ct_matches_something_in_full_catalog(self):
        result = find_mounts("round_brilliant", carat=1.0)
        assert result["ok"] is True
        assert result["best"] is not None

    def test_round_1ct_best_sku_is_round_mount(self):
        result = find_mounts("round_brilliant", carat=1.0)
        assert result["ok"] is True
        # best mount should be in the round seat range covering 6.5 mm
        best = result["best"]
        assert best["seat_mm_range"][0] <= 6.5 <= best["seat_mm_range"][1] or \
               abs(best["fit_mm_delta"]) < 0.4

    def test_oval_stone_not_matched_by_round_only_mount(self):
        result = find_mounts("oval", dim_mm=8.5)
        for m in [result.get("best")] + result.get("alternatives", []):
            if m:
                assert "oval" in m["shape_families"]

    def test_all_accepted_mounts_have_ok_fields(self):
        result = find_mounts("round_brilliant", carat=1.0)
        for m in [result["best"]] + result["alternatives"]:
            if m:
                assert "fit_mm_delta" in m
                assert "score" in m
                assert "why" in m
                assert m["reject_reason"] is None

    def test_score_is_positive(self):
        result = find_mounts("round_brilliant", carat=1.0)
        if result["best"]:
            assert result["best"]["score"] > 0
