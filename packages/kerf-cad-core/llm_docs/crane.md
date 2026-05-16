# Crane & Hoist Mechanism Design

Pure-Python crane and hoist engineering module covering wire-rope reeving,
rope selection, sheave/drum geometry, motor sizing, traffic/duty class,
hook/lug checks, and fall-protection brakes. References FEM 1.001, ISO 4301-1,
DIN 15400, and ASME B30.2.

---

## When to use

Reach for this module when the user asks about:

- wire-rope line pull from reeving, selecting rope diameter by safety factor
- sheave and drum pitch-circle diameter from D/d ratio (FEM 1.001)
- drum barrel length for a given hoist height and rope reeving
- hoist motor power from SWL and hoisting speed
- FEM/ISO M-class for hoist motor from duty group and load spectrum
- required hoist brake holding torque
- crane travel resistance (rolling + wind) and travel motor power
- jib/boom allowable hook load vs. radius (tipping stability load chart)
- bridge crane wheel loads and end-carriage reactions
- hook shank tensile stress check per DIN 15400
- pad-eye or lifting lug net-section, bearing, and shear-out check
- FEM duty group (A1–A8) and M-class from total hoisting cycles
- fall-protection / anti-runaway brake sizing and brake-path distance

---

## Tools

### `crane_wire_rope_reeving`

Compute wire-rope line pull (rope tension at the drum) and hook-block efficiency
from reeving geometry.
Inputs: `SWL_kN`, `n_parts` (required); optional `rope_efficiency` (default
0.98), `reeving_factor`.
Returns: `line_pull_kN`, `line_pull_N`, `eta_block`.

### `crane_rope_diameter`

Select the minimum standard wire-rope nominal diameter (6–40 mm) for a given
line pull and safety factor per DIN 15020-1 / FEM 1.001.
Inputs: `line_pull_kN` (required); optional `safety_factor` (default 5.0),
`grade` (1570/1770/1960 MPa).
Returns: `diameter_mm`, `mbf_kN`, `actual_sf`.

### `crane_sheave_drum_geometry`

Compute minimum sheave and drum pitch-circle diameters from rope D/d ratio
per FEM 1.001. Warns if ratio falls below the FEM minimum for the mechanism
class.
Inputs: `rope_dia_mm` (required); optional `sheave_dd_ratio` (default 18),
`drum_dd_ratio` (default 16), `fem_class` (A–F, default 'E').
Returns: `pcd_sheave_mm`, `pcd_drum_mm`, FEM minimum ratios.

### `crane_drum_length`

Compute drum barrel length from rope diameter, number of reeving parts, and
hoist height.
Inputs: `rope_dia_mm`, `n_parts`, `hoist_height_m` (required); optional
`n_layers`, `groove_pitch_factor` (default 1.15), `dead_turns`.
Returns: `drum_length_mm`, `turns_working`, `groove_pitch_mm`.

### `crane_hoist_motor_power`

Compute required hoist motor power: P = (SWL × g × v) / η × duty_factor.
Inputs: `SWL_kN`, `hoist_speed_mps` (required); optional
`mechanical_efficiency` (default 0.85), `duty_factor` (default 1.0).
Returns: `motor_power_kW`, `lift_power_kW`.

### `crane_hoist_motor_class`

Determine the FEM/ISO M-class (M1–M8) for a hoist motor from duty group
(utilisation class 1–8) and load-spectrum class (Q1–Q4) per FEM 1.001 /
ISO 4301-1.
Inputs: `duty_group`, `load_spectrum` (both required).
Returns: `m_class`. Warning OVER_DUTY for M7/M8.

### `crane_hoist_brake_torque`

Compute required hoist brake holding torque.
Inputs: `SWL_kN`, `drum_pcd_mm`, `n_parts` (required); optional
`brake_factor` (default 1.5, minimum 1.25 per FEM/ASME).
Returns: `required_brake_Nm`, `drum_torque_Nm`, `rope_tension_N`.

### `crane_travel_resistance`

