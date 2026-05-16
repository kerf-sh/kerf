"""
kerf_cad_core.thermalcut.tools — LLM tool wrappers for thermal/abrasive cutting.

Registers eleven tools with the Kerf tool registry:

  thermalcut_laser_speed      — max laser cut speed vs thickness & power
  thermalcut_plasma_speed     — max plasma cut speed vs thickness & amperage
  thermalcut_oxyfuel_speed    — empirical oxyfuel traverse speed
  thermalcut_waterjet_speed   — AWJ traverse speed (Hashish model)
  thermalcut_kerf_width       — kerf width estimate for any process
  thermalcut_haz_width        — heat-affected zone width estimate
  thermalcut_pierce_time      — pierce / punch-through time
  thermalcut_edge_quality     — edge quality regime and dross risk
  thermalcut_gas_consumption  — assist/fuel gas volume and cost
  thermalcut_waterjet_params  — orifice/mixing-tube sizing and jet power
  thermalcut_part_cost        — full part cost roll-up
  thermalcut_process_compare  — side-by-side process comparison

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Steen & Mazumder, "Laser Material Processing", 4th ed., Springer 2010
ESAB Plasma Cutting Handbook, 3rd ed.
AWS C5.2 — Recommended Practices for Plasma Arc Cutting
Hashish, M., J. Eng. for Ind. 1989

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.thermalcut.process import (
    laser_cut_speed,
    plasma_cut_speed,
    oxyfuel_cut_speed,
    waterjet_cut_speed,
    kerf_width,
    haz_width,
    pierce_time,
    edge_quality_regime,
    gas_consumption,
    waterjet_params,
    part_cost,
    process_compare,
)

_VALID_PROCESSES = ["laser", "plasma", "oxyfuel", "waterjet"]
_VALID_MATERIALS = [
    "mild_steel", "stainless_304", "stainless_316", "tool_steel",
    "aluminium_6061", "aluminium_5052", "copper", "brass",
    "titanium_gr2", "carbon_fibre_composite", "glass", "granite",
]


# ---------------------------------------------------------------------------
# Tool: thermalcut_laser_speed
# ---------------------------------------------------------------------------

_laser_speed_spec = ToolSpec(
    name="thermalcut_laser_speed",
    description=(
        "Compute the maximum cutting speed (mm/min) for a CO₂ or fibre laser "
        "using an energy-balance model.\n"
        "\n"
        "Model: v = η·P / (ρ·H·t·w_k) where H = c_p·ΔT + L_f + 0.15·L_v.\n"
        "\n"
        "Returns speed_mm_min, kerf_mm, heat_content_J_kg, and warnings "
        "(too-thick-for-power, material-range).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "thickness_mm": {
                "type": "number",
                "description": "Material thickness (mm). Must be > 0.",
            },
            "power_W": {
                "type": "number",
                "description": "Laser output power at the workpiece (W). Must be > 0.",
            },
            "material": {
                "type": "string",
                "enum": _VALID_MATERIALS,
                "description": "Material key (default 'mild_steel').",
            },
            "assist_gas": {
                "type": "string",
                "enum": ["O2", "N2", "Air"],
                "description": "Assist gas type (default 'O2').",
            },
            "efficiency": {
                "type": "number",
                "description": (
                    "Fraction of laser power absorbed at cut front (0 < η ≤ 1). "
                    "Defaults to 0.55 for O₂, 0.45 for N₂/Air."
                ),
            },
            "kerf_mm": {
                "type": "number",
                "description": "Override kerf width (mm). If omitted, estimated.",
            },
        },
        "required": ["thickness_mm", "power_W"],
    },
)


@register(_laser_speed_spec, write=False)
async def run_thermalcut_laser_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("thickness_mm") is None:
        return json.dumps({"ok": False, "reason": "thickness_mm is required"})
    if a.get("power_W") is None:
        return json.dumps({"ok": False, "reason": "power_W is required"})

    kwargs: dict = {}
    for k in ("material", "assist_gas", "efficiency", "kerf_mm"):
        if k in a:
            kwargs[k] = a[k]

    result = laser_cut_speed(a["thickness_mm"], a["power_W"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_plasma_speed
# ---------------------------------------------------------------------------

_plasma_speed_spec = ToolSpec(
    name="thermalcut_plasma_speed",
    description=(
        "Compute the maximum cutting speed (mm/min) for plasma arc cutting "
        "via the energy-balance model.  Arc power = voltage × amperage.\n"
        "\n"
        "Returns speed_mm_min, arc power (W), kerf_mm, and warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "thickness_mm": {
                "type": "number",
                "description": "Material thickness (mm). Must be > 0.",
            },
            "amperage": {
                "type": "number",
                "description": "Plasma arc current (A). Must be > 0.",
            },
            "material": {
                "type": "string",
                "enum": _VALID_MATERIALS,
                "description": "Material key (default 'mild_steel').",
            },
            "voltage": {
                "type": "number",
                "description": "Arc voltage (V). Default 130 V.",
            },
            "efficiency": {
                "type": "number",
                "description": "Fraction of arc power going into cut front. Default 0.48.",
            },
        },
        "required": ["thickness_mm", "amperage"],
    },
)


@register(_plasma_speed_spec, write=False)
async def run_thermalcut_plasma_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("thickness_mm") is None:
        return json.dumps({"ok": False, "reason": "thickness_mm is required"})
    if a.get("amperage") is None:
        return json.dumps({"ok": False, "reason": "amperage is required"})

    kwargs: dict = {}
    for k in ("material", "voltage", "efficiency"):
        if k in a:
            kwargs[k] = a[k]

    result = plasma_cut_speed(a["thickness_mm"], a["amperage"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_oxyfuel_speed
# ---------------------------------------------------------------------------

_oxyfuel_speed_spec = ToolSpec(
    name="thermalcut_oxyfuel_speed",
    description=(
        "Look up the empirical maximum traverse speed (mm/min) for "
        "oxyfuel (oxy-acetylene / oxy-propane) cutting of ferrous materials.\n"
        "\n"
        "Uses piecewise-linear interpolation from published Lincoln Electric data.\n"
        "Only valid for mild_steel and tool_steel.\n"
        "\n"
        "Errors: {ok:false, reason} for non-ferrous materials or invalid inputs.  "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "thickness_mm": {
                "type": "number",
                "description": "Material thickness (mm). Range: 1–300 mm.",
            },
            "material": {
                "type": "string",
                "enum": _VALID_MATERIALS,
                "description": "Material key.  Must be an oxyfuel-compatible ferrous material.",
            },
        },
        "required": ["thickness_mm"],
    },
)


@register(_oxyfuel_speed_spec, write=False)
async def run_thermalcut_oxyfuel_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("thickness_mm") is None:
        return json.dumps({"ok": False, "reason": "thickness_mm is required"})

    kwargs: dict = {}
    if "material" in a:
        kwargs["material"] = a["material"]

    result = oxyfuel_cut_speed(a["thickness_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_waterjet_speed
# ---------------------------------------------------------------------------

_waterjet_speed_spec = ToolSpec(
    name="thermalcut_waterjet_speed",
    description=(
        "Compute traverse speed (mm/min) for abrasive-waterjet (AWJ) cutting "
        "using the Hashish (1989) machinability model.\n"
        "\n"
        "Model: v = C_m · P_j^1.25 · m_a^0.687 / (t · d_f^1.15 · N_m)\n"
        "\n"
        "Returns speed_mm_min, jet_power_W, mixing_tube_dia_mm, and warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "thickness_mm": {
                "type": "number",
                "description": "Material thickness (mm). Must be > 0.",
            },
            "material": {
                "type": "string",
                "enum": _VALID_MATERIALS,
                "description": "Material key (default 'mild_steel').",
            },
            "pump_power_kW": {
                "type": "number",
                "description": "Hydraulic pump power (kW). Default 30 kW.",
            },
            "orifice_dia_mm": {
                "type": "number",
                "description": "Water orifice diameter (mm). Default 0.356 mm.",
            },
            "abrasive_rate_kg_min": {
                "type": "number",
                "description": "Abrasive (garnet) feed rate (kg/min). Default 0.45.",
            },
            "machinability_number": {
                "type": "number",
                "description": (
                    "Override Hashish machinability number (dimensionless). "
                    "If omitted, uses material database value."
                ),
            },
        },
        "required": ["thickness_mm"],
    },
)


@register(_waterjet_speed_spec, write=False)
async def run_thermalcut_waterjet_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("thickness_mm") is None:
        return json.dumps({"ok": False, "reason": "thickness_mm is required"})

    kwargs: dict = {}
    for k in ("material", "pump_power_kW", "orifice_dia_mm",
              "abrasive_rate_kg_min", "machinability_number"):
        if k in a:
            kwargs[k] = a[k]

    result = waterjet_cut_speed(a["thickness_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_kerf_width
# ---------------------------------------------------------------------------

_kerf_width_spec = ToolSpec(
    name="thermalcut_kerf_width",
    description=(
        "Estimate kerf width (mm) for a given process, thickness, and power.\n"
        "\n"
        "Empirical formulas:\n"
        "  laser    : 0.10 + 0.04·√t  (mm)\n"
        "  plasma   : 1.50 + 0.12·t^0.6\n"
        "  oxyfuel  : 0.80 + 0.06·t^0.7\n"
        "  waterjet : d_orifice·3.5 + 0.02·t\n"
        "\n"
        "For waterjet, power_or_amp is pump power in kW.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "process": {
                "type": "string",
                "enum": _VALID_PROCESSES,
                "description": "Cutting process.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Material thickness (mm). Must be > 0.",
            },
            "power_or_amp": {
                "type": "number",
                "description": (
                    "Laser power (W), plasma amperage (A), "
                    "oxyfuel O₂ flow (L/min), or waterjet pump power (kW)."
                ),
            },
        },
        "required": ["process", "thickness_mm", "power_or_amp"],
    },
)


@register(_kerf_width_spec, write=False)
async def run_thermalcut_kerf_width(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("process", "thickness_mm", "power_or_amp"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = kerf_width(a["process"], a["thickness_mm"], a["power_or_amp"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_haz_width
# ---------------------------------------------------------------------------

_haz_width_spec = ToolSpec(
    name="thermalcut_haz_width",
    description=(
        "Estimate the heat-affected zone (HAZ) width (mm) at the cut edge.\n"
        "\n"
        "Model: HAZ = k_mat · √(P / (v·t))\n"
        "\n"
        "Waterjet returns HAZ = 0 (cold process).\n"
        "For plasma, power_or_amp is the arc current (A).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "process": {
                "type": "string",
                "enum": _VALID_PROCESSES,
                "description": "Cutting process.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Material thickness (mm). Must be > 0.",
            },
            "speed_mm_min": {
                "type": "number",
                "description": "Traverse speed (mm/min). Must be > 0.",
            },
            "power_or_amp": {
                "type": "number",
                "description": (
                    "Laser power (W), plasma amperage (A), or oxyfuel O₂ flow (L/min). "
                    "For waterjet, any positive value is accepted."
                ),
            },
            "material": {
                "type": "string",
                "enum": _VALID_MATERIALS,
                "description": "Material key (default 'mild_steel').",
            },
        },
        "required": ["process", "thickness_mm", "speed_mm_min", "power_or_amp"],
    },
)


@register(_haz_width_spec, write=False)
async def run_thermalcut_haz_width(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("process", "thickness_mm", "speed_mm_min", "power_or_amp"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "material" in a:
        kwargs["material"] = a["material"]

    result = haz_width(
        a["process"], a["thickness_mm"], a["speed_mm_min"], a["power_or_amp"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_pierce_time
# ---------------------------------------------------------------------------

_pierce_time_spec = ToolSpec(
    name="thermalcut_pierce_time",
    description=(
        "Compute the pierce / punch-through time (seconds) before traverse.\n"
        "\n"
        "Empirical models:\n"
        "  laser    : 0.05·t^1.3 / (P_kW^0.4)\n"
        "  plasma   : 0.10·t^0.9 / ((I/100)^0.5)\n"
        "  oxyfuel  : 2.0 + 0.40·t\n"
        "  waterjet : 0.02·t\n"
        "\n"
        "power_W required for laser; amperage required for plasma.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "process": {
                "type": "string",
                "enum": _VALID_PROCESSES,
                "description": "Cutting process.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Material thickness (mm). Must be > 0.",
            },
            "power_W": {
                "type": "number",
                "description": "Laser power (W). Required for laser.",
            },
            "amperage": {
                "type": "number",
                "description": "Plasma current (A). Required for plasma.",
            },
        },
        "required": ["process", "thickness_mm"],
    },
)


@register(_pierce_time_spec, write=False)
async def run_thermalcut_pierce_time(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("process", "thickness_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "power_W" in a:
        kwargs["power_W"] = a["power_W"]
    if "amperage" in a:
        kwargs["amperage"] = a["amperage"]

    result = pierce_time(a["process"], a["thickness_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_edge_quality
# ---------------------------------------------------------------------------

_edge_quality_spec = ToolSpec(
    name="thermalcut_edge_quality",
    description=(
        "Assess edge quality regime and dross risk for a given speed ratio.\n"
        "\n"
        "Regimes:\n"
        "  v < 0.60·v_nom  → too_slow  (dross: high,     quality: poor)\n"
        "  v in [0.60,0.85) → slow      (dross: moderate, quality: fair)\n"
        "  v in [0.85,1.15] → optimal   (dross: low,      quality: excellent)\n"
        "  v in (1.15,1.40] → fast      (dross: moderate, quality: good)\n"
        "  v > 1.40·v_nom  → too_fast  (dross: high,     quality: poor)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "process": {
                "type": "string",
                "enum": _VALID_PROCESSES,
                "description": "Cutting process (informational).",
            },
            "speed_mm_min": {
                "type": "number",
                "description": "Actual traverse speed (mm/min). Must be > 0.",
            },
            "nominal_speed_mm_min": {
                "type": "number",
                "description": "Nominal / optimal speed (mm/min). Must be > 0.",
            },
        },
        "required": ["process", "speed_mm_min", "nominal_speed_mm_min"],
    },
)


@register(_edge_quality_spec, write=False)
async def run_thermalcut_edge_quality(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("process", "speed_mm_min", "nominal_speed_mm_min"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = edge_quality_regime(
        a["process"], a["speed_mm_min"], a["nominal_speed_mm_min"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_gas_consumption
# ---------------------------------------------------------------------------

_gas_consumption_spec = ToolSpec(
    name="thermalcut_gas_consumption",
    description=(
        "Compute assist/fuel gas consumption (litres) and cost (USD) for a cut.\n"
        "\n"
        "Rates:\n"
        "  laser (O₂): 15 L/min  laser (N₂): 30 L/min\n"
        "  plasma:     15 L/min shield gas\n"
        "  oxyfuel:    10 L/min acetylene + 45 L/min O₂\n"
        "  waterjet:   0 (abrasive only)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "process": {
                "type": "string",
                "enum": _VALID_PROCESSES,
                "description": "Cutting process.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Material thickness (mm). Must be > 0.",
            },
            "cut_length_mm": {
                "type": "number",
                "description": "Total cut length (mm). Must be > 0.",
            },
            "speed_mm_min": {
                "type": "number",
                "description": "Traverse speed (mm/min). Must be > 0.",
            },
            "assist_gas": {
                "type": "string",
                "enum": ["O2", "N2", "Air"],
                "description": "Laser assist gas (default 'O2'). Ignored for other processes.",
            },
        },
        "required": ["process", "thickness_mm", "cut_length_mm", "speed_mm_min"],
    },
)


@register(_gas_consumption_spec, write=False)
async def run_thermalcut_gas_consumption(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("process", "thickness_mm", "cut_length_mm", "speed_mm_min"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "assist_gas" in a:
        kwargs["assist_gas"] = a["assist_gas"]

    result = gas_consumption(
        a["process"], a["thickness_mm"], a["cut_length_mm"], a["speed_mm_min"],
        **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_waterjet_params
# ---------------------------------------------------------------------------

_waterjet_params_spec = ToolSpec(
    name="thermalcut_waterjet_params",
    description=(
        "Compute AWJ orifice/mixing-tube sizing, jet power, standoff distance, "
        "and abrasive loading ratio.\n"
        "\n"
        "Orifice flow: Q = C_d·A·√(2·ΔP/ρ)  (C_d = 0.65)\n"
        "Jet power: P_jet = Q·ΔP\n"
        "Mixing tube default: 3.5 × orifice diameter.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pump_power_kW": {
                "type": "number",
                "description": "Hydraulic pump power (kW). Must be > 0.",
            },
            "orifice_dia_mm": {
                "type": "number",
                "description": "Water orifice diameter (mm). Must be > 0.",
            },
            "mixing_tube_dia_mm": {
                "type": "number",
                "description": "Mixing tube inner diameter (mm). If omitted, 3.5 × orifice.",
            },
            "mixing_tube_length_mm": {
                "type": "number",
                "description": "Mixing tube length (mm). If omitted, 75 × d_mixing.",
            },
            "pressure_MPa": {
                "type": "number",
                "description": "Pump operating pressure (MPa). Default 380 MPa.",
            },
            "abrasive_rate_kg_min": {
                "type": "number",
                "description": "Abrasive feed rate (kg/min). Default 0.45.",
            },
        },
        "required": ["pump_power_kW", "orifice_dia_mm"],
    },
)


@register(_waterjet_params_spec, write=False)
async def run_thermalcut_waterjet_params(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("pump_power_kW", "orifice_dia_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("mixing_tube_dia_mm", "mixing_tube_length_mm",
              "pressure_MPa", "abrasive_rate_kg_min"):
        if k in a:
            kwargs[k] = a[k]

    result = waterjet_params(a["pump_power_kW"], a["orifice_dia_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_part_cost
# ---------------------------------------------------------------------------

_part_cost_spec = ToolSpec(
    name="thermalcut_part_cost",
    description=(
        "Compute the total part cutting cost (USD).\n"
        "\n"
        "Cost = (cut_time + pierce_time) × machine_rate + consumables\n"
        "\n"
        "where:\n"
        "  cut_time  = cut_length / speed\n"
        "  pierce_time = n_pierces × pierce_time_s\n"
        "\n"
        "Default machine rates: laser $65/hr, plasma $45/hr, "
        "oxyfuel $25/hr, waterjet $55/hr.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "process": {
                "type": "string",
                "enum": _VALID_PROCESSES,
                "description": "Cutting process.",
            },
            "cut_length_mm": {
                "type": "number",
                "description": "Total cut length (mm). Must be > 0.",
            },
            "speed_mm_min": {
                "type": "number",
                "description": "Average traverse speed (mm/min). Must be > 0.",
            },
            "n_pierces": {
                "type": "integer",
                "description": "Number of pierce operations. Must be >= 0.",
            },
            "pierce_time_s": {
                "type": "number",
                "description": "Time per pierce (seconds). Must be >= 0.",
            },
            "machine_rate_usd_hr": {
                "type": "number",
                "description": "Machine hourly rate (USD/hr). If omitted, uses process default.",
            },
            "consumables_cost_usd": {
                "type": "number",
                "description": "Consumables cost for the part (USD). Default 0.",
            },
        },
        "required": [
            "process", "cut_length_mm", "speed_mm_min",
            "n_pierces", "pierce_time_s",
        ],
    },
)


@register(_part_cost_spec, write=False)
async def run_thermalcut_part_cost(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("process", "cut_length_mm", "speed_mm_min",
                  "n_pierces", "pierce_time_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "machine_rate_usd_hr" in a:
        kwargs["machine_rate_usd_hr"] = a["machine_rate_usd_hr"]
    if "consumables_cost_usd" in a:
        kwargs["consumables_cost_usd"] = a["consumables_cost_usd"]

    result = part_cost(
        a["process"],
        a["cut_length_mm"],
        a["speed_mm_min"],
        a["n_pierces"],
        a["pierce_time_s"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thermalcut_process_compare
# ---------------------------------------------------------------------------

_process_compare_spec = ToolSpec(
    name="thermalcut_process_compare",
    description=(
        "Side-by-side comparison of laser / plasma / oxyfuel / waterjet for "
        "a given material and thickness.\n"
        "\n"
        "For each applicable process returns:\n"
        "  speed_mm_min, kerf_mm, haz_mm, pierce_time_s, part_cost_usd\n"
        "\n"
        "Oxyfuel is marked non-applicable for non-ferrous materials.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "thickness_mm": {
                "type": "number",
                "description": "Material thickness (mm). Must be > 0.",
            },
            "material": {
                "type": "string",
                "enum": _VALID_MATERIALS,
                "description": "Material key (default 'mild_steel').",
            },
            "cut_length_mm": {
                "type": "number",
                "description": "Hypothetical cut length for cost comparison (mm). Default 1000 mm.",
            },
            "n_pierces": {
                "type": "integer",
                "description": "Number of pierces for cost comparison. Default 4.",
            },
        },
        "required": ["thickness_mm"],
    },
)


@register(_process_compare_spec, write=False)
async def run_thermalcut_process_compare(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("thickness_mm") is None:
        return json.dumps({"ok": False, "reason": "thickness_mm is required"})

    kwargs: dict = {}
    for k in ("material", "cut_length_mm", "n_pierces"):
        if k in a:
            kwargs[k] = a[k]

    result = process_compare(a["thickness_mm"], **kwargs)
    return ok_payload(result)
