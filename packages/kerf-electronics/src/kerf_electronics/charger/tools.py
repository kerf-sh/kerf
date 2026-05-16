"""
Battery charger & BMS design LLM tools.

Exposes nine tools to the Kerf agent layer:

  charger_cc_cv_profile       — CC-CV charge profile & time per chemistry
  charger_power               — charger output/input power, efficiency & thermal
  charger_passive_balance     — passive bleed-resistor balance time & power
  charger_active_balance      — active charge-transfer balance time & energy loss
  charger_coulomb_soc         — coulomb-counting SOC with OCV-blend
  charger_state_of_health     — capacity fade & resistance growth (SoH)
  charger_protection          — protection threshold evaluation with hysteresis
  charger_cell_matching       — cell-matching tolerance impact on usable capacity
  charger_mppt_solar          — MPPT solar-charge operating point & daily energy

All handlers follow the kerf never-raise contract:
  - Success: {"ok": True, ...} via ok_payload
  - Failure: {"ok": False, "error": ..., "code": ...} via err_payload
  Never raise.

Author: imranparuk
"""
from __future__ import annotations

import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

from kerf_electronics.charger.bms import (
    active_balance,
    cc_cv_charge_profile,
    cell_matching_usable_capacity,
    charger_power,
    coulomb_soc,
    mppt_solar_charge,
    passive_balance,
    protection_thresholds,
    state_of_health,
)


def _opt_float(d: dict, key: str) -> float | None:
    v = d.get(key)
    if isinstance(v, (int, float)):
        return float(v)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. charger_cc_cv_profile
# ═══════════════════════════════════════════════════════════════════════════════

_CC_CV_SPEC = ToolSpec(
    name="charger_cc_cv_profile",
    description=(
        "Compute the CC-CV charge profile for a battery cell or pack.\n\n"
        "Supported chemistries: li-ion, lifepo4, nimh, lead-acid.\n"
        "CC phase: constant current at cc_fraction × capacity_ah until charge restored.\n"
        "CV phase: constant voltage, current decays to cv_cutoff_fraction × I_cc.\n"
        "Lead-acid: V_max adjusted by −4 mV/°C/cell (temperature compensation).\n"
        "Returns CC time, CV time, total charge time, I_cc, and V_max per cell and pack.\n"
        "Warns on over-temp-charge, under-temp-charge, and over-C-rate.\n\n"
        "Input: { capacity_ah, chemistry?, n_cells_series?, dod?, cc_fraction?, "
        "cv_cutoff_fraction?, v_max_override_v?, t_cell_c? }\n"
        "Returns: { ok, i_cc_a, t_cc_h, t_cv_h, total_time_h, total_time_min, "
        "v_max_pack_v, charge_accepted_ah, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "capacity_ah": {
                "type": "number",
                "description": "Cell (or single-cell-equivalent) rated capacity (Ah).",
            },
            "chemistry": {
                "type": "string",
                "enum": ["li-ion", "lifepo4", "nimh", "lead-acid"],
                "description": "Cell chemistry (default 'li-ion').",
            },
            "n_cells_series": {
                "type": "integer",
                "description": "Number of cells in series (default 1).",
            },
            "dod": {
                "type": "number",
                "description": "Depth of discharge at start of charging (0–1; default 0.8).",
            },
            "cc_fraction": {
                "type": "number",
                "description": "CC rate as C-fraction (A/Ah; overrides chemistry default).",
            },
            "cv_cutoff_fraction": {
                "type": "number",
                "description": "CV taper cutoff as fraction of I_cc (overrides chemistry default).",
            },
            "v_max_override_v": {
                "type": "number",
                "description": "Override per-cell maximum voltage (V).",
            },
            "t_cell_c": {
                "type": "number",
                "description": "Cell temperature (°C; default 25). Used for lead-acid compensation.",
            },
        },
        "required": ["capacity_ah"],
    },
)


