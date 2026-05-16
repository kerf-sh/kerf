"""
kerf_cad_core.boiler.tools — LLM tool wrappers for steam & boiler plant engineering.

Registers tools with the Kerf tool registry:

  boiler_steam_properties       — saturated steam/water properties (P or T)
  boiler_superheat_enthalpy     — superheated steam enthalpy
  boiler_tsat_from_p            — saturation temperature from pressure
  boiler_psat_from_t            — saturation pressure from temperature
  boiler_heat_duty              — boiler heat duty from steam flow and enthalpies
  boiler_steam_output           — steam flow from fuel input and efficiency
  boiler_efficiency_io          — input-output thermal efficiency
  boiler_efficiency_heat_loss   — ASME PTC 4 abbreviated heat-loss method
  boiler_fuel_firing_rate       — fuel mass flow from duty and HHV
  boiler_combustion_air_flow    — combustion air from fuel and stoichiometry
  boiler_blowdown_rate          — continuous blowdown from TDS and CoC
  boiler_blowdown_heat_loss     — heat lost in blowdown discharge
  boiler_feedwater_energy_balance   — boiler mass/energy balance with blowdown
  boiler_deaerator_energy_balance   — direct-contact deaerator heat balance
  boiler_economizer_energy_balance  — economizer pre-heat duty
  boiler_equivalent_evaporation     — EE and factor of evaporation
  boiler_horsepower                 — boiler horsepower from steam flow
  boiler_pipe_velocity              — steam pipe mean velocity
  boiler_pipe_pressure_drop         — Darcy-Weisbach steam pipe ΔP
  boiler_flash_steam_fraction       — flash steam at lower pressure
  boiler_condensate_heat_recovery   — recoverable heat from condensate return
  boiler_steam_trap_capacity        — orifice-based trap discharge rate
  boiler_safety_valve_napier        — Napier formula safety valve relief

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
ASME PTC 4-2013 — Fired Steam Generators Performance Test Codes
IAPWS-IF97 (simplified fitted correlations; ±0.5% over 0.1–20 MPa)
Spirax Sarco Steam Engineering Tutorials
API 520 Part I — Sizing, Selection and Installation of Pressure-Relieving Devices

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.boiler.plant import (
    tsat_from_p,
    psat_from_t,
    steam_properties,
    superheat_h,
    boiler_heat_duty,
    boiler_steam_output,
    boiler_efficiency_io,
    boiler_efficiency_heat_loss,
    fuel_firing_rate,
    combustion_air_flow,
    blowdown_rate,
    blowdown_heat_loss,
    feedwater_energy_balance,
    deaerator_energy_balance,
    economizer_energy_balance,
    equivalent_evaporation,
    boiler_horsepower,
    steam_pipe_velocity,
    steam_pipe_pressure_drop,
    flash_steam_fraction,
    condensate_heat_recovery,
    steam_trap_capacity,
    safety_valve_napier,
)


# ---------------------------------------------------------------------------
# Tool: boiler_tsat_from_p
# ---------------------------------------------------------------------------

_tsat_from_p_spec = ToolSpec(
    name="boiler_tsat_from_p",
    description=(
        "Saturation temperature of steam/water from pressure.\n"
        "\n"
        "Uses IAPWS-IF97-style fitted Antoine correlation, valid 611 Pa – 22 MPa.\n"
        "\n"
        "Returns T_sat_K and T_sat_C.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P_Pa": {
                "type": "number",
                "description": "Saturation pressure (Pa). Valid 611 Pa – 22.06 MPa.",
            },
        },
        "required": ["P_Pa"],
    },
)


@register(_tsat_from_p_spec, write=False)
async def run_tsat_from_p(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("P_Pa") is None:
        return json.dumps({"ok": False, "reason": "P_Pa is required"})
    result = tsat_from_p(a["P_Pa"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_psat_from_t
# ---------------------------------------------------------------------------

_psat_from_t_spec = ToolSpec(
    name="boiler_psat_from_t",
    description=(
        "Saturation pressure of steam/water from temperature.\n"
        "\n"
        "Uses IAPWS-IF97-style fitted Antoine correlation, valid 0.01 – 374 °C.\n"
        "\n"
        "Returns P_sat_Pa, P_sat_kPa, P_sat_MPa.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_C": {
                "type": "number",
                "description": "Saturation temperature (°C). Valid 0.01 – 374 °C.",
            },
        },
        "required": ["T_C"],
    },
)


@register(_psat_from_t_spec, write=False)
async def run_psat_from_t(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("T_C") is None:
        return json.dumps({"ok": False, "reason": "T_C is required"})
    result = psat_from_t(a["T_C"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_steam_properties
# ---------------------------------------------------------------------------

_steam_properties_spec = ToolSpec(
    name="boiler_steam_properties",
    description=(
        "Saturated steam and water properties at given pressure or temperature.\n"
        "\n"
        "Uses fitted correlations against IAPWS-IF97 saturation tables.\n"
        "Accuracy: hf ±2 kJ/kg, hg ±1 kJ/kg, sg ±0.003 kJ/kg·K over 1 kPa–20 MPa.\n"
        "\n"
        "Provide either P_Pa (pressure) or T_sat_C (temperature), not both.\n"
        "\n"
        "Returns: T_sat_C, P_sat_Pa, P_sat_MPa, hf_kJkg, hg_kJkg, hfg_kJkg,\n"
        "         sf_kJkgK, sg_kJkgK, sfg_kJkgK, vf_m3kg, vg_m3kg.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P_Pa": {
                "type": "number",
                "description": "Saturation pressure (Pa). Provide P_Pa or T_sat_C.",
            },
            "T_sat_C": {
                "type": "number",
                "description": "Saturation temperature (°C). Provide P_Pa or T_sat_C.",
            },
        },
    },
)


@register(_steam_properties_spec, write=False)
async def run_steam_properties(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    P_Pa = a.get("P_Pa")
    T_sat_C = a.get("T_sat_C")
    if P_Pa is None and T_sat_C is None:
        return json.dumps({"ok": False, "reason": "Provide P_Pa or T_sat_C"})
    result = steam_properties(P_Pa=P_Pa, T_sat_C=T_sat_C)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_superheat_enthalpy
# ---------------------------------------------------------------------------

_superheat_h_spec = ToolSpec(
    name="boiler_superheat_enthalpy",
    description=(
        "Approximate enthalpy of superheated steam.\n"
        "\n"
        "h_sup ≈ hg(P) + cp_steam × (T_sup - T_sat)\n"
        "cp_steam ≈ 2.05 kJ/kg·K (mean value for moderate superheat).\n"
        "\n"
        "NOT a substitute for IAPWS-IF97 tables; suitable for preliminary design.\n"
        "\n"
        "Returns h_sup_kJkg, T_sat_C, superheat_K.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P_Pa": {
                "type": "number",
                "description": "Steam pressure (Pa).",
            },
            "T_sup_C": {
                "type": "number",
                "description": "Actual steam temperature (°C). Should be > T_sat(P).",
            },
        },
        "required": ["P_Pa", "T_sup_C"],
    },
)


@register(_superheat_h_spec, write=False)
async def run_superheat_h(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("P_Pa", "T_sup_C"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = superheat_h(a["P_Pa"], a["T_sup_C"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_heat_duty
# ---------------------------------------------------------------------------

_heat_duty_spec = ToolSpec(
    name="boiler_heat_duty",
    description=(
        "Boiler heat duty (absorbed heat rate) from steam flow and enthalpies.\n"
        "\n"
        "Q_boiler = m_steam × (h_steam - h_fw)  [kW]\n"
        "\n"
        "Returns Q_kW and specific duty Q_kJkg.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_steam_kgs": {
                "type": "number",
                "description": "Steam mass flow rate (kg/s). Must be >= 0.",
            },
            "h_steam_kJkg": {
                "type": "number",
                "description": "Enthalpy of steam leaving boiler (kJ/kg).",
            },
            "h_fw_kJkg": {
                "type": "number",
                "description": "Enthalpy of feedwater entering boiler (kJ/kg).",
            },
        },
        "required": ["m_steam_kgs", "h_steam_kJkg", "h_fw_kJkg"],
    },
)


@register(_heat_duty_spec, write=False)
async def run_boiler_heat_duty(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_steam_kgs", "h_steam_kJkg", "h_fw_kJkg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = boiler_heat_duty(a["m_steam_kgs"], a["h_steam_kJkg"], a["h_fw_kJkg"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_steam_output
# ---------------------------------------------------------------------------

_steam_output_spec = ToolSpec(
    name="boiler_steam_output",
    description=(
        "Steam output from fuel firing rate and boiler efficiency.\n"
        "\n"
        "m_steam = (Q_fuel × η) / (h_steam - h_fw)\n"
        "\n"
        "Returns m_steam_kgs and m_steam_th (tonne/hour).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q_fuel_kW": {
                "type": "number",
                "description": "Fuel heat input rate (kW) = m_fuel × HHV. Must be > 0.",
            },
            "efficiency": {
                "type": "number",
                "description": "Boiler thermal efficiency (0–1).",
            },
            "h_steam_kJkg": {
                "type": "number",
                "description": "Steam enthalpy at boiler outlet (kJ/kg).",
            },
            "h_fw_kJkg": {
                "type": "number",
                "description": "Feedwater enthalpy at boiler inlet (kJ/kg).",
            },
        },
        "required": ["Q_fuel_kW", "efficiency", "h_steam_kJkg", "h_fw_kJkg"],
    },
)


@register(_steam_output_spec, write=False)
async def run_boiler_steam_output(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Q_fuel_kW", "efficiency", "h_steam_kJkg", "h_fw_kJkg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = boiler_steam_output(
        a["Q_fuel_kW"], a["efficiency"], a["h_steam_kJkg"], a["h_fw_kJkg"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_efficiency_io
# ---------------------------------------------------------------------------

_efficiency_io_spec = ToolSpec(
    name="boiler_efficiency_io",
    description=(
        "Boiler thermal efficiency by input-output method.\n"
        "\n"
        "η = (m_steam × (h_steam - h_fw)) / Q_fuel\n"
        "\n"
        "Returns efficiency (0–1) and efficiency_pct.\n"
        "Flags efficiency < 60% or > 100%.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_steam_kgs": {
                "type": "number",
                "description": "Steam flow (kg/s).",
            },
            "h_steam_kJkg": {
                "type": "number",
                "description": "Steam enthalpy (kJ/kg).",
            },
            "h_fw_kJkg": {
                "type": "number",
                "description": "Feedwater enthalpy (kJ/kg).",
            },
            "Q_fuel_kW": {
                "type": "number",
                "description": "Fuel heat input (kW). Must be > 0.",
            },
        },
        "required": ["m_steam_kgs", "h_steam_kJkg", "h_fw_kJkg", "Q_fuel_kW"],
    },
)


@register(_efficiency_io_spec, write=False)
async def run_boiler_efficiency_io(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_steam_kgs", "h_steam_kJkg", "h_fw_kJkg", "Q_fuel_kW"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = boiler_efficiency_io(
        a["m_steam_kgs"], a["h_steam_kJkg"], a["h_fw_kJkg"], a["Q_fuel_kW"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_efficiency_heat_loss
# ---------------------------------------------------------------------------

_efficiency_hl_spec = ToolSpec(
    name="boiler_efficiency_heat_loss",
    description=(
        "Boiler thermal efficiency by ASME PTC 4 abbreviated heat-loss method.\n"
        "\n"
        "efficiency = 100% - (dry_flue_gas_loss + moisture_loss + radiation_loss + unburnt_loss)\n"
        "\n"
        "Dry flue-gas loss uses Siegert formula approximation.\n"
        "Flags stack temperature > 250°C, excess air > 40%, efficiency < 70%.\n"
        "\n"
        "Returns all loss components and efficiency.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "flue_gas_temp_C": {
                "type": "number",
                "description": "Stack / flue-gas exit temperature (°C). Must be > ambient.",
            },
            "ambient_temp_C": {
                "type": "number",
                "description": "Ambient reference temperature (°C, default 25).",
            },
            "excess_air_pct": {
                "type": "number",
                "description": "Excess air percentage (%, default 20).",
            },
            "moisture_fuel_pct": {
                "type": "number",
                "description": "Moisture in fuel (% by mass, default 5%).",
            },
            "radiation_loss_pct": {
                "type": "number",
                "description": "Radiation + convection loss (%, default 1.5%).",
            },
            "unburnt_loss_pct": {
                "type": "number",
                "description": "Unburnt fuel / carbon loss (%, default 0.5%).",
            },
        },
        "required": ["flue_gas_temp_C"],
    },
)


@register(_efficiency_hl_spec, write=False)
async def run_boiler_efficiency_heat_loss(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("flue_gas_temp_C") is None:
        return json.dumps({"ok": False, "reason": "flue_gas_temp_C is required"})
    kwargs: dict = {}
    for opt in ("ambient_temp_C", "excess_air_pct", "moisture_fuel_pct",
                "radiation_loss_pct", "unburnt_loss_pct"):
        if opt in a:
            kwargs[opt] = a[opt]
    result = boiler_efficiency_heat_loss(a["flue_gas_temp_C"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_fuel_firing_rate
# ---------------------------------------------------------------------------

_fuel_rate_spec = ToolSpec(
    name="boiler_fuel_firing_rate",
    description=(
        "Fuel mass flow rate from boiler duty, efficiency, and heating value.\n"
        "\n"
        "m_fuel = Q_boiler / (efficiency × HHV)\n"
        "\n"
        "Returns m_fuel_kgs, m_fuel_kgh, Q_input_kW.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q_boiler_kW": {
                "type": "number",
                "description": "Useful boiler heat duty (kW). Must be > 0.",
            },
            "efficiency": {
                "type": "number",
                "description": "Boiler thermal efficiency (0–1). Must be in (0, 1].",
            },
            "HHV_kJkg": {
                "type": "number",
                "description": "Higher heating value of fuel (kJ/kg). Must be > 0.",
            },
        },
        "required": ["Q_boiler_kW", "efficiency", "HHV_kJkg"],
    },
)


@register(_fuel_rate_spec, write=False)
async def run_fuel_firing_rate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Q_boiler_kW", "efficiency", "HHV_kJkg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = fuel_firing_rate(a["Q_boiler_kW"], a["efficiency"], a["HHV_kJkg"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_combustion_air_flow
# ---------------------------------------------------------------------------

_air_flow_spec = ToolSpec(
    name="boiler_combustion_air_flow",
    description=(
        "Combustion air flow from fuel flow rate and air-fuel stoichiometry.\n"
        "\n"
        "m_air = m_fuel × AFR_stoich × (1 + EA/100)\n"
        "\n"
        "Default AFR_stoich = 15.6 (natural gas). Flags excess air < 5% or > 50%.\n"
        "\n"
        "Returns m_air_stoich_kgs, m_air_actual_kgs, lambda (excess air ratio).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_fuel_kgs": {
                "type": "number",
                "description": "Fuel mass flow (kg/s). Must be >= 0.",
            },
            "stoich_air_fuel_ratio": {
                "type": "number",
                "description": "Stoichiometric AFR by mass (default 15.6 for natural gas).",
            },
            "excess_air_pct": {
                "type": "number",
                "description": "Excess air percentage (%, default 20%).",
            },
        },
        "required": ["m_fuel_kgs"],
    },
)


@register(_air_flow_spec, write=False)
async def run_combustion_air_flow(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("m_fuel_kgs") is None:
        return json.dumps({"ok": False, "reason": "m_fuel_kgs is required"})
    kwargs: dict = {}
    for opt in ("stoich_air_fuel_ratio", "excess_air_pct"):
        if opt in a:
            kwargs[opt] = a[opt]
    result = combustion_air_flow(a["m_fuel_kgs"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_blowdown_rate
# ---------------------------------------------------------------------------

_blowdown_rate_spec = ToolSpec(
    name="boiler_blowdown_rate",
    description=(
        "Continuous blowdown mass flow rate from TDS and cycles of concentration.\n"
        "\n"
        "CoC = blowdown_TDS_limit / feedwater_TDS\n"
        "BD_fraction = 1 / (CoC - 1)\n"
        "m_blowdown = m_steam × BD_fraction\n"
        "\n"
        "Flags blowdown fraction > 15% (poor feedwater quality).\n"
        "\n"
        "Returns CoC, blowdown_fraction, m_blowdown_kgs, m_blowdown_th.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_steam_kgs": {
                "type": "number",
                "description": "Steam generation rate (kg/s). Must be > 0.",
            },
            "feedwater_TDS_ppm": {
                "type": "number",
                "description": "Feedwater TDS (ppm). Must be > 0.",
            },
            "blowdown_TDS_limit_ppm": {
                "type": "number",
                "description": "Maximum allowable boiler water TDS (ppm). Must be > feedwater TDS.",
            },
            "cycles_of_concentration": {
                "type": "number",
                "description": "Optional; if provided, overrides TDS-derived CoC.",
            },
        },
        "required": ["m_steam_kgs", "feedwater_TDS_ppm", "blowdown_TDS_limit_ppm"],
    },
)


@register(_blowdown_rate_spec, write=False)
async def run_blowdown_rate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_steam_kgs", "feedwater_TDS_ppm", "blowdown_TDS_limit_ppm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "cycles_of_concentration" in a:
        kwargs["cycles_of_concentration"] = a["cycles_of_concentration"]
    result = blowdown_rate(
        a["m_steam_kgs"], a["feedwater_TDS_ppm"], a["blowdown_TDS_limit_ppm"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_blowdown_heat_loss
# ---------------------------------------------------------------------------

_blowdown_hl_spec = ToolSpec(
    name="boiler_blowdown_heat_loss",
    description=(
        "Heat lost in continuous blowdown discharge.\n"
        "\n"
        "Q_bd_loss = m_blowdown × (hf_boiler - hf_drain)\n"
        "\n"
        "Returns Q_loss_kW.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_blowdown_kgs": {
                "type": "number",
                "description": "Blowdown flow rate (kg/s). Must be >= 0.",
            },
            "P_boiler_Pa": {
                "type": "number",
                "description": "Boiler operating pressure (Pa).",
            },
            "T_drain_C": {
                "type": "number",
                "description": "Temperature at blowdown drain (°C, default 40).",
            },
        },
        "required": ["m_blowdown_kgs", "P_boiler_Pa"],
    },
)


@register(_blowdown_hl_spec, write=False)
async def run_blowdown_heat_loss(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_blowdown_kgs", "P_boiler_Pa"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "T_drain_C" in a:
        kwargs["T_drain_C"] = a["T_drain_C"]
    result = blowdown_heat_loss(a["m_blowdown_kgs"], a["P_boiler_Pa"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_feedwater_energy_balance
# ---------------------------------------------------------------------------

_fw_eb_spec = ToolSpec(
    name="boiler_feedwater_energy_balance",
    description=(
        "Overall boiler energy balance including blowdown.\n"
        "\n"
        "Q_absorbed = m_steam×h_steam + m_blowdown×h_bd - m_fw×h_fw\n"
        "where m_fw = m_steam + m_blowdown.\n"
        "\n"
        "Returns m_fw_kgs and Q_absorbed_kW.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_steam_kgs": {"type": "number", "description": "Steam flow (kg/s)."},
            "h_steam_kJkg": {"type": "number", "description": "Steam enthalpy at outlet (kJ/kg)."},
            "m_blowdown_kgs": {"type": "number", "description": "Blowdown flow (kg/s)."},
            "h_fw_kJkg": {"type": "number", "description": "Feedwater enthalpy at inlet (kJ/kg)."},
            "h_blowdown_kJkg": {"type": "number", "description": "Blowdown enthalpy at exit (kJ/kg)."},
        },
        "required": ["m_steam_kgs", "h_steam_kJkg", "m_blowdown_kgs", "h_fw_kJkg", "h_blowdown_kJkg"],
    },
)


@register(_fw_eb_spec, write=False)
async def run_feedwater_energy_balance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_steam_kgs", "h_steam_kJkg", "m_blowdown_kgs", "h_fw_kJkg", "h_blowdown_kJkg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = feedwater_energy_balance(
        a["m_steam_kgs"], a["h_steam_kJkg"],
        a["m_blowdown_kgs"], a["h_fw_kJkg"], a["h_blowdown_kJkg"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_deaerator_energy_balance
# ---------------------------------------------------------------------------

_da_eb_spec = ToolSpec(
    name="boiler_deaerator_energy_balance",
    description=(
        "Direct-contact deaerator (open feedwater heater) energy balance.\n"
        "\n"
        "m_out × h_fw_out = m_fw_cold × h_fw_cold + m_steam × h_steam_sparging\n"
        "\n"
        "Returns m_out_kgs and h_fw_out_kJkg.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_fw_cold_kgs": {"type": "number", "description": "Cold feedwater flow (kg/s)."},
            "h_fw_cold_kJkg": {"type": "number", "description": "Cold feedwater enthalpy (kJ/kg)."},
            "m_steam_sparging_kgs": {"type": "number", "description": "Sparging steam flow (kg/s)."},
            "h_steam_sparging_kJkg": {"type": "number", "description": "Sparging steam enthalpy (kJ/kg)."},
            "T_deaerator_C": {
                "type": "number",
                "description": "Deaerator operating temperature (°C, default 105).",
            },
        },
        "required": ["m_fw_cold_kgs", "h_fw_cold_kJkg", "m_steam_sparging_kgs", "h_steam_sparging_kJkg"],
    },
)


@register(_da_eb_spec, write=False)
async def run_deaerator_energy_balance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_fw_cold_kgs", "h_fw_cold_kJkg", "m_steam_sparging_kgs", "h_steam_sparging_kJkg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "T_deaerator_C" in a:
        kwargs["T_deaerator_C"] = a["T_deaerator_C"]
    result = deaerator_energy_balance(
        a["m_fw_cold_kgs"], a["h_fw_cold_kJkg"],
        a["m_steam_sparging_kgs"], a["h_steam_sparging_kJkg"],
        **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_economizer_energy_balance
# ---------------------------------------------------------------------------

_econ_eb_spec = ToolSpec(
    name="boiler_economizer_energy_balance",
    description=(
        "Economizer (feedwater pre-heater) duty and temperature rise.\n"
        "\n"
        "Q_econ = m_fw × cp × (T_out - T_in)\n"
        "\n"
        "Returns Q_econ_kW, delta_T_C, h_fw_out_kJkg.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_fw_kgs": {"type": "number", "description": "Feedwater mass flow (kg/s)."},
            "T_fw_in_C": {"type": "number", "description": "Feedwater inlet temperature (°C)."},
            "T_fw_out_C": {"type": "number", "description": "Feedwater outlet temperature (°C)."},
            "cp_fw_kJkgK": {
                "type": "number",
                "description": "Specific heat of feedwater (kJ/kg·K, default 4.1868).",
            },
        },
        "required": ["m_fw_kgs", "T_fw_in_C", "T_fw_out_C"],
    },
)


@register(_econ_eb_spec, write=False)
async def run_economizer_energy_balance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_fw_kgs", "T_fw_in_C", "T_fw_out_C"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "cp_fw_kJkgK" in a:
        kwargs["cp_fw_kJkgK"] = a["cp_fw_kJkgK"]
    result = economizer_energy_balance(a["m_fw_kgs"], a["T_fw_in_C"], a["T_fw_out_C"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_equivalent_evaporation
# ---------------------------------------------------------------------------

_ee_spec = ToolSpec(
    name="boiler_equivalent_evaporation",
    description=(
        "Equivalent evaporation (EE) and factor of evaporation.\n"
        "\n"
        "EE = m_steam × (h_steam - h_fw) / (m_fuel × 2256.9)\n"
        "where 2256.9 kJ/kg = hfg at 100°C / 1 atm ('from & at 100°C' basis).\n"
        "\n"
        "Returns EE_kg_per_kg_fuel and factor_of_evaporation.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_steam_kgs": {"type": "number", "description": "Actual steam generation (kg/s)."},
            "h_steam_kJkg": {"type": "number", "description": "Steam enthalpy (kJ/kg)."},
            "h_fw_kJkg": {"type": "number", "description": "Feedwater enthalpy (kJ/kg)."},
            "m_fuel_kgs": {"type": "number", "description": "Fuel mass flow (kg/s). Must be > 0."},
        },
        "required": ["m_steam_kgs", "h_steam_kJkg", "h_fw_kJkg", "m_fuel_kgs"],
    },
)


@register(_ee_spec, write=False)
async def run_equivalent_evaporation(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_steam_kgs", "h_steam_kJkg", "h_fw_kJkg", "m_fuel_kgs"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = equivalent_evaporation(
        a["m_steam_kgs"], a["h_steam_kJkg"], a["h_fw_kJkg"], a["m_fuel_kgs"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_horsepower
# ---------------------------------------------------------------------------

_bhp_spec = ToolSpec(
    name="boiler_horsepower",
    description=(
        "Boiler horsepower (BHP) from steam flow and enthalpies.\n"
        "\n"
        "1 BHP = 9.81 kW = evaporation of 15.65 kg/h from & at 212°F.\n"
        "BHP = m_steam × (h_steam - h_fw_at100C) / 9.81\n"
        "Default h_fw = 419.06 kJ/kg (sat. water at 100°C).\n"
        "\n"
        "Returns BHP and Q_kW.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_steam_kgs": {"type": "number", "description": "Steam flow (kg/s). Must be >= 0."},
            "h_steam_kJkg": {"type": "number", "description": "Steam enthalpy (kJ/kg)."},
            "h_fw_kJkg": {
                "type": "number",
                "description": "Feedwater enthalpy (kJ/kg, default 419.06 = sat. water at 100°C).",
            },
        },
        "required": ["m_steam_kgs", "h_steam_kJkg"],
    },
)


@register(_bhp_spec, write=False)
async def run_boiler_horsepower(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_steam_kgs", "h_steam_kJkg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "h_fw_kJkg" in a:
        kwargs["h_fw_kJkg"] = a["h_fw_kJkg"]
    result = boiler_horsepower(a["m_steam_kgs"], a["h_steam_kJkg"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_pipe_velocity
# ---------------------------------------------------------------------------

_pipe_vel_spec = ToolSpec(
    name="boiler_pipe_velocity",
    description=(
        "Mean velocity of steam in a circular pipe.\n"
        "\n"
        "v = m_steam × vg / (π × d² / 4)\n"
        "\n"
        "Recommended: saturated 20–35 m/s; superheated 30–50 m/s.\n"
        "Flags > 50 m/s (erosion) or < 15 m/s (oversized).\n"
        "\n"
        "Returns velocity_ms and pipe_area_m2.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_steam_kgs": {"type": "number", "description": "Steam mass flow (kg/s)."},
            "pipe_id_m": {"type": "number", "description": "Pipe internal diameter (m). Must be > 0."},
            "vg_m3kg": {"type": "number", "description": "Specific volume of steam (m³/kg). Must be > 0."},
        },
        "required": ["m_steam_kgs", "pipe_id_m", "vg_m3kg"],
    },
)


@register(_pipe_vel_spec, write=False)
async def run_steam_pipe_velocity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_steam_kgs", "pipe_id_m", "vg_m3kg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = steam_pipe_velocity(a["m_steam_kgs"], a["pipe_id_m"], a["vg_m3kg"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_pipe_pressure_drop
# ---------------------------------------------------------------------------

_pipe_dp_spec = ToolSpec(
    name="boiler_pipe_pressure_drop",
    description=(
        "Darcy-Weisbach pressure drop for steam in a straight circular pipe.\n"
        "\n"
        "ΔP = f × (L/D) × (ρ × v²/2)  where ρ = 1/vg.\n"
        "Friction factor from Colebrook-White equation.\n"
        "\n"
        "Flags ΔP > 10 kPa over pipe length (consider larger pipe).\n"
        "\n"
        "Returns dP_Pa, dP_kPa, Reynolds, f_darcy, velocity_ms.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_steam_kgs": {"type": "number", "description": "Steam mass flow (kg/s)."},
            "pipe_id_m": {"type": "number", "description": "Internal pipe diameter (m). Must be > 0."},
            "pipe_length_m": {"type": "number", "description": "Pipe length (m). Must be > 0."},
            "vg_m3kg": {"type": "number", "description": "Specific volume (m³/kg). Must be > 0."},
            "mu_Pa_s": {
                "type": "number",
                "description": "Dynamic viscosity of steam (Pa·s, default 1.5e-5).",
            },
            "roughness_m": {
                "type": "number",
                "description": "Pipe roughness (m, default 4.6e-5 for steel).",
            },
        },
        "required": ["m_steam_kgs", "pipe_id_m", "pipe_length_m", "vg_m3kg"],
    },
)


@register(_pipe_dp_spec, write=False)
async def run_steam_pipe_pressure_drop(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_steam_kgs", "pipe_id_m", "pipe_length_m", "vg_m3kg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    for opt in ("mu_Pa_s", "roughness_m"):
        if opt in a:
            kwargs[opt] = a[opt]
    result = steam_pipe_pressure_drop(
        a["m_steam_kgs"], a["pipe_id_m"], a["pipe_length_m"], a["vg_m3kg"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_flash_steam_fraction
# ---------------------------------------------------------------------------

_flash_spec = ToolSpec(
    name="boiler_flash_steam_fraction",
    description=(
        "Mass fraction of flash steam when condensate flashes to lower pressure.\n"
        "\n"
        "x_flash = (hf_high - hf_low) / hfg_low\n"
        "\n"
        "Returns flash_fraction, T_flash_C.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "h_condensate_kJkg": {
                "type": "number",
                "description": "Enthalpy of condensate before flashing (kJ/kg) = hf at high pressure.",
            },
            "P_flash_Pa": {
                "type": "number",
                "description": "Flash vessel pressure (Pa). Lower than original condensate pressure.",
            },
        },
        "required": ["h_condensate_kJkg", "P_flash_Pa"],
    },
)


@register(_flash_spec, write=False)
async def run_flash_steam_fraction(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("h_condensate_kJkg", "P_flash_Pa"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = flash_steam_fraction(a["h_condensate_kJkg"], a["P_flash_Pa"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_condensate_heat_recovery
# ---------------------------------------------------------------------------

_cond_hr_spec = ToolSpec(
    name="boiler_condensate_heat_recovery",
    description=(
        "Sensible heat recoverable from condensate return.\n"
        "\n"
        "Q_recovered = m_condensate × cp × (T_condensate - T_drain)\n"
        "\n"
        "Returns Q_recovered_kW.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "m_condensate_kgs": {"type": "number", "description": "Condensate return flow (kg/s)."},
            "T_condensate_C": {"type": "number", "description": "Condensate return temperature (°C)."},
            "T_drain_C": {
                "type": "number",
                "description": "Temperature after heat exchange (°C, default 30).",
            },
            "cp_kJkgK": {
                "type": "number",
                "description": "Specific heat of water (kJ/kg·K, default 4.1868).",
            },
        },
        "required": ["m_condensate_kgs", "T_condensate_C"],
    },
)


@register(_cond_hr_spec, write=False)
async def run_condensate_heat_recovery(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("m_condensate_kgs", "T_condensate_C"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    for opt in ("T_drain_C", "cp_kJkgK"):
        if opt in a:
            kwargs[opt] = a[opt]
    result = condensate_heat_recovery(a["m_condensate_kgs"], a["T_condensate_C"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_steam_trap_capacity
# ---------------------------------------------------------------------------

_trap_spec = ToolSpec(
    name="boiler_steam_trap_capacity",
    description=(
        "Steam trap condensate discharge capacity (orifice flow model).\n"
        "\n"
        "m_dot = Cd × A × sqrt(2 × rho × dP)\n"
        "\n"
        "Returns m_condensate_kgs and m_condensate_kgh.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dP_bar": {
                "type": "number",
                "description": "Differential pressure across trap (bar). Must be > 0.",
            },
            "orifice_dia_mm": {
                "type": "number",
                "description": "Orifice diameter (mm). Must be > 0.",
            },
            "Cd": {
                "type": "number",
                "description": "Discharge coefficient (default 0.6).",
            },
            "condensate_temp_C": {
                "type": "number",
                "description": "Condensate temperature (°C, default 100).",
            },
        },
        "required": ["dP_bar", "orifice_dia_mm"],
    },
)


@register(_trap_spec, write=False)
async def run_steam_trap_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("dP_bar", "orifice_dia_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    for opt in ("Cd", "condensate_temp_C"):
        if opt in a:
            kwargs[opt] = a[opt]
    result = steam_trap_capacity(a["dP_bar"], a["orifice_dia_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: boiler_safety_valve_napier
# ---------------------------------------------------------------------------

_sv_napier_spec = ToolSpec(
    name="boiler_safety_valve_napier",
    description=(
        "Safety valve relief capacity by Napier's formula for steam.\n"
        "\n"
        "W [kg/h] = K_Napier × P_abs [bar] × A [mm²] × Ksh\n"
        "P_abs includes standard 10% accumulation above set pressure.\n"
        "Ksh = 1/sqrt(1 + 0.00065 × superheat_C) for superheated steam.\n"
        "\n"
        "Returns W_kgh, W_kgs, P_abs_bar, Ksh.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "set_pressure_barg": {
                "type": "number",
                "description": "Safety valve set pressure (bar gauge). Must be >= 0.",
            },
            "orifice_area_mm2": {
                "type": "number",
                "description": "Orifice / curtain area (mm²). Must be > 0.",
            },
            "steam_type": {
                "type": "string",
                "enum": ["saturated", "superheated"],
                "description": "'saturated' (default) or 'superheated'.",
            },
            "superheat_C": {
                "type": "number",
                "description": "Degrees of superheat (°C) for superheated steam.",
            },
        },
        "required": ["set_pressure_barg", "orifice_area_mm2"],
    },
)


@register(_sv_napier_spec, write=False)
async def run_safety_valve_napier(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("set_pressure_barg", "orifice_area_mm2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    for opt in ("steam_type", "superheat_C"):
        if opt in a:
            kwargs[opt] = a[opt]
    result = safety_valve_napier(a["set_pressure_barg"], a["orifice_area_mm2"], **kwargs)
    return ok_payload(result)
