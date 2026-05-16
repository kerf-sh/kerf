"""
LED driver / lighting electronics design — LLM tools.

Exposes tools to the Kerf agent layer:

  led_string_layout        — series/parallel string configuration from supply V, target lm, Vf/If/lm spec
  led_series_resistor      — series-resistor sizing: R, power, efficiency
  led_driver_topology      — linear CC vs switching topology recommendation
  led_buck_cc_design       — buck converter CC driver: duty cycle, L, C, switch stress
  led_boost_cc_design      — boost converter CC driver: duty cycle, L, C, switch stress
  led_thermal_derating     — junction temperature, lumen/Vf derating from Rth + ambient
  led_pwm_dimming          — average current, brightness ratio, percent-flicker note

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

from kerf_electronics.leddriver.driver import (
    buck_cc_design,
    boost_cc_design,
    driver_topology_choice,
    led_string_layout,
    pwm_dimming,
    series_resistor,
    thermal_derating,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. led_string_layout
# ═══════════════════════════════════════════════════════════════════════════════

_STRING_LAYOUT_SPEC = ToolSpec(
    name="led_string_layout",
    description=(
        "Determine the series/parallel LED string configuration from supply voltage, "
        "target luminous flux, and per-LED electrical/optical parameters.\n\n"
        "Algorithm:\n"
        "  1. n_series = floor((V_supply − vf_headroom) / Vf)\n"
        "  2. lm per string derated by binning_headroom_frac\n"
        "  3. n_parallel = ceil(target_lumens / lm_per_string)\n\n"
        "Warnings are issued for string mismatch (parallel strings without per-string CC), "
        "low efficiency (V_string / V_supply < 60 %), and exceeding max_parallel_strings.\n\n"
        "Input: { supply_v, target_lumens, led_vf, led_if_a, led_lumens, "
        "vf_headroom_v?, binning_headroom_frac?, max_parallel_strings? }\n"
        "Returns: { ok, n_series, n_parallel, n_total, v_string_v, i_total_a, "
        "total_lumens_achievable, input_power_w, efficiency_lm_per_w, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "supply_v": {
                "type": "number",
                "description": "Supply voltage [V].",
            },
            "target_lumens": {
                "type": "number",
                "description": "Required total luminous flux [lm].",
            },
            "led_vf": {
                "type": "number",
                "description": "Typical LED forward voltage [V].",
            },
            "led_if_a": {
                "type": "number",
                "description": "Rated LED forward current [A].",
            },
            "led_lumens": {
                "type": "number",
                "description": "Luminous flux per LED at led_if_a [lm].",
            },
            "vf_headroom_v": {
                "type": "number",
                "description": "Minimum driver headroom above V_string [V] (default 1.5 V).",
            },
            "binning_headroom_frac": {
                "type": "number",
                "description": "Fractional lumen derating for Vf/If bin spread (default 0.05).",
            },
            "max_parallel_strings": {
                "type": "integer",
                "description": "Advisory maximum number of parallel strings (default 8).",
            },
        },
        "required": ["supply_v", "target_lumens", "led_vf", "led_if_a", "led_lumens"],
    },
)


@register(_STRING_LAYOUT_SPEC, write=False)
async def led_string_layout_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = led_string_layout(
        supply_v=a.get("supply_v"),
        target_lumens=a.get("target_lumens"),
        led_vf=a.get("led_vf"),
        led_if_a=a.get("led_if_a"),
        led_lumens=a.get("led_lumens"),
        vf_headroom_v=a.get("vf_headroom_v", 1.5),
        binning_headroom_frac=a.get("binning_headroom_frac", 0.05),
        max_parallel_strings=a.get("max_parallel_strings", 8),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. led_series_resistor
# ═══════════════════════════════════════════════════════════════════════════════

_SERIES_RES_SPEC = ToolSpec(
    name="led_series_resistor",
    description=(
        "Size a series resistor for an LED string and compute resistor power "
        "dissipation and overall efficiency.\n\n"
        "R = (V_supply − n_series × Vf) / If\n"
        "P_R = R × If²\n"
        "efficiency = n_series × Vf / V_supply\n\n"
        "A warning is issued when efficiency < 60 %.\n\n"
        "Input: { supply_v, led_vf, led_if_a, n_series? }\n"
        "Returns: { ok, r_series_ohm, p_resistor_w, p_led_w, efficiency, v_string_v, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "supply_v": {
                "type": "number",
                "description": "Supply voltage [V].",
            },
            "led_vf": {
                "type": "number",
                "description": "LED forward voltage [V].",
            },
            "led_if_a": {
                "type": "number",
                "description": "Target LED forward current [A].",
            },
            "n_series": {
                "type": "integer",
                "description": "Number of LEDs in series (default 1).",
            },
        },
        "required": ["supply_v", "led_vf", "led_if_a"],
    },
)


@register(_SERIES_RES_SPEC, write=False)
async def led_series_resistor_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = series_resistor(
        supply_v=a.get("supply_v"),
        led_vf=a.get("led_vf"),
        led_if_a=a.get("led_if_a"),
        n_series=a.get("n_series", 1),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. led_driver_topology
# ═══════════════════════════════════════════════════════════════════════════════

_TOPOLOGY_SPEC = ToolSpec(
    name="led_driver_topology",
    description=(
        "Recommend linear constant-current (LDO-type) or switching (buck/boost) "
        "driver topology based on supply/string voltage ratio and efficiency target.\n\n"
        "Decision rules:\n"
        "  V_string > V_supply → boost required\n"
        "  linear_eff ≥ efficiency_threshold → linear acceptable\n"
        "  otherwise → buck switching recommended\n\n"
        "Input: { supply_v, v_string_v, led_if_a, efficiency_threshold? }\n"
        "Returns: { ok, topology, linear_efficiency, p_linear_dissipation_w, "
        "v_drop_v, recommend_switching, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "supply_v": {
                "type": "number",
                "description": "Supply voltage [V].",
            },
            "v_string_v": {
                "type": "number",
                "description": "LED string voltage [V].",
            },
            "led_if_a": {
                "type": "number",
                "description": "LED forward current [A].",
            },
            "efficiency_threshold": {
                "type": "number",
                "description": "Minimum acceptable linear efficiency (default 0.80).",
            },
        },
        "required": ["supply_v", "v_string_v", "led_if_a"],
    },
)


@register(_TOPOLOGY_SPEC, write=False)
async def led_driver_topology_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = driver_topology_choice(
        supply_v=a.get("supply_v"),
        v_string_v=a.get("v_string_v"),
        led_if_a=a.get("led_if_a"),
        efficiency_threshold=a.get("efficiency_threshold", 0.80),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. led_buck_cc_design
# ═══════════════════════════════════════════════════════════════════════════════

_BUCK_CC_SPEC = ToolSpec(
    name="led_buck_cc_design",
    description=(
        "Design a buck converter constant-current LED driver.\n\n"
        "Computes duty cycle D = V_string / (V_in × η), inductor value from "
        "peak-to-peak ripple spec, output capacitor for voltage ripple budget, "
        "and switch peak voltage/current stress.\n\n"
        "Requires V_string < V_in (step-down).  Use led_boost_cc_design for step-up.\n\n"
        "Input: { v_in, v_string, i_led, fsw_hz, inductor_ripple_frac?, cap_ripple_v?, eta? }\n"
        "Returns: { ok, duty_cycle, l_inductor_h, c_out_f, i_l_peak_a, i_l_valley_a, "
        "delta_il_a, v_sw_max_v, i_sw_peak_a, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_in": {
                "type": "number",
                "description": "Input voltage [V].",
            },
            "v_string": {
                "type": "number",
                "description": "LED string voltage (converter output) [V].",
            },
            "i_led": {
                "type": "number",
                "description": "LED forward current (converter output current) [A].",
            },
            "fsw_hz": {
                "type": "number",
                "description": "Switching frequency [Hz].",
            },
            "inductor_ripple_frac": {
                "type": "number",
                "description": "Peak-to-peak inductor current ripple / I_led (default 0.20).",
            },
            "cap_ripple_v": {
                "type": "number",
                "description": "Maximum output voltage ripple [V] (default 0.05 V).",
            },
            "eta": {
                "type": "number",
                "description": "Estimated converter efficiency 0 < η ≤ 1 (default 0.90).",
            },
        },
        "required": ["v_in", "v_string", "i_led", "fsw_hz"],
    },
)


@register(_BUCK_CC_SPEC, write=False)
async def led_buck_cc_design_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = buck_cc_design(
        v_in=a.get("v_in"),
        v_string=a.get("v_string"),
        i_led=a.get("i_led"),
        fsw_hz=a.get("fsw_hz"),
        inductor_ripple_frac=a.get("inductor_ripple_frac", 0.20),
        cap_ripple_v=a.get("cap_ripple_v", 0.05),
        eta=a.get("eta", 0.90),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. led_boost_cc_design
# ═══════════════════════════════════════════════════════════════════════════════

_BOOST_CC_SPEC = ToolSpec(
    name="led_boost_cc_design",
    description=(
        "Design a boost converter constant-current LED driver.\n\n"
        "Computes duty cycle D = 1 − V_in × η / V_string, inductor from ripple spec, "
        "output capacitor, and switch stress.\n\n"
        "Requires V_string > V_in (step-up).  Use led_buck_cc_design for step-down.\n\n"
        "Input: { v_in, v_string, i_led, fsw_hz, inductor_ripple_frac?, cap_ripple_v?, eta? }\n"
        "Returns: { ok, duty_cycle, l_inductor_h, c_out_f, i_in_a, i_l_peak_a, "
        "delta_il_a, v_sw_max_v, i_sw_peak_a, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_in": {
                "type": "number",
                "description": "Input voltage [V].",
            },
            "v_string": {
                "type": "number",
                "description": "LED string voltage (converter output) [V].",
            },
            "i_led": {
                "type": "number",
                "description": "LED forward current [A].",
            },
            "fsw_hz": {
                "type": "number",
                "description": "Switching frequency [Hz].",
            },
            "inductor_ripple_frac": {
                "type": "number",
                "description": "Peak-to-peak inductor current ripple / I_in (default 0.20).",
            },
            "cap_ripple_v": {
                "type": "number",
                "description": "Maximum output voltage ripple [V] (default 0.10 V).",
            },
            "eta": {
                "type": "number",
                "description": "Estimated converter efficiency 0 < η ≤ 1 (default 0.88).",
            },
        },
        "required": ["v_in", "v_string", "i_led", "fsw_hz"],
    },
)


@register(_BOOST_CC_SPEC, write=False)
async def led_boost_cc_design_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = boost_cc_design(
        v_in=a.get("v_in"),
        v_string=a.get("v_string"),
        i_led=a.get("i_led"),
        fsw_hz=a.get("fsw_hz"),
        inductor_ripple_frac=a.get("inductor_ripple_frac", 0.20),
        cap_ripple_v=a.get("cap_ripple_v", 0.10),
        eta=a.get("eta", 0.88),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. led_thermal_derating
# ═══════════════════════════════════════════════════════════════════════════════

_THERMAL_SPEC = ToolSpec(
    name="led_thermal_derating",
    description=(
        "Compute LED junction temperature and apply lumen/Vf thermal derating.\n\n"
        "Thermal model: T_j = T_ambient + P × (Rth_jc + Rth_cs)\n"
        "Derating (linear from datasheet): ΔT = T_j − 25 °C\n"
        "  lm_derated = lm_rated × (1 − lm_derating_per_k × ΔT)\n"
        "  vf_derated = vf_rated × (1 − vf_derating_per_k × ΔT)\n\n"
        "Warnings issued for over-temperature (T_j > tj_max_c) and "
        "severe lumen derating (> 50 %).\n\n"
        "Input: { p_dissipated_w, rth_jc, rth_cs, t_ambient_c, lm_rated, vf_rated_v, "
        "lm_derating_per_k?, vf_derating_per_k?, tj_max_c? }\n"
        "Returns: { ok, t_junction_c, delta_t_k, lm_derated, vf_derated_v, "
        "lm_derating_frac, vf_derating_frac, over_temp, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "p_dissipated_w": {
                "type": "number",
                "description": "Total power dissipated in LED junction [W].",
            },
            "rth_jc": {
                "type": "number",
                "description": "Junction-to-case thermal resistance [°C/W].",
            },
            "rth_cs": {
                "type": "number",
                "description": "Case-to-sink (or board) thermal resistance [°C/W].",
            },
            "t_ambient_c": {
                "type": "number",
                "description": "Ambient (heatsink) temperature [°C].",
            },
            "lm_rated": {
                "type": "number",
                "description": "Rated luminous flux at 25 °C [lm].",
            },
            "vf_rated_v": {
                "type": "number",
                "description": "Rated forward voltage at 25 °C [V].",
            },
            "lm_derating_per_k": {
                "type": "number",
                "description": "Fractional lm decrease per °C above 25 °C (default 0.005 = 0.5 %/K).",
            },
            "vf_derating_per_k": {
                "type": "number",
                "description": "Fractional Vf decrease per °C above 25 °C (default 0.002 = 0.2 %/K).",
            },
            "tj_max_c": {
                "type": "number",
                "description": "Maximum rated junction temperature [°C] (default 125 °C).",
            },
        },
        "required": [
            "p_dissipated_w", "rth_jc", "rth_cs", "t_ambient_c",
            "lm_rated", "vf_rated_v",
        ],
    },
)


@register(_THERMAL_SPEC, write=False)
async def led_thermal_derating_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = thermal_derating(
        p_dissipated_w=a.get("p_dissipated_w"),
        rth_jc=a.get("rth_jc"),
        rth_cs=a.get("rth_cs"),
        t_ambient_c=a.get("t_ambient_c"),
        lm_rated=a.get("lm_rated"),
        vf_rated_v=a.get("vf_rated_v"),
        lm_derating_per_k=a.get("lm_derating_per_k", 0.005),
        vf_derating_per_k=a.get("vf_derating_per_k", 0.002),
        tj_max_c=a.get("tj_max_c", 125.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. led_pwm_dimming
# ═══════════════════════════════════════════════════════════════════════════════

_PWM_SPEC = ToolSpec(
    name="led_pwm_dimming",
    description=(
        "Compute average LED current, apparent brightness ratio, and percent-flicker "
        "for PWM LED dimming.\n\n"
        "I_avg = duty_cycle × I_peak\n"
        "brightness_ratio = duty_cycle  (approximately linear for LEDs)\n"
        "percent_flicker = 100 %  (worst-case ideal PWM: I_max=I_peak, I_min=0)\n\n"
        "ENERGY STAR flicker criterion: percent_flicker ≤ 30 % below 1 kHz.\n"
        "A 'visible_flicker' warning is issued when PWM frequency < 1 kHz.\n\n"
        "Input: { pwm_freq_hz, duty_cycle, i_peak_a }\n"
        "Returns: { ok, i_avg_a, brightness_ratio, percent_flicker, "
        "pwm_period_s, visible_flicker_risk, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pwm_freq_hz": {
                "type": "number",
                "description": "PWM switching frequency [Hz].",
            },
            "duty_cycle": {
                "type": "number",
                "description": "PWM duty cycle (0 < D ≤ 1).",
            },
            "i_peak_a": {
                "type": "number",
                "description": "Peak LED current during on-time [A].",
            },
        },
        "required": ["pwm_freq_hz", "duty_cycle", "i_peak_a"],
    },
)


@register(_PWM_SPEC, write=False)
async def led_pwm_dimming_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = pwm_dimming(
        pwm_freq_hz=a.get("pwm_freq_hz"),
        duty_cycle=a.get("duty_cycle"),
        i_peak_a=a.get("i_peak_a"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS export — consumed by plugin._register_tools
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    (_STRING_LAYOUT_SPEC.name,  _STRING_LAYOUT_SPEC,  led_string_layout_tool),
    (_SERIES_RES_SPEC.name,     _SERIES_RES_SPEC,     led_series_resistor_tool),
    (_TOPOLOGY_SPEC.name,       _TOPOLOGY_SPEC,       led_driver_topology_tool),
    (_BUCK_CC_SPEC.name,        _BUCK_CC_SPEC,        led_buck_cc_design_tool),
    (_BOOST_CC_SPEC.name,       _BOOST_CC_SPEC,       led_boost_cc_design_tool),
    (_THERMAL_SPEC.name,        _THERMAL_SPEC,        led_thermal_derating_tool),
    (_PWM_SPEC.name,            _PWM_SPEC,            led_pwm_dimming_tool),
]
