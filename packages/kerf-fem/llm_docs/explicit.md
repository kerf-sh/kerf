# kerf-fem · explicit.py

Explicit time integration for structural dynamics (central-difference
leapfrog, Belytschko-Hughes).

## Entrypoint

### `solve_explicit(model, duration, kind, *, safety_factor=0.9)`

Central-difference explicit time integrator. Returns a time-history dict.

```python
from kerf_fem.explicit import solve_explicit

result = solve_explicit(
    model=model,         # dict: nodes, elements, material, loads, bcs
    duration=0.01,       # simulation end time (s)
    kind="bar",          # "spring_mass" | "bar"
    safety_factor=0.9,   # CFL multiplier (default 0.9)
)
# result keys: t, x, v, KE, IE, CE, dt, n_steps, energy_error
```

## Time-step computation (CFL condition)

**Spring-mass system** (`kind="spring_mass"`):

    dt = safety_factor × 2 / ω_max

where ω_max = sqrt(k_max / m_min).

**Bar / continuum** (`kind="bar"`):

    dt = safety_factor × L_min / c

where c = sqrt(E / ρ) is the bar wave speed and L_min is the minimum element
length.

## Integration algorithm

Start-up half-step (Belytschko-Hughes):

    v[½] = v[0] + a[0] × dt/2

Main loop:

    x[n+1] = x[n] + v[n+½] × dt
    a[n+1] = M⁻¹ (F_ext[n+1] − F_int[n+1])
    v[n+3/2] = v[n+½] + a[n+1] × dt

## Energy balance

- **KE** — kinetic energy ½ m v²
- **IE** — internal (strain) energy; incremented as dIE = −F_int · dx
  (resisting force × displacement increment, negative convention)
- **CE** — contact/constraint energy
- **energy_error** = |KE + IE + CE − W_ext| / max(KE + IE, 1e-12)

## Output keys

| Key | Description |
|---|---|
| `t` | Time array (s) |
| `x` | Nodal displacement history |
| `v` | Nodal velocity history |
| `KE` | Kinetic energy history (J) |
| `IE` | Internal energy history (J) |
| `CE` | Contact energy history (J) |
| `dt` | Stable time step used (s) |
| `n_steps` | Total integration steps |
| `energy_error` | Relative energy error at final step |

## Notes

- The method is conditionally stable; `energy_error` > 0.01 indicates likely
  CFL violation or excessive deformation.
- For implicit (quasi-static) analysis use `kerf_fem.nonlinear`.
- For frequency-domain analysis use `kerf_fem.acoustics_fem` or the FEM
  eigenproblem solver.
