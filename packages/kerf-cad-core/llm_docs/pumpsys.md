# Centrifugal Pump System Engineering

Pure-Python centrifugal pump engineering tools. No OCC dependency. Covers system curves,
pump curve fitting, operating point, power, NPSH, affinity laws, series/parallel
configurations, specific speed, and minimum flow. All tools stateless. References:
Kaplan et al. "Pump Handbook" 4th ed.; White "Fluid Mechanics" 8th ed.; HI 9.6.4.

---

## When to use

Use these tools when the user asks about:
- centrifugal pump, pump selection, pump sizing, pump design
- system curve, H-Q curve, head-flow
- pump curve fit, quadratic pump curve, pump datasheet
- operating point, duty point, pump-system intersection
- hydraulic power, pump power, brake power, shaft power, pump efficiency
- NPSH, net positive suction head, cavitation, NPSHa, NPSHr
- affinity laws, speed scaling, impeller trim, trimming impeller
- pumps in series, series pumps, boost pump
- pumps in parallel, parallel pumps, flow splitting
- specific speed, impeller type, radial, mixed flow, axial
- minimum flow, recirculation, BEP, best efficiency point

---

## Tools

### `pump_system_curve`

System head at a given flow rate: H_sys = H_static + K·Q².

K lumps all Darcy-Weisbach pipe-friction and minor fitting losses.
Use `pump_system_K_from_pipe` to derive K from pipe geometry.

**Input:**
- `H_static` (required) — static head (m, >= 0)
- `K` (required) — system resistance coefficient (s²/m⁵, >= 0)
- `Q` (required) — flow rate (m³/s, >= 0)

**Returns:** `H_system_m`.

---

### `pump_system_K_from_pipe`

System resistance coefficient K from Darcy-Weisbach pipe friction and fittings.

`K = (f·L/D + K_fittings) / (2·g·A²)`

**Input:**
- `f` (required) — Darcy friction factor
- `L` (required) — pipe length (m)
- `D` (required) — internal pipe diameter (m)
- `A` (required) — pipe cross-sectional area (m²)
- `K_fittings` — sum of minor-loss coefficients (default 0)

**Returns:** `K` (s²/m⁵).

---

### `pump_curve_fit`

Fit a quadratic pump curve H = a·Q² + b·Q + c from ≥ 3 catalogue (Q, H) points.

Exactly 3 points: interpolating quadratic. > 3 points: least-squares fit.

**Input:**
- `points` (required) — list of `[Q, H]` pairs (m³/s, m), at least 3

**Returns:** `a`, `b`, `c`, `H_shutoff` (head at Q=0), `Q_max`.

---

### `pump_operating_point`

Pump duty point: intersection of pump curve and system curve.

Solves `(a−K)·Q² + b·Q + (c−H_static) = 0`.

**Input:**
- `a`, `b`, `c` (required) — pump curve coefficients from `pump_curve_fit`
- `H_static` (required), `K` (required)

**Returns:** `Q_op_m3s`, `H_op_m`; flags negative-flow or no-intersection.

---

### `pump_hydraulic_power`

Hydraulic power, brake power, and efficiency.

`P_hydraulic = ρ·g·Q·H`;  `P_brake = P_hydraulic / η`

**Input:**
- `Q_m3s` (required), `H_m` (required)
- `efficiency` — pump hydraulic efficiency η (default 0.75)
- `rho` — fluid density (kg/m³, default 1000)

**Returns:** `P_hydraulic_W`, `P_hydraulic_kW`, `P_brake_W`, `P_brake_kW`.

---

### `pump_npsh_available`

Available NPSH at pump inlet.

`NPSHa = (P_atm − P_vapor)/(ρ·g) − z_s − h_fs`

**Input:**
- `P_atm_Pa` (required) — atmospheric (suction-side) pressure (Pa)
- `P_vapor_Pa` (required) — fluid vapour pressure (Pa)
- `z_s_m` (required) — suction static lift (m; positive = pump above liquid)
- `h_fs_m` (required) — suction friction losses (m)
- `rho` (default 1000 kg/m³)

**Returns:** `NPSHa_m`.

---

### `pump_npsh_check`

Cavitation margin: NPSHa vs required NPSHr.

`margin = NPSHa − NPSHr`; recommended margin ≥ 0.5 m (or safety factor ≥ 1.3).

**Input:**
- `NPSHa_m` (required), `NPSHr_m` (required)
- `safety_factor` (default 1.0)

**Returns:** `margin_m`, `safe` (bool), `warnings`.

---

### `pump_affinity_speed`

Affinity laws: scale pump curve for a speed change.

`Q₂ = Q₁ × (n₂/n₁)`;  `H₂ = H₁ × (n₂/n₁)²`;  `P₂ = P₁ × (n₂/n₁)³`

**Input:**
- `Q1_m3s`, `H1_m`, `P1_kW` (all required), `n1_rpm`, `n2_rpm` (required)

**Returns:** `Q2_m3s`, `H2_m`, `P2_kW`.

---

### `pump_affinity_trim`

Affinity laws: scale pump curve for impeller diameter trim.

`Q₂ = Q₁ × (D₂/D₁)`;  `H₂ = H₁ × (D₂/D₁)²`;  `P₂ = P₁ × (D₂/D₁)³`

**Input:**
- `Q1_m3s`, `H1_m`, `P1_kW` (all required), `D1_mm`, `D2_mm` (required)

**Returns:** `Q2_m3s`, `H2_m`, `P2_kW`.

---

### `pumps_in_series`

Combined H-Q curve for two pumps in series (heads add at same flow).

**Input:**
- `pump1_coeffs` — `{a, b, c}` for pump 1 curve
- `pump2_coeffs` — `{a, b, c}` for pump 2 curve

**Returns:** combined coefficients `a_combined`, `b_combined`, `c_combined`.

---

### `pumps_in_parallel`

Combined flow for two identical or different pumps in parallel at a given head.

**Input:**
- `pump1_coeffs`, `pump2_coeffs` — `{a, b, c}`
- `H_m` (required) — operating head (m)

**Returns:** `Q1_m3s`, `Q2_m3s`, `Q_total_m3s`.

---

### `pump_specific_speed`

Dimensionless specific speed Ns and impeller-type guidance.

`Ns = n × Q^0.5 / H^0.75`

**Input:**
- `n_rpm` (required), `Q_m3s` (required), `H_m` (required)

**Returns:** `Ns`, `impeller_type` (radial/mixed-flow/axial guidance).

---

### `pump_minimum_flow_check`

Warn if operating flow is below minimum continuous stable flow.

**Input:**
- `Q_op_m3s` (required), `Q_bep_m3s` (required)
- `min_fraction` — minimum Q_op/Q_bep ratio (default 0.3)

**Returns:** `ok` (bool), `ratio`, `warnings`.

---

## Example

```
1. pump_curve_fit  points:[[0,35],[0.01,32],[0.02,25],[0.03,12]]
   → a:-38000  b:-100  c:35

2. pump_system_K_from_pipe  f:0.02  L:50  D:0.1  A:0.00785
   → K:81000

3. pump_operating_point  a:-38000  b:-100  c:35  H_static:10  K:81000
   → Q_op_m3s:0.0165  H_op_m:32.3

4. pump_hydraulic_power  Q_m3s:0.0165  H_m:32.3  efficiency:0.72
   → P_hydraulic_kW:5.22  P_brake_kW:7.25

5. pump_npsh_available  P_atm_Pa:101325  P_vapor_Pa:2337  z_s_m:3.0  h_fs_m:0.8
   → NPSHa_m:6.4
```
