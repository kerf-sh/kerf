# kerf-fem · nonlinear.py

Nonlinear FEM solver covering geometric nonlinearity (Total-Lagrangian truss),
material nonlinearity (J2 plasticity, plane-stress), contact (penalty), and
Riks arc-length continuation for snap-through/snap-back.

## Entrypoint

### `solve_nonlinear(mesh, material, bcs, loads, kind, ...) -> dict`

```python
from kerf_fem.nonlinear import solve_nonlinear

result = solve_nonlinear(
    mesh=mesh,
    material={"E": 210e3, "nu": 0.3, "sigma_y": 250, "H": 1000},
    bcs=boundary_conditions,
    loads=load_steps,
    kind="geometric",    # "geometric" | "material" | "contact"
    arc_length=False,
)
# result: {ok, path, warnings, reason}
```

Returns:
- `ok` — bool, convergence flag
- `path` — list of load-step results `{lambda, u, sigma, eps_p}`
- `warnings` — list of strings
- `reason` — failure message if `ok=False`

## Formulation kinds

### `"geometric"` — Total-Lagrangian truss

Green-Lagrange strain:

    ε_GL = (L_d² − L_0²) / (2 L_0²)

Tangent stiffness:

    K = K_material + K_geometric

where K_geometric is the geometric (stress) stiffness accounting for
large-displacement effects.

### `"material"` — Plane-stress J2 plasticity

Radial return mapping for plane-stress bilinear isotropic hardening:

    Δγ = f_trial / (3G + H)

where f_trial = σ_trial_eq − σ_y − H·ε_p_acc and G is the shear modulus.

### `"contact"` — Penalty contact

Normal contact force at penetrating node:

    f_c = k_penalty × g × n

Contact stiffness contribution:

    K_c = k_penalty × n ⊗ n

where g is the gap function (negative = penetration) and n is the outward
normal.

## Arc-length (Riks) continuation

Activated with `arc_length=True`. Uses a cylindrical constraint:

    a1 × dλ + a2 = 0

where a1, a2 are updated each step to maintain a constant arc-length in the
(u, λ) space. Enables tracing snap-through and limit-point behaviour.

`_riks_step()` is the internal per-step solver.

## Convergence

Newton-Raphson iterations with tolerance on the residual norm. Up to 25
Newton iterations per load step by default. Load stepping is halved
automatically on non-convergence.

## Standards reference

- Belytschko, Liu, Moran: Nonlinear Finite Elements for Continua and Structures
- Crisfield: Non-linear Finite Element Analysis of Solids and Structures
