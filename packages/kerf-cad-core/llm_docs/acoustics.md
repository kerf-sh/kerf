# Engineering Acoustics — LLM Reference

Pure-Python ISO/IEC and ASHRAE acoustics calculations. No OCC dependency. All tools are
stateless — they compute and return results; no DB write. Units: dB, Hz, m, m².

---

## When to use

Keywords: acoustics, noise, sound, SPL, decibel, dB, reverberation, RT60, noise criteria,
NC rating, NR rating, transmission loss, TL, sound isolation, barrier, duct noise, octave
band, A-weighting, C-weighting, sound power, Lw, Lp, room acoustics, HVAC noise,
breakout noise.

---

## Tools

### `acoustics_spl_sum`

Logarithmic (energy) sum of multiple SPL values.

**Input:** `levels_db` — list of SPL values (dB).

**Returns:** `total_db` — combined level (10·log₁₀(Σ 10^(Lᵢ/10))).

---

### `acoustics_spl_subtract`

Background-noise subtraction: remove background level from measured total.

**Input:** `total_db`, `background_db` — both in dB.

**Returns:** `source_db` — corrected source level; warns if difference < 3 dB.

---

### `acoustics_spl_average`

Energy-average (Leq) of multiple SPL measurements.

**Input:** `levels_db` — list of dB values.

**Returns:** `Leq_db` — energy-averaged level.

---

### `acoustics_point_source`

SPL at distance `r` from a point source with known sound power level Lw.

**Input:** `Lw_db`, `r_m` (distance, m), `Q` (directivity factor, default 1 = free field), `alpha_bar` (room absorption, default 0 = outdoors).

**Returns:** `Lp_db`.

---

### `acoustics_line_source`

SPL at distance from an incoherent line source (road, pipe, rail).

**Input:** `Lw_per_m_db` (sound power per metre), `r_m` (perpendicular distance, m).

**Returns:** `Lp_db` using cylindrical spreading (-3 dB per doubling of distance).

---

### `acoustics_inverse_square`

Level change when distance from a point source changes.

**Input:** `r1_m`, `r2_m`.

**Returns:** `delta_L_db` = 20·log₁₀(r1/r2).

---

### `acoustics_sabine_rt60`

Sabine reverberation time for a room.

**Input:** `volume_m3`, `total_absorption_m2` (Σ Sᵢαᵢ).

**Returns:** `RT60_s` = 0.161 × V / A. Recommended for ᾱ < 0.2.

---

### `acoustics_eyring_rt60`

Eyring reverberation time (better accuracy at high absorption, ᾱ > 0.2).

**Input:** `volume_m3`, `total_surface_m2`, `mean_absorption_coeff`.

**Returns:** `RT60_s` using Eyring formula.

---

### `acoustics_room_constant`

Room constant R = Sᾱ / (1 − ᾱ).

**Input:** `total_surface_m2`, `mean_absorption_coeff`.

**Returns:** `R_m2`.

---

### `acoustics_reverberant_spl`

Reverberant-field SPL contribution from a source in a room.

**Input:** `Lw_db`, `R_m2` (room constant).

**Returns:** `Lp_reverberant_db` = Lw + 10·log₁₀(4/R).

---

### `acoustics_mass_law_tl`

Mass-law transmission loss through a partition.

**Input:** `mass_kg_m2` (surface density, kg/m²), `freq_hz` (frequency, Hz).

**Returns:** `TL_db` = 20·log₁₀(m·f) − 47.5 (field incidence mass law).

---

### `acoustics_composite_tl`

Composite partition TL for a wall with multiple elements (door, window, solid area).

**Input:** `elements` — list of `{area_m2, TL_db}` dicts.

**Returns:** `TL_composite_db`.

---

### `acoustics_spl_transmitted`

SPL on receiving side of a partition given source-room SPL and partition TL.

**Input:** `Lp_source_db`, `TL_db`, `S_wall_m2`, `R_receive_m2` (room constant of receiving room).

**Returns:** `Lp_receive_db`.

---

### `acoustics_a_weighting`

A-weighting correction at a single frequency.

**Input:** `freq_hz`.

**Returns:** `A_weight_db` — offset to add to unweighted SPL.

---

### `acoustics_c_weighting`

C-weighting correction at a single frequency.

**Input:** `freq_hz`.

**Returns:** `C_weight_db`.

---

### `acoustics_apply_weighting`

Apply A or C weighting to an octave-band spectrum and sum to weighted overall level.

**Input:** `octave_band_spls` — dict of `{freq_hz: SPL_db}`, `weighting` (`"A"` or `"C"`).

**Returns:** `weighted_overall_db`, `weighted_bands` (dict).

---

### `acoustics_octave_combine`

Combine octave-band SPLs to a single broadband level.

**Input:** `octave_band_spls` — dict of `{freq_hz: SPL_db}`.

**Returns:** `overall_db` — energy sum.

---

### `acoustics_nc_rating`

NC (Noise Criteria) rating from an octave-band spectrum (63–8000 Hz).

**Input:** `octave_band_spls` — dict `{freq_hz: SPL_db}`.

**Returns:** `nc_rating` — lowest integer NC curve not exceeded; warns above NC-70.

---

### `acoustics_nr_rating`

NR (Noise Rating) curve for an octave-band spectrum.

**Input:** `octave_band_spls` — dict `{freq_hz: SPL_db}`.

**Returns:** `nr_rating`.

---

### `acoustics_duct_attenuation`

Insertion loss of a lined or unlined rectangular HVAC duct section.

**Input:** `duct_width_m`, `duct_height_m`, `length_m`, `lining_thickness_m` (0 = unlined), `freq_hz`.

**Returns:** `attenuation_db`.

---

### `acoustics_duct_breakout`

Breakout noise transmitted through a rectangular duct wall.

**Input:** `duct_width_m`, `duct_height_m`, `length_m`, `Lw_in_db`, `TL_duct_db`, `room_constant_m2`.

**Returns:** `Lp_breakout_db`.

---

### `acoustics_duct_regen`

Regenerated noise from a duct fitting (elbow, tee, damper) using the ASHRAE power-law method.

**Input:** `fitting_type` (`"elbow"`, `"tee"`, `"damper"`), `velocity_m_s`, `duct_area_m2`.

**Returns:** `Lw_regen_db` per octave band.

---

### `acoustics_lw_from_lp`

Back-calculate sound power level Lw from a measured Lp at a known distance in free field.

**Input:** `Lp_db`, `r_m`, `Q` (directivity, default 1).

**Returns:** `Lw_db`.

---

### `acoustics_lp_from_lw`

Predict Lp at distance r from Lw (free-field or room).

**Input:** `Lw_db`, `r_m`, `Q` (directivity), `R_m2` (room constant, optional).

**Returns:** `Lp_db`.

---

## Example

```
# Combine two noise sources and find NC rating
acoustics_spl_sum  levels_db:[65, 68]       → total_db: 69.8
acoustics_a_weighting  freq_hz:1000         → A_weight_db: 0.0  (1 kHz reference)
acoustics_nc_rating  octave_band_spls:{"500":52,"1000":45,"2000":40}  → nc_rating: 40

# Predict SPL 10 m from 90 dB Lw point source outdoors
acoustics_lp_from_lw  Lw_db:90  r_m:10  Q:2  → Lp_db: 69.0
```
