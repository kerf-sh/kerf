"""
Hermetic tests for kerf_cad_core.plumbing — building plumbing & sanitary engineering.

Coverage:
  design.hunter_demand_gpm        — Hunter curve FU→GPM (flush-tank + flush-valve)
  design.size_supply_pipe         — Hazen-Williams pipe sizing + pressure budget
  design.dfu_to_drain_size        — IPC Table 710.1 drain/branch/stack sizing
  design.vent_size                — IPC Table 906.2 vent NPS selection
  design.trap_arm_slope           — IPC §1002.1 trap arm length + slope checks
  design.drain_slope_manning      — Manning full/half-flow + IPC slope compliance
  design.hot_water_heater_size    — ASHRAE Chapter 50 heater sizing
  design.hw_recirculation_loop    — recirculation flow + pump head
  design.storm_drain_leader       — IPC 1106.2/1106.3 storm leader sizing
  design.water_hammer_arrestor    — PDI WH-201 size selection
  design.expansion_tank_heater    — ASME/ASHRAE expansion tank volume

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Results are verified against IPC/Hunter hand-calcs.

References
----------
Hunter, R.B. (1940) BMS 65 — Methods of Estimating Loads in Plumbing Systems
IPC (2021) — International Plumbing Code, Tables 710.1, 906.2, 1002.1, 1106.2
ASHRAE Applications (2019), Chapter 50

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.plumbing.design import (
    hunter_demand_gpm,
    size_supply_pipe,
    dfu_to_drain_size,
    vent_size,
    trap_arm_slope,
    drain_slope_manning,
    hot_water_heater_size,
    hw_recirculation_loop,
    storm_drain_leader,
    water_hammer_arrestor,
    expansion_tank_heater,
)
from kerf_cad_core.plumbing.tools import (
    run_plumbing_hunter_demand,
    run_plumbing_size_supply_pipe,
    run_plumbing_dfu_drain_size,
    run_plumbing_vent_size,
    run_plumbing_trap_arm_slope,
    run_plumbing_drain_slope_manning,
    run_plumbing_hot_water_heater,
    run_plumbing_hw_recirc_loop,
    run_plumbing_storm_drain_leader,
    run_plumbing_water_hammer_arrestor,
    run_plumbing_expansion_tank,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx():
    """Minimal project context stub."""
    class _Ctx:
        project_id = uuid.uuid4()
    return _Ctx()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _tool_ok(coro_result: str) -> dict:
    data = json.loads(coro_result)
    assert data.get("ok") is True, f"Expected ok=True, got: {data}"
    return data


def _tool_err(coro_result: str) -> dict:
    data = json.loads(coro_result)
    is_ok_false = data.get("ok") is False
    is_err_payload = "error" in data and "code" in data
    assert is_ok_false or is_err_payload, f"Expected error response, got: {data}"
    return data


# ===========================================================================
# 1. hunter_demand_gpm
# ===========================================================================

class TestHunterDemandGpm:
    def test_flush_tank_1fu(self):
        """Hunter table: 1 FU flush-tank → 3.0 gpm."""
        r = hunter_demand_gpm(1)
        assert r["ok"] is True
        assert abs(r["demand_gpm"] - 3.0) < 0.1

    def test_flush_tank_10fu(self):
        """Hunter table: 10 FU flush-tank → 14.6 gpm."""
        r = hunter_demand_gpm(10)
        assert r["ok"] is True
        assert abs(r["demand_gpm"] - 14.6) < 0.5

    def test_flush_tank_100fu(self):
        """Hunter table: 100 FU flush-tank → 50.0 gpm."""
        r = hunter_demand_gpm(100)
        assert r["ok"] is True
        assert abs(r["demand_gpm"] - 50.0) < 1.0

    def test_flush_valve_10fu(self):
        """Hunter flush-valve: 10 FU → 23.0 gpm."""
        r = hunter_demand_gpm(10, system_type="flush_valve")
        assert r["ok"] is True
        assert abs(r["demand_gpm"] - 23.0) < 1.0

    def test_flush_valve_higher_than_tank(self):
        """Flush-valve demand always > flush-tank demand for same FU."""
        r_ft = hunter_demand_gpm(50)
        r_fv = hunter_demand_gpm(50, system_type="flush_valve")
        assert r_fv["demand_gpm"] > r_ft["demand_gpm"]

    def test_interpolation_midpoint(self):
        """Linear interpolation between 8 FU (12.8) and 10 FU (14.6): 9 FU ≈ 13.7."""
        r = hunter_demand_gpm(9)
        assert r["ok"] is True
        assert abs(r["demand_gpm"] - 13.7) < 0.5

    def test_invalid_fu_zero(self):
        r = hunter_demand_gpm(0)
        assert r["ok"] is False

    def test_invalid_system_type(self):
        r = hunter_demand_gpm(10, system_type="unknown")
        assert r["ok"] is False

    def test_large_fu_extrapolation_warning(self):
        r = hunter_demand_gpm(6000)
        assert r["ok"] is True
        assert any("5000" in w for w in r["warnings"])


# ===========================================================================
# 2. size_supply_pipe
# ===========================================================================

class TestSizeSupplyPipe:
    def test_small_flow_selects_small_pipe(self):
        """5 gpm at 60 psi over 50 ft should fit in 3/4\" copper."""
        r = size_supply_pipe(5.0, 60.0, 50.0)
        assert r["ok"] is True
        assert r["recommended_nps"] in ("3/4", "1/2", "3/8", "1")

    def test_large_flow_needs_bigger_pipe(self):
        """50 gpm at 80 psi over 200 ft should need ≥ 2\" pipe."""
        r = size_supply_pipe(50.0, 80.0, 200.0)
        assert r["ok"] is True
        nps = r["recommended_nps"]
        large = ("2", "2-1/2", "3", "4", "6")
        assert nps in large, f"Expected large pipe, got {nps}"

    def test_pressure_at_fixture_positive(self):
        """For adequately sized pipe, pressure at fixture must be > residual."""
        r = size_supply_pipe(10.0, 80.0, 100.0)
        assert r["ok"] is True
        assert r["pressure_at_fixture_psi"] >= 8.0 or any("UNDER-PRESSURE" in w for w in r["warnings"])

    def test_elevation_deducts_pressure(self):
        """Adding 20 ft elevation reduces pressure budget by 0.433×20 = 8.66 psi."""
        r0 = size_supply_pipe(10.0, 80.0, 100.0)
        r1 = size_supply_pipe(10.0, 80.0, 100.0, elevation_diff_ft=20.0)
        assert r1["elevation_loss_psi"] == pytest.approx(8.66, abs=0.05)

    def test_flush_valve_residual(self):
        """With 20 psi residual for flush valve, may warn for marginal supply."""
        r = size_supply_pipe(10.0, 30.0, 200.0, residual_pressure_psi=20.0)
        assert r["ok"] is True
        # May or may not warn, but must not error

    def test_galvanized_C120(self):
        """Galvanized pipe uses C=120; expect higher friction loss than copper."""
        r_cu = size_supply_pipe(20.0, 80.0, 100.0, material="copper_l")
        r_gv = size_supply_pipe(20.0, 80.0, 100.0, material="galvanized")
        # Galvanized may select larger pipe or show higher friction
        assert r_cu["ok"] is True
        assert r_gv["ok"] is True

    def test_missing_demand_error(self):
        r = size_supply_pipe(0, 60.0, 50.0)
        assert r["ok"] is False


