# Lighting Design — Illumination Engineering

Pure-Python illumination engineering module covering the IES lumen method,
point-by-point calculations, glare, road lighting, emergency lighting, lamp
efficacy, and energy-code compliance. References IES Handbook 10th ed.,
EN 12464-1, CIE 117-1995, and ASHRAE 90.1.

---

## When to use

Reach for this module when the user asks about:

- number of luminaires needed for a target lux level (lumen method)
- room cavity ratio (RCR), coefficient of utilization (CU), light loss factor (LLF)
- average illuminance from a known luminaire count
- spacing-to-mounting-height ratio or uniformity check
- horizontal or vertical illuminance at a point (inverse-square law)
- superposition of multiple luminaires at a calculation point
- luminance, luminous exitance, or contrast ratio of a surface
- glare rating (UGR) for interior lighting
- road luminance, pole spacing, roadway utilization method
- emergency lighting lux and maximum spacing (NFPA 101 / BS 5266)
- lamp efficacy (lm/W) by lamp type
- lighting power density (LPD) compliance — ASHRAE 90.1 or California Title 24

---

## Tools

### `lighting_room_cavity_ratio`

Compute the Room Cavity Ratio (RCR) for the IES zonal-cavity lumen method.
RCR = 5 × h_cavity × (L + W) / (L × W).
Inputs: `length_m`, `width_m`, `height_cavity_m` (all required).
Returns: `rcr`.

### `lighting_coefficient_of_utilization`

Interpolate CU from the built-in IES representative table for given RCR and
room reflectances.
Inputs: `rcr` (required); optional `rho_ceiling_pct` (default 70),
`rho_walls_pct` (default 50).
Returns: `cu`, `rcr_used`, `reflectance_key`.

### `lighting_light_loss_factor`

Compute total LLF = LLD × LDD × ballast_factor × temperature_factor.
All inputs optional (defaults: LLD 0.85, LDD 0.90, ballast 1.0, temp 1.0).
Returns: `llf`, component factors.

### `lighting_luminaires_for_target_lux`

Calculate the number of luminaires needed for a target maintained illuminance
using N = ⌈(E × A) / (Φ × n_lamps × CU × LLF)⌉.
Inputs: `area_m2`, `target_lux`, `lumens_per_lamp` (required); optional
`lamps_per_luminaire`, `cu`, `llf`.
Returns: `n_luminaires`, `actual_avg_lux`.

### `lighting_lux_from_luminaires`

Calculate average maintained illuminance from a fixed number of luminaires
using E = (N × Φ × n_lamps × CU × LLF) / A.
Inputs: `n_luminaires`, `lumens_per_lamp`, `area_m2` (required); optional
`lamps_per_luminaire`, `cu`, `llf`.
Returns: `avg_lux`.

### `lighting_spacing_mh_ratio`

Compute luminaire spacing-to-mounting-height (S/MH) ratio. Values > 1.5
indicate likely poor uniformity.
Inputs: `spacing_m`, `mounting_height_m` (required).
Returns: `s_mh_ratio`, `warnings`.

### `lighting_uniformity_check`

Check illuminance uniformity U = E_min / E_avg against EN 12464-1 limit.
Inputs: `min_lux`, `avg_lux` (required); optional `uniformity_limit`
(default 0.70).
Returns: `uniformity_ratio`, `pass`, `warnings`.

### `lighting_horizontal_illuminance`

Horizontal illuminance at a point from a single source: E_h = I × cos(θ) / d².
Inputs: `intensity_cd`, `distance_m` (required); optional
`angle_from_nadir_deg` (default 0).
Returns: `e_horizontal_lux`.

### `lighting_vertical_illuminance`

Vertical illuminance at a point: E_v = I × sin(θ) × cos(θ) / d². Useful for
façade, signage, and vertical-surface tasks.
Inputs: `intensity_cd`, `distance_m`, `angle_from_nadir_deg` (all required).
Returns: `e_vertical_lux`.

### `lighting_multi_luminaire`

Total illuminance at a point by superposition of contributions from multiple
luminaires (point method). Each luminaire: {x, y, z, intensity_cd}.
Inputs: `luminaires` (list), `point` {x, y, z} (required); optional
`plane` (horizontal/vertical).
Returns: `total_lux`, per-luminaire contributions.

### `lighting_luminance`

Lambertian surface luminance: L = E × ρ / π [cd/m²].
Inputs: `illuminance_lux`, `reflectance` (required).
Returns: `luminance_cd_m2`.

