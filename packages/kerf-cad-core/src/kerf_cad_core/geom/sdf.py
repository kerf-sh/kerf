"""GK-112 — Signed distance field (SDF) sampled from a B-rep Body.

API
---
body_sdf(body, resolution=32, padding=0.1) -> dict
    Sample the signed distance field of *body* onto a regular 3-D grid.

    Returns::

        {
            "grid":    np.ndarray of shape (nx, ny, nz),  # float64
            "origin":  np.ndarray([ox, oy, oz]),           # world coords of [0,0,0]
            "spacing": np.ndarray([sx, sy, sz]),           # voxel size
            "dims":    (nx, ny, nz),                       # int tuple
        }

    Sign convention: **negative inside**, positive outside.

sdf_sample(sdf, point) -> float
    Trilinear interpolation into a grid produced by :func:`body_sdf`.
    Points outside the grid are clamped to the boundary.

Algorithm
---------
For each face of the body we delegate to a face-level signed-distance
function.  For analytic faces (SphereSurface, CylinderSurface, Plane,
TorusSurface) we compute the *exact* signed distance in closed form.
For NurbsSurface and generic surfaces we fall back to the nearest-sample
approximation (sample the parametric domain, find the closest sample,
sign via dot product).

The per-face unsigned distances are combined with a minimum to find the
closest face; the sign of that face's signed distance is preserved.

For a closed watertight body the sign is consistent: negative inside,
positive outside.

Pure-Python (numpy only).  No OCCT, no C extensions.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

import numpy as np

from kerf_cad_core.geom.brep import Body, Face


# ---------------------------------------------------------------------------
# Internal: exact signed distance for analytic surface types
# ---------------------------------------------------------------------------

def _sdf_sphere_exact(surface, point: np.ndarray) -> float:
    """Signed distance to SphereSurface: positive outside, negative inside."""
    c = np.asarray(surface.center, dtype=float)
    r = float(surface.radius)
    return float(np.linalg.norm(point - c)) - r


def _sdf_plane_exact(surface, point: np.ndarray) -> float:
    """Signed distance to Plane (signed by face orientation separately)."""
    o = np.asarray(surface.origin, dtype=float)
    n = np.asarray(surface._n, dtype=float)  # precomputed unit normal
    return float(np.dot(point - o, n))


def _sdf_cylinder_exact(surface, point: np.ndarray) -> float:
    """Signed distance to an infinite CylinderSurface barrel.

    Returns the radial signed distance from the axis: positive outside,
    negative inside the cylinder tube.  (No cap handling — caps are
    separate planar faces in the B-rep.)
    """
    c = np.asarray(surface.center, dtype=float)
    axis = np.asarray(surface.axis, dtype=float)  # unit vector
    r = float(surface.radius)
    p = np.asarray(point, dtype=float)
    # Project onto plane perpendicular to axis
    v = p - c
    proj = np.dot(v, axis) * axis
    radial_vec = v - proj
    radial_dist = float(np.linalg.norm(radial_vec))
    return radial_dist - r


def _sdf_torus_exact(surface, point: np.ndarray) -> float:
    """Signed distance to TorusSurface: positive outside tube, negative inside."""
    c = np.asarray(surface.center, dtype=float)
    axis = np.asarray(surface.axis, dtype=float)
    R = float(surface.major_radius)
    r = float(surface.minor_radius)
    p = np.asarray(point, dtype=float)
    v = p - c
    # Distance from the torus tube axis (ring at radius R in the plane ⊥ axis)
    proj = np.dot(v, axis)
    radial_vec = v - proj * axis
    radial = float(np.linalg.norm(radial_vec))
    # Distance from ring circle
    ring_dist = math.sqrt((radial - R) ** 2 + proj ** 2)
    return ring_dist - r


# ---------------------------------------------------------------------------
# Internal: nearest-sample fallback for non-analytic surfaces
# ---------------------------------------------------------------------------

_FD = 1e-6  # finite-difference step for surface normal estimation


def _surface_normal_fd(surface, u: float, v: float) -> np.ndarray:
    """Outward parametric normal via finite-difference."""
    p = np.asarray(surface.evaluate(u, v), dtype=float)
    pu = np.asarray(surface.evaluate(u + _FD, v), dtype=float)
    pv = np.asarray(surface.evaluate(u, v + _FD), dtype=float)
    du = (pu - p) / _FD
    dv = (pv - p) / _FD
    n = np.cross(du, dv)
    norm = float(np.linalg.norm(n))
    if norm < 1e-14:
        if hasattr(surface, "normal"):
            return np.asarray(surface.normal(u, v), dtype=float)
        return np.array([0.0, 0.0, 1.0])
    return n / norm


def _analytic_normal(face: Face, u: float, v: float) -> np.ndarray:
    """Return the face's outward world-normal at parametric (u, v)."""
    surface = face.surface
    if hasattr(surface, "normal"):
        n = np.asarray(surface.normal(u, v), dtype=float)
    else:
        n = _surface_normal_fd(surface, u, v)
    return n if face.orientation else -n


