"""
kerf_cad_core.tolfits.tools — LLM tool wrappers for ISO 286 limits & fits.

Registers five tools with the Kerf tool registry:

  iso286_it_tolerance   — IT tolerance grade value for a nominal size
  iso286_shaft_limits   — shaft upper/lower deviations (es, ei)
  iso286_hole_limits    — hole upper/lower deviations (ES, EI)
  iso286_fit_analysis   — fit classification + clearance/interference limits
  iso286_preferred_fits — ISO 286-2 preferred fit table with optional calc
  iso286_press_fit      — Lamé thick-cylinder interference / press-fit analysis

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": False, "reason": "..."} — tools never raise.

References
----------
ISO 286-1:2010 — Limits and fits (tolerance grades, fundamental deviations)
ISO 286-2:2010 — Preferred fits and limit deviations
Shigley's MED 10th ed. — §2-13 press-fit / Lamé equations

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.tolfits.fits import (
    it_tolerance,
    shaft_limits,
    hole_limits,
    fit_analysis,
    preferred_fits,
    press_fit,
)


# ---------------------------------------------------------------------------
# Tool: iso286_it_tolerance
# ---------------------------------------------------------------------------

_it_tolerance_spec = ToolSpec(
    name="iso286_it_tolerance",
    description=(
        "Return the ISO 286-1 standard tolerance grade (IT) value for a given "
        "nominal size and grade.\n"
        "\n"
        "The IT value is the fundamental building block of all ISO 286 tolerances. "
        "It is computed from the standard tolerance unit:\n"
        "  i = 0.45·D^(1/3) + 0.001·D  (µm, D = geometric mean of size band, mm)\n"
        "and multiplied by the grade factor (e.g. IT6 = 10·i, IT7 = 16·i).\n"
        "\n"
        "Valid grades: IT01, IT0, IT1 … IT18.\n"
        "Valid nominal size: 0 < nominal_mm ≤ 3150 mm.\n"
        "\n"
        "Returns IT_um (µm) and IT_mm plus the size band and tolerance unit.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nominal_mm": {
                "type": "number",
                "description": "Nominal size (mm). Must be in (0, 3150].",
            },
            "grade": {
                "type": "string",
                "description": (
                    "IT tolerance grade: 'IT01', 'IT0', 'IT1', 'IT2', ..., 'IT18'. "
                    "Common engineering grades: IT6 (precision), IT7 (general), "
                    "IT8 (medium), IT11 (free machining)."
                ),
            },
        },
        "required": ["nominal_mm", "grade"],
    },
)


@register(_it_tolerance_spec, write=False)
async def run_iso286_it_tolerance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("nominal_mm") is None:
        return json.dumps({"ok": False, "reason": "nominal_mm is required"})
    if a.get("grade") is None:
        return json.dumps({"ok": False, "reason": "grade is required"})

    result = it_tolerance(a["nominal_mm"], a["grade"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: iso286_shaft_limits
# ---------------------------------------------------------------------------

_shaft_limits_spec = ToolSpec(
    name="iso286_shaft_limits",
    description=(
        "Compute the upper (es) and lower (ei) shaft deviations per ISO 286-1 "
        "for a given nominal diameter and tolerance designation.\n"
        "\n"
        "Shaft designations use lowercase letter codes: a, b, c, d, e, f, g, h "
        "(clearance shafts, negative es), js (symmetric), j, k, m, n "
        "(transition), p, r, s, t, u, v, x, y, z, za, zb, zc "
        "(interference shafts, positive ei).\n"
        "\n"
        "Examples: 'h6', 'g6', 'k6', 'p6', 's7', 'f7', 'h7'\n"
        "\n"
        "Returns:\n"
        "  es_um  — upper shaft deviation (µm; negative for a..h, positive for k..zc)\n"
        "  ei_um  — lower shaft deviation (µm; = es - IT)\n"
        "  upper_limit_mm — nominal + es/1000  (maximum shaft size)\n"
        "  lower_limit_mm — nominal + ei/1000  (minimum shaft size)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nominal_mm": {
                "type": "number",
                "description": "Nominal shaft diameter (mm). Must be in (0, 3150].",
            },
            "designation": {
                "type": "string",
                "description": (
                    "Shaft tolerance designation (lowercase letter + digit), "
                    "e.g. 'h6', 'g6', 'k6', 'p6', 's7', 'f7'."
                ),
            },
        },
        "required": ["nominal_mm", "designation"],
    },
)


@register(_shaft_limits_spec, write=False)
async def run_iso286_shaft_limits(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("nominal_mm") is None:
        return json.dumps({"ok": False, "reason": "nominal_mm is required"})
    if a.get("designation") is None:
        return json.dumps({"ok": False, "reason": "designation is required"})

    result = shaft_limits(a["nominal_mm"], a["designation"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: iso286_hole_limits
# ---------------------------------------------------------------------------

_hole_limits_spec = ToolSpec(
    name="iso286_hole_limits",
    description=(
        "Compute the upper (ES) and lower (EI) hole deviations per ISO 286-1 "
        "for a given nominal diameter and tolerance designation.\n"
        "\n"
        "Hole designations use uppercase letter codes: A, B, C, D, E, F, G, H "
        "(clearance holes, positive EI), JS (symmetric), J, K, M, N "
        "(transition), P, R, S, T, U, V, X, Y, Z, ZA, ZB, ZC "
        "(interference holes, negative ES).\n"
        "\n"
        "The reference hole is H (EI = 0).  The hole-basis system uses H holes "
        "paired with various shaft codes to achieve different fits.\n"
        "\n"
        "Examples: 'H7', 'H8', 'F8', 'G7', 'K7', 'N7', 'P7'\n"
        "\n"
        "Returns:\n"
        "  EI_um  — lower hole deviation (µm; 0 for H, positive for A..G)\n"
        "  ES_um  — upper hole deviation (µm; = EI + IT)\n"
        "  upper_limit_mm — nominal + ES/1000  (maximum hole size)\n"
        "  lower_limit_mm — nominal + EI/1000  (minimum hole size)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nominal_mm": {
                "type": "number",
                "description": "Nominal hole diameter (mm). Must be in (0, 3150].",
            },
            "designation": {
                "type": "string",
                "description": (
                    "Hole tolerance designation (uppercase letter + digit), "
                    "e.g. 'H7', 'H8', 'F8', 'G7', 'K7', 'N7', 'P7'."
                ),
            },
        },
        "required": ["nominal_mm", "designation"],
    },
)


@register(_hole_limits_spec, write=False)
async def run_iso286_hole_limits(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("nominal_mm") is None:
        return json.dumps({"ok": False, "reason": "nominal_mm is required"})
    if a.get("designation") is None:
        return json.dumps({"ok": False, "reason": "designation is required"})

    result = hole_limits(a["nominal_mm"], a["designation"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: iso286_fit_analysis
# ---------------------------------------------------------------------------

_fit_analysis_spec = ToolSpec(
    name="iso286_fit_analysis",
    description=(
        "Compute fit classification and clearance / interference limits for a "
        "hole + shaft combination per ISO 286-1/2.\n"
        "\n"
        "Clearance  = hole_size − shaft_size.\n"
        "  Positive → shaft fits freely inside hole (play).\n"
        "  Negative → interference (shaft must be pressed / shrunk in).\n"
        "\n"
        "Fit types:\n"
        "  clearance    — min_clearance >= 0; always plays\n"
        "  transition   — can be either clearance or interference depending on actual sizes\n"
        "  interference — max_clearance <= 0; always requires force or temperature assembly\n"
        "\n"
        "Common ISO preferred fits (hole-basis):\n"
        "  H7/g6  — sliding fit        H7/k6  — transition\n"
        "  H7/h6  — locational clear   H7/p6  — locational interference\n"
        "  H7/s6  — medium drive       H7/u6  — force fit\n"
        "\n"
        "Returns max/min clearance and interference in mm, fit type, "
        "and all four limit dimensions.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nominal_mm": {
                "type": "number",
                "description": "Nominal diameter (mm). Must be in (0, 3150].",
            },
            "hole_designation": {
                "type": "string",
                "description": (
                    "Hole tolerance designation, e.g. 'H7', 'H8', 'G7'. "
                    "Must use uppercase letter code."
                ),
            },
            "shaft_designation": {
                "type": "string",
                "description": (
                    "Shaft tolerance designation, e.g. 'g6', 'k6', 'h7', 's6'. "
                    "Must use lowercase letter code."
                ),
            },
        },
        "required": ["nominal_mm", "hole_designation", "shaft_designation"],
    },
)


@register(_fit_analysis_spec, write=False)
async def run_iso286_fit_analysis(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("nominal_mm", "hole_designation", "shaft_designation"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = fit_analysis(a["nominal_mm"], a["hole_designation"], a["shaft_designation"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: iso286_preferred_fits
# ---------------------------------------------------------------------------

_preferred_fits_spec = ToolSpec(
    name="iso286_preferred_fits",
    description=(
        "List ISO 286-2 preferred fits for the hole-basis or shaft-basis system, "
        "optionally filtered by fit type and computed for a specific nominal size.\n"
        "\n"
        "The ISO preferred fits cover the full range from loose running to force fit:\n"
        "\n"
        "Hole-basis system (H hole + various shafts):\n"
        "  H11/c11 — Loose running       H7/h6 — Locational clearance\n"
        "  H9/d9   — Free running         H7/k6 — Locational transition\n"
        "  H8/f7   — Close running        H7/p6 — Locational interference\n"
        "  H7/g6   — Sliding              H7/s6 — Medium drive\n"
        "                                 H7/u6 — Force fit\n"
        "\n"
        "When nominal_mm is provided, actual clearance/interference values are "
        "computed for each fit using iso286_fit_analysis.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nominal_mm": {
                "type": "number",
                "description": (
                    "Nominal diameter (mm). If provided, clearance/interference "
                    "values are computed for each preferred fit."
                ),
            },
            "system": {
                "type": "string",
                "enum": ["hole-basis", "shaft-basis"],
                "description": (
                    "'hole-basis' (default): H holes with varying shafts. "
                    "'shaft-basis': h shafts with varying holes."
                ),
            },
            "fit_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["clearance", "transition", "interference"],
                },
                "description": (
                    "Filter by fit type(s). Default: return all types."
                ),
            },
        },
        "required": [],
    },
)


@register(_preferred_fits_spec, write=False)
async def run_iso286_preferred_fits(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    kwargs: dict = {}
    if "nominal_mm" in a:
        kwargs["nominal_mm"] = a["nominal_mm"]
    if "system" in a:
        kwargs["system"] = a["system"]
    if "fit_types" in a:
        kwargs["fit_types"] = a["fit_types"]

    result = preferred_fits(**kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: iso286_press_fit
# ---------------------------------------------------------------------------

_press_fit_spec = ToolSpec(
    name="iso286_press_fit",
    description=(
        "Lamé thick-cylinder interference / press-fit analysis.\n"
        "\n"
        "Given a diametral interference δ between a hub (outer cylinder) and shaft "
        "(inner cylinder), computes:\n"
        "\n"
        "  contact_pressure_MPa       — interface contact pressure p_c (MPa)\n"
        "  hub_hoop_stress_inner_Pa   — max tensile hoop stress in hub at bore\n"
        "  hub_hoop_stress_outer_Pa   — tensile hoop stress at hub outer radius\n"
        "  shaft_hoop_stress_inner_Pa — hoop stress at shaft bore (compressive)\n"
        "  assembly_force_N           — axial press-in force (N) if length provided\n"
        "  shrink_fit_delta_T_C       — minimum ΔT to assemble by heating hub\n"
        "\n"
        "Overstress flags are set if yield strengths are provided and exceeded.\n"
        "Warnings are issued (not exceptions) for boundary conditions.\n"
        "\n"
        "Lamé equations (thick-walled cylinder):\n"
        "  σ_θ(r) = p_c·r_i²/(r_o²−r_i²)·(1 + r_o²/r²)   [hub, tensile]\n"
        "  σ_θ(r) = −p_c·r_i²/(r_i²−r_b²)·(1 + r_b²/r²)  [shaft, compressive]\n"
        "\n"
        "For solid shafts (shaft_bore_mm = 0, default):\n"
        "  shaft hoop stress = −p_c  (uniform compression)\n"
        "\n"
        "References: Shigley's MED 10th ed. §2-13, eq. (2-57)–(2-62)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid geometry.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "nominal_mm": {
                "type": "number",
                "description": (
                    "Nominal interface diameter (mm) — outer diameter of shaft "
                    "and inner diameter of hub. Must be > 0."
                ),
            },
            "interference_mm": {
                "type": "number",
                "description": (
                    "Total diametral interference δ (mm). Must be ≥ 0. "
                    "Positive = shaft is larger than hole."
                ),
            },
            "hub_outer_mm": {
                "type": "number",
                "description": (
                    "Outer diameter of hub (mm). Must be > nominal_mm."
                ),
            },
            "shaft_bore_mm": {
                "type": "number",
                "description": (
                    "Inner bore diameter of shaft (mm). 0 = solid shaft (default)."
                ),
            },
            "E_hub_Pa": {
                "type": "number",
                "description": (
                    "Hub Young's modulus (Pa). Default: 200e9 (steel)."
                ),
            },
            "E_shaft_Pa": {
                "type": "number",
                "description": (
                    "Shaft Young's modulus (Pa). Default: 200e9 (steel)."
                ),
            },
            "nu_hub": {
                "type": "number",
                "description": "Hub Poisson's ratio. Default: 0.3 (steel).",
            },
            "nu_shaft": {
                "type": "number",
                "description": "Shaft Poisson's ratio. Default: 0.3 (steel).",
            },
            "mu_friction": {
                "type": "number",
                "description": (
                    "Coefficient of friction for assembly force calculation. "
                    "Default: 0.12 (dry steel on steel)."
                ),
            },
            "length_mm": {
                "type": "number",
                "description": (
                    "Axial interface length (mm). Required to compute assembly force."
                ),
            },
            "yield_strength_hub_Pa": {
                "type": "number",
                "description": (
                    "Hub material yield strength (Pa). If provided, overstress "
                    "check is performed."
                ),
            },
            "yield_strength_shaft_Pa": {
                "type": "number",
                "description": (
                    "Shaft material yield strength (Pa). If provided, overstress "
                    "check is performed."
                ),
            },
            "alpha_hub": {
                "type": "number",
                "description": (
                    "Hub linear thermal expansion coefficient (1/°C). "
                    "Default: 12e-6 (steel)."
                ),
            },
            "alpha_shaft": {
                "type": "number",
                "description": (
                    "Shaft linear thermal expansion coefficient (1/°C). "
                    "Default: 12e-6 (steel)."
                ),
            },
        },
        "required": ["nominal_mm", "interference_mm", "hub_outer_mm"],
    },
)


@register(_press_fit_spec, write=False)
async def run_iso286_press_fit(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("nominal_mm", "interference_mm", "hub_outer_mm"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for opt in (
        "shaft_bore_mm", "E_hub_Pa", "E_shaft_Pa",
        "nu_hub", "nu_shaft", "mu_friction",
        "length_mm", "yield_strength_hub_Pa", "yield_strength_shaft_Pa",
        "alpha_hub", "alpha_shaft",
    ):
        if opt in a:
            kwargs[opt] = a[opt]

    result = press_fit(a["nominal_mm"], a["interference_mm"], a["hub_outer_mm"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)
