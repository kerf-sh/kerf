"""
Tests for ISO 14040/44 multi-phase LCA extensions:
  - phases.py       (use_phase_impact, transport_impact, eol_impact, lifecycle_summary)
  - impact_categories.py (multi_impact, get_characterisation_factors)
  - functional_unit.py   (FunctionalUnit, normalise_results, compare_alternatives)
  - uncertainty.py       (monte_carlo_uncertainty, impact_uncertainty_bounds)
  - tools/lifecycle_phases.py  (LLM tool)
  - tools/multi_impact.py      (LLM tool)

Worked example: 1-kg aluminium vs 1-kg steel bracket — confirming that
transport and use phases can shift the comparison when aluminium's lighter
weight or lower operational energy matters.
"""

from __future__ import annotations

import asyncio
import json
import math
import pytest

# ---------------------------------------------------------------------------
# Phase calculators
# ---------------------------------------------------------------------------

from kerf_lca.phases import (
    use_phase_impact,
    transport_impact,
    eol_impact,
    lifecycle_summary,
    GRID_FACTORS,
    TRANSPORT_FACTORS,
)


class TestUsePhasImpact:
    def test_basic_world_grid(self):
        result = use_phase_impact("motor", lifetime_years=10, annual_energy_kWh=100)
        expected = 100 * 10 * GRID_FACTORS["WORLD"]
        assert math.isclose(result.gwp_kg_co2_eq, expected, rel_tol=1e-9)
        assert result.phase == "use"

    def test_region_us(self):
        result = use_phase_impact("pump", lifetime_years=5, annual_energy_kWh=200, region="US")
        expected = 200 * 5 * GRID_FACTORS["US"]
        assert math.isclose(result.gwp_kg_co2_eq, expected, rel_tol=1e-9)
        assert result.metadata["region"] == "US"

    def test_region_za(self):
        result = use_phase_impact("fan", lifetime_years=1, annual_energy_kWh=1, region="ZA")
        assert math.isclose(result.gwp_kg_co2_eq, GRID_FACTORS["ZA"], rel_tol=1e-9)

    def test_override_grid_factor(self):
        custom_ef = 0.250
        result = use_phase_impact("device", lifetime_years=2, annual_energy_kWh=50,
                                  grid_emission_factor_kgCO2_per_kWh=custom_ef)
        assert math.isclose(result.gwp_kg_co2_eq, 50 * 2 * custom_ef, rel_tol=1e-9)
        assert result.metadata["region"] == "custom"

    def test_unknown_region_falls_back_to_world(self):
        result = use_phase_impact("x", lifetime_years=1, annual_energy_kWh=1, region="XX")
        assert math.isclose(result.gwp_kg_co2_eq, GRID_FACTORS["WORLD"], rel_tol=1e-9)

    def test_zero_energy(self):
        result = use_phase_impact("passive", lifetime_years=50, annual_energy_kWh=0)
        assert result.gwp_kg_co2_eq == 0.0

    def test_metadata_fields(self):
        result = use_phase_impact("x", lifetime_years=10, annual_energy_kWh=100)
        assert "total_energy_kWh" in result.metadata
        assert result.metadata["total_energy_kWh"] == 1000.0


class TestTransportImpact:
    def test_truck(self):
        result = transport_impact(mass_kg=1000, distance_km=100, mode="truck")
        # 1 tonne × 100 km × 0.10 = 10 kg CO₂
        assert math.isclose(result.gwp_kg_co2_eq, 10.0, rel_tol=1e-9)

    def test_rail(self):
        result = transport_impact(mass_kg=1000, distance_km=1000, mode="rail")
        # 1 tonne × 1000 km × 0.030 = 30 kg CO₂
        assert math.isclose(result.gwp_kg_co2_eq, 30.0, rel_tol=1e-9)

    def test_sea(self):
        result = transport_impact(mass_kg=10_000, distance_km=20_000, mode="sea")
        # 10 t × 20000 km × 0.015 = 3000
        assert math.isclose(result.gwp_kg_co2_eq, 3000.0, rel_tol=1e-9)

    def test_air_highest(self):
        # Air should give highest impact per tonne-km
        truck = transport_impact(1000, 1000, "truck").gwp_kg_co2_eq
        air = transport_impact(1000, 1000, "air").gwp_kg_co2_eq
        assert air > truck

    def test_all_modes_covered(self):
        for mode in TRANSPORT_FACTORS:
            r = transport_impact(mass_kg=100, distance_km=100, mode=mode)
            assert r.gwp_kg_co2_eq >= 0

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown transport mode"):
            transport_impact(100, 100, "horse")

    def test_phase_label(self):
        assert transport_impact(1, 1, "truck").phase == "transport"


