# Motor Drive and Inverter Sizing

Kerf provides motor drive sizing tools for DC brush, BLDC/PMSM, and induction motors: torque/power, inertia, RMS torque, motor constants, operating points, inverter sizing, regenerative braking, brake resistor, and thermal duty check.

## When to use

Use these tools when you need to:
- Compute total shaft torque and mechanical power required from a motor given load, friction, and inertia
- Reflect load inertia through a gearbox or find the optimal gear ratio for inertia matching
- Compute RMS torque over a trapezoidal move profile for continuous motor rating selection
- Derive motor constants (Kt, Ke, back-EMF) from datasheet parameters
- Find the DC brush or BLDC/PMSM operating point (current, voltage, efficiency) at a speed/torque
- Calculate induction motor slip-torque from equivalent circuit parameters
- Size an inverter (device ratings, switching loss, conduction loss) for a three-phase drive
- Compute recoverable energy during regenerative braking or size a dynamic brake resistor
- Check winding temperature duty-cycle compliance

Trigger keywords: motor sizing, torque, shaft power, reflected inertia, gearbox, gear ratio, inertia mismatch, RMS torque, trapezoidal profile, motor constants, Kt, Ke, back-EMF, DC motor, BLDC, PMSM, FOC, d-q axis, induction motor, slip, inverter, IGBT, switching loss, regen, regenerative braking, brake resistor, motor thermal, winding temperature.

## Tools

| Tool | Purpose |
|---|---|
| `motordrive_load_torque_power` | Total shaft torque (load + inertial + friction + viscous) and mechanical power; inputs: speed_rpm, torque_load_nm |
| `motordrive_reflected_inertia` | Reflects load inertia to motor shaft: J_reflected = J_load / (N² × η_gb); inputs: j_load_kgm2, gear_ratio |
| `motordrive_inertia_match` | Load-to-motor inertia mismatch ratio and optimal gear ratio N_opt = sqrt(J_load/J_motor); inputs: j_motor_kgm2, j_load_kgm2 |
| `motordrive_rms_torque` | RMS torque over a trapezoidal velocity profile for continuous rating; inputs: torque and duration for accel/cruise/decel/dwell phases |
| `motordrive_motor_constants` | Derives Kt, Ke, back-EMF, stall torque, copper loss from datasheet params; inputs: rated_torque_nm, rated_current_a, no_load_speed_rpm, rated_voltage_v, winding_resistance_ohm |
| `motordrive_dc_operating_point` | DC brush motor voltage, current, and efficiency at a given speed and torque; inputs: speed_rpm, torque_nm, kt_nm_per_a, ke_v_s_per_rad, winding_resistance_ohm, supply_voltage_v |
| `motordrive_bldc_pmsm_op_point` | BLDC/PMSM d-q operating point: Iq, phase voltage, minimum DC-link voltage, efficiency; inputs: speed_rpm, torque_nm, kt_nm_per_a, ke_v_s_per_rad, phase_resistance_ohm, dc_link_voltage_v |
| `motordrive_induction_slip_torque` | Induction motor torque at a given per-unit slip from equivalent circuit; inputs: synchronous_speed_rpm, rotor_resistance_ohm, stator_resistance_ohm, leakage_reactance_ohm, supply_voltage_v, slip |
| `motordrive_inverter_sizing` | Three-phase inverter device ratings, switching loss, and conduction loss; inputs: peak_phase_current_a, peak_phase_voltage_v, dc_link_voltage_v, switching_freq_hz |
| `motordrive_regen_energy` | Recoverable kinetic energy during regenerative deceleration; inputs: inertia_kgm2, speed_initial_rpm, speed_final_rpm |
| `motordrive_brake_resistor` | Dynamic brake resistor value and average/peak power; inputs: regen_energy_j, dc_link_voltage_v, discharge_time_s |
| `motordrive_thermal_duty` | Steady-state winding temperature from losses × thermal resistance × duty cycle, with over-temp flag; inputs: p_loss_w, rth_winding_ambient, t_ambient_c |

## Example

**User ask:** "I have a servo axis: 5 N·m load torque, 1500 RPM, 20 ms accel, 100 ms cruise, 20 ms decel with 2 s dwell. What continuous torque rating do I need?"

1. Call `motordrive_load_torque_power` to get peak shaft power and inertial torque.
2. Call `motordrive_rms_torque` with the four phase torques and durations → motor continuous rating must exceed T_rms_nm.
