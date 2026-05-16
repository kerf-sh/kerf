# Steel Heat Treatment Engineering

Pure-Python steel heat treatment calculations. No OCC dependency. All tools are stateless.
References: Andrews (1965), Grossmann (1942), Koistinen-Marburger (1959), Hollomon-Jaffe (1945),
ASM Handbook Vol. 4.

---

## When to use

Heat treatment, quenching, tempering, hardening, hardenability, critical diameter, Grossmann DI,
Jominy, Jominy end-quench, martensite, martensite start temperature Ms, martensite finish Mf,
retained austenite, Koistinen-Marburger, Hollomon-Jaffe, tempering parameter, carburizing, case
depth, case hardening, nitriding, white layer, induction hardening, skin depth, austenitizing
temperature, Ac1, Ac3, annealing, normalizing, stress relief, hardness conversion, HRC, HB, HV,
HRB, UTS, steel heat treatment, steel metallurgy.

---

## Tools

### `ht_grossmann_DI`

Grossmann ideal critical diameter DI from steel composition and ASTM grain size.
DI = DI0(C, grain_size) × multiplying factors for Mn, Si, Cr, Ni, Mo, Cu, V.

**Input:** `C` (wt%, required), optional `Mn`, `Si`, `Cr`, `Ni`, `Mo`, `Cu`, `V`,
`grain_size_ASTM` (default 7)

**Returns:** `DI_mm`, individual multiplier factors, warnings

---

### `ht_jominy_hardness`

Jominy end-quench hardness (HRC) at a given distance from the quenched end.
Simplified exponential-decay model for plain carbon steels.

**Input:** `C` (wt%, required), `jominy_dist_mm` (required)

**Returns:** `HRC`, `cooling_rate_approx`

---

### `ht_actual_critical_diameter`

Actual critical diameter D_act from DI and Grossmann quench severity H.
Typical H: 0.2 (still air) to 5.0 (vigorous brine).

**Input:** `DI_mm` (required), `H` (quench severity, required)

**Returns:** `D_act_mm`

---

### `ht_as_quenched_hardness`

As-quenched hardness (HRC) from carbon content and martensite fraction (Hodge-Orehoski).

**Input:** `C_wt_pct` (required), `martensite_pct` (0–100, required)

**Returns:** `HRC`, warnings for low martensite

---

### `ht_hollomon_jaffe`

Hollomon-Jaffe tempering parameter P and tempered hardness (HRC).
P = T_K × (C_HJ + log₁₀(t)).

**Input:** `C_wt_pct` (required), `T_C` (tempering temp °C, required), `t_hours` (required),
`HRC_as_quenched` (optional), `C_HJ` (default 20)

**Returns:** `P`, `HRC_tempered`, warnings

---

### `ht_carburizing_case_depth`

Carburizing case depth via Harris formula and erfc diffusion solution.
Harris: x = k · √(D(T) · t); D(T) = D0 · exp(−Q / R / T).

**Input:** `T_C` (°C, required), `t_hours` (required), `initial_C` (default 0.20),
`surface_C` (default 0.85), `target_C` (default 0.35), `k` (default 1.0)

**Returns:** `depth_harris_mm`, `depth_erfc_mm`, warnings (decarb risk >1050°C)

---

### `ht_nitriding_case_depth`

Nitriding white-layer (compound layer) and diffusion-zone depth for gas nitriding.
Uses Arrhenius diffusivity for N in α-Fe. Typical: 480–570°C for 10–100 hours.

**Input:** `T_C` (required), `t_hours` (required)

**Returns:** `white_layer_mm`, `diffusion_zone_mm`

---

### `ht_induction_case_depth`

Induction hardening case depth from electromagnetic skin depth.
δ = √(ρ / (π·f·μ₀·μᵣ)); case_depth ≈ 1.5·δ.

**Input:** `freq_Hz` (required), `t_s` (heating time s, required),
`rho` (default 1.1e-6 Ω·m), `mu_r` (default 1.0)

**Returns:** `skin_depth_mm`, `case_depth_mm`

---

### `ht_austenitizing_temperature`

