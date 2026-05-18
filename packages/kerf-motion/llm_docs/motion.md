# kerf-motion · Multibody Dynamics & Kinematics

Pure-Python multibody rigid-body dynamics, kinematic chain solvers, and motion
simulation.  No numpy/scipy dependency — runs anywhere Python 3.11+ is
available.  All public routines return `{"ok": False, "reason": "..."}` on bad
input and never raise.

---

## When to use

- Simulate a robot arm, mechanism, or free-flying rigid body over time
- Compute joint angles for a robot to reach a target (IK)
- Calculate the reachable workspace of a serial manipulator
- Verify mechanism behaviour against analytic reference values (pendulum, SMD, free-fall)

---

## Module overview

| Module | What it does |
|---|---|
| `body.py` | `RigidBody` data class; quaternion/matrix math |
| `joints.py` | `RevoluteJoint`, `PrismaticJoint`, `CylindricalJoint`, `UniversalJoint`, `SphericalJoint`, `FixedJoint` |
| `forces.py` | Gravity, spring-damper, applied force/torque, torsional spring |
| `integrator.py` | `rk4_step`, `simulate` (RK4, per-body trajectories) |
| `forward_kinematics.py` | `forward_kinematics`, `end_effector_pose`, `geometric_jacobian` |
| `inverse_kinematics.py` | `analytic_ik_2link`, `jacobian_transpose_ik`, `compute_workspace_2d` |
| `tools.py` | LLM tool surface: `simulate_motion`, `solve_ik`, `compute_workspace` |

---

## `RigidBody`

```python
from kerf_motion.body import RigidBody

I = ((Ixx, 0, 0), (0, Iyy, 0), (0, 0, Izz))   # 3×3 inertia tensor (body frame)
body = RigidBody(
    mass=1.0,
    inertia_tensor=I,
    position=(0.0, 0.0, 0.0),        # world frame
    orientation=(1.0, 0.0, 0.0, 0.0),  # unit quaternion (w,x,y,z)
    velocity=(0.0, 0.0, 0.0),         # world frame
    angular_velocity=(0.0, 0.0, 0.0), # body frame
    name="my_body",
)
```

State vector layout (13 floats): `[px, py, pz, vx, vy, vz, qw, qx, qy, qz, wx, wy, wz]`

---

## Joints

All joints accept `parent_idx`, `child_idx`, `parent_offset` (Vec3 — joint anchor in parent frame), `child_offset`, and `name`.

| Joint | n_dof | Key params |
|---|---|---|
| `FixedJoint` | 0 | — |
| `RevoluteJoint` | 1 | `axis`, `angle`, `limits=(lo,hi)` |
| `PrismaticJoint` | 1 | `axis`, `position`, `limits=(lo,hi)` |
| `CylindricalJoint` | 2 | `axis`, `angle`, `position` |
| `UniversalJoint` | 2 | `axis1`, `axis2`, `angle1`, `angle2` |
| `SphericalJoint` | 3 | `orientation` (quat) or `set_euler_xyz(rx,ry,rz)` |

```python
from kerf_motion.joints import RevoluteJoint

j = RevoluteJoint(0, 1, axis=(0,0,1), angle=1.57, limits=(-3.14, 3.14))
j.set_dof([new_angle])
j.get_dof()          # → [angle]
j.transform()        # → JointTransform(translation, rotation)
```

---

## Force fields

```python
from kerf_motion.forces import gravity, applied_force, spring_damper

grav  = gravity(g=9.80665, axis=1, sign=-1)      # −y direction
const = applied_force(body_idx=0, force=(0,0,100))
sd    = spring_damper(
    body_a_idx=0, body_b_idx=-1,   # -1 = world anchor
    k=1000.0, c=50.0,
    natural_length=1.5,
    attachment_b=(0, 0, 0),        # world anchor point
)
```

Each force field is a callable `f(bodies, t) → [(force_vec3, torque_vec3), ...]`.

---

