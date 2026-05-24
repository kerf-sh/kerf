"""
kerf_cad_core.casting.detail_tools — LLM tool wrappers for casting depth functions.

Registers five tools with the Kerf tool registry:

  casting_shrinkage_factor      — linear shrinkage factor by alloy
  casting_pattern_dimensions    — scale nominal dimensions by shrinkage
  casting_chvorinov_time        — Chvorinov solidification time (mould-aware)
  casting_riser_diameter        — cylindrical riser sizing from casting modulus
  casting_design_package        — integrated riser + gating design

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Heine, R.W., Loper, C.R. & Rosenthal, P.C. "Principles of Metal Casting", 2nd ed.
Campbell, J. "Castings", 2nd ed.
AFS Gating and Risering Manual

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.casting.details import (
    shrinkage_factor,
    pattern_dimensions,
    chvorinov_time,
    riser_diameter,
    design_riser_and_gating,
)

_ALLOY_ENUM = [
    "grey_cast_iron",
    "white_cast_iron",
    "ductile_iron",
    "mild_steel",
    "carbon_steel",
    "stainless_steel",
    "brass",
    "bronze",
    "copper",
    "copper_alloy",
    "aluminium_alloy",
    "aluminium",
    "magnesium_alloy",
    "magnesium",
    "zinc_alloy",
    "zinc",
    "nickel_alloy",
    "titanium_alloy",
]

_MOULD_ENUM = ["sand", "metal", "die"]
_LOCATION_ENUM = ["top", "side"]


# ---------------------------------------------------------------------------
# Tool: casting_shrinkage_factor
# ---------------------------------------------------------------------------

_sf_spec = ToolSpec(
    name="casting_shrinkage_factor",
    description=(
        "Return the linear solidification shrinkage factor for a given alloy.\n"
        "\n"
        "Source: Heine/Loper/Rosenthal Table 5.1 + AFS handbook.\n"
        "\n"
        "Errors: {ok:false, reason} for unknown alloy.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alloy": {
                "type": "string",
                "enum": _ALLOY_ENUM,
                "description": "Alloy name from the catalog.",
            },
        },
        "required": ["alloy"],
    },
)


@register(_sf_spec, write=False)
async def run_casting_shrinkage_factor(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if not a.get("alloy"):
        return json.dumps({"ok": False, "reason": "alloy is required"})
    return ok_payload(shrinkage_factor(a["alloy"]))


# ---------------------------------------------------------------------------
# Tool: casting_pattern_dimensions
# ---------------------------------------------------------------------------

_pd_spec = ToolSpec(
    name="casting_pattern_dimensions",
    description=(
        "Scale nominal part dimensions up to account for solidification shrinkage.\n"
        "\n"
        "pattern_dim = nominal_dim / (1 - linear_shrinkage)\n"
        "\n"
        "Dimensions may be supplied in any consistent unit (mm, m, inches).\n"
        "Machining stock is NOT included here — add it separately.\n"
        "\n"
        "Errors: {ok:false, reason} for unknown alloy or invalid dims.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alloy": {
                "type": "string",
                "enum": _ALLOY_ENUM,
                "description": "Alloy name from the catalog.",
            },
            "part_dims": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 1,
                "description": (
                    "List of nominal part dimensions (any consistent unit, all > 0). "
                    "Example: [50, 50, 50] for a 50 mm cube."
                ),
            },
        },
        "required": ["alloy", "part_dims"],
    },
)


@register(_pd_spec, write=False)
async def run_casting_pattern_dimensions(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if not a.get("alloy"):
        return json.dumps({"ok": False, "reason": "alloy is required"})
    if not a.get("part_dims"):
        return json.dumps({"ok": False, "reason": "part_dims is required"})
    return ok_payload(pattern_dimensions(a["part_dims"], a["alloy"]))


# ---------------------------------------------------------------------------
# Tool: casting_chvorinov_time
# ---------------------------------------------------------------------------

_ct_spec = ToolSpec(
    name="casting_chvorinov_time",
    description=(
        "Estimate solidification time using Chvorinov's rule: t = C · (V/A)²\n"
        "\n"
        "Built-in C constants by mould type and alloy family:\n"
        "  sand  / ferrous:     600 s/m²\n"
        "  sand  / non-ferrous: 400 s/m²\n"
        "  metal / ferrous:     200 s/m²\n"
        "  metal / non-ferrous: 130 s/m²\n"
        "  die   / ferrous:      80 s/m²\n"
        "  die   / non-ferrous:  55 s/m²\n"
        "\n"
        "A custom mould_constant_C may be supplied to override the table.\n"
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
            "surface_area_m2": {
                "type": "number",
                "description": "Casting surface area (m²). Must be > 0.",
            },
            "mould_type": {
                "type": "string",
                "enum": _MOULD_ENUM,
                "description": "Mould material: 'sand' (default), 'metal', or 'die'.",
            },
            "alloy": {
                "type": "string",
                "enum": _ALLOY_ENUM,
                "description": "Alloy name (used to select ferrous vs. non-ferrous C). Default 'carbon_steel'.",
            },
            "mould_constant_C": {
                "type": "number",
                "description": (
                    "Override the built-in Chvorinov constant (s/m²). "
                    "Must be > 0 if supplied."
                ),
            },
        },
        "required": ["volume_m3", "surface_area_m2"],
    },
)


@register(_ct_spec, write=False)
async def run_casting_chvorinov_time(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("volume_m3", "surface_area_m2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    for opt in ("mould_type", "alloy", "mould_constant_C"):
        if opt in a:
            kwargs[opt] = a[opt]
    return ok_payload(chvorinov_time(a["volume_m3"], a["surface_area_m2"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: casting_riser_diameter
# ---------------------------------------------------------------------------

_rd_spec = ToolSpec(
    name="casting_riser_diameter",
    description=(
        "Size a cylindrical riser so that (V/A)_riser ≥ safety × (V/A)_casting.\n"
        "\n"
        "Formula for H/D = k cylinder (side + bottom cooling only):\n"
        "  M_riser = k·D / (4·(k+0.25))\n"
        "  D_min   = 4·(k+0.25)·safety·M_casting / k\n"
        "\n"
        "Riser efficiency:\n"
        "  top  riser: 0.80 (atmospheric pressure assists feeding)\n"
        "  side riser: 0.50\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "casting_VA": {
                "type": "number",
                "description": "V/A modulus of the casting (m). Must be > 0.",
            },
            "height_to_dia_ratio": {
                "type": "number",
                "description": "H/D ratio for the cylindrical riser. Default 1.0 (H=D). Must be > 0.",
            },
            "safety": {
                "type": "number",
                "description": "Modulus safety factor (default 1.1). Typical range 1.0–1.2. Must be > 0.",
            },
            "alloy": {
                "type": "string",
                "enum": _ALLOY_ENUM,
                "description": "Alloy name (informational). Default 'carbon_steel'.",
            },
            "riser_location": {
                "type": "string",
                "enum": _LOCATION_ENUM,
                "description": "'top' (default, efficiency 0.80) or 'side' (efficiency 0.50).",
            },
        },
        "required": ["casting_VA"],
    },
)


@register(_rd_spec, write=False)
async def run_casting_riser_diameter(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("casting_VA") is None:
        return json.dumps({"ok": False, "reason": "casting_VA is required"})
    kwargs: dict = {}
    for opt in ("height_to_dia_ratio", "safety", "alloy", "riser_location"):
        if opt in a:
            kwargs[opt] = a[opt]
    return ok_payload(riser_diameter(a["casting_VA"], **kwargs))


# ---------------------------------------------------------------------------
# Tool: casting_design_package
# ---------------------------------------------------------------------------

_dp_spec = ToolSpec(
    name="casting_design_package",
    description=(
        "Full casting design package: pattern allowance, solidification time,\n"
        "riser dimensions, gating ratios, and recommended pouring rate.\n"
        "\n"
        "Steps performed internally:\n"
        "  1. Shrinkage allowance → pattern scale factor (Heine §5)\n"
        "  2. Chvorinov time → solidification estimate (Chvorinov 1940)\n"
        "  3. Cylindrical riser sizing (Heine §9; Campbell §5)\n"
        "  4. Non-pressurised gating ratios 1:2:4 (AFS/Campbell)\n"
        "  5. Pouring rate from Bernoulli + continuity equation\n"
        "\n"
        "Validation: 50×50×50 mm sand casting in mild steel:\n"
        "  scale ≈ 1.0204 (2.04% oversize), t_solid ≈ 42 s,\n"
        "  riser D ≈ 46 mm, gating ratio 1:2:4.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "part_volume_m3": {
                "type": "number",
                "description": "Casting cavity volume (m³). Must be > 0.",
            },
            "part_surface_m2": {
                "type": "number",
                "description": "Casting surface area (m²). Must be > 0.",
            },
            "alloy": {
                "type": "string",
                "enum": _ALLOY_ENUM,
                "description": "Alloy name from the catalog.",
            },
            "mould_type": {
                "type": "string",
                "enum": _MOULD_ENUM,
                "description": "Mould material: 'sand' (default), 'metal', or 'die'.",
            },
            "height_to_dia_ratio": {
                "type": "number",
                "description": "H/D ratio for the cylindrical riser (default 1.0).",
            },
            "riser_location": {
                "type": "string",
                "enum": _LOCATION_ENUM,
                "description": "'top' (default) or 'side'.",
            },
            "riser_safety": {
                "type": "number",
                "description": "Riser modulus safety factor (default 1.1).",
            },
            "pouring_time_s": {
                "type": "number",
                "description": (
                    "Target pouring time (s). "
                    "If omitted, estimated as max(5, 2.4·√V_cm3). Must be > 0."
                ),
            },
            "sprue_height_m": {
                "type": "number",
                "description": "Effective metallostatic head (m) for gating. Default 0.3 m.",
            },
            "max_fill_time_s": {
                "type": "number",
                "description": (
                    "Maximum acceptable fill time (s). "
                    "A warning is issued if pouring_time_s exceeds this."
                ),
            },
        },
        "required": ["part_volume_m3", "part_surface_m2", "alloy"],
    },
)


@register(_dp_spec, write=False)
async def run_casting_design_package(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("part_volume_m3", "part_surface_m2", "alloy"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    for opt in (
        "mould_type",
        "height_to_dia_ratio",
        "riser_location",
        "riser_safety",
        "pouring_time_s",
        "sprue_height_m",
        "max_fill_time_s",
    ):
        if opt in a:
            kwargs[opt] = a[opt]
    return ok_payload(
        design_riser_and_gating(
            a["part_volume_m3"],
            a["part_surface_m2"],
            a["alloy"],
            **kwargs,
        )
    )
