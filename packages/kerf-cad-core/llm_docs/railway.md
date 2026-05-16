# Railway Engineering

Pure-Python railway track geometry, vehicle dynamics, and structural analysis. Covers superelevation (cant), transition curves, gauge widening, vertical curves, Hertzian wheel-rail contact, Davis resistance, tractive effort, braking distance, rail bending, and CWR thermal stress. No OCC dependency. All tools are stateless and never raise. References: UIC 703-2, EN 13803-1, Esveld (2001).

---

## When to use

Use these tools for railway / rail-transit engineering: track geometry design, cant and superelevation, equilibrium cant, cant deficiency, cant gradient rate check, clothoid / cubic spiral transition length, gauge widening on tight curves, crest and sag vertical curves, wheel-rail Hertzian contact stress, train rolling resistance (Davis formula), tractive effort and adhesion limit, braking distance, rail stress and deflection (Winkler beam on elastic foundation), CWR buckling risk, thermal force in continuously welded rail.

---

## Tools

### `railway_equilibrium_cant`

Equilibrium (theoretical) superelevation for a curve at a given speed: h_eq = V² × G / (g × R). **Input:** `speed_kmh`, `radius_m` (required); `gauge_mm` (default 1435). **Returns:** `cant_eq_mm`.

---

### `railway_applied_cant`

Applied cant capped at `max_cant_mm` (default 150 mm per EN 13803) with cant deficiency check. **Input:** `speed_kmh`, `radius_m` (required); `gauge_mm`, `max_cant_mm`, `cant_deficiency_limit_mm` (optional). **Returns:** `cant_eq_mm`, `cant_applied_mm`, `cant_deficiency_mm`, `warnings`.

---

### `railway_cant_deficiency`

Cant deficiency for a given applied cant on a curve at speed: h_def = h_eq − h_applied. Positive = outer flange loaded. **Input:** `speed_kmh`, `radius_m`, `cant_applied_mm` (required); `gauge_mm`, `deficiency_limit_mm` (optional). **Returns:** `cant_deficiency_mm`, `warning_exceeded`.

---

### `railway_cant_gradient_check`

Cant ramp rate check against UIC/EN 13803 limits. Spatial (≤ 1.0 mm/m) and temporal (≤ 55 mm/s) criteria. **Input:** `cant_change_mm`, `transition_length_m`, `speed_kmh` (required); `gradient_limit_mm_per_m`, `rate_limit_mm_per_s` (optional). **Returns:** `cant_gradient_mm_per_m`, `cant_rate_mm_per_s`, `gradient_ok`, `rate_ok`.

---

### `railway_transition_length`

Minimum clothoid / cubic spiral transition length from cant-ramp constraints. Methods: `rate_of_change` (default), `cant_gradient`, or `combined`. **Input:** `cant_change_mm`, `speed_kmh` (required); `method`, `rate_limit_mm_s`, `gradient_limit_mm_m` (optional). **Returns:** `transition_length_m`, `L_rate_m`, `L_gradient_m`.

---

### `railway_gauge_widening`

Additional gauge widening on tight curves per UIC 505 / EN 13715. UIC table: R ≥ 250 m → 0 mm; R < 150 m → 15 mm. **Input:** `radius_m` (required); `gauge_nom_mm` (default 1435), `method` (`"UIC"` default or `"formula"`). **Returns:** `gauge_widening_mm`, `gauge_design_mm`.

---

### `railway_vertical_curve`

Minimum vertical curve length for a change of grade per EN 13803-1: crest L = V²·|Δg|/1300, sag L = V²·|Δg|/400. **Input:** `delta_g_percent`, `speed_kmh` (required); `curve_type` (`"crest"` default or `"sag"`). **Returns:** `vertical_curve_length_m`, `K_value`.

---

### `railway_hertzian_contact`

Hertzian wheel-rail contact ellipse semi-axes and maximum contact pressure. **Input:** `P_N` (wheel load), `R1x_m` (wheel rolling radius), `R1y_m` (wheel tread radius), `R2x_m` (rail longitudinal, typically 1e9), `R2y_m` (rail head radius) — all required; `E1_Pa`, `nu1`, `E2_Pa`, `nu2` (optional, default steel). **Returns:** `semi_axis_a_m`, `semi_axis_b_m`, `contact_area_m2`, `max_pressure_Pa`.

---

### `railway_davis_resistance`

Davis train resistance R = A + BV + CV² plus grade and curve resistance. **Input:** `mass_kg`, `speed_kmh`, `A`, `B`, `C` (required); `grade_percent`, `curve_radius_m` (optional). **Returns:** `R_davis_N_kN`, `R_grade_N_kN`, `R_curve_N_kN`, `R_total_N_kN`, `R_total_N`.

---

### `railway_tractive_effort`

Maximum continuous tractive effort from power, checked against adhesion limit. **Input:** `power_W`, `speed_kmh` (required); `adhesion_coeff`, `axle_load_N`, `driven_axles` (optional). **Returns:** `TE_power_N`, `TE_adhesion_N`, `TE_applied_N`, `warnings` (adhesion_limited flag).

---

### `railway_braking_distance`

Braking distance from initial speed to rest, including reaction distance. **Input:** `speed_kmh`, `deceleration_ms2` (required); `reaction_time_s` (default 1.5 s), `grade_percent` (optional). **Returns:** `braking_distance_m`, `reaction_distance_m`, `time_to_stop_s`.

---

### `railway_rail_bending`

Winkler beam-on-elastic-foundation rail stress, deflection, and ballast pressure. **Input:** `wheel_load_N`, `rail_I_m4` (required); `rail_E_Pa`, `foundation_modulus_Pa_per_m`, `rail_height_m`, `sleeper_spacing_m`, `sleeper_area_m2` (optional, defaults to UIC60). **Returns:** `deflection_m`, `moment_Nm`, `stress_Pa`, `sleeper_reaction_N`, `ballast_pressure_Pa`.

---

### `railway_thermal_stress`

CWR thermal stress and buckling risk: σ = E·α·ΔT. Positive ΔT = warming = compressive. **Input:** `delta_T_K` (required); `E_Pa`, `alpha`, `CWR` (bool, default true), `rail_area_m2`, `yield_Pa` (optional, defaults to UIC60 grade 900A). **Returns:** `thermal_stress_Pa`, `thermal_force_N`, `CWR_buckling_risk` (bool).

---

## Example

```
1. railway_equilibrium_cant  speed_kmh:160  radius_m:1200
   → cant_eq_mm: 116.7

2. railway_applied_cant  speed_kmh:160  radius_m:1200  max_cant_mm:150
   → cant_applied_mm: 116.7  cant_deficiency_mm: 0  (no deficiency)

3. railway_transition_length  cant_change_mm:116.7  speed_kmh:160  method:"combined"
   → transition_length_m: 117  L_rate_m:117  L_gradient_m:116.7

4. railway_davis_resistance  mass_kg:500000  speed_kmh:100  A:2.0  B:0.02  C:0.002
     grade_percent:1.0
   → R_total_N: 94100
```
