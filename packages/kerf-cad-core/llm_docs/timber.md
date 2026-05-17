# NDS Timber Design

Pure-Python NDS 2018 timber (wood) structural design tools. No OCC dependency.
All tools are stateless. Units: inches (in), psi, kips, lb.

Authoritative standards:
- **NDS 2018** — *National Design Specification for Wood Construction*, American
  Wood Council. All clause references are to NDS 2018.
- **NDS Supplement 2018** — tabulated reference design values (Tables 4A, 4B,
  4C, 5A).
- **NDS Commentary 2018** — Ylinen column equation derivation (§C3.7.1).

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
`Emin_psi` (all tabulated reference/unfactored values).

**Standards alignment:** NDS Supplement 2018 Tables 4A/4B (visually graded lumber)
and 5A (machine stress-rated); values represent the 5th-percentile strength under
10-year load duration at dry-service conditions.

---

### `timber_adjusted_Fb`

Adjusted allowable bending stress Fb' = Fb × CD × CM × Ct × CL × CF × Cfu × Ci × Cr.

**Input:** `Fb_ref` (psi, required); optional factors `CD`, `CM`, `Ct`, `CL`,
`CF`, `Cfu`, `Ci`, `Cr` (all default 1.0).

**Returns:** `Fb_prime_psi` and full factor breakdown.

**Standards alignment (NDS §4.3 / §2.3):**

| Factor | NDS Clause | Description |
|--------|------------|-------------|
| CD | §2.3.2 | Load duration (1.25 two-month, 1.15 two-month, 1.0 ten-year, 0.9 permanent) |
| CM | §4.3.4 | Wet service (0.85 for Fb, sawn lumber when MC > 19%) |
| Ct | §2.3.4 | Temperature (1.0 ≤ 100°F, 0.8 at 125°F) |
| CL | §3.3.3 | Beam stability (1.0 for fully braced top flange) |
| CF | §4.3.6 | Size (bending: 1.5/d^(1/9) for sawn lumber d > 12 in) |
| Cfu | §4.3.7 | Flat-use (applies when depth < width in flat-use orientation) |
| Ci | §4.3.8 | Incising treatment factor |
| Cr | §4.3.9 | Repetitive member (1.15 for joists ≤ 4 in wide, ≥3 members ≤24 in apart) |

---

### `timber_adjusted_Fc`

Adjusted allowable compression-parallel stress Fc' = Fc × CD × CM × Ct × CF × Ci × CP.

**Input:** `Fc_ref` (psi, required); optional `CD`, `CM`, `Ct`, `CF`, `Ci`,
`CP` (all default 1.0).

**Returns:** `Fc_prime_psi` and factor breakdown.

**Standards alignment:** NDS §4.3 / §3.7; CP from `timber_column_stability`;
CF for compression: NDS Supplement Table 4A footnote (size factor not always
applied to Fc — see species supplement).

---

### `timber_sawn_section`

Dressed (S4S) dimensions and section properties for standard sawn lumber.

**Input:** `b_nom_in`, `d_nom_in` (nominal integers, e.g. 2×10).

**Returns:** `b_actual_in`, `d_actual_in`, `A_in2`, `S_in3`, `I_in4`.

**Standards alignment:** Dressed sizes per NDS Supplement Table 1B (e.g. 2×10
nominal = 1.5 × 9.25 in actual). Section properties computed from actual
dressed dimensions.

---

### `timber_glulam_section`

Section properties for glulam using actual dimensions.

**Input:** `b_in`, `d_in` (actual, must be > 0).

**Returns:** `A_in2`, `S_in3`, `I_in4`.

**Standards alignment:** Glulam is sized on actual dimensions (no dressing
deduction). Reference values from ANSI/AWC NDS Supplement Table 5A for structural
glued laminated softwood lumber.

---

### `timber_check_bending`

Bending check: fb ≤ Fb' (NDS **§3.3**).

