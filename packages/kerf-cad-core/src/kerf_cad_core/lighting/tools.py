"""
kerf_cad_core.lighting.tools — LLM tool wrappers for illumination engineering.

Registers tools with the Kerf tool registry:

  lighting_room_cavity_ratio        — RCR for zonal-cavity method
  lighting_coefficient_of_utilization — CU interpolation from table vs RCR & reflectances
  lighting_light_loss_factor         — LLF from LLD × LDD × ballast × temperature
  lighting_luminaires_for_target_lux — number of luminaires for target maintained lux
  lighting_lux_from_luminaires       — average lux from a given number of luminaires
  lighting_spacing_mh_ratio          — spacing-to-mounting-height ratio + uniformity check
  lighting_uniformity_check          — E_min / E_avg uniformity ratio
  lighting_horizontal_illuminance    — point method: horizontal illuminance (inverse-square)
  lighting_vertical_illuminance      — point method: vertical illuminance
  lighting_multi_luminaire           — superposition from multiple luminaires
  lighting_luminance                 — luminance of a Lambertian surface from illuminance
  lighting_exitance                  — luminous exitance of a Lambertian surface
  lighting_contrast_ratio            — Weber contrast ratio
  lighting_ugr                       — CIE simplified Unified Glare Rating
  lighting_road_luminance            — road surface luminance (R-table model)
  lighting_pole_spacing              — roadway pole spacing from S/H ratio
  lighting_roadway_utilization       — average road lux + luminance (luminance method)
  lighting_emergency_lux             — floor-level illuminance below emergency luminaire
  lighting_emergency_spacing         — max spacing for emergency luminaires
  lighting_lamp_lpw                  — luminous efficacy by lamp type
  lighting_lamp_energy               — lamp energy consumption
  lighting_lpd_check                 — LPD vs ASHRAE/Title-24 allowance

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
IES Lighting Handbook, 10th ed. (IESNA, 2011)
CIE 117-1995 — Discomfort Glare in Interior Lighting
EN 12464-1:2021 — Light and Lighting
ASHRAE 90.1-2022, §9 — Lighting

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.lighting.design import (
    room_cavity_ratio,
    coefficient_of_utilization,
    light_loss_factor,
    luminaires_for_target_lux,
    lux_from_luminaires,
    spacing_to_mounting_height_ratio,
    uniformity_check,
    horizontal_illuminance,
    vertical_illuminance,
    multi_luminaire_illuminance,
    luminance_from_illuminance,
    exitance,
    contrast_ratio,
    ugr,
    road_luminance,
    pole_spacing,
    roadway_utilization,
    emergency_lux_at_floor,
    emergency_spacing,
    lamp_lumens_per_watt,
    lamp_energy,
    lpd_check,
)


# ---------------------------------------------------------------------------
# Tool: lighting_room_cavity_ratio
# ---------------------------------------------------------------------------

_rcr_spec = ToolSpec(
    name="lighting_room_cavity_ratio",
    description=(
        "Compute the Room Cavity Ratio (RCR) for use in the IES zonal-cavity "
        "lumen method.\n"
        "\n"
        "RCR = 5 × h_cavity × (length + width) / (length × width)\n"
        "\n"
        "A higher RCR indicates a deeper, narrower room (lower CU); "
        "RCR 0 = infinite open space; RCR 10 = very deep/narrow cavity.\n"
        "\n"
        "Errors: {ok:false, reason} for non-positive dimensions.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "length_m": {
                "type": "number",
                "description": "Room length (m). Must be > 0.",
            },
            "width_m": {
                "type": "number",
                "description": "Room width (m). Must be > 0.",
            },
            "height_cavity_m": {
                "type": "number",
                "description": (
                    "Cavity height from the work-plane to the luminaire plane (m). "
                    "Must be > 0."
                ),
            },
        },
        "required": ["length_m", "width_m", "height_cavity_m"],
    },
)


@register(_rcr_spec, write=False)
async def run_lighting_room_cavity_ratio(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("length_m", "width_m", "height_cavity_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = room_cavity_ratio(a["length_m"], a["width_m"], a["height_cavity_m"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_coefficient_of_utilization
# ---------------------------------------------------------------------------

_cu_spec = ToolSpec(
    name="lighting_coefficient_of_utilization",
    description=(
        "Interpolate the Coefficient of Utilization (CU) from the built-in "
        "IES representative CU table for a given RCR and room reflectances.\n"
        "\n"
        "CU represents the fraction of lamp lumens that actually reach the "
        "work-plane.  The nearest table key is selected for rho_ceiling and "
        "rho_walls; RCR is linearly interpolated between integer values.\n"
        "\n"
        "Returns cu (0–1), the RCR used, and the reflectance key applied.\n"
        "\n"
        "Errors: {ok:false, reason} for out-of-range inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "rcr": {
                "type": "number",
                "description": "Room Cavity Ratio (0–10). Use lighting_room_cavity_ratio to compute.",
            },
            "rho_ceiling_pct": {
                "type": "integer",
                "description": (
                    "Effective ceiling cavity reflectance (%, 0–100). "
                    "Typical: 80 for white, 50 for medium, 10 for dark. Default 70."
                ),
            },
            "rho_walls_pct": {
                "type": "integer",
                "description": (
                    "Wall reflectance (%, 0–100). "
                    "Typical: 50 for medium, 30 for darker walls. Default 50."
                ),
            },
        },
        "required": ["rcr"],
    },
)


@register(_cu_spec, write=False)
async def run_lighting_cu(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("rcr") is None:
        return json.dumps({"ok": False, "reason": "rcr is required"})

    kwargs: dict = {}
    if "rho_ceiling_pct" in a:
        kwargs["rho_ceiling_pct"] = int(a["rho_ceiling_pct"])
    if "rho_walls_pct" in a:
        kwargs["rho_walls_pct"] = int(a["rho_walls_pct"])

    result = coefficient_of_utilization(a["rcr"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_light_loss_factor
# ---------------------------------------------------------------------------

_llf_spec = ToolSpec(
    name="lighting_light_loss_factor",
    description=(
        "Compute the total Light Loss Factor (LLF) for use in the lumen method.\n"
        "\n"
        "LLF = LLD × LDD × ballast_factor × temperature_factor\n"
        "\n"
        "  LLD  — Lamp Lumen Depreciation: lumen output at end-of-life / initial "
        "         (typical 0.80–0.90 for LED, 0.70–0.85 for fluorescent).\n"
        "  LDD  — Luminaire Dirt Depreciation: effect of dust/dirt accumulation "
        "         (typical 0.85–0.95 for clean office environments).\n"
        "  ballast_factor — electronic ballast factor (1.00 for LED drivers).\n"
        "  temperature_factor — correction for ambient temperature (1.00 typical).\n"
        "\n"
        "Typical combined LLF: 0.70–0.80.\n"
        "\n"
        "Errors: {ok:false, reason} for non-positive factors.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "lld": {
                "type": "number",
                "description": "Lamp Lumen Depreciation factor (0 < lld ≤ 1, default 0.85).",
            },
            "ldd": {
                "type": "number",
                "description": "Luminaire Dirt Depreciation factor (0 < ldd ≤ 1, default 0.90).",
            },
            "ballast_factor": {
                "type": "number",
                "description": "Ballast/driver factor (default 1.0).",
            },
            "temperature_factor": {
                "type": "number",
                "description": "Ambient temperature correction factor (default 1.0).",
            },
        },
        "required": [],
    },
)


@register(_llf_spec, write=False)
async def run_lighting_llf(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    kwargs: dict = {}
    for key in ("lld", "ldd", "ballast_factor", "temperature_factor"):
        if key in a:
            kwargs[key] = a[key]

    result = light_loss_factor(**kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_luminaires_for_target_lux
# ---------------------------------------------------------------------------

_n_lum_spec = ToolSpec(
    name="lighting_luminaires_for_target_lux",
    description=(
        "Calculate the number of luminaires needed to achieve a target maintained "
        "illuminance using the IES zonal-cavity lumen method.\n"
        "\n"
        "N = ⌈(E × A) / (Φ_lamp × n_lamps × CU × LLF)⌉\n"
        "\n"
        "Also returns the actual average lux achievable with the rounded-up count.\n"
        "\n"
        "Workflow: compute RCR → CU → LLF → call this tool.\n"
        "\n"
        "Warnings: under-lit if actual lux < target.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "area_m2": {
                "type": "number",
                "description": "Room floor area (m²). Must be > 0.",
            },
            "target_lux": {
                "type": "number",
                "description": "Target maintained average illuminance (lx). Must be > 0.",
            },
            "lumens_per_lamp": {
                "type": "number",
                "description": "Initial lamp lumens per lamp (lm). Must be > 0.",
            },
            "lamps_per_luminaire": {
                "type": "integer",
                "description": "Number of lamps per luminaire (default 1).",
            },
            "cu": {
                "type": "number",
                "description": (
                    "Coefficient of Utilization (default 0.65). "
                    "Use lighting_coefficient_of_utilization to obtain."
                ),
            },
            "llf": {
                "type": "number",
                "description": (
                    "Light Loss Factor (default 0.80). "
                    "Use lighting_light_loss_factor to obtain."
                ),
            },
        },
        "required": ["area_m2", "target_lux", "lumens_per_lamp"],
    },
)


@register(_n_lum_spec, write=False)
async def run_lighting_n_luminaires(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("area_m2", "target_lux", "lumens_per_lamp"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for key in ("lamps_per_luminaire", "cu", "llf"):
        if key in a:
            kwargs[key] = a[key]

    result = luminaires_for_target_lux(
        a["area_m2"], a["target_lux"], a["lumens_per_lamp"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_lux_from_luminaires
# ---------------------------------------------------------------------------

_lux_from_n_spec = ToolSpec(
    name="lighting_lux_from_luminaires",
    description=(
        "Calculate the average maintained illuminance from a given number of "
        "luminaires using the IES lumen method.\n"
        "\n"
        "E = (N × Φ_lamp × n_lamps × CU × LLF) / A\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "n_luminaires": {
                "type": "integer",
                "description": "Number of luminaires installed. Must be >= 0.",
            },
            "lumens_per_lamp": {
                "type": "number",
                "description": "Initial lamp lumens (lm). Must be > 0.",
            },
            "lamps_per_luminaire": {
                "type": "integer",
                "description": "Lamps per luminaire (default 1).",
            },
            "cu": {
                "type": "number",
                "description": "Coefficient of Utilization (default 0.65).",
            },
            "llf": {
                "type": "number",
                "description": "Light Loss Factor (default 0.80).",
            },
            "area_m2": {
                "type": "number",
                "description": "Room floor area (m²). Must be > 0.",
            },
        },
        "required": ["n_luminaires", "lumens_per_lamp", "area_m2"],
    },
)


@register(_lux_from_n_spec, write=False)
async def run_lighting_lux_from_n(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("n_luminaires", "lumens_per_lamp", "area_m2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for key in ("lamps_per_luminaire", "cu", "llf"):
        if key in a:
            kwargs[key] = a[key]

    result = lux_from_luminaires(
        a["n_luminaires"], a["lumens_per_lamp"],
        area_m2=a["area_m2"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_spacing_mh_ratio
# ---------------------------------------------------------------------------

_smh_spec = ToolSpec(
    name="lighting_spacing_mh_ratio",
    description=(
        "Compute the spacing-to-mounting-height (S/MH) ratio for luminaires.\n"
        "\n"
        "IES recommends S/MH ≤ the luminaire's rated maximum (typically 1.0–1.5 "
        "for most direct luminaires).  Values > 1.5 indicate likely poor uniformity.\n"
        "\n"
        "Warnings: poor-uniformity if S/MH > 1.5.\n"
        "\n"
        "Errors: {ok:false, reason} for non-positive inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "spacing_m": {
                "type": "number",
                "description": "Centre-to-centre luminaire spacing (m). Must be > 0.",
            },
            "mounting_height_m": {
                "type": "number",
                "description": "Luminaire mounting height above work-plane (m). Must be > 0.",
            },
        },
        "required": ["spacing_m", "mounting_height_m"],
    },
)


@register(_smh_spec, write=False)
async def run_lighting_smh(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("spacing_m", "mounting_height_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = spacing_to_mounting_height_ratio(a["spacing_m"], a["mounting_height_m"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_uniformity_check
# ---------------------------------------------------------------------------

_uniformity_spec = ToolSpec(
    name="lighting_uniformity_check",
    description=(
        "Check illuminance uniformity ratio U = E_min / E_avg.\n"
        "\n"
        "EN 12464-1 requires U ≥ 0.70 for task areas; roadways typically require "
        "U ≥ 0.40.  Set uniformity_limit accordingly.\n"
        "\n"
        "Warnings: poor-uniformity if U < uniformity_limit.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "min_lux": {
                "type": "number",
                "description": "Minimum point illuminance (lx). Must be >= 0.",
            },
            "avg_lux": {
                "type": "number",
                "description": "Average maintained illuminance (lx). Must be > 0.",
            },
            "uniformity_limit": {
                "type": "number",
                "description": (
                    "Minimum acceptable uniformity ratio (default 0.70 per EN 12464-1)."
                ),
            },
        },
        "required": ["min_lux", "avg_lux"],
    },
)


@register(_uniformity_spec, write=False)
async def run_lighting_uniformity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("min_lux", "avg_lux"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "uniformity_limit" in a:
        kwargs["uniformity_limit"] = a["uniformity_limit"]

    result = uniformity_check(a["min_lux"], a["avg_lux"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_horizontal_illuminance
# ---------------------------------------------------------------------------

_eh_spec = ToolSpec(
    name="lighting_horizontal_illuminance",
    description=(
        "Compute horizontal illuminance at a point from a single point source "
        "using the IES inverse-square cosine law.\n"
        "\n"
        "E_h = I × cos(θ) / d²\n"
        "\n"
        "where d is the slant distance from luminaire to point, and θ is the "
        "angle from the luminaire's nadir (vertical downward direction).\n"
        "\n"
        "Returns e_horizontal_lux and the computed mounting height component.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "intensity_cd": {
                "type": "number",
                "description": "Luminous intensity in direction of the point (cd). Must be >= 0.",
            },
            "distance_m": {
                "type": "number",
                "description": "Slant distance from luminaire to point (m). Must be > 0.",
            },
            "angle_from_nadir_deg": {
                "type": "number",
                "description": (
                    "Angle from nadir (θ), degrees (-90 < θ < 90). "
                    "0 = directly below the luminaire.  Default 0."
                ),
            },
        },
        "required": ["intensity_cd", "distance_m"],
    },
)


@register(_eh_spec, write=False)
async def run_lighting_eh(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("intensity_cd", "distance_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "angle_from_nadir_deg" in a:
        kwargs["angle_from_nadir_deg"] = a["angle_from_nadir_deg"]

    result = horizontal_illuminance(a["intensity_cd"], a["distance_m"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_vertical_illuminance
# ---------------------------------------------------------------------------

_ev_spec = ToolSpec(
    name="lighting_vertical_illuminance",
    description=(
        "Compute vertical illuminance at a point from a single point source.\n"
        "\n"
        "E_v = I × sin(θ) × cos(θ) / d²\n"
        "\n"
        "Useful for façade, signage, and task illuminance on a vertical surface.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "intensity_cd": {
                "type": "number",
                "description": "Luminous intensity (cd). Must be >= 0.",
            },
            "distance_m": {
                "type": "number",
                "description": "Slant distance from luminaire to point (m). Must be > 0.",
            },
            "angle_from_nadir_deg": {
                "type": "number",
                "description": "Angle from nadir θ, degrees [0, 90].",
            },
        },
        "required": ["intensity_cd", "distance_m", "angle_from_nadir_deg"],
    },
)


@register(_ev_spec, write=False)
async def run_lighting_ev(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("intensity_cd", "distance_m", "angle_from_nadir_deg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = vertical_illuminance(
        a["intensity_cd"], a["distance_m"], a["angle_from_nadir_deg"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_multi_luminaire
# ---------------------------------------------------------------------------

_multi_spec = ToolSpec(
    name="lighting_multi_luminaire",
    description=(
        "Compute total illuminance at a point by superposition of contributions "
        "from multiple luminaires (point method).\n"
        "\n"
        "Each luminaire: {\"x\": m, \"y\": m, \"z\": m, \"intensity_cd\": cd}\n"
        "Target point:   {\"x\": m, \"y\": m, \"z\": m}\n"
        "\n"
        "plane = 'horizontal' (default) or 'vertical'.\n"
        "\n"
        "Returns total_lux and per-luminaire contributions.\n"
        "\n"
        "Warnings: very low total lux.\n"
        "\n"
        "Errors: {ok:false, reason} for empty list or invalid plane.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "luminaires": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number"},
                        "intensity_cd": {"type": "number"},
                    },
                    "required": ["x", "y", "z", "intensity_cd"],
                },
                "description": "List of luminaire positions (m) and intensities (cd).",
            },
            "point": {
                "type": "object",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number"},
                },
                "description": "Target point coordinates (m).",
            },
            "plane": {
                "type": "string",
                "enum": ["horizontal", "vertical"],
                "description": "Illuminance plane: 'horizontal' (default) or 'vertical'.",
            },
        },
        "required": ["luminaires", "point"],
    },
)


@register(_multi_spec, write=False)
async def run_lighting_multi(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("luminaires") is None:
        return json.dumps({"ok": False, "reason": "luminaires is required"})
    if a.get("point") is None:
        return json.dumps({"ok": False, "reason": "point is required"})

    kwargs: dict = {}
    if "plane" in a:
        kwargs["plane"] = a["plane"]

    result = multi_luminaire_illuminance(a["luminaires"], a["point"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_luminance
# ---------------------------------------------------------------------------

_lum_spec = ToolSpec(
    name="lighting_luminance",
    description=(
        "Compute the luminance of a perfectly diffuse (Lambertian) surface.\n"
        "\n"
        "L = E × ρ / π   [cd/m²]\n"
        "\n"
        "Parameters\n"
        "----------\n"
        "illuminance_lux : incident illuminance on the surface (lx).\n"
        "reflectance     : surface reflectance ρ (0–1).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "illuminance_lux": {
                "type": "number",
                "description": "Incident illuminance (lx). Must be >= 0.",
            },
            "reflectance": {
                "type": "number",
                "description": "Surface reflectance ρ (0–1).",
            },
        },
        "required": ["illuminance_lux", "reflectance"],
    },
)


@register(_lum_spec, write=False)
async def run_lighting_luminance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("illuminance_lux", "reflectance"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = luminance_from_illuminance(a["illuminance_lux"], a["reflectance"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_exitance
# ---------------------------------------------------------------------------

_exit_spec = ToolSpec(
    name="lighting_exitance",
    description=(
        "Compute the luminous exitance of a Lambertian surface.\n"
        "\n"
        "M = E × ρ   [lm/m²]\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "illuminance_lux": {
                "type": "number",
                "description": "Incident illuminance (lx). Must be >= 0.",
            },
            "reflectance": {
                "type": "number",
                "description": "Surface reflectance ρ (0–1).",
            },
        },
        "required": ["illuminance_lux", "reflectance"],
    },
)


@register(_exit_spec, write=False)
async def run_lighting_exitance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("illuminance_lux", "reflectance"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = exitance(a["illuminance_lux"], a["reflectance"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_contrast_ratio
# ---------------------------------------------------------------------------

_contrast_spec = ToolSpec(
    name="lighting_contrast_ratio",
    description=(
        "Compute Weber contrast ratio C = (L_task - L_bg) / L_bg.\n"
        "\n"
        "Positive = task brighter than background; negative = task darker.\n"
        "Good legibility typically requires |C| ≥ 0.3.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "luminance_task": {
                "type": "number",
                "description": "Task luminance (cd/m²). Must be >= 0.",
            },
            "luminance_background": {
                "type": "number",
                "description": "Background luminance (cd/m²). Must be > 0.",
            },
        },
        "required": ["luminance_task", "luminance_background"],
    },
)


@register(_contrast_spec, write=False)
async def run_lighting_contrast(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("luminance_task", "luminance_background"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = contrast_ratio(a["luminance_task"], a["luminance_background"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_ugr
# ---------------------------------------------------------------------------

_ugr_spec = ToolSpec(
    name="lighting_ugr",
    description=(
        "Compute the Unified Glare Rating (UGR) per CIE 117-1995.\n"
        "\n"
        "UGR = 8 × log10( 0.25/Lb × Σ(Li² × Ωi / pi²) )\n"
        "\n"
        "Typical limits (EN 12464-1):\n"
        "  UGR ≤ 19 — offices, classrooms\n"
        "  UGR ≤ 22 — industrial / assembly\n"
        "  UGR ≤ 25 — heavy industrial\n"
        "  UGR ≤ 28 — severe glare threshold\n"
        "\n"
        "Warnings: glare-exceeds if UGR > 22 or > 28.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "background_luminance_cd_m2": {
                "type": "number",
                "description": "Background (indirect) luminance Lb (cd/m²). Must be > 0.",
            },
            "luminaire_luminances_cd_m2": {
                "type": "array",
                "items": {"type": "number"},
                "description": "List of glare-source luminances Li (cd/m²).",
            },
            "solid_angles_sr": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Solid angles Ωi of each glare source (sr).",
            },
            "guth_position_indices": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Guth position indices pi (≥ 1) for each glare source.",
            },
        },
        "required": [
            "background_luminance_cd_m2",
            "luminaire_luminances_cd_m2",
            "solid_angles_sr",
            "guth_position_indices",
        ],
    },
)


@register(_ugr_spec, write=False)
async def run_lighting_ugr(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "background_luminance_cd_m2",
        "luminaire_luminances_cd_m2",
        "solid_angles_sr",
        "guth_position_indices",
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = ugr(
        a["background_luminance_cd_m2"],
        a["luminaire_luminances_cd_m2"],
        a["solid_angles_sr"],
        a["guth_position_indices"],
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_road_luminance
# ---------------------------------------------------------------------------

_road_lum_spec = ToolSpec(
    name="lighting_road_luminance",
    description=(
        "Estimate road surface luminance using a simplified CIE R-table model.\n"
        "\n"
        "L = I × r / H²   where H = d × cos(θ) is the mounting height.\n"
        "\n"
        "Typical r values: 0.07 for R2/R3 asphalt (default), 0.10 for R1 concrete.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "intensity_cd": {
                "type": "number",
                "description": "Luminaire intensity toward the road point (cd). Must be >= 0.",
            },
            "distance_m": {
                "type": "number",
                "description": "Slant distance from luminaire to road point (m). Must be > 0.",
            },
            "angle_from_nadir_deg": {
                "type": "number",
                "description": "Angle from nadir θ, degrees [0, 90).",
            },
            "r_table_factor": {
                "type": "number",
                "description": (
                    "Reduced luminance coefficient r from CIE R-table "
                    "(default 0.07 for R2/R3 asphalt)."
                ),
            },
        },
        "required": ["intensity_cd", "distance_m", "angle_from_nadir_deg"],
    },
)


@register(_road_lum_spec, write=False)
async def run_lighting_road_luminance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("intensity_cd", "distance_m", "angle_from_nadir_deg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "r_table_factor" in a:
        kwargs["r_table_factor"] = a["r_table_factor"]

    result = road_luminance(
        a["intensity_cd"], a["distance_m"], a["angle_from_nadir_deg"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_pole_spacing
# ---------------------------------------------------------------------------

_pole_spec = ToolSpec(
    name="lighting_pole_spacing",
    description=(
        "Compute recommended roadway pole spacing from mounting height and S/H ratio.\n"
        "\n"
        "Spacing = S/H_ratio × mounting_height\n"
        "\n"
        "Typical S/H ratios: 3.0 (single-sided), 4.0 (staggered), 5.0 (opposite).\n"
        "\n"
        "Errors: {ok:false, reason} for non-positive inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mounting_height_m": {
                "type": "number",
                "description": "Luminaire mounting height above road (m). Must be > 0.",
            },
            "spacing_to_height_ratio": {
                "type": "number",
                "description": "S/H ratio (default 3.0).",
            },
        },
        "required": ["mounting_height_m"],
    },
)


@register(_pole_spec, write=False)
async def run_lighting_pole_spacing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("mounting_height_m") is None:
        return json.dumps({"ok": False, "reason": "mounting_height_m is required"})

    kwargs: dict = {}
    if "spacing_to_height_ratio" in a:
        kwargs["spacing_to_height_ratio"] = a["spacing_to_height_ratio"]

    result = pole_spacing(a["mounting_height_m"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_roadway_utilization
# ---------------------------------------------------------------------------

_road_util_spec = ToolSpec(
    name="lighting_roadway_utilization",
    description=(
        "Compute average road illuminance and luminance using the luminance "
        "(utilization) method.\n"
        "\n"
        "E_road = (Φ × UF) / (W × S)   [lx]\n"
        "L_road ≈ E_road × 0.07          [cd/m²]  (R2 asphalt default)\n"
        "\n"
        "Warnings: poor-uniformity if pole S/H > 5.0.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "luminaire_lumens": {
                "type": "number",
                "description": "Total initial lamp lumens per luminaire (lm). Must be > 0.",
            },
            "utilization_factor": {
                "type": "number",
                "description": "Fraction of lumens falling on carriageway (0–1).",
            },
            "road_width_m": {
                "type": "number",
                "description": "Carriageway width (m). Must be > 0.",
            },
            "spacing_m": {
                "type": "number",
                "description": "Pole spacing (m). Must be > 0.",
            },
            "mounting_height_m": {
                "type": "number",
                "description": "Mounting height above road (m). Must be > 0.",
            },
        },
        "required": [
            "luminaire_lumens",
            "utilization_factor",
            "road_width_m",
            "spacing_m",
            "mounting_height_m",
        ],
    },
)


@register(_road_util_spec, write=False)
async def run_lighting_roadway_util(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in (
        "luminaire_lumens",
        "utilization_factor",
        "road_width_m",
        "spacing_m",
        "mounting_height_m",
    ):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = roadway_utilization(
        a["luminaire_lumens"],
        a["utilization_factor"],
        a["road_width_m"],
        a["spacing_m"],
        a["mounting_height_m"],
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_emergency_lux
# ---------------------------------------------------------------------------

_emerg_lux_spec = ToolSpec(
    name="lighting_emergency_lux",
    description=(
        "Compute floor-level illuminance directly below an emergency luminaire "
        "using the inverse-square law.\n"
        "\n"
        "E = I / d²\n"
        "\n"
        "NFPA 101 / BS 5266 minimum: ≥ 1.0 lx on escape route centreline.\n"
        "\n"
        "Warnings: under-lit if E < 1.0 lx.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "intensity_cd": {
                "type": "number",
                "description": "Nadir luminous intensity (cd). Must be >= 0.",
            },
            "distance_m": {
                "type": "number",
                "description": "Mounting height / slant distance to floor (m). Must be > 0.",
            },
        },
        "required": ["intensity_cd", "distance_m"],
    },
)


@register(_emerg_lux_spec, write=False)
async def run_lighting_emergency_lux(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("intensity_cd", "distance_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = emergency_lux_at_floor(a["intensity_cd"], a["distance_m"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_emergency_spacing
# ---------------------------------------------------------------------------

_emerg_spacing_spec = ToolSpec(
    name="lighting_emergency_spacing",
    description=(
        "Compute maximum centre-to-centre spacing between emergency luminaires "
        "so that the midpoint floor illuminance meets the minimum lux target.\n"
        "\n"
        "Simplified formula: E_mid = I / (h² + (S/2)²)\n"
        "Solved for S: S_max = 2 × √(I/E_min − h²)\n"
        "\n"
        "Warnings: under-lit if luminaire cannot meet target even at nadir.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mounting_height_m": {
                "type": "number",
                "description": "Mounting height above floor (m). Must be > 0.",
            },
            "min_lux_target": {
                "type": "number",
                "description": "Minimum floor illuminance at midpoint (lx, default 1.0).",
            },
            "intensity_cd": {
                "type": "number",
                "description": "Nadir luminous intensity (cd, default 100).",
            },
        },
        "required": ["mounting_height_m"],
    },
)


@register(_emerg_spacing_spec, write=False)
async def run_lighting_emergency_spacing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("mounting_height_m") is None:
        return json.dumps({"ok": False, "reason": "mounting_height_m is required"})

    kwargs: dict = {}
    for key in ("min_lux_target", "intensity_cd"):
        if key in a:
            kwargs[key] = a[key]

    result = emergency_spacing(a["mounting_height_m"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_lamp_lpw
# ---------------------------------------------------------------------------

_lamp_lpw_spec = ToolSpec(
    name="lighting_lamp_lpw",
    description=(
        "Return the approximate initial luminous efficacy (lm/W) for a lamp type.\n"
        "\n"
        "Supported types:\n"
        "  led_standard (100 lm/W), led_high_output (140), fluorescent_t8 (85),\n"
        "  fluorescent_t5 (90), metal_halide (80), high_pressure_sodium (100),\n"
        "  low_pressure_sodium (180), incandescent (15), halogen (20),\n"
        "  cfl (65), ceramic_mh (90), induction (70).\n"
        "\n"
        "Errors: {ok:false, reason} for unknown lamp_type.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "lamp_type": {
                "type": "string",
                "description": (
                    "Lamp type string. One of: led_standard, led_high_output, "
                    "fluorescent_t8, fluorescent_t5, metal_halide, "
                    "high_pressure_sodium, low_pressure_sodium, incandescent, "
                    "halogen, cfl, ceramic_mh, induction."
                ),
            },
        },
        "required": ["lamp_type"],
    },
)


@register(_lamp_lpw_spec, write=False)
async def run_lighting_lamp_lpw(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("lamp_type") is None:
        return json.dumps({"ok": False, "reason": "lamp_type is required"})

    result = lamp_lumens_per_watt(a["lamp_type"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_lamp_energy
# ---------------------------------------------------------------------------

_energy_spec = ToolSpec(
    name="lighting_lamp_energy",
    description=(
        "Compute lamp energy consumption.\n"
        "\n"
        "Energy (Wh) = wattage × hours\n"
        "Energy (kWh) = wattage × hours / 1000\n"
        "\n"
        "Errors: {ok:false, reason} for non-positive inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "wattage_W": {
                "type": "number",
                "description": "Lamp wattage (W). Must be > 0.",
            },
            "hours": {
                "type": "number",
                "description": "Operating hours. Must be > 0.",
            },
        },
        "required": ["wattage_W", "hours"],
    },
)


@register(_energy_spec, write=False)
async def run_lighting_energy(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("wattage_W", "hours"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = lamp_energy(a["wattage_W"], a["hours"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: lighting_lpd_check
# ---------------------------------------------------------------------------

_lpd_spec = ToolSpec(
    name="lighting_lpd_check",
    description=(
        "Check Lighting Power Density (LPD) compliance against ASHRAE 90.1-2022 "
        "or California Title 24 (2022) allowances.\n"
        "\n"
        "LPD = total_watts / area_m2   [W/m²]\n"
        "\n"
        "Supported building types (both standards):\n"
        "  office, classroom, retail, warehouse, hospital, restaurant, gymnasium,\n"
        "  hotel_lobby, parking_garage, corridor, stairway, lobby, manufacturing.\n"
        "\n"
        "Warnings: LPD-over-allowance if LPD > allowance.\n"
        "\n"
        "Errors: {ok:false, reason} for unknown building type.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "total_watts": {
                "type": "number",
                "description": "Total connected lighting power (W). Must be > 0.",
            },
            "area_m2": {
                "type": "number",
                "description": "Floor area (m²). Must be > 0.",
            },
            "building_type": {
                "type": "string",
                "description": (
                    "Building/space type (default 'office'). "
                    "One of: office, classroom, retail, warehouse, hospital, "
                    "restaurant, gymnasium, hotel_lobby, parking_garage, "
                    "corridor, stairway, lobby, manufacturing."
                ),
            },
            "standard": {
                "type": "string",
                "enum": ["ASHRAE", "Title24"],
                "description": "Energy code standard: 'ASHRAE' (default) or 'Title24'.",
            },
        },
        "required": ["total_watts", "area_m2"],
    },
)


@register(_lpd_spec, write=False)
async def run_lighting_lpd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("total_watts", "area_m2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for key in ("building_type", "standard"):
        if key in a:
            kwargs[key] = a[key]

    result = lpd_check(a["total_watts"], a["area_m2"], **kwargs)
    return ok_payload(result)
