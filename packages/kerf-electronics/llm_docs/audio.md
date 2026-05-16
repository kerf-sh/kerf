# Audio Electronics & Loudspeaker Design

Power amplifier class analysis (A, B, AB, D), heatsink sizing, Thiele-Small
sealed and vented enclosure design, driver SPL, passive crossovers, Zobel
networks, L-pad attenuators, damping factor, SPL calculations, dB conversions,
A-weighting, and impedance bridging.

## When to use

Audio amplifier, class A, class B, class AB, class D, power amplifier, efficiency,
quiescent current, device dissipation, switching amplifier, LC output filter, dead time,
heatsink, thermal resistance, Thiele-Small, sealed enclosure, vented enclosure,
bass-reflex, Qtc, QB3, SBB4, box volume, port tuning, port velocity, chuffing, driver
SPL, sensitivity, maximum SPL, excursion, xmax, passive crossover, Butterworth crossover,
Linkwitz-Riley, crossover frequency, Zobel network, impedance compensation, voice coil
inductance, L-pad attenuator, level matching, damping factor, cone control, SPL addition,
inverse-square law, dB, decibel, voltage ratio, power ratio, A-weighting, IEC 61672,
impedance bridging, line level.

## Tools

### `audio_amp_class_a`
Class-A single-ended amplifier: quiescent current, max output power, supply power, device dissipation, and efficiency (max 25%).
Inputs: `vcc`, `rl`; optional `iq_factor`.
Returns `iq_a`, `pout_max_w`, `psupply_w`, `pdiss_max_w`, `efficiency_max_pct`.

### `audio_amp_class_b`
Class-B push-pull amplifier: max output power, per-device worst-case dissipation, and theoretical efficiency (π/4 ≈ 78.5%).
Inputs: `vcc`, `rl`.
Returns `pout_max_w`, `pdiss_per_device_max_w`, `efficiency_max_pct`.

### `audio_amp_class_ab`
Class-AB efficiency bounds (25–78.5%) and practical output power estimate.
Inputs: `vcc`, `rl`; optional `vq`.
Returns `pout_max_w`, `efficiency_lower_pct`, `efficiency_upper_pct`, `efficiency_estimate_pct`.

### `audio_amp_class_d`
Class-D switching amplifier: max output power, dead-time switching loss, estimated practical efficiency, and 2nd-order Butterworth LC output filter values.
Inputs: `vcc`, `rl`, `fsw_hz`; optional `dead_time_ns`, `lc_order`.
Returns `pout_max_w`, `efficiency_est_pct`, `filter_L_H`, `filter_C_F`, `filter_fb_hz`.

### `audio_heatsink_rth`
Required heatsink Rth_sa for an amplifier device given junction budget: solves Tj = Ta + Pdiss × (Rth_jc + Rth_cs + Rth_sa).
Inputs: `pdiss_w`, `tj_max_c`, `ta_c`, `rth_jc`; optional `rth_cs`.
Returns `rth_sa_required_c_per_w`, `tj_actual_c`.

### `audio_sealed_box`
Thiele-Small sealed enclosure: box volume, system resonance, and −3 dB frequency for a target Qtc.
Inputs: `vas_l`, `qts`, `fs_hz`; optional `qtc` (default 0.707 Butterworth).
Returns `vb_l`, `fc_hz`, `f3_hz`, `alpha`.

### `audio_vented_box`
Thiele-Small vented (bass-reflex) enclosure: QB3 or SBB4 alignment, box volume, port tuning frequency, port length, and port air velocity (warns > 17 m/s).
Inputs: `vas_l`, `qts`, `fs_hz`, `re_ohm`, `sd_cm2`; optional `alignment`, `port_diameter_mm`.
Returns `vb_l`, `fb_hz`, `port_length_mm`, `port_velocity_mps`, `chuffing_warning`.

### `audio_driver_spl`
Driver SPL at rated power and excursion-limited maximum SPL.
Inputs: `sensitivity_db_1w_1m`, `power_w`, `xmax_mm`, `sd_cm2`, `re_ohm`; optional `distance_m`.
Returns `spl_at_rated_power_db`, `spl_excursion_limited_100hz_db`.

### `audio_crossover`
Passive crossover component values (L and C) for Butterworth (1st–4th order) or Linkwitz-Riley (2nd, 4th order) topologies.
Inputs: `fc_hz`, `z_load`; optional `order`, `topology`.
Returns `components[]` list with type, value in H/mH or F/µF per stage.

### `audio_zobel`
Zobel RC impedance-compensation network: Rz = Re, Cz = Le/Re².
Inputs: `re_ohm`, `le_mh`.
Returns `rz_ohm`, `cz_uF`.

### `audio_lpad`
L-pad attenuator series (Rs) and shunt (Rp) resistors for loudspeaker level matching while maintaining load impedance.
Inputs: `attenuation_db`, `z_source`, `z_load`.
Returns `rs_ohm`, `rp_ohm`, `actual_attenuation_db`.

### `audio_damping_factor`
Amplifier damping factor including cable resistance: DF = Re / (Zout + R_cable); warns when DF < 10.
Inputs: `amp_zout_ohm`, `re_ohm`; optional `cable_r_ohm`.
Returns `damping_factor`, `quality_note`.

### `audio_spl_add`
Incoherent SPL addition: SPL_total = 10 × log10(Σ 10^(SPLi/10)).
Inputs: `spl_values_db` (list, ≥ 2 values).
Returns `spl_total_db`.

### `audio_spl_distance`
SPL at a new distance by inverse-square law (free-field point source).
Inputs: `spl_ref_db`, `d_ref_m`, `d_target_m`.
Returns `spl_target_db`.

### `audio_db_voltage`
Voltage ratio to dB: 20 × log10(V_out / V_in).
Inputs: `v_ratio`.
Returns `db`.

### `audio_db_power`
Power ratio to dB: 10 × log10(P_out / P_in).
Inputs: `p_ratio`.
Returns `db`.

### `audio_a_weighting`
A-weighting correction [dB] at a given frequency, normalised to 0 dB at 1 kHz (IEC 61672-1).
Inputs: `freq_hz`.
Returns `a_weighting_db`.

### `audio_impedance_bridge`
Line-level impedance bridging check: ratio Z_load/Z_source, voltage transfer dB, and bridging condition (≥ 10×); warns when not met.
Inputs: `z_source`, `z_load`.
Returns `ratio`, `av_db`, `power_transfer_db`, `bridging_ok`.

## Example

Design a sealed enclosure for a 6.5-inch woofer (Vas = 25 L, Qts = 0.35, fs = 45 Hz) targeting Qtc = 0.707:

```json
{
  "tool": "audio_sealed_box",
  "vas_l": 25,
  "qts": 0.35,
  "fs_hz": 45,
  "qtc": 0.707
}
```
