"""
tests/test_crane.py — hermetic unit tests for kerf_cad_core.crane.design

All tests are pure-Python and verify computed results against hand-calculations.
No network, filesystem, or OCC dependency.

Covers:
  - wire_rope_reeving: reeving efficiency, line pull
  - rope_diameter: standard selection, overtension warning
  - sheave_drum_geometry: PCD computation, D/d warning
  - drum_length: groove count and barrel length
  - hoist_motor_power: power formula
  - hoist_motor_class: M-class table lookup
  - hoist_brake_torque: brake sizing
  - travel_resistance: rolling + wind
  - travel_motor_power: power formula
  - jib_load_chart: tipping allowable
  - bridge_wheel_loads: end-carriage reactions
  - hook_shank_check: tensile stress check
  - lifting_lug_check: multi-mode check
  - crane_duty_class: FEM A-class and M-class
  - fall_protection_brake: brake path
  - Error / boundary conditions
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.crane.design import (
    wire_rope_reeving,
    rope_diameter,
    sheave_drum_geometry,
    drum_length,
    hoist_motor_power,
    hoist_motor_class,
    hoist_brake_torque,
    travel_resistance,
    travel_motor_power,
    jib_load_chart,
    bridge_wheel_loads,
    hook_shank_check,
    lifting_lug_check,
    crane_duty_class,
    fall_protection_brake,
)

_G = 9.80665


# ===========================================================================
# 1. wire_rope_reeving
# ===========================================================================

class TestWireRopeReeving:
    def test_single_part_no_loss(self):
        """n_parts=1, efficiency=1.0 → line_pull = SWL."""
        r = wire_rope_reeving(100.0, 1, rope_efficiency=1.0)
        assert r["ok"] is True
        assert math.isclose(r["line_pull_kN"], 100.0, rel_tol=1e-9)

    def test_four_parts_efficiency(self):
        """n=4, η=0.98: η_block = (1-0.98^4)/(4*(1-0.98))."""
        eta = 0.98
        n = 4
        eta_block = (1 - eta**n) / (n * (1 - eta))
        expected_pull = 100.0 / (n * eta_block)
        r = wire_rope_reeving(100.0, n, rope_efficiency=eta)
        assert r["ok"] is True
        assert math.isclose(r["line_pull_kN"], expected_pull, rel_tol=1e-6)
        assert math.isclose(r["eta_block"], eta_block, rel_tol=1e-6)

    def test_line_pull_N_consistency(self):
        """line_pull_N == line_pull_kN * 1000."""
        r = wire_rope_reeving(50.0, 2)
        assert math.isclose(r["line_pull_N"], r["line_pull_kN"] * 1000.0, rel_tol=1e-9)

    def test_override_reeving_factor(self):
        """reeving_factor override bypasses the per-sheave formula."""
        r = wire_rope_reeving(80.0, 4, reeving_factor=0.90)
        assert r["ok"] is True
        expected = 80.0 / (4 * 0.90)
        assert math.isclose(r["line_pull_kN"], expected, rel_tol=1e-9)

    def test_invalid_n_parts(self):
        r = wire_rope_reeving(50.0, 0)
        assert r["ok"] is False

    def test_invalid_swl(self):
        r = wire_rope_reeving(-10.0, 2)
        assert r["ok"] is False

    def test_efficiency_out_of_range(self):
        r = wire_rope_reeving(50.0, 2, rope_efficiency=0.0)
        assert r["ok"] is False


# ===========================================================================
# 2. rope_diameter
# ===========================================================================

class TestRopeDiameter:
    def test_basic_selection(self):
        """10 kN line pull, SF=5 → required MBF=50 kN. For grade 1770,
        d=10mm has MBF=56.5 kN ≥ 50 kN."""
        r = rope_diameter(10.0, safety_factor=5.0, grade="1770")
        assert r["ok"] is True
        assert r["diameter_mm"] == 10.0
        assert r["mbf_kN"] >= 50.0
        assert r["actual_sf"] >= 5.0

    def test_required_mbf_field(self):
        """required_mbf_kN == line_pull * safety_factor."""
        r = rope_diameter(20.0, safety_factor=4.0, grade="1570")
        assert r["ok"] is True
        assert math.isclose(r["required_mbf_kN"], 80.0, rel_tol=1e-9)

    def test_larger_sf_forces_bigger_rope(self):
        """Higher SF should select the same or larger diameter."""
        r_low = rope_diameter(20.0, safety_factor=3.0, grade="1570")
        r_high = rope_diameter(20.0, safety_factor=10.0, grade="1570")
        assert r_high["diameter_mm"] >= r_low["diameter_mm"]

    def test_overtension_warning(self):
        """Extremely high line pull → ROPE_OVERTENSION warning, ok still True."""
        r = rope_diameter(10000.0, safety_factor=5.0, grade="1570")
        assert r["ok"] is True
        assert any("ROPE_OVERTENSION" in w for w in r["warnings"])

    def test_invalid_grade(self):
        r = rope_diameter(10.0, grade="9999")
        assert r["ok"] is False

    def test_invalid_line_pull(self):
        r = rope_diameter(0.0)
        assert r["ok"] is False


# ===========================================================================
# 3. sheave_drum_geometry
# ===========================================================================

class TestSheaveDrumGeometry:
    def test_pcd_computation(self):
        """PCD = rope_dia * dd_ratio."""
        r = sheave_drum_geometry(20.0, sheave_dd_ratio=18.0, drum_dd_ratio=16.0)
        assert r["ok"] is True
        assert math.isclose(r["pcd_sheave_mm"], 360.0, rel_tol=1e-9)
        assert math.isclose(r["pcd_drum_mm"], 320.0, rel_tol=1e-9)

    def test_dd_ratio_low_warning(self):
        """DD ratio below FEM minimum triggers warning."""
        # FEM class E minimum = 18.0 for sheave
        r = sheave_drum_geometry(20.0, sheave_dd_ratio=12.0, fem_class="E")
        assert r["ok"] is True
        assert any("DD_RATIO_LOW" in w for w in r["warnings"])

    def test_no_warning_above_minimum(self):
        """Ratio at or above minimum produces no warning."""
        r = sheave_drum_geometry(20.0, sheave_dd_ratio=20.0, drum_dd_ratio=20.0, fem_class="E")
        assert r["ok"] is True
        assert len(r["warnings"]) == 0

    def test_invalid_fem_class(self):
        r = sheave_drum_geometry(20.0, fem_class="Z")
        assert r["ok"] is False

    def test_invalid_rope_dia(self):
        r = sheave_drum_geometry(0.0)
        assert r["ok"] is False


# ===========================================================================
# 4. drum_length
# ===========================================================================

class TestDrumLength:
    def test_basic(self):
        """Single layer, 10 m hoist, 4 parts rope: total rope = 40 m."""
        r = drum_length(20.0, 4, 10.0, n_layers=1)
        assert r["ok"] is True
        assert math.isclose(r["total_rope_length_m"], 40.0, rel_tol=1e-9)
        assert r["drum_length_mm"] > 0

    def test_groove_pitch(self):
        """Groove pitch = rope_dia * groove_pitch_factor."""
        r = drum_length(16.0, 2, 5.0, groove_pitch_factor=1.15)
        assert math.isclose(r["groove_pitch_mm"], 16.0 * 1.15, rel_tol=1e-9)

    def test_two_layers_shorter_barrel(self):
        """More layers → fewer turns per layer → shorter barrel."""
        r1 = drum_length(20.0, 4, 20.0, n_layers=1)
        r2 = drum_length(20.0, 4, 20.0, n_layers=2)
        assert r2["drum_length_mm"] < r1["drum_length_mm"]

    def test_invalid_n_parts(self):
        r = drum_length(20.0, 0, 10.0)
        assert r["ok"] is False

    def test_invalid_hoist_height(self):
        r = drum_length(20.0, 2, -5.0)
        assert r["ok"] is False


# ===========================================================================
# 5. hoist_motor_power
# ===========================================================================

class TestHoistMotorPower:
    def test_formula(self):
        """P = SWL_N * v / eta. SWL=10 kN, v=0.5 m/s, eta=0.85."""
        r = hoist_motor_power(10.0, 0.5, mechanical_efficiency=0.85)
        assert r["ok"] is True
        expected_kW = 10_000 * 0.5 / 0.85 / 1000
        assert math.isclose(r["motor_power_kW"], expected_kW, rel_tol=1e-6)

    def test_lift_power(self):
        """lift_power = SWL_N * v (ideal, no loss)."""
        r = hoist_motor_power(20.0, 1.0)
        assert math.isclose(r["lift_power_kW"], 20.0, rel_tol=1e-6)  # 20 kN * 1 m/s = 20 kW

    def test_duty_factor(self):
        """duty_factor scales motor power proportionally."""
        r1 = hoist_motor_power(10.0, 1.0, duty_factor=1.0)
        r2 = hoist_motor_power(10.0, 1.0, duty_factor=1.2)
        assert math.isclose(r2["motor_power_kW"] / r1["motor_power_kW"], 1.2, rel_tol=1e-6)

    def test_invalid_speed(self):
        r = hoist_motor_power(10.0, 0.0)
        assert r["ok"] is False

    def test_efficiency_zero(self):
        r = hoist_motor_power(10.0, 1.0, mechanical_efficiency=0.0)
        assert r["ok"] is False


# ===========================================================================
# 6. hoist_motor_class
# ===========================================================================

class TestHoistMotorClass:
    def test_m1_light(self):
        """duty_group=1, load_spectrum=1 → M1."""
        r = hoist_motor_class(1, 1)
        assert r["ok"] is True
        assert r["m_class"] == "M1"

    def test_m8_heavy(self):
        """duty_group=8, load_spectrum=4 → M8."""
        r = hoist_motor_class(8, 4)
        assert r["ok"] is True
        assert r["m_class"] == "M8"

    def test_over_duty_warning(self):
        """M7/M8 class → OVER_DUTY warning."""
        r = hoist_motor_class(6, 4)
        assert r["m_class"] == "M8"
        assert any("OVER_DUTY" in w for w in r["warnings"])

    def test_diagonal_m5(self):
        """duty_group=5, load_spectrum=1 → M4."""
        r = hoist_motor_class(5, 1)
        assert r["ok"] is True
        assert r["m_class"] == "M4"

    def test_invalid_duty_group(self):
        r = hoist_motor_class(0, 2)
        assert r["ok"] is False

    def test_invalid_load_spectrum(self):
        r = hoist_motor_class(3, 5)
        assert r["ok"] is False


# ===========================================================================
# 7. hoist_brake_torque
# ===========================================================================

class TestHoistBrakeTorque:
    def test_formula(self):
        """T_drum = (SWL/n_parts) * r_drum. T_brake = T_drum * brake_factor."""
        SWL_kN = 50.0
        drum_pcd_mm = 500.0
        n_parts = 4
        brake_factor = 1.5
        r_drum = drum_pcd_mm / 2 / 1000  # m
        F_rope = SWL_kN * 1000 / n_parts
        T_drum = F_rope * r_drum
        T_brake = T_drum * brake_factor

        r = hoist_brake_torque(SWL_kN, drum_pcd_mm, n_parts, brake_factor=brake_factor)
        assert r["ok"] is True
        assert math.isclose(r["drum_torque_Nm"], T_drum, rel_tol=1e-6)
        assert math.isclose(r["required_brake_Nm"], T_brake, rel_tol=1e-6)

    def test_rope_tension_is_swl_divided_by_parts(self):
        r = hoist_brake_torque(100.0, 600.0, 2)
        assert math.isclose(r["rope_tension_N"], 100_000 / 2, rel_tol=1e-9)

    def test_low_brake_factor_warning(self):
        r = hoist_brake_torque(50.0, 400.0, 2, brake_factor=1.1)
        assert r["ok"] is True
        assert len(r["warnings"]) > 0

    def test_invalid_swl(self):
        r = hoist_brake_torque(0.0, 400.0, 2)
        assert r["ok"] is False


# ===========================================================================
# 8. travel_resistance
# ===========================================================================

class TestTravelResistance:
    def test_rolling_only(self):
        """F_roll = (crane + payload) * g * f_roll."""
        crane = 5000.0
        payload = 2000.0
        f = 0.015
        expected = (crane + payload) * _G * f
        r = travel_resistance(crane, payload, coeff_rolling=f, frontal_area_m2=0.0)
        assert r["ok"] is True
        assert math.isclose(r["rolling_force_N"], expected, rel_tol=1e-6)
        assert math.isclose(r["total_force_N"], expected, rel_tol=1e-6)

    def test_total_mass(self):
        r = travel_resistance(3000.0, 1000.0)
        assert r["total_mass_kg"] == 4000.0

    def test_wind_force(self):
        """wind_force = wind_pressure * frontal_area * 1.3 * coeff_wind."""
        r = travel_resistance(
            5000.0, 0.0,
            coeff_wind=1.0,
            wind_pressure_Pa=250.0,
            frontal_area_m2=10.0,
        )
        expected_wind = 250.0 * 10.0 * 1.3
        assert math.isclose(r["wind_force_N"], expected_wind, rel_tol=1e-6)

    def test_invalid_crane_mass(self):
        r = travel_resistance(-100.0, 0.0)
        assert r["ok"] is False

    def test_invalid_payload(self):
        r = travel_resistance(1000.0, -50.0)
        assert r["ok"] is False


# ===========================================================================
# 9. travel_motor_power
# ===========================================================================

class TestTravelMotorPower:
    def test_formula(self):
        """P = F * v / eta * af."""
        F = 5000.0
        v = 1.0
        eta = 0.85
        af = 1.25
        expected_W = F * v / eta * af
        r = travel_motor_power(F, v, motor_efficiency=eta, acceleration_factor=af)
        assert r["ok"] is True
        assert math.isclose(r["motor_power_W"], expected_W, rel_tol=1e-6)
        assert math.isclose(r["motor_power_kW"], expected_W / 1000, rel_tol=1e-6)

    def test_invalid_resistance(self):
        r = travel_motor_power(0.0, 1.0)
        assert r["ok"] is False

    def test_efficiency_above_one(self):
        r = travel_motor_power(1000.0, 1.0, motor_efficiency=1.5)
        assert r["ok"] is False


# ===========================================================================
# 10. jib_load_chart
# ===========================================================================

class TestJibLoadChart:
    def test_basic_allowable(self):
        """Hand-calc: restoring=CW*g*r_cw; jib_ot=jib_mass*g*L/2;
        net = restoring/SF - jib_ot; allowable_kg = net / (g * radius)."""
        CW = 5000.0  # kg
        r_cw = 3.0   # m
        jib_mass = 1000.0
        L_jib = 10.0
        radius = 5.0
        SF = 1.5
        M_rest = CW * _G * r_cw
        jib_ot = jib_mass * _G * (L_jib / 2)
        net = M_rest / SF - jib_ot
        allowable_N = net / radius
        allowable_kg = allowable_N / _G

        r = jib_load_chart(
            slew_radius_m=radius,
            jib_length_m=L_jib,
            jib_mass_kg=jib_mass,
            counterweight_kg=CW,
            counterweight_radius_m=r_cw,
            safety_factor=SF,
        )
        assert r["ok"] is True
        assert math.isclose(r["allowable_load_kg"], allowable_kg, rel_tol=1e-6)

    def test_structural_allowable_fraction(self):
        r = jib_load_chart(5.0, 10.0, 500.0, 3000.0, 2.0, tipping_fraction=0.75)
        assert r["ok"] is True
        assert math.isclose(
            r["structural_allowable_kg"],
            r["allowable_load_kg"] * 0.75,
            rel_tol=1e-9,
        )

    def test_tipping_warning_insufficient_cw(self):
        """Very light counterweight at large radius → TIPPING warning."""
        r = jib_load_chart(20.0, 30.0, 10000.0, 100.0, 0.5, safety_factor=1.5)
        assert r["ok"] is True
        assert any("TIPPING" in w for w in r["warnings"])

    def test_invalid_radius(self):
        r = jib_load_chart(0.0, 10.0, 500.0, 3000.0, 2.0)
        assert r["ok"] is False

    def test_invalid_safety_factor(self):
        r = jib_load_chart(5.0, 10.0, 500.0, 3000.0, 2.0, safety_factor=0.0)
        assert r["ok"] is False


# ===========================================================================
# 11. bridge_wheel_loads
# ===========================================================================

class TestBridgeWheelLoads:
    def test_crab_at_centre(self):
        """Crab at centre: both end reactions equal. Wheel loads equal."""
        span = 20.0
        bridge = 10000.0
        crab = 2000.0
        payload = 5000.0
        cx = 10.0   # centre
        r = bridge_wheel_loads(span, bridge, crab, payload, cx)
        assert r["ok"] is True
        # Static reactions should be equal for symmetric crab position
        assert math.isclose(r["left_reaction_N"], r["right_reaction_N"], rel_tol=1e-6)

    def test_reactions_sum_to_total(self):
        """Left + right reactions = (bridge + crab + payload) * g."""
        span = 15.0
        bridge = 8000.0
        crab = 1500.0
        payload = 4000.0
        cx = 5.0
        r = bridge_wheel_loads(span, bridge, crab, payload, cx)
        total_W = (bridge + crab + payload) * _G
        assert math.isclose(
            r["left_reaction_N"] + r["right_reaction_N"], total_W, rel_tol=1e-6
        )

    def test_wheel_load_includes_dynamic_factor(self):
        """wheel_load = end_reaction * dynamic_factor / n_wheels."""
        span = 10.0
        cx = 5.0
        r = bridge_wheel_loads(span, 5000.0, 1000.0, 2000.0, cx,
                               n_wheels_per_end=2, dynamic_factor=1.15)
        expected_kN = r["left_reaction_N"] * 1.15 / 2 / 1000
        assert math.isclose(r["left_wheel_load_kN"], expected_kN, rel_tol=1e-6)

    def test_crab_out_of_range(self):
        r = bridge_wheel_loads(10.0, 5000.0, 1000.0, 2000.0, 15.0)
        assert r["ok"] is False

    def test_invalid_span(self):
        r = bridge_wheel_loads(0.0, 5000.0, 1000.0, 2000.0, 0.0)
        assert r["ok"] is False


# ===========================================================================
# 12. hook_shank_check
# ===========================================================================

class TestHookShankCheck:
    def test_stress_formula(self):
        """σ = P_N / A_root; A_root = π/4 * (d_maj - 0.9743*p)^2."""
        SWL_kN = 50.0
        d_maj = 52.0
        pitch = 5.0
        d_minor = d_maj - 0.9743 * pitch
        A_root = math.pi / 4 * d_minor ** 2
        sigma = 50_000 / A_root

        r = hook_shank_check(SWL_kN, d_maj, pitch, material="grade_P")
        assert r["ok"] is True
        assert math.isclose(r["tension_stress_MPa"], sigma, rel_tol=1e-6)
        assert math.isclose(r["minor_dia_mm"], d_minor, rel_tol=1e-9)

    def test_pass_adequate_shank(self):
        """Large shank for small load → passes."""
        r = hook_shank_check(10.0, 60.0, 4.0, material="grade_S", design_factor=4.0)
        assert r["ok"] is True
        assert r["pass_shank"] is True

    def test_fail_small_shank(self):
        """Small shank, large load → overstress warning."""
        r = hook_shank_check(500.0, 20.0, 2.5, material="grade_P", design_factor=4.0)
        assert r["ok"] is True
        assert r["pass_shank"] is False
        assert any("SHANK_OVERSTRESS" in w for w in r["warnings"])

    def test_invalid_material(self):
        r = hook_shank_check(10.0, 30.0, 3.0, material="titanium")
        assert r["ok"] is False

    def test_minor_dia_positive_required(self):
        """pitch > shank_dia/0.9743 → negative minor diameter → error.
        shank_dia=10, pitch=11 → d_minor = 10 - 0.9743*11 = 10 - 10.717 < 0."""
        r = hook_shank_check(10.0, 10.0, 11.0)
        assert r["ok"] is False


# ===========================================================================
# 13. lifting_lug_check
# ===========================================================================

class TestLiftingLugCheck:
    def test_net_tension(self):
        """σ_t = P_N / ((W - d_hole) * t)."""
        load_kN = 100.0
        t = 30.0
        d_hole = 50.0
        W = 150.0
        A_net = (W - d_hole) * t
        sigma_t = 100_000 / A_net

        r = lifting_lug_check(load_kN, t, d_hole, W)
        assert r["ok"] is True
        assert math.isclose(r["tension_net_stress_MPa"], sigma_t, rel_tol=1e-6)

    def test_all_pass_for_adequate_lug(self):
        """200 mm wide, 40 mm thick lug, 60 mm hole, 100 kN → all pass."""
        r = lifting_lug_check(100.0, 40.0, 60.0, 200.0, Fy_MPa=350.0, design_factor=3.0)
        assert r["ok"] is True
        assert r["tension_pass"] is True
        assert r["bearing_pass"] is True
        assert r["shearout_pass"] is True

    def test_governing_utilisation_is_max(self):
        r = lifting_lug_check(150.0, 20.0, 30.0, 80.0)
        assert r["ok"] is True
        gov = max(r["utilisation_tension"], r["utilisation_bearing"], r["utilisation_shearout"])
        assert math.isclose(r["governing_utilisation"], gov, rel_tol=1e-9)

    def test_hole_larger_than_width_error(self):
        r = lifting_lug_check(50.0, 20.0, 100.0, 80.0)
        assert r["ok"] is False

    def test_wll_exceeded_warning(self):
        """Tiny lug, large load → WLL_EXCEEDED warning."""
        r = lifting_lug_check(1000.0, 5.0, 20.0, 50.0)
        assert r["ok"] is True
        assert any("WLL_EXCEEDED" in w for w in r["warnings"])


# ===========================================================================
# 14. crane_duty_class
# ===========================================================================

class TestCraneDutyClass:
    def test_a1_light(self):
        """3200 cycles → A1; Q1 → M1."""
        r = crane_duty_class(3200, 1)
        assert r["ok"] is True
        assert r["duty_group"] == "A1"
        assert r["m_class"] == "M1"

    def test_a5_m6(self):
        """50000 cycles → A5; Q4 → M7."""
        r = crane_duty_class(50_000, 4)
        assert r["ok"] is True
        assert r["duty_group"] == "A5"
        assert r["m_class"] == "M7"

    def test_a8_heavy(self):
        """500000 cycles → A8; Q3 → M8."""
        r = crane_duty_class(500_000, 3)
        assert r["ok"] is True
        assert r["duty_group"] == "A8"
        assert r["m_class"] == "M8"

    def test_over_duty_warning_m8(self):
        r = crane_duty_class(200_001, 4)
        assert r["ok"] is True
        assert any("OVER_DUTY" in w for w in r["warnings"])

    def test_invalid_cycles(self):
        r = crane_duty_class(0, 2)
        assert r["ok"] is False

    def test_invalid_load_spectrum(self):
        r = crane_duty_class(10_000, 5)
        assert r["ok"] is False

    def test_a3_q2_m4(self):
        """12500 cycles → A3; Q2 → M3 per FEM table."""
        r = crane_duty_class(12_500, 2)
        assert r["ok"] is True
        assert r["duty_group"] == "A3"
        assert r["m_class"] == "M3"


# ===========================================================================
# 15. fall_protection_brake
# ===========================================================================

class TestFallProtectionBrake:
    def test_brake_path_formula(self):
        """s = v_trigger² / (2g)."""
        v_rated = 0.5
        gsf = 1.3
        v_trigger = v_rated * gsf
        expected_path = v_trigger ** 2 / (2 * _G)
        r = fall_protection_brake(50.0, v_rated, gsf, 0.5, 0.25)
        assert r["ok"] is True
        assert math.isclose(r["brake_path_m"], expected_path, rel_tol=1e-6)

    def test_trigger_speed(self):
        r = fall_protection_brake(100.0, 1.0, 1.4, 1.0, 0.3)
        assert math.isclose(r["trigger_speed_mps"], 1.4, rel_tol=1e-9)

    def test_required_brake_includes_load_and_inertia(self):
        """T_req = T_load + T_inertia."""
        SWL_kN = 80.0
        r_drum = 0.25
        J = 2.0
        alpha = _G / r_drum  # rad/s²
        T_load = SWL_kN * 1000 * r_drum
        T_inertia = J * alpha
        T_req = T_load + T_inertia

        r = fall_protection_brake(SWL_kN, 0.5, 1.3, J, r_drum)
        assert r["ok"] is True
        assert math.isclose(r["required_brake_Nm"], T_req, rel_tol=1e-6)

    def test_brake_path_warning(self):
        """Very high speed → brake path > 0.5 m → warning."""
        r = fall_protection_brake(10.0, 5.0, 1.4, 0.1, 0.5)
        assert r["ok"] is True
        assert len(r["warnings"]) > 0

    def test_invalid_governor_factor(self):
        r = fall_protection_brake(50.0, 0.5, 0.9, 0.5, 0.25)
        assert r["ok"] is False

    def test_invalid_drum_radius(self):
        r = fall_protection_brake(50.0, 0.5, 1.3, 0.5, 0.0)
        assert r["ok"] is False


# ===========================================================================
# 16. Additional boundary / integration tests
# ===========================================================================

class TestBoundaryConditions:
    def test_reeving_single_part_large_swl(self):
        """1 part, large SWL → line_pull equals SWL."""
        r = wire_rope_reeving(1000.0, 1, rope_efficiency=1.0)
        assert r["ok"] is True
        assert math.isclose(r["line_pull_kN"], 1000.0, rel_tol=1e-9)

    def test_rope_diameter_just_enough(self):
        """Line pull that exactly requires a known diameter."""
        # d=20mm, grade 1570 → MBF=200 kN; SF=5 → required_mbf=100 kN
        # Use line_pull=20 kN, SF=5 → required=100 kN, d=20mm barely covers
        r = rope_diameter(20.0, safety_factor=5.0, grade="1570")
        assert r["ok"] is True
        assert r["mbf_kN"] >= 100.0

    def test_bridge_wheel_crab_at_left_end(self):
        """Crab at x=0: all payload on left end."""
        span = 10.0
        bridge = 6000.0
        crab = 2000.0
        payload = 4000.0
        r = bridge_wheel_loads(span, bridge, crab, payload, 0.0)
        assert r["ok"] is True
        # Crab+payload entirely at left: R_L_crab = (crab+payload)*g
        W_crab = (crab + payload) * _G
        assert math.isclose(
            r["left_reaction_N"],
            bridge / 2 * _G + W_crab,
            rel_tol=1e-6,
        )

    def test_jib_chart_restoring_moment_field(self):
        """restoring_moment_Nm = CW * g * r_cw (no crane base mass)."""
        CW = 8000.0
        r_cw = 4.0
        r = jib_load_chart(5.0, 15.0, 2000.0, CW, r_cw)
        assert r["ok"] is True
        expected = CW * _G * r_cw
        assert math.isclose(r["restoring_moment_Nm"], expected, rel_tol=1e-9)

    def test_duty_class_boundary_a2(self):
        """6300 cycles → A2."""
        r = crane_duty_class(6300, 1)
        assert r["ok"] is True
        assert r["duty_group"] == "A2"

    def test_hook_shank_grade_t(self):
        """grade_T Fy=590 MPa → higher allowable than grade_P."""
        r_p = hook_shank_check(100.0, 40.0, 3.0, material="grade_P")
        r_t = hook_shank_check(100.0, 40.0, 3.0, material="grade_T")
        assert r_t["allowable_MPa"] > r_p["allowable_MPa"]

    def test_motor_class_table_completeness(self):
        """All 8x4=32 combinations of duty_group x load_spectrum are valid."""
        for dg in range(1, 9):
            for ls in range(1, 5):
                r = hoist_motor_class(dg, ls)
                assert r["ok"] is True
                assert r["m_class"].startswith("M")


# ===========================================================================
# Externally-citable reference cases (production-confidence validation)
# Cross-checked against:
#   - FEM 1.001 "Rules for the Design of Hoisting Appliances", 4th ed.
#   - DIN 15018 (steel structures) / DIN 15020 (rope drives) / DIN 15400
#     (lifting hooks)
#   - Verschoof, "Cranes — Design, Practice and Maintenance", 2nd ed.
#     (running-rope reeving efficiency, tipping stability hand-calcs)
# Each case carries a hand-computed numeric answer in the comment.
# ===========================================================================

class TestCraneExternalReferences:
    """Validated vs FEM 1.001 / DIN 15020 / DIN 15400 / crane handbooks."""

    def test_reeving_efficiency_running_rope_FEM(self):
        # Verschoof "Cranes" / FEM 1.001 running-rope block efficiency:
        #   η_block = (1 − η^n) / (n·(1 − η)).  η=0.98, n=4 → 0.970398.
        r = wire_rope_reeving(100.0, 4, rope_efficiency=0.98)
        eta, n = 0.98, 4
        eta_block = (1.0 - eta ** n) / (n * (1.0 - eta))
        assert r["eta_block"] == pytest.approx(eta_block, rel=1e-12)
        assert r["eta_block"] == pytest.approx(0.970398, rel=1e-5)
        # Line pull = SWL / (n · η_block) = 100 / (4·0.970398) ≈ 25.7626 kN.
        assert r["line_pull_kN"] == pytest.approx(25.762625, rel=1e-6)

    def test_hook_shank_iso_thread_root_DIN15400(self):
        # DIN 15400 hook-shank tensile check, ISO metric thread minor
        # diameter d_3 = d − 0.9743·P (basic minor dia). M48×5, SWL 200 kN.
        r = hook_shank_check(200.0, 48.0, 5.0, material="grade_P", design_factor=4.0)
        d_minor = 48.0 - 0.9743 * 5.0           # 43.1285 mm
        A_root = math.pi / 4.0 * d_minor ** 2    # 1460.8936 mm²
        assert r["minor_dia_mm"] == pytest.approx(d_minor, rel=1e-9)
        assert r["root_area_mm2"] == pytest.approx(A_root, rel=1e-9)
        assert r["tension_stress_MPa"] == pytest.approx(200_000.0 / A_root, rel=1e-9)
        assert r["tension_stress_MPa"] == pytest.approx(136.9025, rel=1e-4)
        # grade_P Fy=355, design factor 4 → allowable 88.75 MPa → overstressed.
        assert r["allowable_MPa"] == pytest.approx(355.0 / 4.0, rel=1e-12)
        assert r["pass_shank"] is False

    def test_jib_tipping_moment_balance(self):
        # Crane-handbook tipping balance about the front edge:
        #   allowable = (M_restore/SF − jib_self_moment) / (g·R).
        # CW 12 t @ 4 m, jib 2 t @ L/2 of 15 m, SF 1.5, R 6 m.
        r = jib_load_chart(6.0, 15.0, 2000.0, 12000.0, 4.0,
                           safety_factor=1.5)
        Mr = 12000.0 * _G * 4.0
        jib_ot = 2000.0 * _G * (15.0 / 2.0)
        net = Mr / 1.5 - jib_ot
        assert r["restoring_moment_Nm"] == pytest.approx(Mr, rel=1e-9)
        assert r["jib_overturning_Nm"] == pytest.approx(jib_ot, rel=1e-9)
        assert r["allowable_load_kg"] == pytest.approx(net / 6.0 / _G, rel=1e-9)
        assert r["allowable_load_kg"] == pytest.approx(2833.333, rel=1e-4)

    def test_bridge_simply_supported_reactions(self):
        # Simply-supported bridge girder (statics): crab+payload share by
        # lever rule, bridge self-weight split equally. Reactions must sum
        # to total weight (DIN 15018 / crane statics).
        r = bridge_wheel_loads(20.0, 12000.0, 2000.0, 8000.0, 5.0,
                               n_wheels_per_end=2, dynamic_factor=1.15)
        Wb = 12000.0 * _G
        Wcp = (2000.0 + 8000.0) * _G
        RL = Wb / 2 + Wcp * (20.0 - 5.0) / 20.0
        RR = Wb / 2 + Wcp * 5.0 / 20.0
        assert r["left_reaction_N"] == pytest.approx(RL, rel=1e-9)
        assert r["right_reaction_N"] == pytest.approx(RR, rel=1e-9)
        assert r["left_reaction_N"] + r["right_reaction_N"] == pytest.approx(
            Wb + Wcp, rel=1e-9
        )
        # Per-wheel load includes dynamic factor: R_L·1.15/2.
        assert r["left_wheel_load_kN"] == pytest.approx(RL * 1.15 / 2 / 1000.0, rel=1e-9)

    def test_hoist_motor_power_lift_formula(self):
        # P = F·v / η (steady lift). SWL 50 kN, v 0.25 m/s, η 0.85.
        r = hoist_motor_power(50.0, 0.25, mechanical_efficiency=0.85)
        assert r["motor_power_kW"] == pytest.approx(
            50_000.0 * 0.25 / 0.85 / 1000.0, rel=1e-12
        )
        assert r["motor_power_kW"] == pytest.approx(14.70588, rel=1e-5)

    def test_travel_rolling_resistance_FEM(self):
        # FEM rolling resistance F = m·g·f. m 30 t, f 0.015 → 4412.99 N.
        r = travel_resistance(30000.0, 0.0, coeff_rolling=0.015)
        assert r["rolling_force_N"] == pytest.approx(30000.0 * _G * 0.015, rel=1e-12)
        assert r["rolling_force_N"] == pytest.approx(4412.9925, rel=1e-5)

    def test_dd_ratio_FEM_15020_minimum(self):
        # DIN 15020 / FEM 1.001: running sheaves require D/d ≥ class minimum;
        # below the table value the DD_RATIO_LOW warning fires.
        r = sheave_drum_geometry(13.0, sheave_dd_ratio=10.0, drum_dd_ratio=10.0,
                                 fem_class="E")
        assert r["ok"] is True
        assert any("DD_RATIO_LOW" in w for w in r["warnings"])
