"""
kerf_cad_core.injection.tools — LLM tool wrappers for injection-moulding
process design.

Registers ten tools with the Kerf tool registry:

  injection_polymer_properties    — polymer data record (PP/ABS/PC/PA/POM)
  injection_clamp_tonnage         — required clamping force
  injection_shot_volume_weight    — shot volume/weight vs machine capacity
  injection_gate_runner_sizing    — gate thickness/width and runner diameter
  injection_cooling_time          — plate-cooling time (Fourier first-term)
  injection_flow_length_feasibility — L/t ratio check
  injection_shrinkage_sink_estimate — linear shrinkage + sink-mark depth
  injection_cycle_time_breakdown  — total cycle and phase fractions
  injection_cavities_from_tonnage — max cavities from press size
  injection_draft_ejection_force  — draft angle + ejection force estimate

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Rosato, D.V. & Rosato, M.G. "Injection Moulding Handbook", 3rd ed.
Menges, G. et al. "How to Make Injection Molds", 3rd ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.injection.process import (
    polymer_properties,
    clamp_tonnage,
    shot_volume_weight,
    gate_runner_sizing,
    cooling_time,
    flow_length_feasibility,
    shrinkage_sink_estimate,
    cycle_time_breakdown,
    cavities_from_tonnage,
    draft_ejection_force,
)

_POLYMER_ENUM = ["PP", "ABS", "PC", "PA", "POM"]


# ---------------------------------------------------------------------------
# Tool: injection_polymer_properties
# ---------------------------------------------------------------------------

_polymer_properties_spec = ToolSpec(
    name="injection_polymer_properties",
    description=(
        "Return the built-in property record for a named injection-moulding "
        "polymer.\n"
        "\n"
        "Supported polymers: PP (polypropylene), ABS, PC (polycarbonate), "
        "PA (nylon-6/6), POM (acetal/Delrin).\n"
        "\n"
        "Returns melt/mould temperature, ejection temperature, linear "
        "shrinkage, thermal diffusivity, density, flow-length/wall-thickness "
        "limit, friction coefficient, and typical cavity pressure.\n"
        "\n"
        "Errors: {ok:false, reason} for unknown polymer.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "polymer": {
                "type": "string",
                "enum": _POLYMER_ENUM,
                "description": "Polymer name: PP, ABS, PC, PA, or POM.",
            },
        },
        "required": ["polymer"],
    },
)


@register(_polymer_properties_spec, write=False)
async def run_polymer_properties(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("polymer") is None:
        return json.dumps({"ok": False, "reason": "polymer is required"})
    result = polymer_properties(a["polymer"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: injection_clamp_tonnage
# ---------------------------------------------------------------------------

_clamp_tonnage_spec = ToolSpec(
    name="injection_clamp_tonnage",
    description=(
        "Compute the required injection-moulding clamping force from "
        "projected area and cavity pressure.\n"
        "\n"
        "  F_clamp = n_cavities × A_proj × P_cavity × safety_factor\n"
        "\n"
        "Returns clamp_force_kN and flags 'over-tonnage' if > 50 000 kN.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "projected_area_m2": {
                "type": "number",
                "description": (
                    "Projected area of one cavity in the parting-line plane (m²). "
                    "Must be > 0."
                ),
            },
            "cavity_pressure_Pa": {
                "type": "number",
                "description": (
                    "Peak cavity pressure (Pa). Typical: 30–80 MPa. "
                    "Must be > 0."
                ),
            },
            "n_cavities": {
                "type": "integer",
                "description": "Number of cavities (default 1). Must be >= 1.",
            },
            "safety_factor": {
                "type": "number",
                "description": "Clamping safety factor (default 1.1).",
            },
        },
        "required": ["projected_area_m2", "cavity_pressure_Pa"],
    },
)


@register(_clamp_tonnage_spec, write=False)
async def run_clamp_tonnage(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("projected_area_m2") is None:
        return json.dumps({"ok": False, "reason": "projected_area_m2 is required"})
    if a.get("cavity_pressure_Pa") is None:
        return json.dumps({"ok": False, "reason": "cavity_pressure_Pa is required"})

    kwargs: dict = {}
    if "n_cavities" in a:
        kwargs["n_cavities"] = a["n_cavities"]
    if "safety_factor" in a:
        kwargs["safety_factor"] = a["safety_factor"]

    result = clamp_tonnage(a["projected_area_m2"], a["cavity_pressure_Pa"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: injection_shot_volume_weight
# ---------------------------------------------------------------------------

_shot_volume_weight_spec = ToolSpec(
    name="injection_shot_volume_weight",
    description=(
        "Compute injection shot volume and weight, and check against machine "
        "capacity.\n"
        "\n"
        "  shot_volume = n_cavities × part_volume + runner_volume\n"
        "  shot_weight = shot_volume × polymer_density\n"
        "\n"
        "Flags 'short-shot risk' if shot_weight exceeds machine capacity.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "part_volume_m3": {
                "type": "number",
                "description": "Volume of one moulded part (m³). Must be > 0.",
            },
            "runner_volume_m3": {
                "type": "number",
                "description": "Combined runner and sprue volume per shot (m³). Must be >= 0.",
            },
            "n_cavities": {
                "type": "integer",
                "description": "Number of cavities. Must be >= 1.",
            },
            "polymer": {
                "type": "string",
                "enum": _POLYMER_ENUM,
                "description": "Polymer name: PP, ABS, PC, PA, or POM.",
            },
            "machine_shot_capacity_kg": {
                "type": "number",
                "description": (
                    "Machine maximum shot capacity (kg, default 5.0). Must be > 0."
                ),
            },
        },
        "required": ["part_volume_m3", "runner_volume_m3", "n_cavities", "polymer"],
    },
)


@register(_shot_volume_weight_spec, write=False)
async def run_shot_volume_weight(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("part_volume_m3", "runner_volume_m3", "n_cavities", "polymer"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "machine_shot_capacity_kg" in a:
        kwargs["machine_shot_capacity_kg"] = a["machine_shot_capacity_kg"]

    result = shot_volume_weight(
        a["part_volume_m3"], a["runner_volume_m3"], a["n_cavities"], a["polymer"],
        **kwargs,
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: injection_gate_runner_sizing
# ---------------------------------------------------------------------------

_gate_runner_sizing_spec = ToolSpec(
    name="injection_gate_runner_sizing",
    description=(
        "Size the gate (land thickness, width) and primary runner diameter "
        "for an injection-moulded part.\n"
        "\n"
        "Gate land thickness = 60% of wall thickness.\n"
        "Gate width sized to keep gate velocity <= gate_velocity_limit_ms.\n"
        "Runner diameter = max(1.5 × gate_thickness, 4 mm).\n"
        "\n"
        "Flags thin-wall-flow risk if wall < 0.8 mm.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "flow_rate_m3s": {
                "type": "number",
                "description": "Volumetric injection flow rate (m³/s). Must be > 0.",
            },
            "wall_thickness_m": {
                "type": "number",
                "description": (
                    "Nominal wall thickness at the gate location (m). Must be > 0."
                ),
            },
            "polymer": {
                "type": "string",
                "enum": _POLYMER_ENUM,
                "description": "Polymer name: PP, ABS, PC, PA, or POM.",
            },
            "gate_velocity_limit_ms": {
                "type": "number",
                "description": (
                    "Maximum allowed gate velocity (m/s, default 0.5). Must be > 0."
                ),
            },
        },
        "required": ["flow_rate_m3s", "wall_thickness_m", "polymer"],
    },
)


@register(_gate_runner_sizing_spec, write=False)
async def run_gate_runner_sizing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("flow_rate_m3s", "wall_thickness_m", "polymer"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "gate_velocity_limit_ms" in a:
        kwargs["gate_velocity_limit_ms"] = a["gate_velocity_limit_ms"]

    result = gate_runner_sizing(
        a["flow_rate_m3s"], a["wall_thickness_m"], a["polymer"], **kwargs
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: injection_cooling_time
# ---------------------------------------------------------------------------

_cooling_time_spec = ToolSpec(
    name="injection_cooling_time",
    description=(
        "Calculate the injection-moulding cooling time for a flat-plate part.\n"
        "\n"
        "Uses the Fourier first-term plate equation:\n"
        "  t_c = (s²/(π²·α)) · ln((8/π²) · (T_m - T_w)/(T_e - T_w))\n"
        "where s = wall/2, α = thermal diffusivity.\n"
        "\n"
        "Thermal diffusivity α is taken from the built-in polymer table.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs or temperature "
        "ordering violations.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "wall_thickness_m": {
                "type": "number",
                "description": "Part wall thickness (m). Must be > 0.",
            },
            "melt_temp_C": {
                "type": "number",
                "description": "Melt injection temperature (°C).",
            },
            "mold_temp_C": {
                "type": "number",
                "description": "Mould wall coolant temperature (°C).",
            },
            "ejection_temp_C": {
                "type": "number",
                "description": (
                    "Part surface temperature at ejection (°C). "
                    "Must satisfy mold_temp_C < ejection_temp_C < melt_temp_C."
                ),
            },
            "polymer": {
                "type": "string",
                "enum": _POLYMER_ENUM,
                "description": "Polymer name: PP, ABS, PC, PA, or POM.",
            },
        },
        "required": [
            "wall_thickness_m", "melt_temp_C", "mold_temp_C",
            "ejection_temp_C", "polymer",
        ],
    },
)


@register(_cooling_time_spec, write=False)
async def run_cooling_time(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("wall_thickness_m", "melt_temp_C", "mold_temp_C",
                  "ejection_temp_C", "polymer"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = cooling_time(
        a["wall_thickness_m"],
        a["melt_temp_C"],
        a["mold_temp_C"],
        a["ejection_temp_C"],
        a["polymer"],
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: injection_flow_length_feasibility
# ---------------------------------------------------------------------------

_flow_length_feasibility_spec = ToolSpec(
    name="injection_flow_length_feasibility",
    description=(
        "Check whether the flow-length / wall-thickness (L/t) ratio is "
        "feasible for the chosen polymer.\n"
        "\n"
        "Each polymer has an empirical maximum L/t limit above which "
        "short-shots are likely.  Flags thin-wall-flow risk.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "flow_length_m": {
                "type": "number",
                "description": (
                    "Longest flow-path from gate to end of fill (m). Must be > 0."
                ),
            },
            "wall_thickness_m": {
                "type": "number",
                "description": "Nominal wall thickness (m). Must be > 0.",
            },
            "polymer": {
                "type": "string",
                "enum": _POLYMER_ENUM,
                "description": "Polymer name: PP, ABS, PC, PA, or POM.",
            },
        },
        "required": ["flow_length_m", "wall_thickness_m", "polymer"],
    },
)


@register(_flow_length_feasibility_spec, write=False)
async def run_flow_length_feasibility(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("flow_length_m", "wall_thickness_m", "polymer"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = flow_length_feasibility(
        a["flow_length_m"], a["wall_thickness_m"], a["polymer"]
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: injection_shrinkage_sink_estimate
# ---------------------------------------------------------------------------

_shrinkage_sink_estimate_spec = ToolSpec(
    name="injection_shrinkage_sink_estimate",
    description=(
        "Estimate linear shrinkage and sink-mark depth for an injection-moulded "
        "part.\n"
        "\n"
        "  ΔL = part_dim × (shrinkage_pct / 100)\n"
        "  mould_dim = part_dim / (1 - shrinkage_pct/100)\n"
        "  sink_depth ≈ 0.003–0.006 × wall_thickness\n"
        "\n"
        "Returns shrinkage, required mould dimension, and estimated sink depth.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "part_dim_m": {
                "type": "number",
                "description": "Nominal finished-part dimension (m). Must be > 0.",
            },
            "wall_thickness_m": {
                "type": "number",
                "description": "Wall thickness at the feature (m). Must be > 0.",
            },
            "polymer": {
                "type": "string",
                "enum": _POLYMER_ENUM,
                "description": "Polymer name: PP, ABS, PC, PA, or POM.",
            },
        },
        "required": ["part_dim_m", "wall_thickness_m", "polymer"],
    },
)


@register(_shrinkage_sink_estimate_spec, write=False)
async def run_shrinkage_sink_estimate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("part_dim_m", "wall_thickness_m", "polymer"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = shrinkage_sink_estimate(
        a["part_dim_m"], a["wall_thickness_m"], a["polymer"]
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: injection_cycle_time_breakdown
# ---------------------------------------------------------------------------

_cycle_time_breakdown_spec = ToolSpec(
    name="injection_cycle_time_breakdown",
    description=(
        "Break down the total injection-moulding cycle time into phases.\n"
        "\n"
        "  total = cooling + fill + pack/hold + mould-open/close + ejection\n"
        "\n"
        "Returns total cycle time, phase fractions, and shots per hour.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cooling_time_s": {
                "type": "number",
                "description": "Cooling/solidification time (s). Must be > 0.",
            },
            "fill_time_s": {
                "type": "number",
                "description": "Injection fill time (s). Must be > 0.",
            },
            "pack_hold_time_s": {
                "type": "number",
                "description": "Pack and hold time (s). Must be >= 0.",
            },
            "mold_open_close_s": {
                "type": "number",
                "description": "Mould open + close traversal time (s). Must be >= 0.",
            },
            "ejection_time_s": {
                "type": "number",
                "description": "Ejection / part-removal time (s). Must be >= 0.",
            },
        },
        "required": [
            "cooling_time_s", "fill_time_s", "pack_hold_time_s",
            "mold_open_close_s", "ejection_time_s",
        ],
    },
)


@register(_cycle_time_breakdown_spec, write=False)
async def run_cycle_time_breakdown(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("cooling_time_s", "fill_time_s", "pack_hold_time_s",
                  "mold_open_close_s", "ejection_time_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = cycle_time_breakdown(
        a["cooling_time_s"],
        a["fill_time_s"],
        a["pack_hold_time_s"],
        a["mold_open_close_s"],
        a["ejection_time_s"],
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: injection_cavities_from_tonnage
# ---------------------------------------------------------------------------

_cavities_from_tonnage_spec = ToolSpec(
    name="injection_cavities_from_tonnage",
    description=(
        "Determine the maximum number of cavities for a given press size.\n"
        "\n"
        "  n_max = floor(F_machine / (A_proj × P_cavity × safety_factor))\n"
        "\n"
        "Flags 'over-tonnage' if the press cannot support even one cavity.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "machine_tonnage_kN": {
                "type": "number",
                "description": "Available machine clamping force (kN). Must be > 0.",
            },
            "projected_area_per_cavity_m2": {
                "type": "number",
                "description": "Projected area of one cavity (m²). Must be > 0.",
            },
            "cavity_pressure_Pa": {
                "type": "number",
                "description": "Peak cavity pressure (Pa). Must be > 0.",
            },
            "safety_factor": {
                "type": "number",
                "description": "Clamping safety factor (default 1.1). Must be > 0.",
            },
        },
        "required": [
            "machine_tonnage_kN",
            "projected_area_per_cavity_m2",
            "cavity_pressure_Pa",
        ],
    },
)


@register(_cavities_from_tonnage_spec, write=False)
async def run_cavities_from_tonnage(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("machine_tonnage_kN", "projected_area_per_cavity_m2",
                  "cavity_pressure_Pa"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "safety_factor" in a:
        kwargs["safety_factor"] = a["safety_factor"]

    result = cavities_from_tonnage(
        a["machine_tonnage_kN"],
        a["projected_area_per_cavity_m2"],
        a["cavity_pressure_Pa"],
        **kwargs,
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: injection_draft_ejection_force
# ---------------------------------------------------------------------------

_draft_ejection_force_spec = ToolSpec(
    name="injection_draft_ejection_force",
    description=(
        "Recommend a draft angle and estimate the ejection force for an "
        "injection-moulded part.\n"
        "\n"
        "Draft angle is selected by surface finish:\n"
        "  polished: 0.5°  |  standard: 1.0°  |  textured: 3.0°\n"
        "\n"
        "Ejection force estimate:\n"
        "  F_eject = μ × P_shrink × A_side\n"
        "where A_side ≈ 4 × √(projected_area) × L_draw.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "projected_area_m2": {
                "type": "number",
                "description": "Projected area in the parting-line plane (m²). Must be > 0.",
            },
            "wall_thickness_m": {
                "type": "number",
                "description": "Nominal wall thickness (m). Must be > 0.",
            },
            "L_draw_m": {
                "type": "number",
                "description": "Draw depth / pull direction length (m). Must be > 0.",
            },
            "polymer": {
                "type": "string",
                "enum": _POLYMER_ENUM,
                "description": "Polymer name: PP, ABS, PC, PA, or POM.",
            },
            "surface_finish": {
                "type": "string",
                "enum": ["polished", "standard", "textured"],
                "description": (
                    "Surface finish: 'polished' (0.5°), 'standard' (1.0°, default), "
                    "or 'textured' (3.0°)."
                ),
            },
        },
        "required": [
            "projected_area_m2", "wall_thickness_m", "L_draw_m", "polymer",
        ],
    },
)


@register(_draft_ejection_force_spec, write=False)
async def run_draft_ejection_force(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("projected_area_m2", "wall_thickness_m", "L_draw_m", "polymer"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "surface_finish" in a:
        kwargs["surface_finish"] = a["surface_finish"]

    result = draft_ejection_force(
        a["projected_area_m2"],
        a["wall_thickness_m"],
        a["L_draw_m"],
        a["polymer"],
        **kwargs,
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)
