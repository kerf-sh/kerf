# Clutch and Brake Design

Pure-Python clutch and brake engineering calculations. No OCC dependency. Covers disc
clutches, cone clutches, band brakes, drum brakes, disc brakes, energy/temperature,
cooling area, pV wear check, engagement time, and friction material lookup. All tools
stateless. References: Shigley's MED 10th ed. §§16-1 to 16-12; Juvinall & Marshek
Machine Component Design 5th ed.

---

## When to use

Use these tools when the user asks about:
- clutch, disc clutch, multi-plate clutch, friction clutch, plate clutch
- cone clutch, conical clutch, cone angle, self-locking
- band brake, flexible band, capstan equation, self-energizing brake
- drum brake, shoe brake, leading shoe, trailing shoe, internal expanding
- disc brake, caliper brake, brake pad
- braking torque, clutch torque, torque capacity
- engagement energy, heat generated during engagement, slip energy
- temperature rise, thermal rise, single engagement
- heat dissipation, cooling area, steady-state braking
- pV limit, pressure-velocity, friction material wear
- engagement time, synchronisation time, inertia
- friction material, dry friction, wet friction, sintered, paper

---

## Tools

### `disc_clutch_torque`

Torque capacity of a disc/plate clutch (uniform-wear or uniform-pressure theory).

Supports multi-plate configurations via `n_plates`.

**Input:**
- `F_a` (required) — axial actuation force (N)
- `mu` (required) — coefficient of friction
- `r_o` (required) — outer friction radius (m)
- `r_i` (required) — inner friction radius (m)
- `method` — `uniform-wear` (default, conservative) or `uniform-pressure` (new surfaces)
- `n_plates` — number of friction disc pairs (default 1)

**Returns:** `torque_Nm`, `torque_per_surface_Nm`, `r_eff_m`.

---

### `cone_clutch_torque`

Torque capacity and actuation force of a cone clutch.

Cone half-angle α is from rotation axis to cone surface (typical 8°–15°; < 6° may self-lock).

**Input:**
- `F_a`, `mu`, `r_o`, `r_i` (all required)
- `half_angle_deg` (required) — cone half-angle α (°)
- `method` — `uniform-wear` (default) or `uniform-pressure`

**Returns:** `torque_Nm`, `r_eff_m`, `sin_alpha`, `self_lock` (bool).

---

### `band_brake_torque`

Band brake braking torque using the capstan equation.

`F_tight / F_slack = exp(μ·θ)`;  `T = (F_tight − F_slack) × r`

**Input:**
- `drum_radius` (required) — drum radius r (m)
- `angle_wrap_deg` (required) — band wrap angle θ (°)
- `mu` (required) — band-drum friction coefficient
- `F_tight` (required) — tight-side tension (N)
- `self_energizing` — report capstan ratio if true (default false)

**Returns:** `torque_Nm`, `F_slack_N`, `capstan_ratio`.

---

### `drum_brake_torque`

Long-shoe drum brake torque for leading and trailing shoes.

**Input:**
- `F_a` (required) — actuating force per shoe (N)
- `mu` (required), `drum_radius_m` (required)
- `shoe_width_m` (required), `shoe_arc_deg` (required)
- `a_m` (required) — pivot-to-drum-centre distance (m)
- `c_m` (required) — pivot-to-line-of-action distance (m)

**Returns:** `T_leading_Nm`, `T_trailing_Nm`, `T_total_Nm`, `self_energizing_factor`.

---

### `disc_brake_torque`

Caliper disc brake torque.

`T = μ × F_clamp × r_eff × n_pads`

**Input:**
- `F_clamp` (required) — clamping force per pad pair (N)
- `mu` (required), `r_eff_m` (required) — effective friction radius (m)
- `n_pads` — number of pad pairs (default 1)

**Returns:** `torque_Nm`.

---

### `engagement_energy`

Energy dissipated during a single clutch/brake engagement.

`E = 0.5 × I × Δω²` (rotational inertia method) or `E = T × θ_slip`.

**Input:**
- `I_kgm2` (required) — combined moment of inertia (kg·m²)
- `omega1_rads` (required) — initial angular velocity (rad/s)
- `omega2_rads` (required) — final angular velocity (rad/s)

**Returns:** `energy_J`, `energy_kJ`.

---

### `temperature_rise`

Lumped-mass temperature rise per single engagement.

`ΔT = E / (m × Cp)`

**Input:**
- `energy_J` (required) — energy from `engagement_energy`
- `mass_kg` (required) — heat-absorbing mass (kg)
- `Cp_J_kgK` (default 460 J/(kg·K) for steel)

**Returns:** `delta_T_C`.

---

### `heat_dissipation_area`

Minimum cooling surface area for steady continuous power dissipation.

`A = P / (h × ΔT_limit)`

**Input:**
- `power_W` (required) — continuous friction power (W)
- `h_W_m2K` (default 15 W/(m²·K) natural convection)
- `delta_T_limit_C` (default 150 °C allowable surface rise)

**Returns:** `area_m2`.

---

### `wear_pv_check`

Check operating pV (pressure × velocity) against friction material catalog limit.

`p = F_a / A_friction`,  `V = π × D × n / 60000`

**Input:**
- `p_MPa` (required) — contact pressure (MPa)
- `V_ms` (required) — rubbing velocity (m/s)
- `material` — friction material name (looks up in built-in catalog; default `organic_dry`)

**Returns:** `pV_MPa_ms`, `pV_limit_MPa_ms`, `ok` (bool), `material_props`.

---

### `engagement_time`

Synchronisation time and slip energy during engagement.

`t_sync = I × Δω / T_clutch`;  `E_slip = 0.5 × I × Δω²`

**Input:**
- `I_kgm2` (required), `omega1_rads` (required), `omega2_rads` (required),
  `T_clutch_Nm` (required)

**Returns:** `t_sync_s`, `E_slip_J`, `average_slip_power_W`.

---

### `friction_material_props`

Look up coefficient of friction μ, max pV, and max operating temperature for a named
friction material.

**Input:**
- `material` (required) — e.g. `organic_dry`, `organic_wet`, `sintered_dry`,
  `sintered_wet`, `paper_wet`, `ceramic_dry`

**Returns:** `mu`, `max_pV_MPa_ms`, `max_temp_C`, `material`.

---

## Example

```
1. friction_material_props  material:"organic_dry"
   → mu:0.35  max_pV_MPa_ms:1.75  max_temp_C:250

2. disc_clutch_torque  F_a:5000  mu:0.35  r_o:0.15  r_i:0.08  n_plates:2
   → torque_Nm:248  r_eff_m:0.115

3. engagement_energy  I_kgm2:0.5  omega1_rads:104.7  omega2_rads:0
   → energy_kJ:2.74

4. temperature_rise  energy_J:2740  mass_kg:2.0
   → delta_T_C:2.98

5. engagement_time  I_kgm2:0.5  omega1_rads:104.7  omega2_rads:0  T_clutch_Nm:248
   → t_sync_s:0.211
```