## `simulate`

```python
from kerf_motion.integrator import simulate

result = simulate(
    bodies=[body1, body2],
    joints=[],              # unused in free-flight
    forces=[grav, sd],
    dt=1e-3,                # seconds
    n_steps=10000,
    record_every=10,        # store every 10th step
)

result["ok"]              # bool
result["t"]               # list of recorded times
result["trajectories"]    # trajectories[body_idx][step] = BodySnapshot
result["final_bodies"]    # list of RigidBody at final time

snap = result["trajectories"][0][100]
snap.t, snap.position, snap.velocity
```

### Integration details

- 4th-order Runge-Kutta (RK4)
- Quaternion re-normalised after each step (prevents drift)
- Global error O(dt⁴); halving dt reduces error by ~16×

---

## Forward kinematics

```python
from kerf_motion.joints import RevoluteJoint
from kerf_motion.forward_kinematics import forward_kinematics, end_effector_pose

j0 = RevoluteJoint(0, 1, axis=(0,0,1), angle=0.5, parent_offset=(0,0,0))
j1 = RevoluteJoint(1, 2, axis=(0,0,1), angle=-0.3, parent_offset=(1.0,0,0))

poses = forward_kinematics([j0, j1])   # list of Pose per link
ee    = end_effector_pose([j0, j1])    # Pose of end-effector

ee.position        # (x, y, z)
ee.orientation     # (qw, qx, qy, qz)
ee.rotation_matrix # 3×3 body→world
```

---

## Inverse kinematics

### Analytic 2-link planar arm

```python
from kerf_motion.inverse_kinematics import analytic_ik_2link

result = analytic_ik_2link(l1=1.0, l2=0.8, target_x=1.2, target_y=0.7,
                            elbow_up=True)
# result["ok"], result["theta1"], result["theta2"]
```

Closed-form (Craig §4.4):
```
cos θ2 = (r² − l1² − l2²) / (2 l1 l2)
θ1     = atan2(y, x) − atan2(l2 sin θ2, l1 + l2 cos θ2)
```

### Numerical IK (Jacobian transpose)

```python
from kerf_motion.inverse_kinematics import jacobian_transpose_ik

result = jacobian_transpose_ik(
    joints=[j0, j1, j2],
    target=(1.5, 0.8, 0.0),
    tol=1e-6,
    max_iterations=1000,
    alpha=0.1,
)
# result["ok"], result["theta"], result["error_norm"], result["iterations"]
```

Convergence: Δθ = α Jᵀ e, with optional α decay.

### Workspace

```python
from kerf_motion.inverse_kinematics import compute_workspace_2d

result = compute_workspace_2d([j0, j1], n_samples=500)
# result["points"] — list of (x,y,z) tuples
```

---

## Analytic oracle reference values (tests)

| Test | Oracle | Tolerance |
|---|---|---|
| Free-fall position | y(t) = −½ g t² | 1e-9 rel. |
| Pendulum period | T = 2π√(L/g) | 1% |
| SMD damped period | Td = 2π/ωd | 1% |
| SMD decay envelope | A(t) = A₀ e^{−ζω₀t} | 1% |
| 2-link analytic IK | FK roundtrip | 1e-10 m |
| Numerical IK vs analytic | ee position | 1e-5 m |
| Euler spin-up | ω(t) = τ/I · t | 1e-6 rel. |
| RK4 order | error ratio ≈ 16 on dt/2 | ratio ∈ [12,20] |

---

## LLM tools

### `simulate_motion`

Run a multibody simulation.  Specify bodies (mass, inertia, position), force fields (gravity/applied/spring_damper), dt, and n_steps.  Returns trajectories.

### `solve_ik`

Compute joint angles for a target end-effector position.
- `method="analytic_2link"` — closed-form for 2-link planar arm
- `method="jacobian_transpose"` — iterative n-DOF

### `compute_workspace`

Return a cloud of reachable end-effector positions by sweeping all revolute joints.
