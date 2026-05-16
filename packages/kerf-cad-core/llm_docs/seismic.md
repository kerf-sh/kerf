# Seismic Equivalent Lateral Force (ASCE 7)

Pure-Python ASCE/SEI 7-22 Equivalent Lateral Force procedure for building seismic
design. No OCC dependency. All tools are stateless. Units: g, metres, kN, kN·m.

---

## When to use

Use these tools when the conversation involves: seismic design, earthquake loads,
ASCE 7, ELF procedure, site class, soil classification, spectral acceleration,
response spectrum, design spectrum, base shear, seismic weight, lateral force
distribution, storey shear, overturning moment, storey drift, P-delta, stability,
SDOF displacement, seismic response coefficient, Cs, SDS, SD1, Ss, S1, Fa, Fv,
structural period, approximate period, risk category, importance factor, response
modification factor R.

---

## Tools

### `seismic_site_coefficients`

Compute ASCE 7 site-modified spectral accelerations from mapped MCE values.

**Input:** `Ss` (g), `S1` (g), `site_class` (`A`|`B`|`C`|`D`|`E`).

**Returns:** `Fa`, `Fv`, `SMS`, `SM1`, `SDS`, `SD1`, warnings.
Site class E with Ss > 0.75g or S1 > 0.30g → error (requires site-specific analysis).

---

### `seismic_design_spectrum`

Evaluate ASCE 7 design response spectral acceleration Sa(T) at a given period.

**Input:** `T` (s), `SDS` (g), `SD1` (g), optional `TL` (s, default 6.0).

**Returns:** `Sa_g`, `region` (rising/constant_a/constant_v/long_period), `T0`,
`Ts`, `TL`, warnings.

---

### `seismic_approximate_period`

Approximate fundamental period Ta = Ct · hn^x per ASCE 7 Table 12.8-2.

**Input:** `hn` (m, height above base), optional `structure_type`
(`steel_moment`|`concrete_moment`|`eccentrically_braced`|`other`, default `other`).

**Returns:** `Ta_s`, `Ct`, `x`, `hn_m`, `structure_type`, warnings.

---

### `seismic_response_coefficient`

Seismic response coefficient Cs per ASCE 7 §12.8.1.1.

**Input:** `SDS`, `SD1`, `T` (s), `R`, `Ie`; optional `TL` (default 6.0),
`S1` (for floor when S1 ≥ 0.6g).

**Returns:** `Cs`, `Cs_basic`, `Cs_cap`, `Cs_floor`, `cap_governs`,
`floor_governs`, `R_over_Ie`, warnings.

---

### `seismic_base_shear`

Seismic base shear V = Cs × W (ASCE 7 §12.8.1).

**Input:** `Cs`, `W` (kN, effective seismic weight).

**Returns:** `V_kN`, `Cs`, `W_kN`, warnings.

---

### `seismic_vertical_distribution`

Distribute base shear V to storey levels as Fx (ASCE 7 §12.8.3).

**Input:** `V` (kN), `W_stories` (list kN, bottom to top), `h_stories`
(list m, bottom to top), `T` (s).

**Returns:** `Fx_kN` (list), `Cvx` (list), `k` exponent, warnings.
k = 1.0 for T ≤ 0.5 s, 2.0 for T ≥ 2.5 s, interpolated between.

---

### `seismic_story_shear_overturning`

Storey shear Vx and overturning moment Mx at each level from Fx distribution.

**Input:** `Fx` (list kN, bottom to top), `h_stories` (list m, bottom to top).

**Returns:** `Vx_kN` (list), `Mx_kNm` (list), warnings.

---

### `seismic_drift_stability`

Inelastic storey drift Δx, drift ratio, and P-delta stability coefficient θ
(ASCE 7 §12.8.6–12.8.7).

**Input:** `delta_xe` (list m, elastic displacements), `Cd`, `Ie`, `Px`
(list kN, gravity above each storey), `Vx` (list kN), `hsx` (list m);
optional `drift_limit_ratio` (default 0.02).

**Returns:** `Delta_x_m`, `drift_ratio`, `drift_ok`, `theta`, `theta_ok`,
warnings (θ > 0.10, drift exceedance).

---

### `seismic_sdof_displacement`

Elastic SDOF spectral displacement: Sd = Sa · g · T² / (4π²).

**Input:** `Sa_g` (spectral acceleration in g), `T` (s).

**Returns:** `Sd_m`, `Sd_mm`, `Sa_g`, `T_s`, warnings.

---

## Example workflow

```
1. seismic_site_coefficients  Ss:1.5  S1:0.6  site_class:"D"
   → SDS:1.0, SD1:0.52, Fa:1.0, Fv:1.3

2. seismic_approximate_period  hn:24.0  structure_type:"concrete_moment"
   → Ta_s:0.82

3. seismic_response_coefficient  SDS:1.0  SD1:0.52  T:0.82  R:5  Ie:1.0
   → Cs:0.127

4. seismic_base_shear  Cs:0.127  W:8000
   → V_kN: 1016

5. seismic_vertical_distribution  V:1016  W_stories:[2000,2000,2000,2000]
                                   h_stories:[3,6,9,12]  T:0.82
   → Fx_kN: [78, 175, 302, 461]

6. seismic_story_shear_overturning  Fx:[78,175,302,461]  h_stories:[3,6,9,12]
   → Vx_kN: [1016,938,763,461]  Mx_kNm: [8469,6051,3162,...]
```
