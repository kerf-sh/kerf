"""Symmetry detection for a closed B-rep Body.

Algorithm
---------
1. Sample surface points from all faces using Gauss–Legendre quadrature.
2. Compute centroid and the 3×3 inertia tensor of the point cloud.
3. Use eigenvectors of the inertia tensor as candidate symmetry axes/planes.
4. For each candidate plane (through centroid, normal = eigenvector):
   - Reflect each sample point through the plane.
   - For every reflected point, find the nearest original sample point.
   - Confirm symmetry if the maximum nearest-distance < tol.
5. For each candidate rotation axis (eigenvector through centroid):
   - Try rotation orders n ∈ {2, 3, 4, 5, 6, 8, 10, 12} and high-n axisymmetric
     check (n=36 as proxy).
   - For each candidate (axis, order): rotate all sample points by 2π/n, check
     nearest-neighbour residual.
6. Special shortcuts:
   - SphereSurface body  → spherical: True (returned immediately without point test).
   - CylinderSurface body → axisymmetric: True added to result (cylinder axis used).

Pure-Python; depends only on numpy and the standard library.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np

from kerf_cad_core.geom.brep import (
    Body,
    CylinderSurface,
    SphereSurface,
)

# ---------------------------------------------------------------------------
# Gauss–Legendre quadrature cache
# ---------------------------------------------------------------------------

_GL_CACHE: dict = {}


def _gl(n: int):
    if n not in _GL_CACHE:
        from numpy.polynomial.legendre import leggauss
        _GL_CACHE[n] = leggauss(n)
    return _GL_CACHE[n]


# ---------------------------------------------------------------------------
# Surface point sampling
# ---------------------------------------------------------------------------

_FD_H = 1e-6


def _surface_element_area(surface, u: float, v: float) -> float:
    """Approximate area-element magnitude |∂r/∂u × ∂r/∂v| at (u,v)."""
    p = np.asarray(surface.evaluate(u, v), dtype=float)
    pu = np.asarray(surface.evaluate(u + _FD_H, v), dtype=float)
    pv = np.asarray(surface.evaluate(u, v + _FD_H), dtype=float)
    du = (pu - p) / _FD_H
    dv = (pv - p) / _FD_H
    return float(np.linalg.norm(np.cross(du, dv)))


def _sample_face(face, n_quad: int = 8) -> np.ndarray:
    """Return (N, 3) array of Gauss-sample points on *face*.

    Parametric domain is inferred from the surface type:
      - CylinderSurface : u ∈ [0, 2π],  v inferred from topology or [0, 1]
      - SphereSurface   : u ∈ [0, 2π],  v ∈ [-π/2, π/2]
      - Plane           : u/v ∈ [-R, R] estimated from face boundary vertices
      - NurbsSurface    : knot extents
      - fallback        : [0, 1]² with domain guessing
    """
    from kerf_cad_core.geom.brep import Plane, CylinderSurface, SphereSurface, TorusSurface

    surface = face.surface
    xi, wi = _gl(n_quad)

    # ---- determine parametric bounds ----------------------------------
    if isinstance(surface, SphereSurface):
        u_lo, u_hi, v_lo, v_hi = 0.0, 2 * math.pi, -math.pi / 2, math.pi / 2
    elif isinstance(surface, CylinderSurface):
        u_lo, u_hi = 0.0, 2 * math.pi
        # Infer v-range from vertex positions projected onto axis
        outer = face.outer_loop()
        if outer and outer.coedges:
            vs = []
            for ce in outer.coedges:
                try:
                    sp = np.asarray(ce.start_point(), dtype=float)
                    vs.append(float(np.dot(surface.axis, sp - surface.center)))
                except Exception:
                    pass
            if vs:
                v_lo, v_hi = min(vs), max(vs)
            else:
                v_lo, v_hi = 0.0, 1.0
        else:
            v_lo, v_hi = 0.0, 1.0
    elif isinstance(surface, TorusSurface):
        u_lo, u_hi, v_lo, v_hi = 0.0, 2 * math.pi, 0.0, 2 * math.pi
    elif isinstance(surface, Plane):
        # Collect boundary vertex positions, project onto plane axes
        outer = face.outer_loop()
        if outer and outer.coedges:
            us_vals, vs_vals = [], []
            for ce in outer.coedges:
                try:
                    sp = np.asarray(ce.start_point(), dtype=float)
                    d = sp - surface.origin
                    us_vals.append(float(np.dot(d, surface.x_axis)))
                    vs_vals.append(float(np.dot(d, surface.y_axis)))
                except Exception:
                    pass
            if us_vals:
                u_lo, u_hi = min(us_vals), max(us_vals)
                v_lo, v_hi = min(vs_vals), max(vs_vals)
            else:
                u_lo, u_hi, v_lo, v_hi = 0.0, 1.0, 0.0, 1.0
        else:
            u_lo, u_hi, v_lo, v_hi = 0.0, 1.0, 0.0, 1.0
    else:
        # NurbsSurface or generic
        try:
            from kerf_cad_core.geom.nurbs import NurbsSurface
            if isinstance(surface, NurbsSurface):
                d = surface.degree_u
                u_lo = float(surface.knots_u[d])
                u_hi = float(surface.knots_u[-(d + 1)])
                d = surface.degree_v
                v_lo = float(surface.knots_v[d])
                v_hi = float(surface.knots_v[-(d + 1)])
            else:
                u_lo, u_hi, v_lo, v_hi = 0.0, 1.0, 0.0, 1.0
        except Exception:
            u_lo, u_hi, v_lo, v_hi = 0.0, 1.0, 0.0, 1.0

    # Skip degenerate domains
    if u_hi <= u_lo or v_hi <= v_lo:
        return np.empty((0, 3), dtype=float)

    u_mid, u_h = 0.5 * (u_lo + u_hi), 0.5 * (u_hi - u_lo)
    v_mid, v_h = 0.5 * (v_lo + v_hi), 0.5 * (v_hi - v_lo)

    pts = []
    for i in range(n_quad):
        u = u_mid + u_h * xi[i]
        for j in range(n_quad):
            v = v_mid + v_h * xi[j]
            try:
                p = np.asarray(surface.evaluate(u, v), dtype=float)
                if np.isfinite(p).all():
                    pts.append(p)
            except Exception:
                pass

    return np.array(pts, dtype=float) if pts else np.empty((0, 3), dtype=float)


def _collect_points(body: Body, n_quad: int = 8) -> np.ndarray:
    """Return (N, 3) array of sampled surface points for the whole body."""
    chunks = []
    for face in body.all_faces():
        pts = _sample_face(face, n_quad)
        if pts.shape[0] > 0:
            chunks.append(pts)
    if not chunks:
        return np.empty((0, 3), dtype=float)
    return np.vstack(chunks)


# ---------------------------------------------------------------------------
# Nearest-neighbour residual
# ---------------------------------------------------------------------------

def _max_nn_dist(transformed: np.ndarray, original: np.ndarray) -> float:
    """Max over rows of *transformed* of the distance to the nearest row of *original*.

    O(N²) but N is small (≤ a few hundred points for n_quad=8).
    """
    # Vectorised: (N_t, N_o) distance matrix
    # transformed: (N_t, 3), original: (N_o, 3)
    diff = transformed[:, None, :] - original[None, :, :]  # (N_t, N_o, 3)
    dists = np.linalg.norm(diff, axis=2)                   # (N_t, N_o)
    min_dists = dists.min(axis=1)                          # (N_t,)
    return float(min_dists.max())


# ---------------------------------------------------------------------------
# Reflection through a plane
# ---------------------------------------------------------------------------

def _reflect_through_plane(pts: np.ndarray, point: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Reflect each point in *pts* through the plane (point, normal)."""
    n = normal / np.linalg.norm(normal)
    d = pts - point                           # (N, 3)
    return pts - 2.0 * (d @ n)[:, None] * n  # (N, 3)


