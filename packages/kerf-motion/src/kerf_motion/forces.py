"""
kerf_motion.forces
==================
Force/torque generators for multibody simulations.

Each force generator is a callable:

    force_fn(bodies: list[RigidBody], t: float)
        → list of (force: Vec3, torque_world: Vec3) — one pair per body

All implementations are pure Python.
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

from kerf_motion.body import (
    RigidBody, Vec3,
    vec3_add, vec3_sub, vec3_scale, vec3_dot, vec3_norm,
    quat_to_rotmat, mat3_vec,
)


ForceField = Callable[[List[RigidBody], float], List[Tuple[Vec3, Vec3]]]

_ZERO3: Vec3 = (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Gravity
# ---------------------------------------------------------------------------

def gravity(g: float = 9.80665, axis: int = 1, sign: int = -1) -> ForceField:
    """
    Uniform gravitational field.

    Parameters
    ----------
    g    : gravitational acceleration magnitude (m/s²).  Default = standard g.
    axis : Cartesian axis (0=x, 1=y, 2=z).  Default = y (downward = negative y).
    sign : +1 or -1.  Default = -1 (gravity acts in the negative axis direction).

    Returns a ForceField that produces  F_i = m_i · g · sign · ê_axis
    and zero torque for every body.
    """
    accel_mag = g * sign

    def _grav(bodies: List[RigidBody], t: float) -> List[Tuple[Vec3, Vec3]]:
        result = []
        for b in bodies:
            fv = [0.0, 0.0, 0.0]
            fv[axis] = b.mass * accel_mag
            result.append(((fv[0], fv[1], fv[2]), _ZERO3))
        return result

    return _grav


# ---------------------------------------------------------------------------
# Constant external force / torque on a single body
# ---------------------------------------------------------------------------

def applied_force(
    body_idx: int,
    force: Vec3 = (0.0, 0.0, 0.0),
    torque: Vec3 = (0.0, 0.0, 0.0),
) -> ForceField:
    """
    Constant external force and/or torque applied to body ``body_idx``.
    Both are expressed in the *world frame*.
    """
    def _f(bodies: List[RigidBody], t: float) -> List[Tuple[Vec3, Vec3]]:
        return [
            ((force if i == body_idx else _ZERO3),
             (torque if i == body_idx else _ZERO3))
            for i in range(len(bodies))
        ]
    return _f


# ---------------------------------------------------------------------------
# Time-varying external force
# ---------------------------------------------------------------------------

def time_varying_force(
    body_idx: int,
    force_fn: Callable[[float], Vec3],
    torque_fn: Optional[Callable[[float], Vec3]] = None,
) -> ForceField:
    """
    Force/torque given by callable ``force_fn(t)`` and optional ``torque_fn(t)``.
    """
    def _f(bodies: List[RigidBody], t: float) -> List[Tuple[Vec3, Vec3]]:
        result: List[Tuple[Vec3, Vec3]] = []
        for i in range(len(bodies)):
            if i == body_idx:
                fv = force_fn(t)
                tv = torque_fn(t) if torque_fn is not None else _ZERO3
                result.append((fv, tv))
            else:
                result.append((_ZERO3, _ZERO3))
        return result
    return _f


# ---------------------------------------------------------------------------
# Spring-damper between two points
# ---------------------------------------------------------------------------

def spring_damper(
    body_a_idx: int,
    body_b_idx: int,
    *,
    k: float,
    c: float,
    natural_length: float,
    attachment_a: Vec3 = (0.0, 0.0, 0.0),
    attachment_b: Vec3 = (0.0, 0.0, 0.0),
) -> ForceField:
    """
    Linear spring-damper connecting a point on body A to a point on body B.

    The force is  F = -(k δ + c δ̇) n̂  where:
      δ  = current length − natural_length
      δ̇  = rate of change of length (velocity along the spring axis)
      n̂  = unit vector from A attachment to B attachment

    ``attachment_a/b`` are offsets in the *body frames* of A and B.

    If body_b_idx is -1, body B is treated as a fixed world-frame anchor at
    the position  body_a.position + attachment_b.
    """
    def _get_world_point(body: RigidBody, local_pt: Vec3) -> Vec3:
        R = quat_to_rotmat(body.orientation)  # type: ignore[arg-type]
        rotated = mat3_vec(R, local_pt)
        return vec3_add(body.position, rotated)

    def _get_world_velocity_at_point(body: RigidBody, local_pt: Vec3) -> Vec3:
        R = quat_to_rotmat(body.orientation)  # type: ignore[arg-type]
        r_world = mat3_vec(R, local_pt)
        # v_point = v_com + ω × r_world
        omega = body.angular_velocity
        # Convert ω body→world:  ω_world = R ω_body
        omega_world = mat3_vec(R, omega)
        cross = (
            omega_world[1] * r_world[2] - omega_world[2] * r_world[1],
            omega_world[2] * r_world[0] - omega_world[0] * r_world[2],
            omega_world[0] * r_world[1] - omega_world[1] * r_world[0],
        )
        return vec3_add(body.velocity, cross)

    def _f(bodies: List[RigidBody], t: float) -> List[Tuple[Vec3, Vec3]]:
        n_bodies = len(bodies)
        result: List[Tuple[Vec3, Vec3]] = [(_ZERO3, _ZERO3)] * n_bodies

        body_a = bodies[body_a_idx]
        pa = _get_world_point(body_a, attachment_a)
        va = _get_world_velocity_at_point(body_a, attachment_a)

        if body_b_idx >= 0:
            body_b = bodies[body_b_idx]
            pb = _get_world_point(body_b, attachment_b)
            vb = _get_world_velocity_at_point(body_b, attachment_b)
        else:
            pb = attachment_b
            vb = _ZERO3

        diff = vec3_sub(pb, pa)
        length = vec3_norm(diff)
        if length < 1e-12:
            return result

        n_hat: Vec3 = (diff[0] / length, diff[1] / length, diff[2] / length)
        delta = length - natural_length
        rel_vel = vec3_sub(vb, va)
        delta_dot = vec3_dot(rel_vel, n_hat)

        # Scalar force magnitude (positive = attractive)
        F_mag = k * delta + c * delta_dot
        F_on_a: Vec3 = (n_hat[0] * F_mag, n_hat[1] * F_mag, n_hat[2] * F_mag)
        F_on_b: Vec3 = (-F_on_a[0], -F_on_a[1], -F_on_a[2])

        # Torque on A:  τ = r × F  (r = attachment_a in world frame)
        R_a = quat_to_rotmat(body_a.orientation)  # type: ignore[arg-type]
        r_a_world = mat3_vec(R_a, attachment_a)
        tau_a: Vec3 = (
            r_a_world[1] * F_on_a[2] - r_a_world[2] * F_on_a[1],
            r_a_world[2] * F_on_a[0] - r_a_world[0] * F_on_a[2],
            r_a_world[0] * F_on_a[1] - r_a_world[1] * F_on_a[0],
        )

        result_list = list(result)
        # Accumulate onto body_a
        fa_old, ta_old = result_list[body_a_idx]
        result_list[body_a_idx] = (
            vec3_add(fa_old, F_on_a),
            vec3_add(ta_old, tau_a),
        )

        if body_b_idx >= 0:
            body_b2 = bodies[body_b_idx]
            R_b = quat_to_rotmat(body_b2.orientation)  # type: ignore[arg-type]
            r_b_world = mat3_vec(R_b, attachment_b)
            tau_b: Vec3 = (
                r_b_world[1] * F_on_b[2] - r_b_world[2] * F_on_b[1],
                r_b_world[2] * F_on_b[0] - r_b_world[0] * F_on_b[2],
                r_b_world[0] * F_on_b[1] - r_b_world[1] * F_on_b[0],
            )
            fb_old, tb_old = result_list[body_b_idx]
            result_list[body_b_idx] = (
                vec3_add(fb_old, F_on_b),
                vec3_add(tb_old, tau_b),
            )

        return result_list

    return _f


# ---------------------------------------------------------------------------
# Torsional spring-damper (revolute joint torque)
# ---------------------------------------------------------------------------

def torsional_spring(
    body_idx: int,
    *,
    k_torsion: float,
    c_torsion: float = 0.0,
    rest_angle: float = 0.0,
    axis: Vec3 = (0.0, 0.0, 1.0),
) -> ForceField:
    """
    Torsional spring about ``axis`` acting on ``body_idx``.

    Torque = -(k_torsion * (θ - rest_angle) + c_torsion * ω_axis) · axis
    where θ is the current rotation about ``axis`` (from identity) and ω_axis
    is the component of angular velocity along the axis.

    NOTE: This is most accurate when axis is a principal body axis.
    """
    import math

    n = math.sqrt(axis[0]**2 + axis[1]**2 + axis[2]**2)
    ax: Vec3 = (axis[0] / n, axis[1] / n, axis[2] / n)

    def _f(bodies: List[RigidBody], t: float) -> List[Tuple[Vec3, Vec3]]:
        result: List[Tuple[Vec3, Vec3]] = [(_ZERO3, _ZERO3)] * len(bodies)
        b = bodies[body_idx]
        # Extract rotation angle about ax from quaternion
        q = b.orientation
        # θ = 2 * atan2( (q·ax), qw )  assuming small-angle or axis-aligned
        # More robustly: project quaternion onto the axis
        qw, qx, qy, qz = q  # type: ignore[misc]
        qv_dot_ax = qx * ax[0] + qy * ax[1] + qz * ax[2]
        theta = 2.0 * math.atan2(qv_dot_ax, qw)

        omega_body = b.angular_velocity
        omega_ax = omega_body[0] * ax[0] + omega_body[1] * ax[1] + omega_body[2] * ax[2]

        T_mag = -(k_torsion * (theta - rest_angle) + c_torsion * omega_ax)
        torque: Vec3 = (ax[0] * T_mag, ax[1] * T_mag, ax[2] * T_mag)

        result_list = list(result)
        result_list[body_idx] = (_ZERO3, torque)
        return result_list

    return _f
