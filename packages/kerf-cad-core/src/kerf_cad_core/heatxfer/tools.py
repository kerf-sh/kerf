"""
kerf_cad_core.heatxfer.tools — LLM tool wrappers for heat-transfer engineering.

Registers tools with the Kerf tool registry:

  hx_composite_wall          — 1D plane composite wall (series resistance)
  hx_cylindrical_shell       — 1D radial conduction through cylindrical shell
  hx_spherical_shell         — 1D radial conduction through spherical shell
  hx_nusselt_flat_plate      — flat-plate forced convection Nu
  hx_nusselt_pipe_dittus     — Dittus-Boelter turbulent pipe Nu
  hx_nusselt_pipe_laminar    — Hausen laminar pipe Nu
  hx_nusselt_cylinder_cb     — Churchill-Bernstein external cylinder Nu
  hx_nusselt_natural_vplate  — Churchill-Chu natural convection vertical plate
  hx_radiation_two_surface   — two-surface gray diffuse radiation exchange
  hx_fin_straight            — straight rectangular fin efficiency/effectiveness
  hx_fin_pin                 — cylindrical pin fin efficiency/effectiveness
  hx_fin_array_resistance    — fin-array thermal resistance
  hx_lmtd                    — LMTD heat-exchanger sizing
  hx_effectiveness_ntu       — ε-NTU method
  hx_lumped_capacitance      — transient lumped-capacitance model

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Incropera, F.P. et al., "Fundamentals of Heat and Mass Transfer", 7th ed.
Churchill & Bernstein (1977), AIChE J., 23(1), 10-16.
Churchill & Chu (1975), Int. J. Heat Mass Transfer, 18, 1323-1329.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.heatxfer.transfer import (
    composite_wall,
    cylindrical_shell,
    spherical_shell,
    nusselt_flat_plate,
    nusselt_pipe_dittus_boelter,
    nusselt_pipe_laminar,
    nusselt_cylinder_churchill_bernstein,
    nusselt_natural_vertical_plate,
    radiation_two_surface,
    fin_efficiency_straight,
    fin_efficiency_pin,
    fin_array_resistance,
    lmtd_heat_exchanger,
    effectiveness_ntu,
    lumped_capacitance,
)


# ---------------------------------------------------------------------------
# Tool: hx_composite_wall
# ---------------------------------------------------------------------------

_composite_wall_spec = ToolSpec(
    name="hx_composite_wall",
    description=(
        "1D steady-state conduction through a plane composite wall.\n"
        "\n"
        "Computes total thermal resistance, per-layer resistances, interface "
        "temperatures, and heat flux Q (W) for a series of planar layers "
        "(material layers and/or contact resistances) under fixed surface "
        "temperatures.\n"
        "\n"
        "Returns Q_W, R_total, layer_resistances, T_interfaces.\n"
        "Errors: {ok:false, reason} for missing/invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "layers": {
                "type": "array",
                "description": (
                    "Ordered list of layer dicts from hot side to cold side. "
                    "Material layer: {\"k\": W/mK, \"t\": m, \"A\": m²(optional, default 1)}. "
                    "Contact layer: {\"R_contact\": m²K/W, \"A\": m²(optional)}."
                ),
                "items": {"type": "object"},
            },
            "T_hot": {
                "type": "number",
                "description": "Hot-side surface temperature (K). Must be > 0.",
            },
            "T_cold": {
                "type": "number",
                "description": "Cold-side surface temperature (K). Must be > 0.",
            },
        },
        "required": ["layers", "T_hot", "T_cold"],
    },
)


@register(_composite_wall_spec, write=False)
async def run_composite_wall(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("layers") is None:
        return json.dumps({"ok": False, "reason": "layers is required"})
    if a.get("T_hot") is None:
        return json.dumps({"ok": False, "reason": "T_hot is required"})
    if a.get("T_cold") is None:
        return json.dumps({"ok": False, "reason": "T_cold is required"})
    result = composite_wall(a["layers"], a["T_hot"], a["T_cold"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_cylindrical_shell
# ---------------------------------------------------------------------------

_cylindrical_shell_spec = ToolSpec(
    name="hx_cylindrical_shell",
    description=(
        "1D radial conduction through a cylindrical shell.\n"
        "\n"
        "Q = 2π k L (T_inner - T_outer) / ln(r_outer / r_inner)\n"
        "\n"
        "Returns Q_W (total W), q_per_m (W/m), R_cond (K/W).\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "r_inner": {"type": "number", "description": "Inner radius (m). Must be > 0."},
            "r_outer": {"type": "number", "description": "Outer radius (m). Must be > r_inner."},
            "k": {"type": "number", "description": "Thermal conductivity (W/m·K). Must be > 0."},
            "T_inner": {"type": "number", "description": "Inner surface temperature (K)."},
            "T_outer": {"type": "number", "description": "Outer surface temperature (K)."},
            "L": {"type": "number", "description": "Cylinder length (m). Default 1.0."},
        },
        "required": ["r_inner", "r_outer", "k", "T_inner", "T_outer"],
    },
)


@register(_cylindrical_shell_spec, write=False)
async def run_cylindrical_shell(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("r_inner", "r_outer", "k", "T_inner", "T_outer"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "L" in a:
        kwargs["L"] = a["L"]
    result = cylindrical_shell(a["r_inner"], a["r_outer"], a["k"],
                               a["T_inner"], a["T_outer"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_spherical_shell
# ---------------------------------------------------------------------------

_spherical_shell_spec = ToolSpec(
    name="hx_spherical_shell",
    description=(
        "1D radial conduction through a spherical shell.\n"
        "\n"
        "Q = 4π k r_i r_o (T_inner - T_outer) / (r_outer - r_inner)\n"
        "\n"
        "Returns Q_W, R_cond.\n"
        "Errors: {ok:false, reason} for invalid inputs. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "r_inner": {"type": "number", "description": "Inner radius (m). Must be > 0."},
            "r_outer": {"type": "number", "description": "Outer radius (m). Must be > r_inner."},
            "k": {"type": "number", "description": "Thermal conductivity (W/m·K). Must be > 0."},
            "T_inner": {"type": "number", "description": "Inner surface temperature (K)."},
            "T_outer": {"type": "number", "description": "Outer surface temperature (K)."},
        },
        "required": ["r_inner", "r_outer", "k", "T_inner", "T_outer"],
    },
)


@register(_spherical_shell_spec, write=False)
async def run_spherical_shell(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("r_inner", "r_outer", "k", "T_inner", "T_outer"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = spherical_shell(
        a["r_inner"], a["r_outer"], a["k"], a["T_inner"], a["T_outer"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_nusselt_flat_plate
# ---------------------------------------------------------------------------

_nusselt_flat_plate_spec = ToolSpec(
    name="hx_nusselt_flat_plate",
    description=(
        "Average Nusselt number for forced convection over a flat plate.\n"
        "\n"
        "Laminar  (Re <= 5e5): Nu = 0.664 Re^0.5 Pr^(1/3)\n"
        "Turbulent (Re > 5e5): Nu = 0.037 Re^(4/5) Pr^(1/3)\n"
        "Mixed (full plate):   Nu = (0.037 Re^(4/5) - 871) Pr^(1/3)\n"
        "'auto' selects laminar or mixed based on Re.\n"
        "\n"
        "Returns Nu, regime. "
        "Validity: 0.6 <= Pr <= 60; warning issued outside this range.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Re_L": {"type": "number", "description": "Reynolds number based on plate length. Must be > 0."},
            "Pr": {"type": "number", "description": "Prandtl number. Must be > 0."},
            "regime": {
                "type": "string",
                "enum": ["auto", "laminar", "turbulent", "mixed"],
                "description": "Flow regime. Default 'auto'.",
            },
        },
        "required": ["Re_L", "Pr"],
    },
)


@register(_nusselt_flat_plate_spec, write=False)
async def run_nusselt_flat_plate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Re_L", "Pr"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "regime" in a:
        kwargs["regime"] = a["regime"]
    result = nusselt_flat_plate(a["Re_L"], a["Pr"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_nusselt_pipe_dittus
# ---------------------------------------------------------------------------

_nusselt_pipe_dittus_spec = ToolSpec(
    name="hx_nusselt_pipe_dittus",
    description=(
        "Dittus-Boelter Nusselt correlation for fully developed turbulent pipe flow.\n"
        "\n"
        "Nu = 0.023 Re^0.8 Pr^n\n"
        "  n = 0.4 (fluid heated, T_s > T_m)\n"
        "  n = 0.3 (fluid cooled, T_s < T_m)\n"
        "\n"
        "Validity: Re > 10 000, 0.6 < Pr < 160, L/D > 10. "
        "Warning issued if Re <= 10 000.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Re_D": {"type": "number", "description": "Reynolds number (pipe diameter). Must be > 0."},
            "Pr": {"type": "number", "description": "Prandtl number. Must be > 0."},
            "heating": {
                "type": "boolean",
                "description": "True = fluid heated (n=0.4, default); False = cooled (n=0.3).",
            },
        },
        "required": ["Re_D", "Pr"],
    },
)


@register(_nusselt_pipe_dittus_spec, write=False)
async def run_nusselt_pipe_dittus(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Re_D", "Pr"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "heating" in a:
        kwargs["heating"] = bool(a["heating"])
    result = nusselt_pipe_dittus_boelter(a["Re_D"], a["Pr"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_nusselt_pipe_laminar
# ---------------------------------------------------------------------------

_nusselt_pipe_laminar_spec = ToolSpec(
    name="hx_nusselt_pipe_laminar",
    description=(
        "Average Nusselt number for laminar internal pipe flow (Hausen correlation).\n"
        "\n"
        "Nu = 3.66 + 0.065 Gz / (1 + 0.04 Gz^(2/3))\n"
        "where Gz = (D/L) Re Pr (Graetz number)\n"
        "\n"
        "Valid for Re_D < 2300. Warning issued if Re >= 2300.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Re_D": {"type": "number", "description": "Reynolds number. Must be > 0."},
            "Pr": {"type": "number", "description": "Prandtl number. Must be > 0."},
            "L_D": {"type": "number", "description": "L/D ratio (length/diameter). Must be > 0."},
        },
        "required": ["Re_D", "Pr", "L_D"],
    },
)


@register(_nusselt_pipe_laminar_spec, write=False)
async def run_nusselt_pipe_laminar(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Re_D", "Pr", "L_D"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = nusselt_pipe_laminar(a["Re_D"], a["Pr"], a["L_D"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_nusselt_cylinder_cb
# ---------------------------------------------------------------------------

_nusselt_cylinder_cb_spec = ToolSpec(
    name="hx_nusselt_cylinder_cb",
    description=(
        "Average Nusselt number for external cross-flow over a cylinder.\n"
        "\n"
        "Churchill & Bernstein (1977) correlation (Incropera 7.54):\n"
        "Nu = 0.3 + [0.62 Re^(1/2) Pr^(1/3)] / [1+(0.4/Pr)^(2/3)]^(1/4)\n"
        "          × [1 + (Re/282000)^(5/8)]^(4/5)\n"
        "\n"
        "Valid for Re·Pr > 0.2. Warning issued otherwise.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Re_D": {"type": "number", "description": "Reynolds number (cylinder diameter). Must be > 0."},
            "Pr": {"type": "number", "description": "Prandtl number. Must be > 0."},
        },
        "required": ["Re_D", "Pr"],
    },
)


@register(_nusselt_cylinder_cb_spec, write=False)
async def run_nusselt_cylinder_cb(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Re_D", "Pr"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = nusselt_cylinder_churchill_bernstein(a["Re_D"], a["Pr"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_nusselt_natural_vplate
# ---------------------------------------------------------------------------

_nusselt_natural_vplate_spec = ToolSpec(
    name="hx_nusselt_natural_vplate",
    description=(
        "Average Nusselt number for natural convection on a vertical plate.\n"
        "\n"
        "Churchill & Chu (1975) correlations:\n"
        "  'laminar' (Ra <= 1e9): Nu = 0.68 + 0.670 Ra^(1/4) / psi^(4/9)\n"
        "  'all' (composite):     Nu = [0.825 + 0.387 Ra^(1/6) / psi^(8/27)]²\n"
        "  where psi = [1 + (0.492/Pr)^(9/16)]\n"
        "\n"
        "Returns Nu. Warning for Ra > 1e9 in 'laminar' mode.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Ra_L": {"type": "number", "description": "Rayleigh number (= Gr·Pr). Must be > 0."},
            "Pr": {"type": "number", "description": "Prandtl number. Must be > 0."},
            "regime": {
                "type": "string",
                "enum": ["all", "laminar"],
                "description": "Correlation variant: 'all' (default) or 'laminar'.",
            },
        },
        "required": ["Ra_L", "Pr"],
    },
)


@register(_nusselt_natural_vplate_spec, write=False)
async def run_nusselt_natural_vplate(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Ra_L", "Pr"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "regime" in a:
        kwargs["regime"] = a["regime"]
    result = nusselt_natural_vertical_plate(a["Ra_L"], a["Pr"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_radiation_two_surface
# ---------------------------------------------------------------------------

_radiation_two_surface_spec = ToolSpec(
    name="hx_radiation_two_surface",
    description=(
        "Net radiation heat transfer between two gray, diffuse surfaces.\n"
        "\n"
        "Uses electrical analogy with surface and space resistances:\n"
        "Q_12 = (σT1⁴ - σT2⁴) / (R_surf1 + R_space + R_surf2)\n"
        "  R_surf = (1-ε)/(εA),  R_space = 1/(A1·F12)\n"
        "\n"
        "Returns Q_12_W (positive = net heat from 1 to 2), R_total, Eb1, Eb2.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T1": {"type": "number", "description": "Surface 1 temperature (K). Must be > 0."},
            "T2": {"type": "number", "description": "Surface 2 temperature (K). Must be > 0."},
            "eps1": {"type": "number", "description": "Emissivity of surface 1 (0, 1]."},
            "eps2": {"type": "number", "description": "Emissivity of surface 2 (0, 1]."},
            "A1": {"type": "number", "description": "Area of surface 1 (m²). Must be > 0."},
            "A2": {"type": "number", "description": "Area of surface 2 (m²). Must be > 0."},
            "F12": {"type": "number", "description": "View factor from surface 1 to 2. [0, 1]."},
        },
        "required": ["T1", "T2", "eps1", "eps2", "A1", "A2", "F12"],
    },
)


@register(_radiation_two_surface_spec, write=False)
async def run_radiation_two_surface(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("T1", "T2", "eps1", "eps2", "A1", "A2", "F12"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = radiation_two_surface(
        a["T1"], a["T2"], a["eps1"], a["eps2"], a["A1"], a["A2"], a["F12"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_fin_straight
# ---------------------------------------------------------------------------

_fin_straight_spec = ToolSpec(
    name="hx_fin_straight",
    description=(
        "Efficiency and effectiveness of a straight rectangular fin.\n"
        "\n"
        "m = sqrt(2h / (k·t)),  L_c = L (adiabatic) or L+t/2 (convective)\n"
        "η_f = tanh(m·L_c) / (m·L_c)\n"
        "ε_f = η_f × 2L_c / t\n"
        "\n"
        "Returns eta_f, eps_f, mL_c, L_c, m.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "L": {"type": "number", "description": "Fin length/height (m). Must be > 0."},
            "t": {"type": "number", "description": "Fin thickness (m). Must be > 0."},
            "k": {"type": "number", "description": "Fin thermal conductivity (W/m·K). Must be > 0."},
            "h": {"type": "number", "description": "Convective coefficient (W/m²·K). Must be > 0."},
            "tip": {
                "type": "string",
                "enum": ["adiabatic", "convective"],
                "description": "Tip condition: 'adiabatic' (default) or 'convective'.",
            },
        },
        "required": ["L", "t", "k", "h"],
    },
)


@register(_fin_straight_spec, write=False)
async def run_fin_straight(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("L", "t", "k", "h"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "tip" in a:
        kwargs["tip"] = a["tip"]
    result = fin_efficiency_straight(a["L"], a["t"], a["k"], a["h"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_fin_pin
# ---------------------------------------------------------------------------

_fin_pin_spec = ToolSpec(
    name="hx_fin_pin",
    description=(
        "Efficiency and effectiveness of a cylindrical pin fin.\n"
        "\n"
        "m = sqrt(4h / (k·D)),  L_c = L + D/4\n"
        "η_f = tanh(m·L_c) / (m·L_c)\n"
        "ε_f = η_f × 4L_c / D\n"
        "\n"
        "Returns eta_f, eps_f, mL_c, L_c, m.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "L": {"type": "number", "description": "Pin fin length (m). Must be > 0."},
            "D": {"type": "number", "description": "Pin fin diameter (m). Must be > 0."},
            "k": {"type": "number", "description": "Thermal conductivity (W/m·K). Must be > 0."},
            "h": {"type": "number", "description": "Convective coefficient (W/m²·K). Must be > 0."},
        },
        "required": ["L", "D", "k", "h"],
    },
)


@register(_fin_pin_spec, write=False)
async def run_fin_pin(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("L", "D", "k", "h"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = fin_efficiency_pin(a["L"], a["D"], a["k"], a["h"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_fin_array_resistance
# ---------------------------------------------------------------------------

_fin_array_resistance_spec = ToolSpec(
    name="hx_fin_array_resistance",
    description=(
        "Overall thermal resistance of a fin array (Incropera 3.108).\n"
        "\n"
        "η_overall = 1 - N·A_fin/A_total × (1 - η_f)\n"
        "R_array = 1 / (η_overall · h · A_total)\n"
        "\n"
        "Returns R_array (K/W), eta_overall.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "N": {"type": "integer", "description": "Number of fins. Must be >= 1."},
            "eta_f": {"type": "number", "description": "Individual fin efficiency [0, 1]."},
            "A_fin": {"type": "number", "description": "Total surface area of one fin (m²). Must be > 0."},
            "A_base": {"type": "number", "description": "Base area between fins per pitch (m²). Must be > 0."},
            "h": {"type": "number", "description": "Convective coefficient (W/m²·K). Must be > 0."},
            "A_total": {"type": "number", "description": "Total heat transfer area = N·A_fin + unfinned base (m²). Must be > 0."},
        },
        "required": ["N", "eta_f", "A_fin", "A_base", "h", "A_total"],
    },
)


@register(_fin_array_resistance_spec, write=False)
async def run_fin_array_resistance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("N", "eta_f", "A_fin", "A_base", "h", "A_total"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = fin_array_resistance(
        a["N"], a["eta_f"], a["A_fin"], a["A_base"], a["h"], a["A_total"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_lmtd
# ---------------------------------------------------------------------------

_lmtd_spec = ToolSpec(
    name="hx_lmtd",
    description=(
        "Heat exchanger sizing via the LMTD method.\n"
        "\n"
        "Q = U · A · F · ΔT_lm\n"
        "\n"
        "Supports counter-flow (F=1), parallel-flow (F=1), and "
        "cross-flow with both fluids unmixed (F from TEMA charts).\n"
        "\n"
        "Returns Q_W, LMTD_K, F, ΔT1, ΔT2.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_h_in":  {"type": "number", "description": "Hot inlet temperature (K). Must be > 0."},
            "T_h_out": {"type": "number", "description": "Hot outlet temperature (K). Must be > 0."},
            "T_c_in":  {"type": "number", "description": "Cold inlet temperature (K). Must be > 0."},
            "T_c_out": {"type": "number", "description": "Cold outlet temperature (K). Must be > 0."},
            "U": {"type": "number", "description": "Overall heat-transfer coefficient (W/m²·K). Must be > 0."},
            "A": {"type": "number", "description": "Heat exchanger area (m²). Must be > 0."},
            "flow": {
                "type": "string",
                "enum": ["counter", "parallel", "crossflow_unmixed"],
                "description": "Flow arrangement. Default 'counter'.",
            },
        },
        "required": ["T_h_in", "T_h_out", "T_c_in", "T_c_out", "U", "A"],
    },
)


@register(_lmtd_spec, write=False)
async def run_lmtd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("T_h_in", "T_h_out", "T_c_in", "T_c_out", "U", "A"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "flow" in a:
        kwargs["flow"] = a["flow"]
    result = lmtd_heat_exchanger(
        a["T_h_in"], a["T_h_out"], a["T_c_in"], a["T_c_out"],
        a["U"], a["A"], **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_effectiveness_ntu
# ---------------------------------------------------------------------------

_effectiveness_ntu_spec = ToolSpec(
    name="hx_effectiveness_ntu",
    description=(
        "Heat exchanger effectiveness via the ε-NTU method.\n"
        "\n"
        "Counter-flow: ε = (1 - exp(-NTU(1-Cr))) / (1 - Cr·exp(-NTU(1-Cr)))\n"
        "  Special case Cr=1: ε = NTU/(NTU+1)\n"
        "Parallel-flow: ε = (1 - exp(-NTU(1+Cr))) / (1+Cr)\n"
        "Cross-flow (unmixed): ε = 1 - exp[(NTU^0.22/Cr)(exp(-Cr·NTU^0.78)-1)]\n"
        "\n"
        "Returns epsilon (effectiveness [0,1]), C_r, NTU, C_min, C_max.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "C_min": {"type": "number", "description": "Minimum heat capacity rate (W/K). Must be > 0."},
            "C_max": {"type": "number", "description": "Maximum heat capacity rate (W/K). Must be >= C_min."},
            "NTU": {"type": "number", "description": "Number of transfer units. Must be > 0."},
            "flow": {
                "type": "string",
                "enum": ["counter", "parallel", "crossflow_unmixed"],
                "description": "Flow arrangement. Default 'counter'.",
            },
        },
        "required": ["C_min", "C_max", "NTU"],
    },
)


@register(_effectiveness_ntu_spec, write=False)
async def run_effectiveness_ntu(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("C_min", "C_max", "NTU"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "flow" in a:
        kwargs["flow"] = a["flow"]
    result = effectiveness_ntu(a["C_min"], a["C_max"], a["NTU"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_lumped_capacitance
# ---------------------------------------------------------------------------

_lumped_capacitance_spec = ToolSpec(
    name="hx_lumped_capacitance",
    description=(
        "Transient temperature response using the lumped-capacitance model.\n"
        "\n"
        "τ = ρ V c_p / (h A_s)    [time constant, s]\n"
        "T(t) = T_inf + (T_i - T_inf) × exp(-t/τ)\n"
        "\n"
        "Optional Biot number check: Bi = h·L_c/k (L_c = V/A_s).\n"
        "A WARNING is issued (not an error) if Bi > 0.1.\n"
        "\n"
        "Returns T_t_K, tau_s, Bi (None if k not provided), theta, Q_total_J.\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_i":   {"type": "number", "description": "Initial body temperature (K). Must be > 0."},
            "T_inf": {"type": "number", "description": "Ambient/fluid temperature (K). Must be > 0."},
            "h":     {"type": "number", "description": "Convective coefficient (W/m²·K). Must be > 0."},
            "A_s":   {"type": "number", "description": "Surface area (m²). Must be > 0."},
            "rho":   {"type": "number", "description": "Density (kg/m³). Must be > 0."},
            "V":     {"type": "number", "description": "Volume (m³). Must be > 0."},
            "c_p":   {"type": "number", "description": "Specific heat capacity (J/kg·K). Must be > 0."},
            "t":     {"type": "number", "description": "Time (s). Must be >= 0."},
            "Lc":    {"type": "number", "description": "Characteristic length L_c (m). Optional; default V/A_s."},
            "k":     {"type": "number", "description": "Body thermal conductivity (W/m·K). Optional; required for Bi check."},
        },
        "required": ["T_i", "T_inf", "h", "A_s", "rho", "V", "c_p", "t"],
    },
)


@register(_lumped_capacitance_spec, write=False)
async def run_lumped_capacitance(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("T_i", "T_inf", "h", "A_s", "rho", "V", "c_p", "t"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "Lc" in a:
        kwargs["Lc"] = a["Lc"]
    if "k" in a:
        kwargs["k"] = a["k"]
    result = lumped_capacitance(
        a["T_i"], a["T_inf"], a["h"], a["A_s"],
        a["rho"], a["V"], a["c_p"], a["t"],
        **kwargs
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: hx_tube_count  (Bell-Delaware / TEMA tube layout)
# ---------------------------------------------------------------------------

from kerf_cad_core.heatxfer.shell_tube_bell import (  # noqa: E402
    tube_count as _tube_count,
    shell_tube_design as _shell_tube_design,
)

_tube_count_spec = ToolSpec(
    name="hx_tube_count",
    description=(
        "Estimate TEMA tube count for a shell-and-tube heat exchanger.\n"
        "\n"
        "Uses the TEMA tube-layout formula:\n"
        "  N_t = (CTP/CL) * (π/4) * (D_s / P_t)²\n"
        "where CL is the layout packing factor and CTP is the tube-count\n"
        "correction for multiple passes.\n"
        "\n"
        "Supported layouts: triangular_30, rotated_60, square_90, rotated_45.\n"
        "TEMA minimum pitch = 1.25 × tube_od.\n"
        "\n"
        "Returns N_tubes (int).\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "shell_id": {"type": "number", "description": "Shell inner diameter (m). Must be > 0."},
            "tube_od":  {"type": "number", "description": "Tube outer diameter (m). Must be > 0."},
            "pitch":    {"type": "number", "description": "Tube pitch centre-to-centre (m). Must be >= 1.25*tube_od."},
            "layout":   {
                "type": "string",
                "enum": ["triangular_30", "rotated_60", "square_90", "rotated_45"],
                "description": "TEMA tube layout pattern.",
            },
            "n_passes": {"type": "integer", "description": "Number of tube passes (1, 2, 4, or 6). Default 1."},
        },
        "required": ["shell_id", "tube_od", "pitch", "layout"],
    },
)


@register(_tube_count_spec, write=False)
async def run_tube_count(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("shell_id", "tube_od", "pitch", "layout"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    try:
        n = _tube_count(
            a["shell_id"], a["tube_od"], a["pitch"], a["layout"],
            a.get("n_passes", 1),
        )
        return ok_payload({"N_tubes": n})
    except Exception as exc:
        return err_payload(str(exc), "BAD_ARGS")


# ---------------------------------------------------------------------------
# Tool: hx_shell_tube_bell_delaware
# ---------------------------------------------------------------------------

_bell_delaware_spec = ToolSpec(
    name="hx_shell_tube_bell_delaware",
    description=(
        "Full Bell-Delaware shell-and-tube heat exchanger design.\n"
        "\n"
        "Computes shell-side h_s with Bell-Delaware correction factors\n"
        "(Jc baffle-cut, Jl leakage, Jb bypass, Jr laminar, Js uneven spacing),\n"
        "tube-side h_t (Dittus-Boelter / Hausen), overall U, required area A_req,\n"
        "tube count, baffle count, and ΔP (tube-side + shell-side).\n"
        "\n"
        "Validated against Kern (1950) kerosene cooler example:\n"
        "  h_s ~500 W/m²·K, h_t ~3000 W/m²·K, U ~400 W/m²·K, A ~50 m² @ 1 MW.\n"
        "\n"
        "Returns: U_W_m2K, A_req_m2, A_actual_m2, overdesign, N_tubes, N_baffles,\n"
        "         h_t_W_m2K, h_s_W_m2K, Re_t, Re_s, LMTD_K, dP_tube_Pa, dP_shell_Pa,\n"
        "         factors (Jc/Jl/Jb/Jr/Js).\n"
        "Errors: {ok:false, reason}. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "duty_W":      {"type": "number", "description": "Heat duty (W). Must be > 0."},
            "t_hot_in":    {"type": "number", "description": "Hot-fluid inlet temperature (°C or K)."},
            "t_hot_out":   {"type": "number", "description": "Hot-fluid outlet temperature."},
            "t_cold_in":   {"type": "number", "description": "Cold-fluid inlet temperature."},
            "t_cold_out":  {"type": "number", "description": "Cold-fluid outlet temperature."},
            "shell_props": {
                "type": "object",
                "description": (
                    "Shell-side fluid properties: "
                    "{rho: kg/m³, mu: Pa·s, cp: J/kg·K, k: W/m·K, Pr: (opt), m_dot: kg/s (opt)}."
                ),
            },
            "tube_props": {
                "type": "object",
                "description": (
                    "Tube-side fluid properties: "
                    "{rho: kg/m³, mu: Pa·s, cp: J/kg·K, k: W/m·K, Pr: (opt), m_dot: kg/s (opt)}."
                ),
            },
            "geometry": {
                "type": "object",
                "description": (
                    "HX geometry: {D_s, tube_od, tube_id, pitch, layout, L_tube, N_t, n_passes, "
                    "N_b, B, baffle_cut, k_wall, R_foul_t, R_foul_s, D_tb, D_sb, n_ss (all optional except D_s/tube_od/tube_id/pitch/L_tube/N_t/N_b/B)}."
                ),
            },
        },
        "required": ["duty_W", "t_hot_in", "t_hot_out", "t_cold_in", "t_cold_out",
                     "shell_props", "tube_props", "geometry"],
    },
)


@register(_bell_delaware_spec, write=False)
async def run_shell_tube_bell_delaware(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    required = ("duty_W", "t_hot_in", "t_hot_out", "t_cold_in", "t_cold_out",
                "shell_props", "tube_props", "geometry")
    for field in required:
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    try:
        result = _shell_tube_design(
            a["duty_W"],
            a["t_hot_in"], a["t_hot_out"],
            a["t_cold_in"], a["t_cold_out"],
            a["shell_props"],
            a["tube_props"],
            a["geometry"],
        )
        return ok_payload(result)
    except Exception as exc:
        return err_payload(str(exc), "COMPUTE_ERROR")