class TestEoLImpact:
    def test_landfill_positive(self):
        result = eol_impact("bracket", mass_kg=1.0, scenario="landfill")
        assert result.gwp_kg_co2_eq > 0
        assert result.phase == "end_of_life"

    def test_incinerate_with_credit(self):
        result = eol_impact("plastic", mass_kg=1.0, scenario="incinerate", grid_region="EU")
        # Should be lower than landfill due to energy recovery credit
        landfill = eol_impact("plastic", mass_kg=1.0, scenario="landfill").gwp_kg_co2_eq
        assert result.gwp_kg_co2_eq < landfill

    def test_recycle_credit_reduces_impact(self):
        # With high gwp_factor, recycle should produce negative impact (net credit)
        result = eol_impact("aluminium", mass_kg=1.0, scenario="recycle",
                            material_gwp_factor=9.16, recycle_allocation=0.5)
        # Credit = 9.16 * 1.0 * 0.5 = 4.58; process = 0.02 → net = 0.02 - 4.58 = -4.56
        assert result.gwp_kg_co2_eq < 0

    def test_cutoff_method_no_credit(self):
        # allocation=0 → cut-off; credit = 0; only process CO₂
        result = eol_impact("aluminium", mass_kg=1.0, scenario="recycle",
                            material_gwp_factor=9.16, recycle_allocation=0.0)
        assert result.gwp_kg_co2_eq >= 0  # only process CO₂, no credit

    def test_invalid_scenario_raises(self):
        with pytest.raises(ValueError, match="Unknown EoL scenario"):
            eol_impact("x", mass_kg=1.0, scenario="compost")

    def test_mass_scales_linearly(self):
        r1 = eol_impact("x", mass_kg=1.0, scenario="landfill").gwp_kg_co2_eq
        r2 = eol_impact("x", mass_kg=2.0, scenario="landfill").gwp_kg_co2_eq
        assert math.isclose(r2, 2 * r1, rel_tol=1e-9)


