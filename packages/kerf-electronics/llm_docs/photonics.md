# Optoelectronics & Photonics Design

LED/laser L-I-V, photodiode responsivity, noise and bandwidth, transimpedance
amplifier design, optocoupler analysis, fiber coupling efficiency, solar cell
I-V model, and Time-of-Flight LiDAR range estimation.

## When to use

LED, laser diode, L-I-V curve, slope efficiency, threshold current, WPE, wall-plug
efficiency, EQE, external quantum efficiency, thermal droop, wavelength shift,
photon energy, photodiode, responsivity, quantum efficiency, photocurrent,
shot noise, dark current, Johnson noise, NEP, noise-equivalent power, D-star, SNR,
bandwidth, RC bandwidth, transit time, TIA, transimpedance amplifier, feedback
resistor, op-amp noise, stability, phase margin, optocoupler, CTR, current transfer
ratio, fiber coupling, mode field diameter, numerical aperture, NA mismatch, single
mode fiber, multimode fiber, solar cell, single-diode model, fill factor, MPP,
efficiency, time of flight, ToF, LiDAR, range equation, atmospheric loss.

## Tools

### `photonics_wavelength_to_energy`
Convert optical wavelength to photon frequency and energy (J and eV).
Inputs: `wavelength_m`.
Returns `wavelength_nm`, `freq_hz`, `photon_energy_j`, `photon_energy_ev`.

### `photonics_led_liv`
LED/laser-diode L-I-V model: optical power, junction voltage, WPE, EQE, and thermal droop + wavelength shift.
Inputs: `current_a`, `wavelength_m`, `slope_efficiency_w_per_a`; optional `threshold_current_a`, `vf_v`, `series_resistance_ohm`, `eqe`, `thermal_droop_per_k`, `wavelength_shift_nm_per_k`, `delta_temp_k`.
Returns `p_opt_w`, `vj_v`, `wpe`, `eqe`, `photon_energy_ev`, `below_threshold`.

### `photonics_laser_threshold`
Laser P-I relation above/below threshold: P = slope_eff × (I − I_th).
Inputs: `current_a`, `threshold_current_a`, `slope_efficiency_w_per_a`.
Returns `p_opt_w`, `above_threshold`, `overdrive_a`.

### `photonics_photodiode_responsivity`
Photodiode responsivity R [A/W] from quantum efficiency and wavelength: R = EQE × q × λ / (h × c).
Inputs: `wavelength_m`; optional `quantum_efficiency` (default 0.8).
Returns `responsivity_a_per_w`, `photon_energy_ev`.

### `photonics_photodiode_photocurrent`
Photocurrent from incident optical power: I_ph = R × P_opt.
Inputs: `optical_power_w`, `responsivity_a_per_w`.
Returns `photocurrent_a`.

### `photonics_photodiode_noise`
Photodiode noise budget: shot, dark-current, and Johnson noise; SNR, NEP, and D*.
Inputs: `optical_power_w`, `responsivity_a_per_w`, `dark_current_a`, `bandwidth_hz`, `load_resistance_ohm`; optional `temp_k`, `snr_min_db`.
Returns `i_noise_rms_a`, `snr_db`, `nep_w_per_root_hz`, `d_star_cm_root_hz_per_w`, `snr_ok`.

### `photonics_photodiode_bandwidth`
Photodiode −3 dB bandwidth from RC time constant and optional carrier transit time (quadrature combination).
Inputs: `junction_capacitance_f`, `load_resistance_ohm`; optional `transit_time_s`.
Returns `f_rc_hz`, `f_3db_hz`, `rc_limited`, `transit_limited`.

### `photonics_tia_design`
Transimpedance amplifier (TIA): gain, total input-referred noise, feedback capacitor for stability, and bandwidth.
Inputs: `feedback_resistance_ohm`, `diode_capacitance_f`, `opamp_voltage_noise_v_per_root_hz`, `opamp_current_noise_a_per_root_hz`, `bandwidth_hz`; optional `temp_k`, `phase_margin_deg`.
Returns `transimpedance_gain_ohm`, `i_total_noise_rms_a`, `cf_stability_f`, `f_3db_hz`, `tia_stable`.

### `photonics_optocoupler`
Optocoupler output current, output voltage, saturation check, and bandwidth vs load resistance.
Inputs: `if_ma`, `ctr_percent`, `vcc_v`, `rload_ohm`; optional `bandwidth_hz`, `propagation_delay_ns`.
Returns `i_out_a`, `v_out_v`, `saturated`, `bandwidth_hz_at_rload`.

### `photonics_fiber_coupling`
Fiber coupling efficiency from Gaussian mode-field overlap and NA mismatch.
Inputs: `source_na`, `fiber_na`, `source_mode_diameter_m`, `fiber_mode_diameter_m`.
Returns `coupling_efficiency`, `coupling_loss_db`, `mode_overlap_efficiency`, `na_efficiency`.

### `photonics_solar_cell_iv`
Solar cell I-V characteristics via single-diode model: FF, Vmpp, Impp, Pmpp, and efficiency.
Inputs: `isc_a`, `voc_v`; optional `ideality_factor`, `series_resistance_ohm`, `shunt_resistance_ohm`, `temp_k`, `irradiance_w_per_m2`, `cell_area_m2`.
Returns `ff`, `pmpp_w`, `vmpp_v`, `impp_a`, `efficiency`.

### `photonics_tof_lidar`
Time-of-Flight/LiDAR received power, photocurrent SNR, maximum range, and round-trip time-of-flight.
Inputs: `peak_power_w`, `target_reflectivity`, `target_distance_m`, `aperture_diameter_m`, `receiver_responsivity_a_per_w`, `dark_current_a`, `bandwidth_hz`, `load_resistance_ohm`; optional `beam_divergence_rad`, `atmospheric_loss_db_per_km`, `temp_k`, `snr_min_db`.
Returns `p_rx_w`, `snr_db`, `snr_ok`, `range_limit_m`, `tof_s`.

## Example

Find responsivity of a silicon photodiode at 850 nm with QE = 0.85:

```json
{
  "tool": "photonics_photodiode_responsivity",
  "wavelength_m": 850e-9,
  "quantum_efficiency": 0.85
}
```
