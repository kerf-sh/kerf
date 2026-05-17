# ACI 318-19 Reinforced Concrete Design

Pure-Python ACI 318-19 reinforced concrete (RC) design tools. No OCC dependency.
All tools are stateless. Units: US customary — inches, psi, kips, kip·in, psf.

Authoritative standards:
- **ACI 318-19** — *Building Code Requirements for Structural Concrete*.
  All section and equation references below are to ACI 318-19.
- **ACI 318R-19** — *Commentary on Building Code Requirements for Structural
  Concrete* — basis for Whitney stress block and Branson Ie.

---

## When to use

Use these tools when the conversation involves: reinforced concrete, ACI 318,
beam flexure, beam shear, rebar, steel reinforcement, Whitney stress block,
tension-controlled, compression-controlled, phi factor, singly reinforced, doubly
reinforced, T-beam, effective flange width, RC column, P-M interaction, axial
load, development length, lap splice, bar spacing, one-way slab, slab thickness,
temperature steel, immediate deflection, Branson effective moment of inertia,
crack control, Gergely-Lutz, stirrups, tied column, spiral column, concrete.

---

## Tools

### `rc_beam_flexure`

ACI 318-19 rectangular beam flexural strength — Whitney stress block.

```
a  = As·fy / (0.85·f'c·b)           [§22.2.2, §22.3.2]
c  = a / β1                          [§22.2.2.4.3]
φMn = φ·As·fy·(d − a/2)
φ  = 0.90 (tension-controlled, εt ≥ 0.005)   [§21.2.2]
φ  = 0.65–0.90 (transition zone)
φ  = 0.65 (compression-controlled, εt ≤ εy)
```

**Input:** `b` (in), `d` (in), `As` (in²), `fc_psi`, `fy_psi`; optional
`As_prime` (compression steel in²), `d_prime` (in).

**Returns:** `a`, `c`, `epsilon_t`, `phi`, `Mn_kipin`, `phi_Mn_kipin`,
`zone` (tension/transition/compression), `rho` vs ACI limits, warnings.

**Standards alignment:** §22.2.2 (Whitney stress block); §22.2.2.4.3 (β1 as
function of f'c); §21.2.2 (φ factors); §9.3.3 (minimum As ≥ 3√f'c·bw·d/fy and
≥ 200·bw·d/fy); §9.3.3.1 (maximum As via εt ≥ 0.004 for net tension).

---

### `rc_beam_required_As`

Required tension steel area for a beam given factored moment Mu.

Iterates on `rc_beam_flexure` to find As such that φMn ≥ Mu.

**Input:** `b`, `d` (in), `Mu_kipin`, `fc_psi`, `fy_psi`.

**Returns:** `As_req_in2`, `phi_Mn_at_As_req`, `As_min_in2`, warnings.

**Standards alignment:** ACI §9.3.3 (As_min); φ per §21.2.2.

---

### `rc_beam_shear`

ACI 318-19 **§22.5** one-way beam shear capacity and stirrup sizing.

```
Vc = [8λ(ρw)^(1/3)√f'c + Nu/(6Ag)] · bw · d    [Eq. 22.5.5.1a, Table 22.5.5.1]
Vs = Av·fy·d/s
Vn = Vc + Vs ≥ Vu/φ   (φ = 0.75)
```

**Input:** `b_w`, `d` (in), `fc_psi`, `fy_psi`, `Vu_kip`, `Av_in2`
(stirrup area both legs), `s_in` (stirrup spacing); optional `rho_w`, `Nu_kip`.

**Returns:** `Vc_kip`, `Vs_kip`, `s_req_in`, `s_max_in`, `adequate`, warnings.

