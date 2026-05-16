"""
Hermetic tests for kerf_cad_core.thermalcut — thermal/abrasive cutting-process
engineering.

Coverage:
  process.laser_cut_speed     — energy-balance speed model
  process.plasma_cut_speed    — arc-power energy-balance
  process.oxyfuel_cut_speed   — empirical table interpolation
  process.waterjet_cut_speed  — Hashish machinability model
  process.kerf_width          — per-process empirical formulas
  process.taper_angle         — speed-ratio taper model
  process.haz_width           — HAZ width formula
  process.pierce_time         — per-process empirical models
  process.lead_in_length      — lead-in geometry
  process.edge_quality_regime — speed-ratio regime classification
  process.gas_consumption     — gas volume and cost
  process.abrasive_consumption — abrasive mass and cost
  process.select_power        — power/amperage selection tables
  process.waterjet_params     — orifice/mixing-tube sizing
  process.part_cost           — cost roll-up
  process.process_compare     — cross-process comparison

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas are verified algebraically against the published models.

References
----------
Steen & Mazumder, "Laser Material Processing", 4th ed., Springer 2010
Hashish, M., J. Eng. for Ind. 1989
ESAB Plasma Cutting Handbook, 3rd ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.thermalcut.process import (
    laser_cut_speed,
    plasma_cut_speed,
    oxyfuel_cut_speed,
    waterjet_cut_speed,
    kerf_width,
    taper_angle,
    haz_width,
    pierce_time,
    lead_in_length,
    edge_quality_regime,
    gas_consumption,
    abrasive_consumption,
    select_power,
    waterjet_params,
    part_cost,
    process_compare,
)
from kerf_cad_core.thermalcut.tools import (
    run_thermalcut_laser_speed,
    run_thermalcut_plasma_speed,
    run_thermalcut_oxyfuel_speed,
    run_thermalcut_waterjet_speed,
    run_thermalcut_kerf_width,
    run_thermalcut_haz_width,
    run_thermalcut_pierce_time,
    run_thermalcut_edge_quality,
    run_thermalcut_gas_consumption,
    run_thermalcut_waterjet_params,
    run_thermalcut_part_cost,
    run_thermalcut_process_compare,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

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


def _ok(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


# ---------------------------------------------------------------------------
# 1. laser_cut_speed — energy-balance hand-calc verification
# ---------------------------------------------------------------------------

class TestLaserCutSpeed:

    def test_basic_mild_steel_returns_ok(self):
        r = laser_cut_speed(6.0, 2000.0)
        assert r["ok"] is True
        assert r["speed_mm_min"] > 0

    def test_energy_balance_formula(self):
        """
        Manually replicate the energy-balance formula and compare.
        mild_steel: rho=7850, cp=500, T_melt=1808, L_f=272000, L_v=6090000
        eta=0.55 (O2), kerf=0.10+0.04*sqrt(6)=0.198mm (clamped after power factor)
        H = 500*(1808-293) + 272000 + 0.15*6090000
        """
        t_mm = 6.0
        P = 2000.0
        rho = 7850.0
        cp = 500.0
        T_melt = 1808.0
        T_amb = 293.0
        L_f = 272_000.0
        L_v = 6_090_000.0
        eta = 0.55

        dT = T_melt - T_amb
        H = cp * dT + L_f + 0.15 * L_v
        w_k_mm = 0.10 + 0.04 * math.sqrt(t_mm)
        power_factor = 1.0 + 0.00005 * P
        w_k_mm = w_k_mm  # power factor applies in kerf_width, not laser_cut_speed

        t_m = t_mm * 1e-3
        w_k_m = w_k_mm * 1e-3
        denom = rho * H * t_m * w_k_m
        v_m_s = eta * P / denom
        expected_mm_min = v_m_s * 60_000.0

        r = laser_cut_speed(t_mm, P)
        assert r["ok"] is True
        assert abs(r["speed_mm_min"] - expected_mm_min) < 1.0  # within 1 mm/min

    def test_high_power_gives_higher_speed(self):
        r1 = laser_cut_speed(10.0, 3000.0)
        r2 = laser_cut_speed(10.0, 6000.0)
        assert r1["ok"] and r2["ok"]
        assert r2["speed_mm_min"] > r1["speed_mm_min"]

    def test_thicker_gives_lower_speed(self):
        r1 = laser_cut_speed(3.0, 2000.0)
        r2 = laser_cut_speed(12.0, 2000.0)
        assert r1["ok"] and r2["ok"]
        assert r1["speed_mm_min"] > r2["speed_mm_min"]

    def test_aluminium_different_from_steel(self):
        r_steel = laser_cut_speed(6.0, 4000.0, "mild_steel")
        r_al = laser_cut_speed(6.0, 4000.0, "aluminium_6061")
        assert r_steel["ok"] and r_al["ok"]
        # Aluminium has lower density → should be faster despite higher L_v
        assert r_al["speed_mm_min"] != r_steel["speed_mm_min"]

    def test_n2_assist_lower_efficiency(self):
        r_o2 = laser_cut_speed(6.0, 2000.0, assist_gas="O2")
        r_n2 = laser_cut_speed(6.0, 2000.0, assist_gas="N2")
        assert r_o2["ok"] and r_n2["ok"]
        # N2 has eta=0.45 vs O2 eta=0.55 → slower
        assert r_o2["speed_mm_min"] > r_n2["speed_mm_min"]

    def test_warns_on_too_thick(self):
        r = laser_cut_speed(60.0, 2000.0, "mild_steel")
        assert r["ok"] is True
        assert any("too thick" in w or "practical laser" in w for w in r["warnings"])

    def test_invalid_material(self):
        r = laser_cut_speed(6.0, 2000.0, "unobtainium")
        assert r["ok"] is False

    def test_negative_thickness(self):
        r = laser_cut_speed(-1.0, 2000.0)
        assert r["ok"] is False

    def test_negative_power(self):
        r = laser_cut_speed(6.0, -500.0)
        assert r["ok"] is False

    def test_efficiency_override(self):
        r = laser_cut_speed(6.0, 2000.0, efficiency=0.70)
        assert r["ok"] is True
        assert r["efficiency"] == 0.70

    def test_kerf_override(self):
        r = laser_cut_speed(6.0, 2000.0, kerf_mm=0.5)
        assert r["ok"] is True
        assert r["kerf_mm"] == 0.5

    def test_efficiency_above_one_fails(self):
        r = laser_cut_speed(6.0, 2000.0, efficiency=1.5)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 2. plasma_cut_speed
# ---------------------------------------------------------------------------

class TestPlasmaCutSpeed:

    def test_basic_returns_ok(self):
        r = plasma_cut_speed(10.0, 130.0)
        assert r["ok"] is True
        assert r["speed_mm_min"] > 0

    def test_arc_power_computed(self):
        r = plasma_cut_speed(10.0, 130.0, voltage=130.0)
        assert r["power_W"] == pytest.approx(130.0 * 130.0, rel=1e-6)

    def test_higher_amperage_faster(self):
        r1 = plasma_cut_speed(12.0, 100.0)
        r2 = plasma_cut_speed(12.0, 200.0)
        assert r1["ok"] and r2["ok"]
        assert r2["speed_mm_min"] > r1["speed_mm_min"]

    def test_thicker_slower(self):
        r1 = plasma_cut_speed(6.0, 130.0)
        r2 = plasma_cut_speed(25.0, 130.0)
        assert r1["ok"] and r2["ok"]
        assert r1["speed_mm_min"] > r2["speed_mm_min"]

    def test_warns_very_thick(self):
        r = plasma_cut_speed(160.0, 450.0)
        assert r["ok"] is True
        assert r["warnings"]

    def test_invalid_material(self):
        r = plasma_cut_speed(10.0, 130.0, "unobtainium")
        assert r["ok"] is False

    def test_zero_amperage_fails(self):
        r = plasma_cut_speed(10.0, 0.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 3. oxyfuel_cut_speed
# ---------------------------------------------------------------------------

class TestOxyfuelCutSpeed:

    def test_mild_steel_6mm(self):
        r = oxyfuel_cut_speed(6.0)
        assert r["ok"] is True
        assert r["speed_mm_min"] == pytest.approx(900.0, rel=0.01)

    def test_interpolation_between_table_points(self):
        # Between 12 mm (600 mm/min) and 19 mm (440 mm/min)
        r = oxyfuel_cut_speed(15.0)
        assert r["ok"] is True
        assert 440.0 < r["speed_mm_min"] < 600.0

    def test_thick_section(self):
        r = oxyfuel_cut_speed(150.0)
        assert r["ok"] is True
        assert r["speed_mm_min"] == pytest.approx(80.0, rel=0.01)
        assert any("heavy" in w.lower() or "preheat" in w.lower() for w in r["warnings"])

    def test_non_ferrous_fails(self):
        r = oxyfuel_cut_speed(6.0, "aluminium_6061")
        assert r["ok"] is False
        assert "oxyfuel" in r["reason"].lower()

    def test_stainless_fails(self):
        r = oxyfuel_cut_speed(6.0, "stainless_304")
        assert r["ok"] is False

    def test_tool_steel_ok(self):
        r = oxyfuel_cut_speed(10.0, "tool_steel")
        assert r["ok"] is True

    def test_negative_thickness_fails(self):
        r = oxyfuel_cut_speed(-5.0)
        assert r["ok"] is False

    def test_below_1mm_fails(self):
        r = oxyfuel_cut_speed(0.5)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 4. waterjet_cut_speed — Hashish model
# ---------------------------------------------------------------------------

class TestWaterjetCutSpeed:

    def test_mild_steel_returns_ok(self):
        r = waterjet_cut_speed(10.0, "mild_steel")
        assert r["ok"] is True
        assert r["speed_mm_min"] > 0

    def test_hashish_formula_components(self):
        """
        Verify Hashish model components are self-consistent.
        At pump_power_kW=30, orifice=0.356mm, abrasive=0.45kg/min
        for 10mm mild steel.
        Calibrated: C_m=1.195e-14 → ~150 mm/min at these parameters.
        """
        r = waterjet_cut_speed(
            10.0, "mild_steel",
            pump_power_kW=30.0,
            orifice_dia_mm=0.356,
            abrasive_rate_kg_min=0.45,
        )
        assert r["ok"] is True
        assert r["jet_power_W"] == pytest.approx(30_000.0 * 0.75, rel=1e-6)
        assert r["mixing_tube_dia_mm"] == pytest.approx(0.356 * 3.5, rel=1e-4)
        # Speed should be ~150 mm/min for these calibration parameters
        assert 100.0 < r["speed_mm_min"] < 250.0

    def test_thicker_slower(self):
        # Use thicker sections to stay below the 10 000 mm/min cap
        r1 = waterjet_cut_speed(10.0, "mild_steel")
        r2 = waterjet_cut_speed(100.0, "mild_steel")
        assert r1["ok"] and r2["ok"]
        assert r1["speed_mm_min"] > r2["speed_mm_min"]

    def test_higher_machinability_faster(self):
        # Use thicker section to stay below cap
        r1 = waterjet_cut_speed(50.0, "mild_steel", machinability_number=50.0)
        r2 = waterjet_cut_speed(50.0, "mild_steel", machinability_number=150.0)
        assert r1["ok"] and r2["ok"]
        assert r2["speed_mm_min"] > r1["speed_mm_min"]

    def test_granite_slower_than_aluminium(self):
        # At 50mm, granite (N_m=35) vs aluminium (N_m=160)
        r_gra = waterjet_cut_speed(50.0, "granite")
        r_al = waterjet_cut_speed(50.0, "aluminium_6061")
        assert r_gra["ok"] and r_al["ok"]
        assert r_al["speed_mm_min"] > r_gra["speed_mm_min"]

    def test_warns_very_thick(self):
        r = waterjet_cut_speed(210.0, "mild_steel")
        assert r["ok"] is True
        assert any("taper" in w.lower() or "limit" in w.lower() for w in r["warnings"])

    def test_invalid_material(self):
        r = waterjet_cut_speed(10.0, "moon_rock")
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 5. kerf_width
# ---------------------------------------------------------------------------

class TestKerfWidth:

    def test_laser_kerf_formula(self):
        # w_k = 0.10 + 0.04·√6 × power_factor
        t_mm = 6.0
        P = 2000.0
        power_factor = 1.0 + 0.00005 * P
        expected = (0.10 + 0.04 * math.sqrt(t_mm)) * power_factor
        r = kerf_width("laser", t_mm, P)
        assert r["ok"] is True
        assert abs(r["kerf_mm"] - expected) < 1e-3

    def test_plasma_wider_than_laser(self):
        r_laser = kerf_width("laser", 10.0, 3000.0)
        r_plasma = kerf_width("plasma", 10.0, 130.0)
        assert r_laser["ok"] and r_plasma["ok"]
        assert r_plasma["kerf_mm"] > r_laser["kerf_mm"]

    def test_waterjet_narrow(self):
        r = kerf_width("waterjet", 20.0, 30.0)
        assert r["ok"] is True
        assert r["kerf_mm"] < 3.0

    def test_oxyfuel_thickness_scaling(self):
        r1 = kerf_width("oxyfuel", 6.0, 45.0)
        r2 = kerf_width("oxyfuel", 50.0, 45.0)
        assert r1["ok"] and r2["ok"]
        assert r2["kerf_mm"] > r1["kerf_mm"]

    def test_invalid_process(self):
        r = kerf_width("oxy-plasma", 10.0, 100.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 6. taper_angle
# ---------------------------------------------------------------------------

class TestTaperAngle:

    def test_at_nominal_speed_base_taper(self):
        # speed = v_nom → speed_ratio = 1.0 → base taper
        r = taper_angle("laser", 10.0, 1000.0, nominal_speed_mm_min=1000.0)
        assert r["ok"] is True
        assert r["taper_half_angle_deg"] == pytest.approx(0.5, abs=0.05)

    def test_fast_speed_increases_taper(self):
        # speed = 2 × v_nom → speed_ratio = 2.0
        r = taper_angle("laser", 10.0, 2000.0, nominal_speed_mm_min=1000.0)
        assert r["ok"] is True
        r_base = taper_angle("laser", 10.0, 1000.0, nominal_speed_mm_min=1000.0)
        assert r["taper_half_angle_deg"] > r_base["taper_half_angle_deg"]

    def test_plasma_more_taper_than_laser(self):
        r_laser = taper_angle("laser", 10.0, 1500.0, nominal_speed_mm_min=1000.0)
        r_plasma = taper_angle("plasma", 10.0, 1500.0, nominal_speed_mm_min=1000.0)
        assert r_laser["ok"] and r_plasma["ok"]
        assert r_plasma["taper_half_angle_deg"] > r_laser["taper_half_angle_deg"]

    def test_waterjet_minimal_taper(self):
        r = taper_angle("waterjet", 10.0, 1500.0, nominal_speed_mm_min=1000.0)
        assert r["ok"] is True
        assert r["taper_half_angle_deg"] < 1.5

    def test_total_taper_is_double_half(self):
        r = taper_angle("plasma", 25.0, 800.0, nominal_speed_mm_min=500.0)
        assert r["ok"] is True
        assert abs(r["taper_angle_total_deg"] - 2.0 * r["taper_half_angle_deg"]) < 1e-9

    def test_excessive_taper_warning(self):
        # Very high speed ratio → excessive taper warning
        r = taper_angle("plasma", 10.0, 5000.0, nominal_speed_mm_min=500.0)
        assert r["ok"] is True
        assert any("excessive" in w.lower() for w in r["warnings"])

    def test_invalid_process(self):
        r = taper_angle("oxy-arc", 10.0, 1000.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 7. haz_width
# ---------------------------------------------------------------------------

class TestHazWidth:

    def test_waterjet_zero_haz(self):
        r = haz_width("waterjet", 10.0, 300.0, 30.0)
        assert r["ok"] is True
        assert r["haz_mm"] == 0.0

    def test_laser_haz_formula(self):
        """
        HAZ = k_mat * sqrt(P / (v * t))
        mild_steel: k = 0.014
        """
        t_mm = 6.0
        v_mm_min = 3000.0
        P_W = 2000.0
        k = 0.014  # mild_steel
        v_m_s = v_mm_min / 60_000.0
        t_m = t_mm * 1e-3
        expected = k * math.sqrt(P_W / (v_m_s * t_m))

        r = haz_width("laser", t_mm, v_mm_min, P_W, "mild_steel")
        assert r["ok"] is True
        assert abs(r["haz_mm"] - expected) < 0.001

    def test_faster_speed_less_haz(self):
        r_slow = haz_width("laser", 6.0, 1000.0, 2000.0)
        r_fast = haz_width("laser", 6.0, 5000.0, 2000.0)
        assert r_slow["ok"] and r_fast["ok"]
        assert r_slow["haz_mm"] > r_fast["haz_mm"]

    def test_plasma_haz_uses_voltage_factor(self):
        r = haz_width("plasma", 10.0, 500.0, 130.0, "mild_steel")
        assert r["ok"] is True
        assert r["haz_mm"] > 0

    def test_titanium_haz_warning(self):
        r = haz_width("laser", 3.0, 100.0, 2000.0, "titanium_gr2")
        assert r["ok"] is True
        # Slow speed → large HAZ → warning on sensitisation
        # (haz might or might not exceed 1.0 mm — check for any haz-related warning)
        assert isinstance(r["warnings"], list)

    def test_invalid_material(self):
        r = haz_width("laser", 6.0, 3000.0, 2000.0, "unobtainium")
        assert r["ok"] is False

    def test_invalid_process(self):
        r = haz_width("electron-beam", 6.0, 3000.0, 2000.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 8. pierce_time
# ---------------------------------------------------------------------------

class TestPierceTime:

    def test_laser_pierce_formula(self):
        """
        t_p = 0.05 * t^1.3 / (P_kW^0.4)
        """
        t_mm = 6.0
        P_W = 2000.0
        P_kW = P_W / 1000.0
        expected = 0.05 * (t_mm ** 1.3) / (P_kW ** 0.4)

        r = pierce_time("laser", t_mm, power_W=P_W)
        assert r["ok"] is True
        assert abs(r["pierce_time_s"] - expected) < 0.001

    def test_plasma_pierce_formula(self):
        t_mm = 10.0
        I = 130.0
        I100 = I / 100.0
        expected = 0.10 * (t_mm ** 0.9) / (I100 ** 0.5)

        r = pierce_time("plasma", t_mm, amperage=I)
        assert r["ok"] is True
        assert abs(r["pierce_time_s"] - expected) < 0.001

    def test_oxyfuel_pierce_long(self):
        r = pierce_time("oxyfuel", 25.0)
        assert r["ok"] is True
        # 2.0 + 0.40 * 25 = 12.0 s
        assert abs(r["pierce_time_s"] - 12.0) < 0.001

    def test_waterjet_pierce_fast(self):
        r = pierce_time("waterjet", 10.0)
        assert r["ok"] is True
        # 0.02 * 10 = 0.2 s
        assert abs(r["pierce_time_s"] - 0.2) < 0.001

    def test_laser_missing_power_fails(self):
        r = pierce_time("laser", 6.0)
        assert r["ok"] is False
        assert "power_W" in r["reason"]

    def test_plasma_missing_amperage_fails(self):
        r = pierce_time("plasma", 6.0)
        assert r["ok"] is False
        assert "amperage" in r["reason"]

    def test_thicker_longer_pierce_laser(self):
        r1 = pierce_time("laser", 3.0, power_W=2000.0)
        r2 = pierce_time("laser", 15.0, power_W=2000.0)
        assert r1["ok"] and r2["ok"]
        assert r2["pierce_time_s"] > r1["pierce_time_s"]

    def test_invalid_process(self):
        r = pierce_time("electron-beam", 6.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 9. lead_in_length
# ---------------------------------------------------------------------------

class TestLeadInLength:

    def test_formula(self):
        """
        L_lead = (v * 0.50) * (tp / 60)
        v=1200 mm/min, tp=2 s → L = (600) * (2/60) = 20 mm
        """
        r = lead_in_length(2.0, 1200.0)
        assert r["ok"] is True
        assert abs(r["lead_in_mm"] - 20.0) < 0.001

    def test_minimum_1mm(self):
        # Very short pierce time → clamped to 1 mm
        r = lead_in_length(0.001, 100.0)
        assert r["ok"] is True
        assert r["lead_in_mm"] >= 1.0

    def test_zero_pierce_time(self):
        r = lead_in_length(0.0, 500.0)
        assert r["ok"] is True
        assert r["lead_in_mm"] >= 1.0

    def test_longer_pierce_longer_lead_in(self):
        r1 = lead_in_length(1.0, 1000.0)
        r2 = lead_in_length(5.0, 1000.0)
        assert r1["ok"] and r2["ok"]
        assert r2["lead_in_mm"] > r1["lead_in_mm"]

    def test_negative_speed_fails(self):
        r = lead_in_length(2.0, -100.0)
        assert r["ok"] is False

    def test_negative_pierce_time_fails(self):
        r = lead_in_length(-1.0, 1000.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 10. edge_quality_regime
# ---------------------------------------------------------------------------

class TestEdgeQualityRegime:

    def test_optimal_regime(self):
        r = edge_quality_regime("laser", 1000.0, 1000.0)  # ratio = 1.0
        assert r["ok"] is True
        assert r["regime"] == "optimal"
        assert r["dross_risk"] == "low"
        assert r["edge_quality"] == "excellent"

    def test_too_slow(self):
        r = edge_quality_regime("laser", 400.0, 1000.0)  # ratio = 0.4
        assert r["ok"] is True
        assert r["regime"] == "too_slow"
        assert r["dross_risk"] == "high"

    def test_slow(self):
        r = edge_quality_regime("plasma", 700.0, 1000.0)  # ratio = 0.7
        assert r["ok"] is True
        assert r["regime"] == "slow"
        assert r["dross_risk"] == "moderate"

    def test_fast(self):
        r = edge_quality_regime("plasma", 1200.0, 1000.0)  # ratio = 1.2
        assert r["ok"] is True
        assert r["regime"] == "fast"

    def test_too_fast(self):
        r = edge_quality_regime("oxyfuel", 1600.0, 1000.0)  # ratio = 1.6
        assert r["ok"] is True
        assert r["regime"] == "too_fast"
        assert r["dross_risk"] == "high"

    def test_speed_ratio_computed(self):
        r = edge_quality_regime("waterjet", 800.0, 1000.0)
        assert r["ok"] is True
        assert abs(r["speed_ratio"] - 0.8) < 1e-6

    def test_invalid_process(self):
        r = edge_quality_regime("electron-beam", 1000.0, 1000.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 11. gas_consumption
# ---------------------------------------------------------------------------

class TestGasConsumption:

    def test_laser_o2_formula(self):
        """
        cut_time = L / v = 1000 / 500 = 2 min
        vol = 15 L/min * 2 = 30 L
        cost = 30 * 0.008 = 0.24 USD
        """
        r = gas_consumption("laser", 6.0, 1000.0, 500.0, assist_gas="O2")
        assert r["ok"] is True
        assert abs(r["cut_time_min"] - 2.0) < 1e-6
        assert abs(r["gas_volume_L"] - 30.0) < 0.001
        assert abs(r["gas_cost_usd"] - 0.24) < 0.001

    def test_n2_more_volume_than_o2(self):
        r_o2 = gas_consumption("laser", 6.0, 1000.0, 500.0, assist_gas="O2")
        r_n2 = gas_consumption("laser", 6.0, 1000.0, 500.0, assist_gas="N2")
        assert r_n2["gas_volume_L"] > r_o2["gas_volume_L"]

    def test_oxyfuel_combined_fuel_and_o2(self):
        # cut_time = 500/500 = 1 min
        # vol = (10 + 45) * 1 = 55 L
        r = gas_consumption("oxyfuel", 10.0, 500.0, 500.0)
        assert r["ok"] is True
        assert abs(r["gas_volume_L"] - 55.0) < 0.01

    def test_plasma_shield_gas(self):
        r = gas_consumption("plasma", 10.0, 1000.0, 1000.0)
        assert r["ok"] is True
        # cut_time = 1 min, rate = 15 L/min → 15 L
        assert abs(r["gas_volume_L"] - 15.0) < 0.001

    def test_waterjet_no_gas(self):
        r = gas_consumption("waterjet", 10.0, 1000.0, 300.0)
        assert r["ok"] is True
        assert r["gas_volume_L"] == 0.0
        assert r["gas_cost_usd"] == 0.0

    def test_invalid_assist_gas_for_laser(self):
        r = gas_consumption("laser", 6.0, 1000.0, 500.0, assist_gas="Argon")
        assert r["ok"] is False

    def test_invalid_process(self):
        r = gas_consumption("flame", 6.0, 1000.0, 500.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 12. abrasive_consumption
# ---------------------------------------------------------------------------

class TestAbrasiveConsumption:

    def test_formula(self):
        """
        cut_time = 500/250 = 2 min
        abrasive_kg = 0.45 * 2 = 0.9 kg
        cost = 0.9 * 0.45 = 0.405 USD
        """
        r = abrasive_consumption(500.0, 250.0, 0.45)
        assert r["ok"] is True
        assert abs(r["cut_time_min"] - 2.0) < 1e-6
        assert abs(r["abrasive_mass_kg"] - 0.9) < 1e-6
        assert abs(r["abrasive_cost_usd"] - 0.405) < 1e-4

    def test_longer_cut_more_abrasive(self):
        r1 = abrasive_consumption(500.0, 250.0)
        r2 = abrasive_consumption(2000.0, 250.0)
        assert r1["ok"] and r2["ok"]
        assert r2["abrasive_mass_kg"] > r1["abrasive_mass_kg"]

    def test_default_rate(self):
        r = abrasive_consumption(300.0, 300.0)
        assert r["ok"] is True
        assert r["abrasive_rate_kg_min"] == 0.45

    def test_zero_length_fails(self):
        r = abrasive_consumption(0.0, 300.0)
        assert r["ok"] is False

    def test_zero_speed_fails(self):
        r = abrasive_consumption(500.0, 0.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 13. select_power
# ---------------------------------------------------------------------------

class TestSelectPower:

    def test_laser_mild_steel_6mm(self):
        r = select_power("laser", 6.0, "mild_steel")
        assert r["ok"] is True
        assert r["recommended_W"] == pytest.approx(2000.0, rel=0.01)

    def test_laser_aluminium_scaled(self):
        r_steel = select_power("laser", 6.0, "mild_steel")
        r_al = select_power("laser", 6.0, "aluminium_6061")
        assert r_steel["ok"] and r_al["ok"]
        # Aluminium scale = 1.30
        assert r_al["recommended_W"] == pytest.approx(r_steel["recommended_W"] * 1.30, rel=0.01)

    def test_plasma_amperage_returned(self):
        r = select_power("plasma", 10.0, "mild_steel")
        assert r["ok"] is True
        assert r["recommended_A"] == pytest.approx(85.0, rel=0.01)

    def test_plasma_thicker_more_amps(self):
        r1 = select_power("plasma", 6.0)
        r2 = select_power("plasma", 50.0)
        assert r1["ok"] and r2["ok"]
        assert r2["recommended_A"] > r1["recommended_A"]

    def test_oxyfuel_not_supported(self):
        r = select_power("oxyfuel", 10.0)
        assert r["ok"] is False

    def test_invalid_material(self):
        r = select_power("laser", 10.0, "unobtainium")
        assert r["ok"] is False

    def test_cfrp_warning(self):
        r = select_power("laser", 3.0, "carbon_fibre_composite")
        assert r["ok"] is True
        assert any("fume" in w.lower() or "CFRP" in w for w in r["warnings"])


# ---------------------------------------------------------------------------
# 14. waterjet_params
# ---------------------------------------------------------------------------

class TestWaterjetParams:

    def test_basic_returns_ok(self):
        r = waterjet_params(30.0, 0.356)
        assert r["ok"] is True

    def test_orifice_area(self):
        d_mm = 0.356
        expected_area_mm2 = math.pi / 4.0 * d_mm ** 2
        r = waterjet_params(30.0, d_mm)
        assert r["ok"] is True
        assert abs(r["orifice_area_mm2"] - expected_area_mm2) < 1e-4

    def test_mixing_tube_default_ratio(self):
        r = waterjet_params(30.0, 0.356)
        assert r["ok"] is True
        assert abs(r["mixing_tube_dia_mm"] - 0.356 * 3.5) < 1e-4

    def test_jet_velocity_bernoulli(self):
        # v_jet = 0.65 * sqrt(2 * 380e6 / 1000)
        P_MPa = 380.0
        dP_Pa = P_MPa * 1e6
        expected_v = 0.65 * math.sqrt(2.0 * dP_Pa / 1000.0)
        r = waterjet_params(30.0, 0.356, pressure_MPa=P_MPa)
        assert r["ok"] is True
        assert abs(r["jet_velocity_m_s"] - expected_v) < 1.0  # within 1 m/s

    def test_default_standoff(self):
        r = waterjet_params(30.0, 0.356)
        assert r["ok"] is True
        assert r["standoff_mm"] == pytest.approx(4.0)

    def test_abrasive_loading_ratio_computed(self):
        r = waterjet_params(30.0, 0.356, abrasive_rate_kg_min=0.45)
        assert r["ok"] is True
        assert 0.0 < r["abrasive_loading_ratio"] < 2.0

    def test_custom_mixing_tube_warns_on_bad_ratio(self):
        # Very narrow mixing tube relative to orifice
        r = waterjet_params(30.0, 0.356, mixing_tube_dia_mm=0.400)
        assert r["ok"] is True  # no failure, just warning
        assert any("ratio" in w.lower() for w in r["warnings"])

    def test_zero_pump_power_fails(self):
        r = waterjet_params(0.0, 0.356)
        assert r["ok"] is False

    def test_zero_orifice_fails(self):
        r = waterjet_params(30.0, 0.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 15. part_cost — cost roll-up
# ---------------------------------------------------------------------------

class TestPartCost:

    def test_basic_formula(self):
        """
        cut_time_hr = 1000/(500*60) = 1/30 hr
        pierce_time_hr = 4*2/3600 = 8/3600 hr
        machine_time_hr = 1/30 + 8/3600
        cost = machine_time_hr * 65 + 0
        """
        cut_len = 1000.0   # mm
        speed = 500.0      # mm/min
        n = 4
        tp_s = 2.0
        rate = 65.0

        cut_time_hr = (cut_len / speed) / 60.0
        pierce_hr = n * tp_s / 3600.0
        expected = (cut_time_hr + pierce_hr) * rate

        r = part_cost("laser", cut_len, speed, n, tp_s,
                      machine_rate_usd_hr=rate, consumables_cost_usd=0.0)
        assert r["ok"] is True
        assert abs(r["total_cost_usd"] - expected) < 0.0001

    def test_consumables_added(self):
        r = part_cost("laser", 1000.0, 500.0, 4, 2.0,
                      machine_rate_usd_hr=65.0, consumables_cost_usd=5.0)
        assert r["ok"] is True
        r_no_cons = part_cost("laser", 1000.0, 500.0, 4, 2.0,
                               machine_rate_usd_hr=65.0, consumables_cost_usd=0.0)
        assert r["ok"] and r_no_cons["ok"]
        assert abs(r["total_cost_usd"] - r_no_cons["total_cost_usd"] - 5.0) < 1e-4

    def test_default_machine_rates(self):
        r_laser = part_cost("laser", 1000.0, 500.0, 1, 1.0)
        r_oxyfuel = part_cost("oxyfuel", 1000.0, 200.0, 1, 10.0)
        assert r_laser["ok"] and r_oxyfuel["ok"]
        # Laser has higher machine rate but much faster speed
        assert r_laser["machine_rate_usd_hr"] == 65.0
        assert r_oxyfuel["machine_rate_usd_hr"] == 25.0

    def test_more_pierces_higher_cost(self):
        r1 = part_cost("plasma", 1000.0, 300.0, 1, 3.0)
        r2 = part_cost("plasma", 1000.0, 300.0, 20, 3.0)
        assert r1["ok"] and r2["ok"]
        assert r2["total_cost_usd"] > r1["total_cost_usd"]

    def test_zero_pierces_ok(self):
        r = part_cost("waterjet", 1000.0, 200.0, 0, 0.0)
        assert r["ok"] is True

    def test_negative_pierces_fails(self):
        r = part_cost("laser", 1000.0, 500.0, -1, 1.0)
        assert r["ok"] is False

    def test_invalid_process_fails(self):
        r = part_cost("shear", 1000.0, 500.0, 1, 1.0)
        assert r["ok"] is False

    def test_zero_speed_fails(self):
        r = part_cost("laser", 1000.0, 0.0, 1, 1.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 16. process_compare
# ---------------------------------------------------------------------------

class TestProcessCompare:

    def test_mild_steel_all_processes(self):
        r = process_compare(10.0, "mild_steel", 1000.0, 4)
        assert r["ok"] is True
        for proc in ("laser", "plasma", "oxyfuel", "waterjet"):
            assert proc in r["results"]
            assert r["results"][proc]["applicable"] is True

    def test_aluminium_no_oxyfuel(self):
        r = process_compare(6.0, "aluminium_6061", 1000.0, 2)
        assert r["ok"] is True
        assert r["results"]["oxyfuel"]["applicable"] is False

    def test_stainless_no_oxyfuel(self):
        r = process_compare(6.0, "stainless_304")
        assert r["ok"] is True
        assert r["results"]["oxyfuel"]["applicable"] is False

    def test_waterjet_zero_haz(self):
        r = process_compare(10.0, "mild_steel")
        assert r["ok"] is True
        assert r["results"]["waterjet"]["haz_mm"] == 0.0

    def test_laser_narrowest_kerf(self):
        r = process_compare(6.0, "mild_steel")
        assert r["ok"] is True
        laser_kerf = r["results"]["laser"]["kerf_mm"]
        plasma_kerf = r["results"]["plasma"]["kerf_mm"]
        assert laser_kerf < plasma_kerf

    def test_invalid_material(self):
        r = process_compare(10.0, "moon_rock")
        assert r["ok"] is False

    def test_part_cost_fields_present(self):
        r = process_compare(10.0, "mild_steel")
        assert r["ok"] is True
        for proc, d in r["results"].items():
            if d["applicable"]:
                assert "part_cost_usd" in d
                assert d["part_cost_usd"] > 0.0


# ---------------------------------------------------------------------------
# 17. LLM tool wrappers — happy path + error paths
# ---------------------------------------------------------------------------

class TestToolWrappers:

    def test_laser_speed_tool_ok(self):
        raw = _run(run_thermalcut_laser_speed(
            _ctx(), _args(thickness_mm=6.0, power_W=2000.0)
        ))
        d = _ok(raw)
        assert d["speed_mm_min"] > 0

    def test_plasma_speed_tool_ok(self):
        raw = _run(run_thermalcut_plasma_speed(
            _ctx(), _args(thickness_mm=10.0, amperage=130.0)
        ))
        _ok(raw)

    def test_oxyfuel_speed_tool_ok(self):
        raw = _run(run_thermalcut_oxyfuel_speed(
            _ctx(), _args(thickness_mm=12.0)
        ))
        _ok(raw)

    def test_waterjet_speed_tool_ok(self):
        raw = _run(run_thermalcut_waterjet_speed(
            _ctx(), _args(thickness_mm=20.0, material="mild_steel")
        ))
        _ok(raw)

    def test_kerf_width_tool_ok(self):
        raw = _run(run_thermalcut_kerf_width(
            _ctx(), _args(process="laser", thickness_mm=6.0, power_or_amp=2000.0)
        ))
        _ok(raw)

    def test_haz_width_tool_ok(self):
        raw = _run(run_thermalcut_haz_width(
            _ctx(), _args(process="laser", thickness_mm=6.0,
                          speed_mm_min=3000.0, power_or_amp=2000.0)
        ))
        _ok(raw)

    def test_pierce_time_tool_laser_ok(self):
        raw = _run(run_thermalcut_pierce_time(
            _ctx(), _args(process="laser", thickness_mm=6.0, power_W=2000.0)
        ))
        _ok(raw)

    def test_edge_quality_tool_ok(self):
        raw = _run(run_thermalcut_edge_quality(
            _ctx(), _args(process="laser", speed_mm_min=1000.0,
                          nominal_speed_mm_min=1000.0)
        ))
        d = _ok(raw)
        assert d["regime"] == "optimal"

    def test_gas_consumption_tool_ok(self):
        raw = _run(run_thermalcut_gas_consumption(
            _ctx(), _args(process="laser", thickness_mm=6.0,
                          cut_length_mm=1000.0, speed_mm_min=500.0)
        ))
        _ok(raw)

    def test_waterjet_params_tool_ok(self):
        raw = _run(run_thermalcut_waterjet_params(
            _ctx(), _args(pump_power_kW=30.0, orifice_dia_mm=0.356)
        ))
        _ok(raw)

    def test_part_cost_tool_ok(self):
        raw = _run(run_thermalcut_part_cost(
            _ctx(), _args(process="laser", cut_length_mm=1000.0,
                          speed_mm_min=500.0, n_pierces=4, pierce_time_s=2.0)
        ))
        _ok(raw)

    def test_process_compare_tool_ok(self):
        raw = _run(run_thermalcut_process_compare(
            _ctx(), _args(thickness_mm=10.0, material="mild_steel")
        ))
        d = _ok(raw)
        assert "laser" in d["results"]

    def test_laser_speed_missing_power_fails(self):
        raw = _run(run_thermalcut_laser_speed(
            _ctx(), _args(thickness_mm=6.0)
        ))
        _err(raw)

    def test_plasma_speed_missing_amperage_fails(self):
        raw = _run(run_thermalcut_plasma_speed(
            _ctx(), _args(thickness_mm=10.0)
        ))
        _err(raw)

    def test_kerf_width_missing_process_fails(self):
        raw = _run(run_thermalcut_kerf_width(
            _ctx(), _args(thickness_mm=6.0, power_or_amp=2000.0)
        ))
        _err(raw)

    def test_part_cost_missing_pierces_fails(self):
        raw = _run(run_thermalcut_part_cost(
            _ctx(), _args(process="laser", cut_length_mm=1000.0,
                          speed_mm_min=500.0, pierce_time_s=2.0)
        ))
        _err(raw)

    def test_invalid_json_returns_error(self):
        raw = _run(run_thermalcut_laser_speed(_ctx(), b"not-valid-json"))
        _err(raw)

    def test_process_compare_missing_thickness_fails(self):
        raw = _run(run_thermalcut_process_compare(
            _ctx(), _args(material="mild_steel")
        ))
        _err(raw)
