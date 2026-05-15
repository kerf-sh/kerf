"""
kerf_cad_core.gearbox.tools — LLM tool wrappers for gear-train assembly.

Registers three tools:

  gearbox_design
      Compose a multi-stage gear train from a list of stage descriptors plus
      an input operating point (rpm, torque).  Returns total ratio, per-shaft
      speed / torque, per-stage interference checks and shaft layout.

  gearbox_ratio
      Compute only the total gear ratio (product of stage z2/z1).

  gearbox_shaft_table
      Return only the shaft table (speed, torque, cumulative centre distance)
      from a gear-train description.

All tools are pure-Python, deterministic, and never raise.
Errors are returned as {ok: false, errors: [...]}.

Author: imranparuk
"""

from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # type: ignore[import]

from kerf_cad_core.gearbox.train import (
    design_gearbox,
    gearbox_ratio  as _gearbox_ratio,
    gearbox_shaft_table as _gearbox_shaft_table,
)


# ---------------------------------------------------------------------------
# Shared stage schema fragment (reused in all three tool schemas)
# ---------------------------------------------------------------------------

_STAGE_SCHEMA = {
    "type": "object",
    "description": (
        "A single meshing pair (pinion + gear). "
        "Required: z1 (pinion teeth), z2 (gear teeth), module (mm). "
        "Optional: pressure_angle_deg (default 20), profile_shift_1 / "
        "profile_shift_2 (default 0), eta (efficiency, default 0.98), "
        "is_idler (bool, default false), shaft_in / shaft_out (string labels)."
    ),
    "properties": {
        "z1": {
            "type": "integer",
            "description": "Pinion tooth count (driver). Must be >= 3.",
        },
        "z2": {
            "type": "integer",
            "description": "Gear tooth count (driven). Must be >= 3.",
        },
        "module": {
            "type": "number",
            "description": "Module m (mm). Standard ISO values: 1, 1.5, 2, 2.5, 3, 4, 5. Must be > 0.",
        },
        "pressure_angle_deg": {
            "type": "number",
            "description": "Pressure angle α in degrees. Default 20. Must be in (10°, 30°).",
        },
        "profile_shift_1": {
            "type": "number",
            "description": "Profile-shift coefficient x1 for pinion (dimensionless). Default 0.",
        },
        "profile_shift_2": {
            "type": "number",
            "description": "Profile-shift coefficient x2 for gear (dimensionless). Default 0.",
        },
        "eta": {
            "type": "number",
            "description": "Per-mesh efficiency (0 < η ≤ 1). Default 0.98.",
        },
        "is_idler": {
            "type": "boolean",
            "description": (
                "Mark as idler stage. Idler ratio = 1 (no speed change) but "
                "reversal of rotation direction is noted. Default false."
            ),
        },
        "shaft_in": {
            "type": "string",
            "description": "Label for the input shaft of this stage. Default 'shaft_i'.",
        },
        "shaft_out": {
            "type": "string",
            "description": "Label for the output shaft of this stage. Default 'shaft_{i+1}'.",
        },
    },
    "required": ["z1", "z2", "module"],
}


# ---------------------------------------------------------------------------
# T-GB-1: gearbox_design
# ---------------------------------------------------------------------------

_gearbox_design_spec = ToolSpec(
    name="gearbox_design",
    description=(
        "Design a multi-stage gear train (gearbox). "
        "Accepts an ordered list of gear stages (each: pinion teeth z1, gear "
        "teeth z2, module m) plus an input operating point (rpm and torque). "
        "\n"
        "Computes: "
        "  • Total gear ratio = ∏ (z2_i / z1_i)  (Shigley §13-4) "
        "  • Per-shaft speed  n_out = n_in / ratio "
        "  • Per-shaft torque T_out = T_in · ratio · η "
        "  • Per-stage interference / undercut warnings (via gears.py checks) "
        "  • Per-stage centre distance a = m·(z1+z2)/2  (ISO 21771 §10.1) "
        "  • Cumulative shaft layout (summed centre distances along the train) "
        "  • Total drivetrain efficiency = ∏ η_i "
        "\n"
        "Idler stages (is_idler=true) pass ratio=1 and reverse rotation direction. "
        "Never raises; validation errors returned as {ok:false, errors:[]}. "
        "Units: mm, rpm, N·m. "
        "References: Shigley §13-4 to §13-7; ISO 21771:2007."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stages": {
                "type": "array",
                "description": "Ordered list of gear-pair stages from input shaft to output shaft.",
                "items": _STAGE_SCHEMA,
                "minItems": 1,
            },
            "input_rpm": {
                "type": "number",
                "description": "Input shaft rotational speed (rpm). Must be > 0.",
            },
            "input_torque": {
                "type": "number",
                "description": "Input shaft torque (N·m). Must be > 0.",
            },
        },
        "required": ["stages", "input_rpm", "input_torque"],
    },
)


