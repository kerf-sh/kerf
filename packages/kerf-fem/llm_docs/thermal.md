# kerf-fem · thermal.py

Steady-state heat conduction FEM for 1-D slabs, fin efficiency, and multilayer thermal resistance. Pure Python — no numpy/scipy dependency. All routines return `{"ok": False, "reason": "..."}` on bad input and never raise.

---

## When to use

- Calculate the temperature profile and heat flux through a 1-D slab (wall, PCB substrate, heat spreader) with Dirichlet end-temperatures and optional volumetric heat generation
- Compute fin efficiency η for a straight rectangular fin with an adiabatic tip
- Sum series thermal resistances for a multilayer composite wall

---

## Public entrypoints

### `solve_1d_conduction(k, L, T_left, T_right, *, n_elem=10, q_vol=0.0, area=1.0) → dict`

Steady-state 1-D conduction in a uniform slab.

Governing equation: `d/dx(k A dT/dx) + q_vol A = 0`
BCs: `T(0) = T_left`, `T(L) = T_right`

Closed-form oracle for `q_vol = 0` (Incropera et al., *Fundamentals of Heat and Mass Transfer*, 7th ed., eq. 3.6):
```
T(x) = T_left + (T_right − T_left) · x / L
q    = k (T_left − T_right) / L   [W/m²]
```
The FEM recovers this exactly (no discretisation error for constant k, zero source).

**Parameters:**
- `k` — thermal conductivity [W/(m K)]
- `L` — slab length [m]
- `T_left`, `T_right` — Dirichlet temperatures [K or °C]
- `n_elem` — number of linear elements
- `q_vol` — volumetric heat generation [W/m³] (default 0)
- `area` — cross-section area [m²] (default 1.0)

**Returns:**
```json
{
  "ok": true,
  "T": [300.0, 295.0, 290.0, ...],
  "x": [0.0, 0.1, 0.2, ...],
  "q_flux": [50000.0, ...],
  "Q_total": 50.0
}
```

```python
from kerf_fem.thermal import solve_1d_conduction

# Steel slab k=50 W/(m K), L=0.1 m, T_left=300 K, T_right=250 K
r = solve_1d_conduction(k=50.0, L=0.1, T_left=300.0, T_right=250.0)
print(r["q_flux"][0])   # ≈ 25 000 W/m²  (Fourier law)
print(r["Q_total"])     # q_flux × area
```

---

### `fin_efficiency(k, h, P, A_c, L) → dict`

Efficiency of a straight rectangular fin with adiabatic tip (Incropera eq. 3.91):

```
m = √( h P / (k A_c) )
η = tanh(m L) / (m L)
```

**Parameters:**
- `k` — fin thermal conductivity [W/(m K)]
- `h` — convection coefficient [W/(m² K)]
- `P` — fin perimeter [m]
- `A_c` — fin cross-section area [m²]
- `L` — fin length [m]

**Returns:** `{ok, eta, m, mL}`

```python
from kerf_fem.thermal import fin_efficiency

# Aluminium fin, k=200, h=50, perimeter=0.02 m, A_c=1e-5 m², L=0.03 m
r = fin_efficiency(k=200.0, h=50.0, P=0.02, A_c=1e-5, L=0.03)
print(f"η = {r['eta']:.3f}")   # e.g. 0.985
```

---

### `thermal_resistance_series(layers) → dict`

Total thermal resistance for a series multilayer wall (Incropera eq. 3.21):

```
R_i = Δx_i / (k_i A)
R_total = Σ R_i
```

**Input:** list of `{"k": float, "dx": float, "A": float}` dicts.

**Returns:** `{ok, R_total, R_layers}` in K/W.

```python
from kerf_fem.thermal import thermal_resistance_series

# Two-layer wall: copper + alumina
r = thermal_resistance_series([
    {"k": 390.0, "dx": 0.002, "A": 0.01},   # copper 2 mm
    {"k":  35.0, "dx": 0.005, "A": 0.01},   # alumina 5 mm
])
print(r["R_total"])   # K/W
```

---

## Analytic oracle citations

| Problem | Reference | Check |
|---|---|---|
| Linear conduction T(x) | Incropera et al., *Fundamentals of HMT*, 7th ed., eq. 3.6 | exact at nodes |
| Fin efficiency η = tanh(mL)/(mL) | Incropera eq. 3.91 | closed-form |
| Series resistance R = Δx/(k A) | Incropera eq. 3.21 | exact |

---

## Limitations

- 1-D only; no 2-D or 3-D FEM thermal mesh.
- Linear elements with constant k per element; non-linear k(T) requires element-wise constant approximation and re-solving.
- Transient conduction is not implemented; for time-dependent problems use `kerf_electronics.thermal_board` (2-D Gauss–Seidel) or an external solver.
- Radiation and convection boundary conditions at interior nodes are not supported (Dirichlet ends only).