def _face_param_bounds(face: Face):
    """Estimate parametric bounds [u_lo, u_hi] × [v_lo, v_hi] for *face*."""
    surface = face.surface
    cls_name = type(surface).__name__

    if cls_name == "SphereSurface":
        return (0.0, 2 * math.pi, -math.pi / 2, math.pi / 2)
    if cls_name == "TorusSurface":
        return (0.0, 2 * math.pi, 0.0, 2 * math.pi)
    if cls_name == "CylinderSurface":
        vert_pts = _loop_vertex_points(face)
        if vert_pts:
            arr = np.array(vert_pts)
            axis = getattr(surface, "axis", np.array([0.0, 0.0, 1.0]))
            c = getattr(surface, "center", np.zeros(3))
            vs = [(arr[i] - c) @ axis for i in range(len(arr))]
            v_lo, v_hi = float(min(vs)), float(max(vs))
            if abs(v_hi - v_lo) < 1e-10:
                v_lo, v_hi = v_lo - 1.0, v_hi + 1.0
            return (0.0, 2 * math.pi, v_lo, v_hi)
        return (0.0, 2 * math.pi, -1.0, 1.0)
    if cls_name == "Plane":
        vert_pts = _loop_vertex_points(face)
        if vert_pts:
            arr = np.array(vert_pts)
            o = np.asarray(surface.origin, dtype=float)
            ex = np.asarray(surface.x_axis, dtype=float)
            ey = np.asarray(surface.y_axis, dtype=float)
            us = [(arr[i] - o) @ ex for i in range(len(arr))]
            vs_list = [(arr[i] - o) @ ey for i in range(len(arr))]
            m = 0.01
            return (min(us) - m, max(us) + m, min(vs_list) - m, max(vs_list) + m)
        return (-1.0, 1.0, -1.0, 1.0)
    if hasattr(surface, "u_knots") and hasattr(surface, "v_knots"):
        uk = surface.u_knots
        vk = surface.v_knots
        return (float(uk[0]), float(uk[-1]), float(vk[0]), float(vk[-1]))
    return (0.0, 1.0, 0.0, 1.0)


def _loop_vertex_points(face: Face):
    outer = face.outer_loop()
    if outer is None or not outer.coedges:
        return []
    pts = []
    for ce in outer.coedges:
        try:
            pts.append(np.asarray(ce.start_point(), dtype=float))
        except Exception:  # noqa: BLE001
            pass
    return pts


def _sample_face(face: Face, n_uv: int = 8):
    """Return (points, normals) sampled from *face* for fallback path."""
    u_lo, u_hi, v_lo, v_hi = _face_param_bounds(face)
    surface = face.surface

    us = np.linspace(u_lo, u_hi, n_uv, endpoint=False) + (u_hi - u_lo) / (2 * n_uv)
    vs = np.linspace(v_lo, v_hi, n_uv, endpoint=False) + (v_hi - v_lo) / (2 * n_uv)

    pts, nrms = [], []
    for u in us:
        for v in vs:
            try:
                p = np.asarray(surface.evaluate(u, v), dtype=float)
                n = _analytic_normal(face, u, v)
            except Exception:  # noqa: BLE001
                continue
            if not np.all(np.isfinite(p)) or not np.all(np.isfinite(n)):
                continue
            norm = float(np.linalg.norm(n))
            if norm < 1e-14:
                continue
            pts.append(p)
            nrms.append(n / norm)

    if not pts:
        return np.empty((0, 3)), np.empty((0, 3))
    return np.array(pts, dtype=float), np.array(nrms, dtype=float)


# ---------------------------------------------------------------------------
# Per-face signed distance
# ---------------------------------------------------------------------------

