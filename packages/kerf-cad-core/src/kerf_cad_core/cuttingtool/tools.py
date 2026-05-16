"""
kerf_cad_core.cuttingtool.tools — LLM tool wrappers for cutting-tool geometry,
mechanics & tool-life economics.

Registers tools with the Kerf tool registry:

  cutting_tool_angle_transform       — orthogonal ↔ normal angle conversion
  cutting_tool_merchant              — Merchant orthogonal cutting model
  cutting_tool_specific_energy       — specific cutting energy & power
  cutting_tool_taylor_life           — Taylor VT^n = C tool life
  cutting_tool_taylor_extended_life  — extended Taylor VT^n f^a d^b = C
  cutting_tool_economic_speed        — economic (min-cost) cutting speed
  cutting_tool_max_rate_speed        — max-production-rate cutting speed
  cutting_tool_break_even            — break-even speed range
  cutting_tool_machinability         — machinability rating vs reference
  cutting_tool_surface_finish        — nose-radius theoretical Ra/Rt

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": False, "reason": "..."} — tools never raise.

References
----------
Boothroyd, G. & Knight, W.A. "Fundamentals of Machining and Machine Tools", 3rd ed.
Shaw, M.C. "Metal Cutting Principles", 2nd ed.
Merchant, M.E. (1945) J. Appl. Phys. 16, 267–275.
Taylor, F.W. (1907) Trans. ASME 28, 31–350.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.cuttingtool.tool import (
    orthogonal_to_normal,
    normal_to_orthogonal,
    merchant_orthogonal,
    specific_cutting_energy,
    cutting_power,
    taylor_tool_life,
    taylor_extended_tool_life,
    economic_cutting_speed,
    max_production_rate_speed,
    break_even_speed,
    machinability_rating,
    nose_radius_roughness,
)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_angle_transform
# ---------------------------------------------------------------------------

_angle_transform_spec = ToolSpec(
    name="cutting_tool_angle_transform",
    description=(
        "Convert cutting-tool angles between orthogonal-plane and normal-plane "
        "systems, with optional inclination angle (3D tools).\n"
        "\n"
        "Two directions:\n"
        "  'orthogonal_to_normal' (default) — (γ_o, α_o, λ_s) → (γ_n, α_n)\n"
        "  'normal_to_orthogonal'           — (γ_n, α_n, λ_s) → (γ_o, α_o)\n"
        "\n"
        "Formulas (Boothroyd §2.3 / Shaw §3.2):\n"
        "  tan(γ_n) = tan(γ_o) · cos(λ_s)\n"
        "  tan(α_n) = tan(α_o) · cos(λ_s)\n"
        "\n"
        "All angles in degrees. Negative rake angles are valid.\n"
        "A warning is issued (not an error) for strongly negative rake (< −60°).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["orthogonal_to_normal", "normal_to_orthogonal"],
                "description": "Transform direction. Default: 'orthogonal_to_normal'.",
            },
            "rake_deg": {
                "type": "number",
                "description": (
                    "Input rake angle (degrees). γ_o for orthogonal_to_normal; "
                    "γ_n for normal_to_orthogonal. Negative values are valid."
                ),
            },
            "clearance_deg": {
                "type": "number",
                "description": (
                    "Input clearance angle (degrees). α_o or α_n depending on direction."
                ),
            },
            "inclination_deg": {
                "type": "number",
                "description": (
                    "Inclination angle λ_s (degrees). Default 0 (orthogonal cutting)."
                ),
            },
        },
        "required": ["rake_deg", "clearance_deg"],
    },
)


@register(_angle_transform_spec, write=False)
async def run_cutting_tool_angle_transform(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("rake_deg") is None:
        return json.dumps({"ok": False, "reason": "rake_deg is required"})
    if a.get("clearance_deg") is None:
        return json.dumps({"ok": False, "reason": "clearance_deg is required"})

    direction = a.get("direction", "orthogonal_to_normal")
    rake = a["rake_deg"]
    clearance = a["clearance_deg"]
    inclination = a.get("inclination_deg", 0.0)

    if direction == "normal_to_orthogonal":
        result = normal_to_orthogonal(rake, clearance, inclination)
    else:
        result = orthogonal_to_normal(rake, clearance, inclination)

    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_merchant
# ---------------------------------------------------------------------------

_merchant_spec = ToolSpec(
    name="cutting_tool_merchant",
    description=(
        "Merchant orthogonal cutting model (2D analysis).\n"
        "\n"
        "Computes from tool rake angle, workpiece shear strength, friction\n"
        "coefficient, uncut chip thickness and cutting speed:\n"
        "  • Shear angle φ (Merchant minimum-energy: φ = 45 + γ_o/2 − β/2)\n"
        "  • Chip-thickness ratio r_c and chip thickness t2\n"
        "  • Cutting force Fc and thrust force Ft\n"
        "  • Shear force Fs, friction force F, normal forces\n"
        "  • Chip velocity and shear velocity\n"
        "\n"
        "References: Merchant (1945), Boothroyd §2, Shaw §3.\n"
        "\n"
        "Warnings (not errors) for φ ≤ 0° or φ > 50° or γ_o < −15°.\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "gamma_o_deg": {
                "type": "number",
                "description": "Orthogonal rake angle (degrees). Negative is valid.",
            },
            "tau_s_Pa": {
                "type": "number",
                "description": (
                    "Shear strength of workpiece (Pa). Must be > 0. "
                    "Approx: 0.577 × yield strength for metals."
                ),
            },
            "mu": {
                "type": "number",
                "description": (
                    "Friction coefficient at chip–tool interface. Must be > 0. "
                    "Typical: 0.3–1.0 for steel on carbide."
                ),
            },
            "t1_mm": {
                "type": "number",
                "description": "Uncut chip thickness (mm). Equals feed for orthogonal cutting. Must be > 0.",
            },
            "vc_m_min": {
                "type": "number",
                "description": "Cutting speed (m/min). Must be > 0.",
            },
            "width_b_mm": {
                "type": "number",
                "description": "Width of cut (mm). Default 1.0 mm. Must be > 0.",
            },
        },
        "required": ["gamma_o_deg", "tau_s_Pa", "mu", "t1_mm", "vc_m_min"],
    },
)


@register(_merchant_spec, write=False)
async def run_cutting_tool_merchant(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("gamma_o_deg", "tau_s_Pa", "mu", "t1_mm", "vc_m_min"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "width_b_mm" in a:
        kwargs["width_b"] = a["width_b_mm"]

    result = merchant_orthogonal(
        a["gamma_o_deg"], a["tau_s_Pa"], a["mu"], a["t1_mm"], a["vc_m_min"], **kwargs
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_specific_energy
# ---------------------------------------------------------------------------

_specific_energy_spec = ToolSpec(
    name="cutting_tool_specific_energy",
    description=(
        "Compute specific cutting energy [J/mm³] and cutting power [W] from\n"
        "the tangential cutting force, width of cut, uncut chip thickness and\n"
        "cutting speed.\n"
        "\n"
        "  u = Fc / (b × t1) × 0.06   [J/mm³]\n"
        "  P = Fc × vc / 60            [W]\n"
        "  MRR = b × t1 × vc × 1000   [mm³/min]\n"
        "\n"
        "Typical values: Al 0.4–1.0, steel 1.5–5.0, Ti 3.0–6.0 J/mm³.\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Fc_N": {
                "type": "number",
                "description": "Cutting (tangential) force (N). Must be > 0.",
            },
            "b_mm": {
                "type": "number",
                "description": "Width of cut (mm). Must be > 0.",
            },
            "t1_mm": {
                "type": "number",
                "description": "Uncut chip thickness / feed (mm). Must be > 0.",
            },
            "vc_m_min": {
                "type": "number",
                "description": "Cutting speed (m/min). Must be > 0.",
            },
        },
        "required": ["Fc_N", "b_mm", "t1_mm", "vc_m_min"],
    },
)


@register(_specific_energy_spec, write=False)
async def run_cutting_tool_specific_energy(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("Fc_N", "b_mm", "t1_mm", "vc_m_min"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = specific_cutting_energy(a["Fc_N"], a["b_mm"], a["t1_mm"], a["vc_m_min"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_taylor_life
# ---------------------------------------------------------------------------

_taylor_life_spec = ToolSpec(
    name="cutting_tool_taylor_life",
    description=(
        "Compute tool life from the Taylor equation V × T^n = C.\n"
        "\n"
        "  T = (C / V)^(1/n)   [minutes]\n"
        "\n"
        "Parameters:\n"
        "  V — cutting speed (m/min)\n"
        "  C — Taylor constant: speed for T = 1 min (m/min)\n"
        "  n — Taylor exponent (dimensionless, typically 0.1–0.5)\n"
        "\n"
        "Optionally: provide VB_actual and VB_reference to estimate tool life\n"
        "at a different wear criterion (linear approximation).\n"
        "\n"
        "A warn_range flag is set (not an error) when V/C is outside [0.01, 10].\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_m_min": {
                "type": "number",
                "description": "Cutting speed (m/min). Must be > 0.",
            },
            "C_m_min": {
                "type": "number",
                "description": "Taylor constant C (m/min). Must be > 0.",
            },
            "n": {
                "type": "number",
                "description": "Taylor exponent n (dimensionless). Must be > 0. Typical: 0.1–0.5.",
            },
            "VB_actual_mm": {
                "type": "number",
                "description": "Actual flank wear (mm). Optional; used with VB_reference_mm.",
            },
            "VB_reference_mm": {
                "type": "number",
                "description": "Reference flank-wear criterion (mm) for which C was measured.",
            },
        },
        "required": ["V_m_min", "C_m_min", "n"],
    },
)


@register(_taylor_life_spec, write=False)
async def run_cutting_tool_taylor_life(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("V_m_min", "C_m_min", "n"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "VB_actual_mm" in a:
        kwargs["VB_actual"] = a["VB_actual_mm"]
    if "VB_reference_mm" in a:
        kwargs["VB_reference"] = a["VB_reference_mm"]

    result = taylor_tool_life(a["V_m_min"], a["C_m_min"], a["n"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_taylor_extended_life
# ---------------------------------------------------------------------------

_taylor_ext_spec = ToolSpec(
    name="cutting_tool_taylor_extended_life",
    description=(
        "Extended Taylor equation: V T^n f^a_f d^a_d = C — tool life\n"
        "accounting for feed and depth-of-cut effects.\n"
        "\n"
        "  C_eff = C × (f_ref/f)^a_f × (d_ref/d)^a_d\n"
        "  T     = (C_eff / V)^(1/n)   [minutes]\n"
        "\n"
        "Parameters:\n"
        "  V    — cutting speed (m/min)\n"
        "  C    — Taylor constant calibrated at f_ref, d_ref\n"
        "  n    — Taylor speed exponent\n"
        "  f    — feed (mm/rev)\n"
        "  a_f  — feed exponent (typical 0.3–0.7)\n"
        "  d    — depth of cut (mm)\n"
        "  a_d  — depth exponent (typical 0.1–0.3)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_m_min": {"type": "number", "description": "Cutting speed (m/min). Must be > 0."},
            "C_m_min": {"type": "number", "description": "Taylor constant (m/min). Must be > 0."},
            "n": {"type": "number", "description": "Taylor speed exponent. Must be > 0."},
            "f_mm_rev": {"type": "number", "description": "Feed (mm/rev). Must be > 0."},
            "a_f": {"type": "number", "description": "Feed exponent. Must be >= 0."},
            "d_mm": {"type": "number", "description": "Depth of cut (mm). Must be > 0."},
            "a_d": {"type": "number", "description": "Depth-of-cut exponent. Must be >= 0."},
            "f_ref_mm_rev": {
                "type": "number",
                "description": "Reference feed for C calibration (mm/rev). Default 1.0.",
            },
            "d_ref_mm": {
                "type": "number",
                "description": "Reference depth for C calibration (mm). Default 1.0.",
            },
        },
        "required": ["V_m_min", "C_m_min", "n", "f_mm_rev", "a_f", "d_mm", "a_d"],
    },
)


@register(_taylor_ext_spec, write=False)
async def run_cutting_tool_taylor_extended_life(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("V_m_min", "C_m_min", "n", "f_mm_rev", "a_f", "d_mm", "a_d"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "f_ref_mm_rev" in a:
        kwargs["f_ref"] = a["f_ref_mm_rev"]
    if "d_ref_mm" in a:
        kwargs["d_ref"] = a["d_ref_mm"]

    result = taylor_extended_tool_life(
        a["V_m_min"], a["C_m_min"], a["n"],
        a["f_mm_rev"], a["a_f"],
        a["d_mm"], a["a_d"],
        **kwargs,
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_economic_speed
# ---------------------------------------------------------------------------

_econ_speed_spec = ToolSpec(
    name="cutting_tool_economic_speed",
    description=(
        "Economic (minimum-cost) cutting speed V_e (Boothroyd §9.3).\n"
        "\n"
        "Balances tool-change cost against machining cost to minimise cost\n"
        "per component.\n"
        "\n"
        "  T_e = (1/n − 1) × (t_ct + C_tool/C_m)\n"
        "  V_e = C / T_e^n\n"
        "\n"
        "Parameters:\n"
        "  C_tool — tool cost per cutting edge\n"
        "  t_ct   — tool-change time (min)\n"
        "  t_c    — machining time per component (min)\n"
        "  C_m    — machine + operator cost rate ($/min)\n"
        "  n      — Taylor exponent (must be < 1)\n"
        "  C      — Taylor constant (m/min)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs or n ≥ 1. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "C_tool": {
                "type": "number",
                "description": "Tool cost per cutting edge (same units as C_m × min). Must be > 0.",
            },
            "t_ct_min": {
                "type": "number",
                "description": "Tool-change time per edge (min). Must be > 0.",
            },
            "t_c_min": {
                "type": "number",
                "description": "Machining time per component (min). Must be > 0.",
            },
            "C_m_per_min": {
                "type": "number",
                "description": "Machine + operator cost rate ($/min). Must be > 0.",
            },
            "n": {
                "type": "number",
                "description": "Taylor exponent. Must be > 0 and < 1.",
            },
            "C_m_min": {
                "type": "number",
                "description": "Taylor constant (m/min). Must be > 0.",
            },
        },
        "required": ["C_tool", "t_ct_min", "t_c_min", "C_m_per_min", "n", "C_m_min"],
    },
)


@register(_econ_speed_spec, write=False)
async def run_cutting_tool_economic_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("C_tool", "t_ct_min", "t_c_min", "C_m_per_min", "n", "C_m_min"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = economic_cutting_speed(
        a["C_tool"], a["t_ct_min"], a["t_c_min"], a["C_m_per_min"], a["n"], a["C_m_min"]
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_max_rate_speed
# ---------------------------------------------------------------------------

_max_rate_spec = ToolSpec(
    name="cutting_tool_max_rate_speed",
    description=(
        "Maximum-production-rate cutting speed V_mpr (Boothroyd §9.3).\n"
        "\n"
        "Minimises total cycle time per component, ignoring tool cost.\n"
        "V_mpr ≥ V_e (economic speed) always.\n"
        "\n"
        "  T_mpr = (1/n − 1) × t_ct\n"
        "  V_mpr = C / T_mpr^n\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs or n ≥ 1. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "t_ct_min": {
                "type": "number",
                "description": "Tool-change time per edge (min). Must be > 0.",
            },
            "t_c_min": {
                "type": "number",
                "description": "Machining time per component (min). Must be > 0.",
            },
            "n": {
                "type": "number",
                "description": "Taylor exponent. Must be > 0 and < 1.",
            },
            "C_m_min": {
                "type": "number",
                "description": "Taylor constant (m/min). Must be > 0.",
            },
        },
        "required": ["t_ct_min", "t_c_min", "n", "C_m_min"],
    },
)


@register(_max_rate_spec, write=False)
async def run_cutting_tool_max_rate_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("t_ct_min", "t_c_min", "n", "C_m_min"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = max_production_rate_speed(a["t_ct_min"], a["t_c_min"], a["n"], a["C_m_min"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_break_even
# ---------------------------------------------------------------------------

_break_even_spec = ToolSpec(
    name="cutting_tool_break_even",
    description=(
        "Break-even analysis between economic (min-cost) and max-production-rate\n"
        "cutting speeds.\n"
        "\n"
        "Returns V_e, V_mpr, their respective tool lives and cost-per-piece\n"
        "values, and the cost ratio cost(V_mpr) / cost(V_e).\n"
        "\n"
        "V_mpr >= V_e; the break-even window is the speed range where the\n"
        "cost penalty of running at V_mpr is acceptable.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "C_tool": {"type": "number", "description": "Tool cost per cutting edge. Must be > 0."},
            "t_ct_min": {"type": "number", "description": "Tool-change time per edge (min). Must be > 0."},
            "t_c_min": {"type": "number", "description": "Machining time per component (min). Must be > 0."},
            "C_m_per_min": {"type": "number", "description": "Machine + operator cost rate ($/min). Must be > 0."},
            "n": {"type": "number", "description": "Taylor exponent. Must be > 0 and < 1."},
            "C_m_min": {"type": "number", "description": "Taylor constant (m/min). Must be > 0."},
        },
        "required": ["C_tool", "t_ct_min", "t_c_min", "C_m_per_min", "n", "C_m_min"],
    },
)


@register(_break_even_spec, write=False)
async def run_cutting_tool_break_even(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("C_tool", "t_ct_min", "t_c_min", "C_m_per_min", "n", "C_m_min"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = break_even_speed(
        a["C_tool"], a["t_ct_min"], a["t_c_min"], a["C_m_per_min"], a["n"], a["C_m_min"]
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_machinability
# ---------------------------------------------------------------------------

_machinability_spec = ToolSpec(
    name="cutting_tool_machinability",
    description=(
        "Machinability rating of a material relative to a reference standard.\n"
        "\n"
        "  rating = (V_material / V_reference) × 100 %\n"
        "\n"
        "Convention: AISI B1112 free-cutting steel at 100 m/min = 100%.\n"
        "Higher rating → easier to machine; lower → harder.\n"
        "\n"
        "Typical values: free-cutting steel 100%, alloy steel 50–80%,\n"
        "titanium 20–40%, aluminium 200–400%.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V_material_m_min": {
                "type": "number",
                "description": (
                    "Cutting speed of the material under test to achieve standard tool life "
                    "(e.g. 60 min at VB=0.3 mm). Must be > 0."
                ),
            },
            "V_reference_m_min": {
                "type": "number",
                "description": (
                    "Same for reference material. Default reference: AISI B1112 at 100 m/min. "
                    "Must be > 0."
                ),
            },
        },
        "required": ["V_material_m_min", "V_reference_m_min"],
    },
)


@register(_machinability_spec, write=False)
async def run_cutting_tool_machinability(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("V_material_m_min") is None:
        return json.dumps({"ok": False, "reason": "V_material_m_min is required"})
    if a.get("V_reference_m_min") is None:
        return json.dumps({"ok": False, "reason": "V_reference_m_min is required"})

    result = machinability_rating(a["V_material_m_min"], a["V_reference_m_min"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: cutting_tool_surface_finish
# ---------------------------------------------------------------------------

_surface_finish_spec = ToolSpec(
    name="cutting_tool_surface_finish",
    description=(
        "Theoretical surface finish (Ra, Rt) from feed and nose radius.\n"
        "\n"
        "  Rt = f² / (8 r_n)   [mm → μm]\n"
        "  Ra ≈ Rt / 4          [geometric sinusoidal approximation]\n"
        "\n"
        "These are the geometric minimums; actual values are typically\n"
        "20–50% higher due to BUE and side-flow.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "f_mm_rev": {
                "type": "number",
                "description": "Feed per revolution (mm/rev). Must be > 0.",
            },
            "r_n_mm": {
                "type": "number",
                "description": "Tool nose radius (mm). Must be > 0.",
            },
        },
        "required": ["f_mm_rev", "r_n_mm"],
    },
)


@register(_surface_finish_spec, write=False)
async def run_cutting_tool_surface_finish(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("f_mm_rev") is None:
        return json.dumps({"ok": False, "reason": "f_mm_rev is required"})
    if a.get("r_n_mm") is None:
        return json.dumps({"ok": False, "reason": "r_n_mm is required"})

    result = nose_radius_roughness(a["f_mm_rev"], a["r_n_mm"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)
