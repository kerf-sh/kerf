"""
kerf_cad_core.composites.tools — LLM tool wrappers for composite laminate analysis.

Registers six tools with the Kerf tool registry:

  composite_reduced_stiffness    — lamina reduced stiffness Q from engineering constants
  composite_transform_Q          — transformed reduced stiffness Q̄(θ) for a ply angle
  composite_abd_matrix           — ABD matrix for a stacking sequence
  composite_laminate_response    — mid-plane strains/curvatures from N,M loads
  composite_failure_indices      — per-ply failure indices (max-stress, Tsai-Wu, etc.)
  composite_engineering_moduli   — effective laminate Ex, Ey, Gxy, nu_xy
  composite_first_ply_failure    — first-ply-failure load scaling factor

All tools are pure-Python; no OCC dependency.
Errors returned as {ok: false, reason: "..."} — tools never raise.

References
----------
Jones, R.M. "Mechanics of Composite Materials", 2nd ed. (1999)
Gibson, R.F. "Principles of Composite Material Mechanics", 4th ed. (2016)

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.composites.laminate import (
    reduced_stiffness,
    transform_Q,
    abd_matrix,
    laminate_response,
    failure_indices,
    laminate_engineering_moduli,
    first_ply_failure_load,
)


# ---------------------------------------------------------------------------
# Tool: composite_reduced_stiffness
# ---------------------------------------------------------------------------

_reduced_stiffness_spec = ToolSpec(
    name="composite_reduced_stiffness",
    description=(
        "Compute the plane-stress reduced stiffness matrix Q for a unidirectional "
        "composite ply from its engineering constants.\n"
        "\n"
        "Classical Lamination Theory (CLT) uses Q to relate in-plane strains to "
        "stresses in the principal material axes of the ply.  The matrix is 3×3 "
        "(Voigt notation: 11, 22, 12):\n"
        "  Q11 = E1/(1 - ν12·ν21),  Q22 = E2/(1 - ν12·ν21),\n"
        "  Q12 = ν12·E2/(1-ν12·ν21),  Q66 = G12\n"
        "\n"
        "Returns Q as a 9-element flat list (row-major) and individual components.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "E1": {
                "type": "number",
                "description": "Young's modulus in fibre direction (Pa). Must be > 0.",
            },
            "E2": {
                "type": "number",
                "description": "Young's modulus transverse to fibre (Pa). Must be > 0.",
            },
            "nu12": {
                "type": "number",
                "description": (
                    "Major Poisson ratio. Must be > 0 and satisfy "
                    "ν12 < sqrt(E1/E2) for positive definiteness."
                ),
            },
            "G12": {
                "type": "number",
                "description": "In-plane shear modulus (Pa). Must be > 0.",
            },
        },
        "required": ["E1", "E2", "nu12", "G12"],
    },
)


@register(_reduced_stiffness_spec, write=False)
async def run_composite_reduced_stiffness(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("E1", "E2", "nu12", "G12"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = reduced_stiffness(a["E1"], a["E2"], a["nu12"], a["G12"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: composite_transform_Q
# ---------------------------------------------------------------------------

_transform_Q_spec = ToolSpec(
    name="composite_transform_Q",
    description=(
        "Transform the reduced stiffness Q to global (x-y) coordinates for a ply "
        "oriented at angle θ (degrees CCW from the laminate x-axis).\n"
        "\n"
        "Returns the transformed matrix Q̄ (Q-bar) as a 9-element flat list and "
        "individual components Q̄11, Q̄12, Q̄16, Q̄22, Q̄26, Q̄66.\n"
        "\n"
        "Input Q must be a 9-element flat list (row-major 3×3, Voigt notation 11,22,12) "
        "as returned by composite_reduced_stiffness.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 9,
                "maxItems": 9,
                "description": "Reduced stiffness Q as 9-element flat row-major list.",
            },
            "theta_deg": {
                "type": "number",
                "description": "Ply fibre angle in degrees (CCW from x-axis).",
            },
        },
        "required": ["Q", "theta_deg"],
    },
)


@register(_transform_Q_spec, write=False)
async def run_composite_transform_Q(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("Q") is None:
        return json.dumps({"ok": False, "reason": "Q is required"})
    if a.get("theta_deg") is None:
        return json.dumps({"ok": False, "reason": "theta_deg is required"})

    Q = a["Q"]
    if not isinstance(Q, list) or len(Q) != 9:
        return json.dumps({"ok": False, "reason": "Q must be a 9-element list"})

    result = transform_Q(Q, a["theta_deg"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: composite_abd_matrix
# ---------------------------------------------------------------------------

_abd_matrix_spec = ToolSpec(
    name="composite_abd_matrix",
    description=(
        "Assemble the 6×6 ABD stiffness matrix for a composite laminate stacking "
        "sequence.\n"
        "\n"
        "The ABD matrix relates in-plane force resultants (N) and moment resultants "
        "(M) per unit width to mid-plane strains (ε0) and curvatures (κ):\n"
        "  [A B] [ε0]   [N]\n"
        "  [B D] [κ ] = [M]\n"
        "\n"
        "The function also detects symmetric (B≈0) and balanced (A16=A26≈0) layups "
        "and warns via Python warnings if coupling (B≠0) is present.\n"
        "\n"
        "Each ply dict must contain:\n"
        "  E1, E2   — moduli (Pa)\n"
        "  nu12     — major Poisson ratio\n"
        "  G12      — shear modulus (Pa)\n"
        "  thickness— ply thickness (m)\n"
        "  angle_deg— fibre angle (degrees CCW)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "plies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "E1":        {"type": "number"},
                        "E2":        {"type": "number"},
                        "nu12":      {"type": "number"},
                        "G12":       {"type": "number"},
                        "thickness": {"type": "number"},
                        "angle_deg": {"type": "number"},
                    },
                    "required": ["E1", "E2", "nu12", "G12", "thickness", "angle_deg"],
                },
                "description": "Ordered list of ply dicts (bottom to top).",
            },
        },
        "required": ["plies"],
    },
)


@register(_abd_matrix_spec, write=False)
async def run_composite_abd_matrix(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("plies") is None:
        return json.dumps({"ok": False, "reason": "plies is required"})

    result = abd_matrix(a["plies"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: composite_laminate_response
# ---------------------------------------------------------------------------

_laminate_response_spec = ToolSpec(
    name="composite_laminate_response",
    description=(
        "Solve the ABD system for laminate mid-plane strains ε0 and curvatures κ "
        "under applied in-plane force and moment resultants.\n"
        "\n"
        "Solves the 6×6 linear system:\n"
        "  [A B] [ε0]   [Nx, Ny, Nxy]\n"
        "  [B D] [κ ] = [Mx, My, Mxy]\n"
        "using pure-Python Gaussian elimination (no numpy).\n"
        "\n"
        "Units:\n"
        "  Nx, Ny, Nxy  — force per width (N/m)\n"
        "  Mx, My, Mxy  — moment per width (N·m/m = N)\n"
        "\n"
        "Errors: {ok:false, reason} for singular ABD or invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "ABD": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 6,
                    "maxItems": 6,
                },
                "minItems": 6,
                "maxItems": 6,
                "description": (
                    "6×6 ABD matrix as a list of 6 rows of 6 floats, "
                    "as returned by composite_abd_matrix."
                ),
            },
            "N_M": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 6,
                "maxItems": 6,
                "description": "[Nx, Ny, Nxy, Mx, My, Mxy] load vector.",
            },
        },
        "required": ["ABD", "N_M"],
    },
)


@register(_laminate_response_spec, write=False)
async def run_composite_laminate_response(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("ABD") is None:
        return json.dumps({"ok": False, "reason": "ABD is required"})
    if a.get("N_M") is None:
        return json.dumps({"ok": False, "reason": "N_M is required"})

    ABD = a["ABD"]
    if not isinstance(ABD, list) or len(ABD) != 6:
        return json.dumps({"ok": False, "reason": "ABD must be a 6×6 matrix"})

    # Wrap into abd_result dict that laminate_response() expects
    abd_mock = {"ok": True, "ABD": ABD}
    result = laminate_response(abd_mock, a["N_M"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: composite_failure_indices
# ---------------------------------------------------------------------------

_failure_indices_spec = ToolSpec(
    name="composite_failure_indices",
    description=(
        "Compute failure indices for a single composite ply using multiple criteria.\n"
        "\n"
        "Supported criteria:\n"
        "  'max-stress'  — max ratio of |stress component| to its allowable\n"
        "  'max-strain'  — max ratio of |strain component| to its allowable "
        "(requires e1t, e1c, e2t, e2c, g12_allow in strengths)\n"
        "  'tsai-hill'   — Hill quadratic criterion (signed strengths)\n"
        "  'tsai-wu'     — Tsai-Wu tensor polynomial criterion\n"
        "\n"
        "Failure occurs when F.I. >= 1.  Warnings are emitted (never raised) "
        "for failing plies.\n"
        "\n"
        "Errors: {ok:false, reason} for missing strength keys.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stress_material": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "[σ1, σ2, τ12] in material (1-2) axes (Pa).",
            },
            "strain_material": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "[ε1, ε2, γ12] in material (1-2) axes.",
            },
            "strengths": {
                "type": "object",
                "description": (
                    "Ply strength properties (Pa): F1t, F1c, F2t, F2c, F12. "
                    "Optional for max-strain: e1t, e1c, e2t, e2c, g12_allow."
                ),
            },
            "criteria": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["max-stress", "max-strain", "tsai-wu", "tsai-hill"],
                },
                "description": "Failure criteria to evaluate (default: all four).",
            },
        },
        "required": ["stress_material", "strain_material", "strengths"],
    },
)


@register(_failure_indices_spec, write=False)
async def run_composite_failure_indices(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("stress_material", "strain_material", "strengths"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "criteria" in a:
        kwargs["criteria"] = a["criteria"]

    result = failure_indices(
        a["stress_material"],
        a["strain_material"],
        a["strengths"],
        **kwargs,
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: composite_engineering_moduli
# ---------------------------------------------------------------------------

_engineering_moduli_spec = ToolSpec(
    name="composite_engineering_moduli",
    description=(
        "Compute effective laminate in-plane engineering moduli from the A matrix.\n"
        "\n"
        "Returns Ex, Ey, Gxy (Pa) and Poisson ratios nu_xy, nu_yx derived from "
        "the inverse of the extensional stiffness A (membrane approximation).\n"
        "\n"
        "Note: these are membrane-averaged values; bending stiffness (D matrix) "
        "gives different 'flexural moduli' for asymmetric laminates.\n"
        "\n"
        "Errors: {ok:false, reason} for singular A or invalid input.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "A": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 9,
                "maxItems": 9,
                "description": (
                    "Extensional stiffness A as 9-element flat row-major list "
                    "(Pa·m), as returned by composite_abd_matrix."
                ),
            },
            "total_thickness": {
                "type": "number",
                "description": "Total laminate thickness (m). Must be > 0.",
            },
        },
        "required": ["A", "total_thickness"],
    },
)


@register(_engineering_moduli_spec, write=False)
async def run_composite_engineering_moduli(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("A") is None:
        return json.dumps({"ok": False, "reason": "A is required"})
    if a.get("total_thickness") is None:
        return json.dumps({"ok": False, "reason": "total_thickness is required"})

    A = a["A"]
    if not isinstance(A, list) or len(A) != 9:
        return json.dumps({"ok": False, "reason": "A must be a 9-element flat list"})

    abd_mock = {
        "ok": True,
        "A": A,
        "total_thickness": float(a["total_thickness"]),
    }
    result = laminate_engineering_moduli(abd_mock)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: composite_first_ply_failure
# ---------------------------------------------------------------------------

_first_ply_failure_spec = ToolSpec(
    name="composite_first_ply_failure",
    description=(
        "Find the first-ply-failure (FPF) load scaling factor λ for a composite "
        "laminate under proportional loading.\n"
        "\n"
        "The applied load N_M = λ × N_M_unit.  The function returns the smallest "
        "λ > 0 at which any ply first satisfies a failure criterion.\n"
        "\n"
        "Uses bisection search; accurate to better than 1e-6 relative error.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "plies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "E1":        {"type": "number"},
                        "E2":        {"type": "number"},
                        "nu12":      {"type": "number"},
                        "G12":       {"type": "number"},
                        "thickness": {"type": "number"},
                        "angle_deg": {"type": "number"},
                    },
                    "required": ["E1", "E2", "nu12", "G12", "thickness", "angle_deg"],
                },
                "description": "Ordered list of ply dicts (bottom to top).",
            },
            "N_M_unit": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 6,
                "maxItems": 6,
                "description": "Unit load vector [Nx, Ny, Nxy, Mx, My, Mxy] at λ=1.",
            },
            "strengths_list": {
                "type": "array",
                "items": {
                    "type": "object",
                    "description": "Strength dict per ply: F1t, F1c, F2t, F2c, F12 (Pa).",
                },
                "description": "One strength dict per ply, same order as plies.",
            },
            "criteria": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["max-stress", "max-strain", "tsai-wu", "tsai-hill"],
                },
                "description": "Failure criteria to check (default: all four).",
            },
        },
        "required": ["plies", "N_M_unit", "strengths_list"],
    },
)


@register(_first_ply_failure_spec, write=False)
async def run_composite_first_ply_failure(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("plies", "N_M_unit", "strengths_list"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "criteria" in a:
        kwargs["criteria"] = a["criteria"]

    result = first_ply_failure_load(
        a["plies"],
        a["N_M_unit"],
        a["strengths_list"],
        **kwargs,
    )
    return ok_payload(result)
