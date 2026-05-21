"""
test_geodesic.py
================
Hermetic analytic-oracle tests for GK-101: curve-on-surface geodesic.

Oracles
-------
1. Plane — geodesic is a straight line (all output points collinear with
   the two endpoint world-space positions).
2. Cylinder — geodesic between two points at the *same height* follows the
   circular arc (constant Z, arc length equals the chord-angle × radius).
3. Length optimality — geodesic length ≤ naïve uv-linear path length.

No OCC, no network, no database.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.curve_toolkit import geodesic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamped_knots(n: int, degree: int) -> np.ndarray:
    """Clamped (open) uniform knot vector."""
    inner = max(0, n - degree - 1)
    parts = [np.zeros(degree + 1)]
    if inner > 0:
        parts.append(np.linspace(0.0, 1.0, inner + 2)[1:-1])
    parts.append(np.ones(degree + 1))
    return np.concatenate(parts)


def _make_plane_surface(
    width: float = 5.0,
    height: float = 5.0,
    nu: int = 5,
    nv: int = 5,
) -> NurbsSurface:
    """Flat XY-plane patch [0, width] × [0, height]."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [width * i / (nu - 1), height * j / (nv - 1), 0.0]
    return NurbsSurface(
        degree_u=min(3, nu - 1),
        degree_v=min(3, nv - 1),
        control_points=cp,
        knots_u=_clamped_knots(nu, min(3, nu - 1)),
        knots_v=_clamped_knots(nv, min(3, nv - 1)),
    )


def _make_cylinder_surface(
    radius: float = 1.0,
    height: float = 2.0,
    nu: int = 12,
    nv: int = 5,
    theta_start: float = 0.0,
    theta_end: float = 2.0 * math.pi,
) -> NurbsSurface:
    """Cylinder x=r·cos θ, y=r·sin θ, z=v·height.
    u ∈ [0,1] maps to θ ∈ [theta_start, theta_end].
    v ∈ [0,1] maps to z ∈ [0, height].
    Non-rational (for simple analytic tests).
    """
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        theta = theta_start + (theta_end - theta_start) * i / (nu - 1)
        for j in range(nv):
            z = height * j / (nv - 1)
            cp[i, j] = [radius * math.cos(theta), radius * math.sin(theta), z]
    return NurbsSurface(
        degree_u=min(3, nu - 1),
        degree_v=min(3, nv - 1),
        control_points=cp,
        knots_u=_clamped_knots(nu, min(3, nu - 1)),
        knots_v=_clamped_knots(nv, min(3, nv - 1)),
    )


def _path_len_world(pts: List[Tuple[float, float, float]]) -> float:
    total = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        dz = pts[i][2] - pts[i - 1][2]
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return total


def _collinear(pts: List[Tuple[float, float, float]], tol: float = 1e-4) -> bool:
    """Return True if all points lie on the line through first and last."""
    p0 = np.array(pts[0], dtype=float)
    p1 = np.array(pts[-1], dtype=float)
    direction = p1 - p0
    norm = np.linalg.norm(direction)
    if norm < 1e-12:
        return True
    direction /= norm
    for pt in pts[1:-1]:
        v = np.array(pt, dtype=float) - p0
        cross = np.cross(v, direction)
        if np.linalg.norm(cross) > tol:
            return False
    return True


# ---------------------------------------------------------------------------
# Oracle 1 — Plane geodesic is a straight line
# ---------------------------------------------------------------------------

class TestGeodesicOnPlane:
    def test_collinear_interior_points(self):
        """On a flat plane, all geodesic points must be collinear."""
        plane = _make_plane_surface(width=5.0, height=5.0, nu=5, nv=5)
        pts = geodesic(plane, (0.0, 0.0), (1.0, 1.0), n=16)
        assert len(pts) == 16
        assert _collinear(pts, tol=1e-3), \
            "Geodesic on plane is not collinear"

    def test_diagonal_collinear(self):
        """Diagonal path on plane — collinear."""
        plane = _make_plane_surface(width=3.0, height=4.0, nu=4, nv=4)
        pts = geodesic(plane, (0.1, 0.1), (0.9, 0.9), n=20)
        assert _collinear(pts, tol=1e-3)

    def test_axis_aligned(self):
        """Axis-aligned path on plane — collinear."""
        plane = _make_plane_surface(width=5.0, height=5.0, nu=5, nv=5)
        pts = geodesic(plane, (0.0, 0.5), (1.0, 0.5), n=10)
        assert _collinear(pts, tol=1e-3)

    def test_endpoints_preserved(self):
        """First and last point match surface eval at start/end UV."""
        from kerf_cad_core.geom.nurbs import surface_evaluate
        plane = _make_plane_surface()
        uv_s = (0.2, 0.3)
        uv_e = (0.8, 0.7)
        pts = geodesic(plane, uv_s, uv_e, n=8)
        p_start = surface_evaluate(plane, *uv_s)
        p_end = surface_evaluate(plane, *uv_e)
        np.testing.assert_allclose(pts[0], p_start, atol=1e-6)
        np.testing.assert_allclose(pts[-1], p_end, atol=1e-6)

    def test_output_length_matches_n(self):
        plane = _make_plane_surface()
        for n in [2, 5, 32]:
            pts = geodesic(plane, (0.0, 0.0), (1.0, 1.0), n=n)
            assert len(pts) == n, f"Expected {n} points, got {len(pts)}"


