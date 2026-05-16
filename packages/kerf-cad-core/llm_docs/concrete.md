# ACI 318-19 Reinforced Concrete Design

Pure-Python ACI 318-19 reinforced concrete (RC) design tools. No OCC dependency.
All tools are stateless. Units: US customary — inches, psi, kips, kip·in, psf.

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

ACI 318-19 rectangular beam flexural strength (Whitney stress block).

**Input:** `b` (in), `d` (in), `As` (in²), `fc_psi`, `fy_psi`; optional
`As_prime` (compression steel in²), `d_prime` (in).

**Returns:** `a`, `c`, `epsilon_t`, `phi`, `Mn_kipin`, `phi_Mn_kipin`,
`zone` (tension/transition/compression), `rho` vs ACI limits, warnings.

---

### `rc_beam_required_As`

Required tension steel area for a beam given factored moment Mu.

**Input:** `b`, `d` (in), `Mu_kipin`, `fc_psi`, `fy_psi`.

**Returns:** `As_req_in2`, `phi_Mn_at_As_req`, `As_min_in2`, warnings.

---

### `rc_beam_shear`

ACI 318-19 §22.5 one-way beam shear capacity and stirrup sizing.

**Input:** `b_w`, `d` (in), `fc_psi`, `fy_psi`, `Vu_kip`, `Av_in2`
(stirrup area both legs), `s_in` (stirrup spacing); optional `rho_w`, `Nu_kip`.

**Returns:** `Vc_kip`, `Vs_kip`, `s_req_in`, `s_max_in`, `adequate`, warnings.

---

### `rc_tbeam_flange`

ACI 318-19 §6.3.2 effective overhanging flange width for T-beams.

**Input:** `bw`, `hf`, `span_in`, `spacing_in` (all in inches); optional
`side` (`"both"` default or `"one"` for L-beam).

**Returns:** `be_overhang_in` (each side), `be_total_in`, governing limit, warnings.

---

### `rc_column_axial`

ACI 318-19 §22.4.2 short tied or spiral column maximum axial load.

**Input:** `b`, `h` (in), `Ast` (in², total longitudinal steel), `fc_psi`, `fy_psi`;
optional `column_type` (`"tied"` default or `"spiral"`).

**Returns:** `Pn_kip`, `phi_Pn_kip`, `rho_g`, ACI steel limits, warnings.

---

### `rc_column_pm_interaction`

ACI 318-19 uniaxial P-M interaction diagram for a rectangular column.

**Input:** `b`, `h`, `d`, `d_prime`, `As_top`, `As_bot` (in²), `fc_psi`, `fy_psi`;
optional `column_type`, `n_points` (default 20).

**Returns:** list of `n_points` `{phi_Pn_kip, phi_Mn_kipin}` pairs.

---

### `rc_development_length`

ACI 318-19 §25.4.2 tension development length for deformed bars.

**Input:** `db_in` (bar diameter), `fc_psi`, `fy_psi`; optional `coating`
(`"uncoated"` or `"epoxy"`), `position` (`"top"` or `"other"`), `cover_in`,
`spacing_in`, `cb_in`, `Ktr`.

**Returns:** `ld_in`, `ld_db_ratio`, modification factors, warnings.

---

### `rc_slab_one_way`

ACI 318-19 §7.3.1 one-way slab minimum thickness and required steel.

**Input:** `span_in`, `fc_psi`, `fy_psi`, `wu_psf`; optional `condition`
(`"simply-supported"` default, `"one-end-continuous"`, `"both-ends-continuous"`,
`"cantilever"`), `b_in` (default 12 in).

**Returns:** `h_min_in`, `d_eff_in`, `As_req_in2`, `As_temp_in2`, warnings.

---

### `rc_immediate_deflection`

ACI 318-19 §24.2.3 immediate deflection using Branson effective Ie.

**Input:** `b`, `h`, `d`, `As` (in²), `fc_psi`, `fy_psi`, `Ma_kipin`
(service moment), `span_in`; optional `load_condition`
(`"midspan"` default or `"cantilever"`).

**Returns:** `Ig`, `Icr`, `Mcr`, `Ie`, `delta_in`, `L_over_delta`, warnings
(flags if L/Δ < L/240).

---

### `rc_crack_control`

ACI 318-19 §24.3 crack-control bar spacing check (Gergely-Lutz z).

**Input:** `b`, `h`, `d`, `As`, `fc_psi`, `fy_psi`, `n_bars`, `Ms_kipin`;
optional `cover_in` (default 1.5 in).

**Returns:** `fs_psi` (service steel stress), `s_max_in`, `s_actual_in`,
`z_factor`, `spacing_ok`, warnings (z > 175 kip/in).

---

## Example workflow

```
1. rc_beam_required_As  b:14  d:22  Mu_kipin:1800  fc_psi:4000  fy_psi:60000
   → As_req_in2: 1.82

2. rc_beam_flexure  b:14  d:22  As:1.82  fc_psi:4000  fy_psi:60000
   → phi_Mn_kipin: 1863, zone:"tension-controlled", phi:0.90

3. rc_beam_shear  b_w:14  d:22  fc_psi:4000  fy_psi:60000
                  Vu_kip:48  Av_in2:0.44  s_in:8
   → Vc_kip:22.8, Vs_kip:36.3, adequate:true
```
