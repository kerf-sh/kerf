# Hydropower Plant & Turbine Engineering

Pure-Python IEC 60193 / Warnick hydropower engineering tools. No OCC dependency. All tools are
stateless — they compute and return results; no DB write. Units: SI (m, m³/s, W, Pa).

---

## When to use

Hydroelectric, hydro plant, turbine selection, Pelton, Francis, Kaplan, Kaplan turbine, Bulb turbine,
Turgo, Crossflow, penstock sizing, penstock friction, penstock wall thickness, water hammer,
Joukowsky pressure, surge tank, cavitation, Thoma sigma, runaway speed, flow-duration curve,
annual energy, micro-hydro, run-of-river, small hydro, hydropower design.

---

## Tools

### `hydro_plant_power`

Compute hydropower shaft power and hydraulic power.

**Input:** `Q` (m³/s, required), `H_net` (m, required), `eta` (default 0.88), `rho` (default 1000)

**Returns:** `P_hydraulic_W`, `P_shaft_W`, `P_shaft_kW`, `P_shaft_MW`

---

### `hydro_turbine_type`

Select turbine type from net head, flow, and optionally runner speed using IEC dimensionless
specific speed Ns or head-range heuristics.

**Input:** `H_net` (m, required), `Q` (m³/s, required), `n_rpm` (optional), `P_kW` (optional)

**Returns:** `turbine_type`, `Ns`, `alternatives`, `head_range_ok`, `warnings`

---

### `hydro_runner_speed`

Estimate runner design speed via n ≈ K·√H (rpm). K factors by type: Pelton 30, Francis 50, Kaplan 150.

**Input:** `H_net` (m, required), `turbine_type` (default `'Francis'`)

**Returns:** `n_rpm_approx`, `K_used`

---

### `hydro_sync_speed_poles`

Find nearest synchronous generator speeds and pole counts for grid coupling.
n_sync = 120·f / p.

**Input:** `n_runner_rpm` (required), `f_hz` (default 50)

**Returns:** `poles_lower`, `n_sync_lower_rpm`, `poles_higher`, `n_sync_higher_rpm`

---

### `hydro_penstock_diameter`

Economic penstock diameter from flow and target velocity. D = √(4·Q / (π·V_economic)).

**Input:** `Q` (m³/s, required), `V_economic` (m/s, default 3.0)

**Returns:** `D_m`, `A_m2`

---

### `hydro_penstock_friction`

Darcy-Weisbach friction head loss. h_f = f·(L/D)·(V²/2g).

**Input:** `Q` (required), `D` (m, required), `L` (m, required), `f` (default 0.015)

**Returns:** `h_f_m`, `V_m_s`, `Re_approx`

---

### `hydro_penstock_wall`

Minimum penstock wall thickness via Barlow thin-wall formula.
t = P·D / (2·σ_allow·e) + corrosion_allowance.

**Input:** `D` (m, required), `P_internal_Pa` (required), `sigma_allow_Pa` (default 120 MPa),
`weld_efficiency` (default 0.85), `corrosion_mm` (default 2.0)

**Returns:** `t_calc_mm`, `t_total_mm`

---

### `hydro_water_hammer_joukowsky`

Joukowsky rapid-closure water-hammer pressure rise. ΔP = ρ·a·ΔV.

**Input:** `V` (m/s, required), `a_wave` (m/s, required), `rho` (default 1000)

**Returns:** `dP_Pa`, `dP_bar`, `dH_m`

---

### `hydro_water_hammer_allievi`

Allievi finite-closure water-hammer. Slow (Michaud) vs rapid (Joukowsky) regime selected from
T_critical = 2L/a.

**Input:** `H_static` (m, required), `V` (required), `a_wave` (required), `L` (required),
`T_close` (s, required), `rho` (default 1000)

**Returns:** `T_critical_s`, `regime`, `dH_max_m`, `H_total_max_m`, `overpressure_ratio`, `warnings`

---

### `hydro_surge_tank`

Surge-tank sizing using Thoma stability criterion.
A_Thoma = A_pipe·L / (2·H_friction_effective).

**Input:** `Q`, `a_wave`, `L`, `H_net`, `D_penstock` (all required), `max_upsurge_m` (optional)

**Returns:** Thoma area, oscillation period, energy-balance area (if `max_upsurge_m` given)

---

### `hydro_thoma_cavitation`

Thoma cavitation check. σ_plant = (H_atm − H_vapor − H_s) / H_net vs σ_crit (Gordon 1999).

**Input:** `H_net` (required), `H_s` (draft head, required), `turbine_type`, `n_rpm`, `Q`,
`P_vapor_Pa`, `P_atm_Pa`, `elevation_m`

**Returns:** `sigma_plant`, `sigma_crit`, `cavitation_risk`

---

### `hydro_runaway_speed`

Turbine runaway (load-rejection) speed. Multipliers: Pelton 1.8×, Kaplan 2.3×, Francis 1.8×.

**Input:** `n_rpm` (required), `turbine_type` (default `'Francis'`)

**Returns:** `n_runaway_rpm`, `runaway_factor`

---

### `hydro_flow_duration_energy`

Annual energy from a discretised flow-duration curve.

**Input:** `flow_fractions` (list, required), `Q_design` (required), `H_net` (required),
`eta` (default 0.88)

**Returns:** `E_annual_MWh`, `capacity_factor`, `plant_factor`, `hours_generating`, `spill_fraction`

---

### `hydro_pelton_jet`

Pelton jet and bucket sizing. V_jet = Cv·√(2·g·H_net); d_jet = √(4·Q / (n_jets·π·V_jet)).

**Input:** `H_net` (required), `Q` (required), `n_jets` (default 1), `Cv` (default 0.97),
`D_runner_m` (optional)

**Returns:** `V_jet_m_s`, `d_jet_m`, `B_bucket_m`, `u_opt_m_s`, `n_opt_rpm` (if D_runner given)

---

### `hydro_micro_quick`

Quick-sizing utility for micro-hydro plants (< 100 kW). Auto-sizes penstock, estimates friction,
returns net head, shaft power, and turbine type.

**Input:** `H_gross` (m, required), `Q` (required), `penstock_length` (default 0),
`eta_overall` (default 0.70)

**Returns:** `H_net_m`, `P_shaft_kW`, `turbine_type`, `D_penstock_m`

---

## Example

```
1. hydro_turbine_type  H_net:45  Q:8.5
   → turbine_type: "Francis"  Ns: 120

2. hydro_plant_power  Q:8.5  H_net:45  eta:0.88
   → P_shaft_kW: 3300

3. hydro_penstock_diameter  Q:8.5  V_economic:4.0
   → D_m: 1.64

4. hydro_water_hammer_allievi  H_static:45  V:4.0  a_wave:1200  L:300  T_close:5.0
   → regime: "slow"  dH_max_m: 18.3  overpressure_ratio: 0.41
```