def _face_signed_distance(face: Face, point: np.ndarray) -> float:
    """Return the signed distance from *point* to *face*.

    For analytic surfaces: exact closed-form.
    For generic surfaces: nearest-sample approximation.

    Sign: positive = same side as outward normal (outside), negative = inside.
    Face orientation is already accounted for.
    """
    surface = face.surface
    cls = type(surface).__name__
    sign_flip = 1.0 if face.orientation else -1.0

    if cls == "SphereSurface":
        return _sdf_sphere_exact(surface, point) * sign_flip
    if cls == "Plane":
        return _sdf_plane_exact(surface, point) * sign_flip
    if cls == "CylinderSurface":
        return _sdf_cylinder_exact(surface, point) * sign_flip
    if cls == "TorusSurface":
        return _sdf_torus_exact(surface, point) * sign_flip

    # Generic fallback: nearest-sample approximation
    # (accuracy depends on sampling density)
    pts, nrms = _sample_face(face, n_uv=16)
    if len(pts) == 0:
        return float("inf")
    diff = point[np.newaxis, :] - pts   # (M, 3)
    sq = (diff * diff).sum(axis=1)
    idx = int(sq.argmin())
    dist = math.sqrt(float(sq[idx]))
    dot = float(np.dot(diff[idx], nrms[idx]))
    return (1.0 if dot >= 0.0 else -1.0) * dist


# ---------------------------------------------------------------------------
# Body bounding-box (sampled from all face surfaces)
# ---------------------------------------------------------------------------

def _body_bbox(body: Body, n_uv: int = 12):
    """Compute the world-space bounding box of the body."""
    faces = body.all_faces()
    lo = np.full(3, +1e30)
    hi = np.full(3, -1e30)
    for face in faces:
        pts, _ = _sample_face(face, n_uv=n_uv)
        if len(pts):
            lo = np.minimum(lo, pts.min(axis=0))
            hi = np.maximum(hi, pts.max(axis=0))
    return lo, hi


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def body_sdf(
    body: Body,
    resolution: int = 32,
    padding: float = 0.1,
) -> dict:
    """Sample the signed distance field of *body* onto a regular 3-D grid.

    Parameters
    ----------
    body:       kerf B-rep Body (must have at least one face)
    resolution: number of grid points along each axis (default 32)
    padding:    fractional padding added to the bounding box (default 0.1 = 10 %)

    Returns
    -------
    dict with keys:

    ``grid``
        ``numpy.ndarray`` of shape ``(nx, ny, nz)``, dtype float64.
        Values are signed distances: **negative inside**, positive outside.
    ``origin``
        ``numpy.ndarray([ox, oy, oz])`` — world coordinate of grid index [0,0,0].
    ``spacing``
        ``numpy.ndarray([sx, sy, sz])`` — voxel size in world units.
    ``dims``
        ``(nx, ny, nz)`` tuple of ints.

    Raises
    ------
    ValueError
        If *body* has no faces or *resolution* < 2.
    """
    if resolution < 2:
        raise ValueError(f"resolution must be >= 2, got {resolution}")

    faces = body.all_faces()
    if not faces:
        raise ValueError("body has no faces — cannot compute SDF")

    # --- 1. Bounding box -----------------------------------------------------
    lo, hi = _body_bbox(body, n_uv=12)
    diag = float(np.linalg.norm(hi - lo))
    if diag < 1e-14:
        diag = 1.0
    pad = padding * diag
    lo -= pad
    hi += pad

    nx, ny, nz = resolution, resolution, resolution
    spacing = (hi - lo) / np.array([nx - 1, ny - 1, nz - 1], dtype=float)
    origin = lo.copy()

    # --- 2. Build grid -------------------------------------------------------
    gx = origin[0] + np.arange(nx, dtype=float) * spacing[0]
    gy = origin[1] + np.arange(ny, dtype=float) * spacing[1]
    gz = origin[2] + np.arange(nz, dtype=float) * spacing[2]
    GX, GY, GZ = np.meshgrid(gx, gy, gz, indexing="ij")   # (nx, ny, nz)
    grid_pts = np.stack([GX, GY, GZ], axis=-1)             # (nx, ny, nz, 3)
    flat_pts = grid_pts.reshape(-1, 3)                     # (N, 3)
    N = len(flat_pts)

    # --- 3. Compute per-face signed distance for each grid point -------------
    # For a watertight body: the body SDF is the face SDF with smallest
    # absolute value (closest face), preserving that face's sign.
    sdf_flat = np.full(N, float("inf"))

    for face in faces:
        surface = face.surface
        cls = type(surface).__name__
        sign_flip = 1.0 if face.orientation else -1.0

        if cls == "SphereSurface":
            c = np.asarray(surface.center, dtype=float)
            r = float(surface.radius)
            dist = np.linalg.norm(flat_pts - c, axis=1) - r  # signed dist
            face_sdf = dist * sign_flip

        elif cls == "Plane":
            o = np.asarray(surface.origin, dtype=float)
            n = np.asarray(surface._n, dtype=float)
            face_sdf = ((flat_pts - o) @ n) * sign_flip

        elif cls == "CylinderSurface":
            c = np.asarray(surface.center, dtype=float)
            axis = np.asarray(surface.axis, dtype=float)
            r = float(surface.radius)
            v = flat_pts - c                              # (N, 3)
            proj = (v @ axis)[:, np.newaxis] * axis      # (N, 3) axial proj
            radial = v - proj                             # (N, 3)
            face_sdf = (np.linalg.norm(radial, axis=1) - r) * sign_flip

        elif cls == "TorusSurface":
            c = np.asarray(surface.center, dtype=float)
            axis = np.asarray(surface.axis, dtype=float)
            R = float(surface.major_radius)
            r_minor = float(surface.minor_radius)
            v = flat_pts - c
            proj = (v @ axis)[:, np.newaxis] * axis
            radial = v - proj
            radial_dist = np.linalg.norm(radial, axis=1)
            axial_proj = (v @ axis)
            ring_dist = np.sqrt((radial_dist - R) ** 2 + axial_proj ** 2)
            face_sdf = (ring_dist - r_minor) * sign_flip

        else:
            # Generic: process each grid point individually (slower)
            face_sdf = np.array(
                [_face_signed_distance(face, flat_pts[i]) for i in range(N)],
                dtype=float,
            )

        # Keep the face SDF whose |value| is smallest (closest boundary)
        update_mask = np.abs(face_sdf) < np.abs(sdf_flat)
        sdf_flat = np.where(update_mask, face_sdf, sdf_flat)

    sdf_grid = sdf_flat.reshape(nx, ny, nz)

    return {
        "grid": sdf_grid,
        "origin": origin,
        "spacing": spacing,
        "dims": (nx, ny, nz),
    }


