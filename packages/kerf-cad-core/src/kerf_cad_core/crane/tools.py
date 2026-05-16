"""
kerf_cad_core.crane.tools — LLM tool wrappers for crane & hoist mechanism design.

Registers tools with the Kerf tool registry:

  crane_wire_rope_reeving      — rope pull and block efficiency from reeving
  crane_rope_diameter          — required rope diameter from line pull & SF
  crane_sheave_drum_geometry   — minimum sheave and drum PCD from D/d ratio
  crane_drum_length            — drum barrel length and winding capacity
  crane_hoist_motor_power      — required hoist motor power
  crane_hoist_motor_class      — FEM/ISO M-class from duty group + load spectrum
  crane_hoist_brake_torque     — required hoist brake holding torque
  crane_travel_resistance      — travel drive resistance force
  crane_travel_motor_power     — required travel motor power
  crane_jib_load_chart         — jib/boom allowable load vs radius (tipping)
  crane_bridge_wheel_loads     — bridge crane wheel loads and end-carriage reactions
  crane_hook_shank_check       — hook shank stress per DIN 15400
  crane_lifting_lug_check      — pad-eye / lifting lug net-section & shear-out
  crane_duty_class             — FEM duty group A-class and M-class from cycles
  crane_fall_protection_brake  — fall-protection brake sizing and brake-path

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
FEM 1.001 Rules for the Design of Hoisting Appliances (4th ed., 1998)
ISO 4301-1:2016 Cranes — Classification — General
DIN 15400:2012  Lifting hooks
ASME B30.2-2022 Overhead and Gantry Cranes

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.crane.design import (
    wire_rope_reeving,
    rope_diameter,
    sheave_drum_geometry,
    drum_length,
    hoist_motor_power,
    hoist_motor_class,
    hoist_brake_torque,
    travel_resistance,
    travel_motor_power,
    jib_load_chart,
    bridge_wheel_loads,
    hook_shank_check,
    lifting_lug_check,
    crane_duty_class,
    fall_protection_brake,
)


# ---------------------------------------------------------------------------
# Tool: crane_wire_rope_reeving
# ---------------------------------------------------------------------------

_reeving_spec = ToolSpec(
    name="crane_wire_rope_reeving",
    description=(
        "Compute wire-rope line pull (rope tension at the drum) and hook-block "
        "efficiency from reeving geometry.\n"
        "\n"
        "For a system with n_parts lines and per-sheave efficiency η:\n"
        "  η_block = (1 − η^n) / (n × (1 − η))\n"
        "  line_pull = SWL / (n_parts × η_block)\n"
        "\n"
        "Returns line_pull_kN, line_pull_N, eta_block.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "SWL_kN": {
                "type": "number",
                "description": "Safe working load at the hook (kN). Must be > 0.",
            },
            "n_parts": {
                "type": "integer",
                "description": "Number of rope parts / lines in the reeving (≥ 1).",
            },
            "rope_efficiency": {
                "type": "number",
                "description": (
                    "Per-sheave efficiency (default 0.98 for roller bearings). "
                    "Must be in (0, 1]."
                ),
            },
            "reeving_factor": {
                "type": "number",
                "description": (
                    "Override block efficiency directly (0, 1]. "
                    "Use when manufacturer provides the reeving factor."
                ),
            },
        },
        "required": ["SWL_kN", "n_parts"],
    },
)


@register(_reeving_spec, write=False)
async def run_crane_wire_rope_reeving(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("SWL_kN") is None:
        return json.dumps({"ok": False, "reason": "SWL_kN is required"})
    if a.get("n_parts") is None:
        return json.dumps({"ok": False, "reason": "n_parts is required"})

    kwargs: dict = {}
    if "rope_efficiency" in a:
        kwargs["rope_efficiency"] = a["rope_efficiency"]
    if "reeving_factor" in a:
        kwargs["reeving_factor"] = a["reeving_factor"]

    result = wire_rope_reeving(a["SWL_kN"], int(a["n_parts"]), **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_rope_diameter
# ---------------------------------------------------------------------------

_rope_dia_spec = ToolSpec(
    name="crane_rope_diameter",
    description=(
        "Select the required wire-rope nominal diameter from line pull and "
        "safety factor per DIN 15020-1 / FEM 1.001.\n"
        "\n"
        "Picks the smallest standard diameter (6–40 mm) whose minimum "
        "breaking force (MBF) ≥ line_pull × safety_factor.\n"
        "\n"
        "Returns diameter_mm, mbf_kN, actual_sf.\n"
        "Warning ROPE_OVERTENSION if no diameter is sufficient.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "line_pull_kN": {
                "type": "number",
                "description": "Rope tension at the drum (kN). Must be > 0.",
            },
            "safety_factor": {
                "type": "number",
                "description": (
                    "Minimum ratio MBF/line_pull. Default 5.0 "
                    "(FEM M3–M4 standard service)."
                ),
            },
            "grade": {
                "type": "string",
                "enum": ["1570", "1770", "1960"],
                "description": "Rope grade (wire UTS MPa). Default '1770'.",
            },
        },
        "required": ["line_pull_kN"],
    },
)


@register(_rope_dia_spec, write=False)
async def run_crane_rope_diameter(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("line_pull_kN") is None:
        return json.dumps({"ok": False, "reason": "line_pull_kN is required"})

    kwargs: dict = {}
    if "safety_factor" in a:
        kwargs["safety_factor"] = a["safety_factor"]
    if "grade" in a:
        kwargs["grade"] = a["grade"]

    result = rope_diameter(a["line_pull_kN"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_sheave_drum_geometry
# ---------------------------------------------------------------------------

_sheave_drum_spec = ToolSpec(
    name="crane_sheave_drum_geometry",
    description=(
        "Compute minimum sheave and drum pitch-circle diameters from D/d ratio "
        "per FEM 1.001.\n"
        "\n"
        "D/d is the ratio of sheave or drum PCD to rope diameter. Low values "
        "increase rope bending fatigue. FEM minimum ratios depend on mechanism "
        "class (A–F).\n"
        "\n"
        "Returns pcd_sheave_mm, pcd_drum_mm, fem minimum ratios.\n"
        "Warning DD_RATIO_LOW if provided ratio is below FEM minimum.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rope_dia_mm": {
                "type": "number",
                "description": "Nominal rope diameter (mm). Must be > 0.",
            },
            "sheave_dd_ratio": {
                "type": "number",
                "description": "D/d ratio for running sheaves (default 18 for FEM class E).",
            },
            "drum_dd_ratio": {
                "type": "number",
                "description": "D/d ratio for the drum (default 16).",
            },
            "fem_class": {
                "type": "string",
                "enum": ["A", "B", "C", "D", "E", "F"],
                "description": "FEM mechanism class A–F (default 'E' ≈ M5).",
            },
        },
        "required": ["rope_dia_mm"],
    },
)


@register(_sheave_drum_spec, write=False)
async def run_crane_sheave_drum_geometry(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("rope_dia_mm") is None:
        return json.dumps({"ok": False, "reason": "rope_dia_mm is required"})

    kwargs: dict = {}
    if "sheave_dd_ratio" in a:
        kwargs["sheave_dd_ratio"] = a["sheave_dd_ratio"]
    if "drum_dd_ratio" in a:
        kwargs["drum_dd_ratio"] = a["drum_dd_ratio"]
    if "fem_class" in a:
        kwargs["fem_class"] = a["fem_class"]

    result = sheave_drum_geometry(a["rope_dia_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_drum_length
# ---------------------------------------------------------------------------

_drum_length_spec = ToolSpec(
    name="crane_drum_length",
    description=(
        "Compute drum barrel length from rope diameter, reeving, and hoist height.\n"
        "\n"
        "Total rope = hoist_height × n_parts. Drum length = total turns per "
        "layer × groove pitch. Groove pitch = rope_dia × groove_pitch_factor.\n"
        "\n"
        "Returns drum_length_mm, turns_working, groove_pitch_mm.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rope_dia_mm": {
                "type": "number",
                "description": "Nominal rope diameter (mm). Must be > 0.",
            },
            "n_parts": {
                "type": "integer",
                "description": "Number of rope parts in the reeving (≥ 1).",
            },
            "hoist_height_m": {
                "type": "number",
                "description": "Hook travel height (m). Must be > 0.",
            },
            "n_layers": {
                "type": "integer",
                "description": "Number of winding layers (default 1).",
            },
            "groove_pitch_factor": {
                "type": "number",
                "description": (
                    "Groove pitch = rope_dia × factor (default 1.15 for standard grooving)."
                ),
            },
            "dead_turns": {
                "type": "integer",
                "description": "Dead anchor turns not in working range (default 3).",
            },
        },
        "required": ["rope_dia_mm", "n_parts", "hoist_height_m"],
    },
)


@register(_drum_length_spec, write=False)
async def run_crane_drum_length(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("rope_dia_mm", "n_parts", "hoist_height_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "n_layers" in a:
        kwargs["n_layers"] = int(a["n_layers"])
    if "groove_pitch_factor" in a:
        kwargs["groove_pitch_factor"] = a["groove_pitch_factor"]
    if "dead_turns" in a:
        kwargs["dead_turns"] = int(a["dead_turns"])

    result = drum_length(a["rope_dia_mm"], int(a["n_parts"]), a["hoist_height_m"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_hoist_motor_power
# ---------------------------------------------------------------------------

_hoist_power_spec = ToolSpec(
    name="crane_hoist_motor_power",
    description=(
        "Compute required hoist motor power from SWL, rope speed, and efficiency.\n"
        "\n"
        "P = (SWL × g × v) / η_mech × duty_factor\n"
        "\n"
        "Returns motor_power_kW, lift_power_kW.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "SWL_kN": {
                "type": "number",
                "description": "Safe working load at hook (kN). Must be > 0.",
            },
            "hoist_speed_mps": {
                "type": "number",
                "description": "Hook hoisting speed (m/s). Must be > 0.",
            },
            "mechanical_efficiency": {
                "type": "number",
                "description": "Drive train efficiency (default 0.85). Must be in (0, 1].",
            },
            "duty_factor": {
                "type": "number",
                "description": "Acceleration inertia multiplier (default 1.0, typical 1.1–1.3).",
            },
        },
        "required": ["SWL_kN", "hoist_speed_mps"],
    },
)


@register(_hoist_power_spec, write=False)
async def run_crane_hoist_motor_power(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("SWL_kN") is None:
        return json.dumps({"ok": False, "reason": "SWL_kN is required"})
    if a.get("hoist_speed_mps") is None:
        return json.dumps({"ok": False, "reason": "hoist_speed_mps is required"})

    kwargs: dict = {}
    if "mechanical_efficiency" in a:
        kwargs["mechanical_efficiency"] = a["mechanical_efficiency"]
    if "duty_factor" in a:
        kwargs["duty_factor"] = a["duty_factor"]

    result = hoist_motor_power(a["SWL_kN"], a["hoist_speed_mps"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_hoist_motor_class
# ---------------------------------------------------------------------------

_motor_class_spec = ToolSpec(
    name="crane_hoist_motor_class",
    description=(
        "Determine the FEM/ISO M-class for a hoist motor from duty group and "
        "load-spectrum class per FEM 1.001 / ISO 4301-1.\n"
        "\n"
        "Duty group (utilisation class) 1–8 × Load spectrum Q1–Q4 → M1–M8.\n"
        "\n"
        "Returns m_class. Warning OVER_DUTY for M7/M8.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "duty_group": {
                "type": "integer",
                "description": (
                    "Utilisation class 1–8 (U1–U8 in FEM/ISO): "
                    "1=rare intermittent … 8=continuous very heavy."
                ),
            },
            "load_spectrum": {
                "type": "integer",
                "description": (
                    "Load spectrum class: 1=Q1 light, 2=Q2 moderate, "
                    "3=Q3 heavy, 4=Q4 very heavy (always at SWL)."
                ),
            },
        },
        "required": ["duty_group", "load_spectrum"],
    },
)


@register(_motor_class_spec, write=False)
async def run_crane_hoist_motor_class(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("duty_group") is None:
        return json.dumps({"ok": False, "reason": "duty_group is required"})
    if a.get("load_spectrum") is None:
        return json.dumps({"ok": False, "reason": "load_spectrum is required"})

    result = hoist_motor_class(int(a["duty_group"]), int(a["load_spectrum"]))
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_hoist_brake_torque
# ---------------------------------------------------------------------------

_brake_torque_spec = ToolSpec(
    name="crane_hoist_brake_torque",
    description=(
        "Compute the required hoist brake holding torque.\n"
        "\n"
        "Rope tension at drum = SWL / n_parts (ignoring reeving loss → conservative).\n"
        "Drum torque = F_rope × r_drum.\n"
        "Required brake torque = brake_factor × drum_torque.\n"
        "\n"
        "Returns required_brake_Nm, drum_torque_Nm, rope_tension_N.\n"
        "Warning if brake_factor < 1.25 (below FEM minimum).\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "SWL_kN": {
                "type": "number",
                "description": "Safe working load (kN). Must be > 0.",
            },
            "drum_pcd_mm": {
                "type": "number",
                "description": "Drum pitch-circle (winding) diameter (mm). Must be > 0.",
            },
            "n_parts": {
                "type": "integer",
                "description": "Number of rope parts (≥ 1).",
            },
            "brake_factor": {
                "type": "number",
                "description": (
                    "Holding factor ≥ 1.25 per FEM/ASME (default 1.5)."
                ),
            },
        },
        "required": ["SWL_kN", "drum_pcd_mm", "n_parts"],
    },
)


@register(_brake_torque_spec, write=False)
async def run_crane_hoist_brake_torque(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("SWL_kN", "drum_pcd_mm", "n_parts"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "brake_factor" in a:
        kwargs["brake_factor"] = a["brake_factor"]

    result = hoist_brake_torque(a["SWL_kN"], a["drum_pcd_mm"], int(a["n_parts"]), **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_travel_resistance
# ---------------------------------------------------------------------------

_travel_resist_spec = ToolSpec(
    name="crane_travel_resistance",
    description=(
        "Compute crane or trolley travel drive resistance.\n"
        "\n"
        "F_roll = (crane_mass + payload) × g × coeff_rolling\n"
        "F_wind = wind_pressure × frontal_area × 1.3 × coeff_wind\n"
        "F_total = F_roll + F_wind\n"
        "\n"
        "Returns total_force_N, total_force_kN.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "crane_mass_kg": {
                "type": "number",
                "description": "Empty crane/trolley mass (kg). Must be > 0.",
            },
            "payload_kg": {
                "type": "number",
                "description": "Suspended payload (kg). Must be >= 0.",
            },
            "coeff_rolling": {
                "type": "number",
                "description": "Rolling resistance coefficient (default 0.015 for steel on rail).",
            },
            "coeff_wind": {
                "type": "number",
                "description": "Wind load multiplier on wind_pressure (default 0 = neglect).",
            },
            "wind_pressure_Pa": {
                "type": "number",
                "description": "Wind pressure (Pa). Default 250 Pa (FEM storm service).",
            },
            "frontal_area_m2": {
                "type": "number",
                "description": "Frontal area exposed to wind (m²). Default 0.",
            },
        },
        "required": ["crane_mass_kg", "payload_kg"],
    },
)


@register(_travel_resist_spec, write=False)
async def run_crane_travel_resistance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("crane_mass_kg") is None:
        return json.dumps({"ok": False, "reason": "crane_mass_kg is required"})
    if a.get("payload_kg") is None:
        return json.dumps({"ok": False, "reason": "payload_kg is required"})

    kwargs: dict = {}
    for k in ("coeff_rolling", "coeff_wind", "wind_pressure_Pa", "frontal_area_m2"):
        if k in a:
            kwargs[k] = a[k]

    result = travel_resistance(a["crane_mass_kg"], a["payload_kg"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_travel_motor_power
# ---------------------------------------------------------------------------

_travel_power_spec = ToolSpec(
    name="crane_travel_motor_power",
    description=(
        "Compute required travel motor power.\n"
        "\n"
        "P = resistance × speed / efficiency × acceleration_factor\n"
        "\n"
        "Returns motor_power_kW, motor_power_W.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "resistance_N": {
                "type": "number",
                "description": "Total travel resistance (N). Must be > 0.",
            },
            "travel_speed_mps": {
                "type": "number",
                "description": "Travel speed (m/s). Must be > 0.",
            },
            "motor_efficiency": {
                "type": "number",
                "description": "Motor + gearbox efficiency (default 0.85). In (0, 1].",
            },
            "acceleration_factor": {
                "type": "number",
                "description": "Inertia factor (default 1.25 per FEM).",
            },
        },
        "required": ["resistance_N", "travel_speed_mps"],
    },
)


@register(_travel_power_spec, write=False)
async def run_crane_travel_motor_power(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("resistance_N") is None:
        return json.dumps({"ok": False, "reason": "resistance_N is required"})
    if a.get("travel_speed_mps") is None:
        return json.dumps({"ok": False, "reason": "travel_speed_mps is required"})

    kwargs: dict = {}
    if "motor_efficiency" in a:
        kwargs["motor_efficiency"] = a["motor_efficiency"]
    if "acceleration_factor" in a:
        kwargs["acceleration_factor"] = a["acceleration_factor"]

    result = travel_motor_power(a["resistance_N"], a["travel_speed_mps"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_jib_load_chart
# ---------------------------------------------------------------------------

_jib_chart_spec = ToolSpec(
    name="crane_jib_load_chart",
    description=(
        "Compute allowable hook load vs. slew radius for a jib / boom crane "
        "from tipping stability.\n"
        "\n"
        "Restoring moment = counterweight × g × counterweight_radius\n"
        "                 + crane_base × g × base_radius\n"
        "Allowable = (restoring / SF − jib_mass × g × L/2) / (g × radius)\n"
        "\n"
        "Returns allowable_load_kg, allowable_load_kN, structural_allowable_kg.\n"
        "Warning TIPPING if counterweight insufficient.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "slew_radius_m": {
                "type": "number",
                "description": "Working radius from slew axis to hook (m). Must be > 0.",
            },
            "jib_length_m": {
                "type": "number",
                "description": "Jib/boom length (m). Must be > 0.",
            },
            "jib_mass_kg": {
                "type": "number",
                "description": "Jib self-weight (kg). Must be >= 0.",
            },
            "counterweight_kg": {
                "type": "number",
                "description": "Counterweight mass (kg). Must be >= 0.",
            },
            "counterweight_radius_m": {
                "type": "number",
                "description": "Counterweight moment arm from tipping axis (m).",
            },
            "safety_factor": {
                "type": "number",
                "description": "Stability safety factor (default 1.5).",
            },
            "tipping_fraction": {
                "type": "number",
                "description": (
                    "Allowable load as fraction of tipping load for structural "
                    "moment limit (default 0.75)."
                ),
            },
            "crane_base_mass_kg": {
                "type": "number",
                "description": "Crane base / turntable mass (kg, default 0).",
            },
            "base_radius_m": {
                "type": "number",
                "description": "Base mass moment arm (m, default 0).",
            },
        },
        "required": [
            "slew_radius_m", "jib_length_m", "jib_mass_kg",
            "counterweight_kg", "counterweight_radius_m",
        ],
    },
)


@register(_jib_chart_spec, write=False)
async def run_crane_jib_load_chart(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("slew_radius_m", "jib_length_m", "jib_mass_kg",
                  "counterweight_kg", "counterweight_radius_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("safety_factor", "tipping_fraction", "crane_base_mass_kg", "base_radius_m"):
        if k in a:
            kwargs[k] = a[k]

    result = jib_load_chart(
        a["slew_radius_m"],
        a["jib_length_m"],
        a["jib_mass_kg"],
        a["counterweight_kg"],
        a["counterweight_radius_m"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_bridge_wheel_loads
# ---------------------------------------------------------------------------

_bridge_wheel_spec = ToolSpec(
    name="crane_bridge_wheel_loads",
    description=(
        "Compute bridge crane wheel loads and end-carriage reactions.\n"
        "\n"
        "Simply-supported beam model:\n"
        "  Bridge mass split equally. Crab+payload distributed by moment.\n"
        "  Wheel load = end_reaction × dynamic_factor / n_wheels_per_end.\n"
        "\n"
        "Returns left_wheel_load_kN, right_wheel_load_kN, and reactions.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "crane_span_m": {
                "type": "number",
                "description": "Rail-to-rail span (m). Must be > 0.",
            },
            "bridge_mass_kg": {
                "type": "number",
                "description": "Bridge girder self-mass (kg). Must be > 0.",
            },
            "crab_mass_kg": {
                "type": "number",
                "description": "Crab/trolley mass (kg). Must be >= 0.",
            },
            "payload_kg": {
                "type": "number",
                "description": "Payload mass (kg). Must be >= 0.",
            },
            "crab_x_m": {
                "type": "number",
                "description": "Crab position from left rail (m). Must be in [0, span].",
            },
            "n_wheels_per_end": {
                "type": "integer",
                "description": "Wheels per end carriage (default 2).",
            },
            "dynamic_factor": {
                "type": "number",
                "description": "Dynamic amplification factor (default 1.15 — FEM HC2).",
            },
        },
        "required": ["crane_span_m", "bridge_mass_kg", "crab_mass_kg",
                     "payload_kg", "crab_x_m"],
    },
)


@register(_bridge_wheel_spec, write=False)
async def run_crane_bridge_wheel_loads(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("crane_span_m", "bridge_mass_kg", "crab_mass_kg",
                  "payload_kg", "crab_x_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "n_wheels_per_end" in a:
        kwargs["n_wheels_per_end"] = int(a["n_wheels_per_end"])
    if "dynamic_factor" in a:
        kwargs["dynamic_factor"] = a["dynamic_factor"]

    result = bridge_wheel_loads(
        a["crane_span_m"],
        a["bridge_mass_kg"],
        a["crab_mass_kg"],
        a["payload_kg"],
        a["crab_x_m"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_hook_shank_check
# ---------------------------------------------------------------------------

_hook_shank_spec = ToolSpec(
    name="crane_hook_shank_check",
    description=(
        "Hook shank tensile stress check per DIN 15400.\n"
        "\n"
        "Critical section: ISO metric thread minor (root) diameter.\n"
        "  d_minor = shank_dia - 0.9743 × pitch\n"
        "  A_root = π/4 × d_minor²\n"
        "  σ = SWL / A_root\n"
        "\n"
        "Returns tension_stress_MPa, allowable_MPa, utilisation, pass_shank.\n"
        "Warning SHANK_OVERSTRESS if utilisation > 1.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "SWL_kN": {
                "type": "number",
                "description": "Safe working load (kN). Must be > 0.",
            },
            "shank_diameter_mm": {
                "type": "number",
                "description": "Nominal thread major diameter (mm).",
            },
            "thread_pitch_mm": {
                "type": "number",
                "description": "Thread pitch (mm). Must be > 0.",
            },
            "material": {
                "type": "string",
                "enum": ["grade_P", "grade_S", "grade_T", "S235", "S355", "42CrMo4"],
                "description": (
                    "Hook material: 'grade_P' (Fy 355 MPa), 'grade_S' (490 MPa), "
                    "'grade_T' (590 MPa), '42CrMo4' (700 MPa). Default 'grade_P'."
                ),
            },
            "design_factor": {
                "type": "number",
                "description": "Design factor on yield (default 4.0 per DIN 15400).",
            },
        },
        "required": ["SWL_kN", "shank_diameter_mm", "thread_pitch_mm"],
    },
)


@register(_hook_shank_spec, write=False)
async def run_crane_hook_shank_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("SWL_kN", "shank_diameter_mm", "thread_pitch_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "material" in a:
        kwargs["material"] = a["material"]
    if "design_factor" in a:
        kwargs["design_factor"] = a["design_factor"]

    result = hook_shank_check(a["SWL_kN"], a["shank_diameter_mm"], a["thread_pitch_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_lifting_lug_check
# ---------------------------------------------------------------------------

_lug_check_spec = ToolSpec(
    name="crane_lifting_lug_check",
    description=(
        "Pad-eye / lifting lug strength check per DIN 15400 / EN 1993 principles.\n"
        "\n"
        "Checks net-section tension, bearing on pin hole, and double shear-out.\n"
        "\n"
        "Returns stresses, allowables, pass/fail flags, gouverning_utilisation.\n"
        "Warning WLL_EXCEEDED if any utilisation > 1.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "load_kN": {
                "type": "number",
                "description": "Applied load (kN). Must be > 0.",
            },
            "plate_thickness_mm": {
                "type": "number",
                "description": "Lug plate thickness (mm). Must be > 0.",
            },
            "hole_diameter_mm": {
                "type": "number",
                "description": "Pin-hole diameter (mm). Must be < lug_width_mm.",
            },
            "lug_width_mm": {
                "type": "number",
                "description": "Width of lug plate at hole section (mm). Must be > hole_dia.",
            },
            "Fy_MPa": {
                "type": "number",
                "description": "Plate yield strength (MPa, default 350).",
            },
            "Fu_MPa": {
                "type": "number",
                "description": "Plate UTS (MPa, default 480).",
            },
            "design_factor": {
                "type": "number",
                "description": "Design factor (default 3.0).",
            },
        },
        "required": ["load_kN", "plate_thickness_mm", "hole_diameter_mm", "lug_width_mm"],
    },
)


@register(_lug_check_spec, write=False)
async def run_crane_lifting_lug_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("load_kN", "plate_thickness_mm", "hole_diameter_mm", "lug_width_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("Fy_MPa", "Fu_MPa", "design_factor"):
        if k in a:
            kwargs[k] = a[k]

    result = lifting_lug_check(
        a["load_kN"],
        a["plate_thickness_mm"],
        a["hole_diameter_mm"],
        a["lug_width_mm"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_duty_class
# ---------------------------------------------------------------------------

_duty_class_spec = ToolSpec(
    name="crane_duty_class",
    description=(
        "Determine FEM duty group (A1–A8) and ISO M-class (M1–M8) from total "
        "hoisting cycles and load-spectrum class per FEM 1.001.\n"
        "\n"
        "Total cycles thresholds: A1≤3200, A2≤6300, A3≤12500, A4≤25000, "
        "A5≤50000, A6≤100000, A7≤200000, A8>200000.\n"
        "Load spectrum: 1=Q1 light … 4=Q4 very heavy.\n"
        "\n"
        "Returns duty_group, m_class. Warning OVER_DUTY for M7/M8.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "total_cycles": {
                "type": "integer",
                "description": "Total expected hoisting cycles over crane service life.",
            },
            "load_spectrum_class": {
                "type": "integer",
                "description": (
                    "Load spectrum class: 1=Q1 light, 2=Q2 moderate, "
                    "3=Q3 heavy, 4=Q4 very heavy."
                ),
            },
            "hours_per_year": {
                "type": "number",
                "description": "Operating hours per year (default 2000).",
            },
        },
        "required": ["total_cycles", "load_spectrum_class"],
    },
)


@register(_duty_class_spec, write=False)
async def run_crane_duty_class(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("total_cycles") is None:
        return json.dumps({"ok": False, "reason": "total_cycles is required"})
    if a.get("load_spectrum_class") is None:
        return json.dumps({"ok": False, "reason": "load_spectrum_class is required"})

    kwargs: dict = {}
    if "hours_per_year" in a:
        kwargs["hours_per_year"] = a["hours_per_year"]

    result = crane_duty_class(int(a["total_cycles"]), int(a["load_spectrum_class"]), **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: crane_fall_protection_brake
# ---------------------------------------------------------------------------

_fall_brake_spec = ToolSpec(
    name="crane_fall_protection_brake",
    description=(
        "Size the fall-protection / anti-runaway brake for a hoist.\n"
        "\n"
        "Trigger speed = rated_speed × governor_factor.\n"
        "Required brake torque = load torque + inertia torque (at 1g deceleration).\n"
        "Brake path = v_trigger² / (2g).\n"
        "\n"
        "Returns required_brake_Nm, brake_path_m, trigger_speed_mps.\n"
        "Warning if brake_path > 0.5 m.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "SWL_kN": {
                "type": "number",
                "description": "Safe working load (kN). Must be > 0.",
            },
            "hoist_speed_mps": {
                "type": "number",
                "description": "Rated hoist speed (m/s). Must be > 0.",
            },
            "governor_speed_factor": {
                "type": "number",
                "description": (
                    "Governor trigger speed as multiple of rated speed "
                    "(typical 1.2–1.4). Must be > 1.0."
                ),
            },
            "drum_inertia_kgm2": {
                "type": "number",
                "description": "Drum rotational inertia (kg·m²). Must be >= 0.",
            },
            "drum_radius_m": {
                "type": "number",
                "description": "Drum winding radius (m). Must be > 0.",
            },
        },
        "required": [
            "SWL_kN", "hoist_speed_mps", "governor_speed_factor",
            "drum_inertia_kgm2", "drum_radius_m",
        ],
    },
)


@register(_fall_brake_spec, write=False)
async def run_crane_fall_protection_brake(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("SWL_kN", "hoist_speed_mps", "governor_speed_factor",
                  "drum_inertia_kgm2", "drum_radius_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = fall_protection_brake(
        a["SWL_kN"],
        a["hoist_speed_mps"],
        a["governor_speed_factor"],
        a["drum_inertia_kgm2"],
        a["drum_radius_m"],
    )
    return ok_payload(result)
