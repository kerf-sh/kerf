# Open-Channel Hydraulics

Pure-Python open-channel hydraulics tools for cross-section properties, normal and
critical depth, Froude number, specific energy, momentum function, hydraulic jump,
gradually-varied-flow (GVF) profile classification and direct-step computation,
best hydraulic section design, weirs (broad, sharp, V-notch), Parshall flume,
culvert control, and channel transitions. Units SI (metres, m³/s). No OCC
dependency. All tools never raise.

---

## When to use

Use when the user asks about: open channel, channel flow, Manning equation, Manning's
n, Chezy equation, normal depth, critical depth, subcritical, supercritical, Froude
number, specific energy, hydraulic jump, sequent depth, GVF profile, water surface
profile, M1 M2 M3 profile, S1 S2 S3 profile, backwater curve, gradually varied flow,
best hydraulic section, most efficient section, weir, broad-crested weir,
sharp-crested weir, V-notch weir, triangular weir, Parshall flume, culvert capacity,
inlet control, outlet control, channel transition, contraction expansion.

---

## Tools

### `channel_section_properties`

Geometry and hydraulic properties of a cross-section at a given depth.

**Input:** `shape` (required), `y` (required, m); shape parameters as needed: `b` (rectangular/trapezoidal), `z` (trapezoidal/triangular), `D` (circular), `T_top` (parabolic)

**Shapes:** `"rectangular"`, `"trapezoidal"`, `"triangular"`, `"circular"`, `"parabolic"`

**Output:** area A, wetted perimeter P, top width T, hydraulic radius R, hydraulic depth D_h, section factor Z

---

### `channel_normal_depth`

Solve for normal depth by bisection (Manning or Chezy equation).

**Input:** `shape`, `flow_m3s`, `slope` (all required); `manning_n` or `chezy_C` (provide one); `max_depth_m` (default 20); shape parameters

**Output:** `normal_depth_m`, velocity, flow area, wetted perimeter, hydraulic radius, top width, `froude_number`, `flow_regime`, `channel_full`

---

### `channel_critical_depth`

Critical depth (Fr = 1, minimum specific energy) by bisection on section factor.

**Input:** `shape`, `flow_m3s` (required); `max_depth_m` (default 20); shape parameters

**Output:** `critical_depth_m`, `critical_velocity_m_per_s`, `critical_area_m2`, `froude_number`, `min_specific_energy_m`

---

### `channel_froude_number`

Froude number and flow regime at a known depth.

**Input:** `shape`, `flow_m3s`, `depth_m` (all required); shape parameters

**Output:** `froude_number`, `flow_regime` (`"subcritical"`, `"critical"`, `"supercritical"`)

---

### `channel_specific_energy`

Specific energy E = y + V²/(2g) at a given flow depth.

**Input:** `shape`, `flow_m3s`, `depth_m` (all required); shape parameters

**Output:** `specific_energy_m`, `velocity_head_m`, `velocity_m_per_s`

---

### `channel_momentum_function`

Specific force (momentum) function M = Q²/(gA) + ȳ·A.

**Input:** `shape`, `flow_m3s`, `depth_m` (all required); shape parameters

**Output:** `momentum_function_m3`, conserved across hydraulic jumps (neglecting wall friction)

---

### `channel_hydraulic_jump`

Sequent (conjugate) depth, energy loss, and estimated jump length.

**Input:** `shape`, `flow_m3s`, `depth1_m` (upstream supercritical depth, all required); shape parameters

**Output:** `depth1_m`, `depth2_m`, `froude1`, `froude2`, `energy_loss_m`, `relative_energy_loss`, `length_estimate_m`; warns if upstream depth is subcritical

---

### `channel_gvf_profile_type`

Classify the GVF water-surface profile type per Chow (1959).

**Input:** `shape`, `flow_m3s`, `slope`, `manning_n`, `depth_m` (all required); shape parameters

**Output:** `profile_type` (M1/M2/M3/S1/S2/S3/C1/C3/H2/H3/A2/A3), `channel_class` (Mild/Steep/Critical/Horizontal/Adverse), `normal_depth_m`, `critical_depth_m`

---

### `channel_gvf_direct_step`

Water-surface profile by direct-step method: Δx = (E₂ − E₁) / (S₀ − S̄_f).

**Input:** `shape`, `flow_m3s`, `slope`, `manning_n`, `depth_start_m`, `depth_end_m` (all required); `n_steps` (default 100); shape parameters

**Output:** `profile` list of `{x_m, depth_m, specific_energy_m, velocity_m_per_s, froude_number, friction_slope}`, `total_length_m`

---

### `channel_best_hydraulic_section`

Dimensions of the most-hydraulically-efficient (best) cross-section.

**Input:** `shape`, `flow_m3s`, `slope`, `manning_n` (all required)

**Output:** `optimal_depth_m` plus shape-specific optimal dimensions (e.g. `b` for rectangular = 2y), `wetted_perimeter_m`, `hydraulic_radius_m`, `flow_area_m2`

---

### `channel_weir_broad_crested`

Broad-crested weir discharge: Q = Cd × L × H^(3/2).

**Input:** `head_m`, `crest_length_m` (both required); `Cd` (default 1.7 SI form)

**Output:** `discharge_m3s`

---

### `channel_weir_sharp_crested`

Sharp-crested rectangular weir discharge (Francis formula): Q = (2/3) × Cd × L × √(2g) × H^(3/2).

**Input:** `head_m`, `crest_length_m` (both required); `Cd` (default 0.611), `end_contractions` (0 or 2, default 2)

**Output:** `discharge_m3s`

---

### `channel_weir_vnotch`

V-notch (triangular) weir discharge: Q = (8/15) × Cd × tan(θ/2) × √(2g) × H^(5/2).

**Input:** `head_m` (required); `notch_angle_deg` (default 90°), `Cd` (default 0.611)

**Output:** `discharge_m3s`

---

### `channel_culvert_control`

Culvert capacity and controlling condition (inlet vs outlet control) per FHWA HDS-5.

**Input:** `diameter_m`, `length_m`, `slope`, `manning_n`, `headwater_m` (all required); `tailwater_m` (default 0), `Ke` (default 0.5 square-edge)

**Output:** `controlling_condition`, `capacity_m3s`, `inlet_control_Q_m3s`, `outlet_control_Q_m3s`

---

### `channel_transition`

Depth at a channel contraction or expansion (energy equation with head-loss coefficient).

**Input:** `shape1`, `shape2`, `flow_m3s`, `depth1_m` (all required); upstream shape params (`b`, `z`, `D`, `T_top`); downstream params suffixed `_2`; `contraction_loss_coeff` (default 0.1), `expansion_loss_coeff` (default 0.3)

**Output:** `depth2_m`, velocities, energies, `head_loss_m`, `transition_type`; warns if downstream Fr ≥ 0.95 (choked)

---

## Example

```
1. channel_normal_depth
     shape:"rectangular"  b:2.0
     flow_m3s:5.0  slope:0.001  manning_n:0.013
   → normal_depth_m:0.94  froude_number:0.71  flow_regime:"subcritical"

2. channel_hydraulic_jump
     shape:"rectangular"  b:2.0  flow_m3s:5.0  depth1_m:0.30
   → depth2_m:1.08  energy_loss_m:0.39  length_estimate_m:4.7

3. channel_best_hydraulic_section
     shape:"trapezoidal"  flow_m3s:10  slope:0.0005  manning_n:0.025
   → optimal_depth_m:1.52  z:0.577  b:1.755
```
