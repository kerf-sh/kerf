"""
Tests for kerf_cad_core.jewelry.enamel

Pure-Python: no OCC, no database, no project context required.

Covers (≥ 25 hermetic tests):
  - technique selector: valid / invalid
  - cloisonné: wire length = Σ perimeters − shared edges
  - cloisonné: enamel volume = Σ area × depth
  - cloisonné: per-colour volume grouping
  - champlevé: metal removed = recess area × depth
  - champlevé: enamel fill = recess volume
  - firing schedule: coats increase with depth
  - firing schedule: hard enamel higher kiln temp than soft
  - firing schedule: counter-enamel adds one extra firing
  - counter-enamel doubles enamel mass (net)
  - enamel_mass_with_wastage: total_mass_g > net_mass_g
  - metal compatibility: fine silver OK, no firescale
  - metal compatibility: sterling firescale risk flag
  - metal compatibility: copper OK
  - metal compatibility: titanium incompatible
  - cost: enamel + labour + markup decomposes correctly
  - plan_enamel: invalid technique graceful
  - plan_enamel: incompatible metal graceful
  - plan_enamel: cloisonné end-to-end
  - plan_enamel: champlevé end-to-end
  - plan_enamel: plique_a_jour (no geometry) succeeds
  - plan_enamel: grisaille succeeds
  - plan_enamel: basse_taille succeeds
  - plugin._TOOL_MODULES contains enamel module
  - shared edges counted once reduces wire length correctly
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.jewelry.enamel import (
    COAT_DEPTH_MM,
    ENAMEL_DENSITY_G_CM3,
    ENAMEL_KILN_TEMP_BANDS,
    MM3_PER_CM3,
    TECHNIQUES,
    champleve_recess,
    cloisonne_layout,
    enamel_cost_estimate,
    enamel_mass_with_wastage,
    firing_schedule,
    metal_enamel_compatibility,
    plan_enamel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def approx(expected, rel=1e-5):
    return pytest.approx(expected, rel=rel)


def _simple_cells(n=3, area=100.0, perim=40.0, depth=0.3, colour="red"):
    return [
        {"perimeter_mm": perim, "area_mm2": area, "depth_mm": depth, "colour": colour}
        for _ in range(n)
    ]


def _simple_recesses(n=2, area=50.0, depth=0.4, colour="blue"):
    return [
        {"area_mm2": area, "depth_mm": depth, "colour": colour}
        for _ in range(n)
    ]


# ---------------------------------------------------------------------------
# Technique selector
# ---------------------------------------------------------------------------

class TestTechniqueSelector:
    def test_valid_techniques_in_set(self):
        expected = {"cloisonne", "champleve", "plique_a_jour", "basse_taille", "grisaille"}
        assert TECHNIQUES == expected

    def test_invalid_technique_returns_ok_false(self):
        result = plan_enamel(technique="invalid_xyz", metal_key="fine_silver")
        assert result["ok"] is False
        assert "technique" in result["reason"].lower() or "Unknown" in result["reason"]

    def test_invalid_technique_never_raises(self):
        # Must not raise; always returns dict
        result = plan_enamel(technique="", metal_key="fine_silver")
        assert isinstance(result, dict)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Cloisonné wire-cell layout
# ---------------------------------------------------------------------------

class TestCloisonneLayout:
    def test_wire_length_equals_sum_of_perimeters_no_shared(self):
        cells = _simple_cells(n=4, perim=30.0)
        result = cloisonne_layout(cells)
        assert result["ok"] is True
        assert result["wire_length_mm"] == approx(4 * 30.0)
        assert result["total_perimeter_mm"] == approx(4 * 30.0)
        assert result["shared_edge_total_mm"] == approx(0.0)

    def test_shared_edges_counted_once_reduces_wire_length(self):
        cells = _simple_cells(n=3, perim=20.0)
        shared = [5.0, 7.0]  # two shared segments
        result = cloisonne_layout(cells, shared_edges=shared)
        assert result["ok"] is True
        assert result["total_perimeter_mm"] == approx(3 * 20.0)
        assert result["shared_edge_total_mm"] == approx(12.0)
        assert result["wire_length_mm"] == approx(3 * 20.0 - 12.0)

    def test_enamel_volume_equals_sum_area_times_depth(self):
        cells = [
            {"perimeter_mm": 20.0, "area_mm2": 100.0, "depth_mm": 0.3, "colour": "red"},
            {"perimeter_mm": 15.0, "area_mm2": 80.0,  "depth_mm": 0.5, "colour": "blue"},
        ]
        result = cloisonne_layout(cells)
        assert result["ok"] is True
        expected_vol = 100.0 * 0.3 + 80.0 * 0.5
        assert result["total_enamel_volume_mm3"] == approx(expected_vol)

    def test_enamel_mass_from_volume_and_density(self):
        cells = _simple_cells(n=1, area=200.0, depth=0.4)
        result = cloisonne_layout(cells)
        vol = 200.0 * 0.4  # mm³
        expected_mass = (vol / MM3_PER_CM3) * ENAMEL_DENSITY_G_CM3
        assert result["total_enamel_mass_g"] == approx(expected_mass)

    def test_colour_volume_grouping(self):
        cells = [
            {"perimeter_mm": 10.0, "area_mm2": 50.0, "depth_mm": 0.3, "colour": "red"},
            {"perimeter_mm": 10.0, "area_mm2": 70.0, "depth_mm": 0.3, "colour": "blue"},
            {"perimeter_mm": 10.0, "area_mm2": 60.0, "depth_mm": 0.3, "colour": "red"},
        ]
        result = cloisonne_layout(cells)
        assert result["ok"] is True
        assert result["colour_volumes"]["red"] == approx((50.0 + 60.0) * 0.3)
        assert result["colour_volumes"]["blue"] == approx(70.0 * 0.3)

    def test_empty_cells_fails_gracefully(self):
        result = cloisonne_layout([])
        assert result["ok"] is False

    def test_cell_count_correct(self):
        cells = _simple_cells(n=5)
        result = cloisonne_layout(cells)
        assert result["cell_count"] == 5


# ---------------------------------------------------------------------------
# Champlevé recess calculator
# ---------------------------------------------------------------------------

class TestChamplveRecess:
    def test_metal_removed_equals_area_times_depth(self):
        recesses = [
            {"area_mm2": 100.0, "depth_mm": 0.5, "colour": "red"},
            {"area_mm2":  60.0, "depth_mm": 0.3, "colour": "blue"},
        ]
        result = champleve_recess(recesses)
        assert result["ok"] is True
        expected = 100.0 * 0.5 + 60.0 * 0.3
        assert result["total_metal_removed_mm3"] == approx(expected)

    def test_enamel_fill_volume_equals_recess_volume(self):
        recesses = [{"area_mm2": 80.0, "depth_mm": 0.4, "colour": "green"}]
        result = champleve_recess(recesses)
        assert result["ok"] is True
        assert result["total_enamel_volume_mm3"] == approx(80.0 * 0.4)
        # Metal removed == enamel fill for a single recess
        assert result["total_metal_removed_mm3"] == approx(result["total_enamel_volume_mm3"])

    def test_enamel_mass_computed_correctly(self):
        recesses = [{"area_mm2": 100.0, "depth_mm": 0.5}]
        result = champleve_recess(recesses)
        vol = 100.0 * 0.5
        expected_mass = (vol / MM3_PER_CM3) * ENAMEL_DENSITY_G_CM3
        assert result["total_enamel_mass_g"] == approx(expected_mass)

    def test_recess_colour_grouping(self):
        recesses = [
            {"area_mm2": 40.0, "depth_mm": 0.3, "colour": "red"},
            {"area_mm2": 60.0, "depth_mm": 0.3, "colour": "red"},
            {"area_mm2": 50.0, "depth_mm": 0.3, "colour": "blue"},
        ]
        result = champleve_recess(recesses)
        assert result["colour_volumes"]["red"] == approx((40.0 + 60.0) * 0.3)
        assert result["colour_volumes"]["blue"] == approx(50.0 * 0.3)

    def test_empty_recesses_fails_gracefully(self):
        result = champleve_recess([])
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Firing schedule
# ---------------------------------------------------------------------------

class TestFiringSchedule:
    def test_more_depth_more_coats(self):
        shallow = firing_schedule(0.2, "medium")
        deep = firing_schedule(1.5, "medium")
        assert deep["coats"] > shallow["coats"]

    def test_coats_equals_ceil_depth_over_coat_depth(self):
        depth = 0.75  # COAT_DEPTH_MM = 0.3 → ceil(0.75/0.3) = 3
        expected_coats = math.ceil(depth / COAT_DEPTH_MM)
        result = firing_schedule(depth, "medium")
        assert result["coats"] == expected_coats

    def test_hard_enamel_higher_kiln_temp_than_soft(self):
        soft = firing_schedule(0.3, "soft")
        hard = firing_schedule(0.3, "hard")
        assert hard["kiln_temp_min_f"] > soft["kiln_temp_min_f"]
        assert hard["kiln_temp_max_f"] > soft["kiln_temp_max_f"]

    def test_counter_enamel_adds_one_firing(self):
        with_counter = firing_schedule(0.3, "medium", counter_enamel_required=True)
        without_counter = firing_schedule(0.3, "medium", counter_enamel_required=False)
        assert with_counter["total_firings"] == without_counter["total_firings"] + 1

    def test_total_time_equals_firings_times_time_per_coat(self):
        result = firing_schedule(0.6, "hard", counter_enamel_required=True)
        assert result["total_time_min"] == approx(
            result["total_firings"] * result["time_per_coat_min"]
        )

    def test_invalid_enamel_type_graceful(self):
        result = firing_schedule(0.3, "ultrahard")
        assert result["ok"] is False
        assert "Unknown enamel_type" in result["reason"]

    def test_kiln_temp_bands_match_constants(self):
        for etype, (lo, hi) in ENAMEL_KILN_TEMP_BANDS.items():
            result = firing_schedule(0.3, etype)
            assert result["ok"] is True
            assert result["kiln_temp_min_f"] == lo
            assert result["kiln_temp_max_f"] == hi


# ---------------------------------------------------------------------------
# Counter-enamel and mass
# ---------------------------------------------------------------------------

class TestEnamelMassWithWastage:
    def test_counter_enamel_doubles_net_mass(self):
        vol = 500.0  # mm³
        without = enamel_mass_with_wastage(vol, counter_enamel_required=False, wastage_pct=0.0)
        with_ce = enamel_mass_with_wastage(vol, counter_enamel_required=True,  wastage_pct=0.0)
        assert with_ce["net_mass_g"] == approx(2.0 * without["net_mass_g"])

    def test_wastage_increases_total_mass(self):
        vol = 400.0
        no_waste = enamel_mass_with_wastage(vol, wastage_pct=0.0)
        with_waste = enamel_mass_with_wastage(vol, wastage_pct=15.0)
        assert with_waste["total_mass_g"] > no_waste["total_mass_g"]

    def test_total_mass_net_plus_wastage(self):
        vol = 300.0
        result = enamel_mass_with_wastage(vol, wastage_pct=20.0, counter_enamel_required=False)
        assert result["total_mass_g"] == approx(result["net_mass_g"] * 1.20)

    def test_counter_enamel_volume_zero_when_not_required(self):
        result = enamel_mass_with_wastage(200.0, counter_enamel_required=False)
        assert result["counter_enamel_volume_mm3"] == 0.0
        assert result["counter_enamel_mass_g"] == 0.0


# ---------------------------------------------------------------------------
# Metal compatibility
# ---------------------------------------------------------------------------

class TestMetalCompatibility:
    def test_fine_silver_compatible_no_firescale(self):
        result = metal_enamel_compatibility("fine_silver")
        assert result["ok"] is True
        assert result["compatible"] is True
        assert result["firescale_risk"] is False

    def test_sterling_firescale_risk_flag(self):
        result = metal_enamel_compatibility("sterling_925")
        assert result["ok"] is True
        assert result["compatible"] is True
        assert result["firescale_risk"] is True

    def test_copper_compatible(self):
        result = metal_enamel_compatibility("copper")
        assert result["ok"] is True
        assert result["compatible"] is True

    def test_titanium_incompatible(self):
        result = metal_enamel_compatibility("titanium")
        assert result["ok"] is False
        assert result["compatible"] is False

    def test_brass_firescale_risk(self):
        result = metal_enamel_compatibility("brass")
        assert result["firescale_risk"] is True


# ---------------------------------------------------------------------------
# Cost estimator
# ---------------------------------------------------------------------------

class TestEnamelCostEstimate:
    def test_cost_decomposes_enamel_plus_labour_plus_markup(self):
        result = enamel_cost_estimate(
            enamel_mass_g=10.0,
            enamel_price_per_g=2.5,
            labour_hours=3.0,
            labour_rate_per_hour=50.0,
            markup_pct=20.0,
        )
        assert result["ok"] is True
        assert result["enamel_cost"] == approx(10.0 * 2.5)
        assert result["labour_cost"] == approx(3.0 * 50.0)
        subtotal = 10.0 * 2.5 + 3.0 * 50.0
        assert result["subtotal"] == approx(subtotal)
        assert result["markup_amount"] == approx(subtotal * 0.20)
        assert result["total_cost"] == approx(subtotal * 1.20)

    def test_zero_markup_total_equals_subtotal(self):
        result = enamel_cost_estimate(5.0, 3.0, markup_pct=0.0)
        assert result["total_cost"] == approx(result["subtotal"])

    def test_negative_mass_fails_gracefully(self):
        result = enamel_cost_estimate(enamel_mass_g=-1.0, enamel_price_per_g=1.0)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# plan_enamel end-to-end
# ---------------------------------------------------------------------------

class TestPlanEnamel:
    def test_cloisonne_end_to_end(self):
        cells = [
            {"perimeter_mm": 20.0, "area_mm2": 100.0, "depth_mm": 0.3, "colour": "red"},
            {"perimeter_mm": 25.0, "area_mm2": 120.0, "depth_mm": 0.3, "colour": "blue"},
        ]
        result = plan_enamel(
            technique="cloisonne",
            metal_key="fine_silver",
            cells=cells,
        )
        assert result["ok"] is True
        assert result["technique"] == "cloisonne"
        assert result["geometry"]["wire_length_mm"] == approx(45.0)
        assert result["firing_schedule"]["ok"] is True
        assert result["mass"]["ok"] is True
        assert result["cost"]["ok"] is True

    def test_champleve_end_to_end(self):
        recesses = [
            {"area_mm2": 80.0, "depth_mm": 0.5, "colour": "green"},
            {"area_mm2": 40.0, "depth_mm": 0.4, "colour": "red"},
        ]
        result = plan_enamel(
            technique="champleve",
            metal_key="copper",
            recesses=recesses,
        )
        assert result["ok"] is True
        assert result["technique"] == "champleve"
        assert result["geometry"]["total_metal_removed_mm3"] == approx(80.0 * 0.5 + 40.0 * 0.4)

    def test_plique_a_jour_succeeds_without_geometry(self):
        result = plan_enamel(technique="plique_a_jour", metal_key="fine_silver")
        assert result["ok"] is True
        assert result["geometry"] is None

    def test_grisaille_succeeds(self):
        result = plan_enamel(technique="grisaille", metal_key="fine_silver")
        assert result["ok"] is True

    def test_basse_taille_succeeds(self):
        result = plan_enamel(technique="basse_taille", metal_key="18k_yellow")
        assert result["ok"] is True

    def test_invalid_technique_graceful(self):
        result = plan_enamel(technique="unknown_technique", metal_key="fine_silver")
        assert result["ok"] is False
        assert isinstance(result["reason"], str)

    def test_incompatible_metal_graceful(self):
        result = plan_enamel(technique="cloisonne", metal_key="titanium")
        assert result["ok"] is False
        assert isinstance(result["reason"], str)

    def test_sterling_includes_firescale_warning(self):
        cells = _simple_cells()
        result = plan_enamel(technique="cloisonne", metal_key="sterling_925", cells=cells)
        assert result["ok"] is True
        assert result["metal_compatibility"]["firescale_risk"] is True


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

class TestPluginRegistration:
    def test_enamel_module_in_tool_modules(self):
        from kerf_cad_core.plugin import _TOOL_MODULES
        assert "kerf_cad_core.jewelry.enamel" in _TOOL_MODULES
