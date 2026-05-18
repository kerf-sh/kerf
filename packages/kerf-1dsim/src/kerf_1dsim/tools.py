"""
kerf_1dsim.tools
================

LLM tool surface for the 1D system simulation plugin.

Tools
-----
  sim1d_run     — simulate a model from inline equations or a Modelica snippet
  sim1d_parse   — parse a Modelica model string and return its structure
"""

from __future__ import annotations

import json
import math
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_1dsim._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx


# ---------------------------------------------------------------------------
# sim1d_run
# ---------------------------------------------------------------------------

sim1d_run_spec = ToolSpec(
    name="sim1d_run",
    description=(
        "Run a 1D lumped-element system simulation using an equation-based DAE "
        "solver (BDF-1 / backward Euler). Supports RC circuits, mass-spring "
        "systems, thermal conduction, and fluid networks. "
        "Provide either a Modelica model string or a component list."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "modelica_source": {
                "type": "string",
                "description": (
                    "Modelica-flavoured model source text. "
                    "Mutually exclusive with 'component_type'."
                ),
            },
            "component_type": {
                "type": "string",
                "enum": ["RC", "mass_spring", "RLC", "thermal", "fluid"],
                "description": "Pre-built component shortcut.",
            },
            "params": {
                "type": "object",
                "description": (
                    "Component parameters. "
                    "RC: {R, C, V0}. "
                    "mass_spring: {m, k, x0, v0}. "
                    "RLC: {R, L, C, V0}. "
                    "thermal: {G, T_a, T_b0}. "
                    "fluid: {Rf, p_in, p_out0}."
                ),
            },
            "t_end": {
                "type": "number",
                "description": "Simulation end time [s]. Default: 1.0.",
            },
            "h": {
                "type": "number",
                "description": "Time step [s]. Default: auto (t_end/1000).",
            },
            "output_vars": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Variable names to return in the result. Default: all.",
            },
        },
    },
)


