"""
kerf_cad_core.pumpsys.tools — LLM tool wrappers for centrifugal-pump engineering.

Registers tools with the Kerf tool registry:

  pump_system_curve           — H = H_static + K·Q²
  pump_system_K_from_pipe     — K from Darcy-Weisbach pipe friction + fittings
  pump_curve_fit              — quadratic fit from ≥ 3 catalogue (Q, H) points
  pump_operating_point        — intersection of pump & system curves
  pump_hydraulic_power        — useful fluid power, brake power, efficiency
  pump_npsh_available         — NPSHa = (P_atm − P_vapor)/ρg − z_s − h_fs
  pump_npsh_check             — cavitation margin: NPSHa vs NPSHr
  pump_affinity_speed         — affinity laws: speed-change scaling
  pump_affinity_trim          — affinity laws: impeller-trim scaling
  pumps_in_series             — combined head-flow curve
  pumps_in_parallel           — combined flow at a given head
  pump_specific_speed         — dimensionless Ns & impeller-type guidance
  pump_minimum_flow_check     — warn if Q_op < Q_bep × min_fraction

All tools are pure-Python; no OCC dependency.
Errors returned as {"ok": false, "reason": "..."} — tools never raise.

References
----------
Kaplan, I. et al., "Pump Handbook", 4th ed., McGraw-Hill (2010).
White, F.M., "Fluid Mechanics", 8th ed., McGraw-Hill (2016).
HI (Hydraulic Institute) Standards 9.6.4.

Author: imranparuk
"""
from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx  # noqa: F401

from kerf_cad_core.pumpsys.curve import (
    system_curve,
    system_K_from_pipe,
    pump_curve_from_points,
    operating_point,
    hydraulic_power,
    npsh_available,
    npsh_check,
    affinity_speed,
    affinity_trim,
    pumps_in_series,
    pumps_in_parallel,
    specific_speed,
    minimum_flow_note,
)


# ---------------------------------------------------------------------------
# Tool: pump_system_curve
# ---------------------------------------------------------------------------

_system_curve_spec = ToolSpec(
    name="pump_system_curve",
    description=(
        "Compute the system head at a given flow rate using the model "
        "H_sys = H_static + K·Q².\n"
        "\n"
        "K lumps all pipe-friction (Darcy-Weisbach) and minor-fitting losses.\n"
        "Use pump_system_K_from_pipe to compute K from pipe geometry.\n"
        "\n"
        "Returns H_system_m (metres). Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "H_static": {
                "type": "number",
                "description": "Static head (m). Must be >= 0.",
            },
            "K": {
                "type": "number",
                "description": "System resistance coefficient (s²/m⁵). Must be >= 0.",
            },
            "Q": {
                "type": "number",
                "description": "Volume flow rate (m³/s). Must be >= 0.",
            },
        },
        "required": ["H_static", "K", "Q"],
    },
)


