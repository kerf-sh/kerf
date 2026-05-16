"""
Electric motor & inverter-drive sizing — LLM tools.

Exposes tools to the Kerf agent layer:

  motordrive_load_torque_power    — shaft torque and power from speed, load, friction, inertia
  motordrive_reflected_inertia    — load inertia reflected through a gearbox (J / N²)
  motordrive_inertia_match        — inertia mismatch ratio and optimal gear ratio
  motordrive_rms_torque           — RMS torque over a trapezoidal move profile for continuous rating
  motordrive_motor_constants      — derive Kt, Ke, back-EMF, copper loss from datasheet params
  motordrive_dc_operating_point   — DC brush motor voltage/current/efficiency at speed+torque
  motordrive_bldc_pmsm_op_point   — BLDC/PMSM d-q operating point, required DC-link voltage
  motordrive_induction_slip_torque— induction motor slip/torque from equivalent circuit
  motordrive_inverter_sizing      — inverter DC-link, switch ratings, switching+conduction loss
  motordrive_regen_energy         — recoverable energy during regenerative braking
  motordrive_brake_resistor       — brake resistor value and power rating
  motordrive_thermal_duty         — winding temperature duty-cycle check; over-temp warning

All handlers follow the kerf never-raise contract:
  Success: {"ok": True, ...}  via ok_payload
  Failure: {"ok": False, "error": ..., "code": ...}  via err_payload
  Never raise.

Author: imranparuk
"""
from __future__ import annotations

import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

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


# ═══════════════════════════════════════════════════════════════════════════════
# 1. motordrive_load_torque_power
# ═══════════════════════════════════════════════════════════════════════════════

_LOAD_TORQUE_SPEC = ToolSpec(
    name="motordrive_load_torque_power",
    description=(
        "Compute total shaft torque and mechanical power required from a motor.\n\n"
        "Total torque: T = T_load + J×α + T_friction + B×ω\n"
        "Mechanical power: P = T_total × ω\n\n"
        "Input: { speed_rpm, torque_load_nm, inertia_kgm2?, accel_rad_s2?, "
        "friction_nm?, viscous_nm_per_rad_s? }\n"
        "Returns: { ok, omega_rad_s, t_total_nm, t_inertial_nm, t_friction_nm, "
        "t_viscous_nm, p_mech_w, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "speed_rpm": {"type": "number", "description": "Shaft speed [RPM]."},
            "torque_load_nm": {"type": "number", "description": "Load (useful output) torque [N·m]."},
            "inertia_kgm2": {"type": "number", "description": "Total reflected inertia [kg·m²] (default 0)."},
            "accel_rad_s2": {"type": "number", "description": "Angular acceleration [rad/s²] (default 0)."},
            "friction_nm": {"type": "number", "description": "Constant friction torque [N·m] (default 0)."},
            "viscous_nm_per_rad_s": {"type": "number", "description": "Viscous damping coefficient [N·m·s/rad] (default 0)."},
        },
        "required": ["speed_rpm", "torque_load_nm"],
    },
)


