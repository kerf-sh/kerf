"""
Switching DC-DC converter design — LLM tools.

Exposes tools to the Kerf agent layer:

  powerconv_buck_design         — buck (step-down) CCM steady-state design
  powerconv_boost_design        — boost (step-up) CCM steady-state design + RHP-zero note
  powerconv_buck_boost_design   — inverting buck-boost CCM design + RHP-zero note
  powerconv_flyback_design      — isolated flyback: turns ratio, Lp, peak currents, RCD snubber note
  powerconv_sepic_design        — SEPIC CCM design: dual inductors, coupling cap, switch stresses
  powerconv_thermal             — junction temperature from power loss × thermal resistance

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

from kerf_electronics.powerconv.converter import (
    buck_design,
    boost_design,
    buck_boost_design,
    flyback_design,
    sepic_design,
    converter_thermal,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. powerconv_buck_design
# ═══════════════════════════════════════════════════════════════════════════════

_BUCK_SPEC = ToolSpec(
    name="powerconv_buck_design",
    description=(
        "Steady-state CCM design for a synchronous/non-synchronous buck (step-down) converter.\n\n"
        "D = Vout / Vin\n"
        "L = (Vin − Vout) × D / (fsw × ΔIL)\n"
        "I_L_peak = Iout + ΔIL/2\n"
        "V_sw_stress = Vin\n\n"
        "Warnings: DCM-when-CCM-assumed, near-CCM-boundary, high duty, efficiency-low.\n\n"
        "Input: { v_in, v_out, i_out, fsw, ripple_frac?, c_out_f?, esr_ohm?, r_ds_on?, "
        "v_diode?, dcr_ohm?, t_rise_s?, t_fall_s? }\n"
        "Returns: { ok, duty, l_h, l_crit_h, ccm, delta_il_a, i_l_peak_a, i_l_valley_a, "
        "i_l_rms_a, i_sw_rms_a, i_diode_rms_a, v_sw_stress_v, v_diode_stress_v, "
        "c_out_min_f, delta_v_esr_v, delta_v_cap_v, delta_v_total_v, "
        "p_sw_cond_w, p_sw_switch_w, p_diode_w, p_dcr_w, p_total_loss_w, "
        "p_out_w, efficiency, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_in": {"type": "number", "description": "Input voltage [V]."},
            "v_out": {"type": "number", "description": "Output voltage [V] (must be < v_in)."},
            "i_out": {"type": "number", "description": "Output (load) current [A]."},
            "fsw": {"type": "number", "description": "Switching frequency [Hz]."},
            "ripple_frac": {"type": "number", "description": "Inductor current ripple as fraction of Iout (default 0.30)."},
            "c_out_f": {"type": "number", "description": "Output capacitor [F] (default 100 µF)."},
            "esr_ohm": {"type": "number", "description": "Output cap ESR [Ω] (default 20 mΩ)."},
            "r_ds_on": {"type": "number", "description": "Switch Rds(on) [Ω] (default 50 mΩ)."},
            "v_diode": {"type": "number", "description": "Catch diode forward voltage [V] (default 0.5 V)."},
            "dcr_ohm": {"type": "number", "description": "Inductor DCR [Ω] (default 10 mΩ)."},
            "t_rise_s": {"type": "number", "description": "Switch current rise time [s] (default 20 ns)."},
            "t_fall_s": {"type": "number", "description": "Switch current fall time [s] (default 20 ns)."},
        },
        "required": ["v_in", "v_out", "i_out", "fsw"],
    },
)


@register(_BUCK_SPEC, write=False)
async def powerconv_buck_design_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = buck_design(
        v_in=a.get("v_in"),
        v_out=a.get("v_out"),
        i_out=a.get("i_out"),
        fsw=a.get("fsw"),
        ripple_frac=a.get("ripple_frac", 0.30),
        c_out_f=a.get("c_out_f", 100e-6),
        esr_ohm=a.get("esr_ohm", 0.020),
        r_ds_on=a.get("r_ds_on", 0.050),
        v_diode=a.get("v_diode", 0.5),
        dcr_ohm=a.get("dcr_ohm", 0.010),
        t_rise_s=a.get("t_rise_s", 20e-9),
        t_fall_s=a.get("t_fall_s", 20e-9),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. powerconv_boost_design
# ═══════════════════════════════════════════════════════════════════════════════

_BOOST_SPEC = ToolSpec(
    name="powerconv_boost_design",
    description=(
        "Steady-state CCM design for a boost (step-up) converter.\n\n"
        "D = 1 − Vin / Vout\n"
        "L = Vin × D / (fsw × ΔIL)\n"
        "V_sw_stress = Vout\n"
        "f_RHP = (1−D)² × Vout / (2π × L × Iout)\n\n"
        "Warnings: DCM-when-CCM-assumed, RHP-zero < 20 % fsw (bandwidth limitation), "
        "high duty, efficiency-low.\n\n"
        "Input: { v_in, v_out, i_out, fsw, ripple_frac?, c_out_f?, esr_ohm?, r_ds_on?, "
        "v_diode?, dcr_ohm?, t_rise_s?, t_fall_s? }\n"
        "Returns: { ok, duty, l_h, l_crit_h, ccm, f_rhp_hz, delta_il_a, i_in_avg_a, "
        "i_l_peak_a, i_l_rms_a, i_sw_rms_a, i_diode_rms_a, v_sw_stress_v, "
        "v_diode_stress_v, c_out_min_f, delta_v_esr_v, delta_v_cap_v, delta_v_total_v, "
        "p_sw_cond_w, p_sw_switch_w, p_diode_w, p_dcr_w, p_total_loss_w, "
        "p_out_w, efficiency, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_in": {"type": "number", "description": "Input voltage [V]."},
            "v_out": {"type": "number", "description": "Output voltage [V] (must be > v_in)."},
            "i_out": {"type": "number", "description": "Output (load) current [A]."},
            "fsw": {"type": "number", "description": "Switching frequency [Hz]."},
            "ripple_frac": {"type": "number", "description": "Inductor current ripple fraction of Iin_avg (default 0.30)."},
            "c_out_f": {"type": "number", "description": "Output capacitor [F] (default 100 µF)."},
            "esr_ohm": {"type": "number", "description": "Output cap ESR [Ω] (default 20 mΩ)."},
            "r_ds_on": {"type": "number", "description": "Switch Rds(on) [Ω] (default 50 mΩ)."},
            "v_diode": {"type": "number", "description": "Boost diode forward voltage [V] (default 0.5 V)."},
            "dcr_ohm": {"type": "number", "description": "Inductor DCR [Ω] (default 10 mΩ)."},
            "t_rise_s": {"type": "number", "description": "Switch current rise time [s] (default 20 ns)."},
            "t_fall_s": {"type": "number", "description": "Switch current fall time [s] (default 20 ns)."},
        },
        "required": ["v_in", "v_out", "i_out", "fsw"],
    },
)


@register(_BOOST_SPEC, write=False)
async def powerconv_boost_design_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = boost_design(
        v_in=a.get("v_in"),
        v_out=a.get("v_out"),
        i_out=a.get("i_out"),
        fsw=a.get("fsw"),
        ripple_frac=a.get("ripple_frac", 0.30),
        c_out_f=a.get("c_out_f", 100e-6),
        esr_ohm=a.get("esr_ohm", 0.020),
        r_ds_on=a.get("r_ds_on", 0.050),
        v_diode=a.get("v_diode", 0.5),
        dcr_ohm=a.get("dcr_ohm", 0.010),
        t_rise_s=a.get("t_rise_s", 20e-9),
        t_fall_s=a.get("t_fall_s", 20e-9),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. powerconv_buck_boost_design
# ═══════════════════════════════════════════════════════════════════════════════

_BUCK_BOOST_SPEC = ToolSpec(
    name="powerconv_buck_boost_design",
    description=(
        "Steady-state CCM design for an inverting buck-boost converter.\n\n"
        "D = Vout_mag / (Vin + Vout_mag)  [output is −Vout_mag]\n"
        "L = Vin × D / (fsw × ΔIL)\n"
        "V_sw_stress = Vin + Vout_mag\n"
        "f_RHP = (1−D)² × Vout_mag / (2π × L × Iout)\n\n"
        "Warnings: polarity-inversion note, DCM-when-CCM-assumed, RHP-limited-bandwidth, "
        "efficiency-low.\n\n"
        "Input: { v_in, v_out_mag, i_out, fsw, ripple_frac?, c_out_f?, esr_ohm?, r_ds_on?, "
        "v_diode?, dcr_ohm?, t_rise_s?, t_fall_s? }\n"
        "Returns: { ok, duty, polarity_note, l_h, l_crit_h, ccm, f_rhp_hz, delta_il_a, "
        "i_l_peak_a, i_l_rms_a, i_sw_rms_a, i_diode_rms_a, v_sw_stress_v, "
        "v_diode_stress_v, c_out_min_f, delta_v_esr_v, delta_v_cap_v, delta_v_total_v, "
        "p_sw_cond_w, p_sw_switch_w, p_diode_w, p_dcr_w, p_total_loss_w, "
        "p_out_w, efficiency, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_in": {"type": "number", "description": "Input voltage [V]."},
            "v_out_mag": {"type": "number", "description": "Output voltage magnitude [V] (output is −v_out_mag)."},
            "i_out": {"type": "number", "description": "Output (load) current magnitude [A]."},
            "fsw": {"type": "number", "description": "Switching frequency [Hz]."},
            "ripple_frac": {"type": "number", "description": "Inductor current ripple fraction (default 0.30)."},
            "c_out_f": {"type": "number", "description": "Output capacitor [F] (default 100 µF)."},
            "esr_ohm": {"type": "number", "description": "Output cap ESR [Ω] (default 20 mΩ)."},
            "r_ds_on": {"type": "number", "description": "Switch Rds(on) [Ω] (default 50 mΩ)."},
            "v_diode": {"type": "number", "description": "Catch diode forward voltage [V] (default 0.5 V)."},
            "dcr_ohm": {"type": "number", "description": "Inductor DCR [Ω] (default 10 mΩ)."},
            "t_rise_s": {"type": "number", "description": "Switch current rise time [s] (default 20 ns)."},
            "t_fall_s": {"type": "number", "description": "Switch current fall time [s] (default 20 ns)."},
        },
        "required": ["v_in", "v_out_mag", "i_out", "fsw"],
    },
)


@register(_BUCK_BOOST_SPEC, write=False)
async def powerconv_buck_boost_design_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = buck_boost_design(
        v_in=a.get("v_in"),
        v_out_mag=a.get("v_out_mag"),
        i_out=a.get("i_out"),
        fsw=a.get("fsw"),
        ripple_frac=a.get("ripple_frac", 0.30),
        c_out_f=a.get("c_out_f", 100e-6),
        esr_ohm=a.get("esr_ohm", 0.020),
        r_ds_on=a.get("r_ds_on", 0.050),
        v_diode=a.get("v_diode", 0.5),
        dcr_ohm=a.get("dcr_ohm", 0.010),
        t_rise_s=a.get("t_rise_s", 20e-9),
        t_fall_s=a.get("t_fall_s", 20e-9),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. powerconv_flyback_design
# ═══════════════════════════════════════════════════════════════════════════════

_FLYBACK_SPEC = ToolSpec(
    name="powerconv_flyback_design",
    description=(
        "Isolated flyback converter steady-state CCM design.\n\n"
        "n = Np/Ns turns ratio = Vin × D / (Vout × (1−D))  [D ≈ 0.40 if n not given]\n"
        "Lp = Vin × D / (fsw × ΔIp)\n"
        "Ip_peak = n × Iout / (1−D) + ΔIp/2\n"
        "V_sw_stress = Vin + n × Vout  (no RCD clamp)\n\n"
        "Warnings: DCM-when-CCM-assumed, RCD-snubber-required (always), efficiency-low.\n\n"
        "Input: { v_in, v_out, i_out, fsw, n_turns_ratio?, ripple_frac?, c_out_f?, esr_ohm?, "
        "r_ds_on?, v_diode?, dcr_primary_ohm?, t_rise_s?, t_fall_s?, snubber_note? }\n"
        "Returns: { ok, duty, n_turns_ratio, l_primary_h, l_primary_crit_h, ccm, "
        "ip_peak_a, ip_rms_a, is_peak_a, v_sw_stress_v, v_sec_diode_stress_v, "
        "c_out_min_f, delta_v_esr_v, delta_v_cap_v, delta_v_total_v, "
        "p_sw_cond_w, p_sw_switch_w, p_diode_w, p_dcr_w, p_total_loss_w, "
        "p_out_w, efficiency, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_in": {"type": "number", "description": "Input voltage [V]."},
            "v_out": {"type": "number", "description": "Output voltage [V]."},
            "i_out": {"type": "number", "description": "Output (load) current [A]."},
            "fsw": {"type": "number", "description": "Switching frequency [Hz]."},
            "n_turns_ratio": {"type": "number", "description": "Primary-to-secondary turns ratio Np/Ns (optional; default: computed for D ≈ 0.40)."},
            "ripple_frac": {"type": "number", "description": "Primary current ripple fraction (default 0.40)."},
            "c_out_f": {"type": "number", "description": "Output capacitor [F] (default 100 µF)."},
            "esr_ohm": {"type": "number", "description": "Output cap ESR [Ω] (default 50 mΩ)."},
            "r_ds_on": {"type": "number", "description": "Primary switch Rds(on) [Ω] (default 200 mΩ)."},
            "v_diode": {"type": "number", "description": "Secondary diode Vf [V] (default 0.7 V)."},
            "dcr_primary_ohm": {"type": "number", "description": "Primary winding DCR [Ω] (default 100 mΩ)."},
            "t_rise_s": {"type": "number", "description": "Switch current rise time [s] (default 50 ns)."},
            "t_fall_s": {"type": "number", "description": "Switch current fall time [s] (default 50 ns)."},
            "snubber_note": {"type": "boolean", "description": "Include RCD snubber note in warnings (default true)."},
        },
        "required": ["v_in", "v_out", "i_out", "fsw"],
    },
)


@register(_FLYBACK_SPEC, write=False)
async def powerconv_flyback_design_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = flyback_design(
        v_in=a.get("v_in"),
        v_out=a.get("v_out"),
        i_out=a.get("i_out"),
        fsw=a.get("fsw"),
        n_turns_ratio=a.get("n_turns_ratio", None),
        ripple_frac=a.get("ripple_frac", 0.40),
        c_out_f=a.get("c_out_f", 100e-6),
        esr_ohm=a.get("esr_ohm", 0.050),
        r_ds_on=a.get("r_ds_on", 0.200),
        v_diode=a.get("v_diode", 0.7),
        dcr_primary_ohm=a.get("dcr_primary_ohm", 0.100),
        t_rise_s=a.get("t_rise_s", 50e-9),
        t_fall_s=a.get("t_fall_s", 50e-9),
        snubber_note=a.get("snubber_note", True),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. powerconv_sepic_design
# ═══════════════════════════════════════════════════════════════════════════════

_SEPIC_SPEC = ToolSpec(
    name="powerconv_sepic_design",
    description=(
        "Steady-state CCM design for a SEPIC converter (non-inverting, buck or boost).\n\n"
        "D = Vout / (Vin + Vout)\n"
        "L1 = L2 = Vin × D / (fsw × ΔIL1)\n"
        "I_sw_peak = IL1_peak + IL2_peak\n"
        "V_sw_stress = Vin + Vout\n"
        "V_C1 = Vin  [coupling cap steady-state]\n\n"
        "Warnings: DCM-when-CCM-assumed, coupling-cap ESR note, efficiency-low.\n\n"
        "Input: { v_in, v_out, i_out, fsw, ripple_frac?, c_out_f?, c_coupling_f?, "
        "esr_ohm?, r_ds_on?, v_diode?, dcr_ohm?, t_rise_s?, t_fall_s? }\n"
        "Returns: { ok, duty, l1_h, l2_h, l_crit_h, ccm, delta_il1_a, i_in_avg_a, "
        "i_sw_peak_a, i_sw_rms_a, i_diode_rms_a, i_l1_rms_a, i_l2_rms_a, "
        "v_c1_v, v_sw_stress_v, v_diode_stress_v, c_out_min_f, c_coupling_min_f, "
        "delta_v_esr_v, delta_v_cap_v, delta_v_total_v, "
        "p_sw_cond_w, p_sw_switch_w, p_diode_w, p_dcr_w, p_total_loss_w, "
        "p_out_w, efficiency, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_in": {"type": "number", "description": "Input voltage [V]."},
            "v_out": {"type": "number", "description": "Output voltage [V]."},
            "i_out": {"type": "number", "description": "Output (load) current [A]."},
            "fsw": {"type": "number", "description": "Switching frequency [Hz]."},
            "ripple_frac": {"type": "number", "description": "L1 current ripple fraction of Iin_avg (default 0.30)."},
            "c_out_f": {"type": "number", "description": "Output capacitor [F] (default 100 µF)."},
            "c_coupling_f": {"type": "number", "description": "Series coupling capacitor C1 [F] (default 10 µF)."},
            "esr_ohm": {"type": "number", "description": "Output cap ESR [Ω] (default 30 mΩ)."},
            "r_ds_on": {"type": "number", "description": "Switch Rds(on) [Ω] (default 100 mΩ)."},
            "v_diode": {"type": "number", "description": "Output diode Vf [V] (default 0.5 V)."},
            "dcr_ohm": {"type": "number", "description": "Inductor DCR per inductor [Ω] (default 20 mΩ)."},
            "t_rise_s": {"type": "number", "description": "Switch current rise time [s] (default 30 ns)."},
            "t_fall_s": {"type": "number", "description": "Switch current fall time [s] (default 30 ns)."},
        },
        "required": ["v_in", "v_out", "i_out", "fsw"],
    },
)


@register(_SEPIC_SPEC, write=False)
async def powerconv_sepic_design_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = sepic_design(
        v_in=a.get("v_in"),
        v_out=a.get("v_out"),
        i_out=a.get("i_out"),
        fsw=a.get("fsw"),
        ripple_frac=a.get("ripple_frac", 0.30),
        c_out_f=a.get("c_out_f", 100e-6),
        c_coupling_f=a.get("c_coupling_f", 10e-6),
        esr_ohm=a.get("esr_ohm", 0.030),
        r_ds_on=a.get("r_ds_on", 0.100),
        v_diode=a.get("v_diode", 0.5),
        dcr_ohm=a.get("dcr_ohm", 0.020),
        t_rise_s=a.get("t_rise_s", 30e-9),
        t_fall_s=a.get("t_fall_s", 30e-9),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. powerconv_thermal
# ═══════════════════════════════════════════════════════════════════════════════

_THERMAL_SPEC = ToolSpec(
    name="powerconv_thermal",
    description=(
        "Junction temperature estimate for a switching converter semiconductor.\n\n"
        "Single-package: Tj = T_ambient + P_loss × Rth_JA\n"
        "With heatsink: Tj = T_ambient + P_loss × (Rth_JC + Rth_CS + Rth_SA)\n\n"
        "A warning is issued when Tj > t_j_max_c (default 150 °C).\n\n"
        "Input: { p_loss_w, rth_ja, t_ambient_c?, t_j_max_c?, rth_jc?, rth_cs? }\n"
        "Returns: { ok, t_junction_c, delta_t_k, t_margin_k, over_temp, rth_total, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_loss_w": {"type": "number", "description": "Total semiconductor power dissipation [W]."},
            "rth_ja": {"type": "number", "description": "Junction-to-ambient thermal resistance [°C/W] (or Rth_SA when rth_jc+rth_cs provided)."},
            "t_ambient_c": {"type": "number", "description": "Ambient temperature [°C] (default 25 °C)."},
            "t_j_max_c": {"type": "number", "description": "Maximum junction temperature [°C] (default 150 °C)."},
            "rth_jc": {"type": "number", "description": "Junction-to-case thermal resistance [°C/W] (optional, for discrete with heatsink)."},
            "rth_cs": {"type": "number", "description": "Case-to-heatsink thermal resistance [°C/W] (optional)."},
        },
        "required": ["p_loss_w", "rth_ja"],
    },
)


@register(_THERMAL_SPEC, write=False)
async def powerconv_thermal_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = converter_thermal(
        p_loss_w=a.get("p_loss_w"),
        rth_ja=a.get("rth_ja"),
        t_ambient_c=a.get("t_ambient_c", 25.0),
        t_j_max_c=a.get("t_j_max_c", 150.0),
        rth_jc=a.get("rth_jc", None),
        rth_cs=a.get("rth_cs", None),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS export — consumed by plugin._register_tools
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    (_BUCK_SPEC.name,       _BUCK_SPEC,       powerconv_buck_design_tool),
    (_BOOST_SPEC.name,      _BOOST_SPEC,      powerconv_boost_design_tool),
    (_BUCK_BOOST_SPEC.name, _BUCK_BOOST_SPEC, powerconv_buck_boost_design_tool),
    (_FLYBACK_SPEC.name,    _FLYBACK_SPEC,    powerconv_flyback_design_tool),
    (_SEPIC_SPEC.name,      _SEPIC_SPEC,      powerconv_sepic_design_tool),
    (_THERMAL_SPEC.name,    _THERMAL_SPEC,    powerconv_thermal_tool),
]
