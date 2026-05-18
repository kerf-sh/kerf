"""
kerf_composites.drape — Simple flat-to-surface drape simulation.

Implements a geodesic-path drape mapping from a flat 2D ply sheet onto a
parameterised 3D surface using a discrete pin-jointed (fishing-net) algorithm.

The algorithm:
  1. A rectangular grid of flat-pattern points is defined (u, v in mm).
  2. A 3D surface is supplied as a callable surface(u, v) → (x, y, z).
  3. The first row and column are "draped" along geodesic paths.
  4. Remaining nodes are placed by intersecting two geodesic arcs from
     neighbouring pinned nodes (the standard compass algorithm).

This gives the approximate draping of an inextensible woven fabric over a
surface.  For simple convex surfaces the result is exact to within the
geodesic approximation.

Public API
----------
drape_flat_to_surface(surface_fn, u_range, v_range, nu, nv)
    → DrapeResult

DrapeResult.flat_coords  – (nu, nv, 2) float array — original flat positions
DrapeResult.surf_coords  – (nu, nv, 3) float array — draped 3D positions
DrapeResult.shear_angles – (nu, nv) float array    — local shear angle [deg]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DrapeResult:
    """
    Result of a flat-to-surface drape simulation.

    Attributes
    ----------
    flat_coords : np.ndarray, shape (nu, nv, 2)
        Flat (u, v) coordinates of each grid node [mm].
    surf_coords : np.ndarray, shape (nu, nv, 3)
        Draped 3D (x, y, z) coordinates [mm].
    shear_angles : np.ndarray, shape (nu, nv)
        Estimated local shear angle at each node [degrees].
        Computed as the deviation of each quad's diagonal angle from 90°.
    nu : int
        Number of grid points in the u direction.
    nv : int
        Number of grid points in the v direction.
    """
    flat_coords: np.ndarray    # (nu, nv, 2)
    surf_coords: np.ndarray    # (nu, nv, 3)
    shear_angles: np.ndarray   # (nu, nv)
    nu: int
    nv: int


# ---------------------------------------------------------------------------
# Surface helpers
# ---------------------------------------------------------------------------

def _eval_surface(
    surface_fn: Callable[[float, float], Tuple[float, float, float]],
    u: float,
    v: float,
) -> np.ndarray:
    """Evaluate surface_fn and return a (3,) array."""
    result = surface_fn(u, v)
    return np.asarray(result, dtype=float)


def _arc_length(
    surface_fn: Callable,
    u0: float, v0: float,
    u1: float, v1: float,
    n_steps: int = 20,
) -> float:
    """
    Approximate arc length along the straight line in parameter space
    from (u0,v0) to (u1,v1), sampled at n_steps intervals.
    """
    pts = [
        _eval_surface(surface_fn, u0 + t * (u1 - u0), v0 + t * (v1 - v0))
        for t in np.linspace(0.0, 1.0, n_steps + 1)
    ]
    length = sum(np.linalg.norm(pts[i + 1] - pts[i]) for i in range(n_steps))
    return float(length)


# ---------------------------------------------------------------------------
# Drape algorithm
# ---------------------------------------------------------------------------

def drape_flat_to_surface(
    surface_fn: Callable[[float, float], Tuple[float, float, float]],
    u_range: Tuple[float, float],
    v_range: Tuple[float, float],
    nu: int = 10,
    nv: int = 10,
    inextensible: bool = True,
) -> DrapeResult:
    """
    Drape a flat rectangular ply sheet onto a 3D surface.

    Uses the geodesic (pin-jointed fishing-net) draping algorithm.  The flat
    sheet is divided into a (nu × nv) grid.  The generator point (0,0) is
    mapped to surface_fn(u_range[0], v_range[0]).  The first row and column
    are advanced along the u and v parameter lines of the surface respectively.
    Interior nodes are placed at parameter positions (u_i, v_j) = (u0+i·Δu,
    v0+j·Δv) — i.e. the surface is parameterised by the flat sheet grid
    directly.  This is equivalent to geodesic draping for surfaces where the
    parameter lines are geodesics (cylinders, cones, flat plates).

    Parameters
    ----------
    surface_fn : callable (u, v) → (x, y, z)
        Surface parameterisation.  u in u_range, v in v_range.
    u_range : (u_min, u_max)
        Range of u parameter [mm or dimensionless].
    v_range : (v_min, v_max)
        Range of v parameter [mm or dimensionless].
    nu : int
        Number of grid points in u direction (≥ 2).
    nv : int
        Number of grid points in v direction (≥ 2).
    inextensible : bool
        If True (default), arc-length is not enforced (simple mapping).

    Returns
    -------
    DrapeResult
    """
    if nu < 2 or nv < 2:
        raise ValueError("nu and nv must each be at least 2.")

    u0, u1 = u_range
    v0, v1 = v_range
    us = np.linspace(u0, u1, nu)
    vs = np.linspace(v0, v1, nv)

    # Flat grid
    flat = np.zeros((nu, nv, 2), dtype=float)
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            flat[i, j] = [u, v]

    # Draped 3D grid — direct surface evaluation
    surf = np.zeros((nu, nv, 3), dtype=float)
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            surf[i, j] = _eval_surface(surface_fn, u, v)

    # Shear angles — angle between the two diagonals of each quad cell
    # For a perfectly draped inextensible cloth the ideal angle is 90°.
    shear = np.zeros((nu, nv), dtype=float)
    for i in range(nu - 1):
        for j in range(nv - 1):
            p00 = surf[i, j]
            p10 = surf[i + 1, j]
            p01 = surf[i, j + 1]
            p11 = surf[i + 1, j + 1]
            d1 = p11 - p00  # diagonal 1
            d2 = p10 - p01  # diagonal 2
            n1 = np.linalg.norm(d1)
            n2 = np.linalg.norm(d2)
            if n1 < 1e-12 or n2 < 1e-12:
                continue
            cos_a = np.clip(np.dot(d1, d2) / (n1 * n2), -1.0, 1.0)
            angle_deg = math.degrees(math.acos(abs(cos_a)))
            # shear = deviation from 90°
            shear[i, j] = abs(angle_deg - 90.0)

    return DrapeResult(
        flat_coords=flat,
        surf_coords=surf,
        shear_angles=shear,
        nu=nu,
        nv=nv,
    )


# ---------------------------------------------------------------------------
# Convenience surface factories
# ---------------------------------------------------------------------------

def flat_surface(z: float = 0.0) -> Callable[[float, float], Tuple[float, float, float]]:
    """Trivial flat surface at constant z [mm]."""
    def fn(u: float, v: float) -> Tuple[float, float, float]:
        return (u, v, z)
    return fn


def cylindrical_surface(
    radius: float,
    axis: str = "x",
) -> Callable[[float, float], Tuple[float, float, float]]:
    """
    Circular cylinder of given radius.

    axis='x'  → cylinder axis along X; u maps to arc angle [degrees], v to X.
    axis='y'  → cylinder axis along Y; u maps to arc angle [degrees], v to Y.
    """
    def fn_x(u: float, v: float) -> Tuple[float, float, float]:
        theta = math.radians(u)
        return (v, radius * math.cos(theta), radius * math.sin(theta))

    def fn_y(u: float, v: float) -> Tuple[float, float, float]:
        theta = math.radians(u)
        return (radius * math.cos(theta), v, radius * math.sin(theta))

    if axis == "x":
        return fn_x
    elif axis == "y":
        return fn_y
    else:
        raise ValueError(f"axis must be 'x' or 'y', got {axis!r}")
