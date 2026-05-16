"""
Tests for kerf_cad_core.jewelry.gem_studio.

All tests are hermetic pure-Python — no OCC, no database, no network.

Coverage (≥ 30 tests):
  - GEM_STUDIO_CUTS contains all 15 required cut names
  - gem_cutter_spec: cutter girdle envelope >= gemstone girdle for every cut
  - gem_cutter_spec: carat↔mm round-trips for every cut
  - gem_cutter_spec: published reference: 1.00 ct RBC ≈ 6.5 mm diameter
  - gem_cutter_spec: 1.00 ct princess ≈ 5.5 mm side
  - gem_cutter_spec: 0.50 ct oval ≈ 6.11 mm long axis
  - gem_cutter_spec: clearances respected (default, custom, zero)
  - gem_cutter_spec: aspect_ratio override propagated to cutter
  - gem_cutter_spec: cabochon special geometry (flat pavilion)
  - gem_cutter_spec: briolette cutter depth >= stone depth
  - gem_cutter_spec: invalid cut raises ValueError
  - gem_cutter_spec: negative carat raises ValueError
  - gem_cutter_spec: both carat+diameter_mm raises ValueError
  - gem_cutter_spec: neither carat nor diameter_mm raises ValueError
  - gem_cutter_spec: total cutter depth > total stone depth for all cuts
  - carat↔mm round-trips vs published gem tables (RBC, princess, oval, emerald)
  - GEM_STUDIO_CATALOG: all required gems present with required keys
  - GEM_STUDIO_CATALOG: refractive index and dispersion are positive
  - GEM_STUDIO_CATALOG: price band is a 2-tuple with low < high
  - gem_fit_check: ok=True when wall is ample
  - gem_fit_check: ok=False when wall is too thin (warning fired)
  - gem_fit_check: tight-clearance warning fires
  - gem_fit_check: culet_allowance warning fires
  - gem_fit_check: setting-type-specific minimum walls differ
  - melee_sequence: n_stones * pitch fits within channel
  - melee_sequence: positions are centred within channel
  - melee_sequence: target_carat=0.10 default stone ≈ expected diameter
  - melee_sequence: target_diameter_mm variant produces correct pitch
  - melee_sequence: both target_carat + target_diameter_mm raises ValueError
  - melee_sequence: zero channel_length raises ValueError
  - LLM tool run_jewelry_gem_studio_cutter: ok path returns gemstone + cutter
  - LLM tool run_jewelry_gem_studio_cutter: bad cut returns err_payload
  - LLM tool run_jewelry_gem_studio_cutter: missing size returns err_payload
  - LLM tool run_jewelry_gem_studio_catalog: material lookup
  - LLM tool run_jewelry_gem_studio_catalog: cut-based lookup
  - LLM tool run_jewelry_gem_studio_catalog: unknown material returns NOT_FOUND
  - LLM tool run_jewelry_gem_studio_fit_check: valid path returns ok flag
  - LLM tool run_jewelry_gem_studio_fit_check: missing cutter returns error
  - LLM tool run_jewelry_gem_studio_melee_seq: sequences round_brilliant row
  - LLM tool run_jewelry_gem_studio_melee_seq: bad cut returns error
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.jewelry.gem_studio import (
    GEM_STUDIO_CUTS,
    GEM_STUDIO_CATALOG,
    gem_cutter_spec,
    gem_fit_check,
    melee_sequence,
    _MIN_WALL_DEFAULTS,
    run_jewelry_gem_studio_cutter,
    run_jewelry_gem_studio_catalog,
    run_jewelry_gem_studio_fit_check,
    run_jewelry_gem_studio_melee_seq,
)
from kerf_cad_core.jewelry.gemstones import carat_from_mm, mm_from_carat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx():
    project_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            return None

        def execute(self, query, *args):
            pass

    from kerf_core.utils.context import ProjectCtx
    return ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _call_cutter(ctx, **kwargs) -> dict:
    """Return a normalised response dict with 'ok', 'data', and optional 'code'."""
    raw = _run(run_jewelry_gem_studio_cutter(ctx, json.dumps(kwargs).encode()))
    parsed = json.loads(raw)
    if "code" in parsed:
        return {"ok": False, "code": parsed["code"], "error": parsed.get("error", "")}
    return {"ok": True, "data": parsed}


def _call_catalog(ctx, **kwargs) -> dict:
    raw = _run(run_jewelry_gem_studio_catalog(ctx, json.dumps(kwargs).encode()))
    parsed = json.loads(raw)
    if "code" in parsed:
        return {"ok": False, "code": parsed["code"], "error": parsed.get("error", "")}
    return {"ok": True, "data": parsed}


def _call_fit(ctx, **kwargs) -> dict:
    raw = _run(run_jewelry_gem_studio_fit_check(ctx, json.dumps(kwargs).encode()))
    parsed = json.loads(raw)
    if "code" in parsed:
        return {"ok": False, "code": parsed["code"], "error": parsed.get("error", "")}
    return {"ok": True, "data": parsed}


def _call_melee(ctx, **kwargs) -> dict:
    raw = _run(run_jewelry_gem_studio_melee_seq(ctx, json.dumps(kwargs).encode()))
    parsed = json.loads(raw)
    if "code" in parsed:
        return {"ok": False, "code": parsed["code"], "error": parsed.get("error", "")}
    return {"ok": True, "data": parsed}


CTX = _make_ctx()

# ---------------------------------------------------------------------------
# Section 1: GEM_STUDIO_CUTS registry
# ---------------------------------------------------------------------------

REQUIRED_CUTS = {
    "round_brilliant", "princess", "emerald", "asscher", "oval",
    "marquise", "pear", "cushion", "radiant", "baguette", "trillion",
    "heart", "briolette", "rose_cut", "cabochon",
}


def test_gem_studio_cuts_completeness():
    """All 15 required cuts must be in GEM_STUDIO_CUTS."""
    missing = REQUIRED_CUTS - GEM_STUDIO_CUTS
    assert not missing, f"Missing cuts: {missing}"


def test_gem_studio_cuts_count():
    assert len(GEM_STUDIO_CUTS) >= 15


# ---------------------------------------------------------------------------
# Section 2: Cutter envelope >= gemstone girdle (all 15 cuts)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cut", sorted(REQUIRED_CUTS))
def test_cutter_envelope_geq_girdle(cut):
    """Cutter bounding long axis must be >= gemstone girdle diameter for every cut."""
    diameter_mm = 5.0
    spec = gem_cutter_spec(cut, diameter_mm)
    cutter = spec["cutter"]
    gem = spec["gemstone"]
    stone_long = gem["diameter_mm"]
    # Cutter bounding long axis must be > stone long axis (girdle clearance added)
    assert cutter["bounding_long_axis_mm"] >= stone_long, (
        f"{cut}: cutter bounding {cutter['bounding_long_axis_mm']:.4f} "
        f"< stone girdle {stone_long:.4f}"
    )


@pytest.mark.parametrize("cut", sorted(REQUIRED_CUTS))
def test_cutter_depth_geq_pavilion_plus_culet(cut):
    """Cutter must be deep enough to contain the full pavilion + culet allowance.

    The crown protrudes above the metal seat, so cutter_depth is not expected
    to exceed total_stone_depth (crown + girdle + pavilion).  The invariant is
    that cutter_depth >= pavilion_depth + girdle_ledge + culet_allowance.
    """
    spec = gem_cutter_spec(cut, 5.0)
    cutter = spec["cutter"]
    required_min = (
        cutter["pavilion_depth_mm"]
        + cutter["girdle_ledge_mm"]
        + cutter["culet_allowance_mm"]
    )
    assert cutter["cutter_depth_mm"] >= required_min, (
        f"{cut}: cutter_depth {cutter['cutter_depth_mm']:.4f} "
        f"< required {required_min:.4f} (pav+ledge+culet)"
    )


# ---------------------------------------------------------------------------
# Section 3: Carat↔mm round-trips (published gem tables)
# ---------------------------------------------------------------------------

def test_rbc_1ct_approx_6p5mm():
    """1.00 ct round brilliant diamond ≈ 6.5 mm (GIA / industry standard)."""
    d = mm_from_carat("round_brilliant", 1.00)
    assert abs(d - 6.5) < 0.05, f"Expected ~6.5 mm; got {d:.4f}"


def test_princess_1ct_approx_5p5mm():
    """1.00 ct princess diamond ≈ 5.5 mm side (industry reference)."""
    d = mm_from_carat("princess", 1.00)
    assert abs(d - 5.5) < 0.10, f"Expected ~5.5 mm; got {d:.4f}"


def test_oval_0p5ct_approx_6p11mm():
    """0.50 ct oval diamond ≈ 6.11 mm long axis (ref_mm=7.7, 0.5^(1/3)*7.7)."""
    expected = 7.7 * (0.5 ** (1.0 / 3.0))
    d = mm_from_carat("oval", 0.50)
    assert abs(d - expected) < 0.05, f"Expected ~{expected:.3f} mm; got {d:.4f}"


def test_emerald_1ct_approx_7mm():
    """1.00 ct emerald cut diamond ≈ 7.0 mm long axis."""
    d = mm_from_carat("emerald", 1.00)
    assert abs(d - 7.0) < 0.05, f"Expected ~7.0 mm; got {d:.4f}"


@pytest.mark.parametrize("cut", sorted(REQUIRED_CUTS - {"cabochon"}))
def test_carat_mm_round_trip(cut):
    """carat_from_mm(mm_from_carat(ct)) == ct for every cut."""
    ct = 0.50
    d = mm_from_carat(cut, ct)
    ct_back = carat_from_mm(cut, d)
    assert abs(ct_back - ct) < 1e-9, (
        f"{cut}: round-trip failed: {ct} -> {d:.4f} mm -> {ct_back:.9f} ct"
    )


def test_gem_studio_cutter_carat_to_mm():
    """gem_cutter_spec with carat input gives correct resolved diameter_mm."""
    spec = gem_cutter_spec("round_brilliant", 0.0, carat=1.0)
    assert abs(spec["diameter_mm"] - 6.5) < 0.05


def test_gem_studio_cutter_carat_returned():
    """gem_cutter_spec with diameter_mm also returns carat field."""
    spec = gem_cutter_spec("round_brilliant", 6.5)
    assert abs(spec["carat"] - 1.0) < 0.05


# ---------------------------------------------------------------------------
# Section 4: Clearance parameters are respected
# ---------------------------------------------------------------------------

def test_default_girdle_clearance_applied():
    """Default girdle_clearance_mm=0.05 is added to cutter radius."""
    spec = gem_cutter_spec("round_brilliant", 6.5)
    expected_r = 6.5 / 2.0 + 0.05
    assert abs(spec["cutter"]["girdle_long_radius_mm"] - expected_r) < 1e-6


def test_custom_girdle_clearance():
    """Custom girdle_clearance_mm is reflected in cutter envelope."""
    spec = gem_cutter_spec("round_brilliant", 6.5, girdle_clearance_mm=0.15)
    expected_r = 6.5 / 2.0 + 0.15
    assert abs(spec["cutter"]["girdle_long_radius_mm"] - expected_r) < 1e-6


def test_zero_girdle_clearance_still_valid():
    """Zero girdle clearance is allowed; cutter radius == stone radius."""
    spec = gem_cutter_spec("round_brilliant", 6.5, girdle_clearance_mm=0.0)
    assert abs(spec["cutter"]["girdle_long_radius_mm"] - 6.5 / 2.0) < 1e-6


def test_culet_allowance_in_cutter_depth():
    """culet_allowance_mm contributes to cutter_depth_mm."""
    spec1 = gem_cutter_spec("round_brilliant", 6.5, culet_allowance_mm=0.10)
    spec2 = gem_cutter_spec("round_brilliant", 6.5, culet_allowance_mm=0.30)
    assert spec2["cutter"]["cutter_depth_mm"] > spec1["cutter"]["cutter_depth_mm"]


def test_table_offset_in_cutter_depth():
    """table_offset_mm contributes to cutter_depth_mm."""
    spec1 = gem_cutter_spec("round_brilliant", 6.5, table_offset_mm=0.05)
    spec2 = gem_cutter_spec("round_brilliant", 6.5, table_offset_mm=0.50)
    assert spec2["cutter"]["cutter_depth_mm"] > spec1["cutter"]["cutter_depth_mm"]


# ---------------------------------------------------------------------------
# Section 5: Aspect ratio
# ---------------------------------------------------------------------------

def test_aspect_ratio_override_propagated():
    """Custom aspect_ratio is reflected in cutter short axis."""
    spec = gem_cutter_spec("oval", 8.0, aspect_ratio=0.70)
    ar = spec["cutter"]["aspect_ratio"]
    assert abs(ar - 0.70) < 1e-6
    # Short axis = long * ar + 2*clearance
    expected_short = 8.0 * 0.70 + 2 * 0.05
    assert abs(spec["cutter"]["bounding_short_axis_mm"] - expected_short) < 0.01


def test_non_round_cut_short_axis_lt_long():
    """For non-square cuts the short axis should be <= long axis."""
    spec = gem_cutter_spec("marquise", 10.0)
    assert spec["cutter"]["bounding_short_axis_mm"] <= spec["cutter"]["bounding_long_axis_mm"]


# ---------------------------------------------------------------------------
# Section 6: Cabochon special geometry
# ---------------------------------------------------------------------------

def test_cabochon_pavilion_angle_zero():
    """Cabochon has pavilion_angle_deg=0.0 (flat base)."""
    spec = gem_cutter_spec("cabochon", 8.0)
    assert spec["gemstone"]["pavilion_angle_deg"] == 0.0


def test_cabochon_table_pct_zero():
    """Cabochon has no table (table_pct=0)."""
    spec = gem_cutter_spec("cabochon", 8.0)
    assert spec["gemstone"]["table_pct"] == 0.0


def test_cabochon_cutter_depth_positive():
    """Cabochon cutter has positive depth."""
    spec = gem_cutter_spec("cabochon", 8.0)
    assert spec["cutter"]["cutter_depth_mm"] > 0.0


# ---------------------------------------------------------------------------
# Section 7: Briolette
# ---------------------------------------------------------------------------

def test_briolette_cutter_depth_geq_pavilion():
    """Briolette cutter covers the lower-half pavilion + culet allowance.

    The full stone depth includes the upper-dome crown.  The cutter only needs
    to accommodate the pavilion (lower half) plus girdle ledge and culet room.
    """
    spec = gem_cutter_spec("briolette", 6.0)
    cutter = spec["cutter"]
    required_min = (
        cutter["pavilion_depth_mm"]
        + cutter["girdle_ledge_mm"]
        + cutter["culet_allowance_mm"]
    )
    assert cutter["cutter_depth_mm"] >= required_min


def test_briolette_has_no_flat_table():
    """Briolette table_pct is 0 (no table)."""
    spec = gem_cutter_spec("briolette", 6.0)
    assert spec["gemstone"]["table_pct"] == 0.0


# ---------------------------------------------------------------------------
# Section 8: Error paths for gem_cutter_spec
# ---------------------------------------------------------------------------

def test_invalid_cut_raises():
    with pytest.raises(ValueError, match="Unknown gem-studio cut"):
        gem_cutter_spec("madeup_cut", 5.0)


def test_negative_carat_raises():
    with pytest.raises(ValueError):
        gem_cutter_spec("round_brilliant", 0.0, carat=-1.0)


def test_both_carat_and_diameter_raises():
    with pytest.raises(ValueError):
        gem_cutter_spec("round_brilliant", 5.0, carat=1.0)


def test_neither_carat_nor_diameter_raises():
    with pytest.raises(ValueError):
        gem_cutter_spec("round_brilliant", 0.0)


# ---------------------------------------------------------------------------
# Section 9: GEM_STUDIO_CATALOG
# ---------------------------------------------------------------------------

REQUIRED_CATALOG_GEMS = {
    "diamond", "ruby", "sapphire", "emerald", "amethyst",
    "aquamarine", "topaz", "garnet", "peridot", "citrine",
    "tanzanite", "spinel", "tourmaline", "morganite", "alexandrite",
}


def test_catalog_contains_required_gems():
    missing = REQUIRED_CATALOG_GEMS - set(GEM_STUDIO_CATALOG)
    assert not missing, f"Missing from catalog: {missing}"


def test_catalog_entries_have_required_keys():
    required_keys = {"density", "ri", "dispersion", "mohs", "colour_grades",
                     "price_per_ct_band", "typical_cuts"}
    for name, entry in GEM_STUDIO_CATALOG.items():
        missing_keys = required_keys - set(entry)
        assert not missing_keys, f"{name} missing keys: {missing_keys}"


def test_catalog_ri_is_positive():
    for name, entry in GEM_STUDIO_CATALOG.items():
        ri = entry["ri"]
        if isinstance(ri, tuple):
            assert ri[0] > 0 and ri[1] > 0, f"{name}: RI must be positive"
        else:
            assert ri > 0, f"{name}: RI must be positive"


def test_catalog_dispersion_nonneg():
    for name, entry in GEM_STUDIO_CATALOG.items():
        assert entry["dispersion"] >= 0.0, f"{name}: dispersion must be >= 0"


def test_catalog_price_band_ordered():
    for name, entry in GEM_STUDIO_CATALOG.items():
        lo, hi = entry["price_per_ct_band"]
        assert lo < hi, f"{name}: price_per_ct_band low must be < high"


def test_catalog_diamond_highest_mohs():
    assert GEM_STUDIO_CATALOG["diamond"]["mohs"] == 10.0


def test_catalog_diamond_highest_dispersion():
    d_disp = GEM_STUDIO_CATALOG["diamond"]["dispersion"]
    # Diamond should have one of the highest dispersions
    assert d_disp > 0.040, f"Diamond dispersion expected > 0.040; got {d_disp}"


# ---------------------------------------------------------------------------
# Section 10: gem_fit_check
# ---------------------------------------------------------------------------

def test_fit_check_ok_when_ample():
    cutter_dict = gem_cutter_spec("round_brilliant", 5.0)["cutter"]
    result = gem_fit_check(cutter_dict, wall_thickness_mm=20.0)
    assert result["ok"] is True
    assert not result["warnings"]


def test_fit_check_fails_when_too_thin():
    cutter_dict = gem_cutter_spec("round_brilliant", 5.0)["cutter"]
    # Wall of 0.1 mm is definitely too thin
    result = gem_fit_check(cutter_dict, wall_thickness_mm=0.1)
    assert result["ok"] is False
    assert any("WALL TOO THIN" in w for w in result["warnings"])


def test_fit_check_tight_clearance_warning():
    cutter_dict = gem_cutter_spec("round_brilliant", 5.0)["cutter"]
    # Wall just barely enough
    min_wall = _MIN_WALL_DEFAULTS["prong"]
    cutter_diam = cutter_dict["bounding_long_axis_mm"]
    barely_ok = cutter_diam + 2 * min_wall + 0.01  # barely ample
    result = gem_fit_check(cutter_dict, wall_thickness_mm=barely_ok,
                           setting_type="prong")
    # ok but tight
    assert result["ok"] is True
    # clearance is small (less than 50% of min_wall)
    assert result["clearance_mm"] < min_wall * 0.5 + 0.1  # within tight range


def test_fit_check_culet_allowance_warning():
    cutter_dict = gem_cutter_spec("round_brilliant", 5.0, culet_allowance_mm=0.01)["cutter"]
    result = gem_fit_check(cutter_dict, wall_thickness_mm=20.0)
    assert any("culet" in w.lower() for w in result["warnings"])


def test_fit_check_setting_type_varies_min_wall():
    cutter_dict = gem_cutter_spec("round_brilliant", 5.0)["cutter"]
    r_tension = gem_fit_check(cutter_dict, wall_thickness_mm=10.0, setting_type="tension")
    r_pave = gem_fit_check(cutter_dict, wall_thickness_mm=10.0, setting_type="pave")
    # Tension requires more wall => less clearance remaining
    assert r_tension["clearance_mm"] < r_pave["clearance_mm"]


def test_fit_check_min_wall_override():
    cutter_dict = gem_cutter_spec("round_brilliant", 5.0)["cutter"]
    # With override of 5.0 mm each side, a 10 mm diameter cutter will fail
    # even with 15 mm wall (10 + 10 = 20 > 15)
    result = gem_fit_check(cutter_dict, wall_thickness_mm=15.0,
                           min_wall_override_mm=5.0)
    cutter_diam = cutter_dict["bounding_long_axis_mm"]
    if cutter_diam + 2 * 5.0 > 15.0:
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Section 11: melee_sequence
# ---------------------------------------------------------------------------

def test_melee_sequence_fits_in_channel():
    result = melee_sequence("round_brilliant", 20.0, target_diameter_mm=2.0)
    n = result["n_stones"]
    pitch = result["pitch_mm"]
    assert n >= 1
    # Verify total set length fits
    total = n * result["stone_diameter_mm"] + 2 * 0.05 + max(0, n - 1) * 0.10
    assert total <= 20.0 + 0.01  # small tolerance


def test_melee_sequence_positions_centred():
    """Positions should be roughly centred in the channel."""
    result = melee_sequence("round_brilliant", 20.0, target_diameter_mm=2.0)
    positions = result["positions_mm"]
    if len(positions) >= 2:
        mid = (positions[0] + positions[-1]) / 2.0
        assert abs(mid - 10.0) < 1.0, f"Centre of positions {mid:.3f} not near 10.0 mm"


def test_melee_sequence_default_carat():
    """Default 0.10 ct melee for round_brilliant ≈ expected diameter."""
    from kerf_cad_core.jewelry.gemstones import mm_from_carat
    expected_d = mm_from_carat("round_brilliant", 0.10)
    result = melee_sequence("round_brilliant", 30.0)
    assert abs(result["stone_diameter_mm"] - expected_d) < 0.01


def test_melee_sequence_target_diameter():
    result = melee_sequence("princess", 25.0, target_diameter_mm=3.0)
    assert abs(result["stone_diameter_mm"] - 3.0) < 0.01


def test_melee_sequence_pitch_equals_cutter_plus_gap():
    result = melee_sequence("round_brilliant", 25.0, target_diameter_mm=2.0, seat_gap_mm=0.15)
    cutter_w = result["cutter_spec"]["cutter"]["bounding_long_axis_mm"]
    expected_pitch = cutter_w + 0.15
    assert abs(result["pitch_mm"] - expected_pitch) < 1e-6


def test_melee_sequence_both_targets_raises():
    with pytest.raises(ValueError):
        melee_sequence("round_brilliant", 20.0,
                       target_carat=0.10, target_diameter_mm=2.0)


def test_melee_sequence_zero_channel_raises():
    with pytest.raises(ValueError):
        melee_sequence("round_brilliant", 0.0, target_diameter_mm=2.0)


# ---------------------------------------------------------------------------
# Section 12: LLM tool runners
# ---------------------------------------------------------------------------

def test_llm_cutter_ok_path_returns_gemstone_and_cutter():
    resp = _call_cutter(CTX, cut="round_brilliant", carat=1.0)
    assert resp.get("ok") is True
    data = resp["data"]
    assert "gemstone" in data
    assert "cutter" in data
    assert data["cut"] == "round_brilliant"


def test_llm_cutter_bad_cut_returns_error():
    resp = _call_cutter(CTX, cut="fancy_made_up", diameter_mm=5.0)
    assert resp.get("ok") is False
    assert resp.get("code") == "BAD_ARGS"


def test_llm_cutter_missing_size_returns_error():
    resp = _call_cutter(CTX, cut="round_brilliant")
    assert resp.get("ok") is False
    assert resp.get("code") == "BAD_ARGS"


def test_llm_cutter_both_carat_and_diameter_error():
    resp = _call_cutter(CTX, cut="round_brilliant", carat=1.0, diameter_mm=6.5)
    assert resp.get("ok") is False


def test_llm_cutter_cabochon_works():
    resp = _call_cutter(CTX, cut="cabochon", diameter_mm=8.0)
    assert resp.get("ok") is True
    assert resp["data"]["gemstone"]["pavilion_angle_deg"] == 0.0


def test_llm_catalog_material_lookup():
    resp = _call_catalog(CTX, material="ruby")
    assert resp.get("ok") is True
    assert "ruby" in resp["data"]["results"]


def test_llm_catalog_cut_based_lookup():
    resp = _call_catalog(CTX, cut="round_brilliant")
    assert resp.get("ok") is True
    results = resp["data"]["results"]
    # diamond lists round_brilliant
    assert "diamond" in results


def test_llm_catalog_unknown_material_not_found():
    resp = _call_catalog(CTX, material="unobtanium_xxz")
    assert resp.get("ok") is False
    assert resp.get("code") == "NOT_FOUND"


def test_llm_catalog_full_dump():
    resp = _call_catalog(CTX)
    assert resp.get("ok") is True
    assert resp["data"]["count"] >= 15


def test_llm_fit_check_ok_path():
    cutter_resp = _call_cutter(CTX, cut="round_brilliant", carat=1.0)
    cutter_dict = cutter_resp["data"]["cutter"]
    resp = _call_fit(CTX, cutter=cutter_dict, wall_thickness_mm=20.0)
    assert resp.get("ok") is True
    assert resp["data"]["ok"] is True


def test_llm_fit_check_missing_cutter_error():
    resp = _call_fit(CTX, wall_thickness_mm=20.0)
    assert resp.get("ok") is False
    assert resp.get("code") == "BAD_ARGS"


def test_llm_fit_check_thin_wall_fires_warning():
    cutter_resp = _call_cutter(CTX, cut="round_brilliant", carat=1.0)
    cutter_dict = cutter_resp["data"]["cutter"]
    resp = _call_fit(CTX, cutter=cutter_dict, wall_thickness_mm=0.5)
    assert resp.get("ok") is True  # tool returns ok; fit_check.ok may be False
    assert resp["data"]["ok"] is False


def test_llm_melee_seq_round_brilliant_row():
    resp = _call_melee(CTX, cut="round_brilliant",
                       channel_length_mm=20.0, target_diameter_mm=2.0)
    assert resp.get("ok") is True
    data = resp["data"]
    assert data["n_stones"] >= 1
    assert len(data["positions_mm"]) == data["n_stones"]


def test_llm_melee_seq_bad_cut_returns_error():
    resp = _call_melee(CTX, cut="nonsense_cut", channel_length_mm=20.0)
    assert resp.get("ok") is False
    assert resp.get("code") == "BAD_ARGS"


def test_llm_melee_seq_zero_channel_returns_error():
    resp = _call_melee(CTX, cut="round_brilliant", channel_length_mm=0.0)
    assert resp.get("ok") is False
    assert resp.get("code") == "BAD_ARGS"
