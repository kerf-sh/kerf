"""
kerf_1dsim.parser
=================

Minimal Modelica-flavoured model parser.

Handles a strict subset of Modelica syntax:

    model <Name>
      parameter Real <var> = <value>;
      Real <var>(start = <value>);
      ...
    equation
      <lhs> = <rhs>;
      der(<var>) = <expr>;
      ...
    end <Name>;

The parser is intentionally small and rule-based (regex + recursive descent).
It is NOT a full Modelica parser; the goal is to bootstrap LLM-authored
models and enable round-trip tests without a full Modelica compiler.

Public API
----------
    parse_model(source: str) -> ParsedModel

    build_simulation(model: ParsedModel) -> (F, x0, dx0, var_names)
        where F is a DAE residual callable suitable for ``integrate_dae``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# AST types
# ---------------------------------------------------------------------------

@dataclass
class VarDecl:
    name: str
    is_parameter: bool = False
    start: float = 0.0
    value: float | None = None   # set for parameters


@dataclass
class Equation:
    """One  lhs = rhs  or  der(x) = rhs  equation."""
    lhs: str            # raw LHS string
    rhs: str            # raw RHS string
    is_der: bool = False
    der_var: str = ""   # variable name inside der()


@dataclass
class ParsedModel:
    name: str
    vars: list[VarDecl] = field(default_factory=list)
    equations: list[Equation] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tokenisation helpers
# ---------------------------------------------------------------------------

_RE_MODEL      = re.compile(r'^\s*model\s+(\w+)', re.IGNORECASE)
_RE_END        = re.compile(r'^\s*end\s+(\w+)\s*;', re.IGNORECASE)
_RE_PARAM      = re.compile(
    r'^\s*parameter\s+Real\s+(\w+)\s*=\s*([\d.eE+\-]+)\s*;', re.IGNORECASE)
_RE_VAR        = re.compile(
    r'^\s*Real\s+(\w+)(?:\s*\(\s*start\s*=\s*([\d.eE+\-]+)\s*\))?\s*;',
    re.IGNORECASE)
_RE_DER_EQ     = re.compile(
    r'^\s*der\s*\(\s*(\w+)\s*\)\s*=\s*(.+?)\s*;', re.IGNORECASE)
_RE_EQ         = re.compile(r'^\s*(.+?)\s*=\s*(.+?)\s*;')
_RE_EQUATION   = re.compile(r'^\s*equation\b', re.IGNORECASE)


def parse_model(source: str) -> ParsedModel:
    """
    Parse a minimal Modelica model string.

    Parameters
    ----------
    source : str
        Modelica model source text.

    Returns
    -------
    ParsedModel

    Raises
    ------
    ValueError
        If the source is not recognisable as a valid model block.
    """
    lines = source.splitlines()
    model_name: str | None = None
    vars_: list[VarDecl] = []
    equations_: list[Equation] = []
    in_equation_section = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue

        if model_name is None:
            m = _RE_MODEL.match(line)
            if m:
                model_name = m.group(1)
            continue

        # Check for "end <Name>;"
        if _RE_END.match(line):
            break

        # Switch to equation section
        if _RE_EQUATION.match(line):
            in_equation_section = True
            continue

        if not in_equation_section:
            # Variable declarations
            mp = _RE_PARAM.match(line)
            if mp:
                vars_.append(VarDecl(
                    name=mp.group(1),
                    is_parameter=True,
                    value=float(mp.group(2)),
                    start=float(mp.group(2)),
                ))
                continue
            mv = _RE_VAR.match(line)
            if mv:
                start_val = float(mv.group(2)) if mv.group(2) else 0.0
                vars_.append(VarDecl(name=mv.group(1), start=start_val))
                continue
        else:
            # Equation section
            md = _RE_DER_EQ.match(line)
            if md:
                equations_.append(Equation(
                    lhs=f"der({md.group(1)})",
                    rhs=md.group(2),
                    is_der=True,
                    der_var=md.group(1),
                ))
                continue
            meq = _RE_EQ.match(line)
            if meq:
                equations_.append(Equation(
                    lhs=meq.group(1),
                    rhs=meq.group(2),
                ))
                continue

    if model_name is None:
        raise ValueError("No 'model <Name>' declaration found in source.")

    return ParsedModel(name=model_name, vars=vars_, equations=equations_)


# ---------------------------------------------------------------------------
# Expression evaluator (safe subset of Python expressions)
# ---------------------------------------------------------------------------

_SAFE_NAMES = {
    "exp": math.exp, "log": math.log, "sqrt": math.sqrt,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "abs": abs, "pi": math.pi, "e": math.e,
}


def _eval_expr(expr: str, env: dict[str, float]) -> float:
    """Evaluate a simple numeric expression in a restricted namespace."""
    # Replace Modelica-isms
    expr = expr.replace("^", "**")
    ns = {**_SAFE_NAMES, **env}
    try:
        return float(eval(expr, {"__builtins__": {}}, ns))  # noqa: S307
    except Exception as exc:
        raise ValueError(f"Cannot evaluate expression {expr!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# Build simulation residual from ParsedModel
# ---------------------------------------------------------------------------

def build_simulation(model: ParsedModel):
    """
    Convert a ``ParsedModel`` to a DAE residual function.

    Returns
    -------
    F : callable(t, x, dx) -> list[float]
        DAE residual; len(F) == len(state variables).
    x0 : list[float]
        Initial values (from ``start`` attributes).
    dx0 : list[float]
        Initial derivatives (zeros).
    var_names : list[str]
        Names of the state / algebraic variables (parameters excluded).
    param_env : dict[str, float]
        Parameter name -> value mapping.
    """
    # Split parameters from state vars
    params: dict[str, float] = {}
    state_vars: list[VarDecl] = []
    for v in model.vars:
        if v.is_parameter:
            params[v.name] = v.value  # type: ignore[arg-type]
        else:
            state_vars.append(v)

    var_names = [v.name for v in state_vars]
    x0 = [v.start for v in state_vars]
    dx0 = [0.0] * len(state_vars)

    equations = model.equations

    def F(t: float, x: list[float], dx: list[float]) -> list[float]:
        # Build environment: params + current state
        env: dict[str, float] = {"t": t, **params}
        for name, val in zip(var_names, x):
            env[name] = val
        # der() references map to dx
        for name, dval in zip(var_names, dx):
            env[f"der_{name}"] = dval  # internal key

        residuals = []
        for eq in equations:
            if eq.is_der:
                # der(x) = rhs  →  residual: dx_var - rhs = 0
                dvar_idx = var_names.index(eq.der_var)
                rhs_val = _eval_expr(eq.rhs, env)
                residuals.append(dx[dvar_idx] - rhs_val)
            else:
                # lhs = rhs  →  residual: lhs_val - rhs_val = 0
                lhs_val = _eval_expr(eq.lhs, env)
                rhs_val = _eval_expr(eq.rhs, env)
                residuals.append(lhs_val - rhs_val)

        return residuals

    return F, x0, dx0, var_names, params
