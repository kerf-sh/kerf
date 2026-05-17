# kerf-fem · modal.py

Natural frequency analysis and Euler buckling for Euler-Bernoulli beams, plus a closed-form first-mode formula for thin rectangular plates. Pure Python — no numpy/scipy dependency. All routines return `{"ok": False, "reason": "..."}` on bad input and never raise.

---

## When to use

- Find the first N natural frequencies (Hz) of a cantilever, simply-supported, or fixed-fixed beam
- Check whether a beam's lowest natural frequency is safely above an excitation frequency
- Compute the Euler buckling load for columns with standard end conditions (K-factor)
- Estimate the fundamental plate frequency for a simply-supported thin rectangular plate (Blevins)

---

## Public entrypoints

### `beam_natural_frequencies(E, I, rho, A, L, supports, *, n_elem=12, n_modes=3) → dict`

Generalised eigenproblem K φ = ω² M φ for an Euler-Bernoulli beam.

Uses a 2-node Hermite cubic element with the consistent mass matrix (Hughes, *The Finite Element Method*, eq. 8.1.13):
```
M_e = ρ A h / 420 × [[156,  22h,   54,  -13h],
                      [ 22h, 4h²,  13h,  -3h²],
                      [  54, 13h,  156,  -22h],
                      [-13h,-3h², -22h,   4h²]]
```
Eigenproblem solved by symmetric Jacobi iteration on the Cholesky-reduced system.

**Analytic oracle — cantilever:**
```
ω_1 = (β₁ L)² / L² · √(EI / (ρ A))    β₁ L = 1.87510407
```
The solver returns f₁ = ω₁ / (2π) within 0.1 % at n_elem = 12 (Blevins, *Formulas for Natural Frequency and Mode Shape*, Table 8-1).

**Parameters:**
- `E` — Young's modulus [Pa]
- `I` — second moment of area [m⁴]
- `rho` — density [kg/m³]
- `A` — cross-section area [m²]
- `L` — beam length [m]
- `supports` — list of `{"type": "fixed" | "pinned", "x": float}` (x in metres)
- `n_elem` — number of elements (≥ 2; 12 gives < 0.1 % error for first mode)
- `n_modes` — number of lowest modes to return

**Returns:**
```json
{
  "ok": true,
  "frequencies_hz": [10.2, 63.9, 179.1],
  "omega": [64.1, 401.5, 1125.0],
  "mode_shapes": [[...], [...], [...]]
}
```

```python
from kerf_fem.modal import beam_natural_frequencies

# Steel cantilever: W100×19, L = 2 m
r = beam_natural_frequencies(
    E=210e9, I=4.77e-6, rho=7850, A=2.48e-3,
    L=2.0,
    supports=[{"type": "fixed", "x": 0.0}],
    n_modes=3,
)
print(r["frequencies_hz"])   # first mode ≈ analytic β₁L = 1.87510407
```

---

### `euler_buckling_load(E, I, L, K_factor=1.0) → dict`

Euler critical compressive load for a slender column.

```
P_cr = π² E I / (K L)²
```

Standard end-condition K-factors:

| End conditions | K |
|---|---|
| Pinned–pinned (theoretical) | 1.0 |
| Fixed–free (cantilever) | 2.0 |
| Fixed–pinned | 0.7 |
| Fixed–fixed | 0.5 |

Returns `{ok, P_cr}` in Newtons.

```python
from kerf_fem.modal import euler_buckling_load

# Pinned-pinned steel column 3 m, I = 4.77e-6 m⁴
r = euler_buckling_load(E=210e9, I=4.77e-6, L=3.0, K_factor=1.0)
print(r["P_cr"])   # ≈ 1.10 MN
```

---

### `plate_first_mode_simply_supported(E, nu, rho, h, a, b) → dict`

Closed-form fundamental natural frequency of a thin isotropic plate simply-supported on all four edges (Blevins, *Formulas for Natural Frequency and Mode Shape*, Table 11-1):

```
f₁ = (π/2) √(D / (ρ h)) · (1/a² + 1/b²)
D  = E h³ / (12 (1 − ν²))
```

**Parameters:**
- `E` — Young's modulus [Pa]
- `nu` — Poisson's ratio
- `rho` — density [kg/m³]
- `h` — plate thickness [m]
- `a`, `b` — plate dimensions [m]

Returns `{ok, f1_hz, D}`.

---

## Analytic oracle citations

| Problem | Reference | Check |
|---|---|---|
| Cantilever β₁L = 1.87510407 | Blevins, *Formulas for Natural Frequency and Mode Shape*, Table 8-1 | < 0.1 % at n_elem = 12 |
| Simply-supported beam ω₁ = π²√(EI/ρAL⁴) | Blevins Table 8-1 | exact |
| Euler buckling P_cr = π²EI/(KL)² | Timoshenko, *Theory of Elastic Stability*, §2 | analytic |
| Plate f₁ | Blevins Table 11-1 | closed-form |

---

## Limitations

- 1-D beam only; no 2-D or 3-D solid eigenproblem.
- Consistent mass matrix (Hermite cubic) gives slightly better frequency estimates than lumped mass for the same n_elem.
- Shear deformation (Timoshenko beam) is not modelled; use n_elem ≥ 12 and verify the result is not sensitive to further mesh refinement.
- Buckling check is linearised Euler buckling — no imperfection, residual stress, or post-buckling.