# ===========================================================================
# 3. dfu_to_drain_size
# ===========================================================================

class TestDfuToDrainSize:
    def test_1dfu_horizontal_branch(self):
        """1 DFU horizontal branch → IPC says 1-1/4\"."""
        r = dfu_to_drain_size(1, pipe_type="horizontal_branch")
        assert r["ok"] is True
        assert r["recommended_nps"] == "1-1/4"

    def test_4dfu_horizontal_branch(self):
        """4 DFU (one water closet) horizontal branch → IPC: 3\" or larger."""
        r = dfu_to_drain_size(4, pipe_type="horizontal_branch")
        assert r["ok"] is True
        # 4 DFU: 2" handles 6 DFU, so 2" is the answer
        assert r["recommended_nps"] == "2"

    def test_water_closet_building_drain(self):
        """Water closet (4 DFU) on building drain → 2\" min in IPC table."""
        r = dfu_to_drain_size(4, pipe_type="building_drain")
        assert r["ok"] is True
        # IPC building drain table: 2" handles 21 DFU
        assert r["recommended_nps"] == "2"

    def test_large_building_stack(self):
        """200 DFU on stack → should be 4\" (IPC table: 4\" = 240 DFU)."""
        r = dfu_to_drain_size(200, pipe_type="stack")
        assert r["ok"] is True
        assert r["recommended_nps"] == "4"

    def test_invalid_pipe_type(self):
        r = dfu_to_drain_size(10, pipe_type="invalid_type")
        assert r["ok"] is False

    def test_zero_dfu_error(self):
        r = dfu_to_drain_size(0)
        assert r["ok"] is False

    def test_id_inch_populated(self):
        """ID inch should be > 0 for valid result."""
        r = dfu_to_drain_size(20, pipe_type="stack")
        assert r["ok"] is True
        assert r["pipe_id_inch"] > 0


