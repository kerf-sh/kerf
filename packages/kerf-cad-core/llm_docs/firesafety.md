# Fire Safety & Fire Protection Engineering

Pure-Python fire protection engineering tools. No OCC dependency. All tools are stateless.
References: NFPA 13, NFPA 20, NFPA 92, NFPA 101, IBC Table 601, SFPE Handbook 5th ed.

---

## When to use

Fire protection, fire sprinkler, sprinkler hydraulic, NFPA 13, sprinkler demand, K-factor,
Hazen-Williams, fire pump, NFPA 20, pump sizing, water supply, hydrant flow test, static pressure,
residual pressure, egress, life safety, NFPA 101, occupant load, exit width, travel distance,
common path, dead-end corridor, design fire, t-squared, heat release rate, HRR, detector activation,
ceiling jet, Alpert, RTI, sprinkler activation, smoke control, atrium exhaust, NFPA 92,
Heskestad plume, fire resistance, ASTM E119, fire rating, IBC occupancy, required fire rating.

---

## Tools

### `sprinkler_hydraulic_demand`

NFPA 13 density/area sprinkler hydraulic demand. Uses K = Q/√P, Hazen-Williams friction,
and hose-stream allowance to determine required source pressure.

**Input:** `occupancy_class` (`'light_hazard'`/`'ordinary_hazard_group_1'`/`'ordinary_hazard_group_2'`/
`'extra_hazard_group_1'`/`'extra_hazard_group_2'`, required), `k_factor` (gpm/psi^0.5, required),
`pipe_d_inch` (required), `pipe_length_ft` (required), `elevation_diff_ft`,
`density_override`, `area_override`, `hw_coeff` (default 120)

**Returns:** `Q_total_gpm`, `P_required_psi`, `design_density`, `design_area_ft2`, warnings

---

### `fire_pump_sizing`

NFPA 20 fire pump three-point curve: rated, 150% flow, and churn/shutoff points.

**Input:** `rated_flow_gpm` (required), `rated_head_psi` (required)

**Returns:** rated/150%/churn points with flow, pressure, and pass/fail flags

---

### `water_supply_adequacy`

Available water supply vs system demand from hydrant flow test data.
Supply curve: P(Q) = P_static − (P_static − P_residual) × (Q/Q_residual)^1.85.

**Input:** `static_pressure_psi` (required), `residual_pressure_psi` (required),
`residual_flow_gpm` (required), `required_flow_gpm` (required), `required_pressure_psi` (required)

**Returns:** `available_pressure_psi`, `adequate` (bool), `margin_psi`

---

### `egress_analysis`

NFPA 101 egress analysis: occupant load, exit count, exit width capacity, travel distance,
common path, dead-end limits, and time-to-egress estimate.

**Input:** `floor_area_ft2` (required), `occupancy_type` (required), `num_exits` (required),
`exit_widths_in` (list, required), `travel_distance_ft` (required),
`common_path_ft`, `dead_end_ft`, `exit_component` (`'stair'`/`'level'`)

**Returns:** `occupant_load`, `exit_capacity`, `travel_ok`, `common_path_ok`, `dead_end_ok`,
`time_to_egress_min`, code violation flags

---

### `design_fire_tsquared`

t-squared design fire HRR: Q = α × t². Growth classes (NFPA 92): `slow`, `medium`, `fast`,
`ultra_fast`. Time to 1 MW: 600 s / 300 s / 150 s / 75 s respectively.

**Input:** `time_s` (required), `growth_class` (default `'medium'`),
`alpha_override` (kW/s²), `max_hrr_kw` (optional cap)

**Returns:** `HRR_kW`, `alpha_kW_s2`, `time_to_1MW_s`

---

### `detector_activation_time`

Sprinkler/detector activation time via Alpert ceiling-jet correlations and RTI model.

**Input:** `hrr_kw` (required), `ceiling_height_m` (required), `radial_distance_m` (required),
`rti` (m^0.5·s^0.5, required), `detector_temp_c` (required), `ambient_temp_c` (default 20)

**Returns:** `ceiling_jet_temp_C`, `ceiling_jet_velocity_m_s`, `t_activation_s`, warnings

---

### `smoke_control_exhaust`

NFPA 92 atrium smoke exhaust from Heskestad axisymmetric plume model.
Computes plume mass flow at design smoke-layer interface height.

**Input:** `hrr_kw` (required), `atrium_height_m` (required), `smoke_layer_height_m` (required)

**Returns:** `exhaust_cfm`, `exhaust_m3s`, `plume_mass_flow_kg_s`, warnings

---

### `fire_resistance_heat_transfer`

1-D steady-state heat transfer through fire-rated assembly.
Checks ASTM E119 unexposed-surface limit: ambient + 139°C.

**Input:** `assembly_layers` (list of `{name, thickness_mm, conductivity_W_mK}`, required),
`fire_side_temp_c` (default 927, ASTM E119 @ 60 min), `ambient_temp_c` (default 20)

**Returns:** `T_unexposed_C`, `passes_E119` (bool), per-interface temperatures, heat flux

---

### `required_fire_rating`

Minimum fire-resistance rating (hours) by occupancy and building height (IBC Table 601).
Optional 1-hour sprinkler credit per IBC §504.

**Input:** `occupancy_group` (`'assembly'`/`'business'`/`'educational'`/`'healthcare'`/
`'industrial'`/`'mercantile'`/`'residential'`/`'storage'`/`'high_hazard'`, required),
`building_height_stories` (int, required), `sprinklered` (default false)

**Returns:** `bearing_wall_hr`, `non_bearing_wall_hr`, `floor_ceiling_hr`, notes

---

## Example

```
1. design_fire_tsquared  time_s:300  growth_class:"fast"
   → HRR_kW: 4220  time_to_1MW_s: 150

2. smoke_control_exhaust  hrr_kw:4220  atrium_height_m:15  smoke_layer_height_m:6
   → exhaust_cfm: 112000  exhaust_m3s: 52.8

3. detector_activation_time
     hrr_kw:1000  ceiling_height_m:4  radial_distance_m:2.5
     rti:80  detector_temp_c:74
   → t_activation_s: 38

4. egress_analysis
     floor_area_ft2:8000  occupancy_type:"business"  num_exits:2
     exit_widths_in:[44,44]  travel_distance_ft:180
   → occupant_load:80  exit_capacity:293  travel_ok:true
```
