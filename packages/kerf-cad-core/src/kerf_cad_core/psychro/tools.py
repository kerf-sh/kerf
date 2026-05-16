"""
kerf_cad_core.psychro.tools — LLM tool wrappers for psychrometrics & HVAC loads.

Registers tools with the Kerf tool registry:

  psychro_state_point          — solve complete moist-air state from any two properties
  psychro_sat_pressure         — saturation pressure (Hyland-Wexler)
  psychro_dew_point            — dew-point temperature
  psychro_wet_bulb             — wet-bulb temperature (iterative)
  psychro_enthalpy             — moist-air specific enthalpy (SI)
  psychro_enthalpy_ip          — moist-air specific enthalpy (IP)
  psychro_specific_volume      — specific volume and density
  psychro_mix_streams          — mixing of two air streams
  psychro_sensible_load        — sensible load: 1.08·CFM·ΔT [BTU/h]
  psychro_latent_load          — latent load: 0.68·CFM·ΔW_gr or 4840·CFM·ΔW [BTU/h]
  psychro_total_load           — total load: 4.5·CFM·Δh [BTU/h]
  psychro_coil_adp             — cooling-coil ADP, bypass factor, SHR
  psychro_coil_leaving         — coil leaving conditions from loads
  psychro_evaporative_cooling  — direct evaporative cooling effectiveness
  psychro_altitude_pressure    — barometric pressure at altitude

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
ASHRAE Handbook — Fundamentals (2021), Chapter 1: Psychrometrics
Hyland, R.W. & Wexler, A. (1983) ASHRAE Trans. 89(2A):500-519

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.psychro.air import (
    sat_pressure,
    altitude_pressure,
    humidity_ratio_from_rh,
    relative_humidity,
    dew_point,
    wet_bulb,
    enthalpy,
    enthalpy_ip,
    specific_volume,
    state_point,
    mix_air_streams,
    sensible_load_ip,
    latent_load_ip,
    total_load_ip,
    coil_adp,
    coil_leaving_conditions,
    evaporative_cooling,
)

_P_STD_PA = 101_325.0


# ---------------------------------------------------------------------------
# Tool: psychro_state_point
# ---------------------------------------------------------------------------

_state_point_spec = ToolSpec(
    name="psychro_state_point",
    description=(
        "Solve the complete moist-air thermodynamic state from any two independent "
        "psychrometric properties.\n"
        "\n"
        "Supported pairs (Tdb_C is almost always required as the second input):\n"
        "  (Tdb_C, RH), (Tdb_C, W), (Tdb_C, Twb_C), (Tdb_C, Tdp_C),\n"
        "  (Tdb_C, h_kJkg), (W, h_kJkg)\n"
        "\n"
        "Returns: Tdb_C, Twb_C, RH, W (kg/kg), Tdp_C, h_kJkg (kJ/kg),\n"
        "         v_m3perkg, rho_kgperm3, and any warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for unsupported property pairs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Tdb_C": {"type": "number", "description": "Dry-bulb temperature [°C]."},
            "Twb_C": {"type": "number", "description": "Wet-bulb temperature [°C]."},
            "RH": {"type": "number", "description": "Relative humidity [0–1]."},
            "W": {"type": "number", "description": "Humidity ratio [kg water / kg dry air]."},
            "Tdp_C": {"type": "number", "description": "Dew-point temperature [°C]."},
            "h_kJkg": {"type": "number", "description": "Specific enthalpy [kJ/kg dry air]."},
            "P_Pa": {
                "type": "number",
                "description": "Atmospheric pressure [Pa]. Default: 101 325 (sea level).",
            },
        },
        "required": [],
    },
)


@register(_state_point_spec, write=False)
async def run_state_point(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    kwargs: dict = {}
    for key in ("Tdb_C", "Twb_C", "RH", "W", "Tdp_C", "h_kJkg", "P_Pa"):
        if key in a:
            kwargs[key] = a[key]

    given = {k: v for k, v in kwargs.items() if k != "P_Pa"}
    if len(given) < 2:
        return json.dumps({"ok": False, "reason": "Provide at least two of: Tdb_C, Twb_C, RH, W, Tdp_C, h_kJkg"})

    result = state_point(**kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_sat_pressure
# ---------------------------------------------------------------------------

_sat_pressure_spec = ToolSpec(
    name="psychro_sat_pressure",
    description=(
        "Saturation pressure of water vapour at a given temperature "
        "(Hyland-Wexler equations, ASHRAE 2021).\n"
        "\n"
        "Returns pws_Pa [Pa].  Valid range: -100 °C to 200 °C.\n"
        "Over ice below 0 °C, over liquid water at or above 0 °C.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_C": {"type": "number", "description": "Temperature [°C].  Range: -100 to 200."},
        },
        "required": ["T_C"],
    },
)


@register(_sat_pressure_spec, write=False)
async def run_sat_pressure(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if "T_C" not in a:
        return json.dumps({"ok": False, "reason": "T_C is required"})

    result = sat_pressure(a["T_C"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_dew_point
# ---------------------------------------------------------------------------

_dew_point_spec = ToolSpec(
    name="psychro_dew_point",
    description=(
        "Dew-point temperature from dry-bulb temperature and relative humidity.\n"
        "\n"
        "Uses Magnus approximation as initial guess, then refines with "
        "Newton iteration against Hyland-Wexler saturation pressure.\n"
        "\n"
        "Returns Tdp_C [°C].  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_C": {"type": "number", "description": "Dry-bulb temperature [°C]."},
            "RH": {"type": "number", "description": "Relative humidity [0–1]."},
            "P_Pa": {"type": "number", "description": "Atmospheric pressure [Pa]. Default: 101 325."},
        },
        "required": ["T_C", "RH"],
    },
)


@register(_dew_point_spec, write=False)
async def run_dew_point(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_C", "RH"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "P_Pa" in a:
        kwargs["P_Pa"] = a["P_Pa"]

    result = dew_point(a["T_C"], a["RH"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_wet_bulb
# ---------------------------------------------------------------------------

_wet_bulb_spec = ToolSpec(
    name="psychro_wet_bulb",
    description=(
        "Wet-bulb temperature by iterative inversion of the Sprung psychrometric "
        "equation.\n"
        "\n"
        "Returns Twb_C [°C] and converged flag.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_C": {"type": "number", "description": "Dry-bulb temperature [°C]."},
            "RH": {"type": "number", "description": "Relative humidity [0–1]."},
            "P_Pa": {"type": "number", "description": "Atmospheric pressure [Pa]. Default: 101 325."},
        },
        "required": ["T_C", "RH"],
    },
)


@register(_wet_bulb_spec, write=False)
async def run_wet_bulb(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_C", "RH"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "P_Pa" in a:
        kwargs["P_Pa"] = a["P_Pa"]

    result = wet_bulb(a["T_C"], a["RH"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_enthalpy
# ---------------------------------------------------------------------------

_enthalpy_spec = ToolSpec(
    name="psychro_enthalpy",
    description=(
        "Moist-air specific enthalpy (SI).\n"
        "\n"
        "Formula: h = 1.006·T + W·(2501 + 1.86·T)  [kJ/kg dry air]\n"
        "\n"
        "Returns h_kJkg [kJ/kg].  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_C": {"type": "number", "description": "Dry-bulb temperature [°C]."},
            "W": {"type": "number", "description": "Humidity ratio [kg/kg]."},
        },
        "required": ["T_C", "W"],
    },
)


@register(_enthalpy_spec, write=False)
async def run_enthalpy(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_C", "W"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = enthalpy(a["T_C"], a["W"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_enthalpy_ip
# ---------------------------------------------------------------------------

_enthalpy_ip_spec = ToolSpec(
    name="psychro_enthalpy_ip",
    description=(
        "Moist-air specific enthalpy (IP units).\n"
        "\n"
        "Formula: h = 0.240·T + W·(1061 + 0.444·T)  [BTU/lb dry air]\n"
        "\n"
        "Returns h_BTUperlb [BTU/lb].  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_F": {"type": "number", "description": "Dry-bulb temperature [°F]."},
            "W_lbperlb": {"type": "number", "description": "Humidity ratio [lb/lb]."},
        },
        "required": ["T_F", "W_lbperlb"],
    },
)


@register(_enthalpy_ip_spec, write=False)
async def run_enthalpy_ip(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_F", "W_lbperlb"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = enthalpy_ip(a["T_F"], a["W_lbperlb"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_specific_volume
# ---------------------------------------------------------------------------

_specific_volume_spec = ToolSpec(
    name="psychro_specific_volume",
    description=(
        "Specific volume and density of moist air.\n"
        "\n"
        "Returns v_m3perkg [m³/kg dry air] and rho_kgperm3 [kg moist air/m³].\n"
        "\n"
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_C": {"type": "number", "description": "Dry-bulb temperature [°C]."},
            "W": {"type": "number", "description": "Humidity ratio [kg/kg]."},
            "P_Pa": {"type": "number", "description": "Atmospheric pressure [Pa]. Default: 101 325."},
        },
        "required": ["T_C", "W"],
    },
)


@register(_specific_volume_spec, write=False)
async def run_specific_volume(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_C", "W"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "P_Pa" in a:
        kwargs["P_Pa"] = a["P_Pa"]

    result = specific_volume(a["T_C"], a["W"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_mix_streams
# ---------------------------------------------------------------------------

_mix_streams_spec = ToolSpec(
    name="psychro_mix_streams",
    description=(
        "Mix two moist-air streams at equal pressure using mass-weighted averages.\n"
        "\n"
        "Inputs are volumetric flows (CFM) and psychrometric state of each stream.\n"
        "Returns mixed Tdb_C, W (kg/kg), and h_kJkg.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cfm1": {"type": "number", "description": "Volumetric flow of stream 1 [CFM]."},
            "Tdb1_C": {"type": "number", "description": "Dry-bulb of stream 1 [°C]."},
            "W1": {"type": "number", "description": "Humidity ratio of stream 1 [kg/kg]."},
            "cfm2": {"type": "number", "description": "Volumetric flow of stream 2 [CFM]."},
            "Tdb2_C": {"type": "number", "description": "Dry-bulb of stream 2 [°C]."},
            "W2": {"type": "number", "description": "Humidity ratio of stream 2 [kg/kg]."},
            "P_Pa": {"type": "number", "description": "Atmospheric pressure [Pa]. Default: 101 325."},
        },
        "required": ["cfm1", "Tdb1_C", "W1", "cfm2", "Tdb2_C", "W2"],
    },
)


@register(_mix_streams_spec, write=False)
async def run_mix_streams(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("cfm1", "Tdb1_C", "W1", "cfm2", "Tdb2_C", "W2"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    P_Pa = a.get("P_Pa", _P_STD_PA)
    result = mix_air_streams(
        a["cfm1"], a["Tdb1_C"], a["W1"],
        a["cfm2"], a["Tdb2_C"], a["W2"],
        P_Pa=P_Pa,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_sensible_load
# ---------------------------------------------------------------------------

_sensible_load_spec = ToolSpec(
    name="psychro_sensible_load",
    description=(
        "Sensible heat load using ASHRAE standard-air IP formula.\n"
        "\n"
        "  Q_sensible = 1.08 × CFM × ΔT   [BTU/h]\n"
        "\n"
        "Returns Q_BTUh [BTU/h].  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cfm": {"type": "number", "description": "Airflow [CFM]."},
            "delta_T_F": {"type": "number", "description": "Temperature difference [°F]."},
        },
        "required": ["cfm", "delta_T_F"],
    },
)


@register(_sensible_load_spec, write=False)
async def run_sensible_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("cfm", "delta_T_F"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = sensible_load_ip(a["cfm"], a["delta_T_F"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_latent_load
# ---------------------------------------------------------------------------

_latent_load_spec = ToolSpec(
    name="psychro_latent_load",
    description=(
        "Latent heat load using ASHRAE standard-air IP formula.\n"
        "\n"
        "  Q_latent = 0.68 × CFM × ΔW_grains   [BTU/h]  (ΔW in grains/lb)\n"
        "  Q_latent = 4840 × CFM × ΔW           [BTU/h]  (ΔW in lb/lb)\n"
        "\n"
        "Provide exactly one of delta_W_grains or delta_W_lbperlb.\n"
        "Returns Q_BTUh [BTU/h].  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cfm": {"type": "number", "description": "Airflow [CFM]."},
            "delta_W_grains": {
                "type": "number",
                "description": "Humidity ratio difference [grains/lb].  7000 grains = 1 lb.",
            },
            "delta_W_lbperlb": {
                "type": "number",
                "description": "Humidity ratio difference [lb water / lb dry air].",
            },
        },
        "required": ["cfm"],
    },
)


@register(_latent_load_spec, write=False)
async def run_latent_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if "cfm" not in a:
        return json.dumps({"ok": False, "reason": "cfm is required"})
    if "delta_W_grains" not in a and "delta_W_lbperlb" not in a:
        return json.dumps({"ok": False, "reason": "Provide delta_W_grains or delta_W_lbperlb"})

    kwargs: dict = {}
    if "delta_W_grains" in a:
        kwargs["delta_W_grains"] = a["delta_W_grains"]
    if "delta_W_lbperlb" in a:
        kwargs["delta_W_lbperlb"] = a["delta_W_lbperlb"]

    result = latent_load_ip(a["cfm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_total_load
# ---------------------------------------------------------------------------

_total_load_spec = ToolSpec(
    name="psychro_total_load",
    description=(
        "Total (sensible + latent) heat load using ASHRAE standard-air IP formula.\n"
        "\n"
        "  Q_total = 4.5 × CFM × Δh   [BTU/h]  (Δh in BTU/lb)\n"
        "\n"
        "Returns Q_BTUh [BTU/h].  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cfm": {"type": "number", "description": "Airflow [CFM]."},
            "delta_h_BTUperlb": {"type": "number", "description": "Enthalpy difference [BTU/lb dry air]."},
        },
        "required": ["cfm", "delta_h_BTUperlb"],
    },
)


@register(_total_load_spec, write=False)
async def run_total_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("cfm", "delta_h_BTUperlb"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = total_load_ip(a["cfm"], a["delta_h_BTUperlb"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_coil_adp
# ---------------------------------------------------------------------------

_coil_adp_spec = ToolSpec(
    name="psychro_coil_adp",
    description=(
        "Cooling-coil Apparatus Dew Point (ADP), Bypass Factor (BF), "
        "and Sensible Heat Ratio (SHR).\n"
        "\n"
        "The ADP is the effective coil-surface temperature found by extending the "
        "line between entering and leaving state points to the saturation curve.\n"
        "\n"
        "  BF = (Tl - T_ADP) / (Te - T_ADP)  [0 = perfect contact, 1 = no contact]\n"
        "  SHR = ΔTs / Δh  (approximate from Tdb/enthalpy change ratio)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Tdb_entering_C": {"type": "number", "description": "Entering dry-bulb [°C]."},
            "Twb_entering_C": {"type": "number", "description": "Entering wet-bulb [°C]."},
            "Tdb_leaving_C": {"type": "number", "description": "Leaving dry-bulb [°C]."},
            "Twb_leaving_C": {"type": "number", "description": "Leaving wet-bulb [°C]."},
            "P_Pa": {"type": "number", "description": "Atmospheric pressure [Pa]. Default: 101 325."},
        },
        "required": ["Tdb_entering_C", "Twb_entering_C", "Tdb_leaving_C", "Twb_leaving_C"],
    },
)


@register(_coil_adp_spec, write=False)
async def run_coil_adp(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Tdb_entering_C", "Twb_entering_C", "Tdb_leaving_C", "Twb_leaving_C"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "P_Pa" in a:
        kwargs["P_Pa"] = a["P_Pa"]

    result = coil_adp(
        a["Tdb_entering_C"], a["Twb_entering_C"],
        a["Tdb_leaving_C"], a["Twb_leaving_C"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_coil_leaving
# ---------------------------------------------------------------------------

_coil_leaving_spec = ToolSpec(
    name="psychro_coil_leaving",
    description=(
        "Cooling-coil leaving-air conditions from entering state and applied loads.\n"
        "\n"
        "Returns leaving Tdb_C, W (kg/kg), h_leaving (kJ/kg), and SHR.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Tdb_entering_C": {"type": "number", "description": "Entering dry-bulb [°C]."},
            "W_entering": {"type": "number", "description": "Entering humidity ratio [kg/kg]."},
            "Q_sensible_kW": {"type": "number", "description": "Sensible cooling load [kW]. Positive = cooling."},
            "Q_total_kW": {"type": "number", "description": "Total cooling load [kW]. Positive = cooling."},
            "mass_flow_kgs": {"type": "number", "description": "Dry-air mass flow rate [kg/s]. Must be > 0."},
            "P_Pa": {"type": "number", "description": "Atmospheric pressure [Pa]. Default: 101 325."},
        },
        "required": ["Tdb_entering_C", "W_entering", "Q_sensible_kW", "Q_total_kW", "mass_flow_kgs"],
    },
)


@register(_coil_leaving_spec, write=False)
async def run_coil_leaving(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Tdb_entering_C", "W_entering", "Q_sensible_kW", "Q_total_kW", "mass_flow_kgs"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "P_Pa" in a:
        kwargs["P_Pa"] = a["P_Pa"]

    result = coil_leaving_conditions(
        a["Tdb_entering_C"], a["W_entering"],
        a["Q_sensible_kW"], a["Q_total_kW"],
        a["mass_flow_kgs"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_evaporative_cooling
# ---------------------------------------------------------------------------

_evap_cooling_spec = ToolSpec(
    name="psychro_evaporative_cooling",
    description=(
        "Direct evaporative cooler leaving conditions.\n"
        "\n"
        "  Tdb_leaving = Tdb - ε × (Tdb - Twb)\n"
        "\n"
        "Enthalpy stays approximately constant (adiabatic saturation).\n"
        "Returns Tdb_leaving_C, W_leaving, RH_leaving, h_leaving_kJkg.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Tdb_C": {"type": "number", "description": "Entering dry-bulb temperature [°C]."},
            "RH": {"type": "number", "description": "Entering relative humidity [0–1]."},
            "effectiveness": {
                "type": "number",
                "description": "Cooler effectiveness [0–1]. Default: 0.80.",
            },
            "P_Pa": {"type": "number", "description": "Atmospheric pressure [Pa]. Default: 101 325."},
        },
        "required": ["Tdb_C", "RH"],
    },
)


@register(_evap_cooling_spec, write=False)
async def run_evaporative_cooling(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Tdb_C", "RH"):
        if field not in a:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "effectiveness" in a:
        kwargs["effectiveness"] = a["effectiveness"]
    if "P_Pa" in a:
        kwargs["P_Pa"] = a["P_Pa"]

    result = evaporative_cooling(a["Tdb_C"], a["RH"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: psychro_altitude_pressure
# ---------------------------------------------------------------------------

_altitude_pressure_spec = ToolSpec(
    name="psychro_altitude_pressure",
    description=(
        "Barometric pressure at a given altitude above sea level (ISA troposphere).\n"
        "\n"
        "  P = 101325 × (1 - 2.25577e-5 × z)^5.2559   [Pa]\n"
        "\n"
        "Returns P_Pa [Pa].  Valid: 0–11 000 m.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "altitude_m": {"type": "number", "description": "Altitude above sea level [m]."},
        },
        "required": ["altitude_m"],
    },
)


@register(_altitude_pressure_spec, write=False)
async def run_altitude_pressure(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if "altitude_m" not in a:
        return json.dumps({"ok": False, "reason": "altitude_m is required"})

    result = altitude_pressure(a["altitude_m"])
    return ok_payload(result)
