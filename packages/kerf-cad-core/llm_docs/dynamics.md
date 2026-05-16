# Rigid-Body Dynamics

Pure-Python engineering dynamics library covering kinematics, Newton-Euler equations, energy/work/impulse methods, mass moments of inertia, flywheel sizing, rotor balancing, and shaking forces. No OCC dependency. All tools are stateless and never raise.

---

## When to use

Use these tools for engineering mechanics / dynamics problems: rectilinear and rotational kinematics, projectile motion, relative motion, Newton's second law, kinetic energy, work-energy theorem, spring potential energy, power from torque or force, linear and angular impulse-momentum, central and oblique impact, mass moment of inertia (cylinder, sphere, rod, plate), parallel-axis theorem, flywheel sizing and rim design, single-plane and two-plane rotor balancing, ISO 1940 balance grade checks, reciprocating shaking forces, gyroscopic moment.

---

## Tools

### `dynamics_rectilinear_kinematics`
Constant-acceleration rectilinear motion: s = s0 + v0·t + ½·a·t², v = v0 + a·t.
**Input:** `v0` (m/s), `a` (m/s²), `t` (s ≥ 0), `s0` (optional, default 0). **Returns:** `s_m`, `v_ms`, `v_squared`.

### `dynamics_projectile_motion`
Projectile motion (no air resistance). **Input:** `v0` (m/s > 0), `theta_deg` (launch angle), `t` (s ≥ 0), `g` (optional, default 9.80665). **Returns:** `x_m`, `y_m`, `vx_ms`, `vy_ms`, `speed_ms`, `time_to_peak_s`, `range_m`.

### `dynamics_rotational_kinematics`
Constant angular-acceleration kinematics: θ = θ0 + ω0·t + ½·α·t². **Input:** `omega0` (rad/s), `alpha` (rad/s²), `t` (s), `theta0` (optional). **Returns:** `theta_rad`, `omega_rad_s`, `omega_squared`.

### `dynamics_relative_motion_velocity`
Absolute velocity of B: v_B = v_A + v_B/A. **Input:** `v_A` (2D or 3D list, m/s), `v_B_A` (same dim). **Returns:** `v_B` vector and `magnitude_ms`.

### `dynamics_newton_translation`
Newton's second law: a = ΣF / m. **Input:** `F_net` (N), `m` (kg > 0). **Returns:** `a_ms2`.

### `dynamics_euler_rotation`
Euler's rotation equation: α = ΣM / I. **Input:** `M_net` (N·m), `I` (kg·m² > 0). **Returns:** `alpha_rad_s2`.

### `dynamics_general_plane_motion`
General plane motion: ΣFx = m·ax, ΣFy = m·ay, ΣM_G = I_G·α. **Input:** `F_x`, `F_y` (N), `M_G` (N·m), `m` (kg), `I_G` (kg·m²). **Returns:** `ax_ms2`, `ay_ms2`, `alpha_rad_s2`.

### `dynamics_kinetic_energy`
T = ½·m·v² + ½·I·ω². **Input:** `m` (kg), `v` (m/s), `I` (optional), `omega` (optional). **Returns:** `T_trans_J`, `T_rot_J`, `T_total_J`.

### `dynamics_work_energy_theorem`
Work-energy balance: T2 − (T1 + W_nc) = 0. **Input:** `KE1`, `KE2`, `W_nc` (J). **Returns:** `residual_J`, `satisfied` (bool).

### `dynamics_spring_pe`
Spring potential energy: V_s = ½·k·x². **Input:** `k` (N/m), `x` (m). **Returns:** `V_s_J`.

### `dynamics_power_torque`
P = M·ω (W). **Input:** `M` (N·m), `omega` (rad/s). **Returns:** `P_W`.

### `dynamics_power_force`
P = F·v (W). **Input:** `F` (N), `v` (m/s). **Returns:** `P_W`.

### `dynamics_linear_impulse`
mv2 = mv1 + F·Δt. **Input:** `F` (N), `dt` (s > 0), `mv1` (optional). **Returns:** `impulse_Ns`, `mv2_kgms`.

### `dynamics_angular_impulse`
L2 = L1 + M·Δt. **Input:** `M` (N·m), `dt` (s > 0), `L1` (optional). **Returns:** `angular_impulse_Nms`, `L2_kgm2s`.

### `dynamics_direct_impact`
Central impact post-impact velocities. **Input:** `m1`, `v1`, `m2`, `v2` (kg/m/s), `e` (COR 0–1). **Returns:** `v1_prime_ms`, `v2_prime_ms`, `ke_loss_J`.

