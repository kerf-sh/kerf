# Circuit Protection Design

Kerf provides circuit protection tools covering fuse selection, inrush limiting, TVS/MOV clamping, reverse-polarity protection, eFuse, PTC resettable fuses, breaker coordination, PCB trace fusing (Onderdonk), and wire ampacity checks.

## When to use

Use these tools when you need to:
- Select and validate a fuse: continuous-current derating, I²t let-through, voltage rating, interrupt rating
- Size an NTC inrush limiter for a power supply with large bulk capacitance
- Check whether a TVS diode or MOV has adequate standoff voltage, clamping voltage, peak power, energy, and IEC 61000-4-5 surge compliance
- Compare series diode vs P-channel MOSFET for reverse-polarity protection
- Validate an eFuse trip threshold and safe operating area (SOA)
- Check a PTC resettable fuse hold/trip current after temperature derating
- Verify fuse/circuit-breaker coordination (selectivity ratio) for a hierarchical protection scheme
- Calculate PCB copper trace fusing current (Onderdonk's equation)
- Check wire ampacity against NEC 310.16 with ambient-temperature correction

Trigger keywords: fuse, fuse selection, inrush current, NTC inrush limiter, TVS diode, MOV, transient voltage suppressor, surge protection, ESD protection, IEC 61000-4-5, reverse polarity protection, P-FET, eFuse, electronic fuse, PTC fuse, resettable fuse, breaker coordination, selectivity, Onderdonk, trace fusing, PCB trace current, wire ampacity, NEC, overcurrent protection.

## Tools

| Tool | Purpose |
|---|---|
| `protection_fuse_select` | Validates fuse: derated current, I²t, voltage rating, interrupt rating; inputs: load_current_a, supply_voltage_v, ambient_temp_c, fuse_rating_a, fuse_voltage_v, fuse_interrupt_a, fuse_i2t_as2, downstream_i2t_withstand_as2 |
| `protection_inrush_ntc_size` | Estimates inrush peak/energy and checks NTC power rating; inputs: supply_voltage_v, bulk_capacitance_uf, ntc_resistance_cold_ohm, ntc_resistance_hot_ohm, ntc_max_power_w, steady_state_current_a |
| `protection_tvs_mov_clamp` | Checks TVS/MOV adequacy: standoff, clamping voltage, pulse power, energy, I_pp, optional IEC 61000-4-5 level; inputs: working_voltage_v, tvs_standoff_v, tvs_clamping_v_at_ipp, tvs_ipp_a, tvs_peak_power_w, surge_current_a, surge_energy_j |
| `protection_reverse_polarity` | Compares series diode vs P-FET: conduction loss, load voltage, recommends lower-loss option; inputs: supply_voltage_v, load_current_a, diode_vf_v, pfet_rds_on_ohm |
| `protection_efuse_trip` | eFuse conduction loss and SOA fault energy vs trip threshold; inputs: current_limit_a, load_current_a, supply_voltage_v, efuse_rds_on_ohm, efuse_max_power_w |
| `protection_ptc_resettable` | PTC hold/trip current derating at ambient temperature and pass/fail; inputs: ptc_hold_current_a, ptc_trip_current_a, load_current_a, ptc_resistance_ohm, supply_voltage_v |
| `protection_breaker_coordination` | Fuse/breaker selectivity ratio and time-current coordination; inputs: upstream_trip_current_a, downstream_trip_current_a, upstream_trip_time_s, downstream_trip_time_s |
| `protection_onderdonk_trace_fuse` | PCB trace fusing current from Onderdonk equation; inputs: trace_width_mm, trace_thickness_um, fusing_time_s |
| `protection_wire_ampacity` | Wire ampacity check with ambient derating per NEC 310.16; inputs: awg, load_current_a, wire_length_m |

## Example

**User ask:** "I have a 24 V / 5 A load. I want to use a 6.3 A fuse. Is it adequately derated at 50 °C ambient, and does the voltage and interrupt rating of a 250 V / 100 A interrupt fuse work?"

Call `protection_fuse_select` with `load_current_a=5`, `supply_voltage_v=24`, `ambient_temp_c=50`, `fuse_rating_a=6.3`, `fuse_voltage_v=250`, `fuse_interrupt_a=100`, plus estimated I²t values → get current_ok, voltage_ok, interrupt_ok, and all_ok.
