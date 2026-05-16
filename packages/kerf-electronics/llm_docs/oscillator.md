# Crystal Oscillator and PLL Design

Kerf provides oscillator and PLL design tools: crystal load cap selection, Pierce oscillator negative-resistance margin, drive-level check, frequency pulling, ppm error budget, RC/LC/ring oscillator frequencies, PLL divider N, loop filter components, lock time, and phase-noise-to-jitter conversion.

## When to use

Use these tools when you need to:
- Select external load capacitors for a Pierce crystal oscillator
- Check whether an inverter's gm provides enough negative resistance to guarantee oscillator startup
- Verify that the drive level won't damage a crystal
- Compute frequency pulling in ppm from a load capacitance mismatch
- Build a frequency accuracy error budget (initial tolerance + temp + aging + load pulling)
- Calculate RC, LC (Colpitts/Clapp/Hartley), or ring oscillator frequency
- Find the integer-N or fractional-N PLL divider for a target output frequency
- Design a type-II charge-pump PLL loop filter (2nd or 3rd order) for a given bandwidth and phase margin
- Estimate PLL lock time after a frequency hop
- Convert phase noise [dBc/Hz] to integrated RMS jitter

Trigger keywords: crystal oscillator, Pierce oscillator, load capacitance, CL, crystal ESR, negative resistance, gm margin, drive level, frequency pulling, ppm budget, frequency accuracy, aging, temperature coefficient, RC oscillator, LC oscillator, Colpitts, ring oscillator, PLL, phase-locked loop, divider N, loop filter, charge pump, loop bandwidth, phase margin, lock time, phase noise, jitter, TCXO, VCXO.

## Tools

| Tool | Purpose |
|---|---|
| `osc_crystal_load_caps` | Computes external load capacitors for a target CL, accounting for PCB stray capacitance; inputs: cl_target_f, cstray_f |
| `osc_pierce_neg_resistance` | Pierce oscillator negative resistance and gm_margin; oscillation guaranteed when margin ≥ safety_factor; inputs: freq_hz, gm_s, c1_f, c2_f, esr_ohm |
| `osc_drive_level` | Estimates power dissipated in crystal (drive level in μW) to verify it won't be damaged; inputs: freq_hz, esr_ohm, c_load_f, v_osc_v |
| `osc_frequency_pulling` | Frequency shift in ppm from CL deviation vs nominal (IEC 60444-5); inputs: freq_hz, cm_f, c0_f, cl_nominal_f, cl_actual_f |
| `osc_ppm_budget` | RSS frequency accuracy budget from initial_tolerance_ppm, temp_ppm, aging_ppm, load_ppm; returns total_ppm and within-budget flag |
| `osc_rc_frequency` | RC oscillator frequency = 1/(2π×R×C); inputs: r_ohm, c_f, rc_factor |
| `osc_lc_frequency` | LC tank resonant frequency = 1/(2π×sqrt(L×C)); inputs: l_h, c_f |
| `osc_ring_frequency` | Ring oscillator frequency = 1/(2×N×τ_pd); inputs: n_stages (odd), tau_pd_s |
| `pll_divider_n` | PLL feedback divider N from f_out_hz and f_ref_hz; supports integer-N and fractional-N; returns freq_error_ppm |
| `pll_loop_filter` | Type-II charge-pump PLL loop filter R, C1, C2; inputs: f_loop_bw_hz, phase_margin_deg, icp_a, kvco_hz_per_v, n_divider |
| `pll_lock_time` | Estimated PLL acquisition lock time for a frequency step; inputs: f_loop_bw_hz, zeta, f_step_hz |
| `pll_phase_noise_to_jitter` | Converts flat phase noise floor [dBc/Hz] to integrated RMS jitter [s, ps, fs]; inputs: f_osc_hz, phase_noise_dbc_hz, integration_bw_hz |

## Example

**User ask:** "I have a 32.768 kHz crystal with CL=12.5 pF and ESR=80 kΩ. My MCU inverter has gm=1 mA/V. Will it start reliably?"

1. Call `osc_crystal_load_caps` with `cl_target_f=12.5e-12` → get symmetric external cap values.
2. Call `osc_pierce_neg_resistance` with `freq_hz=32768`, `gm_s=1e-3`, `c1_f` and `c2_f` from step 1, `esr_ohm=80e3` → verify gm_margin ≥ 3.
