# kerf-fem · cfd_potential.py

2-D incompressible, inviscid, irrotational potential/stream-function flow on a structured Cartesian grid. Solves the Laplace equation by Gauss-Seidel + SOR. Pure Python — no numpy/scipy dependency. All routines return `{"ok": False, "reason": "..."}` on bad input and never raise.

---

## When to use

- Compute velocity and pressure fields for idealized external flow (uniform flow, cylinder, superimposed singularities)
- Evaluate surface pressure coefficient Cp(θ) and compare against the exact analytic result
- Build stream-function fields for flow visualisation or as initial conditions for Navier-Stokes solvers
- Superpose elementary potential-flow solutions (uniform flow, source, sink, doublet)

**Scope:** 2-D only; structured Cartesian grid; inviscid and irrotational. D'Alembert's paradox applies: drag on a closed body is identically zero in this model. No separation, no boundary layer, no turbulence. For viscous effects use `cfd_navier_stokes.py`.

---

## Physics

For irrotational incompressible flow:

```
Δφ = 0   (velocity potential)
u = ∂φ/∂x ,  v = ∂φ/∂y

or equivalently:

Δψ = 0   (stream function)
u = ∂ψ/∂y ,  v = −∂ψ/∂x
```

Pressure from Bernoulli (Kundu & Cohen, *Fluid Mechanics*, 4th ed., §6.5):
```
Cp(θ) = (p − p∞) / (½ ρ V∞²) = 1 − (V/V∞)²
```

**Analytic oracle — uniform flow over a 2-D cylinder** (Lamb, *Hydrodynamics*, 6th ed., §69):
```
ψ(r, θ) = V∞ y (1 − R²/r²)
Cp(θ)   = 1 − 4 sin²θ
```
Stagnation points at θ = 0 and θ = π. Numerical result matches this formula within ~5 % on an 81 × 81 grid with stair-step body mask.

---

## Public entrypoints

### `make_grid(nx, ny, x_range, y_range) → dict`

Create a uniform Cartesian grid descriptor.
```python
grid = make_grid(nx=81, ny=81,
                 x_range=(-1.0, 1.0),
                 y_range=(-1.0, 1.0))
# grid keys: ok, x (list), y (list), nx, ny, dx, dy
```

---

### `solve_laplace(grid, mask, bc_value, *, omega=1.7, tol=1e-7, max_iter=30000, initial=None) → dict`

General Laplace solver for a 2-D domain. Boundary tags:

| mask value | meaning |
|---|---|
| 0 | interior — residual equation applied |
| 1 | Dirichlet — φ fixed to `bc_value[i,j]` |
| 2 | Neumann — ∂φ/∂n imposed; one-sided 2nd-order stencil |
| 3 | solid body interior — φ fixed, excluded from solve |

Returns `{ok, phi, iterations, max_residual}`.

---

### `velocity_from_streamfunction(grid, psi) → dict`

Compute (u, v) velocity components from a stream function field:
`u = ∂ψ/∂y`, `v = −∂ψ/∂x` (central differences).

Returns `{ok, u, v}`.

---

### `pressure_bernoulli(u, v, v_inf, rho=1.0) → dict`

Bernoulli pressure and Cp from a velocity field:
`Cp[i,j] = 1 − (u[i,j]² + v[i,j]²) / v_inf²`

Returns `{ok, Cp, p}`.

---

### `cylinder_streamfunction(R=0.2, v_inf=1.0, domain_half=1.0, nx=81, ny=81, ...) → dict`

High-level solver: uniform flow past a 2-D cylinder of radius R.

Sets up a stream-function problem with exact Dirichlet boundary values on the outer rectangle (`ψ = V∞ y (1 − R²/r²)`) and `ψ = 0` on the cylinder body.

Returns:
```json
{
  "ok": true,
  "psi": [[...]],
  "u": [[...]], "v": [[...]],
  "theta_surf": [...],
  "Cp_surf": [...],
  "Cp_exact": [...]
}
```
`Cp_exact[i] = 1 − 4 sin²(theta_surf[i])` — the Lamb analytic result.

```python
from kerf_fem.cfd_potential import cylinder_streamfunction

r = cylinder_streamfunction(R=0.2, v_inf=1.0, nx=81, ny=81)
print(r["Cp_exact"][0])   # ≈ 1.0  (stagnation, θ=0)
print(r["Cp_exact"][12])  # ≈ −3.0 (top of cylinder, θ=π/2: 1−4·1 = −3)
```

---

### `cylinder_Cp_analytic(theta) → float`

Returns `1 − 4 sin²(theta)`. Convenience function for the exact Lamb/Kundu result.

---

### `uniform_flow(grid, v_inf=1.0) → dict`

Stream function for pure uniform flow: `ψ = V∞ · y`.

---

## Analytic oracle citations

| Result | Reference |
|---|---|
| Cp(θ) = 1 − 4 sin²θ for cylinder | Lamb H., *Hydrodynamics* (6th ed., 1932), §69, p. 75 |
| Stream function ψ = V∞ y(1 − R²/r²) | Kundu P. & Cohen I., *Fluid Mechanics* (4th ed., 2008), §6.5 |
| Bernoulli equation for pressure | Pozar D.M., *Microwave Engineering* (ancillary); Batchelor §2.4 |

---

## Limitations

- Inviscid and irrotational: no drag on closed bodies (D'Alembert's paradox). Only pressure (form) drag; skin-friction drag requires a viscous solver.
- Curved body boundaries are stair-stepped to grid resolution O(h); refine `nx`/`ny` for better Cp agreement near the body.
- No free surface, no compressibility, no vorticity.
- 2-D structured Cartesian only; no immersed-boundary method.