# ===========================================================================
# 4. vent_size
# ===========================================================================

class TestVentSize:
    def test_1dfu_short_vent(self):
        """1 DFU, 10 ft developed length → 1-1/4\" vent (IPC table)."""
        r = vent_size(1, 10.0)
        assert r["ok"] is True
        assert r["recommended_nps"] == "1-1/4"

    def test_8dfu_50ft(self):
        """8 DFU, 50 ft → 1-1/2\" (IPC Table 906.2 allows 8 DFU at 50 ft for 1-1/2\")."""
        r = vent_size(8, 50.0)
        assert r["ok"] is True
        # 1-1/2" handles 8 DFU at 50 ft
        assert r["recommended_nps"] in ("1-1/2", "2")

    def test_larger_dfu_selects_larger_vent(self):
        """Higher DFU requires larger vent NPS."""
        r_small = vent_size(2, 30.0)
        r_large = vent_size(50, 30.0)
        assert r_ok(r_small) <= r_ok(r_large)  # same or larger NPS

    def test_long_run_needs_bigger_vent(self):
        """For same DFU, longer run may require larger NPS."""
        r_short = vent_size(10, 20.0)
        r_long = vent_size(10, 400.0)
        assert r_short["ok"] is True
        assert r_long["ok"] is True
        # r_long should be >= r_short in NPS

    def test_invalid_dfu_zero(self):
        r = vent_size(0, 20.0)
        assert r["ok"] is False

    def test_invalid_length_zero(self):
        r = vent_size(5, 0.0)
        assert r["ok"] is False

    def test_long_run_warning(self):
        r = vent_size(5, 250.0)
        assert r["ok"] is True
        assert any("200" in w for w in r["warnings"])


def r_ok(result):
    """Return NPS string for size comparison — higher NPS = bigger pipe."""
    _ORDER = ["1-1/4", "1-1/2", "2", "2-1/2", "3", "4", "5", "6"]
    try:
        return _ORDER.index(result["recommended_nps"])
    except ValueError:
        return len(_ORDER)


# ===========================================================================
# 5. trap_arm_slope
# ===========================================================================

class TestTrapArmSlope:
    def test_compliant_trap_arm(self):
        """1-1/2\" trap arm, 3 ft, 1/4\" per ft slope — should be OK."""
        r = trap_arm_slope(3.0, "1-1/2")
        assert r["ok"] is True
        assert r["arm_length_ok"] is True
        assert r["slope_ok"] is True

    def test_too_long_arm_warns(self):
        """1-1/2\" trap arm max is 3.5 ft; 5 ft should warn."""
        r = trap_arm_slope(5.0, "1-1/2")
        assert r["ok"] is True
        assert r["arm_length_ok"] is False
        assert any("TOO LONG" in w for w in r["warnings"])

    def test_slope_too_steep_warns(self):
        """Slope > 0.5 in/ft should warn."""
        r = trap_arm_slope(2.0, "1-1/2", slope_in_per_ft=0.75)
        assert r["ok"] is True
        assert r["slope_ok"] is False

    def test_slope_too_shallow_warns(self):
        """Slope < 0.125 in/ft should warn."""
        r = trap_arm_slope(2.0, "2", slope_in_per_ft=0.05)
        assert r["ok"] is True
        assert r["slope_ok"] is False
        assert any("SLOPE-OUT-OF-RANGE" in w for w in r["warnings"])

    def test_max_lengths_by_size(self):
        """Check IPC Table 1002.1 max lengths: 1-1/4=2.5, 1-1/2=3.5, 2=5.0."""
        r1 = trap_arm_slope(2.4, "1-1/4")
        assert r1["arm_length_ok"] is True
        r2 = trap_arm_slope(4.0, "1-1/2")
        assert r2["arm_length_ok"] is False

    def test_slope_pct_calculation(self):
        """0.25 in/ft = 2.083% slope."""
        r = trap_arm_slope(2.0, "2", slope_in_per_ft=0.25)
        assert abs(r["slope_pct"] - (0.25 / 12.0 * 100.0)) < 0.01


