"""
kerf_cad_core.timber.tools — LLM tool wrappers for NDS timber design.

Registers tools with the Kerf tool registry:

  timber_reference_values     — look up tabulated NDS reference design values
  timber_adjusted_Fb          — compute adjusted bending stress Fb'
  timber_adjusted_Fc          — compute adjusted compression stress Fc'
  timber_sawn_section         — dressed section properties for standard sawn lumber
  timber_glulam_section       — section properties for glulam (actual dims)
  timber_check_bending        — bending check fb <= Fb'
  timber_check_shear          — shear check fv <= Fv'
  timber_check_deflection     — deflection limits (L/360 live, L/240 total)
  timber_column_stability     — CP + Fc' for column stability (Ylinen)
  timber_check_column         — column compression check fc <= Fc'
  timber_check_combined       — combined bending+axial interaction (NDS §3.9.2)
  timber_check_bearing        — bearing check fc_perp <= Fc_perp'
  timber_lateral_yield_bolt   — single-fastener lateral yield Z (NDS yield modes)
  timber_withdrawal_nail      — nail withdrawal W (NDS §12.2)

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": False, "reason": "..."} — tools never raise.

References
----------
NDS 2018 — National Design Specification for Wood Construction (AWC)
NDS Supplement 2018 — Design Values for Wood Construction
Breyer, D.E. et al. "Design of Wood Structures", 7th ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.timber.design import (
    reference_design_values,
    adjusted_Fb,
    adjusted_Fv,
    adjusted_Fc,
    adjusted_Fc_perp,
    adjusted_E_prime,
    sawn_section,
    glulam_section,
    check_bending,
    check_shear,
    check_deflection,
    check_compression_column,
    check_combined_bending_axial,
    check_bearing,
    CP_column_stability,
    FcE_critical,
    lateral_yield_bolt,
    withdrawal_nail,
)


# ---------------------------------------------------------------------------
# Tool: timber_reference_values
# ---------------------------------------------------------------------------

_ref_values_spec = ToolSpec(
    name="timber_reference_values",
    description=(
        "Look up tabulated NDS 2018 reference design values (Fb, Fv, Fc, Fc_perp, "
        "Ft, E, Emin) for a given species group and visual grade.\n"
        "\n"
        "Available species: douglas_fir_larch, southern_pine, hem_fir, spruce_pine_fir.\n"
        "Available grades: select_structural, no_1, no_2.\n"
        "\n"
        "Returns Fb_psi, Fv_psi, Fc_psi, Fc_perp_psi, Ft_psi, E_psi, Emin_psi.\n"
        "These are reference (unfactored) values; apply adjustment factors before use.\n"
        "\n"
        "Errors: {ok:false, reason} for unknown species/grade. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "species": {
                "type": "string",
                "enum": ["douglas_fir_larch", "southern_pine", "hem_fir", "spruce_pine_fir"],
                "description": "Species group per NDS Supplement Table 4A/4B.",
            },
            "grade": {
                "type": "string",
                "enum": ["select_structural", "no_1", "no_2"],
                "description": "Visual lumber grade.",
            },
        },
        "required": ["species", "grade"],
    },
)


@register(_ref_values_spec, write=False)
async def run_timber_reference_values(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("species", "grade"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = reference_design_values(a["species"], a["grade"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_adjusted_Fb
# ---------------------------------------------------------------------------

_adj_Fb_spec = ToolSpec(
    name="timber_adjusted_Fb",
    description=(
        "Compute adjusted allowable bending stress Fb' (NDS §2.3).\n"
        "\n"
        "Fb' = Fb_ref × CD × CM × Ct × CL × CF × Cfu × Ci × Cr\n"
        "\n"
        "All adjustment factors default to 1.0 if not supplied.\n"
        "Returns Fb_prime_psi and the full factor breakdown.\n"
        "\n"
        "Errors: {ok:false, reason} for non-positive inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Fb_ref": {"type": "number", "description": "Reference bending stress (psi). Must be > 0."},
            "CD": {"type": "number", "description": "Load-duration factor (default 1.0)."},
            "CM": {"type": "number", "description": "Wet-service factor (default 1.0)."},
            "Ct": {"type": "number", "description": "Temperature factor (default 1.0)."},
            "CL": {"type": "number", "description": "Beam stability factor (default 1.0)."},
            "CF": {"type": "number", "description": "Size factor (default 1.0)."},
            "Cfu": {"type": "number", "description": "Flat-use factor (default 1.0)."},
            "Ci": {"type": "number", "description": "Incising factor (default 1.0)."},
            "Cr": {"type": "number", "description": "Repetitive-member factor (default 1.0)."},
        },
        "required": ["Fb_ref"],
    },
)


@register(_adj_Fb_spec, write=False)
async def run_timber_adjusted_Fb(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("Fb_ref") is None:
        return json.dumps({"ok": False, "reason": "Fb_ref is required"})
    kwargs = {k: a[k] for k in ("CD", "CM", "Ct", "CL", "CF", "Cfu", "Ci", "Cr") if k in a}
    result = adjusted_Fb(a["Fb_ref"], **kwargs)
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_adjusted_Fc
# ---------------------------------------------------------------------------

_adj_Fc_spec = ToolSpec(
    name="timber_adjusted_Fc",
    description=(
        "Compute adjusted allowable compression-parallel stress Fc' (NDS §2.3).\n"
        "\n"
        "Fc' = Fc_ref × CD × CM × Ct × CF × Ci × CP\n"
        "\n"
        "All factors default to 1.0 if not supplied.\n"
        "Returns Fc_prime_psi and factor breakdown.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Fc_ref": {"type": "number", "description": "Reference compression stress (psi). Must be > 0."},
            "CD": {"type": "number", "description": "Load-duration factor (default 1.0)."},
            "CM": {"type": "number", "description": "Wet-service factor (default 1.0)."},
            "Ct": {"type": "number", "description": "Temperature factor (default 1.0)."},
            "CF": {"type": "number", "description": "Size factor (default 1.0)."},
            "Ci": {"type": "number", "description": "Incising factor (default 1.0)."},
            "CP": {"type": "number", "description": "Column stability factor (default 1.0)."},
        },
        "required": ["Fc_ref"],
    },
)


@register(_adj_Fc_spec, write=False)
async def run_timber_adjusted_Fc(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("Fc_ref") is None:
        return json.dumps({"ok": False, "reason": "Fc_ref is required"})
    kwargs = {k: a[k] for k in ("CD", "CM", "Ct", "CF", "Ci", "CP") if k in a}
    result = adjusted_Fc(a["Fc_ref"], **kwargs)
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_sawn_section
# ---------------------------------------------------------------------------

_sawn_section_spec = ToolSpec(
    name="timber_sawn_section",
    description=(
        "Get dressed (S4S) dimensions and section properties for standard sawn lumber.\n"
        "\n"
        "Converts nominal size to actual dressed dimensions per NDS Supplement Table 1B, "
        "then computes A (in²), S (in³), I (in⁴).\n"
        "\n"
        "Supported nominal sizes include: 2x4 through 2x14, 3x–4x series, 6x–12x series.\n"
        "\n"
        "Returns b_actual_in, d_actual_in, A_in2, S_in3, I_in4.\n"
        "\n"
        "Errors: {ok:false, reason} for unsupported nominal sizes. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "b_nom_in": {"type": "integer", "description": "Nominal breadth (in), e.g. 2, 3, 4, 6, 8."},
            "d_nom_in": {"type": "integer", "description": "Nominal depth (in), e.g. 4, 6, 8, 10, 12."},
        },
        "required": ["b_nom_in", "d_nom_in"],
    },
)


@register(_sawn_section_spec, write=False)
async def run_timber_sawn_section(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("b_nom_in", "d_nom_in"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = sawn_section(a["b_nom_in"], a["d_nom_in"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_glulam_section
# ---------------------------------------------------------------------------

_glulam_section_spec = ToolSpec(
    name="timber_glulam_section",
    description=(
        "Compute section properties for a glulam using actual dimensions.\n"
        "\n"
        "Returns A (in²), S (in³), I (in⁴) for a rectangular glulam cross-section.\n"
        "\n"
        "Errors: {ok:false, reason} for non-positive dimensions. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "b_in": {"type": "number", "description": "Actual breadth (in). Must be > 0."},
            "d_in": {"type": "number", "description": "Actual depth (in). Must be > 0."},
        },
        "required": ["b_in", "d_in"],
    },
)


@register(_glulam_section_spec, write=False)
async def run_timber_glulam_section(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("b_in", "d_in"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = glulam_section(a["b_in"], a["d_in"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_check_bending
# ---------------------------------------------------------------------------

_check_bending_spec = ToolSpec(
    name="timber_check_bending",
    description=(
        "Check bending: fb <= Fb' (NDS §3.3).\n"
        "\n"
        "Returns utilization ratio (fb/Fb'), pass/fail flag, and warnings.\n"
        "A warning is added if fb > Fb' (fails).\n"
        "\n"
        "Errors: {ok:false, reason} for non-positive inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fb_psi": {"type": "number", "description": "Actual bending stress (psi). Must be > 0."},
            "Fb_prime_psi": {"type": "number", "description": "Adjusted allowable bending stress Fb' (psi). Must be > 0."},
        },
        "required": ["fb_psi", "Fb_prime_psi"],
    },
)


@register(_check_bending_spec, write=False)
async def run_timber_check_bending(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("fb_psi", "Fb_prime_psi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = check_bending(a["fb_psi"], a["Fb_prime_psi"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_check_shear
# ---------------------------------------------------------------------------

_check_shear_spec = ToolSpec(
    name="timber_check_shear",
    description=(
        "Check horizontal shear: fv <= Fv' (NDS §3.4).\n"
        "\n"
        "Returns utilization ratio and warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fv_psi": {"type": "number", "description": "Actual shear stress (psi). Must be > 0."},
            "Fv_prime_psi": {"type": "number", "description": "Adjusted allowable shear stress Fv' (psi). Must be > 0."},
        },
        "required": ["fv_psi", "Fv_prime_psi"],
    },
)


@register(_check_shear_spec, write=False)
async def run_timber_check_shear(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("fv_psi", "Fv_prime_psi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = check_shear(a["fv_psi"], a["Fv_prime_psi"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_check_deflection
# ---------------------------------------------------------------------------

_check_deflection_spec = ToolSpec(
    name="timber_check_deflection",
    description=(
        "Check deflection limits for live load and total load (NDS Table 3.5).\n"
        "\n"
        "Default limits: live load L/360, total load L/240.\n"
        "Returns util_L (live), util_TL (total), live_ok, total_ok, and warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "delta_L_in": {"type": "number", "description": "Live-load deflection (in). Must be >= 0."},
            "delta_TL_in": {"type": "number", "description": "Total-load deflection (in). Must be >= 0."},
            "span_in": {"type": "number", "description": "Clear span (in). Must be > 0."},
            "limit_L": {"type": "number", "description": "Live-load denominator (default 360)."},
            "limit_TL": {"type": "number", "description": "Total-load denominator (default 240)."},
        },
        "required": ["delta_L_in", "delta_TL_in", "span_in"],
    },
)


@register(_check_deflection_spec, write=False)
async def run_timber_check_deflection(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("delta_L_in", "delta_TL_in", "span_in"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs = {k: a[k] for k in ("limit_L", "limit_TL") if k in a}
    result = check_deflection(a["delta_L_in"], a["delta_TL_in"], a["span_in"], **kwargs)
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_column_stability
# ---------------------------------------------------------------------------

_column_stability_spec = ToolSpec(
    name="timber_column_stability",
    description=(
        "Compute column stability factor CP and critical buckling stress FcE "
        "for a timber column (NDS §3.7.1 Ylinen equation).\n"
        "\n"
        "Steps: FcE = 0.822·E'_min / (le/d)²; then CP via Ylinen with c=0.8 "
        "(sawn lumber).\n"
        "\n"
        "Returns CP, FcE_psi, alpha, le_d, and warnings if slenderness > 50.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "le_d": {
                "type": "number",
                "description": "Slenderness ratio le/d (effective length / least dimension). Must be > 0.",
            },
            "Fc_star_psi": {
                "type": "number",
                "description": "Fc* = Fc × all factors except CP (psi). Must be > 0.",
            },
            "E_prime_min_psi": {
                "type": "number",
                "description": "Adjusted minimum modulus E'_min (psi). Must be > 0.",
            },
        },
        "required": ["le_d", "Fc_star_psi", "E_prime_min_psi"],
    },
)


@register(_column_stability_spec, write=False)
async def run_timber_column_stability(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("le_d", "Fc_star_psi", "E_prime_min_psi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    # First compute FcE
    fce_res = FcE_critical(a["E_prime_min_psi"], a["le_d"])
    if not fce_res["ok"]:
        return json.dumps(fce_res)
    FcE_psi = fce_res["FcE_psi"]
    cp_res = CP_column_stability(a["le_d"], a["Fc_star_psi"], FcE_psi)
    if not cp_res["ok"]:
        return json.dumps(cp_res)
    # Merge FcE into CP result
    cp_res["FcE_psi"] = FcE_psi
    cp_res["E_prime_min_psi"] = float(a["E_prime_min_psi"])
    warnings = fce_res.get("warnings", []) + cp_res.get("warnings", [])
    cp_res["warnings"] = warnings
    return ok_payload(cp_res)


# ---------------------------------------------------------------------------
# Tool: timber_check_column
# ---------------------------------------------------------------------------

_check_column_spec = ToolSpec(
    name="timber_check_column",
    description=(
        "Check column compression: fc <= Fc' (NDS §3.7).\n"
        "\n"
        "Returns utilization ratio (fc/Fc'), pass/fail, and warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for non-positive inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fc_psi": {"type": "number", "description": "Actual compression stress (psi). Must be > 0."},
            "Fc_prime_psi": {"type": "number", "description": "Adjusted allowable compression stress Fc' (psi). Must be > 0."},
        },
        "required": ["fc_psi", "Fc_prime_psi"],
    },
)


@register(_check_column_spec, write=False)
async def run_timber_check_column(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("fc_psi", "Fc_prime_psi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = check_compression_column(a["fc_psi"], a["Fc_prime_psi"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_check_combined
# ---------------------------------------------------------------------------

_check_combined_spec = ToolSpec(
    name="timber_check_combined",
    description=(
        "Check combined bending + axial compression interaction (NDS §3.9.2).\n"
        "\n"
        "NDS Eq. 3.9-3: (fc/Fc')² + fb / (Fb' × (1 - fc/FcE)) <= 1.0, "
        "Fc' = Fc*·CP\n"
        "\n"
        "Returns interaction ratio, pass/fail, and warnings.\n"
        "Warns if fc >= FcE (Euler buckling imminent).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fb_psi": {"type": "number", "description": "Actual bending stress (psi). Must be >= 0."},
            "Fb_prime_psi": {"type": "number", "description": "Adjusted Fb' (psi). Must be > 0."},
            "fc_psi": {"type": "number", "description": "Actual compression stress (psi). Must be >= 0."},
            "Fc_star_psi": {"type": "number", "description": "Fc* = Fc × all factors except CP (psi). Must be > 0."},
            "FcE_psi": {"type": "number", "description": "Euler critical buckling stress (psi). Must be > 0."},
            "CP": {"type": "number", "description": "Column-stability factor (NDS §3.7.1), 0 < CP <= 1. The axial term uses Fc' = Fc*·CP. Default 1.0."},
        },
        "required": ["fb_psi", "Fb_prime_psi", "fc_psi", "Fc_star_psi", "FcE_psi"],
    },
)


@register(_check_combined_spec, write=False)
async def run_timber_check_combined(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("fb_psi", "Fb_prime_psi", "fc_psi", "Fc_star_psi", "FcE_psi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = check_combined_bending_axial(
        a["fb_psi"], a["Fb_prime_psi"], a["fc_psi"], a["Fc_star_psi"], a["FcE_psi"],
        a.get("CP", 1.0),
    )
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_check_bearing
# ---------------------------------------------------------------------------

_check_bearing_spec = ToolSpec(
    name="timber_check_bearing",
    description=(
        "Check bearing perpendicular to grain: fc_perp <= Fc_perp' (NDS §3.10).\n"
        "\n"
        "Returns utilization ratio and warnings.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fc_perp_psi": {"type": "number", "description": "Actual bearing stress perpendicular to grain (psi). Must be > 0."},
            "Fc_perp_prime_psi": {"type": "number", "description": "Adjusted Fc_perp' (psi). Must be > 0."},
        },
        "required": ["fc_perp_psi", "Fc_perp_prime_psi"],
    },
)


@register(_check_bearing_spec, write=False)
async def run_timber_check_bearing(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("fc_perp_psi", "Fc_perp_prime_psi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = check_bearing(a["fc_perp_psi"], a["Fc_perp_prime_psi"])
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_lateral_yield_bolt
# ---------------------------------------------------------------------------

_lateral_yield_spec = ToolSpec(
    name="timber_lateral_yield_bolt",
    description=(
        "Compute single-fastener lateral design value Z (lb) for a bolt or lag "
        "screw in single shear using NDS yield-limit equations (Table I2.2).\n"
        "\n"
        "Evaluates all six yield modes (Im, Is, II, IIIm, IIIs, IV) and returns "
        "the governing (minimum) mode and Z value.\n"
        "\n"
        "Parameters: D (diameter), tm (main-member bearing length), "
        "ts (side-member bearing length), Fyb (fastener yield strength psi), "
        "Fe_m and Fe_s (dowel bearing strengths psi), theta_deg (load-to-grain angle).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D_in": {"type": "number", "description": "Fastener diameter (in). Must be > 0."},
            "tm_in": {"type": "number", "description": "Main-member dowel bearing length (in). Must be > 0."},
            "ts_in": {"type": "number", "description": "Side-member dowel bearing length (in). Must be > 0."},
            "Fyb_psi": {"type": "number", "description": "Fastener bending yield strength (psi). Must be > 0."},
            "Fe_m_psi": {"type": "number", "description": "Dowel bearing strength of main member (psi). Must be > 0."},
            "Fe_s_psi": {"type": "number", "description": "Dowel bearing strength of side member (psi). Must be > 0."},
            "theta_deg": {"type": "number", "description": "Angle of load to grain (degrees, 0=parallel). Default 0."},
        },
        "required": ["D_in", "tm_in", "ts_in", "Fyb_psi", "Fe_m_psi", "Fe_s_psi"],
    },
)


@register(_lateral_yield_spec, write=False)
async def run_timber_lateral_yield_bolt(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("D_in", "tm_in", "ts_in", "Fyb_psi", "Fe_m_psi", "Fe_s_psi"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs = {}
    if "theta_deg" in a:
        kwargs["theta_deg"] = a["theta_deg"]
    result = lateral_yield_bolt(
        a["D_in"], a["tm_in"], a["ts_in"],
        a["Fyb_psi"], a["Fe_m_psi"], a["Fe_s_psi"],
        **kwargs,
    )
    return ok_payload(result) if result["ok"] else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: timber_withdrawal_nail
# ---------------------------------------------------------------------------

_withdrawal_nail_spec = ToolSpec(
    name="timber_withdrawal_nail",
    description=(
        "Compute nail withdrawal capacity per NDS §12.2.\n"
        "\n"
        "W = 1380 × G^(5/2) × D^(3/2) [lb per inch of penetration]\n"
        "\n"
        "Returns W_per_in_lb (capacity per inch) and W_total_lb for the given "
        "penetration length.\n"
        "\n"
        "Typical specific gravity G: Douglas Fir-Larch 0.50, Southern Pine 0.55, "
        "Hem-Fir 0.43, SPF 0.42.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "D_in": {"type": "number", "description": "Nail shank diameter (in). Must be > 0."},
            "L_pen_in": {"type": "number", "description": "Penetration into main member (in). Must be > 0."},
            "G": {"type": "number", "description": "Specific gravity of wood (oven-dry). E.g. 0.50 for DF-L."},
        },
        "required": ["D_in", "L_pen_in", "G"],
    },
)


@register(_withdrawal_nail_spec, write=False)
async def run_timber_withdrawal_nail(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("D_in", "L_pen_in", "G"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = withdrawal_nail(a["D_in"], a["L_pen_in"], a["G"])
    return ok_payload(result) if result["ok"] else json.dumps(result)
