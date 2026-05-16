# Electrical Power Distribution (NEC)

Pure-Python NEC power-distribution engineering module covering demand load
calculation, conductor sizing, voltage drop, conduit fill, overcurrent devices,
motor branch circuits, transformer feeders, short-circuit analysis,
power-factor correction, grounding, panel schedules, and generator sizing.
References NFPA 70 (NEC 2023).

---

## When to use

Reach for this module when the user asks about:

- feeder or service demand load per NEC Art. 220
- conductor ampacity (NEC 310.16) with ambient derating and bundling
- minimum conductor size for a given load or continuous load
- voltage drop check for a branch circuit or feeder; upsize recommendation
- conduit fill percentage (NEC Ch. 9 Table 1)
- overcurrent device (breaker or fuse) sizing per NEC 240.4
- motor branch circuit conductor, OCPD, and overload sizing (NEC Art. 430)
- transformer primary/secondary feeder and OCPD sizing (NEC Art. 450)
- point-to-point short-circuit analysis and required AIC rating
- kVAR and capacitor sizing for power-factor correction
- GEC (NEC 250.66) or EGC (NEC 250.122) sizing
- panel schedule rollup, main breaker, and feeder conductor
- standby generator or UPS kVA sizing with motor starting surge

---

## Tools

### `elecpower_demand_load`

Calculate feeder/service demand load per NEC Art. 220. Applies 125% continuous
factor (NEC 215.2) and optional dwelling demand factors (NEC Table 220.42).
Inputs: `loads` list [{va, continuous, name}] (required); optional `occupancy`
(dwelling/commercial/industrial), `continuous_factor`.
Returns: `demand_va`, `continuous_va`, `noncontinuous_demand_va`.

### `elecpower_conductor_ampacity`

Derated conductor ampacity per NEC 310.16 75°C column. Applies ambient
temperature correction and bundling adjustment factors.
Inputs: `size` (required, e.g. '12', '4/0', '250' kcmil); optional `material`
(cu/al), `ambient_c`, `num_ccc`.
Returns: `base_ampacity_A`, `ambient_correction`, `bundling_factor`,
`derated_ampacity_A`.

### `elecpower_conductor_size`

Select minimum conductor size for a given load current per NEC 310.16,
including derating and optional 125% continuous-load factor.
Inputs: `load_A` (required); optional `material`, `ambient_c`, `num_ccc`,
`continuous`.
Returns: `size`, `required_A`, `derated_ampacity_A`.

### `elecpower_voltage_drop`

Calculate voltage drop for a conductor run and flag if it exceeds the limit.
Formulas: 1φ VD = 2IRL/1000; 3φ VD = √3 × IRL/1000. Suggests upsized
conductor when limit is exceeded.
Inputs: `load_A`, `length_ft`, `size`, `voltage` (required); optional
`phases` (1/3), `material`, `pf`, `vd_limit_pct` (default 3.0%).
Returns: `vd_V`, `vd_pct`, `exceeds_limit`, `upsize_recommendation`.

### `elecpower_conduit_fill`

Calculate conduit fill percentage per NEC Chapter 9. Limits: 53% (1 conductor),
31% (2 conductors), 40% (3+).
Inputs: `conductors` list [{size, material, count}], `conduit_trade_size_in`
(required); optional `conduit_type` (EMT/RMC/IMC/PVC40/PVC80).
Returns: `fill_pct`, `max_fill_pct`, `fill_ok`.

### `elecpower_ocpd_size`

Size overcurrent protection device per NEC 240.4. Selects the next standard
OCPD size (NEC 240.6(A)) at or above derated conductor ampacity.
Inputs: `conductor_size` (required); optional `material`, `load_A`,
`continuous`, `ambient_c`, `num_ccc`.
Returns: `ocpd_A`, `conductor_ampacity_A`, `undersized_conductor`.

### `elecpower_motor_branch`

Size motor branch circuit per NEC Art. 430: conductor ≥ 125% FLC (430.22),
OCPD per Table 430.52, overload per 430.32. Uses NEC 430.248/430.250 FLC tables.
Inputs: `hp`, `voltage` (required); optional `phases`, `service_factor`,
`ocpd_type` (inverse_time_breaker/dual_element_fuse/instantaneous).
Returns: `flc_A`, `conductor_size`, `ocpd_A`, `overload_A`.

### `elecpower_transformer_feeder`

Size transformer primary/secondary feeders and OCPDs per NEC Art. 450 and 215.
Computes primary/secondary FLA, conductor sizes, primary OCPD ≤ 125% FLA
(NEC 450.3(B)), and maximum secondary short-circuit current from %Z.
Inputs: `kva`, `primary_voltage`, `secondary_voltage` (required); optional
`phases`, `impedance_pct`.
Returns: primary and secondary FLA, conductor sizes, OCPD ratings,
`max_secondary_sca_A`.

### `elecpower_short_circuit`

Point-to-point short-circuit analysis (NEC / IEEE 141 Red Book). Computes
transformer secondary bolted fault current from %Z, then reduces it through
cable impedance.
Inputs: `transformer_kva`, `transformer_primary_V`, `transformer_secondary_V`
(required); optional `transformer_z_pct`, `phases`, `cable_length_ft`,
`cable_size`, `cable_material`, `point_name`.
Returns: `isc_transformer_A`, `isc_at_point_A`, `z_transformer_ohms`,
`z_cable_ohms`, `required_aic_A`.

### `elecpower_pf_correction`

Calculate capacitor kVAR for power-factor correction.
Q_correction = P × (tan θ₁ − tan θ₂). Returns bank size rounded to nearest
5 kVAR and capacitance per phase in µF.
Inputs: `load_kw`, `current_pf`, `target_pf`, `voltage` (required); optional
`phases`, `frequency_hz`.
Returns: `kvar_required`, `kvar_bank_size`, `capacitance_uF_per_phase`.

### `elecpower_grounding_conductor`

Size grounding conductors per NEC 250. GEC (250.66) is based on service-entrance
conductor size; EGC (250.122) is based on OCPD rating.
Inputs: `service_conductor_size` (required); optional `ocpd_rating_A`,
`conductor_type` (gec/egc), `material`.
Returns: `size`, `material`, `nec_reference`.

### `elecpower_panel_schedule`

Compile panel/feeder load schedule, apply demand factors, compute feeder amps,
size main breaker, and select feeder conductor per NEC Art. 220.
Inputs: `circuits` list [{va, continuous, name, poles}] (required); optional
`voltage`, `phases`, `include_demand`, `occupancy`.
Returns: `total_connected_va`, `demand_va`, `total_amps`, `main_breaker_A`,
`feeder_conductor_size`.

### `elecpower_generator_size`

Size a standby generator or UPS. Applies demand factor, power factor, motor
starting surge (6× LRC estimate), and spare capacity.
Inputs: `loads` list [{kw, pf, motor_hp, continuous, name}] (required);
optional `demand_factor`, `power_factor`, `include_spare_pct`.
Returns: `total_running_kw`, `running_kva`, `largest_motor_starting_kva`,
`recommended_gen_kva`, `standard_gen_size_kva`.

---

## Example

**User ask:** "I have a 120V single-phase panel with six 15 A circuits (all
continuous) at 1 800 VA each. What feeder size and main breaker do I need?"

1. `elecpower_panel_schedule` — circuits: [{va: 1800, continuous: true} × 6],
   voltage: 120, phases: 1
   → demand_va, total_amps, main_breaker_A, feeder_conductor_size
2. `elecpower_voltage_drop` — load_A from step 1, length_ft: 50, size from
   step 1, voltage: 120, phases: 1
   → confirm vd < 3%
