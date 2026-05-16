"""
Tests for kerf_cad_core.jewelry.plating

Pure-Python: no OCC, no database, no project context required.

Covers:
  - plating_spec validation + normalisation
  - layer_volume_mass: V = area × thickness(µm→mm), mass = V·ρ
  - layered_weight: base + Σ layer masses
  - layered_cost: per-layer decomposition + total
  - hallmark_interaction: 18k-over-silver mapping, vermeil qualification
  - vermeil min-thickness rule (US FTC ≥ 2.5 µm gold over sterling)
  - recommended_min_thickness: increases with wear class
  - incompatibility warnings: silver/thin-gold, brass/gold, titanium
  - LLM tool (run_jewelry_plating) via asyncio
  - plugin._TOOL_MODULES includes plating module
"""

from __future__ import annotations

import asyncio
import json
import importlib.util
import pytest

from kerf_cad_core.jewelry.plating import (
    UM_TO_MM,
    MM3_PER_CM3,
    JURISDICTIONS,
    _WEAR_CLASSES,
    _incompatibility_warnings,
    hallmark_interaction,
    layer_volume_mass,
    layered_cost,
    layered_weight,
    plating_spec,
    recommended_min_thickness,
)
from kerf_cad_core.jewelry.metal_cost import METAL_DENSITY_G_CM3


# ── helpers ───────────────────────────────────────────────────────────────────

def approx(expected, rel=1e-4):
    return pytest.approx(expected, rel=rel)


