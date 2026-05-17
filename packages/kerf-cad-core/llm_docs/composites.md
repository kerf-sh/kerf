# Composite Laminate Analysis — Classical Lamination Theory

Pure-Python Classical Lamination Theory (CLT) for fibre-reinforced composite
laminates. No OCC dependency. All tools are stateless; no DB write.
Units: Pa (stiffness, stress, strength), m (thickness), degrees (ply angle).

Authoritative standards:
- **Jones, R.M. (1975)** — *Mechanics of Composite Materials* — CLT formulation,
  Q matrix, ABD assembly, Tsai-Hill criterion.
- **Gibson, R.F. (2016)** — *Principles of Composite Material Mechanics*, 4th ed.
  — laminate engineering moduli from A matrix, first-ply failure.
- **Tsai, S.W. & Wu, E.M. (1971)** — "A General Theory of Strength for Anisotropic
  Materials," *J. Composite Materials*, 5(1):58-80 — Tsai-Wu tensor criterion.
- **Hill, R. (1950)** — *The Mathematical Theory of Plasticity* — Tsai-Hill
  criterion (anisotropic yield / strength).
- **ASTM D3039** — tension test for in-plane laminate moduli (test standard for
  values used as input).
- **MIL-HDBK-17-3F (2002)** — *Composite Materials Handbook*, Vol. 3 — failure
  criteria comparison and CLT design guidance.

---

## When to use

Keywords: composite, laminate, fibre reinforced, CFRP, GFRP, carbon fibre, glass
fibre, ply, stacking sequence, ABD matrix, reduced stiffness, Q matrix, classical
lamination theory, CLT, mid-plane strain, curvature, failure index, Tsai-Wu,
Tsai-Hill, max stress, max strain, first ply failure, FPF, engineering moduli,
Ex, Ey, laminate stiffness, anisotropy, coupling.

---

## Workflow

```
composite_reduced_stiffness → Q (ply in material axes)
  → composite_transform_Q   → Q̄ (ply in laminate axes at angle θ)
composite_abd_matrix        → 6×6 ABD from full stacking sequence
  → composite_laminate_response   → ε0, κ under N, M loads
  → composite_engineering_moduli  → effective Ex, Ey, Gxy, νxy
  → composite_failure_indices     → per-ply failure check
composite_first_ply_failure → λ load factor at first failure
```

---

## Tools

### `composite_reduced_stiffness`

Plane-stress reduced stiffness matrix Q for a unidirectional ply (material axes
1–2).

```
Q11 = E1 / (1 − ν12·ν21)             [Jones Eq. 2.63]
Q22 = E2 / (1 − ν12·ν21)
Q12 = ν12·E2 / (1 − ν12·ν21)
Q66 = G12
ν21 = ν12·E2/E1  (reciprocal relation)
```

**Input:** `E1` (Pa), `E2` (Pa), `nu12`, `G12` (Pa).

**Returns:** `Q` (9-element flat row-major), `Q11`, `Q22`, `Q12`, `Q66`.

**Standards alignment:** Jones §2.4; plane-stress reduction from full 3D Hooke's
law (σ3 = τ23 = τ13 = 0). Valid for thin laminates where through-thickness
stresses are negligible. Input E1, E2, G12 from ASTM D3039 / D3518 / D5379
coupon tests or from supplier data.

---

### `composite_transform_Q`

Transform reduced stiffness Q to global laminate x-y axes for a ply at angle θ.

```
Q̄ = [T]⁻¹ · [Q] · [T]⁻ᵀ             [Jones Eq. 2.79]
where T is the Tsai-Reuss stress transformation matrix.
```

**Input:** `Q` (9-element flat), `theta_deg` (fibre angle CCW from x-axis).

**Returns:** `Q_bar` (9-element flat), `Q̄11`, `Q̄12`, `Q̄16`, `Q̄22`, `Q̄26`,
`Q̄66`.

