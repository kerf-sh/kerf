# kerf-1dsim · 1D System Simulation

Equation-based DAE solver for lumped-element 1-D system models.
Modelica-compatible component library with BDF-1 time integration.

## Overview

`kerf-1dsim` solves systems described by Differential-Algebraic Equations (DAEs)
of the form **F(t, x, dx/dt) = 0**.  It targets:

- Electrical networks (RC, RL, RLC)
- Mechanical (mass-spring-damper)
- Thermal conduction
- Fluid resistance networks
- Any Modelica-flavoured model expressed as `model ... equation ... end;`

## LLM Tools

### `sim1d_run`

Run a 1-D simulation.

```json
{
  "component_type": "RC",
  "params": { "R": 1000, "C": 1e-6, "V0": 5.0 },
  "t_end": 0.01,
  "output_vars": ["v_C"]
}
```

Or with a Modelica snippet:

```json
{
  "modelica_source": "model RC\n  parameter Real R = 1000.0;\n  parameter Real C = 1e-6;\n  parameter Real V0 = 1.0;\n  Real v_C(start = 0.0);\n  Real i(start = 0.001);\nequation\n  der(v_C) = i / C;\n  v_C + R * i = V0;\nend RC;",
  "t_end": 0.005
}
```

**Pre-built component types:**

| `component_type` | Required params             | State vars         |
|------------------|-----------------------------|--------------------|
| `RC`             | R, C, V0                   | v_C, i             |
| `mass_spring`    | m, k, x0, v0               | q, v               |
| `RLC`            | R, L, C, V0                | v_C, i_L           |
| `thermal`        | G, T_a, T_b0               | T_b, Q             |
| `fluid`          | Rf, p_in, p_out0           | p_out, q           |

**Returns:**

```json
{
  "t": [0.0, 0.001, ...],
  "traces": { "v_C": [0.0, 0.632, ...] },
  "converged": true,
  "warnings": [],
  "n_steps": 2000
}
```

### `sim1d_parse`

Parse a Modelica-flavoured model string; returns variable and equation metadata.

```json
{
  "modelica_source": "model Foo\n  parameter Real k = 1.0;\n  Real x(start = 0.0);\nequation\n  der(x) = -k * x;\nend Foo;"
}
```

Returns: `{ model_name, vars, equations, n_state_vars, n_equations }`.

---

## Python API

### Components

```python
from kerf_1dsim.components import Resistor, Capacitor, Inductor
from kerf_1dsim.components import MassSpring, Damper
from kerf_1dsim.components import ThermalConductor, FluidResistor

# Each component: .equations(t, x, dx) -> list[float]
cap = Capacitor(C=1e-6)
residuals = cap.equations(t=0.0, x=[5.0, 1.0], dx=[1e6, 0.0])
```

### Solver

```python
from kerf_1dsim.solver import integrate_dae, integrate_ode, SimResult

# DAE: F(t, x, dx) = 0
def F_rc(t, x, dx):
    v_C, i = x
    return [1e-6 * dx[0] - i, v_C + 1e3 * i - 1.0]

result = integrate_dae(
    F_rc,
    t_span=(0.0, 5e-3),
    x0=[0.0, 1e-3],
    dx0=[1e3, 0.0],
    h=1e-6,
)
# result.t — time array
# result.x — state array [step][var]
# result.converged — bool
```

### Modelica Parser

```python
from kerf_1dsim.parser import parse_model, build_simulation
from kerf_1dsim.solver import integrate_dae

source = """
model RCCircuit
  parameter Real R = 1000.0;
  parameter Real C = 1e-6;
  parameter Real V0 = 1.0;
  Real v_C(start = 0.0);
  Real i(start = 0.001);
equation
  der(v_C) = i / C;
  v_C + R * i = V0;
end RCCircuit;
"""

model = parse_model(source)
F, x0, dx0, var_names, params = build_simulation(model)

result = integrate_dae(F, t_span=(0.0, 5e-3), x0=x0, dx0=dx0, h=1e-6)
```

### Causalisation (BLT)

```python
from kerf_1dsim.causality import causalise

# incidence[i] = set of variable indices in equation i
incidence = [{0}, {0, 1}, {1, 2}]
cs = causalise(n_eq=3, n_var=3, incidence=incidence)

for block in cs.blocks:
    print(block.eq_indices, block.var_indices, "loop:", block.is_loop)
```

---

## Solver Details

### BDF-1 (Backward Euler DAE)

`integrate_dae` implements a fixed-step, first-order Backward Differentiation
Formula (BDF-1) integration:

    dx/dt ≈ (x_{n+1} - x_n) / h

Substituting into F gives an implicit algebraic system in x_{n+1}, solved by
Newton-Raphson with finite-difference Jacobian and backtracking line search.

Suitable for stiff systems (RC with small tau, structural dynamics).

**Convergence tolerance:** default `tol=1e-8`.  Reduce `h` or tighten `tol`
for greater accuracy.  For RC circuits use `h ≤ tau/200` for 1% accuracy.

### Forward Euler ODE fallback

`integrate_ode` is explicit (non-stiff only):

    x_{n+1} = x_n + h * f(t_n, x_n)

Use only when the system is non-stiff (e.g. slow mechanical oscillators with
large time steps).  For electrical/thermal/stiff problems prefer `integrate_dae`.

---

## Supported Modelica Subset

```
model <Name>
  parameter Real <var> = <value>;          // numeric parameter
  Real <var>;                              // algebraic variable
  Real <var>(start = <value>);             // state with initial value
equation
  der(<var>) = <expr>;                     // ODE equation
  <expr> = <expr>;                         // algebraic equation
end <Name>;
```

Supported expressions: arithmetic (`+`, `-`, `*`, `/`, `^`), `exp()`,
`log()`, `sqrt()`, `sin()`, `cos()`, `tan()`, `abs()`, `pi`, `e`, and
all declared variable/parameter names.

**Not supported:** arrays, connectors, inheritance, when/if blocks, import.

---

## Domain Reference

| Component          | Governing equation                              | Modelica base class                                     |
|--------------------|--------------------------------------------------|----------------------------------------------------------|
| Resistor           | v = R·i                                         | Electrical.Analog.Basic.Resistor                         |
| Capacitor          | C·dv/dt = i                                     | Electrical.Analog.Basic.Capacitor                        |
| Inductor           | L·di/dt = v                                     | Electrical.Analog.Basic.Inductor                         |
| MassSpring         | m·d²q/dt² + k·q = F                            | Mechanics.Translational.Mass + Spring                    |
| Damper             | F_d = b·v_rel                                   | Mechanics.Translational.Damper                           |
| ThermalConductor   | Q = G·(T_a − T_b)                              | Thermal.HeatTransfer.ThermalConductor                    |
| FluidResistor      | q = (p_in − p_out) / Rf                         | Fluid linearised pipe resistance                         |
