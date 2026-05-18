"""
kerf_motion.body
================
RigidBody data class for 3-D multibody dynamics.

State vector layout (18 floats per body):
    [0:3]   position        (x, y, z)
    [3:6]   linear velocity (vx, vy, vz)
    [6:10]  orientation quaternion (qw, qx, qy, qz)  — unit quaternion
    [10:13] angular velocity (wx, wy, wz)  — body frame

The inertia_tensor is the 3×3 symmetric positive-definite matrix in the
*body frame* (principal axes are most efficient but not required).

All arithmetic is pure Python (lists/tuples) — no numpy dependency so the
module remains embeddable and fast to import in constrained environments.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# 3-D vector / matrix helpers (pure Python)
# ---------------------------------------------------------------------------

Vec3 = Tuple[float, float, float]
Mat3 = Tuple[Tuple[float, float, float],
             Tuple[float, float, float],
             Tuple[float, float, float]]
Quat = Tuple[float, float, float, float]  # (w, x, y, z)


def vec3_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec3_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec3_scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def vec3_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec3_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec3_norm(a: Vec3) -> float:
    return math.sqrt(vec3_dot(a, a))


def mat3_vec(M: Mat3, v: Vec3) -> Vec3:
    return (
        M[0][0] * v[0] + M[0][1] * v[1] + M[0][2] * v[2],
        M[1][0] * v[0] + M[1][1] * v[1] + M[1][2] * v[2],
        M[2][0] * v[0] + M[2][1] * v[1] + M[2][2] * v[2],
    )


def mat3_T(M: Mat3) -> Mat3:
    """Transpose."""
    return (
        (M[0][0], M[1][0], M[2][0]),
        (M[0][1], M[1][1], M[2][1]),
        (M[0][2], M[1][2], M[2][2]),
    )


def mat3_mul(A: Mat3, B: Mat3) -> Mat3:
    return tuple(
        tuple(sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )  # type: ignore[return-value]


def mat3_inv_symmetric_pd(M: Mat3) -> Mat3:
    """Invert a 3×3 symmetric positive-definite matrix (Cramer's rule)."""
    a, b, c = M[0][0], M[0][1], M[0][2]
    d, e, f = M[1][0], M[1][1], M[1][2]
    g, h, i = M[2][0], M[2][1], M[2][2]
    det = (a * (e * i - f * h)
           - b * (d * i - f * g)
           + c * (d * h - e * g))
    if abs(det) < 1e-300:
        raise ValueError("Inertia tensor is singular — body has zero inertia component.")
    inv_det = 1.0 / det
    return (
        ((e * i - f * h) * inv_det, (c * h - b * i) * inv_det, (b * f - c * e) * inv_det),
        ((f * g - d * i) * inv_det, (a * i - c * g) * inv_det, (c * d - a * f) * inv_det),
        ((d * h - e * g) * inv_det, (b * g - a * h) * inv_det, (a * e - b * d) * inv_det),
    )


# ---------------------------------------------------------------------------
# Quaternion helpers
# ---------------------------------------------------------------------------

def quat_mul(p: Quat, q: Quat) -> Quat:
    """Hamilton product p ⊗ q."""
    pw, px, py, pz = p
    qw, qx, qy, qz = q
    return (
        pw * qw - px * qx - py * qy - pz * qz,
        pw * qx + px * qw + py * qz - pz * qy,
        pw * qy - px * qz + py * qw + pz * qx,
        pw * qz + px * qy - py * qx + pz * qw,
    )


def quat_norm(q: Quat) -> float:
    return math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2 + q[3] ** 2)


def quat_normalize(q: Quat) -> Quat:
    n = quat_norm(q)
    if n < 1e-300:
        return (1.0, 0.0, 0.0, 0.0)
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def quat_to_rotmat(q: Quat) -> Mat3:
    """Convert unit quaternion to 3×3 rotation matrix (body→world)."""
    qw, qx, qy, qz = q
    return (
        (1 - 2 * (qy * qy + qz * qz),  2 * (qx * qy - qz * qw),       2 * (qx * qz + qy * qw)),
        (2 * (qx * qy + qz * qw),       1 - 2 * (qx * qx + qz * qz),   2 * (qy * qz - qx * qw)),
        (2 * (qx * qz - qy * qw),       2 * (qy * qz + qx * qw),       1 - 2 * (qx * qx + qy * qy)),
    )


def quat_from_axis_angle(axis: Vec3, angle_rad: float) -> Quat:
    """Build unit quaternion from axis (need not be normalised) and angle."""
    n = vec3_norm(axis)
    if n < 1e-300:
        return (1.0, 0.0, 0.0, 0.0)
    s = math.sin(angle_rad / 2.0)
    return (
        math.cos(angle_rad / 2.0),
        axis[0] / n * s,
        axis[1] / n * s,
        axis[2] / n * s,
    )


def quat_deriv(q: Quat, omega_body: Vec3) -> Quat:
    """Time derivative q̇ = 0.5 q ⊗ [0, ω_body]."""
    omega_quat: Quat = (0.0, omega_body[0], omega_body[1], omega_body[2])
    dq = quat_mul(q, omega_quat)
    return (dq[0] * 0.5, dq[1] * 0.5, dq[2] * 0.5, dq[3] * 0.5)


# ---------------------------------------------------------------------------
# RigidBody
# ---------------------------------------------------------------------------

