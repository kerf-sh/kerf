# kerf-fem · thermal.py

> **Straggler — source not yet implemented.**
>
> `packages/kerf-fem/src/kerf_fem/thermal.py` does not exist on the `refactor`
> branch. This document is a placeholder describing the planned interface.

## Planned entrypoint

```python
from kerf_fem.thermal import solve_thermal

result = solve_thermal(
    mesh=mesh,
    material={"k": 50.0, "rho": 7850, "cp": 460},
    bcs={"dirichlet": [...], "neumann_flux": [...]},
    source=0.0,         # volumetric heat source (W/m³)
    transient=False,    # True for time-dependent
    duration=None,      # s, if transient
)
# planned returns: {T, heat_flux, total_heat_flow}
```

## Planned formulation

Steady-state: −∇·(k∇T) = Q

Transient: ρ c_p ∂T/∂t − ∇·(k∇T) = Q  (Crank-Nicolson or backward Euler)

Assembled in the same Poisson/Laplace FEM framework as `kerf_fem.em_field`.

## See also

- `kerf_fem.em_field` — same FEM assembly (Poisson equation)
- `kerf_electronics.thermal` — PCB thermal analysis
