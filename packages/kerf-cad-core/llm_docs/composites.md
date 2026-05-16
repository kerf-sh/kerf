# Composite Laminate Analysis — LLM Reference

Classical Lamination Theory (CLT) for fibre-reinforced composite laminates per Jones and
Gibson. No OCC dependency. All tools are stateless; no DB write.
Units: Pa (stiffness, stress, strength), m (thickness), degrees (ply angle).

---

## When to use

Keywords: composite, laminate, fibre reinforced, CFRP, GFRP, carbon fibre, glass fibre,
ply, stacking sequence, ABD matrix, reduced stiffness, Q matrix, classical lamination theory,
CLT, mid-plane strain, curvature, failure index, Tsai-Wu, Tsai-Hill, max stress, max strain,
first ply failure, FPF, engineering moduli, Ex, Ey, laminate stiffness, anisotropy, coupling.

---

## Workflow

```
composite_reduced_stiffness → Q (ply in material axes)
  → composite_transform_Q   → Q̄ (ply in laminate axes at angle θ)
composite_abd_matrix        → 6×6 ABD from full stacking sequence
  → composite_laminate_response    → ε0, κ under N, M loads
  → composite_engineering_moduli  → effective Ex, Ey, Gxy, νxy
  → composite_failure_indices     → per-ply failure check
composite_first_ply_failure → λ load factor at first failure
```

---

## Tools

### `composite_reduced_stiffness`

Plane-stress reduced stiffness matrix Q for a unidirectional ply.

**Input:** `E1` (fibre-direction modulus, Pa), `E2` (transverse modulus, Pa), `nu12` (major Poisson ratio), `G12` (in-plane shear modulus, Pa).

**Returns:** `Q` as 9-element flat row-major list (Voigt notation 11, 22, 12), plus individual components `Q11`, `Q22`, `Q12`, `Q66`.

---

### `composite_transform_Q`

Transform reduced stiffness Q to global laminate x-y axes for a ply at angle θ.

**Input:** `Q` (9-element flat list from `composite_reduced_stiffness`), `theta_deg` (fibre angle CCW from x-axis, degrees).

**Returns:** `Q_bar` (9-element flat list), individual components `Q̄11`, `Q̄12`, `Q̄16`, `Q̄22`, `Q̄26`, `Q̄66`.

---

### `composite_abd_matrix`

Assemble the 6×6 ABD stiffness matrix for a complete stacking sequence.

Relates [N; M] = [A B; B D] [ε0; κ].

**Input:** `plies` — ordered list (bottom to top) of dicts, each with:
- `E1`, `E2` (Pa), `nu12`, `G12` (Pa)
- `thickness` (m)
- `angle_deg` (fibre angle CCW, degrees)

**Returns:** `ABD` (6×6 matrix), `A` (9-element flat), `B`, `D`, `total_thickness_m`, `symmetric` flag, `balanced` flag; warns if coupling (B ≠ 0).

---

### `composite_laminate_response`

Solve the ABD system for mid-plane strains ε0 and curvatures κ under applied loads.

**Input:** `ABD` (6×6 matrix from `composite_abd_matrix`), `N_M` (6-element load vector `[Nx, Ny, Nxy, Mx, My, Mxy]` in N/m and N·m/m).

**Returns:** `epsilon0` (3-element: εx, εy, γxy), `kappa` (3-element: κx, κy, κxy).

---

### `composite_failure_indices`

Per-ply failure indices using multiple criteria simultaneously.

**Input:**
- `stress_material` — `[σ1, σ2, τ12]` in material axes (Pa)
- `strain_material` — `[ε1, ε2, γ12]` in material axes
- `strengths` — dict with `F1t`, `F1c`, `F2t`, `F2c`, `F12` (Pa); optionally `e1t`, `e1c`, `e2t`, `e2c`, `g12_allow` for max-strain
- `criteria` — list of `"max-stress"`, `"max-strain"`, `"tsai-hill"`, `"tsai-wu"` (default: all four)

**Returns:** dict of `{criterion: failure_index}`; F.I. ≥ 1.0 means failure.

---

### `composite_engineering_moduli`

Effective laminate in-plane engineering moduli from the A matrix (membrane approximation).

**Input:** `A` (9-element flat extensional stiffness, Pa·m, from `composite_abd_matrix`), `total_thickness` (m).

**Returns:** `Ex_Pa`, `Ey_Pa`, `Gxy_Pa`, `nu_xy`, `nu_yx`.

---

### `composite_first_ply_failure`

First-ply-failure (FPF) load scaling factor λ for proportional loading.

Finds smallest λ such that N_M = λ × N_M_unit causes any ply to fail.

**Input:** `plies` (same format as `composite_abd_matrix`), `N_M_unit` (unit load vector, 6 elements), `strengths_list` (one strength dict per ply), `criteria` (optional).

**Returns:** `lambda_fpf` (load factor at first failure), `critical_ply_index`, `critical_criterion`, `failure_index_at_fpf`.

---

## Example

```
# T300/5208 CFRP ply: E1=181 GPa, E2=10.3 GPa, nu12=0.28, G12=7.17 GPa
composite_reduced_stiffness  E1:181e9  E2:10.3e9  nu12:0.28  G12:7.17e9
  → Q11:182.4e9  Q22:10.35e9  Q12:2.897e9  Q66:7.17e9

# [0/±45/90]s laminate ABD matrix
composite_abd_matrix  plies:[
  {E1:181e9, E2:10.3e9, nu12:0.28, G12:7.17e9, thickness:0.000125, angle_deg:0},
  {E1:181e9, E2:10.3e9, nu12:0.28, G12:7.17e9, thickness:0.000125, angle_deg:45},
  ... (symmetric)]
  → symmetric:true  balanced:true  A:[[...]]

# Effective moduli
composite_engineering_moduli  A:<above>  total_thickness:0.001
  → Ex_Pa:50.4e9  Ey_Pa:50.4e9  Gxy_Pa:27.0e9  nu_xy:0.30
```
