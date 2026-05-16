"""
kerf_cad_core.buildingenergy.tools — LLM tool wrappers for building energy & daylighting.

Registers tools with the Kerf tool registry:

  be_uvalue_series              — U-value for series opaque assembly
  be_uvalue_parallel            — area-weighted parallel U-value
  be_uvalue_bridged             — U-value with thermal bridging
  be_whole_building_ua          — whole-building UA coefficient
  be_balance_point_temperature  — balance-point temperature
  be_degree_day_energy          — degree-day annual heating/cooling energy
  be_annual_fuel_cost           — annual fuel or electricity cost
  be_design_heating_load        — design heating load
  be_design_cooling_load        — design cooling load
  be_infiltration_ach_blower_door — infiltration ACH from blower-door
  be_infiltration_ach_aim2      — AIM-2/LBL infiltration ACH
  be_glaser_condensation        — interstitial condensation check (Glaser)
  be_solar_heat_gain            — instantaneous solar heat gain through glazing
  be_shading_projection_factor  — overhang shading fraction
  be_daylight_factor            — average daylight factor (BRE formula)
  be_window_to_floor_ratio      — window-to-floor ratio
  be_no_sky_line_depth          — no-sky-line depth from window
  be_overheating_hours          — overheating hours estimate
  be_eui                        — Energy Use Intensity
  be_ashrae901_envelope_compliance — ASHRAE 90.1-2022 envelope compliance

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
ASHRAE Handbook — Fundamentals (2021)
ASHRAE 90.1-2022 — Energy Standard for Buildings
ISO 6946:2017 — Thermal resistance and thermal transmittance
ISO 13788:2012 — Hygrothermal performance (Glaser method)
CIBSE Guide A (2015) — Environmental Design
BRE Digest 309 (1986) — Estimating daylight in buildings

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.buildingenergy.energy import (
    uvalue_series,
    uvalue_parallel,
    uvalue_bridged,
    whole_building_ua,
    balance_point_temperature,
    degree_day_energy,
    annual_fuel_cost,
    design_heating_load,
    design_cooling_load,
    infiltration_ach_blower_door,
    infiltration_ach_aim2,
    glaser_condensation,
    solar_heat_gain,
    shading_projection_factor,
    daylight_factor,
    window_to_floor_ratio,
    no_sky_line_depth,
    overheating_hours,
    eui,
    ashrae901_envelope_compliance,
)


# ---------------------------------------------------------------------------
# Tool: be_uvalue_series
# ---------------------------------------------------------------------------

_uvalue_series_spec = ToolSpec(
    name="be_uvalue_series",
    description=(
        "Compute the overall U-value and total R-value for an opaque building assembly "
        "with thermal layers in series.\n"
        "\n"
        "Each layer is specified as either:\n"
        "  {\"r\": R}         — layer R-value (m²·K/W)\n"
        "  {\"k\": k, \"d\": d} — conductivity (W/m·K) and thickness (m)\n"
        "\n"
        "Include air-film resistances (Rsi ≈ 0.13 m²K/W inner, Rse ≈ 0.04 outer) as layers.\n"
        "Returns U_W_m2K and R_total_m2KW.\n"
        "\n"
        "Reference: ISO 6946:2017.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "layers": {
                "type": "array",
                "description": (
                    "List of layer dicts. Each dict must have either:\n"
                    "  'r' (float): R-value in m²·K/W, OR\n"
                    "  'k' (float) AND 'd' (float): conductivity W/(m·K) and thickness m."
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["layers"],
    },
)


@register(_uvalue_series_spec, write=False)
async def run_uvalue_series(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    layers = a.get("layers")
    if layers is None:
        return json.dumps({"ok": False, "reason": "layers is required"})

    result = uvalue_series(layers)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_uvalue_parallel
# ---------------------------------------------------------------------------

_uvalue_parallel_spec = ToolSpec(
    name="be_uvalue_parallel",
    description=(
        "Compute the area-weighted parallel U-value for a building assembly with "
        "mixed heat-flow paths (e.g. insulated cavity vs. stud framing).\n"
        "\n"
        "fractions_and_uvalues is a list of [area_fraction, U] pairs.\n"
        "Area fractions should sum to 1.0.\n"
        "\n"
        "Reference: ISO 6946:2017 §6.9.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fractions_and_uvalues": {
                "type": "array",
                "description": (
                    "List of [area_fraction, U_W_m2K] pairs. "
                    "area_fraction values must sum to 1.0 (±0.01 tolerance)."
                ),
                "items": {"type": "array"},
            },
        },
        "required": ["fractions_and_uvalues"],
    },
)


@register(_uvalue_parallel_spec, write=False)
async def run_uvalue_parallel(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    fav = a.get("fractions_and_uvalues")
    if fav is None:
        return json.dumps({"ok": False, "reason": "fractions_and_uvalues is required"})

    result = uvalue_parallel(fav)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_uvalue_bridged
# ---------------------------------------------------------------------------

_uvalue_bridged_spec = ToolSpec(
    name="be_uvalue_bridged",
    description=(
        "Compute the combined U-value of an assembly that includes thermal bridges "
        "using the fractional-area (linear combination) method.\n"
        "\n"
        "  U_combined = (1 − bridge_fraction) × U_clear + bridge_fraction × U_bridge\n"
        "\n"
        "Reference: ASHRAE Fundamentals 2021 Ch. 27.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "U_clear": {
                "type": "number",
                "description": "U-value of clear-field (unbridged) area (W/(m²·K)). Must be >= 0.",
            },
            "U_bridge": {
                "type": "number",
                "description": "U-value through the thermal bridge (W/(m²·K)). Must be >= 0.",
            },
            "bridge_fraction": {
                "type": "number",
                "description": "Fraction of total area occupied by bridges [0–1].",
            },
        },
        "required": ["U_clear", "U_bridge", "bridge_fraction"],
    },
)


@register(_uvalue_bridged_spec, write=False)
async def run_uvalue_bridged(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("U_clear", "U_bridge", "bridge_fraction"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = uvalue_bridged(a["U_clear"], a["U_bridge"], a["bridge_fraction"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_whole_building_ua
# ---------------------------------------------------------------------------

_whole_building_ua_spec = ToolSpec(
    name="be_whole_building_ua",
    description=(
        "Compute the whole-building UA coefficient (W/K) from a list of envelope surfaces.\n"
        "\n"
        "Each surface: {\"area_m2\": A, \"U\": U}\n"
        "  UA = Σ (A_i × U_i)\n"
        "\n"
        "Returns UA_W_per_K, total area, and mean U-value.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "surfaces": {
                "type": "array",
                "description": (
                    "List of envelope surface dicts, each with:\n"
                    "  'area_m2' (float): surface area in m²\n"
                    "  'U' (float): U-value in W/(m²·K)"
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["surfaces"],
    },
)


@register(_whole_building_ua_spec, write=False)
async def run_whole_building_ua(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    surfaces = a.get("surfaces")
    if surfaces is None:
        return json.dumps({"ok": False, "reason": "surfaces is required"})

    result = whole_building_ua(surfaces)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_balance_point_temperature
# ---------------------------------------------------------------------------

_balance_point_spec = ToolSpec(
    name="be_balance_point_temperature",
    description=(
        "Compute the balance-point temperature (°C) — the outdoor temperature at which "
        "the building is in thermal equilibrium from internal gains alone.\n"
        "\n"
        "  T_balance = T_indoor − Q_internal / UA\n"
        "\n"
        "Heating is required when T_outdoor < T_balance.\n"
        "\n"
        "Reference: ASHRAE Fundamentals 2021 Ch. 18.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_indoor_C": {
                "type": "number",
                "description": "Indoor setpoint temperature (°C).",
            },
            "internal_gains_W": {
                "type": "number",
                "description": "Total steady-state internal heat gains (W). Must be >= 0.",
            },
            "ua_W_per_K": {
                "type": "number",
                "description": "Whole-building UA coefficient (W/K). Must be > 0.",
            },
        },
        "required": ["T_indoor_C", "internal_gains_W", "ua_W_per_K"],
    },
)


@register(_balance_point_spec, write=False)
async def run_balance_point_temperature(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_indoor_C", "internal_gains_W", "ua_W_per_K"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = balance_point_temperature(
        a["T_indoor_C"], a["internal_gains_W"], a["ua_W_per_K"]
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_degree_day_energy
# ---------------------------------------------------------------------------

_degree_day_energy_spec = ToolSpec(
    name="be_degree_day_energy",
    description=(
        "Estimate annual heating or cooling energy (kWh) from degree-days.\n"
        "\n"
        "  E = UA × DD × 24 / efficiency / 1000  [kWh]\n"
        "\n"
        "For heating: use HDD and AFUE (e.g. 0.9 for 90% furnace).\n"
        "For cooling: use CDD and COP (e.g. 3.5 for AC).\n"
        "\n"
        "Reference: ASHRAE Fundamentals 2021 Ch. 18 §18.3.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "HDD_or_CDD": {
                "type": "number",
                "description": "Heating degree-days (HDD) or cooling degree-days (CDD) in K·day.",
            },
            "UA_W_per_K": {
                "type": "number",
                "description": "Whole-building UA coefficient (W/K). Must be > 0.",
            },
            "mode": {
                "type": "string",
                "enum": ["heating", "cooling"],
                "description": "'heating' (default) or 'cooling'.",
            },
            "efficiency": {
                "type": "number",
                "description": (
                    "System efficiency: AFUE fraction for heating (e.g. 0.9), "
                    "COP for cooling (e.g. 3.5). Default 0.9."
                ),
            },
        },
        "required": ["HDD_or_CDD", "UA_W_per_K"],
    },
)


@register(_degree_day_energy_spec, write=False)
async def run_degree_day_energy(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("HDD_or_CDD", "UA_W_per_K"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "mode" in a:
        kwargs["mode"] = a["mode"]
    if "efficiency" in a:
        kwargs["efficiency"] = a["efficiency"]

    result = degree_day_energy(a["HDD_or_CDD"], a["UA_W_per_K"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_annual_fuel_cost
# ---------------------------------------------------------------------------

_annual_fuel_cost_spec = ToolSpec(
    name="be_annual_fuel_cost",
    description=(
        "Estimate annual fuel or electricity cost from building energy demand.\n"
        "\n"
        "Fuel HHV values: electricity 1 kWh/kWh, natural_gas 10.55 kWh/m³, "
        "propane 7.08 kWh/L, oil 10.35 kWh/L.\n"
        "\n"
        "Returns cost in the currency of price_per_unit, and fuel units required.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "energy_kWh": {
                "type": "number",
                "description": "Building energy demand (kWh). Must be >= 0.",
            },
            "fuel_type": {
                "type": "string",
                "enum": ["electricity", "natural_gas", "propane", "oil"],
                "description": "Fuel type.",
            },
            "price_per_unit": {
                "type": "number",
                "description": (
                    "Cost per fuel unit: electricity $/kWh, natural_gas $/m³, "
                    "propane $/litre, oil $/litre. Must be >= 0."
                ),
            },
        },
        "required": ["energy_kWh", "fuel_type", "price_per_unit"],
    },
)


@register(_annual_fuel_cost_spec, write=False)
async def run_annual_fuel_cost(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("energy_kWh", "fuel_type", "price_per_unit"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = annual_fuel_cost(a["energy_kWh"], a["fuel_type"], price_per_unit=a["price_per_unit"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_design_heating_load
# ---------------------------------------------------------------------------

_design_heating_load_spec = ToolSpec(
    name="be_design_heating_load",
    description=(
        "Compute design heating load (W) for an envelope + infiltration + ventilation system.\n"
        "\n"
        "  Q = (UA_env + UA_inf + UA_vent) × (T_in − T_out) − Q_internal\n"
        "\n"
        "surfaces: list of {\"area_m2\": A, \"U\": U} envelope assemblies.\n"
        "\n"
        "Reference: ASHRAE Fundamentals 2021 Ch. 18.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "surfaces": {
                "type": "array",
                "description": "List of {area_m2, U} envelope surfaces.",
                "items": {"type": "object"},
            },
            "T_indoor_C": {
                "type": "number",
                "description": "Indoor setpoint temperature (°C).",
            },
            "T_outdoor_C": {
                "type": "number",
                "description": "Design outdoor temperature (°C). Should be < T_indoor_C for heating.",
            },
            "infiltration_W_per_K": {
                "type": "number",
                "description": "Infiltration UA contribution (W/K). Default 0.",
            },
            "ventilation_W_per_K": {
                "type": "number",
                "description": "Mechanical ventilation UA contribution (W/K). Default 0.",
            },
            "internal_gains_W": {
                "type": "number",
                "description": "Total internal heat gains (W) — reduces heating load. Default 0.",
            },
        },
        "required": ["surfaces", "T_indoor_C", "T_outdoor_C"],
    },
)


@register(_design_heating_load_spec, write=False)
async def run_design_heating_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("surfaces", "T_indoor_C", "T_outdoor_C"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("infiltration_W_per_K", "ventilation_W_per_K", "internal_gains_W"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = design_heating_load(a["surfaces"], a["T_indoor_C"], a["T_outdoor_C"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_design_cooling_load
# ---------------------------------------------------------------------------

_design_cooling_load_spec = ToolSpec(
    name="be_design_cooling_load",
    description=(
        "Compute design cooling load (W) including envelope, infiltration, ventilation, "
        "internal gains, solar gain, and latent loads.\n"
        "\n"
        "  Q = (UA_env + UA_inf + UA_vent) × (T_out − T_in) + Q_int + Q_solar + Q_latent\n"
        "\n"
        "Reference: ASHRAE Fundamentals 2021 Ch. 18.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "surfaces": {
                "type": "array",
                "description": "List of {area_m2, U} envelope surfaces.",
                "items": {"type": "object"},
            },
            "T_indoor_C": {
                "type": "number",
                "description": "Indoor setpoint temperature (°C).",
            },
            "T_outdoor_C": {
                "type": "number",
                "description": "Design outdoor temperature (°C). Should be > T_indoor_C for cooling.",
            },
            "infiltration_W_per_K": {
                "type": "number",
                "description": "Infiltration UA contribution (W/K). Default 0.",
            },
            "ventilation_W_per_K": {
                "type": "number",
                "description": "Mechanical ventilation UA contribution (W/K). Default 0.",
            },
            "internal_gains_W": {
                "type": "number",
                "description": "Total sensible internal gains (W). Default 0.",
            },
            "solar_gain_W": {
                "type": "number",
                "description": "Total solar heat gain through glazing (W). Default 0.",
            },
            "latent_gain_W": {
                "type": "number",
                "description": "Latent (moisture) gains (W). Default 0.",
            },
        },
        "required": ["surfaces", "T_indoor_C", "T_outdoor_C"],
    },
)


@register(_design_cooling_load_spec, write=False)
async def run_design_cooling_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("surfaces", "T_indoor_C", "T_outdoor_C"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("infiltration_W_per_K", "ventilation_W_per_K", "internal_gains_W", "solar_gain_W", "latent_gain_W"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = design_cooling_load(a["surfaces"], a["T_indoor_C"], a["T_outdoor_C"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_infiltration_ach_blower_door
# ---------------------------------------------------------------------------

_infil_blower_door_spec = ToolSpec(
    name="be_infiltration_ach_blower_door",
    description=(
        "Estimate natural infiltration ACH from a blower-door test result at 50 Pa.\n"
        "\n"
        "  ACH_nat = ACH50 / n\n"
        "\n"
        "Typical n values: 20 (tight/low-rise), 17 (average), 10 (leaky/tall buildings).\n"
        "\n"
        "Reference: Sherman & Grimsrud (1980); ASHRAE 62.2-2022.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ACH50": {
                "type": "number",
                "description": "Measured air changes per hour at 50 Pa (h⁻¹). Must be >= 0.",
            },
            "n": {
                "type": "number",
                "description": "Divisor: 20 (default, tight), 17 (average), 10 (leaky).",
            },
        },
        "required": ["ACH50"],
    },
)


@register(_infil_blower_door_spec, write=False)
async def run_infiltration_ach_blower_door(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("ACH50") is None:
        return json.dumps({"ok": False, "reason": "ACH50 is required"})

    kwargs: dict = {}
    if "n" in a:
        kwargs["n"] = a["n"]

    result = infiltration_ach_blower_door(a["ACH50"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_infiltration_ach_aim2
# ---------------------------------------------------------------------------

_infil_aim2_spec = ToolSpec(
    name="be_infiltration_ach_aim2",
    description=(
        "Estimate infiltration ACH using the AIM-2/LBL model combining stack and wind effects.\n"
        "\n"
        "Stack: Q_stack = C_i × (ρ·g·H·ΔT/T_avg)^n\n"
        "Wind:  Q_wind  = C_i × (0.5·ρ·Cs·v²)^n\n"
        "Total: Q = sqrt(Q_stack² + Q_wind²)  →  ACH = Q/(floor_area × height)\n"
        "\n"
        "C_i is the envelope leakage coefficient from a blower-door test.\n"
        "\n"
        "Reference: Shaw & Tamura (1977); ASHRAE Fundamentals 2021 Ch. 16.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "floor_area_m2": {
                "type": "number",
                "description": "Conditioned floor area (m²). Must be > 0.",
            },
            "height_m": {
                "type": "number",
                "description": "Mean ceiling height for stack effect (m). Must be > 0.",
            },
            "C_i": {
                "type": "number",
                "description": "Envelope leakage coefficient (m³/s·Pa^n). Must be > 0.",
            },
            "n_exp": {
                "type": "number",
                "description": "Pressure exponent (typically 0.65). Range 0.4–1.0.",
            },
            "delta_T_C": {
                "type": "number",
                "description": "Indoor–outdoor temperature difference |ΔT| (K).",
            },
            "wind_speed_m_s": {
                "type": "number",
                "description": "Local wind speed at building height (m/s). Must be >= 0.",
            },
            "terrain_class": {
                "type": "string",
                "enum": ["urban", "suburban", "rural"],
                "description": "Wind terrain shielding: 'urban', 'suburban' (default), 'rural'.",
            },
        },
        "required": ["floor_area_m2", "height_m", "C_i", "n_exp", "delta_T_C", "wind_speed_m_s"],
    },
)


@register(_infil_aim2_spec, write=False)
async def run_infiltration_ach_aim2(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("floor_area_m2", "height_m", "C_i", "n_exp", "delta_T_C", "wind_speed_m_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "terrain_class" in a:
        kwargs["terrain_class"] = a["terrain_class"]

    result = infiltration_ach_aim2(
        a["floor_area_m2"], a["height_m"], a["C_i"],
        a["n_exp"], a["delta_T_C"], a["wind_speed_m_s"], **kwargs
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_glaser_condensation
# ---------------------------------------------------------------------------

_glaser_spec = ToolSpec(
    name="be_glaser_condensation",
    description=(
        "Glaser dew-point method: check for interstitial condensation risk in a wall/roof assembly.\n"
        "\n"
        "Each layer: {\"name\": str, \"d_m\": thickness (m), \"k_W_mK\": conductivity, \"mu\": vapour resistance factor}\n"
        "mu examples: mineral wool ≈ 1–2, EPS ≈ 50, XPS ≈ 100, PE vapour barrier ≈ 10000.\n"
        "\n"
        "Returns temperature and dew-point at each interface; flags condensation risk.\n"
        "\n"
        "Reference: ISO 13788:2012; Glaser (1958).\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "layers": {
                "type": "array",
                "description": (
                    "List of layer dicts: {name, d_m, k_W_mK, mu}. "
                    "mu = vapour diffusion resistance factor (dimensionless, ≥1)."
                ),
                "items": {"type": "object"},
            },
            "T_inside_C": {
                "type": "number",
                "description": "Indoor air temperature (°C).",
            },
            "T_outside_C": {
                "type": "number",
                "description": "Outdoor air temperature (°C).",
            },
            "RH_inside": {
                "type": "number",
                "description": "Indoor relative humidity (0–1, e.g. 0.5 = 50%).",
            },
            "RH_outside": {
                "type": "number",
                "description": "Outdoor relative humidity (0–1).",
            },
        },
        "required": ["layers", "T_inside_C", "T_outside_C", "RH_inside", "RH_outside"],
    },
)


@register(_glaser_spec, write=False)
async def run_glaser_condensation(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("layers", "T_inside_C", "T_outside_C", "RH_inside", "RH_outside"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = glaser_condensation(
        a["layers"], a["T_inside_C"], a["T_outside_C"],
        a["RH_inside"], a["RH_outside"]
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_solar_heat_gain
# ---------------------------------------------------------------------------

_solar_gain_spec = ToolSpec(
    name="be_solar_heat_gain",
    description=(
        "Compute instantaneous solar heat gain through glazing (W).\n"
        "\n"
        "  IAM = 1 − b₀ × (1/cosθ − 1)   [incidence angle modifier, b₀ = 0.1 default]\n"
        "  Q_solar = area × SHGC × IAM × irradiance × shading_factor\n"
        "\n"
        "Reference: ASHRAE Fundamentals 2021 Ch. 15.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "area_m2": {
                "type": "number",
                "description": "Glazing area (m²). Must be >= 0.",
            },
            "SHGC": {
                "type": "number",
                "description": "Solar heat gain coefficient at normal incidence [0–1].",
            },
            "irradiance_W_m2": {
                "type": "number",
                "description": "Total solar irradiance on glazing plane (W/m²). Must be >= 0.",
            },
            "incidence_angle_deg": {
                "type": "number",
                "description": "Angle of incidence from normal (degrees, 0–89.9). Default 0.",
            },
            "shading_factor": {
                "type": "number",
                "description": "External shading factor [0–1]; 1 = no shading. Default 1.",
            },
            "b0": {
                "type": "number",
                "description": "IAM coefficient b₀ (default 0.1 per ASHRAE).",
            },
        },
        "required": ["area_m2", "SHGC", "irradiance_W_m2"],
    },
)


@register(_solar_gain_spec, write=False)
async def run_solar_heat_gain(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("area_m2", "SHGC", "irradiance_W_m2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("incidence_angle_deg", "shading_factor", "b0"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = solar_heat_gain(a["area_m2"], a["SHGC"], a["irradiance_W_m2"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_shading_projection_factor
# ---------------------------------------------------------------------------

_shading_pf_spec = ToolSpec(
    name="be_shading_projection_factor",
    description=(
        "Compute the fraction of window area shaded by a horizontal overhang.\n"
        "\n"
        "shadow_depth = overhang_depth × tan(altitude) / cos(Δazimuth)\n"
        "shaded_fraction = min(shadow_depth / window_height, 1.0)\n"
        "\n"
        "Reference: CIBSE Guide A (2015) §5.5.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "overhang_depth_m": {
                "type": "number",
                "description": "Horizontal projection depth of overhang (m). Must be >= 0.",
            },
            "window_height_m": {
                "type": "number",
                "description": "Window height (m). Must be > 0.",
            },
            "solar_altitude_deg": {
                "type": "number",
                "description": "Solar altitude above horizon (degrees, 0–90).",
            },
            "solar_azimuth_deg": {
                "type": "number",
                "description": "Solar azimuth from north clockwise (degrees).",
            },
            "facade_azimuth_deg": {
                "type": "number",
                "description": "Facade normal azimuth from north clockwise (degrees).",
            },
        },
        "required": ["overhang_depth_m", "window_height_m", "solar_altitude_deg",
                     "solar_azimuth_deg", "facade_azimuth_deg"],
    },
)


@register(_shading_pf_spec, write=False)
async def run_shading_projection_factor(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("overhang_depth_m", "window_height_m", "solar_altitude_deg",
                  "solar_azimuth_deg", "facade_azimuth_deg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = shading_projection_factor(
        a["overhang_depth_m"], a["window_height_m"],
        a["solar_altitude_deg"], a["solar_azimuth_deg"], a["facade_azimuth_deg"]
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_daylight_factor
# ---------------------------------------------------------------------------

_daylight_factor_spec = ToolSpec(
    name="be_daylight_factor",
    description=(
        "Compute the average daylight factor (DF) using the BRE simplified formula.\n"
        "\n"
        "  DF = Tv × A_w × θ / (A_floor × (1 − R̄²))\n"
        "\n"
        "where θ = sky_component_fraction (fraction of sky visible from window).\n"
        "Typical DF targets: ≥ 2% residential living rooms, ≥ 5% studios.\n"
        "\n"
        "Reference: CIBSE LG10; BRE Digest 309.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "window_area_m2": {
                "type": "number",
                "description": "Total glazing area (m²). Must be >= 0.",
            },
            "floor_area_m2": {
                "type": "number",
                "description": "Room floor area (m²). Must be > 0.",
            },
            "Tv": {
                "type": "number",
                "description": "Visible light transmittance of glazing [0–1].",
            },
            "room_depth_m": {
                "type": "number",
                "description": "Room depth perpendicular to window (m). Default 5.",
            },
            "room_width_m": {
                "type": "number",
                "description": "Room width parallel to window (m). Default 5.",
            },
            "reflectance_avg": {
                "type": "number",
                "description": "Area-weighted average surface reflectance [0–1]. Default 0.5.",
            },
            "sky_component_fraction": {
                "type": "number",
                "description": "Fraction of unobstructed sky visible (0–1). Default 0.45 (urban).",
            },
        },
        "required": ["window_area_m2", "floor_area_m2", "Tv"],
    },
)


@register(_daylight_factor_spec, write=False)
async def run_daylight_factor(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("window_area_m2", "floor_area_m2", "Tv"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("room_depth_m", "room_width_m", "reflectance_avg", "sky_component_fraction"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = daylight_factor(a["window_area_m2"], a["floor_area_m2"], a["Tv"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_window_to_floor_ratio
# ---------------------------------------------------------------------------

_wfr_spec = ToolSpec(
    name="be_window_to_floor_ratio",
    description=(
        "Compute the window-to-floor ratio (WFR) for a room or zone.\n"
        "\n"
        "  WFR = window_area_m2 / floor_area_m2\n"
        "\n"
        "Typical targets: 0.10–0.20 residential, 0.15–0.25 office.\n"
        "Warnings issued for WFR < 0.10 (under-glazed) or > 0.40 (over-glazed).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "window_area_m2": {
                "type": "number",
                "description": "Total glazing area (m²). Must be >= 0.",
            },
            "floor_area_m2": {
                "type": "number",
                "description": "Room or zone floor area (m²). Must be > 0.",
            },
        },
        "required": ["window_area_m2", "floor_area_m2"],
    },
)


@register(_wfr_spec, write=False)
async def run_window_to_floor_ratio(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("window_area_m2", "floor_area_m2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = window_to_floor_ratio(a["window_area_m2"], a["floor_area_m2"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_no_sky_line_depth
# ---------------------------------------------------------------------------

_no_sky_line_spec = ToolSpec(
    name="be_no_sky_line_depth",
    description=(
        "Compute the no-sky-line depth — the distance from the window at which a "
        "working-plane point can just see the sky.\n"
        "\n"
        "  depth = multiplier × window_head_height_m   (default multiplier = 2.0)\n"
        "\n"
        "Points beyond this depth receive no direct sky light.\n"
        "\n"
        "Reference: BRE Digest 309 (1986); CIBSE LG10.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "window_head_height_m": {
                "type": "number",
                "description": "Height of window head above working plane (m). Must be > 0.",
            },
            "multiplier": {
                "type": "number",
                "description": "Depth multiplier (default 2.0 per BRE).",
            },
        },
        "required": ["window_head_height_m"],
    },
)


@register(_no_sky_line_spec, write=False)
async def run_no_sky_line_depth(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("window_head_height_m") is None:
        return json.dumps({"ok": False, "reason": "window_head_height_m is required"})

    kwargs: dict = {}
    if "multiplier" in a:
        kwargs["multiplier"] = a["multiplier"]

    result = no_sky_line_depth(a["window_head_height_m"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_overheating_hours
# ---------------------------------------------------------------------------

_overheating_hours_spec = ToolSpec(
    name="be_overheating_hours",
    description=(
        "Estimate overheating hours from hourly outdoor temperatures using a "
        "simplified free-floating steady-state model.\n"
        "\n"
        "  T_indoor_h = T_outdoor_h + (Q_internal + Q_solar) / UA\n"
        "\n"
        "Returns overheating_hours (count above T_comfort_max_C), total_hours, "
        "and overheating_fraction.\n"
        "\n"
        "Reference: CIBSE TM52:2013 (simplified).\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "internal_gains_W": {
                "type": "number",
                "description": "Total steady internal heat gains (W).",
            },
            "solar_gain_W": {
                "type": "number",
                "description": "Average solar heat gain (W).",
            },
            "UA_W_per_K": {
                "type": "number",
                "description": "Whole-building UA (W/K). Must be > 0.",
            },
            "T_outdoor_C_list": {
                "type": "array",
                "description": "List of hourly outdoor temperatures (°C). Typically 8760 values.",
                "items": {"type": "number"},
            },
            "T_comfort_max_C": {
                "type": "number",
                "description": "Upper comfort threshold (°C). Typical: 25–28 °C.",
            },
        },
        "required": ["internal_gains_W", "solar_gain_W", "UA_W_per_K",
                     "T_outdoor_C_list", "T_comfort_max_C"],
    },
)


@register(_overheating_hours_spec, write=False)
async def run_overheating_hours(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("internal_gains_W", "solar_gain_W", "UA_W_per_K",
                  "T_outdoor_C_list", "T_comfort_max_C"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = overheating_hours(
        a["internal_gains_W"], a["solar_gain_W"], a["UA_W_per_K"],
        a["T_outdoor_C_list"], a["T_comfort_max_C"]
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_eui
# ---------------------------------------------------------------------------

_eui_spec = ToolSpec(
    name="be_eui",
    description=(
        "Compute the Energy Use Intensity (EUI) in kWh/(m²·yr).\n"
        "\n"
        "  EUI = annual_energy_kWh / floor_area_m2\n"
        "\n"
        "Typical ranges: residential 50–150, office 100–250, hospital 300–700 kWh/(m²·yr).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "annual_energy_kWh": {
                "type": "number",
                "description": "Total annual building energy use (kWh). Must be >= 0.",
            },
            "floor_area_m2": {
                "type": "number",
                "description": "Gross conditioned floor area (m²). Must be > 0.",
            },
        },
        "required": ["annual_energy_kWh", "floor_area_m2"],
    },
)


@register(_eui_spec, write=False)
async def run_eui(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("annual_energy_kWh", "floor_area_m2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = eui(a["annual_energy_kWh"], a["floor_area_m2"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_ashrae901_envelope_compliance
# ---------------------------------------------------------------------------

_ashrae901_spec = ToolSpec(
    name="be_ashrae901_envelope_compliance",
    description=(
        "Check if a proposed building envelope assembly meets the ASHRAE 90.1-2022 "
        "prescriptive maximum U-value (or F-factor for slabs) for the given climate zone.\n"
        "\n"
        "assembly_type: 'roof' | 'wall_above_grade' | 'floor' | 'window_vertical' | "
        "'door_opaque' | 'slab_on_grade'\n"
        "climate_zone: integer 1–8 (use primary number; e.g. zone 4A → 4)\n"
        "\n"
        "For slab_on_grade: supply F_proposed (W/(m·K)) instead of U_proposed.\n"
        "\n"
        "Reference: ASHRAE 90.1-2022 Tables 5.5-1 through 5.5-8 (Non-Residential).\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "assembly_type": {
                "type": "string",
                "enum": ["roof", "wall_above_grade", "floor", "window_vertical",
                         "door_opaque", "slab_on_grade"],
                "description": "Assembly type to check.",
            },
            "U_proposed": {
                "type": "number",
                "description": "Proposed U-value (W/(m²·K)). Not required for slab_on_grade.",
            },
            "climate_zone": {
                "type": "integer",
                "description": "ASHRAE climate zone integer (1–8).",
            },
            "F_proposed": {
                "type": "number",
                "description": "For slab_on_grade only: proposed F-factor (W/(m·K)).",
            },
        },
        "required": ["assembly_type", "climate_zone"],
    },
)


@register(_ashrae901_spec, write=False)
async def run_ashrae901_envelope_compliance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("assembly_type", "climate_zone"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    U_proposed = a.get("U_proposed", 0.0)
    kwargs: dict = {}
    if "F_proposed" in a:
        kwargs["F_proposed"] = a["F_proposed"]

    result = ashrae901_envelope_compliance(
        a["assembly_type"], U_proposed, a["climate_zone"], **kwargs
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)
