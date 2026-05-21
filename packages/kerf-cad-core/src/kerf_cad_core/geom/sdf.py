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


# ---------------------------------------------------------------------------
# GK-113 — Marching Cubes: SDF / scalar grid → watertight triangle mesh
# ---------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Marching-cubes look-up tables (standard Lorensen & Cline 1987 encoding)
# --------------------------------------------------------------------------

# _MC_EDGE_TABLE[case] is a 12-bit mask: bit i set means edge i is crossed.
_MC_EDGE_TABLE: list[int] = [
    0x000, 0x109, 0x203, 0x30a, 0x406, 0x50f, 0x605, 0x70c,
    0x80c, 0x905, 0xa0f, 0xb06, 0xc0a, 0xd03, 0xe09, 0xf00,
    0x190, 0x099, 0x393, 0x29a, 0x596, 0x49f, 0x795, 0x69c,
    0x99c, 0x895, 0xb9f, 0xa96, 0xd9a, 0xc93, 0xf99, 0xe90,
    0x230, 0x339, 0x033, 0x13a, 0x636, 0x73f, 0x435, 0x53c,
    0xa3c, 0xb35, 0x83f, 0x936, 0xe3a, 0xf33, 0xc39, 0xd30,
    0x3a0, 0x2a9, 0x1a3, 0x0aa, 0x7a6, 0x6af, 0x5a5, 0x4ac,
    0xbac, 0xaa5, 0x9af, 0x8a6, 0xfaa, 0xea3, 0xda9, 0xca0,
    0x460, 0x569, 0x663, 0x76a, 0x066, 0x16f, 0x265, 0x36c,
    0xc6c, 0xd65, 0xe6f, 0xf66, 0x86a, 0x963, 0xa69, 0xb60,
    0x5f0, 0x4f9, 0x7f3, 0x6fa, 0x1f6, 0x0ff, 0x3f5, 0x2fc,
    0xdfc, 0xcf5, 0xfff, 0xef6, 0x9fa, 0x8f3, 0xbf9, 0xaf0,
    0x650, 0x759, 0x453, 0x55a, 0x256, 0x35f, 0x055, 0x15c,
    0xe5c, 0xf55, 0xc5f, 0xd56, 0xa5a, 0xb53, 0x859, 0x950,
    0x7c0, 0x6c9, 0x5c3, 0x4ca, 0x3c6, 0x2cf, 0x1c5, 0x0cc,
    0xfcc, 0xec5, 0xdcf, 0xcc6, 0xbca, 0xac3, 0x9c9, 0x8c0,
    0x8c0, 0x9c9, 0xac3, 0xbca, 0xcc6, 0xdcf, 0xec5, 0xfcc,
    0x0cc, 0x1c5, 0x2cf, 0x3c6, 0x4ca, 0x5c3, 0x6c9, 0x7c0,
    0x950, 0x859, 0xb53, 0xa5a, 0xd56, 0xc5f, 0xf55, 0xe5c,
    0x15c, 0x055, 0x35f, 0x256, 0x55a, 0x453, 0x759, 0x650,
    0xaf0, 0xbf9, 0x8f3, 0x9fa, 0xef6, 0xfff, 0xcf5, 0xdfc,
    0x2fc, 0x3f5, 0x0ff, 0x1f6, 0x6fa, 0x7f3, 0x4f9, 0x5f0,
    0xb60, 0xa69, 0x963, 0x86a, 0xf66, 0xe6f, 0xd65, 0xc6c,
    0x36c, 0x265, 0x16f, 0x066, 0x76a, 0x663, 0x569, 0x460,
    0xca0, 0xda9, 0xea3, 0xfaa, 0x8a6, 0x9af, 0xaa5, 0xbac,
    0x4ac, 0x5a5, 0x6af, 0x7a6, 0x0aa, 0x1a3, 0x2a9, 0x3a0,
    0xd30, 0xc39, 0xf33, 0xe3a, 0x936, 0x835, 0xb3f, 0xa36,  # noqa
    0x53c, 0x435, 0x73f, 0x636, 0x13a, 0x033, 0x339, 0x230,
    0xe90, 0xf99, 0xc93, 0xd9a, 0xa96, 0xb9f, 0x895, 0x99c,
    0x69c, 0x795, 0x49f, 0x596, 0x29a, 0x393, 0x099, 0x190,
    0xf00, 0xe09, 0xd03, 0xc0a, 0xb06, 0xa0f, 0x905, 0x80c,
    0x70c, 0x605, 0x50f, 0x406, 0x30a, 0x203, 0x109, 0x000,
]

