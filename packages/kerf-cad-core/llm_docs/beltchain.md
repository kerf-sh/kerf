# Belt and Chain Drive Selection

Pure-Python belt and chain drive design tools. No OCC dependency. Covers classical/narrow
V-belt drives, synchronous (timing) belt drives, and ANSI roller-chain drives. All tools
stateless. References: Shigley's MED 10th ed. §§17-1 to 17-12; ANSI/RMA IP-20; ANSI/ASME
B29.1.

---

## When to use

Use these tools when the user asks about:
- V-belt, vee belt, classical belt, narrow belt, A-belt, B-belt, C-belt, D-belt, 3V, 5V, 8V
- belt drive, sheave, pulley, belt selection, belt sizing
- timing belt, synchronous belt, toothed belt, HTD belt, 3M 5M 8M 14M belt
- chain drive, roller chain, ANSI chain, sprocket, chain pitch, chain number
- power transmission, speed ratio, gear ratio, drive ratio
- belt length, belt pitch length, centre distance
- wrap angle, contact angle, tension ratio, tight side, slack side
- number of belts, drive design, service factor
- chains in mesh, teeth in mesh, lubrication regime, type A drip, type B bath, type C pump
- shaft load, belt tension, capstan tension

---

## Tools

### `vbelt_design`

Design a classical or narrow V-belt drive.

Computes design power (nominal × service factor Ks), belt cross-section recommendation
(A/B/C/D/3V/5V/8V), large-sheave diameter, belt speed, pitch belt length and centre
distance, wrap angles, wrap-angle correction Cv and length correction Kc, corrected
per-belt rated power, number of belts, tight/slack tensions via capstan e^(μθ), total
shaft load.

**Input:**
- `power_kW` (required), `n_driver_rpm` (required), `n_driven_rpm` (required)
- `d_small_mm` — pitch diameter of small sheave (mm; if omitted, chosen from belt section minimum)
- `center_distance_mm` — desired centre distance (mm; default D_large + d_small)
- `service_factor` — manual Ks override (if omitted, looked up from driver_type × load_hours)
- `driver_type` — `normal` (default, AC motor) or `heavy` (high-torque/IC engine)
- `load_hours` — `light` (< 10 h/day), `moderate` (10–16 h, default), `heavy` (> 16 h)
- `mu` — friction coefficient between belt and sheave (default 0.51 rubber on cast iron)

**Returns:** `belt_section`, `n_belts`, `d_large_mm`, `belt_speed_ms`, `pitch_length_mm`,
`center_distance_mm`, `wrap_small_deg`, `wrap_large_deg`, `T1_N`, `T2_N`, `shaft_load_N`,
`design_power_kW`, `warnings`.

---

### `timing_belt_design`

Design a synchronous (timing) belt drive.

Computes belt pitch selection (MXL/3M/5M/8M/14M/H), driver and driven sprocket tooth
counts from speed ratio, pitch diameters (d = z·p/π), belt speed, belt pitch length and
centre distance, teeth in mesh on small sprocket, minimum belt width.

**Input:**
- `power_kW` (required), `n_driver_rpm` (required)
- `pitch_mm` — belt pitch (mm); standard: 2.032 MXL, 3 (3M), 5 (5M), 8 (8M), 14 (14M),
  25.4 H; if omitted, auto-selected from design power
- `z_driver` — driver sprocket tooth count (default 18, minimum 10)
- `speed_ratio` — n_driver / n_driven (default 1.0; values < 1 are inverted)
- `center_distance_mm` — desired centre distance (default 3 × large pitch diameter)
- `service_factor` — Ks (default 1.3)

**Returns:** `pitch_mm`, `z_driver`, `z_driven`, `d_driver_mm`, `d_driven_mm`,
`belt_speed_ms`, `pitch_length_mm`, `center_distance_mm`, `teeth_in_mesh`, `width_mm`,
`warnings`.

---

### `chain_drive_design`

Design an ANSI roller-chain drive.

Computes ANSI chain number (25/35/40/50/60/80/100/120/140/160/180/200/240), design power
(power × Ks), sprocket pitch diameters (d = p / sin(π/z)), chain speed, chain length in
pitches (even integer), centre distance, rated power per strand, multi-strand rated power,
working tension, breaking-load safety factor, lubrication regime.

**Input:**
- `power_kW` (required), `n_small_rpm` (required), `z_small` (required, >= 7),
  `z_large` (required, >= z_small)
- `chain_no` — ANSI chain number string (if omitted, smallest adequate chain auto-selected)
- `load_type` — `smooth` (Ks=1.0, default), `moderate` (1.25), `heavy` (1.5)
- `n_strands` — number of parallel strands (default 1)

**Returns:** `chain_no`, `pitch_mm`, `d_small_mm`, `d_large_mm`, `chain_speed_ms`,
`n_pitches`, `center_distance_mm`, `rated_power_kW`, `safety_factor`, `lubrication_regime`,
`warnings`.

---

## Example

```
1. vbelt_design  power_kW:7.5  n_driver_rpm:1450  n_driven_rpm:580
   → belt_section:"B"  n_belts:2  d_large_mm:315
     center_distance_mm:520  wrap_small_deg:152  shaft_load_N:1840

2. timing_belt_design  power_kW:2.2  n_driver_rpm:1500  speed_ratio:3.0
   → pitch_mm:5  z_driver:18  z_driven:54  teeth_in_mesh:9
     width_mm:15  center_distance_mm:180

3. chain_drive_design  power_kW:5.5  n_small_rpm:960  z_small:19  z_large:38
   → chain_no:"50"  pitch_mm:15.875  n_pitches:96
     center_distance_mm:483  safety_factor:9.4  lubrication_regime:"type_B_bath"
```
