# Electrical Safety, Grounding & Arc Flash

IEC/IEEE electrical safety calculations: PE conductor sizing, bonding,
ground electrode resistance, GPR, touch/step voltage, creepage/clearance,
hi-pot test voltage, leakage current limits, RCD thresholds, arc flash
incident energy, wire ampacity, and SELV/PELV checks.

## When to use

Protective earth, PE conductor, EGC, bonding, grounding, earth electrode,
ground resistance, ground potential rise, GPR, touch voltage, step voltage,
creepage, clearance, IEC 60664, pollution degree, overvoltage category,
hi-pot, dielectric withstand, hipot, insulation class, reinforced insulation,
leakage current, touch current, RCD, GFCI, residual current, arc flash,
incident energy, NFPA 70E, PPE category, IEEE 1584, wire ampacity, XLPE,
PVC, SELV, PELV, extra-low voltage, IEC 61140.

## Tools

### `elecsafety_pe_conductor_size`
Minimum PE/EGC cross-section via adiabatic equation: A = I·√t / k (IEC 60364-5-54).
Inputs: `fault_current_a`, `fault_duration_s`, optional `material` (copper/aluminium/steel).
Returns `area_min_mm2`, `material`, `k`.

### `elecsafety_bonding_resistance`
Equipotential bonding GPR check: GPR = I·R_bond; flags when GPR > safe touch voltage.
Inputs: `fault_current_a`, `bond_resistance_ohm`, optional `safe_touch_voltage_v`.
Returns `gpr_v`, `gpr_hazard`.

### `elecsafety_ground_electrode`
Ground electrode resistance: rod (Dwight), plate, or Schwarz grid (IEEE 80-2013).
Inputs: `electrode_type` (rod/plate/grid), `soil_resistivity_ohm_m`; geometry params.
Returns `resistance_ohm`, `electrode_type`.

### `elecsafety_gpr`
Ground potential rise: GPR = I_fault · R_ground (IEEE 80-2013).
Flags HAZARD (> 1 kV) and EXTREME (> 5 kV).
Inputs: `fault_current_a`, `ground_resistance_ohm`.
Returns `gpr_v`, `hazard_level`.

### `elecsafety_touch_step_voltage`
Permissible touch and step voltage (IEC 60479-1 / IEEE 80-2013 §8).
Inputs: `fault_current_a`, `fault_duration_s`; optional `surface_layer_resistivity_ohm_m`.
Returns `v_touch_permissible_v`, `v_step_permissible_v`, `i_body_permissible_a`.

### `elecsafety_creepage_clearance`
Minimum creepage and clearance per IEC 60664-1:2007+A1.
Inputs: `working_voltage_v_rms`; optional `overvoltage_category`, `pollution_degree`,
`material_group`, `altitude_m`, measured values for compliance check.
Returns `min_creepage_mm`, `min_clearance_mm`, `creepage_ok`, `clearance_ok`.

### `elecsafety_insulation_hipot`
Hi-pot (dielectric withstand) test voltage per IEC 60664-1 / IEC 62368-1.
Inputs: `working_voltage_v_rms`; optional `insulation_class`, `equipment_class`.
Returns `test_voltage_v_rms`, `test_voltage_v_peak`.

### `elecsafety_leakage_limit`
Permissible leakage/touch current per IEC 62368-1 (IT) or IEC 60601-1 (medical).
Inputs: optional `equipment_class`, `application`, `connection`, `measured_leakage_a`.
Returns `limit_a`, `limit_ma`, `compliant`.

### `elecsafety_rcd_threshold`
RCD/GFCI trip threshold check (IEC 61008 / UL 943).
Inputs: `rcd_rating_a`, `measured_leakage_a`, optional `device_type`.
Returns `will_trip`, `margin_a`, `trip_threshold_a`.

### `elecsafety_arc_flash`
Arc-flash incident energy and boundary (IEEE 1584-2002 + Lee method).
Returns the more conservative estimate, arc-flash boundary, and NFPA 70E PPE category.
Inputs: `system_voltage_v`, `bolted_fault_current_ka`, `arcing_duration_s`.
Returns `incident_energy_cal_cm2`, `afb_mm`, `ppe_category`.

### `elecsafety_wire_ampacity`
Wire ampacity with insulation temperature rating and ambient derating (IEC 60364-5-52).
Inputs: `cross_section_mm2`; optional `insulation` (pvc/xlpe/ptfe/silicone…), `ambient_temp_c`.
Returns `derated_ampacity_a`, `base_ampacity_a`, `overloaded`.

### `elecsafety_selv_pelv`
SELV/PELV threshold check (IEC 61140 / IEC 60364-4-41): AC ≤ 50 V, DC ≤ 120 V.
Inputs: optional `voltage_v_ac_rms`, `voltage_v_dc`, `circuit_type`.
Returns `is_selv_pelv`, `borderline`.

## Example

Check whether a 230 V working voltage PCB trace meets IEC 60664-1
creepage and clearance at pollution degree 2, material group II:

```json
{
  "tool": "elecsafety_creepage_clearance",
  "working_voltage_v_rms": 230,
  "pollution_degree": 2,
  "material_group": "II",
  "measured_creepage_mm": 3.2,
  "measured_clearance_mm": 2.5
}
```
