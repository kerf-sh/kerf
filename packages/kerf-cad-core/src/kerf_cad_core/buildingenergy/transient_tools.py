"""
kerf_cad_core.buildingenergy.transient_tools — LLM tool wrappers for transient cooling load methods.

Registers tools with the Kerf tool registry:

  be_sol_air_temp                  — sol-air surface temperature
  be_cltd_wall                     — tabulated CLTD for opaque walls
  be_cltd_roof                     — tabulated CLTD for roofs
  be_correct_cltd                  — apply CLTD latitude/colour/temperature corrections
  be_wall_cooling_load             — q = U·A·CLTDc
  be_solar_heat_gain_rts           — solar heat gain through fenestration (direct + diffuse + ground)
  be_cooling_load_fenestration_rts — fenestration cooling load via RTS
  be_zone_24h_cooling_load         — full zone 24-hour cooling load profile

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
ASHRAE Handbook — Fundamentals (1989), Chapters 26 & 27 (CLTD/CLF)
ASHRAE Handbook — Fundamentals (2009), Chapter 18 (RTS method)
ASHRAE Handbook — Fundamentals (2021), Chapter 18 §18.4 (sol-air temperature)

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.buildingenergy.transient import (
    sol_air_temp,
    cltd_wall,
    cltd_roof,
    correct_cltd,
    wall_cooling_load,
    solar_heat_gain,
    cooling_load_fenestration_rts,
    zone_24h_cooling_load,
)


# ---------------------------------------------------------------------------
# Tool: be_sol_air_temp
# ---------------------------------------------------------------------------

_sol_air_spec = ToolSpec(
    name="be_sol_air_temp",
    description=(
        "Compute the sol-air temperature (°C or °F) for an exterior surface.\n"
        "\n"
        "  Tsa = T_outdoor + α·I_solar / h_o  −  ε·ΔR / h_o\n"
        "\n"
        "This is the equivalent outdoor temperature that drives the same heat flux "
        "into the surface as the combined effect of outdoor air temperature and solar "
        "irradiance.  Used as input to conduction-time-series or CLTD calculations.\n"
        "\n"
        "Reference: ASHRAE Fundamentals (2021) Ch. 18 §18.4.\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_outdoor": {
                "type": "number",
                "description": "Outdoor dry-bulb temperature (°C or °F, same unit as output).",
            },
            "I_solar": {
                "type": "number",
                "description": "Solar irradiance on the surface (W/m² or Btu/(hr·ft²)). Must be >= 0.",
            },
            "absorptance_short": {
                "type": "number",
                "description": "Short-wave absorptance α of the outer surface [0–1]. Dark ≈ 0.9, light ≈ 0.45.",
            },
            "h_o": {
                "type": "number",
                "description": (
                    "Exterior surface film coefficient (W/(m²·K) or Btu/(hr·ft²·°F)). "
                    "ASHRAE SI default: 22.7 W/(m²·K)."
                ),
            },
            "dT_long_wave": {
                "type": "number",
                "description": (
                    "Long-wave radiation correction ΔR (same units as I_solar). "
                    "For roofs use ~63 W/m² (SI) or ~20 Btu/(hr·ft²) (IP). "
                    "For vertical walls use 0 (default)."
                ),
            },
            "emittance": {
                "type": "number",
                "description": "Long-wave emittance ε of surface [0–1]. Default 1.0 (matte).",
            },
        },
        "required": ["T_outdoor", "I_solar", "absorptance_short", "h_o"],
    },
)


@register(_sol_air_spec, write=False)
async def run_sol_air_temp(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_outdoor", "I_solar", "absorptance_short", "h_o"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("dT_long_wave", "emittance"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = sol_air_temp(
        a["T_outdoor"], a["I_solar"], a["absorptance_short"], a["h_o"], **kwargs
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_cltd_wall
# ---------------------------------------------------------------------------

_cltd_wall_spec = ToolSpec(
    name="be_cltd_wall",
    description=(
        "Return the tabulated Cooling Load Temperature Difference (CLTD, °F) for "
        "an opaque wall at a given solar hour.\n"
        "\n"
        "Groups:\n"
        "  A = no mass (fast response, e.g. glass-curtain)\n"
        "  B = light frame with insulation\n"
        "  C = medium-weight masonry / concrete block\n"
        "  D = heavy masonry / 8\" brick (slow response)\n"
        "\n"
        "Standard conditions: 40°N, July, Ti=78°F, To_mean=85°F.\n"
        "Apply correct_cltd to adjust for actual conditions.\n"
        "\n"
        "Reference: ASHRAE Handbook of Fundamentals, 1989, Table 34.\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "wall_type": {
                "type": "string",
                "enum": ["A", "B", "C", "D"],
                "description": "Wall thermal mass group.",
            },
            "hour": {
                "type": "integer",
                "description": "Solar time hour (0–23).",
            },
        },
        "required": ["wall_type", "hour"],
    },
)


@register(_cltd_wall_spec, write=False)
async def run_cltd_wall(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("wall_type", "hour"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = cltd_wall(a["wall_type"], a["hour"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_cltd_roof
# ---------------------------------------------------------------------------

_cltd_roof_spec = ToolSpec(
    name="be_cltd_roof",
    description=(
        "Return the tabulated Cooling Load Temperature Difference (CLTD, °F) for "
        "a roof at a given solar hour.\n"
        "\n"
        "Roof types:\n"
        "  light  = steel deck + 1\" insulation (fast)\n"
        "  medium = concrete + insulation\n"
        "  heavy  = 8\" concrete + insulation (slow)\n"
        "\n"
        "Standard conditions: 40°N, July, Ti=78°F, To_mean=85°F.\n"
        "Apply correct_cltd to adjust for actual conditions.\n"
        "\n"
        "Reference: ASHRAE Handbook of Fundamentals, 1989, Table 36.\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "roof_type": {
                "type": "string",
                "enum": ["light", "medium", "heavy"],
                "description": "Roof thermal mass category.",
            },
            "hour": {
                "type": "integer",
                "description": "Solar time hour (0–23).",
            },
        },
        "required": ["roof_type", "hour"],
    },
)


@register(_cltd_roof_spec, write=False)
async def run_cltd_roof(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("roof_type", "hour"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = cltd_roof(a["roof_type"], a["hour"])
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_correct_cltd
# ---------------------------------------------------------------------------

_correct_cltd_spec = ToolSpec(
    name="be_correct_cltd",
    description=(
        "Apply latitude–month and temperature corrections to a tabulated CLTD.\n"
        "\n"
        "  CLTDc = (CLTD_tab + LM) × K + (78 − Ti) + (To_mean − 85)\n"
        "\n"
        "Returns CLTDc in both °F (IP) and °C (SI delta-temperature).\n"
        "\n"
        "Parameters:\n"
        "  CLTD_tab       — raw table value (°F)\n"
        "  LM             — latitude–month correction °F (Table 35, default 0)\n"
        "  K              — color factor: 1.0 dark, ~0.5 light (default 1.0)\n"
        "  T_indoor_F     — actual design indoor temp °F (default 78)\n"
        "  T_outdoor_F_mean — design-day mean outdoor temp °F (default 85)\n"
        "\n"
        "Reference: ASHRAE Handbook of Fundamentals, 1989, Ch. 26 Eq. (3).\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "CLTD_tab": {
                "type": "number",
                "description": "Tabulated CLTD from wall or roof table (°F).",
            },
            "LM": {
                "type": "number",
                "description": "Latitude–month correction (°F). Default 0.",
            },
            "K": {
                "type": "number",
                "description": "Color factor [0–1]: 1.0 = dark/default, 0.5 = light surface.",
            },
            "T_indoor_F": {
                "type": "number",
                "description": "Design indoor temperature (°F). Default 78.",
            },
            "T_outdoor_F_mean": {
                "type": "number",
                "description": "Mean daily outdoor design temperature (°F). Default 85.",
            },
        },
        "required": ["CLTD_tab"],
    },
)


@register(_correct_cltd_spec, write=False)
async def run_correct_cltd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("CLTD_tab") is None:
        return json.dumps({"ok": False, "reason": "CLTD_tab is required"})

    kwargs: dict = {}
    for opt in ("LM", "K", "T_indoor_F", "T_outdoor_F_mean"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = correct_cltd(a["CLTD_tab"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_wall_cooling_load
# ---------------------------------------------------------------------------

_wall_cl_spec = ToolSpec(
    name="be_wall_cooling_load",
    description=(
        "Compute the instantaneous conductive cooling load through an opaque "
        "wall or roof element.\n"
        "\n"
        "  q = U × A × CLTDc\n"
        "\n"
        "Returns q_W (watts) and q_Btuhr (Btu/hr).\n"
        "\n"
        "When ip_units=true: U in Btu/(hr·ft²·°F), A in ft², CLTDc in °F → q in Btu/hr.\n"
        "When ip_units=false (default): U in W/(m²·K), A in m², CLTDc in °C → q in W.\n"
        "\n"
        "Reference: ASHRAE Handbook of Fundamentals, 1989, Ch. 26.\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "U": {
                "type": "number",
                "description": "U-value [W/(m²·K) or Btu/(hr·ft²·°F)]. Must be >= 0.",
            },
            "A": {
                "type": "number",
                "description": "Surface area [m² or ft²]. Must be >= 0.",
            },
            "CLTDc": {
                "type": "number",
                "description": "Corrected CLTD [°C or °F depending on ip_units].",
            },
            "ip_units": {
                "type": "boolean",
                "description": "True = IP (ft², °F, Btu/hr). False = SI (m², °C, W). Default false.",
            },
        },
        "required": ["U", "A", "CLTDc"],
    },
)


@register(_wall_cl_spec, write=False)
async def run_wall_cooling_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("U", "A", "CLTDc"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "ip_units" in a:
        kwargs["ip_units"] = bool(a["ip_units"])

    result = wall_cooling_load(a["U"], a["A"], a["CLTDc"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_solar_heat_gain_rts  (renamed to avoid clash with be_solar_heat_gain in energy)
# ---------------------------------------------------------------------------

_shg_rts_spec = ToolSpec(
    name="be_solar_heat_gain_rts",
    description=(
        "Compute instantaneous solar heat gain through a fenestration element (W), "
        "accounting for direct beam, diffuse sky, and ground-reflected components.\n"
        "\n"
        "  Q_dir  = SHGC × IAC × I_dir × area × frame_factor\n"
        "  Q_diff = SHGC × IAC × I_diff × Fsky × area × frame_factor\n"
        "  Q_gnd  = SHGC × IAC × ρ_g × (I_dir+I_diff) × Fgnd × area × frame_factor\n"
        "\n"
        "This function is used as input to the RTS fenestration cooling-load method.\n"
        "\n"
        "Reference: ASHRAE Fundamentals (2009) Ch. 18; ASHRAE Fundamentals (2021) Ch. 15.\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "I_dir": {
                "type": "number",
                "description": "Direct in-plane irradiance on the glazing (W/m²). Must be >= 0.",
            },
            "I_diff": {
                "type": "number",
                "description": "Diffuse horizontal irradiance (W/m²). Must be >= 0.",
            },
            "area": {
                "type": "number",
                "description": "Glazing area (m²). Must be >= 0.",
            },
            "SHGC": {
                "type": "number",
                "description": "Solar heat gain coefficient at normal incidence [0–1].",
            },
            "IAC": {
                "type": "number",
                "description": "Interior attenuation coefficient (blind/shade) [0–1]. Default 1.0 (no shade).",
            },
            "frame_factor": {
                "type": "number",
                "description": "Glazing fraction of opening [0–1]. Default 1.0 (no frame).",
            },
            "orientation": {
                "type": "string",
                "enum": ["south", "north", "east", "west", "horizontal"],
                "description": "Facade orientation. Default 'south'.",
            },
            "ground_reflectance": {
                "type": "number",
                "description": "Ground albedo [0–1]. Default 0.2.",
            },
        },
        "required": ["I_dir", "I_diff", "area", "SHGC"],
    },
)


@register(_shg_rts_spec, write=False)
async def run_solar_heat_gain_rts(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("I_dir", "I_diff", "area", "SHGC"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("IAC", "frame_factor", "orientation", "ground_reflectance"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = solar_heat_gain(
        a["I_dir"], a["I_diff"], a["area"], a["SHGC"], **kwargs
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_cooling_load_fenestration_rts
# ---------------------------------------------------------------------------

_cl_fenestr_rts_spec = ToolSpec(
    name="be_cooling_load_fenestration_rts",
    description=(
        "Apply the ASHRAE Radiant Time Series (RTS) method to convert a 24-hour "
        "fenestration solar heat gain profile into a cooling load profile.\n"
        "\n"
        "  CL(t) = Σ_{i=0}^{23} RTS[i] × SHG(t−i)  [cyclic]\n"
        "\n"
        "SHG_24h: list of 24 hourly solar heat gains (W) from be_solar_heat_gain_rts.\n"
        "RTS_series: optional 24-element Radiant Time Series (default: medium-weight zone, "
        "ASHRAE 2009 HoF Table 19).\n"
        "\n"
        "Returns CL_24h (24-h cooling load profile, W), peak_hour, and peak_load_W.\n"
        "\n"
        "Reference: ASHRAE Handbook — Fundamentals (2009), Ch. 18 §18.4.\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "SHG_24h": {
                "type": "array",
                "description": "24 hourly solar heat gain values (W), hours 0–23.",
                "items": {"type": "number"},
            },
            "RTS_series": {
                "type": "array",
                "description": (
                    "Optional 24-element RTS vector (fractions summing to 1.0). "
                    "Default: medium-weight zone per ASHRAE 2009 HoF Table 19."
                ),
                "items": {"type": "number"},
            },
        },
        "required": ["SHG_24h"],
    },
)


@register(_cl_fenestr_rts_spec, write=False)
async def run_cooling_load_fenestration_rts(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("SHG_24h") is None:
        return json.dumps({"ok": False, "reason": "SHG_24h is required"})

    kwargs: dict = {}
    if "RTS_series" in a:
        kwargs["RTS_series"] = a["RTS_series"]

    result = cooling_load_fenestration_rts(a["SHG_24h"], **kwargs)
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: be_zone_24h_cooling_load
# ---------------------------------------------------------------------------

_zone_24h_spec = ToolSpec(
    name="be_zone_24h_cooling_load",
    description=(
        "Compute the full 24-hour sensible cooling load profile for a zone using "
        "the CLTD method for opaque envelope elements and the RTS method for "
        "fenestration solar gains.\n"
        "\n"
        "Returns:\n"
        "  CL_24h         — list of 24 hourly total cooling loads (W)\n"
        "  peak_hour      — hour of peak cooling load (0–23)\n"
        "  peak_load_W    — peak cooling load (W)\n"
        "  envelope_24h   — opaque wall + roof contribution per hour\n"
        "  fenestration_24h — window solar gain (RTS-weighted) per hour\n"
        "  internal_24h   — internal gains per hour\n"
        "  infiltration_24h — infiltration/ventilation per hour\n"
        "\n"
        "Reference: ASHRAE Fundamentals (1989) Ch. 26 (CLTD); (2009) Ch. 18 (RTS).\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "walls": {
                "type": "array",
                "description": (
                    "List of wall dicts: {U (W/(m²·K)), A (m²), wall_type ('A'–'D'), "
                    "LM (°F, opt), K (opt), T_outdoor_mean_F (opt, default 85)}."
                ),
                "items": {"type": "object"},
            },
            "roof": {
                "type": "object",
                "description": (
                    "Roof dict: {U, A, roof_type ('light'|'medium'|'heavy'), "
                    "LM (opt), K (opt), T_outdoor_mean_F (opt)}. Null to omit."
                ),
            },
            "windows": {
                "type": "array",
                "description": (
                    "List of window dicts: {I_dir_24h (list 24), I_diff_24h (list 24), "
                    "area, SHGC, IAC (opt), frame_factor (opt), orientation (opt)}."
                ),
                "items": {"type": "object"},
            },
            "internal_gains": {
                "type": "array",
                "description": "24 hourly sensible internal gains (W).",
                "items": {"type": "number"},
            },
            "outdoor_temp_24h": {
                "type": "array",
                "description": "24 hourly outdoor dry-bulb temperatures (°C).",
                "items": {"type": "number"},
            },
            "solar_24h": {
                "type": "array",
                "description": "Reserved for future per-hour solar overrides. Pass [] if unused.",
                "items": {"type": "object"},
            },
            "design_indoor_T": {
                "type": "number",
                "description": "Indoor design setpoint temperature (°C). Typically 24–26.",
            },
            "RTS_series": {
                "type": "array",
                "description": "Optional 24-element RTS vector. Default: medium-weight zone.",
                "items": {"type": "number"},
            },
            "infiltration_UA": {
                "type": "number",
                "description": "Infiltration + ventilation UA coefficient (W/K). Default 0.",
            },
        },
        "required": [
            "walls", "windows", "internal_gains",
            "outdoor_temp_24h", "solar_24h", "design_indoor_T",
        ],
    },
)


@register(_zone_24h_spec, write=False)
async def run_zone_24h_cooling_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("walls", "windows", "internal_gains", "outdoor_temp_24h",
                  "solar_24h", "design_indoor_T"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "RTS_series" in a:
        kwargs["RTS_series"] = a["RTS_series"]
    if "infiltration_UA" in a:
        kwargs["infiltration_UA"] = a["infiltration_UA"]

    result = zone_24h_cooling_load(
        a["walls"],
        a.get("roof"),
        a["windows"],
        a["internal_gains"],
        a["outdoor_temp_24h"],
        a["solar_24h"],
        a["design_indoor_T"],
        **kwargs,
    )
    if result.get("ok"):
        return ok_payload(result)
    return json.dumps(result)
