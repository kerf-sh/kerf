"""
kerf_cad_core.casting.tools — LLM tool wrappers for metal casting design.

Registers seven tools with the Kerf tool registry:

  casting_shrinkage_allowance  — pattern shrinkage + machining allowance by alloy
  casting_draft_angle_volume   — volume addition due to draft angle taper
  casting_chvorinov            — Chvorinov solidification time t = B·(V/A)^n
  casting_riser_size           — riser sizing by modulus method (M_r >= 1.2·M_c)
  casting_gating_system        — sprue/runner/gate areas via Bernoulli + continuity
  casting_yield                — casting yield % and quality flag
  casting_pouring_guidance     — fluidity and pouring temperature guidance

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Groover, M.P. "Fundamentals of Modern Manufacturing", 5th ed., Ch. 11
Kalpakjian, S. & Schmid, S.R. "Manufacturing Engineering & Technology", 7th ed.
Campbell, J. "Castings", 2nd ed.
AFS Gating and Risering Manual

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.casting.design import (
    shrinkage_allowance,
    draft_angle_volume,
    chvorinov_solidification,
    riser_size,
    gating_system,
    casting_yield,
    pouring_guidance,
)

# Shared alloy enum used across several tools
_ALLOY_ENUM = [
    "grey_cast_iron",
    "white_cast_iron",
    "ductile_iron",
    "carbon_steel",
    "stainless_steel",
    "aluminium_alloy",
    "copper_alloy",
    "bronze",
    "zinc_alloy",
    "magnesium_alloy",
    "nickel_alloy",
    "titanium_alloy",
]


# ---------------------------------------------------------------------------
# Tool: casting_shrinkage_allowance
# ---------------------------------------------------------------------------

_shrinkage_spec = ToolSpec(
    name="casting_shrinkage_allowance",
    description=(
        "Compute pattern shrinkage allowance and machining stock for a casting dimension.\n"
        "\n"
        "The foundry pattern must be made larger than the final casting dimension to\n"
        "account for (1) solidification shrinkage and (2) machining stock.\n"
        "\n"
        "Returns the pattern dimension (mm) after shrinkage compensation and machining\n"
        "allowance addition.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid/unknown alloy.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alloy": {
                "type": "string",
                "enum": _ALLOY_ENUM,
                "description": "Alloy name from the catalog.",
            },
            "nominal_dim_mm": {
                "type": "number",
                "description": "Final desired casting dimension (mm). Must be > 0.",
            },
            "extra_machining_mm": {
                "type": "number",
                "description": (
                    "Additional machining stock per surface beyond alloy default (mm). "
                    "Must be >= 0 (default 0.0)."
                ),
            },
        },
        "required": ["alloy", "nominal_dim_mm"],
    },
)


@register(_shrinkage_spec, write=False)
async def run_casting_shrinkage_allowance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("alloy") is None:
        return json.dumps({"ok": False, "reason": "alloy is required"})
    if a.get("nominal_dim_mm") is None:
        return json.dumps({"ok": False, "reason": "nominal_dim_mm is required"})

    kwargs: dict = {}
    if "extra_machining_mm" in a:
        kwargs["extra_machining_mm"] = a["extra_machining_mm"]

    result = shrinkage_allowance(a["alloy"], a["nominal_dim_mm"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: casting_draft_angle_volume
# ---------------------------------------------------------------------------

_draft_spec = ToolSpec(
    name="casting_draft_angle_volume",
    description=(
        "Compute the extra volume added to a pattern face by a draft angle taper.\n"
        "\n"
        "Draft angles are required on vertical pattern faces to allow withdrawal\n"
        "from the sand mold without damaging the mold wall.\n"
        "\n"
        "Added volume ≈ base_area × height × tan(draft_deg).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "base_area_m2": {
                "type": "number",
                "description": "Cross-sectional area at the parting plane (m²). Must be > 0.",
            },
            "height_m": {
                "type": "number",
                "description": "Height of the drafted face (m). Must be > 0.",
            },
            "draft_deg": {
                "type": "number",
                "description": (
                    "Draft angle (degrees). Typical range: 0.5°–5°. Must be > 0."
                ),
            },
        },
        "required": ["base_area_m2", "height_m", "draft_deg"],
    },
)


@register(_draft_spec, write=False)
async def run_casting_draft_angle_volume(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("base_area_m2", "height_m", "draft_deg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = draft_angle_volume(a["base_area_m2"], a["height_m"], a["draft_deg"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: casting_chvorinov
# ---------------------------------------------------------------------------

_chvorinov_spec = ToolSpec(
    name="casting_chvorinov",
    description=(
        "Estimate casting solidification time using Chvorinov's Rule.\n"
        "\n"
        "Chvorinov (1940): t = B · (V/A)^n\n"
        "  V = casting volume (m³), A = casting surface area (m²)\n"
        "  B = mold constant (s/m²) — calibrated experimentally per alloy/mold\n"
        "  n = exponent (typically 2.0; range 1.5–2.0)\n"
        "\n"
        "Returns solidification time in seconds.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "volume_m3": {
                "type": "number",
                "description": "Casting volume (m³). Must be > 0.",
            },
            "area_m2": {
                "type": "number",
                "description": "Casting surface area (m²). Must be > 0.",
            },
            "B": {
                "type": "number",
                "description": (
                    "Chvorinov mold constant (s/m²). "
                    "Default 600 s/m² (green sand / steel). Must be > 0."
                ),
            },
            "n": {
                "type": "number",
                "description": (
                    "Exponent in Chvorinov's rule. Default 2.0. "
                    "Typical range [1.5, 2.0]. Must be > 0."
                ),
            },
        },
        "required": ["volume_m3", "area_m2"],
    },
)


@register(_chvorinov_spec, write=False)
async def run_casting_chvorinov(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("volume_m3", "area_m2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "B" in a:
        kwargs["B"] = a["B"]
    if "n" in a:
        kwargs["n"] = a["n"]

    result = chvorinov_solidification(a["volume_m3"], a["area_m2"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: casting_riser_size
# ---------------------------------------------------------------------------

_riser_spec = ToolSpec(
    name="casting_riser_size",
    description=(
        "Size a feeder riser for a casting using the modulus method.\n"
        "\n"
        "The AFS feeding criterion: M_riser >= 1.2 × M_casting\n"
        "where M = V / A_cooling (casting modulus).\n"
        "\n"
        "For a cylindrical riser (H = D): M_riser = D / 5\n"
        "→ D_min = 6 × M_casting.\n"
        "\n"
        "Issues a warning if the riser is insufficient to feed the casting\n"
        "(shrinkage-porosity risk).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "casting_volume_m3": {
                "type": "number",
                "description": "Casting volume (m³). Must be > 0.",
            },
            "casting_surface_area_m2": {
                "type": "number",
                "description": "Casting surface area (m²). Must be > 0.",
            },
            "alloy": {
                "type": "string",
                "enum": _ALLOY_ENUM,
                "description": "Alloy name (used for warning context). Default 'carbon_steel'.",
            },
            "riser_shape": {
                "type": "string",
                "enum": ["cylindrical"],
                "description": "Riser geometry. Currently only 'cylindrical' (H = D) supported.",
            },
            "B": {
                "type": "number",
                "description": (
                    "Chvorinov mold constant (s/m²). Default 600 s/m²."
                ),
            },
            "n": {
                "type": "number",
                "description": (
                    "Chvorinov exponent. Default 2.0."
                ),
            },
        },
        "required": ["casting_volume_m3", "casting_surface_area_m2"],
    },
)


@register(_riser_spec, write=False)
async def run_casting_riser_size(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("casting_volume_m3", "casting_surface_area_m2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "alloy" in a:
        kwargs["alloy"] = a["alloy"]
    if "riser_shape" in a:
        kwargs["riser_shape"] = a["riser_shape"]
    if "B" in a:
        kwargs["B"] = a["B"]
    if "n" in a:
        kwargs["n"] = a["n"]

    result = riser_size(
        a["casting_volume_m3"], a["casting_surface_area_m2"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: casting_gating_system
# ---------------------------------------------------------------------------

_gating_spec = ToolSpec(
    name="casting_gating_system",
    description=(
        "Design the gating system (sprue / runner / gate) areas for a casting.\n"
        "\n"
        "Uses Bernoulli's equation to find the metal velocity at the choke:\n"
        "  v = Cd · √(2 · g · H)\n"
        "Then continuity gives the choke area:\n"
        "  A_choke = (m / ρ) / (t_pour · v)\n"
        "\n"
        "Gating ratios:\n"
        "  'unpressurised' (default): sprue:runner:gate = 1:2:4 (choke at sprue)\n"
        "  'pressurised':             sprue:runner:gate = 1:0.75:0.5 (choke at gate)\n"
        "\n"
        "Returns all cross-section areas (m²).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "casting_mass_kg": {
                "type": "number",
                "description": "Total metal mass to pour including runners (kg). Must be > 0.",
            },
            "alloy": {
                "type": "string",
                "enum": _ALLOY_ENUM,
                "description": "Alloy name (for density lookup).",
            },
            "pouring_time_s": {
                "type": "number",
                "description": "Target total pouring time (s). Must be > 0.",
            },
            "sprue_height_m": {
                "type": "number",
                "description": (
                    "Effective metallostatic head at choke (m). "
                    "For a simple sprue use sprue height. Must be > 0."
                ),
            },
            "system_type": {
                "type": "string",
                "enum": ["unpressurised", "pressurised"],
                "description": (
                    "Gating system type: "
                    "'unpressurised' (default, choke at sprue, 1:2:4) or "
                    "'pressurised' (choke at gate, 1:0.75:0.5)."
                ),
            },
            "discharge_coeff": {
                "type": "number",
                "description": (
                    "Discharge coefficient Cd (default 0.85). Range (0, 1]."
                ),
            },
        },
        "required": ["casting_mass_kg", "alloy", "pouring_time_s", "sprue_height_m"],
    },
)


@register(_gating_spec, write=False)
async def run_casting_gating_system(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("casting_mass_kg", "alloy", "pouring_time_s", "sprue_height_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "system_type" in a:
        kwargs["system_type"] = a["system_type"]
    if "discharge_coeff" in a:
        kwargs["discharge_coeff"] = a["discharge_coeff"]

    result = gating_system(
        a["casting_mass_kg"],
        a["alloy"],
        a["pouring_time_s"],
        a["sprue_height_m"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: casting_yield
# ---------------------------------------------------------------------------

_yield_spec = ToolSpec(
    name="casting_yield",
    description=(
        "Compute casting yield as a percentage of useful casting mass vs total poured.\n"
        "\n"
        "yield = (casting_mass / total_poured) × 100%\n"
        "\n"
        "Issues a warning when yield < 60% (poor economics) or < 50% (redesign needed).\n"
        "\n"
        "Typical yields: sand casting 50–70%, investment casting 80–95%.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "casting_mass_kg": {
                "type": "number",
                "description": "Mass of the finished casting (kg). Must be > 0.",
            },
            "total_poured_mass_kg": {
                "type": "number",
                "description": (
                    "Total metal poured = casting + gating + risers (kg). "
                    "Must be >= casting_mass_kg."
                ),
            },
        },
        "required": ["casting_mass_kg", "total_poured_mass_kg"],
    },
)


@register(_yield_spec, write=False)
async def run_casting_yield(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("casting_mass_kg", "total_poured_mass_kg"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = casting_yield(a["casting_mass_kg"], a["total_poured_mass_kg"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: casting_pouring_guidance
# ---------------------------------------------------------------------------

_pouring_spec = ToolSpec(
    name="casting_pouring_guidance",
    description=(
        "Provide pouring temperature range and fluidity guidance for a given alloy "
        "and minimum section thickness.\n"
        "\n"
        "Returns the recommended pouring temperature range (°C) and alloy-specific\n"
        "fluidity notes.  Issues a warning for thin sections below the alloy threshold:\n"
        "  Ferrous alloys:    < 5 mm is thin\n"
        "  Al/Mg alloys:      < 3 mm is thin\n"
        "  Other non-ferrous: < 2 mm is thin\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alloy": {
                "type": "string",
                "enum": _ALLOY_ENUM,
                "description": "Alloy name from the catalog.",
            },
            "section_thickness_mm": {
                "type": "number",
                "description": (
                    "Minimum section thickness in the casting (mm). "
                    "Must be > 0."
                ),
            },
        },
        "required": ["alloy", "section_thickness_mm"],
    },
)


@register(_pouring_spec, write=False)
async def run_casting_pouring_guidance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("alloy", "section_thickness_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = pouring_guidance(a["alloy"], a["section_thickness_mm"])
    return ok_payload(result)
