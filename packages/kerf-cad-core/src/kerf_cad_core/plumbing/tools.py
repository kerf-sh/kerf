"""
kerf_cad_core.plumbing.tools — LLM tool wrappers for building plumbing engineering.

Registers eleven tools with the Kerf tool registry:

  plumbing_hunter_demand       — fixture units → design GPM (Hunter curve)
  plumbing_size_supply_pipe    — supply pipe sizing with pressure budget
  plumbing_dfu_drain_size      — DFU → drain/branch/stack NPS (IPC tables)
  plumbing_vent_size           — vent pipe sizing by DFU + developed length
  plumbing_trap_arm_slope      — trap-arm length and slope compliance
  plumbing_drain_slope_manning — drain slope full/half-flow capacity (Manning)
  plumbing_hot_water_heater    — storage water heater sizing (ASHRAE)
  plumbing_hw_recirc_loop      — hot-water recirculation loop sizing
  plumbing_storm_drain_leader  — roof storm drain and leader sizing
  plumbing_water_hammer_arrestor — fixture units → PDI WHA size
  plumbing_expansion_tank      — closed water-heater expansion tank sizing

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
IPC (2021) — International Plumbing Code
Hunter, R.B. (1940) — Methods of Estimating Loads in Plumbing Systems (BMS 65)
ASHRAE Handbook — HVAC Applications (2019), Chapter 50
PDI WH-201 — Water Hammer Arrestor Sizing Guide

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.plumbing.design import (
    hunter_demand_gpm,
    size_supply_pipe,
    dfu_to_drain_size,
    vent_size,
    trap_arm_slope,
    drain_slope_manning,
    hot_water_heater_size,
    hw_recirculation_loop,
    storm_drain_leader,
    water_hammer_arrestor,
    expansion_tank_heater,
)


# ---------------------------------------------------------------------------
# Tool: plumbing_hunter_demand
# ---------------------------------------------------------------------------

_hunter_demand_spec = ToolSpec(
    name="plumbing_hunter_demand",
    description=(
        "Convert total supply fixture units (WSFU) to design demand flow (GPM) "
        "using the Hunter probability curve (BMS 65, IPC Appendix E).\n"
        "\n"
        "Two system types:\n"
        "  'flush_tank'  — gravity flush tanks (residential/light commercial)\n"
        "  'flush_valve' — flushometer water closets/urinals (higher peak demand)\n"
        "\n"
        "Common fixture unit values (WSFU): lavatory=1, shower=2, bathtub=2, "
        "water_closet_FT=3, water_closet_FV=6, kitchen_sink=2, hose_bib=3.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fixture_units": {
                "type": "number",
                "description": "Total supply fixture units (WSFU) for the system. Must be > 0.",
            },
            "system_type": {
                "type": "string",
                "enum": ["flush_tank", "flush_valve"],
                "description": (
                    "'flush_tank' (default, residential) or 'flush_valve' (commercial flushometers)."
                ),
            },
        },
        "required": ["fixture_units"],
    },
)


@register(_hunter_demand_spec, write=False)
async def run_plumbing_hunter_demand(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("fixture_units") is None:
        return json.dumps({"ok": False, "reason": "fixture_units is required"})

    kwargs: dict = {}
    if "system_type" in a:
        kwargs["system_type"] = a["system_type"]

    result = hunter_demand_gpm(a["fixture_units"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_size_supply_pipe
# ---------------------------------------------------------------------------

_size_supply_pipe_spec = ToolSpec(
    name="plumbing_size_supply_pipe",
    description=(
        "Select the minimum NPS for a cold-water supply pipe given demand flow "
        "and available pressure budget.\n"
        "\n"
        "Pressure budget:\n"
        "  ΔP_friction ≤ P_static − P_elevation − P_meter − P_residual\n"
        "\n"
        "Uses Hazen-Williams (C=150 for copper/plastic, C=120 for galvanized). "
        "Also enforces IPC §604.3 velocity limit (default 8 ft/s).\n"
        "\n"
        "Flags: under-pressure at fixture / pipe velocity exceeded.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "demand_gpm": {
                "type": "number",
                "description": "Design flow demand at the fixture or branch (gpm). Must be > 0.",
            },
            "available_pressure_psi": {
                "type": "number",
                "description": "Static supply pressure at the meter or main (psi). Must be > 0.",
            },
            "pipe_length_ft": {
                "type": "number",
                "description": "Developed pipe length including fittings equivalent length (ft). Must be > 0.",
            },
            "elevation_diff_ft": {
                "type": "number",
                "description": (
                    "Elevation from supply main to fixture (ft, positive = fixture above main). "
                    "0.433 psi deducted per foot. Default 0."
                ),
            },
            "meter_loss_psi": {
                "type": "number",
                "description": "Pressure loss through the water meter at demand flow (psi). Default 0.",
            },
            "residual_pressure_psi": {
                "type": "number",
                "description": (
                    "Minimum required residual pressure at the fixture (psi). "
                    "IPC §604.3: 8 psi most fixtures; 20 psi flush valves. Default 8."
                ),
            },
            "material": {
                "type": "string",
                "enum": ["copper_l", "cpvc", "pex", "galvanized", "cast_iron"],
                "description": "Pipe material (default 'copper_l'). Sets Hazen-Williams C.",
            },
            "velocity_limit_fps": {
                "type": "number",
                "description": "Maximum allowable velocity (ft/s). Default 8.0 (IPC §604.3).",
            },
        },
        "required": ["demand_gpm", "available_pressure_psi", "pipe_length_ft"],
    },
)


@register(_size_supply_pipe_spec, write=False)
async def run_plumbing_size_supply_pipe(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("demand_gpm", "available_pressure_psi", "pipe_length_ft"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("elevation_diff_ft", "meter_loss_psi", "residual_pressure_psi",
                "material", "velocity_limit_fps"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = size_supply_pipe(a["demand_gpm"], a["available_pressure_psi"], a["pipe_length_ft"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_dfu_drain_size
# ---------------------------------------------------------------------------

_dfu_drain_size_spec = ToolSpec(
    name="plumbing_dfu_drain_size",
    description=(
        "Select the minimum drainage pipe NPS for a given DFU load per IPC "
        "Table 710.1.\n"
        "\n"
        "Three pipe contexts:\n"
        "  'horizontal_branch' — individual fixture branch/horizontal drain\n"
        "  'building_drain'    — building drain or sanitary sewer\n"
        "  'stack'             — soil/waste stack (vertical)\n"
        "\n"
        "Common DFU values: lavatory=1, shower=2, bathtub=2, water_closet=4, "
        "kitchen_sink=2, clothes_washer=3, urinal_FV=4.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dfu": {
                "type": "integer",
                "description": "Total drainage fixture units to be served. Must be >= 1.",
            },
            "pipe_type": {
                "type": "string",
                "enum": ["horizontal_branch", "building_drain", "stack"],
                "description": (
                    "Pipe context: 'horizontal_branch' (default), 'building_drain', or 'stack'."
                ),
            },
        },
        "required": ["dfu"],
    },
)


@register(_dfu_drain_size_spec, write=False)
async def run_plumbing_dfu_drain_size(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("dfu") is None:
        return json.dumps({"ok": False, "reason": "dfu is required"})

    kwargs: dict = {}
    if "pipe_type" in a:
        kwargs["pipe_type"] = a["pipe_type"]

    result = dfu_to_drain_size(a["dfu"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_vent_size
# ---------------------------------------------------------------------------

_vent_size_spec = ToolSpec(
    name="plumbing_vent_size",
    description=(
        "Select the minimum vent pipe NPS per IPC Table 906.2, based on the "
        "DFU load and developed vent length.\n"
        "\n"
        "Both the DFU served and the developed length from trap to terminal "
        "(or vent stack connection) must be satisfied simultaneously.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "dfu_served": {
                "type": "integer",
                "description": "Drainage fixture units served by this vent. Must be >= 1.",
            },
            "developed_length_ft": {
                "type": "number",
                "description": (
                    "Developed length of vent run from trap to terminal or vent stack (ft). "
                    "Must be > 0."
                ),
            },
        },
        "required": ["dfu_served", "developed_length_ft"],
    },
)


@register(_vent_size_spec, write=False)
async def run_plumbing_vent_size(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("dfu_served", "developed_length_ft"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = vent_size(a["dfu_served"], a["developed_length_ft"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_trap_arm_slope
# ---------------------------------------------------------------------------

_trap_arm_slope_spec = ToolSpec(
    name="plumbing_trap_arm_slope",
    description=(
        "Check trap-arm length and slope compliance per IPC §1002.1.\n"
        "\n"
        "IPC limits:\n"
        "  - Maximum trap arm length by pipe size (IPC Table 1002.1)\n"
        "  - Slope: 1/8\" to 1/2\" per foot; > 1/2\"/ft risks siphoning the trap seal\n"
        "\n"
        "Flags: arm too long / slope out of range.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "trap_arm_length_ft": {
                "type": "number",
                "description": "Actual trap arm length from trap outlet to vent (ft). Must be > 0.",
            },
            "trap_size_nps": {
                "type": "string",
                "description": (
                    "Nominal trap/trap-arm pipe size. "
                    "Supported: '1-1/4', '1-1/2', '2', '3', '4'."
                ),
            },
            "slope_in_per_ft": {
                "type": "number",
                "description": "Trap arm slope (inches drop per foot of run). Default 0.25.",
            },
        },
        "required": ["trap_arm_length_ft", "trap_size_nps"],
    },
)


@register(_trap_arm_slope_spec, write=False)
async def run_plumbing_trap_arm_slope(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("trap_arm_length_ft", "trap_size_nps"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "slope_in_per_ft" in a:
        kwargs["slope_in_per_ft"] = a["slope_in_per_ft"]

    result = trap_arm_slope(a["trap_arm_length_ft"], a["trap_size_nps"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_drain_slope_manning
# ---------------------------------------------------------------------------

_drain_slope_manning_spec = ToolSpec(
    name="plumbing_drain_slope_manning",
    description=(
        "Compute full-flow and half-flow drain capacity using Manning's equation.\n"
        "\n"
        "Manning: Q = (1.486/n) × A × R^(2/3) × S^(1/2)\n"
        "For circular pipe: R = d/4 (full flow), R = d/4 (half flow, same as full).\n"
        "\n"
        "IPC §704.1 minimum slope: 1/4\"/ft for pipes ≤ 3\"; 1/8\"/ft for ≥ 4\".\n"
        "\n"
        "Flags: slope below IPC minimum.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "pipe_nps": {
                "type": "string",
                "description": "Nominal pipe size. Supported: '1-1/4' through '12'.",
            },
            "slope_in_per_ft": {
                "type": "number",
                "description": "Drain slope (inches drop per foot of run). Must be > 0.",
            },
            "n_manning": {
                "type": "number",
                "description": (
                    "Manning roughness coefficient. Default 0.013 (PVC/ABS DWV). "
                    "Use 0.015 for cast iron, 0.012 for smooth plastic."
                ),
            },
        },
        "required": ["pipe_nps", "slope_in_per_ft"],
    },
)


@register(_drain_slope_manning_spec, write=False)
async def run_plumbing_drain_slope_manning(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("pipe_nps", "slope_in_per_ft"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "n_manning" in a:
        kwargs["n_manning"] = a["n_manning"]

    result = drain_slope_manning(a["pipe_nps"], a["slope_in_per_ft"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_hot_water_heater
# ---------------------------------------------------------------------------

_hot_water_heater_spec = ToolSpec(
    name="plumbing_hot_water_heater",
    description=(
        "Size a storage water heater using ASHRAE Applications Chapter 50 "
        "occupancy-based daily demand and peak-hour fractions.\n"
        "\n"
        "Occupancy types: 'apartment', 'dormitory', 'motel', 'hotel', 'office', "
        "'restaurant', 'school_elem', 'school_high', 'hospital'.\n"
        "\n"
        "Returns peak hourly demand, recovery rate, required BTU/hr, and "
        "recommended storage volume.\n"
        "\n"
        "Flags: supply temperature out of safe range (< 120°F Legionella risk; "
        "> 140°F scald risk).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "occupancy_type": {
                "type": "string",
                "enum": [
                    "apartment", "dormitory", "motel", "hotel", "office",
                    "restaurant", "school_elem", "school_high", "hospital",
                ],
                "description": "ASHRAE Chapter 50 occupancy type for demand estimation.",
            },
            "num_units": {
                "type": "number",
                "description": (
                    "Number of units/rooms/persons/seats as applicable. Must be > 0."
                ),
            },
            "inlet_temp_f": {
                "type": "number",
                "description": "Cold water supply temperature (°F). Default 55.",
            },
            "supply_temp_f": {
                "type": "number",
                "description": "Hot-water supply temperature (°F). Default 120.",
            },
            "recovery_efficiency": {
                "type": "number",
                "description": "Heater thermal efficiency (0–1). Default 0.80.",
            },
            "fuel_btu_hr": {
                "type": "number",
                "description": (
                    "Heater fuel input rate (BTU/hr). If omitted, sized to meet "
                    "peak demand automatically."
                ),
            },
        },
        "required": ["occupancy_type", "num_units"],
    },
)


@register(_hot_water_heater_spec, write=False)
async def run_plumbing_hot_water_heater(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("occupancy_type", "num_units"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("inlet_temp_f", "supply_temp_f", "recovery_efficiency", "fuel_btu_hr"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = hot_water_heater_size(a["occupancy_type"], a["num_units"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_hw_recirc_loop
# ---------------------------------------------------------------------------

_hw_recirc_loop_spec = ToolSpec(
    name="plumbing_hw_recirc_loop",
    description=(
        "Size a hot-water recirculation loop: minimum pump flow, heat loss, "
        "and pump head (ASHRAE Applications §50.6).\n"
        "\n"
        "The recirculation flow compensates for pipe heat loss so that hot "
        "water is instantly available at fixtures (ΔT_drop = 10°F criterion).\n"
        "\n"
        "Flags: high recirculation flow (poor insulation), uninsulated pipe.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "loop_length_ft": {
                "type": "number",
                "description": "Total developed length of hot-water distribution loop (ft). Must be > 0.",
            },
            "pipe_nps": {
                "type": "string",
                "description": (
                    "Hot-water supply pipe NPS (copper type L). "
                    "Supported: '3/8', '1/2', '3/4', '1', '1-1/4', '1-1/2', '2', '2-1/2', '3', '4', '6'."
                ),
            },
            "supply_temp_f": {
                "type": "number",
                "description": "Hot-water supply temperature (°F). Default 140.",
            },
            "ambient_temp_f": {
                "type": "number",
                "description": "Ambient temperature around pipes (°F). Default 70.",
            },
            "insulation_r_value": {
                "type": "number",
                "description": (
                    "Pipe insulation R-value (hr·ft²·°F/BTU). "
                    "Default 4.0 (approx. 1\" fiberglass on 1\" pipe). "
                    "Use 0 for uninsulated pipe."
                ),
            },
        },
        "required": ["loop_length_ft", "pipe_nps"],
    },
)


@register(_hw_recirc_loop_spec, write=False)
async def run_plumbing_hw_recirc_loop(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("loop_length_ft", "pipe_nps"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("supply_temp_f", "ambient_temp_f", "insulation_r_value"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = hw_recirculation_loop(a["loop_length_ft"], a["pipe_nps"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_storm_drain_leader
# ---------------------------------------------------------------------------

_storm_drain_leader_spec = ToolSpec(
    name="plumbing_storm_drain_leader",
    description=(
        "Size roof storm-drain leaders and horizontal storm drains from "
        "rainfall intensity × roof area (IPC Tables 1106.2/1106.3).\n"
        "\n"
        "Design flow: Q (gpm) = roof_area_ft² × rainfall_in_hr / 96.23.\n"
        "Use 100-year storm intensity for the project location.\n"
        "\n"
        "Flags: design flow exceeds largest standard leader size.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "roof_area_ft2": {
                "type": "number",
                "description": "Horizontal roof area draining to this leader (ft²). Must be > 0.",
            },
            "rainfall_rate_in_hr": {
                "type": "number",
                "description": "Design rainfall rate (in/hr, 100-year storm). Must be > 0.",
            },
            "leader_type": {
                "type": "string",
                "enum": ["vertical", "horizontal"],
                "description": (
                    "'vertical' (default) — vertical roof leader/downspout; "
                    "'horizontal' — horizontal storm drain."
                ),
            },
        },
        "required": ["roof_area_ft2", "rainfall_rate_in_hr"],
    },
)


@register(_storm_drain_leader_spec, write=False)
async def run_plumbing_storm_drain_leader(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("roof_area_ft2", "rainfall_rate_in_hr"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "leader_type" in a:
        kwargs["leader_type"] = a["leader_type"]

    result = storm_drain_leader(a["roof_area_ft2"], a["rainfall_rate_in_hr"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_water_hammer_arrestor
# ---------------------------------------------------------------------------

_water_hammer_arrestor_spec = ToolSpec(
    name="plumbing_water_hammer_arrestor",
    description=(
        "Select a water hammer arrestor (WHA) PDI size letter per PDI WH-201.\n"
        "\n"
        "PDI sizes A–F correspond to fixture unit ranges on the branch:\n"
        "  A: 1–11 FU   B: 12–32   C: 33–60   D: 61–112   E: 113–154   F: 155–329\n"
        "  > 329 FU: multiple Size F units required.\n"
        "\n"
        "Install at each branch serving quick-closing valves (solenoid, "
        "washing machines, dishwashers, flush valves).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fixture_units": {
                "type": "integer",
                "description": "Total supply fixture units on the branch to be protected. Must be >= 1.",
            },
            "location": {
                "type": "string",
                "description": "Descriptive location label (informational). Default 'supply_branch'.",
            },
        },
        "required": ["fixture_units"],
    },
)


@register(_water_hammer_arrestor_spec, write=False)
async def run_plumbing_water_hammer_arrestor(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("fixture_units") is None:
        return json.dumps({"ok": False, "reason": "fixture_units is required"})

    kwargs: dict = {}
    if "location" in a:
        kwargs["location"] = a["location"]

    result = water_hammer_arrestor(a["fixture_units"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: plumbing_expansion_tank
# ---------------------------------------------------------------------------

_expansion_tank_spec = ToolSpec(
    name="plumbing_expansion_tank",
    description=(
        "Size a diaphragm-type expansion tank for a closed water-heater system "
        "(ASHRAE Applications §50.7 / ASME A112.4.3M).\n"
        "\n"
        "Sizing equation:\n"
        "  V_tank = V_sys × (v_hot/v_cold − 1) / (1 − P_fill/P_max)\n"
        "\n"
        "where v_hot, v_cold are specific volumes of water at supply and fill "
        "temperatures, and pressures are absolute (psia).\n"
        "\n"
        "Flags: supply temperature out of safe range; acceptance volume anomalies.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "system_water_volume_gal": {
                "type": "number",
                "description": (
                    "Total system water volume (gallons): heater tank + distribution piping. "
                    "Must be > 0."
                ),
            },
            "supply_temp_f": {
                "type": "number",
                "description": "Hot-water supply temperature (°F). Default 120.",
            },
            "cold_fill_temp_f": {
                "type": "number",
                "description": "Cold-water fill temperature (°F). Default 40.",
            },
            "system_pressure_psi": {
                "type": "number",
                "description": "Static fill pressure at the expansion tank (psig). Default 80.",
            },
            "relief_valve_psi": {
                "type": "number",
                "description": "T&P relief valve setting (psig). Default 150.",
            },
        },
        "required": ["system_water_volume_gal"],
    },
)


@register(_expansion_tank_spec, write=False)
async def run_plumbing_expansion_tank(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("system_water_volume_gal") is None:
        return json.dumps({"ok": False, "reason": "system_water_volume_gal is required"})

    kwargs: dict = {}
    for opt in ("supply_temp_f", "cold_fill_temp_f", "system_pressure_psi", "relief_valve_psi"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = expansion_tank_heater(a["system_water_volume_gal"], **kwargs)
    return ok_payload(result)
