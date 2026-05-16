# ISO 286 Limits and Fits

Pure-Python ISO 286 tolerance and fit calculations. No OCC dependency. Covers IT tolerance
grades, shaft/hole deviations, fit classification, preferred fits, and Lamé press-fit
analysis. All tools stateless. References: ISO 286-1:2010; ISO 286-2:2010; Shigley's MED
10th ed.

---

## When to use

Use these tools when the user asks about:
- ISO 286, limits and fits, tolerance, tolerancing
- IT grade, IT6, IT7, IT8, IT tolerance value
- shaft tolerance, shaft designation h6 g6 k6 p6 s7 f7
- hole tolerance, hole designation H7 H8 F8 G7 K7 N7 P7
- clearance fit, transition fit, interference fit, locational fit, running fit
- fit analysis, max clearance, min clearance, max interference
- preferred fits, hole-basis, shaft-basis
- press fit, shrink fit, interference fit, Lamé equations, hub stress, assembly force
- fundamental deviation, upper deviation es, lower deviation ei, ES, EI

---

## Tools

### `iso286_it_tolerance`

ISO 286-1 standard tolerance grade (IT) value for a nominal size and grade.

`i = 0.45·D^(1/3) + 0.001·D`  (µm); IT value = grade factor × i.

**Input:**
- `nominal_mm` (required) — nominal size (mm), must be in (0, 3150]
- `grade` (required) — IT grade string: `IT01`, `IT0`, `IT1` … `IT18`
  (common: IT6 precision, IT7 general, IT8 medium, IT11 free machining)

**Returns:** `IT_um` (µm), `IT_mm`, `size_band_mm`, `tolerance_unit_um`.

---

### `iso286_shaft_limits`

Upper (es) and lower (ei) shaft deviations per ISO 286-1.

Shaft letter codes: a, b, c, d, e, f, g, h (clearance), js (symmetric),
j, k, m, n (transition), p, r, s, t, u, v, x, y, z, za, zb, zc (interference).

**Input:**
- `nominal_mm` (required) — nominal shaft diameter (mm), (0, 3150]
- `designation` (required) — e.g. `h6`, `g6`, `k6`, `p6`, `s7`, `f7`

**Returns:** `es_um`, `ei_um`, `upper_limit_mm`, `lower_limit_mm`.

---

### `iso286_hole_limits`

Upper (ES) and lower (EI) hole deviations per ISO 286-1.

Hole letter codes: A, B, C, D, E, F, G, H (clearance), JS, J, K, M, N (transition),
P, R, S, T, U, V, X, Y, Z, ZA, ZB, ZC (interference). H is the reference hole (EI = 0).

**Input:**
- `nominal_mm` (required) — nominal hole diameter (mm), (0, 3150]
- `designation` (required) — e.g. `H7`, `H8`, `F8`, `G7`, `K7`, `N7`, `P7`

**Returns:** `EI_um`, `ES_um`, `upper_limit_mm`, `lower_limit_mm`.

---

### `iso286_fit_analysis`

Fit classification and clearance/interference limits for a hole + shaft combination.

`Clearance = hole_size − shaft_size` (positive = play, negative = interference).

Fit types: `clearance` (min_clearance ≥ 0), `transition`, `interference` (max_clearance ≤ 0).

**Input:**
- `nominal_mm` (required), `hole_designation` (required, e.g. `H7`),
  `shaft_designation` (required, e.g. `g6`)

**Returns:** `fit_type`, `max_clearance_mm`, `min_clearance_mm`,
`max_interference_mm`, `min_interference_mm`, all four limit dimensions.

---

### `iso286_preferred_fits`

ISO 286-2 preferred fits for hole-basis or shaft-basis system.

Common hole-basis preferred fits:
- H11/c11 Loose running, H9/d9 Free running, H8/f7 Close running
- H7/g6 Sliding, H7/h6 Locational clearance, H7/k6 Locational transition
- H7/p6 Locational interference, H7/s6 Medium drive, H7/u6 Force fit

**Input:** all optional:
- `nominal_mm` — if provided, clearance/interference values are computed for each fit
- `system` — `hole-basis` (default) or `shaft-basis`
- `fit_types` — array filter: `clearance`, `transition`, `interference`

**Returns:** list of fit descriptors with clearance/interference ranges if `nominal_mm` given.

---

### `iso286_press_fit`

Lamé thick-cylinder interference / press-fit analysis.

```
contact_pressure_MPa
hub_hoop_stress_inner_Pa  (max tensile)
hub_hoop_stress_outer_Pa
shaft_hoop_stress_inner_Pa (compressive)
assembly_force_N          (if length_mm provided)
shrink_fit_delta_T_C      (minimum ΔT to heat hub for assembly)
```

**Input:**
- `nominal_mm` (required) — interface diameter (mm)
- `interference_mm` (required) — total diametral interference δ (mm)
- `hub_outer_mm` (required) — outer diameter of hub (mm), must be > nominal_mm
- `shaft_bore_mm` (default 0 = solid shaft)
- `E_hub_Pa`, `E_shaft_Pa` (default 200e9 steel)
- `nu_hub`, `nu_shaft` (default 0.3)
- `mu_friction` (default 0.12 for assembly force)
- `length_mm` — axial interface length (required for assembly_force_N)
- `yield_strength_hub_Pa`, `yield_strength_shaft_Pa` — overstress check if provided
- `alpha_hub`, `alpha_shaft` (default 12e-6 steel, for shrink_fit_delta_T_C)

**Returns:** contact pressure, hoop stresses, assembly force, ΔT, overstress flags.

---

## Example

```
1. iso286_it_tolerance  nominal_mm:50  grade:"IT7"
   → IT_um:25  IT_mm:0.025

2. iso286_hole_limits  nominal_mm:50  designation:"H7"
   → EI_um:0  ES_um:25  upper_limit_mm:50.025  lower_limit_mm:50.0

3. iso286_shaft_limits  nominal_mm:50  designation:"g6"
   → es_um:-9  ei_um:-25  upper_limit_mm:49.991  lower_limit_mm:49.975

4. iso286_fit_analysis  nominal_mm:50  hole_designation:"H7"  shaft_designation:"g6"
   → fit_type:"clearance"  max_clearance_mm:0.050  min_clearance_mm:0.009

5. iso286_press_fit  nominal_mm:80  interference_mm:0.05  hub_outer_mm:120  length_mm:60
   → contact_pressure_MPa:48.3  assembly_force_N:22000  shrink_fit_delta_T_C:55
```