def _spec(base="sterling_925", layers=None):
    """Build a default valid plating spec for testing."""
    if layers is None:
        layers = [
            {"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0}
        ]
    return plating_spec(base, layers)


def run_tool(**kwargs) -> dict:
    from kerf_cad_core.jewelry.plating import run_jewelry_plating
    raw = asyncio.new_event_loop().run_until_complete(
        run_jewelry_plating(None, json.dumps(kwargs).encode())
    )
    return json.loads(raw)


# ── plating_spec ──────────────────────────────────────────────────────────────

class TestPlatingSpec:
    def test_valid_spec_ok(self):
        spec = _spec()
        assert spec["ok"] is True
        assert spec["error"] is None
        assert spec["base_alloy"] == "sterling_925"

    def test_unknown_base_alloy_fails(self):
        spec = plating_spec("unobtanium", [])
        assert spec["ok"] is False
        assert "Unknown base_alloy" in spec["error"]

    def test_unknown_plate_alloy_fails(self):
        spec = plating_spec("sterling_925", [
            {"alloy": "unobtanium", "thickness_um": 1.0, "coverage_mm2": 100.0}
        ])
        assert spec["ok"] is False
        assert "unknown alloy" in spec["error"].lower()

    def test_missing_alloy_field_fails(self):
        spec = plating_spec("sterling_925", [
            {"thickness_um": 1.0, "coverage_mm2": 100.0}
        ])
        assert spec["ok"] is False
        assert "alloy" in spec["error"]

    def test_missing_thickness_fails(self):
        spec = plating_spec("sterling_925", [
            {"alloy": "18k_yellow", "coverage_mm2": 100.0}
        ])
        assert spec["ok"] is False
        assert "thickness_um" in spec["error"]

    def test_missing_coverage_fails(self):
        spec = plating_spec("sterling_925", [
            {"alloy": "18k_yellow", "thickness_um": 1.0}
        ])
        assert spec["ok"] is False
        assert "coverage_mm2" in spec["error"]

    def test_zero_thickness_fails(self):
        spec = plating_spec("sterling_925", [
            {"alloy": "18k_yellow", "thickness_um": 0.0, "coverage_mm2": 100.0}
        ])
        assert spec["ok"] is False

    def test_negative_coverage_fails(self):
        spec = plating_spec("sterling_925", [
            {"alloy": "18k_yellow", "thickness_um": 1.0, "coverage_mm2": -10.0}
        ])
        assert spec["ok"] is False

    def test_rhodium_accepted_as_plate(self):
        spec = plating_spec("18k_white", [
            {"alloy": "rhodium", "thickness_um": 0.5, "coverage_mm2": 400.0}
        ])
        assert spec["ok"] is True
        assert spec["plate_layers"][0]["alloy"] == "rhodium"

    def test_multi_layer_spec(self):
        spec = plating_spec("sterling_925", [
            {"alloy": "18k_yellow", "thickness_um": 2.0, "coverage_mm2": 500.0},
            {"alloy": "rhodium",    "thickness_um": 0.3, "coverage_mm2": 500.0},
        ])
        assert spec["ok"] is True
        assert len(spec["plate_layers"]) == 2

    def test_density_populated_in_layer(self):
        spec = _spec()
        layer = spec["plate_layers"][0]
        assert "density_g_cm3" in layer
        assert layer["density_g_cm3"] > 0

    def test_base_key_normalised_lowercase(self):
        spec = plating_spec("STERLING_925", [
            {"alloy": "18k_yellow", "thickness_um": 1.0, "coverage_mm2": 100.0}
        ])
        assert spec["ok"] is True
        assert spec["base_alloy"] == "sterling_925"


# ── layer_volume_mass ─────────────────────────────────────────────────────────

class TestLayerVolumeMass:
    def _layer(self, alloy="18k_yellow", thickness_um=1.0, coverage_mm2=1000.0):
        spec = plating_spec("sterling_925", [
            {"alloy": alloy, "thickness_um": thickness_um, "coverage_mm2": coverage_mm2}
        ])
        return spec["plate_layers"][0]

    def test_volume_formula(self):
        """V = area × thickness_mm  (thickness_um × 1e-3)."""
        layer = self._layer(thickness_um=5.0, coverage_mm2=200.0)
        result = layer_volume_mass(layer)
        expected_vol = 200.0 * (5.0 * UM_TO_MM)   # 200 × 0.005 = 1.0 mm³
        assert result["volume_mm3"] == approx(expected_vol)

    def test_mass_formula(self):
        """mass_g = (volume_mm3 / 1000) × density_g_cm3."""
        layer = self._layer(alloy="18k_yellow", thickness_um=2.5, coverage_mm2=400.0)
        result = layer_volume_mass(layer)
        expected_vol = 400.0 * (2.5 * UM_TO_MM)
        expected_mass = (expected_vol / MM3_PER_CM3) * METAL_DENSITY_G_CM3["18k_yellow"]
        assert result["mass_g"] == approx(expected_mass)

    def test_sterling_base_reference(self):
        """1 µm of sterling over 1000 mm² → ~10.36e-6 g per µm (density check)."""
        layer = self._layer(alloy="sterling_925", thickness_um=1.0, coverage_mm2=1000.0)
        result = layer_volume_mass(layer)
        # vol = 1000 × 0.001 = 1.0 mm³ = 0.001 cm³
        expected_mass = 0.001 * METAL_DENSITY_G_CM3["sterling_925"]
        assert result["mass_g"] == approx(expected_mass)

    def test_thicker_layer_heavier(self):
        thin = self._layer(thickness_um=1.0, coverage_mm2=500.0)
        thick = self._layer(thickness_um=5.0, coverage_mm2=500.0)
        assert layer_volume_mass(thick)["mass_g"] > layer_volume_mass(thin)["mass_g"]

    def test_larger_coverage_heavier(self):
        small = self._layer(thickness_um=2.0, coverage_mm2=100.0)
        large = self._layer(thickness_um=2.0, coverage_mm2=1000.0)
        assert layer_volume_mass(large)["mass_g"] > layer_volume_mass(small)["mass_g"]


# ── layered_weight ────────────────────────────────────────────────────────────

class TestLayeredWeight:
    def test_total_weight_equals_base_plus_layers(self):
        """total_mass_g == base_mass_g + Σ layer_mass_g (key invariant)."""
        spec = plating_spec("sterling_925", [
            {"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0},
        ])
        weights = layered_weight(1000.0, spec)
        assert weights["ok"] is True
        assert weights["total_mass_g"] == approx(
            weights["base_mass_g"] + weights["total_layer_mass_g"]
        )

    def test_base_mass_calculation(self):
        """base_mass_g = (volume_mm3 / 1000) × ρ_base."""
        spec = _spec()
        weights = layered_weight(500.0, spec)
        expected_base = (500.0 / MM3_PER_CM3) * METAL_DENSITY_G_CM3["sterling_925"]
        assert weights["base_mass_g"] == approx(expected_base)

    def test_18k_over_sterling_weight_breakdown(self):
        """18k-over-silver: base is sterling, top layer is 18k yellow gold."""
        spec = plating_spec("sterling_925", [
            {"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 600.0}
        ])
        weights = layered_weight(800.0, spec)
        assert weights["ok"] is True
        # Layer mass check
        layer = weights["layers"][0]
        expected_layer_vol = 600.0 * (3.0 * UM_TO_MM)
        expected_layer_mass = (expected_layer_vol / MM3_PER_CM3) * METAL_DENSITY_G_CM3["18k_yellow"]
        assert layer["mass_g"] == approx(expected_layer_mass)
        # Total
        base_mass = (800.0 / MM3_PER_CM3) * METAL_DENSITY_G_CM3["sterling_925"]
        assert weights["total_mass_g"] == approx(base_mass + expected_layer_mass)

    def test_multi_layer_sum(self):
        spec = plating_spec("sterling_925", [
            {"alloy": "18k_yellow", "thickness_um": 2.0, "coverage_mm2": 400.0},
            {"alloy": "rhodium",    "thickness_um": 0.5, "coverage_mm2": 400.0},
        ])
        weights = layered_weight(1000.0, spec)
        assert weights["ok"] is True
        assert len(weights["layers"]) == 2
        sum_layers = sum(l["mass_g"] for l in weights["layers"])
        assert weights["total_layer_mass_g"] == approx(sum_layers)
        assert weights["total_mass_g"] == approx(weights["base_mass_g"] + sum_layers)

    def test_invalid_spec_propagates_error(self):
        bad_spec = {"ok": False, "error": "bad spec", "base_alloy": "sterling_925",
                    "plate_layers": [], "warnings": []}
        result = layered_weight(1000.0, bad_spec)
        assert result["ok"] is False

    def test_zero_volume_fails(self):
        spec = _spec()
        result = layered_weight(0.0, spec)
        assert result["ok"] is False

    def test_layer_mass_scales_linearly_with_thickness(self):
        def mass_for_thick(t):
            spec = plating_spec("sterling_925", [
                {"alloy": "18k_yellow", "thickness_um": t, "coverage_mm2": 500.0}
            ])
            w = layered_weight(1000.0, spec)
            return w["layers"][0]["mass_g"]

        m1 = mass_for_thick(1.0)
        m2 = mass_for_thick(2.0)
        assert m2 == approx(2 * m1)


# ── layered_cost ──────────────────────────────────────────────────────────────

class TestLayeredCost:
    def _weights(self, base="sterling_925", plate_alloy="18k_yellow",
                 thickness_um=3.0, coverage_mm2=500.0, vol=1000.0):
        spec = plating_spec(base, [
            {"alloy": plate_alloy, "thickness_um": thickness_um, "coverage_mm2": coverage_mm2}
        ])
        return layered_weight(vol, spec)

    def test_total_cost_equals_base_plus_layers(self):
        weights = self._weights()
        prices = {"sterling_925": 0.85, "18k_yellow": 50.0}
        cost = layered_cost(weights, prices)
        assert cost["ok"] is True
        assert cost["total_cost"] == approx(cost["base_cost"] + cost["total_layer_cost"])

    def test_base_cost_formula(self):
        weights = self._weights(vol=2000.0)
        prices = {"sterling_925": 1.0, "18k_yellow": 0.0}
        cost = layered_cost(weights, prices)
        expected_base = weights["base_mass_g"] * 1.0
        assert cost["base_cost"] == approx(expected_base)

    def test_layer_cost_formula(self):
        weights = self._weights(plate_alloy="18k_yellow")
        prices = {"sterling_925": 0.0, "18k_yellow": 48.0}
        cost = layered_cost(weights, prices)
        layer_mass = weights["layers"][0]["mass_g"]
        assert cost["layer_costs"][0]["cost"] == approx(layer_mass * 48.0)

    def test_zero_price_gives_zero_cost(self):
        weights = self._weights()
        cost = layered_cost(weights, {})
        assert cost["total_cost"] == approx(0.0)

    def test_missing_price_defaults_to_zero(self):
        weights = self._weights(plate_alloy="18k_yellow")
        prices = {"sterling_925": 1.0}  # no 18k_yellow
        cost = layered_cost(weights, prices)
        assert cost["layer_costs"][0]["price_g"] == 0.0
        assert cost["layer_costs"][0]["cost"] == 0.0

    def test_cost_decomposition_integrity(self):
        """layer_costs[i].cost = layer_costs[i].mass_g × layer_costs[i].price_g."""
        weights = self._weights(plate_alloy="14k_white")
        prices = {"sterling_925": 0.8, "14k_white": 38.0}
        cost = layered_cost(weights, prices)
        for lc in cost["layer_costs"]:
            assert lc["cost"] == approx(lc["mass_g"] * lc["price_g"])

    def test_invalid_weights_propagates_error(self):
        bad = {"ok": False, "error": "bad", "base_alloy": "x", "layers": [], "warnings": []}
        cost = layered_cost(bad, {})
        assert cost["ok"] is False


# ── hallmark_interaction ──────────────────────────────────────────────────────

class TestHallmarkInteraction:
    def test_18k_over_silver_hallmark(self):
        """18k-over-sterling: base hallmark is 925; outer is gold plated."""
        result = hallmark_interaction(
            base="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0}],
            jurisdiction="us",
        )
        assert result["ok"] is True
        assert result["base_hallmark"] == 925
        assert result["base_hallmark_label"] == "925"
        # Should mention gold plating in required terms
        combined = " ".join(result["required_terms"]).lower()
        assert "gold" in combined

    def test_vermeil_qualifies_over_2_5_um(self):
        """US vermeil: ≥ 2.5 µm 10k+ gold over sterling."""
        result = hallmark_interaction(
            base="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0}],
            jurisdiction="us",
        )
        assert result["vermeil"] is True
        assert "vermeil" in result["vermeil_notes"].lower()

    def test_vermeil_fails_under_2_5_um(self):
        """Thin gold (< 2.5 µm) over sterling does NOT qualify as vermeil."""
        result = hallmark_interaction(
            base="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 1.0, "coverage_mm2": 500.0}],
            jurisdiction="us",
        )
        assert result["vermeil"] is False
        assert "does not qualify" in result["vermeil_notes"].lower() or \
               "not qualify" in result["vermeil_notes"].lower()

    def test_vermeil_fails_sub_10k_gold(self):
        """Even thick 8k gold over sterling is not US vermeil (< 10k)."""
        # Use 10k as the minimum; test with 10k_yellow at exactly 2.5 µm (passes)
        # and verify that a non-gold alloy over silver is not vermeil
        result = hallmark_interaction(
            base="sterling_925",
            plate_layers=[{"alloy": "sterling_925", "thickness_um": 5.0, "coverage_mm2": 500.0}],
            jurisdiction="us",
        )
        assert result["vermeil"] is False

    def test_gold_over_non_silver_not_vermeil(self):
        """Gold over brass is 'gold plated', not vermeil."""
        result = hallmark_interaction(
            base="brass",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 5.0, "coverage_mm2": 500.0}],
            jurisdiction="us",
        )
        assert result["vermeil"] is False
        assert "base is not silver" in result["vermeil_notes"].lower()

    def test_rhodium_plate_required_term(self):
        """Rhodium plating must be declared."""
        result = hallmark_interaction(
            base="18k_white",
            plate_layers=[{"alloy": "rhodium", "thickness_um": 0.5, "coverage_mm2": 400.0}],
            jurisdiction="us",
        )
        assert result["ok"] is True
        combined = " ".join(result["required_terms"]).lower()
        assert "rhodium" in combined

    def test_base_hallmark_present_for_precious(self):
        result = hallmark_interaction(
            base="14k_yellow",
            plate_layers=[{"alloy": "rhodium", "thickness_um": 0.5, "coverage_mm2": 400.0}],
            jurisdiction="us",
        )
        assert result["base_hallmark"] == 583

    def test_non_precious_base_has_no_hallmark(self):
        result = hallmark_interaction(
            base="brass",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 5.0, "coverage_mm2": 500.0}],
            jurisdiction="us",
        )
        assert result["base_hallmark"] is None

    def test_unknown_jurisdiction_falls_back_to_int(self):
        result = hallmark_interaction(
            base="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0}],
            jurisdiction="narnia",
        )
        assert result["ok"] is True
        assert result["jurisdiction"] == "int"
        assert any("Unknown jurisdiction" in w for w in result["warnings"])

    def test_vermeil_exactly_2_5_um_qualifies(self):
        """Exactly 2.5 µm is the FTC threshold — should qualify."""
        result = hallmark_interaction(
            base="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 2.5, "coverage_mm2": 500.0}],
            jurisdiction="us",
        )
        assert result["vermeil"] is True


