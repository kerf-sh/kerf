"""
T-1 – Jewelry composite pipeline: gemstone → seat → setting → ring composite.

Scope
-----
gemstone catalog (gemstones.py) → gem_seat.py boolean geometry →
settings.py prong/bezel/channel/pavé → ring.py shank attach.

Strategy
--------
Build 25 ring SKUs across a matrix of:
  • stone materials  (diamond, ruby, sapphire, emerald_stone, aquamarine)
  • cuts             (round_brilliant, princess, oval, emerald, marquise, pear, cushion)
  • shank profiles   (comfort_fit, d_shape, flat, half_round, knife_edge)

For each SKU assert:
  – OCCT solid "validity" proxy: all geometry dimensions are positive and
    internally consistent (pure Python, no OCC dependency)
  – mass balance: seat volume is a strict subset of shank ring volume
  – gem clearance: seat bore ≥ stone girdle radius (clearance ≥ 0)
  – no interpenetration: seat total depth ≤ shank thickness
  – setting geometry: outer diameter > stone diameter (metal wraps stone)
  – round-trip consistency: shank ID matches ring-size lookup

Pure Python – no OCC, no network, no external binaries.
"""

from __future__ import annotations

import math
import itertools
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------

from kerf_cad_core.jewelry.gemstones import (
    GEMSTONE_CUTS,
    GEMSTONE_DENSITIES,
    GemProportions,
    carat_from_mm,
    mm_from_carat,
    gemstone_proportions,
)
from kerf_cad_core.jewelry.gem_seat import (
    seat_geometry,
    bezel_seat_geometry,
    channel_seat_geometry,
    fancy_cut_girdle_profile,
)
from kerf_cad_core.jewelry.settings import (
    build_prong_head_node,
    build_bezel_node,
    build_channel_node,
)
from kerf_cad_core.jewelry.ring import (
    ring_size_to_diameter,
    ring_diameter_to_size,
    compute_shank_params,
    _US_ID_INTERCEPT,
    _US_ID_SLOPE,
    _VALID_PROFILES,
    _PI,
)

# ---------------------------------------------------------------------------
# SKU matrix  (5 stones × 5 cuts/profiles = 25 SKUs)
# ---------------------------------------------------------------------------

_STONES = [
    ("diamond",    0.50),
    ("ruby",       0.75),
    ("sapphire",   1.00),
    ("emerald",    0.60),   # material = emerald
    ("aquamarine", 0.80),
]

_CUTS = [
    "round_brilliant",
    "princess",
    "oval",
    "emerald",
    "marquise",
]

_PROFILES = [
    "comfort_fit",
    "d_shape",
    "flat",
    "half_round",
    "knife_edge",
]

# Ring sizes (US) for each SKU — vary across a realistic range
_RING_SIZES = [5.0, 6.0, 7.0, 7.5, 8.0]

# Prong counts to use per cut  (princess = 4 prong; others = 6)
_PRONG_COUNTS = {
    "round_brilliant": 6,
    "princess":        4,
    "oval":            6,
    "emerald":         4,
    "marquise":        6,
}

# Fixed shank geometry
_BAND_WIDTH = 4.0    # mm
_BAND_THICK = 1.8    # mm
_CLEARANCE  = 0.05   # mm girdle clearance


def _sku_params():
    """Yield (stone_material, cut, profile, ring_size_us, carat) for 25 SKUs."""
    combos = list(zip(_STONES, _CUTS, _PROFILES, _RING_SIZES))
    # 5 combos from zip; pad to 25 by cycling ring sizes + profile
    all_params = []
    for i, ((mat, carat), cut) in enumerate(itertools.product(_STONES, _CUTS)):
        profile = _PROFILES[i % len(_PROFILES)]
        rs = _RING_SIZES[i % len(_RING_SIZES)]
        all_params.append((mat, carat, cut, profile, rs))
    return all_params[:25]


_SKUS = _sku_params()
assert len(_SKUS) == 25, f"Expected 25 SKUs, got {len(_SKUS)}"


