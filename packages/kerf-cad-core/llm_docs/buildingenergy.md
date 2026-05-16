# Building Energy & Daylighting

Pure-Python building energy, thermal envelope, daylighting, and ASHRAE compliance tools.
No OCC dependency. All tools are stateless. References: ASHRAE Fundamentals (2021), ASHRAE 90.1-2022,
ISO 6946, ISO 13788, CIBSE Guide A, BRE Digest 309.

---

## When to use

Building energy, U-value, R-value, thermal transmittance, thermal resistance, thermal bridge,
wall assembly, roof assembly, insulation, whole-building UA, balance point temperature, degree day,
HDD, CDD, heating load, cooling load, HVAC sizing, infiltration, blower door test, ACH, air
changes per hour, AIM-2, condensation, Glaser method, interstitial condensation, solar heat gain,
SHGC, shading, overhang, daylight factor, window-to-floor ratio, no-sky-line, overheating,
energy use intensity EUI, ASHRAE 90.1 compliance, building envelope, building performance.

---

## Tools

### `be_uvalue_series`

Overall U-value and total R-value for series opaque assembly (ISO 6946:2017).
Each layer: `{r}` or `{k, d}`. Include air-film resistances as layers.

**Input:** `layers` (list of layer dicts, required)

**Returns:** `U_W_m2K`, `R_total_m2KW`

---

### `be_uvalue_parallel`

Area-weighted parallel U-value for mixed heat-flow paths (ISO 6946:2017 §6.9).

**Input:** `fractions_and_uvalues` (list of `[area_fraction, U]` pairs, required)

**Returns:** `U_parallel_W_m2K`

---

### `be_uvalue_bridged`

Combined U-value with thermal bridges (fractional-area method).
U_combined = (1 − bridge_fraction) × U_clear + bridge_fraction × U_bridge.

**Input:** `U_clear` (required), `U_bridge` (required), `bridge_fraction` (required)

**Returns:** `U_combined_W_m2K`

---

### `be_whole_building_ua`

Whole-building UA coefficient (W/K) from list of envelope surfaces.
UA = Σ (A_i × U_i).

**Input:** `surfaces` (list of `{area_m2, U}` dicts, required)

**Returns:** `UA_W_per_K`, `total_area_m2`, `mean_U`

---

### `be_balance_point_temperature`

Balance-point temperature: T_balance = T_indoor − Q_internal / UA.

**Input:** `T_indoor_C` (required), `internal_gains_W` (required), `ua_W_per_K` (required)

**Returns:** `T_balance_C`

---

### `be_degree_day_energy`

Annual heating or cooling energy from degree-days.
E = UA × DD × 24 / efficiency / 1000 (kWh).

**Input:** `HDD_or_CDD` (required), `UA_W_per_K` (required),
`mode` (`'heating'`/`'cooling'`, default `'heating'`), `efficiency` (default 0.9)

**Returns:** `E_kWh`

---

### `be_annual_fuel_cost`

Annual fuel or electricity cost from energy demand.
Supports: `electricity`, `natural_gas`, `propane`, `oil`.

**Input:** `energy_kWh` (required), `fuel_type` (required), `price_per_unit` (required)

**Returns:** `annual_cost`, `fuel_units_required`

---

### `be_design_heating_load`

Design heating load (W): Q = (UA_env + UA_inf + UA_vent) × ΔT − Q_internal.

**Input:** `surfaces` (list, required), `T_indoor_C` (required), `T_outdoor_C` (required),
`infiltration_W_per_K`, `ventilation_W_per_K`, `internal_gains_W`

**Returns:** `Q_heating_W`, component breakdown

---

### `be_design_cooling_load`

Design cooling load (W) including envelope, infiltration, internal, solar, and latent gains.

**Input:** `surfaces` (list, required), `T_indoor_C` (required), `T_outdoor_C` (required),
`infiltration_W_per_K`, `ventilation_W_per_K`, `internal_gains_W`, `solar_gain_W`, `latent_gain_W`

**Returns:** `Q_cooling_W`, component breakdown

---

### `be_infiltration_ach_blower_door`

Natural infiltration ACH from blower-door test at 50 Pa.
ACH_nat = ACH50 / n. Typical n: 20 (tight), 17 (average), 10 (leaky).

**Input:** `ACH50` (required), `n` (default 20)

**Returns:** `ACH_nat`

---

### `be_infiltration_ach_aim2`

