"""
kerf_motion.joints
==================
Joint (constraint) classes for multibody kinematic chains.

Each joint:
  - stores the parent/child body indices
  - tracks its generalised coordinate(s) — angle(s), translation(s)
  - can compute the joint transform  T_child_in_parent(q)
  - exposes ``n_dof``

Joint types implemented
-----------------------
FixedJoint          0 DOF  — rigid attachment
RevoluteJoint       1 DOF  — rotation about one axis
PrismaticJoint      1 DOF  — translation along one axis
CylindricalJoint    2 DOF  — rotation + translation about/along the same axis
UniversalJoint      2 DOF  — two perpendicular rotation axes (Hooke's coupling)
SphericalJoint      3 DOF  — rotation about three axes (ball-and-socket)

All pure Python, no numpy/scipy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from kerf_motion.body import (
    Vec3, Mat3, Quat,
    quat_from_axis_angle, quat_mul, quat_normalize,
    mat3_mul, mat3_T, mat3_vec,
    vec3_add,
)


# ---------------------------------------------------------------------------
# Joint transform result
# ---------------------------------------------------------------------------

@dataclass
class JointTransform:
    """
    Pose of the child origin w.r.t. the parent origin.

    translation : Vec3  — offset in parent frame
    rotation    : Quat  — unit quaternion (w,x,y,z), child←parent
    """
    translation: Vec3
    rotation: Quat


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Joint:
    """Abstract base — concrete joints override ``transform()``."""

    n_dof: int = 0

    def __init__(
        self,
        parent_idx: int,
        child_idx: int,
        *,
        parent_offset: Vec3 = (0.0, 0.0, 0.0),
        child_offset: Vec3 = (0.0, 0.0, 0.0),
        name: str = "joint",
    ):
        self.parent_idx = parent_idx
        self.child_idx = child_idx
        self.parent_offset = parent_offset   # joint anchor in parent body frame
        self.child_offset = child_offset     # joint anchor in child body frame
        self.name = name

    def transform(self) -> JointTransform:
        """Return current joint transform (child pose in parent frame)."""
        raise NotImplementedError

    def set_dof(self, values: List[float]) -> None:
        """Set generalised coordinates."""
        if len(values) != self.n_dof:
            raise ValueError(
                f"{self.name}: expected {self.n_dof} dof values, got {len(values)}"
            )

    def get_dof(self) -> List[float]:
        return []


# ---------------------------------------------------------------------------
# FixedJoint
# ---------------------------------------------------------------------------

class FixedJoint(Joint):
    """
    Rigid attachment — zero DOF.

    The child is permanently offset by ``parent_offset`` in the parent frame
    with identity relative rotation.
    """

    n_dof = 0

    def transform(self) -> JointTransform:
        return JointTransform(
            translation=self.parent_offset,
            rotation=(1.0, 0.0, 0.0, 0.0),
        )


# ---------------------------------------------------------------------------
# RevoluteJoint
# ---------------------------------------------------------------------------

class RevoluteJoint(Joint):
    """
    Single-axis rotational joint.

    Parameters
    ----------
    axis : Vec3
        Rotation axis in the parent frame (need not be normalised).
    angle : float
        Initial angle in radians.
    limits : tuple or None
        (lower, upper) angle limits in radians.  None means unconstrained.
    """

    n_dof = 1

    def __init__(
        self,
        parent_idx: int,
        child_idx: int,
        axis: Vec3 = (0.0, 0.0, 1.0),
        angle: float = 0.0,
        limits: Optional[Tuple[float, float]] = None,
        **kwargs,
    ):
        super().__init__(parent_idx, child_idx, **kwargs)
        n = math.sqrt(axis[0]**2 + axis[1]**2 + axis[2]**2)
        if n < 1e-12:
            raise ValueError(f"RevoluteJoint '{self.name}': axis must be non-zero")
        self.axis: Vec3 = (axis[0] / n, axis[1] / n, axis[2] / n)
        self.angle = angle
        self.limits = limits

    def set_dof(self, values: List[float]) -> None:
        super().set_dof(values)
        theta = values[0]
        if self.limits is not None:
            lo, hi = self.limits
            theta = max(lo, min(hi, theta))
        self.angle = theta

    def get_dof(self) -> List[float]:
        return [self.angle]

    def transform(self) -> JointTransform:
        q = quat_from_axis_angle(self.axis, self.angle)
        return JointTransform(translation=self.parent_offset, rotation=q)


# ---------------------------------------------------------------------------
# PrismaticJoint
# ---------------------------------------------------------------------------

class PrismaticJoint(Joint):
    """
    Single-axis translational joint.

    Parameters
    ----------
    axis : Vec3
        Sliding direction in the parent frame (normalised internally).
    position : float
        Initial displacement along the axis (m).
    limits : tuple or None
        (lower, upper) position limits in metres.
    """

    n_dof = 1

    def __init__(
        self,
        parent_idx: int,
        child_idx: int,
        axis: Vec3 = (1.0, 0.0, 0.0),
        position: float = 0.0,
        limits: Optional[Tuple[float, float]] = None,
        **kwargs,
    ):
        super().__init__(parent_idx, child_idx, **kwargs)
        n = math.sqrt(axis[0]**2 + axis[1]**2 + axis[2]**2)
        if n < 1e-12:
            raise ValueError(f"PrismaticJoint '{self.name}': axis must be non-zero")
        self.axis: Vec3 = (axis[0] / n, axis[1] / n, axis[2] / n)
        self.position = position
        self.limits = limits

    def set_dof(self, values: List[float]) -> None:
        super().set_dof(values)
        d = values[0]
        if self.limits is not None:
            lo, hi = self.limits
            d = max(lo, min(hi, d))
        self.position = d

    def get_dof(self) -> List[float]:
        return [self.position]

    def transform(self) -> JointTransform:
        a = self.axis
        d = self.position
        total: Vec3 = (
            self.parent_offset[0] + a[0] * d,
            self.parent_offset[1] + a[1] * d,
            self.parent_offset[2] + a[2] * d,
        )
        return JointTransform(translation=total, rotation=(1.0, 0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# CylindricalJoint
# ---------------------------------------------------------------------------

class CylindricalJoint(Joint):
    """
    2-DOF joint: rotation + translation along the same axis (cylindrical pair).

    DOF order: [angle_rad, translation_m]
    """

    n_dof = 2

    def __init__(
        self,
        parent_idx: int,
        child_idx: int,
        axis: Vec3 = (0.0, 0.0, 1.0),
        angle: float = 0.0,
        position: float = 0.0,
        **kwargs,
    ):
        super().__init__(parent_idx, child_idx, **kwargs)
        n = math.sqrt(axis[0]**2 + axis[1]**2 + axis[2]**2)
        self.axis: Vec3 = (axis[0] / n, axis[1] / n, axis[2] / n)
        self.angle = angle
        self.position = position

    def set_dof(self, values: List[float]) -> None:
        super().set_dof(values)
        self.angle = values[0]
        self.position = values[1]

    def get_dof(self) -> List[float]:
        return [self.angle, self.position]

    def transform(self) -> JointTransform:
        q = quat_from_axis_angle(self.axis, self.angle)
        a = self.axis
        d = self.position
        trans: Vec3 = (
            self.parent_offset[0] + a[0] * d,
            self.parent_offset[1] + a[1] * d,
            self.parent_offset[2] + a[2] * d,
        )
        return JointTransform(translation=trans, rotation=q)


# ---------------------------------------------------------------------------
# UniversalJoint  (Hooke's coupling)
# ---------------------------------------------------------------------------

class UniversalJoint(Joint):
    """
    2-DOF universal (Hooke's) joint.

    The first rotation is about ``axis1`` (parent frame).
    The second rotation is about ``axis2`` (rotated child frame after first rotation).

    By convention  axis1 ⊥ axis2  (typically Z and X).

    DOF order: [angle1_rad, angle2_rad]
    """

    n_dof = 2

    def __init__(
        self,
        parent_idx: int,
        child_idx: int,
        axis1: Vec3 = (0.0, 0.0, 1.0),
        axis2: Vec3 = (1.0, 0.0, 0.0),
        angle1: float = 0.0,
        angle2: float = 0.0,
        **kwargs,
    ):
        super().__init__(parent_idx, child_idx, **kwargs)

        def _norm(v: Vec3) -> Vec3:
            n = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
            return (v[0] / n, v[1] / n, v[2] / n)

        self.axis1 = _norm(axis1)
        self.axis2 = _norm(axis2)
        self.angle1 = angle1
        self.angle2 = angle2

    def set_dof(self, values: List[float]) -> None:
        super().set_dof(values)
        self.angle1, self.angle2 = values[0], values[1]

    def get_dof(self) -> List[float]:
        return [self.angle1, self.angle2]

    def transform(self) -> JointTransform:
        q1 = quat_from_axis_angle(self.axis1, self.angle1)
        q2 = quat_from_axis_angle(self.axis2, self.angle2)
        q = quat_normalize(quat_mul(q1, q2))
        return JointTransform(translation=self.parent_offset, rotation=q)


# ---------------------------------------------------------------------------
# SphericalJoint  (ball-and-socket)
# ---------------------------------------------------------------------------

class SphericalJoint(Joint):
    """
    3-DOF ball-and-socket joint parameterised by a unit quaternion.

    DOF order: [qw, qx, qy, qz]  (automatically re-normalised on set_dof).
    """

    n_dof = 3  # true DOF; stored as 4-param quaternion but one is constrained

    def __init__(
        self,
        parent_idx: int,
        child_idx: int,
        orientation: Optional[Quat] = None,
        **kwargs,
    ):
        super().__init__(parent_idx, child_idx, **kwargs)
        self._q: Quat = orientation if orientation is not None else (1.0, 0.0, 0.0, 0.0)

    # For a spherical joint the 3 independent DOFs are Euler angles or
    # axis-angle; we expose [angle_x, angle_y, angle_z] (extrinsic XYZ) for
    # simplicity in tool calls.

    def set_orientation(self, q: Quat) -> None:
        self._q = quat_normalize(q)

    def set_euler_xyz(self, rx: float, ry: float, rz: float) -> None:
        qx = quat_from_axis_angle((1.0, 0.0, 0.0), rx)
        qy = quat_from_axis_angle((0.0, 1.0, 0.0), ry)
        qz = quat_from_axis_angle((0.0, 0.0, 1.0), rz)
        self._q = quat_normalize(quat_mul(quat_mul(qz, qy), qx))

    def transform(self) -> JointTransform:
        return JointTransform(translation=self.parent_offset, rotation=self._q)