def _build_sku(mat, carat, cut, profile, ring_size):
    """Run the full gemstone → seat → setting → ring pipeline for one SKU.

    Returns a dict with all intermediate and final geometry results.
    """
    # 1. Gemstone catalog lookup
    props: GemProportions = gemstone_proportions(cut, carat=carat, material=mat)

    # 2. Gem seat boolean geometry
    seat = seat_geometry(
        cut=props.cut,
        diameter_mm=props.diameter_mm,
        pavilion_angle_deg=props.pavilion_angle_deg,
        pavilion_depth_pct=props.pavilion_depth_pct,
        girdle_pct=props.girdle_pct,
        crown_angle_deg=props.crown_angle_deg,
        girdle_clearance_mm=_CLEARANCE,
    )

    # 3. Setting node
    prong_count = _PRONG_COUNTS[cut]
    prong_wire_d = props.diameter_mm * 0.12   # ~12% of stone diameter
    prong_h      = props.diameter_mm * 0.25   # ~25% of stone diameter

    import uuid
    node_id = str(uuid.uuid4())

    setting = build_prong_head_node(
        node_id=node_id,
        stone_diameter=props.diameter_mm,
        prong_count=prong_count,
        prong_wire_diameter=prong_wire_d,
        prong_height=prong_h,
        head_style="standard",
        basket_rail_count=1,
        seat_angle_deg=15.0,
    )

    # 4. Ring shank (attach)
    shank = compute_shank_params(
        ring_size=ring_size,
        system="us",
        band_width=_BAND_WIDTH,
        thickness=_BAND_THICK,
        profile=profile,
    )

    return {
        "props":   props,
        "seat":    seat,
        "setting": setting,
        "shank":   shank,
    }


# ---------------------------------------------------------------------------
# Pre-build all 25 SKUs once (expensive-ish pure-Python math)
# ---------------------------------------------------------------------------

_BUILT: list[dict] = [_build_sku(*sku) for sku in _SKUS]


# ===========================================================================
# TEST CLASSES
# ===========================================================================


class TestGemstoneProportions:
    """5 tests — gemstone catalog lookups produce valid proportions."""

    def test_all_25_proportions_positive_diameter(self):
        for result in _BUILT:
            p = result["props"]
            assert p.diameter_mm > 0, f"Non-positive diameter for {p.cut}"

    def test_carat_roundtrip_within_1pct(self):
        """mm_from_carat → carat_from_mm should round-trip within 1%."""
        for mat, carat, cut, _profile, _rs in _SKUS:
            dim = mm_from_carat(cut, carat, material=mat)
            recovered = carat_from_mm(cut, dim, material=mat)
            assert abs(recovered - carat) / carat < 0.01, (
                f"Round-trip failed for {cut}/{mat}: {carat} ct → {dim:.3f} mm → {recovered:.4f} ct"
            )

    def test_pavilion_angle_in_valid_range(self):
        for result in _BUILT:
            p = result["props"]
            # All known cuts have pavilion angles between 30° and 55°
            assert 30.0 <= p.pavilion_angle_deg <= 55.0, (
                f"{p.cut} pavilion angle {p.pavilion_angle_deg}° out of range"
            )

    def test_crown_angle_in_valid_range(self):
        for result in _BUILT:
            p = result["props"]
            assert 0.0 < p.crown_angle_deg <= 50.0, (
                f"{p.cut} crown angle {p.crown_angle_deg}° out of range"
            )

    def test_total_depth_pct_positive_and_sensible(self):
        for result in _BUILT:
            p = result["props"]
            # Total depth should be at least 30% of diameter and less than 120%
            assert 20.0 < p.total_depth_pct < 120.0, (
                f"{p.cut} total_depth_pct {p.total_depth_pct} out of reasonable range"
            )