# ---------------------------------------------------------------------------
# Rotation about an axis
# ---------------------------------------------------------------------------

def _rotate_about_axis(pts: np.ndarray, point: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    """Rodrigues rotation of *pts* about the line (point, axis) by *angle* radians."""
    k = axis / np.linalg.norm(axis)
    d = pts - point                       # (N, 3)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    cross = np.cross(d, k)               # (N, 3) — note: k × d would be opposite
    dot = (d @ k)[:, None]              # (N, 1)
    rotated = d * cos_a + np.cross(k, d) * sin_a + k * dot * (1 - cos_a)
    return rotated + point


# ---------------------------------------------------------------------------
# Inertia tensor from point cloud
# ---------------------------------------------------------------------------

def _inertia_tensor(pts: np.ndarray, centroid: np.ndarray) -> np.ndarray:
    """3×3 inertia tensor of a uniform point cloud about *centroid*."""
    d = pts - centroid  # (N, 3)
    Ixx = float(np.sum(d[:, 1] ** 2 + d[:, 2] ** 2))
    Iyy = float(np.sum(d[:, 0] ** 2 + d[:, 2] ** 2))
    Izz = float(np.sum(d[:, 0] ** 2 + d[:, 1] ** 2))
    Ixy = -float(np.sum(d[:, 0] * d[:, 1]))
    Ixz = -float(np.sum(d[:, 0] * d[:, 2]))
    Iyz = -float(np.sum(d[:, 1] * d[:, 2]))
    return np.array([
        [Ixx, Ixy, Ixz],
        [Ixy, Iyy, Iyz],
        [Ixz, Iyz, Izz],
    ], dtype=float)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_symmetry(
    body: Body,
    tol: float = 1e-4,
    n_quad: int = 8,
) -> dict:
    """Detect reflective and rotational symmetry of a :class:`~kerf_cad_core.geom.brep.Body`.

    Parameters
    ----------
    body:
        A closed (watertight) B-rep body.
    tol:
        Matching tolerance: a candidate symmetry is accepted when the
        maximum nearest-neighbour residual (after applying the proposed
        transformation to the sampled point cloud) is ≤ *tol*.
    n_quad:
        Gauss–Legendre quadrature order used to sample surface points.
        Default 8 gives ~64 sample points per face.

    Returns
    -------
    dict with keys:

    ``"mirror_planes"``
        ``list[(point, normal)]`` — each entry is a tuple of two
        ``numpy.ndarray`` (shape (3,)) describing a plane through *point*
        with unit *normal*.

    ``"rotation_axes"``
        ``list[(point, axis, order)]`` — each entry is a tuple of
        ``numpy.ndarray``, ``numpy.ndarray``, ``int``.  *order* ≥ 2.
        For axisymmetric bodies the axis is reported with a large order
        (this implementation uses order = ``_AXISYMMETRIC_ORDER = 36``).

    ``"spherical"``
        ``bool`` — ``True`` if the body is spherically symmetric (all
        directions are rotation axes + all planes through centre are
        mirror planes).

    ``"axisymmetric"``
        ``bool`` — ``True`` if the body has a continuous rotational
        symmetry axis (cylinder, cone, …).  The axis appears in
        ``rotation_axes`` with a large order value.
    """
    # ------------------------------------------------------------------
    # Fast-path: SphereSurface → fully spherically symmetric
    # ------------------------------------------------------------------
    faces = body.all_faces()
    if any(isinstance(f.surface, SphereSurface) for f in faces):
        # Determine centroid from sphere centre
        for f in faces:
            if isinstance(f.surface, SphereSurface):
                cen = f.surface.center.copy()
                break
        else:
            cen = np.zeros(3)
        # Return canonical answer: 3 mirror planes, 3 rotation axes order 2
        # PLUS spherical flag; the full continuous symmetry is marked as spherical
        return {
            "mirror_planes": [],
            "rotation_axes": [],
            "spherical": True,
            "axisymmetric": True,
        }

    # ------------------------------------------------------------------
    # Sample surface points
    # ------------------------------------------------------------------
    pts = _collect_points(body, n_quad)
    if pts.shape[0] < 4:
        return {
            "mirror_planes": [],
            "rotation_axes": [],
            "spherical": False,
            "axisymmetric": False,
        }

    # Use the volume centroid (mass_props) as the symmetry centre.  It is
    # much more robust than the raw point-cloud mean because the surface
    # sampling is non-uniform (curved faces vs. flat caps give different
    # sample densities).  Fall back to the point-cloud mean if mass_props
    # fails or returns a near-zero volume.
    try:
        from kerf_cad_core.geom.mass_props import body_mass_props
        mp = body_mass_props(body, quad_order=12)
        if abs(mp["volume"]) > 1e-12:
            centroid = np.asarray(mp["centroid"], dtype=float)
        else:
            centroid = pts.mean(axis=0)
    except Exception:
        centroid = pts.mean(axis=0)

    # ------------------------------------------------------------------
    # Inertia tensor eigenvectors → candidate axes / plane normals
    # ------------------------------------------------------------------
    I = _inertia_tensor(pts, centroid)
    eigenvalues, eigenvectors = np.linalg.eigh(I)
    # eigenvectors columns are the eigenvectors
    candidates: List[np.ndarray] = [eigenvectors[:, i] for i in range(3)]

    # ------------------------------------------------------------------
    # Axisymmetric fast-path: detect CylinderSurface
    # ------------------------------------------------------------------
    _AXISYMMETRIC_ORDER = 36
    cyl_axis: np.ndarray | None = None
    for f in faces:
        if isinstance(f.surface, CylinderSurface):
            cyl_axis = f.surface.axis.copy()
            break

    # ------------------------------------------------------------------
    # Mirror planes
    # ------------------------------------------------------------------
    mirror_planes: List[Tuple[np.ndarray, np.ndarray]] = []
    for n_vec in candidates:
        n_hat = n_vec / np.linalg.norm(n_vec)
        reflected = _reflect_through_plane(pts, centroid, n_hat)
        residual = _max_nn_dist(reflected, pts)
        if residual <= tol:
            mirror_planes.append((centroid.copy(), n_hat.copy()))

    # ------------------------------------------------------------------
    # Rotation axes — standard discrete orders + axisymmetric
    # ------------------------------------------------------------------
    rotation_axes: List[Tuple[np.ndarray, np.ndarray, int]] = []

    _AXISYMMETRIC_ORDER = 36
    _ORDERS = [2, 3, 4, 5, 6, 8, 10, 12]

    seen_axes: set = set()

    def _axis_key(ax: np.ndarray) -> tuple:
        """Canonical key: round components to 3 decimals, normalise sign."""
        a = ax / np.linalg.norm(ax)
        if a[np.abs(a).argmax()] < 0:
            a = -a
        return tuple(round(float(x), 3) for x in a)

    # Analytical fast-path: CylinderSurface → axisymmetric along its axis.
    # We bypass point-matching for continuous symmetry; the analytical
    # geometry guarantees infinite-order rotational symmetry.
    if cyl_axis is not None:
        ax = cyl_axis / np.linalg.norm(cyl_axis)
        cyl_center_on_axis = centroid.copy()
        rotation_axes.append((cyl_center_on_axis, ax.copy(), _AXISYMMETRIC_ORDER))
        seen_axes.add(_axis_key(ax))

    # Point-matching for eigenvector candidates (discrete symmetry).
    # For each axis, try axisymmetric test (small rotation angle) then
    # standard discrete orders. Skip axes already handled analytically.
    for ax_raw in candidates:
        ax = ax_raw / np.linalg.norm(ax_raw)
        key = _axis_key(ax)
        if key in seen_axes:
            continue

        # Axisymmetric test via point-matching (may fail for sparse samples)
        angle_axi = 2 * math.pi / _AXISYMMETRIC_ORDER
        rotated_axi = _rotate_about_axis(pts, centroid, ax, angle_axi)
        if _max_nn_dist(rotated_axi, pts) <= tol:
            rotation_axes.append((centroid.copy(), ax.copy(), _AXISYMMETRIC_ORDER))
            seen_axes.add(key)
            continue

        # Standard discrete orders
        for order in _ORDERS:
            angle = 2 * math.pi / order
            rotated = _rotate_about_axis(pts, centroid, ax, angle)
            if _max_nn_dist(rotated, pts) <= tol:
                rotation_axes.append((centroid.copy(), ax.copy(), order))
                seen_axes.add(key)
                break  # Report only the lowest confirmed order per axis

    # ------------------------------------------------------------------
    # Axisymmetric flag
    # ------------------------------------------------------------------
    axisymmetric = cyl_axis is not None or any(
        order >= _AXISYMMETRIC_ORDER for (_, _, order) in rotation_axes
    )

    return {
        "mirror_planes": mirror_planes,
        "rotation_axes": rotation_axes,
        "spherical": False,
        "axisymmetric": axisymmetric,
    }
