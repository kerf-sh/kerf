# Serial Robot Arm Kinematics — LLM Reference

Denavit-Hartenberg forward and inverse kinematics for serial robot arms. No OCC dependency.
All tools are stateless; no DB write. Units: metres, degrees (inputs/outputs), radians (internal).

---

## When to use

Keywords: robot, robot arm, kinematics, forward kinematics, inverse kinematics, IK, FK,
Denavit-Hartenberg, DH parameters, end effector, manipulator, Jacobian, manipulability,
workspace, joint angles, trajectory planning, trapezoidal velocity, 2R robot, 3R robot,
Yoshikawa, singularity, reach, robot path.

---

## Workflow

```
robot_fk                         → end-effector 4×4 transform
  → robot_end_effector_pose      → x, y, z, roll, pitch, yaw
robot_ik_2r_planar / robot_ik_3r_planar → joint angles for a target pose
robot_jacobian                   → 6×n Jacobian
  → robot_manipulability         → dexterity scalar w
robot_workspace                  → r_min, r_max reachable radius
robot_trajectory_trapezoidal     → time-sampled joint path
```

---

## Tools

### `robot_fk`

Denavit-Hartenberg forward kinematics for an n-link serial arm (Craig convention).

**Input:**
- `dh_params` — list of n rows `[a_i, alpha_i_deg, d_i, theta_offset_deg]`
- `joint_angles_deg` — list of n joint angles (degrees added to theta_offset)
- `joint_limits_deg` — optional `[[lo, hi], ...]` per joint; null to skip

**Returns:** 4×4 homogeneous end-effector transform matrix (list of 4 rows × 4 columns), warnings for out-of-limit joints.

---

### `robot_end_effector_pose`

Extract position and ZYX Euler orientation from a 4×4 homogeneous transform.

**Input:** `matrix` — 4×4 transform (as returned by `robot_fk`).

**Returns:** `x_m`, `y_m`, `z_m`, `roll_deg`, `pitch_deg`, `yaw_deg` (ZYX convention: R = Rz·Ry·Rx).

---

### `robot_ik_2r_planar`

Closed-form inverse kinematics for a planar 2R robot arm.

**Input:** `l1` (link 1 length, m), `l2` (link 2 length, m), `px` (target x, m), `py` (target y, m), `elbow_up` (bool, default true), `joint_limits_deg` (optional).

**Returns:** `q1_deg`, `q2_deg` (and radians), `reachable` flag; if unreachable, snaps to nearest boundary.

---

### `robot_ik_3r_planar`

Closed-form inverse kinematics for a planar 3R robot arm.

**Input:** `l1`, `l2`, `l3` (link lengths, m), `px`, `py` (target position, m), `phi_deg` (end-effector orientation angle, default 0), `joint_limits_deg` (optional).

**Returns:** `q1_deg`, `q2_deg`, `q3_deg` (and radians), `reachable` flag, warnings.

---

### `robot_jacobian`

Geometric Jacobian (6×n) for a serial arm — maps joint velocities to end-effector spatial velocity [v; ω].

**Input:** `dh_params`, `joint_angles_deg` (same format as `robot_fk`).

**Returns:** `J` (6×n matrix, list of 6 rows), `singular` flag, warnings.

---

### `robot_manipulability`

Yoshikawa manipulability measure: w = √det(J·Jᵀ).

**Input:** `J` — 6×n Jacobian matrix (as returned by `robot_jacobian`).

**Returns:** `manipulability` scalar; w = 0 indicates a singular configuration.

---

### `robot_workspace`

Estimate workspace radius bounds from DH parameters.

**Input:** `dh_params` — DH rows `[a_i, alpha_i_deg, d_i, theta_offset_deg]`.

**Returns:** `r_max_m` (sum of effective link lengths), `r_min_m` (inner void radius).

---

### `robot_trajectory_trapezoidal`

Generate a joint-space trapezoidal velocity profile trajectory between two configurations.

All joints are time-scaled to the same synchronised duration (driven by the slowest joint).

**Input:** `q_start_deg` (list), `q_end_deg` (list), `v_max_deg_s`, `a_max_deg_s2`, `dt_s` (time step, default 0.01 s).

**Returns:** `times_s`, `positions_deg` (time × joint), `velocities_deg_s` (time × joint), `T_sync_s` (total duration).

---

## Example

```
# 3-DOF planar arm: l1=0.5 m, l2=0.4 m, l3=0.3 m
# Forward kinematics at [30°, 45°, -20°]
robot_fk
  dh_params: [[0.5,0,0,0], [0.4,0,0,0], [0.3,0,0,0]]
  joint_angles_deg: [30, 45, -20]
  → matrix: [[...4x4...]]

robot_end_effector_pose  matrix: <above>
  → x_m: 0.92  y_m: 0.48  z_m: 0  yaw_deg: 55

# IK to reach (0.8, 0.3) with phi=0
robot_ik_3r_planar  l1:0.5 l2:0.4 l3:0.3  px:0.8 py:0.3
  → q1_deg: 8.2  q2_deg: 38.5  q3_deg: -22.1  reachable: true

# Plan trapezoidal move from home to target
robot_trajectory_trapezoidal
  q_start_deg:[0,0,0]  q_end_deg:[30,45,-20]
  v_max_deg_s:60  a_max_deg_s2:120
  → T_sync_s: 1.25  positions_deg: [...]
```
