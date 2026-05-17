# kerf-mates · solver.py

Geometric constraint solver for parametric assembly mates.

## Entrypoints

### `solve_assembly(assembly_doc) -> SolveResult`

Public entry point. Extracts `Entity` and `MateConstraint` objects from the
assembly document, runs `GeometricConstraintSolver.solve()`, and returns a
`SolveResult`.

```python
from kerf_mates.solver import solve_assembly

result = solve_assembly(assembly_doc)
if result.converged:
    for entity_id, transform in result.transforms.items():
        # transform is a 16-float tuple, row-major 4×4 matrix
        apply_transform(entity_id, transform)
```

### `GeometricConstraintSolver.solve() -> SolveResult`

Gradient-descent Newton-like loop. Maximum 100 iterations, convergence
threshold 1e-6 on the residual norm. Each iteration:

1. Evaluates all constraint residuals `r_i`.
2. Forms numerical Jacobian by finite-difference perturbation.
3. Updates DOF vector: `q += -J⁺ · r` (pseudo-inverse via numpy lstsq).
4. Checks `‖r‖ < 1e-6`.

```python
solver = GeometricConstraintSolver(entities, constraints)
result = solver.solve()
# result.converged: bool
# result.iterations: int
# result.residual: float
# result.transforms: dict[str, tuple[float, ...]]  (16-element row-major)
```

## Data types

| Type | Key fields |
|---|---|
| `Entity` | `id`, `kind` (`part`/`assembly`), `transform` (16-float tuple) |
| `MateConstraint` | `id`, `type`, `refs` (list of 2 mate refs), `value`, `unit` |
| `SolveResult` | `converged`, `iterations`, `residual`, `transforms`, `warnings` |

Mate ref fields: `component_id`, `feature_name` (preferred over legacy
`feature_id`), `feature_type` (`face`/`edge`/`vertex`/`axis`).

## Constraint types

`coincident`, `concentric`, `parallel`, `perpendicular`, `distance`,
`angle`, `tangent`.  Distance and angle constraints require `value` and
`unit`; the others are zero-DOF-removal constraints that contribute no
residual displacement magnitude.

## Transform convention

All transforms are 4×4 row-major matrices stored as 16-float tuples
(index 0–15, row-first). Column 3 is the translation; row 3 is `[0,0,0,1]`.

## `compute_tolerance_stackup(assembly_doc)`

Computes worst-case and RSS tolerance contributions for all distance/angle
mates in the assembly. Returns `{mate_id: {worst_case, rss}}`. Delegates
to `kerf_mates.tolerance` functions.

## LLM tool: `solve_assembly`

Registered in `kerf_mates.tools`. Accepts `assembly_file_id`, runs the
solver, and returns `{converged, iterations, residual, transform_count}`.