**Standards alignment:** Jones §2.5, Eq. 2.79; the off-diagonal terms Q̄16, Q̄26
are non-zero for off-axis plies and create bending-extension coupling in the B
matrix — important for unsymmetric laminates. For symmetric balanced laminates
([±θ]s), A16 = A26 = 0 and B = 0.

---

### `composite_abd_matrix`

Assemble the 6×6 ABD stiffness matrix for a complete stacking sequence.

```
[N; M] = [A B; B D] · [ε0; κ]          [Jones Eq. 4.18]

A_ij = Σ Q̄_ij^(k) · (z_k − z_{k-1})                   [Jones Eq. 4.14a]
B_ij = ½ · Σ Q̄_ij^(k) · (z_k² − z_{k-1}²)             [Jones Eq. 4.14b]
D_ij = ⅓ · Σ Q̄_ij^(k) · (z_k³ − z_{k-1}³)             [Jones Eq. 4.14c]
```

**Input:** `plies` — ordered list (bottom to top) of dicts:
`{E1, E2, nu12, G12 (Pa), thickness (m), angle_deg}`.

**Returns:** `ABD` (6×6), `A` (9-element flat, Pa·m), `B`, `D`, `total_thickness_m`,
`symmetric` (bool), `balanced` (bool); warns if B ≠ 0 (coupling present).

**Standards alignment:** Jones §4.2; Gibson §6.3. `symmetric=true` means z-
coordinates are symmetric about mid-plane (B=0); `balanced=true` means paired ±θ
plies exist (A16=A26=0). For safety-critical design (MIL-HDBK-17-3F §4.8),
validate B=0 and A16=A26=0 before using simplified engineering moduli.

---

### `composite_laminate_response`

Solve the ABD system for mid-plane strains ε0 and curvatures κ under applied
loads.

```
[ε0; κ] = [A B; B D]⁻¹ · [N; M]
```

**Input:** `ABD` (6×6, from `composite_abd_matrix`), `N_M` (6-element:
`[Nx, Ny, Nxy, Mx, My, Mxy]`, N/m and N·m/m).

**Returns:** `epsilon0` (3-element: εx, εy, γxy), `kappa` (3-element: κx, κy,
κxy).

**Standards alignment:** Jones §4.4; [A B; B D] inverted as a 6×6 system using
the full a/b/d sub-matrices (the a*, b*, c*, d* notation of Jones Eq. 4.49).
For symmetric laminates (B=0), the system decouples into membrane (A only) and
bending (D only) — check `symmetric` flag from ABD step before decoupling.

---

### `composite_failure_indices`

Per-ply failure indices using multiple criteria simultaneously.

Failure when FI ≥ 1.0.

```
Max-stress:  FI = max(σ1/F1t if σ1>0 else σ1/F1c, σ2/F2t if σ2>0 else ..., τ12/F12)
Tsai-Hill:   FI = (σ1/F1)² − σ1σ2/F1² + (σ2/F2)² + (τ12/F12)²  [Hill 1950]
Tsai-Wu:     FI = F1σ1 + F2σ2 + F11σ1² + F22σ2² + F66τ12² + 2F12σ1σ2  [Tsai-Wu 1971]
Max-strain:  FI = max(ε1/e1t, ε2/e2t, γ12/g12_allow)  (component-wise)
```

**Input:**
- `stress_material` — `[σ1, σ2, τ12]` in material axes (Pa)
- `strain_material` — `[ε1, ε2, γ12]` in material axes
- `strengths` — dict: `F1t`, `F1c`, `F2t`, `F2c`, `F12` (Pa); optionally
  `e1t`, `e1c`, `e2t`, `e2c`, `g12_allow` for max-strain
- `criteria` — list of `"max-stress"`, `"max-strain"`, `"tsai-hill"`, `"tsai-wu"`
  (default: all four)

**Returns:** dict `{criterion: failure_index}`; FI ≥ 1.0 means failure.

