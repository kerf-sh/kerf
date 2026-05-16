# Flow Metering, Control Valves & Relief Valves

Pure-Python tools for differential-pressure flow meters (ISO 5167), liquid/gas/steam
control valve sizing (ISA/IEC Cv & Kv), API 520 pressure-relief valve orifice sizing,
pitot and annubar velocity, open-channel weirs, Parshall flumes, rotameter
correction, and meter turndown ratio. No OCC dependency. All tools never raise.

---

## When to use

Use when the user asks about: flow meter, orifice plate, venturi, nozzle, ISO 5167,
differential pressure, DP meter, Cv, Kv, control valve sizing, liquid valve, gas
valve, steam valve, choked flow, cavitation, PRV, pressure relief valve, safety
valve, API 520, API 526, orifice area, Napier equation, pitot tube, annubar,
averaging pitot, V-notch weir, triangular weir, rectangular weir, Parshall flume,
open channel measurement, rotameter, variable area meter, turndown ratio.

---

## Tools

### `dp_meter`

ISO 5167 differential-pressure flow meter (orifice, venturi, or nozzle).

**Input:**
- `meter_type` (required) — `"orifice"`, `"venturi"`, or `"nozzle"`
- `pipe_d_m`, `beta`, `dp_pa`, `rho_kg_m3` (all required)
- `mu_pa_s` — viscosity (default 1e-3 for water)
- `p1_pa`, `kappa` — required for compressible gas; `gas:true` applies expansibility factor

**Output:** `mass_flow_kg_s`, `vol_flow_m3_s`, `Cd`, `Re_D`, `expansibility`, `permanent_pressure_loss_pa`

---

### `control_valve_liquid`

ISA/IEC Cv & Kv sizing for liquid control valves with choked-flow and cavitation check.

**Input:**
- `q_m3h`, `rho_kg_m3`, `dp_kpa`, `p1_kpa`, `pv_kpa`, `pc_kpa` (all required)
- `FL` — pressure recovery factor (default 0.90)

**Output:** `Cv`, `Kv`, `choked_dp_kpa`, `cavitation_index`, `is_choked`, `is_cavitating`

---

### `control_valve_gas`

ISA/IEC Cv & Kv sizing for compressible gas control valves.

**Input:**
- `q_kg_s`, `p1_pa`, `T1_K`, `MW_g_mol`, `dp_pa` (all required)
- `xT` — terminal pressure-drop ratio (default 0.72); `Fp`, `Z`, `kappa` optional

**Output:** `Cv`, `Kv`, `x`, `x_choked`, `Y`, `is_choked`

---

### `control_valve_steam`

IEC 60534-2-1 Cv sizing for steam control valves (N6 mass-flow form).

**Input:**
- `q_kg_s`, `p1_pa`, `dp_pa`, `v1_m3_kg` (all required)
- `xT` (default 0.72), `Fp` (default 1.0)

**Output:** `Cv`, `Kv`, `x`, `x_choked`, `Y`, `is_choked`

---

### `prv_gas`

API 520 Part I gas/vapour PRV orifice area sizing (critical and sub-critical flow).

**Input:**
- `q_kg_s`, `p_set_pa`, `T_K`, `MW_g_mol` (all required)
- `overpressure_frac` (default 0.10), `backpressure_pa`, `Z`, `kd`, `kb`, `kc` optional

**Output:** `area_m2`, `area_in2`, `api526_letter`, `P1_pa`, `is_subcritical`

---

### `prv_liquid`

API 520 Part I liquid PRV orifice area sizing.

**Input:**
- `q_m3s`, `p_set_pa`, `rho_kg_m3` (all required)
- `overpressure_frac` (default 0.25), `backpressure_pa`, `kd`, `kw`, `kc`, `kv` optional

**Output:** `area_m2`, `area_in2`, `api526_letter`

---

### `prv_steam`

API 520 Part I steam PRV orifice area sizing (Napier equation).

**Input:**
- `q_kg_s`, `p_set_pa` (both required)
- `overpressure_frac` (default 0.10), `kd`, `kb`, `ksh` optional

**Output:** `area_m2`, `area_in2`, `api526_letter`

---

### `pitot_velocity`

Pitot-tube point velocity from impact pressure: v = Cp × √(2 × dp / ρ).

**Input:**
- `dp_pa` (required) — stagnation minus static pressure
- `rho_kg_m3` (required)
- `Cp` — pitot coefficient (default 1.0)

**Output:** `velocity_m_s`

---

### `annubar_flow`

Annubar (multi-port averaging pitot) volume and mass flow.

**Input:**
- `dp_pa`, `rho_kg_m3`, `pipe_d_m` (all required)
- `Cp` — annubar flow coefficient (default 0.77)

**Output:** `v_avg_m_s`, `vol_flow_m3_s`, `mass_flow_kg_s`

---

### `v_notch_weir`

ISO 1438 V-notch (triangular) weir open-channel flow: Q = (8/15) × Cd × √(2g) × tan(θ/2) × H^(5/2).

**Input:**
- `H_m` (required) — head above notch vertex
- `theta_deg` — notch angle (default 90°), `Cd` (default 0.611)

**Output:** `discharge_m3_s`

---

### `rectangular_weir`

Rectangular sharp-crested weir flow (Francis / Rehbock formula) with end-contraction correction.

**Input:**
- `H_m`, `L_m` (both required)
- `Cd` (default 0.611), `end_contractions` (0 or 2, default 2)

**Output:** `discharge_m3_s`

---

### `parshall_flume`

Parshall flume free-flow discharge: Q = C × Ha^n (USBR standard).

**Input:**
- `Ha_m` (required) — upstream gauge head
- `throat_w_m` (required) — matched to nearest standard size (0.025–1.829 m)

**Output:** `discharge_m3_s`, `throat_w_actual_m`

---

### `rotameter_scale`

Rotameter (variable-area meter) flow correction for actual fluid density.

**Input:**
- `Q_ref_m3s`, `rho_ref_kg_m3`, `rho_actual_kg_m3` (all required)
- `float_density_kg_m3` — default 8000 (316SS)

**Output:** `Q_actual_m3s`

---

### `turndown_ratio`

Meter or control valve turndown ratio = Q_max / Q_min.

**Input:** `Q_max` (required), `Q_min` (required)

**Output:** `turndown_ratio`; warns if < 3:1

---

## Example

```
1. dp_meter
     meter_type:"orifice"  pipe_d_m:0.1  beta:0.6
     dp_pa:5000  rho_kg_m3:1000
   → mass_flow_kg_s:7.8  Cd:0.604  Re_D:98400

2. control_valve_liquid
     q_m3h:50  rho_kg_m3:900  dp_kpa:200
     p1_kpa:800  pv_kpa:5  pc_kpa:5000
   → Cv:31.5  Kv:27.2  is_choked:false

3. prv_gas
     q_kg_s:0.5  p_set_pa:1000000  T_K:400  MW_g_mol:29
   → area_m2:0.000184  api526_letter:"D"
```