### `lighting_exitance`

Lambertian luminous exitance: M = E × ρ [lm/m²].
Inputs: `illuminance_lux`, `reflectance` (required).
Returns: `exitance_lm_m2`.

### `lighting_contrast_ratio`

Weber contrast ratio C = (L_task − L_bg) / L_bg. Good legibility requires
|C| ≥ 0.3.
Inputs: `luminance_task`, `luminance_background` (required).
Returns: `contrast_ratio`.

### `lighting_ugr`

CIE 117-1995 Unified Glare Rating (UGR). EN 12464-1 limits: ≤ 19 offices,
≤ 22 industrial, ≤ 28 absolute threshold.
Inputs: `background_luminance_cd_m2`, `luminaire_luminances_cd_m2` (list),
`solid_angles_sr` (list), `guth_position_indices` (list) — all required.
Returns: `ugr`, `warnings`.

### `lighting_road_luminance`

Road surface luminance using simplified CIE R-table model:
L = I × r / H². Default r = 0.07 (R2/R3 asphalt).
Inputs: `intensity_cd`, `distance_m`, `angle_from_nadir_deg` (required);
optional `r_table_factor`.
Returns: `road_luminance_cd_m2`.

### `lighting_pole_spacing`

Recommended roadway pole spacing from mounting height and S/H ratio.
Spacing = S/H_ratio × mounting_height.
Inputs: `mounting_height_m` (required); optional `spacing_to_height_ratio`
(default 3.0).
Returns: `spacing_m`.

### `lighting_roadway_utilization`

Average road illuminance and luminance using the luminance (utilization) method:
E_road = (Φ × UF) / (W × S).
Inputs: `luminaire_lumens`, `utilization_factor`, `road_width_m`, `spacing_m`,
`mounting_height_m` (all required).
Returns: `avg_road_lux`, `avg_road_luminance_cd_m2`.

### `lighting_emergency_lux`

Floor-level illuminance below an emergency luminaire using E = I / d².
NFPA 101 / BS 5266 minimum: ≥ 1.0 lx on escape route centreline.
Inputs: `intensity_cd`, `distance_m` (required).
Returns: `e_floor_lux`, `warnings`.

### `lighting_emergency_spacing`

Maximum spacing between emergency luminaires so midpoint meets minimum lux.
S_max = 2 × √(I/E_min − h²).
Inputs: `mounting_height_m` (required); optional `min_lux_target` (default 1.0),
`intensity_cd` (default 100).
Returns: `max_spacing_m`.

### `lighting_lamp_lpw`

Approximate initial luminous efficacy (lm/W) for a lamp type.
Supported types include: `led_standard` (100), `led_high_output` (140),
`fluorescent_t8` (85), `metal_halide` (80), `high_pressure_sodium` (100),
`incandescent` (15), and others.
Inputs: `lamp_type` (required).
Returns: `lumens_per_watt`, `lamp_type`.

### `lighting_lamp_energy`

Lamp energy consumption: Energy (kWh) = wattage × hours / 1000.
Inputs: `wattage_W`, `hours` (required).
Returns: `energy_Wh`, `energy_kWh`.

### `lighting_lpd_check`

Lighting Power Density (LPD) compliance against ASHRAE 90.1-2022 or Title 24
(2022). LPD = total_watts / area_m2 [W/m²].
Inputs: `total_watts`, `area_m2` (required); optional `building_type`
(default 'office'), `standard` (ASHRAE/Title24).
Returns: `lpd_W_m2`, `allowance_W_m2`, `compliant`, `warnings`.

---

## Example

**User ask:** "I have a 10 m × 8 m office with 2.8 m luminaire mounting height
above the 0.8 m work-plane. Target 500 lx. LED panels, 4 400 lm each. What is
the LPD?"

1. `lighting_room_cavity_ratio` — length_m: 10, width_m: 8, height_cavity_m: 2.0
2. `lighting_coefficient_of_utilization` — rcr from step 1, rho_ceiling_pct: 70
3. `lighting_light_loss_factor` — lld: 0.90, ldd: 0.92
4. `lighting_luminaires_for_target_lux` — area_m2: 80, target_lux: 500,
   lumens_per_lamp: 4400, cu from step 2, llf from step 3
5. `lighting_lpd_check` — total_watts: (n × 40 W), area_m2: 80,
   building_type: 'office'
