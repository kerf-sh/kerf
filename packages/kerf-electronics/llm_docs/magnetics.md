# Magnetics Design

Switched-mode transformer and inductor design: core selection (area-product
and Kg methods), primary turns, inductor turns, air-gap sizing, wire AWG,
Steinmetz core loss, Dowell AC copper loss, temperature rise, and saturation
check.

## When to use

Transformer design, inductor design, flyback, forward converter, buck,
boost, core selection, ETD, EE, PQ, toroid, ferrite, N87, Steinmetz,
core loss, copper loss, Dowell, skin effect, proximity effect, winding loss,
air gap, AL value, turns, Faraday, Ampere, flux density, Bmax, Bsat,
saturation, window utilisation, AWG, current density, wire gauge,
temperature rise, thermal model, heatsink, SMPS magnetics, power converter.

## Tools

### `magnetics_core_select_ap`
Core selection by area-product method: Ap = Wa·Ae = S/(kt·kw·Bmax·J·fsw).
Returns the smallest core from the built-in ETD/EE/PQ/toroid catalogue meeting Ap.
Inputs: `power_va`, `freq_hz`, `bmax_t`; optional `j_am2`, `kw`, `kt`.
Returns `ap_required_cm4`, `selected_core`, `candidates`.

### `magnetics_core_select_kg`
Core selection by geometric constant: Kg = Ae²·Wa/MLT (McLyman §3.4).
Inputs: `power_va`, `freq_hz`, `bmax_t`; optional `rdc_target_ohm`, `j_am2`, `kw`.
Returns `kg_required_m5`, `selected_core`, `candidates`.

### `magnetics_transformer_turns`
Primary turns from Faraday's law (square-wave or sinusoidal).
Square-wave: Np = V/(4·f·Bmax·Ae); sinusoidal: Np = V/(4.44·f·Bmax·Ae).
Inputs: `v_primary`, `freq_hz`, `bmax_t`, `ae_m2`; optional `waveform`.
Returns `Np` (ceil integer), `Np_exact`, `waveform`.

### `magnetics_inductor_turns`
Inductor turns from Ampere's law: N = L·I_peak/(Bmax·Ae).
Inputs: `inductance_h`, `i_peak_a`, `bmax_t`, `ae_m2`.
Returns `N` (ceil integer), `N_exact`.

### `magnetics_gap_length`
Air-gap length and resulting AL for a gapped inductor (with fringing correction).
lg = μ0·N²·Ae/L; AL = μ0·Ae/(lg_eff + le/μi).
Inputs: `inductance_h`, `n_turns`, `ae_m2`; optional `mu_i`.
Returns `lg_mm`, `lg_eff_mm`, `fringing_factor`, `AL_nH_per_turn2`.

### `magnetics_awg_select`
Wire AWG selection from RMS current and current density.
A_wire = I_rms/J; returns finest AWG whose area ≥ A_wire.
Inputs: `i_rms_a`; optional `j_am2` (default 4 MA/m²).
Returns `awg`, `diameter_mm`, `area_mm2`, `rdc_ohm_per_m`, `actual_j_am2`.

### `magnetics_core_loss`
Steinmetz volumetric and total core loss: Pv = k·f^α·B_peak^β.
Built-in materials: N87, N49, 3C95, 77-series, and more.
Inputs: `freq_hz`, `b_peak_t`, `core_volume_m3`; optional `material` (default N87).
Returns `p_volume_w_m3`, `p_core_w`, `saturation_flag`, `Bsat_t`.

### `magnetics_copper_loss`
DC + Dowell AC winding loss: P = I²·Rdc·Fr.
Supply `fr` directly, or provide `freq_hz`, `wire_dia_m`, `n_layers` for auto Fr.
Inputs: `i_rms_dc_a`, `rdc_ohm`; optional Fr or Dowell inputs.
Returns `p_dc_w`, `p_ac_w`, `p_total_w`, `rac_ohm`.

### `magnetics_temperature_rise`
Temperature rise via surface-area convection or thermal-resistance model.
ΔT = P/(h·A_surface) or ΔT = P·Rth; warns when Tambient + ΔT > T_max.
Inputs: `p_total_w`, one of `surface_area_m2` or `rth_c_per_w`; optional `t_ambient_c`, `t_max_c`.
Returns `delta_t_k`, `t_total_c`, `t_margin_k`, `over_temp`.

### `magnetics_saturation_check`
Peak flux density vs Bsat check: B_peak = μ0·μi·N·I_peak/le.
Warns when B_peak ≥ Bsat or within 5% margin.
Inputs: `n_turns`, `i_peak_a`, `ae_m2`, `le_m`, `mu_i`; optional `material` or `bsat_override_t`.
Returns `b_peak_t`, `bsat_t`, `margin_t`, `saturated`.

## Example

Select a core for a 100 W, 100 kHz flyback transformer targeting Bmax = 0.2 T:

```json
{
  "tool": "magnetics_core_select_ap",
  "power_va": 100,
  "freq_hz": 100000,
  "bmax_t": 0.2,
  "kt": 0.5
}
```
