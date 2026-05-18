"""
kerf_motion.inverse_kinematics
================================
Inverse kinematics solvers.

Solvers
-------
analytic_ik_2link(l1, l2, target_x, target_y, elbow_up=True)
    Closed-form IK for a planar 2-link arm.

jacobian_transpose_ik(joints, target, ...)
    Numerical IK (Jacobian transpose) for an n-DOF serial chain.

All pure Python.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from kerf_motion.body import Vec3
from kerf_motion.forward_kinematics import (
    end_effector_pose, geometric_jacobian, Pose,
)
from kerf_motion.joints import Joint, RevoluteJoint, PrismaticJoint


# ---------------------------------------------------------------------------
# 2-link planar arm — closed-form IK
# ---------------------------------------------------------------------------

def analytic_ik_2link(
    l1: float,
    l2: float,
    target_x: float,
    target_y: float,
    *,
    elbow_up: bool = True,
) -> Dict:
    """
    Closed-form inverse kinematics for a planar 2-link arm (shoulder + elbow,
    both revolute joints about the Z-axis, base at origin).

    Reference
    ---------
    Craig, J.J., Introduction to Robotics, 3rd ed. (2005), §4.4.

    Parameters
    ----------
    l1, l2      : link lengths (m)
    target_x/y  : end-effector target position in the XY plane
    elbow_up    : True  → positive elbow angle (above the line l1–target)
                  False → negative elbow angle

    Returns
    -------
    dict
        ok           : bool
        theta1, theta2 : joint angles in radians (shoulder, elbow)
        reason         : error string if ok=False
    """
    if l1 <= 0 or l2 <= 0:
        return {"ok": False, "reason": "link lengths must be positive"}

    r2 = target_x ** 2 + target_y ** 2
    r = math.sqrt(r2)

    # Reachability: |l1 - l2| ≤ r ≤ l1 + l2
    if r > l1 + l2 + 1e-12:
        return {"ok": False, "reason": f"target unreachable: r={r:.6g} > l1+l2={l1+l2:.6g}"}
    if r < abs(l1 - l2) - 1e-12:
        return {"ok": False, "reason": f"target unreachable: r={r:.6g} < |l1-l2|={abs(l1-l2):.6g}"}

    # Cosine rule: cos(θ2) = (r² - l1² - l2²) / (2 l1 l2)
    cos_theta2 = (r2 - l1 ** 2 - l2 ** 2) / (2.0 * l1 * l2)
    cos_theta2 = max(-1.0, min(1.0, cos_theta2))  # clamp numerical noise
    sin_theta2 = math.sqrt(max(0.0, 1.0 - cos_theta2 ** 2))

    if not elbow_up:
        sin_theta2 = -sin_theta2

    theta2 = math.atan2(sin_theta2, cos_theta2)

    # Shoulder angle: θ1 = atan2(y, x) − atan2(l2 sin θ2, l1 + l2 cos θ2)
    k1 = l1 + l2 * cos_theta2
    k2 = l2 * sin_theta2
    gamma = math.atan2(k2, k1)
    phi = math.atan2(target_y, target_x)
    theta1 = phi - gamma

    return {
        "ok": True,
        "theta1": theta1,
        "theta2": theta2,
        "elbow_up": elbow_up,
    }


# ---------------------------------------------------------------------------
# Numerical IK — Jacobian transpose method
# ---------------------------------------------------------------------------

def jacobian_transpose_ik(
    joints: List[Joint],
    target: Vec3,
    *,
    root_pose: Optional[Pose] = None,
    max_iterations: int = 1000,
    tol: float = 1e-6,
    alpha: float = 0.1,
    alpha_decay: float = 0.999,
) -> Dict:
    """
    Jacobian transpose IK for a serial chain of Revolute/Prismatic joints.

    At each iteration:
        e = target − p_ee
        Δθ = αJᵀ e
        θ ← θ + Δθ

    Parameters
    ----------
    joints         : list of Joint objects forming the serial chain
    target         : (x, y, z) target end-effector position in world frame
    root_pose      : world pose of the chain root (default = identity)
    max_iterations : iteration budget
    tol            : convergence criterion on ||e||
    alpha          : initial step size
    alpha_decay    : multiply alpha by this each iteration (≤ 1.0)

    Returns
    -------
    dict
        ok          : bool
        theta       : list of final joint values (DOF order)
        error_norm  : final ||e||
        iterations  : iterations taken
        reason      : error string if ok=False
    """
    active_joints = [j for j in joints if isinstance(j, (RevoluteJoint, PrismaticJoint))]
    if not active_joints:
        return {"ok": False, "reason": "no active (revolute/prismatic) joints found"}

    alpha_cur = alpha
    n = len(active_joints)

    for it in range(max_iterations):
        ee = end_effector_pose(joints, root_pose)
        p = ee.position
        ex = target[0] - p[0]
        ey = target[1] - p[1]
        ez = target[2] - p[2]
        err_norm = math.sqrt(ex * ex + ey * ey + ez * ez)

        if err_norm < tol:
            theta_out = []
            for j in active_joints:
                theta_out.extend(j.get_dof())
            return {
                "ok": True,
                "theta": theta_out,
                "error_norm": err_norm,
                "iterations": it,
            }

        # Jacobian (linear part only, rows 0-2)
        J = geometric_jacobian(joints, root_pose, delta=1e-7)

        if not J:
            return {"ok": False, "reason": "Jacobian is empty"}

        e_vec = [ex, ey, ez]
        # Jᵀ e  — only use linear rows
        dtheta = [0.0] * n
        for col in range(n):
            for row in range(3):
                dtheta[col] += J[row][col] * e_vec[row]

        # Update joint DOFs
        col = 0
        for aj in active_joints:
            dof = aj.get_dof()
            new_dof = [dof[k] + alpha_cur * dtheta[col + k] for k in range(len(dof))]
            aj.set_dof(new_dof)
            col += len(dof)

        alpha_cur *= alpha_decay

    # Did not converge
    ee = end_effector_pose(joints, root_pose)
    p = ee.position
    ex = target[0] - p[0]
    ey = target[1] - p[1]
    ez = target[2] - p[2]
    err_norm = math.sqrt(ex * ex + ey * ey + ez * ez)
    theta_out = []
    for j in active_joints:
        theta_out.extend(j.get_dof())
    return {
        "ok": err_norm < tol * 10,   # loose convergence
        "theta": theta_out,
        "error_norm": err_norm,
        "iterations": max_iterations,
        "reason": "max_iterations reached" if err_norm >= tol * 10 else "converged (loose)",
    }


# ---------------------------------------------------------------------------
# Workspace sampler
# ---------------------------------------------------------------------------

def compute_workspace_2d(
    joints: List[Joint],
    *,
    root_pose: Optional[Pose] = None,
    n_samples: int = 200,
) -> Dict:
    """
    Monte-Carlo workspace for a planar serial chain projected onto XY.

    Sweeps each revolute joint over its full range (or [−π, π] if unconstrained)
    and returns the cloud of reachable end-effector positions.

    Returns
    -------
    dict
        ok     : bool
        points : list of (x, y, z) tuples
        count  : number of sampled configurations
    """
    import itertools

    revolute_joints = [j for j in joints if isinstance(j, RevoluteJoint)]
    if not revolute_joints:
        return {"ok": False, "reason": "no revolute joints found"}

    # Determine sweep ranges
    ranges: List[Tuple[float, float]] = []
    for j in revolute_joints:
        if j.limits is not None:
            lo, hi = j.limits
        else:
            lo, hi = -math.pi, math.pi
        ranges.append((lo, hi))

    n_joints = len(revolute_joints)
    # Samples per joint (total = n_samples^(1/n_joints) approximately)
    per_joint = max(2, int(round(n_samples ** (1.0 / n_joints))))

    angles_per_joint = [
        [lo + (hi - lo) * k / max(per_joint - 1, 1) for k in range(per_joint)]
        for lo, hi in ranges
    ]

    points = []
    for combo in itertools.product(*angles_per_joint):
        for j, theta in zip(revolute_joints, combo):
            j.set_dof([theta])
        ee = end_effector_pose(joints, root_pose)
        points.append(ee.position)

    return {"ok": True, "points": points, "count": len(points)}
