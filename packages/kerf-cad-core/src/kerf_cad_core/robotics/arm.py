"""
kerf_cad_core.robotics.arm — Denavit-Hartenberg serial robot-arm kinematics.

Pure-Python implementation (math module only — no numpy).

Public functions
----------------
dh_matrix(a, alpha, d, theta)
    Build a single 4x4 DH homogeneous transform.

fk_chain(dh_params, joint_angles)
    Forward kinematics: product of DH matrices for an n-link chain.
    Returns the 4x4 end-effector transform T_0n.

end_effector_pose(T)
    Extract (x, y, z) position and ZYX Euler angles (roll, pitch, yaw) from T.

ik_2r_planar(l1, l2, px, py, elbow_up, joint_limits)
    Closed-form inverse kinematics for a planar 2R arm.

ik_3r_planar(l1, l2, l3, px, py, phi_deg, joint_limits)
    Closed-form IK for a planar 3R arm (end-effector orientation specified).

geometric_jacobian(dh_params, joint_angles)
    6×n geometric Jacobian (linear + angular velocity parts).

manipulability(J)
    Yoshikawa manipulability measure: sqrt(det(J @ J^T)).

workspace_radius(dh_params)
    Min/max workspace radius bounds from link-length geometry.

joint_trajectory_trapezoidal(q_start, q_end, v_max, a_max, dt)
    Joint-space trapezoidal velocity trajectory (time-scaled, synchronised).

DH convention (Modified Craig / standard):
  Each row of dh_params: [a_i, alpha_i, d_i, theta_offset_i]
  joint_angles[i] is added to theta_offset_i for revolute joints.

All warning conditions (unreachable, singular, joint limit) are appended to
a 'warnings' list in the returned dict.  Functions never raise.

References
----------
Craig, J.J. "Introduction to Robotics: Mechanics and Control", 3rd ed.
Spong, M.W., Hutchinson, S., Vidyasagar, M. "Robot Modeling and Control", 2006.
Siciliano, B. et al. "Robotics: Modelling, Planning and Control", 2009.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings as _warnings_module
from typing import List, Optional, Tuple

from kerf_cad_core._linalg import (
    identity4 as _identity4,
    mat4_mul as _mat4_mul,
    mat4_col as _mat4_col,
    cross3 as _cross3,
    dot3 as _dot3,
    norm3 as _norm3,
    mat_mul_rect as _mat_mul_rect,
    mat_transpose as _mat_transpose,
    det_square as _det_square,
)

# ---------------------------------------------------------------------------
# Type alias kept for local annotations
# ---------------------------------------------------------------------------

_Mat4 = List[List[float]]


# ---------------------------------------------------------------------------
# DH matrix
# ---------------------------------------------------------------------------

def dh_matrix(a: float, alpha: float, d: float, theta: float) -> dict:
    """
    Build a single 4×4 Denavit-Hartenberg homogeneous transform.

    Standard DH convention (Craig):
        T = Rz(theta) · Tz(d) · Tx(a) · Rx(alpha)

    Parameters
    ----------
    a     : link length (metres)
    alpha : link twist (radians)
    d     : link offset (metres)
    theta : joint angle (radians)

    Returns
    -------
    dict with keys:
        ok     : True
        matrix : 4×4 list-of-lists (row-major)
    """
    ct = math.cos(theta)
    st = math.sin(theta)
    ca = math.cos(alpha)
    sa = math.sin(alpha)

    T: _Mat4 = [
        [ct,       -st * ca,   st * sa,   a * ct],
        [st,        ct * ca,  -ct * sa,   a * st],
        [0.0,       sa,         ca,        d     ],
        [0.0,       0.0,        0.0,       1.0   ],
    ]
    return {"ok": True, "matrix": T}


# ---------------------------------------------------------------------------
# Forward kinematics
# ---------------------------------------------------------------------------

def fk_chain(
    dh_params: List[List[float]],
    joint_angles: List[float],
    joint_limits: Optional[List[Optional[Tuple[float, float]]]] = None,
) -> dict:
    """
    Forward kinematics for an n-link revolute-joint serial chain.

    Parameters
    ----------
    dh_params   : list of n rows, each [a_i, alpha_i, d_i, theta_offset_i]
                  alpha_i and theta_offset_i in radians.
    joint_angles: list of n joint angles (radians), added to theta_offset_i.
    joint_limits: optional list of (lo, hi) tuples in radians per joint;
                  None entries skip that joint's limit check.

    Returns
    -------
    dict with keys:
        ok           : True / False
        T            : 4×4 homogeneous transform T_0n (list-of-lists)
        joint_angles : list of effective joint angles used
        warnings     : list of warning strings
    """
    warn: List[str] = []

    if len(dh_params) != len(joint_angles):
        return {
            "ok": False,
            "reason": (
                f"dh_params has {len(dh_params)} rows but "
                f"joint_angles has {len(joint_angles)} elements"
            ),
        }

    n = len(dh_params)
    if n == 0:
        return {
            "ok": True,
            "T": _identity4(),
            "joint_angles": [],
            "warnings": [],
        }

    # Joint limit check
    if joint_limits is not None:
        for i, (q, lim) in enumerate(zip(joint_angles, joint_limits)):
            if lim is None:
                continue
            lo, hi = lim
            if not (lo <= q <= hi):
                warn.append(
                    f"Joint {i} angle {math.degrees(q):.2f}° outside limit "
                    f"[{math.degrees(lo):.2f}°, {math.degrees(hi):.2f}°]"
                )
                _warnings_module.warn(warn[-1], stacklevel=2)

    T = _identity4()
    for i in range(n):
        row = dh_params[i]
        a_i = float(row[0])
        alpha_i = float(row[1])
        d_i = float(row[2])
        theta_offset_i = float(row[3])
        theta_i = theta_offset_i + float(joint_angles[i])
        Ti = dh_matrix(a_i, alpha_i, d_i, theta_i)["matrix"]
        T = _mat4_mul(T, Ti)

    return {
        "ok": True,
        "T": T,
        "joint_angles": list(joint_angles),
        "warnings": warn,
    }


# ---------------------------------------------------------------------------
# End-effector pose
# ---------------------------------------------------------------------------

def end_effector_pose(T: List[List[float]]) -> dict:
    """
    Extract end-effector position and ZYX Euler angles from a 4×4 transform.

    ZYX Euler (roll=Rz, pitch=Ry, yaw=Rx) convention:
        R = Rz(yaw) · Ry(pitch) · Rx(roll)

    Parameters
    ----------
    T : 4×4 homogeneous transform (list-of-lists).

    Returns
    -------
    dict with keys:
        ok        : True
        x, y, z   : end-effector position (metres)
        roll_deg  : rotation about Z (degrees)
        pitch_deg : rotation about Y (degrees)
        yaw_deg   : rotation about X (degrees)
        warnings  : list of warning strings
    """
    warn: List[str] = []

    x = T[0][3]
    y = T[1][3]
    z = T[2][3]

    # ZYX extraction: R = Rz(yaw)*Ry(pitch)*Rx(roll)
    # R[2][0] = -sin(pitch)
    r20 = max(-1.0, min(1.0, T[2][0]))
    pitch = math.asin(-r20)

    cos_pitch = math.cos(pitch)
    if abs(cos_pitch) < 1e-10:
        # Gimbal lock
        warn.append("Gimbal lock detected (cos(pitch) ≈ 0); roll set to 0")
        _warnings_module.warn(warn[-1], stacklevel=2)
        roll = 0.0
        yaw = math.atan2(-T[0][1], T[1][1])
    else:
        roll = math.atan2(T[2][1] / cos_pitch, T[2][2] / cos_pitch)
        yaw  = math.atan2(T[1][0] / cos_pitch, T[0][0] / cos_pitch)

    return {
        "ok": True,
        "x": x,
        "y": y,
        "z": z,
        "roll_deg": math.degrees(roll),
        "pitch_deg": math.degrees(pitch),
        "yaw_deg": math.degrees(yaw),
        "warnings": warn,
    }


# ---------------------------------------------------------------------------
# Inverse kinematics — planar 2R
# ---------------------------------------------------------------------------

def ik_2r_planar(
    l1: float,
    l2: float,
    px: float,
    py: float,
    elbow_up: bool = True,
    joint_limits: Optional[List[Optional[Tuple[float, float]]]] = None,
) -> dict:
    """
    Closed-form inverse kinematics for a planar 2R robot arm.

    The arm lies in the XY plane.
    Joint 1 is at the origin; joint 2 is at the tip of link 1.

    Parameters
    ----------
    l1, l2      : link lengths (metres, > 0).
    px, py      : target end-effector position (metres).
    elbow_up    : True → elbow-up solution; False → elbow-down.
    joint_limits: optional [(lo1,hi1), (lo2,hi2)] in radians.

    Returns
    -------
    dict with keys:
        ok        : True / False
        q1_deg    : joint-1 angle (degrees)
        q2_deg    : joint-2 angle (degrees)
        q1_rad    : joint-1 angle (radians)
        q2_rad    : joint-2 angle (radians)
        reachable : bool
        elbow_up  : bool (the solution used)
        warnings  : list of warning strings
    """
    warn: List[str] = []

    if l1 <= 0.0 or l2 <= 0.0:
        return {"ok": False, "reason": "l1 and l2 must be > 0"}

    r2 = px * px + py * py
    r = math.sqrt(r2)
    r_max = l1 + l2
    r_min = abs(l1 - l2)

    reachable = True
    if r > r_max:
        warn.append(
            f"Target unreachable: distance {r:.6f} > r_max {r_max:.6f}; "
            "clamping to workspace boundary"
        )
        _warnings_module.warn(warn[-1], stacklevel=2)
        reachable = False
        # Clamp
        scale = (r_max - 1e-9) / r
        px *= scale
        py *= scale
        r2 = px * px + py * py
        r = math.sqrt(r2)
    elif r < r_min:
        warn.append(
            f"Target unreachable: distance {r:.6f} < r_min {r_min:.6f}; "
            "clamping to workspace boundary"
        )
        _warnings_module.warn(warn[-1], stacklevel=2)
        reachable = False
        if r < 1e-12:
            px = r_min + 1e-9
            py = 0.0
        else:
            scale = (r_min + 1e-9) / r
            px *= scale
            py *= scale
        r2 = px * px + py * py
        r = math.sqrt(r2)

    # cos(q2) from cosine rule
    cos_q2 = (r2 - l1 * l1 - l2 * l2) / (2.0 * l1 * l2)
    cos_q2 = max(-1.0, min(1.0, cos_q2))
    sin_q2 = math.sqrt(max(0.0, 1.0 - cos_q2 * cos_q2))

    if not elbow_up:
        sin_q2 = -sin_q2

    q2 = math.atan2(sin_q2, cos_q2)

    # q1
    k1 = l1 + l2 * cos_q2
    k2 = l2 * sin_q2
    gamma = math.atan2(py, px)
    beta  = math.atan2(k2, k1)
    q1 = gamma - beta

    # Joint limit check
    if joint_limits is not None:
        for i, (q, lim) in enumerate(zip([q1, q2], joint_limits)):
            if lim is None:
                continue
            lo, hi = lim
            if not (lo <= q <= hi):
                warn.append(
                    f"Joint {i + 1} solution {math.degrees(q):.2f}° outside limit "
                    f"[{math.degrees(lo):.2f}°, {math.degrees(hi):.2f}°]"
                )
                _warnings_module.warn(warn[-1], stacklevel=2)

    return {
        "ok": True,
        "q1_deg": math.degrees(q1),
        "q2_deg": math.degrees(q2),
        "q1_rad": q1,
        "q2_rad": q2,
        "reachable": reachable,
        "elbow_up": elbow_up,
        "warnings": warn,
    }


# ---------------------------------------------------------------------------
# Inverse kinematics — planar 3R
# ---------------------------------------------------------------------------

def ik_3r_planar(
    l1: float,
    l2: float,
    l3: float,
    px: float,
    py: float,
    phi_deg: float = 0.0,
    joint_limits: Optional[List[Optional[Tuple[float, float]]]] = None,
) -> dict:
    """
    Closed-form IK for a planar 3R arm with specified end-effector orientation.

    The wrist (end of link 3) is placed at (px, py) with orientation phi_deg.
    The problem reduces to a 2R IK for the wrist position.

    Parameters
    ----------
    l1, l2, l3  : link lengths (metres, > 0).
    px, py      : end-effector (wrist tip) target position.
    phi_deg     : desired total end-effector angle from the x-axis (degrees).
                  phi = q1 + q2 + q3.
    joint_limits: optional [(lo,hi)×3] in radians.

    Returns
    -------
    dict with keys:
        ok          : True / False
        q1_deg, q2_deg, q3_deg  : joint angles (degrees)
        q1_rad, q2_rad, q3_rad  : joint angles (radians)
        reachable   : bool
        warnings    : list of warning strings
    """
    warn: List[str] = []

    if l1 <= 0.0 or l2 <= 0.0 or l3 <= 0.0:
        return {"ok": False, "reason": "l1, l2, l3 must be > 0"}

    phi = math.radians(phi_deg)

    # Wrist centre (base of link 3)
    wx = px - l3 * math.cos(phi)
    wy = py - l3 * math.sin(phi)

    # Solve 2R for (wx, wy) using l1, l2
    ik2 = ik_2r_planar(l1, l2, wx, wy, elbow_up=True, joint_limits=None)

    reachable = ik2["reachable"]
    if ik2.get("warnings"):
        warn.extend(ik2["warnings"])

    q1 = ik2["q1_rad"]
    q2 = ik2["q2_rad"]
    q3 = phi - q1 - q2

    # Joint limit check
    if joint_limits is not None:
        for i, (q, lim) in enumerate(zip([q1, q2, q3], joint_limits)):
            if lim is None:
                continue
            lo, hi = lim
            if not (lo <= q <= hi):
                warn.append(
                    f"Joint {i + 1} solution {math.degrees(q):.2f}° outside limit "
                    f"[{math.degrees(lo):.2f}°, {math.degrees(hi):.2f}°]"
                )
                _warnings_module.warn(warn[-1], stacklevel=2)

    return {
        "ok": True,
        "q1_deg": math.degrees(q1),
        "q2_deg": math.degrees(q2),
        "q3_deg": math.degrees(q3),
        "q1_rad": q1,
        "q2_rad": q2,
        "q3_rad": q3,
        "reachable": reachable,
        "warnings": warn,
    }


# ---------------------------------------------------------------------------
# Geometric Jacobian
# ---------------------------------------------------------------------------

def geometric_jacobian(
    dh_params: List[List[float]],
    joint_angles: List[float],
) -> dict:
    """
    Compute the 6×n geometric Jacobian for a revolute-joint serial chain.

    The Jacobian maps joint velocities to end-effector spatial velocity:
        [v; omega] = J · dq/dt

    For revolute joint i:
        J_v_i = z_{i-1} × (p_n - p_{i-1})
        J_w_i = z_{i-1}

    where z_{i-1} is the z-axis of frame i-1 and p is the origin position.

    Parameters
    ----------
    dh_params   : n rows of [a, alpha, d, theta_offset] (radians).
    joint_angles: n joint angles (radians).

    Returns
    -------
    dict with keys:
        ok         : True / False
        J          : 6×n Jacobian as list-of-lists (rows: [Jv; Jw])
        n_joints   : int
        singular   : bool (det(J·J^T) ≈ 0)
        warnings   : list of warning strings
    """
    warn: List[str] = []

    if len(dh_params) != len(joint_angles):
        return {
            "ok": False,
            "reason": (
                f"dh_params has {len(dh_params)} rows but "
                f"joint_angles has {len(joint_angles)} elements"
            ),
        }

    n = len(dh_params)
    if n == 0:
        return {
            "ok": True,
            "J": [],
            "n_joints": 0,
            "singular": False,
            "warnings": [],
        }

    # Build intermediate transforms T_0_i for i=0..n
    transforms = [_identity4()]  # T_0_0 = I
    T = _identity4()
    for i in range(n):
        row = dh_params[i]
        a_i     = float(row[0])
        alpha_i = float(row[1])
        d_i     = float(row[2])
        theta_offset_i = float(row[3])
        theta_i = theta_offset_i + float(joint_angles[i])
        Ti = dh_matrix(a_i, alpha_i, d_i, theta_i)["matrix"]
        T = _mat4_mul(T, Ti)
        transforms.append(T)

    # End-effector origin
    T_0n = transforms[n]
    p_n = [T_0n[0][3], T_0n[1][3], T_0n[2][3]]

    # Build Jacobian columns
    J: List[List[float]] = [[0.0] * n for _ in range(6)]

    for i in range(n):
        T_0i = transforms[i]  # frame i-1 (0-indexed: frame before joint i)
        z_i = [T_0i[0][2], T_0i[1][2], T_0i[2][2]]   # z-axis of frame i-1
        p_i = [T_0i[0][3], T_0i[1][3], T_0i[2][3]]   # origin of frame i-1

        dp = [p_n[k] - p_i[k] for k in range(3)]
        Jv = _cross3(z_i, dp)
        Jw = z_i

        J[0][i] = Jv[0]
        J[1][i] = Jv[1]
        J[2][i] = Jv[2]
        J[3][i] = Jw[0]
        J[4][i] = Jw[1]
        J[5][i] = Jw[2]

    # Singularity check via det(J·J^T) for square (n=6) or sub-block
    singular = False
    if n >= 3:
        # Use 3×n linear part Jv
        Jv_mat = [J[r][:] for r in range(3)]
        JvJvT = _mat_mul_rect(Jv_mat, _mat_transpose(Jv_mat))
        d = _det_square(JvJvT)
        if abs(d) < 1e-10:
            singular = True
            warn.append("Near-singular configuration detected (det(Jv·Jv^T) ≈ 0)")
            _warnings_module.warn(warn[-1], stacklevel=2)

    return {
        "ok": True,
        "J": J,
        "n_joints": n,
        "singular": singular,
        "warnings": warn,
    }


# ---------------------------------------------------------------------------
# Manipulability
# ---------------------------------------------------------------------------

def manipulability(J: List[List[float]]) -> dict:
    """
    Yoshikawa manipulability measure: w = sqrt(det(J · J^T)).

    A value of w = 0 indicates a singular configuration.
    Higher w means greater dexterity.

    Parameters
    ----------
    J : 6×n Jacobian (list-of-lists, 6 rows).

    Returns
    -------
    dict with keys:
        ok             : True / False
        manipulability : float
        singular       : bool
        warnings       : list of warning strings
    """
    warn: List[str] = []

    if not J or len(J) != 6:
        return {"ok": False, "reason": "J must be a 6×n matrix (6 rows)"}

    n = len(J[0])
    if n == 0:
        return {
            "ok": True,
            "manipulability": 0.0,
            "singular": True,
            "warnings": ["Zero-column Jacobian"],
        }

    JJT = _mat_mul_rect(J, _mat_transpose(J))
    d = _det_square(JJT)

    if d < 0.0:
        # Numerical noise
        d = 0.0

    w = math.sqrt(d)
    singular = w < 1e-10

    if singular:
        warn.append("Singular configuration: manipulability ≈ 0")
        _warnings_module.warn(warn[-1], stacklevel=2)

    return {
        "ok": True,
        "manipulability": w,
        "singular": singular,
        "warnings": warn,
    }


# ---------------------------------------------------------------------------
# Workspace radius bounds
# ---------------------------------------------------------------------------

def workspace_radius(dh_params: List[List[float]]) -> dict:
    """
    Geometric workspace radius bounds for a revolute-joint serial chain.

    r_max = sum of all link lengths (a_i) + |d_i| contributions.
    r_min = max(0, r_max - 2 * min_link) for symmetric retraction.

    Parameters
    ----------
    dh_params : n rows of [a_i, alpha_i, d_i, theta_offset_i].

    Returns
    -------
    dict with keys:
        ok    : True
        r_max : maximum reach (metres)
        r_min : minimum reach (inner void radius, metres)
    """
    if not dh_params:
        return {"ok": True, "r_max": 0.0, "r_min": 0.0}

    link_lengths = []
    for row in dh_params:
        a_i = abs(float(row[0]))
        d_i = abs(float(row[2]))
        # Use Euclidean combination for offset joints
        effective = math.sqrt(a_i * a_i + d_i * d_i)
        link_lengths.append(effective)

    r_max = sum(link_lengths)
    min_link = min(link_lengths) if link_lengths else 0.0
    r_min = max(0.0, r_max - 2.0 * min_link)

    return {"ok": True, "r_max": r_max, "r_min": r_min}


# ---------------------------------------------------------------------------
# Joint-space trapezoidal velocity trajectory
# ---------------------------------------------------------------------------

def joint_trajectory_trapezoidal(
    q_start: List[float],
    q_end: List[float],
    v_max: float,
    a_max: float,
    dt: float = 0.01,
) -> dict:
    """
    Generate a joint-space trapezoidal velocity trajectory.

    Time-scales so all joints finish simultaneously (synchronised).
    Each joint follows an individual trapezoidal profile scaled to the
    longest-motion joint's duration T_sync.

    Parameters
    ----------
    q_start : list of start joint angles (radians).
    q_end   : list of end joint angles (radians).
    v_max   : maximum joint velocity (rad/s, > 0).
    a_max   : maximum joint acceleration (rad/s², > 0).
    dt      : time step (seconds, > 0, default 0.01).

    Returns
    -------
    dict with keys:
        ok           : True / False
        times        : list of time samples (seconds)
        positions    : list of lists — positions[i][j] = q_j at time i
        velocities   : list of lists — velocities[i][j]
        T_sync       : synchronised motion duration (seconds)
        n_joints     : int
        warnings     : list of warning strings
    """
    warn: List[str] = []

    n = len(q_start)
    if n == 0:
        return {"ok": False, "reason": "q_start must not be empty"}
    if len(q_end) != n:
        return {
            "ok": False,
            "reason": f"q_start length {n} != q_end length {len(q_end)}",
        }
    if v_max <= 0.0:
        return {"ok": False, "reason": "v_max must be > 0"}
    if a_max <= 0.0:
        return {"ok": False, "reason": "a_max must be > 0"}
    if dt <= 0.0:
        return {"ok": False, "reason": "dt must be > 0"}

    displacements = [abs(q_end[j] - q_start[j]) for j in range(n)]

    # Duration for each joint independently
    def _trap_duration(d: float) -> float:
        if d < 1e-12:
            return 0.0
        # Check if triangular profile needed (can't reach v_max)
        d_ramp = v_max * v_max / a_max
        if d_ramp > d:
            # Triangular: T = 2 * sqrt(d / a_max)
            return 2.0 * math.sqrt(d / a_max)
        else:
            t_ramp = v_max / a_max
            t_coast = (d - d_ramp) / v_max
            return 2.0 * t_ramp + t_coast

    durations = [_trap_duration(d) for d in displacements]
    T_sync = max(durations) if durations else 0.0

    if T_sync < 1e-12:
        # Already at goal
        warn.append("Start == end; zero-duration trajectory")
        return {
            "ok": True,
            "times": [0.0],
            "positions": [[q_start[j] for j in range(n)]],
            "velocities": [[0.0] * n],
            "T_sync": 0.0,
            "n_joints": n,
            "warnings": warn,
        }

    # Build time array
    n_steps = max(2, int(math.ceil(T_sync / dt)) + 1)
    times = [i * dt for i in range(n_steps)]
    if times[-1] < T_sync:
        times.append(T_sync)

    def _trap_pos_vel(d: float, sign: float, t: float, T: float) -> Tuple[float, float]:
        """
        Position and velocity for a trapezoidal profile scaled to duration T.
        d  : displacement magnitude
        sign: +1 or -1
        t  : current time
        T  : total duration
        """
        if T < 1e-12 or d < 1e-12:
            return 0.0, 0.0

        t = max(0.0, min(t, T))

        # Scaled peak velocity to fit T_sync (may be < v_max)
        # For synchronisation we scale v_peak to hit T_sync:
        # T = 2*(v/a) + (d - v^2/a)/v = d/v + v/a
        # Solving: a*v^2 - a*T*v + a*d = 0 → v = (T ± sqrt(T²-4d/a)) * a/2 / a
        # i.e. v = a/2*(T ± sqrt(T^2 - 4*d/a))
        discriminant = T * T - 4.0 * d / a_max
        if discriminant < 0.0:
            discriminant = 0.0
        v_peak = 0.5 * a_max * (T - math.sqrt(discriminant))
        v_peak = max(0.0, min(v_peak, v_max))

        t_ramp = v_peak / a_max if a_max > 0.0 else 0.0

        if t <= t_ramp:
            pos = 0.5 * a_max * t * t
            vel = a_max * t
        elif t <= T - t_ramp:
            pos = 0.5 * a_max * t_ramp * t_ramp + v_peak * (t - t_ramp)
            vel = v_peak
        else:
            tau = T - t
            pos = d - 0.5 * a_max * tau * tau
            vel = a_max * tau

        return sign * pos, sign * vel

    positions: List[List[float]] = []
    velocities: List[List[float]] = []

    for t in times:
        pos_row = []
        vel_row = []
        for j in range(n):
            d = displacements[j]
            sign = 1.0 if q_end[j] >= q_start[j] else -1.0
            dp, dv = _trap_pos_vel(d, sign, t, T_sync)
            pos_row.append(q_start[j] + dp)
            vel_row.append(dv)
        positions.append(pos_row)
        velocities.append(vel_row)

    return {
        "ok": True,
        "times": times,
        "positions": positions,
        "velocities": velocities,
        "T_sync": T_sync,
        "n_joints": n,
        "warnings": warn,
    }
