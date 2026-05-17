# Seismic Equivalent Lateral Force (ASCE 7-22)

Pure-Python ASCE/SEI 7-22 Equivalent Lateral Force procedure for building seismic
design. No OCC dependency. All tools are stateless. Units: g, metres, kN, kN·m.

Authoritative standards:
- **ASCE/SEI 7-22** — *Minimum Design Loads and Associated Criteria for Buildings
  and Other Structures*, Chapter 11 (seismic general provisions) and Chapter 12
  (seismic design requirements). All section references below are to ASCE 7-22.
- **FEMA P-749** — *Earthquake-Resistant Design Concepts* — ELF procedure background.
- **ASCE 41-23** — seismic evaluation and retrofit (for reference; not implemented).

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

Compute ASCE 7-22 site-modified spectral accelerations from mapped MCE values.

```
SMS = Fa × Ss                           [§11.4.4, Eq. 11.4-1]
SM1 = Fv × S1                           [§11.4.4, Eq. 11.4-2]
SDS = (2/3) × SMS                       [§11.4.5, Eq. 11.4-3]
SD1 = (2/3) × SM1                       [§11.4.5, Eq. 11.4-4]
```

**Input:** `Ss` (g), `S1` (g), `site_class` (`A`|`B`|`C`|`D`|`E`).

**Returns:** `Fa`, `Fv`, `SMS`, `SM1`, `SDS`, `SD1`, warnings.

**Standards alignment:** Fa from §11.4.4 / Table 11.4-1; Fv from §11.4.4 /
Table 11.4-2. Site class E with Ss > 0.75 g or S1 > 0.30 g requires site-specific
ground motion procedure per §11.4.8 — returns error in that case, consistent with
§11.4.7 (site-specific exceptions).

---

### `seismic_design_spectrum`

Evaluate ASCE 7-22 design response spectral acceleration Sa(T) at a given period.

```
For 0 ≤ T ≤ T0:  Sa = SDS·(0.4 + 0.6T/T0)      [§11.4.6, Eq. 11.4-5]
For T0 < T ≤ Ts: Sa = SDS                        [§11.4.6, constant accelera.]
For Ts < T ≤ TL: Sa = SD1/T                      [§11.4.6, Eq. 11.4-7]
For T > TL:      Sa = SD1·TL/T²                  [§11.4.6, Eq. 11.4-8]
T0 = 0.2·SD1/SDS;  Ts = SD1/SDS
```

**Input:** `T` (s), `SDS` (g), `SD1` (g), optional `TL` (s, default 6.0).

**Returns:** `Sa_g`, `region`, `T0`, `Ts`, `TL`, warnings.

**Standards alignment:** §11.4.6; TL (long-period transition) from USGS hazard
maps (§11.4.6, default 6 s is conservative for most US sites).

---

### `seismic_approximate_period`

Approximate fundamental period Ta = Ct · hn^x per ASCE 7-22 **Table 12.8-2**.

```
Steel moment frame:          Ct=0.028, x=0.8
Concrete moment frame:       Ct=0.016, x=0.9
Eccentrically braced frame:  Ct=0.03,  x=0.75
Other:                       Ct=0.02,  x=0.75
```

**Input:** `hn` (m, height above base), optional `structure_type`
(`steel_moment`|`concrete_moment`|`eccentrically_braced`|`other`, default `other`).

**Returns:** `Ta_s`, `Ct`, `x`, `hn_m`, `structure_type`, warnings.

**Standards alignment:** §12.8.2.1, Table 12.8-2. The computed period T shall
not exceed Cu × Ta per §12.8.2 (Cu depends on SD1; prevents unconservatively
long period when a modal analysis is not performed).

---

### `seismic_response_coefficient`

Seismic response coefficient Cs per ASCE 7-22 **§12.8.1.1**.

```
Cs = SDS / (R/Ie)                       [Eq. 12.8-2, basic]
Cs ≤ SD1 / [T·(R/Ie)]    when T ≤ TL    [Eq. 12.8-3, upper cap]
Cs ≤ SD1·TL / [T²·(R/Ie)] when T > TL  [Eq. 12.8-4]
Cs ≥ 0.044·SDS·Ie ≥ 0.01               [Eq. 12.8-5, floor]
Cs ≥ 0.5·S1/(R/Ie)       when S1 ≥ 0.6g [Eq. 12.8-6, near-fault floor]
```

**Input:** `SDS`, `SD1`, `T` (s), `R`, `Ie`; optional `TL` (default 6.0),
`S1` (for near-fault floor when S1 ≥ 0.6 g).

**Returns:** `Cs`, `Cs_basic`, `Cs_cap`, `Cs_floor`, `cap_governs`,
`floor_governs`, `R_over_Ie`, warnings.

**Standards alignment:** §12.8.1.1, Eq. 12.8-2 through 12.8-6. R values from
Table 12.2-1 (e.g. Special Steel Moment Frame R=8; Ordinary Special Moment
Frame R=3.5). Ie from Table 1.5-2 (Risk Category II → Ie=1.0; Risk Category IV
→ Ie=1.5).

---

### `seismic_base_shear`

