# Antenna Element Design

Analytical antenna design: dipole, monopole, small loop, microstrip patch,
Yagi-Uda, helical, horn; plus gain/directivity/efficiency, beamwidth,
aperture, near/far-field boundaries, polarisation, ground-plane image,
ULA array factor, and VSWR bandwidth from Q.

## When to use

Antenna design, dipole, half-wave dipole, monopole, quarter-wave,
small loop, NFC loop, microstrip patch, patch antenna, inset feed,
Yagi-Uda, director, reflector, helical axial, helix, horn antenna,
gain, directivity, efficiency, HPBW, beamwidth, aperture efficiency,
effective aperture, near field, far field, Fraunhofer, reactive near field,
polarisation, axial ratio, polarisation loss, ground plane, image theory,
uniform linear array, ULA, grating lobe, array factor, VSWR bandwidth,
antenna Q, impedance matching, 50 ohm.

## Tools

### `antenna_half_wave_dipole`
Half-wave dipole resonant length, input impedance (73.1+j42.5 Ω), gain (2.15 dBi),
HPBW, and VSWR=2 bandwidth (Balanis §4.3).
Inputs: `freq_hz`; optional `efficiency`, `wire_diameter_m`.
Returns `resonant_length_m`, `R_in_ohm`, `X_in_ohm`, `gain_dbi`, `vswr_bw_hz`.

### `antenna_monopole`
Quarter-wave monopole over ground: R_in = 36.5 Ω, gain = 5.16 dBi (image theory).
Inputs: `freq_hz`; optional `efficiency`.
Returns `resonant_length_m`, `R_in_ohm`, `gain_dbi`.

### `antenna_small_loop`
Electrically-small loop radiation resistance and gain; warns when ka ≥ 0.5.
Inputs: `freq_hz`, `loop_area_m2`; optional `n_turns`, `efficiency`.
Returns `radiation_resistance_ohm`, `gain_dbi`, `ka`, `electrically_small`.

### `antenna_microstrip_patch`
Rectangular microstrip patch: width W, length L, fringing ΔL, edge impedance,
inset-feed distance y₀ for 50 Ω match, and gain (Balanis §14.2).
Inputs: `freq_hz`, `er`, `h_m`; optional `efficiency`.
Returns `patch_width_m`, `patch_length_m`, `er_eff`, `edge_impedance_ohm`, `inset_feed_m`, `gain_dbi`.

### `antenna_yagi_uda`
Yagi-Uda element dimensions, estimated gain, and F/B ratio (Kraus empirical).
Inputs: `freq_hz`; optional `n_directors`, `boom_wavelengths`, `efficiency`.
Returns `driven_length_m`, `reflector_length_m`, `director_length_m`, `gain_dbi`, `fb_ratio_db`.

### `antenna_helical_axial`
Axial-mode helix gain, HPBW, axial ratio, and input impedance (Kraus §7-5).
Inputs: `freq_hz`, `n_turns`; optional `circumference_wavelengths`, `pitch_angle_deg`.
Returns `gain_dbi`, `hpbw_deg`, `axial_ratio`, `R_in_ohm`, `axial_length_m`.

### `antenna_horn_gain`
Horn antenna gain from aperture dimensions: G = η·ηap·4π·a·b/λ².
Inputs: `freq_hz`, `aperture_width_m`, `aperture_height_m`; optional `aperture_efficiency`.
Returns `gain_dbi`, `hpbw_e_plane_deg`, `hpbw_h_plane_deg`, `effective_aperture_m2`.

### `antenna_directivity_gain`
Compute the missing member of the D / G / η triangle (provide any 2 of 3).
Inputs: `directivity`, `gain_dbi`, `efficiency` (any 2).
Returns all three.

### `antenna_beamwidth_dir`
Directivity from E- and H-plane HPBW (Kraus + Tai-Pereira approximations).
Inputs: `hpbw_e_deg`, `hpbw_h_deg`.
Returns `directivity_kraus`, `directivity_tai`, `gain_dbi_kraus`, `gain_dbi_tai`.

### `antenna_aperture_eff`
Effective aperture Aeff = G·λ²/(4π); aperture efficiency ηap if physical area given.
Inputs: `freq_hz`, `gain_dbi`; optional `physical_aperture_m2`.
Returns `effective_aperture_m2`, `aperture_efficiency`.

### `antenna_near_far_field`
Fraunhofer far-field distance (2D²/λ), reactive near-field, and plane-wave boundary.
Inputs: `freq_hz`, `max_dimension_m`.
Returns `fraunhofer_distance_m`, `reactive_near_field_m`, `plane_wave_boundary_m`.

### `antenna_polarization_ar`
Polarisation loss factor from axial ratio; linear-to-linear tilt loss.
Inputs: `axial_ratio`; optional `tilt_angle_deg`.
Returns `plf_worst_case`, `plf_loss_db_worst`, `is_circular`, `is_linear`.

### `antenna_ground_plane_image`
Convert dipole parameters to monopole-over-ground via image theory.
Inputs: `dipole_R_in_ohm`, `dipole_X_in_ohm`, `dipole_gain_dbi`.
Returns `monopole_R_in_ohm`, `monopole_X_in_ohm`, `monopole_gain_dbi`.

### `antenna_array_factor_ula`
ULA array gain, HPBW, grating-lobe check, and null angles.
Inputs: `freq_hz`, `n_elements`, `element_spacing_m`; optional `scan_angle_deg`.
Returns `array_gain_dbi`, `hpbw_deg`, `grating_lobe_present`, `grating_lobe_angles_deg`.

### `antenna_vswr_bw`
VSWR bandwidth from antenna Q (Yaghjian & Best 2005): BW = (S−1)/(Q·√S).
Inputs: `freq_hz`, `q_factor`; optional `vswr_limit` (default 2.0).
Returns `bw_fraction`, `bw_hz`, `bw_lower_hz`, `bw_upper_hz`, `return_loss_db`.

## Example

Design a 2.4 GHz rectangular microstrip patch on FR4 (εr = 4.4, h = 1.6 mm):

```json
{
  "tool": "antenna_microstrip_patch",
  "freq_hz": 2.4e9,
  "er": 4.4,
  "h_m": 0.0016
}
```
