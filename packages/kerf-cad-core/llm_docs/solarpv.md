# Solar PV System Sizing

Pure-Python photovoltaic system sizing and solar geometry tools. No OCC
dependency. All tools are stateless. Units: W, kWh, kWp, m², degrees, hours.

---

## When to use

Use these tools when the conversation involves: solar panels, PV system, solar
power, solar energy, photovoltaic, PV array, solar irradiance, plane of array,
POA, tilt angle, azimuth, peak sun hours, battery bank, off-grid, on-grid,
inverter sizing, DC/AC ratio, string sizing, module voltage, MPPT, row spacing,
inter-row shading, ground cover ratio, GCR, annual yield, specific yield,
performance ratio, solar position, sunrise, sunset, day length, cable sizing,
voltage drop, energy storage, autonomy.

---

## Tools

### `pv_solar_position`

Calculate solar altitude, azimuth, and zenith angle.

**Input:** `latitude_deg` (+N/−S), `day_of_year` (1–365), `solar_time_h`
(decimal hours, 12.0 = solar noon).

**Returns:** `altitude_deg`, `azimuth_deg` (from south, +east), `zenith_deg`.

---

### `pv_sunrise_sunset`

Sunrise/sunset solar hour angles, solar times, and day length.

**Input:** `latitude_deg`, `day_of_year`.

**Returns:** `omega_sunrise_deg`, `omega_sunset_deg`, `sunrise_solar_h`,
`sunset_solar_h`, `day_length_h`.

---

### `pv_poa_irradiance`

Plane-of-array (POA) irradiance using isotropic-sky (Liu & Jordan) model.

**Input:** `ghi`, `dni`, `dhi` (W/m²), `tilt_deg`, `azimuth_deg`,
`solar_altitude_deg`, `solar_azimuth_deg`; optional `albedo` (default 0.2).

**Returns:** `beam_W_m2`, `diffuse_W_m2`, `reflected_W_m2`, `total_W_m2`, `R_b`.

---

### `pv_optimal_tilt`

Rule-of-thumb optimal fixed-tilt angle for maximum annual yield.

**Input:** `latitude_deg`.

**Returns:** `tilt_deg`, `faces` (`"south"` or `"north"`), confidence note.

---

### `pv_array_size`

Required DC array peak power from daily load and peak sun hours.

**Input:** `daily_load_kWh`, `peak_sun_hours`, `derate_pr`; optional
`safety_factor` (default 1.25).

**Returns:** `array_kWp` and input echoes.

---

### `pv_module_string_sizing`

Size PV module strings (series/parallel) versus inverter limits, with
temperature-corrected Voc/Vmp.

**Input:** `modules` object (`voc_v`, `vmp_v`, `isc_a`, `imp_a`, `pmax_w`,
`beta_voc`, `gamma_pmax`), `inverter` object (`vdc_max_v`, `mppt_vmin_v`,
`mppt_vmax_v`, `idc_max_a`); optional `t_min_c` (default −10°C),
`t_max_c` (default 70°C).

**Returns:** `modules_per_string`, `strings_in_parallel`, cold/hot voltages,
`total_kWp`, warnings (flags overvoltage).

---

### `pv_inverter_dc_ac_ratio`

Check inverter DC/AC clipping ratio.

**Input:** `array_kWp`, `inverter_kVAc`; optional `min_ratio` (default 1.0),
`max_ratio` (default 1.35).

**Returns:** `dc_ac_ratio`, `status` (`"ok"`, `"undersized"`, or `"oversized"`).

---

### `pv_battery_bank`

Off-grid battery bank sizing for given autonomy and depth of discharge.

**Input:** `daily_load_kWh`, `autonomy_days`, `dod_fraction`, `system_voltage_v`;
optional `cell_ah` (default 100 Ah), `efficiency` (default 0.85),
`safety_factor` (default 1.1).

**Returns:** `gross_kWh`, `usable_kWh`, `bank_ah`, `cells_series`,
`strings_parallel`, `total_cells`, warnings.

---

### `pv_cable_sizing`

Minimum DC cable cross-section (mm²) for allowable voltage drop.

**Input:** `current_a`, `length_m`, `voltage_v`, `max_drop_pct`; optional
`temperature_c` (default 75°C).

**Returns:** `min_mm2`, `standard_mm2` (next IEC size), `actual_drop_pct`,
warnings.

---

### `pv_energy_yield`

Annual and lifetime PV system energy yield with annual degradation.

**Input:** `array_kWp`, `poa_annual_kWh_m2`, `pr`; optional
`degradation_rate` (default 0.005 = 0.5%/yr), `years` (default 25).

**Returns:** `annual_yield_yr1_kWh`, `specific_yield_kWh_kWp`,
`lifetime_yield_kWh`, `performance_ratio`.

---

### `pv_row_spacing`

Minimum row pitch and ground-cover ratio (GCR) for no inter-row shading.

**Input:** `module_length_m`, `tilt_deg`, `latitude_deg`; optional `gcr`
(if given, derives pitch from GCR), `winter_margin_h` (default 3 h from solar noon).

**Returns:** `row_pitch_m`, `gcr`, `module_horizontal_m`, `shadow_length_m`,
`min_solar_altitude_deg`.

---

## Example

```
1. pv_optimal_tilt  latitude_deg:-26.0
   → tilt_deg: 26, faces:"north"

2. pv_array_size  daily_load_kWh:20  peak_sun_hours:5.5  derate_pr:0.78
   → array_kWp: 5.84

3. pv_module_string_sizing
     modules:{voc_v:40.5,vmp_v:33.8,isc_a:9.8,imp_a:9.2,pmax_w:310,beta_voc:-0.003}
     inverter:{vdc_max_v:550,mppt_vmin_v:100,mppt_vmax_v:520,idc_max_a:25}
   → modules_per_string:13, strings_in_parallel:2, total_kWp:8.06
```
