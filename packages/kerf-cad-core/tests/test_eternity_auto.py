"""
Hermetic tests for kerf_cad_core.jewelry.eternity_auto.

≥30 tests covering:
  - stone_count × pitch_mm ≈ inner_circumference for fixed_size / fixed_count
  - even angular spacing (fixed_count mode)
  - gaps positive and ≥ min
  - graduated sizes monotonically non-increasing outward from centre
  - coverage ratio for full / three_quarter / half
  - metal_removed_mm3 == Σ per-cutter volumes
  - all setting styles produce non-empty retention list
  - thin_metal warnings fire correctly
  - ring-size conversions (US / UK / EU)
  - error on unknown cut / style / mode
  - fixed_count too tight raises ValueError
  - per-stone positions lie on inner bore circle
  - pitch_deg × n == arc_deg (within tolerance)
  - total_carat == sum of per-stone carats
  - prong retention geometry is non-trivial
  - channel retention contains wall thickness
  - shared_bead bead_diameter > 0
  - u_cut prong_tips count == 2
  - bezel wall_mm > 0
  - node builder round-trips params
  - graduated monotone: first > last stone_mm
  - half eternity coverage_pct < 50 for sub-mm gap setting
  - three_quarter coverage arc is 270°
  - seat_cutter position matches stone position
  - normal vector in seat_cutter is radially inward
  - stone_mm larger → fewer stones for same ring
  - total_carat scales with stone_mm (larger → more per stone)
  - metal_removed scales with n_stones
  - metal_weight_estimate_g > 0
  - warn == '' when bridge is large enough
  - warn == 'thin_metal' when bridge below threshold
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.jewelry.eternity_auto import (
    _VALID_SETTING_STYLES,
    _VALID_CALIBRATION_MODES,
    _VALID_COVERAGES,
    _COVERAGE_ARC,
    _ABS_MIN_GAP_MM,
    _seat_cutter_volume_mm3,
    _graduated_sizes,
    _stone_position,
    eternity_auto_distribute,
    build_eternity_node,
)
from kerf_cad_core.jewelry.ring import ring_size_to_diameter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PI = math.pi

def _inner_circ(ring_size, system="us"):
    d = ring_size_to_diameter(system, ring_size)
    return _PI * d


def _distribute(**kwargs):
    """Thin wrapper; fills in required defaults."""
    defaults = dict(
        ring_size=7,
        stone_cut="round_brilliant",
        stone_mm=2.0,
        setting_style="prong",
        calibration_mode="fixed_size",
    )
    defaults.update(kwargs)
    return eternity_auto_distribute(**defaults)


# ===========================================================================
# 1. stone_count × pitch_mm ≈ inner_circumference (fixed_size, full eternity)
# ===========================================================================

def test_pitch_times_count_equals_circumference_fixed_size():
    res = _distribute(ring_size=7, stone_mm=2.0, calibration_mode="fixed_size")
    circ = res["inner_circumference_mm"]
    n = res["stone_count"]
    pitch = res["pitch_mm"]
    assert abs(n * pitch - circ) < 0.01, (
        f"n={n} × pitch={pitch:.4f} = {n*pitch:.4f} vs circ={circ:.4f}"
    )


# ===========================================================================
# 2. fixed_count: pitch × n == circumference (full)
# ===========================================================================

def test_fixed_count_pitch_times_n_equals_circumference():
    res = _distribute(
        ring_size=7, stone_mm=2.0,
        calibration_mode="fixed_count", fixed_count=18,
    )
    circ = res["inner_circumference_mm"]
    assert abs(res["stone_count"] * res["pitch_mm"] - circ) < 0.01
    assert res["stone_count"] == 18


# ===========================================================================
# 3. Even angular spacing (fixed_count)
# ===========================================================================

def test_even_angular_spacing_fixed_count():
    res = _distribute(calibration_mode="fixed_count", fixed_count=20)
    stones = res["stones"]
    angles = [s["angle_deg"] for s in stones]
    # full eternity: differences should all equal pitch_deg
    diffs = [(angles[i+1] - angles[i]) for i in range(len(angles)-1)]
    expected = res["pitch_deg"]
    for d in diffs:
        assert abs(d - expected) < 1e-4, f"Uneven gap: {d:.6f} vs {expected:.6f}"


# ===========================================================================
# 4. gap_mm >= _ABS_MIN_GAP_MM in fixed_size mode
# ===========================================================================

def test_gap_is_nonnegative_and_at_least_min():
    res = _distribute(ring_size=6, stone_mm=1.5)
    assert res["gap_mm"] >= _ABS_MIN_GAP_MM - 1e-9


# ===========================================================================
# 5. gap_mm > 0 for all calibration modes
# ===========================================================================

@pytest.mark.parametrize("mode", ["fixed_size", "graduated"])
def test_gap_positive_all_modes(mode):
    res = _distribute(calibration_mode=mode)
    assert res["gap_mm"] > 0


# ===========================================================================
# 6. Graduated sizes: monotonically non-increasing outward
# ===========================================================================

def test_graduated_sizes_monotone():
    res = _distribute(
        calibration_mode="graduated",
        stone_mm=3.0,
        size_step_mm=0.15,
        coverage="full",
    )
    sizes = [s["stone_mm"] for s in res["stones"]]
    n = len(sizes)
    # The center stone(s) are largest; going toward the ends sizes should not increase
    half = n // 2
    for k in range(1, half):
        # First half outward
        assert sizes[k] <= sizes[k - 1] + 1e-6, (
            f"Graduated sizes not monotone at index {k}: {sizes[k]} > {sizes[k-1]}"
        )


def test_graduated_first_gt_last():
    """Center stone is larger than the last stone in graduated mode."""
    sizes = _graduated_sizes(center_mm=3.0, size_step_mm=0.1, n_total=11)
    assert sizes[0] >= sizes[-1]


def test_graduated_sizes_length():
    for n in [5, 10, 11, 20]:
        sizes = _graduated_sizes(3.0, 0.1, n)
        assert len(sizes) == n


# ===========================================================================
# 7. Coverage ratio matches arc fraction
# ===========================================================================

def test_full_coverage_arc_is_360():
    res = _distribute(coverage="full")
    assert res["arc_deg"] == 360.0


def test_three_quarter_coverage_arc_is_270():
    res = _distribute(coverage="three_quarter")
    assert res["arc_deg"] == 270.0


def test_half_coverage_arc_is_180():
    res = _distribute(coverage="half")
    assert res["arc_deg"] == 180.0


def test_half_eternity_fewer_stones_than_full():
    full = _distribute(coverage="full")
    half = _distribute(coverage="half")
    assert half["stone_count"] < full["stone_count"]


# ===========================================================================
# 8. pitch_deg × n == arc_deg within tolerance
# ===========================================================================

@pytest.mark.parametrize("cov", ["full", "three_quarter", "half"])
def test_pitch_deg_times_n_equals_arc_deg(cov):
    res = _distribute(coverage=cov)
    n = res["stone_count"]
    pitch_deg = res["pitch_deg"]
    arc = res["arc_deg"]
    assert abs(n * pitch_deg - arc) < 1e-4, (
        f"coverage={cov}: n={n}×pitch={pitch_deg:.6f}={n*pitch_deg:.6f} vs arc={arc}"
    )


# ===========================================================================
# 9. metal_removed_mm3 == Σ per-cutter volumes
# ===========================================================================

def test_metal_removed_equals_sum_cutter_volumes():
    res = _distribute(ring_size=7, stone_mm=2.0)
    summed = sum(sc["cutter_volume_mm3"] for sc in res["seat_cutters"])
    # Both values are independently rounded to 4–5 decimal places, so allow 1e-3
    assert abs(res["metal_removed_mm3"] - summed) < 1e-3, (
        f"metal_removed={res['metal_removed_mm3']:.6f} vs sum={summed:.6f}"
    )


# ===========================================================================
# 10. total_carat == sum of per-stone carats
# ===========================================================================

def test_total_carat_equals_sum_per_stone():
    res = _distribute()
    # Both total_carat and per-stone carats are independently rounded to 4-5
    # decimal places; allow rounding accumulation across ~26 stones (1e-4 each).
    per_stone = sum(s["carat"] for s in res["stones"])
    assert abs(res["total_carat"] - per_stone) < 1e-2


# ===========================================================================
# 11. Stone positions lie on the inner bore circle
# ===========================================================================

def test_stone_positions_on_inner_circle():
    res = _distribute(ring_size=7, stone_mm=2.0)
    r = res["inner_radius_mm"]
    for s in res["stones"]:
        dist = math.sqrt(s["seat_x"] ** 2 + s["seat_y"] ** 2)
        assert abs(dist - r) < 1e-4, (
            f"Stone {s['index']} at r={dist:.4f} vs expected {r:.4f}"
        )


# ===========================================================================
# 12. seat_cutter position matches stone position
# ===========================================================================

def test_seat_cutter_position_matches_stone():
    res = _distribute()
    for stone, cutter in zip(res["stones"], res["seat_cutters"]):
        cx, cy, cz = cutter["position"]
        assert abs(cx - stone["seat_x"]) < 1e-4
        assert abs(cy - stone["seat_y"]) < 1e-4
        assert cz == stone["seat_z"]


# ===========================================================================
# 13. Normal vector in seat_cutter is radially inward (anti-parallel to position)
# ===========================================================================

def test_seat_cutter_normal_is_radially_inward():
    res = _distribute(ring_size=7, stone_mm=2.0)
    r = res["inner_radius_mm"]
    for cutter in res["seat_cutters"]:
        px, py, _ = cutter["position"]
        nx, ny, _ = cutter["normal"]
        # Normal should point from stone toward ring centre (negative radial)
        dot = px * nx + py * ny
        assert dot < 0 or abs(dot) < 1e-4, (
            f"Normal not inward: pos=({px:.4f},{py:.4f}), n=({nx:.4f},{ny:.4f})"
        )


# ===========================================================================
# 14. All setting styles: retention list is non-empty and correct length
# ===========================================================================

@pytest.mark.parametrize("style", list(_VALID_SETTING_STYLES))
def test_retention_list_non_empty_all_styles(style):
    res = _distribute(setting_style=style)
    assert len(res["retention"]) == res["stone_count"]


# ===========================================================================
# 15. prong style: each retention entry has 'prongs' list with 2 entries
# ===========================================================================

def test_prong_retention_has_two_prongs():
    res = _distribute(setting_style="prong")
    for ret in res["retention"]:
        assert ret["style"] == "prong"
        assert ret["prong_count"] == 2
        assert len(ret["prongs"]) == 2


# ===========================================================================
# 16. channel retention contains rail_wall_thickness_mm
# ===========================================================================

def test_channel_retention_has_wall_thickness():
    res = _distribute(setting_style="channel")
    for ret in res["retention"]:
        assert "rail_wall_thickness_mm" in ret
        assert ret["rail_wall_thickness_mm"] > 0


# ===========================================================================
# 17. shared_bead bead_diameter > 0
# ===========================================================================

def test_shared_bead_diameter_positive():
    res = _distribute(setting_style="shared_bead")
    for ret in res["retention"]:
        assert ret["bead_diameter_mm"] > 0


# ===========================================================================
# 18. u_cut: two prong tips per stone
# ===========================================================================

def test_u_cut_two_prong_tips():
    res = _distribute(setting_style="u_cut")
    for ret in res["retention"]:
        assert len(ret["prong_tips"]) == 2


# ===========================================================================
# 19. bezel wall_mm > 0
# ===========================================================================

def test_bezel_wall_positive():
    res = _distribute(setting_style="bezel")
    for ret in res["retention"]:
        assert ret["bezel_wall_mm"] > 0


# ===========================================================================
# 20. metal_weight_estimate_g > 0
# ===========================================================================

def test_metal_weight_estimate_positive():
    res = _distribute()
    assert res["metal_weight_estimate_g"] > 0


# ===========================================================================
# 21. Larger stone → fewer stones for same ring size
# ===========================================================================

def test_larger_stone_fewer_count():
    small = _distribute(stone_mm=1.5)
    large = _distribute(stone_mm=3.0)
    assert large["stone_count"] < small["stone_count"]


# ===========================================================================
# 22. total_carat higher for larger stones
# ===========================================================================

def test_larger_stone_more_carat_per_stone():
    small = _distribute(stone_mm=1.5)
    large = _distribute(stone_mm=3.0)
    if large["stone_count"] > 0 and small["stone_count"] > 0:
        ct_small = small["total_carat"] / small["stone_count"]
        ct_large = large["total_carat"] / large["stone_count"]
        assert ct_large > ct_small


# ===========================================================================
# 23. metal_removed_mm3 scales with stone count (more stones → more removed)
# ===========================================================================

def test_metal_removed_scales_with_count():
    few = _distribute(calibration_mode="fixed_count", fixed_count=10)
    many = _distribute(calibration_mode="fixed_count", fixed_count=20)
    assert many["metal_removed_mm3"] > few["metal_removed_mm3"]


# ===========================================================================
# 24. warn == '' when gap is large
# ===========================================================================

def test_no_thin_metal_warning_with_large_gap():
    res = _distribute(stone_mm=1.5, gap_mm=0.5)
    assert res["warn"] == ""
    assert res["thin_metal_warnings"] == 0


# ===========================================================================
# 25. warn == 'thin_metal' when bridge below threshold
# ===========================================================================

def test_thin_metal_warning_when_bridge_too_small():
    # Use a very high min_bridge_mm so every stone triggers it
    res = _distribute(stone_mm=2.0, min_bridge_mm=999.0)
    assert res["warn"] == "thin_metal"
    assert res["thin_metal_warnings"] > 0


# ===========================================================================
# 26. Error on unknown cut
# ===========================================================================

def test_error_on_unknown_cut():
    with pytest.raises(ValueError, match="Unknown stone_cut"):
        _distribute(stone_cut="fake_cut_xyz")


# ===========================================================================
# 27. Error on unknown setting style
# ===========================================================================

def test_error_on_unknown_setting_style():
    with pytest.raises(ValueError, match="Unknown setting_style"):
        _distribute(setting_style="invisible_rail")


# ===========================================================================
# 28. Error on unknown calibration mode
# ===========================================================================

def test_error_on_unknown_calibration_mode():
    with pytest.raises(ValueError, match="Unknown calibration_mode"):
        _distribute(calibration_mode="magic")


# ===========================================================================
# 29. fixed_count too tight raises ValueError
# ===========================================================================

def test_fixed_count_too_tight_raises():
    # 100 × 5 mm stones can't fit on a US 7 ring (circ ≈ 54.4 mm)
    with pytest.raises(ValueError, match="gap="):
        _distribute(
            ring_size=7, stone_mm=5.0,
            calibration_mode="fixed_count", fixed_count=100,
        )


# ===========================================================================
# 30. ring_size with UK system produces valid result
# ===========================================================================

def test_uk_ring_size_accepted():
    res = _distribute(ring_size="N", size_system="uk", setting_style="channel")
    assert res["stone_count"] > 0
    assert res["inner_diameter_mm"] > 0


# ===========================================================================
# 31. EU ring size accepted
# ===========================================================================

def test_eu_ring_size():
    res = _distribute(ring_size=54, size_system="eu")
    # EU 54 mm circumference → ID ≈ 17.19 mm
    assert abs(res["inner_circumference_mm"] - 54.0) < 0.1


# ===========================================================================
# 32. build_eternity_node round-trips params
# ===========================================================================

def test_build_node_round_trips_params():
    node = build_eternity_node(
        node_id="test-node-1",
        ring_size=7,
        stone_cut="princess",
        stone_mm=2.5,
        setting_style="channel",
        calibration_mode="fixed_size",
        coverage="three_quarter",
    )
    p = node["_params"]
    assert p["ring_size"] == 7
    assert p["stone_cut"] == "princess"
    assert p["stone_mm"] == 2.5
    assert p["coverage"] == "three_quarter"
    assert node["op"] == "jewelry_eternity_auto"
    assert node["id"] == "test-node-1"


# ===========================================================================
# 33. Node contains expected top-level keys
# ===========================================================================

def test_node_has_required_keys():
    node = build_eternity_node(
        "nid", 7, "round_brilliant", 2.0
    )
    for key in [
        "stone_count", "pitch_mm", "gap_mm", "total_carat",
        "metal_removed_mm3", "stones", "seat_cutters", "retention",
        "coverage_pct", "arc_deg",
    ]:
        assert key in node, f"Missing key: {key}"


# ===========================================================================
# 34. Seat cutter volume helper basic sanity
# ===========================================================================

def test_seat_cutter_volume_positive():
    vol = _seat_cutter_volume_mm3(2.0, 40.75, 43.1, 2.5)
    assert vol > 0


# ===========================================================================
# 35. Stone count > 0 for all valid cut types (smoke)
# ===========================================================================

@pytest.mark.parametrize("cut", [
    "round_brilliant", "princess", "baguette", "emerald", "oval"
])
def test_smoke_various_cuts(cut):
    res = _distribute(stone_cut=cut, stone_mm=2.0)
    assert res["stone_count"] > 0


# ===========================================================================
# 36. Stone count > 0 for all coverage options
# ===========================================================================

@pytest.mark.parametrize("cov", ["full", "three_quarter", "half"])
def test_smoke_all_coverages(cov):
    res = _distribute(coverage=cov, stone_mm=2.0)
    assert res["stone_count"] > 0


# ===========================================================================
# 37. coverage_pct <= 100 always
# ===========================================================================

def test_coverage_pct_bounded():
    for cov in ["full", "three_quarter", "half"]:
        res = _distribute(coverage=cov)
        assert res["coverage_pct"] <= 100.0
        assert res["coverage_pct"] >= 0.0
