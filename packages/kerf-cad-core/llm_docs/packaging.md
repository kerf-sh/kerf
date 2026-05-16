# Protective Packaging & Shipping Design

Pure-Python tools for corrugated-box compression, pallet pattern optimisation,
shipping weight / freight classification, foam cushion design, shock
transmissibility, ISO container fill optimisation, and stretch-wrap compliance.
No OCC dependency. All tools are stateless and never raise.

---

## When to use

Use when the user asks about: packaging, box compression, McKee BCT, corrugated
carton, pallet pattern, pallet loading, interlock, column stack, shipping weight,
DIM weight, volumetric weight, dimensional weight, NMFC freight class, foam cushion,
drop height, fragility G, shock transmissibility, resonance, container stuffing,
ISO container 20GP 40GP 40HC 45HC, stretch wrap, EUMOS 40509, containment force.

---

## Tools

### `pkg_box_compression_strength`

Corrugated-box BCT using the McKee formula, with humidity/time derating and optional
stack-overload check.

**Input:**
- `ECT` (required) — edge-crush test value (N/m)
- `C_f` (required) — McKee constant (typical SI: 5.874)
- `Z` (required) — box perimeter (mm)
- `safety_factor` — default 1.0 (TAPPI recommends ≥ 1.5)
- `humidity_factor` — 0–1 derate (default 1.0 = dry)
- `time_factor` — 0–1 creep derate (default 1.0 = short-term)
- `stack_load_N` — optional; checks allowable ≥ stack_load_N
- `flute` — `"A"`, `"B"`, `"C"` (default), `"E"`, `"F"`, `"BC"`, `"EB"`

**Output:** `BCT_N`, `BCT_derated_N`, `allowable_N`, `board_thickness_mm`, `stack_overload`

---

### `pkg_pallet_pattern`

Optimise pallet loading: column vs interlock (brick) patterns.

**Input:**
- `case_L`, `case_W`, `case_H`, `pallet_L`, `pallet_W`, `max_height` (all required, mm)
- `pattern` — `"column"`, `"interlock"`, or `"auto"` (default)
- `case_weight_kg` — optional; enables `pallet_weight_kg` output
- `max_pallet_kg` — optional; caps layers

**Output:** `pattern_used`, `cases_per_layer`, `layers`, `cases_per_pallet`, `area_utilisation`, `cube_utilisation`, `pallet_weight_kg`

---

### `pkg_shipping_weight`

DIM weight, chargeable weight, and NMFC freight class.

**Input:**
- `length_mm`, `width_mm`, `height_mm`, `actual_kg` (all required)
- `carrier` — `"domestic"` (DIM factor 5000, default) or `"international"` (6000)
- `freight_class_override` — optional NMFC class override

**Output:** `volume_cm3`, `dim_weight_kg`, `chargeable_weight_kg`, `dim_factor`, `density_lb_ft3`, `freight_class`

---

### `pkg_cushion_design`

Design protective-foam cushion from drop height, product fragility, and foam
cushion-curve data per ASTM D1596 / ISTA.

**Input:**
- `product_weight_kg`, `drop_height_m`, `fragility_G`, `foam_static_stress_kPa`, `foam_cushion_curve_G` (all required)
- `bearing_area_cm2` — default 100 cm²
- `safety_factor` — default 1.5

**Output:** `delta_V_m_s`, `static_stress_kPa`, `required_thickness_mm`, `G_allow`, `under_cushioned`, `fragile_exceeded`

---

### `pkg_shock_transmissibility`

Single-DOF shock & vibration transmissibility through a packaging cushion.

**Input:**
- `fn_Hz` (required) — natural frequency of packaged product on cushion
- `damping_ratio` (required) — ζ (0 < ζ < 1; typical foam 0.05–0.20)
- `input_freq_Hz` (required) — excitation frequency

**Output:** `frequency_ratio`, `transmissibility`, `attenuation_dB`, `isolation_pct`, `resonance_warning`

---

### `pkg_container_fill`

Optimise case-count in an ISO shipping container by trying all 6 box orientations.

**Input:**
- `case_L`, `case_W`, `case_H` (all required, mm)
- `container_type` — `"20GP"`, `"40GP"` (default), `"40HC"`, `"45HC"`
- `orientation_permutations` — try all 6 orientations (default true)

**Output:** `container_type`, internal dimensions, `orientation_used`, `cases_per_row`, `cases_per_col`, `layers`, `total_cases`, `volume_utilisation`

---

### `pkg_stretch_wrap`

Stretch-wrap containment force and EUMOS 40509 class-1 compliance check.

**Input:**
- `pallet_weight_kg` (required) — gross pallet weight (kg)
- `film_gauge_um` (required) — film gauge (μm; typical 17–30 μm)
- `revolutions` — default 3
- `overlap_fraction` — default 0.50
- `pre_stretch_pct` — default 200%

**Output:** `F_per_revolution_N`, `F_total_N`, `F_min_required_N`, `eumos_compliant`, `revolutions_for_minimum`

---

## Example

```
1. pkg_box_compression_strength
     ECT:5000  C_f:5.874  Z:1200
     safety_factor:1.5  humidity_factor:0.70  time_factor:0.50
     stack_load_N:800
   → BCT_N:4390, BCT_derated_N:1537, allowable_N:1025
   → stack_overload:true

2. pkg_pallet_pattern
     case_L:400  case_W:300  case_H:200
     pallet_L:1200  pallet_W:1000  max_height:2200
   → pattern_used:"interlock"  cases_per_pallet:44
     area_utilisation:0.88  cube_utilisation:0.73

3. pkg_container_fill
     case_L:400  case_W:300  case_H:200  container_type:"40GP"
   → total_cases:540  volume_utilisation:0.71
```