**Input:** `fb_psi` (actual bending stress), `Fb_prime_psi` (adjusted Fb').

**Returns:** `utilization` (fb/Fb'), `pass_fail`, warnings.

**Standards alignment:** NDS §3.3.1 bending design requirement fb ≤ Fb'.
Actual fb = M/S (M in lb·in, S in in³ from dressed section).

---

### `timber_check_shear`

Horizontal shear check: fv ≤ Fv' (NDS **§3.4**).

**Input:** `fv_psi`, `Fv_prime_psi`.

**Returns:** `utilization`, `pass_fail`, warnings.

**Standards alignment:** NDS §3.4.2; actual fv = 1.5V/(bwd) for rectangular
sections (NDS Eq. 3.4-2). Notch effects at supports (NDS §3.4.3) are outside
scope; check manually when notches are present.

---

### `timber_check_deflection`

Deflection limit checks for live load and total load (NDS **Table 3.5**).

**Input:** `delta_L_in`, `delta_TL_in`, `span_in`; optional `limit_L`
(default 360), `limit_TL` (default 240).

**Returns:** `util_L`, `util_TL`, `live_ok`, `total_ok`, warnings.

**Standards alignment:** NDS Table 3.5.1 deflection limits: L/360 live load;
L/240 total load for floor joists. Roofs may use L/240 live / L/180 total —
override with `limit_L` and `limit_TL`.

---

### `timber_column_stability`

Column stability factor CP and critical buckling stress FcE — Ylinen equation
(NDS **§3.7.1**).

```
FcE = 0.822·E'min / (le/d)²
α   = FcE / Fc*
CP  = [1 + α/c] / (2c)  −  √{[(1+α/c)/(2c)]² − α/c}
where c = 0.8 (sawn lumber), 0.9 (glulam), 1.0 (mechanically laminated)
```

**Input:** `le_d` (slenderness ratio, effective length / least dimension),
`Fc_star_psi` (Fc × all factors except CP), `E_prime_min_psi` (adjusted Emin).

**Returns:** `CP`, `FcE_psi`, `alpha`, `le_d`, warnings (slenderness > 50).

**Standards alignment:** NDS §3.7.1.5, Eq. 3.7-1 (CP); §3.7.1.4 (FcE);
§3.7.1.3 (le/d ≤ 50 limit); Commentary §C3.7.1 (Ylinen curve derivation).
E'min = Emin × adjustment factors per §2.3.6 (CM, Ct, Ci, CT).

---

### `timber_check_column`

Column compression check: fc ≤ Fc' (NDS **§3.7**).

**Input:** `fc_psi`, `Fc_prime_psi`.

**Returns:** `utilization`, `pass_fail`, warnings.

**Standards alignment:** NDS §3.7.1; Fc' = Fc × CD × CM × Ct × CF × Ci × CP.

---

### `timber_check_combined`

Combined bending + axial compression interaction (NDS **§3.9.2 Eq. 3.9-3**).

```
(fc/Fc*)²  +  fb1 / (Fb1'·(1 − fc/FcE1))  ≤  1.0
```

**Input:** `fb_psi`, `Fb_prime_psi`, `fc_psi`, `Fc_star_psi`, `FcE_psi`.

**Returns:** `interaction_ratio`, `pass_fail`, warnings (fc ≥ FcE).

**Standards alignment:** NDS §3.9.2, Eq. 3.9-3; the amplification term
1/(1−fc/FcE) accounts for the P-Δ moment amplification in the Ylinen stability
model. The equation is unconservative if fc ≥ FcE (column has buckled) — a warning
is always emitted in that case.

---

### `timber_check_bearing`

Bearing perpendicular to grain: fc_perp ≤ Fc_perp' (NDS **§3.10**).

**Input:** `fc_perp_psi`, `Fc_perp_prime_psi`.

**Returns:** `utilization`, `pass_fail`, warnings.

**Standards alignment:** NDS §3.10.2; Fc_perp is not adjusted by CD (load
duration does not apply to bearing, NDS §2.3.2 exception); Cb (bearing area
factor) per §3.10.4 may increase Fc_perp for bearings < 6 in long — apply Cb
manually when relevant.

---

### `timber_lateral_yield_bolt`

Single-fastener lateral design value Z (lb) via NDS **yield-limit equations**
(all six yield modes Im, Is, II, IIIm, IIIs, IV).

```
Mode Im:  Z = Dl·Fe·tm·l_m      (bearing, main member only)
Mode IIIm: Z = ...               (combined bending + bearing in main member)
Mode IV:  Z = (D²/Rd)·√(2Fe·Fyb/3)  (fastener bending controls)
```
Z governs as the minimum across all modes.

**Input:** `D_in` (diameter), `tm_in`, `ts_in` (bearing lengths), `Fyb_psi`
(fastener yield), `Fe_m_psi`, `Fe_s_psi` (dowel bearing strengths);
optional `theta_deg` (load-to-grain angle, default 0).

**Returns:** `Z_lb`, `governing_mode`, all mode values.

**Standards alignment:** NDS §12 yield-limit model; Appendix I dowel equations
(Eqs. I-1 through I-6); Fe at angle θ via Hankinson formula (NDS §11.3.2);
CD, CM, Ct, Cg (group action), Ceg (end grain), Cdi (diaphragm) adjustments
applied separately by the caller.

---

### `timber_withdrawal_nail`

Nail withdrawal capacity W = 1380 × G^(5/2) × D^(3/2) per NDS **§12.2**.

**Input:** `D_in` (nail shank diameter), `L_pen_in` (penetration), `G`
(specific gravity; DF-L 0.50, SYP 0.55, Hem-Fir 0.43, SPF 0.42).

**Returns:** `W_per_in_lb` (per inch of penetration), `W_total_lb`.

**Standards alignment:** NDS §12.2 (wire nail withdrawal, NDS Eq. 12.2-1);
minimum penetration for design value: ≥ 10D into main member (§12.1.7.3).
Multiply W by CD, CM, Ct, etc. per §10.3 to obtain W' (adjusted design value).

---

## Example workflow

```
1. timber_reference_values  species:"douglas_fir_larch"  grade:"no_2"
   → Fb_psi:900  Fv_psi:180  Fc_psi:1350  E_psi:1,600,000  Emin_psi:580,000
   (NDS Supplement Table 4A, Douglas Fir-Larch No. 2, 2×10 size)

2. timber_sawn_section  b_nom_in:2  d_nom_in:10
   → b_actual:1.5  d_actual:9.25  A:13.88 in²  S:21.39 in³  I:98.93 in⁴

3. timber_adjusted_Fb  Fb_ref:900  CD:1.15  CF:1.1  Cr:1.15
   → Fb_prime_psi:1313
   (CD=1.15 for roof snow per §2.3.2; CF=1.1 per NDS Supp. Table 4A footnote for 2×10;
    Cr=1.15 repetitive member per §4.3.9)

4. timber_check_bending  fb_psi:980  Fb_prime_psi:1313
   → utilization:0.746  pass_fail:"pass"  (NDS §3.3)

5. timber_column_stability  le_d:18.5  Fc_star_psi:1350  E_prime_min_psi:580000
   → FcE_psi:1362  CP:0.838  (NDS §3.7.1 Ylinen, c=0.8 sawn lumber)

6. timber_check_combined  fb_psi:200  Fb_prime_psi:1313  fc_psi:900
                           Fc_star_psi:1350  FcE_psi:1362
   → interaction_ratio:0.71  pass_fail:"pass"  (NDS Eq. 3.9-3)
```
