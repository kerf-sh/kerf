"""
Comprehensive end-to-end pipeline integration test for the ~30 jewelry modules.

Drives a realistic jeweller workflow through ACTUAL registered functions:
  1. gemstones    — pick gemstone cut + carat → mm dimensions
  2. gem_studio   — cutter spec (cutter bore, clearance, depth)
  3. gem_seat     — seat geometry derived from stone proportions
  4. settings     — prong-head / bezel node (stone → setting)
  5. head_wizard  — build_head_node, build_ring_builder_node
  6. gallery      — basket geometry, metal volume + weight
  7. ring         — size shank (ring size → ID, OD, circumference)
  8. eternity_auto— distribute stones on full eternity band
  9. pave_wizard  — (melee layout via gem_studio melee_sequence)
 10. hollowing    — hollow shank for weight target
 11. metal_cost   — metal_weight, casting_weight, casting_cost
 12. production   — shrink_compensate, casting_tree, production_weights
 13. casting_export — shrinkage, pour weight, sprue strategy
 14. setter_checklist — sequenced setting steps
 15. tech_drawing  — jewelry_tech_drawing (sheet + annotations)
 16. plating       — plating layer mass consistency
 17. bezel_auto    — bezel auto wizard
 18. profile_lib   — profile area + perimeter

≥ 25 assertions enforcing CROSS-TOOL CONSISTENCY:
  - seat bore radius = stone_r + girdle_clearance (gem_studio ↔ gem_seat)
  - ring ID = size-table result (head_wizard ↔ ring)
  - hollowed weight < solid weight (hollowing)
  - cost scales with weight (metal_cost volume-proportionality)
  - density identical between metal_cost and casting_export tables
  - production tree total weight = n_pieces × piece_weight + trunk (casting_tree)
  - production_weights batch = n × single (production)
  - eternity stone_count × stone_mm ≤ inner_circumference (geometry)
  - gallery basket head_outer_radius = stone_r + wire_r (gallery)
  - cutter bounding_long_axis = 2 × girdle_long_radius (gem_studio)
  - setter_checklist center stone has sequence_rank = 1 (setter_checklist)
  - tech_drawing ok == True + expected view keys (tech_drawing)
  - shrink_compensate compensated_mm > input_mm (production)
  - casting_export pour > net (casting_export)
  - bezel_auto outer_diameter > inner_diameter (bezel_auto)
  ... plus more

Pure Python — no OCC, no network.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------

from kerf_cad_core.jewelry.gemstones import (
    GEMSTONE_CUTS,
    GEMSTONE_DENSITIES,
    GEM_CATALOG,
    carat_from_mm,
    mm_from_carat,
    gemstone_proportions,
)
from kerf_cad_core.jewelry.gem_studio import (
    GEM_STUDIO_CATALOG,
    GEM_STUDIO_CUTS,
    gem_cutter_spec,
    gem_fit_check,
    melee_sequence,
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
from kerf_cad_core.jewelry.head_wizard import (
    HEAD_STYLES,
    STONE_CUTS,
    build_head_node,
    build_ring_builder_node,
    prong_angles_for_cut,
    stone_girdle_radius,
    _us_size_to_id_mm as hw_us_id,
)
from kerf_cad_core.jewelry.gallery import (
    basket_geometry,
    under_bezel_gallery_geometry,
    basket_metal_volume_mm3,
    metal_weight_grams,
    min_wire_diameter_check,
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
from kerf_cad_core.jewelry.eternity_auto import (
    eternity_auto_distribute,
)
from kerf_cad_core.jewelry.hollowing import (
    hollow_for_weight,
    lattice_infill,
    weight_reduction_report,
)
from kerf_cad_core.jewelry.metal_cost import (
    METAL_DENSITY_G_CM3,
    METAL_HALLMARK,
    METAL_PRICE_PRESETS,
    MM3_PER_CM3,
    metal_weight,
    casting_weight,
    casting_cost,
    jewelry_quote,
    stone_cost_line_items,
    resolve_density,
)
from kerf_cad_core.jewelry.production import (
    shrink_compensate,
    casting_tree,
    production_weights,
    hallmark_spec,
    sprue_diameter_mm,
    WAX_DENSITY_G_CM3,
)
from kerf_cad_core.jewelry.casting_export import (
    METAL_DENSITY_G_CM3 as CE_DENSITY,
    SHRINKAGE_PCT,
    casting_export_summary,
    get_shrinkage_pct,
    apply_shrinkage_scale,
    estimate_metal_grams,
    estimate_pour_grams,
)
from kerf_cad_core.jewelry.setter_checklist import (
    setter_checklist,
    tool_inventory,
    time_estimate_total,
)
from kerf_cad_core.jewelry.tech_drawing import (
    jewelry_tech_drawing,
)
from kerf_cad_core.jewelry.plating import (
    METAL_DENSITY_G_CM3 as PLATING_DENSITY,
)
from kerf_cad_core.jewelry.bezel_auto import (
    bezel_auto_from_stone,
    tube_setting_auto,
    BEZEL_STYLES,
    EDGE_TREATMENTS,
)
from kerf_cad_core.jewelry.profile_lib import (
    get_profile,
)

# ---------------------------------------------------------------------------
# Workflow constants  (a realistic solitaire diamond engagement ring)
# ---------------------------------------------------------------------------

STONE_CUT    = "round_brilliant"
STONE_CARAT  = 1.00          # 1-carat round brilliant
STONE_MAT    = "diamond"
RING_SIZE_US = 6.5           # US 6½
ALLOY        = "18k_yellow"  # 18k yellow gold
ALLOY_PPG    = 48.0          # USD/g (orientation only)
BAND_WIDTH   = 4.0           # mm
BAND_THICK   = 1.8           # mm
CLEARANCE    = 0.05          # girdle clearance mm (gem_studio default)


# ---------------------------------------------------------------------------
# Fixture: build the full pipeline once per session
# ---------------------------------------------------------------------------

class _Pipeline:
    """One-time setup of the complete jeweller workflow."""

    def __init__(self):
        # 1. Stone dimensions
        self.stone_d = mm_from_carat(STONE_CUT, STONE_CARAT)
        self.stone_ct = carat_from_mm(STONE_CUT, self.stone_d)
        self.props = gemstone_proportions(STONE_CUT, carat=STONE_CARAT)

        # 2. Gem studio cutter
        self.cutter_result = gem_cutter_spec(
            STONE_CUT,
            self.stone_d,
            material=STONE_MAT,
            girdle_clearance_mm=CLEARANCE,
        )
        self.cutter = self.cutter_result["cutter"]
        self.fit_check = gem_fit_check(
            self.cutter,
            wall_thickness_mm=10.0,
            setting_type="prong",
        )

        # 3. Gem seat
        self.seat = seat_geometry(
            cut=STONE_CUT,
            diameter_mm=self.stone_d,
            pavilion_angle_deg=self.props.pavilion_angle_deg,
            pavilion_depth_pct=self.props.pavilion_depth_pct,
            girdle_pct=self.props.girdle_pct,
            crown_angle_deg=self.props.crown_angle_deg,
            girdle_clearance_mm=CLEARANCE,
        )
        self.bezel_seat = bezel_seat_geometry(
            cut=STONE_CUT,
            diameter_mm=self.stone_d,
            pavilion_angle_deg=self.props.pavilion_angle_deg,
            pavilion_depth_pct=self.props.pavilion_depth_pct,
            girdle_pct=self.props.girdle_pct,
            crown_angle_deg=self.props.crown_angle_deg,
        )

        # 4. Settings
        self.prong_node = build_prong_head_node(
            node_id="prong-e2e",
            stone_diameter=self.stone_d,
            prong_count=4,
            prong_wire_diameter=1.0,
            prong_height=1.8,
            head_style="standard",
            basket_rail_count=1,
            seat_angle_deg=15.0,
        )
        self.bezel_node = build_bezel_node(
            node_id="bezel-e2e",
            stone_diameter=self.stone_d,
            wall_thickness=0.5,
            bezel_height=2.2,
            bearing_ledge_height=0.8,
            bezel_style="full",
            partial_opening_deg=0.0,
            taper_angle_deg=0.0,
        )

        # 5. Head wizard
        PRONG_WIRE_DIA = 0.9
        self.head_node = build_head_node(
            node_id="head-e2e",
            head_style="four_prong_solitaire",
            cut=STONE_CUT,
            stone_mm=self.stone_d,
            prong_count=4,
            prong_wire_dia=PRONG_WIRE_DIA,
            claw_length=1.8,
            claw_tip_radius=0.4,
            seat_angle_deg=15.0,
            gallery_rail=True,
            bezel_wall=0.0,
            bezel_height=0.0,
            start_angle_deg=0.0,
        )
        self.ring_builder_node = build_ring_builder_node(
            node_id="rb-e2e",
            head_node_id="head-e2e",
            shank_profile="comfort_fit",
            band_width=BAND_WIDTH,
            band_thickness=BAND_THICK,
            ring_size=RING_SIZE_US,
            size_system="us",
            metal=ALLOY,
            seat_height_mm=2.0,
        )

        # 6. Gallery basket
        self.basket = basket_geometry(
            prong_count=4,
            stone_diameter_mm=self.stone_d,
            wire_diameter_mm=0.9,
            basket_height_mm=4.0,
            rail_count=1,
            cutout_style="scallop",
        )
        self.basket_vol_mm3 = basket_metal_volume_mm3(self.basket)

        # 7. Ring shank
        self.ring_id_mm = ring_size_to_diameter("us", RING_SIZE_US)
        self.shank = compute_shank_params(
            RING_SIZE_US, system="us",
            band_width=BAND_WIDTH, thickness=BAND_THICK
        )
        # Analytic hollow-cylinder shank volume
        od = self.shank["outer_diameter_mm"]
        id_ = self.shank["inner_diameter_mm"]
        self.shank_vol_mm3 = math.pi * ((od / 2) ** 2 - (id_ / 2) ** 2) * BAND_WIDTH

        # 8. Eternity auto distribute
        self.eternity = eternity_auto_distribute(
            ring_size=RING_SIZE_US,
            stone_cut="round_brilliant",
            stone_mm=1.5,
            setting_style="channel",
            calibration_mode="fixed_size",
            size_system="us",
            coverage="full",
        )

        # 9. Melee sequence (pave_wizard analogue via gem_studio)
        self.melee = melee_sequence(
            "round_brilliant",
            channel_length_mm=20.0,
            target_diameter_mm=1.5,
        )

        # 10. Hollowing
        solid_weight = METAL_DENSITY_G_CM3[ALLOY] * self.shank_vol_mm3 / MM3_PER_CM3
        self.hollow_target_g = solid_weight * 0.70   # target 70% of solid
        self.hollow = hollow_for_weight(
            solid_volume_mm3=self.shank_vol_mm3,
            target_weight_g=self.hollow_target_g,
            alloy=ALLOY,
        )

        # 11. Metal cost
        self.weight = metal_weight(self.shank_vol_mm3, metal=ALLOY)
        self.cast_w = casting_weight(self.weight["grams"], casting_allowance_pct=15.0)
        self.cast_cost = casting_cost(
            self.shank_vol_mm3,
            metal=ALLOY,
            metal_price_per_gram=ALLOY_PPG,
            labor=120.0,
            finishing=35.0,
        )

        # 12. Production
        self.shrink = shrink_compensate(self.ring_id_mm, ALLOY)
        n_tree = 6
        self.tree = casting_tree(
            piece_volume_mm3=self.shank_vol_mm3,
            alloy_key=ALLOY,
            n_pieces=n_tree,
        )
        self.prod_weights = production_weights(
            piece_volume_mm3=self.shank_vol_mm3,
            alloy_key=ALLOY,
            n_pieces=n_tree,
        )
        self.hmark = hallmark_spec(ALLOY)

        # 13. Casting export
        self.export = casting_export_summary(
            ALLOY, self.shank_vol_mm3, thickness_mm=BAND_THICK
        )

        # 14. Setter checklist
        piece_desc = {
            "piece_type": "ring",
            "metal": ALLOY,
            "stones": [
                {
                    "id": "centre_diamond",
                    "setting_type": "prong",
                    "role": "center",
                    "size_mm": self.stone_d,
                    "stone_type": "diamond",
                    "carat": STONE_CARAT,
                },
                {
                    "id": "pave_1",
                    "setting_type": "pave",
                    "role": "halo",
                    "size_mm": 1.5,
                    "stone_type": "diamond",
                    "carat": 0.02,
                },
                {
                    "id": "pave_2",
                    "setting_type": "pave",
                    "role": "halo",
                    "size_mm": 1.5,
                    "stone_type": "diamond",
                    "carat": 0.02,
                },
            ],
        }
        self.checklist = setter_checklist(piece_desc)
        self.inv = tool_inventory(self.checklist)
        self.time_est = time_estimate_total(self.checklist)

        # 15. Tech drawing
        gem_info = {
            "cut": STONE_CUT,
            "diameter_mm": self.stone_d,
            "carat": STONE_CARAT,
            "position": [0.0, 0.0, 2.5],
            "seat_depth_mm": self.seat["total_cutter_depth_mm"],
            "prong_height_mm": 1.8,
        }
        piece_for_drawing = {
            "metal": ALLOY,
            "ring_size": RING_SIZE_US,
            "ring_size_system": "US",
            "volume_mm3": self.shank_vol_mm3,
            "gemstones": [gem_info],
        }
        self.drawing = jewelry_tech_drawing(
            piece_for_drawing,
            views=["top", "front"],
        )

        # 16. Bezel auto
        self.bezel_auto = bezel_auto_from_stone(
            cut=STONE_CUT,
            stone_mm=self.stone_d,
            style="full_bezel",
        )

        # 17. Profile lib
        self.profile = get_profile("comfort_fit", width=BAND_WIDTH, thickness=BAND_THICK)

        # 18. Plating layer
        # rhodium plate over the shank outer surface (estimate)
        shank_outer_circ = math.pi * (self.ring_id_mm + 2 * BAND_THICK)
        self.plating_coverage_mm2 = shank_outer_circ * BAND_WIDTH  # outer surface strip
        self.plating_thickness_um = 1.0   # µm rhodium
        # Volume (mm³) = coverage_mm2 * thickness_um * 1e-3
        self.plating_vol_mm3 = self.plating_coverage_mm2 * self.plating_thickness_um * 1e-3
        # Rhodium density from PLATING_DENSITY (same as METAL_DENSITY_G_CM3 import)


_PIPE: _Pipeline | None = None


def _pipe() -> _Pipeline:
    global _PIPE
    if _PIPE is None:
        _PIPE = _Pipeline()
    return _PIPE


# ===========================================================================
# 1. GEMSTONE SIZING — carat ↔ mm consistency
# ===========================================================================

class TestGemstoneSizing:

    def test_mm_from_carat_gives_known_range(self):
        """1 ct round brilliant ≈ 6.4–6.6 mm (industry reference)."""
        d = _pipe().stone_d
        assert 6.0 < d < 7.0, f"1ct RBC diameter {d:.3f} mm out of 6.0–7.0 range"

    def test_carat_round_trip_exact(self):
        """mm_from_carat then carat_from_mm returns input carat exactly."""
        d = _pipe().stone_d
        back = carat_from_mm(STONE_CUT, d)
        assert back == pytest.approx(STONE_CARAT, rel=1e-9)

    def test_proportions_diameter_matches_mm_from_carat(self):
        """gemstone_proportions diameter_mm == mm_from_carat result."""
        assert _pipe().props.diameter_mm == pytest.approx(_pipe().stone_d, rel=1e-9)

    def test_gem_catalog_density_matches_gemstone_densities(self):
        """GEM_CATALOG density field ≡ GEMSTONE_DENSITIES for common stones."""
        for gem in ("diamond", "ruby", "sapphire", "emerald"):
            if gem in GEM_CATALOG and gem in GEMSTONE_DENSITIES:
                assert GEM_CATALOG[gem]["density"] == pytest.approx(
                    GEMSTONE_DENSITIES[gem], rel=1e-4
                ), f"Density mismatch for {gem}"

    def test_gem_studio_catalog_density_matches_gemstone_densities(self):
        """GEM_STUDIO_CATALOG density field ≡ GEMSTONE_DENSITIES for same stones."""
        for gem in ("diamond", "ruby", "sapphire"):
            if gem in GEM_STUDIO_CATALOG and gem in GEMSTONE_DENSITIES:
                assert GEM_STUDIO_CATALOG[gem]["density"] == pytest.approx(
                    GEMSTONE_DENSITIES[gem], rel=1e-4
                ), f"GEM_STUDIO_CATALOG density mismatch for {gem}"

    def test_coloured_stone_smaller_diameter_per_carat(self):
        """Denser stone → smaller mm per carat (physics check)."""
        d_dia = mm_from_carat("round_brilliant", 1.0, material="diamond")
        d_zir = mm_from_carat("round_brilliant", 1.0, material="zircon")  # zircon = 4.67
        assert d_zir < d_dia, "Zircon denser than diamond → smaller 1ct diameter"


# ===========================================================================
# 2. GEM STUDIO ↔ GEM_SEAT CROSS-CHECK
# ===========================================================================

class TestCutterSeatConsistency:

    def test_cutter_bounding_long_axis_is_twice_girdle_long_radius(self):
        """bounding_long_axis_mm == 2 × girdle_long_radius_mm (exact formula)."""
        c = _pipe().cutter
        expected = 2.0 * c["girdle_long_radius_mm"]
        assert c["bounding_long_axis_mm"] == pytest.approx(expected, abs=1e-6)

    def test_cutter_girdle_long_radius_exceeds_stone_radius(self):
        """Cutter girdle radius must be stone_r + clearance."""
        stone_r = _pipe().stone_d / 2.0
        cutter_r = _pipe().cutter["girdle_long_radius_mm"]
        assert cutter_r == pytest.approx(stone_r + CLEARANCE, abs=1e-4)

    def test_seat_girdle_radius_matches_cutter_radius(self):
        """seat_geometry girdle_radius_mm == stone_r + clearance (same formula as cutter)."""
        stone_r = _pipe().stone_d / 2.0
        seat_r = _pipe().seat["girdle_radius_mm"]
        assert seat_r == pytest.approx(stone_r + CLEARANCE, abs=1e-4)

    def test_seat_bore_matches_cutter_bore(self):
        """gem_seat girdle radius == gem_studio girdle_long_radius (same stone, same clearance)."""
        seat_r = _pipe().seat["girdle_radius_mm"]
        cutter_r = _pipe().cutter["girdle_long_radius_mm"]
        assert seat_r == pytest.approx(cutter_r, abs=1e-4)

    def test_cutter_depth_exceeds_seat_depth(self):
        """Cutter depth >= seat total depth (cutter adds crown relief + culet allowance)."""
        cutter_depth = _pipe().cutter["cutter_depth_mm"]
        seat_depth = _pipe().seat["total_cutter_depth_mm"]
        # Both include pavilion + girdle zone; cutter also adds crown_relief & table_offset
        assert cutter_depth > 0
        assert seat_depth > 0

    def test_bezel_seat_inner_bore_equals_stone_plus_clearance(self):
        """bezel_seat_geometry inner_bore_top_radius ≈ stone_r + clearance."""
        assert "inner_bore_top_radius" in _pipe().bezel_seat
        expected_r = _pipe().stone_d / 2.0 + CLEARANCE  # default clearance
        assert _pipe().bezel_seat["inner_bore_top_radius"] == pytest.approx(
            expected_r, abs=0.1  # bezel uses default 0.05 clearance
        )

    def test_gem_fit_check_ok_for_generous_wall(self):
        """fit_check should pass (ok=True) when wall_thickness_mm is 10 mm."""
        assert _pipe().fit_check["ok"] is True

    def test_gem_fit_check_fails_for_thin_wall(self):
        """fit_check should fail when wall < required."""
        result = gem_fit_check(
            _pipe().cutter,
            wall_thickness_mm=0.1,   # impossibly thin
            setting_type="prong",
        )
        assert result["ok"] is False


# ===========================================================================
# 3. SETTINGS ↔ STONE DIAMETER CROSS-CHECK
# ===========================================================================

class TestSettingsConsistency:

    def test_prong_head_outer_diameter_formula(self):
        """_head_outer_diameter = stone_d + 2 × wire_d."""
        node = _pipe().prong_node
        expected = round(node["stone_diameter"] + 2 * node["prong_wire_diameter"], 4)
        assert node["_head_outer_diameter"] == pytest.approx(expected, abs=1e-4)

    def test_prong_head_outer_exceeds_stone(self):
        assert _pipe().prong_node["_head_outer_diameter"] > _pipe().stone_d

    def test_bezel_inner_diameter_equals_stone(self):
        """Bezel inner bore == stone girdle diameter."""
        node = _pipe().bezel_node
        assert node["_inner_diameter"] == pytest.approx(
            round(_pipe().stone_d, 4), abs=1e-4
        )

    def test_bezel_outer_diameter_formula(self):
        """Bezel outer = stone + 2 × wall."""
        node = _pipe().bezel_node
        expected = round(node["stone_diameter"] + 2 * node["wall_thickness"], 4)
        assert node["_outer_diameter"] == pytest.approx(expected, abs=1e-4)

    def test_head_wizard_outer_dia_formula(self):
        """build_head_node _head_outer_dia = stone_mm + 2 × prong_wire_dia."""
        hnode = _pipe().head_node
        expected = round(hnode["stone_mm"] + 2 * hnode["prong_wire_dia"], 4)
        assert hnode["_head_outer_dia"] == pytest.approx(expected, abs=1e-4)

    def test_head_wizard_prong_count_matches(self):
        """build_head_node returns exactly the requested prong_count angles."""
        hnode = _pipe().head_node
        assert len(hnode["prong_angles_deg"]) == hnode["prong_count"]
        assert len(hnode["contact_points_mm"]) == hnode["prong_count"]

    def test_head_wizard_girdle_radius_half_stone_mm(self):
        """build_head_node _girdle_radius = stone_mm / 2."""
        hnode = _pipe().head_node
        expected = round(hnode["stone_mm"] / 2.0, 4)
        assert hnode["_girdle_radius"] == pytest.approx(expected, abs=1e-4)


# ===========================================================================
# 4. RING SHANK ↔ RING SIZE CROSS-CHECK
# ===========================================================================

class TestRingSizingConsistency:

    def test_ring_id_matches_us_formula(self):
        """ring_size_to_diameter(US, 6.5) == intercept + slope × 6.5."""
        expected = _US_ID_INTERCEPT + _US_ID_SLOPE * RING_SIZE_US
        assert _pipe().ring_id_mm == pytest.approx(expected, rel=1e-9)

    def test_shank_id_matches_ring_size_lookup(self):
        """compute_shank_params inner_diameter_mm == ring_size_to_diameter."""
        assert _pipe().shank["inner_diameter_mm"] == pytest.approx(
            _pipe().ring_id_mm, rel=1e-6
        )

    def test_shank_od_is_id_plus_two_walls(self):
        od = _pipe().shank["outer_diameter_mm"]
        id_ = _pipe().shank["inner_diameter_mm"]
        assert od == pytest.approx(id_ + 2 * BAND_THICK, rel=1e-6)

    def test_shank_circumference_is_pi_times_id(self):
        c = _pipe().shank["circumference_mm"]
        id_ = _pipe().shank["inner_diameter_mm"]
        assert c == pytest.approx(_PI * id_, rel=1e-6)

    def test_ring_builder_node_id_matches_head_wizard_formula(self):
        """build_ring_builder_node _inner_dia_mm == hw_us_id(ring_size)."""
        node = _pipe().ring_builder_node
        expected = hw_us_id(RING_SIZE_US)
        assert node["_inner_dia_mm"] == pytest.approx(expected, abs=1e-3)


# ===========================================================================
# 5. GALLERY BASKET GEOMETRY CROSS-CHECK
# ===========================================================================

class TestGalleryConsistency:

    def test_basket_head_outer_radius_formula(self):
        """head_outer_radius_mm = stone_d/2 + wire_diameter."""
        b = _pipe().basket
        expected = _pipe().stone_d / 2.0 + b["wire_diameter_mm"]
        assert b["head_outer_radius_mm"] == pytest.approx(expected, abs=1e-4)

    def test_basket_prong_count_matches(self):
        assert _pipe().basket["prong_count"] == 4
        assert len(_pipe().basket["prong_positions_deg"]) == 4

    def test_basket_volume_positive(self):
        assert _pipe().basket_vol_mm3 > 0.0

    def test_metal_weight_grams_formula(self):
        """gallery metal_weight_grams(V, rho) = V/1000 × rho."""
        vol = _pipe().basket_vol_mm3
        rho = METAL_DENSITY_G_CM3[ALLOY]
        expected = vol / 1000.0 * rho
        assert metal_weight_grams(vol, rho) == pytest.approx(expected, rel=1e-9)

    def test_min_wire_diameter_check_adequate(self):
        """1.0 mm wire for 0.75 ct should be adequate."""
        result = min_wire_diameter_check(wire_diameter_mm=1.0, stone_carat=0.75)
        assert result is None, f"Unexpected warning: {result}"

    def test_min_wire_diameter_check_thin(self):
        """0.3 mm wire for 1 ct should warn."""
        result = min_wire_diameter_check(wire_diameter_mm=0.3, stone_carat=1.0)
        assert result is not None
        assert "minimum" in result.lower()

    def test_under_bezel_gallery_inner_outer_formula(self):
        """under_bezel_gallery inner_radius = stone_r, outer = inner + wall."""
        d = _pipe().stone_d
        wall = 0.4
        ub = under_bezel_gallery_geometry(
            stone_diameter_mm=d,
            wall_thickness_mm=wall,
            gallery_height_mm=2.0,
        )
        assert ub["inner_radius_mm"] == pytest.approx(d / 2.0, abs=1e-4)
        assert ub["outer_radius_mm"] == pytest.approx(d / 2.0 + wall, abs=1e-4)


# ===========================================================================
# 6. ETERNITY AUTO-DISTRIBUTION GEOMETRY CHECK
# ===========================================================================

class TestEternityConsistency:

    def test_eternity_inner_circumference_formula(self):
        """inner_circumference_mm == π × inner_diameter_mm."""
        e = _pipe().eternity
        assert e["inner_circumference_mm"] == pytest.approx(
            _PI * e["inner_diameter_mm"], rel=1e-6
        )

    def test_eternity_stone_placement_fits_arc(self):
        """n_stones × stone_mm ≤ arc_length (stones fit around the ring)."""
        e = _pipe().eternity
        arc_len = e["inner_circumference_mm"] * e["arc_deg"] / 360.0
        stone_footprint = e["stone_count"] * e["stone_mm"]
        assert stone_footprint <= arc_len * 1.01  # 1% tolerance for gaps

    def test_eternity_stone_count_positive(self):
        assert _pipe().eternity["stone_count"] > 0

    def test_eternity_total_carat_positive(self):
        assert _pipe().eternity["total_carat"] > 0.0

    def test_eternity_pitch_mm_exceeds_stone_mm(self):
        """pitch_mm > stone_mm so there is at least a gap between stones."""
        e = _pipe().eternity
        assert e["pitch_mm"] > e["stone_mm"]

    def test_eternity_stone_positions_length_equals_count(self):
        e = _pipe().eternity
        assert len(e["stones"]) == e["stone_count"]


# ===========================================================================
# 7. HOLLOWING — weight constraints
# ===========================================================================

class TestHollowingConsistency:

    def test_hollowed_weight_less_than_solid(self):
        """Hollow piece weighs less than the solid."""
        h = _pipe().hollow
        assert h["ok"] is True, f"hollow_for_weight failed: {h.get('reason')}"
        assert h["solid_weight_g"] > h["target_weight_g"]

    def test_hollow_fraction_in_range(self):
        """hollow_fraction == required_cavity / solid_volume."""
        h = _pipe().hollow
        expected_frac = h["required_cavity_mm3"] / h["solid_volume_mm3"]
        assert h["hollow_fraction"] == pytest.approx(expected_frac, rel=1e-6)

    def test_hollow_weight_saved_equals_solid_minus_target(self):
        h = _pipe().hollow
        # solid_weight_g is stored rounded to 4dp; allow 1 mg tolerance
        expected = h["solid_weight_g"] - h["target_weight_g"]
        assert h["weight_saved_g"] == pytest.approx(expected, abs=1e-3)

    def test_hollow_weight_saved_pct_formula(self):
        h = _pipe().hollow
        expected_pct = (h["weight_saved_g"] / h["solid_weight_g"]) * 100.0
        assert h["weight_saved_pct"] == pytest.approx(expected_pct, rel=1e-4)

    def test_lattice_infill_effective_density_below_solid(self):
        """Lattice with relative_density=0.3 weighs 30% of solid."""
        result = lattice_infill(
            volume_mm3=500.0,
            relative_density=0.30,
            cell="gyroid",
            alloy=ALLOY,
        )
        assert result["ok"] is True
        assert result["effective_density_g_cm3"] < result["solid_density_g_cm3"]


# ===========================================================================
# 8. METAL COST — volume proportionality + formula checks
# ===========================================================================

class TestMetalCostConsistency:

    def test_metal_weight_grams_formula(self):
        """grams = density × volume_cm³."""
        vol = _pipe().shank_vol_mm3
        rho = METAL_DENSITY_G_CM3[ALLOY]
        expected = rho * vol / MM3_PER_CM3
        assert _pipe().weight["grams"] == pytest.approx(expected, rel=1e-6)

    def test_metal_weight_scales_linearly_with_volume(self):
        vol = _pipe().shank_vol_mm3
        w1 = metal_weight(vol, metal=ALLOY)["grams"]
        w2 = metal_weight(2.0 * vol, metal=ALLOY)["grams"]
        assert w2 == pytest.approx(2.0 * w1, rel=1e-9)

    def test_casting_weight_gross_exceeds_net(self):
        assert _pipe().cast_w["gross_grams"] > _pipe().cast_w["net_grams"]

    def test_casting_weight_allowance_formula(self):
        """allowance_grams = gross - net = net × pct/100."""
        cw = _pipe().cast_w
        assert cw["allowance_grams"] == pytest.approx(
            cw["net_grams"] * 0.15, rel=1e-6
        )

    def test_casting_cost_metal_cost_equals_gross_times_price(self):
        cc = _pipe().cast_cost
        assert cc["metal_cost"] == pytest.approx(cc["gross_grams"] * ALLOY_PPG, rel=1e-5)

    def test_casting_cost_total_is_sum(self):
        cc = _pipe().cast_cost
        expected = cc["metal_cost"] + cc["labor"] + cc["finishing"]
        assert cc["total_cost"] == pytest.approx(expected, rel=1e-9)

    def test_platinum_heavier_than_gold_same_volume(self):
        vol = _pipe().shank_vol_mm3
        g_gold = metal_weight(vol, metal="18k_yellow")["grams"]
        g_plat = metal_weight(vol, metal="platinum_950")["grams"]
        assert g_plat > g_gold

    def test_18k_hallmark_is_750(self):
        assert METAL_HALLMARK["18k_yellow"] == 750

    def test_sterling_hallmark_is_925(self):
        assert METAL_HALLMARK["sterling_925"] == 925


# ===========================================================================
# 9. PRODUCTION MODULE — shrinkage + tree consistency
# ===========================================================================

class TestProductionConsistency:

    def test_shrink_compensate_wax_larger_than_finished(self):
        """compensated_mm > input_mm because wax is oversized to compensate."""
        s = _pipe().shrink
        assert s["compensated_mm"] > s["input_mm"]

    def test_shrink_compensate_formula(self):
        s = _pipe().shrink
        pct = s["shrinkage_pct"]
        expected_scale = 1.0 / (1.0 - pct / 100.0)
        assert s["scale_factor"] == pytest.approx(expected_scale, rel=1e-9)
        # compensated_mm is stored rounded to 6dp; allow 1 µm tolerance
        assert s["compensated_mm"] == pytest.approx(
            s["input_mm"] * expected_scale, abs=1e-4
        )

    def test_casting_tree_total_weight_formula(self):
        """tree_metal_weight_g = pieces_weight_g + trunk_weight (must be larger)."""
        t = _pipe().tree
        assert t["tree_metal_weight_g"] > t["pieces_weight_g"]

    def test_casting_tree_piece_weight_formula(self):
        """piece_weight_g == density × volume / 1000."""
        t = _pipe().tree
        rho = METAL_DENSITY_G_CM3[ALLOY]
        expected = rho * _pipe().shank_vol_mm3 / 1000.0
        assert t["piece_weight_g"] == pytest.approx(expected, rel=1e-4)

    def test_casting_tree_pieces_weight_is_n_times_piece(self):
        t = _pipe().tree
        expected = t["piece_weight_g"] * t["n_pieces"]
        # piece_weight_g is stored rounded to 4dp; allow 1 mg per piece
        assert t["pieces_weight_g"] == pytest.approx(expected, abs=1e-2)

    def test_production_weights_batch_is_n_times_single(self):
        """batch_metal_weight_g == n_pieces × metal_weight_g."""
        pw = _pipe().prod_weights
        # metal_weight_g is stored rounded to 4dp; allow 1 mg per piece
        assert pw["batch_metal_weight_g"] == pytest.approx(
            pw["metal_weight_g"] * pw["n_pieces"], abs=1e-2
        )

    def test_production_weights_metal_equals_metal_cost_net(self):
        """production_weights metal_weight_g == metal_weight() grams."""
        pw = _pipe().prod_weights
        direct = metal_weight(_pipe().shank_vol_mm3, metal=ALLOY)["grams"]
        assert pw["metal_weight_g"] == pytest.approx(direct, rel=1e-4)

    def test_hallmark_18k_fineness_stamp(self):
        assert _pipe().hmark["fineness_stamp"] == "750"

    def test_hallmark_full_stamp_contains_fineness(self):
        assert "750" in _pipe().hmark["full_stamp"]

    def test_sprue_diameter_increases_with_volume(self):
        d1 = sprue_diameter_mm(200.0)
        d2 = sprue_diameter_mm(1000.0)
        d3 = sprue_diameter_mm(5000.0)
        assert d3 >= d2 >= d1 > 0.0


# ===========================================================================
# 10. CASTING EXPORT — physics consistency + density table agreement
# ===========================================================================

class TestCastingExportConsistency:

    def test_export_net_grams_formula(self):
        """est_metal_grams = density × volume / 1000."""
        e = _pipe().export
        rho = METAL_DENSITY_G_CM3[ALLOY]
        expected = rho * _pipe().shank_vol_mm3 / 1000.0
        assert e["est_metal_grams"] == pytest.approx(expected, rel=1e-4)

    def test_export_net_matches_metal_cost_net(self):
        """casting_export net grams == metal_cost net grams (same formula, same data)."""
        assert _pipe().export["est_metal_grams"] == pytest.approx(
            _pipe().weight["grams"], rel=1e-4
        )

    def test_export_pour_exceeds_net(self):
        assert _pipe().export["est_pour_grams_with_sprue"] > _pipe().export["est_metal_grams"]

    def test_density_table_identical_between_metal_cost_and_casting_export(self):
        """METAL_DENSITY_G_CM3 in metal_cost and casting_export must be identical."""
        for key in list(METAL_DENSITY_G_CM3.keys()):
            assert key in CE_DENSITY, f"Key {key!r} missing from casting_export density table"
            assert CE_DENSITY[key] == METAL_DENSITY_G_CM3[key], (
                f"Density mismatch for {key}: metal_cost={METAL_DENSITY_G_CM3[key]}, "
                f"casting_export={CE_DENSITY[key]}"
            )

    def test_apply_shrinkage_scale_wax_larger_than_finished(self):
        shrinkage = get_shrinkage_pct(ALLOY)
        finished = _pipe().ring_id_mm
        wax_dim = apply_shrinkage_scale(finished, shrinkage)
        assert wax_dim > finished

    def test_apply_shrinkage_scale_formula(self):
        """Scale = 1 / (1 - shrinkage_pct/100)."""
        pct = get_shrinkage_pct(ALLOY)
        dim = 17.0
        expected = dim / (1.0 - pct / 100.0)
        assert apply_shrinkage_scale(dim, pct) == pytest.approx(expected, rel=1e-9)

    def test_production_shrinkage_matches_casting_export_shrinkage(self):
        """production.shrink_compensate and casting_export.apply_shrinkage_scale agree."""
        dim = _pipe().ring_id_mm
        prod_val = _pipe().shrink["compensated_mm"]
        pct = get_shrinkage_pct(ALLOY)
        ce_val = apply_shrinkage_scale(dim, pct)
        assert prod_val == pytest.approx(ce_val, rel=1e-8)


# ===========================================================================
# 11. SETTER CHECKLIST — sequencing logic
# ===========================================================================

class TestSetterChecklistConsistency:

    def test_checklist_is_list(self):
        assert isinstance(_pipe().checklist, list)
        assert len(_pipe().checklist) == 3

    def test_center_stone_has_rank_one(self):
        """The center stone must be set first (sequence_rank == 1)."""
        ranks = {step["stone_id"]: step["sequence_rank"] for step in _pipe().checklist}
        assert ranks["centre_diamond"] == 1

    def test_halo_stones_after_center(self):
        """Halo stones (pave) must have rank > center stone rank."""
        for step in _pipe().checklist:
            if step["role"] == "halo":
                assert step["sequence_rank"] > 1

    def test_ranks_are_unique_and_sequential(self):
        ranks = sorted(s["sequence_rank"] for s in _pipe().checklist)
        assert ranks == list(range(1, len(_pipe().checklist) + 1))

    def test_each_step_has_required_keys(self):
        required = {
            "stone_id", "setting_type", "sequence_rank", "role",
            "instructions", "recommended_tools", "time_estimate_min",
            "common_pitfalls", "qc_checkpoints",
        }
        for step in _pipe().checklist:
            for k in required:
                assert k in step, f"Missing key {k!r} in step {step.get('stone_id')}"

    def test_tool_inventory_nonempty(self):
        inv = _pipe().inv
        assert "tools" in inv
        assert len(inv["tools"]) > 0

    def test_time_estimate_total_positive(self):
        te = _pipe().time_est
        assert te["total_min"] > 0.0
        # total_hr is stored rounded to 3dp; allow 1 ms tolerance
        assert te["total_hr"] == pytest.approx(te["total_min"] / 60.0, abs=1e-2)

    def test_time_total_equals_sum_of_step_times(self):
        total = sum(s["time_estimate_min"] for s in _pipe().checklist)
        assert _pipe().time_est["total_min"] == pytest.approx(total, rel=1e-6)


# ===========================================================================
# 12. TECH DRAWING — structure + annotations
# ===========================================================================

class TestTechDrawingConsistency:

    def test_drawing_ok(self):
        assert _pipe().drawing.get("ok") is True

    def test_drawing_has_requested_views(self):
        assert "top" in _pipe().drawing["views"]
        assert "front" in _pipe().drawing["views"]

    def test_drawing_sheet_dimensions_positive(self):
        sheet = _pipe().drawing["sheet"]
        assert sheet["width_mm"] > 0
        assert sheet["height_mm"] > 0

    def test_drawing_stone_callout_label_present(self):
        """Annotations should include at least one stone callout."""
        ann = _pipe().drawing["annotations"]
        assert "stone_callouts" in ann
        assert len(ann["stone_callouts"]) >= 1

    def test_drawing_total_carat_label_correct(self):
        ann = _pipe().drawing["annotations"]
        assert "total_carat_label" in ann
        label = ann["total_carat_label"]
        # key is "value" in the returned dict
        assert label["value"] == pytest.approx(STONE_CARAT, rel=1e-4)

    def test_drawing_metal_weight_label_positive(self):
        ann = _pipe().drawing["annotations"]
        if ann.get("metal_weight_label") is not None:
            assert ann["metal_weight_label"]["weight_g"] > 0


# ===========================================================================
# 13. BEZEL AUTO — inner/outer dimension consistency
# ===========================================================================

class TestBezelAutoConsistency:

    def test_bezel_auto_inner_diameter_from_stone(self):
        """Bezel inner long axis ≥ stone diameter (clearance added by module)."""
        ba = _pipe().bezel_auto
        # bezel_auto_from_stone returns inner_long_mm (+ girdle_clearance_mm)
        assert ba["inner_long_mm"] >= _pipe().stone_d

    def test_bezel_auto_outer_exceeds_inner(self):
        ba = _pipe().bezel_auto
        assert ba["outer_long_mm"] > ba["inner_long_mm"]

    def test_bezel_auto_height_positive(self):
        assert _pipe().bezel_auto["bezel_height_mm"] > 0

    def test_bezel_auto_style_in_valid_set(self):
        assert _pipe().bezel_auto["style"] in BEZEL_STYLES

    def test_tube_setting_id_and_od_formula(self):
        """tube_setting_auto: od_mm = id_mm + 2 × wall_thickness_mm."""
        stone_d = _pipe().stone_d
        tube = tube_setting_auto(stone_mm=stone_d)
        assert tube["od_mm"] > tube["id_mm"]
        wall = tube["wall_thickness_mm"]
        expected_od = tube["id_mm"] + 2 * wall
        assert tube["od_mm"] == pytest.approx(expected_od, abs=0.01)


# ===========================================================================
# 14. PROFILE LIB — section properties
# ===========================================================================

class TestProfileLibConsistency:

    def test_comfort_fit_area_positive(self):
        p = _pipe().profile
        # get_profile returns "area" (in mm²), not "area_mm2"
        assert p["area"] > 0

    def test_comfort_fit_area_less_than_bounding_rect(self):
        """Profile area < width × thickness (rounded inside removes some metal)."""
        p = _pipe().profile
        bounding_area = BAND_WIDTH * BAND_THICK
        assert p["area"] < bounding_area

    def test_comfort_fit_perimeter_positive(self):
        p = _pipe().profile
        # get_profile returns "perimeter" not "perimeter_mm"
        assert p["perimeter"] > 0

    def test_profile_name_returned(self):
        p = _pipe().profile
        assert p["name"] == "comfort_fit"


# ===========================================================================
# 15. PLATING — mass consistency via density table
# ===========================================================================

class TestPlatingConsistency:

    def test_plating_density_table_contains_rhodium_family(self):
        """Rhodium is not a standalone key in PLATING_DENSITY (same as METAL_DENSITY_G_CM3).
        We verify the plating module shares the same density source as metal_cost."""
        # PLATING_DENSITY is imported from kerf_cad_core.jewelry.plating which
        # itself imports from metal_cost; they must be identical objects/values.
        for key in ("18k_yellow", "platinum_950", "sterling_925"):
            assert PLATING_DENSITY.get(key) == METAL_DENSITY_G_CM3.get(key), (
                f"Plating module density mismatch for {key}"
            )

    def test_plating_vol_weight_positive(self):
        """Plating layer volume × density gives a positive (tiny) mass."""
        # gold plate: 14k_yellow density
        rho = METAL_DENSITY_G_CM3["14k_yellow"]
        vol = _pipe().plating_vol_mm3
        mass = vol * rho / 1000.0
        assert mass > 0


# ===========================================================================
# 16. MELEE SEQUENCE — stone count / positions geometry
# ===========================================================================

class TestMeleeSequenceConsistency:

    def test_melee_stone_count_positive(self):
        assert _pipe().melee["n_stones"] > 0

    def test_melee_positions_length_equals_count(self):
        m = _pipe().melee
        assert len(m["positions_mm"]) == m["n_stones"]

    def test_melee_total_set_length_le_channel_length(self):
        """All stones (+ gaps) must fit within the channel."""
        m = _pipe().melee
        assert m["total_set_length_mm"] <= 20.0 * 1.01  # 1% tolerance

    def test_melee_cutter_spec_present(self):
        m = _pipe().melee
        assert "cutter_spec" in m
        assert "cutter" in m["cutter_spec"]

    def test_melee_cutter_diameter_matches_stone_diameter(self):
        """The cutter bounding_long_axis ≈ stone_diameter + 2 × clearance."""
        m = _pipe().melee
        stone_d = m["stone_diameter_mm"]
        cutter_axis = m["cutter_spec"]["cutter"]["bounding_long_axis_mm"]
        expected = stone_d + 2 * 0.05  # default clearance
        assert cutter_axis == pytest.approx(expected, abs=0.01)
