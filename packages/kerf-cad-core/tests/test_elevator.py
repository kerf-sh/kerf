"""
Hermetic tests for kerf_cad_core.elevator — vertical-transportation engineering.

Coverage:
  design.traction_lift      — roping, counterweight, traction ratio, D/d
  design.hydraulic_lift     — jack force, pressure, pump flow, power
  design.motor_power        — balanced-load motor power, duty derating
  design.kinematics         — S-curve, floor-to-floor time, short floor
  design.traffic_analysis   — RTT, interval, handling capacity, cars required
  design.buffer_stroke      — EN 81-1 stroke, governor trip, safety gear
  design.escalator          — capacity, power, incline checks
  tools.*                   — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulae verified against CIBSE Guide D 4th ed. and EN 81-1/81-2 hand-calcs.

References
----------
CIBSE Guide D: Transportation Systems in Buildings, 4th ed.
EN 81-1:1998+A3:2009 — Safety rules for electric traction lifts
EN 81-2:1998+A3:2009 — Safety rules for hydraulic lifts
EN 115-1:2017 — Safety of escalators and moving walks
Barney, G.C. — Elevator Traffic Handbook (2003)

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.elevator.design import (
    traction_lift,
    hydraulic_lift,
    motor_power,
    kinematics,
    traffic_analysis,
    buffer_stroke,
    escalator,
)
from kerf_cad_core.elevator.tools import (
    run_traction_lift,
    run_hydraulic_lift,
    run_motor_power,
    run_kinematics,
    run_traffic_analysis,
    run_buffer_stroke,
    run_escalator,
)

_G = 9.80665  # m/s²


# ---------------------------------------------------------------------------
# Helpers
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


def _args(**kw) -> bytes:
    return json.dumps(kw).encode()


def _is_error_response(r: dict) -> bool:
    return r.get("ok") is False or ("error" in r and "code" in r)


# ===========================================================================
# traction_lift tests
# ===========================================================================

class TestTractionLift:

    def test_basic_returns_ok(self):
        """Standard 1000 kg car at 1.6 m/s, 1:1 roping."""
        r = traction_lift(1000.0, 900.0, 1.6)
        assert r["ok"] is True
        assert "counterweight_mass_kg" in r
        assert "traction_ratio_full" in r

    def test_counterweight_mass_default_50pct(self):
        """CW = car_mass + 50% × rated_load = 900 + 0.5×1000 = 1400 kg."""
        r = traction_lift(1000.0, 900.0, 1.6)
        assert r["ok"] is True
        assert abs(r["counterweight_mass_kg"] - 1400.0) < 0.01

    def test_counterweight_mass_custom_balance(self):
        """CW = 900 + 0.45×1000 = 1350 kg at 45% balance."""
        r = traction_lift(1000.0, 900.0, 1.6, counterweight_balance_pct=45.0)
        assert r["ok"] is True
        assert abs(r["counterweight_mass_kg"] - 1350.0) < 0.01

    def test_traction_ratio_full_load(self):
        """T1/T2 (full load) = (car+load) / CW for 1:1 roping."""
        r = traction_lift(1000.0, 900.0, 1.6)
        assert r["ok"] is True
        car_full = (900.0 + 1000.0) * _G
        cw = 1400.0 * _G
        expected = car_full / cw
        assert abs(r["traction_ratio_full"] - expected) < 0.001

    def test_traction_ratio_empty_car(self):
        """T1/T2 (empty) = CW / car_mass for 1:1 roping."""
        r = traction_lift(1000.0, 900.0, 1.6)
        assert r["ok"] is True
        cw = 1400.0 * _G
        car_empty = 900.0 * _G
        expected = cw / car_empty
        assert abs(r["traction_ratio_empty"] - expected) < 0.001

    def test_traction_limit_formula(self):
        """Traction limit = e^(μ_eff × α)."""
        mu = 0.09
        groove_deg = 40.0
        wrap_deg = 180.0
        # V-groove: mu_eff = mu / sin(groove_rad)
        mu_eff = mu / math.sin(math.radians(groove_deg))
        alpha = math.radians(wrap_deg)
        expected_limit = math.exp(mu_eff * alpha)
        r = traction_lift(1000.0, 900.0, 1.6, mu=mu,
                          groove_angle_deg=groove_deg, wrap_angle_deg=wrap_deg)
        assert r["ok"] is True
        assert abs(r["traction_limit"] - expected_limit) < 0.001

    def test_2to1_roping_halves_tensions(self):
        """2:1 roping halves the rope tension vs 1:1."""
        r1 = traction_lift(1000.0, 900.0, 1.6, roping=1)
        r2 = traction_lift(1000.0, 900.0, 1.6, roping=2)
        assert r1["ok"] and r2["ok"]
        # Forces should be half for 2:1
        assert abs(r2["car_side_force_full_N"] - r1["car_side_force_full_N"] / 2.0) < 0.1

    def test_sheave_dd_ratio_minimum(self):
        """Default sheave diameter gives D/d = 40."""
        r = traction_lift(1000.0, 900.0, 1.6, rope_diameter_mm=13.0)
        assert r["ok"] is True
        assert abs(r["sheave_D_d_ratio"] - 40.0) < 0.01

    def test_sheave_dd_warning_below_minimum(self):
        """Sheave below D/d=40 triggers a warning."""
        r = traction_lift(1000.0, 900.0, 1.6,
                          rope_diameter_mm=13.0, sheave_diameter_mm=400.0)
        assert r["ok"] is True
        # 400/13 = 30.8 < 40 → warning
        warn_text = " ".join(r["warnings"]).lower()
        assert "d/d" in warn_text or "d_d" in warn_text or "diameter" in warn_text.lower()

    def test_overbalance_zero_at_50pct(self):
        """Overbalance = 0 exactly at 50% balance."""
        r = traction_lift(1000.0, 900.0, 1.6, counterweight_balance_pct=50.0)
        assert r["ok"] is True
        assert abs(r["overbalance_kg"]) < 0.01

    def test_overbalance_positive_above_50pct(self):
        """55% balance → CW is heavier than 50% → positive overbalance."""
        r = traction_lift(1000.0, 900.0, 1.6, counterweight_balance_pct=55.0)
        assert r["ok"] is True
        assert r["overbalance_kg"] > 0.0

    def test_warnings_list_always_present(self):
        r = traction_lift(1000.0, 900.0, 1.6)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)

    def test_invalid_roping_returns_error(self):
        r = traction_lift(1000.0, 900.0, 1.6, roping=3)
        assert r["ok"] is False
        assert "roping" in r["reason"]

    def test_invalid_negative_load_returns_error(self):
        r = traction_lift(-100.0, 900.0, 1.6)
        assert r["ok"] is False
        assert "rated_load_kg" in r["reason"]

    def test_inadequate_traction_warns(self):
        """Very low wrap angle + high load imbalance should warn about traction."""
        # Use tiny wrap (90°) and high load ratio to force inadequate traction
        r = traction_lift(
            3000.0, 500.0, 1.0,
            wrap_angle_deg=90.0, mu=0.05, groove_angle_deg=40.0,
        )
        assert r["ok"] is True
        # Should have a warning about inadequate traction
        warn_text = " ".join(r["warnings"]).lower()
        assert "traction" in warn_text or not r["traction_adequate_full"]


# ===========================================================================
# hydraulic_lift tests
# ===========================================================================

class TestHydraulicLift:

    def test_basic_returns_ok(self):
        r = hydraulic_lift(1000.0, 800.0, 0.15, 200.0)
        assert r["ok"] is True
        assert "jack_force_N" in r
        assert "working_pressure_MPa" in r

    def test_jack_force_formula(self):
        """Jack force = (car_mass + load) × g for 1:1 roping."""
        r = hydraulic_lift(1000.0, 800.0, 0.15, 200.0, roping=1)
        assert r["ok"] is True
        expected = (1000.0 + 800.0) * _G
        assert abs(r["jack_force_N"] - expected) < 0.5

    def test_jack_force_2to1_roping(self):
        """Jack force = total_weight / 2 for 2:1 roping."""
        r = hydraulic_lift(1000.0, 800.0, 0.15, 200.0, roping=2)
        assert r["ok"] is True
        expected = (1000.0 + 800.0) * _G / 2.0
        assert abs(r["jack_force_N"] - expected) < 0.5

    def test_piston_area_formula(self):
        """A = π × d² / 4 for d = 200 mm = 0.2 m."""
        r = hydraulic_lift(1000.0, 800.0, 0.15, 200.0)
        assert r["ok"] is True
        d = 0.200  # m
        expected_area = math.pi * d ** 2 / 4.0
        assert abs(r["piston_area_m2"] - expected_area) < 1e-8

    def test_working_pressure_formula(self):
        """p = F / A."""
        r = hydraulic_lift(1000.0, 800.0, 0.15, 200.0)
        assert r["ok"] is True
        p_expected = r["jack_force_N"] / r["piston_area_m2"]
        assert abs(r["working_pressure_Pa"] - p_expected) < 1.0

    def test_proof_pressure_formula(self):
        """Proof pressure = working_pressure × safety_factor."""
        SF = 2.5
        r = hydraulic_lift(1000.0, 800.0, 0.15, 200.0, safety_factor=SF)
        assert r["ok"] is True
        expected = r["working_pressure_MPa"] * SF
        assert abs(r["proof_pressure_MPa"] - expected) < 0.001

    def test_pump_flow_formula(self):
        """Q_pump = A × jack_speed / pump_efficiency."""
        eta_p = 0.80
        r = hydraulic_lift(1000.0, 800.0, 0.15, 200.0, pump_efficiency=eta_p)
        assert r["ok"] is True
        d = 0.200  # m
        A = math.pi * d ** 2 / 4.0
        v_jack = 0.15 / 1  # m/s (1:1 roping)
        Q_ideal = A * v_jack
        Q_actual = Q_ideal / eta_p
        assert abs(r["pump_flow_m3_s"] - Q_actual) < 1e-7

    def test_pressure_warning_when_exceeded(self):
        """Warning when working pressure > max_working_pressure_MPa."""
        # Tiny piston → high pressure
        r = hydraulic_lift(2000.0, 1500.0, 0.5, 50.0, max_working_pressure_MPa=5.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "pressure" in warn_text

    def test_invalid_piston_diameter_zero(self):
        r = hydraulic_lift(1000.0, 800.0, 0.15, 0.0)
        assert r["ok"] is False

    def test_warnings_list_present(self):
        r = hydraulic_lift(1000.0, 800.0, 0.15, 200.0)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)


# ===========================================================================
# motor_power tests
# ===========================================================================

class TestMotorPower:

    def test_basic_returns_ok(self):
        r = motor_power(1000.0, 900.0, 1400.0, 1.6)
        assert r["ok"] is True
        assert "motor_power_kW" in r
        assert "worst_case_force_N" in r

    def test_net_force_full_load(self):
        """F_full = (car + load - CW) × g / roping."""
        r = motor_power(1000.0, 900.0, 1400.0, 1.6, roping=1)
        assert r["ok"] is True
        expected = (900.0 + 1000.0 - 1400.0) * _G
        assert abs(r["net_force_full_load_N"] - expected) < 0.5

    def test_net_force_empty_car(self):
        """F_empty = (car_mass - CW) × g for 1:1 roping (negative when CW heavier)."""
        r = motor_power(1000.0, 900.0, 1400.0, 1.6, roping=1)
        assert r["ok"] is True
        expected = (900.0 - 1400.0) * _G
        assert abs(r["net_force_empty_N"] - expected) < 0.5

    def test_motor_power_formula(self):
        """P = F_worst × v / η."""
        eta = 0.85
        v = 1.6
        r = motor_power(1000.0, 900.0, 1400.0, v, drive_efficiency=eta)
        assert r["ok"] is True
        P_expected = r["worst_case_force_N"] * v / eta
        assert abs(r["motor_power_W"] - P_expected) < 1.0

    def test_derated_power_formula(self):
        """Derated power = motor_power / duty_factor."""
        df = 0.8
        r = motor_power(1000.0, 900.0, 1400.0, 1.6, duty_factor=df)
        assert r["ok"] is True
        expected = r["motor_power_kW"] / df
        assert abs(r["derated_motor_power_kW"] - expected) < 0.001

    def test_starts_per_hour_warning(self):
        """Warning when starts_per_hour > 240."""
        r = motor_power(1000.0, 900.0, 1400.0, 1.6, starts_per_hour=300)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "starts" in warn_text or "240" in warn_text

    def test_invalid_rated_speed_zero(self):
        r = motor_power(1000.0, 900.0, 1400.0, 0.0)
        assert r["ok"] is False

    def test_warnings_list_present(self):
        r = motor_power(1000.0, 900.0, 1400.0, 1.6)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)


# ===========================================================================
# kinematics tests
# ===========================================================================

class TestKinematics:

    def test_basic_returns_ok(self):
        """Standard 3.3 m floor at 1.6 m/s."""
        r = kinematics(3.3, 1.6)
        assert r["ok"] is True
        assert "flight_time_s" in r
        assert "floor_to_floor_time_s" in r

    def test_floor_to_floor_includes_door_time(self):
        """floor_to_floor = flight_time + door_time."""
        t_door = 6.0
        r = kinematics(3.3, 1.6, door_time_s=t_door)
        assert r["ok"] is True
        assert abs(r["floor_to_floor_time_s"] - (r["flight_time_s"] + t_door)) < 0.001

    def test_jerk_phase_time(self):
        """t_jerk = a / j."""
        a = 1.0
        j = 2.0
        r = kinematics(5.0, 2.0, acceleration_m_s2=a, jerk_m_s3=j)
        assert r["ok"] is True
        assert abs(r["t_jerk_s"] - a / j) < 0.001

    def test_v_max_le_rated_speed(self):
        """Maximum achieved speed is always <= rated speed."""
        r = kinematics(10.0, 2.5)
        assert r["ok"] is True
        assert r["v_max_achieved_m_s"] <= 2.5 + 1e-9

    def test_short_floor_warning(self):
        """Short floor triggers warning and v_max < rated."""
        # Accel distance ≈ v²/a = 1.6²/1.0 = 2.56 m; use 1.0 m floor
        r = kinematics(0.5, 1.6)
        assert r["ok"] is True
        assert r["v_max_achieved_m_s"] < 1.6
        warn_text = " ".join(r["warnings"]).lower()
        assert "short" in warn_text or "rated speed" in warn_text or "speed" in warn_text

    def test_total_distance_conservation(self):
        """d_accel + d_constant + d_decel ≈ floor_height."""
        H = 5.0
        r = kinematics(H, 1.6)
        assert r["ok"] is True
        # d_accel_decel = 2 × d_accel, plus constant
        d_total = 2.0 * r["d_accel_m"] + r["d_constant_m"]
        assert abs(d_total - H) < 0.01

    def test_high_jerk_warning(self):
        """Jerk > 2.0 m/s³ triggers comfort warning."""
        r = kinematics(10.0, 2.0, jerk_m_s3=3.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "jerk" in warn_text or "comfort" in warn_text

    def test_high_acceleration_warning(self):
        """Acceleration > 1.5 m/s² triggers comfort warning."""
        r = kinematics(10.0, 2.0, acceleration_m_s2=2.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "acceleration" in warn_text or "comfort" in warn_text

    def test_zero_door_time_allowed(self):
        """door_time_s = 0 is valid."""
        r = kinematics(3.3, 1.6, door_time_s=0.0)
        assert r["ok"] is True
        assert abs(r["floor_to_floor_time_s"] - r["flight_time_s"]) < 0.001

    def test_invalid_floor_height(self):
        r = kinematics(-1.0, 1.6)
        assert r["ok"] is False


# ===========================================================================
# traffic_analysis tests
# ===========================================================================

class TestTrafficAnalysis:

    def test_basic_returns_ok(self):
        """10-floor office, 400 persons, 8-person car, 1.6 m/s."""
        r = traffic_analysis(10, 3.3, 400, 8, 1.6)
        assert r["ok"] is True
        assert "rtt_s" in r
        assert "interval_s" in r
        assert "handling_capacity_pct" in r

    def test_probable_stops_barney_formula(self):
        """S = N × (1 - (1 - 1/N)^P_trip) where P_trip = 0.8 × CC."""
        N = 10
        CC = 8
        P_trip = CC * 0.80  # = 6.4
        S_expected = N * (1.0 - (1.0 - 1.0 / N) ** P_trip)
        r = traffic_analysis(N, 3.3, 400, CC, 1.6)
        assert r["ok"] is True
        assert abs(r["probable_stops_S"] - S_expected) < 0.01

    def test_highest_reversal_floor(self):
        """H = N × (1 - ((N-1)/N)^P_trip)."""
        N = 10
        CC = 8
        P_trip = CC * 0.80
        H_expected = N * (1.0 - ((N - 1.0) / N) ** P_trip)
        r = traffic_analysis(N, 3.3, 400, CC, 1.6)
        assert r["ok"] is True
        assert abs(r["highest_reversal_H"] - H_expected) < 0.01

    def test_interval_single_car(self):
        """interval = rtt for a single car."""
        r = traffic_analysis(10, 3.3, 400, 8, 1.6, n_cars=1)
        assert r["ok"] is True
        assert abs(r["interval_s"] - r["rtt_s"]) < 0.001

    def test_interval_multiple_cars(self):
        """interval = rtt / n_cars."""
        r = traffic_analysis(10, 3.3, 400, 8, 1.6, n_cars=3)
        assert r["ok"] is True
        expected_interval = r["rtt_s"] / 3.0
        assert abs(r["interval_s"] - expected_interval) < 0.001

    def test_persons_per_trip(self):
        """persons_per_trip = rated_load_persons × 0.8."""
        r = traffic_analysis(10, 3.3, 400, 8, 1.6)
        assert r["ok"] is True
        assert abs(r["persons_per_trip"] - 6.4) < 0.001

    def test_handling_capacity_formula(self):
        """HC% = (persons_5min / total_pop) × 100."""
        r = traffic_analysis(10, 3.3, 400, 8, 1.6, n_cars=2)
        assert r["ok"] is True
        persons_5min = (300.0 / r["rtt_s"]) * r["persons_per_trip"] * 2
        expected_hc = (persons_5min / 400.0) * 100.0
        assert abs(r["handling_capacity_pct"] - expected_hc) < 0.1

    def test_interval_warning_when_too_long(self):
        """1-car, 20-floor building with 500 persons → long interval → warning."""
        r = traffic_analysis(20, 3.3, 500, 8, 1.0, n_cars=1)
        assert r["ok"] is True
        if r["interval_s"] > 30.0:
            warn_text = " ".join(r["warnings"]).lower()
            assert "interval" in warn_text

    def test_cars_required_for_target_interval(self):
        """n_cars_for_target returned when target_interval_s is given."""
        r = traffic_analysis(10, 3.3, 400, 8, 1.6, target_interval_s=30.0)
        assert r["ok"] is True
        assert "n_cars_for_target" in r
        assert isinstance(r["n_cars_for_target"], int)
        assert r["n_cars_for_target"] >= 1

    def test_handling_capacity_warning(self):
        """Warning when handling_capacity_pct < target."""
        r = traffic_analysis(10, 3.3, 400, 8, 1.0, n_cars=1,
                              target_handling_pct=20.0)
        assert r["ok"] is True
        if r["handling_capacity_pct"] < 20.0:
            warn_text = " ".join(r["warnings"]).lower()
            assert "handling" in warn_text or "capacity" in warn_text

    def test_invalid_n_floors_below_2(self):
        r = traffic_analysis(1, 3.3, 400, 8, 1.6)
        assert r["ok"] is False

    def test_invalid_negative_persons(self):
        r = traffic_analysis(10, 3.3, -1, 8, 1.6)
        assert r["ok"] is False

    def test_warnings_list_present(self):
        r = traffic_analysis(10, 3.3, 400, 8, 1.6)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)


# ===========================================================================
# buffer_stroke tests
# ===========================================================================

class TestBufferStroke:

    def test_basic_returns_ok(self):
        r = buffer_stroke(1.6)
        assert r["ok"] is True
        assert "buffer_stroke_min_mm" in r
        assert "governor_trip_speed_m_s" in r

    def test_governor_trip_speed_default_factor(self):
        """Trip speed = rated_speed × factor."""
        v = 2.5
        factor = 1.10
        r = buffer_stroke(v, overspeed_governor_factor=factor)
        assert r["ok"] is True
        assert abs(r["governor_trip_speed_m_s"] - v * factor) < 0.001

    def test_buffer_impact_speed_equals_trip_speed(self):
        """Buffer impact speed = governor trip speed (worst case)."""
        r = buffer_stroke(2.5)
        assert r["ok"] is True
        assert abs(r["buffer_impact_speed_m_s"] - r["governor_trip_speed_m_s"]) < 0.001

    def test_oil_buffer_absolute_minimum_420mm(self):
        """Oil buffer absolute minimum is 420 mm per EN 81-1."""
        # At slow speed the formula gives < 420 mm
        r = buffer_stroke(0.3, buffer_type="oil")
        assert r["ok"] is True
        assert r["buffer_stroke_min_mm"] >= 420.0

    def test_spring_buffer_absolute_minimum_150mm(self):
        """Spring/polyurethane buffer absolute minimum is 150 mm."""
        r = buffer_stroke(0.3, buffer_type="spring")
        assert r["ok"] is True
        assert r["buffer_stroke_min_mm"] >= 150.0

    def test_buffer_stroke_scales_with_speed(self):
        """Faster lifts need longer buffer strokes."""
        r_slow = buffer_stroke(1.0, buffer_type="oil")
        r_fast = buffer_stroke(4.0, buffer_type="oil")
        assert r_slow["ok"] and r_fast["ok"]
        assert r_fast["buffer_stroke_min_mm"] > r_slow["buffer_stroke_min_mm"]

    def test_governor_factor_warning_below_115pct(self):
        """Factor < 1.115 should trigger EN 81-1 §10.4.1 warning."""
        r = buffer_stroke(2.0, overspeed_governor_factor=1.10)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "115" in warn_text or "minimum" in warn_text

    def test_safety_gear_stop_distance_positive(self):
        r = buffer_stroke(2.5)
        assert r["ok"] is True
        assert r["safety_gear_stop_distance_m"] > 0.0

    def test_safety_gear_stop_distance_formula(self):
        """d = v_impact² / (2 × 0.5g)."""
        v = 2.5
        factor = 1.115
        r = buffer_stroke(v, overspeed_governor_factor=factor)
        assert r["ok"] is True
        v_impact = r["buffer_impact_speed_m_s"]
        expected_d = v_impact ** 2 / (2.0 * 0.5 * _G)
        assert abs(r["safety_gear_stop_distance_m"] - expected_d) < 0.001

    def test_invalid_speed_zero(self):
        r = buffer_stroke(0.0)
        assert r["ok"] is False

    def test_invalid_buffer_type(self):
        r = buffer_stroke(2.0, buffer_type="rubber")
        assert r["ok"] is False

    def test_warnings_list_present(self):
        r = buffer_stroke(2.0)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)


# ===========================================================================
# escalator tests
# ===========================================================================

class TestEscalator:

    def test_basic_returns_ok(self):
        """Standard 800 mm step, 0.5 m/s, 4 m rise, 30°."""
        r = escalator(0.80, 0.5, 4.0)
        assert r["ok"] is True
        assert "theoretical_capacity_pph" in r
        assert "motor_power_kW" in r

    def test_escalator_length_formula(self):
        """L = rise / sin(inclination)."""
        rise = 5.0
        phi_deg = 30.0
        r = escalator(0.80, 0.5, rise, inclination_deg=phi_deg)
        assert r["ok"] is True
        expected_L = rise / math.sin(math.radians(phi_deg))
        assert abs(r["escalator_length_m"] - expected_L) < 0.01

    def test_theoretical_capacity_formula(self):
        """Q_theory = pps × (v / step_pitch) × 3600."""
        # 800 mm step → pps=1.5; step_pitch = 0.4 / cos(30°)
        w = 0.80
        v = 0.5
        sd = 0.40
        phi = math.radians(30.0)
        step_pitch = sd / math.cos(phi)
        pps = 1.5  # 800 mm step
        expected_Q = pps * (v / step_pitch) * 3600.0
        r = escalator(w, v, 4.0, inclination_deg=30.0)
        assert r["ok"] is True
        assert abs(r["theoretical_capacity_pph"] - expected_Q) < 1.0

    def test_actual_capacity_with_utilisation(self):
        """Actual = theoretical × utilisation_factor."""
        r = escalator(0.80, 0.5, 4.0, utilisation_factor=0.8)
        assert r["ok"] is True
        expected = r["theoretical_capacity_pph"] * 0.8
        assert abs(r["actual_capacity_pph"] - expected) < 1.0

    def test_over_incline_escalator_warning(self):
        """Incline > 30° for rise ≤ 6 m triggers EN 115-1 warning."""
        r = escalator(0.80, 0.5, 4.0, inclination_deg=35.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "inclin" in warn_text or "en 115" in warn_text or "limit" in warn_text

    def test_over_speed_warning(self):
        """Speed > 0.75 m/s for escalator triggers EN 115-1 warning."""
        r = escalator(0.80, 0.90, 4.0)
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "speed" in warn_text or "0.75" in warn_text

    def test_lift_power_positive(self):
        """Power must be positive for a rising escalator."""
        r = escalator(0.80, 0.5, 4.0)
        assert r["ok"] is True
        assert r["lift_power_W"] > 0.0

    def test_motor_power_gt_total_power(self):
        """Motor power >= total power (includes efficiency loss)."""
        r = escalator(0.80, 0.5, 4.0, drive_efficiency=0.85)
        assert r["ok"] is True
        assert r["motor_power_kW"] >= r["total_power_kW"] - 1e-6

    def test_moving_walk_incline_limit(self):
        """Moving walk at 15° inclination triggers EN 115-1 warning (limit 12°)."""
        r = escalator(0.80, 0.5, 2.0, inclination_deg=15.0, escalator_type="moving_walk")
        assert r["ok"] is True
        warn_text = " ".join(r["warnings"]).lower()
        assert "inclin" in warn_text or "en 115" in warn_text or "limit" in warn_text

    def test_capacity_warning_when_below_target(self):
        """Warning when actual capacity < target."""
        r = escalator(0.60, 0.3, 4.0, target_capacity_pph=5000.0)
        assert r["ok"] is True
        if r["actual_capacity_pph"] < 5000.0:
            warn_text = " ".join(r["warnings"]).lower()
            assert "capacity" in warn_text or "target" in warn_text

    def test_invalid_negative_rise(self):
        r = escalator(0.80, 0.5, -1.0)
        assert r["ok"] is False

    def test_invalid_escalator_type(self):
        r = escalator(0.80, 0.5, 4.0, escalator_type="travelator")
        assert r["ok"] is False

    def test_warnings_list_present(self):
        r = escalator(0.80, 0.5, 4.0)
        assert r["ok"] is True
        assert isinstance(r["warnings"], list)


# ===========================================================================
# LLM tool wrapper tests
# ===========================================================================

class TestTractionLiftTool:

    def test_happy_path(self):
        result = _run(run_traction_lift(_ctx(), _args(
            rated_load_kg=1000.0, car_mass_kg=900.0, rated_speed_m_s=1.6,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert "counterweight_mass_kg" in r

    def test_missing_car_mass_returns_error(self):
        result = _run(run_traction_lift(_ctx(), _args(
            rated_load_kg=1000.0, rated_speed_m_s=1.6,
        )))
        r = json.loads(result)
        assert r["ok"] is False
        assert "car_mass_kg" in r["reason"]

    def test_invalid_json_returns_error(self):
        result = _run(run_traction_lift(_ctx(), b"not_json"))
        r = json.loads(result)
        assert _is_error_response(r)


class TestHydraulicLiftTool:

    def test_happy_path(self):
        result = _run(run_hydraulic_lift(_ctx(), _args(
            rated_load_kg=1000.0, car_mass_kg=800.0,
            rated_speed_m_s=0.15, piston_diameter_mm=200.0,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert "working_pressure_MPa" in r

    def test_missing_piston_diameter_returns_error(self):
        result = _run(run_hydraulic_lift(_ctx(), _args(
            rated_load_kg=1000.0, car_mass_kg=800.0, rated_speed_m_s=0.15,
        )))
        r = json.loads(result)
        assert r["ok"] is False
        assert "piston_diameter_mm" in r["reason"]

    def test_invalid_json_returns_error(self):
        result = _run(run_hydraulic_lift(_ctx(), b"{bad"))
        r = json.loads(result)
        assert _is_error_response(r)


class TestMotorPowerTool:

    def test_happy_path(self):
        result = _run(run_motor_power(_ctx(), _args(
            rated_load_kg=1000.0, car_mass_kg=900.0,
            counterweight_mass_kg=1400.0, rated_speed_m_s=1.6,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert "motor_power_kW" in r

    def test_missing_counterweight_returns_error(self):
        result = _run(run_motor_power(_ctx(), _args(
            rated_load_kg=1000.0, car_mass_kg=900.0, rated_speed_m_s=1.6,
        )))
        r = json.loads(result)
        assert r["ok"] is False
        assert "counterweight_mass_kg" in r["reason"]

    def test_invalid_json_returns_error(self):
        result = _run(run_motor_power(_ctx(), b""))
        r = json.loads(result)
        assert _is_error_response(r)


class TestKinematicsTool:

    def test_happy_path(self):
        result = _run(run_kinematics(_ctx(), _args(
            floor_height_m=3.3, rated_speed_m_s=1.6,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert "floor_to_floor_time_s" in r

    def test_missing_rated_speed_returns_error(self):
        result = _run(run_kinematics(_ctx(), _args(floor_height_m=3.3)))
        r = json.loads(result)
        assert r["ok"] is False
        assert "rated_speed_m_s" in r["reason"]

    def test_invalid_json_returns_error(self):
        result = _run(run_kinematics(_ctx(), b"not json"))
        r = json.loads(result)
        assert _is_error_response(r)


class TestTrafficAnalysisTool:

    def test_happy_path(self):
        result = _run(run_traffic_analysis(_ctx(), _args(
            n_floors=10, floor_height_m=3.3, n_persons=400,
            rated_load_persons=8, rated_speed_m_s=1.6,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert "rtt_s" in r

    def test_missing_n_persons_returns_error(self):
        result = _run(run_traffic_analysis(_ctx(), _args(
            n_floors=10, floor_height_m=3.3,
            rated_load_persons=8, rated_speed_m_s=1.6,
        )))
        r = json.loads(result)
        assert r["ok"] is False
        assert "n_persons" in r["reason"]

    def test_invalid_json_returns_error(self):
        result = _run(run_traffic_analysis(_ctx(), b""))
        r = json.loads(result)
        assert _is_error_response(r)


class TestBufferStrokeTool:

    def test_happy_path(self):
        result = _run(run_buffer_stroke(_ctx(), _args(rated_speed_m_s=2.5)))
        r = json.loads(result)
        assert r["ok"] is True
        assert "buffer_stroke_min_mm" in r

    def test_missing_speed_returns_error(self):
        result = _run(run_buffer_stroke(_ctx(), _args(buffer_type="oil")))
        r = json.loads(result)
        assert r["ok"] is False
        assert "rated_speed_m_s" in r["reason"]

    def test_invalid_json_returns_error(self):
        result = _run(run_buffer_stroke(_ctx(), b"xyz"))
        r = json.loads(result)
        assert _is_error_response(r)


class TestEscalatorTool:

    def test_happy_path(self):
        result = _run(run_escalator(_ctx(), _args(
            step_width_m=0.80, belt_speed_m_s=0.5, rise_m=4.0,
        )))
        r = json.loads(result)
        assert r["ok"] is True
        assert "actual_capacity_pph" in r

    def test_missing_rise_returns_error(self):
        result = _run(run_escalator(_ctx(), _args(
            step_width_m=0.80, belt_speed_m_s=0.5,
        )))
        r = json.loads(result)
        assert r["ok"] is False
        assert "rise_m" in r["reason"]

    def test_invalid_json_returns_error(self):
        result = _run(run_escalator(_ctx(), b"["))
        r = json.loads(result)
        assert _is_error_response(r)