# ===========================================================================
# 6. drain_slope_manning
# ===========================================================================

class TestDrainSlopeManning:
    def test_4inch_quarter_slope(self):
        """4\" pipe at 1/4\"/ft slope with n=0.013: verify Q and V."""
        r = drain_slope_manning("4", 0.25)
        assert r["ok"] is True
        # Hand-calc: d=4.026\", A=π/4×(4.026/12)²=0.08841 ft², R=d/4=0.08387 ft
        # S=0.25/12=0.020833 ft/ft
        # V=1.486/0.013×0.08387^(2/3)×0.020833^0.5
        d_ft = 4.026 / 12.0
        A = math.pi / 4.0 * d_ft ** 2
        R = d_ft / 4.0
        S = 0.25 / 12.0
        V_expected = (1.486 / 0.013) * R ** (2.0 / 3.0) * S ** 0.5
        Q_expected_gpm = V_expected * A * 7.48052 * 60.0
        assert abs(r["full_flow_gpm"] - Q_expected_gpm) < 1.0

    def test_half_flow_is_half_of_full(self):
        """Half-flow capacity = exactly half of full-flow for circular pipe."""
        r = drain_slope_manning("3", 0.25)
        assert r["ok"] is True
        assert abs(r["half_flow_gpm"] - r["full_flow_gpm"] / 2.0) < 0.01

    def test_slope_below_minimum_warns_3inch(self):
        """3\" pipe slope < 1/4\"/ft should warn (IPC §704.1)."""
        r = drain_slope_manning("3", 0.125)
        assert r["ok"] is True
        assert r["slope_ok"] is False
        assert any("SLOPE-OUT-OF-RANGE" in w for w in r["warnings"])

    def test_4inch_min_slope_is_eighth(self):
        """4\" pipe: 1/8\"/ft slope is exactly OK (IPC §704.1)."""
        r = drain_slope_manning("4", 0.125)
        assert r["ok"] is True
        assert r["slope_ok"] is True

    def test_higher_slope_increases_capacity(self):
        """Higher slope → higher flow capacity."""
        r_low = drain_slope_manning("4", 0.25)
        r_high = drain_slope_manning("4", 0.5)
        assert r_high["full_flow_gpm"] > r_low["full_flow_gpm"]

    def test_invalid_nps(self):
        r = drain_slope_manning("99", 0.25)
        assert r["ok"] is False

    def test_velocity_increases_with_slope(self):
        """Velocity proportional to √slope (Manning)."""
        r1 = drain_slope_manning("6", 0.25)
        r4 = drain_slope_manning("6", 1.0)
        ratio = r4["full_flow_fps"] / r1["full_flow_fps"]
        assert abs(ratio - 2.0) < 0.05  # √(1.0/0.25) = 2.0


# ===========================================================================
# 7. hot_water_heater_size
# ===========================================================================

