# kerf-fem · linear_static.py

Analytic-exact 1-D structural FEM solvers for axial bars, Euler-Bernoulli beams, and constrained thermal-stress bars. Pure Python — no numpy/scipy dependency. All routines return `{"ok": False, "reason": "..."}` on bad input and never raise.

---

## When to use

- Calculate tip deflection and stress of an axially-loaded bar fixed at one end (Roark Table 8.1 axial member)
- Find deflections and reactions of simply-supported, cantilever, or fixed-fixed beams under concentrated or distributed loads (Roark Table 8.1; Timoshenko & Goodier)
- Calculate thermal stress in a fully-constrained bar subject to a uniform temperature change

The Hermite cubic beam element is exact (no discretisation error) for the polynomial loading cases listed above because the Euler-Bernoulli homogeneous solution is at most cubic between concentrated loads.

---

## Public entrypoints

### `solve_axial_bar(E, A, L, P, *, n_elem=1) → dict`

Uniaxial prismatic bar, fixed at x = 0, tip force P at x = L.

Closed-form oracle (Timoshenko):
```
u(L) = P L / (A E)
σ    = P / A
```

Returns `{ok, displacement, stress, reaction, nodal_disp}`.

```python
from kerf_fem.linear_static import solve_axial_bar

r = solve_axial_bar(E=210e9, A=1e-4, L=1.0, P=10e3)
print(r["displacement"])   # ≈ 4.76e-4 m
print(r["stress"])         # 1e8 Pa
```

---

### `solve_beam(E, I, L, supports, loads, *, n_elem=10) → dict`

Euler-Bernoulli beam with arbitrary simple/pinned/fixed supports and concentrated/UDL loads.

**supports** — list of `{"type": "fixed" | "pinned", "x": float}` (x in metres, measured from left end).

**loads** — list of `{"type": "point" | "udl", "x": float, "P": float}` or `{"type": "udl", "w": float}`.

Returns `{ok, displacements, rotations, shear_force, bending_moment, reactions}`.

```python
from kerf_fem.linear_static import solve_beam

# Cantilever: tip load P = 1 kN, length 2 m
r = solve_beam(
    E=200e9, I=1e-5, L=2.0,
    supports=[{"type": "fixed", "x": 0.0}],
    loads=[{"type": "point", "x": 2.0, "P": -1e3}],
    n_elem=10,
)
print(r["displacements"][-1])  # ≈ −PL³/(3EI) = −1.33e-4 m
```

---

### `solve_thermal_stress_bar(E, alpha, dT, *, area=1.0) → dict`

Fully-constrained prismatic bar under uniform temperature rise ΔT.

Closed-form oracle (Incropera; Timoshenko & Goodier §13):
```
σ = −E α ΔT   (compressive for positive ΔT)
ε_free = α ΔT  (blocked)
```

Returns `{ok, stress, strain_free, reaction_force, note}`.

```python
from kerf_fem.linear_static import solve_thermal_stress_bar

r = solve_thermal_stress_bar(E=70e9, alpha=23e-6, dT=100.0)
print(r["stress"])   # −1.61e8 Pa (compressive)
```

---

## Analytic oracle citations

| Problem | Reference | Oracle value |
|---|---|---|
| Cantilever tip load δ = PL³/3EI | Roark 9th ed., Table 8.1 case 1 | exact at tip |
| Simply-supported midspan load δ = PL³/48EI | Roark Table 8.1 case 7 | exact at midspan |
| Axial bar u = PL/AE | Timoshenko & Goodier, *Theory of Elasticity*, 3rd ed., §1 | exact |
| Thermal stress σ = −EαΔT | Incropera et al., *Fundamentals of Heat and Mass Transfer*, 7th ed. | exact |
| Fixed-fixed beam UDL | Roark Table 8.1 case 15 | exact at midspan and ends |

---

## Limitations

- 1-D formulations only; no 2-D or 3-D FEM mesh.
- Beam solver handles Hermite cubic elements — correct for concentrated loads; for higher-order distributed loads increase `n_elem`.
- Large-displacement / geometric nonlinearity: use `kerf_fem.nonlinear`.
- Dynamic problems: use `kerf_fem.modal` (natural frequencies) or `kerf_fem.explicit` (time-domain).
