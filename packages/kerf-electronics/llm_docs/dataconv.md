# ADC / DAC Data Converter Design

System-level performance analysis for ADCs and DACs: ideal SNR, ENOB,
noise budget, oversampling gain, delta-sigma SQNR, SAR timing, pipeline
latency, DAC glitch, reference noise, driver settling, and dynamic range.

## When to use

ADC, DAC, analog-to-digital, digital-to-analog, SNR, ENOB, SINAD, SFDR,
THD, dynamic range, noise budget, quantisation noise, aperture jitter,
kTC noise, oversampling, OSR, delta-sigma, ΔΣ, SQNR, noise shaping, SAR,
successive approximation, pipeline ADC, DAC glitch, INL, DNL, SFDR,
reference noise, voltage reference drift, driver settling, anti-alias filter.

## Tools

### `adc_ideal_snr`
Ideal SNR for N-bit ADC: SNR = 6.02·N + 1.76 dB (Bennett 1948).
Input: `bits`. Returns `snr_ideal_db`, `dynamic_range_db`.

### `adc_snr_with_backoff`
SNR with input backoff below full scale.
Inputs: `bits`, `backoff_db` (≤ 0).
Returns `snr_ideal_db`, `snr_actual_db`, `enob_actual`.

### `adc_enob_from_sinad`
ENOB from measured SINAD: ENOB = (SINAD − 1.76) / 6.02 (IEEE 1241).
Input: `sinad_db`. Returns `enob`, `implied_ideal_bits`.

### `adc_interconvert_metrics`
Interconvert SNR, SFDR, THD, SINAD — provide any 3, compute the 4th.
Inputs: `snr_db`, `sfdr_dbc`, `thd_dbc`, `sinad_db` (any 3 of 4).
Returns all four metrics plus `enob`.

### `adc_total_noise_budget`
RSS noise budget: quantisation + kTC + aperture jitter + amplifier noise.
Inputs: `bits`, `v_fs`, `freq_in_hz`, `t_jitter_s`; optional cap, en_amp, bw, temp.
Returns `vn_total_vrms`, `snr_total_db`, `dominant_noise`, `warnings_list`.

### `adc_oversampling_gain`
Oversampling processing gain and required OSR for a target ENOB.
Inputs: `bits`, `osr`; optional `target_enob`.
Returns `process_gain_db`, `snr_with_osr_db`, `enob_with_osr`, `osr_required`.

### `dac_delta_sigma_sqnr`
Ideal ΔΣ modulator SQNR and noise-shaping (Candy & Temes 1992).
Inputs: `order` (1–8), `osr`.
Returns `sqnr_db`, `enob_equivalent`, `osr_insufficient`.

### `adc_sar_conversion_time`
SAR ADC conversion time including comparator and RC kickback settling.
Inputs: `bits`, `t_comp_s`, `t_sw_s`; optional `r_src_ohm`, `c_dac_f`.
Returns `t_total_s`, `throughput_max_sps`.

### `adc_pipeline_latency`
Pipeline ADC latency, total bits, and stage residue gain.
Inputs: `num_stages`, `bits_per_stage`, `t_clk_s`; optional `flash_bits`.
Returns `total_bits_nominal`, `latency_s`, `latency_clocks`, `throughput_sps`.

### `dac_glitch_sfdr`
DAC glitch/settling analysis and SFDR estimate from INL.
Inputs: `bits`, `inl_lsb`, `v_fs`, `v_glitch_v`, `t_glitch_s`, `tau_s`.
Returns `lsb_size_v`, `sfdr_dbc`, `e_glitch_vs`, `t_settle_s`.

### `adc_reference_noise`
Reference noise and temperature-drift contribution to LSB error.
Inputs: `bits`, `v_ref`, `e_ref_rms_v`; optional `drift_ppm_per_c`, `delta_temp_c`.
Returns `lsb_v`, `snr_ref_db`, `drift_error_lsb`, `drift_error_v`.

### `adc_driver_settling`
Driver and RC anti-alias filter kickback settling time.
Inputs: `bits`, `r_ohm`, `c_in_f`; optional `c_aa_f`.
Returns `tau_s`, `t_settle_s`, `f_aa_3db_hz`, `t_settle_aa_s`.

### `adc_bits_for_dynamic_range`
Minimum ADC bits for a target dynamic range: N = ceil((DR − 1.76) / 6.02).
Input: `dr_db`. Returns `bits_min`, `snr_achieved_db`, `margin_db`.

## Example

Determine ENOB from a measured SINAD of 68 dB, then check if oversampling
by 16× can reach 14-bit performance:

```json
{"tool": "adc_enob_from_sinad", "sinad_db": 68}
{"tool": "adc_oversampling_gain", "bits": 12, "osr": 16, "target_enob": 14}
```