# Triangle table: for each of 256 cases, up to 5 triangles, each triangle
# is 3 edge indices (0-11).  Terminated by -1.
_MC_TRI_TABLE: list[list[int]] = [
    [],
    [0, 8, 3],
    [0, 1, 9],
    [1, 8, 3, 9, 8, 1],
    [1, 2, 10],
    [0, 8, 3, 1, 2, 10],
    [9, 2, 10, 0, 2, 9],
    [2, 8, 3, 2, 10, 8, 10, 9, 8],
    [3, 11, 2],
    [0, 11, 2, 8, 11, 0],
    [1, 9, 0, 2, 3, 11],
    [1, 11, 2, 1, 9, 11, 9, 8, 11],
    [3, 10, 1, 11, 10, 3],
    [0, 10, 1, 0, 8, 10, 8, 11, 10],
    [3, 9, 0, 3, 11, 9, 11, 10, 9],
    [9, 8, 10, 10, 8, 11],
    [4, 7, 8],
    [4, 3, 0, 7, 3, 4],
    [0, 1, 9, 8, 4, 7],
    [4, 1, 9, 4, 7, 1, 7, 3, 1],
    [1, 2, 10, 8, 4, 7],
    [3, 4, 7, 3, 0, 4, 1, 2, 10],
    [9, 2, 10, 9, 0, 2, 8, 4, 7],
    [2, 10, 9, 2, 9, 7, 2, 7, 3, 7, 9, 4],
    [8, 4, 7, 3, 11, 2],
    [11, 4, 7, 11, 2, 4, 2, 0, 4],
    [9, 0, 1, 8, 4, 7, 2, 3, 11],
    [4, 7, 11, 9, 4, 11, 9, 11, 2, 9, 2, 1],
    [3, 10, 1, 3, 11, 10, 7, 8, 4],
    [1, 11, 10, 1, 4, 11, 1, 0, 4, 7, 11, 4],
    [4, 7, 8, 9, 0, 11, 9, 11, 10, 11, 0, 3],
    [4, 7, 11, 4, 11, 9, 9, 11, 10],
    [9, 5, 4],
    [9, 5, 4, 0, 8, 3],
    [0, 5, 4, 1, 5, 0],
    [8, 5, 4, 8, 3, 5, 3, 1, 5],
    [1, 2, 10, 9, 5, 4],
    [3, 0, 8, 1, 2, 10, 4, 9, 5],
    [5, 2, 10, 5, 4, 2, 4, 0, 2],
    [2, 10, 5, 3, 2, 5, 3, 5, 4, 3, 4, 8],
    [9, 5, 4, 2, 3, 11],
    [0, 11, 2, 0, 8, 11, 4, 9, 5],
    [0, 5, 4, 0, 1, 5, 2, 3, 11],
    [2, 1, 5, 2, 5, 8, 2, 8, 11, 4, 8, 5],
    [10, 3, 11, 10, 1, 3, 9, 5, 4],
    [4, 9, 5, 0, 8, 1, 8, 10, 1, 8, 11, 10],
    [5, 4, 0, 5, 0, 11, 5, 11, 10, 11, 0, 3],
    [5, 4, 8, 5, 8, 10, 10, 8, 11],
    [9, 7, 8, 5, 7, 9],
    [9, 3, 0, 9, 5, 3, 5, 7, 3],
    [0, 7, 8, 0, 1, 7, 1, 5, 7],
    [1, 5, 3, 3, 5, 7],
    [9, 7, 8, 9, 5, 7, 10, 1, 2],
    [10, 1, 2, 9, 5, 0, 5, 3, 0, 5, 7, 3],
    [8, 0, 2, 8, 2, 5, 8, 5, 7, 10, 5, 2],
    [2, 10, 5, 2, 5, 3, 3, 5, 7],
    [7, 9, 5, 7, 8, 9, 3, 11, 2],
    [9, 5, 7, 9, 7, 2, 9, 2, 0, 2, 7, 11],
    [2, 3, 11, 0, 1, 8, 1, 7, 8, 1, 5, 7],
    [11, 2, 1, 11, 1, 7, 7, 1, 5],
    [9, 5, 8, 8, 5, 7, 10, 1, 3, 10, 3, 11],
    [5, 7, 0, 5, 0, 9, 7, 11, 0, 1, 0, 10, 11, 10, 0],
    [11, 10, 0, 11, 0, 3, 10, 5, 0, 8, 0, 7, 5, 7, 0],
    [11, 10, 5, 7, 11, 5],
    [10, 6, 5],
    [0, 8, 3, 5, 10, 6],
    [9, 0, 1, 5, 10, 6],
    [1, 8, 3, 1, 9, 8, 5, 10, 6],
    [1, 6, 5, 2, 6, 1],
    [1, 6, 5, 1, 2, 6, 3, 0, 8],
    [9, 6, 5, 9, 0, 6, 0, 2, 6],
    [5, 9, 8, 5, 8, 2, 5, 2, 6, 3, 2, 8],
    [2, 3, 11, 10, 6, 5],
    [11, 0, 8, 11, 2, 0, 10, 6, 5],
    [0, 1, 9, 2, 3, 11, 5, 10, 6],
    [5, 10, 6, 1, 9, 2, 9, 11, 2, 9, 8, 11],
    [6, 3, 11, 6, 5, 3, 5, 1, 3],
    [0, 8, 11, 0, 11, 5, 0, 5, 1, 5, 11, 6],
    [3, 11, 6, 0, 3, 6, 0, 6, 5, 0, 5, 9],
    [6, 5, 9, 6, 9, 11, 11, 9, 8],
    [5, 10, 6, 4, 7, 8],
    [4, 3, 0, 4, 7, 3, 6, 5, 10],
    [1, 9, 0, 5, 10, 6, 8, 4, 7],
    [10, 6, 5, 1, 9, 7, 1, 7, 3, 7, 9, 4],
    [6, 1, 2, 6, 5, 1, 4, 7, 8],
    [1, 2, 5, 5, 2, 6, 3, 0, 4, 3, 4, 7],
    [8, 4, 7, 9, 0, 5, 0, 6, 5, 0, 2, 6],
    [7, 3, 9, 7, 9, 4, 3, 2, 9, 5, 9, 6, 2, 6, 9],
    [3, 11, 2, 7, 8, 4, 10, 6, 5],
    [5, 10, 6, 4, 7, 2, 4, 2, 0, 2, 7, 11],
    [0, 1, 9, 4, 7, 8, 2, 3, 11, 5, 10, 6],
    [9, 2, 1, 9, 11, 2, 9, 4, 11, 7, 11, 4, 5, 10, 6],
    [8, 4, 7, 3, 11, 5, 3, 5, 1, 5, 11, 6],
    [5, 1, 11, 5, 11, 6, 1, 0, 11, 7, 11, 4, 0, 4, 11],
    [0, 5, 9, 0, 6, 5, 0, 3, 6, 11, 6, 3, 8, 4, 7],
    [6, 5, 9, 6, 9, 11, 4, 7, 9, 7, 11, 9],
    [10, 4, 9, 6, 4, 10],
    [4, 10, 6, 4, 9, 10, 0, 8, 3],
    [10, 0, 1, 10, 6, 0, 6, 4, 0],
    [8, 3, 1, 8, 1, 6, 8, 6, 4, 6, 1, 10],
    [1, 4, 9, 1, 2, 4, 2, 6, 4],
    [3, 0, 8, 1, 2, 9, 2, 4, 9, 2, 6, 4],
    [0, 2, 4, 4, 2, 6],
    [8, 3, 2, 8, 2, 4, 4, 2, 6],
    [10, 4, 9, 10, 6, 4, 11, 2, 3],
    [0, 8, 2, 2, 8, 11, 4, 9, 10, 4, 10, 6],
    [3, 11, 2, 0, 1, 6, 0, 6, 4, 6, 1, 10],
    [6, 4, 1, 6, 1, 10, 4, 8, 1, 2, 1, 11, 8, 11, 1],
    [9, 6, 4, 9, 3, 6, 9, 1, 3, 11, 6, 3],
    [8, 11, 1, 8, 1, 0, 11, 6, 1, 9, 1, 4, 6, 4, 1],
    [3, 11, 6, 3, 6, 0, 0, 6, 4],
    [6, 4, 8, 11, 6, 8],
    [7, 10, 6, 7, 8, 10, 8, 9, 10],
    [0, 7, 3, 0, 10, 7, 0, 9, 10, 6, 7, 10],
    [10, 6, 7, 1, 10, 7, 1, 7, 8, 1, 8, 0],
    [10, 6, 7, 10, 7, 1, 1, 7, 3],
    [1, 2, 6, 1, 6, 8, 1, 8, 9, 8, 6, 7],
    [2, 6, 9, 2, 9, 1, 6, 7, 9, 0, 9, 3, 7, 3, 9],
    [7, 8, 0, 7, 0, 6, 6, 0, 2],
    [7, 3, 2, 6, 7, 2],
    [2, 3, 11, 10, 6, 8, 10, 8, 9, 8, 6, 7],
    [2, 0, 7, 2, 7, 11, 0, 9, 7, 6, 7, 10, 9, 10, 7],
    [1, 8, 0, 1, 7, 8, 1, 10, 7, 6, 7, 10, 2, 3, 11],
    [11, 2, 1, 11, 1, 7, 10, 6, 1, 6, 7, 1],
    [8, 9, 6, 8, 6, 7, 9, 1, 6, 11, 6, 3, 1, 3, 6],
    [0, 9, 1, 11, 6, 7],
    [7, 8, 0, 7, 0, 6, 3, 11, 0, 11, 6, 0],
    [7, 11, 6],
    [7, 6, 11],
    [3, 0, 8, 11, 7, 6],
    [0, 1, 9, 11, 7, 6],
    [8, 1, 9, 8, 3, 1, 11, 7, 6],
    [10, 1, 2, 6, 11, 7],
    [1, 2, 10, 3, 0, 8, 6, 11, 7],
    [2, 9, 0, 2, 10, 9, 6, 11, 7],
    [6, 11, 7, 2, 10, 3, 10, 8, 3, 10, 9, 8],
    [7, 2, 3, 6, 2, 7],
    [7, 0, 8, 7, 6, 0, 6, 2, 0],
    [2, 7, 6, 2, 3, 7, 0, 1, 9],
    [1, 6, 2, 1, 8, 6, 1, 9, 8, 8, 7, 6],
    [10, 7, 6, 10, 1, 7, 1, 3, 7],
    [10, 7, 6, 1, 7, 10, 1, 8, 7, 1, 0, 8],
    [0, 3, 7, 0, 7, 10, 0, 10, 9, 6, 10, 7],
    [7, 6, 10, 7, 10, 8, 8, 10, 9],
    [6, 8, 4, 11, 8, 6],
    [3, 6, 11, 3, 0, 6, 0, 4, 6],
    [8, 6, 11, 8, 4, 6, 9, 0, 1],
    [9, 4, 6, 9, 6, 3, 9, 3, 1, 11, 3, 6],
    [6, 8, 4, 6, 11, 8, 2, 10, 1],
    [1, 2, 10, 3, 0, 11, 0, 6, 11, 0, 4, 6],
    [4, 11, 8, 4, 6, 11, 0, 2, 9, 2, 10, 9],
    [10, 9, 3, 10, 3, 2, 9, 4, 3, 11, 3, 6, 4, 6, 3],
    [8, 2, 3, 8, 4, 2, 4, 6, 2],
    [0, 4, 2, 4, 6, 2],
    [1, 9, 0, 2, 3, 4, 2, 4, 6, 4, 3, 8],
    [1, 9, 4, 1, 4, 2, 2, 4, 6],
    [8, 1, 3, 8, 6, 1, 8, 4, 6, 6, 10, 1],
    [10, 1, 0, 10, 0, 6, 6, 0, 4],
    [4, 6, 3, 4, 3, 8, 6, 10, 3, 0, 3, 9, 10, 9, 3],
    [10, 9, 4, 6, 10, 4],
    [4, 9, 5, 7, 6, 11],
    [0, 8, 3, 4, 9, 5, 11, 7, 6],
    [5, 0, 1, 5, 4, 0, 7, 6, 11],
    [11, 7, 6, 8, 3, 4, 3, 5, 4, 3, 1, 5],
    [9, 5, 4, 10, 1, 2, 7, 6, 11],
    [6, 11, 7, 1, 2, 10, 0, 8, 3, 4, 9, 5],
    [7, 6, 11, 5, 4, 10, 4, 2, 10, 4, 0, 2],
    [3, 4, 8, 3, 5, 4, 3, 2, 5, 10, 5, 2, 11, 7, 6],
    [7, 2, 3, 7, 6, 2, 5, 4, 9],
    [9, 5, 4, 0, 8, 6, 0, 6, 2, 6, 8, 7],
    [3, 6, 2, 3, 7, 6, 1, 5, 0, 5, 4, 0],
    [6, 2, 8, 6, 8, 7, 2, 1, 8, 4, 8, 5, 1, 5, 8],
    [9, 5, 4, 10, 1, 6, 1, 7, 6, 1, 3, 7],
    [1, 6, 10, 1, 7, 6, 1, 0, 7, 8, 7, 0, 9, 5, 4],
    [4, 0, 10, 4, 10, 5, 0, 3, 10, 6, 10, 7, 3, 7, 10],
    [7, 6, 10, 7, 10, 8, 5, 4, 10, 4, 8, 10],
    [6, 9, 5, 6, 11, 9, 11, 8, 9],
    [3, 6, 11, 0, 6, 3, 0, 5, 6, 0, 9, 5],
    [0, 11, 8, 0, 5, 11, 0, 1, 5, 5, 6, 11],
    [6, 11, 3, 6, 3, 5, 5, 3, 1],
    [1, 2, 10, 9, 5, 11, 9, 11, 8, 11, 5, 6],
    [0, 11, 3, 0, 6, 11, 0, 9, 6, 5, 6, 9, 1, 2, 10],
    [11, 8, 5, 11, 5, 6, 8, 0, 5, 10, 5, 2, 0, 2, 5],
    [6, 11, 3, 6, 3, 5, 2, 10, 3, 10, 5, 3],
    [5, 8, 9, 5, 2, 8, 5, 6, 2, 3, 8, 2],
    [9, 5, 6, 9, 6, 0, 0, 6, 2],
    [1, 5, 8, 1, 8, 0, 5, 6, 8, 3, 8, 2, 6, 2, 8],
    [1, 5, 6, 2, 1, 6],
    [1, 3, 6, 1, 6, 10, 3, 8, 6, 5, 6, 9, 8, 9, 6],
    [10, 1, 0, 10, 0, 6, 9, 5, 0, 5, 6, 0],
    [0, 3, 8, 5, 6, 10],
    [10, 5, 6],
    [11, 5, 10, 7, 5, 11],
    [11, 5, 10, 11, 7, 5, 8, 3, 0],
    [5, 11, 7, 5, 10, 11, 1, 9, 0],
    [10, 7, 5, 10, 11, 7, 9, 8, 1, 8, 3, 1],
    [11, 1, 2, 11, 7, 1, 7, 5, 1],
    [0, 8, 3, 1, 2, 7, 1, 7, 5, 7, 2, 11],
    [9, 7, 5, 9, 2, 7, 9, 0, 2, 2, 11, 7],
    [7, 5, 2, 7, 2, 11, 5, 9, 2, 3, 2, 8, 9, 8, 2],
    [2, 5, 10, 2, 3, 5, 3, 7, 5],
    [8, 2, 0, 8, 5, 2, 8, 7, 5, 10, 2, 5],
    [9, 0, 1, 5, 10, 3, 5, 3, 7, 3, 10, 2],
    [9, 8, 2, 9, 2, 1, 8, 7, 2, 10, 2, 5, 7, 5, 2],
    [1, 3, 5, 3, 7, 5],
    [0, 8, 7, 0, 7, 1, 1, 7, 5],
    [9, 0, 3, 9, 3, 5, 5, 3, 7],
    [9, 8, 7, 5, 9, 7],
    [5, 8, 4, 5, 10, 8, 10, 11, 8],
    [5, 0, 4, 5, 11, 0, 5, 10, 11, 11, 3, 0],
    [0, 1, 9, 8, 4, 10, 8, 10, 11, 10, 4, 5],
    [10, 11, 4, 10, 4, 5, 11, 3, 4, 9, 4, 1, 3, 1, 4],
    [2, 5, 1, 2, 8, 5, 2, 11, 8, 4, 5, 8],
    [0, 4, 11, 0, 11, 3, 4, 5, 11, 2, 11, 1, 5, 1, 11],
    [0, 2, 5, 0, 5, 9, 2, 11, 5, 4, 5, 8, 11, 8, 5],
    [9, 4, 5, 2, 11, 3],
    [2, 5, 10, 3, 5, 2, 3, 4, 5, 3, 8, 4],
    [5, 10, 2, 5, 2, 4, 4, 2, 0],
    [3, 10, 2, 3, 5, 10, 3, 8, 5, 4, 5, 8, 0, 1, 9],
    [5, 10, 2, 5, 2, 4, 1, 9, 2, 9, 4, 2],
    [8, 4, 5, 8, 5, 3, 3, 5, 1],
    [0, 4, 5, 1, 0, 5],
    [8, 4, 5, 8, 5, 3, 9, 0, 5, 0, 3, 5],
    [9, 4, 5],
    [4, 11, 7, 4, 9, 11, 9, 10, 11],
    [0, 8, 3, 4, 9, 7, 9, 11, 7, 9, 10, 11],
    [1, 10, 11, 1, 11, 4, 1, 4, 0, 7, 4, 11],
    [3, 1, 4, 3, 4, 8, 1, 10, 4, 7, 4, 11, 10, 11, 4],
    [4, 11, 7, 9, 11, 4, 9, 2, 11, 9, 1, 2],
    [9, 7, 4, 9, 11, 7, 9, 1, 11, 2, 11, 1, 0, 8, 3],
    [11, 7, 4, 11, 4, 2, 2, 4, 0],
    [11, 7, 4, 11, 4, 2, 8, 3, 4, 3, 2, 4],
    [2, 9, 10, 2, 7, 9, 2, 3, 7, 7, 4, 9],
    [9, 10, 7, 9, 7, 4, 10, 2, 7, 8, 7, 0, 2, 0, 7],
    [3, 7, 10, 3, 10, 2, 7, 4, 10, 1, 10, 0, 4, 0, 10],
    [1, 10, 2, 8, 7, 4],
    [4, 9, 1, 4, 1, 7, 7, 1, 3],
    [4, 9, 1, 4, 1, 7, 0, 8, 1, 8, 7, 1],
    [4, 0, 3, 7, 4, 3],
    [4, 8, 7],
    [9, 10, 8, 10, 11, 8],
    [3, 0, 9, 3, 9, 11, 11, 9, 10],
    [0, 1, 10, 0, 10, 8, 8, 10, 11],
    [3, 1, 10, 11, 3, 10],
    [1, 2, 11, 1, 11, 9, 9, 11, 8],
    [3, 0, 9, 3, 9, 11, 1, 2, 9, 2, 11, 9],
    [0, 2, 11, 8, 0, 11],
    [3, 2, 11],
    [2, 3, 8, 2, 8, 10, 10, 8, 9],
    [9, 10, 2, 0, 9, 2],
    [2, 3, 8, 2, 8, 10, 0, 1, 8, 1, 10, 8],
    [1, 10, 2],
    [1, 3, 8, 9, 1, 8],
    [0, 9, 1],
    [0, 3, 8],
    [],
]

