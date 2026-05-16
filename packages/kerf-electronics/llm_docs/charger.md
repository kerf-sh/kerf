# Battery Charger & BMS Design

CC-CV charge profiling, charger power and thermal analysis, passive and active
cell balancing, coulomb-counting SOC, state-of-health estimation, BMS protection
thresholds, cell matching, and MPPT solar charging.

## When to use

Battery charger, CC-CV, constant current, constant voltage, lithium ion, li-ion,
LiFePO4, NiMH, lead-acid, charge time, C-rate, cell balancing, passive balance,
active balance, BMS, battery management system, SOC, state of charge, coulomb
counting, OCV blend, state of health, capacity fade, resistance growth, cycle count,
over-voltage protection, under-voltage protection, over-current protection,
over-temperature protection, short circuit, hysteresis, cell matching, capacity
spread, tolerance, MPPT, maximum power point tracking, solar charge, peak sun hours,
battery efficiency, charger thermal.

## Tools

### `charger_cc_cv_profile`
CC-CV charge profile for a cell or pack: CC time, CV time, total charge time, and pack voltage.
Supports li-ion, lifepo4, nimh, lead-acid; applies lead-acid temperature compensation (−4 mV/°C/cell).
Inputs: `capacity_ah`; optional `chemistry`, `n_cells_series`, `dod`, `cc_fraction`, `cv_cutoff_fraction`, `v_max_override_v`, `t_cell_c`.
Returns `i_cc_a`, `t_cc_h`, `t_cv_h`, `total_time_h`, `v_max_pack_v`, `charge_accepted_ah`.

### `charger_power`
Charger output power, input power, conversion loss, and junction temperature.
Inputs: `v_bat_v`, `i_charge_a`; optional `efficiency`, `rth_c_a_k_per_w`, `t_ambient_c`.
Returns `p_out_w`, `p_in_w`, `p_loss_w`, `efficiency`, `t_junction_c`.

### `charger_passive_balance`
Passive bleed-resistor cell balancing: bleed current, power dissipation, and equalisation time.
Inputs: `v_high_v`, `v_low_v`, `cell_capacity_ah`, `r_bleed_ohm`.
Returns `delta_v_v`, `i_bleed_a`, `p_bleed_w`, `balance_time_h`, `balance_time_min`.

### `charger_active_balance`
Active cell balancing: charge-transfer time and energy loss for inductor/flying-cap/transformer topologies.
Inputs: `v_high_v`, `v_low_v`, `cell_capacity_ah`, `transfer_current_a`; optional `efficiency`.
Returns `dq_ah`, `transfer_time_h`, `energy_loss_wh`.

### `charger_coulomb_soc`
State-of-charge from coulomb counting with optional OCV-blend correction and drift budget.
Inputs: `soc_init`, `charge_ah`, `capacity_ah`, `elapsed_h`; optional `drift_fraction_per_hour`, `ocv_soc`, `alpha_ocv`.
Returns `soc_cc`, `drift_budget`, `soc_blend`, `soc_final`.

### `charger_state_of_health`
Capacity fade and resistance growth from cycle count; returns SoH% and cycles remaining to 80% EOL.
Inputs: `q_new_ah`, `r_new_ohm`, `n_cycles`; optional `capacity_fade_per_cycle`, `resistance_growth_per_cycle`.
Returns `q_now_ah`, `r_now_ohm`, `soh_pct`, `cycles_to_80pct`.

### `charger_protection`
BMS protection thresholds (OV/UV/OC/OT/SC) with hysteresis and optional live condition evaluation.
Inputs: `v_ov_trip_v`, `v_uv_trip_v`, `i_oc_trip_a`, `t_ot_trip_c`, `i_sc_trip_a`; optional `hysteresis_v`, `hysteresis_t_c`, `v_cell_v`, `i_cell_a`, `t_cell_c`.
Returns trip and release thresholds; `flags` when live values are supplied.

### `charger_cell_matching`
Usable pack capacity accounting for cell-to-cell capacity spread; weakest cell limits the string.
Inputs: `q_nominal_ah`, `tolerance_fraction`; optional `n_series`, `n_parallel`.
Returns `q_cell_usable_ah`, `q_pack_usable_ah`, `energy_loss_fraction`, `usable_fraction`.

### `charger_mppt_solar`
MPPT solar-charge operating point, daily energy delivered, and ΔSOC with panel temperature derating.
Inputs: `v_mpp_v`, `i_mpp_a`, `peak_sun_hours`, `v_bat_v`, `capacity_ah`; optional `soc_init`, `t_panel_c`, `isc_temp_coeff_per_c`, `mppt_efficiency`.
Returns `p_mppt_w`, `p_mppt_to_bat_w`, `e_day_wh`, `delta_soc`, `soc_end`.

## Example

Compute CC-CV charge profile for a 3S li-ion pack with 5 Ah cells, 80% DOD:

```json
{
  "tool": "charger_cc_cv_profile",
  "capacity_ah": 5,
  "chemistry": "li-ion",
  "n_cells_series": 3,
  "dod": 0.8
}
```
