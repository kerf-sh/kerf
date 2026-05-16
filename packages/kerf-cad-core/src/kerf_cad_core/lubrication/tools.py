"""
kerf_cad_core.lubrication.tools — LLM tool wrappers for tribology & fluid-film bearing design.

Registers tools with the Kerf tool registry:

  journal_bearing_sommerfeld    — Sommerfeld number for journal bearing
  journal_bearing_raimondi_boyd — dimensionless RB results (ε, h_min, friction, flow, pressure)
  journal_bearing_petroff       — Petroff friction torque & power loss
  bearing_temperature_rise      — lubricant temperature rise from power loss & flow
  viscosity_walther             — ASTM D341 viscosity-temperature (Walther equation)
  viscosity_barus               — Barus viscosity-pressure relation
  ehl_line_contact              — Dowson-Higginson minimum film thickness (line contact)
  ehl_point_contact             — Hamrock-Dowson minimum film thickness (point contact)
  thrust_pad_load               — fixed-incline thrust pad load capacity
  bearing_specific_load         — specific (projected) bearing load p = W/(L·D)
  bearing_lambda_ratio          — Stribeck λ and lubrication regime

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Shigley's Mechanical Engineering Design, 10th ed., Ch. 12
Hamrock, Schmid & Jacobson, Fundamentals of Fluid Film Lubrication, 2nd ed.
Raimondi & Boyd, Trans. ASLE 1, 159–209, 1958
Dowson & Higginson, Elasto-Hydrodynamic Lubrication, 1977
Hamrock & Dowson, ASME J. Lubr. Technol. 99(2):264–276, 1977

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.lubrication.film import (
    sommerfeld_number,
    journal_bearing_raimondi_boyd,
    petroff_friction,
    temperature_rise,
    viscosity_walther,
    viscosity_barus,
    ehl_film_line,
    ehl_film_point,
    thrust_pad_fixed_incline,
    specific_load,
    lambda_ratio,
)


# ---------------------------------------------------------------------------
# Tool: journal_bearing_sommerfeld
# ---------------------------------------------------------------------------

_sommerfeld_spec = ToolSpec(
    name="journal_bearing_sommerfeld",
    description=(
        "Compute the dimensionless Sommerfeld number S = (R/c)²·(μ·N)/P for a "
        "full hydrodynamic journal bearing.\n"
        "\n"
        "P = W/(L·D) is the specific projected bearing load.\n"
        "If L is omitted, L/D = 1 is assumed.\n"
        "\n"
        "S is the primary input to the Raimondi-Boyd design charts.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W": {
                "type": "number",
                "description": "Radial bearing load (N). Must be > 0.",
            },
            "mu": {
                "type": "number",
                "description": "Dynamic lubricant viscosity (Pa·s). Must be > 0.",
            },
            "N": {
                "type": "number",
                "description": "Journal rotational speed (rev/s). Must be > 0.",
            },
            "R": {
                "type": "number",
                "description": "Journal radius (m). Must be > 0.",
            },
            "c": {
                "type": "number",
                "description": "Radial clearance (m). Must be > 0.",
            },
            "L": {
                "type": "number",
                "description": "Bearing length (m). If omitted, L = 2R (L/D=1) is assumed.",
            },
        },
        "required": ["W", "mu", "N", "R", "c"],
    },
)


@register(_sommerfeld_spec, write=False)
async def run_journal_bearing_sommerfeld(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("W", "mu", "N", "R", "c"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "L" in a:
        kwargs["L"] = a["L"]

    result = sommerfeld_number(a["W"], a["mu"], a["N"], a["R"], a["c"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: journal_bearing_raimondi_boyd
# ---------------------------------------------------------------------------

_rb_spec = ToolSpec(
    name="journal_bearing_raimondi_boyd",
    description=(
        "Raimondi-Boyd dimensionless results for a full hydrodynamic journal bearing "
        "from Sommerfeld number S and L/D ratio.\n"
        "\n"
        "Returns:\n"
        "  epsilon          — eccentricity ratio ε = e/c\n"
        "  hmin_over_c      — minimum film-thickness ratio h_min/c = 1 - ε\n"
        "  friction_variable — f·(R/c) dimensionless friction\n"
        "  flow_variable    — Q/(R·c·N·L) dimensionless oil flow\n"
        "  max_pressure_ratio — P_max / P_mean\n"
        "  side_flow_ratio  — Q_s/Q\n"
        "\n"
        "Warns if film is extremely thin or bearing is boundary-lubrication risk.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "S": {
                "type": "number",
                "description": "Sommerfeld number (dimensionless). Must be > 0.",
            },
            "L_D": {
                "type": "number",
                "description": (
                    "Length-to-diameter ratio L/D (default 1.0). "
                    "Validated range [0.25, 2.0]."
                ),
            },
        },
        "required": ["S"],
    },
)


@register(_rb_spec, write=False)
async def run_journal_bearing_raimondi_boyd(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    if a.get("S") is None:
        return json.dumps({"ok": False, "reason": "S is required"})

    kwargs: dict = {}
    if "L_D" in a:
        kwargs["L_D"] = a["L_D"]

    result = journal_bearing_raimondi_boyd(a["S"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: journal_bearing_petroff
# ---------------------------------------------------------------------------

_petroff_spec = ToolSpec(
    name="journal_bearing_petroff",
    description=(
        "Petroff equation: friction torque and power loss for a lightly-loaded "
        "journal bearing assuming concentric (zero-eccentricity) operation.\n"
        "\n"
        "Returns torque (N·m), friction force (N), and viscous power loss (W).\n"
        "This is a lower-bound estimate (actual friction is higher under load).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mu": {
                "type": "number",
                "description": "Dynamic lubricant viscosity (Pa·s). Must be > 0.",
            },
            "N": {
                "type": "number",
                "description": "Journal rotational speed (rev/s). Must be > 0.",
            },
            "R": {
                "type": "number",
                "description": "Journal radius (m). Must be > 0.",
            },
            "c": {
                "type": "number",
                "description": "Radial clearance (m). Must be > 0.",
            },
            "L": {
                "type": "number",
                "description": "Bearing length (m). Must be > 0.",
            },
        },
        "required": ["mu", "N", "R", "c", "L"],
    },
)


@register(_petroff_spec, write=False)
async def run_journal_bearing_petroff(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("mu", "N", "R", "c", "L"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = petroff_friction(a["mu"], a["N"], a["R"], a["c"], a["L"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bearing_temperature_rise
# ---------------------------------------------------------------------------

_temp_rise_spec = ToolSpec(
    name="bearing_temperature_rise",
    description=(
        "Compute lubricant bulk temperature rise ΔT = P_loss / (ρ·Q·Cp) "
        "from viscous power dissipation and oil flow rate.\n"
        "\n"
        "Warns if ΔT > 30 K (must iterate with temperature-corrected viscosity) "
        "or > 50 K (oil degradation risk).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "power_loss_W": {
                "type": "number",
                "description": "Viscous power loss (W). Must be >= 0.",
            },
            "Q_m3_s": {
                "type": "number",
                "description": "Volumetric oil flow rate (m³/s). Must be > 0.",
            },
            "rho": {
                "type": "number",
                "description": (
                    "Oil density (kg/m³). Default 870 (typical mineral oil at ~60°C)."
                ),
            },
            "Cp": {
                "type": "number",
                "description": (
                    "Specific heat capacity (J/kg·K). Default 1900 (mineral oil)."
                ),
            },
        },
        "required": ["power_loss_W", "Q_m3_s"],
    },
)


@register(_temp_rise_spec, write=False)
async def run_bearing_temperature_rise(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("power_loss_W", "Q_m3_s"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    kwargs: dict = {}
    if "rho" in a:
        kwargs["rho"] = a["rho"]
    if "Cp" in a:
        kwargs["Cp"] = a["Cp"]

    result = temperature_rise(a["power_loss_W"], a["Q_m3_s"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: viscosity_walther
# ---------------------------------------------------------------------------

_walther_spec = ToolSpec(
    name="viscosity_walther",
    description=(
        "Walther / ASTM D341 kinematic viscosity-temperature relation.\n"
        "\n"
        "log₁₀(log₁₀(ν + 0.7)) = A - B·log₁₀(T)\n"
        "\n"
        "where T is in Kelvin and ν is kinematic viscosity in cSt.\n"
        "Constants A and B are fitted from two known viscosity-temperature data "
        "points (e.g. ν₄₀ and ν₁₀₀ per ISO 2909).\n"
        "\n"
        "Typical SAE 30: A ≈ 10.8, B ≈ 3.65 (T in K, ν in cSt).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs or equation overflow.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "T_K": {
                "type": "number",
                "description": "Temperature (K). Must be > 0.",
            },
            "A": {
                "type": "number",
                "description": "Walther constant A (from two-point viscosity fit).",
            },
            "B": {
                "type": "number",
                "description": "Walther constant B (positive for typical oils).",
            },
        },
        "required": ["T_K", "A", "B"],
    },
)


@register(_walther_spec, write=False)
async def run_viscosity_walther(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("T_K", "A", "B"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = viscosity_walther(a["T_K"], a["A"], a["B"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: viscosity_barus
# ---------------------------------------------------------------------------

_barus_spec = ToolSpec(
    name="viscosity_barus",
    description=(
        "Barus viscosity-pressure relation: μ(p) = μ₀·exp(α·p).\n"
        "\n"
        "Used in EHL calculations where lubricant viscosity rises dramatically "
        "under contact pressures (GPa range).\n"
        "\n"
        "Typical mineral oil: α ≈ 2.2×10⁻⁸ Pa⁻¹ at 40°C.\n"
        "\n"
        "Warns if α·p > 20 (Barus model exceeds typical validity; "
        "Roelands model recommended for p > 1 GPa).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs or overflow.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mu0": {
                "type": "number",
                "description": "Dynamic viscosity at atmospheric pressure (Pa·s). Must be > 0.",
            },
            "alpha": {
                "type": "number",
                "description": "Pressure-viscosity coefficient α (Pa⁻¹). Must be > 0.",
            },
            "p": {
                "type": "number",
                "description": "Gauge pressure (Pa). Must be >= 0.",
            },
        },
        "required": ["mu0", "alpha", "p"],
    },
)


@register(_barus_spec, write=False)
async def run_viscosity_barus(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("mu0", "alpha", "p"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = viscosity_barus(a["mu0"], a["alpha"], a["p"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: ehl_line_contact
# ---------------------------------------------------------------------------

_ehl_line_spec = ToolSpec(
    name="ehl_line_contact",
    description=(
        "Dowson-Higginson minimum film thickness for EHL line contact.\n"
        "\n"
        "H_min = 2.65·G^0.54·U^0.70·W^(-0.13)\n"
        "\n"
        "where U = (μ₀·u_s)/(E'·R), W = W'/(E'·R), G = α·E'.\n"
        "\n"
        "IMPORTANT: the u_s parameter must be μ₀·u_s_physical (Pa·s × m/s = Pa·m).\n"
        "\n"
        "Applicable to cylindrical contact (spur gears, cylindrical roller bearings).\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "R": {
                "type": "number",
                "description": "Equivalent radius of curvature R = R1·R2/(R1+R2) (m). Must be > 0.",
            },
            "E_prime": {
                "type": "number",
                "description": (
                    "Reduced modulus E' (Pa): 2/E' = (1-ν1²)/E1 + (1-ν2²)/E2. Must be > 0."
                ),
            },
            "u_s": {
                "type": "number",
                "description": (
                    "μ₀ × mean entraining velocity (Pa·s·m/s). Must be > 0. "
                    "Equals (dynamic viscosity) × (mean surface speed)."
                ),
            },
            "W_prime": {
                "type": "number",
                "description": "Load per unit contact length (N/m). Must be > 0.",
            },
            "k": {
                "type": "number",
                "description": "Pressure-viscosity coefficient α (Pa⁻¹). Must be > 0.",
            },
        },
        "required": ["R", "E_prime", "u_s", "W_prime", "k"],
    },
)


@register(_ehl_line_spec, write=False)
async def run_ehl_line_contact(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("R", "E_prime", "u_s", "W_prime", "k"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = ehl_film_line(a["R"], a["E_prime"], a["u_s"], a["W_prime"], a["k"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: ehl_point_contact
# ---------------------------------------------------------------------------

_ehl_point_spec = ToolSpec(
    name="ehl_point_contact",
    description=(
        "Hamrock-Dowson minimum film thickness for EHL point (elliptical) contact.\n"
        "\n"
        "H_min = 3.63·U^0.68·G^0.49·W^(-0.073)·(1 - exp(-0.68·k_ell))\n"
        "\n"
        "where k_ell = R_x/R_y is the ellipticity parameter.\n"
        "For circular contact: R_x = R_y.\n"
        "\n"
        "IMPORTANT: u_s must be μ₀·u_s_physical (Pa·s × m/s = Pa·m).\n"
        "\n"
        "Applicable to ball bearings, bevel gears, crowned rollers.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "R_x": {
                "type": "number",
                "description": "Equivalent radius in rolling direction (m). Must be > 0.",
            },
            "R_y": {
                "type": "number",
                "description": (
                    "Equivalent radius transverse to rolling (m). Must be > 0. "
                    "k_ell = R_x/R_y."
                ),
            },
            "E_prime": {
                "type": "number",
                "description": "Reduced elastic modulus E' (Pa). Must be > 0.",
            },
            "u_s": {
                "type": "number",
                "description": (
                    "μ₀ × mean entraining velocity (Pa·s·m/s). Must be > 0."
                ),
            },
            "W": {
                "type": "number",
                "description": "Normal contact load (N). Must be > 0.",
            },
            "k": {
                "type": "number",
                "description": "Pressure-viscosity coefficient α (Pa⁻¹). Must be > 0.",
            },
        },
        "required": ["R_x", "R_y", "E_prime", "u_s", "W", "k"],
    },
)


@register(_ehl_point_spec, write=False)
async def run_ehl_point_contact(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("R_x", "R_y", "E_prime", "u_s", "W", "k"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = ehl_film_point(
        a["R_x"], a["R_y"], a["E_prime"], a["u_s"], a["W"], a["k"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: thrust_pad_load
# ---------------------------------------------------------------------------

_thrust_pad_spec = ToolSpec(
    name="thrust_pad_load",
    description=(
        "Load capacity and friction for a fixed-incline (tapered-land) hydrodynamic "
        "thrust pad using the classical 1-D Reynolds equation solution.\n"
        "\n"
        "The pad has a linearly converging gap from h_1 (inlet) to h_2 (outlet).\n"
        "h_1 must be > h_2.\n"
        "\n"
        "Returns: load W (N), friction force F (N), max film pressure p_max (Pa), "
        "and minimum film thickness h_min = h_2 (m).\n"
        "\n"
        "Optimal K = h_1/h_2 ≈ 2–2.5 for maximum load capacity.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "B": {
                "type": "number",
                "description": "Pad length in direction of motion (m). Must be > 0.",
            },
            "L": {
                "type": "number",
                "description": "Pad width perpendicular to motion (m). Must be > 0.",
            },
            "U": {
                "type": "number",
                "description": "Sliding surface velocity (m/s). Must be > 0.",
            },
            "h_1": {
                "type": "number",
                "description": "Inlet film thickness (m). Must be > h_2.",
            },
            "h_2": {
                "type": "number",
                "description": "Outlet (minimum) film thickness (m). Must be > 0.",
            },
            "mu": {
                "type": "number",
                "description": "Dynamic lubricant viscosity (Pa·s). Must be > 0.",
            },
        },
        "required": ["B", "L", "U", "h_1", "h_2", "mu"],
    },
)


@register(_thrust_pad_spec, write=False)
async def run_thrust_pad_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("B", "L", "U", "h_1", "h_2", "mu"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = thrust_pad_fixed_incline(
        a["B"], a["L"], a["U"], a["h_1"], a["h_2"], a["mu"]
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bearing_specific_load
# ---------------------------------------------------------------------------

_specific_load_spec = ToolSpec(
    name="bearing_specific_load",
    description=(
        "Specific (projected) bearing load p = W / (L × D).\n"
        "\n"
        "This is a key design parameter for journal bearings — typical allowable "
        "values are 1–7 MPa for babbitt-lined bearings.\n"
        "\n"
        "Warns if p > 10 MPa (likely to exceed babbitt limits) or L/D is "
        "outside the typical design range [0.5, 2.0].\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "W": {
                "type": "number",
                "description": "Radial bearing load (N). Must be > 0.",
            },
            "L": {
                "type": "number",
                "description": "Bearing length (m). Must be > 0.",
            },
            "D": {
                "type": "number",
                "description": "Journal diameter (m). Must be > 0.",
            },
        },
        "required": ["W", "L", "D"],
    },
)


@register(_specific_load_spec, write=False)
async def run_bearing_specific_load(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("W", "L", "D"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = specific_load(a["W"], a["L"], a["D"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: bearing_lambda_ratio
# ---------------------------------------------------------------------------

_lambda_spec = ToolSpec(
    name="bearing_lambda_ratio",
    description=(
        "Stribeck lambda ratio λ = h_min / √(Ra1² + Ra2²) and lubrication "
        "regime classification.\n"
        "\n"
        "Regime boundaries:\n"
        "  λ < 1          — boundary lubrication (metal contact, rapid wear)\n"
        "  1 ≤ λ < 3      — mixed lubrication (partial asperity contact)\n"
        "  λ ≥ 3          — full hydrodynamic / EHL lubrication (minimal wear)\n"
        "\n"
        "Warns on boundary and mixed regimes.\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs.  Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "h_min": {
                "type": "number",
                "description": "Minimum film thickness (m). Must be > 0.",
            },
            "Ra1": {
                "type": "number",
                "description": "Surface roughness Ra of surface 1 (m). Must be > 0.",
            },
            "Ra2": {
                "type": "number",
                "description": "Surface roughness Ra of surface 2 (m). Must be > 0.",
            },
        },
        "required": ["h_min", "Ra1", "Ra2"],
    },
)


@register(_lambda_spec, write=False)
async def run_bearing_lambda_ratio(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    for field in ("h_min", "Ra1", "Ra2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})

    result = lambda_ratio(a["h_min"], a["Ra1"], a["Ra2"])
    return ok_payload(result)
