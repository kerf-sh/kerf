"""
kerf_cad_core.firesafety.tools — LLM tool wrappers for fire-protection engineering.

Registers nine tools with the Kerf tool registry:

  sprinkler_hydraulic_demand  — NFPA 13 density/area sprinkler demand
  fire_pump_sizing            — NFPA 20 fire pump rated/150%/churn points
  water_supply_adequacy       — available vs required pressure-flow curve
  egress_analysis             — occupant load, exit width, travel limits
  design_fire_tsquared        — t-squared fire growth Q=αt²
  detector_activation_time    — Alpert ceiling-jet + RTI activation
  smoke_control_exhaust       — NFPA 92 atrium plume exhaust
  fire_resistance_heat_transfer — 1-D steady-state heat through rated assembly
  required_fire_rating        — minimum rating by occupancy/height (IBC/NFPA)

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
NFPA 13 (2022) — Standard for the Installation of Sprinkler Systems
NFPA 20 (2022) — Standard for the Installation of Stationary Pumps for Fire Protection
NFPA 92 (2021) — Standard for Smoke Control Systems
NFPA 101 (2021) — Life Safety Code
SFPE Handbook of Fire Protection Engineering, 5th ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.firesafety.fire import (
    sprinkler_hydraulic_demand,
    fire_pump_sizing,
    water_supply_adequacy,
    egress_analysis,
    design_fire_tsquared,
    detector_activation_time,
    smoke_control_exhaust,
    fire_resistance_heat_transfer,
    required_fire_rating,
)


# ---------------------------------------------------------------------------
# Tool: sprinkler_hydraulic_demand
# ---------------------------------------------------------------------------

_sprinkler_hydraulic_demand_spec = ToolSpec(
    name="sprinkler_hydraulic_demand",
    description=(
        "Calculate NFPA 13 density/area sprinkler hydraulic demand.\n"
        "\n"
        "Uses K = Q/√P to relate flow and pressure at each sprinkler, applies the "
        "design density over the most-remote area, adds hose-stream allowance, then "
        "walks back via Hazen-Williams friction to determine the required source pressure.\n"
        "\n"
        "Flags: source pressure > 175 psi (NFPA 13 system limit).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "occupancy_class": {
                "type": "string",
                "enum": [
                    "light_hazard",
                    "ordinary_hazard_group_1",
                    "ordinary_hazard_group_2",
                    "extra_hazard_group_1",
                    "extra_hazard_group_2",
                ],
                "description": "NFPA 13 occupancy class for density/area selection.",
            },
            "k_factor": {
                "type": "number",
                "description": (
                    "Sprinkler K-factor (gpm/psi^0.5). Common: 5.6 (std response), "
                    "8.0, 11.2 (extended coverage), 14.0, 16.8. Must be > 0."
                ),
            },
            "pipe_d_inch": {
                "type": "number",
                "description": "Supply pipe inside diameter (inches). Must be > 0.",
            },
            "pipe_length_ft": {
                "type": "number",
                "description": "Equivalent pipe length from remote area to source (ft). Must be >= 0.",
            },
            "elevation_diff_ft": {
                "type": "number",
                "description": (
                    "Elevation from source to most-remote sprinkler (ft, positive = "
                    "sprinklers above source). Default 0."
                ),
            },
            "density_override": {
                "type": "number",
                "description": "Override design density (gpm/ft²). If omitted, uses NFPA 13 table.",
            },
            "area_override": {
                "type": "number",
                "description": "Override design area (ft²). If omitted, uses NFPA 13 table.",
            },
            "hw_coeff": {
                "type": "number",
                "description": "Hazen-Williams C coefficient (default 120 for sched-40 steel).",
            },
        },
        "required": ["occupancy_class", "k_factor", "pipe_d_inch", "pipe_length_ft"],
    },
)


@register(_sprinkler_hydraulic_demand_spec, write=False)
async def run_sprinkler_hydraulic_demand(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("occupancy_class", "k_factor", "pipe_d_inch", "pipe_length_ft"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("elevation_diff_ft", "density_override", "area_override", "hw_coeff"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = sprinkler_hydraulic_demand(
        a["occupancy_class"], a["k_factor"], a["pipe_d_inch"], a["pipe_length_ft"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: fire_pump_sizing
# ---------------------------------------------------------------------------

_fire_pump_sizing_spec = ToolSpec(
    name="fire_pump_sizing",
    description=(
        "Size a fire pump per NFPA 20.\n"
        "\n"
        "Derives the three mandatory pump curve points:\n"
        "  Rated point   : (rated_flow_gpm, rated_head_psi)\n"
        "  150% flow point: flow = 1.5 × rated, pressure ≥ 65% rated\n"
        "  Churn/shutoff  : flow = 0, pressure ≤ 140% rated\n"
        "\n"
        "Flags: churn > 140% rated, flow < 25 gpm min, pressure < 40 psi typical.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rated_flow_gpm": {
                "type": "number",
                "description": "Rated pump flow (gpm). Must be > 0. NFPA 20 min = 25 gpm.",
            },
            "rated_head_psi": {
                "type": "number",
                "description": "Rated net pressure (psi). Must be > 0.",
            },
        },
        "required": ["rated_flow_gpm", "rated_head_psi"],
    },
)


@register(_fire_pump_sizing_spec, write=False)
async def run_fire_pump_sizing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("rated_flow_gpm", "rated_head_psi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = fire_pump_sizing(a["rated_flow_gpm"], a["rated_head_psi"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: water_supply_adequacy
# ---------------------------------------------------------------------------

_water_supply_adequacy_spec = ToolSpec(
    name="water_supply_adequacy",
    description=(
        "Check available water supply against system demand.\n"
        "\n"
        "Uses the standard hydraulic supply curve "
        "P(Q) = P_static - (P_static - P_residual) × (Q/Q_residual)^1.85 "
        "to find the available pressure at the required flow, then compares "
        "to the required pressure.\n"
        "\n"
        "Flags: INADEQUATE_WATER_SUPPLY when available < required.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "static_pressure_psi": {
                "type": "number",
                "description": "Static (no-flow) supply pressure from hydrant flow test (psi).",
            },
            "residual_pressure_psi": {
                "type": "number",
                "description": "Residual test pressure at hydrant during flow test (psi).",
            },
            "residual_flow_gpm": {
                "type": "number",
                "description": "Flow from test hydrant when residual pressure was recorded (gpm).",
            },
            "required_flow_gpm": {
                "type": "number",
                "description": "System demand flow (gpm) — sprinkler + hose stream.",
            },
            "required_pressure_psi": {
                "type": "number",
                "description": "Minimum pressure required at the supply connection point (psi).",
            },
        },
        "required": [
            "static_pressure_psi",
            "residual_pressure_psi",
            "residual_flow_gpm",
            "required_flow_gpm",
            "required_pressure_psi",
        ],
    },
)


@register(_water_supply_adequacy_spec, write=False)
async def run_water_supply_adequacy(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "static_pressure_psi",
        "residual_pressure_psi",
        "residual_flow_gpm",
        "required_flow_gpm",
        "required_pressure_psi",
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = water_supply_adequacy(
        a["static_pressure_psi"],
        a["residual_pressure_psi"],
        a["residual_flow_gpm"],
        a["required_flow_gpm"],
        a["required_pressure_psi"],
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: egress_analysis
# ---------------------------------------------------------------------------

_egress_analysis_spec = ToolSpec(
    name="egress_analysis",
    description=(
        "Egress analysis per NFPA 101 Life Safety Code.\n"
        "\n"
        "Calculates occupant load from area × occupant-load-factor, checks exit "
        "count and width capacity, verifies travel distance / common path / dead-end "
        "limits, and estimates time-to-egress.\n"
        "\n"
        "Flags: EGRESS_CAPACITY_EXCEEDED, insufficient exits, code limit violations.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "floor_area_ft2": {
                "type": "number",
                "description": "Gross floor area of the space (ft²). Must be > 0.",
            },
            "occupancy_type": {
                "type": "string",
                "description": (
                    "NFPA 101 occupancy type for OLF and limits. Examples: "
                    "'business', 'assembly_concentrated', 'educational', "
                    "'healthcare_sleeping', 'residential', 'storage', 'mercantile_street_floor'."
                ),
            },
            "num_exits": {
                "type": "integer",
                "description": "Number of exits provided. Must be >= 1.",
            },
            "exit_widths_in": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Clear width (inches) of each exit. Length must equal num_exits.",
            },
            "travel_distance_ft": {
                "type": "number",
                "description": "Maximum actual travel distance to nearest exit (ft).",
            },
            "common_path_ft": {
                "type": "number",
                "description": "Maximum common path of travel (ft). Default 0.",
            },
            "dead_end_ft": {
                "type": "number",
                "description": "Maximum dead-end corridor length (ft). Default 0.",
            },
            "exit_component": {
                "type": "string",
                "enum": ["stair", "level"],
                "description": "Exit type: 'stair' (0.3 in/person) or 'level' (0.2 in/person).",
            },
        },
        "required": [
            "floor_area_ft2",
            "occupancy_type",
            "num_exits",
            "exit_widths_in",
            "travel_distance_ft",
        ],
    },
)


@register(_egress_analysis_spec, write=False)
async def run_egress_analysis(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "floor_area_ft2", "occupancy_type", "num_exits",
        "exit_widths_in", "travel_distance_ft",
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("common_path_ft", "dead_end_ft", "exit_component"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = egress_analysis(
        a["floor_area_ft2"],
        a["occupancy_type"],
        a["num_exits"],
        a["exit_widths_in"],
        a["travel_distance_ft"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: design_fire_tsquared
# ---------------------------------------------------------------------------

_design_fire_tsquared_spec = ToolSpec(
    name="design_fire_tsquared",
    description=(
        "t-squared design fire heat-release rate Q = α × t².\n"
        "\n"
        "Growth classes (NFPA 92):\n"
        "  slow      — 1 MW in 600 s   (α = 0.00293 kW/s²)\n"
        "  medium    — 1 MW in 300 s   (α = 0.01172 kW/s²)\n"
        "  fast      — 1 MW in 150 s   (α = 0.04689 kW/s²)\n"
        "  ultra_fast— 1 MW in 75 s    (α = 0.1878 kW/s²)\n"
        "\n"
        "Returns HRR at the specified time and time-to-1-MW.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "time_s": {
                "type": "number",
                "description": "Time from ignition (seconds). Must be >= 0.",
            },
            "growth_class": {
                "type": "string",
                "enum": ["slow", "medium", "fast", "ultra_fast"],
                "description": "t-squared fire growth rate class (default 'medium').",
            },
            "alpha_override": {
                "type": "number",
                "description": "Override α coefficient (kW/s²). Overrides growth_class if provided.",
            },
            "max_hrr_kw": {
                "type": "number",
                "description": "Maximum (capped) HRR in kW. Optional.",
            },
        },
        "required": ["time_s"],
    },
)


@register(_design_fire_tsquared_spec, write=False)
async def run_design_fire_tsquared(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("time_s") is None:
        return json.dumps({"ok": False, "reason": "time_s is required"})

    kwargs: dict = {}
    for opt in ("growth_class", "alpha_override", "max_hrr_kw"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = design_fire_tsquared(a["time_s"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: detector_activation_time
# ---------------------------------------------------------------------------

_detector_activation_time_spec = ToolSpec(
    name="detector_activation_time",
    description=(
        "Sprinkler/detector activation time using Alpert ceiling-jet correlations "
        "and the RTI (Response Time Index) model.\n"
        "\n"
        "Alpert (1972) ceiling-jet temperature and velocity are used to determine "
        "the quasi-steady activation condition, then the RTI ODE analytical solution "
        "gives estimated time-to-activation.\n"
        "\n"
        "RTI values: standard response 80–350 m^0.5·s^0.5; quick response 28–50.\n"
        "\n"
        "Flags: ceiling-jet temp < activation temp; activation time > 5 min.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "hrr_kw": {
                "type": "number",
                "description": "Fire HRR Q (kW) at time of interest. Must be > 0.",
            },
            "ceiling_height_m": {
                "type": "number",
                "description": "Height from fire base to ceiling (m). Must be > 0.",
            },
            "radial_distance_m": {
                "type": "number",
                "description": "Radial distance from fire axis to detector (m). Must be >= 0.",
            },
            "rti": {
                "type": "number",
                "description": "Response Time Index (m^0.5·s^0.5). STD response: 80-350; QR: 28-50.",
            },
            "detector_temp_c": {
                "type": "number",
                "description": "Detector/sprinkler activation temperature (°C). Must be > ambient.",
            },
            "ambient_temp_c": {
                "type": "number",
                "description": "Ambient room temperature (°C). Default 20.",
            },
        },
        "required": [
            "hrr_kw",
            "ceiling_height_m",
            "radial_distance_m",
            "rti",
            "detector_temp_c",
        ],
    },
)


@register(_detector_activation_time_spec, write=False)
async def run_detector_activation_time(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "hrr_kw", "ceiling_height_m", "radial_distance_m", "rti", "detector_temp_c"
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "ambient_temp_c" in a:
        kwargs["ambient_temp_c"] = a["ambient_temp_c"]

    result = detector_activation_time(
        a["hrr_kw"],
        a["ceiling_height_m"],
        a["radial_distance_m"],
        a["rti"],
        a["detector_temp_c"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: smoke_control_exhaust
# ---------------------------------------------------------------------------

_smoke_control_exhaust_spec = ToolSpec(
    name="smoke_control_exhaust",
    description=(
        "Atrium smoke exhaust airflow per NFPA 92 axisymmetric plume model.\n"
        "\n"
        "Computes the plume mass flow rate at the design smoke-layer interface "
        "height using NFPA 92 Eq. A.2 (Heskestad axisymmetric plume), then "
        "converts to required exhaust airflow (cfm and m³/s).\n"
        "\n"
        "Convective fraction assumed 70% per NFPA 92.\n"
        "\n"
        "Flags: smoke-layer height < 1 m; layer < 1/3 of atrium height.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "hrr_kw": {
                "type": "number",
                "description": "Fire HRR Q (kW). Must be > 0.",
            },
            "atrium_height_m": {
                "type": "number",
                "description": "Total atrium height from floor to ceiling (m). Must be > 0.",
            },
            "smoke_layer_height_m": {
                "type": "number",
                "description": (
                    "Design smoke-layer interface height above fire source (m). "
                    "Must be > 0 and < atrium_height_m."
                ),
            },
        },
        "required": ["hrr_kw", "atrium_height_m", "smoke_layer_height_m"],
    },
)


@register(_smoke_control_exhaust_spec, write=False)
async def run_smoke_control_exhaust(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("hrr_kw", "atrium_height_m", "smoke_layer_height_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = smoke_control_exhaust(
        a["hrr_kw"], a["atrium_height_m"], a["smoke_layer_height_m"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: fire_resistance_heat_transfer
# ---------------------------------------------------------------------------

_fire_resistance_heat_transfer_spec = ToolSpec(
    name="fire_resistance_heat_transfer",
    description=(
        "1-D steady-state heat transfer through a fire-rated wall/floor assembly.\n"
        "\n"
        "Models assembly as resistors in series: R = thickness / conductivity for "
        "each layer, plus standard surface resistances (0.13 m²K/W hot side, "
        "0.04 m²K/W cold side).\n"
        "\n"
        "Checks ASTM E119 unexposed-surface temperature limit: ≤ ambient + 139°C.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "assembly_layers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "thickness_mm": {"type": "number"},
                        "conductivity_W_mK": {"type": "number"},
                    },
                    "required": ["name", "thickness_mm", "conductivity_W_mK"],
                },
                "description": (
                    "Ordered list of assembly layers from fire side to ambient side. "
                    "Each layer: {name, thickness_mm, conductivity_W_mK}."
                ),
            },
            "fire_side_temp_c": {
                "type": "number",
                "description": "Fire-side temperature (°C). Default 927 (ASTM E119 @ 60 min).",
            },
            "ambient_temp_c": {
                "type": "number",
                "description": "Ambient side temperature (°C). Default 20.",
            },
        },
        "required": ["assembly_layers"],
    },
)


@register(_fire_resistance_heat_transfer_spec, write=False)
async def run_fire_resistance_heat_transfer(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("assembly_layers") is None:
        return json.dumps({"ok": False, "reason": "assembly_layers is required"})

    kwargs: dict = {}
    for opt in ("fire_side_temp_c", "ambient_temp_c"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = fire_resistance_heat_transfer(a["assembly_layers"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: required_fire_rating
# ---------------------------------------------------------------------------

_required_fire_rating_spec = ToolSpec(
    name="required_fire_rating",
    description=(
        "Minimum fire-resistance rating (hours) by occupancy group and building height.\n"
        "\n"
        "Based on IBC Table 601 simplified to occupancy group + low-rise (≤4 stories) "
        "vs high-rise (>4 stories). Optional 1-hour sprinkler credit per IBC §504.\n"
        "\n"
        "Returns required bearing-wall, non-bearing-wall, and floor/ceiling ratings.\n"
        "\n"
        "Flags: high-rise without sprinklers; sprinkler credit applied.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "occupancy_group": {
                "type": "string",
                "enum": [
                    "assembly", "business", "educational", "healthcare",
                    "industrial", "mercantile", "residential", "storage", "high_hazard",
                ],
                "description": "Occupancy group per IBC/NFPA 101.",
            },
            "building_height_stories": {
                "type": "integer",
                "description": "Number of stories above grade. Must be >= 1.",
            },
            "sprinklered": {
                "type": "boolean",
                "description": "True if building is fully sprinklered per NFPA 13. Default false.",
            },
        },
        "required": ["occupancy_group", "building_height_stories"],
    },
)


@register(_required_fire_rating_spec, write=False)
async def run_required_fire_rating(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("occupancy_group", "building_height_stories"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "sprinklered" in a:
        kwargs["sprinklered"] = a["sprinklered"]

    result = required_fire_rating(
        a["occupancy_group"], a["building_height_stories"], **kwargs
    )
    return ok_payload(result)