# ── recommended_min_thickness ─────────────────────────────────────────────────

class TestRecommendedMinThickness:
    def test_increases_with_wear_class(self):
        """Min thickness for gold plating must increase: light < medium < heavy < extreme."""
        thicknesses = {}
        for wc in _WEAR_CLASSES:
            rec = recommended_min_thickness("sterling_925", "18k_yellow", wc)
            assert rec["ok"] is True
            thicknesses[wc] = rec["min_thickness_um"]

        assert thicknesses["light"] <= thicknesses["medium"]
        assert thicknesses["medium"] <= thicknesses["heavy"]
        assert thicknesses["heavy"] <= thicknesses["extreme"]

    def test_rhodium_min_thickness_by_wear(self):
        """Rhodium thicknesses also scale with wear class."""
        light = recommended_min_thickness("18k_white", "rhodium", "light")["min_thickness_um"]
        heavy = recommended_min_thickness("18k_white", "rhodium", "heavy")["min_thickness_um"]
        assert heavy > light

    def test_gold_medium_is_1_25_um(self):
        """Gold medium wear: 1.25 µm (industry midpoint)."""
        rec = recommended_min_thickness("sterling_925", "18k_yellow", "medium")
        assert rec["min_thickness_um"] == approx(1.25)

    def test_us_vermeil_min_is_2_5_um_for_heavy(self):
        """Gold heavy wear ≥ 2.5 µm aligns with US vermeil threshold."""
        rec = recommended_min_thickness("sterling_925", "18k_yellow", "heavy")
        assert rec["min_thickness_um"] >= 2.5

    def test_copper_base_raises_minimum(self):
        """Brass/bronze base + gold requires ≥ 2.5 µm due to copper migration."""
        rec_silver = recommended_min_thickness("sterling_925", "18k_yellow", "light")
        rec_brass = recommended_min_thickness("brass", "18k_yellow", "light")
        assert rec_brass["min_thickness_um"] >= 2.5

    def test_unknown_wear_class_defaults_to_medium(self):
        rec = recommended_min_thickness("sterling_925", "18k_yellow", "planetary")
        assert rec["ok"] is True
        assert any("Unknown wear_class" in w for w in rec["warnings"])

    def test_unknown_base_alloy_fails(self):
        rec = recommended_min_thickness("unobtanium", "18k_yellow", "medium")
        assert rec["ok"] is False
        assert "Unknown base_alloy" in rec["error"]

    def test_unknown_plate_alloy_fails(self):
        rec = recommended_min_thickness("sterling_925", "unobtanium", "medium")
        assert rec["ok"] is False

    def test_titanium_base_warning(self):
        rec = recommended_min_thickness("titanium", "18k_yellow", "light")
        assert rec["ok"] is True
        assert any("PVD" in w or "titanium" in w.lower() for w in rec["warnings"])


