"""
kerf_cad_core.turning.tools — LLM tool wrappers for lathe/turning CAM.

Registers six tools with the Kerf tool registry:

  turning_roughing_passes     — G71-equivalent OD roughing from a profile
  turning_finishing_pass      — G70-equivalent finish pass along profile
  turning_facing              — facing cycle (face-end)
  turning_parting             — parting / cut-off cycle
  turning_od_threading        — external thread (G76-style infeed schedule)
  turning_id_threading        — internal thread (G76-style infeed schedule)
  turning_grooving            — single/multi-step grooving cycle
  turning_cutting_params      — compute spindle RPM + feed per profile point

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
ISO 6983-1:2009 — Numerical control of machines — Part 1: general
Fanuc Series 0i-TF Operator's Manual (G71, G70, G76, G32)
Machinery's Handbook, 30th ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.turning.cycles import (
    roughing_passes,
    finishing_pass,
    facing_pass,
    parting_pass,
    od_threading,
    id_threading,
    grooving_pass,
    cutting_params,
    emit_gcode,
    TurningResult,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _result_payload(result: TurningResult) -> str:
    """Serialise a TurningResult to a JSON string suitable for the tool response."""
    if not result.ok:
        return json.dumps({"ok": False, "reason": result.reason})
    payload: dict = {
        "ok": True,
        "pass_count": len(result.passes),
        "passes": result.passes,
        "gcode_lines": len(result.gcode),
        "gcode": result.gcode,
        "warnings": result.warnings,
    }
    return json.dumps(payload)


def _parse(args: bytes) -> tuple[dict | None, str]:
    """Parse JSON bytes; returns (parsed_dict, error_str)."""
    try:
        return json.loads(args), ""
    except Exception as exc:
        return None, f"invalid args JSON: {exc}"


def _require(a: dict, *keys: str) -> str:
    """Return an error string for the first missing key, or '' if all present."""
    for k in keys:
        if a.get(k) is None:
            return f"{k} is required"
    return ""


def _profile_from_args(a: dict) -> tuple[list | None, str]:
    """Extract and lightly validate a profile from the args dict."""
    raw = a.get("profile")
    if raw is None:
        return None, "profile is required"
    if not isinstance(raw, list) or len(raw) < 2:
        return None, "profile must be a JSON array of at least 2 [Z, X] pairs"
    pts = []
    for i, pt in enumerate(raw):
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return None, f"profile[{i}] must be a [Z, X] pair"
        try:
            pts.append((float(pt[0]), float(pt[1])))
        except (TypeError, ValueError):
            return None, f"profile[{i}] contains non-numeric values"
    return pts, ""


# ---------------------------------------------------------------------------
# Tool: turning_cutting_params
# ---------------------------------------------------------------------------

_cutting_params_spec = ToolSpec(
    name="turning_cutting_params",
    description=(
        "Compute spindle RPM (constant surface speed) and feed rate (mm/min) for "
        "each point in a 2-D turning profile.\n"
        "\n"
        "Profile convention: list of [Z, X] pairs where Z is the axial position "
        "(mm, positive towards tailstock) and X is the radius in mm (not diameter).\n"
        "\n"
        "Returns per-point dict with z_mm, x_mm, diameter_mm, rpm, feed_mm_min.\n"
        "\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "profile": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": "List of [Z, X] pairs. Z = axial mm; X = radius mm.",
                "minItems": 1,
            },
            "css_m_per_min": {
                "type": "number",
                "description": "Constant surface speed in m/min. Default 180.",
            },
            "feed_mm_rev": {
                "type": "number",
                "description": "Feed per revolution in mm/rev. Default 0.20.",
            },
            "rpm_min": {
                "type": "number",
                "description": "Minimum spindle RPM. Default 50.",
            },
            "rpm_max": {
                "type": "number",
                "description": "Maximum spindle RPM. Default 3500.",
            },
        },
        "required": ["profile"],
    },
)


@register(_cutting_params_spec, write=False)
async def run_turning_cutting_params(ctx: ProjectCtx, args: bytes) -> str:
    a, parse_err = _parse(args)
    if parse_err:
        return err_payload(parse_err, "BAD_ARGS")

    profile, perr = _profile_from_args(a)
    if perr:
        return err_payload(perr, "BAD_ARGS")

    kwargs: dict = {}
    for k in ("css_m_per_min", "feed_mm_rev", "rpm_min", "rpm_max"):
        if k in a:
            kwargs[k] = a[k]

    result = cutting_params(profile, **kwargs)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: turning_roughing_passes
# ---------------------------------------------------------------------------

_roughing_spec = ToolSpec(
    name="turning_roughing_passes",
    description=(
        "Generate G71-equivalent OD roughing passes from a 2-D turning profile.\n"
        "\n"
        "Starting from the stock OD radius, generates successive axial passes "
        "stepping inward by depth-of-cut until the profile contour (plus a finish "
        "allowance) is reached.  Returns ISO G-code lines and per-pass metadata.\n"
        "\n"
        "Profile: list of [Z, X] pairs (Z axial mm, X radius mm, monotone Z).\n"
        "\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "profile": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": "2-D profile as list of [Z_mm, X_radius_mm] pairs.",
                "minItems": 2,
            },
            "stock_x_mm": {
                "type": "number",
                "description": "Initial stock radius (mm). Must be > max profile X.",
            },
            "doc_mm": {
                "type": "number",
                "description": "Radial depth of cut per pass (mm). Default 2.0.",
            },
            "css_m_per_min": {
                "type": "number",
                "description": "Constant surface speed (m/min). Default 180.",
            },
            "feed_mm_rev": {
                "type": "number",
                "description": "Feed per revolution (mm/rev). Default 0.20.",
            },
            "rpm_min": {"type": "number", "description": "Min RPM. Default 50."},
            "rpm_max": {"type": "number", "description": "Max RPM. Default 3500."},
            "retract_mm": {
                "type": "number",
                "description": "Rapid clearance (mm). Default 2.0.",
            },
            "finish_allowance_mm": {
                "type": "number",
                "description": "Radial material left for finishing pass (mm). Default 0.3.",
            },
        },
        "required": ["profile", "stock_x_mm"],
    },
)


@register(_roughing_spec, write=False)
async def run_turning_roughing_passes(ctx: ProjectCtx, args: bytes) -> str:
    a, parse_err = _parse(args)
    if parse_err:
        return err_payload(parse_err, "BAD_ARGS")

    profile, perr = _profile_from_args(a)
    if perr:
        return err_payload(perr, "BAD_ARGS")

    if a.get("stock_x_mm") is None:
        return err_payload("stock_x_mm is required", "BAD_ARGS")

    kwargs: dict = {}
    for k in ("doc_mm", "css_m_per_min", "feed_mm_rev", "rpm_min", "rpm_max",
               "retract_mm", "finish_allowance_mm"):
        if k in a:
            kwargs[k] = a[k]

    result = roughing_passes(profile, a["stock_x_mm"], **kwargs)
    return _result_payload(result)


# ---------------------------------------------------------------------------
# Tool: turning_finishing_pass
# ---------------------------------------------------------------------------

_finishing_spec = ToolSpec(
    name="turning_finishing_pass",
    description=(
        "Generate a G70-equivalent finishing pass that follows the exact 2-D "
        "turning profile at a fine feed rate.\n"
        "\n"
        "RPM is computed per-segment using constant surface speed.\n"
        "Returns ISO G-code lines and pass metadata.\n"
        "\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "profile": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": "2-D profile as list of [Z_mm, X_radius_mm] pairs.",
                "minItems": 2,
            },
            "css_m_per_min": {
                "type": "number",
                "description": "Constant surface speed (m/min). Default 180.",
            },
            "feed_mm_rev": {
                "type": "number",
                "description": "Finishing feed (mm/rev). Default 0.08.",
            },
            "rpm_min": {"type": "number"},
            "rpm_max": {"type": "number"},
            "retract_mm": {"type": "number"},
            "doc_mm": {
                "type": "number",
                "description": "Finishing depth of cut for metadata. Default 0.25.",
            },
        },
        "required": ["profile"],
    },
)


@register(_finishing_spec, write=False)
async def run_turning_finishing_pass(ctx: ProjectCtx, args: bytes) -> str:
    a, parse_err = _parse(args)
    if parse_err:
        return err_payload(parse_err, "BAD_ARGS")

    profile, perr = _profile_from_args(a)
    if perr:
        return err_payload(perr, "BAD_ARGS")

    kwargs: dict = {}
    for k in ("css_m_per_min", "feed_mm_rev", "rpm_min", "rpm_max", "retract_mm", "doc_mm"):
        if k in a:
            kwargs[k] = a[k]

    result = finishing_pass(profile, **kwargs)
    return _result_payload(result)


# ---------------------------------------------------------------------------
# Tool: turning_facing
# ---------------------------------------------------------------------------

_facing_spec = ToolSpec(
    name="turning_facing",
    description=(
        "Generate a facing cycle that cuts the end face of the workpiece.\n"
        "\n"
        "The tool feeds from the OD (x_max_mm) inward to the bore or spindle "
        "centreline at the specified Z position.  Multiple passes step the face "
        "back axially by doc_mm per pass.\n"
        "\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "x_max_mm": {
                "type": "number",
                "description": "Outer radius at the face (mm). Must be > 0.",
            },
            "z_face_mm": {
                "type": "number",
                "description": "Axial position of the face to be cut (mm).",
            },
            "doc_mm": {
                "type": "number",
                "description": "Axial depth of cut per pass (mm). Default 2.0.",
            },
            "n_passes": {
                "type": "integer",
                "description": "Number of facing passes. Default 1.",
                "minimum": 1,
            },
            "css_m_per_min": {"type": "number", "description": "Surface speed (m/min)."},
            "feed_mm_rev": {"type": "number", "description": "Feed per rev (mm/rev)."},
            "rpm_min": {"type": "number"},
            "rpm_max": {"type": "number"},
            "retract_mm": {"type": "number"},
            "bore_radius_mm": {
                "type": "number",
                "description": "Inner bore radius (stop before). Default 0 (through-centre).",
            },
        },
        "required": ["x_max_mm", "z_face_mm"],
    },
)


@register(_facing_spec, write=False)
async def run_turning_facing(ctx: ProjectCtx, args: bytes) -> str:
    a, parse_err = _parse(args)
    if parse_err:
        return err_payload(parse_err, "BAD_ARGS")

    err = _require(a, "x_max_mm", "z_face_mm")
    if err:
        return err_payload(err, "BAD_ARGS")

    kwargs: dict = {}
    for k in ("doc_mm", "n_passes", "css_m_per_min", "feed_mm_rev",
               "rpm_min", "rpm_max", "retract_mm", "bore_radius_mm"):
        if k in a:
            kwargs[k] = a[k]

    result = facing_pass(a["x_max_mm"], a["z_face_mm"], **kwargs)
    return _result_payload(result)


# ---------------------------------------------------------------------------
# Tool: turning_parting
# ---------------------------------------------------------------------------

_parting_spec = ToolSpec(
    name="turning_parting",
    description=(
        "Generate a parting (cut-off) cycle at a specified Z position.\n"
        "\n"
        "Feeds a parting blade inward from the OD to the bore or spindle "
        "centreline.  Optional peck parting for deeper cuts.\n"
        "\n"
        "Recommended CSS: 60-100 m/min; feed: 0.03-0.08 mm/rev.\n"
        "\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "z_part_mm": {
                "type": "number",
                "description": "Axial position of the parting cut (mm).",
            },
            "x_max_mm": {
                "type": "number",
                "description": "Outer radius at cut location (mm). Must be > 0.",
            },
            "css_m_per_min": {
                "type": "number",
                "description": "Surface speed (m/min). Default 80 (lower for parting).",
            },
            "feed_mm_rev": {
                "type": "number",
                "description": "Feed per rev (mm/rev). Default 0.05.",
            },
            "rpm_min": {"type": "number"},
            "rpm_max": {
                "type": "number",
                "description": "Max RPM (default 1200 — limited for parting).",
            },
            "retract_mm": {"type": "number"},
            "bore_radius_mm": {
                "type": "number",
                "description": "Stop radius for hollow workpiece. Default 0.",
            },
            "peck_depth_mm": {
                "type": "number",
                "description": "Peck depth increment for deep/interrupted cuts (mm). Omit for single plunge.",
            },
        },
        "required": ["z_part_mm", "x_max_mm"],
    },
)


@register(_parting_spec, write=False)
async def run_turning_parting(ctx: ProjectCtx, args: bytes) -> str:
    a, parse_err = _parse(args)
    if parse_err:
        return err_payload(parse_err, "BAD_ARGS")

    err = _require(a, "z_part_mm", "x_max_mm")
    if err:
        return err_payload(err, "BAD_ARGS")

    kwargs: dict = {}
    for k in ("css_m_per_min", "feed_mm_rev", "rpm_min", "rpm_max",
               "retract_mm", "bore_radius_mm", "peck_depth_mm"):
        if k in a:
            kwargs[k] = a[k]

    result = parting_pass(a["z_part_mm"], a["x_max_mm"], **kwargs)
    return _result_payload(result)


# ---------------------------------------------------------------------------
# Tool: turning_od_threading
# ---------------------------------------------------------------------------

_od_thread_spec = ToolSpec(
    name="turning_od_threading",
    description=(
        "Generate an external (OD) threading cycle using a G76-style degressive "
        "infeed schedule.\n"
        "\n"
        "Produces G32 constant-lead thread cuts with compound infeed at "
        "'infeed_deg' degrees (default 29.5° for 60° threads).  Thread depth "
        "defaults to 0.6495 × pitch for ISO/metric threads.\n"
        "\n"
        "Returns G-code and per-pass metadata including cumulative depth and "
        "spring pass flags.\n"
        "\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "z_start_mm": {
                "type": "number",
                "description": "Thread start Z (approach end), mm.",
            },
            "z_end_mm": {
                "type": "number",
                "description": "Thread end Z (relief end), mm.  z_end != z_start.",
            },
            "x_major_mm": {
                "type": "number",
                "description": "Major diameter radius (OD), mm.",
            },
            "pitch_mm": {
                "type": "number",
                "description": "Thread pitch (mm). Default 1.5.",
            },
            "thread_depth_mm": {
                "type": "number",
                "description": "Full radial thread depth (mm). Default: 0.6495 × pitch.",
            },
            "infeed_deg": {
                "type": "number",
                "description": "Compound infeed angle (degrees). Default 29.5° (60° thread).",
            },
            "first_pass_depth_mm": {
                "type": "number",
                "description": "First pass radial depth (mm). Default 0.3.",
            },
            "min_pass_depth_mm": {
                "type": "number",
                "description": "Minimum pass depth for degression (mm). Default 0.05.",
            },
            "spring_passes": {
                "type": "integer",
                "description": "Number of no-feed spring passes at full depth. Default 2.",
                "minimum": 0,
            },
            "css_m_per_min": {
                "type": "number",
                "description": "Surface speed (m/min). Default 100 for threading.",
            },
            "rpm_min": {"type": "number"},
            "rpm_max": {
                "type": "number",
                "description": "Max threading RPM (default 800).",
            },
            "retract_mm": {"type": "number"},
        },
        "required": ["z_start_mm", "z_end_mm", "x_major_mm"],
    },
)


@register(_od_thread_spec, write=False)
async def run_turning_od_threading(ctx: ProjectCtx, args: bytes) -> str:
    a, parse_err = _parse(args)
    if parse_err:
        return err_payload(parse_err, "BAD_ARGS")

    err = _require(a, "z_start_mm", "z_end_mm", "x_major_mm")
    if err:
        return err_payload(err, "BAD_ARGS")

    kwargs: dict = {}
    for k in ("pitch_mm", "thread_depth_mm", "infeed_deg", "first_pass_depth_mm",
               "min_pass_depth_mm", "spring_passes", "css_m_per_min",
               "rpm_min", "rpm_max", "retract_mm"):
        if k in a:
            kwargs[k] = a[k]

    result = od_threading(a["z_start_mm"], a["z_end_mm"], a["x_major_mm"], **kwargs)
    return _result_payload(result)


# ---------------------------------------------------------------------------
# Tool: turning_id_threading
# ---------------------------------------------------------------------------

_id_thread_spec = ToolSpec(
    name="turning_id_threading",
    description=(
        "Generate an internal (ID/bore) threading cycle using a G76-style "
        "degressive infeed schedule.\n"
        "\n"
        "Mirror of turning_od_threading for bores: the tool starts at the minor "
        "radius and moves outward (+X) with each pass.\n"
        "\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "z_start_mm": {
                "type": "number",
                "description": "Thread start Z (approach end), mm.",
            },
            "z_end_mm": {
                "type": "number",
                "description": "Thread end Z, mm.  z_end != z_start.",
            },
            "x_minor_mm": {
                "type": "number",
                "description": "Bore (minor) radius before threading, mm.",
            },
            "pitch_mm": {
                "type": "number",
                "description": "Thread pitch (mm). Default 1.5.",
            },
            "thread_depth_mm": {
                "type": "number",
                "description": "Full radial thread depth (mm). Default: 0.6495 × pitch.",
            },
            "infeed_deg": {
                "type": "number",
                "description": "Compound infeed angle (degrees). Default 29.5°.",
            },
            "first_pass_depth_mm": {
                "type": "number",
                "description": "First pass depth (mm). Default 0.2.",
            },
            "min_pass_depth_mm": {
                "type": "number",
                "description": "Minimum pass depth (mm). Default 0.03.",
            },
            "spring_passes": {
                "type": "integer",
                "description": "Spring passes at full depth. Default 2.",
                "minimum": 0,
            },
            "css_m_per_min": {"type": "number"},
            "rpm_min": {"type": "number"},
            "rpm_max": {"type": "number"},
            "retract_mm": {"type": "number"},
        },
        "required": ["z_start_mm", "z_end_mm", "x_minor_mm"],
    },
)


@register(_id_thread_spec, write=False)
async def run_turning_id_threading(ctx: ProjectCtx, args: bytes) -> str:
    a, parse_err = _parse(args)
    if parse_err:
        return err_payload(parse_err, "BAD_ARGS")

    err = _require(a, "z_start_mm", "z_end_mm", "x_minor_mm")
    if err:
        return err_payload(err, "BAD_ARGS")

    kwargs: dict = {}
    for k in ("pitch_mm", "thread_depth_mm", "infeed_deg", "first_pass_depth_mm",
               "min_pass_depth_mm", "spring_passes", "css_m_per_min",
               "rpm_min", "rpm_max", "retract_mm"):
        if k in a:
            kwargs[k] = a[k]

    result = id_threading(a["z_start_mm"], a["z_end_mm"], a["x_minor_mm"], **kwargs)
    return _result_payload(result)


# ---------------------------------------------------------------------------
# Tool: turning_grooving
# ---------------------------------------------------------------------------

_grooving_spec = ToolSpec(
    name="turning_grooving",
    description=(
        "Generate a grooving (recessing) cycle.\n"
        "\n"
        "Cuts a groove of specified width and depth centred at z_center_mm, "
        "starting from x_start_mm (OD).  If the groove is wider than the tool, "
        "multiple overlapping plunges are generated automatically.\n"
        "\n"
        "Optional peck grooving for deep grooves.\n"
        "\n"
        "Errors: {ok:false, reason} — never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "z_center_mm": {
                "type": "number",
                "description": "Axial centre of the groove (mm).",
            },
            "x_start_mm": {
                "type": "number",
                "description": "OD radius at groove location (mm).",
            },
            "groove_depth_mm": {
                "type": "number",
                "description": "Radial depth of groove (mm). Default 2.0.",
            },
            "groove_width_mm": {
                "type": "number",
                "description": "Total axial width of groove (mm). Default 3.0.",
            },
            "tool_width_mm": {
                "type": "number",
                "description": "Grooving insert width (mm). Default 3.0.",
            },
            "css_m_per_min": {
                "type": "number",
                "description": "Surface speed (m/min). Default 100.",
            },
            "feed_mm_rev": {
                "type": "number",
                "description": "Feed per rev (mm/rev). Default 0.05.",
            },
            "rpm_min": {"type": "number"},
            "rpm_max": {"type": "number"},
            "retract_mm": {"type": "number"},
            "peck_depth_mm": {
                "type": "number",
                "description": "Peck increment for deep grooves (mm). Omit for direct plunge.",
            },
        },
        "required": ["z_center_mm", "x_start_mm"],
    },
)


@register(_grooving_spec, write=False)
async def run_turning_grooving(ctx: ProjectCtx, args: bytes) -> str:
    a, parse_err = _parse(args)
    if parse_err:
        return err_payload(parse_err, "BAD_ARGS")

    err = _require(a, "z_center_mm", "x_start_mm")
    if err:
        return err_payload(err, "BAD_ARGS")

    kwargs: dict = {}
    for k in ("groove_depth_mm", "groove_width_mm", "tool_width_mm",
               "css_m_per_min", "feed_mm_rev", "rpm_min", "rpm_max",
               "retract_mm", "peck_depth_mm"):
        if k in a:
            kwargs[k] = a[k]

    result = grooving_pass(a["z_center_mm"], a["x_start_mm"], **kwargs)
    return _result_payload(result)
