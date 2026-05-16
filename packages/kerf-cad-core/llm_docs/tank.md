# API 650 Atmospheric Storage Tank Design

Pure-Python API 650 / API 2000 storage-tank engineering: shell thickness, roof design, wind and seismic stability, venting, settlement, nozzle reinforcement, and anchorage. All tools are stateless and never raise. Units: SI (metres, Pascals, Newtons).

---

## When to use

Use these tools for atmospheric storage tanks: API 650, oil/water/chemical storage, shell course thickness, cone or dome roof design, wind girder sizing, overturning stability, anchor bolt sizing, seismic (Annex E) sloshing and base shear, API 2000 normal/emergency venting, settlement tolerance check, nozzle reinforcement area replacement.

---

## Tools

### `tank_shell_course_thickness`

Required shell-plate thickness for one course (API 650 §5.6). 1-foot method (design point 0.3 m above course bottom) or variable-design-point method.

**Input:** `D` (m, required), `H` (design liquid height above course bottom, m, required), `G` (specific gravity, default 1.0), `Sd`/`St` (allowable stresses Pa), `c` (corrosion allowance m), `method` (`"1-foot"` default or `"variable"`), `x` (design-point height, required for `variable`).

**Returns:** `t_product_m`, `t_hydrotest_m`, `t_required_m`, `warnings`.

---

### `tank_minimum_shell_thickness`

API 650 Table 5-6a minimum shell thickness by tank diameter. **Input:** `D` (m). **Returns:** `t_min_m` (5 mm for D≤15 m, 6 mm ≤30 m, 8 mm ≤60 m, 10 mm >60 m).

---

### `tank_bottom_plate_thickness`

API 650 §5.4.1 minimum bottom plate thickness (≥6 mm net + corrosion allowance). **Input:** `c` (optional), `has_liner` (bool, optional). **Returns:** `t_bottom_m`, `warnings`.

---

### `tank_annular_plate_thickness`

Minimum annular bottom plate thickness per API 650 §5.5, governed by hydrostatic pressure at first-course base. **Input:** `D`, `H` (required), `G`, `Fy_shell_Pa`, `c` (optional). **Returns:** `t_annular_m`, `projection_min_m` (600 mm).

---

### `tank_cone_roof_thickness`

Cone-roof plate thickness per API 650 §5.10.5.1. Supported or self-supporting cone; cone half-angle 9.46°–37°. Also returns `frangible_joint` flag. **Input:** `D` (required), `theta_deg`, `design_load_Pa`, `Sd`, `E_joint`, `c`, `self_supporting` (optional). **Returns:** `t_required_m`, `frangible_joint`, `warnings`.

---

### `tank_dome_roof_thickness`

Self-supporting dome roof per API 650 §5.10.5.2; membrane formula t = w·Rc/(2·Sd·E). Crown radius 0.8D–1.5D (default 0.8D). **Input:** `D` (required), `Rc`, `design_load_Pa`, `Sd`, `E_joint`, `c` (optional). **Returns:** `t_required_m`.

---

### `tank_wind_girder_section_modulus`

Required section modulus of top wind girder per API 650 §5.9.7.1, and maximum unstiffened shell height W_max. **Input:** `D`, `t_shell` (required), `V_wind_m_s` (default 45 m/s), `H_shell` (optional). **Returns:** `Z_required_m3`, `W_max_m`, `warnings`.

---

### `tank_intermediate_stiffener`

Maximum intermediate wind stiffener spacing per API 650 §5.9.7.3. **Input:** `D`, `t_shell`, `H_shell` (required), `V_wind_m_s` (optional). **Returns:** `W_max_m`, `n_stiffeners_min`, `stiffener_spacing_m`.

---

### `tank_overturning_stability`

Wind overturning stability check per API 650 §5.11. SF = M_resist / M_wind; must be ≥ 1.5. **Input:** `D`, `H_shell`, `W_total_N` (required), `V_wind_m_s`, `rho_air`, `Cf`, `H_liquid_m`, `rho_liquid` (optional). **Returns:** `M_wind_Nm`, `M_resist_Nm`, `SF`, `warnings`.

---

### `tank_anchorage_requirement`

Anchor bolt area sizing per API 650 §5.11.2. Supported grades: A307, A193-B7, A36. **Input:** `D`, `M_overturning_Nm`, `W_shell_N` (required), `n_bolts`, `bolt_grade`, `safety_factor` (optional). **Returns:** `F_per_bolt_N`, `A_bolt_required_m2`, `net_uplift_N`.

---

### `tank_seismic_annex_e`

API 650 Annex E seismic: Housner model impulsive/convective masses, base shear (SRSS), overturning moment, sloshing wave height, and freeboard check. **Input:** `D`, `H_liquid` (required), `rho_liquid`, `Sds`, `Sd1`, `I` (optional). **Returns:** impulsive/convective masses and periods, base shear, overturning moment, `delta_s_m`, `freeboard_required_m`, `warnings`.

---

### `tank_venting_normal`

Normal vent capacity per API 2000 §4 (thermal breathing + fill/drain). **Input:** `V_tank_m3` (required), `flash_point_C`, `fill_rate_m3_s`, `draw_rate_m3_s` (optional). **Returns:** `in_breathing_m3h`, `out_breathing_m3h`, `warnings`.

---

### `tank_venting_emergency`

Emergency vent capacity (fire case) per API 2000 §5.3.2: Q = 3.091 × A_w^0.82. **Input:** `V_tank_m3` (required); provide `wetted_area_m2` or `D` + `H_liquid` to compute it. **Returns:** `Q_emergency_m3h`.

---

### `tank_settlement_check`

API 650 Appendix B settlement tolerance check: edge, planar tilt, and differential settlement. **Input:** `D` (required), `S_edge_mm`, `S_planar_mm`, `S_diff_max_mm`, `measurement_arc_deg` (optional). **Returns:** `edge_ok`, `planar_ok`, `differential_ok`, `warnings`.

---

### `tank_nozzle_reinforcement`

API 650 §5.7.3 nozzle reinforcement area-replacement check. **Input:** `D_shell`, `t_shell`, `d_nozzle`, `t_nozzle`, `H` (required), `G`, `Sd`, `c` (optional). **Returns:** `A_required_m2`, `A_available_m2`, `reinforcement_ok`, `shortfall_m2`.

---

## Example

```
1. tank_shell_course_thickness  D:20  H:12  G:0.9  c:0.003
   → t_required_m: 0.0128  (12.8 mm)

2. tank_minimum_shell_thickness  D:20
   → t_min_m: 0.006  (6 mm; D in 15–30 m band)

3. tank_wind_girder_section_modulus  D:20  t_shell:0.012  V_wind_m_s:40
   → Z_required_m3: 1.42e-4  W_max_m: 6.5

4. tank_overturning_stability  D:20  H_shell:14  W_total_N:2e6  V_wind_m_s:40
   → SF: 2.3  warnings: []
```
