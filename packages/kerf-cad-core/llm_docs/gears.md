# Involute Gear Generator

Pure-Python ISO 21771 involute gear math. No OCC dependency. All tools are
stateless — they compute and return geometry; no DB write. Units: mm, degrees.

---

## Tools

### `gear_spur`

Generate a 2D involute spur (external) gear profile.

**Input:**
- `module` (required) — module m (mm), e.g. 1, 1.5, 2, 2.5, 3, 4, 5
- `teeth` (required) — tooth count z (≥ 3)
- `pressure_angle_deg` — pressure angle α, in (10°, 30°), default 20°
- `profile_shift` — shift coefficient x (default 0; use ≥ 0.5 for z < 17)
- `face_width` — axial length b (mm), stored for reference
- `profile_points` — involute sample points per flank (4–256, default 32)

**Output:** ISO 21771 gear data + `tooth_polyline` (closed 2D polygon, one tooth, +X axis).

Key fields: `pitch_diameter`, `base_diameter`, `tip_diameter`, `root_diameter`,
`circular_pitch`, `tooth_thickness`, `whole_depth`, `undercut_risk`, `recipe`.

**Validation:** m ≤ 0, z < 3, α ∉ (10°, 30°) → `{ok: false, errors: [...]}`

---

### `gear_helical`

Extends `gear_spur` with a helix angle β.

**Input:** same as `gear_spur` + `helix_angle_deg` (required, in (0°, 90°))

**Additional output:**
- `transverse_module` = m_n / cos(β)
- `transverse_pressure_angle_deg` via tan(α_t) = tan(α_n) / cos(β)
- `axial_pitch` = π · m_n / sin(β)
- `face_contact_ratio` (if `face_width` given) = b · sin(β) / (π · m_n)

The tooth polyline is in the transverse plane.

---

### `gear_internal`

Internal (ring/annular) gear: teeth point inward.

**Input:** `module`, `teeth`, `pressure_angle_deg`, `profile_shift`, `profile_points`

**Sign conventions (ISO 21771 §4.3):**
- `tip_diameter`  = d − 2·m·(1−x)   (inner, smaller than pitch circle)
- `root_diameter` = d + 2·m·(1.25+x)  (outer, larger than pitch circle)

Mesh with a spur pinion: use `gear_pair_check` to verify fit.

---

### `gear_rack`

Linear rack (infinite-radius gear).

**Input:** `module`, `pressure_angle_deg`, `n_teeth` (2–50, default 6)

**Output:**
- `linear_pitch` = π · m
- `addendum` = m, `dedendum` = 1.25·m, `whole_depth` = 2.25·m
- `tooth_polyline` — one tooth centred at x=0 on the pitch line
- `rack_polyline` — n_teeth teeth centred around origin

---

### `gear_pair_check`

Mesh-check two external spur gears.

**Input:** `module`, `teeth_1`, `teeth_2`, `pressure_angle_deg`,
`profile_shift_1`, `profile_shift_2`

**Output:**
- `gear_ratio` = z2 / z1
- `centre_distance` — operating centre distance a_w (mm)
- `standard_centre_distance` — m·(z1+z2)/2 (for x1=x2=0)
- `operating_pressure_angle_deg` — α_w solved from inv(α_w) = inv(α) + 2·(x1+x2)·tan(α)/(z1+z2)
- `contact_ratio` εα — should be > 1.2 for smooth transmission
- `warnings` — list of undercut / interference / low-contact warnings

---

## Formulas (ISO 21771:2007)

| Quantity | Formula |
|----------|---------|
| Pitch diameter | d = m · z |
| Base diameter | d_b = d · cos α |
| Tip diameter | d_a = d + 2·m·(1+x) |
| Root diameter | d_f = d − 2·m·(1.25−x) |
| Circular pitch | p = π · m |
| Tooth thickness (pitch circle) | s = π·m/2 + 2·x·m·tan α |
| Involute function | inv(φ) = tan φ − φ |
| Contact ratio | εα = (√(r_a1²−r_b1²) + √(r_a2²−r_b2²) − a_w·sin α_w) / (π·m·cos α) |

Undercut occurs when r_f < r_b (root circle inside base circle).
For α=20°, standard dedendum: minimum z without undercut ≈ 42.

---

## Typical workflow

```
1. gear_spur   module:2  teeth:20  pressure_angle_deg:20
   → pitch_diameter:40, base_diameter:37.59, tip_diameter:44, root_diameter:35
   → tooth_polyline: [[...], ...]   (closed, 2D, one tooth)
   → undercut_risk: true  (z=20 < 42, consider profile shift)

2. gear_spur   module:2  teeth:40  pressure_angle_deg:20
   → pitch_diameter:80 ...

3. gear_pair_check  module:2  teeth_1:20  teeth_2:40
   → gear_ratio:2.0  centre_distance:60.0  contact_ratio:1.63
   → warnings: ["Gear 1: undercut risk ..."]
```

---

## Notes

- All tools are **pure-Python**, no OCC.
- Profile polyline is in the **transverse plane**, centred on the **+X axis**.
- Do NOT call OCCT here — pass the `recipe` dict + `tooth_polyline` to the
  frontend/worker for 3D extrusion.
- For helical gears, extrude the transverse polyline with a helix transform
  (helix angle β, axial pitch p_x).