Infiltration ACH using AIM-2/LBL model (stack + wind effects combined).

**Input:** `floor_area_m2`, `height_m`, `C_i` (leakage coefficient), `n_exp` (pressure exponent),
`delta_T_C`, `wind_speed_m_s` (all required), `terrain_class` (default `'suburban'`)

**Returns:** `ACH_nat`, `Q_total_m3s`

---

### `be_glaser_condensation`

Glaser dew-point interstitial condensation check (ISO 13788). Each layer: `{name, d_m, k_W_mK, mu}`.

**Input:** `layers` (list, required), `T_inside_C` (required), `T_outside_C` (required),
`RH_inside` (required), `RH_outside` (required)

**Returns:** per-interface temperatures and dew points, `condensation_risk` (bool), risk locations

---

### `be_solar_heat_gain`

Instantaneous solar heat gain through glazing.
Q = area × SHGC × IAM × irradiance × shading_factor.

**Input:** `area_m2` (required), `SHGC` (required), `irradiance_W_m2` (required),
`incidence_angle_deg`, `shading_factor`, `b0`

**Returns:** `Q_solar_W`

---

### `be_shading_projection_factor`

Fraction of window area shaded by horizontal overhang.

**Input:** `overhang_depth_m`, `window_height_m`, `solar_altitude_deg`,
`solar_azimuth_deg`, `facade_azimuth_deg` (all required)

**Returns:** `shaded_fraction`

---

### `be_daylight_factor`

Average daylight factor (DF) via BRE simplified formula.
DF = Tv × A_w × θ / (A_floor × (1 − R̄²)).

**Input:** `window_area_m2` (required), `floor_area_m2` (required), `Tv` (required),
`room_depth_m`, `room_width_m`, `reflectance_avg`, `sky_component_fraction`

**Returns:** `DF_pct`, warnings if DF < 2% or > 5%

---

### `be_window_to_floor_ratio`

Window-to-floor ratio WFR = window_area / floor_area.
Warnings for WFR < 0.10 (under-glazed) or > 0.40 (over-glazed).

**Input:** `window_area_m2` (required), `floor_area_m2` (required)

**Returns:** `WFR`

---

### `be_no_sky_line_depth`

No-sky-line depth from window (BRE Digest 309).
depth = multiplier × window_head_height.

**Input:** `window_head_height_m` (required), `multiplier` (default 2.0)

**Returns:** `no_sky_line_depth_m`

---

### `be_overheating_hours`

Overheating hours from hourly outdoor temperatures (CIBSE TM52 simplified).
T_indoor_h = T_outdoor_h + (Q_int + Q_solar) / UA.

**Input:** `internal_gains_W` (required), `solar_gain_W` (required), `UA_W_per_K` (required),
`T_outdoor_C_list` (list of hourly temps, required), `T_comfort_max_C` (required)

**Returns:** `overheating_hours`, `total_hours`, `overheating_fraction`

---

### `be_eui`

Energy Use Intensity: EUI = annual_energy_kWh / floor_area_m2.

**Input:** `annual_energy_kWh` (required), `floor_area_m2` (required)

**Returns:** `EUI_kWh_m2_yr`

---

### `be_ashrae901_envelope_compliance`

Check proposed assembly against ASHRAE 90.1-2022 prescriptive maximum U-value (or F-factor
for slab-on-grade) for a climate zone.

**Input:** `assembly_type` (`'roof'`/`'wall_above_grade'`/`'floor'`/`'window_vertical'`/
`'door_opaque'`/`'slab_on_grade'`, required), `climate_zone` (int 1–8, required),
`U_proposed`, `F_proposed` (slab only)

**Returns:** `compliant` (bool), `U_limit`, `margin`

---

## Example

```
1. be_uvalue_series
     layers: [{r:0.13}, {k:0.04, d:0.12}, {k:0.8, d:0.1}, {r:0.04}]
   → U_W_m2K: 0.27  R_total_m2KW: 3.7

2. be_design_heating_load
     surfaces:[{area_m2:200, U:0.27},{area_m2:50, U:1.4}]
     T_indoor_C:21  T_outdoor_C:-5
   → Q_heating_W: 5200

3. be_degree_day_energy  HDD_or_CDD:2800  UA_W_per_K:210  efficiency:0.92
   → E_kWh: 15900

4. be_ashrae901_envelope_compliance
     assembly_type:"wall_above_grade"  climate_zone:5  U_proposed:0.28
   → compliant: true
```
