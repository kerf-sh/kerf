"""
kerf_textiles.mass_spring
=========================
Explicit-Euler mass-spring cloth solver.

Architecture
------------
ClothMesh  — holds particle positions, velocities, masses, and spring
             topology (structural / shear / bend).

solve_step — single time-step using semi-implicit Euler (symplectic):
               1. Accumulate spring + gravity forces (Hooke only, no
                  spring-axis velocity damping — that term is numerically
                  unstable in explicit integration).
               2. Integrate velocity: v += (F/m) * dt.
               3. Damp velocity globally: v *= velocity_damping.
               4. Integrate position: x += v * dt.
               5. Resolve collisions (projection + velocity kill).

             Auto-substep: the caller may pass any dt; the function
             automatically splits it into stable sub-steps based on the
             maximum spring stiffness.

Springs
-------
Structural springs  connect adjacent grid neighbours (N/S/E/W — 1 cell).
Shear springs       connect diagonal neighbours (NE/NW/SE/SW — √2 cells).
Bend springs        connect second neighbours (2 cells) to resist folding.

Each spring has a rest-length and a stiffness k only.  Energy dissipation
is handled by the per-step *velocity_damping* multiplier passed to
solve_step, not by spring-axis velocity forces.

Stability
---------
Explicit Euler on a spring-mass system is stable when

    dt_sub ≤ C * sqrt(m_min / k_max)

where C < 2 (theoretical) but we use C = 0.2 as a conservative safety
factor for the coupled 2-D lattice.  solve_step computes this automatically
and takes as many sub-steps as required.

Collision
---------
Sphere and horizontal-plane primitives.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Vec3 helpers (pure Python — no numpy required)
# ---------------------------------------------------------------------------

Vec3 = tuple[float, float, float]


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _normalize(a: Vec3) -> Vec3:
    n = _norm(a)
    if n < 1e-15:
        return (0.0, 0.0, 0.0)
    return _scale(a, 1.0 / n)


# ---------------------------------------------------------------------------
# Spring definition
# ---------------------------------------------------------------------------

@dataclass
class Spring:
    """A spring connecting two particle indices (Hooke stiffness only)."""
    i: int
    j: int
    rest_length: float
    stiffness: float = 100.0


# ---------------------------------------------------------------------------
# ClothMesh
# ---------------------------------------------------------------------------

@dataclass
class ClothMesh:
    """
    Grid cloth mesh with particle positions, velocities, and spring topology.

    Parameters
    ----------
    rows, cols : int
        Particle grid dimensions.
    spacing : float
        Rest distance between adjacent particles (metres).
    mass : float
        Per-particle mass (kg).
    k_structural : float
        Stiffness of structural (edge) springs (N/m).
    k_shear : float
        Stiffness of shear (diagonal) springs (N/m).
    k_bend : float
        Stiffness of bending (skip-1) springs (N/m).
    """

    rows: int
    cols: int
    spacing: float = 0.1
    mass: float = 0.01
    k_structural: float = 200.0
    k_shear: float = 100.0
    k_bend: float = 50.0

    # Initialised in __post_init__
    positions: list[Vec3] = field(default_factory=list)
    velocities: list[Vec3] = field(default_factory=list)
    masses: list[float] = field(default_factory=list)
    pinned: list[bool] = field(default_factory=list)
    springs: list[Spring] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = self.rows * self.cols
        s = self.spacing
        # Flat grid in XZ plane (Y = 0, hangs downward under gravity).
        # Particles centred at origin.
        x0 = -(self.cols - 1) * s / 2.0
        z0 = -(self.rows - 1) * s / 2.0
        self.positions = [
            (x0 + c * s, 0.0, z0 + r * s)
            for r in range(self.rows)
            for c in range(self.cols)
        ]
        self.velocities = [(0.0, 0.0, 0.0)] * n
        self.masses = [self.mass] * n
        self.pinned = [False] * n
        self._build_springs()

    def _idx(self, r: int, c: int) -> int:
        return r * self.cols + c

    def _build_springs(self) -> None:
        springs: list[Spring] = []
        R, C = self.rows, self.cols
        s = self.spacing

        def add(i: int, j: int, L0: float, k: float) -> None:
            if k > 0.0:
                springs.append(Spring(i=i, j=j, rest_length=L0, stiffness=k))

        for r in range(R):
            for c in range(C):
                idx = self._idx(r, c)
                # Structural — horizontal
                if c + 1 < C:
                    add(idx, self._idx(r, c + 1), s, self.k_structural)
                # Structural — vertical
                if r + 1 < R:
                    add(idx, self._idx(r + 1, c), s, self.k_structural)
                # Shear — diagonal
                if r + 1 < R and c + 1 < C:
                    add(idx, self._idx(r + 1, c + 1), s * math.sqrt(2), self.k_shear)
                if r + 1 < R and c - 1 >= 0:
                    add(idx, self._idx(r + 1, c - 1), s * math.sqrt(2), self.k_shear)
                # Bend — skip-1 horizontal
                if c + 2 < C:
                    add(idx, self._idx(r, c + 2), 2 * s, self.k_bend)
                # Bend — skip-1 vertical
                if r + 2 < R:
                    add(idx, self._idx(r + 2, c), 2 * s, self.k_bend)

        self.springs = springs

    def pin(self, r: int, c: int) -> None:
        """Pin particle (r, c) — it will not move."""
        self.pinned[self._idx(r, c)] = True

    def set_position(self, r: int, c: int, pos: Vec3) -> None:
        self.positions[self._idx(r, c)] = pos

    def total_energy(self) -> float:
        """Return total kinetic + spring potential energy."""
        ke = 0.0
        for i, (v, m) in enumerate(zip(self.velocities, self.masses)):
            ke += 0.5 * m * _dot(v, v)
        pe = 0.0
        for sp in self.springs:
            d = _norm(_sub(self.positions[sp.j], self.positions[sp.i]))
            stretch = d - sp.rest_length
            pe += 0.5 * sp.stiffness * stretch * stretch
        return ke + pe


# ---------------------------------------------------------------------------
# Collision primitives
# ---------------------------------------------------------------------------

@dataclass
class SpherePrimitive:
    """Solid sphere collision body."""
    centre: Vec3
    radius: float


@dataclass
class PlanePrimitive:
    """Infinite horizontal plane at y = height (default floor at y = 0)."""
    height: float = 0.0


# ---------------------------------------------------------------------------
# Stable time-step computation
# ---------------------------------------------------------------------------

_STABILITY_FACTOR = 0.2   # conservative factor for 2-D coupled lattice


def _safe_dt(k_max: float, m_min: float) -> float:
    """
    Return the largest stable sub-step for explicit Euler on a spring-mass
    lattice with max stiffness *k_max* and min free-particle mass *m_min*.

    Stability criterion: dt < 2/omega_max where omega_max = sqrt(k_max/m_min).
    We apply a safety factor of 0.2 for coupled 2-D lattice modes.
    """
    return _STABILITY_FACTOR * math.sqrt(m_min / k_max)


# ---------------------------------------------------------------------------
# Single integration step
# ---------------------------------------------------------------------------

_GRAVITY: Vec3 = (0.0, -9.81, 0.0)


def solve_step(
    mesh: ClothMesh,
    dt: float,
    gravity: Vec3 = _GRAVITY,
    velocity_damping: float = 0.99,
    colliders: Sequence[SpherePrimitive | PlanePrimitive] | None = None,
    auto_substep: bool = True,
) -> None:
    """
    Advance cloth simulation by one time step dt (seconds).

    Uses semi-implicit Euler (symplectic):
      1. Accumulate spring (Hooke) + gravity forces.
      2. Integrate velocity: v += (F/m) * dt.
      3. Apply per-step velocity damping: v *= velocity_damping.
      4. Integrate position: x += v * dt.
      5. Resolve collisions (projection).

    Parameters
    ----------
    mesh : ClothMesh
    dt : float
        Requested time step (seconds).  If *auto_substep* is True (default),
        this is automatically split into stable sub-steps.
    gravity : Vec3
        Gravitational acceleration.
    velocity_damping : float
        Per-sub-step velocity multiplier for energy dissipation.
        Set to values < 1 to damp oscillations (e.g. 0.98–0.999).
        NOTE: this is applied *per sub-step* so the effective per-outer-step
        damping is velocity_damping ** n_substeps.
    colliders : list of collision primitives, optional
    auto_substep : bool
        If True, split dt into stable sub-steps automatically.
    """
    if auto_substep and mesh.springs:
        ks = [sp.stiffness for sp in mesh.springs]
        k_max = max(ks)
        free_masses = [m for m, p in zip(mesh.masses, mesh.pinned) if not p]
        m_min = min(free_masses) if free_masses else min(mesh.masses)
        dt_sub = _safe_dt(k_max, m_min)
        if dt_sub < dt:
            n_sub = math.ceil(dt / dt_sub)
            dt_actual = dt / n_sub
            for _ in range(n_sub):
                solve_step(
                    mesh, dt_actual,
                    gravity=gravity,
                    velocity_damping=velocity_damping,
                    colliders=colliders,
                    auto_substep=False,
                )
            return

    n = len(mesh.positions)
    forces: list[Vec3] = [(0.0, 0.0, 0.0)] * n

    # --- Gravity -------------------------------------------------------
    for i in range(n):
        if not mesh.pinned[i]:
            m = mesh.masses[i]
            forces[i] = _scale(gravity, m)

    # --- Spring forces (Hooke only, no velocity damping in force) ------
    pos = mesh.positions
    for sp in mesh.springs:
        pi, pj = pos[sp.i], pos[sp.j]
        delta = _sub(pj, pi)
        dist = _norm(delta)
        if dist < 1e-15:
            continue
        n_hat = _scale(delta, 1.0 / dist)
        stretch = dist - sp.rest_length
        fvec = _scale(n_hat, sp.stiffness * stretch)
        if not mesh.pinned[sp.i]:
            forces[sp.i] = _add(forces[sp.i], fvec)
        if not mesh.pinned[sp.j]:
            forces[sp.j] = _sub(forces[sp.j], fvec)

    # --- Velocity integration + global damping -------------------------
    vel = mesh.velocities
    new_vel: list[Vec3] = []
    for i in range(n):
        if mesh.pinned[i]:
            new_vel.append((0.0, 0.0, 0.0))
        else:
            m = mesh.masses[i]
            a = _scale(forces[i], 1.0 / m)
            v_new = _scale(_add(vel[i], _scale(a, dt)), velocity_damping)
            new_vel.append(v_new)
    mesh.velocities = new_vel

    # --- Position integration ------------------------------------------
    new_pos: list[Vec3] = []
    for i in range(n):
        if mesh.pinned[i]:
            new_pos.append(pos[i])
        else:
            new_pos.append(_add(pos[i], _scale(mesh.velocities[i], dt)))
    mesh.positions = new_pos

    # --- Collision response --------------------------------------------
    if colliders:
        for i in range(n):
            if mesh.pinned[i]:
                continue
            p = mesh.positions[i]
            v = mesh.velocities[i]
            for col in colliders:
                if isinstance(col, SpherePrimitive):
                    d = _sub(p, col.centre)
                    dist = _norm(d)
                    if dist < col.radius:
                        n_hat = _normalize(d) if dist > 1e-15 else (0.0, 1.0, 0.0)
                        p = _add(col.centre, _scale(n_hat, col.radius * 1.001))
                        vn = _dot(v, n_hat)
                        if vn < 0:
                            v = _sub(v, _scale(n_hat, vn))
                elif isinstance(col, PlanePrimitive):
                    if p[1] < col.height:
                        p = (p[0], col.height, p[2])
                        vy = min(v[1], 0.0)
                        v = (v[0], v[1] - vy, v[2])
            mesh.positions[i] = p
            mesh.velocities[i] = v
