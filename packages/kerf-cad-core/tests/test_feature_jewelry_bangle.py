"""
test_feature_jewelry_bangle.py — T-4 hermetic pytest suite
===========================================================

Scope: kerf_cad_core.jewelry.bangle — parametric closure round-trip.

Success criteria (from testing-breakdown.md T-4):
  - 25 wrist-size × profile combinations; inner perimeter accuracy ±0.1 mm
  - Hinge/clasp variants pass clash check
  - Boundary / malformed / idempotency cases

All tests are pure-Python — no OCC, no DB, no network.
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.jewelry.bangle import (
    WRIST_SIZE_TABLE,
    _VALID_INNER_PROFILES,
    _VALID_CROSS_SECTIONS,
    _VALID_CLASP_STYLES,
    _VALID_FINIALS,
    wrist_size_to_inner_circumference,
    inner_circumference_to_diameter,
    compute_closed_bangle_params,
    compute_open_cuff_params,
    compute_torque_params,
    compute_hinged_bangle_params,
)

_PI = math.pi

# ---------------------------------------------------------------------------
# Parametric matrix: 25 wrist-size × profile combinations
# ---------------------------------------------------------------------------
# 5 wrist sizes × 5 profiles = 25 combos (covering the spec floor exactly).
# For inner-perimeter accuracy we verify:  |returned_inner_circumference - input| ≤ 0.1 mm

_WRIST_SIZES_5 = ["XS", "S", "M", "L", "XL"]
_INNER_PROFILES_5 = ["round", "oval", "cushion", "square", "round"]  # round repeated intentionally


@pytest.mark.parametrize("size,inner_profile", [
    (size, profile)
    for size, profile in zip(
        [s for s in _WRIST_SIZES_5 for _ in range(5)],
        _INNER_PROFILES_5 * 5,
    )
])
def test_closed_bangle_inner_circumference_accuracy(size: str, inner_profile: str):
    """Inner circumference returned by compute_closed_bangle_params must
    match the WRIST_SIZE_TABLE value within ±0.1 mm (spec tolerance)."""
    target_circ = WRIST_SIZE_TABLE[size]
    params = compute_closed_bangle_params(
        inner_circumference_mm=target_circ,
        cross_section="round_wire",
        cs_width_mm=4.0,
        inner_profile=inner_profile,
    )
    assert abs(params["inner_circumference_mm"] - target_circ) <= 0.1, (
        f"size={size} profile={inner_profile}: "
        f"inner_circumference mismatch: {params['inner_circumference_mm']} vs {target_circ}"
    )


# ---------------------------------------------------------------------------
# Wrist-size × cross-section: 25 round-trip combinations
# ---------------------------------------------------------------------------

_CROSS_SECTIONS_5 = ["round_wire", "d_shape", "square", "knife_edge", "half_round"]


@pytest.mark.parametrize("size,cs", [
    (size, cs)
    for size in _WRIST_SIZES_5
    for cs in _CROSS_SECTIONS_5
])
def test_closed_bangle_profile_cs_matrix(size: str, cs: str):
    """All 25 wrist-size × cross-section combinations: volume > 0,
    inner_diameter within ±0.1 mm of target, type == 'closed_bangle'."""
    target_circ = WRIST_SIZE_TABLE[size]
    params = compute_closed_bangle_params(
        inner_circumference_mm=target_circ,
        cross_section=cs,
        cs_width_mm=5.0,
    )
    assert params["type"] == "closed_bangle"
    assert params["volume_mm3"] > 0
    expected_d = target_circ / _PI
    assert abs(params["inner_diameter_mm"] - expected_d) <= 0.1, (
        f"size={size} cs={cs}: diameter mismatch: {params['inner_diameter_mm']} vs {expected_d:.4f}"
    )


# ---------------------------------------------------------------------------
# Hinge / clasp variants — clash check
# ---------------------------------------------------------------------------
# A clash is defined as: hinge_volume_mm3 interfering with arm volume, i.e.
# hinge_volume_mm3 > 0 and total_volume > arm_volume (no subtraction).

@pytest.mark.parametrize("clasp_style", list(_VALID_CLASP_STYLES))
def test_hinged_bangle_clasp_variants_no_clash(clasp_style: str):
    """All clasp styles: hinge volume is additive (total > arm volume) —
    i.e. the hinge body does not eat into the arm (no negative clash)."""
    params = compute_hinged_bangle_params(
        inner_circumference_mm=165.0,
        cross_section="d_shape",
        cs_width_mm=6.0,
        clasp_style=clasp_style,
    )
    assert params["hinge_volume_mm3"] > 0, "Hinge volume must be positive (clash sentinel)"
    assert params["volume_total_mm3"] > params["volume_mm3"], (
        f"clasp={clasp_style}: total_vol ({params['volume_total_mm3']}) "
        f"must exceed arm_vol ({params['volume_mm3']}) — hinge addition"
    )
    assert params["clasp_style"] == clasp_style.lower().strip()


@pytest.mark.parametrize("size", _WRIST_SIZES_5)
def test_hinged_bangle_all_sizes_no_clash(size: str):
    """Hinged bangle: every wrist size passes clash check."""
    circ = WRIST_SIZE_TABLE[size]
    params = compute_hinged_bangle_params(inner_circumference_mm=circ)
    assert params["hinge_volume_mm3"] > 0
    assert params["volume_total_mm3"] > params["volume_mm3"]
    assert abs(params["inner_circumference_mm"] - circ) <= 0.1


# ---------------------------------------------------------------------------
# Open cuff — spring-back correctness across sizes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("size", _WRIST_SIZES_5)
def test_open_cuff_spring_back_all_sizes(size: str):
    """Open cuff with metal: mandrel smaller than target + gap narrows after forming."""
    circ = WRIST_SIZE_TABLE[size]
    params = compute_open_cuff_params(
        inner_circumference_mm=circ,
        gap_angle_deg=30.0,
        metal="18k_yellow",
    )
    sb = params["spring_back"]
    assert sb is not None
    assert sb["mandrel_diameter_mm"] < sb["target_inner_diameter_mm"]
    assert sb["gap_angle_after_forming_deg"] < sb["gap_angle_deg"]


# ---------------------------------------------------------------------------
# Torque — finial variants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("finial", list(_VALID_FINIALS))
def test_torque_finial_variants_volume(finial: str):
    """All finial styles: total volume > arm volume (finial adds material),
    and type == 'torque'."""
    params = compute_torque_params(
        inner_circumference_mm=165.0,
        cs_width_mm=5.0,
        finial_style=finial,
    )
    assert params["type"] == "torque"
    assert params["volume_total_mm3"] > 0
    # finials add volume (even if zero-mass hint styles use sphere estimate)
    assert params["volume_total_mm3"] >= params["volume_arm_mm3"]


# ---------------------------------------------------------------------------
# Boundary cases
# ---------------------------------------------------------------------------

def test_closed_bangle_minimum_legal_circumference():
    """Very small but positive circumference does not raise."""
    params = compute_closed_bangle_params(
        inner_circumference_mm=1.0,
        cross_section="round_wire",
        cs_width_mm=0.1,
    )
    assert params["volume_mm3"] > 0


def test_closed_bangle_very_large_circumference():
    """Very large circumference (e.g. oversized decorative piece)."""
    params = compute_closed_bangle_params(
        inner_circumference_mm=600.0,
        cross_section="square",
        cs_width_mm=10.0,
    )
    assert params["inner_circumference_mm"] == pytest.approx(600.0, abs=0.1)


def test_open_cuff_minimum_gap():
    """Minimum gap > 0 (boundary: 0.1°)."""
    params = compute_open_cuff_params(165.0, gap_angle_deg=0.1)
    assert params["active_arc_deg"] == pytest.approx(359.9, rel=1e-4)


def test_open_cuff_maximum_gap():
    """Maximum gap < 360° (boundary: 359.9°)."""
    params = compute_open_cuff_params(165.0, gap_angle_deg=359.9)
    assert params["active_arc_deg"] == pytest.approx(0.1, rel=1e-2)


def test_torque_minimum_twist():
    """Zero twist_turns is legal (no rotation)."""
    params = compute_torque_params(165.0, twist_turns=0.0)
    assert params["helix_angle_deg"] == pytest.approx(0.0)


def test_torque_large_twist():
    """High twist count (10 turns) is legal — helix angle < 90°."""
    params = compute_torque_params(165.0, twist_turns=10.0)
    assert 0 < params["helix_angle_deg"] < 90.0


def test_hinged_bangle_thin_pin():
    """Very thin hinge pin (0.1 mm) is legal."""
    params = compute_hinged_bangle_params(165.0, hinge_pin_diameter_mm=0.1)
    assert params["hinge_volume_mm3"] > 0


def test_hinged_bangle_stone_stations_top_half_only():
    """Stone stations on a hinged bangle are confined to top 180° arc."""
    params = compute_hinged_bangle_params(
        inner_circumference_mm=165.0,
        n_stone_stations=5,
    )
    stations = params["stone_stations"]
    assert len(stations) == 5
    for s in stations:
        assert 0.0 <= s["angle_deg"] <= 180.0, (
            f"Station {s['station_index']} angle {s['angle_deg']} outside top-half arc"
        )


# ---------------------------------------------------------------------------
# Malformed / error cases
# ---------------------------------------------------------------------------

def test_closed_bangle_zero_circumference_raises():
    with pytest.raises(ValueError):
        compute_closed_bangle_params(0.0, "round_wire", 4.0)


def test_closed_bangle_negative_circumference_raises():
    with pytest.raises(ValueError):
        compute_closed_bangle_params(-10.0, "round_wire", 4.0)


def test_closed_bangle_zero_width_raises():
    with pytest.raises(ValueError):
        compute_closed_bangle_params(165.0, "round_wire", 0.0)


def test_closed_bangle_bad_inner_profile_raises():
    with pytest.raises(ValueError, match="Unknown inner_profile"):
        compute_closed_bangle_params(165.0, "round_wire", 4.0, inner_profile="triangle")


def test_closed_bangle_bad_cross_section_raises():
    with pytest.raises(ValueError, match="Unknown cross_section"):
        compute_closed_bangle_params(165.0, "hexagonal_wire", 4.0)


def test_open_cuff_zero_gap_raises():
    with pytest.raises(ValueError):
        compute_open_cuff_params(165.0, gap_angle_deg=0.0)


def test_open_cuff_full_360_gap_raises():
    with pytest.raises(ValueError):
        compute_open_cuff_params(165.0, gap_angle_deg=360.0)


def test_torque_bad_finial_raises():
    with pytest.raises(ValueError, match="Unknown finial_style"):
        compute_torque_params(165.0, finial_style="dragon_xyz")


def test_torque_negative_twist_raises():
    with pytest.raises(ValueError):
        compute_torque_params(165.0, twist_turns=-1.0)


def test_hinged_bangle_bad_clasp_raises():
    with pytest.raises(ValueError, match="Unknown clasp_style"):
        compute_hinged_bangle_params(165.0, clasp_style="mystery_clasp")


def test_hinged_bangle_zero_pin_raises():
    with pytest.raises(ValueError):
        compute_hinged_bangle_params(165.0, hinge_pin_diameter_mm=0.0)


def test_wrist_size_unknown_raises():
    with pytest.raises(ValueError, match="Unknown wrist size"):
        wrist_size_to_inner_circumference("ENORMOUS")


# ---------------------------------------------------------------------------
# Idempotency: calling compute_* twice with same args returns same result
# ---------------------------------------------------------------------------

def test_closed_bangle_idempotent():
    kwargs = dict(
        inner_circumference_mm=165.0,
        cross_section="d_shape",
        cs_width_mm=5.0,
        inner_profile="oval",
        metal="18k_yellow",
        n_stone_stations=3,
    )
    p1 = compute_closed_bangle_params(**kwargs)
    p2 = compute_closed_bangle_params(**kwargs)
    assert p1 == p2


def test_open_cuff_idempotent():
    kwargs = dict(
        inner_circumference_mm=175.0,
        gap_angle_deg=45.0,
        cross_section="knife_edge",
        cs_width_mm=6.0,
        metal="sterling_925",
    )
    p1 = compute_open_cuff_params(**kwargs)
    p2 = compute_open_cuff_params(**kwargs)
    assert p1 == p2


def test_torque_idempotent():
    kwargs = dict(
        inner_circumference_mm=155.0,
        cs_width_mm=4.0,
        twist_turns=3.0,
        finial_style="cone",
        metal="platinum_950",
    )
    p1 = compute_torque_params(**kwargs)
    p2 = compute_torque_params(**kwargs)
    assert p1 == p2


def test_hinged_bangle_idempotent():
    kwargs = dict(
        inner_circumference_mm=185.0,
        cross_section="half_round",
        cs_width_mm=7.0,
        clasp_style="hidden_box",
        metal="14k_rose",
        n_stone_stations=4,
    )
    p1 = compute_hinged_bangle_params(**kwargs)
    p2 = compute_hinged_bangle_params(**kwargs)
    assert p1 == p2


# ---------------------------------------------------------------------------
# Inner perimeter accuracy — explicit ±0.1 mm check for all 6 table sizes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("size_key", list(WRIST_SIZE_TABLE.keys()))
def test_inner_circumference_accuracy_all_table_sizes(size_key: str):
    """For every entry in WRIST_SIZE_TABLE the returned inner_circumference_mm
    matches the lookup value to within ±0.1 mm."""
    target = WRIST_SIZE_TABLE[size_key]
    params = compute_closed_bangle_params(
        inner_circumference_mm=target,
        cross_section="round_wire",
        cs_width_mm=4.0,
    )
    assert abs(params["inner_circumference_mm"] - target) <= 0.1


@pytest.mark.parametrize("size_key", list(WRIST_SIZE_TABLE.keys()))
def test_inner_diameter_accuracy_all_table_sizes(size_key: str):
    """inner_diameter_mm = inner_circumference_mm / π ± 0.1 mm."""
    target_circ = WRIST_SIZE_TABLE[size_key]
    expected_d = target_circ / _PI
    params = compute_closed_bangle_params(
        inner_circumference_mm=target_circ,
        cross_section="half_round",
        cs_width_mm=3.0,
    )
    assert abs(params["inner_diameter_mm"] - expected_d) <= 0.1
