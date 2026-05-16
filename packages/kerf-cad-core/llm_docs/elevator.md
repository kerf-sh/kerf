# Elevator & Escalator Engineering

Pure-Python vertical-transportation engineering module covering traction lifts,
hydraulic lifts, motor sizing, traffic analysis, safety gear, and escalators.
References EN 81-1/81-2, EN 115-1, and CIBSE Guide D.

---

## When to use

Reach for this module when the user asks about:

- sizing a traction lift: counterweight, rope tensions, traction ratio, D/d check
- hydraulic lift jack force, working pressure, pump flow, motor power
- hoist motor power for a lift from load and speed
- lift travel kinematics: S-curve, floor-to-floor time, acceleration/jerk
- traffic analysis: round-trip time, interval, handling capacity, cars required
- EN 81-1 buffer stroke and overspeed governor trip speed
- escalator or moving-walk capacity and drive power
- CIBSE Guide D lift design calculations

---

## Tools

### `elevator_traction_lift`

Analyse a traction lift roping configuration per EN 81-1.
Inputs: `rated_load_kg`, `car_mass_kg`, `rated_speed_m_s` (required);
optional `roping` (1:1 or 2:1), `counterweight_balance_pct`, `mu`,
`groove_angle_deg`, `wrap_angle_deg`, `n_ropes`, `rope_diameter_mm`,
`sheave_diameter_mm`.
Returns: counterweight mass, rope tensions, traction ratio T1/T2, traction
limit, adequacy flags, recommended rope count, sheave D/d ratio.

### `elevator_hydraulic_lift`

Compute hydraulic lift jack force, pump flow, and motor power per EN 81-2.
Inputs: `rated_load_kg`, `car_mass_kg`, `rated_speed_m_s`, `piston_diameter_mm`
(required); optional `roping`, `pump_efficiency`, `motor_efficiency`,
`safety_factor`, `max_working_pressure_MPa`.
Returns: jack force, working pressure, proof pressure, pump flow rate (m³/s
and L/min), hydraulic shaft power, motor power.

### `elevator_motor_power`

Compute traction lift motor power from the balanced-load method per CIBSE
Guide D §3.3.
Inputs: `rated_load_kg`, `car_mass_kg`, `counterweight_mass_kg`,
`rated_speed_m_s` (required); optional `roping`, `drive_efficiency`,
`starts_per_hour`, `duty_factor`.
Returns: motor shaft power, net unbalanced force, thermally-derated motor power.

### `elevator_kinematics`

Compute floor-to-floor travel kinematics using a symmetric S-curve
(trapezoidal jerk) profile.
Inputs: `floor_height_m`, `rated_speed_m_s` (required); optional
`acceleration_m_s2`, `jerk_m_s3`, `door_time_s`.
Returns: jerk time, accel time, max achieved speed, accel distance,
constant-speed distance, flight time, floor-to-floor time. Warns if
acceleration > 1.5 m/s² or jerk > 2.0 m/s³ (CIBSE comfort limits).

### `elevator_traffic_analysis`

CIBSE Guide D round-trip time (RTT) traffic analysis. Uses Barney & Dos Santos
probable-stops and highest-reversal-floor formulae.
Inputs: `n_floors`, `floor_height_m`, `n_persons`, `rated_load_persons`,
`rated_speed_m_s` (required); optional `acceleration_m_s2`, `jerk_m_s3`,
`door_time_s`, `n_cars`, `target_interval_s`, `target_handling_pct`.
Returns: probable stops S, reversal floor H, RTT per car, average interval,
5-minute handling capacity (%), cars required for target interval.

### `elevator_buffer_stroke`

Compute EN 81-1 buffer stroke and overspeed governor trip speed.
Inputs: `rated_speed_m_s` (required); optional `overspeed_governor_factor`,
`buffer_type` (oil/polyurethane/spring).
Returns: governor trip speed, speed at buffer impact, minimum buffer stroke
per EN 81-1 §10.4.3, safety gear stopping distance.

### `elevator_escalator`

Compute escalator or moving-walk capacity and drive power per EN 115-1 and
CIBSE Guide D §7.
Inputs: `step_width_m`, `belt_speed_m_s`, `rise_m` (required); optional
`inclination_deg`, `escalator_type` (escalator/moving_walk),
`utilisation_factor`, `drive_efficiency`, `target_capacity_pph`.
Returns: inclined truss length, theoretical capacity (pph), actual capacity,
passenger lift power, friction power, total drive power, motor power.

---

## Example

**User ask:** "I need a traction lift for a 10-storey office: 1 000 kg rated
load, 1 200 kg car, 2.5 m/s. How many 8-person cars do I need to keep average
interval ≤ 30 s for 200 occupants at 3.5 m floor height?"

1. `elevator_traction_lift` — rated_load_kg: 1000, car_mass_kg: 1200,
   rated_speed_m_s: 2.5
   → counterweight, traction ratio, rope recommendation
2. `elevator_motor_power` — rated_load_kg: 1000, car_mass_kg: 1200,
   counterweight_mass_kg: (from step 1), rated_speed_m_s: 2.5
   → motor_power_kW
3. `elevator_traffic_analysis` — n_floors: 10, floor_height_m: 3.5,
   n_persons: 200, rated_load_persons: 8, rated_speed_m_s: 2.5,
   target_interval_s: 30
   → interval per car, cars_required

---

## Notes

- All tools are **pure-Python**; no OCC dependency.
- Tools are **stateless** — validate and return dicts; no DB writes.
- Invalid inputs return `{ok: false, reason: "..."}` — never raise.
- References: EN 81-1:1998+A3:2009, EN 81-2:1998+A3:2009, EN 115-1:2017,
  CIBSE Guide D (4th ed.).