@register(_CC_CV_SPEC, write=False)
async def charger_cc_cv_profile(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = cc_cv_charge_profile(
        capacity_ah=a.get("capacity_ah"),
        chemistry=a.get("chemistry", "li-ion"),
        n_cells_series=a.get("n_cells_series", 1),
        dod=a.get("dod", 0.8),
        cc_fraction=_opt_float(a, "cc_fraction"),
        cv_cutoff_fraction=_opt_float(a, "cv_cutoff_fraction"),
        v_max_override_v=_opt_float(a, "v_max_override_v"),
        t_cell_c=a.get("t_cell_c", 25.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. charger_power
# ═══════════════════════════════════════════════════════════════════════════════

_CHARGER_POWER_SPEC = ToolSpec(
    name="charger_power",
    description=(
        "Compute charger output power, input power, conversion losses, and "
        "junction temperature.\n\n"
        "P_out = V_bat × I_charge; P_in = P_out / efficiency; "
        "P_loss = P_in − P_out.\n"
        "Junction temperature: T_j = T_ambient + P_loss × Rth_c_a (when Rth given).\n"
        "Warns when T_j > 125°C.\n\n"
        "Input: { v_bat_v, i_charge_a, efficiency?, rth_c_a_k_per_w?, t_ambient_c? }\n"
        "Returns: { ok, p_out_w, p_in_w, p_loss_w, efficiency, t_junction_c?, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_bat_v": {
                "type": "number",
                "description": "Battery terminal voltage during charging (V).",
            },
            "i_charge_a": {
                "type": "number",
                "description": "Charge current (A).",
            },
            "efficiency": {
                "type": "number",
                "description": "Charger conversion efficiency (0–1; default 0.90).",
            },
            "rth_c_a_k_per_w": {
                "type": "number",
                "description": "Thermal resistance case-to-ambient (K/W). Optional.",
            },
            "t_ambient_c": {
                "type": "number",
                "description": "Ambient temperature (°C; default 25).",
            },
        },
        "required": ["v_bat_v", "i_charge_a"],
    },
)


@register(_CHARGER_POWER_SPEC, write=False)
async def charger_power_tool(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = charger_power(
        v_bat_v=a.get("v_bat_v"),
        i_charge_a=a.get("i_charge_a"),
        efficiency=a.get("efficiency", 0.90),
        rth_c_a_k_per_w=_opt_float(a, "rth_c_a_k_per_w"),
        t_ambient_c=a.get("t_ambient_c", 25.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. charger_passive_balance
# ═══════════════════════════════════════════════════════════════════════════════

_PASSIVE_BAL_SPEC = ToolSpec(
    name="charger_passive_balance",
    description=(
        "Compute passive cell balancing parameters: bleed current, power "
        "dissipation, and time to equalise two cells.\n\n"
        "Bleed current: I = V_high / R_bleed.\n"
        "Balance time estimated from charge mismatch dQ = dV × (Q / V_high).\n"
        "Warns when cell voltage spread > 100 mV (possible degradation).\n\n"
        "Input: { v_high_v, v_low_v, cell_capacity_ah, r_bleed_ohm }\n"
        "Returns: { ok, delta_v_v, i_bleed_a, p_bleed_w, balance_time_h, "
        "balance_time_min, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_high_v": {
                "type": "number",
                "description": "Voltage of the highest cell (V).",
            },
            "v_low_v": {
                "type": "number",
                "description": "Voltage of the lowest cell (V).",
            },
            "cell_capacity_ah": {
                "type": "number",
                "description": "Cell capacity (Ah).",
            },
            "r_bleed_ohm": {
                "type": "number",
                "description": "Bleed resistor value (Ω).",
            },
        },
        "required": ["v_high_v", "v_low_v", "cell_capacity_ah", "r_bleed_ohm"],
    },
)


@register(_PASSIVE_BAL_SPEC, write=False)
async def charger_passive_balance(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = passive_balance(
        v_high_v=a.get("v_high_v"),
        v_low_v=a.get("v_low_v"),
        cell_capacity_ah=a.get("cell_capacity_ah"),
        r_bleed_ohm=a.get("r_bleed_ohm"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. charger_active_balance
# ═══════════════════════════════════════════════════════════════════════════════

_ACTIVE_BAL_SPEC = ToolSpec(
    name="charger_active_balance",
    description=(
        "Compute active cell balancing transfer time and energy loss.\n\n"
        "Energy transferred from high cell to low cell via an active balancer "
        "(inductor, flying-cap, or transformer topology).\n"
        "dQ = dV × (Q / V_high); transfer time = dQ / I_transfer.\n"
        "Energy loss = V_high × dQ × (1 − efficiency).\n"
        "Warns when cell voltage spread > 100 mV.\n\n"
        "Input: { v_high_v, v_low_v, cell_capacity_ah, transfer_current_a, efficiency? }\n"
        "Returns: { ok, delta_v_v, dq_ah, transfer_time_h, transfer_time_min, "
        "energy_loss_wh, efficiency, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_high_v": {"type": "number", "description": "Voltage of highest cell (V)."},
            "v_low_v": {"type": "number", "description": "Voltage of lowest cell (V)."},
            "cell_capacity_ah": {"type": "number", "description": "Cell capacity (Ah)."},
            "transfer_current_a": {
                "type": "number",
                "description": "Active balancer transfer current (A).",
            },
            "efficiency": {
                "type": "number",
                "description": "Balancer efficiency (0–1; default 0.90).",
            },
        },
        "required": ["v_high_v", "v_low_v", "cell_capacity_ah", "transfer_current_a"],
    },
)


@register(_ACTIVE_BAL_SPEC, write=False)
async def charger_active_balance(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = active_balance(
        v_high_v=a.get("v_high_v"),
        v_low_v=a.get("v_low_v"),
        cell_capacity_ah=a.get("cell_capacity_ah"),
        transfer_current_a=a.get("transfer_current_a"),
        efficiency=a.get("efficiency", 0.90),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. charger_coulomb_soc
# ═══════════════════════════════════════════════════════════════════════════════

_COULOMB_SOC_SPEC = ToolSpec(
    name="charger_coulomb_soc",
    description=(
        "Estimate state-of-charge using coulomb counting with optional OCV-SOC blend.\n\n"
        "SOC_cc = SOC_init + charge_ah / capacity_ah (clamped 0–1).\n"
        "Drift budget = drift_fraction_per_hour × elapsed_h.\n"
        "Blend: SOC_final = (1 − alpha_ocv) × SOC_cc + alpha_ocv × ocv_soc.\n"
        "Warns when drift budget > 5% (suggests OCV recalibration needed).\n\n"
        "Input: { soc_init, charge_ah, capacity_ah, elapsed_h, "
        "drift_fraction_per_hour?, ocv_soc?, alpha_ocv? }\n"
        "Returns: { ok, soc_cc, drift_budget, soc_blend, soc_final, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "soc_init": {
                "type": "number",
                "description": "Initial SOC (0–1).",
            },
            "charge_ah": {
                "type": "number",
                "description": "Charge added (+) or removed (−) since last reset (Ah).",
            },
            "capacity_ah": {
                "type": "number",
                "description": "Rated capacity (Ah).",
            },
            "elapsed_h": {
                "type": "number",
                "description": "Elapsed time since last SOC reset (h).",
            },
            "drift_fraction_per_hour": {
                "type": "number",
                "description": "Coulomb-counting drift rate (fraction/h; default 0.001).",
            },
            "ocv_soc": {
                "type": "number",
                "description": "OCV-based SOC estimate (0–1). Optional.",
            },
            "alpha_ocv": {
                "type": "number",
                "description": "Blend weight for OCV estimate (0–1; default 0.1).",
            },
        },
        "required": ["soc_init", "charge_ah", "capacity_ah", "elapsed_h"],
    },
)


@register(_COULOMB_SOC_SPEC, write=False)
async def charger_coulomb_soc(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = coulomb_soc(
        soc_init=a.get("soc_init"),
        charge_ah=a.get("charge_ah"),
        capacity_ah=a.get("capacity_ah"),
        elapsed_h=a.get("elapsed_h"),
        drift_fraction_per_hour=a.get("drift_fraction_per_hour", 0.001),
        ocv_soc=_opt_float(a, "ocv_soc"),
        alpha_ocv=a.get("alpha_ocv", 0.1),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. charger_state_of_health
# ═══════════════════════════════════════════════════════════════════════════════

_SOH_SPEC = ToolSpec(
    name="charger_state_of_health",
    description=(
        "Estimate battery state-of-health from cycle count.\n\n"
        "Q_now = Q_new × (1 − capacity_fade_per_cycle × n_cycles).\n"
        "R_now = R_new × (1 + resistance_growth_per_cycle × n_cycles).\n"
        "SoH (%) = 100 × Q_now / Q_new.\n"
        "Returns cycles remaining to 80% EOL threshold.\n"
        "Warns when SoH < 80%.\n\n"
        "Input: { q_new_ah, r_new_ohm, n_cycles, capacity_fade_per_cycle?, "
        "resistance_growth_per_cycle? }\n"
        "Returns: { ok, q_now_ah, r_now_ohm, soh_pct, cycles_to_80pct, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "q_new_ah": {
                "type": "number",
                "description": "Fresh cell capacity (Ah).",
            },
            "r_new_ohm": {
                "type": "number",
                "description": "Fresh cell internal resistance (Ω).",
            },
            "n_cycles": {
                "type": "integer",
                "description": "Number of full charge/discharge cycles completed.",
            },
            "capacity_fade_per_cycle": {
                "type": "number",
                "description": (
                    "Fractional capacity loss per cycle (default 5e-5 → 80% at ~4000 cycles)."
                ),
            },
            "resistance_growth_per_cycle": {
                "type": "number",
                "description": (
                    "Fractional resistance increase per cycle (default 1e-4)."
                ),
            },
        },
        "required": ["q_new_ah", "r_new_ohm", "n_cycles"],
    },
)


@register(_SOH_SPEC, write=False)
async def charger_state_of_health(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    n_cycles = a.get("n_cycles")
    if isinstance(n_cycles, float) and n_cycles.is_integer():
        n_cycles = int(n_cycles)

    result = state_of_health(
        q_new_ah=a.get("q_new_ah"),
        r_new_ohm=a.get("r_new_ohm"),
        n_cycles=n_cycles,
        capacity_fade_per_cycle=a.get("capacity_fade_per_cycle", 0.00005),
        resistance_growth_per_cycle=a.get("resistance_growth_per_cycle", 0.0001),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. charger_protection
# ═══════════════════════════════════════════════════════════════════════════════

_PROT_SPEC = ToolSpec(
    name="charger_protection",
    description=(
        "Define BMS protection thresholds with hysteresis and optionally evaluate "
        "whether current cell conditions trigger any protection.\n\n"
        "OV/UV use voltage hysteresis; OT uses temperature hysteresis.\n"
        "Short-circuit threshold must be above OC threshold.\n"
        "Returns release voltages/temperatures as well as trip points.\n"
        "When v_cell_v / i_cell_a / t_cell_c are provided, evaluates flags.\n\n"
        "Input: { v_ov_trip_v, v_uv_trip_v, i_oc_trip_a, t_ot_trip_c, i_sc_trip_a, "
        "hysteresis_v?, hysteresis_t_c?, v_cell_v?, i_cell_a?, t_cell_c? }\n"
        "Returns: { ok, ov_trip_v, ov_release_v, uv_trip_v, uv_release_v, "
        "oc_trip_a, sc_trip_a, ot_trip_c, ot_release_c, flags?, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_ov_trip_v": {
                "type": "number",
                "description": "Over-voltage trip threshold (V/cell).",
            },
            "v_uv_trip_v": {
                "type": "number",
                "description": "Under-voltage trip threshold (V/cell).",
            },
            "i_oc_trip_a": {
                "type": "number",
                "description": "Over-current trip threshold (A).",
            },
            "t_ot_trip_c": {
                "type": "number",
                "description": "Over-temperature trip threshold (°C).",
            },
            "i_sc_trip_a": {
                "type": "number",
                "description": "Short-circuit trip threshold (A); must be > i_oc_trip_a.",
            },
            "hysteresis_v": {
                "type": "number",
                "description": "Voltage hysteresis (V; default 0.05).",
            },
            "hysteresis_t_c": {
                "type": "number",
                "description": "Temperature hysteresis (°C; default 5).",
            },
            "v_cell_v": {
                "type": "number",
                "description": "Present cell voltage (V). Optional; triggers flag evaluation.",
            },
            "i_cell_a": {
                "type": "number",
                "description": "Present cell current (A). Optional.",
            },
            "t_cell_c": {
                "type": "number",
                "description": "Present cell temperature (°C). Optional.",
            },
        },
        "required": [
            "v_ov_trip_v", "v_uv_trip_v", "i_oc_trip_a",
            "t_ot_trip_c", "i_sc_trip_a",
        ],
    },
)


@register(_PROT_SPEC, write=False)
async def charger_protection(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = protection_thresholds(
        v_ov_trip_v=a.get("v_ov_trip_v"),
        v_uv_trip_v=a.get("v_uv_trip_v"),
        i_oc_trip_a=a.get("i_oc_trip_a"),
        t_ot_trip_c=a.get("t_ot_trip_c"),
        i_sc_trip_a=a.get("i_sc_trip_a"),
        hysteresis_v=a.get("hysteresis_v", 0.05),
        hysteresis_t_c=a.get("hysteresis_t_c", 5.0),
        v_cell_v=_opt_float(a, "v_cell_v"),
        i_cell_a=_opt_float(a, "i_cell_a"),
        t_cell_c=_opt_float(a, "t_cell_c"),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. charger_cell_matching
# ═══════════════════════════════════════════════════════════════════════════════

_CELL_MATCH_SPEC = ToolSpec(
    name="charger_cell_matching",
    description=(
        "Estimate usable pack capacity accounting for cell-to-cell capacity spread.\n\n"
        "The weakest cell in a series string limits the string's usable capacity.\n"
        "Q_usable = Q_nominal × (1 − tolerance_fraction).\n"
        "Warns when tolerance > 5%.\n\n"
        "Input: { q_nominal_ah, tolerance_fraction, n_series?, n_parallel? }\n"
        "Returns: { ok, q_cell_usable_ah, q_pack_usable_ah, "
        "energy_loss_fraction, usable_fraction, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "q_nominal_ah": {
                "type": "number",
                "description": "Nominal cell capacity (Ah).",
            },
            "tolerance_fraction": {
                "type": "number",
                "description": "Cell capacity spread (±fraction; e.g. 0.02 = ±2%).",
            },
            "n_series": {
                "type": "integer",
                "description": "Number of cells in series (default 1).",
            },
            "n_parallel": {
                "type": "integer",
                "description": "Number of parallel branches (default 1).",
            },
        },
        "required": ["q_nominal_ah", "tolerance_fraction"],
    },
)


@register(_CELL_MATCH_SPEC, write=False)
async def charger_cell_matching(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    n_series = a.get("n_series", 1)
    n_parallel = a.get("n_parallel", 1)
    if isinstance(n_series, float) and n_series.is_integer():
        n_series = int(n_series)
    if isinstance(n_parallel, float) and n_parallel.is_integer():
        n_parallel = int(n_parallel)

    result = cell_matching_usable_capacity(
        q_nominal_ah=a.get("q_nominal_ah"),
        tolerance_fraction=a.get("tolerance_fraction"),
        n_series=n_series,
        n_parallel=n_parallel,
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. charger_mppt_solar
# ═══════════════════════════════════════════════════════════════════════════════

_MPPT_SPEC = ToolSpec(
    name="charger_mppt_solar",
    description=(
        "Estimate MPPT solar-charge operating point and daily energy delivered.\n\n"
        "MPP current is derated for panel temperature: "
        "I_derated = I_mpp × (1 + isc_temp_coeff × (T − 25)).\n"
        "P_to_bat = V_mpp × I_derated × mppt_efficiency.\n"
        "E_day = P_to_bat × peak_sun_hours  (Wh/day).\n"
        "ΔSOC = E_day / (V_bat × capacity_ah).\n"
        "Warns when output < 1W or panel temperature > 70°C.\n\n"
        "Input: { v_mpp_v, i_mpp_a, peak_sun_hours, v_bat_v, capacity_ah, "
        "soc_init?, t_panel_c?, isc_temp_coeff_per_c?, mppt_efficiency? }\n"
        "Returns: { ok, p_mppt_w, p_mppt_to_bat_w, e_day_wh, delta_soc, "
        "soc_end, i_mpp_derated_a, warnings }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "v_mpp_v": {
                "type": "number",
                "description": "Panel MPP voltage at STC (V).",
            },
            "i_mpp_a": {
                "type": "number",
                "description": "Panel MPP current at STC (A).",
            },
            "peak_sun_hours": {
                "type": "number",
                "description": "Daily peak sun hours (h/day).",
            },
            "v_bat_v": {
                "type": "number",
                "description": "Battery terminal voltage during charging (V).",
            },
            "capacity_ah": {
                "type": "number",
                "description": "Battery capacity (Ah).",
            },
            "soc_init": {
                "type": "number",
                "description": "SOC at start of day (0–1; default 0.5).",
            },
            "t_panel_c": {
                "type": "number",
                "description": "Panel operating temperature (°C; default 25 = STC).",
            },
            "isc_temp_coeff_per_c": {
                "type": "number",
                "description": "I_sc temperature coefficient (fraction/°C; default 0.0004).",
            },
            "mppt_efficiency": {
                "type": "number",
                "description": "MPPT converter efficiency (0–1; default 0.95).",
            },
        },
        "required": ["v_mpp_v", "i_mpp_a", "peak_sun_hours", "v_bat_v", "capacity_ah"],
    },
)


@register(_MPPT_SPEC, write=False)
async def charger_mppt_solar(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    result = mppt_solar_charge(
        v_mpp_v=a.get("v_mpp_v"),
        i_mpp_a=a.get("i_mpp_a"),
        peak_sun_hours=a.get("peak_sun_hours"),
        v_bat_v=a.get("v_bat_v"),
        capacity_ah=a.get("capacity_ah"),
        soc_init=a.get("soc_init", 0.5),
        t_panel_c=a.get("t_panel_c", 25.0),
        isc_temp_coeff_per_c=a.get("isc_temp_coeff_per_c", 0.0004),
        mppt_efficiency=a.get("mppt_efficiency", 0.95),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown error"), "BAD_ARGS")
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS export — consumed by plugin._register_tools
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    (_CC_CV_SPEC.name,        _CC_CV_SPEC,        charger_cc_cv_profile),
    (_CHARGER_POWER_SPEC.name, _CHARGER_POWER_SPEC, charger_power_tool),
    (_PASSIVE_BAL_SPEC.name,  _PASSIVE_BAL_SPEC,  charger_passive_balance),
    (_ACTIVE_BAL_SPEC.name,   _ACTIVE_BAL_SPEC,   charger_active_balance),
    (_COULOMB_SOC_SPEC.name,  _COULOMB_SOC_SPEC,  charger_coulomb_soc),
    (_SOH_SPEC.name,          _SOH_SPEC,          charger_state_of_health),
    (_PROT_SPEC.name,         _PROT_SPEC,         charger_protection),
    (_CELL_MATCH_SPEC.name,   _CELL_MATCH_SPEC,   charger_cell_matching),
    (_MPPT_SPEC.name,         _MPPT_SPEC,         charger_mppt_solar),
]
