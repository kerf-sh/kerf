# Electronics Reliability Prediction

MIL-HDBK-217F parts-count and part-stress FIT/MTBF prediction, Arrhenius
and Peck accelerated-life factors, Coffin-Manson solder-joint fatigue,
voltage acceleration, derating checks, bathtub hazard rate, redundancy
MTBF, Chi-square MTBF confidence bounds, and duty-cycle FIT adjustment.

## When to use

Reliability, FIT, failure rate, MTBF, mean time between failures,
MIL-HDBK-217F, 217F, parts count, part stress, Arrhenius, activation energy,
HALT, HASS, ALT, accelerated life test, Coffin-Manson, solder joint fatigue,
thermal cycling, Peck model, humidity acceleration, voltage acceleration,
derating, bathtub curve, infant mortality, wear-out, Weibull, redundancy,
active redundancy, standby redundancy, Chi-square confidence, MTBF demo test,
duty cycle, power-on hours, Telcordia SR-332.

## Tools

### `eerel_mil217f_parts_count`
MIL-HDBK-217F parts-count prediction: λ = Σ Ni·λg·πQ·πE for a full BOM.
Inputs: `parts` list (each: `type`, optional `count`, `quality`); optional `environment`, `quality`.
Returns `fit_total`, `mtbf_hours`, `part_breakdown`, `warnings`.

### `eerel_mil217f_part_stress`
MIL-HDBK-217F part-stress for a single component: λ_p = λ_b·πT·πS·πE·πQ·πA.
Inputs: `part_type`, `tj_c`; optional `voltage_stress`, `power_stress`, `environment`, `quality`, `pi_a`.
Returns `fit`, `pi_t`, `pi_s`, `pi_e`, `pi_q`, `pi_a`, `warnings`.

### `eerel_board_fit_mtbf`
Aggregate part-stress predictions across all board components.
Inputs: `parts` list (each may include `type`, `count`, `quality`, `tj_c`, stresses); optional `environment`.
Returns `fit_total`, `mtbf_hours`, `part_breakdown`, `warnings`, `telcordia_note`.

### `eerel_arrhenius_af`
Arrhenius acceleration factor for ALT/HALT: AF = exp(Ea/k·(1/T_use − 1/T_test)).
Inputs: `t_use_c`, `t_test_c`; optional `ea_ev` (default 0.7 eV).
Returns `acceleration_factor`, `ea_ev`.

### `eerel_coffin_manson`
Solder-joint cycles-to-failure via Coffin-Manson: Nf = C_f / ΔT^m.
Inputs: `delta_t_c`; optional `c_f`, `m`, `f_cyc_per_day`.
Returns `nf_cycles`, `lifetime_years`.

### `eerel_peck_humidity`
Peck model humidity + temperature acceleration factor.
AF = (RH_test/RH_use)^n_rh × exp(Ea/k·(1/T_use − 1/T_test)).
Inputs: `rh_use`, `rh_test`, `t_use_c`, `t_test_c`; optional `ea_ev`, `n_rh`.
Returns `acceleration_factor`, `humidity_factor`, `thermal_factor`.

### `eerel_voltage_acceleration`
Voltage acceleration factor for dielectric/oxide wear-out: AF = (V_test/V_use)^β.
Inputs: `v_use`, `v_test`; optional `beta` (default 2.5).
Returns `acceleration_factor`, `v_use`, `v_test`, `beta`, `warnings`.

### `eerel_derating_check`
Check voltage/power/temperature/current stress ratios against derating limits.
Inputs: `part_type`; optional stress ratios (`voltage_ratio`, `power_ratio`, etc.).
Returns `compliant`, `violations`, `limits`, `warnings`.

### `eerel_bathtub`
Bathtub λ(t) hazard rate from superimposed infant-mortality + random + wear-out Weibull.
Input: `t_hours`; optional phase parameters.
Returns `lambda_fit`, `phase`.

### `eerel_redundancy_mtbf`
System MTBF for active (parallel) or standby redundancy.
Inputs: `fit_per_unit`; optional `n_active`, `redundancy_type`, `switch_reliability`.
Returns `mtbf_unit_hours`, `mtbf_system_hours`.

### `eerel_mtbf_confidence`
One-sided MTBF Chi-square confidence bound from demonstration test data (MIL-HDBK-781A).
Inputs: `total_hours`, `n_failures`; optional `confidence`, `bound`.
Returns `mtbf_bound_hours`, `confidence`, `bound`, `chi2`, `df`.

### `eerel_duty_cycle_fit`
Adjust rated FIT and MTBF for partial power-on duty cycle.
Inputs: `fit_rated`, `duty_cycle`; optional `calendar_hours_per_year`.
Returns `fit_adjusted`, `mtbf_calendar_hours`, `mtbf_calendar_years`.

## Example

Quick parts-count prediction for a commercial-grade board in a ground-fixed
environment with 10 resistors, 20 capacitors, and 5 digital ICs:

```json
{
  "tool": "eerel_mil217f_parts_count",
  "parts": [
    {"type": "resistor", "count": 10},
    {"type": "capacitor", "count": 20},
    {"type": "ic_digital", "count": 5}
  ],
  "environment": "GF",
  "quality": "commercial"
}
```