Recommended austenitizing temperature range for quench hardening.
Hypoeutectoid (C < 0.77%): Ac3 + 50–80°C. Hypereutectoid: Ac1 + 30–60°C.

**Input:** `C_wt_pct` (required)

**Returns:** `T_low_C`, `T_high_C`, `basis`

---

### `ht_andrews_Ac1`

Andrews (1965) lower critical temperature Ac1 (°C) from composition.
Ac1 = 723 − 16.9·Ni + 29.1·Si − 10.7·Mn + 16.9·Cr + 6.38·W.

**Input:** optional `C`, `Si`, `Mn`, `Cr`, `Ni`, `Mo`, `V`, `W`, `Cu`, `Co` (all wt%, default 0)

**Returns:** `Ac1_C`

---

### `ht_andrews_Ac3`

Andrews (1965) upper critical temperature Ac3 (°C) from composition.

**Input:** optional `C` (default 0.20), `Si`, `Mn`, `Cr`, `Ni`, `Mo`, `V`, `W`, `Cu`, `Co`

**Returns:** `Ac3_C`

---

### `ht_martensite_start_Ms`

Andrews (1965) martensite-start temperature Ms (°C).
Ms = 539 − 423·C − 30.4·Mn − 17.7·Ni − 12.1·Cr − 7.5·Mo + 10·Co − 7.5·Si.

**Input:** optional `C` (default 0.20), `Mn`, `Cr`, `Ni`, `Mo`, `Si`, `V`, `W`, `Co`

**Returns:** `Ms_C`, warning if Ms < 0 (cryogenic treatment needed)

---

### `ht_martensite_finish_Mf`

Martensite-finish temperature Mf ≈ Ms − 215°C (Payson & Savage).

**Input:** `Ms_C` (required)

**Returns:** `Mf_C`, warning if Mf < 0

---

### `ht_koistinen_marburger`

Koistinen-Marburger martensite fraction at quench temperature.
f_M = 1 − exp(−0.011 × (Ms − T)) for T < Ms.

**Input:** `T_C` (quench temperature, required), `Ms_C` (required)

**Returns:** `f_M` (volume fraction)

---

### `ht_retained_austenite`

Retained austenite fraction after quenching. RA = 1 − f_M.

**Input:** `T_quench_C` (required), `Ms_C` (required)

**Returns:** `RA_fraction`, warning if RA > 15%

---

### `ht_annealing_temperature`

Recommended full-anneal and process-anneal temperature ranges for steel.

**Input:** `C_wt_pct` (required)

**Returns:** `full_anneal_low_C`, `full_anneal_high_C`, `process_anneal_range`

---

### `ht_normalizing_temperature`

Recommended normalizing temperature (Ac3 + 50–100°C). Flags hypereutectoid compositions.

**Input:** `C_wt_pct` (required)

**Returns:** `T_low_C`, `T_high_C`, warnings

---

### `ht_stress_relief_temperature`

Recommended stress-relief temperature range by steel family.
Supported: `plain_carbon`, `low_alloy`, `tool_steel`, `stainless_304`, `stainless_316`,
`stainless_martensitic`, `maraging`, `cast_iron`, `spring_steel`.

**Input:** `steel_type` (default `'plain_carbon'`)

**Returns:** `T_low_C`, `T_high_C`, notes

---

### `ht_hardness_convert`

ASTM E140 hardness conversions between HRC, HB, HV, HRB, and approximate UTS (MPa).

**Input:** `value` (required), `from_scale` (`'HRC'`/`'HB'`/`'HV'`/`'HRB'`/`'UTS'`, required)

**Returns:** all equivalent hardness scales and UTS_MPa

---

## Example

```
1. ht_andrews_Ms  C:0.40  Mn:0.80  Cr:0.90
   (use ht_martensite_start_Ms)  → Ms_C: 320

2. ht_koistinen_marburger  T_C:25  Ms_C:320
   → f_M: 0.965

3. ht_hollomon_jaffe  C_wt_pct:0.40  T_C:200  t_hours:1
   → P: 7200  HRC_tempered: 55

4. ht_carburizing_case_depth  T_C:925  t_hours:4
   → depth_harris_mm: 0.84  depth_erfc_mm: 0.91
```