@register(_gearbox_design_spec, write=False)
async def run_gearbox_design(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid JSON: {e}", "BAD_ARGS")

    stages = a.get("stages")
    if stages is None:
        return err_payload("missing required field 'stages'", "BAD_ARGS")

    try:
        input_rpm    = float(a.get("input_rpm", 0))
        input_torque = float(a.get("input_torque", 0))
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric argument required: {e}", "BAD_ARGS")

    result = design_gearbox(stages, input_rpm, input_torque)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# T-GB-2: gearbox_ratio
# ---------------------------------------------------------------------------

_gearbox_ratio_spec = ToolSpec(
    name="gearbox_ratio",
    description=(
        "Compute the total gear ratio for a multi-stage gear train. "
        "\n"
        "total_ratio = ∏ (z2_i / z1_i)  for non-idler stages "
        "(idler stages contribute ratio=1). "
        "\n"
        "Returns {ok, total_ratio, stage_ratios:[...]}. "
        "Faster than gearbox_design when only the ratio is needed. "
        "Never raises. "
        "Reference: ISO 21771:2007 §3.12."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stages": {
                "type": "array",
                "description": "Ordered list of gear-pair stages.",
                "items": _STAGE_SCHEMA,
                "minItems": 1,
            },
        },
        "required": ["stages"],
    },
)


@register(_gearbox_ratio_spec, write=False)
async def run_gearbox_ratio(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid JSON: {e}", "BAD_ARGS")

    stages = a.get("stages")
    if stages is None:
        return err_payload("missing required field 'stages'", "BAD_ARGS")

    result = _gearbox_ratio(stages)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# T-GB-3: gearbox_shaft_table
# ---------------------------------------------------------------------------

_gearbox_shaft_table_spec = ToolSpec(
    name="gearbox_shaft_table",
    description=(
        "Return the shaft speed / torque table for a multi-stage gear train. "
        "\n"
        "Each row: shaft_id, rpm, torque_nm, cumulative_centre_distance_mm. "
        "\n"
        "Equations: "
        "  n_shaft = n_input / ∏ ratio_upstream "
        "  T_shaft = T_input · ∏ (ratio_i · η_i)_upstream "
        "  a_cumulative = ∑ m_i·(z1_i+z2_i)/2  (ISO 21771 §10.1) "
        "\n"
        "Returns {ok, shafts:[{shaft_id, rpm, torque_nm, cumulative_centre_distance_mm}]}. "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stages": {
                "type": "array",
                "description": "Ordered list of gear-pair stages.",
                "items": _STAGE_SCHEMA,
                "minItems": 1,
            },
            "input_rpm": {
                "type": "number",
                "description": "Input shaft rotational speed (rpm). Must be > 0.",
            },
            "input_torque": {
                "type": "number",
                "description": "Input shaft torque (N·m). Must be > 0.",
            },
        },
        "required": ["stages", "input_rpm", "input_torque"],
    },
)


@register(_gearbox_shaft_table_spec, write=False)
async def run_gearbox_shaft_table(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid JSON: {e}", "BAD_ARGS")

    stages = a.get("stages")
    if stages is None:
        return err_payload("missing required field 'stages'", "BAD_ARGS")

    try:
        input_rpm    = float(a.get("input_rpm", 0))
        input_torque = float(a.get("input_torque", 0))
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric argument required: {e}", "BAD_ARGS")

    result = _gearbox_shaft_table(stages, input_rpm, input_torque)
    return ok_payload(result)
