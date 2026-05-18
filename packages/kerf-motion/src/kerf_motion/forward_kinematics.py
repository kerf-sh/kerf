"""
kerf_motion.forward_kinematics
===============================
Forward kinematics for kinematic chains.

Given a root body and a sequence of joints (each with a current DOF value),
compute the end-effector pose (position + orientation) in the world frame.

All pure Python — no numpy/scipy.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from kerf_motion.body import (
    Vec3, Mat3, Quat,
    quat_mul, quat_normalize, quat_to_rotmat,
    mat3_vec, mat3_T, mat3_mul,
    vec3_add,
)
from kerf_motion.joints import Joint


# ---------------------------------------------------------------------------
# Pose dataclass
# ---------------------------------------------------------------------------

class Pose:
    """6-DOF pose: position (world frame) + orientation (unit quaternion)."""
    __slots__ = ("position", "orientation")

    def __init__(self, position: Vec3, orientation: Quat):
        self.position: Vec3 = position
        self.orientation: Quat = orientation

    @property
    def rotation_matrix(self) -> Mat3:
        return quat_to_rotmat(self.orientation)

    def __repr__(self) -> str:
        p = self.position
        q = self.orientation
        return (f"Pose(pos=({p[0]:.4f},{p[1]:.4f},{p[2]:.4f}), "
                f"quat=({q[0]:.4f},{q[1]:.4f},{q[2]:.4f},{q[3]:.4f}))")


# ---------------------------------------------------------------------------
# Compose two poses: T_world_child = T_world_parent ∘ T_parent_child
# ---------------------------------------------------------------------------

def compose_poses(parent: Pose, child_in_parent: Pose) -> Pose:
    """
    Compose parent pose with a child pose expressed in the parent frame.

    new_position    = parent.position + R_parent * child_in_parent.position
    new_orientation = parent.orientation ⊗ child_in_parent.orientation
    """
    R_p = quat_to_rotmat(parent.orientation)
    offset_world = mat3_vec(R_p, child_in_parent.position)
    new_pos: Vec3 = vec3_add(parent.position, offset_world)
    new_ori: Quat = quat_normalize(quat_mul(parent.orientation, child_in_parent.orientation))
    return Pose(position=new_pos, orientation=new_ori)


# ---------------------------------------------------------------------------
# Forward kinematics for a serial chain
# ---------------------------------------------------------------------------

def forward_kinematics(
    joints: List[Joint],
    root_pose: Optional[Pose] = None,
) -> List[Pose]:
    """
    Compute the pose of each link in a serial kinematic chain.

    Parameters
    ----------
    joints    : ordered list of Joint objects (root → tip).
                Each joint's ``transform()`` is called to get the current
                child-in-parent pose contributed by that joint.
    root_pose : world-frame pose of the root link (default: identity).

    Returns
    -------
    poses : list of Pose, one per joint link *after* that joint,
            i.e. ``poses[i]`` is the pose of the (i+1)-th link in the world
            frame.  ``len(poses) == len(joints)``.

    Notes
    -----
    For a chain  root → J0 → link0 → J1 → link1 → … → Jn → end-effector:
        poses[0] = world pose of link0
        poses[-1] = world pose of the end-effector frame
    """
    if root_pose is None:
        root_pose = Pose(position=(0.0, 0.0, 0.0), orientation=(1.0, 0.0, 0.0, 0.0))

    current_pose = root_pose
    poses: List[Pose] = []

    for joint in joints:
        jt = joint.transform()
        joint_pose = Pose(position=jt.translation, orientation=jt.rotation)
        current_pose = compose_poses(current_pose, joint_pose)
        poses.append(current_pose)

    return poses


def end_effector_pose(
    joints: List[Joint],
    root_pose: Optional[Pose] = None,
) -> Pose:
    """Convenience: return only the final (end-effector) pose."""
    poses = forward_kinematics(joints, root_pose)
    if not poses:
        if root_pose is None:
            return Pose((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
        return root_pose
    return poses[-1]


# ---------------------------------------------------------------------------
# Jacobian (for numerical IK)
# ---------------------------------------------------------------------------

def geometric_jacobian(
    joints: List[Joint],
    root_pose: Optional[Pose] = None,
    delta: float = 1e-6,
) -> List[List[float]]:
    """
    Compute the 6×n geometric Jacobian of the end-effector w.r.t. each
    revolute joint angle using finite differences.

    Returns
    -------
    J : list of lists, shape (6, n_revolute_joints)
        Rows 0-2: linear velocity Jacobian (dx/dθ_i)
        Rows 3-5: angular velocity Jacobian (omitted — set to zero for 2-D FK tests)

    Only RevoluteJoint and PrismaticJoint are considered for the column count.
    """
    from kerf_motion.joints import RevoluteJoint, PrismaticJoint

    active_joints = [j for j in joints if isinstance(j, (RevoluteJoint, PrismaticJoint))]
    n = len(active_joints)
    if n == 0:
        return []

    # Baseline end-effector position
    base_ee = end_effector_pose(joints, root_pose)
    p0 = base_ee.position
    q0 = base_ee.orientation

    J: List[List[float]] = [[0.0] * n for _ in range(6)]

    for col, aj in enumerate(active_joints):
        # Save current DOF
        saved = aj.get_dof()

        # Perturb
        perturbed = [v + (delta if k == 0 else 0.0) for k, v in enumerate(saved)]
        aj.set_dof(perturbed)

        ee_plus = end_effector_pose(joints, root_pose)
        pp = ee_plus.position

        # Restore
        aj.set_dof(saved)

        # Linear part
        J[0][col] = (pp[0] - p0[0]) / delta
        J[1][col] = (pp[1] - p0[1]) / delta
        J[2][col] = (pp[2] - p0[2]) / delta
        # Angular part (simplified — uses quaternion difference axis)
        # For this implementation angular Jacobian rows 3-5 left as zeros
        # (sufficient for position-only IK)

    return J
