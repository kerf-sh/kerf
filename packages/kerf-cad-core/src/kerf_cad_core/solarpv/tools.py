"""
kerf_cad_core.solarpv.tools — LLM tool wrappers for photovoltaic system sizing.

Registers tools with the Kerf tool registry:

  pv_solar_position        — solar altitude/azimuth for lat/date/time
  pv_sunrise_sunset        — sunrise, sunset, and day length
  pv_poa_irradiance        — plane-of-array irradiance (isotropic sky model)
  pv_optimal_tilt          — rule-of-thumb optimal fixed tilt angle
  pv_array_size            — DC array size from daily load & PSH
  pv_module_string_sizing  — modules in series/parallel vs inverter limits
  pv_inverter_dc_ac_ratio  — check DC/AC clipping ratio
  pv_battery_bank          — off-grid battery bank sizing
  pv_cable_sizing          — DC cable cross-section for %voltage-drop
  pv_energy_yield          — annual/lifetime yield, specific yield, PR
  pv_row_spacing           — row pitch and GCR for no inter-row shading

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Duffie, J.A. & Beckman, W.A., "Solar Engineering of Thermal Processes", 4th ed.
Liu, B.Y.H. & Jordan, R.C. (1963) — isotropic sky transposition model.
IEC 60364-5-52 — cable current-carrying capacity.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.solarpv.sizing import (
    solar_position,
    sunrise_sunset,
    poa_irradiance,
    optimal_tilt,
    array_size,
    module_string_sizing,
    inverter_dc_ac_ratio,
    battery_bank,
    cable_sizing,
    energy_yield,
    row_spacing,
)


# ---------------------------------------------------------------------------
# Tool: pv_solar_position
# ---------------------------------------------------------------------------

_solar_position_spec = ToolSpec(
    name="pv_solar_position",
    description=(
        "Calculate solar altitude, azimuth, and zenith angle for a given "
        "site, day-of-year, and solar time.\n"
        "\n"
        "Uses spherical trigonometry (Duffie & Beckman §1.6) and the Spencer "
        "(1971) declination formula.\n"
        "\n"
        "Returns altitude_deg (above horizon), azimuth_deg (from south, + east), "
        "and zenith_deg.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "latitude_deg": {
                "type": "number",
                "description": "Site latitude (degrees, + north, − south). Range −90 to +90.",
            },
            "day_of_year": {
                "type": "integer",
                "description": "Julian day number (1 = 1 Jan, 365 = 31 Dec).",
            },
            "solar_time_h": {
                "type": "number",
                "description": "Solar (apparent) time in decimal hours (0–24). 12.0 = solar noon.",
            },
        },
        "required": ["latitude_deg", "day_of_year", "solar_time_h"],
    },
)


@register(_solar_position_spec, write=False)
async def run_pv_solar_position(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("latitude_deg", "day_of_year", "solar_time_h"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = solar_position(a["latitude_deg"], int(a["day_of_year"]), a["solar_time_h"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_sunrise_sunset
# ---------------------------------------------------------------------------

_sunrise_sunset_spec = ToolSpec(
    name="pv_sunrise_sunset",
    description=(
        "Return sunrise/sunset solar hour angles, solar times, and day length "
        "for a given latitude and day-of-year.\n"
        "\n"
        "Returns omega_sunrise_deg, omega_sunset_deg, sunrise_solar_h, "
        "sunset_solar_h, day_length_h.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "latitude_deg": {
                "type": "number",
                "description": "Site latitude (degrees, + north, − south).",
            },
            "day_of_year": {
                "type": "integer",
                "description": "Julian day number (1–365).",
            },
        },
        "required": ["latitude_deg", "day_of_year"],
    },
)


@register(_sunrise_sunset_spec, write=False)
async def run_pv_sunrise_sunset(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("latitude_deg", "day_of_year"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = sunrise_sunset(a["latitude_deg"], int(a["day_of_year"]))
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_poa_irradiance
# ---------------------------------------------------------------------------

_poa_irradiance_spec = ToolSpec(
    name="pv_poa_irradiance",
    description=(
        "Compute plane-of-array (POA) irradiance from horizontal irradiance "
        "components using the isotropic-sky (Liu & Jordan) transposition model.\n"
        "\n"
        "Decomposes into beam, isotropic sky diffuse, and ground-reflected "
        "components on a tilted surface.\n"
        "\n"
        "Returns beam_W_m2, diffuse_W_m2, reflected_W_m2, total_W_m2, R_b.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ghi": {
                "type": "number",
                "description": "Global horizontal irradiance (W/m²). Must be >= 0.",
            },
            "dni": {
                "type": "number",
                "description": "Direct normal irradiance (W/m²). Must be >= 0.",
            },
            "dhi": {
                "type": "number",
                "description": "Diffuse horizontal irradiance (W/m²). Must be >= 0.",
            },
            "tilt_deg": {
                "type": "number",
                "description": "Collector tilt from horizontal (degrees, 0=horiz, 90=vertical).",
            },
            "azimuth_deg": {
                "type": "number",
                "description": "Collector azimuth from south (degrees, + east, − west).",
            },
            "solar_altitude_deg": {
                "type": "number",
                "description": "Solar altitude above horizon (degrees).",
            },
            "solar_azimuth_deg": {
                "type": "number",
                "description": "Solar azimuth from south (degrees, + east, − west).",
            },
            "albedo": {
                "type": "number",
                "description": "Ground reflectance (default 0.2 = grass/soil).",
            },
        },
        "required": [
            "ghi", "dni", "dhi", "tilt_deg", "azimuth_deg",
            "solar_altitude_deg", "solar_azimuth_deg",
        ],
    },
)


@register(_poa_irradiance_spec, write=False)
async def run_pv_poa_irradiance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    required = ["ghi", "dni", "dhi", "tilt_deg", "azimuth_deg",
                "solar_altitude_deg", "solar_azimuth_deg"]
    for field in required:
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "albedo" in a:
        kwargs["albedo"] = a["albedo"]

    result = poa_irradiance(
        a["ghi"], a["dni"], a["dhi"],
        a["tilt_deg"], a["azimuth_deg"],
        a["solar_altitude_deg"], a["solar_azimuth_deg"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_optimal_tilt
# ---------------------------------------------------------------------------

_optimal_tilt_spec = ToolSpec(
    name="pv_optimal_tilt",
    description=(
        "Return the rule-of-thumb optimal fixed-tilt angle for maximum annual "
        "PV energy yield at a given latitude.\n"
        "\n"
        "Returns tilt_deg, faces ('south' or 'north'), and a confidence note.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "latitude_deg": {
                "type": "number",
                "description": "Site latitude (degrees, + north, − south).",
            },
        },
        "required": ["latitude_deg"],
    },
)


@register(_optimal_tilt_spec, write=False)
async def run_pv_optimal_tilt(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("latitude_deg") is None:
        return json.dumps({"ok": False, "reason": "latitude_deg is required"})

    result = optimal_tilt(a["latitude_deg"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_array_size
# ---------------------------------------------------------------------------

_array_size_spec = ToolSpec(
    name="pv_array_size",
    description=(
        "Calculate the required DC array peak power (kWp) from daily load, "
        "peak sun hours, and system performance ratio.\n"
        "\n"
        "Formula: P_kWp = (daily_load / PSH / PR) × safety_factor\n"
        "\n"
        "Returns array_kWp and input echoes.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "daily_load_kWh": {
                "type": "number",
                "description": "Daily energy consumption (kWh/day). Must be > 0.",
            },
            "peak_sun_hours": {
                "type": "number",
                "description": (
                    "Peak sun hours (h/day): daily in-plane irradiation in kWh/m². "
                    "Typical 3–6 h/day depending on location."
                ),
            },
            "derate_pr": {
                "type": "number",
                "description": (
                    "System performance ratio (0–1), accounting for all losses. "
                    "Typical 0.70–0.85."
                ),
            },
            "safety_factor": {
                "type": "number",
                "description": "Array oversize safety factor (default 1.25). Must be >= 1.",
            },
        },
        "required": ["daily_load_kWh", "peak_sun_hours", "derate_pr"],
    },
)


@register(_array_size_spec, write=False)
async def run_pv_array_size(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("daily_load_kWh", "peak_sun_hours", "derate_pr"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "safety_factor" in a:
        kwargs["safety_factor"] = a["safety_factor"]

    result = array_size(a["daily_load_kWh"], a["peak_sun_hours"], a["derate_pr"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_module_string_sizing
# ---------------------------------------------------------------------------

_module_string_spec = ToolSpec(
    name="pv_module_string_sizing",
    description=(
        "Size PV module strings (series/parallel) for a given inverter, "
        "accounting for Voc temperature rise at T_min and Vmp at T_max.\n"
        "\n"
        "Flags string overvoltage in warnings if cold-Voc exceeds inverter "
        "max DC input voltage.\n"
        "\n"
        "modules object: {voc_v, vmp_v, isc_a, imp_a, pmax_w, beta_voc, gamma_pmax}\n"
        "inverter object: {vdc_max_v, mppt_vmin_v, mppt_vmax_v, idc_max_a}\n"
        "\n"
        "Returns modules_per_string, strings_in_parallel, voltages, total kWp.\n"
        "\n"
        "Errors: {ok:false, reason} for missing/invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "modules": {
                "type": "object",
                "description": (
                    "Module electrical parameters at STC: "
                    "voc_v, vmp_v, isc_a, imp_a, pmax_w, "
                    "beta_voc (1/°C, e.g. −0.003), gamma_pmax (1/°C)."
                ),
                "properties": {
                    "voc_v":      {"type": "number"},
                    "vmp_v":      {"type": "number"},
                    "isc_a":      {"type": "number"},
                    "imp_a":      {"type": "number"},
                    "pmax_w":     {"type": "number"},
                    "beta_voc":   {"type": "number"},
                    "gamma_pmax": {"type": "number"},
                },
                "required": ["voc_v", "vmp_v", "isc_a", "imp_a", "pmax_w", "beta_voc"],
            },
            "inverter": {
                "type": "object",
                "description": (
                    "Inverter limits: vdc_max_v (abs max DC input V), "
                    "mppt_vmin_v, mppt_vmax_v (MPPT window), idc_max_a."
                ),
                "properties": {
                    "vdc_max_v":   {"type": "number"},
                    "mppt_vmin_v": {"type": "number"},
                    "mppt_vmax_v": {"type": "number"},
                    "idc_max_a":   {"type": "number"},
                },
                "required": ["vdc_max_v", "mppt_vmin_v", "mppt_vmax_v", "idc_max_a"],
            },
            "t_min_c": {
                "type": "number",
                "description": "Minimum expected ambient temperature (°C). Default −10°C.",
            },
            "t_max_c": {
                "type": "number",
                "description": "Maximum expected module temperature (°C). Default 70°C.",
            },
        },
        "required": ["modules", "inverter"],
    },
)


@register(_module_string_spec, write=False)
async def run_pv_module_string_sizing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("modules") is None:
        return json.dumps({"ok": False, "reason": "modules is required"})
    if a.get("inverter") is None:
        return json.dumps({"ok": False, "reason": "inverter is required"})

    kwargs: dict = {}
    if "t_min_c" in a:
        kwargs["t_min_c"] = a["t_min_c"]
    if "t_max_c" in a:
        kwargs["t_max_c"] = a["t_max_c"]

    try:
        result = module_string_sizing(a["modules"], a["inverter"], **kwargs)
    except (KeyError, TypeError) as exc:
        return json.dumps({"ok": False, "reason": f"invalid modules/inverter data: {exc}"})
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_inverter_dc_ac_ratio
# ---------------------------------------------------------------------------

_inverter_ratio_spec = ToolSpec(
    name="pv_inverter_dc_ac_ratio",
    description=(
        "Check the inverter DC/AC ratio (clipping ratio) for a PV array.\n"
        "\n"
        "Flags undersized (ratio < min) or oversized (ratio > max) in warnings.\n"
        "Typical acceptable range: 1.0–1.35.\n"
        "\n"
        "Returns dc_ac_ratio and status: 'ok', 'undersized', or 'oversized'.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "array_kWp": {
                "type": "number",
                "description": "DC peak power of the array (kWp).",
            },
            "inverter_kVAc": {
                "type": "number",
                "description": "Inverter nominal AC output power (kVAc).",
            },
            "min_ratio": {
                "type": "number",
                "description": "Minimum acceptable DC/AC ratio (default 1.0).",
            },
            "max_ratio": {
                "type": "number",
                "description": "Maximum acceptable DC/AC ratio (default 1.35).",
            },
        },
        "required": ["array_kWp", "inverter_kVAc"],
    },
)


@register(_inverter_ratio_spec, write=False)
async def run_pv_inverter_dc_ac_ratio(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("array_kWp", "inverter_kVAc"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "min_ratio" in a:
        kwargs["min_ratio"] = a["min_ratio"]
    if "max_ratio" in a:
        kwargs["max_ratio"] = a["max_ratio"]

    result = inverter_dc_ac_ratio(a["array_kWp"], a["inverter_kVAc"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_battery_bank
# ---------------------------------------------------------------------------

_battery_bank_spec = ToolSpec(
    name="pv_battery_bank",
    description=(
        "Size an off-grid battery bank for given autonomy days and maximum "
        "depth of discharge.\n"
        "\n"
        "Flags undersized bank (autonomy < 1 day) or dangerous DoD (> 0.8) "
        "in warnings.\n"
        "\n"
        "Returns gross kWh required, usable kWh, bank Ah, cells in series, "
        "parallel strings, and total cell count.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "daily_load_kWh": {
                "type": "number",
                "description": "Daily energy consumption (kWh/day). Must be > 0.",
            },
            "autonomy_days": {
                "type": "number",
                "description": "Days of autonomy without solar charging (typically 1–5).",
            },
            "dod_fraction": {
                "type": "number",
                "description": (
                    "Maximum depth of discharge (0–1). "
                    "Lead-acid 0.5, Li-ion 0.8."
                ),
            },
            "system_voltage_v": {
                "type": "number",
                "description": "Nominal DC system voltage (V). Typical: 12, 24, 48 V.",
            },
            "cell_ah": {
                "type": "number",
                "description": "Individual battery nominal capacity (Ah). Default 100 Ah.",
            },
            "efficiency": {
                "type": "number",
                "description": "Round-trip battery efficiency (default 0.85).",
            },
            "safety_factor": {
                "type": "number",
                "description": "Oversize factor (default 1.1).",
            },
        },
        "required": ["daily_load_kWh", "autonomy_days", "dod_fraction", "system_voltage_v"],
    },
)


@register(_battery_bank_spec, write=False)
async def run_pv_battery_bank(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("daily_load_kWh", "autonomy_days", "dod_fraction", "system_voltage_v"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("cell_ah", "efficiency", "safety_factor"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = battery_bank(
        a["daily_load_kWh"], a["autonomy_days"],
        a["dod_fraction"], a["system_voltage_v"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_cable_sizing
# ---------------------------------------------------------------------------

_cable_sizing_spec = ToolSpec(
    name="pv_cable_sizing",
    description=(
        "Calculate the minimum DC cable cross-section (mm²) for a given "
        "current, run length, system voltage, and maximum allowable voltage "
        "drop percentage.\n"
        "\n"
        "Returns the calculated minimum mm², next standard IEC size, and "
        "actual voltage drop % at that size.  Flags excess-drop in warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "current_a": {
                "type": "number",
                "description": "Design current (A). Must be > 0.",
            },
            "length_m": {
                "type": "number",
                "description": "One-way cable run length (m). Must be > 0.",
            },
            "voltage_v": {
                "type": "number",
                "description": "DC system voltage (V). Must be > 0.",
            },
            "max_drop_pct": {
                "type": "number",
                "description": (
                    "Maximum allowable voltage drop (%). "
                    "Typical 1–3% for PV strings."
                ),
            },
            "temperature_c": {
                "type": "number",
                "description": "Maximum conductor operating temperature (°C). Default 75°C.",
            },
        },
        "required": ["current_a", "length_m", "voltage_v", "max_drop_pct"],
    },
)


@register(_cable_sizing_spec, write=False)
async def run_pv_cable_sizing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("current_a", "length_m", "voltage_v", "max_drop_pct"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "temperature_c" in a:
        kwargs["temperature_c"] = a["temperature_c"]

    result = cable_sizing(
        a["current_a"], a["length_m"], a["voltage_v"], a["max_drop_pct"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_energy_yield
# ---------------------------------------------------------------------------

_energy_yield_spec = ToolSpec(
    name="pv_energy_yield",
    description=(
        "Calculate annual and lifetime PV system energy yield, specific yield, "
        "and performance ratio.\n"
        "\n"
        "Year-1: E = array_kWp × POA_annual × PR\n"
        "Subsequent years degraded at degradation_rate per year.\n"
        "\n"
        "Returns annual_yield_yr1_kWh, specific_yield_kWh_kWp, "
        "lifetime_yield_kWh, and performance_ratio.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "array_kWp": {
                "type": "number",
                "description": "DC peak power of the array (kWp).",
            },
            "poa_annual_kWh_m2": {
                "type": "number",
                "description": "Annual plane-of-array irradiation (kWh/m²/year).",
            },
            "pr": {
                "type": "number",
                "description": "System performance ratio (0–1).",
            },
            "degradation_rate": {
                "type": "number",
                "description": "Annual module degradation fraction (default 0.005 = 0.5%/yr).",
            },
            "years": {
                "type": "integer",
                "description": "System lifetime for lifetime yield calculation (default 25).",
            },
        },
        "required": ["array_kWp", "poa_annual_kWh_m2", "pr"],
    },
)


@register(_energy_yield_spec, write=False)
async def run_pv_energy_yield(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("array_kWp", "poa_annual_kWh_m2", "pr"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "degradation_rate" in a:
        kwargs["degradation_rate"] = a["degradation_rate"]
    if "years" in a:
        kwargs["years"] = int(a["years"])

    result = energy_yield(a["array_kWp"], a["poa_annual_kWh_m2"], a["pr"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pv_row_spacing
# ---------------------------------------------------------------------------

_row_spacing_spec = ToolSpec(
    name="pv_row_spacing",
    description=(
        "Calculate minimum PV row pitch and ground-cover ratio (GCR) to avoid "
        "inter-row shading at the worst-case winter solar elevation.\n"
        "\n"
        "Shadow analysis uses the winter solstice at solar noon ± "
        "winter_margin_h hours.  GCR is defined as module horizontal "
        "projection / row pitch.\n"
        "\n"
        "Returns row_pitch_m, gcr, module_horizontal_m, shadow_length_m, "
        "and min_solar_altitude_deg used.\n"
        "\n"
        "Errors: {ok:false, reason} for missing inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "module_length_m": {
                "type": "number",
                "description": "Module (or row) length in the tilt direction (m). Must be > 0.",
            },
            "tilt_deg": {
                "type": "number",
                "description": "Array tilt from horizontal (degrees).",
            },
            "latitude_deg": {
                "type": "number",
                "description": "Site latitude (degrees, + north, − south).",
            },
            "gcr": {
                "type": "number",
                "description": (
                    "If provided, derive row pitch from this GCR instead "
                    "of the no-shade constraint.  Must be in (0, 1)."
                ),
            },
            "winter_margin_h": {
                "type": "number",
                "description": (
                    "Hours from solar noon for worst-case shading check (default 3 h)."
                ),
            },
        },
        "required": ["module_length_m", "tilt_deg", "latitude_deg"],
    },
)


@register(_row_spacing_spec, write=False)
async def run_pv_row_spacing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("module_length_m", "tilt_deg", "latitude_deg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "gcr" in a:
        kwargs["gcr"] = a["gcr"]
    if "winter_margin_h" in a:
        kwargs["winter_margin_h"] = a["winter_margin_h"]

    result = row_spacing(
        a["module_length_m"], a["tilt_deg"], a["latitude_deg"], **kwargs
    )
    return ok_payload(result)
