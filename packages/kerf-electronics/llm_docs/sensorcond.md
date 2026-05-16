# Sensor Signal Conditioning

Kerf provides sensor signal-conditioning tools: Wheatstone bridge output and excitation, strain-to-stress conversion, PT100 RTD forward/inverse models (Callendar-Van Dusen), RTD lead-wire error correction, thermocouple EMF-to-temperature conversion with cold-junction compensation, INA gain and error budget, ADC bit-width calculation, ENOB from noise, anti-alias filter corner, 4–20 mA loop scaling and burden voltage, noise RSS budget, and active filter topology selection.

## When to use

Use these tools when you need to:
- Compute Wheatstone bridge output voltage for a strain gauge (quarter/half/full bridge) and check excitation self-heating
- Convert strain gauge microstrain reading to stress via Hooke's law
- Convert PT100 (or other RTD) temperature to resistance or resistance to temperature using the Callendar-Van Dusen model
- Quantify lead-wire resistance error in 2-wire RTD measurements and apply 3-wire correction
- Convert a thermocouple EMF to temperature (types J/K/T/E/N/S/R/B) with cold-junction compensation
- Calculate instrumentation amplifier (INA) gain and total input-referred error budget (offset, CMRR, drift)
- Determine how many ADC bits are needed for a target measurement resolution, or compute ENOB from system noise
- Find the anti-alias filter corner frequency for a given sample rate and stopband attenuation
- Scale a 4–20 mA current loop to engineering units or check compliance/burden voltage headroom
- Combine independent noise sources into a total RMS noise budget (RSS)
- Choose between Sallen-Key and MFB active filter topology based on gain and Q requirements

Trigger keywords: sensor conditioning, signal conditioning, Wheatstone bridge, strain gauge, microstrain, stress, gauge factor, RTD, PT100, Callendar-Van Dusen, CVD, temperature sensor, lead wire, 3-wire RTD, thermocouple, cold junction compensation, CJC, type K thermocouple, INA, instrumentation amplifier, CMRR, ADC resolution, ENOB, effective number of bits, anti-alias filter, 4-20 mA, loop current, burden voltage, noise budget, RSS noise, Sallen-Key, MFB filter topology.

## Tools

| Tool | Purpose |
|---|---|
| `sensorcond_bridge_output` | Wheatstone bridge output voltage (linearised and exact) for quarter/half/full config; inputs: excitation_v, gauge_factor, strain_ue, config |
| `sensorcond_bridge_excitation` | Bridge excitation power per arm and maximum safe excitation voltage (30 mW self-heating limit); inputs: excitation_v, nominal_resistance_ohm |
| `sensorcond_strain_to_stress` | Microstrain [µε] → stress [MPa] via σ = E×ε; inputs: strain_ue, youngs_modulus_gpa |
| `sensorcond_rtd_resistance` | PT100 CVD forward model: temperature → resistance; inputs: temperature_c, r0_ohm |
| `sensorcond_rtd_temperature` | PT100 CVD inverse model: resistance → temperature (Newton-Raphson for T < 0 °C); inputs: resistance_ohm, r0_ohm |
| `sensorcond_rtd_lead_wire` | RTD lead-wire resistance error and temperature error for 2/3/4-wire configurations; inputs: measurement_resistance_ohm, lead_resistance_ohm, wiring |
| `sensorcond_thermocouple` | TC EMF → temperature using NIST ITS-90 inverse polynomial with CJC; inputs: voltage_mv, tc_type (J/K/T/E/N/S/R/B), cold_junction_temp_c |
| `sensorcond_ina_gain` | INA gain and input-referred error budget (offset, CMRR, drift); inputs: r_gain_ohm |
| `sensorcond_adc_bits` | Minimum ADC bit-width for a target resolution; inputs: full_scale_range_v, target_resolution_mv |
| `sensorcond_enob` | ENOB from input-referred RMS noise: ENOB = log2(FSR / (noise × √12)); inputs: noise_rms_uv, full_scale_range_v |
| `sensorcond_antialias_corner` | Anti-alias filter corner frequency for a given sample rate and stopband attenuation; inputs: sample_rate_hz, stopband_attenuation_db, filter_order |
| `sensorcond_4_20ma_scale` | Scales 4–20 mA loop current to engineering units; inputs: current_ma, span_low, span_high |
| `sensorcond_burden_voltage` | Checks 4–20 mA loop compliance headroom; inputs: current_ma, burden_resistance_ohm, supply_voltage_v |
| `sensorcond_noise_rss` | RSS total noise from a list of independent noise sources [µV]; flags the dominant source |
| `sensorcond_filter_topology` | Recommends Sallen-Key or MFB active LP filter topology from gain, Q, supply type, and noise priority |

## Example

**User ask:** "I have a K-type thermocouple reading 8.138 mV at a terminal block that's at 25 °C. What temperature is it measuring?"

Call `sensorcond_thermocouple` with `voltage_mv=8.138`, `tc_type="K"`, `cold_junction_temp_c=25` → returns `temperature_c` with CJC applied.
