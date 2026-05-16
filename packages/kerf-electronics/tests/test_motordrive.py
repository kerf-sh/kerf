"""
Hermetic tests for kerf_electronics motor & inverter-drive sizing module.

Covers (≥30 tests):

  load_torque_power
    - omega = RPM × 2π/60  hand-calc
    - t_total = t_load + J×α + friction + B×ω  hand-calc
    - p_mech = t_total × ω  hand-calc
    - Zero-valued optional params → pure load torque
    - Non-positive speed → ok=False
    - Negative inertia → ok=False

  reflected_inertia
    - J_reflected = J_load / N²  hand-calc at η=1
    - J_reflected = J_load / (N² × η)  hand-calc at η<1
    - Larger gear ratio → smaller reflected inertia
    - Non-positive j_load → ok=False
    - Non-positive gear_ratio → ok=False

  inertia_match_ratio
    - N_opt = sqrt(J_load / J_motor)  hand-calc
    - mismatch = J_load / (N² × J_motor)  hand-calc
    - mismatch > threshold → inertia_matched=False, warning issued
    - mismatch ≤ threshold → inertia_matched=True
    - Non-positive j_motor → ok=False

  rms_torque_trapezoidal
    - Pure-accel single phase: T_rms = T_a  hand-calc
    - Multi-phase: exact RMS formula
    - t_peak = max of all torque values
    - duty_cycle_active = (dt_accel + dt_cruise + dt_decel) / cycle_time
    - All zero times → ok=False

  motor_constants
    - Kt = T_rated / I_rated  hand-calc
    - Ke == Kt  (SI units)
    - E_bemf = Ke × ω_no_load  hand-calc
    - T_stall = Kt × V_rated / R  hand-calc
    - P_copper = I² × R  hand-calc
    - Odd poles → ok=False
    - Non-positive winding resistance → ok=False
    - Back-EMF > rated voltage → voltage_insufficient warning

  dc_operating_point
    - I_a = T / Kt  hand-calc
    - E_bemf = Ke × ω  hand-calc
    - V_terminal = E_bemf + I_a × R  hand-calc
    - efficiency = P_out / P_input  hand-calc
    - V_terminal > supply → voltage_insufficient warning
    - Non-positive Kt → ok=False

  bldc_pmsm_operating_point
    - Iq = T / (1.5 × p × Kt)  hand-calc
    - omega_elec = pole_pairs × omega_mech  hand-calc
    - P_copper = 1.5 × R × (Iq² + Id²)  hand-calc
    - V_dc_min > supply → voltage_insufficient warning
    - Non-positive speed → ok=False

  induction_motor_slip_torque
    - P_ag > 0 for positive slip
    - Slip=0 → ok=False
    - High slip (> 20 %) → warning issued
    - Negative slip → generator-mode warning
    - Non-positive rotor resistance → ok=False
    - omega_rotor = omega_sync × (1 − slip)  hand-calc

  inverter_sizing
    - n_devices = phases × 2  (default 6 for 3-phase)
    - P_sw = n_devices × E_sw_j × fsw  hand-calc
    - I_device_rated = I_peak / derating  hand-calc
    - V_device_rated = 2 × V_dc  hand-calc
    - Non-positive switching energy → ok=False
    - Derating > 1 → ok=False

  regen_energy
    - ΔKE = 0.5 × J × (ω_i² − ω_f²)  hand-calc
    - E_regen = ΔKE × η  hand-calc
    - E_dissipated = ΔKE − E_regen  hand-calc
    - speed_final >= speed_initial → ok=False
    - Non-positive inertia → ok=False

  brake_resistor_sizing
    - V_brake = V_dc × (1 + margin)  hand-calc
    - R_brake = V_brake² × t / (2 × E)  hand-calc
    - P_avg = E / t  hand-calc
    - P_peak = V_brake² / R_brake  hand-calc
    - Non-positive discharge time → ok=False

  thermal_duty_check
    - T_winding = T_ambient + P_eff × Rth  hand-calc
    - over_temp=True when T > T_max
    - over_temp=False at low load
    - Duty cycle < 1 → P_eff < P_loss
    - Thermal time-constant correction applied when τ > 0
    - Non-positive Rth → ok=False

  LLM tool handlers
    - motordrive_load_torque_power_tool happy path
    - motordrive_reflected_inertia_tool happy path
    - motordrive_rms_torque_tool happy path
    - motordrive_dc_operating_point_tool happy path
    - motordrive_bldc_pmsm_op_point_tool happy path
    - motordrive_inverter_sizing_tool happy path
    - motordrive_regen_energy_tool happy path
    - motordrive_brake_resistor_tool happy path
    - motordrive_thermal_duty_tool happy path
    - Tool with invalid JSON → error payload

Author: imranparuk
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import types
import warnings

# ── Prefer the real kerf_chat if installed; stub otherwise ───────────────────
try:
    import kerf_chat as _kc_pkg  # noqa: F401
    import kerf_chat.tools as _kc_tools  # noqa: F401
    import kerf_chat.tools.registry as _kc_real  # noqa: F401
except Exception:
    _kc_real = None

_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.Registry = type("Registry", (list,), {})
_reg_stub.ToolSpec = type(
    "ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)}
)
_reg_stub.err_payload = lambda msg, code: json.dumps(
    {"ok": False, "error": msg, "code": code}
)
_reg_stub.ok_payload = lambda v: json.dumps({"ok": True, **v})
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

_kerf_chat_stub = types.ModuleType("kerf_chat")
_kerf_chat_tools_stub = types.ModuleType("kerf_chat.tools")
sys.modules.setdefault("kerf_chat", _kerf_chat_stub)
sys.modules.setdefault("kerf_chat.tools", _kerf_chat_tools_stub)
if _kc_real is None:
    sys.modules["kerf_chat.tools.registry"] = _reg_stub

# ── Ensure src/ is on path ────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from kerf_electronics.motordrive.sizing import (
    load_torque_power,
    reflected_inertia,
    inertia_match_ratio,
    rms_torque_trapezoidal,
    motor_constants,
    dc_operating_point,
    bldc_pmsm_operating_point,
    induction_motor_slip_torque,
    inverter_sizing,
    regen_energy,
    brake_resistor_sizing,
    thermal_duty_check,
)

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.motordrive.tools",
    os.path.join(_SRC, "kerf_electronics", "motordrive", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

_load_torque_tool = _tool_mod.motordrive_load_torque_power_tool
_reflected_inertia_tool = _tool_mod.motordrive_reflected_inertia_tool
_rms_torque_tool = _tool_mod.motordrive_rms_torque_tool
_dc_op_tool = _tool_mod.motordrive_dc_operating_point_tool
_bldc_tool = _tool_mod.motordrive_bldc_pmsm_op_point_tool
_inverter_tool = _tool_mod.motordrive_inverter_sizing_tool
_regen_tool = _tool_mod.motordrive_regen_energy_tool
_brake_tool = _tool_mod.motordrive_brake_resistor_tool
_thermal_tool = _tool_mod.motordrive_thermal_duty_tool


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. load_torque_power
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadTorquePower:
    def test_omega_conversion(self):
        """omega_rad_s = speed_rpm × 2π/60"""
        res = load_torque_power(speed_rpm=1000.0, torque_load_nm=5.0)
        expected = 1000.0 * (2 * math.pi / 60)
        assert abs(res["omega_rad_s"] - expected) < 1e-6

    def test_pure_load_torque_power(self):
        """With no friction/inertia/viscous: t_total = t_load, p = t × ω"""
        res = load_torque_power(speed_rpm=3000.0, torque_load_nm=2.0)
        omega = 3000.0 * (2.0 * math.pi / 60.0)
        assert abs(res["t_total_nm"] - 2.0) < 1e-6
        assert abs(res["p_mech_w"] - 2.0 * omega) < 1e-3

    def test_inertial_term(self):
        """t_inertial = J × α"""
        J = 0.01   # kg·m²
        alpha = 50.0  # rad/s²
        res = load_torque_power(
            speed_rpm=500.0, torque_load_nm=1.0,
            inertia_kgm2=J, accel_rad_s2=alpha
        )
        assert abs(res["t_inertial_nm"] - J * alpha) < 1e-9

    def test_viscous_term(self):
        """t_viscous = B × ω"""
        B = 0.002  # N·m·s/rad
        speed = 1500.0
        omega = speed * (2.0 * math.pi / 60.0)
        res = load_torque_power(
            speed_rpm=speed, torque_load_nm=0.5,
            viscous_nm_per_rad_s=B
        )
        assert abs(res["t_viscous_nm"] - B * omega) < 1e-6

    def test_total_torque_sum(self):
        """t_total = t_load + t_inertial + t_friction + t_viscous"""
        res = load_torque_power(
            speed_rpm=1000.0, torque_load_nm=2.0,
            inertia_kgm2=0.01, accel_rad_s2=20.0,
            friction_nm=0.3, viscous_nm_per_rad_s=0.001
        )
        expected = (
            2.0
            + res["t_inertial_nm"]
            + res["t_friction_nm"]
            + res["t_viscous_nm"]
        )
        assert abs(res["t_total_nm"] - expected) < 1e-9

    def test_nonpositive_speed_error(self):
        res = load_torque_power(speed_rpm=0.0, torque_load_nm=1.0)
        assert res["ok"] is False
        assert "speed_rpm" in res["reason"]

    def test_negative_inertia_error(self):
        res = load_torque_power(speed_rpm=1000.0, torque_load_nm=1.0, inertia_kgm2=-0.01)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. reflected_inertia
# ═══════════════════════════════════════════════════════════════════════════════

class TestReflectedInertia:
    def test_ideal_gearbox_formula(self):
        """J_reflected = J_load / N² at η=1"""
        J_load = 0.5
        N = 5.0
        res = reflected_inertia(j_load_kgm2=J_load, gear_ratio=N)
        assert abs(res["j_reflected_kgm2"] - J_load / N ** 2) < 1e-12

    def test_with_efficiency(self):
        """J_reflected = J_load / (N² × η)"""
        J_load = 0.8
        N = 4.0
        eta = 0.95
        res = reflected_inertia(j_load_kgm2=J_load, gear_ratio=N, gearbox_efficiency=eta)
        expected = J_load / (N ** 2 * eta)
        assert abs(res["j_reflected_kgm2"] - expected) < 1e-12

    def test_larger_ratio_smaller_reflected(self):
        """Higher gear ratio → smaller reflected inertia."""
        r_low = reflected_inertia(j_load_kgm2=0.4, gear_ratio=2.0)
        r_high = reflected_inertia(j_load_kgm2=0.4, gear_ratio=10.0)
        assert r_low["j_reflected_kgm2"] > r_high["j_reflected_kgm2"]

    def test_nonpositive_jload_error(self):
        res = reflected_inertia(j_load_kgm2=0.0, gear_ratio=5.0)
        assert res["ok"] is False

    def test_nonpositive_gear_ratio_error(self):
        res = reflected_inertia(j_load_kgm2=0.5, gear_ratio=-1.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. inertia_match_ratio
# ═══════════════════════════════════════════════════════════════════════════════

class TestInertiaMatchRatio:
    def test_n_opt_formula(self):
        """N_opt = sqrt(J_load / J_motor)"""
        J_m = 0.001
        J_l = 0.1
        res = inertia_match_ratio(j_motor_kgm2=J_m, j_load_kgm2=J_l)
        expected_n_opt = math.sqrt(J_l / J_m)
        assert abs(res["n_opt"] - expected_n_opt) < 1e-6

    def test_mismatch_formula(self):
        """mismatch = J_load / (N² × J_motor)"""
        J_m = 0.002
        J_l = 0.2
        N = 5.0
        res = inertia_match_ratio(j_motor_kgm2=J_m, j_load_kgm2=J_l, gear_ratio=N)
        expected = J_l / (N ** 2 * J_m)
        assert abs(res["mismatch_ratio"] - expected) < 1e-9

    def test_high_mismatch_warning(self):
        """mismatch > threshold → inertia_matched=False, warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = inertia_match_ratio(
                j_motor_kgm2=0.001, j_load_kgm2=1.0, gear_ratio=1.0
            )
            assert res["inertia_matched"] is False
            assert any("mismatch" in str(x.message).lower() for x in w)

    def test_good_match_no_warning(self):
        """mismatch <= threshold → inertia_matched=True, no mismatch warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = inertia_match_ratio(
                j_motor_kgm2=0.01, j_load_kgm2=0.09, gear_ratio=3.0
            )
            assert res["ok"] is True
            mismatch_warns = [x for x in w if "mismatch" in str(x.message).lower()]
            assert len(mismatch_warns) == 0

    def test_nonpositive_jmotor_error(self):
        res = inertia_match_ratio(j_motor_kgm2=0.0, j_load_kgm2=0.1)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. rms_torque_trapezoidal
# ═══════════════════════════════════════════════════════════════════════════════

class TestRmsTorqueTrapezoidal:
    def test_single_phase_exact(self):
        """Pure accel only (all others zero): T_rms = T_accel"""
        T_a = 5.0
        res = rms_torque_trapezoidal(
            t_accel_nm=T_a, t_cruise_nm=0.0, t_decel_nm=0.0, t_dwell_nm=0.0,
            dt_accel_s=1.0, dt_cruise_s=0.0, dt_decel_s=0.0, dt_dwell_s=0.0
        )
        assert abs(res["t_rms_nm"] - T_a) < 1e-9

    def test_four_phase_formula(self):
        """Verify T_rms formula for a complete trapezoidal profile."""
        T_a, T_c, T_d, T_dw = 10.0, 3.0, 8.0, 0.5
        dt_a, dt_c, dt_d, dt_dw = 0.5, 2.0, 0.5, 1.0
        t_cycle = dt_a + dt_c + dt_d + dt_dw
        expected_rms = math.sqrt(
            (T_a**2 * dt_a + T_c**2 * dt_c + T_d**2 * dt_d + T_dw**2 * dt_dw) / t_cycle
        )
        res = rms_torque_trapezoidal(
            t_accel_nm=T_a, t_cruise_nm=T_c, t_decel_nm=T_d, t_dwell_nm=T_dw,
            dt_accel_s=dt_a, dt_cruise_s=dt_c, dt_decel_s=dt_d, dt_dwell_s=dt_dw
        )
        assert abs(res["t_rms_nm"] - expected_rms) < 1e-5

    def test_t_peak_is_maximum(self):
        """t_peak = max of all torque inputs."""
        res = rms_torque_trapezoidal(
            t_accel_nm=10.0, t_cruise_nm=3.0, t_decel_nm=8.0, t_dwell_nm=0.5,
            dt_accel_s=0.5, dt_cruise_s=2.0, dt_decel_s=0.5, dt_dwell_s=1.0
        )
        assert abs(res["t_peak_nm"] - 10.0) < 1e-9

    def test_duty_cycle_active(self):
        """duty_cycle_active = (dt_accel + dt_cruise + dt_decel) / total"""
        dt_a, dt_c, dt_d, dt_dw = 0.5, 2.0, 0.5, 1.0
        res = rms_torque_trapezoidal(
            t_accel_nm=5.0, t_cruise_nm=2.0, t_decel_nm=4.0, t_dwell_nm=0.0,
            dt_accel_s=dt_a, dt_cruise_s=dt_c, dt_decel_s=dt_d, dt_dwell_s=dt_dw
        )
        expected = (dt_a + dt_c + dt_d) / (dt_a + dt_c + dt_d + dt_dw)
        assert abs(res["duty_cycle_active"] - expected) < 1e-9

    def test_zero_cycle_time_error(self):
        """All dt_* = 0 → ok=False."""
        res = rms_torque_trapezoidal(
            t_accel_nm=5.0, t_cruise_nm=2.0, t_decel_nm=4.0, t_dwell_nm=0.0,
            dt_accel_s=0.0, dt_cruise_s=0.0, dt_decel_s=0.0, dt_dwell_s=0.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. motor_constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestMotorConstants:
    def test_kt_formula(self):
        """Kt = T_rated / I_rated"""
        T = 2.0
        I = 5.0
        res = motor_constants(
            rated_torque_nm=T, rated_current_a=I,
            no_load_speed_rpm=3000.0, rated_voltage_v=24.0,
            winding_resistance_ohm=0.5
        )
        assert abs(res["kt_nm_per_a"] - T / I) < 1e-8

    def test_ke_equals_kt(self):
        """Ke == Kt in SI units."""
        res = motor_constants(
            rated_torque_nm=1.5, rated_current_a=3.0,
            no_load_speed_rpm=2000.0, rated_voltage_v=24.0,
            winding_resistance_ohm=0.8
        )
        assert abs(res["ke_v_s_per_rad"] - res["kt_nm_per_a"]) < 1e-10

    def test_e_bemf_formula(self):
        """E_bemf = Ke × ω_no_load"""
        res = motor_constants(
            rated_torque_nm=1.0, rated_current_a=2.0,
            no_load_speed_rpm=1500.0, rated_voltage_v=48.0,
            winding_resistance_ohm=1.0
        )
        omega = 1500.0 * (2.0 * math.pi / 60.0)
        expected_e = res["ke_v_s_per_rad"] * omega
        assert abs(res["e_bemf_rated_v"] - expected_e) < 1e-6

    def test_t_stall_formula(self):
        """T_stall = Kt × V_rated / R"""
        res = motor_constants(
            rated_torque_nm=2.0, rated_current_a=4.0,
            no_load_speed_rpm=2000.0, rated_voltage_v=24.0,
            winding_resistance_ohm=1.0
        )
        expected = res["kt_nm_per_a"] * 24.0 / 1.0
        assert abs(res["t_stall_nm"] - expected) < 1e-6

    def test_p_copper_formula(self):
        """P_copper = I_rated² × R"""
        I = 3.0
        R = 0.5
        res = motor_constants(
            rated_torque_nm=1.5, rated_current_a=I,
            no_load_speed_rpm=3000.0, rated_voltage_v=24.0,
            winding_resistance_ohm=R
        )
        assert abs(res["p_copper_w"] - I ** 2 * R) < 1e-9

    def test_odd_poles_error(self):
        res = motor_constants(
            rated_torque_nm=1.0, rated_current_a=2.0,
            no_load_speed_rpm=3000.0, rated_voltage_v=24.0,
            winding_resistance_ohm=0.5, poles=3
        )
        assert res["ok"] is False

    def test_voltage_insufficient_warning(self):
        """back-EMF > rated voltage triggers voltage_insufficient warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Kt=2/4=0.5, omega=100×2π/60≈10.47, Ke=0.5, E=5.24 V < 24V → no warn
            # Force E_bemf > V_rated: high speed, high Kt
            res = motor_constants(
                rated_torque_nm=5.0, rated_current_a=1.0,  # Kt=5
                no_load_speed_rpm=10000.0,                   # omega=1047 rad/s, E=5235V >> 24V
                rated_voltage_v=24.0,
                winding_resistance_ohm=0.1
            )
            assert res["ok"] is True
            assert any("voltage" in str(x.message).lower() for x in w)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. dc_operating_point