# ---------------------------------------------------------------------------
# Oracle 2 — Cylinder at same height follows circular arc
# ---------------------------------------------------------------------------

class TestGeodesicOnCylinder:
    def _same_height_arc(self, radius: float, theta1: float, theta2: float):
        """Return the analytic arc length between two angles at same height."""
        return radius * abs(theta2 - theta1)

    def test_same_height_length_vs_arc(self):
        """Geodesic between two points at same Z on a cylinder equals arc length."""
        radius = 2.0
        theta_start = 0.0
        theta_end = math.pi  # half circle in u
        cyl = _make_cylinder_surface(
            radius=radius,
            height=3.0,
            nu=24,
            nv=5,
            theta_start=theta_start,
            theta_end=theta_end,
        )
        # Both points at v=0.5 (midheight), full u range
        pts = geodesic(cyl, (0.0, 0.5), (1.0, 0.5), n=24)

        # Analytic arc length: half circle = π × radius
        analytic_len = math.pi * radius
        geo_len = _path_len_world(pts)
        # Allow 1% relative tolerance (approximation by non-rational NurbsSurface)
        assert abs(geo_len - analytic_len) / analytic_len < 0.02, (
            f"Cylinder geodesic length {geo_len:.5f} not close to "
            f"analytic {analytic_len:.5f}"
        )

    def test_same_height_constant_z(self):
        """Same-height geodesic on cylinder should stay near constant Z."""
        radius = 1.0
        cyl = _make_cylinder_surface(
            radius=radius,
            height=2.0,
            nu=24,
            nv=5,
            theta_start=0.0,
            theta_end=math.pi,
        )
        pts = geodesic(cyl, (0.0, 0.5), (1.0, 0.5), n=16)
        zs = [p[2] for p in pts]
        z_mean = sum(zs) / len(zs)
        # All z values should be near the midheight
        for z in zs:
            assert abs(z - z_mean) < 0.05 * radius, \
                f"Z drifted: z={z:.5f}, mean={z_mean:.5f}"


# ---------------------------------------------------------------------------
# Oracle 3 — Geodesic length ≤ naïve UV-linear path length
# ---------------------------------------------------------------------------

class TestGeodesicLengthOptimality:
    def _uv_linear_length(
        self,
        surface: NurbsSurface,
        uv_start: Tuple[float, float],
        uv_end: Tuple[float, float],
        n: int,
    ) -> float:
        """Length of a naïve UV-linearly interpolated path."""
        from kerf_cad_core.geom.nurbs import surface_evaluate
        ts = np.linspace(0.0, 1.0, n)
        pts = []
        for t in ts:
            uu = uv_start[0] * (1 - t) + uv_end[0] * t
            vv = uv_start[1] * (1 - t) + uv_end[1] * t
            p = surface_evaluate(surface, uu, vv)
            pts.append(p)
        total = 0.0
        for i in range(1, len(pts)):
            total += float(np.linalg.norm(pts[i] - pts[i - 1]))
        return total

    def test_plane_shorter_than_uv_linear(self):
        """On a plane, geodesic should be equal to or shorter than UV linear."""
        plane = _make_plane_surface(nu=5, nv=5)
        n = 16
        uv_s, uv_e = (0.1, 0.1), (0.9, 0.9)
        geo_pts = geodesic(plane, uv_s, uv_e, n=n)
        geo_len = _path_len_world(geo_pts)
        naive_len = self._uv_linear_length(plane, uv_s, uv_e, n)
        assert geo_len <= naive_len + 1e-6, (
            f"Geodesic {geo_len:.6f} > naive {naive_len:.6f}"
        )

    def test_cylinder_shorter_than_uv_linear_diagonal(self):
        """On a cylinder, geodesic diagonal should be ≤ UV-linear diagonal."""
        cyl = _make_cylinder_surface(radius=1.0, height=2.0, nu=16, nv=5)
        n = 16
        uv_s, uv_e = (0.05, 0.1), (0.95, 0.9)
        geo_pts = geodesic(cyl, uv_s, uv_e, n=n)
        geo_len = _path_len_world(geo_pts)
        naive_len = self._uv_linear_length(cyl, uv_s, uv_e, n)
        assert geo_len <= naive_len + 1e-4, (
            f"Geodesic {geo_len:.6f} > naive {naive_len:.6f}"
        )

    def test_n_equals_2_returns_two_endpoints(self):
        """n=2 returns just the two endpoint evaluations."""
        plane = _make_plane_surface()
        pts = geodesic(plane, (0.0, 0.0), (1.0, 1.0), n=2)
        assert len(pts) == 2
