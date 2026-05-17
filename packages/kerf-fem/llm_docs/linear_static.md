# kerf-fem · linear_static.py

> **Straggler — source not yet implemented.**
>
> `packages/kerf-fem/src/kerf_fem/linear_static.py` does not exist on the
> `refactor` branch. This document is a placeholder describing the planned
> interface for future implementation.

## Planned entrypoint

```python
from kerf_fem.linear_static import solve_linear_static

result = solve_linear_static(
    mesh=mesh,
    material={"E": 210e3, "nu": 0.3},
    bcs=boundary_conditions,
    loads=nodal_loads,
)
# planned returns: {u, sigma, eps, reactions}
```

## Planned formulation

Standard linear-elastic FEM:

    K u = f

Global stiffness assembled from CST (constant-strain triangle) or Q4 elements.
Dirichlet BCs enforced by row/column elimination. Solve by sparse LU or CG.

## See also

- `kerf_fem.nonlinear` — for `kind="material"` or `kind="geometric"` problems
- `kerf_fem.explicit` — for dynamic problems
