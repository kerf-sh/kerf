"""
Gate-driver & switching-loss design — LLM tools.

Exposes tools to the Kerf agent layer:

  gatedrive_gate_drive_power    — Qg·fsw·Vgs drive current and driver power
  gatedrive_gate_resistor       — gate-resistor for target transition time, peak current
  gatedrive_miller_spurious     — Miller-plateau dv/dt spurious-turn-on margin
  gatedrive_switching_loss      — Eon/Eoff energy and Psw from overlap model
  gatedrive_conduction_loss     — Rds(on)·Irms² or Vce·I_avg conduction loss
  gatedrive_diode_recovery_loss — body/freewheeling diode Qrr reverse-recovery loss
  gatedrive_total_thermal       — aggregate loss, Tj, heatsink sizing, SOA check
  gatedrive_dead_time           — minimum dead time from Coss; shoot-through check
  gatedrive_bootstrap_cap       — high-side bootstrap capacitor sizing

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

from kerf_electronics.gatedrive.drive import (
    gate_drive_power,
    gate_resistor_design,
    miller_spurious_turnon,
    switching_loss,
    conduction_loss,
    diode_recovery_loss,
    total_loss_and_thermal,
    dead_time_select,
    bootstrap_cap_sizing,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. gatedrive_gate_drive_power
# ═══════════════════════════════════════════════════════════════════════════════

_GD_POWER_SPEC = ToolSpec(
    name="gatedrive_gate_drive_power",
    description=(
        "Compute gate charge parameters and gate-driver power dissipation.\n\n"
        "Model (IR AN-978 / TI SLUA618):\n"
        "  Ig_avg  = Qg × fsw\n"
        "  P_drive = Qg × fsw × Vgs_swing\n\n"
        "Supports negative turn-off bias (vgs_off_v < 0) for spurious-turn-on suppression.\n\n"
        "Input: { qg_c, fsw_hz, vgs_drive_v, vgs_off_v? }\n"
        "Returns: { ok, ig_avg_a, p_drive_w, vgs_swing_v, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "qg_c": {
                "type": "number",
                "description": "Total gate charge [C] (e.g. 100e-9 for 100 nC).",
            },
            "fsw_hz": {
                "type": "number",
                "description": "Switching frequency [Hz].",
            },
            "vgs_drive_v": {
                "type": "number",
                "description": "Gate drive voltage (turn-on) [V], e.g. 12 or 15.",
            },
            "vgs_off_v": {
                "type": "number",
                "description": (
                    "Gate turn-off voltage [V] (default 0). "
                    "Use negative value (e.g. -5) for negative turn-off bias."
                ),
            },
        },
        "required": ["qg_c", "fsw_hz", "vgs_drive_v"],
    },
)


@register(_GD_POWER_SPEC, write=False)
async def gatedrive_gate_drive_power(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = gate_drive_power(
        qg_c=a.get("qg_c"),
        fsw_hz=a.get("fsw_hz"),
        vgs_drive_v=a.get("vgs_drive_v"),
        vgs_off_v=a.get("vgs_off_v", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. gatedrive_gate_resistor
# ═══════════════════════════════════════════════════════════════════════════════

_GD_RG_SPEC = ToolSpec(
    name="gatedrive_gate_resistor",
    description=(
        "Select external gate resistor for a target switch transition time.\n\n"
        "Model (Mohan §6.4 simplified charge-based):\n"
        "  Rg_total = Vgs_swing × t_transition / Qg\n"
        "  Rg_ext   = Rg_total − Rg_internal\n"
        "  Ipeak    = Vgs_swing / Rg_total\n\n"
        "Input: { vgs_drive_v, qg_c, t_transition_s, vgs_off_v?, rg_internal_ohm?, vgs_th_v? }\n"
        "Returns: { ok, rg_total_ohm, rg_ext_ohm, ipeak_a, vgs_swing_v, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "vgs_drive_v": {
                "type": "number",
                "description": "Gate drive voltage [V].",
            },
            "qg_c": {
                "type": "number",
                "description": "Total gate charge [C].",
            },
            "t_transition_s": {
                "type": "number",
                "description": "Target turn-on or turn-off time [s].",
            },
            "vgs_off_v": {
                "type": "number",
                "description": "Turn-off gate voltage [V] (default 0).",
            },
            "rg_internal_ohm": {
                "type": "number",
                "description": "Device internal gate resistance [Ω] (default 0).",
            },
            "vgs_th_v": {
                "type": "number",
                "description": "Threshold voltage [V] (optional; triggers margin warning).",
            },
        },
        "required": ["vgs_drive_v", "qg_c", "t_transition_s"],
    },
)


@register(_GD_RG_SPEC, write=False)
async def gatedrive_gate_resistor(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = gate_resistor_design(
        vgs_drive_v=a.get("vgs_drive_v"),
        qg_c=a.get("qg_c"),
        t_transition_s=a.get("t_transition_s"),
        vgs_off_v=a.get("vgs_off_v", 0.0),
        rg_internal_ohm=a.get("rg_internal_ohm", 0.0),
        vgs_th_v=a.get("vgs_th_v"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. gatedrive_miller_spurious
# ═══════════════════════════════════════════════════════════════════════════════

_GD_MILLER_SPEC = ToolSpec(
    name="gatedrive_miller_spurious",
    description=(
        "Miller-plateau analysis and dv/dt-induced spurious-turn-on margin.\n\n"
        "Model (Infineon AN-6076):\n"
        "  dv/dt_crit = (Vgs_th − Vgs_off) / (Cgd × Rg_off)\n\n"
        "If t_rise_s is supplied, bus dv/dt = Vbus / t_rise_s is estimated and compared "
        "to dv/dt_crit. Spurious-turn-on risk is flagged when dv/dt_bus ≥ dv/dt_crit.\n\n"
        "Input: { cgd_f, vgs_th_v, rg_off_ohm, vbus_v, t_rise_s?, vgs_off_v? }\n"
        "Returns: { ok, dvdt_critical_vps, spurious_risk, margin_ratio, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cgd_f": {
                "type": "number",
                "description": "Gate-drain (Miller) capacitance [F].",
            },
            "vgs_th_v": {
                "type": "number",
                "description": "Gate threshold voltage [V].",
            },
            "rg_off_ohm": {
                "type": "number",
                "description": "Total gate resistance during turn-off [Ω].",
            },
            "vbus_v": {
                "type": "number",
                "description": "DC bus voltage [V].",
            },
            "t_rise_s": {
                "type": "number",
                "description": (
                    "Complementary switch drain rise time [s] (optional). "
                    "Used to estimate dv/dt_bus = Vbus / t_rise_s."
                ),
            },
            "vgs_off_v": {
                "type": "number",
                "description": "Turn-off gate voltage [V] (default 0; use negative for neg. bias).",
            },
        },
        "required": ["cgd_f", "vgs_th_v", "rg_off_ohm", "vbus_v"],
    },
)


@register(_GD_MILLER_SPEC, write=False)
async def gatedrive_miller_spurious(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = miller_spurious_turnon(
        cgd_f=a.get("cgd_f"),
        vgs_th_v=a.get("vgs_th_v"),
        rg_off_ohm=a.get("rg_off_ohm"),
        vbus_v=a.get("vbus_v"),
        t_rise_s=a.get("t_rise_s"),
        vgs_off_v=a.get("vgs_off_v", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. gatedrive_switching_loss
# ═══════════════════════════════════════════════════════════════════════════════

_GD_SW_LOSS_SPEC = ToolSpec(
    name="gatedrive_switching_loss",
    description=(
        "Switching energy (Eon, Eoff) and total switching loss from the "
        "current/voltage overlap model.\n\n"
        "Model (Mohan §6.5):\n"
        "  Eon  = 0.5 × Vbus × Iload × t_on\n"
        "  Eoff = 0.5 × Vbus × Iload × t_off\n"
        "  Psw  = (Eon + Eoff) × fsw\n\n"
        "When rg_actual_ohm and rg_ref_ohm are supplied, transition times are "
        "scaled linearly: t_scaled = t_ref × (Rg_actual / Rg_ref).\n\n"
        "Input: { vbus_v, i_load_a, t_on_s, t_off_s, fsw_hz, rg_actual_ohm?, rg_ref_ohm? }\n"
        "Returns: { ok, eon_j, eoff_j, esw_total_j, psw_w, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "vbus_v": {
                "type": "number",
                "description": "DC bus voltage [V].",
            },
            "i_load_a": {
                "type": "number",
                "description": "Load current at switching instant [A].",
            },
            "t_on_s": {
                "type": "number",
                "description": "Turn-on transition time [s].",
            },
            "t_off_s": {
                "type": "number",
                "description": "Turn-off transition time [s].",
            },
            "fsw_hz": {
                "type": "number",
                "description": "Switching frequency [Hz].",
            },
            "rg_actual_ohm": {
                "type": "number",
                "description": "Actual gate resistance [Ω] (optional, for Rg scaling).",
            },
            "rg_ref_ohm": {
                "type": "number",
                "description": "Datasheet reference gate resistance [Ω] (optional).",
            },
        },
        "required": ["vbus_v", "i_load_a", "t_on_s", "t_off_s", "fsw_hz"],
    },
)


@register(_GD_SW_LOSS_SPEC, write=False)
async def gatedrive_switching_loss(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = switching_loss(
        vbus_v=a.get("vbus_v"),
        i_load_a=a.get("i_load_a"),
        t_on_s=a.get("t_on_s"),
        t_off_s=a.get("t_off_s"),
        fsw_hz=a.get("fsw_hz"),
        rg_actual_ohm=a.get("rg_actual_ohm"),
        rg_ref_ohm=a.get("rg_ref_ohm"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. gatedrive_conduction_loss
# ═══════════════════════════════════════════════════════════════════════════════

_GD_COND_SPEC = ToolSpec(
    name="gatedrive_conduction_loss",
    description=(
        "Conduction loss for MOSFET or IGBT power switches.\n\n"
        "MOSFET: P_cond = Rds(on) × Irms²\n"
        "IGBT:   P_cond = Vce_sat × I_avg\n\n"
        "Input: { device_type, i_rms_a, rds_on_ohm?, vce_sat_v?, i_avg_a?, duty? }\n"
        "Returns: { ok, p_cond_w, formula, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "device_type": {
                "type": "string",
                "enum": ["mosfet", "igbt"],
                "description": "Device type: 'mosfet' or 'igbt'.",
            },
            "i_rms_a": {
                "type": "number",
                "description": "RMS current through the device [A].",
            },
            "rds_on_ohm": {
                "type": "number",
                "description": "MOSFET drain-source on-resistance [Ω] (required for mosfet).",
            },
            "vce_sat_v": {
                "type": "number",
                "description": "IGBT collector-emitter saturation voltage [V] (required for igbt).",
            },
            "i_avg_a": {
                "type": "number",
                "description": "Average current [A] (optional, for IGBT; preferred over simplified).",
            },
            "duty": {
                "type": "number",
                "description": "Duty cycle [0..1] (used for simplified IGBT I_avg estimate, default 1).",
            },
        },
        "required": ["device_type", "i_rms_a"],
    },
)


@register(_GD_COND_SPEC, write=False)
async def gatedrive_conduction_loss(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = conduction_loss(
        device_type=a.get("device_type"),
        i_rms_a=a.get("i_rms_a"),
        rds_on_ohm=a.get("rds_on_ohm"),
        vce_sat_v=a.get("vce_sat_v"),
        i_avg_a=a.get("i_avg_a"),
        duty=a.get("duty", 1.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. gatedrive_diode_recovery_loss
# ═══════════════════════════════════════════════════════════════════════════════

_GD_RR_SPEC = ToolSpec(
    name="gatedrive_diode_recovery_loss",
    description=(
        "Body diode (or freewheeling diode) reverse-recovery switching loss.\n\n"
        "Model (Mohan §6.2):\n"
        "  P_rr = Qrr × Vbus × fsw\n\n"
        "Significant for Si MOSFET body diodes; negligible for SiC/GaN.\n\n"
        "Input: { qrr_c, vbus_v, fsw_hz }\n"
        "Returns: { ok, p_rr_w, e_rr_j, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "qrr_c": {
                "type": "number",
                "description": "Reverse-recovery charge [C] (from datasheet).",
            },
            "vbus_v": {
                "type": "number",
                "description": "DC bus voltage [V].",
            },
            "fsw_hz": {
                "type": "number",
                "description": "Switching frequency [Hz].",
            },
        },
        "required": ["qrr_c", "vbus_v", "fsw_hz"],
    },
)


@register(_GD_RR_SPEC, write=False)
async def gatedrive_diode_recovery_loss(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = diode_recovery_loss(
        qrr_c=a.get("qrr_c"),
        vbus_v=a.get("vbus_v"),
        fsw_hz=a.get("fsw_hz"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. gatedrive_total_thermal
# ═══════════════════════════════════════════════════════════════════════════════

_GD_THERMAL_SPEC = ToolSpec(
    name="gatedrive_total_thermal",
    description=(
        "Aggregate all loss components and compute junction temperature.\n\n"
        "Thermal model:\n"
        "  P_total = Psw + Pcond + Pdrive + Prr\n"
        "  Tj = T_amb + P_total × (Rθjc + Rθcs + Rθsa)\n"
        "  Rθsa_required = (Tj_max − T_amb) / P_total − Rθjc − Rθcs\n\n"
        "Also performs SOA derating check (Vds_stress > 80% of rated → warning).\n\n"
        "Input: { p_sw_w, p_cond_w, p_drive_w?, p_rr_w?, t_amb_c?, "
        "r_th_jc?, r_th_cs?, r_th_sa?, tj_max_c?, vds_stress_v?, vds_rated_v? }\n"
        "Returns: { ok, p_total_w, tj_c, over_temp, t_margin_c, r_th_sa_required, soa_ok, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_sw_w": {
                "type": "number",
                "description": "Switching loss [W].",
            },
            "p_cond_w": {
                "type": "number",
                "description": "Conduction loss [W].",
            },
            "p_drive_w": {
                "type": "number",
                "description": "Gate driver power [W] (default 0).",
            },
            "p_rr_w": {
                "type": "number",
                "description": "Diode recovery loss [W] (default 0).",
            },
            "t_amb_c": {
                "type": "number",
                "description": "Ambient temperature [°C] (default 25).",
            },
            "r_th_jc": {
                "type": "number",
                "description": "Junction-to-case thermal resistance [°C/W] (default 0).",
            },
            "r_th_cs": {
                "type": "number",
                "description": "Case-to-heatsink thermal resistance [°C/W] (default 0).",
            },
            "r_th_sa": {
                "type": "number",
                "description": "Heatsink-to-ambient thermal resistance [°C/W] (default 0).",
            },
            "tj_max_c": {
                "type": "number",
                "description": "Maximum junction temperature [°C] (default 150).",
            },
            "vds_stress_v": {
                "type": "number",
                "description": "Actual Vds/Vce voltage stress [V] (optional, SOA check).",
            },
            "vds_rated_v": {
                "type": "number",
                "description": "Rated device breakdown voltage [V] (optional, SOA check).",
            },
        },
        "required": ["p_sw_w", "p_cond_w"],
    },
)


@register(_GD_THERMAL_SPEC, write=False)
async def gatedrive_total_thermal(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = total_loss_and_thermal(
        p_sw_w=a.get("p_sw_w"),
        p_cond_w=a.get("p_cond_w"),
        p_drive_w=a.get("p_drive_w", 0.0),
        p_rr_w=a.get("p_rr_w", 0.0),
        t_amb_c=a.get("t_amb_c", 25.0),
        r_th_jc=a.get("r_th_jc", 0.0),
        r_th_cs=a.get("r_th_cs", 0.0),
        r_th_sa=a.get("r_th_sa", 0.0),
        tj_max_c=a.get("tj_max_c", 150.0),
        vds_stress_v=a.get("vds_stress_v"),
        vds_rated_v=a.get("vds_rated_v"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. gatedrive_dead_time
# ═══════════════════════════════════════════════════════════════════════════════

_GD_DT_SPEC = ToolSpec(
    name="gatedrive_dead_time",
    description=(
        "Minimum dead time selection and shoot-through / body-diode risk check.\n\n"
        "Model (TI SLUA618):\n"
        "  t_dead_min = Coss × Vbus / I_drive\n\n"
        "If t_dead_s is supplied it is compared against t_dead_min (shoot-through risk) "
        "and t_body_diode_max_s (excessive body-diode conduction).\n\n"
        "Input: { coss_f, vbus_v, i_drive_a, t_dead_s?, t_body_diode_max_s? }\n"
        "Returns: { ok, t_dead_min_s, shoot_through_risk?, excessive_body_diode?, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "coss_f": {
                "type": "number",
                "description": "Output capacitance Coss [F] (from datasheet).",
            },
            "vbus_v": {
                "type": "number",
                "description": "DC bus voltage [V].",
            },
            "i_drive_a": {
                "type": "number",
                "description": "Available commutation drive current [A].",
            },
            "t_dead_s": {
                "type": "number",
                "description": "Actual dead time used [s] (optional, for check).",
            },
            "t_body_diode_max_s": {
                "type": "number",
                "description": "Maximum body-diode conduction time [s] (default 500 ns).",
            },
        },
        "required": ["coss_f", "vbus_v", "i_drive_a"],
    },
)


@register(_GD_DT_SPEC, write=False)
async def gatedrive_dead_time(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = dead_time_select(
        coss_f=a.get("coss_f"),
        vbus_v=a.get("vbus_v"),
        i_drive_a=a.get("i_drive_a"),
        t_dead_s=a.get("t_dead_s"),
        t_body_diode_max_s=a.get("t_body_diode_max_s", 500e-9),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. gatedrive_bootstrap_cap
# ═══════════════════════════════════════════════════════════════════════════════

_GD_BOOT_SPEC = ToolSpec(
    name="gatedrive_bootstrap_cap",
    description=(
        "High-side bootstrap capacitor sizing.\n\n"
        "Model (Fairchild AN-6076):\n"
        "  C_boot = (Qg×N + I_bias×T + I_leakage×T + Q_extra) / ΔV_boot\n\n"
        "Input: { qg_c, i_bias_a, fsw_hz, dv_max_v, n_cycles?, i_leakage_a?, q_extra_c? }\n"
        "Returns: { ok, c_boot_f, q_total_c, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "qg_c": {
                "type": "number",
                "description": "Gate charge per switching event [C].",
            },
            "i_bias_a": {
                "type": "number",
                "description": "Quiescent bias current of the high-side driver IC [A].",
            },
            "fsw_hz": {
                "type": "number",
                "description": "Switching frequency [Hz].",
            },
            "dv_max_v": {
                "type": "number",
                "description": "Maximum allowed bootstrap voltage droop [V].",
            },
            "n_cycles": {
                "type": "integer",
                "description": "Number of consecutive high-side cycles before recharge (default 1).",
            },
            "i_leakage_a": {
                "type": "number",
                "description": "Bootstrap capacitor leakage current [A] (default 0).",
            },
            "q_extra_c": {
                "type": "number",
                "description": "Additional charge budget (e.g. level-shifter) [C] (default 0).",
            },
        },
        "required": ["qg_c", "i_bias_a", "fsw_hz", "dv_max_v"],
    },
)


@register(_GD_BOOT_SPEC, write=False)
async def gatedrive_bootstrap_cap(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = bootstrap_cap_sizing(
        qg_c=a.get("qg_c"),
        i_bias_a=a.get("i_bias_a"),
        fsw_hz=a.get("fsw_hz"),
        dv_max_v=a.get("dv_max_v"),
        n_cycles=a.get("n_cycles", 1),
        i_leakage_a=a.get("i_leakage_a", 0.0),
        q_extra_c=a.get("q_extra_c", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS export — consumed by plugin._register_tools
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    (_GD_POWER_SPEC.name,    _GD_POWER_SPEC,    gatedrive_gate_drive_power),
    (_GD_RG_SPEC.name,       _GD_RG_SPEC,       gatedrive_gate_resistor),
    (_GD_MILLER_SPEC.name,   _GD_MILLER_SPEC,   gatedrive_miller_spurious),
    (_GD_SW_LOSS_SPEC.name,  _GD_SW_LOSS_SPEC,  gatedrive_switching_loss),
    (_GD_COND_SPEC.name,     _GD_COND_SPEC,     gatedrive_conduction_loss),
    (_GD_RR_SPEC.name,       _GD_RR_SPEC,       gatedrive_diode_recovery_loss),
    (_GD_THERMAL_SPEC.name,  _GD_THERMAL_SPEC,  gatedrive_total_thermal),
    (_GD_DT_SPEC.name,       _GD_DT_SPEC,       gatedrive_dead_time),
    (_GD_BOOT_SPEC.name,     _GD_BOOT_SPEC,     gatedrive_bootstrap_cap),
]
