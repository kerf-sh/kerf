# RF & Fiber-Optic Link Budget

Complete RF link budget (FSPL, EIRP, received power, noise figure, C/N,
Shannon capacity, BER, rain attenuation) and fiber-optic power budget
(loss margin, chromatic dispersion limit, OSNR).

## When to use

Link budget, FSPL, free-space path loss, Friis, EIRP, received power,
noise figure, cascaded NF, thermal noise, carrier-to-noise, C/N, SNR,
Shannon capacity, spectral efficiency, BER, BPSK, QPSK, QAM, Eb/N0,
rain attenuation, ITU-R P.838, fiber budget, fiber loss, chromatic
dispersion, OSNR, EDFA, optical SNR, satellite link, wireless budget,
RF margin.

## Tools

### `linkbudget_fspl`
Free-space path loss via Friis: FSPL = 20·log10(4π·d·f/c).
Inputs: `freq_hz`, `distance_m`. Returns `fspl_db`, `wavelength_m`.

### `linkbudget_eirp`
Effective isotropic radiated power: EIRP = P_tx + G_tx.
Inputs: `p_tx_dbw`, `g_tx_dbi`. Returns `eirp_dbw`, `eirp_dbm`.

### `linkbudget_received_power`
Friis received power including FSPL and miscellaneous losses.
Inputs: `p_tx_dbw`, `g_tx_dbi`, `g_rx_dbi`, `freq_hz`, `distance_m`, `other_losses_db`.
Returns `p_rx_dbw`, `p_rx_dbm`, `fspl_db`, `eirp_dbw`, `link_loss_db`.

### `linkbudget_noise_cascade`
Cascaded noise figure (Friis noise formula) for a receiver chain.
Inputs: `nf_db_list`, `gain_db_list` (one entry per stage).
Returns `nf_cascade_db`, `f_cascade_linear`, `stage_count`.

### `linkbudget_thermal_noise`
Thermal noise floor N = kTB.
Inputs: `bandwidth_hz`, optional `temp_k` (default 290 K).
Returns `noise_dbw`, `noise_dbm`, `noise_w`.

### `linkbudget_cn`
Carrier-to-noise ratio C/N = P_rx − N.
Inputs: `p_rx_dbw`, `noise_dbw`. Returns `cn_db`.

### `linkbudget_shannon`
Shannon channel capacity and spectral efficiency.
Inputs: `bandwidth_hz`, `snr_db`.
Returns `capacity_bps`, `spectral_efficiency_bps_per_hz`.

### `linkbudget_ber_bpsk`
BER for coherent BPSK or QPSK at a given Eb/N0.
Inputs: `eb_n0_db`, optional `modulation` (`BPSK`/`QPSK`).
Returns `ber`, `eb_n0_db`, `modulation`.

### `linkbudget_ber_qam`
Approximate BER for Gray-coded M-QAM at a given Eb/N0.
Inputs: `eb_n0_db`, `m` (power of 2, ≥ 4).
Returns `ber`, `eb_n0_db`, `m`.

### `linkbudget_required_ebn0`
Required Eb/N0 for a target BER by bisection inversion.
Inputs: `target_ber`, `modulation` (BPSK/QPSK/QAM/PSK), optional `m`.
Returns `eb_n0_db`, `eb_n0_linear`, `target_ber`.

### `linkbudget_rain_atten`
Rain path attenuation via ITU-R P.838-3: γ_R = k·R^α, A = γ_R·L.
Inputs: `freq_hz`, `rain_rate_mm_per_hr`, `path_length_km`.
Returns `a_rain_db`, `specific_atten_db_per_km`.

### `linkbudget_rf_budget`
Complete RF link budget in one call: FSPL, EIRP, P_rx, noise, C/N, margin.
Inputs: `p_tx_dbw`, `g_tx_dbi`, `g_rx_dbi`, `freq_hz`, `distance_m`,
`noise_figure_db`, `bandwidth_hz`, `required_snr_db`.
Returns `passes`, `margin_db`, `p_rx_dbw`, `cn_db`, `t_sys_k`.

### `linkbudget_fiber_budget`
Fiber-optic link power budget: margin = (P_tx − Rx_sensitivity) − losses.
Inputs: `p_tx_dbm`, `rx_sensitivity_dbm`, `fiber_loss_db_per_km`, `length_km`.
Returns `passes`, `margin_db`, `available_loss_db`.

### `linkbudget_fiber_cd`
Chromatic dispersion bandwidth limit for single-mode fiber.
Inputs: `dispersion_ps_per_nm_km`, `length_km`, `source_linewidth_nm`, optional `bit_rate_bps`.
Returns `cd_total_ps`, `bw_limit_bps`, `dispersion_limited`.

### `linkbudget_fiber_osnr`
OSNR for a multi-span EDFA-amplified fiber link.
Inputs: `p_signal_dbm`, `nf_amp_db`, `freq_hz`, `n_spans`, optional `noise_bandwidth_hz`.
Returns `osnr_db`, `n_ase_dbm`.

## Example

Complete RF link budget for a 2.4 GHz Wi-Fi hop at 100 m:

```json
{
  "tool": "linkbudget_rf_budget",
  "p_tx_dbw": -10,
  "g_tx_dbi": 3,
  "g_rx_dbi": 3,
  "freq_hz": 2.4e9,
  "distance_m": 100,
  "noise_figure_db": 7,
  "bandwidth_hz": 20e6,
  "required_snr_db": 20
}
```