Seismic base shear V = Cs × W (ASCE 7-22 **§12.8.1**).

**Input:** `Cs`, `W` (kN, effective seismic weight per §12.7.2).

**Returns:** `V_kN`, `Cs`, `W_kN`, warnings.

**Standards alignment:** §12.8.1, Eq. 12.8-1. W includes: 100% dead load +
applicable snow load per §12.7.2; storage 25% of floor live; partition 10 psf
minimum per §4.3.2 when applicable.

---

### `seismic_vertical_distribution`

Distribute base shear V to storey levels as Fx (ASCE 7-22 **§12.8.3**).

```
Cvx = wx·hx^k / Σ(wi·hi^k)            [Eq. 12.8-12]
Fx  = Cvx · V                          [Eq. 12.8-11]
k = 1.0 for T ≤ 0.5 s; k = 2.0 for T ≥ 2.5 s; linear interpolation between.
```

**Input:** `V` (kN), `W_stories` (list kN, bottom to top), `h_stories`
(list m, bottom to top), `T` (s).

**Returns:** `Fx_kN` (list), `Cvx` (list), `k` exponent, warnings.

**Standards alignment:** §12.8.3, Eq. 12.8-11 and 12.8-12. For buildings with
T ≤ 0.5 s (k=1), distribution is triangular. For longer periods (k=2), larger
portion goes to upper storeys, capturing higher-mode effects.

---

### `seismic_story_shear_overturning`

Storey shear Vx and overturning moment Mx at each level from Fx distribution.

```
Vx = Σ Fi  (from top down to storey x)   [§12.8.4]
Mx = Σ Fi·(hi − hx)                      [§12.8.5]
```

**Input:** `Fx` (list kN, bottom to top), `h_stories` (list m, bottom to top).

**Returns:** `Vx_kN` (list), `Mx_kNm` (list), warnings.

**Standards alignment:** §12.8.4 (storey shear); §12.8.5 (overturning moment);
overturning reduction factor τ (0.8–1.0 for buildings > 10 storeys) per
§12.8.5 commentary is not applied automatically.

---

### `seismic_drift_stability`

Inelastic storey drift Δx, drift ratio, and P-delta stability coefficient θ
(ASCE 7-22 **§12.8.6–12.8.7**).

```
Δx = Cd·δxe / Ie                        [§12.8.6, Eq. 12.8-15]
Drift ratio = Δx / hsx ≤ Δa             [§12.12.1, Table 12.12-1]
θ = Px·Δx / (Vx·hsx·Cd)                [§12.8.7, Eq. 12.8-16]
```

**Input:** `delta_xe` (list m, elastic displacements), `Cd`, `Ie`, `Px`
(list kN, gravity above each storey), `Vx` (list kN), `hsx` (list m);
optional `drift_limit_ratio` (default 0.02).

**Returns:** `Delta_x_m`, `drift_ratio`, `drift_ok`, `theta`, `theta_ok`,
warnings (θ > 0.10, drift exceedance).

**Standards alignment:** §12.8.6 (inelastic drift); §12.12.1 and Table 12.12-1
(allowable drifts: Risk Category II office 0.02h; healthcare 0.015h; etc.).
§12.8.7 (P-delta): θ ≤ 0.10 no correction needed; 0.10 < θ ≤ θ_max amplification
1/(1−θ); θ_max = 0.5/(β·Cd) but ≤ 0.25 — check manually.

---

### `seismic_sdof_displacement`

Elastic SDOF spectral displacement: Sd = Sa · g · T² / (4π²).

**Input:** `Sa_g` (spectral acceleration in g), `T` (s).

**Returns:** `Sd_m`, `Sd_mm`, `Sa_g`, `T_s`, warnings.

**Standards alignment:** Standard SDOF kinematics (Chopra, *Dynamics of
Structures*, §3.6). Used for quick displacement check before running full
ELF procedure.

---

## Example workflow

```
1. seismic_site_coefficients  Ss:1.5  S1:0.6  site_class:"D"
   → Fa:1.0  Fv:1.3  SDS:1.0  SD1:0.52  (§11.4.4 / 11.4.5)

2. seismic_approximate_period  hn:24.0  structure_type:"concrete_moment"
   → Ta_s:0.82  (§12.8.2.1, Ct=0.016, x=0.9)

3. seismic_response_coefficient  SDS:1.0  SD1:0.52  T:0.82  R:5  Ie:1.0
   → Cs:0.127  Cs_basic:0.200  Cs_cap:0.127 (cap governs)  (§12.8.1.1)

4. seismic_base_shear  Cs:0.127  W:8000
   → V_kN:1016  (§12.8.1, V=Cs×W)

5. seismic_vertical_distribution  V:1016  W_stories:[2000,2000,2000,2000]
                                   h_stories:[3,6,9,12]  T:0.82
   → k:1.64  Fx_kN:[78,175,302,461]  (§12.8.3, k interpolated)

6. seismic_story_shear_overturning  Fx:[78,175,302,461]  h_stories:[3,6,9,12]
   → Vx_kN:[1016,938,763,461]  Mx_kNm:[8469,6051,3162,1384]  (§12.8.4/12.8.5)
```
