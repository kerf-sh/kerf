# kerf-fem · cfd_navier_stokes.py

2-D incompressible Navier-Stokes solver via Chorin's projection method on a staggered MAC grid. Laminar only — no turbulence model. Pure Python — no numpy/scipy dependency. All routines return `{"ok": False, "reason": "..."}` on bad input and never raise.

---

## When to use

- Solve laminar internal flows (channel, cavity) at low-to-moderate Reynolds number
- Validate against the Ghia, Ghia & Shin (1982) lid-driven cavity benchmark at Re = 100
- Compute Hagen-Poiseuille velocity profile and pressure drop for pipe/channel flow
- Generate a pressure and velocity field for a 2-D structured-grid domain with custom boundary conditions

**Scope:** 2-D, laminar only. Solutions at Re above the laminar-turbulent transition (Re ≳ 2 300 pipe; Re ≳ 10 000 cavity) may converge but are physically incorrect. Not for engineering turbulent flows.

---

## Formulation

Projection method (Chorin 1968):

1. **Provisional velocity** (explicit Euler, no pressure):
   ```
   u* = uⁿ + Δt(−(uⁿ·∇)uⁿ + ν ∇²uⁿ)
   ```
   Convective terms: 2nd-order central differences with ~10 % upwind blend for stability.

2. **Pressure Poisson solve:**
   ```
   ∇² p^{n+1} = (ρ/Δt) ∇·u*
   ```
   Solved by Gauss–Seidel + SOR (homogeneous Neumann BCs on walls).

3. **Velocity correction:**
   ```
   u^{n+1} = u* − (Δt/ρ) ∂p/∂x
   ```

**Grid layout (staggered MAC):**
- Pressure p at cell centres
- u at cell vertical faces
- v at cell horizontal faces

**Stability:** adaptive Δt using CFL/von-Neumann: `Δt < min(0.25 dx²/ν, 0.25 dy²/ν, CFL·dx/|u|_max)`.

---

## Public entrypoints

### `make_staggered_grid(nx, ny, Lx=1.0, Ly=1.0) → dict`

Create a MAC staggered-grid descriptor.
```python
from kerf_fem.cfd_navier_stokes import make_staggered_grid

grid = make_staggered_grid(nx=41, ny=41, Lx=1.0, Ly=1.0)
# keys: ok, nx, ny, dx, dy, Lx, Ly
```

---

### `solve_projection(grid, nu, rho, bcs, *, body_force=(0,0), max_steps=30000) → dict`

Solve to steady state (false-transient marching).

**`bcs`** — dict with one entry per wall:
```json
{
  "top":    {"type": "moving", "u": 1.0, "v": 0.0},
  "bottom": {"type": "wall"},
  "left":   {"type": "wall"},
  "right":  {"type": "wall"}
}
```

Wall types: `"wall"` (no-slip), `"moving"` (specify `u`, `v`), `"inflow"` (specify `u`, `v`), `"outflow"` (zero-gradient), `"symmetry"`.

Returns:
```json
{
  "ok": true,
  "U": [[...]],
  "V": [[...]],
  "P": [[...]],
  "steps": 18450,
  "converged": true,
  "max_div": 1.2e-8
}
```

---

### `velocities_cell_centred(grid, U, V) → dict`

Interpolate staggered u/v to cell centres for post-processing or visualisation.
Returns `{u_cc, v_cc}`.

---

### `solve_projection` — lid-driven cavity Re=100

```python
from kerf_fem.cfd_navier_stokes import make_staggered_grid, solve_projection

nu = 0.01   # Re = U L / nu = 1.0 × 1.0 / 0.01 = 100
grid = make_staggered_grid(nx=41, ny=41, Lx=1.0, Ly=1.0)
result = solve_projection(
    grid, nu=nu, rho=1.0,
    bcs={
        "top":    {"type": "moving", "u": 1.0, "v": 0.0},
        "bottom": {"type": "wall"},
        "left":   {"type": "wall"},
        "right":  {"type": "wall"},
    },
    max_steps=50000,
)
print(result["converged"])
```

---

### `ghia_re100_centreline() → dict`

Return Ghia-Ghia-Shin (1982) tabulated u-velocity along the vertical centreline (x = 0.5) of the unit lid-driven cavity at Re = 100.

```python
from kerf_fem.cfd_navier_stokes import ghia_re100_centreline

ref = ghia_re100_centreline()
# ref["y_over_H"] — 17 y-stations from Table I
# ref["u_over_Ulid"] — corresponding u/U_lid values
# ref["source"] — citation string
```

Use these values to verify a solver result against the published benchmark.

---

### `poiseuille_velocity_profile(y_over_h, U_mean) → float`

Hagen-Poiseuille (fully-developed laminar channel) velocity profile:
```
u(y) = (3/2) U_mean (1 − (2y/h)²)
```
Reference: Schlichting, *Boundary-Layer Theory*, §5.

---

### `poiseuille_pressure_drop(mu, U_mean, L, h) → float`

Hagen-Poiseuille pressure drop for a 2-D channel:
```
Δp = 12 μ U_mean L / h²
```

---

## Analytic oracle citations

| Validation problem | Reference |
|---|---|
| Lid-driven cavity Re=100 centreline u-velocity | Ghia U., Ghia K.N., Shin C.T., *J. Comput. Phys.* **48** (1982) 387–411, Table I |
| Hagen-Poiseuille u(y), dp/dx | Schlichting H., *Boundary-Layer Theory* (7th ed.), §5 |
| Chorin projection method | Chorin A.J., *Math. Comp.* **22** (1968) 745–762 |

---

## Limitations

- **Laminar only** — no RANS, LES, k-ε, or Spalart-Allmaras model.
- 2-D only; no 3-D Taylor-Görtler vortices.
- Structured Cartesian grid only; solid bodies must be axis-aligned rectangles.
- False-transient marching; expect O(10⁴–10⁵) steps for cavity Re = 100 on a 41 × 41 grid.
- At Re ≫ 100 convergence slows significantly and the laminar steady-state may not be physically realised (bifurcation).
