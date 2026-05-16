"""
kerf_cad_core.conveyor.tools — LLM tool wrappers for bulk-material conveyor design.

Registers three tools with the Kerf tool registry:

  belt_conveyor_design
      CEMA-style troughed belt conveyor: capacity, effective tension, drive
      power, slack-side tension, belt rating index, idler load, takeup
      tension, inclination vs angle of repose.

  screw_conveyor_design
      CEMA screw conveyor: capacity, material/drive/incline power, shaft
      torque, fill ratio.

  bucket_elevator_design
      Bucket elevator: capacity, lift power, belt tension, motor sizing.

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
CEMA — Belt Conveyors for Bulk Materials, 7th ed.
CEMA — Screw Conveyors for Bulk Materials, 5th ed.
Fenner Dunlop — Conveyor Handbook, 2009

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.conveyor.design import (
    belt_conveyor,
    screw_conveyor,
    bucket_elevator,
)


# ---------------------------------------------------------------------------
# Tool: belt_conveyor_design
# ---------------------------------------------------------------------------

_belt_conveyor_spec = ToolSpec(
    name="belt_conveyor_design",
    description=(
        "Design a CEMA-style troughed or flat belt conveyor for bulk materials.\n"
        "\n"
        "Computes:\n"
        "  • Load cross-section area (3-roll equal-troughing idler, CEMA method)\n"
        "  • Volumetric capacity (m³/h) and mass throughput (t/h)\n"
        "  • Effective tension Te = friction (Ky) + lift + accessories (N)\n"
        "  • Required drive power at pulley and motor shaft power (kW)\n"
        "  • Slack-side tension T2 = Te / (e^(μθ) - 1) for no-slip (N)\n"
        "  • Belt rating tension index Te / belt_width (N/m)\n"
        "  • Carrying idler load (N)\n"
        "  • Takeup (counterweight) tension (N)\n"
        "  • Inclination angle and angle-of-repose safety check\n"
        "\n"
        "Warnings (never fatal): over-incline vs angle of repose, "
        "belt overtension, capacity shortfall vs target.\n"
        "\n"
        "References: CEMA Belt Conveyors for Bulk Materials, 7th ed.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "belt_width_m": {
                "type": "number",
                "description": (
                    "Belt width (m). Must be > 0. Typical range: 0.45–2.4 m."
                ),
            },
            "belt_speed_m_s": {
                "type": "number",
                "description": (
                    "Belt speed (m/s). Must be > 0. Typical 0.5–5 m/s."
                ),
            },
            "length_m": {
                "type": "number",
                "description": (
                    "Horizontal projected conveyor length (m). Must be > 0."
                ),
            },
            "lift_m": {
                "type": "number",
                "description": (
                    "Vertical lift (m). Positive = uphill, negative = downhill, "
                    "0 = flat (default)."
                ),
            },
            "bulk_density_kg_m3": {
                "type": "number",
                "description": (
                    "Bulk density of material (kg/m³). Must be > 0. "
                    "Examples: coal ~800, iron ore ~2000, grain ~750."
                ),
            },
            "trough_angle_deg": {
                "type": "number",
                "description": (
                    "Troughing idler angle (deg). Default 35. "
                    "Supported: 0 (flat), 20, 35, 45."
                ),
            },
            "surcharge_angle_deg": {
                "type": "number",
                "description": (
                    "Material surcharge angle on belt (deg). Default 20. Range 0–30."
                ),
            },
            "friction_factor": {
                "type": "number",
                "description": (
                    "CEMA Ky belt-and-material flexing resistance factor. "
                    "Default 0.020. Typical 0.016–0.025."
                ),
            },
            "drive_efficiency": {
                "type": "number",
                "description": "Overall drive efficiency (0–1). Default 0.90.",
            },
            "belt_mass_kg_m": {
                "type": "number",
                "description": (
                    "Belt mass per metre (kg/m). If omitted, estimated as "
                    "10 × belt_width_m."
                ),
            },
            "idler_spacing_m": {
                "type": "number",
                "description": "Carrying-side idler spacing (m). Default 1.2 m.",
            },
            "wrap_angle_deg": {
                "type": "number",
                "description": (
                    "Drive pulley wrap angle (deg). Default 210. Range 90–360."
                ),
            },
            "mu_belt_pulley": {
                "type": "number",
                "description": (
                    "Belt-to-pulley friction coefficient. Default 0.35 "
                    "(rubber on lagged steel)."
                ),
            },
            "accessory_tension_N": {
                "type": "number",
                "description": (
                    "Additional tension from skirt boards, plows, cleaners (N). "
                    "Default 0."
                ),
            },
            "target_capacity_t_h": {
                "type": "number",
                "description": (
                    "Required throughput (t/h). If given, warns if actual < target."
                ),
            },
            "repose_angle_deg": {
                "type": "number",
                "description": (
                    "Material angle of repose (deg). If given, warns if "
                    "conveyor inclination > 0.75 × repose_angle."
                ),
            },
        },
        "required": ["belt_width_m", "belt_speed_m_s", "length_m",
                     "lift_m", "bulk_density_kg_m3"],
    },
)


@register(_belt_conveyor_spec, write=False)
async def run_belt_conveyor_design(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("belt_width_m", "belt_speed_m_s", "length_m",
                  "lift_m", "bulk_density_kg_m3"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in (
        "trough_angle_deg", "surcharge_angle_deg", "friction_factor",
        "drive_efficiency", "belt_mass_kg_m", "idler_spacing_m",
        "wrap_angle_deg", "mu_belt_pulley", "accessory_tension_N",
        "target_capacity_t_h", "repose_angle_deg",
    ):
        if opt in a:
            kwargs[opt] = a[opt]

    result = belt_conveyor(
        a["belt_width_m"],
        a["belt_speed_m_s"],
        a["length_m"],
        a["lift_m"],
        a["bulk_density_kg_m3"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: screw_conveyor_design
# ---------------------------------------------------------------------------

_screw_conveyor_spec = ToolSpec(
    name="screw_conveyor_design",
    description=(
        "Design a CEMA screw conveyor for bulk materials.\n"
        "\n"
        "Computes:\n"
        "  • Trough capacity (m³/h) and mass throughput (t/h)\n"
        "  • Fill ratio vs CEMA maximum\n"
        "  • Material conveyance power Pm (kW)\n"
        "  • Incline lift power Pi (kW)\n"
        "  • Total shaft power Pt = (Pm + Pi) × drive-loss factor (kW)\n"
        "  • Motor power = Pt / η (kW)\n"
        "  • Shaft torque (N·m)\n"
        "\n"
        "Warnings (never fatal): over-fill, over-speed (> 100 rpm), "
        "capacity shortfall vs target.\n"
        "\n"
        "Material classes: grain, coal_dry, coal_wet, cement_dry, sand_dry, "
        "sand_wet, clay_dry, fly_ash, limestone, generic_light, generic_medium, "
        "generic_heavy.\n"
        "Loading classes: light (45%), medium (38%), heavy (30%), special (15%).\n"
        "\n"
        "References: CEMA Screw Conveyors for Bulk Materials, 5th ed.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "diameter_m": {
                "type": "number",
                "description": (
                    "Screw flight outer diameter (m). Must be > 0. "
                    "Standard sizes: 0.15, 0.20, 0.25, 0.30, 0.40, 0.50 m."
                ),
            },
            "pitch_m": {
                "type": "number",
                "description": (
                    "Screw pitch (m). Standard pitch = diameter. Must be > 0."
                ),
            },
            "speed_rpm": {
                "type": "number",
                "description": (
                    "Screw rotational speed (rpm). Must be > 0. "
                    "Typical CEMA max: 60–100 rpm for bulk materials."
                ),
            },
            "length_m": {
                "type": "number",
                "description": "Conveyor length (m). Must be > 0.",
            },
            "bulk_density_kg_m3": {
                "type": "number",
                "description": "Bulk density (kg/m³). Must be > 0.",
            },
            "material_class": {
                "type": "string",
                "enum": [
                    "grain", "coal_dry", "coal_wet", "cement_dry",
                    "sand_dry", "sand_wet", "clay_dry", "fly_ash",
                    "limestone", "generic_light", "generic_medium", "generic_heavy",
                ],
                "description": "CEMA material class (default 'generic_medium').",
            },
            "loading_class": {
                "type": "string",
                "enum": ["light", "medium", "heavy", "special"],
                "description": (
                    "CEMA trough loading class (default 'medium'): "
                    "light=45%, medium=38%, heavy=30%, special=15%."
                ),
            },
            "lift_m": {
                "type": "number",
                "description": (
                    "Vertical lift (m). Default 0 (horizontal). "
                    "Positive = uphill, negative = downhill (conservative: no power credit)."
                ),
            },
            "drive_efficiency": {
                "type": "number",
                "description": "Drive efficiency (0–1). Default 0.85.",
            },
            "target_capacity_t_h": {
                "type": "number",
                "description": (
                    "Required throughput (t/h). Warns if actual < target."
                ),
            },
        },
        "required": ["diameter_m", "pitch_m", "speed_rpm",
                     "length_m", "bulk_density_kg_m3"],
    },
)


@register(_screw_conveyor_spec, write=False)
async def run_screw_conveyor_design(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("diameter_m", "pitch_m", "speed_rpm",
                  "length_m", "bulk_density_kg_m3"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("material_class", "loading_class", "lift_m",
                "drive_efficiency", "target_capacity_t_h"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = screw_conveyor(
        a["diameter_m"],
        a["pitch_m"],
        a["speed_rpm"],
        a["length_m"],
        a["bulk_density_kg_m3"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bucket_elevator_design
# ---------------------------------------------------------------------------

_bucket_elevator_spec = ToolSpec(
    name="bucket_elevator_design",
    description=(
        "Design a bucket elevator (centrifugal or continuous discharge) for "
        "bulk materials.\n"
        "\n"
        "Computes:\n"
        "  • Volumetric capacity (m³/h) and mass throughput (t/h)\n"
        "  • Material mass per bucket (kg)\n"
        "  • Lift power to raise material (kW)\n"
        "  • Belt/chain power component (kW)\n"
        "  • Total shaft and motor power (kW)\n"
        "  • Approximate belt tension at head pulley (N)\n"
        "\n"
        "Warnings (never fatal): over-speed for elevator type, "
        "capacity shortfall vs target.\n"
        "\n"
        "References: CEMA; Fenner Dunlop Conveyor Handbook.\n"
        "Errors → {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "bucket_volume_m3": {
                "type": "number",
                "description": (
                    "Geometric volume of one bucket (m³). Must be > 0. "
                    "Typical: 0.002–0.050 m³."
                ),
            },
            "bucket_spacing_m": {
                "type": "number",
                "description": (
                    "Centre-to-centre bucket spacing on belt (m). Must be > 0."
                ),
            },
            "belt_speed_m_s": {
                "type": "number",
                "description": (
                    "Belt or chain speed (m/s). Must be > 0. "
                    "Centrifugal: 1–2.5 m/s; continuous: 0.5–1.5 m/s."
                ),
            },
            "lift_height_m": {
                "type": "number",
                "description": "Vertical lift height (m). Must be > 0.",
            },
            "bulk_density_kg_m3": {
                "type": "number",
                "description": "Bulk density of material (kg/m³). Must be > 0.",
            },
            "fill_factor": {
                "type": "number",
                "description": (
                    "Bucket fill factor (0–1). Default 0.75. "
                    "Actual fill as fraction of bucket geometric volume."
                ),
            },
            "belt_mass_kg_m": {
                "type": "number",
                "description": "Belt or chain mass per metre (kg/m). Default 5.0.",
            },
            "drive_efficiency": {
                "type": "number",
                "description": "Drive efficiency (0–1). Default 0.85.",
            },
            "elevator_type": {
                "type": "string",
                "enum": ["centrifugal", "continuous"],
                "description": (
                    "Elevator type: 'centrifugal' (default, high-speed discharge) "
                    "or 'continuous' (gentle, low-speed, fragile materials)."
                ),
            },
            "target_capacity_t_h": {
                "type": "number",
                "description": (
                    "Required throughput (t/h). Warns if actual < target."
                ),
            },
        },
        "required": ["bucket_volume_m3", "bucket_spacing_m", "belt_speed_m_s",
                     "lift_height_m", "bulk_density_kg_m3"],
    },
)


@register(_bucket_elevator_spec, write=False)
async def run_bucket_elevator_design(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("bucket_volume_m3", "bucket_spacing_m", "belt_speed_m_s",
                  "lift_height_m", "bulk_density_kg_m3"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in ("fill_factor", "belt_mass_kg_m", "drive_efficiency",
                "elevator_type", "target_capacity_t_h"):
        if opt in a:
            kwargs[opt] = a[opt]

    result = bucket_elevator(
        a["bucket_volume_m3"],
        a["bucket_spacing_m"],
        a["belt_speed_m_s"],
        a["lift_height_m"],
        a["bulk_density_kg_m3"],
        **kwargs,
    )
    return ok_payload(result)