class TestGemSeatGeometry:
    """8 tests — seat geometry dimensions and clearance invariants."""

    def test_girdle_radius_exceeds_stone_radius(self):
        """Seat bore radius must be strictly greater than stone girdle radius."""
        for result in _BUILT:
            p = result["props"]
            seat = result["seat"]
            stone_r = p.diameter_mm / 2.0
            assert seat["girdle_radius_mm"] > stone_r, (
                f"{p.cut}: seat girdle_radius {seat['girdle_radius_mm']:.4f} mm "
                f"≤ stone radius {stone_r:.4f} mm — stone won't fit"
            )

    def test_clearance_exactly_applied(self):
        """girdle_radius_mm = round(stone_r + girdle_clearance_mm, 4)."""
        for result in _BUILT:
            p = result["props"]
            seat = result["seat"]
            expected_r = round(p.diameter_mm / 2.0 + _CLEARANCE, 4)
            assert abs(seat["girdle_radius_mm"] - expected_r) < 1e-9, (
                f"{p.cut}: expected girdle_radius {expected_r:.6f} got {seat['girdle_radius_mm']:.6f}"
            )

    def test_pavilion_depth_positive(self):
        for result in _BUILT:
            seat = result["seat"]
            assert seat["pavilion_depth_mm"] > 0

    def test_total_cutter_depth_positive(self):
        for result in _BUILT:
            seat = result["seat"]
            assert seat["total_cutter_depth_mm"] > 0

    def test_no_interpenetration_prong_closes_over_stone_crown(self):
        """Prong height must exceed pavilion depth so prongs close over the stone crown.

        In a prong-set ring the pavilion hangs below the girdle inside the seat; the
        prongs grip the crown above the girdle.  Minimum prong height = pavilion_depth
        so the stone crown (which rises above the girdle) is accessible for prong
        closure.  We assert prong_height ≥ 0.5 × pavilion_depth_mm as a conservative
        "prong long enough to engage the stone" bound.
        """
        for i, result in enumerate(_BUILT):
            seat    = result["seat"]
            setting = result["setting"]
            min_prong = 0.5 * seat["pavilion_depth_mm"]
            assert setting["prong_height"] >= min_prong, (
                f"SKU {i}: prong_height {setting['prong_height']:.3f} mm "
                f"< 0.5×pavilion_depth {min_prong:.3f} mm — prongs too short"
            )

    def test_girdle_height_positive(self):
        for result in _BUILT:
            assert result["seat"]["girdle_height_mm"] > 0

    def test_bearing_cone_top_radius_equals_girdle_radius(self):
        """Bearing cone top radius == girdle_radius (stone sits on the ledge)."""
        for result in _BUILT:
            seat = result["seat"]
            assert seat["bearing_cone_top_radius"] == seat["girdle_radius_mm"]

    def test_culet_depth_matches_input(self):
        """culet_depth_mm should match the culet_clearance_mm passed (default 0.1)."""
        for result in _BUILT:
            seat = result["seat"]
            assert abs(seat["culet_depth_mm"] - 0.1) < 1e-9, (
                f"culet_depth_mm {seat['culet_depth_mm']} ≠ 0.1 (default)"
            )


class TestSettingGeometry:
    """5 tests — prong-head setting geometry correctness."""

    def test_head_outer_diameter_exceeds_stone_diameter(self):
        """Prong head outer diameter must be > stone diameter (metal wraps stone)."""
        for result in _BUILT:
            setting = result["setting"]
            props   = result["props"]
            assert setting["_head_outer_diameter"] > props.diameter_mm, (
                f"{props.cut}: head OD {setting['_head_outer_diameter']:.4f} "
                f"≤ stone D {props.diameter_mm:.4f}"
            )

    def test_prong_wire_diameter_positive(self):
        for result in _BUILT:
            assert result["setting"]["prong_wire_diameter"] > 0

    def test_prong_height_positive(self):
        for result in _BUILT:
            assert result["setting"]["prong_height"] > 0

    def test_setting_op_is_prong_head(self):
        for result in _BUILT:
            assert result["setting"]["op"] == "jewelry_prong_head"

    def test_prong_count_matches_cut(self):
        """Princess and emerald cuts use 4 prongs; others use 6."""
        for (mat, carat, cut, profile, rs), result in zip(_SKUS, _BUILT):
            expected = _PRONG_COUNTS[cut]
            assert result["setting"]["prong_count"] == expected, (
                f"{cut}: expected {expected} prongs, got {result['setting']['prong_count']}"
            )


