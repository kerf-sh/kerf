# Lifting & Rigging Engineering

Pure-Python ASME B30 lifting and rigging engineering tools. Covers sling tension,
multi-leg load sharing, pick-point CG loads, hardware capacity look-ups, spreader
beam checks, padeye checks, two-crane lifts, and crane chart interpolation. No OCC
dependency. All tools are stateless and never raise.

---

## When to use

Use when the user asks about: rigging, lifting, sling tension, load-angle factor,
wire rope, alloy chain, synthetic sling, WLL, working load limit, spreader beam,
lifting lug, padeye, two-crane lift, tandem lift, crane chart, crane capacity,
tip-over, centre of gravity, pick points, rigging hardware derating, ASME B30.

---

## Tools

### `rigging_sling_tension`

Compute sling tension from the load-angle factor 1/sin θ.

**Input:**
- `load_kg` (required) — total suspended load (kg)
- `angle_deg` (required) — sling angle from horizontal (degrees); values < 30° trigger a warning
- `n_legs` — number of equal-share sling legs (default 1, max 8)
- `design_factor` — design factor for required WLL (default 5.0)

**Output:** `tension_per_leg_kN`, `tension_per_leg_kg`, `load_angle_factor`, `required_wll_kg`

---

### `rigging_multi_leg_share`

Per-leg load share for 2-, 3-, or 4-leg lifts with unequal sling lengths.

**Input:**
- `load_kg` (required) — total load (kg)
- `sling_lengths` (required) — list of sling lengths in metres (2, 3, or 4 entries)
- `mode` — `"flexible"` (default) or `"rigid"`
- `design_factor` — default 5.0

**Output:** `leg_loads_kg`, `required_wll_kg`; warns if 4-leg flexible (longest leg treated non-load-bearing per ASME B30.9)

---

### `rigging_cg_pick_loads`

Per-pick-point vertical loads from CG geometry using moment equilibrium / barycentric.

**Input:**
- `load_kg` (required), `cg_x` (required), `cg_y` (required) — CG in metres
- `pick_points` (required) — list of 2, 3, or 4 `[x, y]` pick-point coordinates (m)

**Output:** `pick_loads_kg`, `pick_loads_kN`, `pick_shares`, `cg_inside`; warns UNSTABLE if CG outside polygon

---

### `rigging_sling_wll_derate`

Angular WLL derating for slings, shackles, or eyebolts per ASME B30.9 / B30.26.

**Input:**
- `rated_wll_kg` (required) — rated WLL at reference angle (kg)
- `angle_deg` (required) — loading angle (degrees)
- `hardware_type` — `"sling"` (default), `"eyebolt"`, or `"shackle"`
- `n_legs` — multiplies derated WLL (default 1)

**Output:** `derated_wll_kg`, `total_wll_kg`

---

### `rigging_wire_rope_capacity`

Wire rope minimum break force and WLL by diameter and grade.

**Input:**
- `diameter_mm` (required) — nominal diameter (8–40 mm depending on grade)
- `grade` — `"6x19_iwrc_1570"` (default), `"6x19_iwrc_1770"`, `"6x37_iwrc_1570"`, `"6x36_ws_1770"`
- `design_factor` — default 5.0

**Output:** `mbf_kN`, `wll_kN`, `wll_kg`

---

### `rigging_chain_capacity`

Alloy steel chain WLL by chain size and grade.

**Input:**
- `size_mm` (required) — link diameter (6, 7, 8, 10, 13, 16, 19, 22, 26, 32 mm)
- `grade` — `"grade_80"` (default) or `"grade_100"`
- `design_factor` — default 4.0

**Output:** `wll_t`, `wll_kg`, `wll_kN`, `effective_wll_kg`

---

### `rigging_synthetic_sling_capacity`

Flat-web synthetic sling WLL by width, ply, material, and hitch type.

**Input:**
- `width_mm` (required) — 25, 50, 75, 100, 150, or 200 mm
- `ply` (required) — 1 or 2
- `material` — `"polyester"` (default) or `"nylon"`
- `hitch` — `"vertical"` (×1.0), `"choker"` (×0.80), `"basket"` (×2.0), `"basket_45deg"`, `"basket_60deg"` (default `"vertical"`)
- `design_factor` — default 7.0

**Output:** `base_wll_kg`, `adjusted_wll_kg`, `effective_wll_kg`

---

### `rigging_spreader_beam_check`

Check a spreader or lifting beam for bending and axial compression.

**Input:**
- `load_kg` (required), `span_m` (required)
- `section` — section string e.g. `"tube_square_200x200x10"`, `"tube_round_219x10"`, `"wide_flange_300x150x8x12"`
- `Fy_MPa` — yield strength (default 350 MPa)
- `design_factor` — default 3.0

**Output:** `bending_stress_MPa`, `axial_stress_MPa`, `combined`, `utilisation`, `pass_bending`

---

### `rigging_padeye_check`

Simplified padeye / lifting lug strength check (net-section tension, bearing, double shear-out).

**Input:**
- `load_kN` (required), `plate_thickness_mm` (required), `hole_diameter_mm` (required), `pin_diameter_mm` (required)
- `Fy_MPa` (default 350), `Fu_MPa` (default 480), `design_factor` (default 3.0)

**Output:** stresses, allowables, pass/fail flags, and utilisations for all three failure modes

---

### `rigging_tip_over_two_crane`

Load share and tip-over check for a two-crane tandem lift.

**Input:**
- `total_load_kg`, `crane_a_capacity_t`, `crane_b_capacity_t`, `lift_point_a_x`, `lift_point_b_x`, `cg_x` (all required, positions in metres)

**Output:** `crane_a_load_kg`, `crane_b_load_kg`, `utilisations`, `cg_between_hooks`; warns if either crane is overloaded or CG is outside lift points

---

### `rigging_crane_radius_interpolate`

Interpolate crane capacity from a radius–capacity chart table.

**Input:**
- `radius_m` (required) — operating radius (m)
- `chart_table` (required) — list of `[radius_m, capacity_t]` pairs (at least 2, ascending radius order)

**Output:** `capacity_t`, `capacity_kg`; warns when extrapolating

---

## Example

```
1. rigging_wire_rope_capacity  diameter_mm:20  grade:"6x19_iwrc_1770"
   → wll_kN:32.4, wll_kg:3305

2. rigging_sling_tension  load_kg:5000  angle_deg:45  n_legs:2
   → load_angle_factor:1.414, tension_per_leg_kN:34.6, required_wll_kg:3535

3. rigging_cg_pick_loads
     load_kg:5000  cg_x:1.2  cg_y:0.8
     pick_points:[[0,0],[2.4,0],[2.4,1.6],[0,1.6]]
   → pick_loads_kg:[1250,1250,1250,1250]  cg_inside:true
```
