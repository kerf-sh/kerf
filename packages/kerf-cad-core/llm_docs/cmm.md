# CMM Inspection Planning & Measurement Analysis

Pure-Python coordinate measuring machine (CMM) inspection tools covering
least-squares geometry fitting, datum-reference-frame alignment, GD&T evaluation
(flatness/circularity/cylindricity/perpendicularity/parallelism/angularity/position/
profile), GUM measurement uncertainty, probe compensation, sample-point
recommendations, Gauge R&R (ANOVA and average-range), and process capability
Cpk/Ppk. No OCC dependency. All tools are stateless and never raise.

---

## When to use

Use when the user asks about: CMM, coordinate measuring machine, inspection, measured
points, point cloud, least squares fit, best-fit geometry, datum alignment, 3-2-1
alignment, best-fit alignment, GD&T, flatness, circularity, roundness, cylindricity,
perpendicularity, parallelism, angularity, true position, MMC, maximum material
condition, surface profile, GUM, measurement uncertainty, Type A uncertainty, Type B
uncertainty, expanded uncertainty, coverage factor, probe radius compensation, stylus
compensation, sample points, Nyquist, Gauge R&R, MSA, ANOVA, average range, process
capability, Cpk, Ppk, ISO 1101, ASME Y14.5.

---

## Tools

### `cmm_fit_geometry`

Least-squares fit of a geometric primitive to measured 3D points.

**Input:**
- `shape` (required) — `"line"`, `"plane"`, `"circle"`, `"sphere"`, or `"cylinder"`
- `points` (required) — list of `[x, y, z]` points (≥ 2)
- `plane_normal` — for `"circle"`: measurement plane normal (default `[0,0,1]`)
- `axis_guess` — for `"cylinder"`: initial axis direction (estimated from PCA if omitted)

**Output:** shape-dependent; `form_error` = peak-to-valley deviation (= form tolerance zone); e.g. plane gives `normal`, `d`, `flatness`; circle gives `centre`, `radius`, `roundness`

---

### `cmm_align_datum`

Datum-reference-frame (DRF) alignment transform.

**Input:**
- `method` (required) — `"3-2-1"` or `"best-fit"`
- For `"3-2-1"`: `primary_pts` (≥3), `secondary_pts` (≥2), `tertiary_pts` (≥1)
- For `"best-fit"`: `nominal_pts` and `measured_pts` (equal length, ≥3 each)

**Output:** 4×4 homogeneous rigid transform (row-major), DRF axes, translation

---

### `cmm_eval_gdt`

Evaluate a GD&T characteristic from measured point clouds.

**Input:**
- `characteristic` (required) — `"flatness"`, `"circularity"`, `"cylindricity"`, `"perpendicularity"`, `"parallelism"`, or `"angularity"`
- `points` (required) — measured `[x, y, z]` points
- `tolerance` — drawing callout value (optional; enables pass/fail)
- `datum_normal` — required for perpendicularity, parallelism, angularity
- `plane_normal` — for circularity measurement plane
- `axis_guess` — for cylindricity initial axis
- `nominal_angle_deg` — required for angularity

**Output:** `form_error` (tolerance zone width), `within_tolerance` flag, warnings if out of tolerance

---

### `cmm_eval_position`

True-position GD&T per ASME Y14.5-2018 §8 with optional MMC bonus tolerance.

**Input:**
- `measured_center` (required), `true_position` (required) — `[x, y, z]` coordinates
- `tolerance` (required) — diametral tolerance zone
- `mmc_size` + `actual_size` — optional; bonus = |actual_size − mmc_size|

**Output:** `positional_deviation`, `effective_tolerance`, `within_tolerance`

---

### `cmm_eval_profile`

Surface profile GD&T evaluation (profile of a surface, ISO 1101 §17).

**Input:**
- `measured_pts` (required) — measured surface points
- `nominal_pts` (required) — nominal CAD surface points
- `tolerance` — bilateral zone (optional)

**Output:** `profile_value` = 2 × max(|deviation|), signed deviations, `within_tolerance`

---

### `cmm_gum_uncertainty`

Combine measurement uncertainty components per GUM (JCGM 100:2008).

**Input:**
- `type_a` — list of Type-A standard uncertainties (statistical)
- `type_b` — list of Type-B standard uncertainties (calibration, specs); pre-divide half-widths by √3 (rectangular) or √6 (triangular) before passing
- `coverage_factor` — k (default 2.0 ≈ 95% normal)

**Output:** `uc` (combined standard uncertainty), `U` (expanded uncertainty = k × uc)

---

### `cmm_probe_compensate`

Compensate raw CMM hit points for stylus-tip (probe) radius.

**Input:**
- `measured_pts` (required) — raw CMM hit points `[x, y, z]`
- `surface_normals` (required) — outward normals at each hit point `[nx, ny, nz]`
- `probe_radius` (required) — stylus tip radius (mm, ≥ 0)

**Output:** `compensated_pts` — actual surface points (offset by −probe_radius along normal)

---

### `cmm_recommend_samples`

Nyquist-based CMM sampling point count recommendation.

**Input:**
- `expected_harmonics` (required) — highest harmonic in form error (e.g. 3 for tri-lobing)
- `safety_factor` — multiplier above Nyquist (default 2.5 per ISO/TS 12781-2)

**Output:** `n_nyquist`, `n_recommended`

---

### `cmm_gauge_rr`

Gauge Repeatability & Reproducibility study per AIAG MSA 4th edition.

**Input:**
- `method` (required) — `"anova"` or `"avg-range"`
- `data` (required) — 3-D array `[part][operator][replicate]`
- `usl`, `lsl` — optional; enables %tolerance output

**Output:** `EV` (repeatability), `AV` (reproducibility), `GRR`, `PV` (part variation), `TV`, `pct_study_var`, `ndc` (number of distinct categories); warns if pct_study_var > 10% or ndc < 5

---

### `cmm_process_capability`

Process capability Cpk and Ppk from CMM measurement samples.

**Input:**
- `measurements` (required) — list of measured values (≥ 2)
- `usl`, `lsl` (both required)

**Output:** `Cpk`, `Ppk`, `mean`, `sigma_within`, `sigma_overall`; warns for Cpk < 1.33

---

## Example

```
1. cmm_fit_geometry
     shape:"plane"
     points:[[0,0,0.01],[1,0,-0.01],[0,1,0.005],[1,1,-0.005]]
   → normal:[0,0,1]  flatness:0.020  (20 µm form error)

2. cmm_eval_position
     measured_center:[10.05,20.03,0]
     true_position:[10.0,20.0,0]
     tolerance:0.1
   → positional_deviation:0.117  within_tolerance:false

3. cmm_process_capability
     measurements:[10.01,9.99,10.02,10.00,9.98,10.01]
     usl:10.1  lsl:9.9
   → Cpk:1.18  Ppk:1.15  (marginal — warns Cpk < 1.33)
```
