"""
Tests for kerf_cad_core.geom.revolve_srf
=========================================
Pure-Python, no database, no OCC required.

Covers:
  - Knot vector and weight correctness for 90 / 180 / 270 / 360-degree sweeps
  - Revolved line → cylinder: surface points on exact cylinder, area via Pappus
  - Revolved arc → approximate sphere checks: points on analytic sphere within tol
  - Torus: profile circle revolved around Y-axis
  - Partial-angle surface (90°, 180°)
  - Pole degeneracy: profile with a point on axis
  - rail_revolve basic smoke test
  - evaluate_revolve at parameter boundaries
  - n_arc_segment helper
  - Error paths: bad sweep, zero axis, cap=True
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface
from kerf_cad_core.geom.revolve_srf import (
    _arc_segment_count,
    _build_arc_data,
    evaluate_revolve,
    rail_revolve,
    revolve_surface,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PI = math.pi
_TWO_PI = 2.0 * _PI


def _make_line_profile(p0, p1, degree: int = 1) -> NurbsCurve:
    """Degree-1 line profile between p0 and p1."""
    cp = np.array([p0, p1], dtype=float)
    knots = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsCurve(degree=degree, control_points=cp, knots=knots)


def _make_polyline_profile(pts, degree: int = 1) -> NurbsCurve:
    """Degree-1 polyline through the given points."""
    cp = np.array(pts, dtype=float)
    n = len(pts)
    knots = np.concatenate([
        np.zeros(2),
        np.linspace(0.0, 1.0, n)[1:-1],
        np.ones(2),
    ])
    return NurbsCurve(degree=degree, control_points=cp, knots=knots)


def _revolve_cylinder_pts(surf, r, h, n_u=5, n_v=8):
    """Sample surface points and check they lie on the cylinder x²+z²=r², 0≤y≤h."""
    us = np.linspace(surf.knots_u[0], surf.knots_u[-1], n_u + 2)[1:-1]
    vs = np.linspace(surf.knots_v[0], surf.knots_v[-1], n_v + 2)[1:-1]
    pts = []
    for u in us:
        for v in vs:
            pt = evaluate_revolve(surf, u, v)
            pts.append(pt)
    return pts


# ---------------------------------------------------------------------------
# 1. _arc_segment_count
# ---------------------------------------------------------------------------

class TestArcSegmentCount:
    def test_90_degrees(self):
        assert _arc_segment_count(math.pi / 2) == 1

    def test_just_under_90(self):
        assert _arc_segment_count(math.pi / 2 - 1e-8) == 1

    def test_180_degrees(self):
        assert _arc_segment_count(math.pi) == 2

    def test_270_degrees(self):
        assert _arc_segment_count(3.0 * math.pi / 2) == 3

    def test_360_degrees(self):
        assert _arc_segment_count(2.0 * math.pi) == 4

    def test_small_angle(self):
        assert _arc_segment_count(0.1) == 1


# ---------------------------------------------------------------------------
# 2. _build_arc_data  — knot vector and weight checks
# ---------------------------------------------------------------------------

class TestBuildArcData:
    def _center_x_y(self):
        return (
            np.array([0.0, 0.0, 0.0]),
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
        )

    def test_90_arc_n_control_points(self):
        c, x, y = self._center_x_y()
        pts, wts, knots = _build_arc_data(c, x, y, 1.0, 0.0, _PI / 2)
        assert pts.shape == (3, 3)   # 2*1+1 = 3

    def test_90_arc_knot_length(self):
        c, x, y = self._center_x_y()
        _, _, knots = _build_arc_data(c, x, y, 1.0, 0.0, _PI / 2)
        # degree 2, n=3: n_knots = n + degree + 1 = 6
        assert len(knots) == 6

    def test_90_arc_clamped_knots(self):
        c, x, y = self._center_x_y()
        _, _, knots = _build_arc_data(c, x, y, 1.0, 0.0, _PI / 2)
        assert knots[0] == pytest.approx(0.0)
        assert knots[1] == pytest.approx(0.0)
        assert knots[2] == pytest.approx(0.0)
        assert knots[-1] == pytest.approx(1.0)
        assert knots[-2] == pytest.approx(1.0)
        assert knots[-3] == pytest.approx(1.0)

    def test_90_arc_tangent_weight(self):
        c, x, y = self._center_x_y()
        _, wts, _ = _build_arc_data(c, x, y, 1.0, 0.0, _PI / 2)
        # middle CP weight = cos(45°) = 1/√2
        assert wts[1] == pytest.approx(math.cos(_PI / 4), rel=1e-10)
        assert wts[0] == pytest.approx(1.0)
        assert wts[2] == pytest.approx(1.0)

    def test_180_arc_n_control_points(self):
        c, x, y = self._center_x_y()
        pts, wts, knots = _build_arc_data(c, x, y, 1.0, 0.0, _PI)
        assert pts.shape == (5, 3)

    def test_180_arc_tangent_weights(self):
        c, x, y = self._center_x_y()
        _, wts, _ = _build_arc_data(c, x, y, 1.0, 0.0, _PI)
        # Two tangent CPs (indices 1 and 3), weight = cos(45°)
        assert wts[1] == pytest.approx(math.cos(_PI / 4), rel=1e-10)
        assert wts[3] == pytest.approx(math.cos(_PI / 4), rel=1e-10)

    def test_360_arc_n_control_points(self):
        c, x, y = self._center_x_y()
        pts, wts, knots = _build_arc_data(c, x, y, 1.0, 0.0, _TWO_PI)
        assert pts.shape == (9, 3)

    def test_360_arc_start_end_coincide(self):
        """For a full circle the first and last control points should coincide."""
        c, x, y = self._center_x_y()
        pts, _, _ = _build_arc_data(c, x, y, 1.0, 0.0, _TWO_PI)
        assert np.allclose(pts[0], pts[-1], atol=1e-10)

    def test_arc_on_circle(self):
        """The on-curve CPs (even indices) should lie exactly on the circle."""
        c, x, y = self._center_x_y()
        r = 3.5
        pts, wts, _ = _build_arc_data(c, x, y, r, 0.0, _TWO_PI)
        for idx in range(0, 9, 2):
            dist = np.linalg.norm(pts[idx] - c)
            assert dist == pytest.approx(r, abs=1e-10)


# ---------------------------------------------------------------------------
# 3. revolve_surface — output shape / degree / knots
# ---------------------------------------------------------------------------

class TestRevolveSurfaceShape:
    def test_line_full_360_shape(self):
        profile = _make_line_profile([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        surf = revolve_surface(profile, [0,0,0], [0,1,0])
        # profile: 2 CPs, degree 1; arc: 4 segs → 9 CPs, degree 2
        assert surf.control_points.shape == (2, 9, 4)
        assert surf.degree_u == 1
        assert surf.degree_v == 2

    def test_line_90_degree_shape(self):
        profile = _make_line_profile([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        surf = revolve_surface(profile, [0,0,0], [0,1,0], 0.0, _PI / 2)
        assert surf.control_points.shape == (2, 3, 4)

    def test_line_180_degree_shape(self):
        profile = _make_line_profile([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        surf = revolve_surface(profile, [0,0,0], [0,1,0], 0.0, _PI)
        assert surf.control_points.shape == (2, 5, 4)

    def test_line_270_degree_shape(self):
        profile = _make_line_profile([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        surf = revolve_surface(profile, [0,0,0], [0,1,0], 0.0, 1.5 * _PI)
        assert surf.control_points.shape == (2, 7, 4)

    def test_knots_u_equals_profile_knots(self):
        profile = _make_line_profile([2.0, 0.0, 0.0], [2.0, 3.0, 0.0])
        surf = revolve_surface(profile, [0,0,0], [0,1,0])
        assert np.allclose(surf.knots_u, profile.knots)

    def test_knots_v_degree_2_clamped(self):
        profile = _make_line_profile([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        surf = revolve_surface(profile, [0,0,0], [0,1,0])
        kv = surf.knots_v
        assert kv[0] == pytest.approx(0.0)
        assert kv[1] == pytest.approx(0.0)
        assert kv[2] == pytest.approx(0.0)
        assert kv[-1] == pytest.approx(1.0)
        assert kv[-2] == pytest.approx(1.0)
        assert kv[-3] == pytest.approx(1.0)

    def test_knots_v_length_full_360(self):
        # 4 segs, degree 2: n_knots = 9+2+1 = 12
        profile = _make_line_profile([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        surf = revolve_surface(profile, [0,0,0], [0,1,0])
        assert len(surf.knots_v) == 12

    def test_knots_v_length_90(self):
        # 1 seg, degree 2: n_knots = 3+2+1 = 6
        profile = _make_line_profile([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        surf = revolve_surface(profile, [0,0,0], [0,1,0], 0.0, _PI / 2)
        assert len(surf.knots_v) == 6


# ---------------------------------------------------------------------------
# 4. Cylinder: revolved vertical line
# ---------------------------------------------------------------------------

class TestCylinder:
    """Revolve a line at radius r, height 0..h around the Y-axis → cylinder."""

    def _build(self, r=2.0, h=3.0):
        # Profile: line from (r,0,0) to (r,h,0) in XY-plane
        profile = _make_line_profile([r, 0.0, 0.0], [r, h, 0.0])
        return revolve_surface(profile, [0,0,0], [0,1,0]), r, h

    def test_points_on_cylinder(self):
        surf, r, h = self._build()
        n_u, n_v = 4, 12
        us = np.linspace(0.0, 1.0, n_u + 2)[1:-1]
        vs = np.linspace(0.0, 1.0, n_v + 2)[1:-1]
        for u in us:
            for v in vs:
                pt = evaluate_revolve(surf, u, v)
                radial = math.sqrt(pt[0]**2 + pt[2]**2)
                assert radial == pytest.approx(r, abs=1e-10), f"u={u},v={v}: r={radial}"

    def test_cylinder_height(self):
        """y-coordinate of surface points should vary linearly 0..h."""
        surf, r, h = self._build()
        us = np.linspace(0.0, 1.0, 6)[1:-1]
        for u in us:
            pt0 = evaluate_revolve(surf, u, 0.0)
            pt1 = evaluate_revolve(surf, u, 1.0)
            # For a degree-1 profile the u-parameter maps linearly to height
            # both extremes should be near 0 and h
        pt_bot = evaluate_revolve(surf, 0.0, 0.5)
        pt_top = evaluate_revolve(surf, 1.0, 0.5)
        assert pt_bot[1] == pytest.approx(0.0, abs=1e-10)
        assert pt_top[1] == pytest.approx(h, abs=1e-10)

    def test_pappus_lateral_area(self):
        """Lateral area of cylinder = 2π r h (Pappus theorem for a line).

        We verify via numerical integration of the Jacobian over the surface.
        """
        r, h = 2.0, 3.0
        expected_area = _TWO_PI * r * h

        surf, _, _ = self._build(r=r, h=h)

        # Numerical integration via midpoint rule on a fine grid
        N = 50
        us = np.linspace(0.0, 1.0, N + 1)
        vs = np.linspace(0.0, 1.0, N + 1)
        du = 1.0 / N
        dv = 1.0 / N

        # Approximate Jacobian via finite differences at midpoints
        area = 0.0
        for i in range(N):
            for j in range(N):
                u = (us[i] + us[i+1]) / 2
                v = (vs[j] + vs[j+1]) / 2

                eps = 1e-5
                pu = (evaluate_revolve(surf, min(u + eps, 0.9999), v) -
                      evaluate_revolve(surf, max(u - eps, 1e-5), v)) / (2 * eps)
                pv = (evaluate_revolve(surf, u, min(v + eps, 0.9999)) -
                      evaluate_revolve(surf, u, max(v - eps, 1e-5))) / (2 * eps)
                cross = np.cross(pu, pv)
                area += np.linalg.norm(cross) * du * dv

        assert area == pytest.approx(expected_area, rel=0.02)

    def test_on_arc_cps_are_on_cylinder(self):
        """The on-arc control points (even columns, w=1) lie on the cylinder.

        CPs are stored as homogeneous (w*x, w*y, w*z, w).  For on-arc CPs w=1
        so the Cartesian point is just the first 3 coords.
        """
        surf, r, h = self._build()
        cp = surf.control_points
        for i in range(cp.shape[0]):
            for j in range(0, cp.shape[1], 2):
                w = cp[i, j, 3]
                pt = cp[i, j, :3] / w if abs(w) > 1e-15 else cp[i, j, :3]
                radial = math.sqrt(pt[0]**2 + pt[2]**2)
                assert radial == pytest.approx(r, abs=1e-10)


# ---------------------------------------------------------------------------
# 5. Sphere: revolved semicircle
# ---------------------------------------------------------------------------

class TestSphere:
    """Revolve a semicircle (XY-plane, centre at origin) around the Y-axis."""

    def _build_sphere(self, R=1.5):
        # Approximate a semicircle with 3 control points (rational quadratic)
        # Exact quarter-circle: P0=(0,-R), P1=(R,-R), P2=(R,0)  — first quarter
        # For a full semicircle from (0,-R) to (0,R) via (R,0):
        # Using 2-segment quadratic
        # Segment 1: (0,-R)→(R,-R)→(R,0)  weight cos45 at middle
        # Segment 2: (R,0)→(R,R)→(0,R)    weight cos45 at middle
        w = math.cos(_PI / 4)
        cp = np.array([
            [0.0, -R, 0.0, 1.0],   # south pole on axis
            [R,   -R, 0.0, w],
            [R,    0.0, 0.0, 1.0],
            [R,    R,  0.0, w],
            [0.0,  R,  0.0, 1.0],  # north pole on axis
        ])
        knots = np.array([0.0, 0.0, 0.0, 0.5, 0.5, 1.0, 1.0, 1.0])
        profile = NurbsCurve(degree=2, control_points=cp, knots=knots)
        return revolve_surface(profile, [0, 0, 0], [0, 1, 0]), R

    def test_sphere_points_on_surface(self):
        """Sampled surface points should lie within tol of the analytic sphere."""
        surf, R = self._build_sphere()
        n_u, n_v = 6, 10
        us = np.linspace(0.0, 1.0, n_u + 2)[1:-1]
        vs = np.linspace(0.0, 1.0, n_v + 2)[1:-1]
        for u in us:
            for v in vs:
                pt = evaluate_revolve(surf, u, v)
                dist = np.linalg.norm(pt)
                assert dist == pytest.approx(R, abs=1e-8), f"u={u},v={v}: |pt|={dist}"

    def test_sphere_north_south_poles(self):
        """At u=0 and u=1 the surface should be at the poles (on axis)."""
        surf, R = self._build_sphere()
        for v in [0.0, 0.25, 0.5, 0.75, 1.0]:
            south = evaluate_revolve(surf, 0.0, v)
            north = evaluate_revolve(surf, 1.0, v)
            # South pole ≈ (0,-R,0), north pole ≈ (0,R,0)
            assert abs(south[0]) < 1e-8
            assert abs(south[2]) < 1e-8
            assert south[1] == pytest.approx(-R, abs=1e-8)
            assert abs(north[0]) < 1e-8
            assert abs(north[2]) < 1e-8
            assert north[1] == pytest.approx(R, abs=1e-8)

    def test_sphere_equator(self):
        """At u=0.5 the surface should be near the equator (y ≈ 0, |pt|=R)."""
        surf, R = self._build_sphere()
        for v in [0.0, 0.25, 0.5, 0.75]:
            pt = evaluate_revolve(surf, 0.5, v)
            assert abs(pt[1]) < 1e-7
            assert math.sqrt(pt[0]**2 + pt[2]**2) == pytest.approx(R, abs=1e-7)


# ---------------------------------------------------------------------------
# 6. Torus: profile circle revolved around Y-axis
# ---------------------------------------------------------------------------

class TestTorus:
    """Revolve a profile circle of radius r centred at (R, 0, 0) around Y-axis.

    The profile circle must lie in the XY-plane (the plane containing the
    revolution axis).  The x_ax for _build_arc_data points radially outward
    from the Y-axis (i.e. +X), and y_ax points along the Y-axis.  Revolving
    around the Y-axis then sweeps the circle into the full torus.
    """

    def _build_torus(self, R=3.0, r=1.0):
        from kerf_cad_core.geom.revolve_srf import _build_arc_data
        centre = np.array([R, 0.0, 0.0])
        # Profile circle lies in XY-plane: x_ax=+X (radial), y_ax=+Y (axial)
        x_ax = np.array([1.0, 0.0, 0.0])
        y_ax = np.array([0.0, 1.0, 0.0])
        pts, wts, knots = _build_arc_data(centre, x_ax, y_ax, r, 0.0, _TWO_PI)
        cp = np.zeros((len(pts), 4))
        cp[:, :3] = pts
        cp[:, 3] = wts
        profile = NurbsCurve(degree=2, control_points=cp, knots=knots)
        return revolve_surface(profile, [0, 0, 0], [0, 1, 0]), R, r

    def test_torus_points_on_surface(self):
        """Each surface point (x,y,z) should satisfy (sqrt(x²+z²)-R)²+y²=r²."""
        surf, R, r = self._build_torus()
        n_u, n_v = 6, 10
        us = np.linspace(0.0, 1.0, n_u + 2)[1:-1]
        vs = np.linspace(0.0, 1.0, n_v + 2)[1:-1]
        for u in us:
            for v in vs:
                pt = evaluate_revolve(surf, u, v)
                rho = math.sqrt(pt[0]**2 + pt[2]**2)
                val = (rho - R)**2 + pt[1]**2
                assert val == pytest.approx(r**2, abs=1e-7), f"u={u},v={v}: val={val}"


# ---------------------------------------------------------------------------
# 7. Partial-angle sweeps
# ---------------------------------------------------------------------------

class TestPartialAngle:
    def test_90_sweep_boundary_points(self):
        """v=0 → start angle, v=1 → start+π/2.

        Revolving around +Y with right-hand rule rotates from +X toward -Z
        (clockwise when viewed from above).  At 90° the radial direction is -Z.
        """
        r = 2.0
        profile = _make_line_profile([r, 0.0, 0.0], [r, 1.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0], 0.0, _PI / 2)
        # At v=0, u=0.5: point should be at (r, 0.5, 0)
        pt_start = evaluate_revolve(surf, 0.5, 0.0)
        assert pt_start[0] == pytest.approx(r, abs=1e-8)
        assert abs(pt_start[2]) < 1e-8
        # At v=1, u=0.5: point should be at (0, 0.5, -r) — right-hand rule around +Y
        pt_end = evaluate_revolve(surf, 0.5, 1.0)
        assert abs(pt_end[0]) < 1e-8
        assert pt_end[2] == pytest.approx(-r, abs=1e-8)

    def test_180_sweep_midpoint(self):
        """At v=0.5 of a 180° sweep we should be at 90° (x=0, z=-r).

        Right-hand rotation around +Y takes +X toward -Z.
        """
        r = 2.0
        profile = _make_line_profile([r, 0.0, 0.0], [r, 1.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0], 0.0, _PI)
        pt_mid = evaluate_revolve(surf, 0.5, 0.5)
        assert abs(pt_mid[0]) < 1e-7
        assert pt_mid[2] == pytest.approx(-r, abs=1e-7)

    def test_partial_angle_radial_distance(self):
        """All sampled points of a partial-sweep cylinder should be at radius r."""
        r = 1.5
        profile = _make_line_profile([r, 0.0, 0.0], [r, 2.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0], 0.0, _PI * 1.5)
        for u in np.linspace(0.01, 0.99, 5):
            for v in np.linspace(0.01, 0.99, 8):
                pt = evaluate_revolve(surf, u, v)
                radial = math.sqrt(pt[0]**2 + pt[2]**2)
                assert radial == pytest.approx(r, abs=1e-8)


# ---------------------------------------------------------------------------
# 8. Pole degeneracy: profile point on axis
# ---------------------------------------------------------------------------

class TestPoleDegeneracy:
    def test_apex_maps_to_axis_point(self):
        """A profile point at radius=0 should produce a pole on the axis."""
        # Profile: line from axis origin to (1, 1, 0)
        profile = _make_line_profile([0.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0])
        # All control points in row 0 should map to (0,0,0)
        cp = surf.control_points
        for j in range(cp.shape[1]):
            pt = cp[0, j, :3]
            assert np.linalg.norm(pt) < 1e-10, f"j={j}: pt={pt}"

    def test_apex_evaluate_near_pole(self):
        """Evaluating near u=0 should give a point near the axis."""
        profile = _make_line_profile([0.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0])
        for v in [0.0, 0.5, 1.0]:
            pt = evaluate_revolve(surf, 0.0, v)
            assert np.linalg.norm(pt) < 1e-10

    def test_tip_cone(self):
        """Revolve a line from (0,1,0) to (r,0,0) → cone apex at (0,1,0)."""
        r = 2.0
        profile = _make_line_profile([0.0, 1.0, 0.0], [r, 0.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0])
        apex = evaluate_revolve(surf, 0.0, 0.5)
        assert abs(apex[0]) < 1e-9
        assert apex[1] == pytest.approx(1.0, abs=1e-9)
        assert abs(apex[2]) < 1e-9


# ---------------------------------------------------------------------------
# 9. Weight correctness
# ---------------------------------------------------------------------------

class TestWeightCorrectness:
    def test_90_sweep_weights(self):
        """For a 90° sweep the weights should be [1, cos45, 1] per profile row."""
        r = 1.0
        profile = _make_line_profile([r, 0.0, 0.0], [r, 1.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0], 0.0, _PI / 2)
        cp = surf.control_points
        cos45 = math.cos(_PI / 4)
        for i in range(cp.shape[0]):
            assert cp[i, 0, 3] == pytest.approx(1.0, abs=1e-10)
            assert cp[i, 1, 3] == pytest.approx(cos45, abs=1e-10)
            assert cp[i, 2, 3] == pytest.approx(1.0, abs=1e-10)

    def test_360_sweep_weights_pattern(self):
        """For 360° sweep the weights should alternate 1, cos45, 1, cos45, ..."""
        r = 1.0
        profile = _make_line_profile([r, 0.0, 0.0], [r, 1.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0], 0.0, _TWO_PI)
        cp = surf.control_points
        cos45 = math.cos(_PI / 4)
        row = cp[0, :, 3]
        for j in range(len(row)):
            expected = 1.0 if (j % 2 == 0) else cos45
            assert row[j] == pytest.approx(expected, abs=1e-10), f"j={j}: w={row[j]}"

    def test_180_sweep_weights(self):
        """For 180° sweep each segment uses cos(45°) for tangent CPs."""
        r = 1.0
        profile = _make_line_profile([r, 0.0, 0.0], [r, 1.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0], 0.0, _PI)
        cp = surf.control_points
        cos45 = math.cos(_PI / 4)
        # n_arc = 5: indices 0,2,4 → w=1; indices 1,3 → w=cos45
        for i in range(cp.shape[0]):
            assert cp[i, 0, 3] == pytest.approx(1.0, abs=1e-10)
            assert cp[i, 1, 3] == pytest.approx(cos45, abs=1e-10)
            assert cp[i, 2, 3] == pytest.approx(1.0, abs=1e-10)
            assert cp[i, 3, 3] == pytest.approx(cos45, abs=1e-10)
            assert cp[i, 4, 3] == pytest.approx(1.0, abs=1e-10)


# ---------------------------------------------------------------------------
# 10. Error paths
# ---------------------------------------------------------------------------

class TestErrorPaths:
    def test_bad_sweep_zero(self):
        profile = _make_line_profile([1, 0, 0], [1, 1, 0])
        with pytest.raises(ValueError, match="end_angle must be"):
            revolve_surface(profile, [0, 0, 0], [0, 1, 0], 0.0, 0.0)

    def test_bad_sweep_negative(self):
        profile = _make_line_profile([1, 0, 0], [1, 1, 0])
        with pytest.raises(ValueError):
            revolve_surface(profile, [0, 0, 0], [0, 1, 0], 1.0, 0.5)

    def test_sweep_too_large(self):
        profile = _make_line_profile([1, 0, 0], [1, 1, 0])
        with pytest.raises(ValueError, match="2π"):
            revolve_surface(profile, [0, 0, 0], [0, 1, 0], 0.0, _TWO_PI * 2)

    def test_cap_raises(self):
        profile = _make_line_profile([1, 0, 0], [1, 1, 0])
        with pytest.raises(NotImplementedError):
            revolve_surface(profile, [0, 0, 0], [0, 1, 0], cap=True)

    def test_zero_axis_raises(self):
        profile = _make_line_profile([1, 0, 0], [1, 1, 0])
        with pytest.raises(ValueError):
            revolve_surface(profile, [0, 0, 0], [0, 0, 0])


# ---------------------------------------------------------------------------
# 11. Pappus theorem for revolving a profile segment
# ---------------------------------------------------------------------------

class TestPappus:
    def test_pappus_disk_area(self):
        """Revolving a horizontal line segment of length L at height y=c around
        Y-axis: lateral area = 2π * centroid_x * L = 2π * (r1+r2)/2 * L."""
        r1, r2 = 1.0, 3.0
        h = 0.0
        L = r2 - r1  # length of the segment
        centroid_x = (r1 + r2) / 2.0
        expected_area = _TWO_PI * centroid_x * L

        profile = _make_line_profile([r1, h, 0.0], [r2, h, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0])

        # Numerical integration
        N = 80
        du, dv = 1.0 / N, 1.0 / N
        us = np.linspace(0.5 * du, 1.0 - 0.5 * du, N)
        vs = np.linspace(0.5 * dv, 1.0 - 0.5 * dv, N)
        area = 0.0
        eps = 1e-5
        for u in us:
            for v in vs:
                pu = (evaluate_revolve(surf, min(u + eps, 0.9999), v) -
                      evaluate_revolve(surf, max(u - eps, 1e-5), v)) / (2 * eps)
                pv = (evaluate_revolve(surf, u, min(v + eps, 0.9999)) -
                      evaluate_revolve(surf, u, max(v - eps, 1e-5))) / (2 * eps)
                cross = np.cross(pu, pv)
                area += np.linalg.norm(cross) * du * dv

        assert area == pytest.approx(expected_area, rel=0.03)


# ---------------------------------------------------------------------------
# 12. rail_revolve smoke test
# ---------------------------------------------------------------------------

class TestRailRevolve:
    def _build(self):
        """Profile: vertical line at x=1; rail: circle of radius 2."""
        profile = _make_line_profile([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        # Rail: use a line at radius 2 (constant radius → same as revolve)
        rail = _make_line_profile([2.0, 0.0, 0.0], [2.0, 0.0, 0.0])
        return profile, rail

    def test_rail_revolve_returns_nurbs_surface(self):
        profile, rail = self._build()
        surf = rail_revolve(profile, rail, [0, 0, 0], [0, 1, 0])
        assert isinstance(surf, NurbsSurface)

    def test_rail_revolve_shape(self):
        profile, rail = self._build()
        surf = rail_revolve(profile, rail, [0, 0, 0], [0, 1, 0])
        assert surf.control_points.shape[2] == 4  # homogeneous

    def test_rail_revolve_degree_v_is_2(self):
        profile, rail = self._build()
        surf = rail_revolve(profile, rail, [0, 0, 0], [0, 1, 0])
        assert surf.degree_v == 2

    def test_rail_revolve_profile_on_axis_raises(self):
        """Profile with first CP on axis should raise."""
        profile = _make_line_profile([0.0, 0.0, 0.0], [0.0, 1.0, 0.0])
        rail = _make_line_profile([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        with pytest.raises(ValueError, match="axis"):
            rail_revolve(profile, rail, [0, 0, 0], [0, 1, 0])


# ---------------------------------------------------------------------------
# 13. evaluate_revolve at parameter boundaries
# ---------------------------------------------------------------------------

class TestEvaluateRevolveBoundaries:
    def test_start_angle_boundary(self):
        """At v=0 the surface should coincide with the profile's start position."""
        r = 2.5
        profile = _make_line_profile([r, 0.0, 0.0], [r, 1.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0])
        pt = evaluate_revolve(surf, 0.5, 0.0)
        assert pt[0] == pytest.approx(r, abs=1e-8)
        assert abs(pt[2]) < 1e-8

    def test_full_circle_seam(self):
        """v=0 and v=1 should give the same point (full 360° seam)."""
        r = 2.5
        profile = _make_line_profile([r, 0.0, 0.0], [r, 1.0, 0.0])
        surf = revolve_surface(profile, [0, 0, 0], [0, 1, 0])
        for u in [0.1, 0.5, 0.9]:
            pt0 = evaluate_revolve(surf, u, 0.0)
            pt1 = evaluate_revolve(surf, u, 1.0)
            assert np.allclose(pt0, pt1, atol=1e-9), f"u={u}: {pt0} vs {pt1}"
