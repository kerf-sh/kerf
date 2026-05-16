# NDS Timber Design

Pure-Python NDS 2018 timber (wood) structural design tools. No OCC dependency.
All tools are stateless. Units: inches (in), psi, kips, lb.

---

## When to use

Use these tools when the conversation involves: timber design, wood framing,
sawn lumber, glulam, NDS, allowable stress design, ASD, bending stress, shear
stress, compression, tension, deflection limit, L/360, L/240, column stability,
Ylinen equation, column stability factor CP, FcE, Euler buckling, combined
bending and axial, bearing perpendicular to grain, fastener, bolt, lag screw,
lateral yield, withdrawal, nail, Douglas Fir, Southern Pine, Hem-Fir, SPF,
select structural, No. 1, No. 2, load duration, wet service, temperature factor,
size factor.

---

## Tools

### `timber_reference_values`

Look up NDS 2018 tabulated reference design values for a species and grade.

**Input:** `species` (`douglas_fir_larch`|`southern_pine`|`hem_fir`|`spruce_pine_fir`),
`grade` (`select_structural`|`no_1`|`no_2`).

**Returns:** `Fb_psi`, `Fv_psi`, `Fc_psi`, `Fc_perp_psi`, `Ft_psi`, `E_psi`,
`Emin_psi` (all reference/unfactored values).

---

### `timber_adjusted_Fb`

Adjusted allowable bending stress Fb' = Fb × CD × CM × Ct × CL × CF × Cfu × Ci × Cr.

**Input:** `Fb_ref` (psi, required); optional factors `CD`, `CM`, `Ct`, `CL`,
`CF`, `Cfu`, `Ci`, `Cr` (all default 1.0).

**Returns:** `Fb_prime_psi` and full factor breakdown.

---

### `timber_adjusted_Fc`

Adjusted allowable compression-parallel stress Fc' = Fc × CD × CM × Ct × CF × Ci × CP.

**Input:** `Fc_ref` (psi, required); optional `CD`, `CM`, `Ct`, `CF`, `Ci`,
`CP` (all default 1.0).

**Returns:** `Fc_prime_psi` and factor breakdown.

---

### `timber_sawn_section`

Dressed (S4S) dimensions and section properties for standard sawn lumber.

**Input:** `b_nom_in`, `d_nom_in` (nominal integers, e.g. 2×10).

**Returns:** `b_actual_in`, `d_actual_in`, `A_in2`, `S_in3`, `I_in4`.

---

### `timber_glulam_section`

Section properties for glulam using actual dimensions.

**Input:** `b_in`, `d_in` (actual, must be > 0).

**Returns:** `A_in2`, `S_in3`, `I_in4`.

---

### `timber_check_bending`

Bending check: fb ≤ Fb' (NDS §3.3).

**Input:** `fb_psi` (actual bending stress), `Fb_prime_psi` (adjusted Fb').

**Returns:** `utilization` (fb/Fb'), `pass_fail`, warnings.

---

### `timber_check_shear`

Horizontal shear check: fv ≤ Fv' (NDS §3.4).

**Input:** `fv_psi`, `Fv_prime_psi`.

**Returns:** `utilization`, `pass_fail`, warnings.

---

### `timber_check_deflection`

Deflection limit checks for live load and total load (NDS Table 3.5).

**Input:** `delta_L_in`, `delta_TL_in`, `span_in`; optional `limit_L`
(default 360), `limit_TL` (default 240).

**Returns:** `util_L`, `util_TL`, `live_ok`, `total_ok`, warnings.

---

### `timber_column_stability`

Column stability factor CP and critical buckling stress FcE (Ylinen equation,
NDS §3.7.1).

**Input:** `le_d` (slenderness ratio, effective length / least dimension),
`Fc_star_psi` (Fc × all factors except CP), `E_prime_min_psi` (adjusted Emin).

**Returns:** `CP`, `FcE_psi`, `alpha`, `le_d`, warnings (slenderness > 50).

---

### `timber_check_column`

Column compression check: fc ≤ Fc' (NDS §3.7).

**Input:** `fc_psi`, `Fc_prime_psi`.

**Returns:** `utilization`, `pass_fail`, warnings.

---

### `timber_check_combined`

Combined bending + axial compression interaction (NDS §3.9.2 Eq. 3.9-3).

(fc/Fc*)² + fb / (Fb' × (1 − fc/FcE)) ≤ 1.0

**Input:** `fb_psi`, `Fb_prime_psi`, `fc_psi`, `Fc_star_psi`, `FcE_psi`.

**Returns:** `interaction_ratio`, `pass_fail`, warnings (fc ≥ FcE).

---

### `timber_check_bearing`

Bearing perpendicular to grain: fc_perp ≤ Fc_perp' (NDS §3.10).

**Input:** `fc_perp_psi`, `Fc_perp_prime_psi`.

**Returns:** `utilization`, `pass_fail`, warnings.

---

### `timber_lateral_yield_bolt`

Single-fastener lateral design value Z (lb) via NDS yield-limit equations
(all six yield modes Im, Is, II, IIIm, IIIs, IV).

**Input:** `D_in` (diameter), `tm_in`, `ts_in` (bearing lengths), `Fyb_psi`
(fastener yield), `Fe_m_psi`, `Fe_s_psi` (dowel bearing strengths);
optional `theta_deg` (load-to-grain angle, default 0).

**Returns:** `Z_lb`, `governing_mode`, all mode values.

---

### `timber_withdrawal_nail`

Nail withdrawal capacity W = 1380 × G^(5/2) × D^(3/2) per NDS §12.2.

**Input:** `D_in` (nail shank diameter), `L_pen_in` (penetration), `G`
(specific gravity; DF-L 0.50, SYP 0.55, Hem-Fir 0.43, SPF 0.42).

**Returns:** `W_per_in_lb` (per inch of penetration), `W_total_lb`.

---

## Example workflow

```
1. timber_reference_values  species:"douglas_fir_larch"  grade:"no_2"
   → Fb_psi:900, Fv_psi:180, Fc_psi:1350, E_psi:1600000

2. timber_sawn_section  b_nom_in:2  d_nom_in:10
   → b_actual:1.5, d_actual:9.25, A:13.88 in², S:21.39 in³

3. timber_adjusted_Fb  Fb_ref:900  CD:1.15  CF:1.1  Cr:1.15
   → Fb_prime_psi: 1313

4. timber_check_bending  fb_psi:980  Fb_prime_psi:1313
   → utilization:0.746, pass_fail:"pass"
```
