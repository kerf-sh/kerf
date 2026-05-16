# Tribology & Fluid-Film Lubrication — LLM Reference

Hydrodynamic journal bearings, EHL film thickness, thrust pads, and viscosity models
per Shigley, Hamrock-Schmid-Jacobson, Raimondi-Boyd, and Dowson-Higginson.
No OCC dependency. All tools are stateless; no DB write.
Units: Pa, Pa·s, N, m, m/s, rpm, K.

---

## When to use

Keywords: lubrication, journal bearing, hydrodynamic, fluid film, Sommerfeld number,
Raimondi Boyd, Petroff, oil film, minimum film thickness, h_min, eccentricity ratio,
viscosity, Walther equation, ASTM D341, Barus, viscosity-pressure, EHL,
elastohydrodynamic, Dowson-Higginson, Hamrock-Dowson, line contact, point contact,
thrust pad, Stribeck, lambda ratio, lubrication regime, specific load, bearing clearance,
power loss, temperature rise.

---

## Workflow

```
viscosity_walther / viscosity_barus  → μ at operating temperature/pressure
bearing_specific_load                → p = W/(L·D)
journal_bearing_sommerfeld           → S (Sommerfeld number)
  → journal_bearing_raimondi_boyd    → ε, h_min, friction, flow, pressure
  → journal_bearing_petroff          → friction torque, power loss
     → bearing_temperature_rise      → ΔT from power loss + flow
ehl_line_contact / ehl_point_contact → minimum EHL film thickness
bearing_lambda_ratio                 → λ = h_min / composite roughness → regime
thrust_pad_load                      → fixed-incline thrust capacity
```

---

## Tools

### `journal_bearing_sommerfeld`

Dimensionless Sommerfeld number S = (R/c)² · (μN/P) for a full hydrodynamic journal bearing.

**Input:** `W` (radial load, N), `mu` (dynamic viscosity, Pa·s), `N` (speed, rev/s), `R` (journal radius, m), `c` (radial clearance, m), `L` (bearing length, m; default = D for L/D = 1).

**Returns:** `S`, `specific_load_Pa` = W/(L·D).

---

### `journal_bearing_raimondi_boyd`

Dimensionless performance from Raimondi-Boyd design charts (curve-fit).

**Input:** `S` (Sommerfeld number), `L_D_ratio` (L/D, default 1.0).

**Returns:** `epsilon` (eccentricity ratio), `h_min_factor` (= h_min/c), `friction_variable` (= f·R/c), `flow_variable` (= Q/(R·c·N·L)), `max_pressure_ratio` (p_max / p̄).

---

### `journal_bearing_petroff`

Petroff (lightly loaded) friction torque and power loss.

**Input:** `mu` (Pa·s), `N` (rev/s), `R` (m), `c` (m), `L` (m).

**Returns:** `friction_torque_Nm`, `power_loss_W`.

---

### `bearing_temperature_rise`

Lubricant temperature rise from power loss and flow rate.

**Input:** `power_loss_W`, `flow_rate_m3_s` (volumetric flow), `rho` (oil density, kg/m³, default 860), `cp` (specific heat, J/(kg·K), default 1900).

**Returns:** `delta_T_K` = power_loss / (ρ · cp · Q̇).

---

### `viscosity_walther`

ASTM D341 viscosity-temperature relationship (Walther equation).

Predicts kinematic viscosity ν (mm²/s) at a new temperature from two reference measurements.

**Input:** `T1_K`, `nu1_cSt` (first reference point), `T2_K`, `nu2_cSt` (second reference point), `T_query_K` (temperature to predict).

**Returns:** `nu_cSt` at T_query.

---

### `viscosity_barus`

Barus viscosity-pressure relationship: μ(p) = μ₀ · exp(α·p).

**Input:** `mu0_Pa_s` (viscosity at atmospheric pressure), `alpha_Pa_inv` (pressure-viscosity coefficient, Pa⁻¹; typical mineral oil ~2×10⁻⁸), `p_Pa` (operating pressure, Pa).

**Returns:** `mu_Pa_s` at p.

---

### `ehl_line_contact`

Dowson-Higginson minimum film thickness for elastohydrodynamic line contact.

**Input:** `U` (speed parameter), `G` (materials parameter), `W` (load parameter), `R_m` (reduced radius, m), `E_prime_Pa` (reduced elastic modulus).

**Returns:** `h_min_m`, `h_central_m`, dimensionless film parameters.

---

### `ehl_point_contact`

Hamrock-Dowson minimum film thickness for EHL circular/elliptical point contact.

**Input:** `U` (speed parameter), `G` (materials parameter), `W` (load parameter), `k_ellipticity` (ellipticity ratio a/b), `R_x_m`, `R_y_m` (reduced radii), `E_prime_Pa`.

**Returns:** `h_min_m`, `h_central_m`.

---

### `thrust_pad_load`

Load capacity of a fixed-incline (Rayleigh-step) thrust pad.

**Input:** `mu` (Pa·s), `U` (sliding speed, m/s), `L` (pad length, m), `B` (pad width, m), `h1_m` (outlet film thickness), `h2_m` (inlet film thickness; h2 > h1).

**Returns:** `W_N` (load capacity), `friction_force_N`, `COF`.

---

### `bearing_specific_load`

Specific (projected) bearing load p = W / (L × D).

**Input:** `W_N` (radial load), `L_m` (bearing length), `D_m` (journal diameter).

**Returns:** `p_Pa`.

---

### `bearing_lambda_ratio`

Stribeck λ-ratio and lubrication regime classification.

λ = h_min / √(Rq1² + Rq2²), where Rq = RMS surface roughness.

**Input:** `h_min_m`, `Rq1_m` (RMS roughness surface 1), `Rq2_m` (RMS roughness surface 2).

**Returns:** `lambda`, `regime` (`"boundary"` λ < 1, `"mixed"` 1–3, `"full_film"` > 3).

---

## Example

```
# Journal bearing design: shaft ∅50 mm, L=50 mm, W=5000 N, 1500 rpm
# ISO VG 46 oil at 60°C: μ ≈ 0.023 Pa·s, c = 0.05 mm

bearing_specific_load  W_N:5000  L_m:0.05  D_m:0.05
  → p_Pa: 2.0e6

journal_bearing_sommerfeld  W:5000  mu:0.023  N:25  R:0.025  c:0.00005  L:0.05
  → S: 0.144

journal_bearing_raimondi_boyd  S:0.144  L_D_ratio:1.0
  → epsilon:0.72  h_min_factor:0.28  friction_variable:3.8

# h_min = 0.28 × c = 14 µm
bearing_lambda_ratio  h_min_m:0.000014  Rq1_m:0.8e-6  Rq2_m:0.4e-6
  → lambda: 15.7  regime: "full_film"
```