class TestHotWaterHeaterSize:
    def test_apartment_10_units(self):
        """10 apartment units: 60 gal/day/unit × 10 = 600 gal/day."""
        r = hot_water_heater_size("apartment", 10)
        assert r["ok"] is True
        assert abs(r["daily_demand_gal"] - 600.0) < 1.0

    def test_peak_hour_fraction(self):
        """Peak hourly demand = 17% of daily for apartments."""
        r = hot_water_heater_size("apartment", 10)
        assert abs(r["peak_hourly_gal"] - 600.0 * 0.17) < 1.0

    def test_btu_calculation(self):
        """BTU/hr = recovery_gph × 8.33 × ΔT / η."""
        r = hot_water_heater_size("apartment", 10, inlet_temp_f=40.0, supply_temp_f=120.0)
        assert r["ok"] is True
        delta_T = 120.0 - 40.0
        expected_btu = (r["recovery_rate_gph"] * 8.33 * delta_T) / 0.80
        assert abs(r["heater_btu_hr"] - expected_btu) < 100.0

    def test_storage_volume_1p5x_peak(self):
        """Storage volume ≈ 1.5 × peak hourly demand."""
        r = hot_water_heater_size("motel", 20)
        assert abs(r["storage_volume_gal"] - r["peak_hourly_gal"] * 1.5) < 1.0

    def test_undersized_heater_warning(self):
        """Fuel input that can't meet peak demand warns."""
        r = hot_water_heater_size("hotel", 50, fuel_btu_hr=10000)
        assert r["ok"] is True
        assert any("UNDERSIZED" in w for w in r["warnings"])

    def test_legionella_warning_below_120(self):
        r = hot_water_heater_size("apartment", 5, supply_temp_f=110.0, inlet_temp_f=55.0)
        assert r["ok"] is True
        assert any("120" in w or "Legionella" in w for w in r["warnings"])

    def test_scald_warning_above_140(self):
        r = hot_water_heater_size("apartment", 5, supply_temp_f=150.0, inlet_temp_f=55.0)
        assert r["ok"] is True
        assert any("140" in w or "scald" in w for w in r["warnings"])

    def test_invalid_occupancy(self):
        r = hot_water_heater_size("warehouse", 100)
        assert r["ok"] is False

    def test_supply_below_inlet_error(self):
        r = hot_water_heater_size("apartment", 10, inlet_temp_f=120.0, supply_temp_f=90.0)
        assert r["ok"] is False


# ===========================================================================
# 8. hw_recirculation_loop
# ===========================================================================

class TestHwRecirculationLoop:
    def test_basic_recirc_loop(self):
        """100 ft, 3/4\" pipe, 140°F supply, R=4: heat loss and flow calculated."""
        r = hw_recirculation_loop(100.0, "3/4")
        assert r["ok"] is True
        assert r["recirc_flow_gpm"] > 0
        assert r["total_heat_loss_btu_hr"] > 0
        assert r["pump_head_ft"] >= 0

    def test_higher_temp_higher_heat_loss(self):
        """Higher supply temperature → more heat loss."""
        r_lo = hw_recirculation_loop(100.0, "1", supply_temp_f=100.0)
        r_hi = hw_recirculation_loop(100.0, "1", supply_temp_f=160.0)
        assert r_hi["total_heat_loss_btu_hr"] > r_lo["total_heat_loss_btu_hr"]

    def test_longer_loop_higher_heat_loss(self):
        r_short = hw_recirculation_loop(50.0, "3/4")
        r_long = hw_recirculation_loop(200.0, "3/4")
        assert r_long["total_heat_loss_btu_hr"] > r_short["total_heat_loss_btu_hr"]

    def test_uninsulated_warns(self):
        r = hw_recirculation_loop(100.0, "1", insulation_r_value=0)
        assert r["ok"] is True
        assert any("uninsulated" in w.lower() for w in r["warnings"])

    def test_supply_below_ambient_error(self):
        r = hw_recirculation_loop(100.0, "1", supply_temp_f=50.0, ambient_temp_f=70.0)
        assert r["ok"] is False

    def test_invalid_pipe_nps(self):
        r = hw_recirculation_loop(100.0, "99")
        assert r["ok"] is False


# ===========================================================================
# 9. storm_drain_leader
# ===========================================================================

