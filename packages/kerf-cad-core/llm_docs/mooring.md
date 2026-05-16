# Offshore Mooring & Station-Keeping

Pure-Python offshore mooring and station-keeping analysis tools. No OCC dependency. All tools are
stateless. References: API RP 2SK (3rd ed.), DNV-OS-E301, Morison et al. (1950), OCIMF MEG3.

---

## When to use

Mooring, catenary, mooring line, station-keeping, spread mooring, turret mooring, chain, wire rope,
FPSO, semi-submersible, offshore platform, watch circle, offset, restoring force, mooring stiffness,
anchor, drag embedment, pile anchor, suction caisson, holding capacity, Morison equation, wave force,
current force, wind force, hull drag, OCIMF, API RP 2SK, safety factor, MBL, breaking load,
riser tension, riser top tension, DNV-OS-F201, API RP 16Q.

---

## Tools

### `mooring_catenary_line`

Single-segment elastic catenary mooring line analysis.

**Input:** `w` (N/m submerged weight, required), `L` (m unstretched length, required),
`H` (N horizontal tension at fairlead, required), `EA` (axial stiffness N, optional),
`water_depth` (m, optional), `n_profile_pts` (default 50)

**Returns:** `H_N`, `V_fairlead_N`, `T_fairlead_N`, `V_anchor_N`, `T_anchor_N`,
`angle_fairlead_deg`, `angle_anchor_deg`, `catenary_param_m`, `horizontal_span_m`,
`vertical_span_m`, `arc_length_m`, `touchdown_m`, `scope`, `profile_x`, `profile_z`

---

### `mooring_multiseg_catenary`

Multi-segment catenary mooring line (e.g. chain + wire + chain). Segments share
horizontal tension H and accumulate vertical loads from anchor to fairlead.

**Input:** `segments` (list of `{w, L, label}`, required), `H` (N, required)

**Returns:** `T_fairlead_N`, `V_fairlead_N`, total spans, per-segment catenary results

---

### `mooring_system_stiffness`

Spread-mooring system restoring force vs vessel offset and linearised stiffness.

**Input:** `lines` (list of `{w, L, H0, azimuth_deg}`, required),
`water_depth` (m, required), `fairlead_radius` (m, required),
`offsets` (list of m values, required)

**Returns:** per-offset `restoring_force_N`, `stiffness_N_m`, `max_line_tension_N`

---

### `mooring_anchor_holding`

Simplified holding capacity for three anchor types.

- `'drag_embedment'`: H = holding_factor × anchor_weight_kN (factors: soft_clay 30, sand 10)
- `'pile'`: H = 9 × Su × D × L (API RP 2SK)
- `'suction_caisson'`: H = Su × D × L × 10 (DNV-OS-E301)

**Input:** `anchor_type` (required), plus type-specific: `anchor_weight_kN`, `soil_type`,
`pile_diameter_m`, `pile_length_m`, `Su_kPa`, `caisson_diameter_m`, `caisson_length_m`, `Su_avg_kPa`

**Returns:** `holding_kN`, `method_note`, warnings

---

### `mooring_morison_force`

Morison equation: wave + current drag and inertia force on a vertical circular cylinder.
F/L = ½ρCd·D·|u_r|u_r + ρCm(πD²/4)·du_w/dt.

**Input:** `D` (m, required), `L` (m, required), `rho` (required), `Cd` (required),
`Cm` (required), `U_c` (current m/s, required), `U_w` (wave amplitude m/s, required),
`omega` (rad/s, required), `k` (wave number rad/m, required), `z` (depth m, default 0)

**Returns:** `F_drag_max_N`, `F_inertia_max_N`, `F_total_max_N`, `KC`, `Re`

---

### `mooring_mean_env_load`

Mean wind and current drag force on vessel hull (OCIMF-style simplified).
F = ½ρCdAV² for each.

**Input:** `hull_area_wind` (m², required), `Cd_wind` (required), `rho_air` (required),
`V_wind` (m/s, required), `hull_area_current` (m², required), `Cd_current` (required),
`rho_water` (required), `V_current` (m/s, required)

**Returns:** `F_wind_N`, `F_current_N`, `F_total_N`

---

### `mooring_watch_circle`

Watch circle and maximum permissible offset check per API RP 2SK §3.3.
Default limit: max offset ≤ 5% of water depth.

**Input:** `system_result` (output from `mooring_system_stiffness`, required),
`max_offset_fraction` (default 0.05), `water_depth` (m)

**Returns:** `max_offset_m`, `watch_circle_radius_m`, `offset_exceeded`, `critical_offset_m`

---

### `mooring_line_sf`

Line tension safety factor and API RP 2SK compliance.
Intact: SF ≥ 1.67 (60% MBL). Damaged (one line lost): SF ≥ 1.25.

**Input:** `T_applied_kN` (required), `T_break_kN` (MBL, required),
`sf_required` (default 1.67)

**Returns:** `SF_actual`, `pass_sf`, `utilisation_pct`, warnings

---

### `mooring_riser_top_tension`

Riser top tension: T_top = T_bottom + w_r × L_r × cos(θ).

**Input:** `w_r` (N/m submerged unit weight, required), `L_r` (m, required),
`T_bottom` (N, required), `theta_deg` (default 0)

**Returns:** `T_top_N`, `H_top_N`, `weight_component_N`, warning if θ > 15°

---

## Example

```
1. mooring_catenary_line  w:3500  L:800  H:1.5e6  water_depth:200
   → T_fairlead_N: 1.62e6  angle_fairlead_deg: 22.4  touchdown_m: 180

2. mooring_line_sf  T_applied_kN:850  T_break_kN:2000
   → SF_actual: 2.35  pass_sf: true  utilisation_pct: 42.5

3. mooring_morison_force
     D:1.2  L:20  rho:1025  Cd:0.8  Cm:2.0
     U_c:0.5  U_w:2.0  omega:0.628  k:0.040
   → F_total_max_N: 184000  KC: 10.5

4. mooring_anchor_holding  anchor_type:"drag_embedment"
     anchor_weight_kN:150  soil_type:"soft_clay"
   → holding_kN: 4500
```
