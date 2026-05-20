"""
test_surface_offset.py
======================
GK-83 — Hermetic pytest oracle for surface_offset / parallel surface.

Oracle contracts
----------------
1. Offset of a unit sphere by d yields a sphere of radius 1 + d (± tol).
2. Offset of a plane along its normal moves it by d exactly.
3. surface_offset is importable from kerf_cad_core.geom.

Run:
    python -m pytest packages/kerf-cad-core/tests/test_surface_offset.py -q
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom import surface_offset
from kerf_cad_core.geom.nurbs import NurbsSurface, surface_evaluate
from kerf_cad_core.geom.inversion import _surface_param_range


# ---------------------------------------------------------------------------
# Helpers / factories (copied from test_offset.py to keep test hermetic)
# ---------------------------------------------------------------------------

_S = math.sqrt(2.0) / 2.0


def make_rational_sphere(center, r) -> NurbsSurface:
    """Exact rational quadratic NURBS sphere of radius *r* centred at *center*."""
    center = np.asarray(center, dtype=float)
    mer = [
        (0.0, -r, 1.0), (r, -r, _S), (r, 0.0, 1.0), (r, r, _S), (0.0, r, 1.0),
    ]
    circ9 = [
        (1.0, 0.0, 1.0), (1.0, 1.0, _S), (0.0, 1.0, 1.0), (-1.0, 1.0, _S),
        (-1.0, 0.0, 1.0), (-1.0, -1.0, _S), (0.0, -1.0, 1.0), (1.0, -1.0, _S),
        (1.0, 0.0, 1.0),
    ]
    cp = np.zeros((9, 5, 3))
    w = np.zeros((9, 5))
    for i, (cx, cy, cw) in enumerate(circ9):
        for j, (mx, my, mw) in enumerate(mer):
            cp[i, j] = center + np.array([cx * mx, cx * my, mx * 0.0 + my * 0.0 + r * 0.0])
            # Full 3-D revolution: revolve the meridian about the y-axis.
            # meridian point (m_rho, m_y) in cylindrical coords (rho = r*sin,
            # y = r*cos-shifted).  The circle9 gives the angle in the xz-plane.
            # Simpler: use the exact formula.
            #   (x, y, z) = ( mx * cx - my_zero, my_abs, mx * cy )
            # where meridian y stays, x/z are the revolution.
            m_rho = mx   # horizontal distance from axis (x-axis of meridian)
            m_y   = my   # height
            circ_x = cx   # x of unit circle
            circ_y = cy   # y of unit circle
            cp[i, j] = center + np.array([m_rho * circ_x, m_y, m_rho * circ_y])
            w[i, j] = cw * mw

    ku9 = np.array([0, 0, 0, .25, .25, .5, .5, .75, .75, 1, 1, 1.0])
    kv5 = np.array([0.0, 0.0, 0.0, 0.5, 0.5, 1.0, 1.0, 1.0])
    return NurbsSurface(
        degree_u=2, degree_v=2,
        control_points=cp, knots_u=ku9, knots_v=kv5,
        weights=w,
    )


def make_plane_nurbs(origin, normal, size: float = 2.0) -> NurbsSurface:
    """Degree-(1,1) planar NURBS patch centred at *origin* with unit *normal*."""
    origin = np.asarray(origin, dtype=float)
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = ref - np.dot(ref, n) * n
    e1 = e1 / np.linalg.norm(e1) * size
    e2 = np.cross(n, e1)
    e2 = e2 / np.linalg.norm(e2) * size
    p00 = origin - e1 * 0.5 - e2 * 0.5
    p10 = origin + e1 * 0.5 - e2 * 0.5
    p01 = origin - e1 * 0.5 + e2 * 0.5
    p11 = origin + e1 * 0.5 + e2 * 0.5
    cps = np.array([[p00, p01], [p10, p11]])
    ku = np.array([0.0, 0.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsSurface(degree_u=1, degree_v=1, control_points=cps,
                        knots_u=ku, knots_v=kv)


def _sample_surface_pts(surf: NurbsSurface, n: int) -> np.ndarray:
    u0, u1, v0, v1 = _surface_param_range(surf)
    us = np.linspace(u0, u1, n)
    vs = np.linspace(v0, v1, n)
    pts = []
    for u in us:
        for v in vs:
            pts.append(surface_evaluate(surf, float(u), float(v))[:3])
    return np.array(pts)


# ---------------------------------------------------------------------------
# Oracle 1: sphere offset
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("d,r", [
    (0.5, 1.0),
    (-0.3, 1.0),
    (2.0, 1.0),
    (0.1, 3.0),
])
def test_sphere_offset_radius(d, r):
    """Offset of a sphere of radius r by d yields a sphere of radius r + d."""
    tol = 1e-6
    sphere = make_rational_sphere([0.0, 0.0, 0.0], r)
    offset = surface_offset(sphere, d)

    assert isinstance(offset, NurbsSurface)

    pts = _sample_surface_pts(offset, 8)
    dists = np.linalg.norm(pts, axis=1)
    expected_r = r + d
    assert abs(float(np.mean(dists)) - expected_r) < tol, (
        f"mean radius {np.mean(dists):.6f} != expected {expected_r:.6f}"
    )
    assert float(np.max(np.abs(dists - expected_r))) < tol, (
        f"max deviation {np.max(np.abs(dists - expected_r)):.6f} exceeds tol {tol}"
    )


def test_sphere_offset_collapses_raises():
    """Offsetting a unit sphere by -2 (collapses) must raise ValueError."""
    sphere = make_rational_sphere([0.0, 0.0, 0.0], 1.0)
    with pytest.raises(ValueError, match="collapse"):
        surface_offset(sphere, -2.0)


def test_sphere_offset_uv_structure_preserved():
    """The offset sphere has the same degree, knot vectors and net shape."""
    sphere = make_rational_sphere([0.0, 0.0, 0.0], 1.0)
    offset = surface_offset(sphere, 0.5)
    assert offset.degree_u == sphere.degree_u
    assert offset.degree_v == sphere.degree_v
    assert offset.control_points.shape == sphere.control_points.shape
    assert np.allclose(offset.knots_u, sphere.knots_u)
    assert np.allclose(offset.knots_v, sphere.knots_v)


# ---------------------------------------------------------------------------
# Oracle 2: plane offset
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("d,origin,normal", [
    (1.0,  [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]),
    (-0.5, [1.0, 2.0, 3.0], [0.0, 1.0, 0.0]),
    (0.25, [0.0, 0.0, 0.0], [1.0, 1.0, 0.0]),
])
def test_plane_offset_translates_by_d(d, origin, normal):
    """Offset of a plane moves every point by exactly d along the plane normal."""
    tol = 1e-9
    plane = make_plane_nurbs(origin, normal)
    offset = surface_offset(plane, d)

    assert isinstance(offset, NurbsSurface)

    n_unit = np.asarray(normal, dtype=float)
    n_unit = n_unit / np.linalg.norm(n_unit)

    # Every control point of the offset should be displaced by d*n from the
    # corresponding input control point.
    orig_cps = plane.control_points[:, :, :3]
    off_cps  = offset.control_points[:, :, :3]
    expected = orig_cps + d * n_unit
    assert np.allclose(off_cps, expected, atol=tol), (
        f"max cp displacement error: {np.max(np.abs(off_cps - expected)):.2e}"
    )


def test_plane_offset_uv_structure_preserved():
    """Plane offset preserves degree, knot vectors and CP net shape."""
    plane = make_plane_nurbs([0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
    offset = surface_offset(plane, 1.5)
    assert offset.degree_u == plane.degree_u
    assert offset.degree_v == plane.degree_v
    assert offset.control_points.shape == plane.control_points.shape
    assert np.allclose(offset.knots_u, plane.knots_u)
    assert np.allclose(offset.knots_v, plane.knots_v)


# ---------------------------------------------------------------------------
# Oracle 3: public import from kerf_cad_core.geom
# ---------------------------------------------------------------------------

def test_surface_offset_importable_from_geom():
    """surface_offset must be importable directly from kerf_cad_core.geom."""
    import kerf_cad_core.geom as geom
    assert hasattr(geom, "surface_offset")
    assert callable(geom.surface_offset)


# ---------------------------------------------------------------------------
# Oracle 4: zero offset is identity
# ---------------------------------------------------------------------------

def test_zero_offset_identity():
    """A zero offset should return a surface sampling at the same points."""
    tol = 1e-9
    plane = make_plane_nurbs([0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
    offset = surface_offset(plane, 0.0)
    orig_cps = plane.control_points[:, :, :3]
    off_cps  = offset.control_points[:, :, :3]
    assert np.allclose(orig_cps, off_cps, atol=tol)


# ---------------------------------------------------------------------------
# Oracle 5: ValueError on bad distance
# ---------------------------------------------------------------------------

def test_nan_distance_raises():
    plane = make_plane_nurbs([0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
    with pytest.raises(ValueError):
        surface_offset(plane, float("nan"))


def test_inf_distance_raises():
    plane = make_plane_nurbs([0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
    with pytest.raises(ValueError):
        surface_offset(plane, float("inf"))