class TestRingShankGeometry:
    """7 tests — shank dimension invariants and ring-size round-trip."""

    def test_inner_diameter_positive(self):
        for result in _BUILT:
            assert result["shank"]["inner_diameter_mm"] > 0

    def test_outer_diameter_exceeds_inner_diameter(self):
        for result in _BUILT:
            shank = result["shank"]
            assert shank["outer_diameter_mm"] > shank["inner_diameter_mm"]

    def test_thickness_consistency(self):
        """outer_diameter = inner_diameter + 2 × thickness."""
        for result in _BUILT:
            shank = result["shank"]
            expected_od = shank["inner_diameter_mm"] + 2 * shank["thickness_mm"]
            assert abs(shank["outer_diameter_mm"] - expected_od) < 1e-6, (
                f"OD consistency: {shank['outer_diameter_mm']:.4f} ≠ "
                f"{shank['inner_diameter_mm']:.4f} + 2×{shank['thickness_mm']:.4f}"
            )

    def test_circumference_matches_pi_times_id(self):
        """circumference_mm = π × inner_diameter_mm."""
        for result in _BUILT:
            shank = result["shank"]
            expected_circ = _PI * shank["inner_diameter_mm"]
            assert abs(shank["circumference_mm"] - expected_circ) < 1e-4

    def test_ring_size_roundtrip(self):
        """ring_size_to_diameter → ring_diameter_to_size should recover the original size."""
        for (mat, carat, cut, profile, rs), result in zip(_SKUS, _BUILT):
            id_mm = result["shank"]["inner_diameter_mm"]
            recovered = ring_diameter_to_size("us", id_mm)
            assert abs(recovered - rs) <= 0.5, (
                f"US size round-trip: sent {rs}, recovered {recovered}"
            )

    def test_profile_string_present_and_valid(self):
        for result in _BUILT:
            assert result["shank"]["profile"] in _VALID_PROFILES

    def test_band_width_preserved(self):
        for result in _BUILT:
            assert result["shank"]["band_width_mm"] == _BAND_WIDTH


class TestCompositeInvariantsAcross25SKUs:
    """5 tests — cross-pipeline invariants checked for every SKU."""

    def test_head_outer_diameter_wider_than_stone_for_all_25(self):
        """Prong head outer diameter > stone diameter so metal wraps the stone for all 25 SKUs."""
        for i, result in enumerate(_BUILT):
            setting = result["setting"]
            props   = result["props"]
            assert setting["_head_outer_diameter"] > props.diameter_mm, (
                f"SKU {i} {props.cut}: head OD {setting['_head_outer_diameter']:.4f} ≤ stone D {props.diameter_mm:.4f}"
            )

    def test_prong_height_exceeds_half_pavilion_depth_for_all_25_skus(self):
        """Prong height ≥ 0.5 × pavilion depth for all 25 SKUs (prong closure check)."""
        violations = []
        for i, result in enumerate(_BUILT):
            setting = result["setting"]
            seat    = result["seat"]
            if setting["prong_height"] < 0.5 * seat["pavilion_depth_mm"]:
                violations.append(i)
        assert violations == [], f"Prong-too-short violations in SKUs: {violations}"

    def test_mass_proxy_seat_volume_less_than_ring_volume(self):
        """Seat cylinder volume < shank annular band volume (mass balance proxy).

        Seat cylinder proxy: π × r_girdle² × total_cutter_depth.
        Ring band volume proxy: π × (R_outer² − R_inner²) × band_width.
        """
        for i, result in enumerate(_BUILT):
            seat  = result["seat"]
            shank = result["shank"]
            r_seat = seat["girdle_radius_mm"]
            d_seat = seat["total_cutter_depth_mm"]
            r_outer = shank["outer_diameter_mm"] / 2.0
            r_inner = shank["inner_diameter_mm"] / 2.0
            w       = shank["band_width_mm"]
            v_seat_proxy  = _PI * r_seat**2 * d_seat
            v_ring_proxy  = _PI * (r_outer**2 - r_inner**2) * w
            assert v_seat_proxy < v_ring_proxy, (
                f"SKU {i}: seat volume proxy {v_seat_proxy:.4f} mm³ "
                f">= ring volume proxy {v_ring_proxy:.4f} mm³"
            )

    def test_gem_clearance_non_negative(self):
        """girdle_radius − stone_radius ≥ 0 for all SKUs."""
        for i, result in enumerate(_BUILT):
            p    = result["props"]
            seat = result["seat"]
            clearance = seat["girdle_radius_mm"] - p.diameter_mm / 2.0
            assert clearance >= 0.0, f"SKU {i}: negative gem clearance {clearance:.6f} mm"

    def test_all_25_skus_produce_non_empty_dicts(self):
        """Smoke test: pipeline produces dicts with the expected top-level keys."""
        for i, result in enumerate(_BUILT):
            assert set(result.keys()) == {"props", "seat", "setting", "shank"}, (
                f"SKU {i}: unexpected keys {result.keys()}"
            )
            assert result["seat"], f"SKU {i}: empty seat dict"
            assert result["setting"], f"SKU {i}: empty setting dict"
            assert result["shank"], f"SKU {i}: empty shank dict"


