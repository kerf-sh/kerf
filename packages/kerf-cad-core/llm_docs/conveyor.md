# Bulk-Material Conveyor Design

Pure-Python CEMA-based bulk-material conveyor design tools. No OCC dependency.
All tools are stateless. Units: SI (metres, kg, kN, kW) unless noted.

---

## When to use

Use these tools when the conversation involves: belt conveyor, screw conveyor,
bucket elevator, bulk material handling, CEMA, conveyor capacity, throughput,
belt tension, effective tension, drive power, motor sizing, slack-side tension,
belt takeup, counterweight, troughing angle, surcharge angle, angle of repose,
inclined conveyor, conveyor power, idler spacing, idler load, belt speed, belt
width, screw flight, pitch, fill ratio, bucket elevator, lift power, coal,
iron ore, grain, cement, sand, fly ash, limestone, conveyor design.

---

## Tools

### `belt_conveyor_design`

CEMA-style troughed or flat belt conveyor for bulk materials.

**Input:** `belt_width_m`, `belt_speed_m_s`, `length_m`, `lift_m` (+ up/− down),
`bulk_density_kg_m3` (all required); optional `trough_angle_deg` (default 35),
`surcharge_angle_deg` (default 20), `friction_factor` (Ky, default 0.020),
`drive_efficiency` (default 0.90), `belt_mass_kg_m`, `idler_spacing_m` (default 1.2),
`wrap_angle_deg` (default 210), `mu_belt_pulley` (default 0.35),
`accessory_tension_N`, `target_capacity_t_h`, `repose_angle_deg`.

**Returns:** `capacity_t_h`, `capacity_m3_h`, `Te_N` (effective tension),
`power_drive_kW`, `motor_kW`, `T2_N` (slack-side), `belt_rating_N_m`,
`idler_load_N`, `takeup_N`, `inclination_deg`, warnings (over-incline,
belt overtension, capacity shortfall).

---

### `screw_conveyor_design`

CEMA screw conveyor for bulk materials.

**Input:** `diameter_m`, `pitch_m`, `speed_rpm`, `length_m`, `bulk_density_kg_m3`
(all required); optional `material_class` (default `generic_medium`, options:
`grain`, `coal_dry`, `coal_wet`, `cement_dry`, `sand_dry`, `sand_wet`,
`clay_dry`, `fly_ash`, `limestone`, `generic_light`, `generic_medium`,
`generic_heavy`), `loading_class` (default `medium`; `light`=45%, `medium`=38%,
`heavy`=30%, `special`=15%), `lift_m` (default 0), `drive_efficiency`
(default 0.85), `target_capacity_t_h`.

**Returns:** `capacity_t_h`, `capacity_m3_h`, `fill_ratio`, `Pm_kW`, `Pi_kW`,
`Pt_kW`, `motor_kW`, `torque_Nm`, warnings (over-fill, over-speed,
capacity shortfall).

---

### `bucket_elevator_design`

Bucket elevator (centrifugal or continuous discharge) for bulk materials.

**Input:** `bucket_volume_m3`, `bucket_spacing_m`, `belt_speed_m_s`,
`lift_height_m`, `bulk_density_kg_m3` (all required); optional `fill_factor`
(default 0.75), `belt_mass_kg_m` (default 5.0), `drive_efficiency` (default 0.85),
`elevator_type` (`"centrifugal"` default or `"continuous"`),
`target_capacity_t_h`.

**Returns:** `capacity_t_h`, `capacity_m3_h`, `lift_power_kW`,
`belt_power_kW`, `motor_kW`, `belt_tension_N`, warnings (over-speed for type,
capacity shortfall).

---

## Example

```
1. belt_conveyor_design
     belt_width_m:1.0  belt_speed_m_s:2.5  length_m:200
     lift_m:8  bulk_density_kg_m3:800
     trough_angle_deg:35  target_capacity_t_h:600
   → capacity_t_h: 648  Te_N: 42300  motor_kW: 118

2. screw_conveyor_design
     diameter_m:0.30  pitch_m:0.30  speed_rpm:60
     length_m:15  bulk_density_kg_m3:750  material_class:"grain"
   → capacity_t_h: 28.4  motor_kW: 2.1

3. bucket_elevator_design
     bucket_volume_m3:0.010  bucket_spacing_m:0.40  belt_speed_m_s:1.5
     lift_height_m:25  bulk_density_kg_m3:800
   → capacity_t_h: 81  motor_kW: 14.2
```
