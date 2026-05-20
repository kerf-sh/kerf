"""
kerf_textiles.drape
===================
Cloth drape simulation — settle a cloth mesh under gravity and optional
collision bodies, then compute the BS 5058 / ASTM D 4399 drape coefficient.

Quick start
-----------
::

    from kerf_textiles.drape import drape_simulate, drape_on_disc

    # Square cloth pinned at two top corners, hanging freely
    result = drape_simulate(
        rows=20, cols=20, spacing=0.05,
        k_structural=100.0, k_shear=50.0, k_bend=10.0,
        pin_indices=[(0, 0), (0, 19)],
        steps=2000, dt=0.005,
    )
    print(result.max_sag)             # metres

    # BS 5058 drape-coefficient test
    dc_result = drape_on_disc(
        cloth_radius=0.14, disc_radius=0.07,
        k_structural=100.0, k_bend=10.0,
    )
    print(dc_result.drape_coefficient)   # dimensionless, 0–1

Drape coefficient (BS 5058 / ASTM D 4399)
------------------------------------------

    DC = (A_projected - A_disc) / (A_cloth - A_disc)

where:
  * A_cloth     = area of the original flat cloth circle.
  * A_disc      = area of the supporting pedestal disc.
  * A_projected = projected area of the draped cloth onto the
                  horizontal reference plane.

DC ≈ 1.0  →  stiff fabric (barely droops — projected area ≈ A_cloth).
DC ≈ 0.0  →  very limp (hangs close to vertical — projected area ≈ A_disc).

Published range for real textiles: 0.30 – 0.95.
Stiffer fabric (higher k_bend) → higher DC.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from kerf_textiles.mass_spring import (
    ClothMesh,
    SpherePrimitive,
    PlanePrimitive,
    solve_step,
    Vec3,
    _norm,
    _sub,
    _add,
    _scale,
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DrapeResult:
    """
    Output of :func:`drape_simulate` and :func:`drape_on_disc`.

    Attributes
    ----------
    mesh : ClothMesh
        Final settled cloth mesh (positions are the draped geometry).
    max_sag : float
        Maximum downward displacement from the initial plane (metres, ≥ 0).
    drape_coefficient : float | None
        BS 5058 projected-area drape coefficient (dimensionless, 0–1).
        ``None`` if a circular disc pedestal was not used.
    energy_history : list[float]
        Total mechanical energy sampled every ``energy_sample_interval`` steps.
    converged : bool
        ``True`` if RMS velocity dropped below *tol* before the step limit.
    steps_taken : int
        Actual number of outer integration steps executed.
    """
    mesh: ClothMesh
    max_sag: float
    drape_coefficient: float | None
    energy_history: list[float]
    converged: bool
    steps_taken: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def drape_simulate(
    rows: int = 20,
    cols: int = 20,
    spacing: float = 0.05,
    mass: float = 0.005,
    k_structural: float = 100.0,
    k_shear: float = 50.0,
    k_bend: float = 10.0,
    velocity_damping: float = 0.98,
    pin_indices: list[tuple[int, int]] | None = None,
    pin_positions: dict[tuple[int, int], Vec3] | None = None,
    colliders: list[SpherePrimitive | PlanePrimitive] | None = None,
    gravity: Vec3 = (0.0, -9.81, 0.0),
    steps: int = 3000,
    dt: float = 0.005,
    tol: float = 1e-4,
    energy_sample_interval: int = 100,
) -> DrapeResult:
    """
    Simulate cloth draping under gravity, optionally colliding with primitives.

    Parameters
    ----------
    rows, cols : int
        Cloth grid resolution.
    spacing : float
        Rest length between adjacent particles (metres).
    mass : float
        Per-particle mass (kg).
    k_structural, k_shear, k_bend : float
        Spring stiffnesses (N/m).  Higher *k_bend* → stiffer fabric → higher DC.
    velocity_damping : float
        Per-sub-step velocity multiplier (0 < d ≤ 1).  Values < 1 dissipate
        kinetic energy.  Default 0.98 provides moderate damping.
    pin_indices : list of (row, col) tuples
        Particles fixed in space throughout the simulation.
    pin_positions : dict mapping (row, col) → Vec3, optional
        Override initial position of specified particles.  Useful for setting
        the horizontal span of a hanging strip shorter than the natural length,
        which creates a catenary configuration.  Interior particles in a
        single-column strip are linearly interpolated between the two pins.
    colliders : list of collision primitives
        :class:`~kerf_textiles.mass_spring.SpherePrimitive` or
        :class:`~kerf_textiles.mass_spring.PlanePrimitive`.
    gravity : Vec3
        Gravitational acceleration vector (default: −g ĵ).
    steps : int
        Maximum integration steps.
    dt : float
        Outer time step (seconds).  Automatically sub-stepped for stability.
    tol : float
        RMS velocity convergence tolerance (m/s).
    energy_sample_interval : int
        Record total energy every this many outer steps.

    Returns
    -------
    DrapeResult
    """
    mesh = ClothMesh(
        rows=rows,
        cols=cols,
        spacing=spacing,
        mass=mass,
        k_structural=k_structural,
        k_shear=k_shear,
        k_bend=k_bend,
    )

    if pin_indices:
        for r, c in pin_indices:
            mesh.pin(r, c)

    # Override initial positions of specific particles (e.g. to set pin span)
    if pin_positions:
        for (r, c), pos in pin_positions.items():
            idx = mesh._idx(r, c)
            mesh.positions[idx] = pos
            # Also linearly interpolate all free particles in the strip if
            # this is a single-column strip (cols=1) and both end pins are given.
        # If this is a 1-column strip with exactly 2 pin-position overrides,
        # re-distribute interior particles linearly between the two endpoints.
        if cols == 1 and pin_indices and len(pin_positions) == 2:
            sorted_pins = sorted(pin_positions.keys(), key=lambda rc: rc[0])
            (r0, _), (rN, _) = sorted_pins
            p0 = pin_positions[(r0, 0)]
            pN = pin_positions[(rN, 0)]
            for ri in range(r0 + 1, rN):
                frac = (ri - r0) / (rN - r0)
                mesh.positions[mesh._idx(ri, 0)] = (
                    p0[0] + frac * (pN[0] - p0[0]),
                    p0[1] + frac * (pN[1] - p0[1]),
                    p0[2] + frac * (pN[2] - p0[2]),
                )

    energy_history: list[float] = []
    converged = False
    step = 0

    for step in range(1, steps + 1):
        solve_step(
            mesh, dt=dt,
            gravity=gravity,
            velocity_damping=velocity_damping,
            colliders=colliders or [],
        )

        if step % energy_sample_interval == 0:
            energy_history.append(mesh.total_energy())

        # Convergence: check RMS velocity of free particles
        if step % 50 == 0:
            n_free = sum(1 for p in mesh.pinned if not p)
            if n_free > 0:
                rms_v = math.sqrt(
                    sum(_norm(v) ** 2 for v, p in zip(mesh.velocities, mesh.pinned) if not p)
                    / n_free
                )
                if rms_v < tol:
                    converged = True
                    break

    # --- Max sag (drop below initial y=0 plane) -------------------------
    max_sag = max(0.0, -min(p[1] for p in mesh.positions))

    return DrapeResult(
        mesh=mesh,
        max_sag=max_sag,
        drape_coefficient=None,
        energy_history=energy_history,
        converged=converged,
        steps_taken=step,
    )


def drape_on_disc(
    cloth_radius: float = 0.14,
    disc_radius: float = 0.07,
    spacing: float = 0.02,
    mass: float = 0.001,
    k_structural: float = 5.0,
    k_shear: float = 2.5,
    k_bend: float = 0.5,
    velocity_damping: float = 0.97,
    disc_height: float = 0.0,
    steps: int = 2000,
    dt: float = 0.005,
    tol: float = 1e-4,
) -> DrapeResult:
    """
    Simulate a circular cloth draped over a cylindrical disc pedestal,
    replicating the BS 5058 drape-coefficient test.

    Geometry
    --------
    * Circular cloth of radius *cloth_radius* centred on a disc of radius
      *disc_radius*.
    * Disc particles (r ≤ disc_radius) are pinned to the pedestal surface.
    * Ring particles (disc_radius < r ≤ cloth_radius) hang freely.
    * Particles outside the cloth circle are removed from the simulation
      (their spring connections to ring-edge particles are cut).

    The cloth ring hangs under gravity.  With low bending stiffness the ring
    hangs nearly vertical (DC → 0); with high bending stiffness it barely
    droops (DC → 1).

    Drape coefficient
    -----------------
    The horizontal projection of the hanging ring determines DC.  As the
    outer edge swings INWARD under gravity, the projected area shrinks below
    A_cloth, giving DC < 1.

    Returns a :class:`DrapeResult` with a populated ``drape_coefficient``.
    """
    from kerf_textiles.mass_spring import Spring

    # Build a square mesh large enough to cover the cloth circle
    half = int(math.ceil(cloth_radius / spacing))
    n_cells = 2 * half + 1
    mesh = ClothMesh(
        rows=n_cells,
        cols=n_cells,
        spacing=spacing,
        mass=mass,
        k_structural=k_structural,
        k_shear=k_shear,
        k_bend=k_bend,
    )

    cx = (n_cells - 1) / 2.0
    cy = (n_cells - 1) / 2.0
    cloth_r2 = cloth_radius ** 2
    disc_r2 = disc_radius ** 2

    # Classify particles
    outside_ids: set[int] = set()
    disc_ids: set[int] = set()
    for r in range(n_cells):
        for c in range(n_cells):
            dx = (c - cx) * spacing
            dz = (r - cy) * spacing
            d2 = dx * dx + dz * dz
            idx = mesh._idx(r, c)
            if d2 > cloth_r2:
                outside_ids.add(idx)
            elif d2 <= disc_r2:
                disc_ids.add(idx)

    # Pin disc particles (resting on pedestal)
    for i in disc_ids:
        mesh.pinned[i] = True

    # REMOVE springs that connect to outside-cloth particles.
    # This allows the ring's outer edge to hang freely without being anchored
    # to fixed outside particles, which would prevent inward collapse.
    mesh.springs = [
        sp for sp in mesh.springs
        if sp.i not in outside_ids and sp.j not in outside_ids
    ]

    # Lift all cloth-ring particles to disc height
    for r in range(n_cells):
        for c in range(n_cells):
            idx = mesh._idx(r, c)
            if idx in outside_ids:
                continue  # don't touch outside particles (irrelevant)
            p = mesh.positions[idx]
            mesh.positions[idx] = (p[0], disc_height, p[2])

    # Floor collider — prevents particles from falling forever
    floor = PlanePrimitive(height=disc_height - cloth_radius * 2.0)

    energy_history: list[float] = []
    converged = False
    step = 0
    ring_ids = [i for i in range(len(mesh.positions))
                if i not in outside_ids and i not in disc_ids]

    for step in range(1, steps + 1):
        solve_step(
            mesh, dt=dt,
            gravity=(0.0, -9.81, 0.0),
            velocity_damping=velocity_damping,
            colliders=[floor],
        )

        if step % 100 == 0:
            energy_history.append(mesh.total_energy())

        if step % 50 == 0 and ring_ids:
            rms_v = math.sqrt(
                sum(_norm(mesh.velocities[i]) ** 2 for i in ring_ids) / len(ring_ids)
            )
            if rms_v < tol:
                converged = True
                break

    # --- Drape coefficient (BS 5058 / ASTM D 4399) ----------------------
    # The draped cloth projects onto the horizontal plane.
    # Disc particles project to their fixed positions (A_disc area).
    # Ring particles swing inward → their projected radius shrinks.
    # We count unique (gx, gz) cells occupied by ring + disc particles.

    projected_set: set[tuple[int, int]] = set()

    # Disc: add cells at original grid positions within disc
    for r in range(n_cells):
        for c in range(n_cells):
            dx = (c - cx) * spacing
            dz = (r - cy) * spacing
            if dx * dx + dz * dz <= disc_r2:
                gx = int(round(dx / spacing))
                gz = int(round(dz / spacing))
                projected_set.add((gx, gz))

    # Ring: use actual simulated positions
    for i in ring_ids:
        px, _, pz = mesh.positions[i]
        if px != px or pz != pz:  # NaN guard
            continue
        gx = int(round(px / spacing))
        gz = int(round(pz / spacing))
        projected_set.add((gx, gz))

    cell_area = spacing * spacing
    A_projected = len(projected_set) * cell_area
    A_cloth = math.pi * cloth_radius ** 2
    A_disc = math.pi * disc_radius ** 2

    if A_cloth <= A_disc:
        dc = None
    else:
        dc = max(0.0, min(1.0, (A_projected - A_disc) / (A_cloth - A_disc)))

    # Max sag
    sag_vals = [disc_height - mesh.positions[i][1]
                for i in ring_ids
                if mesh.positions[i][1] == mesh.positions[i][1]]  # NaN check
    max_sag = max(0.0, max(sag_vals)) if sag_vals else 0.0

    return DrapeResult(
        mesh=mesh,
        max_sag=max_sag,
        drape_coefficient=dc,
        energy_history=energy_history,
        converged=converged,
        steps_taken=step,
    )


# ---------------------------------------------------------------------------
# Catenary reference
# ---------------------------------------------------------------------------

def catenary_max_sag(span: float, total_length: float) -> float:
    """
    Compute the maximum sag (dip) of a catenary with given horizontal span
    and total arc length, using the standard catenary equation.

    Parameters
    ----------
    span : float
        Horizontal distance between the two support points (metres).
    total_length : float
        Total arc length of the hanging chain / cloth strip (metres).

    Returns
    -------
    float
        Maximum vertical sag at the midpoint (metres).

    Notes
    -----
    The catenary is y = a*(cosh(x/a) - 1) with vertex at the midpoint.
    Arc length L = 2*a*sinh(S/(2*a)) where S = span.
    Sag f = a*(cosh(S/(2*a)) - 1).
    We solve for *a* via Newton's method on g(a) = 2*a*sinh(S/(2a)) - L = 0.
    """
    if total_length <= span + 1e-12:
        return 0.0  # Taut — no sag

    S = span
    L = total_length

    # Initial guess from parabolic approximation: sag ≈ sqrt(3*(L-S)*S)/2
    a_init = S * S / (8.0 * max(L - S, 1e-12))
    a = max(a_init, 1e-6)

    for _ in range(200):
        arg = S / (2.0 * a)
        sinh_val = math.sinh(arg)
        cosh_val = math.cosh(arg)
        f = 2.0 * a * sinh_val - L
        df = 2.0 * sinh_val - (S / a) * cosh_val
        if abs(df) < 1e-15:
            break
        a_new = a - f / df
        if a_new < 1e-9:
            a_new = a / 2.0
        if abs(a_new - a) < 1e-12:
            a = a_new
            break
        a = a_new

    return a * (math.cosh(S / (2.0 * a)) - 1.0)