@register(sim1d_run_spec)
async def run_sim1d_run(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    t_end = float(a.get("t_end", 1.0))
    params = a.get("params") or {}

    if "modelica_source" in a:
        # Parse and simulate Modelica snippet
        from kerf_1dsim.parser import parse_model, build_simulation
        from kerf_1dsim.solver import integrate_dae

        try:
            model = parse_model(a["modelica_source"])
            F, x0, dx0, var_names, _ = build_simulation(model)
        except Exception as e:
            return err_payload(f"parse error: {e}", "PARSE_ERROR")

        h = float(a.get("h", t_end / 1000))
        try:
            result = integrate_dae(F, t_span=(0.0, t_end), x0=x0, dx0=dx0, h=h)
        except Exception as e:
            return err_payload(f"solver error: {e}", "SOLVER_ERROR")

        return _format_result(result, var_names, a.get("output_vars"))

    comp = a.get("component_type")
    if comp == "RC":
        return _run_rc(params, t_end, a.get("h"), a.get("output_vars"))
    elif comp == "mass_spring":
        return _run_mass_spring(params, t_end, a.get("h"), a.get("output_vars"))
    elif comp == "RLC":
        return _run_rlc(params, t_end, a.get("h"), a.get("output_vars"))
    elif comp == "thermal":
        return _run_thermal(params, t_end, a.get("h"), a.get("output_vars"))
    elif comp == "fluid":
        return _run_fluid(params, t_end, a.get("h"), a.get("output_vars"))
    else:
        return err_payload("Provide 'modelica_source' or 'component_type'.", "BAD_ARGS")


def _format_result(result, var_names: list[str], output_vars=None) -> str:
    from kerf_1dsim.tools import ok_payload
    t_arr = result.t
    x_arr = result.x
    n_steps = len(t_arr)
    # Downsample to at most 500 points for payload size
    stride = max(1, n_steps // 500)
    t_out = t_arr[::stride]
    x_out = x_arr[::stride]

    if output_vars:
        indices = [var_names.index(v) for v in output_vars if v in var_names]
        names_out = [var_names[i] for i in indices]
    else:
        indices = list(range(len(var_names)))
        names_out = var_names

    traces = {}
    for idx, name in zip(indices, names_out):
        traces[name] = [row[idx] for row in x_out]

    return ok_payload({
        "t": t_out,
        "traces": traces,
        "converged": result.converged,
        "warnings": result.warnings,
        "n_steps": n_steps,
    })


def _run_rc(params: dict, t_end: float, h_hint, output_vars) -> str:
    R = float(params.get("R", 1e3))
    C = float(params.get("C", 1e-6))
    V0 = float(params.get("V0", 1.0))
    from kerf_1dsim.solver import integrate_dae

    def F_rc(t, x, dx):
        v_C, i = x[0], x[1]
        dv_C = dx[0]
        return [
            C * dv_C - i,           # capacitor: C dv/dt = i
            v_C + R * i - V0,       # KVL: v_C + R*i = V0
        ]

    h = float(h_hint) if h_hint else t_end / 2000
    result = integrate_dae(F_rc, (0.0, t_end), [0.0, V0 / R], [V0 / (R * C), 0.0], h)
    return _format_result(result, ["v_C", "i"], output_vars)


def _run_mass_spring(params: dict, t_end: float, h_hint, output_vars) -> str:
    m = float(params.get("m", 1.0))
    k = float(params.get("k", 1.0))
    x0 = float(params.get("x0", 1.0))
    v0 = float(params.get("v0", 0.0))
    from kerf_1dsim.solver import integrate_dae

    def F_ms(t, x, dx):
        q, v = x[0], x[1]
        dq, dv = dx[0], dx[1]
        return [
            dq - v,
            m * dv + k * q,
        ]

    h = float(h_hint) if h_hint else t_end / 2000
    result = integrate_dae(F_ms, (0.0, t_end), [x0, v0], [v0, -k * x0 / m], h)
    return _format_result(result, ["q", "v"], output_vars)


def _run_rlc(params: dict, t_end: float, h_hint, output_vars) -> str:
    R = float(params.get("R", 10.0))
    L = float(params.get("L", 1e-3))
    C = float(params.get("C", 1e-6))
    V0 = float(params.get("V0", 1.0))
    from kerf_1dsim.solver import integrate_dae

    # States: v_C, i_L
    def F_rlc(t, x, dx):
        v_C, i_L = x[0], x[1]
        dv_C, di_L = dx[0], dx[1]
        return [
            C * dv_C - i_L,                  # capacitor
            L * di_L + R * i_L + v_C - V0,   # KVL
        ]

    h = float(h_hint) if h_hint else t_end / 5000
    result = integrate_dae(F_rlc, (0.0, t_end), [0.0, 0.0], [0.0, V0 / L], h)
    return _format_result(result, ["v_C", "i_L"], output_vars)


def _run_thermal(params: dict, t_end: float, h_hint, output_vars) -> str:
    from kerf_1dsim.components import ThermalConductor
    G = float(params.get("G", 1.0))
    T_a = float(params.get("T_a", 100.0))
    T_b0 = float(params.get("T_b0", 20.0))
    tc = ThermalConductor(G)

    def F_thermal(t, x, dx):
        return tc.equations(t, [T_a, x[0], x[1]], dx)

    from kerf_1dsim.solver import integrate_dae
    h = float(h_hint) if h_hint else t_end / 1000
    result = integrate_dae(F_thermal, (0.0, t_end), [T_b0, G * (T_a - T_b0)], [0.0, 0.0], h)
    return _format_result(result, ["T_b", "Q"], output_vars)


def _run_fluid(params: dict, t_end: float, h_hint, output_vars) -> str:
    from kerf_1dsim.components import FluidResistor
    Rf = float(params.get("Rf", 1e6))
    p_in = float(params.get("p_in", 1e5))
    p_out0 = float(params.get("p_out0", 0.0))
    fr = FluidResistor(Rf)

    def F_fluid(t, x, dx):
        return fr.equations(t, [p_in, x[0], x[1]], dx)

    from kerf_1dsim.solver import integrate_dae
    h = float(h_hint) if h_hint else t_end / 1000
    result = integrate_dae(F_fluid, (0.0, t_end), [p_out0, (p_in - p_out0) / Rf], [0.0, 0.0], h)
    return _format_result(result, ["p_out", "q"], output_vars)


# ---------------------------------------------------------------------------
# sim1d_parse
# ---------------------------------------------------------------------------

sim1d_parse_spec = ToolSpec(
    name="sim1d_parse",
    description=(
        "Parse a Modelica-flavoured model string and return its structural "
        "representation: variable declarations, parameter values, and equations."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "modelica_source": {
                "type": "string",
                "description": "Modelica model source text.",
            },
        },
        "required": ["modelica_source"],
    },
)


@register(sim1d_parse_spec)
async def run_sim1d_parse(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    source = a.get("modelica_source", "")
    if not source:
        return err_payload("modelica_source is required", "BAD_ARGS")

    from kerf_1dsim.parser import parse_model

    try:
        model = parse_model(source)
    except Exception as e:
        return err_payload(f"parse error: {e}", "PARSE_ERROR")

    vars_out = [
        {
            "name": v.name,
            "is_parameter": v.is_parameter,
            "start": v.start,
            **({"value": v.value} if v.is_parameter else {}),
        }
        for v in model.vars
    ]
    eqs_out = [
        {
            "lhs": eq.lhs,
            "rhs": eq.rhs,
            "is_der": eq.is_der,
            **({"der_var": eq.der_var} if eq.is_der else {}),
        }
        for eq in model.equations
    ]

    return ok_payload({
        "model_name": model.name,
        "vars": vars_out,
        "equations": eqs_out,
        "n_state_vars": sum(1 for v in model.vars if not v.is_parameter),
        "n_equations": len(model.equations),
    })
