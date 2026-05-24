"""
kerf_cad_core.mbd.solver — planar constrained rigid multibody dynamics solver.

Overview
--------
Implements a Lagrange-multiplier / index-3 DAE solver for planar (2-D)
rigid multibody systems with Baumgarte constraint stabilisation (or
coordinate-projection as a fallback).

State vector for N unconstrained bodies:
    q  = [x1, y1, θ1,  x2, y2, θ2,  ...  xN, yN, θN]          shape (3N,)
    qd = dq/dt                                                   shape (3N,)

Equations of motion with nc constraints:
    M · q̈  +  Φ_q^T · λ  =  Q(q, qd, t)        (Newton-Euler, 3N eqs)
    Φ(q, t) = 0                                  (constraint, nc eqs)

Augmented system (index-3 DAE):
    [M    Φ_q^T] [q̈ ]   [Q          ]
    [Φ_q   0   ] [λ  ] = [-Φ_tt - γ  ]

where γ = -Φ_qq qd² term (velocity-level).

Baumgarte stabilisation replaces the constraint RHS with:
    -Φ_tt - 2α Φ_t - β² Φ

so that constraint violation decays as a damped oscillator.

Integration uses a simple semi-implicit (Newmark-like) trapezoidal stepping
with iterative correction, or plain Euler as a bootstrap.

All public functions return plain dicts and NEVER raise; errors → {"ok": False}.

Author: imranparuk
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from kerf_cad_core._linalg import (
    matmul as _dot,
    matvec as _matvec,
    transpose as _transpose,
    vadd as _vecadd,
    vsub as _vecsub,
    vscale as _vecscale,
    vdot as _vecdot,
    vnorm as _vecnorm,
    zeros as _zeros,
    eye as _eye,
    lu_solve as _lu_solve,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Body:
    """
    A rigid body in the planar MBD system.

    Parameters
    ----------
    mass : float
        Mass in kg. Must be > 0.
    inertia : float
        Planar (scalar) moment of inertia about the body's centroid (kg·m²).
        Must be > 0.
    x0 : float
        Initial x-position of centroid (m).
    y0 : float
        Initial y-position of centroid (m).
    theta0 : float
        Initial orientation (rad).
    vx0 : float
        Initial x-velocity (m/s).
    vy0 : float
        Initial y-velocity (m/s).
    omega0 : float
        Initial angular velocity (rad/s).
    name : str
        Optional label for output.
    fixed : bool
        If True the body is a kinematic ground (DOF frozen).
    """
    mass: float
    inertia: float
    x0: float = 0.0
    y0: float = 0.0
    theta0: float = 0.0
    vx0: float = 0.0
    vy0: float = 0.0
    omega0: float = 0.0
    name: str = ""
    fixed: bool = False

    # Runtime index assigned by MBDSystem
    _idx: int = field(default=-1, repr=False)


@dataclass
class RevoluteJoint:
    """
    Revolute (pin) joint — 2 translational constraints, allows rotation.

    Connects point sP (body-frame offset from centroid of body_i) to
    point sQ (body-frame offset from centroid of body_j) so that the
    world-frame positions of those points coincide.

    If body_j is None the joint pins to the global frame (ground).

    Parameters
    ----------
    body_i : int | Body
        Index or Body object for body i.
    body_j : int | Body | None
        Index or Body object for body j (None = ground).
    s_i : tuple[float, float]
        Body-frame position of joint point on body i (metres).
    s_j : tuple[float, float]
        Body-frame position of joint point on body j (metres from j's centroid,
        or world coordinates if body_j is None).
    """
    body_i: Any
    body_j: Any  # None for ground
    s_i: tuple = (0.0, 0.0)
    s_j: tuple = (0.0, 0.0)

    @property
    def n_constraints(self) -> int:
        return 2


@dataclass
class PrismaticJoint:
    """
    Prismatic (sliding) joint — 1 translational + 1 rotational constraint.

    Body j slides along the axis defined by `axis_angle_rad` (in global
    coordinates) relative to body i.  If body_j is None the joint slides
    along a fixed global direction.

    Parameters
    ----------
    body_i : int | Body
        Slider body.
    body_j : int | Body | None
        Guide body (None = ground).
    axis_angle_rad : float
        Angle of slide axis with respect to global x-axis (radians).
    s_i : tuple[float, float]
        Attachment point offset on body i (body frame).
    s_j : tuple[float, float]
        Attachment point offset on body j / world reference point.
    """
    body_i: Any
    body_j: Any
    axis_angle_rad: float = 0.0
    s_i: tuple = (0.0, 0.0)
    s_j: tuple = (0.0, 0.0)

    @property
    def n_constraints(self) -> int:
        return 2


@dataclass
class FixedJoint:
    """
    Fixed (weld) joint — 3 DOF removed: Δx=0, Δy=0, Δθ=0.

    Parameters
    ----------
    body_i : int | Body
    body_j : int | Body | None
        None = ground.
    s_i : tuple[float, float]
    s_j : tuple[float, float]
    """
    body_i: Any
    body_j: Any
    s_i: tuple = (0.0, 0.0)
    s_j: tuple = (0.0, 0.0)

    @property
    def n_constraints(self) -> int:
        return 3


@dataclass
class DistanceJoint:
    """
    Distance constraint — keeps |rP - rQ| == d.

    1 constraint (scalar distance equation).

    Parameters
    ----------
    body_i : int | Body
    body_j : int | Body | None
    s_i : tuple[float, float]
    s_j : tuple[float, float]
    distance : float
        Required distance (m).
    """
    body_i: Any
    body_j: Any
    s_i: tuple = (0.0, 0.0)
    s_j: tuple = (0.0, 0.0)
    distance: float = 1.0

    @property
    def n_constraints(self) -> int:
        return 1


@dataclass
class SpringDamper:
    """
    Linear spring-damper element (applied force, not a constraint).

    Parameters
    ----------
    body_i, body_j : int | Body
        Bodies connected by the spring.
    s_i, s_j : tuple[float, float]
        Attachment offsets in body frames.
    k : float
        Spring stiffness (N/m).
    c : float
        Viscous damping coefficient (N·s/m). Default 0.
    L0 : float
        Natural (unstretched) length (m). Default 0.
    """
    body_i: Any
    body_j: Any
    s_i: tuple = (0.0, 0.0)
    s_j: tuple = (0.0, 0.0)
    k: float = 0.0
    c: float = 0.0
    L0: float = 0.0


@dataclass
class GravityForce:
    """
    Constant gravitational acceleration applied to all non-fixed bodies.

    Parameters
    ----------
    gx, gy : float
        Gravity components (m/s²). Default (0, -9.80665).
    """
    gx: float = 0.0
    gy: float = -9.80665


@dataclass
class AppliedForce:
    """
    Constant or time-invariant force applied at a point on a body.

    Parameters
    ----------
    body : int | Body
    s : tuple[float, float]
        Application point in body frame.
    fx, fy : float
        Force components in global frame (N).
    """
    body: Any
    s: tuple = (0.0, 0.0)
    fx: float = 0.0
    fy: float = 0.0


@dataclass
class AppliedTorque:
    """
    Constant torque applied to a body.

    Parameters
    ----------
    body : int | Body
    torque : float
        Torque (N·m), positive counter-clockwise.
    """
    body: Any
    torque: float = 0.0


# ---------------------------------------------------------------------------
# MBD System
# ---------------------------------------------------------------------------

class MBDSystem:
    """
    Container for a planar multibody system.

    Usage
    -----
        sys = MBDSystem()
        b0 = sys.add_body(Body(mass=1.0, inertia=0.01, fixed=True))
        b1 = sys.add_body(Body(mass=1.0, inertia=0.01, x0=0, y0=-1.0))
        sys.add_joint(RevoluteJoint(b0, None, s_i=(0, 0), s_j=(0, 0)))
        sys.add_joint(RevoluteJoint(b0, b1, s_i=(0, 0), s_j=(0, 1.0)))
        sys.add_force(GravityForce())
        result = simulate(sys, t_end=5.0, dt=0.001)
    """

    def __init__(self) -> None:
        self.bodies: list[Body] = []
        self.joints: list = []
        self.forces: list = []

    def add_body(self, body: Body) -> int:
        """Add a body; return its integer index."""
        idx = len(self.bodies)
        body._idx = idx
        self.bodies.append(body)
        return idx

    def add_joint(self, joint) -> None:
        self.joints.append(joint)

    def add_force(self, force) -> None:
        self.forces.append(force)

    def _body_index(self, ref) -> int:
        if ref is None:
            return -1
        if isinstance(ref, int):
            return ref
        if isinstance(ref, Body):
            return ref._idx
        return int(ref)

    # ── coordinate helpers ────────────────────────────────────────────────

    def _q_size(self) -> int:
        return 3 * len(self.bodies)

    def _init_state(self):
        """Return initial (q, qd) vectors."""
        q = _zeros(self._q_size())
        qd = _zeros(self._q_size())
        for i, b in enumerate(self.bodies):
            q[3*i]   = b.x0
            q[3*i+1] = b.y0
            q[3*i+2] = b.theta0
            qd[3*i]   = b.vx0
            qd[3*i+1] = b.vy0
            qd[3*i+2] = b.omega0
        return q, qd

    def _world_point(self, q: list[float], body_idx: int, s_body: tuple) -> tuple[float, float]:
        """World position of body-frame point s_body on body body_idx."""
        if body_idx < 0:
            # Ground: s_body is already in world frame
            return float(s_body[0]), float(s_body[1])
        xi = q[3*body_idx]
        yi = q[3*body_idx + 1]
        ti = q[3*body_idx + 2]
        ct, st = math.cos(ti), math.sin(ti)
        sx, sy = float(s_body[0]), float(s_body[1])
        return xi + ct*sx - st*sy, yi + st*sx + ct*sy

    def _world_vel(self, q: list[float], qd: list[float],
                   body_idx: int, s_body: tuple) -> tuple[float, float]:
        """World velocity of body-frame point s_body."""
        if body_idx < 0:
            return 0.0, 0.0
        vx = qd[3*body_idx]
        vy = qd[3*body_idx + 1]
        om = qd[3*body_idx + 2]
        ti = q[3*body_idx + 2]
        ct, st = math.cos(ti), math.sin(ti)
        sx, sy = float(s_body[0]), float(s_body[1])
        # d/dt (R·s) = ω × (R·s)  (2-D: ω in z-direction)
        rs_x =  ct*sx - st*sy
        rs_y =  st*sx + ct*sy
        return vx - om*rs_y, vy + om*rs_x

    # ── mass matrix ──────────────────────────────────────────────────────

    def _mass_matrix(self) -> list[list[float]]:
        n = self._q_size()
        M = [[0.0] * n for _ in range(n)]
        for i, b in enumerate(self.bodies):
            if b.fixed:
                M[3*i][3*i] = 1.0      # placeholder; rows will be zeroed in augmented
                M[3*i+1][3*i+1] = 1.0
                M[3*i+2][3*i+2] = 1.0
            else:
                M[3*i][3*i]     = b.mass
                M[3*i+1][3*i+1] = b.mass
                M[3*i+2][3*i+2] = b.inertia
        return M

    # ── applied forces ────────────────────────────────────────────────────

    def _generalized_forces(self, q: list[float], qd: list[float]) -> list[float]:
        n = self._q_size()
        Q = _zeros(n)

        for force in self.forces:
            if isinstance(force, GravityForce):
                for i, b in enumerate(self.bodies):
                    if b.fixed:
                        continue
                    Q[3*i]   += b.mass * force.gx
                    Q[3*i+1] += b.mass * force.gy

            elif isinstance(force, AppliedForce):
                bi = self._body_index(force.body)
                b = self.bodies[bi]
                if b.fixed:
                    continue
                ti = q[3*bi + 2]
                ct, st = math.cos(ti), math.sin(ti)
                sx, sy = float(force.s[0]), float(force.s[1])
                rs_x = ct*sx - st*sy
                rs_y = st*sx + ct*sy
                Q[3*bi]     += force.fx
                Q[3*bi + 1] += force.fy
                # Torque from offset force: τ = r × F (z-component)
                Q[3*bi + 2] += rs_x * force.fy - rs_y * force.fx

            elif isinstance(force, AppliedTorque):
                bi = self._body_index(force.body)
                if self.bodies[bi].fixed:
                    continue
                Q[3*bi + 2] += force.torque

            elif isinstance(force, SpringDamper):
                bi = self._body_index(force.body_i)
                bj = self._body_index(force.body_j)
                Pi = self._world_point(q, bi, force.s_i)
                Pj = self._world_point(q, bj, force.s_j)
                dx = Pj[0] - Pi[0]
                dy = Pj[1] - Pi[1]
                L  = math.sqrt(dx*dx + dy*dy)
                if L < 1e-14:
                    continue
                ux, uy = dx / L, dy / L  # unit vector i→j
                Vi = self._world_vel(q, qd, bi, force.s_i)
                Vj = self._world_vel(q, qd, bj, force.s_j)
                Ldot = (Vj[0]-Vi[0])*ux + (Vj[1]-Vi[1])*uy
                Fmag = force.k * (L - force.L0) + force.c * Ldot
                # Force on i in direction of unit vector
                fx_i =  Fmag * ux
                fy_i =  Fmag * uy
                if bi >= 0 and not self.bodies[bi].fixed:
                    ti = q[3*bi + 2]
                    ct, st = math.cos(ti), math.sin(ti)
                    sx, sy = float(force.s_i[0]), float(force.s_i[1])
                    rs_x = ct*sx - st*sy
                    rs_y = st*sx + ct*sy
                    Q[3*bi]     += fx_i
                    Q[3*bi + 1] += fy_i
                    Q[3*bi + 2] += rs_x * fy_i - rs_y * fx_i
                if bj >= 0 and not self.bodies[bj].fixed:
                    tj = q[3*bj + 2]
                    ct, st = math.cos(tj), math.sin(tj)
                    sx, sy = float(force.s_j[0]), float(force.s_j[1])
                    rs_x = ct*sx - st*sy
                    rs_y = st*sx + ct*sy
                    Q[3*bj]     -= fx_i
                    Q[3*bj + 1] -= fy_i
                    Q[3*bj + 2] -= (rs_x * (-fy_i) - rs_y * (-fx_i))

        return Q

    # ── constraints ──────────────────────────────────────────────────────

    def _n_constraints(self) -> int:
        nc = 0
        for j in self.joints:
            nc += j.n_constraints
        # Fixed bodies: 3 DOF each clamped
        for b in self.bodies:
            if b.fixed:
                nc += 3
        return nc

    def _constraint_vector(self, q: list[float], t: float,
                           alpha_b: float = 0.0, beta_b: float = 0.0,
                           Phi0: list[float] | None = None,
                           Phid0: list[float] | None = None) -> list[float]:
        """
        Compute Φ(q, t).  Baumgarte terms are folded in when alpha_b/beta_b != 0.
        Phi0 / Phid0 are Φ and Φ_t at the previous step for Baumgarte.
        """
        Phi = []

        for j in self.joints:
            bi = self._body_index(j.body_i)
            bj = self._body_index(j.body_j)
            Pi = self._world_point(q, bi, j.s_i)
            Pj = self._world_point(q, bj, j.s_j)

            if isinstance(j, RevoluteJoint):
                Phi.append(Pi[0] - Pj[0])
                Phi.append(Pi[1] - Pj[1])

            elif isinstance(j, PrismaticJoint):
                # Constraint 1: relative displacement perpendicular to axis = 0
                ax = math.cos(j.axis_angle_rad)
                ay = math.sin(j.axis_angle_rad)
                nx, ny = -ay, ax   # normal to axis
                dx = Pi[0] - Pj[0]
                dy = Pi[1] - Pj[1]
                Phi.append(dx*nx + dy*ny)
                # Constraint 2: relative angle = 0
                theta_i = q[3*bi + 2] if bi >= 0 else 0.0
                theta_j = q[3*bj + 2] if bj >= 0 else 0.0
                Phi.append(theta_i - theta_j - j.axis_angle_rad)

            elif isinstance(j, FixedJoint):
                Phi.append(Pi[0] - Pj[0])
                Phi.append(Pi[1] - Pj[1])
                theta_i = q[3*bi + 2] if bi >= 0 else 0.0
                theta_j = q[3*bj + 2] if bj >= 0 else 0.0
                Phi.append(theta_i - theta_j)

            elif isinstance(j, DistanceJoint):
                dx = Pi[0] - Pj[0]
                dy = Pi[1] - Pj[1]
                Phi.append(dx*dx + dy*dy - j.distance**2)

        # Fixed bodies
        for b in self.bodies:
            if b.fixed:
                i = b._idx
                Phi.append(q[3*i]   - b.x0)
                Phi.append(q[3*i+1] - b.y0)
                Phi.append(q[3*i+2] - b.theta0)

        return Phi

    def _constraint_jacobian(self, q: list[float]) -> list[list[float]]:
        """Compute Φ_q  (nc × 3N) Jacobian via finite differences."""
        nq = self._q_size()
        nc = self._n_constraints()
        Phi0 = self._constraint_vector(q, 0.0)
        h = 1e-7
        J = [[0.0] * nq for _ in range(nc)]
        for k in range(nq):
            qp = q[:]
            qp[k] += h
            Phip = self._constraint_vector(qp, 0.0)
            for row in range(nc):
                J[row][k] = (Phip[row] - Phi0[row]) / h
        return J

    def _constraint_velocity_rhs(self, q: list[float], qd: list[float]) -> list[float]:
        """
        Compute the velocity-level RHS: -d(Φ)/dt = Φ_q · qd.
        This is the negative of the time derivative of constraints at given q.
        For time-independent constraints Φ_t = 0.
        Returns -Φ_q · qd  (should = 0 when constraints satisfied at vel level).
        """
        J = self._constraint_jacobian(q)
        Jqd = _matvec(J, qd)
        return [-v for v in Jqd]

    def _gamma(self, q: list[float], qd: list[float]) -> list[float]:
        """
        Acceleration-level RHS term γ = -d²Φ/dt² + Φ_q·q̈
        For time-independent constraints: γ = -(Φ_q qd)_q qd = -d/dt(Φ_q)·qd
        Approximated via finite difference on Φ_q.
        """
        nc = self._n_constraints()
        h = 1e-7
        J0 = self._constraint_jacobian(q)
        # Perturb q slightly forward to get dJ/dt ≈ (J(q+h·qd) - J(q)) / h
        qp = _vecadd(q, _vecscale(h, qd))
        J1 = self._constraint_jacobian(qp)
        Jdot = [[(J1[i][k] - J0[i][k]) / h for k in range(len(q))] for i in range(nc)]
        # γ = -Jdot · qd
        gamma = _matvec(Jdot, qd)
        return [-v for v in gamma]

    # ── augmented system solve ─────────────────────────────────────────────

    def _solve_accelerations(self, q: list[float], qd: list[float],
                              alpha_b: float, beta_b: float) -> tuple[list[float], list[float]]:
        """
        Solve the augmented EOM for (qdd, lambda).

        [M    J^T] [qdd]   [Q    ]
        [J    0  ] [lam] = [gamma - 2α(Φ_t+J·qd) - β²·Φ]

        Returns (qdd, lambda).  On failure returns zero accelerations.
        """
        nq = self._q_size()
        nc = self._n_constraints()
        M  = self._mass_matrix()
        Q  = self._generalized_forces(q, qd)

        # Unconstrained case: just M qdd = Q
        if nc == 0:
            sol = _lu_solve(M, Q)
            if sol is None:
                return _zeros(nq), []
            qdd = sol
            for b in self.bodies:
                if b.fixed:
                    i = b._idx
                    qdd[3*i]   = 0.0
                    qdd[3*i+1] = 0.0
                    qdd[3*i+2] = 0.0
            return qdd, []

        J  = self._constraint_jacobian(q)
        JT = _transpose(J)
        gamma = self._gamma(q, qd)

        # Baumgarte stabilisation: replace gamma with
        # gamma - 2α·(J·qd) - β²·Φ
        Phi = self._constraint_vector(q, 0.0)
        Jqd = _matvec(J, qd)
        rhs_c = [gamma[i] - 2*alpha_b*Jqd[i] - beta_b**2*Phi[i] for i in range(nc)]

        # Build augmented matrix (nq+nc) × (nq+nc)
        ntot = nq + nc
        A = [[0.0] * ntot for _ in range(ntot)]
        for i in range(nq):
            for k in range(nq):
                A[i][k] = M[i][k]
        for i in range(nq):
            for j in range(nc):
                A[i][nq + j] = JT[i][j]
        for i in range(nc):
            for k in range(nq):
                A[nq + i][k] = J[i][k]

        rhs = Q + rhs_c

        sol = _lu_solve(A, rhs)
        if sol is None:
            return _zeros(nq), _zeros(nc)

        qdd = sol[:nq]
        lam  = sol[nq:]

        # Zero out acceleration for fixed bodies (set by constraint rows, but
        # mass-matrix row uses placeholder 1 → override to 0)
        for b in self.bodies:
            if b.fixed:
                i = b._idx
                qdd[3*i]   = 0.0
                qdd[3*i+1] = 0.0
                qdd[3*i+2] = 0.0

        return qdd, lam

    # ── energy ────────────────────────────────────────────────────────────

    def _kinetic_energy(self, q: list[float], qd: list[float]) -> float:
        T = 0.0
        for i, b in enumerate(self.bodies):
            if b.fixed:
                continue
            vx = qd[3*i]
            vy = qd[3*i + 1]
            om = qd[3*i + 2]
            T += 0.5 * b.mass * (vx**2 + vy**2) + 0.5 * b.inertia * om**2
        return T

    def _potential_energy(self, q: list[float]) -> float:
        """Gravitational + spring potential energy."""
        V = 0.0
        # Gravity
        gx, gy = 0.0, 0.0
        for force in self.forces:
            if isinstance(force, GravityForce):
                gx += force.gx
                gy += force.gy
        for i, b in enumerate(self.bodies):
            if b.fixed:
                continue
            V -= b.mass * (gx * q[3*i] + gy * q[3*i+1])

        # Springs
        for force in self.forces:
            if isinstance(force, SpringDamper):
                bi = self._body_index(force.body_i)
                bj = self._body_index(force.body_j)
                Pi = self._world_point(q, bi, force.s_i)
                Pj = self._world_point(q, bj, force.s_j)
                dx = Pj[0] - Pi[0]
                dy = Pj[1] - Pi[1]
                L  = math.sqrt(dx*dx + dy*dy)
                ext = L - force.L0
                V += 0.5 * force.k * ext**2
        return V

    def _joint_reaction_forces(self, q: list[float], qd: list[float],
                                lam: list[float]) -> list[dict]:
        """Convert Lagrange multipliers to physical reaction forces."""
        reactions = []
        if not lam:
            # No constraints → no reactions
            return reactions

        J  = self._constraint_jacobian(q)
        JT = _transpose(J)

        row = 0
        for j in self.joints:
            nc_j = j.n_constraints
            bi = self._body_index(j.body_i)
            lam_j = lam[row: row + nc_j] if row + nc_j <= len(lam) else []
            # Force on body i from joint = J_i^T · lam_j  (2-body contribution)
            # For a revolute joint the first two Lagrange multipliers are forces
            fx, fy = (lam_j[0], lam_j[1]) if len(lam_j) >= 2 else (0.0, 0.0)
            reactions.append({
                "joint_type": type(j).__name__,
                "body_i": bi,
                "body_j": self._body_index(j.body_j),
                "lambda": lam_j,
                "Fx": fx,
                "Fy": fy,
            })
            row += nc_j

        return reactions


# ---------------------------------------------------------------------------
# Public simulation function
# ---------------------------------------------------------------------------

def simulate(
    system: MBDSystem,
    t_end: float,
    dt: float,
    *,
    alpha_baumgarte: float = 5.0,
    beta_baumgarte: float = 5.0,
    max_steps: int | None = None,
    store_every: int = 1,
) -> dict:
    """
    Integrate the planar MBD system over [0, t_end] using fixed step dt.

    Uses a 2nd-order trapezoidal (Newmark-like) integration with
    Baumgarte constraint stabilisation to prevent drift in the index-3 DAE.

    Parameters
    ----------
    system : MBDSystem
        Assembled multibody system.
    t_end : float
        End time (s).
    dt : float
        Fixed time step (s). Smaller → more accurate but slower.
    alpha_baumgarte : float
        Baumgarte stabilisation parameter α (critical ≈ 5–10 for dt≈1e-3).
    beta_baumgarte : float
        Baumgarte stabilisation parameter β (same magnitude as α).
    max_steps : int | None
        Safety limit on number of steps; None = no limit.
    store_every : int
        Store trajectory data every this many steps (reduce memory for long runs).

    Returns
    -------
    dict
        ok        : bool
        t         : list[float]                  — time stamps
        q         : list[list[float]]            — generalised coordinates at each t
        qd        : list[list[float]]            — generalised velocities at each t
        energy    : list[dict]                   — {t, T, V, E} kinetic/potential/total
        reactions : list[dict]                   — reaction forces at final step
        n_steps   : int
        reason    : str  (only on failure)
    """
    try:
        return _simulate_inner(system, t_end, dt,
                               alpha_baumgarte=alpha_baumgarte,
                               beta_baumgarte=beta_baumgarte,
                               max_steps=max_steps,
                               store_every=store_every)
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def _simulate_inner(
    system: MBDSystem,
    t_end: float,
    dt: float,
    *,
    alpha_baumgarte: float,
    beta_baumgarte: float,
    max_steps: int | None,
    store_every: int,
) -> dict:
    if t_end <= 0:
        return {"ok": False, "reason": "t_end must be > 0"}
    if dt <= 0:
        return {"ok": False, "reason": "dt must be > 0"}
    if not system.bodies:
        return {"ok": False, "reason": "system has no bodies"}

    for b in system.bodies:
        if b.mass <= 0 and not b.fixed:
            return {"ok": False, "reason": f"body '{b.name}' has non-positive mass {b.mass}"}
        if b.inertia <= 0 and not b.fixed:
            return {"ok": False, "reason": f"body '{b.name}' has non-positive inertia {b.inertia}"}

    q, qd = system._init_state()
    t = 0.0

    n_steps_total = int(math.ceil(t_end / dt))
    if max_steps is not None:
        n_steps_total = min(n_steps_total, max_steps)

    ts: list[float] = []
    qs: list[list[float]] = []
    qds: list[list[float]] = []
    energies: list[dict] = []

    def _store(t_, q_, qd_):
        ts.append(t_)
        qs.append(q_[:])
        qds.append(qd_[:])
        T = system._kinetic_energy(q_, qd_)
        V = system._potential_energy(q_)
        energies.append({"t": t_, "T": T, "V": V, "E": T + V})

    _store(0.0, q, qd)

    qdd, lam = system._solve_accelerations(q, qd, alpha_baumgarte, beta_baumgarte)

    step_count = 0
    for step in range(1, n_steps_total + 1):
        # Prediction (explicit Euler)
        q_pred  = _vecadd(q,  _vecscale(dt, qd))
        q_pred  = _vecadd(q_pred, _vecscale(0.5 * dt * dt, qdd))
        qd_pred = _vecadd(qd, _vecscale(dt, qdd))

        # Correction: solve at predicted state
        qdd_new, lam = system._solve_accelerations(q_pred, qd_pred,
                                                   alpha_baumgarte, beta_baumgarte)

        # Corrected update (trapezoidal velocity, position from midpoint accel)
        qd_new = _vecadd(qd, _vecscale(0.5 * dt, _vecadd(qdd, qdd_new)))
        q_new  = _vecadd(q,  _vecscale(0.5 * dt, _vecadd(qd, qd_new)))

        # Coordinate projection for constraint positions
        # Try up to 3 Newton iterations to satisfy Φ(q) = 0
        if system._n_constraints() > 0:
            for _ in range(3):
                Phi = system._constraint_vector(q_new, t + dt)
                if _vecnorm(Phi) < 1e-10:
                    break
                J = system._constraint_jacobian(q_new)
                JT = _transpose(J)
                M  = system._mass_matrix()
                # Projection: Δq = -M^{-1} J^T (J M^{-1} J^T)^{-1} Φ
                # Build J M^{-1} J^T  (nc × nc)
                nq = len(q_new)
                nc = len(Phi)
                if nc == 0:
                    break
                Minv_JT = [[0.0] * nc for _ in range(nq)]
                for row_i in range(nq):
                    m_inv = 1.0 / M[row_i][row_i] if abs(M[row_i][row_i]) > 1e-14 else 0.0
                    for col in range(nc):
                        Minv_JT[row_i][col] = m_inv * JT[row_i][col]
                JMJT = _dot(J, Minv_JT)
                delta_lam = _lu_solve(JMJT, [-v for v in Phi])
                if delta_lam is None:
                    break
                dq = _matvec(Minv_JT, delta_lam)
                q_new = _vecadd(q_new, dq)

        q   = q_new
        qd  = qd_new
        qdd = qdd_new
        t  += dt
        step_count += 1

        if step % store_every == 0 or step == n_steps_total:
            _store(t, q, qd)

    _, final_lam = system._solve_accelerations(q, qd, alpha_baumgarte, beta_baumgarte)
    reactions = system._joint_reaction_forces(q, qd, final_lam)

    return {
        "ok": True,
        "t": ts,
        "q": qs,
        "qd": qds,
        "energy": energies,
        "reactions": reactions,
        "n_steps": step_count,
    }


# ---------------------------------------------------------------------------
# LLM tool-layer (registered via @register in tools.py — see mbd/tools.py)
# ---------------------------------------------------------------------------
# The solver itself is purely computational.  Tool wrappers are in a sibling
# tools.py file following the kerf pattern so this module has no registry
# dependency.