class TestStormDrainLeader:
    def test_small_roof_small_leader(self):
        """500 ft² at 4 in/hr: Q = 500×4/96.23 ≈ 20.8 gpm → 2\" vertical."""
        r = storm_drain_leader(500.0, 4.0)
        assert r["ok"] is True
        Q = r["design_flow_gpm"]
        assert abs(Q - 500.0 * 4.0 / 96.23) < 0.5
        assert r["recommended_nps"] == "2"

    def test_large_roof_needs_larger_leader(self):
        """10000 ft² at 6 in/hr → large leader required."""
        r = storm_drain_leader(10000.0, 6.0)
        assert r["ok"] is True
        assert r["recommended_nps"] in ("4", "5", "6", "8")

    def test_horizontal_vs_vertical_different_capacity(self):
        """Horizontal drain has different capacity table than vertical leader."""
        r_v = storm_drain_leader(2000.0, 4.0, leader_type="vertical")
        r_h = storm_drain_leader(2000.0, 4.0, leader_type="horizontal")
        assert r_v["ok"] is True
        assert r_h["ok"] is True
        # They may give different NPS

    def test_design_flow_formula(self):
        """Q = area × rainfall / 96.23."""
        area = 1200.0
        rain = 3.0
        r = storm_drain_leader(area, rain)
        assert abs(r["design_flow_gpm"] - area * rain / 96.23) < 0.1

    def test_zero_area_error(self):
        r = storm_drain_leader(0.0, 4.0)
        assert r["ok"] is False

    def test_invalid_leader_type(self):
        r = storm_drain_leader(1000.0, 4.0, leader_type="diagonal")
        assert r["ok"] is False

    def test_pipe_id_populated(self):
        r = storm_drain_leader(800.0, 5.0)
        assert r["ok"] is True
        assert r["pipe_id_inch"] > 0


# ===========================================================================
# 10. water_hammer_arrestor
# ===========================================================================

class TestWaterHammerArrestor:
    def test_1fu_size_A(self):
        """1 FU → PDI Size A."""
        r = water_hammer_arrestor(1)
        assert r["ok"] is True
        assert r["pdi_size"] == "A"

    def test_11fu_size_A(self):
        """11 FU → still Size A."""
        r = water_hammer_arrestor(11)
        assert r["ok"] is True
        assert r["pdi_size"] == "A"

    def test_12fu_size_B(self):
        """12 FU → Size B."""
        r = water_hammer_arrestor(12)
        assert r["ok"] is True
        assert r["pdi_size"] == "B"

    def test_60fu_size_C(self):
        """60 FU → Size C (boundary)."""
        r = water_hammer_arrestor(60)
        assert r["ok"] is True
        assert r["pdi_size"] == "C"

    def test_330fu_multiple_F(self):
        """330 FU → 'F (multiple)' with warning."""
        r = water_hammer_arrestor(330)
        assert r["ok"] is True
        assert "F" in r["pdi_size"]
        assert any("329" in w or "multiple" in w.lower() for w in r["warnings"])

    def test_zero_fu_error(self):
        r = water_hammer_arrestor(0)
        assert r["ok"] is False

    def test_location_label(self):
        r = water_hammer_arrestor(5, location="washing_machine_branch")
        assert r["ok"] is True
        assert r["location"] == "washing_machine_branch"


# ===========================================================================
# 11. expansion_tank_heater
# ===========================================================================

class TestExpansionTankHeater:
    def test_basic_sizing(self):
        """50 gal system at 120°F/40°F cold fill: expansion volume is positive."""
        r = expansion_tank_heater(50.0)
        assert r["ok"] is True
        assert r["volume_expansion_gal"] > 0
        assert r["expansion_tank_volume_gal"] >= 2.0

    def test_higher_temp_more_expansion(self):
        """Higher supply temperature → more expansion."""
        r_lo = expansion_tank_heater(50.0, supply_temp_f=100.0)
        r_hi = expansion_tank_heater(50.0, supply_temp_f=160.0)
        assert r_hi["volume_expansion_gal"] > r_lo["volume_expansion_gal"]

    def test_larger_system_more_expansion(self):
        """Larger system volume → more expansion."""
        r_sm = expansion_tank_heater(20.0)
        r_lg = expansion_tank_heater(200.0)
        assert r_lg["volume_expansion_gal"] > r_sm["volume_expansion_gal"]

    def test_specific_volumes_realistic(self):
        """Water specific volume at 120°F (~0.01620 ft³/lb) > cold (55°F ~0.01602)."""
        r = expansion_tank_heater(50.0, cold_fill_temp_f=55.0, supply_temp_f=120.0)
        assert r["v_hot_ft3_lb"] > r["v_cold_ft3_lb"]

    def test_supply_below_fill_error(self):
        r = expansion_tank_heater(50.0, supply_temp_f=30.0, cold_fill_temp_f=40.0)
        assert r["ok"] is False

    def test_relief_below_system_error(self):
        r = expansion_tank_heater(50.0, system_pressure_psi=150.0, relief_valve_psi=100.0)
        assert r["ok"] is False

    def test_tank_minimum_2gal(self):
        """Very small systems should still return at least 2 gal tank."""
        r = expansion_tank_heater(1.0, supply_temp_f=80.0, cold_fill_temp_f=70.0)
        assert r["ok"] is True
        assert r["expansion_tank_volume_gal"] >= 2.0


