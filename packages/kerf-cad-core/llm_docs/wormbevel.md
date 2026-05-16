# Worm Gear and Bevel Gear Design

Pure-Python worm-gear and bevel-gear design tools per Shigley/AGMA standards.
No OCC dependency. All tools are stateless. Units: mm for lengths, N·mm for
torques, MPa for stresses (SI default for bevel).

---

## When to use

Use these tools when the conversation involves: worm gear, worm drive, worm-and-
wheel, bevel gear, straight bevel, spiral bevel, conical gear, right-angle drive,
self-locking gear, back-drive, worm lead angle, worm efficiency, worm geometry,
worm forces, AGMA 6022 worm rating, thermal rating, bevel pitch angle, cone
distance, virtual teeth, bevel force analysis, bevel stress, bevel AGMA stress,
contact stress, bending stress, geometry factor, overload factor, dynamic factor,
worm starts, gear ratio, centre distance, module, normal pressure angle, Lewis
equation, Shigley gear design.

---

## Tools

### `worm_geometry`

Worm-gear pair geometry: lead, lead angle, pitch diameters, centre distance,
gear ratio, maximum face width.

**Input:** `m_n` (normal module, mm), `N_w` (worm starts), `N_g` (gear teeth)
(all required); optional `C` (centre distance, mm — enables AGMA 6022 preferred
sizing), `phi_n_deg` (normal pressure angle, default 20°).

**Returns:** `m_n_mm`, `N_w`, `N_g`, `m_G` (gear ratio), `phi_n_deg`,
`lead_mm`, `lead_angle_deg`, `d_w_mm`, `d_g_mm`, `C_mm`, `face_width_max_mm`,
`axial_pitch_mm`, warnings.

---

### `worm_efficiency`

Worm-gear efficiency (worm driving gear) and back-drive efficiency; checks
self-locking criterion.

η_forward = tan(λ) × (cos φ_n − μ tan λ) / (cos φ_n tan λ + μ)

**Input:** `lambda_deg` (worm lead angle, required); optional `phi_n_deg`
(default 20°), `mu` (friction coefficient, default 0.05).

**Returns:** `eta_forward`, `eta_back`, `self_locking` (bool), warnings.

---

### `worm_forces`

Force analysis on a worm-gear pair (worm driving gear).

**Input:** `T_w` (worm input torque, N·mm), `d_w` (worm pitch diameter, mm),
`lambda_deg` (required); optional `phi_n_deg`, `mu` (default 0.05).

**Returns:** `W_t_w_N` (tangential on worm = axial on gear), `W_a_w_N`
(axial on worm = tangential on gear), `W_r_N` (separating), `W_n_N` (normal).

---

### `worm_agma_rating`

AGMA 6022 rated tangential load and approximate thermal power limit.

W_t_rated = C_s × d_g^0.8 × b × C_m × C_v

**Input:** `C_s`, `C_m`, `C_v`, `d_g` (mm), `b` (face width, mm), `d_w` (mm),
`n_w` (rpm) (all required); optional `material_pair`
(`sand_cast_bronze_cast_iron`|`centrifugal_cast_bronze_steel` default|
`chilled_cast_bronze_steel`).

**Returns:** `W_t_rated_N`, `rated_power_kW`, `thermal_power_kW`,
`thermal_ok`, warnings (over-temperature).

---

### `bevel_geometry`

Straight-bevel gear pair geometry at 90° shaft angle.

**Input:** `N_p` (pinion teeth ≥ 12), `N_g` (gear teeth > N_p), `m` (outer
module, mm) (all required); optional `b_fraction` (face width fraction of A_0,
AGMA limit 0.333, default 0.3).

**Returns:** `Gamma_p_deg` (pinion pitch angle), `Gamma_g_deg`,
`A_0_mm` (cone distance), `b_mm` (face width), `m_m_mm` (mean module),
`d_m_p_mm` (mean pitch diameter, pinion), `N_e_p`, `N_e_g` (virtual spur teeth).

---

### `bevel_forces`

Force analysis on a straight-bevel pinion at the mean pitch circle.

W_r = W_t × tan(φ_n) × cos(Γ_p) [radial on pinion = axial on gear]
W_a = W_t × tan(φ_n) × sin(Γ_p) [axial on pinion = radial on gear]

**Input:** `T_p` (pinion torque, N·mm), `d_m_p` (mean pitch diameter, mm),
`Gamma_p_deg` (pinion pitch angle) (all required); optional `phi_n_deg` (default 20°).

**Returns:** `W_t_N`, `W_r_N`, `W_a_N`, `W_total_N`.

---

### `bevel_agma_stress`

AGMA bending and contact stress for straight-bevel (or spiral-bevel) gears.

Bending: σ_t = Wt·Ko·Kv·Ks·Km / (b·m_m·J) [MPa]
Contact: σ_c = Cp × √(Wt·Ko·Kv·Ks·Km / (d_m_p·b·I)) [MPa]

**Input:** `Wt`, `Ko`, `Kv`, `Ks`, `Km`, `b`, `m_m`, `J`, `I`, `Cp`, `d_m_p`
(all required); optional `metric` (default True; False = English units).

**Returns:** `sigma_t_MPa` (bending stress), `sigma_c_MPa` (contact stress),
warnings (overstress).

---

## Example

```
1. worm_geometry  m_n:3  N_w:2  N_g:40  C:120
   → d_w: 48mm, d_g: 192mm, lead_angle_deg: 7.1°, m_G: 20

2. worm_efficiency  lambda_deg:7.1  mu:0.06
   → eta_forward: 0.724, self_locking: false

3. bevel_geometry  N_p:16  N_g:48  m:3
   → Gamma_p_deg: 18.4°, A_0: 75.9mm, b: 22.8mm, m_m: 2.55mm

4. bevel_forces  T_p:50000  d_m_p:40  Gamma_p_deg:18.4
   → W_t: 2500N, W_r: 864N, W_a: 287N
```
