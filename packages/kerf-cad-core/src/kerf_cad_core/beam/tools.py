"""
kerf_cad_core.beam.tools — LLM tool wrappers for beam & cross-section analysis.

Registers seven tools with the Kerf tool registry:

  beam_section_properties  — area, centroid, I, S, Z, r_g, J
  beam_loads               — deflection/slope/moment/shear (cantilever/SS/fixed-fixed)
  beam_superpose           — linear superposition combiner
  beam_buckling            — Euler + Johnson critical loads
  beam_combined_stress     — axial + bending stress
  beam_mohr_circle         — principal stresses from σ, τ
  beam_shear_flow          — VQ/It shear stress

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Roark's Formulas for Stress and Strain, 8th ed. (Young & Budynas)
Hibbeler, Mechanics of Materials, 10th ed.
AISC Steel Construction Manual, 15th ed.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.beam.analysis import (
    section_properties,
    beam_loads,
    superpose,
    buckling,
    combined_stress,
    mohr_circle,
    shear_flow,
)


# ---------------------------------------------------------------------------
# Tool: beam_section_properties
# ---------------------------------------------------------------------------

_section_properties_spec = ToolSpec(
    name="beam_section_properties",
    description=(
        "Compute cross-section properties for standard structural shapes.\n"
        "\n"
        "Returns area A (m²), centroid (cx, cy), second moments of area Ix/Iy (m⁴),\n"
        "elastic section moduli Sx_top/Sx_bot/Sy (m³), plastic section moduli Zx/Zy (m³),\n"
        "radii of gyration rx/ry (m), and torsion constant J (m⁴).\n"
        "\n"
        "Supported shapes and required dimension keys (all in metres):\n"
        "  'rectangle'   — b (width), h (height)\n"
        "  'circle'      — d (diameter)\n"
        "  'hollow_rect' — b, h, t (wall thickness)\n"
        "  'hollow_circ' — d (outer diameter), t (wall thickness)\n"
        "  'I'           — bf (flange width), d (total depth), tf (flange thick), tw (web thick)\n"
        "  'channel'     — b (flange width), d (total depth), tf (flange thick), tw (web thick)\n"
        "  'angle'       — b (horizontal leg), h (vertical leg), t (uniform thickness)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid / missing inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "shape": {
                "type": "string",
                "enum": ["rectangle", "circle", "hollow_rect", "hollow_circ",
                         "I", "channel", "angle"],
                "description": "Cross-section shape identifier.",
            },
            "b": {"type": "number", "description": "Width or flange width (m)."},
            "h": {"type": "number", "description": "Height or depth (m)."},
            "d": {"type": "number", "description": "Diameter or total depth (m)."},
            "t": {"type": "number", "description": "Wall / leg thickness (m)."},
            "bf": {"type": "number", "description": "Flange width for I/channel (m)."},
            "tf": {"type": "number", "description": "Flange thickness for I/channel (m)."},
            "tw": {"type": "number", "description": "Web thickness for I/channel (m)."},
        },
        "required": ["shape"],
    },
)


@register(_section_properties_spec, write=False)
async def run_section_properties(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    shape = a.get("shape")
    if not shape:
        return json.dumps({"ok": False, "reason": "shape is required"})

    dims = {k: v for k, v in a.items() if k != "shape"}
    result = section_properties(shape, **dims)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: beam_loads
# ---------------------------------------------------------------------------

_beam_loads_spec = ToolSpec(
    name="beam_loads",
    description=(
        "Closed-form beam analysis: max deflection, slope, bending moment, shear force,\n"
        "and support reactions for standard support and load combinations.\n"
        "\n"
        "Supports:\n"
        "  'cantilever'       — fixed at A (x=0), free at B\n"
        "  'simply_supported' — pinned at A, roller at B\n"
        "  'fixed_fixed'      — both ends clamped\n"
        "\n"
        "Load types:\n"
        "  'point' — transverse point load P (N) at distance a (m) from A.\n"
        "            a defaults to L (free end) for cantilever, L/2 for others.\n"
        "  'udl'   — uniformly distributed load w (N/m) over full span.\n"
        "  'moment'— applied moment M0 (N·m) at end A (cantilever/simply-supported)\n"
        "            or midspan (fixed-fixed).\n"
        "\n"
        "All units SI: E (Pa), I (m⁴), L (m).\n"
        "Returns max_deflection (m), slope_end (rad), max_moment (N·m),\n"
        "max_shear (N), Ra, Rb (N).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "support": {
                "type": "string",
                "enum": ["cantilever", "simply_supported", "fixed_fixed"],
                "description": "Beam support condition.",
            },
            "load_type": {
                "type": "string",
                "enum": ["point", "udl", "moment"],
                "description": "Applied load type.",
            },
            "E": {"type": "number", "description": "Young's modulus (Pa). Must be > 0."},
            "I": {"type": "number", "description": "Second moment of area (m⁴). Must be > 0."},
            "L": {"type": "number", "description": "Span length (m). Must be > 0."},
            "P": {"type": "number", "description": "Point load (N). Required for load_type='point'."},
            "a": {"type": "number", "description": "Load position from A (m). Optional for point load."},
            "w": {"type": "number", "description": "UDL intensity (N/m). Required for load_type='udl'."},
            "M0": {"type": "number", "description": "Applied moment (N·m). Required for load_type='moment'."},
        },
        "required": ["support", "load_type", "E", "I", "L"],
    },
)


@register(_beam_loads_spec, write=False)
async def run_beam_loads(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("support", "load_type", "E", "I", "L"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    load_params = {k: v for k, v in a.items()
                   if k in ("P", "a", "w", "M0")}

    result = beam_loads(
        a["support"], a["load_type"],
        E=a["E"], I=a["I"], L=a["L"],
        **load_params,
    )
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: beam_superpose
# ---------------------------------------------------------------------------

_beam_superpose_spec = ToolSpec(
    name="beam_superpose",
    description=(
        "Linearly superpose multiple beam_loads results.\n"
        "\n"
        "All cases must have ok=True. max_deflection, max_moment, and max_shear\n"
        "are summed (conservative upper bound).\n"
        "\n"
        "Pass an array of beam_loads result objects as 'cases'.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cases": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of beam_loads result dicts (each with ok=True).",
            },
        },
        "required": ["cases"],
    },
)


@register(_beam_superpose_spec, write=False)
async def run_beam_superpose(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    cases = a.get("cases")
    if not isinstance(cases, list):
        return json.dumps({"ok": False, "reason": "cases must be an array"})

    result = superpose(cases)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: beam_buckling
# ---------------------------------------------------------------------------

_beam_buckling_spec = ToolSpec(
    name="beam_buckling",
    description=(
        "Column buckling analysis: Euler critical load + Johnson short-column transition.\n"
        "\n"
        "Computes:\n"
        "  P_euler  = π² E I / (K·L)²\n"
        "  P_johnson = A·Fy [1 - (Fy/4π²E)(KL/r)²]  (governs for short/intermediate columns)\n"
        "  Cc       = π √(2E/Fy)  — transition slenderness ratio\n"
        "\n"
        "For KL/r > Cc: Euler governs. For KL/r <= Cc: Johnson governs.\n"
        "\n"
        "End-condition factor K:\n"
        "  K=0.5  — fixed-fixed\n"
        "  K=0.7  — fixed-pin\n"
        "  K=1.0  — pin-pin (default)\n"
        "  K=2.0  — fixed-free (flagpole / cantilever)\n"
        "\n"
        "A warning is emitted if the critical stress exceeds yield strength.\n"
        "Warns if KL/r > 200 (AISC recommends <= 200).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "L_eff": {"type": "number", "description": "Effective column length (m). Must be > 0."},
            "A": {"type": "number", "description": "Cross-sectional area (m²). Must be > 0."},
            "I": {"type": "number", "description": "Minimum second moment of area (m⁴). Must be > 0."},
            "E": {"type": "number", "description": "Young's modulus (Pa). Must be > 0. Steel ≈ 200e9."},
            "Fy": {"type": "number", "description": "Yield strength (Pa). Must be > 0. Steel A36 ≈ 250e6."},
            "K": {
                "type": "number",
                "description": "End-condition factor (default 1.0). See description for values.",
            },
        },
        "required": ["L_eff", "A", "I", "E", "Fy"],
    },
)


@register(_beam_buckling_spec, write=False)
async def run_beam_buckling(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("L_eff", "A", "I", "E", "Fy"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "K" in a:
        kwargs["K"] = a["K"]

    result = buckling(a["L_eff"], a["A"], a["I"], a["E"], Fy=a["Fy"], **kwargs)
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: beam_combined_stress
# ---------------------------------------------------------------------------

_combined_stress_spec = ToolSpec(
    name="beam_combined_stress",
    description=(
        "Compute combined axial + bending stress at extreme fibres.\n"
        "\n"
        "  σ_top = P/A - M/S\n"
        "  σ_bot = P/A + M/S\n"
        "\n"
        "where P (N) is axial load (positive = tension),\n"
        "M (N·m) is bending moment magnitude,\n"
        "A (m²) is cross-sectional area,\n"
        "S (m³) is the elastic section modulus (use smaller of Sx_top/Sx_bot).\n"
        "\n"
        "Returns sigma_axial, sigma_bending, sigma_top, sigma_bot, sigma_max (all in Pa).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P": {"type": "number", "description": "Axial load (N). Positive = tension."},
            "M": {"type": "number", "description": "Bending moment magnitude (N·m)."},
            "A": {"type": "number", "description": "Cross-sectional area (m²). Must be > 0."},
            "S": {"type": "number", "description": "Elastic section modulus (m³). Must be > 0."},
        },
        "required": ["P", "M", "A", "S"],
    },
)


@register(_combined_stress_spec, write=False)
async def run_combined_stress(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("P", "M", "A", "S"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = combined_stress(a["P"], a["M"], a["A"], a["S"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: beam_mohr_circle
# ---------------------------------------------------------------------------

_mohr_circle_spec = ToolSpec(
    name="beam_mohr_circle",
    description=(
        "Mohr's circle for a 2D plane stress state.\n"
        "\n"
        "Given normal stresses σx, σy (Pa) and shear stress τxy (Pa), computes:\n"
        "  sigma_avg   = (σx + σy) / 2\n"
        "  R           = √[((σx-σy)/2)² + τxy²]\n"
        "  sigma_1     = sigma_avg + R  (major principal stress)\n"
        "  sigma_2     = sigma_avg - R  (minor principal stress)\n"
        "  tau_max     = R\n"
        "  theta_p_deg — angle of principal plane from x-axis (degrees, CCW+)\n"
        "\n"
        "Errors: {ok:false, reason} for non-finite inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sigma_x":  {"type": "number", "description": "Normal stress on x-face (Pa)."},
            "sigma_y":  {"type": "number", "description": "Normal stress on y-face (Pa)."},
            "tau_xy":   {"type": "number", "description": "Shear stress on x-face (Pa)."},
        },
        "required": ["sigma_x", "sigma_y", "tau_xy"],
    },
)


@register(_mohr_circle_spec, write=False)
async def run_mohr_circle(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("sigma_x", "sigma_y", "tau_xy"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = mohr_circle(a["sigma_x"], a["sigma_y"], a["tau_xy"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: beam_shear_flow
# ---------------------------------------------------------------------------

_shear_flow_spec = ToolSpec(
    name="beam_shear_flow",
    description=(
        "Shear stress at a horizontal section cut using the shear flow formula.\n"
        "\n"
        "  τ = VQ / (I·b)\n"
        "\n"
        "where:\n"
        "  V (N) — shear force at the cross-section\n"
        "  Q (m³) — first moment of area of the portion above/below the cut\n"
        "            about the neutral axis\n"
        "  I (m⁴) — second moment of area of the full section about the neutral axis\n"
        "  b (m)  — width of the cross-section at the cut\n"
        "\n"
        "Returns tau_Pa (Pa).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "V": {"type": "number", "description": "Shear force (N)."},
            "Q": {"type": "number", "description": "First moment of area (m³). Must be >= 0."},
            "I": {"type": "number", "description": "Second moment of area (m⁴). Must be > 0."},
            "b": {"type": "number", "description": "Cut width (m). Must be > 0."},
        },
        "required": ["V", "Q", "I", "b"],
    },
)


@register(_shear_flow_spec, write=False)
async def run_shear_flow(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("V", "Q", "I", "b"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = shear_flow(a["V"], a["Q"], a["I"], a["b"])
    return ok_payload(result) if result.get("ok") else json.dumps(result)