@register(_LOAD_TORQUE_SPEC, write=False)
async def motordrive_load_torque_power_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = load_torque_power(
        speed_rpm=a.get("speed_rpm"),
        torque_load_nm=a.get("torque_load_nm"),
        inertia_kgm2=a.get("inertia_kgm2", 0.0),
        accel_rad_s2=a.get("accel_rad_s2", 0.0),
        friction_nm=a.get("friction_nm", 0.0),
        viscous_nm_per_rad_s=a.get("viscous_nm_per_rad_s", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. motordrive_reflected_inertia
# ═══════════════════════════════════════════════════════════════════════════════

_REFLECTED_INERTIA_SPEC = ToolSpec(
    name="motordrive_reflected_inertia",
    description=(
        "Reflect load-side inertia to the motor shaft through a gearbox.\n\n"
        "J_reflected = J_load / (N² × η_gb)\n\n"
        "Input: { j_load_kgm2, gear_ratio, gearbox_efficiency? }\n"
        "Returns: { ok, j_reflected_kgm2, gear_ratio, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "j_load_kgm2": {"type": "number", "description": "Load-side inertia [kg·m²]."},
            "gear_ratio": {"type": "number", "description": "Gear ratio N = ω_motor / ω_load."},
            "gearbox_efficiency": {"type": "number", "description": "Gearbox mechanical efficiency (0, 1] (default 1.0)."},
        },
        "required": ["j_load_kgm2", "gear_ratio"],
    },
)


@register(_REFLECTED_INERTIA_SPEC, write=False)
async def motordrive_reflected_inertia_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = reflected_inertia(
        j_load_kgm2=a.get("j_load_kgm2"),
        gear_ratio=a.get("gear_ratio"),
        gearbox_efficiency=a.get("gearbox_efficiency", 1.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. motordrive_inertia_match
# ═══════════════════════════════════════════════════════════════════════════════

_INERTIA_MATCH_SPEC = ToolSpec(
    name="motordrive_inertia_match",
    description=(
        "Compute load-to-motor inertia mismatch ratio and optimal gear ratio "
        "for inertia matching.\n\n"
        "N_opt = sqrt(J_load / J_motor)\n"
        "mismatch = J_load / (N² × J_motor)\n\n"
        "A warning is issued when mismatch > mismatch_threshold (default 10).\n\n"
        "Input: { j_motor_kgm2, j_load_kgm2, gear_ratio?, mismatch_threshold? }\n"
        "Returns: { ok, mismatch_ratio, n_opt, inertia_matched, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "j_motor_kgm2": {"type": "number", "description": "Motor rotor inertia [kg·m²]."},
            "j_load_kgm2": {"type": "number", "description": "Load inertia at load shaft [kg·m²]."},
            "gear_ratio": {"type": "number", "description": "Current gear ratio N = ω_motor / ω_load (default 1)."},
            "mismatch_threshold": {"type": "number", "description": "Advisory mismatch ratio limit (default 10)."},
        },
        "required": ["j_motor_kgm2", "j_load_kgm2"],
    },
)


@register(_INERTIA_MATCH_SPEC, write=False)
async def motordrive_inertia_match_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = inertia_match_ratio(
        j_motor_kgm2=a.get("j_motor_kgm2"),
        j_load_kgm2=a.get("j_load_kgm2"),
        gear_ratio=a.get("gear_ratio", 1.0),
        mismatch_threshold=a.get("mismatch_threshold", 10.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. motordrive_rms_torque
# ═══════════════════════════════════════════════════════════════════════════════

_RMS_TORQUE_SPEC = ToolSpec(
    name="motordrive_rms_torque",
    description=(
        "Compute RMS torque over a trapezoidal velocity move profile for "
        "continuous-rating motor selection.\n\n"
        "T_rms = sqrt( (T_a²·dt_a + T_c²·dt_c + T_d²·dt_d + T_dw²·dt_dw) / t_cycle )\n\n"
        "Motor continuous torque rating must exceed T_rms.\n\n"
        "Input: { t_accel_nm, t_cruise_nm, t_decel_nm, t_dwell_nm, "
        "dt_accel_s, dt_cruise_s, dt_decel_s, dt_dwell_s }\n"
        "Returns: { ok, t_rms_nm, t_peak_nm, cycle_time_s, duty_cycle_active, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "t_accel_nm": {"type": "number", "description": "Torque during acceleration [N·m]."},
            "t_cruise_nm": {"type": "number", "description": "Torque during cruise [N·m]."},
            "t_decel_nm": {"type": "number", "description": "Torque during deceleration [N·m]."},
            "t_dwell_nm": {"type": "number", "description": "Torque during dwell (holding or 0) [N·m]."},
            "dt_accel_s": {"type": "number", "description": "Acceleration phase duration [s]."},
            "dt_cruise_s": {"type": "number", "description": "Cruise phase duration [s]."},
            "dt_decel_s": {"type": "number", "description": "Deceleration phase duration [s]."},
            "dt_dwell_s": {"type": "number", "description": "Dwell phase duration [s]."},
        },
        "required": [
            "t_accel_nm", "t_cruise_nm", "t_decel_nm", "t_dwell_nm",
            "dt_accel_s", "dt_cruise_s", "dt_decel_s", "dt_dwell_s",
        ],
    },
)


@register(_RMS_TORQUE_SPEC, write=False)
async def motordrive_rms_torque_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = rms_torque_trapezoidal(
        t_accel_nm=a.get("t_accel_nm"),
        t_cruise_nm=a.get("t_cruise_nm"),
        t_decel_nm=a.get("t_decel_nm"),
        t_dwell_nm=a.get("t_dwell_nm"),
        dt_accel_s=a.get("dt_accel_s"),
        dt_cruise_s=a.get("dt_cruise_s"),
        dt_decel_s=a.get("dt_decel_s"),
        dt_dwell_s=a.get("dt_dwell_s"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. motordrive_motor_constants
# ═══════════════════════════════════════════════════════════════════════════════

_MOTOR_CONSTANTS_SPEC = ToolSpec(
    name="motordrive_motor_constants",
    description=(
        "Derive motor constants from datasheet parameters.\n\n"
        "Kt [N·m/A] = rated_torque / rated_current\n"
        "Ke [V·s/rad] = Kt  (equal in SI units)\n"
        "E_bemf = Ke × ω_no_load\n"
        "T_stall = Kt × V_rated / R_winding\n"
        "P_copper = I_rated² × R_winding\n\n"
        "Input: { rated_torque_nm, rated_current_a, no_load_speed_rpm, "
        "rated_voltage_v, winding_resistance_ohm, poles? }\n"
        "Returns: { ok, kt_nm_per_a, ke_v_s_per_rad, omega_no_load_rad_s, "
        "e_bemf_rated_v, p_copper_w, t_stall_nm, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rated_torque_nm": {"type": "number", "description": "Rated output torque [N·m]."},
            "rated_current_a": {"type": "number", "description": "Rated current [A]."},
            "no_load_speed_rpm": {"type": "number", "description": "No-load speed at rated voltage [RPM]."},
            "rated_voltage_v": {"type": "number", "description": "Rated terminal voltage [V]."},
            "winding_resistance_ohm": {"type": "number", "description": "Phase/armature resistance [Ω]."},
            "poles": {"type": "integer", "description": "Number of motor poles (even; default 2)."},
        },
        "required": [
            "rated_torque_nm", "rated_current_a", "no_load_speed_rpm",
            "rated_voltage_v", "winding_resistance_ohm",
        ],
    },
)


@register(_MOTOR_CONSTANTS_SPEC, write=False)
async def motordrive_motor_constants_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = motor_constants(
        rated_torque_nm=a.get("rated_torque_nm"),
        rated_current_a=a.get("rated_current_a"),
        no_load_speed_rpm=a.get("no_load_speed_rpm"),
        rated_voltage_v=a.get("rated_voltage_v"),
        winding_resistance_ohm=a.get("winding_resistance_ohm"),
        poles=a.get("poles", 2),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. motordrive_dc_operating_point
# ═══════════════════════════════════════════════════════════════════════════════

_DC_OP_SPEC = ToolSpec(
    name="motordrive_dc_operating_point",
    description=(
        "DC brush motor operating point at a given speed and torque.\n\n"
        "I_a = T / Kt\n"
        "E_bemf = Ke × ω\n"
        "V_terminal = E_bemf + I_a × Ra\n"
        "η = P_out / (V_t × I_a)\n\n"
        "A warning is issued when V_terminal > supply_voltage_v.\n\n"
        "Input: { speed_rpm, torque_nm, kt_nm_per_a, ke_v_s_per_rad, "
        "winding_resistance_ohm, supply_voltage_v }\n"
        "Returns: { ok, omega_rad_s, i_a_a, e_bemf_v, v_terminal_v, p_copper_w, "
        "p_out_w, p_input_w, efficiency, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "speed_rpm": {"type": "number", "description": "Shaft speed [RPM]."},
            "torque_nm": {"type": "number", "description": "Output torque [N·m]."},
            "kt_nm_per_a": {"type": "number", "description": "Torque constant Kt [N·m/A]."},
            "ke_v_s_per_rad": {"type": "number", "description": "Back-EMF constant Ke [V·s/rad]."},
            "winding_resistance_ohm": {"type": "number", "description": "Armature resistance [Ω]."},
            "supply_voltage_v": {"type": "number", "description": "Available DC supply voltage [V]."},
        },
        "required": [
            "speed_rpm", "torque_nm", "kt_nm_per_a", "ke_v_s_per_rad",
            "winding_resistance_ohm", "supply_voltage_v",
        ],
    },
)


@register(_DC_OP_SPEC, write=False)
async def motordrive_dc_operating_point_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = dc_operating_point(
        speed_rpm=a.get("speed_rpm"),
        torque_nm=a.get("torque_nm"),
        kt_nm_per_a=a.get("kt_nm_per_a"),
        ke_v_s_per_rad=a.get("ke_v_s_per_rad"),
        winding_resistance_ohm=a.get("winding_resistance_ohm"),
        supply_voltage_v=a.get("supply_voltage_v"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. motordrive_bldc_pmsm_op_point
# ═══════════════════════════════════════════════════════════════════════════════

_BLDC_PMSM_SPEC = ToolSpec(
    name="motordrive_bldc_pmsm_op_point",
    description=(
        "BLDC/PMSM operating point using simplified d-q axis model.\n\n"
        "Iq = T / (1.5 × p × Kt)  [FOC, p = pole_pairs]\n"
        "E_ph = Ke × ω_elec / sqrt(3)\n"
        "V_dc_min ≈ sqrt(2) × V_phase\n"
        "P_copper = 1.5 × Rs × (Iq² + Id²)\n\n"
        "A warning is issued when V_dc_min > dc_link_voltage_v.\n\n"
        "Input: { speed_rpm, torque_nm, kt_nm_per_a, ke_v_s_per_rad, "
        "phase_resistance_ohm, dc_link_voltage_v, pole_pairs?, id_a? }\n"
        "Returns: { ok, omega_mech_rad_s, omega_elec_rad_s, iq_a, is_a, "
        "e_bemf_v, v_phase_v, v_dc_min_v, p_copper_w, p_out_w, p_input_w, "
        "efficiency, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "speed_rpm": {"type": "number", "description": "Mechanical shaft speed [RPM]."},
            "torque_nm": {"type": "number", "description": "Output torque [N·m]."},
            "kt_nm_per_a": {"type": "number", "description": "Torque constant Kt [N·m/A_peak]."},
            "ke_v_s_per_rad": {"type": "number", "description": "Back-EMF constant Ke [V·s/rad_mech]."},
            "phase_resistance_ohm": {"type": "number", "description": "Per-phase resistance [Ω]."},
            "dc_link_voltage_v": {"type": "number", "description": "Available DC bus voltage [V]."},
            "pole_pairs": {"type": "integer", "description": "Number of pole pairs (default 2)."},
            "id_a": {"type": "number", "description": "d-axis current [A] for flux weakening (default 0)."},
        },
        "required": [
            "speed_rpm", "torque_nm", "kt_nm_per_a", "ke_v_s_per_rad",
            "phase_resistance_ohm", "dc_link_voltage_v",
        ],
    },
)


@register(_BLDC_PMSM_SPEC, write=False)
async def motordrive_bldc_pmsm_op_point_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = bldc_pmsm_operating_point(
        speed_rpm=a.get("speed_rpm"),
        torque_nm=a.get("torque_nm"),
        kt_nm_per_a=a.get("kt_nm_per_a"),
        ke_v_s_per_rad=a.get("ke_v_s_per_rad"),
        phase_resistance_ohm=a.get("phase_resistance_ohm"),
        dc_link_voltage_v=a.get("dc_link_voltage_v"),
        pole_pairs=a.get("pole_pairs", 2),
        id_a=a.get("id_a", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. motordrive_induction_slip_torque
# ═══════════════════════════════════════════════════════════════════════════════

_INDUCTION_SPEC = ToolSpec(
    name="motordrive_induction_slip_torque",
    description=(
        "Basic induction motor torque at a given slip using the approximate "
        "equivalent circuit (Chapman §6.4 model).\n\n"
        "P_ag = 3 × Vs² × (R2/s) / [(Rs + R2/s)² + X_eq²]\n"
        "T = P_ag / ω_sync\n\n"
        "Warnings for slip > 20 % (unstable region) or slip < 0 (generator mode).\n\n"
        "Input: { synchronous_speed_rpm, rotor_resistance_ohm, stator_resistance_ohm, "
        "leakage_reactance_ohm, supply_voltage_v, slip }\n"
        "Returns: { ok, omega_sync_rad_s, omega_rotor_rad_s, rotor_speed_rpm, "
        "torque_nm, air_gap_power_w, stator_copper_loss_w, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "synchronous_speed_rpm": {"type": "number", "description": "Synchronous speed [RPM]."},
            "rotor_resistance_ohm": {"type": "number", "description": "Rotor resistance referred to stator [Ω]."},
            "stator_resistance_ohm": {"type": "number", "description": "Stator resistance [Ω]."},
            "leakage_reactance_ohm": {"type": "number", "description": "Total leakage reactance [Ω]."},
            "supply_voltage_v": {"type": "number", "description": "Per-phase RMS supply voltage [V]."},
            "slip": {"type": "number", "description": "Per-unit slip s = (ω_s − ω_r) / ω_s (non-zero)."},
        },
        "required": [
            "synchronous_speed_rpm", "rotor_resistance_ohm", "stator_resistance_ohm",
            "leakage_reactance_ohm", "supply_voltage_v", "slip",
        ],
    },
)


@register(_INDUCTION_SPEC, write=False)
async def motordrive_induction_slip_torque_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = induction_motor_slip_torque(
        synchronous_speed_rpm=a.get("synchronous_speed_rpm"),
        rotor_resistance_ohm=a.get("rotor_resistance_ohm"),
        stator_resistance_ohm=a.get("stator_resistance_ohm"),
        leakage_reactance_ohm=a.get("leakage_reactance_ohm"),
        supply_voltage_v=a.get("supply_voltage_v"),
        slip=a.get("slip"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. motordrive_inverter_sizing
# ═══════════════════════════════════════════════════════════════════════════════

_INVERTER_SPEC = ToolSpec(
    name="motordrive_inverter_sizing",
    description=(
        "Size a three-phase inverter: device ratings, switching loss, conduction loss.\n\n"
        "I_device_rated = I_peak / current_derating\n"
        "V_device_rated = V_dc × 2\n"
        "P_sw = N_devices × E_sw × fsw\n"
        "P_cond = phases × 2 × V_drop × I_rms\n\n"
        "Input: { peak_phase_current_a, peak_phase_voltage_v, dc_link_voltage_v, "
        "switching_freq_hz, conduction_voltage_drop_v?, switching_energy_uj?, "
        "phases?, current_derating? }\n"
        "Returns: { ok, i_device_rated_a, v_device_rated_v, i_rms_a, "
        "p_switching_w, p_conduction_w, p_total_loss_w, n_devices, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "peak_phase_current_a": {"type": "number", "description": "Peak phase current [A]."},
            "peak_phase_voltage_v": {"type": "number", "description": "Peak phase voltage [V]."},
            "dc_link_voltage_v": {"type": "number", "description": "DC bus voltage [V]."},
            "switching_freq_hz": {"type": "number", "description": "PWM switching frequency [Hz]."},
            "conduction_voltage_drop_v": {"type": "number", "description": "Device on-state voltage drop [V] (default 2.0 V)."},
            "switching_energy_uj": {"type": "number", "description": "Per-device switching energy [μJ/cycle] (default 100 μJ)."},
            "phases": {"type": "integer", "description": "Number of phases (default 3)."},
            "current_derating": {"type": "number", "description": "Device current derating factor (default 0.80)."},
        },
        "required": [
            "peak_phase_current_a", "peak_phase_voltage_v",
            "dc_link_voltage_v", "switching_freq_hz",
        ],
    },
)


@register(_INVERTER_SPEC, write=False)
async def motordrive_inverter_sizing_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = inverter_sizing(
        peak_phase_current_a=a.get("peak_phase_current_a"),
        peak_phase_voltage_v=a.get("peak_phase_voltage_v"),
        dc_link_voltage_v=a.get("dc_link_voltage_v"),
        switching_freq_hz=a.get("switching_freq_hz"),
        conduction_voltage_drop_v=a.get("conduction_voltage_drop_v", 2.0),
        switching_energy_uj=a.get("switching_energy_uj", 100.0),
        phases=a.get("phases", 3),
        current_derating=a.get("current_derating", 0.80),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. motordrive_regen_energy
# ═══════════════════════════════════════════════════════════════════════════════

_REGEN_SPEC = ToolSpec(
    name="motordrive_regen_energy",
    description=(
        "Compute recoverable kinetic energy during regenerative deceleration.\n\n"
        "ΔKE = 0.5 × J × (ω_i² − ω_f²)\n"
        "E_regen = ΔKE × η_drivetrain\n\n"
        "Input: { inertia_kgm2, speed_initial_rpm, speed_final_rpm, drivetrain_efficiency? }\n"
        "Returns: { ok, delta_ke_j, e_regen_j, e_dissipated_j, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "inertia_kgm2": {"type": "number", "description": "Total rotating inertia [kg·m²]."},
            "speed_initial_rpm": {"type": "number", "description": "Initial speed [RPM]."},
            "speed_final_rpm": {"type": "number", "description": "Final speed [RPM] (must be < initial)."},
            "drivetrain_efficiency": {"type": "number", "description": "Round-trip drivetrain efficiency (default 0.90)."},
        },
        "required": ["inertia_kgm2", "speed_initial_rpm", "speed_final_rpm"],
    },
)


@register(_REGEN_SPEC, write=False)
async def motordrive_regen_energy_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = regen_energy(
        inertia_kgm2=a.get("inertia_kgm2"),
        speed_initial_rpm=a.get("speed_initial_rpm"),
        speed_final_rpm=a.get("speed_final_rpm"),
        drivetrain_efficiency=a.get("drivetrain_efficiency", 0.90),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. motordrive_brake_resistor
# ═══════════════════════════════════════════════════════════════════════════════

_BRAKE_RES_SPEC = ToolSpec(
    name="motordrive_brake_resistor",
    description=(
        "Size a brake (dynamic braking) resistor for a DC-link inverter.\n\n"
        "V_brake = V_dc × (1 + overvoltage_margin)\n"
        "R_brake = V_brake² × t_discharge / (2 × E_regen)\n"
        "P_avg = E_regen / t_discharge\n"
        "P_peak = V_brake² / R_brake\n\n"
        "Input: { regen_energy_j, dc_link_voltage_v, discharge_time_s, "
        "overvoltage_margin_frac? }\n"
        "Returns: { ok, v_brake_v, r_brake_ohm, p_avg_w, p_peak_w, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "regen_energy_j": {"type": "number", "description": "Total energy to dissipate [J]."},
            "dc_link_voltage_v": {"type": "number", "description": "Nominal DC-link voltage [V]."},
            "discharge_time_s": {"type": "number", "description": "Maximum discharge time [s]."},
            "overvoltage_margin_frac": {"type": "number", "description": "Fractional overvoltage above nominal (default 0.10 = 10 %)."},
        },
        "required": ["regen_energy_j", "dc_link_voltage_v", "discharge_time_s"],
    },
)


@register(_BRAKE_RES_SPEC, write=False)
async def motordrive_brake_resistor_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = brake_resistor_sizing(
        regen_energy_j=a.get("regen_energy_j"),
        dc_link_voltage_v=a.get("dc_link_voltage_v"),
        discharge_time_s=a.get("discharge_time_s"),
        overvoltage_margin_frac=a.get("overvoltage_margin_frac", 0.10),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. motordrive_thermal_duty
# ═══════════════════════════════════════════════════════════════════════════════

_THERMAL_DUTY_SPEC = ToolSpec(
    name="motordrive_thermal_duty",
    description=(
        "Motor thermal duty-cycle check: steady-state winding temperature "
        "from ambient, losses, and thermal resistance.\n\n"
        "P_eff = P_loss × duty_cycle\n"
        "ΔT = P_eff × Rth_winding_ambient\n"
        "T_winding = T_ambient + ΔT\n\n"
        "With thermal time constant: ΔT = ΔT_ss × (1 − exp(−t_on / τ))\n\n"
        "A warning is issued when T_winding > t_max_c (default 130 °C Class F).\n\n"
        "Input: { p_loss_w, rth_winding_ambient, t_ambient_c, duty_cycle?, "
        "t_max_c?, thermal_time_constant_s?, cycle_time_s? }\n"
        "Returns: { ok, t_winding_c, delta_t_k, t_margin_k, over_temp, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_loss_w": {"type": "number", "description": "Total motor loss at operating point [W]."},
            "rth_winding_ambient": {"type": "number", "description": "Winding-to-ambient thermal resistance [°C/W]."},
            "t_ambient_c": {"type": "number", "description": "Ambient temperature [°C]."},
            "duty_cycle": {"type": "number", "description": "Duty cycle S (0 < S ≤ 1, default 1.0 = continuous)."},
            "t_max_c": {"type": "number", "description": "Maximum winding temperature [°C] (default 130 °C Class F)."},
            "thermal_time_constant_s": {"type": "number", "description": "Motor thermal time constant [s] (0 = not used)."},
            "cycle_time_s": {"type": "number", "description": "Duty cycle period [s] (0 = not used)."},
        },
        "required": ["p_loss_w", "rth_winding_ambient", "t_ambient_c"],
    },
)


@register(_THERMAL_DUTY_SPEC, write=False)
async def motordrive_thermal_duty_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = thermal_duty_check(
        p_loss_w=a.get("p_loss_w"),
        rth_winding_ambient=a.get("rth_winding_ambient"),
        t_ambient_c=a.get("t_ambient_c"),
        duty_cycle=a.get("duty_cycle", 1.0),
        t_max_c=a.get("t_max_c", 130.0),
        thermal_time_constant_s=a.get("thermal_time_constant_s", 0.0),
        cycle_time_s=a.get("cycle_time_s", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS export — consumed by plugin._register_tools
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    (_LOAD_TORQUE_SPEC.name,       _LOAD_TORQUE_SPEC,       motordrive_load_torque_power_tool),
    (_REFLECTED_INERTIA_SPEC.name, _REFLECTED_INERTIA_SPEC, motordrive_reflected_inertia_tool),
    (_INERTIA_MATCH_SPEC.name,     _INERTIA_MATCH_SPEC,     motordrive_inertia_match_tool),
    (_RMS_TORQUE_SPEC.name,        _RMS_TORQUE_SPEC,        motordrive_rms_torque_tool),
    (_MOTOR_CONSTANTS_SPEC.name,   _MOTOR_CONSTANTS_SPEC,   motordrive_motor_constants_tool),
    (_DC_OP_SPEC.name,             _DC_OP_SPEC,             motordrive_dc_operating_point_tool),
    (_BLDC_PMSM_SPEC.name,         _BLDC_PMSM_SPEC,         motordrive_bldc_pmsm_op_point_tool),
    (_INDUCTION_SPEC.name,         _INDUCTION_SPEC,         motordrive_induction_slip_torque_tool),
    (_INVERTER_SPEC.name,          _INVERTER_SPEC,          motordrive_inverter_sizing_tool),
    (_REGEN_SPEC.name,             _REGEN_SPEC,             motordrive_regen_energy_tool),
    (_BRAKE_RES_SPEC.name,         _BRAKE_RES_SPEC,         motordrive_brake_resistor_tool),
    (_THERMAL_DUTY_SPEC.name,      _THERMAL_DUTY_SPEC,      motordrive_thermal_duty_tool),
]