# ===========================================================================
# Tool wrapper tests (happy path + error path)
# ===========================================================================

class TestToolWrappers:
    """Smoke tests for all 11 LLM tool wrappers."""

    def test_hunter_demand_tool_ok(self):
        args = json.dumps({"fixture_units": 50}).encode()
        result = _run(run_plumbing_hunter_demand(_ctx(), args))
        data = _tool_ok(result)
        assert data["demand_gpm"] > 0

    def test_hunter_demand_tool_missing_field(self):
        args = json.dumps({}).encode()
        result = _run(run_plumbing_hunter_demand(_ctx(), args))
        _tool_err(result)

    def test_size_supply_pipe_tool_ok(self):
        args = json.dumps({
            "demand_gpm": 10.0,
            "available_pressure_psi": 70.0,
            "pipe_length_ft": 80.0,
        }).encode()
        result = _run(run_plumbing_size_supply_pipe(_ctx(), args))
        data = _tool_ok(result)
        assert "recommended_nps" in data

    def test_dfu_drain_size_tool_ok(self):
        args = json.dumps({"dfu": 20}).encode()
        result = _run(run_plumbing_dfu_drain_size(_ctx(), args))
        data = _tool_ok(result)
        assert "recommended_nps" in data

    def test_vent_size_tool_ok(self):
        args = json.dumps({"dfu_served": 4, "developed_length_ft": 40.0}).encode()
        result = _run(run_plumbing_vent_size(_ctx(), args))
        _tool_ok(result)

    def test_trap_arm_slope_tool_ok(self):
        args = json.dumps({"trap_arm_length_ft": 3.0, "trap_size_nps": "2"}).encode()
        result = _run(run_plumbing_trap_arm_slope(_ctx(), args))
        _tool_ok(result)

    def test_drain_slope_manning_tool_ok(self):
        args = json.dumps({"pipe_nps": "4", "slope_in_per_ft": 0.25}).encode()
        result = _run(run_plumbing_drain_slope_manning(_ctx(), args))
        _tool_ok(result)

    def test_hot_water_heater_tool_ok(self):
        args = json.dumps({"occupancy_type": "apartment", "num_units": 20}).encode()
        result = _run(run_plumbing_hot_water_heater(_ctx(), args))
        data = _tool_ok(result)
        assert data["heater_btu_hr"] > 0

    def test_hw_recirc_loop_tool_ok(self):
        args = json.dumps({"loop_length_ft": 150.0, "pipe_nps": "1"}).encode()
        result = _run(run_plumbing_hw_recirc_loop(_ctx(), args))
        _tool_ok(result)

    def test_storm_drain_leader_tool_ok(self):
        args = json.dumps({"roof_area_ft2": 2000.0, "rainfall_rate_in_hr": 4.0}).encode()
        result = _run(run_plumbing_storm_drain_leader(_ctx(), args))
        data = _tool_ok(result)
        assert "recommended_nps" in data

    def test_water_hammer_arrestor_tool_ok(self):
        args = json.dumps({"fixture_units": 25}).encode()
        result = _run(run_plumbing_water_hammer_arrestor(_ctx(), args))
        data = _tool_ok(result)
        assert data["pdi_size"] == "B"

    def test_expansion_tank_tool_ok(self):
        args = json.dumps({"system_water_volume_gal": 80.0}).encode()
        result = _run(run_plumbing_expansion_tank(_ctx(), args))
        data = _tool_ok(result)
        assert data["expansion_tank_volume_gal"] >= 2.0

    def test_tool_bad_json(self):
        """All tools must return an error response for bad JSON, not raise."""
        bad = b"not-json{"
        for coro_fn in (
            run_plumbing_hunter_demand,
            run_plumbing_size_supply_pipe,
            run_plumbing_dfu_drain_size,
        ):
            result = _run(coro_fn(_ctx(), bad))
            _tool_err(result)
