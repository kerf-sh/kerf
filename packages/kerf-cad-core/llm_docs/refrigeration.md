# Vapor-Compression Refrigeration and Heat Pump Design

Pure-Python vapor-compression refrigeration cycle analysis covering single-stage, two-stage with flash intercooler, cascade cycles (two refrigerants), compressor sizing, superheat/subcooling effects, defrost energy, and pressure ratio checks. Supported refrigerants: R134a, R410A, R717 (ammonia), R744 (CO₂), R290 (propane). No OCC dependency. All tools are stateless and never raise. Reference: ASHRAE Fundamentals Handbook 2021.

---

## When to use

Use these tools for refrigeration and heat-pump engineering: saturation pressure for refrigerants, single-stage vapor-compression cycle COP and mass flow, refrigeration capacity unit conversions (TR/kW/BTU), compressor displacement sizing, effect of suction superheat and liquid subcooling on COP, two-stage compression with flash intercooler (large temperature lifts), cascade cycle for deep freeze below −40°C, defrost energy estimation for cold-room coils, pressure ratio and discharge temperature pre-check.

---

## Tools

### `refrig_saturation_pressure`

Saturation pressure of a refrigerant at a given temperature using fitted Antoine/Clausius-Clapeyron correlations.

**Input:** `T_C` (required); `refrigerant` (optional, default `R134a`; options: `R134a`, `R410A`, `R717`, `R744`, `R290`). **Returns:** `P_sat_Pa`, `T_K`.

---

### `refrig_single_stage_cycle`

Full single-stage vapor-compression cycle analysis: saturation pressures, pressure ratio, refrigerating effect, compressor work (ideal + real via isentropic efficiency), COP cooling and heating, mass flow, volumetric/displacement flow, condenser duty, estimated discharge temperature, capacity in TR.

**Input:** `T_evap_C`, `T_cond_C`, `capacity_W` (required); `refrigerant`, `eta_isentropic` (default 0.75), `superheat_K` (default 5), `subcool_K` (default 3), `eta_volumetric` (default 0.85) (optional). **Returns:** `COP`, `COP_heat`, `mass_flow_kgs`, `power_W`, `condenser_duty_W`, `capacity_TR`, `pressure_ratio`, `discharge_temp_C`, `warnings`.

---

### `refrig_tons_of_refrigeration`

Convert cooling capacity between W, kW, tons of refrigeration (TR), and BTU/h. Provide exactly one non-zero input.

**Input:** `capacity_W`, `capacity_kW`, `capacity_TR`, or `capacity_BTUh` (provide one). **Returns:** all four unit values.

---

### `refrig_compressor_sizing`

Compressor sizing from a single-stage cycle: mass flow, volumetric flow, swept displacement, shaft power, COP, and pressure ratio.

**Input:** `capacity_W`, `T_evap_C`, `T_cond_C` (required); `refrigerant`, `eta_isentropic`, `superheat_K`, `subcool_K`, `eta_volumetric` (optional). **Returns:** `mass_flow_kgs`, `volumetric_flow_m3s`, `displacement_m3s`, `power_W`, `COP`, `pressure_ratio`.

---

### `refrig_superheat_subcool_effect`

Quantify the effect of suction superheat and liquid subcooling on cycle COP and refrigerating effect versus the baseline saturated cycle.

**Input:** `T_evap_C`, `T_cond_C`, `capacity_W` (required); `refrigerant`, `superheat_K`, `subcool_K` (optional). **Returns:** baseline and modified `COP`, `refrigerating_effect_kJkg`, absolute and percentage changes.

---

### `refrig_two_stage_cycle`

Two-stage vapor-compression cycle with flash intercooler. Better COP than single-stage when pressure ratio > ~10. Per-stage pressure ratios, mass flows, and compressor powers. Interstage uses geometric-mean temperature by default.

**Input:** `T_evap_C`, `T_cond_C`, `capacity_W` (required); `refrigerant`, `eta_isentropic`, `superheat_K`, `subcool_K`, `eta_volumetric`, `T_interstage_C` (optional). **Returns:** per-stage pressure ratios, mass flows, powers, and `overall_COP`.

---

### `refrig_cascade_cycle`

Two-refrigerant cascade cycle for very low temperatures (below −40°C). Two circuits share a cascade heat exchanger. Common pairs: R744/R134a, R717/R134a, R290/R134a.

**Input:** `T_evap_C`, `T_cond_C`, `capacity_W` (required); `refrigerant_low` (default `R744`), `refrigerant_high` (default `R134a`), `eta_isentropic`, `T_cascade_C`, `superheat_K`, `subcool_K`, `cascade_approach_K` (optional). **Returns:** per-circuit mass flows, powers, pressure ratios, `cascade_duty_W`, `overall_COP`.

---

### `refrig_defrost_energy`

Daily defrost energy for a low-temperature refrigerated coil. Modelled as a fraction (default 5%) of the daily evaporator load.

**Input:** `Q_evap_W`, `operating_hours_per_day`, `defrost_cycles_per_day`, `defrost_duration_min` (required); `defrost_fraction` (optional, default 0.05). **Returns:** `daily_evap_energy_kWh`, `total_defrost_energy_kWh`, `per_cycle_defrost_kWh`, `total_defrost_time_min`, `effective_operating_hours`.

---

### `refrig_pressure_ratio_check`

Quick pressure ratio and estimated discharge temperature check before running a full cycle. Returns flags for high pressure ratio (>10) and high discharge temperature (>130°C).

**Input:** `T_evap_C`, `T_cond_C` (required); `refrigerant`, `superheat_K` (optional). **Returns:** `P_evap_Pa`, `P_cond_Pa`, `pressure_ratio`, `discharge_temp_est_C`, `flag_high_ratio`, `flag_high_discharge`.

---

## Example

```
1. refrig_pressure_ratio_check  T_evap_C:-10  T_cond_C:45  refrigerant:"R134a"
   → pressure_ratio: 5.2  discharge_temp_est_C: 72  flag_high_ratio: false

2. refrig_single_stage_cycle
     T_evap_C:-10  T_cond_C:45  capacity_W:10000  refrigerant:"R134a"
   → COP: 2.8  power_W:3571  mass_flow_kgs:0.073  capacity_TR:2.84

3. refrig_tons_of_refrigeration  capacity_W:10000
   → capacity_TR:2.84  capacity_kW:10.0  capacity_BTUh:34121

4. refrig_two_stage_cycle
     T_evap_C:-40  T_cond_C:40  capacity_W:20000  refrigerant:"R717"
   → overall_COP:3.1  (vs single-stage ~2.4 at this lift)
```