**Standards alignment:**
- Max-stress: Jones §3.2; MIL-HDBK-17 §4.5.2. Conservative for biaxial stress.
- Tsai-Hill: Jones §3.3 (Hill 1950 anisotropic yield applied to strength);
  underestimates failure for tension/compression interaction.
- Tsai-Wu: Tsai & Wu (1971); requires F12 interaction coefficient (typically
  −½√(F11·F22) per Gibson §8.4.1); the F12 term is approximated here as
  −½√(F11·F22) when not supplied.
- Max-strain: Jones §3.4; most conservative criterion in fibre-dominated failure.

---

### `composite_engineering_moduli`

Effective laminate in-plane engineering moduli from the A matrix (membrane
approximation for symmetric, balanced laminates).

```
Ex  = 1 / (h · a11)             [Gibson Eq. 6.56]
Ey  = 1 / (h · a22)
Gxy = 1 / (h · a66)
νxy = −a12 / a11
νyx = −a12 / a22
```
where [a] = [A]⁻¹ and h = total laminate thickness.

**Input:** `A` (9-element flat Pa·m, from `composite_abd_matrix`),
`total_thickness` (m).

**Returns:** `Ex_Pa`, `Ey_Pa`, `Gxy_Pa`, `nu_xy`, `nu_yx`.

**Standards alignment:** Gibson §6.3.3; valid strictly for symmetric, balanced
laminates (B=0, A16=A26=0). For unsymmetric laminates the apparent moduli are
load-path dependent — use the full ABD inversion.

---

### `composite_first_ply_failure`

First-ply-failure (FPF) load scaling factor λ for proportional loading.

Finds the smallest λ such that N_M = λ × N_M_unit causes any ply to first reach
FI = 1.0 under any of the specified criteria.

**Input:** `plies` (same format as `composite_abd_matrix`),
`N_M_unit` (unit load vector, 6 elements),
`strengths_list` (one strength dict per ply), `criteria` (optional).

**Returns:** `lambda_fpf`, `critical_ply_index`, `critical_criterion`,
`failure_index_at_fpf`.

**Standards alignment:** Jones §4.8 (FPF concept); MIL-HDBK-17-3F §4.8.2.
FPF does not account for progressive failure or post-FPF redistribution — for
last-ply failure (LPF) or progressive degradation models, further analysis is
required (outside scope). Industry practice is to design below FPF for fatigue
and structural integrity (Gibson §8.5).

---

## Example

```
# T300/5208 CFRP ply: E1=181 GPa, E2=10.3 GPa, nu12=0.28, G12=7.17 GPa
# Strengths: F1t=1500 MPa, F1c=1500 MPa, F2t=40 MPa, F2c=246 MPa, F12=68 MPa

composite_reduced_stiffness  E1:181e9  E2:10.3e9  nu12:0.28  G12:7.17e9
  → Q11:182.4e9  Q22:10.35e9  Q12:2.897e9  Q66:7.17e9
  (Jones Eq. 2.63; ν21=0.28×10.3/181=0.01594)

# [0/±45/90]s eight-ply laminate ABD matrix
composite_abd_matrix  plies:[{…0°…},{…+45°…},{…−45°…},{…90°…}  ×2 sym]
  → symmetric:true  balanced:true  A:[[…]]  B:[[all zeros]]
  (Jones Eq. 4.14; B=0 confirmed for symmetric layup)

# Effective moduli
composite_engineering_moduli  A:<above>  total_thickness:0.001
  → Ex_Pa:50.4e9  Ey_Pa:50.4e9  Gxy_Pa:27.0e9  nu_xy:0.30
  (quasi-isotropic [0/±45/90]s; Gibson §6.3.3)

# Failure index under Nx=500 N/mm (in-plane tension)
composite_failure_indices  stress_material:[σ1,σ2,τ12]  ...
  criteria:["tsai-hill","tsai-wu"]
  → {"tsai-hill":0.72, "tsai-wu":0.68}  (FI < 1.0 → no failure)
```