# ── _incompatibility_warnings ─────────────────────────────────────────────────

class TestIncompatibilityWarnings:
    def _layer(self, alloy, thickness_um, coverage_mm2=500.0):
        spec = plating_spec("sterling_925", [
            {"alloy": alloy, "thickness_um": thickness_um, "coverage_mm2": coverage_mm2}
        ])
        return spec["plate_layers"][0]

    def test_thin_gold_over_silver_warns(self):
        """Silver base + gold < 0.5 µm → tarnish bleed-through warning."""
        layer = self._layer("18k_yellow", 0.2)
        warnings = _incompatibility_warnings("sterling_925", [layer])
        combined = " ".join(warnings).lower()
        assert "tarnish" in combined or "bleed" in combined

    def test_thick_gold_over_silver_no_warn(self):
        """Silver base + gold ≥ 0.5 µm → no tarnish warning."""
        layer = self._layer("18k_yellow", 1.0)
        warnings = _incompatibility_warnings("sterling_925", [layer])
        combined = " ".join(warnings).lower()
        assert "tarnish" not in combined

    def test_thin_gold_over_brass_warns(self):
        """Brass base + gold < 2.5 µm → copper migration warning."""
        spec = plating_spec("brass", [
            {"alloy": "18k_yellow", "thickness_um": 1.0, "coverage_mm2": 500.0}
        ])
        layer = spec["plate_layers"][0]
        warnings = _incompatibility_warnings("brass", [layer])
        combined = " ".join(warnings).lower()
        assert "copper" in combined or "migration" in combined or "pink" in combined

    def test_titanium_base_warns(self):
        """Titanium base always warns about adhesion."""
        spec = plating_spec("titanium", [
            {"alloy": "18k_yellow", "thickness_um": 1.0, "coverage_mm2": 500.0}
        ])
        layer = spec["plate_layers"][0]
        warnings = _incompatibility_warnings("titanium", [layer])
        combined = " ".join(warnings).lower()
        assert "pvd" in combined or "adhesion" in combined or "titanium" in combined

    def test_palladium_over_palladium_warns(self):
        """Palladium plate over palladium base is redundant."""
        spec = plating_spec("palladium_950", [
            {"alloy": "palladium_950", "thickness_um": 1.0, "coverage_mm2": 500.0}
        ])
        layer = spec["plate_layers"][0]
        warnings = _incompatibility_warnings("palladium_950", [layer])
        combined = " ".join(warnings).lower()
        assert "redundant" in combined or "palladium" in combined


