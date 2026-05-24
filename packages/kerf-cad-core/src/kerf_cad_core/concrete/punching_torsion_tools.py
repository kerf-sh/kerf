"""
kerf_cad_core.concrete.punching_torsion_tools — LLM tool wrappers for
ACI 318-19 §22.6 punching shear and §22.7 torsion design.

Registers five tools with the Kerf tool registry:

  rc_critical_perimeter           — b0 at d/2 from column face
  rc_two_way_shear_strength       — φVc per ACI 318-19 Table 22.6.5.2
  rc_punching_shear_check         — full punching shear adequacy check
  rc_cracking_torsion             — Tcr and threshold torsion Tth
  rc_torsion_capacity             — φTn from stirrups + longitudinal steel
  rc_combined_shear_torsion       — §22.7.7.1 interaction check

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

Units are controlled by the ``metric`` boolean input (default true).
  metric=true  → SI  (MPa, mm, N, N·mm)
  metric=false → US-customary (psi, in, lbf, lb·in)

References
----------
ACI 318-19 §22.6, §22.7.
Wight "Reinforced Concrete: Mechanics and Design" 8th ed.
Nilson, Darwin & Dolan "Design of Concrete Structures" 14th ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.concrete.punching_torsion import (
    critical_perimeter,
    two_way_concrete_shear_strength,
    punching_shear_check,
    cracking_torsion,
    torsion_capacity,
    combined_shear_torsion_check,
)


# ---------------------------------------------------------------------------
# Tool: rc_critical_perimeter
# ---------------------------------------------------------------------------

_rc_crit_perim_spec = ToolSpec(
    name="rc_critical_perimeter",
    description=(
        "ACI 318-19 §22.6.4.1 — critical perimeter b0 at d/2 from column face.\n"
        "\n"
        "Interior: b0 = 2(c1+d) + 2(c2+d).\n"
        "Edge    : b0 = 2(c1+d/2) + (c2+d).  (one free face)\n"
        "Corner  : b0 = (c1+d/2) + (c2+d/2). (two free faces)\n"
        "\n"
        "Units follow 'metric' flag (default true = SI, mm).\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "c1": {"type": "number", "description": "Column dimension in bending direction (mm or in)."},
            "c2": {"type": "number", "description": "Column dimension perpendicular to bending (mm or in)."},
            "d": {"type": "number", "description": "Effective slab depth (mm or in)."},
            "column_location": {
                "type": "string",
                "enum": ["interior", "edge", "corner"],
                "description": "Column location: 'interior' (default), 'edge', or 'corner'.",
            },
            "metric": {"type": "boolean", "description": "True (default) = SI mm; False = US-customary in."},
        },
        "required": ["c1", "c2", "d"],
    },
)


@register(_rc_crit_perim_spec, write=False)
async def run_rc_critical_perimeter(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("c1", "c2", "d"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "column_location" in a:
        kwargs["column_location"] = a["column_location"]

    result = critical_perimeter(a["c1"], a["c2"], a["d"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rc_two_way_shear_strength
# ---------------------------------------------------------------------------

_rc_two_way_spec = ToolSpec(
    name="rc_two_way_shear_strength",
    description=(
        "ACI 318-19 Table 22.6.5.2 — nominal two-way (punching) shear "
        "strength Vc (concrete only, before φ).\n"
        "\n"
        "Returns the minimum of three formulas:\n"
        "  (1) 4·λs·λ·√f'c·b0·d   [USC] / 0.33·λs·λ·√f'c·b0·d [SI]\n"
        "  (2) (2+4/β_c)·λs·λ·√f'c·b0·d  [USC] / (0.17+0.34/β_c)·… [SI]\n"
        "  (3) (αs·d/b0+2)·λs·λ·√f'c·b0·d [USC] / (αs·d/b0+0.17)·… [SI]\n"
        "\n"
        "Size-effect factor λs = min(1, √(2/(1+0.004·d_mm))) per §22.5.5.1.3.\n"
        "Units follow 'metric' flag (default true = SI, N).\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "b0": {"type": "number", "description": "Critical perimeter (mm or in)."},
            "d": {"type": "number", "description": "Effective slab depth (mm or in)."},
            "fc": {"type": "number", "description": "f'c (MPa or psi)."},
            "beta_c": {"type": "number", "description": "Long/short column dimension ratio (≥ 1)."},
            "alpha_s": {"type": "number", "description": "40 = interior, 30 = edge, 20 = corner column."},
            "lam": {"type": "number", "description": "Concrete density factor λ; 1.0 normal-weight (default)."},
            "lambda_s": {"type": "number", "description": "Override size-effect factor λs; computed if omitted."},
            "metric": {"type": "boolean", "description": "True (default) = SI (N); False = US-customary (lbf)."},
        },
        "required": ["b0", "d", "fc", "beta_c", "alpha_s"],
    },
)


@register(_rc_two_way_spec, write=False)
async def run_rc_two_way_shear_strength(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("b0", "d", "fc", "beta_c", "alpha_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("lam", "lambda_s", "metric"):
        if k in a:
            kwargs[k] = a[k]

    result = two_way_concrete_shear_strength(
        a["b0"], a["d"], a["fc"], a["beta_c"], a["alpha_s"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rc_punching_shear_check
# ---------------------------------------------------------------------------

_rc_punch_spec = ToolSpec(
    name="rc_punching_shear_check",
    description=(
        "ACI 318-19 §22.6 punching shear design check (Vu ≤ φVc).\n"
        "\n"
        "Computes φVc from the minimum of three two-way shear formulas with "
        "size-effect factor λs, reports demand/capacity ratio, and flags "
        "which formula governs.  Warns when Vu > φVc.\n"
        "\n"
        "alpha_s: 40 = interior column, 30 = edge, 20 = corner.\n"
        "Units follow 'metric' flag (default true = SI, N).\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Vu": {"type": "number", "description": "Factored punching shear demand (N or lbf)."},
            "b0": {"type": "number", "description": "Critical perimeter at d/2 from column (mm or in)."},
            "d": {"type": "number", "description": "Effective slab depth (mm or in)."},
            "fc": {"type": "number", "description": "f'c (MPa or psi)."},
            "beta_c": {"type": "number", "description": "Long/short column dimension ratio (≥ 1)."},
            "alpha_s": {"type": "number", "description": "40 interior / 30 edge / 20 corner."},
            "phi": {"type": "number", "description": "Strength-reduction factor; default 0.75."},
            "lam": {"type": "number", "description": "Concrete density factor λ; 1.0 normal-weight (default)."},
            "lambda_s": {"type": "number", "description": "Override size-effect factor λs; computed if omitted."},
            "metric": {"type": "boolean", "description": "True (default) = SI (N); False = US-customary (lbf)."},
        },
        "required": ["Vu", "b0", "d", "fc", "beta_c", "alpha_s"],
    },
)


@register(_rc_punch_spec, write=False)
async def run_rc_punching_shear_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Vu", "b0", "d", "fc", "beta_c", "alpha_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("phi", "lam", "lambda_s", "metric"):
        if k in a:
            kwargs[k] = a[k]

    result = punching_shear_check(
        a["Vu"], a["b0"], a["d"], a["fc"], a["beta_c"], a["alpha_s"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rc_cracking_torsion
# ---------------------------------------------------------------------------

_rc_tcr_spec = ToolSpec(
    name="rc_cracking_torsion",
    description=(
        "ACI 318-19 §22.7.4–22.7.5 — cracking torsion Tcr and threshold "
        "torsion below which torsion design may be neglected.\n"
        "\n"
        "  SI:  Tcr = 0.33·λ·√f'c·Acp²/pcp  (N·mm)\n"
        "  USC: Tcr = 4·λ·√f'c·Acp²/pcp     (lb·in)\n"
        "  Tth = Tcr/4;  φ·Tth = 0.75·Tth\n"
        "\n"
        "If Tu ≤ φ·Tth torsion design is not required.\n"
        "Units follow 'metric' flag (default true = SI).\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Acp": {"type": "number", "description": "Gross cross-section area enclosed by outer perimeter (mm² or in²)."},
            "pcp": {"type": "number", "description": "Outer perimeter of gross section (mm or in)."},
            "fc": {"type": "number", "description": "f'c (MPa or psi)."},
            "lam": {"type": "number", "description": "Concrete density factor λ; 1.0 normal-weight (default)."},
            "metric": {"type": "boolean", "description": "True (default) = SI (N·mm); False = US-customary (lb·in)."},
        },
        "required": ["Acp", "pcp", "fc"],
    },
)


@register(_rc_tcr_spec, write=False)
async def run_rc_cracking_torsion(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Acp", "pcp", "fc"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("lam", "metric"):
        if k in a:
            kwargs[k] = a[k]

    result = cracking_torsion(a["Acp"], a["pcp"], a["fc"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rc_torsion_capacity
# ---------------------------------------------------------------------------

_rc_tn_spec = ToolSpec(
    name="rc_torsion_capacity",
    description=(
        "ACI 318-19 §22.7.6 — torsional capacity φTn from closed stirrups "
        "and longitudinal steel.\n"
        "\n"
        "  Ao  = 0.85·Aoh\n"
        "  Tn  = 2·Ao·(At/s)·fyt·cot θ           (§22.7.6.1a)\n"
        "  Al ≥ At·fyt·ph/(s·fy)                  (§22.7.6.1.2 min. Al)\n"
        "\n"
        "θ = 45° per ACI default.  Warns if s > ph/8 or Al < Al_req.\n"
        "Units follow 'metric' flag (default true = SI, N·mm).\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Aoh": {"type": "number", "description": "Area enclosed by centerline of outermost closed stirrups (mm² or in²)."},
            "ph": {"type": "number", "description": "Perimeter of closed stirrups (mm or in)."},
            "fyt": {"type": "number", "description": "Stirrup yield strength (MPa or psi)."},
            "s": {"type": "number", "description": "Stirrup spacing (mm or in)."},
            "At": {"type": "number", "description": "Area of ONE leg of closed stirrup (mm² or in²)."},
            "Al": {"type": "number", "description": "Total area of longitudinal torsion steel (mm² or in²)."},
            "fy": {"type": "number", "description": "Longitudinal steel fy (MPa or psi); defaults to fyt if omitted."},
            "theta_deg": {"type": "number", "description": "Compression diagonal angle (degrees); default 45."},
            "phi": {"type": "number", "description": "Strength-reduction factor; default 0.75."},
            "metric": {"type": "boolean", "description": "True (default) = SI (N·mm); False = US-customary (lb·in)."},
        },
        "required": ["Aoh", "ph", "fyt", "s", "At", "Al"],
    },
)


@register(_rc_tn_spec, write=False)
async def run_rc_torsion_capacity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Aoh", "ph", "fyt", "s", "At", "Al"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("fy", "theta_deg", "phi", "metric"):
        if k in a:
            kwargs[k] = a[k]

    result = torsion_capacity(
        a["Aoh"], a["ph"], a["fyt"], a["s"], a["At"], a["Al"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: rc_combined_shear_torsion
# ---------------------------------------------------------------------------

_rc_cst_spec = ToolSpec(
    name="rc_combined_shear_torsion",
    description=(
        "ACI 318-19 §22.7.7.1 — combined shear + torsion interaction check "
        "for solid sections.\n"
        "\n"
        "  LHS = √[ (Vu/bw·d)² + (Tu·ph/1.7·Aoh²)² ]\n"
        "  RHS = φ·[ Vc/(bw·d) + 0.66·√f'c ]   [SI]\n"
        "        φ·[ Vc/(bw·d) + 8·√f'c   ]    [USC]\n"
        "\n"
        "Returns demand ratio LHS/RHS and ok flag.  Warns when LHS > RHS.\n"
        "Units follow 'metric' flag (default true = SI, MPa/N).\n"
        "Errors: {ok:false, reason}.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Vu": {"type": "number", "description": "Factored shear force (N or lbf)."},
            "Tu": {"type": "number", "description": "Factored torsion (N·mm or lb·in)."},
            "Vc": {"type": "number", "description": "Nominal concrete shear strength (N or lbf); from rc_beam_shear."},
            "b_w": {"type": "number", "description": "Web width (mm or in)."},
            "d": {"type": "number", "description": "Effective depth (mm or in)."},
            "Aoh": {"type": "number", "description": "Area enclosed by stirrup centerline (mm² or in²)."},
            "ph": {"type": "number", "description": "Perimeter of closed stirrups (mm or in)."},
            "fc": {"type": "number", "description": "f'c (MPa or psi)."},
            "phi": {"type": "number", "description": "Strength-reduction factor; default 0.75."},
            "metric": {"type": "boolean", "description": "True (default) = SI; False = US-customary."},
        },
        "required": ["Vu", "Tu", "Vc", "b_w", "d", "Aoh", "ph", "fc"],
    },
)


@register(_rc_cst_spec, write=False)
async def run_rc_combined_shear_torsion(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Vu", "Tu", "Vc", "b_w", "d", "Aoh", "ph", "fc"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    for k in ("phi", "metric"):
        if k in a:
            kwargs[k] = a[k]

    result = combined_shear_torsion_check(
        a["Vu"], a["Tu"], a["Vc"],
        a["b_w"], a["d"], a["Aoh"], a["ph"], a["fc"],
        **kwargs
    )
    return ok_payload(result)
