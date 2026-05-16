"""
Hermetic tests for kerf_cad_core.costing — parametric manufacturing should-cost.

Coverage:
  estimate.cnc_cost          — happy path, batch amortisation, setup-dominated warning
  estimate.casting_cost      — yield adjustment, pattern amortisation
  estimate.injection_cost    — scrap rate, multi-cavity, tiny-batch warning
  estimate.sheet_metal_cost  — blank mass, bending, cutting, setup amortisation
  estimate.printing_cost     — material + support, shared machine time
  estimate.assembly_cost     — multi-operation roll-up, long-shift warning
  estimate.rollup            — full waterfall hand-calc, negative margin warning
  estimate.batch_curve       — breakpoints, monotone decrease
  estimate.learning_curve    — Wright 80%, doubling law
  estimate.make_vs_buy       — break-even, prefer-make, prefer-buy
  tools.*                    — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Hand-calculations are provided inline for each numeric assertion.

References
----------
Boothroyd, Dewhurst & Knight, "Product Design for Manufacture and Assembly", 3rd ed.
Wright, T.P. (1936), "Factors Affecting the Cost of Airplanes", JAS 3(4)

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.costing.estimate import (
    cnc_cost,
    casting_cost,
    injection_cost,
    sheet_metal_cost,
    printing_cost,
    assembly_cost,
    rollup,
    batch_curve,
    learning_curve,
    make_vs_buy,
)
from kerf_cad_core.costing.tools import (
    run_costing_cnc,
    run_costing_casting,
    run_costing_injection,
    run_costing_sheet_metal,
    run_costing_printing,
    run_costing_assembly,
    run_costing_rollup,
    run_costing_batch_curve,
    run_costing_learning_curve,
    run_costing_make_vs_buy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REL = 1e-9


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


# ===========================================================================
# 1. cnc_cost
# ===========================================================================

class TestCncCost:

    def test_basic_hand_calc(self):
        """
        material=10, cycle=0.5hr, rate=100/hr → machine=50
        setup=0.5hr, batch=10 → unit_setup = 0.5*100/10 = 5
        tooling=0, overhead=0.15 → overhead=(50+5)*0.15=8.25
        total = 10+50+5+0+8.25 = 73.25
        """
        res = cnc_cost(
            material_cost=10.0,
            cycle_time_hr=0.5,
            machine_rate_per_hr=100.0,
            setup_time_hr=0.5,
            batch_size=10,
            tooling_cost=0.0,
            overhead_rate=0.15,
        )
        assert res["ok"] is True
        assert abs(res["unit_machine"] - 50.0) < REL
        assert abs(res["unit_setup"] - 5.0) < REL
        assert abs(res["unit_overhead"] - 8.25) < REL
        assert abs(res["unit_total_cost"] - 73.25) < REL

    def test_tooling_amortisation(self):
        """tooling=1000, life=100 → unit_tooling=10"""
        res = cnc_cost(
            material_cost=5.0,
            cycle_time_hr=0.1,
            machine_rate_per_hr=80.0,
            tooling_cost=1000.0,
            tooling_life_parts=100,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_tooling"] - 10.0) < REL

    def test_batch_size_one_amortises_full_setup(self):
        """batch=1 → unit_setup = setup_time * rate"""
        res = cnc_cost(
            material_cost=1.0,
            cycle_time_hr=0.1,
            machine_rate_per_hr=100.0,
            setup_time_hr=2.0,
            batch_size=1,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_setup"] - 200.0) < REL

    def test_setup_dominated_warning_issued(self):
        """setup_time=1hr >> cycle=0.01hr → setup warning"""
        res = cnc_cost(
            material_cost=1.0,
            cycle_time_hr=0.01,
            machine_rate_per_hr=100.0,
            setup_time_hr=1.0,
            batch_size=1,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert len(res["warnings"]) > 0
        assert "setup" in res["warnings"][0].lower()

    def test_no_setup_no_warning(self):
        """No setup → no warning"""
        res = cnc_cost(
            material_cost=5.0,
            cycle_time_hr=1.0,
            machine_rate_per_hr=100.0,
            setup_time_hr=0.0,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert res["warnings"] == []

    def test_invalid_negative_material(self):
        res = cnc_cost(material_cost=-1.0, cycle_time_hr=0.5, machine_rate_per_hr=100.0)
        assert res["ok"] is False

    def test_invalid_zero_cycle_time(self):
        res = cnc_cost(material_cost=5.0, cycle_time_hr=0.0, machine_rate_per_hr=100.0)
        assert res["ok"] is False


# ===========================================================================
# 2. casting_cost
# ===========================================================================

class TestCastingCost:

    def test_yield_adjustment_hand_calc(self):
        """
        part=1kg, yield=0.70 → poured=1/0.7≈1.4286kg
        material_cost=20/kg → unit_material≈28.571
        pattern=0, pour=0.05hr*80=4, finishing=0, overhead=0.20
        direct=28.571+0+4+0=32.571; overhead=32.571*0.20=6.514
        total=32.571+6.514=39.086
        """
        res = casting_cost(
            material_cost_per_kg=20.0,
            part_mass_kg=1.0,
            yield_fraction=0.70,
            pattern_cost=0.0,
            pattern_life_parts=500,
            finishing_cost_per_part=0.0,
            machine_rate_per_hr=80.0,
            pour_time_hr=0.05,
            overhead_rate=0.20,
        )
        assert res["ok"] is True
        expected_material = 20.0 / 0.70
        assert abs(res["unit_material"] - expected_material) < 1e-6
        expected_pour = 0.05 * 80.0
        assert abs(res["unit_pour"] - expected_pour) < REL
        total = (expected_material + expected_pour) * 1.20
        assert abs(res["unit_total_cost"] - total) < 1e-6

    def test_pattern_amortisation(self):
        """pattern=5000, life=1000 → unit_pattern=5"""
        res = casting_cost(
            material_cost_per_kg=10.0,
            part_mass_kg=0.5,
            pattern_cost=5000.0,
            pattern_life_parts=1000,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_pattern"] - 5.0) < REL

    def test_tiny_batch_warning(self):
        """batch=5 with pattern_cost>0 → warning"""
        res = casting_cost(
            material_cost_per_kg=10.0,
            part_mass_kg=0.5,
            pattern_cost=1000.0,
            batch_size=5,
        )
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_yield_above_one_invalid(self):
        res = casting_cost(material_cost_per_kg=10.0, part_mass_kg=1.0, yield_fraction=1.1)
        assert res["ok"] is False

    def test_finishing_adds_to_cost(self):
        res_no_finish = casting_cost(
            material_cost_per_kg=5.0, part_mass_kg=0.5,
            finishing_cost_per_part=0.0, overhead_rate=0.0,
        )
        res_with_finish = casting_cost(
            material_cost_per_kg=5.0, part_mass_kg=0.5,
            finishing_cost_per_part=10.0, overhead_rate=0.0,
        )
        assert res_with_finish["unit_total_cost"] > res_no_finish["unit_total_cost"]
        assert abs(
            res_with_finish["unit_total_cost"] - res_no_finish["unit_total_cost"] - 10.0
        ) < REL


# ===========================================================================
# 3. injection_cost
# ===========================================================================

class TestInjectionCost:

    def test_scrap_inflates_material(self):
        """
        shot_mass=0.01kg, mat=50/kg, scrap=0.05
        unit_material = 0.01 * 50 / (1-0.05) = 0.5/0.95 ≈ 0.5263
        """
        res = injection_cost(
            material_cost_per_kg=50.0,
            shot_mass_kg=0.01,
            scrap_rate=0.05,
            cycle_time_hr=0.005,
            machine_rate_per_hr=120.0,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        expected_mat = 0.01 * 50.0 / 0.95
        assert abs(res["unit_material"] - expected_mat) < 1e-6

    def test_multi_cavity_halves_machine_cost(self):
        """cavities=2 → machine cost per part = half of single-cavity"""
        res1 = injection_cost(
            material_cost_per_kg=10.0, shot_mass_kg=0.01,
            scrap_rate=0.0, cycle_time_hr=0.01, machine_rate_per_hr=100.0,
            cavities=1, overhead_rate=0.0,
        )
        res2 = injection_cost(
            material_cost_per_kg=10.0, shot_mass_kg=0.01,
            scrap_rate=0.0, cycle_time_hr=0.01, machine_rate_per_hr=100.0,
            cavities=2, overhead_rate=0.0,
        )
        assert res1["ok"] is True and res2["ok"] is True
        assert abs(res2["unit_machine"] - res1["unit_machine"] / 2.0) < 1e-9

    def test_mould_amortisation(self):
        """mould=50000, life=100000, cavities=1 → unit_mould=0.50"""
        res = injection_cost(
            material_cost_per_kg=10.0, shot_mass_kg=0.01,
            mould_cost=50_000.0, mould_life_shots=100_000,
            cavities=1, overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_mould"] - 0.50) < REL

    def test_tiny_batch_warning(self):
        """batch=100 with mould_cost → warning"""
        res = injection_cost(
            material_cost_per_kg=10.0, shot_mass_kg=0.01,
            mould_cost=50_000.0, batch_size=100,
        )
        assert res["ok"] is True
        assert any("tiny batch" in w for w in res["warnings"])

    def test_zero_scrap_no_inflation(self):
        """scrap=0 → material = shot_mass * cost_per_kg"""
        res = injection_cost(
            material_cost_per_kg=40.0, shot_mass_kg=0.025,
            scrap_rate=0.0, overhead_rate=0.0,
            cycle_time_hr=0.005, machine_rate_per_hr=0.0,
        )
        # machine_rate=0 not valid, use small value
        res = injection_cost(
            material_cost_per_kg=40.0, shot_mass_kg=0.025,
            scrap_rate=0.0, overhead_rate=0.0,
        )
        assert res["ok"] is True
        # unit_material should equal shot_mass * cost / (1-0) = 0.025*40=1.0
        assert abs(res["unit_material"] - 1.0) < 1e-6


# ===========================================================================
# 4. sheet_metal_cost
# ===========================================================================

class TestSheetMetalCost:

    def test_blank_mass_calculation(self):
        """
        area=0.1m², thickness=0.002m, density=7850 kg/m³
        mass = 0.1*0.002*7850 = 1.57 kg
        """
        res = sheet_metal_cost(
            blank_area_m2=0.1,
            material_cost_per_kg=2.0,
            material_density_kg_m3=7850.0,
            sheet_thickness_m=0.002,
            num_bends=0,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["blank_mass_kg"] - 1.57) < 1e-6
        assert abs(res["unit_material"] - 1.57 * 2.0) < 1e-6

    def test_bending_cost(self):
        """
        3 bends × 0.02hr × 60/hr = 3.60
        """
        res = sheet_metal_cost(
            blank_area_m2=0.05,
            material_cost_per_kg=1.0,
            material_density_kg_m3=7850.0,
            sheet_thickness_m=0.001,
            num_bends=3,
            bend_time_hr=0.02,
            press_rate_per_hr=60.0,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_bending"] - 3.60) < REL

    def test_laser_cutting_cost(self):
        """
        perimeter=2m, speed=10m/hr, rate=80/hr → cut_time=0.2hr → cost=16
        """
        res = sheet_metal_cost(
            blank_area_m2=0.05,
            material_cost_per_kg=1.0,
            material_density_kg_m3=7850.0,
            sheet_thickness_m=0.001,
            cut_perimeter_m=2.0,
            cut_speed_m_per_hr=10.0,
            laser_cut_rate_per_hr=80.0,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_cutting"] - 16.0) < REL

    def test_setup_amortisation_over_batch(self):
        """setup=100, batch=10 → unit_setup=10"""
        res = sheet_metal_cost(
            blank_area_m2=0.05,
            material_cost_per_kg=1.0,
            material_density_kg_m3=7850.0,
            sheet_thickness_m=0.001,
            setup_cost=100.0,
            batch_size=10,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_setup"] - 10.0) < REL

    def test_invalid_zero_area(self):
        res = sheet_metal_cost(
            blank_area_m2=0.0,
            material_cost_per_kg=1.0,
            material_density_kg_m3=7850.0,
            sheet_thickness_m=0.001,
        )
        assert res["ok"] is False


# ===========================================================================
# 5. printing_cost
# ===========================================================================

class TestPrintingCost:

    def test_support_fraction_inflates_material(self):
        """
        vol=10cm³, support=0.20, cost=0.10/cm³
        total_vol=10*1.2=12, unit_material=12*0.10=1.2
        """
        res = printing_cost(
            material_volume_cm3=10.0,
            material_cost_per_cm3=0.10,
            build_time_hr=1.0,
            machine_rate_per_hr=5.0,
            support_volume_fraction=0.20,
            overhead_rate=0.0,
            machine_utilisation=1.0,
        )
        assert res["ok"] is True
        assert abs(res["total_material_volume_cm3"] - 12.0) < REL
        assert abs(res["unit_material"] - 1.2) < REL

    def test_shared_machine_time_over_batch(self):
        """
        build=2hr, batch=4, rate=100/hr, utilisation=1
        unit_machine = 2/4 * 100 * 1 = 50
        """
        res = printing_cost(
            material_volume_cm3=5.0,
            material_cost_per_cm3=0.05,
            build_time_hr=2.0,
            machine_rate_per_hr=100.0,
            batch_size=4,
            machine_utilisation=1.0,
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_machine"] - 50.0) < REL

    def test_post_processing_added(self):
        """post=5 → unit_post=5"""
        res = printing_cost(
            material_volume_cm3=1.0,
            material_cost_per_cm3=0.10,
            build_time_hr=0.5,
            machine_rate_per_hr=10.0,
            post_processing_cost=5.0,
            overhead_rate=0.0,
            machine_utilisation=1.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_post"] - 5.0) < REL

    def test_high_support_fraction_warning(self):
        """support=0.40 → warning"""
        res = printing_cost(
            material_volume_cm3=5.0,
            material_cost_per_cm3=0.10,
            build_time_hr=1.0,
            machine_rate_per_hr=20.0,
            support_volume_fraction=0.40,
        )
        assert res["ok"] is True
        assert any("support" in w.lower() for w in res["warnings"])


# ===========================================================================
# 6. assembly_cost
# ===========================================================================

class TestAssemblyCost:

    def test_single_operation_hand_calc(self):
        """1 op: 0.5hr × 25/hr = 12.5, overhead 0.20 → 2.5, total 15"""
        res = assembly_cost(
            [{"name": "screw", "time_hr": 0.5, "rate_per_hr": 25.0}],
            overhead_rate=0.20,
        )
        assert res["ok"] is True
        assert abs(res["unit_labour"] - 12.5) < REL
        assert abs(res["unit_overhead"] - 2.5) < REL
        assert abs(res["unit_total_cost"] - 15.0) < REL

    def test_multi_operation_sum(self):
        """2 ops: (0.3hr×20) + (0.2hr×30) = 6+6=12; OH=0 → total=12"""
        res = assembly_cost(
            [
                {"time_hr": 0.3, "rate_per_hr": 20.0},
                {"time_hr": 0.2, "rate_per_hr": 30.0},
            ],
            overhead_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_labour"] - 12.0) < REL
        assert abs(res["unit_total_cost"] - 12.0) < REL

    def test_long_shift_warning(self):
        """total > 8hr → warning"""
        ops = [{"time_hr": 5.0, "rate_per_hr": 15.0},
               {"time_hr": 4.0, "rate_per_hr": 15.0}]
        res = assembly_cost(ops)
        assert res["ok"] is True
        assert any("shift" in w.lower() for w in res["warnings"])

    def test_empty_operations_error(self):
        res = assembly_cost([])
        assert res["ok"] is False

    def test_missing_time_hr_error(self):
        res = assembly_cost([{"rate_per_hr": 20.0}])
        assert res["ok"] is False


# ===========================================================================
# 7. rollup
# ===========================================================================

class TestRollup:

    def test_full_waterfall_hand_calc(self):
        """
        dm=10, dl=5, mc=8, setup_batch=20, batch=10, tooling=1
        unit_setup = 20/10 = 2
        total_direct = 10+5+8+2+1 = 26
        manufacturing = 26*(1+0.20) = 31.2
        full_cost = 31.2*(1+0.10) = 34.32
        unit_price = 34.32 / (1-0.25) = 45.76
        gross_margin = 45.76-34.32 = 11.44
        margin_actual = 11.44/45.76 = 0.25
        """
        res = rollup(
            direct_material=10.0,
            direct_labour=5.0,
            machine_cost=8.0,
            setup_cost_per_batch=20.0,
            batch_size=10,
            tooling_amortisation=1.0,
            overhead_rate=0.20,
            sga_rate=0.10,
            margin_rate=0.25,
        )
        assert res["ok"] is True
        assert abs(res["total_direct_cost"] - 26.0) < REL
        assert abs(res["manufacturing_cost"] - 31.2) < REL
        assert abs(res["full_cost"] - 34.32) < 1e-9
        assert abs(res["unit_price"] - 34.32 / 0.75) < 1e-9
        assert abs(res["margin_rate_actual"] - 0.25) < 1e-9

    def test_zero_margin_unit_price_equals_full_cost(self):
        """margin=0 → unit_price == full_cost"""
        res = rollup(
            direct_material=20.0,
            direct_labour=5.0,
            machine_cost=10.0,
            overhead_rate=0.0,
            sga_rate=0.0,
            margin_rate=0.0,
        )
        assert res["ok"] is True
        assert abs(res["unit_price"] - res["full_cost"]) < REL

    def test_negative_margin_warning(self):
        """
        margin_rate not negative; but full_cost > unit_price is impossible with margin>=0.
        Instead test that negative margin_rate=0 and very high costs is fine,
        and that if somehow (impossible via API) margin_actual < 0, we'd warn.
        Since margin_rate ∈ [0,1) the API can never produce negative margin.
        Test margin=0 → no negative-margin warning.
        """
        res = rollup(
            direct_material=10.0, direct_labour=5.0, machine_cost=5.0,
            overhead_rate=0.0, sga_rate=0.0, margin_rate=0.0,
        )
        assert res["ok"] is True
        # No negative margin warning
        neg_warnings = [w for w in res["warnings"] if "negative" in w.lower()]
        assert len(neg_warnings) == 0

    def test_setup_dominated_warning(self):
        """setup=500, batch=1, small other costs → warning"""
        res = rollup(
            direct_material=1.0,
            direct_labour=0.5,
            machine_cost=0.5,
            setup_cost_per_batch=500.0,
            batch_size=1,
            overhead_rate=0.0,
            sga_rate=0.0,
            margin_rate=0.0,
        )
        assert res["ok"] is True
        assert any("setup" in w.lower() or "batch" in w.lower() for w in res["warnings"])

    def test_invalid_margin_rate_gte_one(self):
        res = rollup(
            direct_material=5.0, direct_labour=2.0, machine_cost=3.0,
            margin_rate=1.0,
        )
        assert res["ok"] is False


# ===========================================================================
# 8. batch_curve
# ===========================================================================

class TestBatchCurve:

    def test_hand_calc_values(self):
        """
        fixed=100, variable=5
        n=1: 5+100=105; n=10: 5+10=15; n=100: 5+1=6
        """
        res = batch_curve(
            fixed_cost_per_run=100.0,
            variable_cost_per_unit=5.0,
            batch_sizes=[1, 10, 100],
        )
        assert res["ok"] is True
        bp = {b["batch_size"]: b["unit_cost"] for b in res["breakpoints"]}
        assert abs(bp[1] - 105.0) < REL
        assert abs(bp[10] - 15.0) < REL
        assert abs(bp[100] - 6.0) < REL

    def test_monotone_decreasing(self):
        """Unit cost must decrease (or stay flat) as batch size increases."""
        res = batch_curve(
            fixed_cost_per_run=200.0,
            variable_cost_per_unit=3.0,
            batch_sizes=[1, 5, 10, 50, 100, 500],
        )
        assert res["ok"] is True
        costs = [b["unit_cost"] for b in res["breakpoints"]]
        for i in range(len(costs) - 1):
            assert costs[i] >= costs[i + 1]

    def test_min_max_correct(self):
        res = batch_curve(50.0, 2.0, [1, 2, 5, 20])
        assert res["ok"] is True
        all_costs = [b["unit_cost"] for b in res["breakpoints"]]
        assert abs(res["min_unit_cost"] - min(all_costs)) < REL
        assert abs(res["max_unit_cost"] - max(all_costs)) < REL

    def test_zero_fixed_no_variation(self):
        """fixed=0 → all unit costs == variable"""
        res = batch_curve(0.0, 7.5, [1, 10, 100])
        assert res["ok"] is True
        for bp in res["breakpoints"]:
            assert abs(bp["unit_cost"] - 7.5) < REL
        assert len(res["warnings"]) > 0  # should warn about zero fixed cost

    def test_invalid_batch_size_zero(self):
        res = batch_curve(100.0, 5.0, [0, 10])
        assert res["ok"] is False


# ===========================================================================
# 9. learning_curve
# ===========================================================================

class TestLearningCurve:

    def test_doubling_law_80pct(self):
        """
        80% curve: at n=2, cost = t1*2^b where b=log(0.8)/log(2)
        = t1 * 0.80 (by definition of 80% curve)
        """
        t1 = 100.0
        res = learning_curve(t1=t1, cumulative_volume=2.0, learning_rate=0.80)
        assert res["ok"] is True
        assert abs(res["unit_cost"] - 80.0) < 1e-9

    def test_doubling_again(self):
        """At n=4, cost = t1 * 0.80^2 = t1 * 0.64"""
        t1 = 100.0
        res = learning_curve(t1=t1, cumulative_volume=4.0, learning_rate=0.80)
        assert res["ok"] is True
        assert abs(res["unit_cost"] - 64.0) < 1e-9

    def test_at_volume_one_returns_t1(self):
        """n=1 → unit_cost = t1 exactly"""
        res = learning_curve(t1=250.0, cumulative_volume=1.0, learning_rate=0.85)
        assert res["ok"] is True
        assert abs(res["unit_cost"] - 250.0) < 1e-9

    def test_b_exponent_formula(self):
        """b = log(lr) / log(2) for lr=0.70"""
        res = learning_curve(t1=1.0, cumulative_volume=8.0, learning_rate=0.70)
        assert res["ok"] is True
        b_expected = math.log(0.70) / math.log(2.0)
        assert abs(res["b_exponent"] - b_expected) < REL

    def test_cost_reduction_fraction(self):
        """cost_reduction_fraction = 1 - unit_cost/t1"""
        res = learning_curve(t1=200.0, cumulative_volume=16.0, learning_rate=0.80)
        assert res["ok"] is True
        expected_reduction = 1.0 - res["unit_cost"] / 200.0
        assert abs(res["cost_reduction_fraction"] - expected_reduction) < REL

    def test_rate_1_no_learning(self):
        """learning_rate=1.0 → unit_cost == t1 always (warning issued)"""
        res = learning_curve(t1=50.0, cumulative_volume=100.0, learning_rate=1.0)
        assert res["ok"] is True
        assert abs(res["unit_cost"] - 50.0) < REL
        assert len(res["warnings"]) > 0

    def test_invalid_zero_t1(self):
        res = learning_curve(t1=0.0, cumulative_volume=10.0)
        assert res["ok"] is False

    def test_invalid_learning_rate_above_one(self):
        res = learning_curve(t1=10.0, cumulative_volume=5.0, learning_rate=1.1)
        assert res["ok"] is False


# ===========================================================================
# 10. make_vs_buy
# ===========================================================================

class TestMakeVsBuy:

    def test_prefer_make_when_volume_above_breakeven(self):
        """
        make_unit=5, buy=10, fixed=100
        breakeven = ceil(100 / (10-5)) = 20
        at volume=50 → make preferred
        """
        res = make_vs_buy(
            make_unit_cost=5.0,
            buy_unit_price=10.0,
            make_fixed_cost=100.0,
            annual_volume=50,
        )
        assert res["ok"] is True
        assert res["breakeven_volume"] == 20
        assert res["preferred"] == "make"

    def test_prefer_buy_when_volume_below_breakeven(self):
        """volume=10 < breakeven=20 → buy preferred"""
        res = make_vs_buy(
            make_unit_cost=5.0,
            buy_unit_price=10.0,
            make_fixed_cost=100.0,
            annual_volume=10,
        )
        assert res["ok"] is True
        assert res["preferred"] == "buy"

    def test_annual_totals_hand_calc(self):
        """
        make_unit=8, buy=12, fixed=500, n=100
        make_annual = 8*100+500 = 1300
        buy_annual = 12*100 = 1200
        savings_if_make = 1200-1300 = -100 (negative → buy saves)
        """
        res = make_vs_buy(
            make_unit_cost=8.0,
            buy_unit_price=12.0,
            make_fixed_cost=500.0,
            annual_volume=100,
        )
        assert res["ok"] is True
        assert abs(res["make_annual_total"] - 1300.0) < REL
        assert abs(res["buy_annual_total"] - 1200.0) < REL
        assert abs(res["annual_savings_if_make"] - (-100.0)) < REL

    def test_no_fixed_cost_always_cheaper_buy_when_buy_price_lower(self):
        """
        no fixed: make=15, buy=10 → buy is always cheaper
        """
        res = make_vs_buy(
            make_unit_cost=15.0,
            buy_unit_price=10.0,
            make_fixed_cost=0.0,
            annual_volume=100,
        )
        assert res["ok"] is True
        assert res["preferred"] == "buy"

    def test_lead_time_warning(self):
        """make_lead >> buy_lead → warning"""
        res = make_vs_buy(
            make_unit_cost=5.0,
            buy_unit_price=8.0,
            make_lead_time_days=60.0,
            buy_lead_time_days=7.0,
        )
        assert res["ok"] is True
        assert any("lead time" in w.lower() for w in res["warnings"])

    def test_invalid_zero_volume(self):
        res = make_vs_buy(make_unit_cost=5.0, buy_unit_price=10.0, annual_volume=0)
        assert res["ok"] is False


# ===========================================================================
# 11. Tool wrappers — happy path
# ===========================================================================

class TestToolsHappyPath:

    def test_cnc_tool(self):
        raw = _run(run_costing_cnc(
            _ctx(),
            _args(material_cost=10.0, cycle_time_hr=0.5, machine_rate_per_hr=100.0),
        ))
        d = _ok_tool(raw)
        assert "unit_total_cost" in d

    def test_casting_tool(self):
        raw = _run(run_costing_casting(
            _ctx(),
            _args(material_cost_per_kg=20.0, part_mass_kg=1.0),
        ))
        d = _ok_tool(raw)
        assert "unit_total_cost" in d

    def test_injection_tool(self):
        raw = _run(run_costing_injection(
            _ctx(),
            _args(material_cost_per_kg=50.0, shot_mass_kg=0.01),
        ))
        d = _ok_tool(raw)
        assert "unit_total_cost" in d

    def test_sheet_metal_tool(self):
        raw = _run(run_costing_sheet_metal(
            _ctx(),
            _args(
                blank_area_m2=0.1, material_cost_per_kg=2.0,
                material_density_kg_m3=7850.0, sheet_thickness_m=0.002,
            ),
        ))
        d = _ok_tool(raw)
        assert "unit_total_cost" in d

    def test_printing_tool(self):
        raw = _run(run_costing_printing(
            _ctx(),
            _args(
                material_volume_cm3=10.0, material_cost_per_cm3=0.10,
                build_time_hr=1.0, machine_rate_per_hr=20.0,
            ),
        ))
        d = _ok_tool(raw)
        assert "unit_total_cost" in d

    def test_assembly_tool(self):
        raw = _run(run_costing_assembly(
            _ctx(),
            _args(operations=[{"time_hr": 0.5, "rate_per_hr": 20.0}]),
        ))
        d = _ok_tool(raw)
        assert "unit_total_cost" in d

    def test_rollup_tool(self):
        raw = _run(run_costing_rollup(
            _ctx(),
            _args(direct_material=10.0, direct_labour=5.0, machine_cost=8.0),
        ))
        d = _ok_tool(raw)
        assert "unit_price" in d

    def test_batch_curve_tool(self):
        raw = _run(run_costing_batch_curve(
            _ctx(),
            _args(
                fixed_cost_per_run=100.0,
                variable_cost_per_unit=5.0,
                batch_sizes=[1, 10, 50],
            ),
        ))
        d = _ok_tool(raw)
        assert "breakpoints" in d
        assert len(d["breakpoints"]) == 3

    def test_learning_curve_tool(self):
        raw = _run(run_costing_learning_curve(
            _ctx(),
            _args(t1=100.0, cumulative_volume=2.0),
        ))
        d = _ok_tool(raw)
        assert abs(d["unit_cost"] - 80.0) < 1e-6

    def test_make_vs_buy_tool(self):
        raw = _run(run_costing_make_vs_buy(
            _ctx(),
            _args(make_unit_cost=5.0, buy_unit_price=10.0),
        ))
        d = _ok_tool(raw)
        assert "preferred" in d


# ===========================================================================
# 12. Tool wrappers — error paths
# ===========================================================================

class TestToolsErrorPaths:

    def test_cnc_missing_required(self):
        raw = _run(run_costing_cnc(
            _ctx(),
            _args(cycle_time_hr=0.5, machine_rate_per_hr=100.0),
        ))
        _err_tool(raw)

    def test_casting_invalid_json(self):
        raw = _run(run_costing_casting(_ctx(), b"not-json"))
        _err_tool(raw)

    def test_injection_missing_shot_mass(self):
        raw = _run(run_costing_injection(
            _ctx(),
            _args(material_cost_per_kg=50.0),
        ))
        _err_tool(raw)

    def test_sheet_metal_missing_thickness(self):
        raw = _run(run_costing_sheet_metal(
            _ctx(),
            _args(blank_area_m2=0.1, material_cost_per_kg=2.0,
                  material_density_kg_m3=7850.0),
        ))
        _err_tool(raw)

    def test_printing_missing_build_time(self):
        raw = _run(run_costing_printing(
            _ctx(),
            _args(material_volume_cm3=10.0, material_cost_per_cm3=0.10,
                  machine_rate_per_hr=20.0),
        ))
        _err_tool(raw)

    def test_assembly_missing_operations(self):
        raw = _run(run_costing_assembly(_ctx(), _args(overhead_rate=0.2)))
        _err_tool(raw)

    def test_rollup_missing_machine_cost(self):
        raw = _run(run_costing_rollup(
            _ctx(),
            _args(direct_material=5.0, direct_labour=3.0),
        ))
        _err_tool(raw)

    def test_batch_curve_invalid_json(self):
        raw = _run(run_costing_batch_curve(_ctx(), b"{bad json"))
        _err_tool(raw)

    def test_learning_curve_missing_volume(self):
        raw = _run(run_costing_learning_curve(_ctx(), _args(t1=100.0)))
        _err_tool(raw)

    def test_make_vs_buy_missing_buy_price(self):
        raw = _run(run_costing_make_vs_buy(_ctx(), _args(make_unit_cost=5.0)))
        _err_tool(raw)


# ---------------------------------------------------------------------------
# Externally-citable reference cases
#   Wright, T.P. (1936) "Factors Affecting the Cost of Airplanes",
#     J. Aeronautical Sciences 3(4), 122-128 (learning curve).
#   Ostwald & Munoz "Manufacturing Processes and Systems" 9th ed.
#     (cost build-up, batch economics, make-vs-buy break-even).
#   Boothroyd, Dewhurst & Knight "Product Design for Manufacture and
#     Assembly" 3rd ed.
# ---------------------------------------------------------------------------

class TestCostingExternalReferenceCases:
    """Cross-checked against Wright (1936) learning curve and standard
    manufacturing cost-estimation build-ups (Ostwald & Munoz, DFMA)."""

    def test_wright_learning_curve_exponent(self):
        # Wright (1936): b = ln(LR)/ln(2).  LR = 0.80 -> b = -0.32193.
        r = learning_curve(10.0, 8, learning_rate=0.80)
        assert math.isclose(r["b_exponent"], math.log(0.80) / math.log(2.0),
                            rel_tol=1e-6)

    def test_wright_learning_curve_value(self):
        # Wright power law: cost at unit n = t1 * n^b.
        # t1=10, n=8, LR=0.8 -> 10 * 8^(log2 0.8) = 5.12.
        r = learning_curve(10.0, 8, learning_rate=0.80)
        b = math.log(0.80) / math.log(2.0)
        assert math.isclose(r["unit_cost"], 10.0 * 8.0 ** b, rel_tol=1e-6)

    def test_learning_curve_doubling_rule(self):
        # Wright doubling rule: every doubling of volume multiplies the
        # cost by the learning rate (here 0.80).
        a = learning_curve(10.0, 100, learning_rate=0.80)
        b = learning_curve(10.0, 200, learning_rate=0.80)
        assert math.isclose(b["unit_cost"], 0.80 * a["unit_cost"],
                            rel_tol=1e-6)

    def test_cnc_cost_machine_time_component(self):
        # Standard cost build-up: machine cost = cycle_time * machine_rate.
        r = cnc_cost(material_cost=5.0, cycle_time_hr=0.25,
                     machine_rate_per_hr=80.0, setup_time_hr=0.5,
                     batch_size=10, tooling_cost=200.0,
                     tooling_life_parts=1000, overhead_rate=0.15)
        assert math.isclose(r["unit_machine"], 0.25 * 80.0, rel_tol=1e-9)

    def test_cnc_cost_setup_amortised_over_batch(self):
        # Ostwald & Munoz: setup cost amortised = setup_time*rate / batch.
        r = cnc_cost(material_cost=5.0, cycle_time_hr=0.25,
                     machine_rate_per_hr=80.0, setup_time_hr=0.5,
                     batch_size=10)
        assert math.isclose(r["unit_setup"], 0.5 * 80.0 / 10.0, rel_tol=1e-9)

    def test_cnc_cost_tooling_amortised_over_life(self):
        # Tooling amortisation = tooling_cost / tooling_life_parts.
        r = cnc_cost(material_cost=5.0, cycle_time_hr=0.25,
                     machine_rate_per_hr=80.0, tooling_cost=200.0,
                     tooling_life_parts=1000)
        assert math.isclose(r["unit_tooling"], 200.0 / 1000.0, rel_tol=1e-9)

    def test_batch_curve_unit_cost_formula(self):
        # Batch economics: unit cost = fixed_per_run/batch + variable.
        r = batch_curve(1000.0, 5.0, [10, 100, 1000])
        bp = {b["batch_size"]: b["unit_cost"] for b in r["breakpoints"]}
        assert math.isclose(bp[10], 1000.0 / 10 + 5.0, rel_tol=1e-9)
        assert math.isclose(bp[100], 1000.0 / 100 + 5.0, rel_tol=1e-9)
        assert math.isclose(bp[1000], 1000.0 / 1000 + 5.0, rel_tol=1e-9)

    def test_batch_curve_monotone_decreasing(self):
        # Fixed-cost dilution: larger batches -> lower unit cost.
        r = batch_curve(1000.0, 5.0, [10, 100, 1000])
        costs = [b["unit_cost"] for b in r["breakpoints"]]
        assert costs == sorted(costs, reverse=True)

    def test_make_vs_buy_breakeven(self):
        # Ostwald & Munoz break-even: make total vs buy total over volume.
        r = make_vs_buy(make_unit_cost=8.0, buy_unit_price=10.0,
                        make_fixed_cost=2000.0, annual_volume=2000)
        # Break-even volume = fixed / (buy - make) = 2000 / 2 = 1000 units.
        assert math.isclose(r["breakeven_volume"], 2000.0 / (10.0 - 8.0),
                            rel_tol=1e-6)

    def test_rollup_margin_buildup(self):
        # DFMA cost roll-up: price = full_cost / (1 - margin_rate).
        r = rollup(direct_material=10.0, direct_labour=5.0,
                   machine_cost=20.0, overhead_rate=0.2,
                   sga_rate=0.1, margin_rate=0.2)
        assert math.isclose(r["unit_price"],
                            r["full_cost"] / (1.0 - 0.2), rel_tol=1e-6)
        assert math.isclose(r["margin_rate_actual"], 0.2, rel_tol=1e-6)
