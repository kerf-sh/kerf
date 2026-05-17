# Beam and Cross-Section Analysis

Pure-Python beam bending, cross-section properties, buckling, and stress tools.
No OCC dependency. All tools are stateless. Units: SI (N, m, Pa).

Authoritative standards:
- **Roark's Formulas for Stress and Strain**, 8th ed. (Young & Budynas) — beam
  tables, shear-flow formula, cross-section formulas.
- **Hibbeler, Mechanics of Materials**, 10th ed., §§6 (shear), 7 (combined),
  9 (Mohr's circle), 11 (deflection), 14 (energy methods).
- **AISC 360-22 §E3** — Johnson column formula and KL/r ≤ 200 slenderness limit.
- **AISC Steel Construction Manual, 16th ed.** — W-shape Zx/Zy plastic-modulus
  expressions used for the I-section tool.

---

## When to use

Use these tools when the user asks about beam deflection, bending moment, shear
force, cross-section properties (moment of inertia, section modulus), column
buckling, combined axial and bending stress, principal stresses, shear flow,
or Mohr's circle.

Keywords: beam, deflection, bending moment, shear force, cantilever, simply
supported, fixed-fixed, section modulus, moment of inertia, I-beam, channel,
hollow tube, column buckling, Euler, Johnson, combined stress, Mohr circle,
principal stress, shear flow, VQ/It.

---

## Tools

### `beam_section_properties`

Cross-section properties for standard structural shapes.

Returns: area A, centroid (cx, cy), Ix/Iy, Sx_top/Sx_bot/Sy (elastic section
moduli), Zx/Zy (plastic moduli), rx/ry (radii of gyration), J (torsion
constant).

**Input:** `shape` (required) — one of: `'rectangle'`, `'circle'`, `'hollow_rect'`,
`'hollow_circ'`, `'I'`, `'channel'`, `'angle'`

Dimensions (all in metres) as needed by shape: `b`, `h`, `d`, `t`, `bf`, `tf`, `tw`

**Standards alignment:**
- Solid rectangle Ix = bh³/12 — Roark Table 3.1 case 1.
- Hollow rectangle Ix = (bh³ − bi·hi³)/12 — Roark Table 3.1 case 3.
- I-section Ix = (bf·d³ − (bf−tw)·hw³)/12; Zx = 2·[bf·tf·(d/2−tf/2) + tw·hw²/8] —
  AISC SCM 16th ed., Part 1 shape properties; aligns with §F2 plastic-moment
  capacity Mp = Fy·Zx.
- Hollow closed-section torsion J via Bredt–Batho: J = 4A_enc²/(Σds/t) — Roark
  Table 10.7.
- Open thin-wall torsion J ≈ (1/3)Σb_i·t_i³ — Roark §10.4.
- Angle section: Zx/Zy are approximate about centroidal geometric axes; principal
  axes differ for unequal legs — a warning is always emitted.

---

### `beam_loads`

Closed-form beam analysis: max deflection, slope, moment, shear, reactions.

**Input:**
- `support` (required) — `'cantilever'` / `'simply_supported'` / `'fixed_fixed'`
- `load_type` (required) — `'point'` / `'udl'` / `'moment'`
- `E` (Pa), `I` (m⁴), `L` (m) — all required
- `P` (N) for point load; `w` (N/m) for udl; `M0` (N·m) for moment
- `a` (m) — point load position from A (optional)

**Returns:** `max_deflection` (m), `slope_end` (rad), `max_moment` (N·m),
`max_shear` (N), `Ra`, `Rb` (N), `EI` (N·m²)

**Standards alignment — Roark Table 8 formulas used:**
| Case | Deflection formula | Source |
|------|--------------------|--------|
| Cantilever, point load P at a | δ = Pa²(3L−a)/(6EI) | Roark Table 8.1 row 1b |
| Cantilever, UDL w | δ = wL⁴/(8EI) | Roark Table 8.1 row 2a |
| SS, point load P at a | δ_max via x_max = √((L²−b²)/3) | Roark Table 8.2 row 1b |
| SS, UDL w | δ = 5wL⁴/(384EI) | Roark Table 8.2 row 2a |
| Fixed-fixed, point load P at a | Ra = Pb²(3a+b)/L³ | Roark Table 8.3 row 1 |
| Fixed-fixed, UDL w | δ = wL⁴/(384EI); M_end = wL²/12 | Roark Table 8.3 row 2a |

---

### `beam_superpose`

Linearly superpose multiple `beam_loads` result dicts (conservative sum of
max_deflection, max_moment, max_shear). Algebraically sums Ra and Rb.

**Input:** `cases` (array of beam_loads result objects, required)

**Returns:** summed `max_deflection`, `max_moment`, `max_shear`, combined `Ra`/`Rb`,
`n_cases`

**Note:** Magnitudes are summed — this is a conservative upper bound for loads
acting in the same direction. For loads with opposite signs, use FEA or decompose
sign explicitly. Principle of superposition applies to linear elastic beams —
Hibbeler §12.1.

---

### `beam_buckling`

Column buckling: Euler critical load and Johnson short-column transition.

P_euler = π²EI/(K·L)².  Governs when KL/r > Cc.  
For KL/r ≤ Cc: P_johnson = A·Fy·[1 − (Fy/(4π²E))·(KL/r)²].

K values: 0.5 fixed-fixed, 0.7 fixed-pin, 1.0 pin-pin (default), 2.0 fixed-free.

**Input:** `L_eff`, `A`, `I`, `E`, `Fy` (all required); `K` (default 1.0)

**Returns:** `r`, `KL_over_r`, `Cc`, `P_euler`, `P_johnson`, `P_cr`, `sigma_cr`,
`mode`, warnings if KL/r > 200 or σ_cr > Fy

**Standards alignment:**
- Euler load: P_e = π²EI/(KL)² — Euler (1744); Hibbeler §13.3.
- Transition slenderness: Cc = π√(2E/Fy) — AISC LRFD Manual 3rd ed. §E2.
- Johnson parabola: P_j = A·Fy[1−(KL/r)²·Fy/(4π²E)] — AISC 360-22 §E3,
  Eq. E3-2 (effective-slenderness form).
- KL/r ≤ 200 recommendation — AISC 360-22 §E2 Commentary.

---

### `beam_combined_stress`

Combined axial + bending stress at extreme fibres.

σ_top = P/A − M/S;  σ_bot = P/A + M/S

**Input:** `P` (N, tension positive), `M` (N·m), `A` (m²), `S` (m³) — all required

**Returns:** `sigma_axial`, `sigma_bending`, `sigma_top`, `sigma_bot`, `sigma_max` (Pa)

**Standards alignment:** σ = P/A ± Mc/I (with S = I/c) — Hibbeler §6.4, Eq. 6-17
and §8.1. Use the smaller of Sx_top and Sx_bot for conservative bending; compare
sigma_max to allowable or factored Fy for code check per AISC §H1-1.

---

### `beam_mohr_circle`

Mohr's circle for 2D plane stress: principal stresses and max shear.

**Input:** `sigma_x`, `sigma_y`, `tau_xy` (Pa) — all required

**Returns:** `sigma_1`, `sigma_2` (Pa), `tau_max` (Pa), `sigma_avg` (Pa), `R` (Pa),
`theta_p_deg`

**Standards alignment:**
- σ_avg = (σx+σy)/2; R = √(((σx−σy)/2)²+τxy²) — Hibbeler §9.3, Eq. 9-5/9-6.
- θp = ½·atan2(2τxy, σx−σy) — Hibbeler §9.3, Eq. 9-4.
- τ_max = R = (σ1−σ2)/2 — Hibbeler §9.4.

---

### `beam_shear_flow`

Shear stress at a section cut: τ = VQ/(I·b).

**Input:** `V` (N), `Q` (m³), `I` (m⁴), `b` (m) — all required

**Returns:** `tau_Pa`

**Standards alignment:** τ = VQ/(Ib) — Hibbeler §7.3, Eq. 7-3; Roark Table 3.2.
Q is the first moment of area of the cut portion about the neutral axis.

---

## Example

```
1. beam_section_properties  shape:"I"  bf:0.150  d:0.300  tf:0.010  tw:0.008
   → A:5.04e-3 m²  Ix:1.214e-4 m⁴  Sx_top:8.09e-4 m³  Zx:9.18e-4 m³

2. beam_loads  support:"simply_supported"  load_type:"udl"
               E:200e9  I:1.214e-4  L:6.0  w:15000
   → max_deflection:0.0124 m  max_moment:67500 N·m  (5wL⁴/384EI)

3. beam_combined_stress  P:50000  M:67500  A:5.04e-3  S:8.09e-4
   → sigma_top:73.5 MPa  sigma_bot:93.1 MPa  (P/A ± M/S)

4. beam_buckling  L_eff:4.0  A:5.04e-3  I:1.214e-4  E:200e9  Fy:250e6  K:1.0
   → P_cr:5.95 MN  mode:"euler"  KL/r:18.6
   Governing: Euler (KL/r=18.6 < Cc=125.7 → actually Johnson governs at this KL/r)
```

---

## Design workflow notes

For a complete AISC 360-22 beam check:
1. `beam_section_properties` → get Ix, Sx, Zx, ry, J.
2. `beam_loads` → get Mu (factored moment demand).
3. Compute φMn = φ·Fy·Zx (§F2); check Mu ≤ φMn.
4. For lateral-torsional buckling check (§F2.2), compute Lp = 1.76·ry·√(E/Fy)
   and Lr. Compare Lb to Lp/Lr to select reduction factor Cb.
5. `beam_shear_flow` → confirm web shear Vu ≤ φVn = 0.6·Fy·Aw (§G2.1).
