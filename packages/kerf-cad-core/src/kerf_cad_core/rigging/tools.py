"""
kerf_cad_core.rigging.tools — LLM tool wrappers for lifting & rigging engineering.

Registers tools with the Kerf tool registry:

  rigging_sling_tension           — sling tension from load-angle factor 1/sin θ
  rigging_multi_leg_share         — per-leg load share for 2/3/4-leg lifts
  rigging_cg_pick_loads           — per-pick-point loads from CG geometry
  rigging_sling_wll_derate        — angular WLL derating for slings/shackles/eyebolts
  rigging_wire_rope_capacity      — wire rope WLL by diameter & grade
  rigging_chain_capacity          — alloy chain WLL by size & grade
  rigging_synthetic_sling_capacity — flat-web/round synthetic sling WLL
  rigging_spreader_beam_check     — spreader beam bending & column check
  rigging_padeye_check            — padeye/lug tension, bearing, shear-out check
  rigging_tip_over_two_crane      — two-crane load share & tip-over
  rigging_crane_radius_interpolate — crane capacity from radius–chart table

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
ASME B30.9-2018  — Slings
ASME B30.26-2015 — Rigging Hardware
Rigging Engineering Basics, J.D. Isbester, 2013

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.rigging.lift import (
    sling_tension,
    multi_leg_share,
    cg_pick_loads,
    sling_wll_derate,
    wire_rope_capacity,
    chain_capacity,
    synthetic_sling_capacity,
    spreader_beam_check,
    padeye_check,
    tip_over_two_crane,
    crane_radius_interpolate,
)


# ---------------------------------------------------------------------------
# Tool: rigging_sling_tension
# ---------------------------------------------------------------------------

_sling_tension_spec = ToolSpec(
    name="rigging_sling_tension",
    description=(
        "Compute sling tension from the load-angle factor 1/sin θ.\n"
        "\n"
        "As the sling angle from horizontal decreases, the tension in each "
        "sling leg increases by the load-angle factor (LAF = 1/sin θ). "
        "Angles below 30° from horizontal trigger a warning.\n"
        "\n"
        "Returns tension_per_leg_kN, tension_per_leg_kg, load_angle_factor, "
        "and the required WLL per sling (tension / design_factor).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "load_kg": {
                "type": "number",
                "description": "Total suspended load (kg). Must be > 0.",
            },
            "angle_deg": {
                "type": "number",
                "description": (
                    "Sling angle from horizontal (degrees). "
                    "Must be in (0, 90]. Values < 30° trigger a warning."
                ),
            },
            "n_legs": {
                "type": "integer",
                "description": "Number of equal-share sling legs (default 1, max 8).",
            },
            "design_factor": {
                "type": "number",
                "description": "Design factor for required WLL (default 5.0).",
            },
        },
        "required": ["load_kg", "angle_deg"],
    },
)


@register(_sling_tension_spec, write=False)
async def run_rigging_sling_tension(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("load_kg") is None:
        return json.dumps({"ok": False, "reason": "load_kg is required"})
    if a.get("angle_deg") is None:
        return json.dumps({"ok": False, "reason": "angle_deg is required"})

    kwargs: dict = {}
    if "n_legs" in a:
        kwargs["n_legs"] = a["n_legs"]
    if "design_factor" in a:
        kwargs["design_factor"] = a["design_factor"]

    result = sling_tension(a["load_kg"], a["angle_deg"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_multi_leg_share
# ---------------------------------------------------------------------------

_multi_leg_share_spec = ToolSpec(
    name="rigging_multi_leg_share",
    description=(
        "Compute per-leg load share for 2-, 3-, or 4-leg lifts.\n"
        "\n"
        "Supports equal-leg and unequal-leg geometry via the sling_lengths "
        "parameter. For flexible rigs with 4 legs, the longest (slackest) "
        "leg is treated as non-load-bearing (conservative per LEEA/ASME B30.9). "
        "Rigid mode forces equal sharing.\n"
        "\n"
        "Returns leg_loads_kg (per leg), required_wll_kg (minimum WLL per sling), "
        "and any FLEXIBLE_4LEG warnings.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "load_kg": {
                "type": "number",
                "description": "Total load (kg). Must be > 0.",
            },
            "sling_lengths": {
                "type": "array",
                "items": {"type": "number"},
                "description": (
                    "List of sling lengths (m) for each leg. "
                    "Length 2, 3, or 4. All values must be > 0."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["flexible", "rigid"],
                "description": (
                    "'flexible' (default) — unequal-leg distribution; "
                    "'rigid' — forced equal share."
                ),
            },
            "design_factor": {
                "type": "number",
                "description": "Design factor for required WLL (default 5.0).",
            },
        },
        "required": ["load_kg", "sling_lengths"],
    },
)


@register(_multi_leg_share_spec, write=False)
async def run_rigging_multi_leg_share(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("load_kg") is None:
        return json.dumps({"ok": False, "reason": "load_kg is required"})
    if a.get("sling_lengths") is None:
        return json.dumps({"ok": False, "reason": "sling_lengths is required"})

    kwargs: dict = {}
    if "mode" in a:
        kwargs["mode"] = a["mode"]
    if "design_factor" in a:
        kwargs["design_factor"] = a["design_factor"]

    result = multi_leg_share(a["load_kg"], a["sling_lengths"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_cg_pick_loads
# ---------------------------------------------------------------------------

_cg_pick_loads_spec = ToolSpec(
    name="rigging_cg_pick_loads",
    description=(
        "Compute per-pick-point vertical loads from CG geometry.\n"
        "\n"
        "Distributes the total load to 2, 3, or 4 pick points using "
        "moment equilibrium (lever arm for 2 points, barycentric coordinates "
        "for 3 or 4 points). Also checks whether the CG lies inside the "
        "pick-point polygon; if not, an UNSTABLE warning is raised.\n"
        "\n"
        "Returns pick_loads_kg, pick_loads_kN, pick_shares, cg_inside.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "load_kg": {
                "type": "number",
                "description": "Total load (kg). Must be > 0.",
            },
            "cg_x": {
                "type": "number",
                "description": "Centre-of-gravity X position (m).",
            },
            "cg_y": {
                "type": "number",
                "description": "Centre-of-gravity Y position (m).",
            },
            "pick_points": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": (
                    "List of 2, 3, or 4 pick-point [x, y] coordinates (m) in plan."
                ),
            },
        },
        "required": ["load_kg", "cg_x", "cg_y", "pick_points"],
    },
)


@register(_cg_pick_loads_spec, write=False)
async def run_rigging_cg_pick_loads(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("load_kg", "cg_x", "cg_y", "pick_points"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    pts = [tuple(p) for p in a["pick_points"]]
    result = cg_pick_loads(a["load_kg"], a["cg_x"], a["cg_y"], pts)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_sling_wll_derate
# ---------------------------------------------------------------------------

_sling_wll_derate_spec = ToolSpec(
    name="rigging_sling_wll_derate",
    description=(
        "Compute the derated WLL for slings, shackles, or eyebolts under "
        "angular loading.\n"
        "\n"
        "Uses ASME B30.9 tables for slings (angle from vertical), "
        "ASME B30.26 for eyebolts (angle from bolt axis), and shackle "
        "data for off-plane shackle loading.\n"
        "\n"
        "Returns derated_wll_kg (per leg) and total_wll_kg (×n_legs).\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rated_wll_kg": {
                "type": "number",
                "description": "Rated WLL at reference angle (0° = on-axis) (kg).",
            },
            "angle_deg": {
                "type": "number",
                "description": (
                    "Loading angle (degrees). "
                    "Slings: angle from vertical [0, 90). "
                    "Eyebolts: angle from bolt axis [0, 90]. "
                    "Shackles: off-plane angle [0, 90]."
                ),
            },
            "hardware_type": {
                "type": "string",
                "enum": ["sling", "eyebolt", "shackle"],
                "description": "Hardware type (default 'sling').",
            },
            "n_legs": {
                "type": "integer",
                "description": "Number of legs — multiplies derated WLL (default 1).",
            },
        },
        "required": ["rated_wll_kg", "angle_deg"],
    },
)


@register(_sling_wll_derate_spec, write=False)
async def run_rigging_sling_wll_derate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("rated_wll_kg") is None:
        return json.dumps({"ok": False, "reason": "rated_wll_kg is required"})
    if a.get("angle_deg") is None:
        return json.dumps({"ok": False, "reason": "angle_deg is required"})

    kwargs: dict = {}
    if "hardware_type" in a:
        kwargs["hardware_type"] = a["hardware_type"]
    if "n_legs" in a:
        kwargs["n_legs"] = a["n_legs"]

    result = sling_wll_derate(a["rated_wll_kg"], a["angle_deg"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_wire_rope_capacity
# ---------------------------------------------------------------------------

_wire_rope_capacity_spec = ToolSpec(
    name="rigging_wire_rope_capacity",
    description=(
        "Look up wire rope MBF and compute WLL by diameter and grade.\n"
        "\n"
        "Built-in grades: 6x19_iwrc_1570, 6x19_iwrc_1770, 6x37_iwrc_1570, "
        "6x36_ws_1770. Diameters 8–40 mm depending on grade.\n"
        "\n"
        "Returns mbf_kN, wll_kN, wll_kg.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "diameter_mm": {
                "type": "number",
                "description": "Nominal wire rope diameter (mm).",
            },
            "grade": {
                "type": "string",
                "enum": [
                    "6x19_iwrc_1570",
                    "6x19_iwrc_1770",
                    "6x37_iwrc_1570",
                    "6x36_ws_1770",
                ],
                "description": "Wire rope grade / construction (default '6x19_iwrc_1570').",
            },
            "design_factor": {
                "type": "number",
                "description": "Design factor MBF/WLL (default 5.0).",
            },
        },
        "required": ["diameter_mm"],
    },
)


@register(_wire_rope_capacity_spec, write=False)
async def run_rigging_wire_rope_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("diameter_mm") is None:
        return json.dumps({"ok": False, "reason": "diameter_mm is required"})

    kwargs: dict = {}
    if "grade" in a:
        kwargs["grade"] = a["grade"]
    if "design_factor" in a:
        kwargs["design_factor"] = a["design_factor"]

    result = wire_rope_capacity(a["diameter_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_chain_capacity
# ---------------------------------------------------------------------------

_chain_capacity_spec = ToolSpec(
    name="rigging_chain_capacity",
    description=(
        "Look up alloy steel chain WLL by chain size and grade.\n"
        "\n"
        "Built-in grades: grade_80 (default), grade_100. "
        "Chain sizes: 6, 7, 8, 10, 13, 16, 19, 22, 26, 32 mm.\n"
        "\n"
        "Returns wll_t, wll_kg, wll_kN, and effective_wll_kg (after design factor).\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "size_mm": {
                "type": "number",
                "description": "Chain link diameter (mm). Available: 6,7,8,10,13,16,19,22,26,32.",
            },
            "grade": {
                "type": "string",
                "enum": ["grade_80", "grade_100"],
                "description": "Chain grade (default 'grade_80').",
            },
            "design_factor": {
                "type": "number",
                "description": "Design factor applied to catalogue WLL (default 4.0).",
            },
        },
        "required": ["size_mm"],
    },
)


@register(_chain_capacity_spec, write=False)
async def run_rigging_chain_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("size_mm") is None:
        return json.dumps({"ok": False, "reason": "size_mm is required"})

    kwargs: dict = {}
    if "grade" in a:
        kwargs["grade"] = a["grade"]
    if "design_factor" in a:
        kwargs["design_factor"] = a["design_factor"]

    result = chain_capacity(a["size_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_synthetic_sling_capacity
# ---------------------------------------------------------------------------

_synthetic_sling_capacity_spec = ToolSpec(
    name="rigging_synthetic_sling_capacity",
    description=(
        "Compute flat-web synthetic sling WLL by width, ply, and hitch type.\n"
        "\n"
        "Materials: polyester (default), nylon. "
        "Widths: 25, 50, 75, 100, 150, 200 mm. Ply: 1 or 2.\n"
        "Hitch types: vertical (×1.0), choker (×0.80), basket (×2.0), "
        "basket_45deg (×1.41), basket_60deg (×1.0).\n"
        "\n"
        "Returns base_wll_kg, adjusted_wll_kg (with hitch factor), "
        "effective_wll_kg (after design factor).\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "width_mm": {
                "type": "number",
                "description": "Sling width (mm). Available: 25, 50, 75, 100, 150, 200.",
            },
            "ply": {
                "type": "integer",
                "enum": [1, 2],
                "description": "Number of plies (1 or 2).",
            },
            "material": {
                "type": "string",
                "enum": ["polyester", "nylon"],
                "description": "Sling material (default 'polyester').",
            },
            "hitch": {
                "type": "string",
                "enum": ["vertical", "choker", "basket", "basket_45deg", "basket_60deg"],
                "description": "Hitch configuration (default 'vertical').",
            },
            "design_factor": {
                "type": "number",
                "description": "Design factor (default 7.0).",
            },
        },
        "required": ["width_mm", "ply"],
    },
)


@register(_synthetic_sling_capacity_spec, write=False)
async def run_rigging_synthetic_sling_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("width_mm") is None:
        return json.dumps({"ok": False, "reason": "width_mm is required"})
    if a.get("ply") is None:
        return json.dumps({"ok": False, "reason": "ply is required"})

    kwargs: dict = {}
    if "material" in a:
        kwargs["material"] = a["material"]
    if "hitch" in a:
        kwargs["hitch"] = a["hitch"]
    if "design_factor" in a:
        kwargs["design_factor"] = a["design_factor"]

    result = synthetic_sling_capacity(a["width_mm"], int(a["ply"]), **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_spreader_beam_check
# ---------------------------------------------------------------------------

_spreader_beam_check_spec = ToolSpec(
    name="rigging_spreader_beam_check",
    description=(
        "Check a spreader / lifting beam for bending and axial compression.\n"
        "\n"
        "The beam is modelled as simply-supported under a central point load "
        "(M = WL/4). Axial compression from the sling angles is estimated "
        "conservatively as W/2. Combined utilisation is bending + axial vs "
        "Fy / design_factor.\n"
        "\n"
        "Section string formats:\n"
        "  'tube_square_200x200x10'     — SHS 200×200×10 mm\n"
        "  'tube_round_219x10'          — CHS OD 219 mm × 10 mm wall\n"
        "  'wide_flange_300x150x8x12'   — WF d=300 b=150 tw=8 tf=12 mm\n"
        "\n"
        "Returns bending_stress_MPa, axial_stress_MPa, combined, utilisation, "
        "pass_bending.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "load_kg": {
                "type": "number",
                "description": "Total rigged load (kg). Must be > 0.",
            },
            "span_m": {
                "type": "number",
                "description": "Spreader beam span (m). Must be > 0.",
            },
            "section": {
                "type": "string",
                "description": (
                    "Section string: 'tube_square_DxDxT', 'tube_round_DxT', "
                    "or 'wide_flange_DxBxTwxTf' (all dims in mm)."
                ),
            },
            "Fy_MPa": {
                "type": "number",
                "description": "Steel yield strength (MPa, default 350).",
            },
            "design_factor": {
                "type": "number",
                "description": "Design factor on yield (default 3.0).",
            },
        },
        "required": ["load_kg", "span_m"],
    },
)


@register(_spreader_beam_check_spec, write=False)
async def run_rigging_spreader_beam_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("load_kg") is None:
        return json.dumps({"ok": False, "reason": "load_kg is required"})
    if a.get("span_m") is None:
        return json.dumps({"ok": False, "reason": "span_m is required"})

    kwargs: dict = {}
    if "section" in a:
        kwargs["section"] = a["section"]
    if "Fy_MPa" in a:
        kwargs["Fy_MPa"] = a["Fy_MPa"]
    if "design_factor" in a:
        kwargs["design_factor"] = a["design_factor"]

    result = spreader_beam_check(a["load_kg"], a["span_m"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_padeye_check
# ---------------------------------------------------------------------------

_padeye_check_spec = ToolSpec(
    name="rigging_padeye_check",
    description=(
        "Simplified padeye / lifting lug strength check.\n"
        "\n"
        "Checks three failure modes:\n"
        "  1. Net-section tension (at the pin hole)\n"
        "  2. Bearing on the pin hole\n"
        "  3. Double shear-out\n"
        "\n"
        "Allowables: tension = Fu/DF, bearing = 1.5·Fy/DF, shear = 0.6·Fy/DF.\n"
        "\n"
        "Returns stresses, allowables, pass/fail flags, and utilisations for "
        "all three modes.\n"
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
                "description": "Plate thickness (mm). Must be > 0.",
            },
            "hole_diameter_mm": {
                "type": "number",
                "description": "Pin-hole diameter (mm). Must be > pin_diameter_mm.",
            },
            "pin_diameter_mm": {
                "type": "number",
                "description": "Pin diameter (mm). Must be < hole_diameter_mm.",
            },
            "Fy_MPa": {
                "type": "number",
                "description": "Plate yield strength (MPa, default 350).",
            },
            "Fu_MPa": {
                "type": "number",
                "description": "Plate ultimate tensile strength (MPa, default 480).",
            },
            "design_factor": {
                "type": "number",
                "description": "Design factor (default 3.0).",
            },
        },
        "required": ["load_kN", "plate_thickness_mm", "hole_diameter_mm", "pin_diameter_mm"],
    },
)


@register(_padeye_check_spec, write=False)
async def run_rigging_padeye_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("load_kN", "plate_thickness_mm", "hole_diameter_mm", "pin_diameter_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "Fy_MPa" in a:
        kwargs["Fy_MPa"] = a["Fy_MPa"]
    if "Fu_MPa" in a:
        kwargs["Fu_MPa"] = a["Fu_MPa"]
    if "design_factor" in a:
        kwargs["design_factor"] = a["design_factor"]

    result = padeye_check(
        a["load_kN"],
        a["plate_thickness_mm"],
        a["hole_diameter_mm"],
        a["pin_diameter_mm"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_tip_over_two_crane
# ---------------------------------------------------------------------------

_tip_over_two_crane_spec = ToolSpec(
    name="rigging_tip_over_two_crane",
    description=(
        "Compute load share and tip-over check for a two-crane lift.\n"
        "\n"
        "Resolves vertical reactions at each crane hook by moment equilibrium "
        "about the opposite hook. Flags if either crane exceeds its rated "
        "capacity and if the CG is outside the two lift points (UNSTABLE).\n"
        "\n"
        "Returns crane_a_load_kg, crane_b_load_kg, utilisations, and "
        "cg_between_hooks.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "total_load_kg": {
                "type": "number",
                "description": "Total load (kg). Must be > 0.",
            },
            "crane_a_capacity_t": {
                "type": "number",
                "description": "Crane A capacity at its working radius (metric tonnes).",
            },
            "crane_b_capacity_t": {
                "type": "number",
                "description": "Crane B capacity at its working radius (metric tonnes).",
            },
            "lift_point_a_x": {
                "type": "number",
                "description": "X-position of Crane A lift point (m).",
            },
            "lift_point_b_x": {
                "type": "number",
                "description": "X-position of Crane B lift point (m). Must differ from A.",
            },
            "cg_x": {
                "type": "number",
                "description": "CG X-position (m).",
            },
        },
        "required": [
            "total_load_kg", "crane_a_capacity_t", "crane_b_capacity_t",
            "lift_point_a_x", "lift_point_b_x", "cg_x",
        ],
    },
)


@register(_tip_over_two_crane_spec, write=False)
async def run_rigging_tip_over_two_crane(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "total_load_kg", "crane_a_capacity_t", "crane_b_capacity_t",
        "lift_point_a_x", "lift_point_b_x", "cg_x",
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = tip_over_two_crane(
        a["total_load_kg"],
        a["crane_a_capacity_t"],
        a["crane_b_capacity_t"],
        a["lift_point_a_x"],
        a["lift_point_b_x"],
        a["cg_x"],
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rigging_crane_radius_interpolate
# ---------------------------------------------------------------------------

_crane_radius_interpolate_spec = ToolSpec(
    name="rigging_crane_radius_interpolate",
    description=(
        "Interpolate crane capacity from a radius–capacity chart table.\n"
        "\n"
        "Linearly interpolates between the two bounding table entries. "
        "Extrapolation beyond the maximum radius uses the minimum capacity "
        "(conservative — never extrapolate upward beyond the chart). "
        "A warning is issued when extrapolating.\n"
        "\n"
        "Returns capacity_t (metric tonnes) and capacity_kg.\n"
        "\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "radius_m": {
                "type": "number",
                "description": "Operating radius (m). Must be > 0.",
            },
            "chart_table": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": (
                    "Crane chart as list of [radius_m, capacity_t] pairs "
                    "(at least 2 entries, sorted by ascending radius). "
                    "Example: [[5, 40], [10, 25], [15, 18], [20, 13]]."
                ),
            },
        },
        "required": ["radius_m", "chart_table"],
    },
)


@register(_crane_radius_interpolate_spec, write=False)
async def run_rigging_crane_radius_interpolate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("radius_m") is None:
        return json.dumps({"ok": False, "reason": "radius_m is required"})
    if a.get("chart_table") is None:
        return json.dumps({"ok": False, "reason": "chart_table is required"})

    table = [tuple(row) for row in a["chart_table"]]
    result = crane_radius_interpolate(a["radius_m"], table)
    return ok_payload(result)
