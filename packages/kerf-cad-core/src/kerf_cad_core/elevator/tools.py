"""
kerf_cad_core.elevator.tools — LLM tool wrappers for vertical-transportation
engineering.

Registers seven tools with the Kerf tool registry:

  elevator_traction_lift      — roping, counterweight, traction ratio, rope/sheave
  elevator_hydraulic_lift     — jack force, pump flow, working pressure
  elevator_motor_power        — balanced-load motor power, duty derating
  elevator_kinematics         — S-curve acceleration/jerk, floor-to-floor time
  elevator_traffic_analysis   — CIBSE RTT, interval, handling capacity
  elevator_buffer_stroke      — EN 81-1 buffer stroke, governor trip speed
  elevator_escalator          — escalator/moving-walk capacity and power

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
CIBSE Guide D: Transportation Systems in Buildings, 4th ed.
EN 81-1:1998+A3:2009 — Safety rules for electric traction lifts
EN 81-2:1998+A3:2009 — Safety rules for hydraulic lifts
EN 115-1:2017 — Safety of escalators and moving walks

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.elevator.design import (
    traction_lift,
    hydraulic_lift,
    motor_power,
    kinematics,
    traffic_analysis,
    buffer_stroke,
    escalator,
)


# ---------------------------------------------------------------------------
# Tool: elevator_traction_lift
# ---------------------------------------------------------------------------

_traction_lift_spec = ToolSpec(
    name="elevator_traction_lift",
    description=(
        "Analyse a traction lift roping configuration.\n"
        "\n"
        "Computes:\n"
        "  • Counterweight mass (car + balance% × rated_load)\n"
        "  • Rope tensions on car side and counterweight side\n"
        "  • Traction ratio T1/T2 (full load ascending and empty car ascending)\n"
        "  • Traction limit e^(μ_eff × α) per EN 81-1 §9.3\n"
        "  • Traction adequacy flags (warnings if traction fails)\n"
        "  • Recommended rope count and minimum sheave D/d ratio\n"
        "  • Counterweight overbalance (kg above 50% balance)\n"
        "\n"
        "Supports 1:1 and 2:1 roping; V-groove and semicircular groove traction.\n"
        "\n"
        "Warnings: inadequate traction (full load / empty), D/d below EN 81-1 §9.7,\n"
        "n_ropes below minimum, balance outside 40–55% range.\n"
        "\n"
        "References: EN 81-1 §9.2/§9.3/§9.7, CIBSE Guide D §3.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rated_load_kg": {
                "type": "number",
                "description": "Rated payload (kg). Must be > 0.",
            },
            "car_mass_kg": {
                "type": "number",
                "description": "Empty car mass (kg). Must be > 0.",
            },
            "rated_speed_m_s": {
                "type": "number",
                "description": "Rated car speed (m/s). Must be > 0.",
            },
            "roping": {
                "type": "integer",
                "enum": [1, 2],
                "description": "Roping ratio: 1 for 1:1 (default) or 2 for 2:1.",
            },
            "counterweight_balance_pct": {
                "type": "number",
                "description": (
                    "Counterweight balance as % of rated load added to car mass. "
                    "Default 50%. Recommended range 40–55%."
                ),
            },
            "mu": {
                "type": "number",
                "description": (
                    "Equivalent coefficient of friction between rope and groove. "
                    "Default 0.09 for grooved traction sheave (EN 81-1 §9.3)."
                ),
            },
            "groove_angle_deg": {
                "type": "number",
                "description": (
                    "V-groove half-angle (°). Default 40°. "
                    "For semicircular groove use 90°."
                ),
            },
            "wrap_angle_deg": {
                "type": "number",
                "description": "Rope wrap angle on traction sheave (°). Default 180°.",
            },
            "n_ropes": {
                "type": "integer",
                "description": "Number of suspension ropes. Default: auto (minimum 3).",
            },
            "rope_diameter_mm": {
                "type": "number",
                "description": "Rope nominal diameter (mm). Default 13 mm.",
            },
            "sheave_diameter_mm": {
                "type": "number",
                "description": (
                    "Traction sheave pitch diameter (mm). "
                    "Default: minimum D/d = 40 × rope_diameter."
                ),
            },
        },
        "required": ["rated_load_kg", "car_mass_kg", "rated_speed_m_s"],
    },
)


@register(_traction_lift_spec, write=False)
async def run_traction_lift(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("rated_load_kg", "car_mass_kg", "rated_speed_m_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in (
        "roping", "counterweight_balance_pct", "mu", "groove_angle_deg",
        "wrap_angle_deg", "n_ropes", "rope_diameter_mm", "sheave_diameter_mm",
    ):
        if opt in a:
            kwargs[opt] = a[opt]

    result = traction_lift(
        a["rated_load_kg"], a["car_mass_kg"], a["rated_speed_m_s"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: elevator_hydraulic_lift
# ---------------------------------------------------------------------------

_hydraulic_lift_spec = ToolSpec(
    name="elevator_hydraulic_lift",
    description=(
        "Compute hydraulic lift jack force, pump flow, and motor power.\n"
        "\n"
        "Computes:\n"
        "  • Jack/piston force = total suspended weight / roping ratio\n"
        "  • Working pressure = force / piston area\n"
        "  • Proof pressure = working × safety_factor (EN 81-2)\n"
        "  • Pump flow rate (m³/s and L/min)\n"
        "  • Hydraulic pump shaft power and electric motor power\n"
        "\n"
        "Supports direct (1:1) and indirect (2:1) roping.\n"
        "\n"
        "Warnings: working pressure > max_working_pressure, low pump efficiency.\n"
        "\n"
        "References: EN 81-2 §12, CIBSE Guide D §5.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rated_load_kg": {
                "type": "number",
                "description": "Rated payload (kg). Must be > 0.",
            },
            "car_mass_kg": {
                "type": "number",
                "description": "Empty car mass (kg). Must be > 0.",
            },
            "rated_speed_m_s": {
                "type": "number",
                "description": "Rated car speed (m/s). Must be > 0.",
            },
            "piston_diameter_mm": {
                "type": "number",
                "description": "Hydraulic piston/plunger diameter (mm). Must be > 0.",
            },
            "roping": {
                "type": "integer",
                "enum": [1, 2],
                "description": "Roping ratio: 1 (direct, default) or 2 (indirect).",
            },
            "pump_efficiency": {
                "type": "number",
                "description": "Hydraulic pump efficiency (0–1). Default 0.80.",
            },
            "motor_efficiency": {
                "type": "number",
                "description": "Electric motor efficiency (0–1). Default 0.90.",
            },
            "safety_factor": {
                "type": "number",
                "description": (
                    "Pressure safety factor for proof pressure (EN 81-2). "
                    "Default 2.5."
                ),
            },
            "max_working_pressure_MPa": {
                "type": "number",
                "description": "Maximum allowable working pressure (MPa). Default 15.",
            },
        },
        "required": ["rated_load_kg", "car_mass_kg", "rated_speed_m_s", "piston_diameter_mm"],
    },
)


@register(_hydraulic_lift_spec, write=False)
async def run_hydraulic_lift(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("rated_load_kg", "car_mass_kg", "rated_speed_m_s", "piston_diameter_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in (
        "roping", "pump_efficiency", "motor_efficiency",
        "safety_factor", "max_working_pressure_MPa",
    ):
        if opt in a:
            kwargs[opt] = a[opt]

    result = hydraulic_lift(
        a["rated_load_kg"], a["car_mass_kg"], a["rated_speed_m_s"],
        a["piston_diameter_mm"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: elevator_motor_power
# ---------------------------------------------------------------------------

_motor_power_spec = ToolSpec(
    name="elevator_motor_power",
    description=(
        "Compute traction lift motor power from the balanced-load method.\n"
        "\n"
        "Computes worst-case net unbalanced force (full load ascending vs. "
        "empty car ascending), motor shaft power = F × v / η, and "
        "thermally-derated motor power for S3/S4 duty.\n"
        "\n"
        "Warnings: starts/hour > 240 IEC thermal limit, low drive efficiency.\n"
        "\n"
        "References: CIBSE Guide D §3.3, EN 81-1 §12.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rated_load_kg": {
                "type": "number",
                "description": "Rated payload (kg). Must be > 0.",
            },
            "car_mass_kg": {
                "type": "number",
                "description": "Empty car mass (kg). Must be > 0.",
            },
            "counterweight_mass_kg": {
                "type": "number",
                "description": "Counterweight mass (kg). Must be > 0.",
            },
            "rated_speed_m_s": {
                "type": "number",
                "description": "Rated car speed (m/s). Must be > 0.",
            },
            "roping": {
                "type": "integer",
                "enum": [1, 2],
                "description": "Roping ratio (1 or 2). Default 1.",
            },
            "drive_efficiency": {
                "type": "number",
                "description": (
                    "Overall mechanical + electrical drive efficiency (0–1). "
                    "Default 0.80. Gearless drives: 0.85–0.93."
                ),
            },
            "starts_per_hour": {
                "type": "integer",
                "description": "Motor starts per hour. Default 180. Warning if > 240.",
            },
            "duty_factor": {
                "type": "number",
                "description": (
                    "Thermal derating duty factor (0–1). Default 1.0. "
                    "For S3 duty at X% on-time: set duty_factor = sqrt(X/100)."
                ),
            },
        },
        "required": [
            "rated_load_kg", "car_mass_kg", "counterweight_mass_kg", "rated_speed_m_s",
        ],
    },
)


@register(_motor_power_spec, write=False)
async def run_motor_power(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("rated_load_kg", "car_mass_kg", "counterweight_mass_kg", "rated_speed_m_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("roping", "drive_efficiency", "starts_per_hour", "duty_factor"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = motor_power(
        a["rated_load_kg"], a["car_mass_kg"],
        a["counterweight_mass_kg"], a["rated_speed_m_s"],
        **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: elevator_kinematics
# ---------------------------------------------------------------------------

_kinematics_spec = ToolSpec(
    name="elevator_kinematics",
    description=(
        "Compute lift travel kinematics for a single floor-to-floor journey.\n"
        "\n"
        "Uses a symmetric S-curve (trapezoidal jerk) profile:\n"
        "  • Jerk ramp → constant acceleration → jerk ramp down → "
        "constant speed → symmetric deceleration.\n"
        "  • For short floors where rated speed is not reached, the profile "
        "is truncated and maximum achieved speed < rated speed.\n"
        "\n"
        "Computes jerk time, accel time, max achieved speed, accel distance,\n"
        "constant-speed distance, flight time, and floor-to-floor time.\n"
        "\n"
        "Warnings: acceleration > 1.5 m/s² (CIBSE comfort), jerk > 2.0 m/s³,\n"
        "floor too short to reach rated speed.\n"
        "\n"
        "References: CIBSE Guide D §3.4, Barney 2003 §4.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "floor_height_m": {
                "type": "number",
                "description": "Floor-to-floor travel distance (m). Must be > 0.",
            },
            "rated_speed_m_s": {
                "type": "number",
                "description": "Rated car speed (m/s). Must be > 0.",
            },
            "acceleration_m_s2": {
                "type": "number",
                "description": (
                    "Peak acceleration (m/s²). Default 1.0 m/s². "
                    "CIBSE comfort: 0.8–1.2 m/s²."
                ),
            },
            "jerk_m_s3": {
                "type": "number",
                "description": (
                    "Maximum jerk (m/s³). Default 2.0 m/s³. "
                    "CIBSE comfort limit: ≤ 2.0 m/s³."
                ),
            },
            "door_time_s": {
                "type": "number",
                "description": "Door open + dwell + close time (s). Default 5.0 s.",
            },
        },
        "required": ["floor_height_m", "rated_speed_m_s"],
    },
)


@register(_kinematics_spec, write=False)
async def run_kinematics(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("floor_height_m", "rated_speed_m_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("acceleration_m_s2", "jerk_m_s3", "door_time_s"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = kinematics(a["floor_height_m"], a["rated_speed_m_s"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: elevator_traffic_analysis
# ---------------------------------------------------------------------------

_traffic_analysis_spec = ToolSpec(
    name="elevator_traffic_analysis",
    description=(
        "CIBSE Guide D round-trip time (RTT) lift traffic analysis.\n"
        "\n"
        "Uses Barney & Dos Santos probable-stops (S) and highest-reversal-floor\n"
        "(H) formulae for a single-entrance building with uniform population.\n"
        "\n"
        "Computes:\n"
        "  • Probable stops S and highest reversal floor H\n"
        "  • Round-trip time RTT per car\n"
        "  • Average interval (s) between departures\n"
        "  • 5-minute handling capacity (% of building population)\n"
        "  • Cars required to achieve a target interval\n"
        "\n"
        "Warnings: interval > 30 s (poor service), interval > 60 s (very poor),\n"
        "handling capacity below target.\n"
        "\n"
        "References: CIBSE Guide D §3.4, Barney 2003 Eq. 3.9.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "n_floors": {
                "type": "integer",
                "description": "Number of served floors above entry level. Must be >= 2.",
            },
            "floor_height_m": {
                "type": "number",
                "description": "Average floor-to-floor height (m). Must be > 0.",
            },
            "n_persons": {
                "type": "integer",
                "description": "Estimated total building population (above entry). Must be > 0.",
            },
            "rated_load_persons": {
                "type": "integer",
                "description": "Car rated capacity in persons. Must be >= 1.",
            },
            "rated_speed_m_s": {
                "type": "number",
                "description": "Rated car speed (m/s). Must be > 0.",
            },
            "acceleration_m_s2": {
                "type": "number",
                "description": "Peak acceleration (m/s²). Default 1.0.",
            },
            "jerk_m_s3": {
                "type": "number",
                "description": "Maximum jerk (m/s³). Default 2.0.",
            },
            "door_time_s": {
                "type": "number",
                "description": "Door open + dwell + close time per stop (s). Default 5.0.",
            },
            "n_cars": {
                "type": "integer",
                "description": "Number of cars in the group. Default 1.",
            },
            "target_interval_s": {
                "type": "number",
                "description": (
                    "Desired average interval (s). "
                    "CIBSE Guide D good service: ≤ 30 s. Warning if exceeded."
                ),
            },
            "target_handling_pct": {
                "type": "number",
                "description": (
                    "Required 5-minute handling capacity (%). "
                    "CIBSE Guide D: typically 12–17% for office buildings."
                ),
            },
        },
        "required": [
            "n_floors", "floor_height_m", "n_persons",
            "rated_load_persons", "rated_speed_m_s",
        ],
    },
)


@register(_traffic_analysis_spec, write=False)
async def run_traffic_analysis(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "n_floors", "floor_height_m", "n_persons",
        "rated_load_persons", "rated_speed_m_s",
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in (
        "acceleration_m_s2", "jerk_m_s3", "door_time_s",
        "n_cars", "target_interval_s", "target_handling_pct",
    ):
        if opt in a:
            kwargs[opt] = a[opt]

    result = traffic_analysis(
        int(a["n_floors"]), a["floor_height_m"], int(a["n_persons"]),
        int(a["rated_load_persons"]), a["rated_speed_m_s"],
        **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: elevator_buffer_stroke
# ---------------------------------------------------------------------------

_buffer_stroke_spec = ToolSpec(
    name="elevator_buffer_stroke",
    description=(
        "Compute EN 81-1 buffer stroke and overspeed governor trip speed.\n"
        "\n"
        "Computes:\n"
        "  • Overspeed governor trip speed (% of rated speed)\n"
        "  • Speed at buffer impact (= governor trip speed)\n"
        "  • Minimum buffer stroke per EN 81-1 §10.4.3\n"
        "    (with EN 81-1 absolute minimum: 420 mm for oil, 150 mm for spring)\n"
        "  • Safety gear stopping distance (progressive gear at 0.5 g)\n"
        "\n"
        "Supported buffer types: 'oil', 'polyurethane', 'spring'.\n"
        "\n"
        "Warnings: trip factor < 115% (EN 81-1 §10.4.1), > 140%.\n"
        "\n"
        "References: EN 81-1 §9.8, §10.4.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rated_speed_m_s": {
                "type": "number",
                "description": "Rated car speed (m/s). Must be > 0.",
            },
            "overspeed_governor_factor": {
                "type": "number",
                "description": (
                    "Trip speed as fraction of rated speed. Default 1.10 (110%). "
                    "EN 81-1 §10.4.1: must be 1.115–1.40."
                ),
            },
            "buffer_type": {
                "type": "string",
                "enum": ["oil", "polyurethane", "spring"],
                "description": "Buffer type. Default 'oil'.",
            },
        },
        "required": ["rated_speed_m_s"],
    },
)


@register(_buffer_stroke_spec, write=False)
async def run_buffer_stroke(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("rated_speed_m_s") is None:
        return json.dumps({"ok": False, "reason": "rated_speed_m_s is required"})

    kwargs: dict = {}
    for opt in ("overspeed_governor_factor", "buffer_type"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = buffer_stroke(a["rated_speed_m_s"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: elevator_escalator
# ---------------------------------------------------------------------------

_escalator_spec = ToolSpec(
    name="elevator_escalator",
    description=(
        "Compute escalator or moving walk capacity and drive power.\n"
        "\n"
        "Computes:\n"
        "  • Inclined truss length from rise and inclination\n"
        "  • Theoretical capacity (persons/hour) from step width and speed\n"
        "  • Actual capacity with utilisation factor\n"
        "  • Passenger lift power = mass flow × g × vertical speed\n"
        "  • Handrail/step chain friction power\n"
        "  • Total drive power and motor power\n"
        "\n"
        "Supports 'escalator' and 'moving_walk' types.\n"
        "\n"
        "Warnings: inclination > EN 115-1 §5.4 limit, speed > EN 115-1 max,\n"
        "actual capacity below target.\n"
        "\n"
        "References: EN 115-1:2017 §5, CIBSE Guide D §7.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "step_width_m": {
                "type": "number",
                "description": (
                    "Clear step width (m). Standard: 0.60, 0.80, 1.00 m. Must be > 0."
                ),
            },
            "belt_speed_m_s": {
                "type": "number",
                "description": (
                    "Step/belt speed (m/s). EN 115-1 max: 0.75 m/s escalator, "
                    "0.90 m/s moving walk. Must be > 0."
                ),
            },
            "rise_m": {
                "type": "number",
                "description": "Total vertical rise (m). Must be > 0.",
            },
            "inclination_deg": {
                "type": "number",
                "description": (
                    "Inclination angle from horizontal (°). Default 30°. "
                    "EN 115-1: ≤ 30° (rise ≤ 6 m), ≤ 35° (rise > 6 m), ≤ 12° (walk)."
                ),
            },
            "escalator_type": {
                "type": "string",
                "enum": ["escalator", "moving_walk"],
                "description": "Type: 'escalator' (default) or 'moving_walk'.",
            },
            "utilisation_factor": {
                "type": "number",
                "description": "Utilisation factor (0.1–1.0). Default 0.75.",
            },
            "drive_efficiency": {
                "type": "number",
                "description": "Drive efficiency (0–1). Default 0.85.",
            },
            "target_capacity_pph": {
                "type": "number",
                "description": (
                    "Required capacity (persons/hour). Warning if actual < target."
                ),
            },
        },
        "required": ["step_width_m", "belt_speed_m_s", "rise_m"],
    },
)


@register(_escalator_spec, write=False)
async def run_escalator(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("step_width_m", "belt_speed_m_s", "rise_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in (
        "inclination_deg", "escalator_type", "utilisation_factor",
        "drive_efficiency", "target_capacity_pph",
    ):
        if opt in a:
            kwargs[opt] = a[opt]

    result = escalator(a["step_width_m"], a["belt_speed_m_s"], a["rise_m"], **kwargs)
    return ok_payload(result)