@register(_system_curve_spec, write=False)
async def run_system_curve(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("H_static", "K", "Q"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = system_curve(a["H_static"], a["K"], a["Q"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_system_K_from_pipe
# ---------------------------------------------------------------------------

_system_K_spec = ToolSpec(
    name="pump_system_K_from_pipe",
    description=(
        "Compute the system resistance coefficient K from Darcy-Weisbach "
        "pipe friction and minor fittings.\n"
        "\n"
        "K = (f·L/D + K_fittings) / (2·g·A²)\n"
        "\n"
        "Returns K (s²/m⁵). Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "f": {
                "type": "number",
                "description": "Darcy friction factor (dimensionless). Must be > 0.",
            },
            "L": {
                "type": "number",
                "description": "Pipe length (m). Must be > 0.",
            },
            "D": {
                "type": "number",
                "description": "Internal pipe diameter (m). Must be > 0.",
            },
            "A": {
                "type": "number",
                "description": (
                    "Pipe cross-sectional area (m²). Must be > 0. "
                    "Circular pipe: A = π·D²/4."
                ),
            },
            "K_fittings": {
                "type": "number",
                "description": (
                    "Sum of minor-loss coefficients for fittings (dimensionless). "
                    "Default 0."
                ),
            },
        },
        "required": ["f", "L", "D", "A"],
    },
)


@register(_system_K_spec, write=False)
async def run_system_K_from_pipe(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("f", "L", "D", "A"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "K_fittings" in a:
        kwargs["K_fittings"] = a["K_fittings"]
    result = system_K_from_pipe(a["f"], a["L"], a["D"], a["A"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_curve_fit
# ---------------------------------------------------------------------------

_pump_curve_fit_spec = ToolSpec(
    name="pump_curve_fit",
    description=(
        "Fit a quadratic pump curve H = a·Q² + b·Q + c from ≥ 3 catalogue "
        "(Q, H) points (Q in m³/s, H in m).\n"
        "\n"
        "For exactly 3 points the quadratic passes through all three. "
        "For > 3 points, a least-squares fit is used.\n"
        "\n"
        "Returns coefficients a, b, c, H_shutoff (head at Q=0), and Q_max.\n"
        "Use with pump_operating_point to find the duty point. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": (
                    "List of [Q, H] pairs (m³/s, m) from the pump datasheet. "
                    "At least 3 distinct Q values required."
                ),
                "minItems": 3,
            },
        },
        "required": ["points"],
    },
)


@register(_pump_curve_fit_spec, write=False)
async def run_pump_curve_fit(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("points") is None:
        return json.dumps({"ok": False, "reason": "points is required"})
    result = pump_curve_from_points(a["points"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_operating_point
# ---------------------------------------------------------------------------

_operating_point_spec = ToolSpec(
    name="pump_operating_point",
    description=(
        "Find the pump operating point (duty point): intersection of the pump "
        "curve H = a·Q² + b·Q + c and the system curve H = H_static + K·Q².\n"
        "\n"
        "Solves the quadratic (a−K)·Q² + b·Q + (c−H_static) = 0.\n"
        "\n"
        "Returns Q_op_m3s (m³/s) and H_op_m (m). "
        "Flags negative-flow or no-real-intersection. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "a": {"type": "number", "description": "Pump curve coefficient a (H = a·Q² + b·Q + c)."},
            "b": {"type": "number", "description": "Pump curve coefficient b."},
            "c": {"type": "number", "description": "Pump curve coefficient c (shut-off head)."},
            "H_static": {
                "type": "number",
                "description": "Static system head (m). Must be >= 0.",
            },
            "K": {
                "type": "number",
                "description": "System resistance coefficient (s²/m⁵). Must be >= 0.",
            },
        },
        "required": ["a", "b", "c", "H_static", "K"],
    },
)


@register(_operating_point_spec, write=False)
async def run_operating_point(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("a", "b", "c", "H_static", "K"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = operating_point(a["a"], a["b"], a["c"], a["H_static"], a["K"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_hydraulic_power
# ---------------------------------------------------------------------------

_hydraulic_power_spec = ToolSpec(
    name="pump_hydraulic_power",
    description=(
        "Compute hydraulic (fluid) power, brake (shaft) power, and efficiency.\n"
        "\n"
        "P_hydraulic = ρ·g·Q·H\n"
        "P_brake     = P_hydraulic / η\n"
        "η           = P_hydraulic / P_brake\n"
        "\n"
        "Provide either eta OR P_shaft_W; the other is computed. "
        "If neither is given, only P_hydraulic is returned. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q": {
                "type": "number",
                "description": "Volume flow rate (m³/s). Must be > 0.",
            },
            "H": {
                "type": "number",
                "description": "Total dynamic head (m). Must be > 0.",
            },
            "rho": {
                "type": "number",
                "description": "Fluid density (kg/m³). Must be > 0. Water ≈ 1000.",
            },
            "eta": {
                "type": "number",
                "description": "Overall pump efficiency (0 < η ≤ 1). Optional.",
            },
            "P_shaft_W": {
                "type": "number",
                "description": "Shaft (brake) power (W). Optional. Mutually exclusive with eta.",
            },
        },
        "required": ["Q", "H", "rho"],
    },
)


@register(_hydraulic_power_spec, write=False)
async def run_hydraulic_power(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Q", "H", "rho"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "eta" in a:
        kwargs["eta"] = a["eta"]
    if "P_shaft_W" in a:
        kwargs["P_shaft_W"] = a["P_shaft_W"]
    result = hydraulic_power(a["Q"], a["H"], a["rho"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_npsh_available
# ---------------------------------------------------------------------------

_npsh_available_spec = ToolSpec(
    name="pump_npsh_available",
    description=(
        "Compute Net Positive Suction Head Available (NPSHa).\n"
        "\n"
        "NPSHa = (P_atm − P_vapor) / (ρ·g) − z_suction − h_friction\n"
        "\n"
        "z_suction is positive for suction lift (pump above liquid), "
        "negative for flooded suction (pump below liquid). Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "P_atm_Pa": {
                "type": "number",
                "description": (
                    "Absolute pressure at suction source (Pa). "
                    "Standard atmosphere ≈ 101325 Pa. Must be > 0."
                ),
            },
            "P_vapor_Pa": {
                "type": "number",
                "description": (
                    "Vapour pressure of fluid at operating temperature (Pa). "
                    "Water 20°C ≈ 2338 Pa. Must be >= 0."
                ),
            },
            "rho": {
                "type": "number",
                "description": "Fluid density (kg/m³). Must be > 0.",
            },
            "z_suction_m": {
                "type": "number",
                "description": (
                    "Suction lift (m). Positive = pump above liquid (suction lift). "
                    "Negative = pump below liquid (flooded suction)."
                ),
            },
            "h_friction_m": {
                "type": "number",
                "description": "Friction head loss in suction line (m). Must be >= 0.",
            },
        },
        "required": ["P_atm_Pa", "P_vapor_Pa", "rho", "z_suction_m", "h_friction_m"],
    },
)


@register(_npsh_available_spec, write=False)
async def run_npsh_available(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("P_atm_Pa", "P_vapor_Pa", "rho", "z_suction_m", "h_friction_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = npsh_available(
        a["P_atm_Pa"], a["P_vapor_Pa"], a["rho"],
        a["z_suction_m"], a["h_friction_m"],
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_npsh_check
# ---------------------------------------------------------------------------

_npsh_check_spec = ToolSpec(
    name="pump_npsh_check",
    description=(
        "Check NPSHa against NPSHr with a cavitation safety margin.\n"
        "\n"
        "Cavitation risk is flagged when NPSHa < NPSHr + margin_m.\n"
        "Default margin = 0.5 m per HI standard.\n"
        "\n"
        "Returns cavitation_risk (bool) and NPSHa − NPSHr difference. "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "NPSHa_m": {
                "type": "number",
                "description": "NPSH available (m), from pump_npsh_available.",
            },
            "NPSHr_m": {
                "type": "number",
                "description": "NPSH required by the pump (m), from manufacturer data. Must be > 0.",
            },
            "margin_m": {
                "type": "number",
                "description": "Cavitation safety margin (m). Default 0.5 m. Must be >= 0.",
            },
        },
        "required": ["NPSHa_m", "NPSHr_m"],
    },
)


@register(_npsh_check_spec, write=False)
async def run_npsh_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("NPSHa_m", "NPSHr_m"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "margin_m" in a:
        kwargs["margin_m"] = a["margin_m"]
    result = npsh_check(a["NPSHa_m"], a["NPSHr_m"], **kwargs)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_affinity_speed
# ---------------------------------------------------------------------------

_affinity_speed_spec = ToolSpec(
    name="pump_affinity_speed",
    description=(
        "Apply pump affinity laws for a rotational speed change.\n"
        "\n"
        "  Q₂ = Q₁·(n₂/n₁)\n"
        "  H₂ = H₁·(n₂/n₁)²\n"
        "  P₂ = P₁·(n₂/n₁)³\n"
        "\n"
        "Valid range: speed ratio 0.5–2.0. Warns outside this range. "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q1": {"type": "number", "description": "Original flow (m³/s). Must be > 0."},
            "H1": {"type": "number", "description": "Original head (m). Must be > 0."},
            "P1": {"type": "number", "description": "Original power (W). Must be > 0."},
            "n1": {"type": "number", "description": "Original speed (rpm). Must be > 0."},
            "n2": {"type": "number", "description": "New speed (rpm). Must be > 0."},
        },
        "required": ["Q1", "H1", "P1", "n1", "n2"],
    },
)


@register(_affinity_speed_spec, write=False)
async def run_affinity_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Q1", "H1", "P1", "n1", "n2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = affinity_speed(a["Q1"], a["H1"], a["P1"], a["n1"], a["n2"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_affinity_trim
# ---------------------------------------------------------------------------

_affinity_trim_spec = ToolSpec(
    name="pump_affinity_trim",
    description=(
        "Apply pump affinity laws for an impeller-trim (diameter) change.\n"
        "\n"
        "  Q₂ = Q₁·(D₂/D₁)\n"
        "  H₂ = H₁·(D₂/D₁)²\n"
        "  P₂ = P₁·(D₂/D₁)³\n"
        "\n"
        "Warns if trim ratio < 70% (accuracy degrades) or > 100% (non-physical). "
        "Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q1": {"type": "number", "description": "Original flow (m³/s). Must be > 0."},
            "H1": {"type": "number", "description": "Original head (m). Must be > 0."},
            "P1": {"type": "number", "description": "Original power (W). Must be > 0."},
            "D1": {"type": "number", "description": "Original impeller diameter (m). Must be > 0."},
            "D2": {"type": "number", "description": "Trimmed impeller diameter (m). Must be > 0."},
        },
        "required": ["Q1", "H1", "P1", "D1", "D2"],
    },
)


@register(_affinity_trim_spec, write=False)
async def run_affinity_trim(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Q1", "H1", "P1", "D1", "D2"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = affinity_trim(a["Q1"], a["H1"], a["P1"], a["D1"], a["D2"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pumps_in_series
# ---------------------------------------------------------------------------

_pumps_in_series_spec = ToolSpec(
    name="pumps_in_series",
    description=(
        "Compute combined head of pumps in series at a given flow rate.\n"
        "\n"
        "H_combined(Q) = Σ H_i(Q)  where H_i(Q) = a_i·Q² + b_i·Q + c_i\n"
        "\n"
        "Supply a list of [a, b, c] pump-curve coefficient triples. "
        "Returns combined and individual heads at Q_eval. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "curves": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "description": "List of [a, b, c] coefficient triples from pump_curve_fit.",
                "minItems": 1,
            },
            "Q_eval": {
                "type": "number",
                "description": "Flow rate at which to evaluate combined head (m³/s). Must be >= 0.",
            },
        },
        "required": ["curves", "Q_eval"],
    },
)


@register(_pumps_in_series_spec, write=False)
async def run_pumps_in_series(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("curves") is None:
        return json.dumps({"ok": False, "reason": "curves is required"})
    if a.get("Q_eval") is None:
        return json.dumps({"ok": False, "reason": "Q_eval is required"})
    result = pumps_in_series(a["curves"], a["Q_eval"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pumps_in_parallel
# ---------------------------------------------------------------------------

_pumps_in_parallel_spec = ToolSpec(
    name="pumps_in_parallel",
    description=(
        "Compute combined flow of pumps in parallel at a given head.\n"
        "\n"
        "Each pump operates at the common head H_eval; combined flow = Σ Q_i(H).\n"
        "For each pump, solves a·Q² + b·Q + (c − H) = 0 for the positive root.\n"
        "\n"
        "Supply a list of [a, b, c] pump-curve coefficient triples. "
        "Returns combined and individual flows at H_eval. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "curves": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "description": "List of [a, b, c] coefficient triples from pump_curve_fit.",
                "minItems": 1,
            },
            "H_eval": {
                "type": "number",
                "description": "Common head at which to evaluate individual flows (m). Must be >= 0.",
            },
        },
        "required": ["curves", "H_eval"],
    },
)


@register(_pumps_in_parallel_spec, write=False)
async def run_pumps_in_parallel(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    if a.get("curves") is None:
        return json.dumps({"ok": False, "reason": "curves is required"})
    if a.get("H_eval") is None:
        return json.dumps({"ok": False, "reason": "H_eval is required"})
    result = pumps_in_parallel(a["curves"], a["H_eval"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_specific_speed
# ---------------------------------------------------------------------------

_specific_speed_spec = ToolSpec(
    name="pump_specific_speed",
    description=(
        "Compute dimensionless specific speed Ns and recommend impeller type.\n"
        "\n"
        "Ns = ω·√Q / H^(3/4)   (SI dimensionless, ω in rad/s)\n"
        "\n"
        "Impeller guidance (approximate Ns ranges):\n"
        "  Ns < 0.4   — radial (low-Ns); consider PD pump if Ns < 0.2\n"
        "  0.4–1.5    — radial centrifugal (best efficiency range)\n"
        "  1.5–3.5    — mixed-flow (Francis)\n"
        "  Ns > 3.5   — axial-flow / propeller\n"
        "\n"
        "Returns Ns, impeller_type, and guidance text. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q": {
                "type": "number",
                "description": "BEP flow rate (m³/s). Must be > 0.",
            },
            "H": {
                "type": "number",
                "description": "BEP head (m). Must be > 0.",
            },
            "n": {
                "type": "number",
                "description": "Rotational speed (rpm). Must be > 0.",
            },
        },
        "required": ["Q", "H", "n"],
    },
)


@register(_specific_speed_spec, write=False)
async def run_specific_speed(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Q", "H", "n"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    result = specific_speed(a["Q"], a["H"], a["n"])
    return ok_payload(result)


# ---------------------------------------------------------------------------
# Tool: pump_minimum_flow_check
# ---------------------------------------------------------------------------

_min_flow_spec = ToolSpec(
    name="pump_minimum_flow_check",
    description=(
        "Check whether the operating flow is above the minimum continuous "
        "stable flow (MCSF).\n"
        "\n"
        "MCSF ≈ 25% of BEP flow (Kaplan §2.4, HI 9.6.4). Below MCSF, risk "
        "of recirculation, vibration, and reduced bearing life.\n"
        "\n"
        "Also warns if Q_op > 120% of BEP (overloading / cavitation risk).\n"
        "\n"
        "Returns below_min_flow (bool) and Q_fraction. Never raises."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "Q_op": {
                "type": "number",
                "description": "Operating flow rate (m³/s). Must be >= 0.",
            },
            "Q_bep": {
                "type": "number",
                "description": "Best efficiency point (BEP) flow rate (m³/s). Must be > 0.",
            },
            "min_fraction": {
                "type": "number",
                "description": (
                    "Minimum-flow fraction of Q_bep (default 0.25 = 25%). "
                    "Must be in (0, 1)."
                ),
            },
        },
        "required": ["Q_op", "Q_bep"],
    },
)


@register(_min_flow_spec, write=False)
async def run_minimum_flow_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
    for field in ("Q_op", "Q_bep"):
        if a.get(field) is None:
            return json.dumps({"ok": False, "reason": f"{field} is required"})
    kwargs: dict = {}
    if "min_fraction" in a:
        kwargs["min_fraction"] = a["min_fraction"]
    result = minimum_flow_note(a["Q_op"], a["Q_bep"], **kwargs)
    return ok_payload(result)