Compute crane or trolley travel drive resistance (rolling + wind load).
Inputs: `crane_mass_kg`, `payload_kg` (required); optional `coeff_rolling`
(default 0.015), `coeff_wind`, `wind_pressure_Pa`, `frontal_area_m2`.
Returns: `total_force_N`, `total_force_kN`.

### `crane_travel_motor_power`

Compute required travel motor power: P = resistance × speed / efficiency ×
acceleration_factor.
Inputs: `resistance_N`, `travel_speed_mps` (required); optional
`motor_efficiency` (default 0.85), `acceleration_factor` (default 1.25).
Returns: `motor_power_kW`, `motor_power_W`.

### `crane_jib_load_chart`

Compute allowable hook load vs. slew radius from tipping stability for a
jib/boom crane.
Inputs: `slew_radius_m`, `jib_length_m`, `jib_mass_kg`, `counterweight_kg`,
`counterweight_radius_m` (all required); optional `safety_factor` (default 1.5),
`tipping_fraction`, `crane_base_mass_kg`, `base_radius_m`.
Returns: `allowable_load_kg`, `allowable_load_kN`, `structural_allowable_kg`.

### `crane_bridge_wheel_loads`

Compute bridge crane wheel loads and end-carriage reactions using a
simply-supported beam model with dynamic amplification.
Inputs: `crane_span_m`, `bridge_mass_kg`, `crab_mass_kg`, `payload_kg`,
`crab_x_m` (all required); optional `n_wheels_per_end`, `dynamic_factor`
(default 1.15 FEM HC2).
Returns: `left_wheel_load_kN`, `right_wheel_load_kN`, end reactions.

### `crane_hook_shank_check`

Hook shank tensile stress check per DIN 15400 at the thread root (ISO metric
minor diameter).
Inputs: `SWL_kN`, `shank_diameter_mm`, `thread_pitch_mm` (required); optional
`material` (grade_P/grade_S/grade_T/42CrMo4), `design_factor`.
Returns: `tension_stress_MPa`, `allowable_MPa`, `utilisation`, `pass_shank`.

### `crane_lifting_lug_check`

Pad-eye / lifting lug strength check: net-section tension, bearing on pin hole,
and double shear-out per EN 1993 principles.
Inputs: `load_kN`, `plate_thickness_mm`, `hole_diameter_mm`, `lug_width_mm`
(required); optional `Fy_MPa`, `Fu_MPa`, `design_factor`.
Returns: stresses, allowables, pass/fail flags, `governing_utilisation`.

### `crane_duty_class`

Determine FEM duty group (A1–A8) and M-class (M1–M8) from total hoisting
cycles and load-spectrum class per FEM 1.001.
Inputs: `total_cycles`, `load_spectrum_class` (required); optional
`hours_per_year`.
Returns: `duty_group`, `m_class`.

### `crane_fall_protection_brake`

Size the fall-protection / anti-runaway brake for a hoist. Computes trigger
speed, required brake torque, and brake-path distance. Warns if brake path
exceeds 0.5 m.
Inputs: `SWL_kN`, `hoist_speed_mps`, `governor_speed_factor`,
`drum_inertia_kgm2`, `drum_radius_m` (all required).
Returns: `required_brake_Nm`, `brake_path_m`, `trigger_speed_mps`.

---

## Example

**User ask:** "Design a 5 t SWL overhead bridge crane with 4-part reeving,
1 200 kg bridge, 3 m span, 0.5 m/s hoist speed. Select rope diameter and check
motor power."

1. `crane_wire_rope_reeving` — SWL_kN: 50, n_parts: 4
   → line_pull_kN ≈ 12.9
2. `crane_rope_diameter` — line_pull_kN from step 1, safety_factor: 5
   → diameter_mm
3. `crane_hoist_motor_power` — SWL_kN: 50, hoist_speed_mps: 0.5
   → motor_power_kW
4. `crane_bridge_wheel_loads` — crane_span_m: 3, bridge_mass_kg: 1200,
   crab_mass_kg: 200, payload_kg: 5000, crab_x_m: 1.5
   → wheel loads for rail design