**Standards alignment:** §22.5.5.1 (Vc with ρw term, Table 22.5.5.1 Method 1);
§22.5.8 (Vs = Av·fy·d/s); §9.6.3.3 (maximum stirrup spacing d/2 or 600 mm when
Vs ≤ 4√f'c·bw·d; halved when Vs > that threshold); §26.5.3 (minimum stirrup
area Av_min = 0.75√f'c·bw·s/fy but ≥ 50·bw·s/fy).

---

### `rc_tbeam_flange`

ACI 318-19 **§6.3.2** effective overhanging flange width for T-beams.

Effective overhang each side ≤ min(8hf, sw/2, ln/8).

**Input:** `bw`, `hf`, `span_in`, `spacing_in` (all in inches); optional
`side` (`"both"` default or `"one"` for L-beam).

**Returns:** `be_overhang_in` (each side), `be_total_in`, governing limit, warnings.

**Standards alignment:** §6.3.2.1 (isolated T-beam flanges ≥ 4·bw); §6.3.2.2
(flanges of T/L beams per the three limits above).

---

### `rc_column_axial`

ACI 318-19 **§22.4.2** short tied or spiral column maximum axial load.

```
Tied:   φPn,max = 0.80·φ·[0.85·f'c·(Ag−Ast) + fy·Ast]   [§22.4.2.1]
Spiral: φPn,max = 0.85·φ·[0.85·f'c·(Ag−Ast) + fy·Ast]
φ = 0.65 (tied), 0.75 (spiral)                            [§21.2.2]
```

**Input:** `b`, `h` (in), `Ast` (in², total longitudinal steel), `fc_psi`, `fy_psi`;
optional `column_type` (`"tied"` default or `"spiral"`).

**Returns:** `Pn_kip`, `phi_Pn_kip`, `rho_g`, ACI steel limits, warnings.

**Standards alignment:** §22.4.2 (concentrically loaded columns); §10.6.1.1
(ρg limits: 1–8%); §22.4.2.1 (tied factor 0.80); §22.4.2.2 (spiral factor 0.85).

---

### `rc_column_pm_interaction`

ACI 318-19 uniaxial P-M interaction diagram for a rectangular column.

Generates n_points along the balanced → pure tension axis by scanning eccentricity
from e = 0 (axial) to e → ∞ (pure bending).

**Input:** `b`, `h`, `d`, `d_prime`, `As_top`, `As_bot` (in²), `fc_psi`, `fy_psi`;
optional `column_type`, `n_points` (default 20).

**Returns:** list of n_points `{phi_Pn_kip, phi_Mn_kipin}` pairs.

**Standards alignment:** Whitney stress block §22.2.2; φ factor transitions per
§21.2.2; balanced point at εt = εy = fy/Es (Es = 29 000 ksi per §20.2.2.2).

---

### `rc_development_length`

ACI 318-19 **§25.4.2** tension development length for deformed bars.

```
ld/db = (3/40)·(fy/λ√f'c)·(ψt·ψe·ψs·ψg)/(cb+Ktr)/db
```
where (cb+Ktr)/db ≤ 2.5.

**Input:** `db_in` (bar diameter), `fc_psi`, `fy_psi`; optional `coating`
(`"uncoated"` or `"epoxy"`), `position` (`"top"` or `"other"`), `cover_in`,
`spacing_in`, `cb_in`, `Ktr`.

**Returns:** `ld_in`, `ld_db_ratio`, modification factors, warnings.

**Standards alignment:** §25.4.2.4 (simplified) or §25.4.2.3 (detailed);
Table 25.4.2.4 (ψt top-bar = 1.3; ψe epoxy = 1.5; ψs size ≤ 0.19 in → 0.8);
minimum ld ≥ 12 in per §25.4.2.1.

---

### `rc_slab_one_way`

ACI 318-19 **§7.3.1** one-way slab minimum thickness and required steel.

h_min from Table 7.3.1.1 (e.g. simply supported: ℓ/20; one-end-continuous: ℓ/24;
both-ends-continuous: ℓ/28; cantilever: ℓ/10). Multiplied by fy correction
(0.4 + fy/100 000) when fy ≠ 60 000 psi.

**Input:** `span_in`, `fc_psi`, `fy_psi`, `wu_psf`; optional `condition`,
`b_in` (default 12 in).

**Returns:** `h_min_in`, `d_eff_in`, `As_req_in2`, `As_temp_in2`, warnings.

**Standards alignment:** §7.3.1 (h_min); §24.4.3.2 (temperature steel As_temp =
0.0018·Ag when fy ≤ 60 ksi; §24.4.3.4 reduced to 0.0014 for fy > 60 ksi).

---

### `rc_immediate_deflection`

ACI 318-19 **§24.2.3** immediate deflection using Branson effective Ie.

```
Ie = (Mcr/Ma)³·Ig + [1−(Mcr/Ma)³]·Icr  ≤ Ig     [Eq. 24.2.3.5a]
Mcr = fr·Ig/yt  where fr = 7.5λ√f'c (psi)        [§19.2.3.1]
```

**Input:** `b`, `h`, `d`, `As` (in²), `fc_psi`, `fy_psi`, `Ma_kipin`
(service moment), `span_in`; optional `load_condition`.

**Returns:** `Ig`, `Icr`, `Mcr`, `Ie`, `delta_in`, `L_over_delta`, warnings
(flags if L/Δ < L/240).

**Standards alignment:** §24.2.3 (immediate deflection); Eq. 24.2.3.5a (Branson);
§19.2.3.1 (fr = 7.5λ√f'c); §24.2.2 (L/240 live, L/480 total for non-sensitive).

---

### `rc_crack_control`

ACI 318-19 **§24.3** crack-control bar spacing check (Gergely-Lutz z-factor).

```
s ≤ 15·(40 000/fs) − 2.5·cc      [Eq. 24.3.2.1]
but not more than: 12·(40 000/fs)
```

**Input:** `b`, `h`, `d`, `As`, `fc_psi`, `fy_psi`, `n_bars`, `Ms_kipin`;
optional `cover_in` (default 1.5 in).

**Returns:** `fs_psi` (service steel stress), `s_max_in`, `s_actual_in`,
`z_factor`, `spacing_ok`, warnings (z > 175 kip/in).

**Standards alignment:** §24.3.2 (crack control for Class C exposure); Commentary
R24.3 (Gergely-Lutz z retained for legacy comparison; §24.3.2 spacing formula is
the code-mandated check since ACI 318-99).

---

## Example workflow

```
1. rc_beam_required_As  b:14  d:22  Mu_kipin:1800  fc_psi:4000  fy_psi:60000
   → As_req_in2: 1.82  (ACI §9.3.3 As_min: 0.91 in²)

2. rc_beam_flexure  b:14  d:22  As:1.82  fc_psi:4000  fy_psi:60000
   → a:3.19 in  c:3.75 in  epsilon_t:0.0153  phi:0.90
   → phi_Mn_kipin: 1863  zone:"tension-controlled"
   (Eq. 22.5 Whitney block; εt=0.0153 >> 0.005 → φ=0.90 per §21.2.2)

3. rc_beam_shear  b_w:14  d:22  fc_psi:4000  fy_psi:60000
                  Vu_kip:48  Av_in2:0.44  s_in:8
   → Vc_kip:22.8  Vs_kip:36.3  Vn_kip:59.1  adequate:true
   (φVn = 0.75×59.1 = 44.3 kip < Vu — check spacing per §9.6.3.3)

4. rc_development_length  db_in:0.75  fc_psi:4000  fy_psi:60000
                           position:"other"  coating:"uncoated"
   → ld_in: 28.1  ld_db_ratio: 37.4  (§25.4.2.3)
```