# The 12 edges of the MC cube, each as a pair of vertex indices (0-7).
# Vertex numbering (standard Lorensen):
#   v0=(0,0,0)  v1=(1,0,0)  v2=(1,1,0)  v3=(0,1,0)
#   v4=(0,0,1)  v5=(1,0,1)  v6=(1,1,1)  v7=(0,1,1)
_MC_CUBE_EDGES: list[tuple[int, int]] = [
    (0, 1), (1, 2), (2, 3), (3, 0),  # edges 0-3 (bottom face z=0)
    (4, 5), (5, 6), (6, 7), (7, 4),  # edges 4-7 (top face z=1)
    (0, 4), (1, 5), (2, 6), (3, 7),  # edges 8-11 (vertical)
]

# Vertex offsets in (i,j,k) space.
_MC_VERT_OFFSETS: list[tuple[int, int, int]] = [
    (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
    (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
]


def marching_cubes(
    sdf_or_grid,
    iso: float = 0.0,
) -> dict:
    """GK-113 — Marching cubes: SDF / scalar grid → watertight triangle mesh.

    Parameters
    ----------
    sdf_or_grid
        Either:

        - A ``dict`` returned by :func:`body_sdf` (keys: ``grid``,
          ``origin``, ``spacing``, ``dims``), or
        - A raw ``dict`` with the same keys (``grid``, ``origin``,
          ``spacing``; ``dims`` is optional and inferred if absent).

    iso
        Iso-surface value (default ``0.0`` for signed-distance fields where
        the surface is at the zero level-set).

    Returns
    -------
    dict
        ``{"verts": np.ndarray (V, 3), "faces": np.ndarray (F, 3)}``

        - ``verts``: float64 world-space vertex positions.
        - ``faces``: int32 vertex indices, one triangle per row.
          The mesh is **watertight** when the input SDF represents a
          closed manifold body (all boundary edges are shared).

    Raises
    ------
    ValueError
        If required keys are missing or the grid has fewer than 2 nodes
        along any axis.

    Notes
    -----
    Implements the standard 256-case Lorensen & Cline (1987) marching-cubes
    algorithm with linear interpolation along cube edges.  Pure-Python /
    numpy only; no C extensions.

    Sign convention: iso=0.0 extracts the zero level-set.  With the SDF
    produced by :func:`body_sdf` (negative inside, positive outside) this
    yields a mesh that covers the interior of the body.
    """
    # --- Validate / unpack input --------------------------------------------
    if not isinstance(sdf_or_grid, dict):
        raise ValueError("sdf_or_grid must be a dict (body_sdf output or raw grid dict)")

    required = {"grid", "origin", "spacing"}
    missing = required - set(sdf_or_grid.keys())
    if missing:
        raise ValueError(f"sdf_or_grid dict missing required keys: {missing}")

    grid: np.ndarray = np.asarray(sdf_or_grid["grid"], dtype=np.float64)
    origin: np.ndarray = np.asarray(sdf_or_grid["origin"], dtype=np.float64)
    spacing: np.ndarray = np.asarray(sdf_or_grid["spacing"], dtype=np.float64)

    if grid.ndim != 3:
        raise ValueError(f"grid must be 3-D, got shape {grid.shape}")

    nx, ny, nz = grid.shape
    if nx < 2 or ny < 2 or nz < 2:
        raise ValueError(
            f"grid must have at least 2 nodes per axis, got ({nx},{ny},{nz})"
        )

    # --- Shift grid by iso so we find the 0-crossing -----------------------
    # (avoids special-casing throughout)
    g = grid - iso

    # --- Build mesh via marching cubes -------------------------------------
    # We accumulate (edge_key → vertex_index) and face index triples.
    edge_verts: dict[tuple, int] = {}
    verts_list: list[np.ndarray] = []
    faces_list: list[tuple[int, int, int]] = []

    # Offsets in flat index space for the 8 cube corners
    # corner k = (di, dj, dk) → flat index (i+di)*ny*nz + (j+dj)*nz + (k+dk)
    # We work directly with (i,j,k) indices.

    def _get_edge_vert(
        i: int, j: int, k: int,
        edge_idx: int,
    ) -> int:
        """Return (creating if necessary) the vertex index for an edge crossing."""
        # Canonical edge key: (min_corner, max_corner) in (i,j,k) space
        d0 = _MC_VERT_OFFSETS[_MC_CUBE_EDGES[edge_idx][0]]
        d1 = _MC_VERT_OFFSETS[_MC_CUBE_EDGES[edge_idx][1]]
        ci0 = (i + d0[0], j + d0[1], k + d0[2])
        ci1 = (i + d1[0], j + d1[1], k + d1[2])
        key = (min(ci0, ci1), max(ci0, ci1))

        if key in edge_verts:
            return edge_verts[key]

        # Linear interpolation
        v0_val = float(g[ci0[0], ci0[1], ci0[2]])
        v1_val = float(g[ci1[0], ci1[1], ci1[2]])
        denom = v1_val - v0_val
        if abs(denom) < 1e-14:
            t = 0.5
        else:
            t = -v0_val / denom
        t = max(0.0, min(1.0, t))

        p0 = origin + np.array(ci0, dtype=float) * spacing
        p1 = origin + np.array(ci1, dtype=float) * spacing
        pos = p0 + t * (p1 - p0)

        idx = len(verts_list)
        verts_list.append(pos)
        edge_verts[key] = idx
        return idx

    # --- Main cube loop (i,j,k) = lower-left-front corner of each cell ----
    for i in range(nx - 1):
        for j in range(ny - 1):
            for k in range(nz - 1):
                # Build 8-bit cube index from sign of corners
                cube_idx = 0
                for bit, (di, dj, dk) in enumerate(_MC_VERT_OFFSETS):
                    if g[i + di, j + dj, k + dk] < 0.0:
                        cube_idx |= (1 << bit)

                if cube_idx == 0 or cube_idx == 255:
                    continue  # fully inside or fully outside

                edge_mask = _MC_EDGE_TABLE[cube_idx]
                if edge_mask == 0:
                    continue

                # Emit triangles
                tris = _MC_TRI_TABLE[cube_idx]
                for t_start in range(0, len(tris), 3):
                    e0 = tris[t_start]
                    e1 = tris[t_start + 1]
                    e2 = tris[t_start + 2]
                    v0 = _get_edge_vert(i, j, k, e0)
                    v1 = _get_edge_vert(i, j, k, e1)
                    v2 = _get_edge_vert(i, j, k, e2)
                    faces_list.append((v0, v1, v2))

    # --- Assemble output arrays --------------------------------------------
    if not verts_list:
        verts = np.empty((0, 3), dtype=np.float64)
        faces = np.empty((0, 3), dtype=np.int32)
    else:
        verts = np.array(verts_list, dtype=np.float64)
        faces = np.array(faces_list, dtype=np.int32)

    return {"verts": verts, "faces": faces}


# ---------------------------------------------------------------------------
# GK-114 — Voxel boolean / CSG on SDF grids
# ---------------------------------------------------------------------------

def _resample_to_common(sdf_a: dict, sdf_b: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Resample *sdf_b* onto the grid of *sdf_a* via trilinear interpolation.

    Returns (grid_a, grid_b_resampled, origin, spacing) where both grids
    share the *sdf_a* coordinate frame.
    """
    grid_a: np.ndarray = np.asarray(sdf_a["grid"], dtype=np.float64)
    origin_a: np.ndarray = np.asarray(sdf_a["origin"], dtype=np.float64)
    spacing_a: np.ndarray = np.asarray(sdf_a["spacing"], dtype=np.float64)
    nx, ny, nz = grid_a.shape

    grid_b: np.ndarray = np.asarray(sdf_b["grid"], dtype=np.float64)
    origin_b: np.ndarray = np.asarray(sdf_b["origin"], dtype=np.float64)
    spacing_b: np.ndarray = np.asarray(sdf_b["spacing"], dtype=np.float64)

    # Build world-space coordinates for each node in grid_a.
    ix = origin_a[0] + np.arange(nx, dtype=np.float64) * spacing_a[0]
    iy = origin_a[1] + np.arange(ny, dtype=np.float64) * spacing_a[1]
    iz = origin_a[2] + np.arange(nz, dtype=np.float64) * spacing_a[2]

    # Map those world coords into fractional indices of grid_b.
    nbx, nby, nbz = grid_b.shape
    fi = (ix - origin_b[0]) / spacing_b[0]   # (nx,)
    fj = (iy - origin_b[1]) / spacing_b[1]   # (ny,)
    fk = (iz - origin_b[2]) / spacing_b[2]   # (nz,)

    fi = np.clip(fi, 0.0, nbx - 1)
    fj = np.clip(fj, 0.0, nby - 1)
    fk = np.clip(fk, 0.0, nbz - 1)

    i0 = np.floor(fi).astype(np.int32)
    j0 = np.floor(fj).astype(np.int32)
    k0 = np.floor(fk).astype(np.int32)
    i1 = np.minimum(i0 + 1, nbx - 1)
    j1 = np.minimum(j0 + 1, nby - 1)
    k1 = np.minimum(k0 + 1, nbz - 1)

    tx = (fi - i0).astype(np.float64)  # (nx,)
    ty = (fj - j0).astype(np.float64)  # (ny,)
    tz = (fk - k0).astype(np.float64)  # (nz,)

    # Trilinear interpolation via broadcasting over all three axes.
    # grid_b has shape (nbx, nby, nbz); we index along each axis.
    # c000[i,j,k] = grid_b[i0[i], j0[j], k0[k]] etc.
    c000 = grid_b[i0[:, np.newaxis, np.newaxis], j0[np.newaxis, :, np.newaxis], k0[np.newaxis, np.newaxis, :]]
    c001 = grid_b[i0[:, np.newaxis, np.newaxis], j0[np.newaxis, :, np.newaxis], k1[np.newaxis, np.newaxis, :]]
    c010 = grid_b[i0[:, np.newaxis, np.newaxis], j1[np.newaxis, :, np.newaxis], k0[np.newaxis, np.newaxis, :]]
    c011 = grid_b[i0[:, np.newaxis, np.newaxis], j1[np.newaxis, :, np.newaxis], k1[np.newaxis, np.newaxis, :]]
    c100 = grid_b[i1[:, np.newaxis, np.newaxis], j0[np.newaxis, :, np.newaxis], k0[np.newaxis, np.newaxis, :]]
    c101 = grid_b[i1[:, np.newaxis, np.newaxis], j0[np.newaxis, :, np.newaxis], k1[np.newaxis, np.newaxis, :]]
    c110 = grid_b[i1[:, np.newaxis, np.newaxis], j1[np.newaxis, :, np.newaxis], k0[np.newaxis, np.newaxis, :]]
    c111 = grid_b[i1[:, np.newaxis, np.newaxis], j1[np.newaxis, :, np.newaxis], k1[np.newaxis, np.newaxis, :]]

    tx3 = tx[:, np.newaxis, np.newaxis]
    ty3 = ty[np.newaxis, :, np.newaxis]
    tz3 = tz[np.newaxis, np.newaxis, :]

    c00 = c000 * (1 - tz3) + c001 * tz3
    c01 = c010 * (1 - tz3) + c011 * tz3
    c10 = c100 * (1 - tz3) + c101 * tz3
    c11 = c110 * (1 - tz3) + c111 * tz3

    c0 = c00 * (1 - ty3) + c01 * ty3
    c1 = c10 * (1 - ty3) + c11 * ty3

    grid_b_resampled: np.ndarray = c0 * (1 - tx3) + c1 * tx3

    return grid_a, grid_b_resampled, origin_a, spacing_a


def voxel_union(sdf_a: dict, sdf_b: dict) -> dict:
    """GK-114 — Voxel CSG union of two SDF grids.

    The result SDF grid represents the union of the two bodies:
    ``union(d_a, d_b) = min(d_a, d_b)``  (R-function / F-rep standard).

    The output grid uses *sdf_a*'s coordinate frame; *sdf_b* is resampled
    onto that frame via trilinear interpolation before the min is applied.

    Parameters
    ----------
    sdf_a, sdf_b
        SDF grid dicts as returned by :func:`body_sdf` (keys: ``grid``,
        ``origin``, ``spacing``, ``dims``).

    Returns
    -------
    dict
        Same structure as :func:`body_sdf` output, on *sdf_a*'s grid.
    """
    grid_a, grid_b, origin, spacing = _resample_to_common(sdf_a, sdf_b)
    result_grid = np.minimum(grid_a, grid_b)
    nx, ny, nz = result_grid.shape
    return {
        "grid": result_grid,
        "origin": origin,
        "spacing": spacing,
        "dims": (nx, ny, nz),
    }


def voxel_intersection(sdf_a: dict, sdf_b: dict) -> dict:
    """GK-114 — Voxel CSG intersection of two SDF grids.

    The result SDF grid represents the intersection of the two bodies:
    ``intersection(d_a, d_b) = max(d_a, d_b)``

    Parameters
    ----------
    sdf_a, sdf_b
        SDF grid dicts as returned by :func:`body_sdf`.

    Returns
    -------
    dict
        Same structure as :func:`body_sdf` output, on *sdf_a*'s grid.
    """
    grid_a, grid_b, origin, spacing = _resample_to_common(sdf_a, sdf_b)
    result_grid = np.maximum(grid_a, grid_b)
    nx, ny, nz = result_grid.shape
    return {
        "grid": result_grid,
        "origin": origin,
        "spacing": spacing,
        "dims": (nx, ny, nz),
    }


def voxel_difference(sdf_a: dict, sdf_b: dict) -> dict:
    """GK-114 — Voxel CSG difference of two SDF grids (A minus B).

    The result SDF grid represents the subtraction of body B from body A:
    ``difference(d_a, d_b) = max(d_a, -d_b)``

    Parameters
    ----------
    sdf_a
        The body to subtract from (minuend).
    sdf_b
        The body to subtract (subtrahend).

    Returns
    -------
    dict
        Same structure as :func:`body_sdf` output, on *sdf_a*'s grid.
    """
    grid_a, grid_b, origin, spacing = _resample_to_common(sdf_a, sdf_b)
    result_grid = np.maximum(grid_a, -grid_b)
    nx, ny, nz = result_grid.shape
    return {
        "grid": result_grid,
        "origin": origin,
        "spacing": spacing,
        "dims": (nx, ny, nz),
    }
