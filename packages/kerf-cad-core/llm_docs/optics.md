# Geometric Optics & Lens Design — LLM Reference

Geometric optics: lensmaker's equation, Gaussian imaging, ABCD ray-transfer matrices,
diffraction limits, Snell's law, aberration and achromat design (Hecht; Smith). No OCC
dependency. All tools are stateless; no DB write. Units: metres, degrees, dioptres.

---

## When to use

Keywords: optics, lens, focal length, lensmaker, thin lens, thick lens, imaging, magnification,
depth of field, DOF, hyperfocal, F-number, numerical aperture, NA, diffraction, Airy disk,
Snell's law, refraction, total internal reflection, TIR, critical angle, Brewster angle,
prism, chromatic aberration, Abbe number, achromat, doublet, ABCD matrix, ray transfer,
telescope, microscope, camera, beam optics.

---

## Workflow

```
optics_lensmaker           → focal length from radii and index
optics_thin_lens_imaging   → image position and magnification
optics_two_lens_system     → combined system EFL
optics_abcd_system         → ray-matrix cascade for multi-element systems
optics_fnumber / optics_numerical_aperture → aperture metrics
optics_depth_of_field      → DOF + hyperfocal
optics_airy_spot           → diffraction-limited spot radius
optics_snell               → refraction at interface; TIR detection
optics_chromatic_aberration → longitudinal chromatic aberration
optics_achromat_powers     → doublet element powers for zero chromatic aberration
```

---

## Tools

### `optics_lensmaker`

Focal length from the lensmaker's equation (thin or thick lens).

**Input:** `R1` (first radius of curvature, m), `R2` (second radius, m), `n` (refractive index ≥ 1), `d` (centre thickness, m, default 0 = thin lens). Use R = 1e18 for a flat surface.

**Returns:** `f_m` (focal length), `power_dioptre`, `lens_type` (`"converging"` / `"diverging"`).

---

### `optics_thin_lens_imaging`

Gaussian thin-lens imaging: 1/f = 1/s_o + 1/s_i.

**Input:** `f_m` (focal length), `s_o_m` (object distance, m; positive = real object).

**Returns:** `s_i_m` (image distance), `magnification`, `image_type` (`"real"` / `"virtual"`).

---

### `optics_mirror_imaging`

Spherical mirror imaging (convex or concave).

**Input:** `R_m` (radius of curvature; negative = concave), `s_o_m`.

**Returns:** `f_m`, `s_i_m`, `magnification`, `image_type`.

---

### `optics_two_lens_system`

Effective focal length and back focal distance for two thin lenses separated by distance d.

**Input:** `f1_m`, `f2_m`, `d_m` (separation).

**Returns:** `EFL_m`, `BFD_m` (back focal distance), `FFL_m` (front focal distance), `power_dioptre`.

---

### `optics_abcd_system`

Cascade of ABCD ray-transfer matrices for a multi-element optical system.

**Input:** `elements` — ordered list of `{type, ...}` dicts:
- `{type:"free_space", d_m}` — propagation
- `{type:"refraction", n1, n2, R_m}` — spherical surface refraction
- `{type:"thin_lens", f_m}` — thin lens

**Returns:** `M` (2×2 ABCD matrix, flat list of 4), `EFL_m`, `stable` flag (|A+D| ≤ 2).

---

### `optics_fnumber`

F-number (focal ratio).

**Input:** `f_m`, `D_m` (entrance pupil diameter).

**Returns:** `N_fnumber` = f / D.

---

### `optics_numerical_aperture`

Numerical aperture.

**Input:** `n` (medium refractive index), `theta_half_angle_deg` (half-angle of acceptance cone).

**Returns:** `NA` = n · sin(θ).

---

### `optics_depth_of_field`

Depth of field (DOF) and hyperfocal distance for a camera system.

**Input:** `f` (focal length, m), `N` (F-number), `c` (circle of confusion diameter, m), `s_o` (subject distance, m).

**Returns:** `DOF_total_m`, `DOF_near_m`, `DOF_far_m`, `hyperfocal_m`. Far DOF is `∞` when s_o ≥ hyperfocal.

---

### `optics_airy_spot`

Diffraction-limited Airy disk radius (first dark ring).

**Input:** `lambda_m` (wavelength, m), `N_fnumber` or `NA`.

**Returns:** `r_airy_m` = 1.22 · λ / (2·NA) = 1.22 · λ · N.

---

### `optics_snell`

Snell's law refraction at an interface; detects total internal reflection.

**Input:** `n1` (incident medium), `n2` (refracted medium), `theta_i_deg` (angle of incidence from normal, degrees).

**Returns:** `theta_t_deg` (refraction angle), `TIR` (bool — total internal reflection), `critical_angle_deg` (if n1 > n2).

---

### `optics_critical_angle`

Critical angle for total internal reflection at an n1 → n2 interface (n1 > n2 required).

**Input:** `n1`, `n2`.

**Returns:** `critical_angle_deg` = arcsin(n2/n1).

---

### `optics_brewster_angle`

Brewster's angle (p-polarisation transmitted without reflection).

**Input:** `n1`, `n2`.

**Returns:** `brewster_deg` = arctan(n2/n1).

---

### `optics_prism_deviation`

Deviation angle of a prism at minimum deviation (equilateral or general).

**Input:** `n` (refractive index), `apex_deg` (prism apex angle, degrees).

**Returns:** `deviation_min_deg` (minimum deviation angle), `theta_i_deg` (incidence angle at minimum deviation).

---

### `optics_chromatic_aberration`

Longitudinal chromatic aberration of a thin lens from Abbe number.

**Input:** `f_m` (focal length), `V` (Abbe number / V-number of glass).

**Returns:** `LCA_m` = f / V (longitudinal chromatic aberration).

---

### `optics_achromat_powers`

Optical powers of the two elements of an achromatic doublet.

**Input:** `phi_total` (total optical power, 1/m = dioptres), `V1` (Abbe number of crown element), `V2` (Abbe number of flint element).

**Returns:** `phi1` (crown power, dioptres), `phi2` (flint power, dioptres); phi1 + phi2 = phi_total.

---

## Example

```
# Design a simple imaging lens
optics_lensmaker  R1:0.1  R2:-0.15  n:1.5
  → f_m: 0.12  power_dioptre: 8.33  lens_type: "converging"

optics_thin_lens_imaging  f_m:0.12  s_o_m:0.5
  → s_i_m: 0.171  magnification: -0.343  image_type: "real"

optics_depth_of_field  f:0.05  N:2.8  c:0.000025  s_o:3.0
  → DOF_total_m: 2.21  DOF_near_m: 2.21  hyperfocal_m: 35.7

# Check for TIR in a glass fibre (n_glass=1.5, n_air=1.0)
optics_critical_angle  n1:1.5  n2:1.0
  → critical_angle_deg: 41.8

# Achromat doublet (BK7 + F2) for f=100 mm
optics_achromat_powers  phi_total:10  V1:64.2  V2:36.4
  → phi1: 22.9 dioptre  phi2: -12.9 dioptre
```