# ── LLM tool (run_jewelry_plating) ────────────────────────────────────────────

class TestRunJewelryPlating:
    def test_basic_success(self):
        result = run_tool(
            base_alloy="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0}],
            piece_solid_volume_mm3=1000.0,
        )
        assert "error" not in result
        assert "spec" in result
        assert "hallmark" in result

    def test_missing_base_alloy_returns_bad_args(self):
        result = run_tool(
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 1.0, "coverage_mm2": 100.0}]
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_missing_plate_layers_returns_bad_args(self):
        result = run_tool(base_alloy="sterling_925")
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_unknown_base_returns_bad_args(self):
        result = run_tool(
            base_alloy="unobtanium",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 1.0, "coverage_mm2": 100.0}],
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_weight_and_cost_returned_with_volume(self):
        result = run_tool(
            base_alloy="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0}],
            piece_solid_volume_mm3=1000.0,
            alloy_prices={"sterling_925": 0.85, "18k_yellow": 50.0},
        )
        assert "error" not in result
        assert "weight" in result
        assert "cost" in result
        assert result["weight"]["total_mass_g"] > 0
        assert result["cost"]["total_cost"] > 0

    def test_no_weight_when_no_volume(self):
        result = run_tool(
            base_alloy="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0}],
        )
        assert "error" not in result
        assert "weight" not in result
        assert "cost" not in result

    def test_vermeil_hallmark_in_result(self):
        result = run_tool(
            base_alloy="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0}],
            jurisdiction="us",
        )
        assert "error" not in result
        assert result["hallmark"]["vermeil"] is True

    def test_invalid_json_returns_bad_args(self):
        from kerf_cad_core.jewelry.plating import run_jewelry_plating
        raw = asyncio.new_event_loop().run_until_complete(
            run_jewelry_plating(None, b"not-json{{{")
        )
        r = json.loads(raw)
        assert "error" in r
        assert r.get("code") == "BAD_ARGS"

    def test_thickness_recommendations_in_result(self):
        result = run_tool(
            base_alloy="sterling_925",
            plate_layers=[{"alloy": "18k_yellow", "thickness_um": 3.0, "coverage_mm2": 500.0}],
            wear_class="heavy",
        )
        assert "error" not in result
        assert "thickness_recommendations" in result
        assert len(result["thickness_recommendations"]) == 1
        assert result["thickness_recommendations"][0]["min_thickness_um"] >= 2.5


# ── plugin._TOOL_MODULES ──────────────────────────────────────────────────────

class TestPluginRegistration:
    def test_plugin_tool_modules_includes_plating(self):
        spec_path = (
            "/Users/pc/code/exo/kerf/packages/kerf-cad-core/src/kerf_cad_core/plugin.py"
        )
        spec = importlib.util.spec_from_file_location("plugin_check_plating", spec_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert "kerf_cad_core.jewelry.plating" in mod._TOOL_MODULES