@dataclass
class RigidBody:
    """
    Rigid body with 6 degrees of freedom.

    Parameters
    ----------
    mass : float
        Total mass (kg).  Must be > 0.
    inertia_tensor : Mat3
        3×3 symmetric positive-definite inertia tensor in the *body frame* (kg m²).
        Pass ``((Ixx,0,0),(0,Iyy,0),(0,0,Izz))`` for principal axes.
    position : Vec3
        Initial position in world frame (m).
    orientation : Quat or None
        Initial orientation as unit quaternion (w,x,y,z).  Defaults to identity.
    velocity : Vec3
        Initial linear velocity in world frame (m/s).
    angular_velocity : Vec3
        Initial angular velocity in *body frame* (rad/s).
    name : str
        Optional label for debugging and output.
    """

    mass: float
    inertia_tensor: Mat3
    position: Vec3 = (0.0, 0.0, 0.0)
    orientation: Optional[Quat] = None
    velocity: Vec3 = (0.0, 0.0, 0.0)
    angular_velocity: Vec3 = (0.0, 0.0, 0.0)
    name: str = "body"

    def __post_init__(self):
        if self.mass <= 0:
            raise ValueError(f"RigidBody '{self.name}': mass must be positive, got {self.mass}")
        if self.orientation is None:
            object.__setattr__(self, "orientation", (1.0, 0.0, 0.0, 0.0))
        # Validate inertia tensor dimensions
        I = self.inertia_tensor
        if len(I) != 3 or any(len(row) != 3 for row in I):
            raise ValueError(f"RigidBody '{self.name}': inertia_tensor must be 3×3")
        # Precompute inverse inertia (fail fast on degenerate inputs)
        self._I_inv: Mat3 = mat3_inv_symmetric_pd(I)

    # ---- convenience properties --------------------------------------------

    @property
    def rotation_matrix(self) -> Mat3:
        """Current body→world rotation matrix from the orientation quaternion."""
        return quat_to_rotmat(self.orientation)  # type: ignore[arg-type]

    @property
    def I_body(self) -> Mat3:
        return self.inertia_tensor

    @property
    def I_body_inv(self) -> Mat3:
        return self._I_inv

    def I_world_inv(self) -> Mat3:
        """Inverse inertia tensor expressed in world frame:  R · I_body⁻¹ · Rᵀ."""
        R = self.rotation_matrix
        Rt = mat3_T(R)
        return mat3_mul(R, mat3_mul(self._I_inv, Rt))

    # ---- state vector encoding / decoding ----------------------------------

    def to_state(self) -> List[float]:
        """
        Pack body state into a flat list of 13 floats:
            [px, py, pz, vx, vy, vz, qw, qx, qy, qz, wx, wy, wz]
        """
        p = self.position
        v = self.velocity
        q = self.orientation
        w = self.angular_velocity
        return [p[0], p[1], p[2],
                v[0], v[1], v[2],
                q[0], q[1], q[2], q[3],  # type: ignore[index]
                w[0], w[1], w[2]]

    @classmethod
    def from_state(cls, body: "RigidBody", state: List[float]) -> "RigidBody":
        """
        Return a new RigidBody with updated state (non-mutating).
        ``body`` is used as a template for mass/inertia/name.
        """
        from dataclasses import replace
        pos: Vec3 = (state[0], state[1], state[2])
        vel: Vec3 = (state[3], state[4], state[5])
        ori: Quat = quat_normalize((state[6], state[7], state[8], state[9]))
        omg: Vec3 = (state[10], state[11], state[12])
        return replace(body, position=pos, velocity=vel, orientation=ori, angular_velocity=omg)

    # ---- equations of motion (derivatives) ---------------------------------

    def state_derivatives(
        self,
        net_force: Vec3,
        net_torque_world: Vec3,
    ) -> List[float]:
        """
        Compute ẋ = f(x) given applied force and torque (both in world frame).

        Returns 13 floats matching the ``to_state()`` layout:
            [ṗx, ṗy, ṗz, v̇x, v̇y, v̇z, q̇w, q̇x, q̇y, q̇z, ẇx, ẇy, ẇz]

        Newton-Euler equations:
            ṗ = v
            mv̇ = F
            q̇ = 0.5 q ⊗ [0, ω]
            I_body ω̇ = τ_body − ω × (I_body ω)
        """
        v = self.velocity
        q = self.orientation  # type: ignore[assignment]
        omega_body = self.angular_velocity

        # Linear: ṗ = v
        dp = v

        # Linear: v̇ = F/m
        dv: Vec3 = (net_force[0] / self.mass,
                    net_force[1] / self.mass,
                    net_force[2] / self.mass)

        # Angular: q̇
        dq = quat_deriv(q, omega_body)

        # Convert world torque → body torque:  τ_body = Rᵀ τ_world
        R = self.rotation_matrix
        Rt = mat3_T(R)
        tau_body = mat3_vec(Rt, net_torque_world)

        # Euler equation: I ω̇ = τ - ω × (I ω)
        I = self.I_body
        Iw: Vec3 = mat3_vec(I, omega_body)
        gyro: Vec3 = vec3_cross(omega_body, Iw)
        rhs: Vec3 = vec3_sub(tau_body, gyro)
        domega: Vec3 = mat3_vec(self._I_inv, rhs)

        return [dp[0], dp[1], dp[2],
                dv[0], dv[1], dv[2],
                dq[0], dq[1], dq[2], dq[3],
                domega[0], domega[1], domega[2]]
