# Injection Moulding Process Design

Pure-Python tools for injection-moulding process engineering. No OCC dependency.
Covers polymer selection, clamping, shot sizing, gate/runner design, cooling, cycle time,
and ejection force. All tools stateless — compute and return; no DB write. Units: SI.

---

## When to use

Use these tools when the user asks about:
- injection moulding, injection molding, IM, plastics processing
- clamping force, tonnage, press selection
- shot weight, shot volume, machine capacity
- gate design, runner sizing, sprue
- cooling time, solidification time, mould temperature
- flow length, L/t ratio, short shot risk
- shrinkage, sink mark, mould dimension compensation
- cycle time, shots per hour, throughput
- number of cavities, multi-cavity tool
- draft angle, ejection force, demoulding
- polymers PP, ABS, PC, PA, POM

---

## Tools

### `injection_polymer_properties`

Return built-in property record for a named injection-moulding polymer.

**Input:**
- `polymer` (required) — one of `PP`, `ABS`, `PC`, `PA`, `POM`

**Returns:** melt temperature, mould temperature, ejection temperature, linear shrinkage,
thermal diffusivity, density, flow-length/wall-thickness limit, friction coefficient,
typical cavity pressure.

---

### `injection_clamp_tonnage`

Compute required clamping force from projected area and cavity pressure.

`F_clamp = n_cavities × A_proj × P_cavity × safety_factor`

**Input:**
- `projected_area_m2` (required) — parting-line projected area per cavity (m²)
- `cavity_pressure_Pa` (required) — peak cavity pressure (Pa), typical 30–80 MPa
- `n_cavities` — number of cavities (default 1)
- `safety_factor` — clamping safety factor (default 1.1)

**Returns:** `clamp_force_kN`; flags over-tonnage if > 50 000 kN.

---

### `injection_shot_volume_weight`

Compute injection shot volume and weight and check against machine capacity.

`shot_volume = n_cavities × part_volume + runner_volume`

**Input:**
- `part_volume_m3` (required), `runner_volume_m3` (required), `n_cavities` (required),
  `polymer` (required), `machine_shot_capacity_kg` (default 5.0)

**Returns:** `shot_volume_m3`, `shot_weight_kg`, `utilisation`; flags short-shot risk.

---

### `injection_gate_runner_sizing`

Size gate land thickness/width and primary runner diameter.

Gate land = 60% of wall thickness; runner = max(1.5 × gate_thickness, 4 mm).

**Input:**
- `flow_rate_m3s` (required), `wall_thickness_m` (required), `polymer` (required)
- `gate_velocity_limit_ms` (default 0.5 m/s)

**Returns:** `gate_thickness_m`, `gate_width_m`, `runner_diameter_m`; flags thin-wall risk.

---

### `injection_cooling_time`

Cooling time for a flat-plate part (Fourier first-term equation).

`t_c = (s²/(π²·α)) · ln((8/π²) · (T_m − T_w) / (T_e − T_w))`

**Input:**
- `wall_thickness_m`, `melt_temp_C`, `mold_temp_C`, `ejection_temp_C`, `polymer` (all required)

**Returns:** `cooling_time_s`.

---

### `injection_flow_length_feasibility`

Check flow-length / wall-thickness (L/t) ratio against polymer limit.

**Input:**
- `flow_length_m` (required), `wall_thickness_m` (required), `polymer` (required)

**Returns:** `lt_ratio`, `lt_limit`, `feasible` (bool); flags thin-wall-flow risk.

---

### `injection_shrinkage_sink_estimate`

Estimate linear shrinkage and sink-mark depth.

`ΔL = part_dim × (shrinkage_pct / 100)`;  `mould_dim = part_dim / (1 − shrinkage/100)`

**Input:**
- `part_dim_m` (required), `wall_thickness_m` (required), `polymer` (required)

**Returns:** `shrinkage_pct`, `delta_L_m`, `mould_dim_m`, `sink_depth_m`.

---

### `injection_cycle_time_breakdown`

Break total injection cycle into phases and compute shots per hour.

`total = cooling + fill + pack/hold + mould_open_close + ejection`

**Input:**
- `cooling_time_s`, `fill_time_s`, `pack_hold_time_s`, `mold_open_close_s`, `ejection_time_s`
  (all required)

**Returns:** `total_cycle_s`, phase fractions, `shots_per_hour`.

---

### `injection_cavities_from_tonnage`

Maximum number of cavities a given press can support.

`n_max = floor(F_machine / (A_proj × P_cavity × safety_factor))`

**Input:**
- `machine_tonnage_kN` (required), `projected_area_per_cavity_m2` (required),
  `cavity_pressure_Pa` (required), `safety_factor` (default 1.1)

**Returns:** `n_max_cavities`; flags over-tonnage if press cannot support one cavity.

---

### `injection_draft_ejection_force`

Recommend draft angle and estimate ejection force.

`F_eject = μ × P_shrink × A_side` where `A_side ≈ 4 × √(proj_area) × L_draw`.

**Input:**
- `projected_area_m2` (required), `wall_thickness_m` (required), `L_draw_m` (required),
  `polymer` (required)
- `surface_finish` — `polished` (0.5°), `standard` (1.0°, default), `textured` (3.0°)

**Returns:** `draft_angle_deg`, `ejection_force_N`.

---

## Example

```
1. injection_polymer_properties  polymer:"ABS"
   → shrinkage_pct:0.6, melt_temp_C:230, alpha:1.1e-7 m²/s ...

2. injection_clamp_tonnage  projected_area_m2:0.005  cavity_pressure_Pa:50e6  n_cavities:4
   → clamp_force_kN:1100

3. injection_cooling_time  wall_thickness_m:0.003  melt_temp_C:230  mold_temp_C:60
     ejection_temp_C:90  polymer:"ABS"
   → cooling_time_s:8.4

4. injection_cycle_time_breakdown  cooling_time_s:8.4  fill_time_s:1.5
     pack_hold_time_s:3.0  mold_open_close_s:2.0  ejection_time_s:1.0
   → total_cycle_s:15.9  shots_per_hour:226
```
