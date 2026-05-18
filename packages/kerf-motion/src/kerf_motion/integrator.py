"""
kerf_motion.integrator
======================
Numerical integration for multibody dynamics.

Public API
----------
rk4_step(state, derivs_fn, dt)
    Single RK4 advance.

simulate(bodies, joints, forces, dt, n_steps)
    Simulate a multibody system and return per-body trajectories.

Design notes
------------
State layout per body: 13 floats
    [px, py, pz, vx, vy, vz, qw, qx, qy, qz, wx, wy, wz]

The global state vector concatenates all body states: 13 * n_bodies floats.

After each RK4 step the quaternion of every body is re-normalised to prevent
drift.

All pure Python.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from kerf_motion.body import RigidBody, Vec3, quat_normalize, vec3_add


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

State = List[float]
DerivsFn = Callable[[State, float], State]


# ---------------------------------------------------------------------------
# Generic RK4 step (works on any flat state vector)
# ---------------------------------------------------------------------------

def rk4_step(state: State, derivs_fn: DerivsFn, dt: float) -> State:
    """
    Classic 4th-order Runge-Kutta step.

    Parameters
    ----------
    state     : current state vector  x(t)
    derivs_fn : callable  f(x, t) → ẋ   (time-derivative of state)
    dt        : time step (s)

    Returns
    -------
    new_state : x(t + dt)

    Butcher tableau:
        c = [0, 1/2, 1/2, 1]
        k1 = f(x,           t)
        k2 = f(x + dt/2 k1, t + dt/2)
        k3 = f(x + dt/2 k2, t + dt/2)
        k4 = f(x + dt   k3, t + dt)
        x_new = x + dt/6 (k1 + 2k2 + 2k3 + k4)
    """
    n = len(state)
    k1 = derivs_fn(state, 0.0)

    s2 = [state[i] + 0.5 * dt * k1[i] for i in range(n)]
    k2 = derivs_fn(s2, 0.0)

    s3 = [state[i] + 0.5 * dt * k2[i] for i in range(n)]
    k3 = derivs_fn(s3, 0.0)

    s4 = [state[i] + dt * k3[i] for i in range(n)]
    k4 = derivs_fn(s4, 0.0)

    new_state = [
        state[i] + dt / 6.0 * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])
        for i in range(n)
    ]
    return new_state


# ---------------------------------------------------------------------------
# Multibody-aware helpers
# ---------------------------------------------------------------------------

_BODY_STATE_LEN = 13  # floats per body


def _pack_state(bodies: List[RigidBody]) -> State:
    state: State = []
    for b in bodies:
        state.extend(b.to_state())
    return state


def _unpack_state(bodies_template: List[RigidBody], state: State) -> List[RigidBody]:
    n = len(bodies_template)
    assert len(state) == n * _BODY_STATE_LEN
    result = []
    for i, b in enumerate(bodies_template):
        s = state[i * _BODY_STATE_LEN: (i + 1) * _BODY_STATE_LEN]
        result.append(RigidBody.from_state(b, s))
    return result


def _renormalize_quaternions(state: State, n_bodies: int) -> State:
    """Re-normalise all quaternion blocks in place (returns a new list)."""
    s = list(state)
    for i in range(n_bodies):
        base = i * _BODY_STATE_LEN + 6  # qw,qx,qy,qz start
        q = (s[base], s[base + 1], s[base + 2], s[base + 3])
        qn = quat_normalize(q)
        s[base], s[base + 1], s[base + 2], s[base + 3] = qn
    return s


def _build_derivs_fn(
    bodies_template: List[RigidBody],
    force_fields: list,
    t_offset: float = 0.0,
) -> DerivsFn:
    """
    Construct a stateless derivatives function for the RK4 integrator.

    ``force_fields`` is a list of callables  f(bodies, t) → [(force, torque), …]
    """

    def _derivs(state: State, dummy_t: float) -> State:
        t = t_offset
        bodies = _unpack_state(bodies_template, state)
        n = len(bodies)

        # Accumulate forces/torques
        forces: List[Vec3] = [(0.0, 0.0, 0.0)] * n
        torques: List[Vec3] = [(0.0, 0.0, 0.0)] * n

        for ff in force_fields:
            contributions = ff(bodies, t)
            for i, (fv, tv) in enumerate(contributions):
                forces[i] = (
                    forces[i][0] + fv[0],
                    forces[i][1] + fv[1],
                    forces[i][2] + fv[2],
                )
                torques[i] = (
                    torques[i][0] + tv[0],
                    torques[i][1] + tv[1],
                    torques[i][2] + tv[2],
                )

        # Compute state derivatives
        derivs: State = []
        for i, b in enumerate(bodies):
            d = b.state_derivatives(forces[i], torques[i])
            derivs.extend(d)

        return derivs

    return _derivs


# ---------------------------------------------------------------------------
# Trajectory snapshot
# ---------------------------------------------------------------------------

class BodySnapshot:
    """Lightweight snapshot of a single body at one time step."""
    __slots__ = ("t", "position", "velocity", "orientation", "angular_velocity")

    def __init__(self, t: float, body: RigidBody):
        self.t: float = t
        self.position: Vec3 = body.position
        self.velocity: Vec3 = body.velocity
        self.orientation = body.orientation
        self.angular_velocity: Vec3 = body.angular_velocity


# ---------------------------------------------------------------------------
# Main simulate() function
# ---------------------------------------------------------------------------

def simulate(
    bodies: List[RigidBody],
    joints: list,
    forces: list,
    dt: float,
    n_steps: int,
    *,
    record_every: int = 1,
    t_start: float = 0.0,
) -> Dict[str, Any]:
    """
    Simulate a multibody system using 4th-order Runge-Kutta integration.

    Parameters
    ----------
    bodies      : list of RigidBody (initial conditions)
    joints      : list of Joint objects (for kinematic FK; not used in free-flight)
    forces      : list of ForceField callables  f(bodies, t) → [(F, τ), …]
    dt          : time step (s)
    n_steps     : number of integration steps
    record_every: record a snapshot every N steps (default = 1, every step)
    t_start     : simulation start time (default = 0.0)

    Returns
    -------
    dict with keys:
        "ok"           : bool
        "t"            : list of recorded times
        "trajectories" : list of lists — trajectories[body_idx][step_idx] = BodySnapshot
        "final_bodies" : list of RigidBody (final state)
        "n_steps"      : total steps taken
        "dt"           : time step used
    """
    if not bodies:
        return {"ok": False, "reason": "no bodies provided"}
    if dt <= 0:
        return {"ok": False, "reason": f"dt must be positive, got {dt}"}
    if n_steps <= 0:
        return {"ok": False, "reason": f"n_steps must be positive, got {n_steps}"}

    n_bodies = len(bodies)
    state = _pack_state(bodies)

    # Pre-allocate trajectory lists
    trajectories: List[List[BodySnapshot]] = [[] for _ in range(n_bodies)]
    times: List[float] = []

    current_bodies = list(bodies)

    # Record initial state (step 0)
    times.append(t_start)
    for i, b in enumerate(current_bodies):
        trajectories[i].append(BodySnapshot(t_start, b))

    for step in range(n_steps):
        t_curr = t_start + step * dt
        derivs_fn = _build_derivs_fn(current_bodies, forces, t_offset=t_curr)
        state = rk4_step(state, derivs_fn, dt)
        state = _renormalize_quaternions(state, n_bodies)
        current_bodies = _unpack_state(bodies, state)

        t_new = t_start + (step + 1) * dt

        if (step + 1) % record_every == 0:
            times.append(t_new)
            for i, b in enumerate(current_bodies):
                trajectories[i].append(BodySnapshot(t_new, b))

    return {
        "ok": True,
        "t": times,
        "trajectories": trajectories,
        "final_bodies": current_bodies,
        "n_steps": n_steps,
        "dt": dt,
    }