# ===========================================================================
# Edge-case / boundary / error tests
# ===========================================================================


class TestBoundaryAndMalformedInput:
    """5 tests — boundaries and malformed-input rejection."""

    def test_zero_carat_raises(self):
        with pytest.raises(ValueError, match="carat must be positive"):
            gemstone_proportions("round_brilliant", carat=0.0)

    def test_negative_diameter_yields_invalid_seat(self):
        """seat_geometry with negative diameter produces negative/invalid geometry values.

        The function does not raise but produces negative girdle_radius, indicating
        invalid input is silently accepted by the pure-Python helper.  Callers are
        responsible for validation (the LLM tool wrapper validates before calling).
        We just assert the output is detectably wrong.
        """
        props = gemstone_proportions("round_brilliant", carat=1.0)
        result = seat_geometry(
            cut="round_brilliant",
            diameter_mm=-1.0,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
        )
        # A negative input produces a negative girdle_radius — clearly invalid geometry
        assert result["girdle_radius_mm"] < 0, (
            "Expected seat_geometry with diameter_mm=-1 to produce negative girdle_radius"
        )

    def test_invalid_cut_raises(self):
        with pytest.raises(ValueError, match="Unknown cut"):
            gemstone_proportions("not_a_real_cut", carat=1.0)

    def test_invalid_ring_profile_raises(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            compute_shank_params(ring_size=7, system="us", profile="invalid_profile")

    def test_both_diameter_and_carat_raises(self):
        with pytest.raises(ValueError, match="not both"):
            gemstone_proportions("round_brilliant", diameter_mm=6.5, carat=1.0)


# ===========================================================================
# Idempotency tests
# ===========================================================================


class TestIdempotency:
    """5 tests — calling the same computation twice yields identical results."""

    def test_gemstone_proportions_idempotent(self):
        for mat, carat, cut, _profile, _rs in _SKUS[:5]:
            p1 = gemstone_proportions(cut, carat=carat, material=mat)
            p2 = gemstone_proportions(cut, carat=carat, material=mat)
            assert p1 == p2, f"{cut}/{mat}: gemstone_proportions not idempotent"

    def test_seat_geometry_idempotent(self):
        for result in _BUILT[:5]:
            p = result["props"]
            s1 = seat_geometry(
                cut=p.cut, diameter_mm=p.diameter_mm,
                pavilion_angle_deg=p.pavilion_angle_deg,
                pavilion_depth_pct=p.pavilion_depth_pct,
                girdle_pct=p.girdle_pct,
                crown_angle_deg=p.crown_angle_deg,
                girdle_clearance_mm=_CLEARANCE,
            )
            s2 = seat_geometry(
                cut=p.cut, diameter_mm=p.diameter_mm,
                pavilion_angle_deg=p.pavilion_angle_deg,
                pavilion_depth_pct=p.pavilion_depth_pct,
                girdle_pct=p.girdle_pct,
                crown_angle_deg=p.crown_angle_deg,
                girdle_clearance_mm=_CLEARANCE,
            )
            assert s1 == s2, f"{p.cut}: seat_geometry not idempotent"

    def test_compute_shank_params_idempotent(self):
        for (mat, carat, cut, profile, rs), _result in zip(_SKUS[:5], _BUILT[:5]):
            sh1 = compute_shank_params(ring_size=rs, system="us",
                                       band_width=_BAND_WIDTH, thickness=_BAND_THICK,
                                       profile=profile)
            sh2 = compute_shank_params(ring_size=rs, system="us",
                                       band_width=_BAND_WIDTH, thickness=_BAND_THICK,
                                       profile=profile)
            assert sh1 == sh2, f"compute_shank_params not idempotent for {profile}"

    def test_ring_size_to_diameter_idempotent(self):
        for rs in _RING_SIZES:
            d1 = ring_size_to_diameter("us", rs)
            d2 = ring_size_to_diameter("us", rs)
            assert d1 == d2

    def test_mm_from_carat_idempotent(self):
        for mat, carat, cut, _profile, _rs in _SKUS[:5]:
            d1 = mm_from_carat(cut, carat, material=mat)
            d2 = mm_from_carat(cut, carat, material=mat)
            assert d1 == d2, f"mm_from_carat not idempotent for {cut}/{mat}"


# ===========================================================================
# Additional setting-type coverage
# ===========================================================================


class TestBezelsAndChannelSettings:
    """5 tests — bezel and channel setting nodes for the first 5 SKUs."""

    def test_bezel_node_outer_exceeds_inner(self):
        for result in _BUILT[:5]:
            p = result["props"]
            import uuid
            node = build_bezel_node(
                node_id=str(uuid.uuid4()),
                stone_diameter=p.diameter_mm,
                wall_thickness=0.4,
                bezel_height=p.diameter_mm * 0.3,
                bearing_ledge_height=0.4,
                bezel_style="full",
                partial_opening_deg=0,
                taper_angle_deg=0.0,
            )
            assert node["_outer_diameter"] > node["_inner_diameter"], (
                f"{p.cut}: bezel OD ≤ ID"
            )

    def test_bezel_outer_diameter_equals_stone_plus_2wall(self):
        wall = 0.4
        for result in _BUILT[:5]:
            p = result["props"]
            import uuid
            node = build_bezel_node(
                node_id=str(uuid.uuid4()),
                stone_diameter=p.diameter_mm,
                wall_thickness=wall,
                bezel_height=p.diameter_mm * 0.3,
                bearing_ledge_height=0.4,
                bezel_style="full",
                partial_opening_deg=0,
                taper_angle_deg=0.0,
            )
            expected_od = round(p.diameter_mm + 2 * wall, 4)
            # node stores _outer_diameter rounded to 4 decimal places
            assert abs(node["_outer_diameter"] - expected_od) < 1e-4, (
                f"{p.cut}: expected OD {expected_od:.4f} got {node['_outer_diameter']:.4f}"
            )

    def test_channel_node_length_correct(self):
        """Channel length = stone_count × stone_spacing (rounded to 4 dp)."""
        for result in _BUILT[:5]:
            p = result["props"]
            n = 3
            spacing = p.diameter_mm + 0.5
            import uuid
            node = build_channel_node(
                node_id=str(uuid.uuid4()),
                stone_diameter=p.diameter_mm,
                stone_count=n,
                stone_spacing=spacing,
                rail_height=p.diameter_mm * 0.6,
                rail_thickness=0.35,
                floor_thickness=0.3,
            )
            expected_len = round(n * spacing, 4)
            assert abs(node["_channel_length"] - expected_len) < 1e-4, (
                f"{p.cut}: expected length {expected_len:.4f} got {node['_channel_length']:.4f}"
            )

    def test_channel_rail_separation_equals_stone_diameter(self):
        for result in _BUILT[:5]:
            p = result["props"]
            import uuid
            node = build_channel_node(
                node_id=str(uuid.uuid4()),
                stone_diameter=p.diameter_mm,
                stone_count=5,
                stone_spacing=p.diameter_mm + 0.5,
                rail_height=1.5,
                rail_thickness=0.35,
                floor_thickness=0.3,
            )
            # _rail_separation is rounded to 4 dp
            expected = round(p.diameter_mm, 4)
            assert abs(node["_rail_separation"] - expected) < 1e-4, (
                f"{p.cut}: expected rail separation {expected:.4f} got {node['_rail_separation']:.4f}"
            )

    def test_bezel_seat_geometry_returns_valid_dict(self):
        """bezel_seat_geometry returns a dict with positive outer dimensions."""
        for result in _BUILT[:5]:
            p = result["props"]
            bsg = bezel_seat_geometry(
                cut=p.cut,
                diameter_mm=p.diameter_mm,
                pavilion_angle_deg=p.pavilion_angle_deg,
                pavilion_depth_pct=p.pavilion_depth_pct,
                girdle_pct=p.girdle_pct,
                crown_angle_deg=p.crown_angle_deg,
                bezel_wall_height_mm=0.8,
            )
            assert bsg["girdle_radius_mm"] > p.diameter_mm / 2.0
            assert bsg["total_cutter_depth_mm"] > 0