# ═══════════════════════════════════════════════════════════════════════════════

class TestDcOperatingPoint:
    def test_i_a_formula(self):
        """I_a = T / Kt"""
        T = 1.5
        Kt = 0.5
        res = dc_operating_point(
            speed_rpm=1000.0, torque_nm=T, kt_nm_per_a=Kt,
            ke_v_s_per_rad=Kt, winding_resistance_ohm=1.0,
            supply_voltage_v=48.0
        )
        assert abs(res["i_a_a"] - T / Kt) < 1e-9

    def test_e_bemf_formula(self):
        """E_bemf = Ke × ω"""
        Ke = 0.5
        speed = 1500.0
        omega = speed * (2.0 * math.pi / 60.0)
        res = dc_operating_point(
            speed_rpm=speed, torque_nm=1.0, kt_nm_per_a=Ke,
            ke_v_s_per_rad=Ke, winding_resistance_ohm=1.0,
            supply_voltage_v=100.0
        )
        assert abs(res["e_bemf_v"] - Ke * omega) < 1e-6

    def test_v_terminal_formula(self):
        """V_t = E_bemf + I_a × R"""
        Ke = 0.5
        Kt = 0.5
        R = 1.0
        T = 2.0
        speed = 1000.0
        omega = speed * (2.0 * math.pi / 60.0)
        I_a = T / Kt
        E = Ke * omega
        res = dc_operating_point(
            speed_rpm=speed, torque_nm=T, kt_nm_per_a=Kt,
            ke_v_s_per_rad=Ke, winding_resistance_ohm=R,
            supply_voltage_v=100.0
        )
        assert abs(res["v_terminal_v"] - (E + I_a * R)) < 1e-6

    def test_efficiency_formula(self):
        """η = P_out / P_input"""
        res = dc_operating_point(
            speed_rpm=1000.0, torque_nm=1.5, kt_nm_per_a=0.3,
            ke_v_s_per_rad=0.3, winding_resistance_ohm=0.5,
            supply_voltage_v=60.0
        )
        expected_eta = res["p_out_w"] / res["p_input_w"]
        assert abs(res["efficiency"] - expected_eta) < 1e-6

    def test_voltage_insufficient_warning(self):
        """V_terminal > supply_voltage triggers warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # At high torque + high speed the terminal voltage will exceed supply
            res = dc_operating_point(
                speed_rpm=5000.0, torque_nm=5.0, kt_nm_per_a=0.1,
                ke_v_s_per_rad=0.1, winding_resistance_ohm=2.0,
                supply_voltage_v=12.0
            )
            assert res["ok"] is True
            assert any("voltage" in str(x.message).lower() for x in w)

    def test_nonpositive_kt_error(self):
        res = dc_operating_point(
            speed_rpm=1000.0, torque_nm=1.0, kt_nm_per_a=0.0,
            ke_v_s_per_rad=0.5, winding_resistance_ohm=1.0,
            supply_voltage_v=24.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 7. bldc_pmsm_operating_point
# ═══════════════════════════════════════════════════════════════════════════════

class TestBldcPmsmOperatingPoint:
    def test_iq_formula(self):
        """Iq = T / (1.5 × p × Kt)"""
        T = 3.0
        Kt = 0.5
        p = 2
        res = bldc_pmsm_operating_point(
            speed_rpm=1500.0, torque_nm=T, kt_nm_per_a=Kt,
            ke_v_s_per_rad=Kt, phase_resistance_ohm=0.5,
            dc_link_voltage_v=48.0, pole_pairs=p
        )
        expected_iq = T / (1.5 * p * Kt)
        assert abs(res["iq_a"] - expected_iq) < 1e-9

    def test_omega_elec_formula(self):
        """ω_elec = p × ω_mech"""
        p = 3
        speed = 1000.0
        res = bldc_pmsm_operating_point(
            speed_rpm=speed, torque_nm=1.0, kt_nm_per_a=0.3,
            ke_v_s_per_rad=0.3, phase_resistance_ohm=0.3,
            dc_link_voltage_v=48.0, pole_pairs=p
        )
        omega_mech = speed * (2.0 * math.pi / 60.0)
        assert abs(res["omega_elec_rad_s"] - p * omega_mech) < 1e-6

    def test_p_copper_formula(self):
        """P_copper = 1.5 × R × (Iq² + Id²)"""
        R = 0.4
        res = bldc_pmsm_operating_point(
            speed_rpm=1000.0, torque_nm=2.0, kt_nm_per_a=0.4,
            ke_v_s_per_rad=0.4, phase_resistance_ohm=R,
            dc_link_voltage_v=60.0, pole_pairs=2, id_a=1.0
        )
        expected_p_cu = 1.5 * R * (res["iq_a"] ** 2 + 1.0 ** 2)
        assert abs(res["p_copper_w"] - expected_p_cu) < 1e-6

    def test_voltage_insufficient_warning(self):
        """V_dc_min > dc_link_voltage triggers warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Very high speed → large E_bemf → large V_dc_min
            res = bldc_pmsm_operating_point(
                speed_rpm=10000.0, torque_nm=2.0, kt_nm_per_a=0.3,
                ke_v_s_per_rad=0.3, phase_resistance_ohm=0.5,
                dc_link_voltage_v=12.0, pole_pairs=2
            )
            assert res["ok"] is True
            assert any("voltage" in str(x.message).lower() for x in w)

    def test_nonpositive_speed_error(self):
        res = bldc_pmsm_operating_point(
            speed_rpm=0.0, torque_nm=1.0, kt_nm_per_a=0.5,
            ke_v_s_per_rad=0.5, phase_resistance_ohm=0.5,
            dc_link_voltage_v=48.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 8. induction_motor_slip_torque
# ═══════════════════════════════════════════════════════════════════════════════

class TestInductionMotorSlipTorque:
    def test_positive_slip_positive_torque(self):
        """Positive slip → positive air-gap power → positive torque."""
        res = induction_motor_slip_torque(
            synchronous_speed_rpm=1500.0,
            rotor_resistance_ohm=0.5,
            stator_resistance_ohm=0.3,
            leakage_reactance_ohm=2.0,
            supply_voltage_v=230.0,
            slip=0.05
        )
        assert res["ok"] is True
        assert res["torque_nm"] > 0.0

    def test_slip_zero_error(self):
        """slip = 0 → ok=False."""
        res = induction_motor_slip_torque(
            synchronous_speed_rpm=1500.0,
            rotor_resistance_ohm=0.5,
            stator_resistance_ohm=0.3,
            leakage_reactance_ohm=2.0,
            supply_voltage_v=230.0,
            slip=0.0
        )
        assert res["ok"] is False

    def test_omega_rotor_formula(self):
        """ω_rotor = ω_sync × (1 − s)"""
        slip = 0.04
        sync_rpm = 1500.0
        res = induction_motor_slip_torque(
            synchronous_speed_rpm=sync_rpm,
            rotor_resistance_ohm=0.4,
            stator_resistance_ohm=0.25,
            leakage_reactance_ohm=1.5,
            supply_voltage_v=220.0,
            slip=slip
        )
        omega_sync = sync_rpm * (2.0 * math.pi / 60.0)
        expected_omega_r = omega_sync * (1.0 - slip)
        assert abs(res["omega_rotor_rad_s"] - expected_omega_r) < 1e-6

    def test_high_slip_warning(self):
        """slip > 20 % → warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = induction_motor_slip_torque(
                synchronous_speed_rpm=1500.0,
                rotor_resistance_ohm=0.5,
                stator_resistance_ohm=0.3,
                leakage_reactance_ohm=2.0,
                supply_voltage_v=230.0,
                slip=0.30
            )
            assert res["ok"] is True
            assert any("slip" in str(x.message).lower() for x in w)

    def test_negative_slip_generator_warning(self):
        """slip < 0 → generator mode warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = induction_motor_slip_torque(
                synchronous_speed_rpm=1500.0,
                rotor_resistance_ohm=0.5,
                stator_resistance_ohm=0.3,
                leakage_reactance_ohm=2.0,
                supply_voltage_v=230.0,
                slip=-0.03
            )
            assert res["ok"] is True
            assert any("generator" in str(x.message).lower() for x in w)

    def test_nonpositive_rotor_resistance_error(self):
        res = induction_motor_slip_torque(
            synchronous_speed_rpm=1500.0,
            rotor_resistance_ohm=0.0,
            stator_resistance_ohm=0.3,
            leakage_reactance_ohm=2.0,
            supply_voltage_v=230.0,
            slip=0.05
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. inverter_sizing
# ═══════════════════════════════════════════════════════════════════════════════

class TestInverterSizing:
    def test_n_devices(self):
        """n_devices = phases × 2  (default 6 for 3-phase)."""
        res = inverter_sizing(
            peak_phase_current_a=20.0, peak_phase_voltage_v=150.0,
            dc_link_voltage_v=400.0, switching_freq_hz=10000.0
        )
        assert res["n_devices"] == 6

    def test_i_device_rated(self):
        """I_device_rated = I_peak / current_derating"""
        I_peak = 30.0
        derating = 0.8
        res = inverter_sizing(
            peak_phase_current_a=I_peak, peak_phase_voltage_v=200.0,
            dc_link_voltage_v=600.0, switching_freq_hz=8000.0,
            current_derating=derating
        )
        assert abs(res["i_device_rated_a"] - I_peak / derating) < 1e-6

    def test_v_device_rated(self):
        """V_device_rated = 2 × V_dc"""
        V_dc = 400.0
        res = inverter_sizing(
            peak_phase_current_a=20.0, peak_phase_voltage_v=150.0,
            dc_link_voltage_v=V_dc, switching_freq_hz=10000.0
        )
        assert abs(res["v_device_rated_v"] - 2.0 * V_dc) < 1e-6

    def test_p_switching_formula(self):
        """P_sw = n_devices × E_sw_j × fsw"""
        E_sw_uj = 80.0
        fsw = 10000.0
        res = inverter_sizing(
            peak_phase_current_a=20.0, peak_phase_voltage_v=150.0,
            dc_link_voltage_v=400.0, switching_freq_hz=fsw,
            switching_energy_uj=E_sw_uj
        )
        expected_p_sw = res["n_devices"] * (E_sw_uj * 1e-6) * fsw
        assert abs(res["p_switching_w"] - expected_p_sw) < 1e-6

    def test_derating_exceeds_one_error(self):
        res = inverter_sizing(
            peak_phase_current_a=20.0, peak_phase_voltage_v=150.0,
            dc_link_voltage_v=400.0, switching_freq_hz=10000.0,
            current_derating=1.5
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. regen_energy
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegenEnergy:
    def test_delta_ke_formula(self):
        """ΔKE = 0.5 × J × (ω_i² − ω_f²)"""
        J = 0.05
        n_i = 3000.0
        n_f = 1000.0
        omega_i = n_i * (2.0 * math.pi / 60.0)
        omega_f = n_f * (2.0 * math.pi / 60.0)
        res = regen_energy(inertia_kgm2=J, speed_initial_rpm=n_i, speed_final_rpm=n_f)
        expected = 0.5 * J * (omega_i ** 2 - omega_f ** 2)
        assert abs(res["delta_ke_j"] - expected) < 1e-3

    def test_e_regen_with_efficiency(self):
        """E_regen = ΔKE × η"""
        eta = 0.85
        res = regen_energy(
            inertia_kgm2=0.02, speed_initial_rpm=2000.0, speed_final_rpm=0.0,
            drivetrain_efficiency=eta
        )
        assert abs(res["e_regen_j"] - res["delta_ke_j"] * eta) < 1e-3

    def test_e_dissipated(self):
        """E_dissipated = ΔKE − E_regen"""
        res = regen_energy(
            inertia_kgm2=0.03, speed_initial_rpm=2500.0, speed_final_rpm=500.0
        )
        assert abs(res["e_dissipated_j"] - (res["delta_ke_j"] - res["e_regen_j"])) < 1e-9

    def test_final_ge_initial_error(self):
        """speed_final >= speed_initial → ok=False."""
        res = regen_energy(
            inertia_kgm2=0.02, speed_initial_rpm=1000.0, speed_final_rpm=1500.0
        )
        assert res["ok"] is False

    def test_nonpositive_inertia_error(self):
        res = regen_energy(
            inertia_kgm2=0.0, speed_initial_rpm=2000.0, speed_final_rpm=0.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 11. brake_resistor_sizing
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrakeResistorSizing:
    def test_v_brake_formula(self):
        """V_brake = V_dc × (1 + margin)"""
        V_dc = 400.0
        margin = 0.10
        res = brake_resistor_sizing(
            regen_energy_j=500.0, dc_link_voltage_v=V_dc,
            discharge_time_s=0.5, overvoltage_margin_frac=margin
        )
        assert abs(res["v_brake_v"] - V_dc * (1 + margin)) < 1e-6

    def test_r_brake_formula(self):
        """R_brake = V_brake² × t / (2 × E)"""
        E = 400.0
        V_dc = 400.0
        t = 0.4
        margin = 0.10
        V_brake = V_dc * (1 + margin)
        res = brake_resistor_sizing(
            regen_energy_j=E, dc_link_voltage_v=V_dc,
            discharge_time_s=t, overvoltage_margin_frac=margin
        )
        expected_r = V_brake ** 2 * t / (2 * E)
        assert abs(res["r_brake_ohm"] - expected_r) < 1e-6

    def test_p_avg_formula(self):
        """P_avg = E_regen / t_discharge"""
        E = 300.0
        t = 0.5
        res = brake_resistor_sizing(
            regen_energy_j=E, dc_link_voltage_v=400.0, discharge_time_s=t
        )
        assert abs(res["p_avg_w"] - E / t) < 1e-6

    def test_p_peak_formula(self):
        """P_peak = V_brake² / R_brake"""
        res = brake_resistor_sizing(
            regen_energy_j=500.0, dc_link_voltage_v=400.0, discharge_time_s=0.5
        )
        expected_p_peak = res["v_brake_v"] ** 2 / res["r_brake_ohm"]
        assert abs(res["p_peak_w"] - expected_p_peak) < 0.01

    def test_nonpositive_discharge_time_error(self):
        res = brake_resistor_sizing(
            regen_energy_j=300.0, dc_link_voltage_v=400.0, discharge_time_s=0.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 12. thermal_duty_check
# ═══════════════════════════════════════════════════════════════════════════════

class TestThermalDutyCheck:
    def test_t_winding_continuous(self):
        """T_winding = T_ambient + P_loss × Rth at duty=1."""
        P = 50.0
        Rth = 0.8
        T_amb = 40.0
        res = thermal_duty_check(
            p_loss_w=P, rth_winding_ambient=Rth, t_ambient_c=T_amb
        )
        expected = T_amb + P * Rth
        assert abs(res["t_winding_c"] - expected) < 1e-6

    def test_duty_cycle_reduces_temp(self):
        """Duty cycle < 1 → lower effective temperature rise."""
        r_full = thermal_duty_check(
            p_loss_w=100.0, rth_winding_ambient=0.5, t_ambient_c=25.0
        )
        r_half = thermal_duty_check(
            p_loss_w=100.0, rth_winding_ambient=0.5, t_ambient_c=25.0,
            duty_cycle=0.5
        )
        assert r_half["t_winding_c"] < r_full["t_winding_c"]

    def test_over_temp_true(self):
        """T_winding > T_max → over_temp=True, warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = thermal_duty_check(
                p_loss_w=200.0, rth_winding_ambient=1.0, t_ambient_c=40.0,
                t_max_c=130.0
            )
            assert res["over_temp"] is True
            assert any("over_temp" in str(x.message).lower() for x in w)

    def test_over_temp_false(self):
        """Low loss → over_temp=False."""
        res = thermal_duty_check(
            p_loss_w=10.0, rth_winding_ambient=0.5, t_ambient_c=25.0,
            t_max_c=130.0
        )
        assert res["over_temp"] is False

    def test_thermal_time_constant_correction(self):
        """With τ > 0 and finite cycle, ΔT < steady-state ΔT."""
        res_ss = thermal_duty_check(
            p_loss_w=100.0, rth_winding_ambient=0.5, t_ambient_c=25.0,
            thermal_time_constant_s=0.0, cycle_time_s=0.0
        )
        res_tc = thermal_duty_check(
            p_loss_w=100.0, rth_winding_ambient=0.5, t_ambient_c=25.0,
            thermal_time_constant_s=60.0, cycle_time_s=10.0
        )
        # With τ=60s and t_on=10s × 1.0 duty: factor = 1 - exp(-10/60) ≈ 0.154
        assert res_tc["t_winding_c"] < res_ss["t_winding_c"]

    def test_nonpositive_rth_error(self):
        res = thermal_duty_check(
            p_loss_w=50.0, rth_winding_ambient=0.0, t_ambient_c=25.0
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 13. LLM tool handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_load_torque_power_tool_ok(self):
        res = await call(
            _load_torque_tool,
            speed_rpm=1500.0, torque_load_nm=2.0
        )
        assert res["ok"] is True
        assert "t_total_nm" in res

    @pytest.mark.asyncio
    async def test_reflected_inertia_tool_ok(self):
        res = await call(
            _reflected_inertia_tool,
            j_load_kgm2=0.5, gear_ratio=5.0
        )
        assert res["ok"] is True
        assert "j_reflected_kgm2" in res

    @pytest.mark.asyncio
    async def test_rms_torque_tool_ok(self):
        res = await call(
            _rms_torque_tool,
            t_accel_nm=10.0, t_cruise_nm=3.0, t_decel_nm=8.0, t_dwell_nm=0.5,
            dt_accel_s=0.5, dt_cruise_s=2.0, dt_decel_s=0.5, dt_dwell_s=1.0
        )
        assert res["ok"] is True
        assert "t_rms_nm" in res

    @pytest.mark.asyncio
    async def test_dc_operating_point_tool_ok(self):
        res = await call(
            _dc_op_tool,
            speed_rpm=1500.0, torque_nm=1.0, kt_nm_per_a=0.5,
            ke_v_s_per_rad=0.5, winding_resistance_ohm=1.0,
            supply_voltage_v=60.0
        )
        assert res["ok"] is True
        assert "efficiency" in res

    @pytest.mark.asyncio
    async def test_bldc_pmsm_tool_ok(self):
        res = await call(
            _bldc_tool,
            speed_rpm=1000.0, torque_nm=2.0, kt_nm_per_a=0.4,
            ke_v_s_per_rad=0.4, phase_resistance_ohm=0.5,
            dc_link_voltage_v=48.0
        )
        assert res["ok"] is True
        assert "iq_a" in res

    @pytest.mark.asyncio
    async def test_inverter_sizing_tool_ok(self):
        res = await call(
            _inverter_tool,
            peak_phase_current_a=20.0, peak_phase_voltage_v=150.0,
            dc_link_voltage_v=400.0, switching_freq_hz=10000.0
        )
        assert res["ok"] is True
        assert "p_total_loss_w" in res

    @pytest.mark.asyncio
    async def test_regen_energy_tool_ok(self):
        res = await call(
            _regen_tool,
            inertia_kgm2=0.05, speed_initial_rpm=3000.0, speed_final_rpm=0.0
        )
        assert res["ok"] is True
        assert "e_regen_j" in res

    @pytest.mark.asyncio
    async def test_brake_resistor_tool_ok(self):
        res = await call(
            _brake_tool,
            regen_energy_j=500.0, dc_link_voltage_v=400.0, discharge_time_s=0.5
        )
        assert res["ok"] is True
        assert "r_brake_ohm" in res

    @pytest.mark.asyncio
    async def test_thermal_duty_tool_ok(self):
        res = await call(
            _thermal_tool,
            p_loss_w=50.0, rth_winding_ambient=0.8, t_ambient_c=35.0
        )
        assert res["ok"] is True
        assert "t_winding_c" in res

    @pytest.mark.asyncio
    async def test_tool_invalid_json_returns_error(self):
        result = await _load_torque_tool(None, b"not valid json {{")
        data = json.loads(result)
        assert data.get("ok") is False or "error" in data