### `dynamics_oblique_impact`
2-D oblique impact with line of impact along x-axis. **Input:** `m1`, `v1x`, `v1y`, `m2`, `v2x`, `v2y` (kg/m/s), `e`. **Returns:** `v1x_prime`, `v1y_prime`, `v2x_prime`, `v2y_prime` (m/s), `ke_loss_J`.

### `dynamics_moi_solid_cylinder`
I = ½·m·r² about longitudinal axis. **Input:** `m` (kg), `r` (m). **Returns:** `I_kgm2`.

### `dynamics_moi_hollow_cylinder`
I = ½·m·(r_o² + r_i²). **Input:** `m`, `r_o`, `r_i` (kg/m). **Returns:** `I_kgm2`.

### `dynamics_moi_solid_sphere`
I = 2/5·m·r² about a diameter. **Input:** `m`, `r`. **Returns:** `I_kgm2`.

### `dynamics_moi_thin_rod`
I about centroid (1/12·m·L²) or end (1/3·m·L²). **Input:** `m`, `L` (kg/m), `axis` (`"centroid"` default or `"end"`). **Returns:** `I_kgm2`.

### `dynamics_moi_rectangular_plate`
I_z = 1/12·m·(a²+b²); I_x = 1/12·m·b²; I_y = 1/12·m·a². **Input:** `m`, `a`, `b` (kg/m). **Returns:** `I_z_kgm2`, `I_x_kgm2`, `I_y_kgm2`.

### `dynamics_parallel_axis`
I = I_cm + m·d² (Steiner theorem). **Input:** `I_cm` (kg·m²), `m` (kg), `d` (m). **Returns:** `I_kgm2`.

### `dynamics_flywheel_sizing`
Required flywheel MOI: I = ΔE / (ω_mean² · Cs). **Input:** `E_fluctuation` (J), `omega_mean` (rad/s), `Cs` (speed fluctuation coefficient). **Returns:** `I_kgm2`.

### `dynamics_flywheel_rim`
Rim cross-section for a rim-type flywheel. **Input:** `I_required` (kg·m²), `rho` (kg/m³), `r_mean` (m), `b` (axial width, m). **Returns:** `area_m2`, `thickness_m`, `mass_kg`.

### `dynamics_static_balance`
Single-plane resultant unbalance and correction mass·radius. **Input:** `masses` (kg list), `radii` (m list), `angles_deg` (list). **Returns:** `resultant_mr_kgm`, `resultant_angle_deg`, `correction_mr_kgm`, `correction_angle_deg`.

### `dynamics_dynamic_balance_two_plane`
Two-plane dynamic balancing: correction mass·radius in planes A and B. **Input:** `masses`, `radii`, `angles_deg`, `axial_positions` (m), `plane_a_pos`, `plane_b_pos` (m). **Returns:** correction MR and angles for planes A and B.

### `dynamics_residual_unbalance`
U = m·e (g·mm) per ISO 1940. **Input:** `m_correction` (g), `e` (mm). **Returns:** `U_g_mm`.

### `dynamics_iso1940_grade`
ISO 1940 balance grade check. **Input:** `U_g_mm`, `m_rotor_kg`, `omega_rad_s`, `grade` (optional, default `"G6.3"`). **Returns:** `within_grade`, `eper_mm`, `eper_permissible_mm`, `U_permissible_g_mm`.

### `dynamics_shaking_force_primary`
F_primary = m_recip · r · ω² · cos(θ). **Input:** `m_recip` (kg), `r` (m), `omega` (rad/s), `theta_deg`. **Returns:** `F_primary_N`.

### `dynamics_shaking_force_secondary`
F_secondary = m_recip · r · ω² · (1/n) · cos(2θ). **Input:** `m_recip`, `r`, `omega`, `n` (connecting-rod ratio L/r), `theta_deg`. **Returns:** `F_secondary_N`.

### `dynamics_gyroscopic_moment`
M_gyro = I_spin · ω_spin · ω_precession. **Input:** `I_spin` (kg·m²), `omega_spin` (rad/s), `omega_precession` (rad/s). **Returns:** `M_gyro_Nm`.

---

## Example

```
1. dynamics_moi_solid_cylinder  m:50  r:0.3
   → I_kgm2: 2.25

2. dynamics_flywheel_sizing  E_fluctuation:5000  omega_mean:31.4  Cs:0.02
   → I_kgm2: 253.7

3. dynamics_iso1940_grade  U_g_mm:800  m_rotor_kg:50  omega_rad_s:314  grade:"G6.3"
   → within_grade: false  eper_mm: 16.0  eper_permissible_mm: 6.3
```
