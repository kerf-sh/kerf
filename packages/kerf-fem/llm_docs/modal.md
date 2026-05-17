# kerf-fem · modal.py

> **Straggler — source not yet implemented.**
>
> `packages/kerf-fem/src/kerf_fem/modal.py` does not exist on the `refactor`
> branch. This document is a placeholder describing the planned interface.

## Planned entrypoint

```python
from kerf_fem.modal import solve_modal

result = solve_modal(
    mesh=mesh,
    material={"E": 210e3, "nu": 0.3, "rho": 7850},
    bcs=boundary_conditions,
    n_modes=10,
)
# planned returns: {frequencies_hz, mode_shapes, mass_participation}
```

## Planned formulation

Generalised eigenproblem:

    [K − ω² M] φ = 0

Solved by shifted inverse iteration or Lanczos iteration for the lowest
n_modes. Mass matrix M can be consistent or lumped.

## See also

- `kerf_fem.acoustics_fem` — already implements 1D/2D Helmholtz eigenproblem
- `kerf_fem.explicit` — time-domain dynamics