class TestLifecycleSummary:
    def test_all_phases(self):
        summary = lifecycle_summary(
            "bracket",
            cradle_to_gate_gwp=9.16,
            use_args={"lifetime_years": 10, "annual_energy_kWh": 50, "region": "EU"},
            transport_args={"mass_kg": 1.0, "distance_km": 500, "mode": "truck"},
            eol_args={"mass_kg": 1.0, "scenario": "recycle",
                      "material_gwp_factor": 9.16, "recycle_allocation": 0.5},
            functional_unit="1 kg aluminium bracket",
        )
        assert len(summary.phases) == 4
        assert summary.total_gwp_kg_co2_eq != 0
        assert summary.product == "bracket"
        assert not summary.warnings

    def test_partial_phases(self):
        summary = lifecycle_summary("widget", cradle_to_gate_gwp=1.80,
                                    transport_args={"mass_kg": 1.0, "distance_km": 100, "mode": "rail"})
        assert len(summary.phases) == 2
        expected = 1.80 + transport_impact(1.0, 100, "rail").gwp_kg_co2_eq
        assert math.isclose(summary.total_gwp_kg_co2_eq, expected, rel_tol=1e-9)

    def test_to_dict_serialisable(self):
        summary = lifecycle_summary("p", cradle_to_gate_gwp=5.0)
        d = summary.to_dict()
        s = json.dumps(d)
        back = json.loads(s)
        assert back["total_gwp_kg_co2_eq"] == pytest.approx(5.0)

    def test_aluminium_vs_steel_use_phase_comparison(self):
        """
        Worked example: 1-kg Al part vs 1-kg steel part.

        Cradle-to-gate: Al (9.16) >> steel (1.80).
        After adding 20-year use-phase (EU grid, same energy) and truck transport,
        the ratio compresses — Al's higher embodied carbon does NOT flip,
        but transport impact (same mass→same transport) stays equal.
        """
        al_c2g = 9.16   # kg CO₂-eq
        st_c2g = 1.80

        # Same use-phase energy (hypothetical: same device power draw)
        use_kw = {"lifetime_years": 20, "annual_energy_kWh": 100, "region": "EU"}
        transport_kw = {"mass_kg": 1.0, "distance_km": 1000, "mode": "truck"}

        al_summary = lifecycle_summary(
            "aluminium_bracket", cradle_to_gate_gwp=al_c2g,
            use_args=use_kw, transport_args=transport_kw,
        )
        st_summary = lifecycle_summary(
            "steel_bracket", cradle_to_gate_gwp=st_c2g,
            use_args=use_kw, transport_args=transport_kw,
        )

        # Aluminium still worse (same use + transport phases)
        assert al_summary.total_gwp_kg_co2_eq > st_summary.total_gwp_kg_co2_eq

        # Use phase dominates for both (20 yr × 100 kWh × 0.233 = 466 kg CO₂)
        use_gwp = use_phase_impact("x", **use_kw).gwp_kg_co2_eq
        assert use_gwp > al_c2g  # use > embodied for both materials

        # Transport equal for same mass
        al_transport = next(p for p in al_summary.phases if p.phase == "transport")
        st_transport = next(p for p in st_summary.phases if p.phase == "transport")
        assert math.isclose(al_transport.gwp_kg_co2_eq, st_transport.gwp_kg_co2_eq, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Impact categories
# ---------------------------------------------------------------------------

from kerf_lca.impact_categories import (
    multi_impact,
    get_characterisation_factors,
    list_characterised_materials,
    IMPACT_UNITS,
)


class TestImpactCategories:
    def test_all_units_defined(self):
        expected = {"gwp100", "ap", "ep", "htp", "water", "pm25"}
        assert set(IMPACT_UNITS.keys()) == expected

    def test_characterisation_factors_aluminium(self):
        cf = get_characterisation_factors("aluminium_primary")
        assert cf["gwp100"] == pytest.approx(9.16)
        assert cf["ap"] > 0
        assert cf["water"] > 0

    def test_unknown_material_returns_zeros(self):
        cf = get_characterisation_factors("unobtainium_xyz")
        assert all(v == 0.0 for v in cf.values())

    def test_multi_impact_single_material(self):
        result = multi_impact([{"material_id": "steel_general", "mass_kg": 2.0}])
        assert result["impacts"]["gwp100"] == pytest.approx(1.80 * 2, rel=1e-6)
        assert result["impacts"]["ap"] > 0

    def test_multi_impact_two_materials(self):
        result = multi_impact([
            {"material_id": "aluminium_primary", "mass_kg": 1.0},
            {"material_id": "steel_general", "mass_kg": 1.0},
        ])
        al_cf = get_characterisation_factors("aluminium_primary")
        st_cf = get_characterisation_factors("steel_general")
        expected_gwp = al_cf["gwp100"] * 1.0 + st_cf["gwp100"] * 1.0
        assert result["impacts"]["gwp100"] == pytest.approx(expected_gwp, rel=1e-6)

    def test_multi_impact_unknown_warns(self):
        result = multi_impact([
            {"material_id": "unknown_xyz", "mass_kg": 1.0},
            {"material_id": "steel_general", "mass_kg": 1.0},
        ])
        assert any("unknown_xyz" in w for w in result["warnings"])
        # Known material still counted
        assert result["impacts"]["gwp100"] > 0

    def test_multi_impact_empty(self):
        result = multi_impact([])
        assert all(v == 0.0 for v in result["impacts"].values())

    def test_list_characterised_materials(self):
        mats = list_characterised_materials()
        assert "aluminium_primary" in mats
        assert "steel_general" in mats
        assert len(mats) >= 10

    def test_aluminium_higher_gwp_than_steel(self):
        al = get_characterisation_factors("aluminium_primary")["gwp100"]
        st = get_characterisation_factors("steel_general")["gwp100"]
        assert al > st


# ---------------------------------------------------------------------------
# Functional unit
# ---------------------------------------------------------------------------

from kerf_lca.functional_unit import (
    FunctionalUnit,
    normalise_results,
    compare_alternatives,
)


class TestFunctionalUnit:
    def test_basic_normalise(self):
        fu = FunctionalUnit("bracket", quantity=1.0, unit="kg", reference_flow=2.0)
        # 1 FU / 2 kg reference → scale = 0.5
        result = fu.normalise({"gwp100": 20.0, "ap": 4.0})
        assert result["gwp100"] == pytest.approx(10.0)
        assert result["ap"] == pytest.approx(2.0)

    def test_scale_factor(self):
        fu = FunctionalUnit("x", quantity=5.0, unit="m²", reference_flow=10.0)
        assert fu.scale_factor == pytest.approx(0.5)

    def test_identity_normalise(self):
        fu = FunctionalUnit("x", quantity=1.0, unit="piece", reference_flow=1.0)
        impacts = {"gwp100": 9.16, "ap": 0.04}
        assert fu.normalise(impacts) == pytest.approx(impacts)

    def test_invalid_quantity_raises(self):
        with pytest.raises(ValueError):
            FunctionalUnit("x", quantity=0, unit="kg", reference_flow=1.0)

    def test_invalid_reference_flow_raises(self):
        with pytest.raises(ValueError):
            FunctionalUnit("x", quantity=1.0, unit="kg", reference_flow=-1.0)

    def test_to_dict(self):
        fu = FunctionalUnit("y", quantity=2.0, unit="m", reference_flow=4.0, notes="test")
        d = fu.to_dict()
        assert d["scale_factor"] == pytest.approx(0.5)
        assert "notes" in d

    def test_normalise_results_helper(self):
        fu = FunctionalUnit("z", quantity=1.0, unit="piece", reference_flow=1.0)
        r = normalise_results({"gwp100": 5.0}, fu)
        assert r["gwp100"] == pytest.approx(5.0)

    def test_compare_alternatives(self):
        fu = FunctionalUnit("bracket", quantity=1.0, unit="kg", reference_flow=1.0)
        alts = [
            {"name": "aluminium", "results": {"gwp100": 9.16}, "functional_unit": fu},
            {"name": "steel", "results": {"gwp100": 1.80}, "functional_unit": fu},
        ]
        ranked = compare_alternatives(alts, "gwp100")
        assert ranked[0]["name"] == "steel"   # lower impact = rank 1
        assert ranked[1]["name"] == "aluminium"
        assert ranked[0]["rank"] == 1

    def test_compare_alternatives_no_fu(self):
        alts = [
            {"name": "A", "results": {"gwp100": 10.0}},
            {"name": "B", "results": {"gwp100": 2.0}},
        ]
        ranked = compare_alternatives(alts, "gwp100")
        assert ranked[0]["name"] == "B"


# ---------------------------------------------------------------------------
# Uncertainty
# ---------------------------------------------------------------------------

from kerf_lca.uncertainty import (
    monte_carlo_uncertainty,
    impact_uncertainty_bounds,
    lognormal_params,
    gsd2_for_category,
)


class TestUncertainty:
    def test_lognormal_params_mean_preserved(self):
        mean = 9.16
        gsd2 = 1.05
        mu, sigma = lognormal_params(mean, gsd2)
        # E[lognormal] = exp(mu + sigma²/2) should equal mean
        recovered = math.exp(mu + 0.5 * sigma ** 2)
        assert recovered == pytest.approx(mean, rel=1e-6)

    def test_gsd2_for_known_category(self):
        assert gsd2_for_category("gwp100") == pytest.approx(1.05)
        assert gsd2_for_category("htp") == pytest.approx(2.00)

    def test_gsd2_for_unknown_returns_default(self):
        assert gsd2_for_category("unknown_category") == pytest.approx(1.50)

    def test_impact_uncertainty_bounds_structure(self):
        bounds = impact_uncertainty_bounds(9.16, "gwp100")
        assert "mean" in bounds
        assert "ci_low" in bounds
        assert "ci_high" in bounds
        assert bounds["ci_low"] <= bounds["mean"] <= bounds["ci_high"]

    def test_impact_uncertainty_bounds_zero(self):
        bounds = impact_uncertainty_bounds(0.0, "gwp100")
        assert bounds["ci_low"] == 0.0
        assert bounds["ci_high"] == 0.0

    def test_monte_carlo_basic(self):
        def model(a, b):
            return a * b

        result = monte_carlo_uncertainty(
            model,
            distributions={
                "a": {"mean": 9.16, "gsd2": 1.05},
                "b": {"mean": 1.0, "gsd2": 1.10},
            },
            n_samples=5000,
            seed=42,
        )
        assert "mean" in result
        assert "ci_low" in result
        assert "ci_high" in result
        assert result["ci_low"] <= result["mean"] <= result["ci_high"]
        # Mean should be near 9.16 × 1.0
        assert result["mean"] == pytest.approx(9.16, rel=0.05)

    def test_monte_carlo_returns_90ci_by_default(self):
        def model(x):
            return x

        result = monte_carlo_uncertainty(
            model,
            distributions={"x": {"mean": 1.0, "gsd2": 1.20}},
            n_samples=10_000,
        )
        assert result["ci_level"] == pytest.approx(0.90)
        assert result["n_samples"] == 10_000

    def test_monte_carlo_deterministic_gsd1(self):
        """GSD2 ≤ 1.0 should give all samples equal to mean."""
        def model(x):
            return x

        result = monte_carlo_uncertainty(
            model,
            distributions={"x": {"mean": 5.0, "gsd2": 1.0}},
            n_samples=1000,
        )
        assert result["mean"] == pytest.approx(5.0, rel=1e-9)
        assert result["std"] == pytest.approx(0.0, abs=1e-9)

    def test_monte_carlo_wider_with_higher_gsd2(self):
        """Higher GSD2 should produce a wider CI."""
        def model(x):
            return x

        narrow = monte_carlo_uncertainty(
            model, {"x": {"mean": 10.0, "gsd2": 1.05}}, n_samples=10_000, seed=42
        )
        wide = monte_carlo_uncertainty(
            model, {"x": {"mean": 10.0, "gsd2": 2.00}}, n_samples=10_000, seed=42
        )
        narrow_range = narrow["ci_high"] - narrow["ci_low"]
        wide_range = wide["ci_high"] - wide["ci_low"]
        assert wide_range > narrow_range


# ---------------------------------------------------------------------------
# LLM tools
# ---------------------------------------------------------------------------

from kerf_lca.tools.lifecycle_phases import lifecycle_phases_spec, run_lifecycle_phases
from kerf_lca.tools.multi_impact import multi_impact_spec, run_multi_impact


class _FakeCtx:
    pool = None
    project_id = None
    user_id = None
    storage = None
    http_client = None


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestLifecyclePhasesTool:
    def test_spec_name(self):
        assert lifecycle_phases_spec.name == "lifecycle_phases"

    def test_full_lifecycle(self):
        args = json.dumps({
            "product": "aluminium bracket",
            "cradle_to_gate_gwp": 9.16,
            "use_phase": {"lifetime_years": 10, "annual_energy_kWh": 100, "region": "US"},
            "transport": {"mass_kg": 1.0, "distance_km": 500, "mode": "truck"},
            "eol": {"mass_kg": 1.0, "scenario": "recycle",
                    "material_gwp_factor": 9.16, "recycle_allocation": 0.5},
        }).encode()
        raw = _run(run_lifecycle_phases(_FakeCtx(), args))
        d = json.loads(raw)
        assert "error" not in d
        assert len(d["phases"]) == 4
        assert d["total_gwp_kg_co2_eq"] != 0

    def test_missing_product_returns_error(self):
        args = json.dumps({"cradle_to_gate_gwp": 9.16}).encode()
        raw = _run(run_lifecycle_phases(_FakeCtx(), args))
        d = json.loads(raw)
        assert d.get("code") == "BAD_ARGS"

    def test_bad_json(self):
        raw = _run(run_lifecycle_phases(_FakeCtx(), b"not-json"))
        d = json.loads(raw)
        assert d.get("code") == "BAD_ARGS"

    def test_cradle_only(self):
        args = json.dumps({"product": "widget", "cradle_to_gate_gwp": 5.0}).encode()
        raw = _run(run_lifecycle_phases(_FakeCtx(), args))
        d = json.loads(raw)
        assert d["total_gwp_kg_co2_eq"] == pytest.approx(5.0)


class TestMultiImpactTool:
    def test_spec_name(self):
        assert multi_impact_spec.name == "multi_impact"

    def test_basic(self):
        args = json.dumps({
            "product_breakdown": [
                {"material_id": "aluminium_primary", "mass_kg": 1.0},
                {"material_id": "steel_general", "mass_kg": 2.0},
            ]
        }).encode()
        raw = _run(run_multi_impact(_FakeCtx(), args))
        d = json.loads(raw)
        assert "error" not in d
        assert d["impacts"]["gwp100"] == pytest.approx(9.16 + 1.80 * 2, rel=1e-6)

    def test_not_array_returns_error(self):
        args = json.dumps({"product_breakdown": "bad"}).encode()
        raw = _run(run_multi_impact(_FakeCtx(), args))
        d = json.loads(raw)
        assert d.get("code") == "BAD_ARGS"

    def test_bad_json(self):
        raw = _run(run_multi_impact(_FakeCtx(), b"{bad"))
        d = json.loads(raw)
        assert d.get("code") == "BAD_ARGS"