def sdf_sample(sdf: dict, point) -> float:
    """Trilinear interpolation into an SDF grid produced by :func:`body_sdf`.

    Parameters
    ----------
    sdf:   dict returned by :func:`body_sdf`
    point: array-like of length 3 — world-space query point

    Returns
    -------
    float
        Interpolated signed distance.  Points outside the grid are clamped
        to the nearest boundary cell.

    Raises
    ------
    ValueError
        If *sdf* is missing required keys.
    """
    required = {"grid", "origin", "spacing", "dims"}
    missing = required - set(sdf.keys())
    if missing:
        raise ValueError(f"sdf dict missing keys: {missing}")

    grid: np.ndarray = sdf["grid"]
    origin: np.ndarray = np.asarray(sdf["origin"], dtype=float)
    spacing: np.ndarray = np.asarray(sdf["spacing"], dtype=float)
    nx, ny, nz = sdf["dims"]

    p = np.asarray(point, dtype=float)

    fi = (p[0] - origin[0]) / spacing[0]
    fj = (p[1] - origin[1]) / spacing[1]
    fk = (p[2] - origin[2]) / spacing[2]

    fi = float(np.clip(fi, 0.0, nx - 1))
    fj = float(np.clip(fj, 0.0, ny - 1))
    fk = float(np.clip(fk, 0.0, nz - 1))

    i0, j0, k0 = int(math.floor(fi)), int(math.floor(fj)), int(math.floor(fk))
    i1 = min(i0 + 1, nx - 1)
    j1 = min(j0 + 1, ny - 1)
    k1 = min(k0 + 1, nz - 1)

    tx = fi - i0
    ty = fj - j0
    tz = fk - k0

    c000 = float(grid[i0, j0, k0])
    c001 = float(grid[i0, j0, k1])
    c010 = float(grid[i0, j1, k0])
    c011 = float(grid[i0, j1, k1])
    c100 = float(grid[i1, j0, k0])
    c101 = float(grid[i1, j0, k1])
    c110 = float(grid[i1, j1, k0])
    c111 = float(grid[i1, j1, k1])

    c00 = c000 * (1 - tz) + c001 * tz
    c01 = c010 * (1 - tz) + c011 * tz
    c10 = c100 * (1 - tz) + c101 * tz
    c11 = c110 * (1 - tz) + c111 * tz

    c0 = c00 * (1 - ty) + c01 * ty
    c1 = c10 * (1 - ty) + c11 * ty

    return c0 * (1 - tx) + c1 * tx
