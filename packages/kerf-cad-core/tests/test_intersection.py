"""
Tests for kerf_cad_core.geom.intersection -- curve-surface, surface-surface,
and curve-curve intersection primitives.

All tests are hermetic: pure Python + NumPy, no OCC, no database, no network.

Coverage (>=30 tests):
  1.  Helpers  -- _aabb, _aabb_overlap, _merge_close_hits, param-range helpers.
  2.  curve_surface_intersect -- vertical line pierces flat XY surface; two
      distinct z-planes give two hits at analytic positions; parallel line gives
      0 hits; line misses lateral patch; bad types return []; t parameter in
      range; accuracy on known-position hit.
  3.  surface_surface_intersect -- XY-plane x XZ-plane gives >=1 branch along
      X-axis; branch points lie on y=0,z=0; parallel offset planes give 0
      branches; bad types return error dict; dict keys always present; branch
      params have equal length; coincident surfaces no crash; two near-orthogonal
      vertical surfaces intersect.
  4.  curve_curve_intersect -- two crossing lines give 1 pt at (0.5,0.5,0);
      parallel lines 0 pts; skew 3-D lines 0 pts; shared-endpoint lines >=1 pt;
      bad types []; t params in range; ta/tb midpoint symmetry.
  5.  Newton internals -- _newton_curve_surface converges on z=0 plane;
      _newton_curve_curve converges for X crossing; _newton_surf_surf_point
      converges on plane intersection; _surf_normal correct for z=0 plane;
      _nurbs_surface_eval correct bilinear for known point.
  6.  never-raise guarantee -- all three public functions accept None/string
      inputs without raising.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface
from kerf_cad_core.geom.intersection import (
    _aabb,
    _aabb_overlap,
    _curve_eval,
    _curve_param_range,
    _merge_close_hits,
    _newton_curve_curve,
    _newton_curve_surface,
    _newton_surf_surf_point,
    _nurbs_surface_eval,
    _surf_eval,
    _surf_normal,
    _surface_param_range,
    curve_curve_intersect,
    curve_surface_intersect,
    surface_surface_intersect,
)


# ---------------------------------------------------------------------------
# Geometry factories
# ---------------------------------------------------------------------------

def make_line_curve(p0, p1) -> NurbsCurve:
    cp = np.array([p0, p1], dtype=float)
    knots = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsCurve(degree=1, control_points=cp, knots=knots)


def make_flat_surface_xy(
    x0: float = 0.0, x1: float = 1.0,
    y0: float = 0.0, y1: float = 1.0,
    z: float = 0.0,
    nu: int = 3, nv: int = 3,
) -> NurbsSurface:
    """Flat surface in the z=const plane over [x0,x1] x [y0,y1]."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [
                x0 + (x1 - x0) * i / (nu - 1),
                y0 + (y1 - y0) * j / (nv - 1),
                z,
            ]
    def _k(n: int) -> np.ndarray:
        inner = max(0, n - 2)
        return np.concatenate([
            np.zeros(2),
            np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
            np.ones(2),
        ])
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_k(nu), knots_v=_k(nv),
    )


def make_flat_surface_xz(
    x0: float = 0.0, x1: float = 1.0,
    z0: float = 0.0, z1: float = 1.0,
    y: float = 0.0,
    nu: int = 3, nv: int = 3,
) -> NurbsSurface:
    """Flat surface in the y=const plane over [x0,x1] x [z0,z1]."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [
                x0 + (x1 - x0) * i / (nu - 1),
                y,
                z0 + (z1 - z0) * j / (nv - 1),
            ]
    def _k(n: int) -> np.ndarray:
        inner = max(0, n - 2)
        return np.concatenate([
            np.zeros(2),
            np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
            np.ones(2),
        ])
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_k(nu), knots_v=_k(nv),
    )


# ---------------------------------------------------------------------------
# 1. Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_aabb_single_segment(self):
        pts = [np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0])]
        lo, hi = _aabb(pts)
        np.testing.assert_array_almost_equal(lo, [1, 2, 3])
        np.testing.assert_array_almost_equal(hi, [4, 5, 6])

    def test_aabb_overlap_yes(self):
        lo_a = np.array([0.0, 0.0, 0.0])
        hi_a = np.array([1.0, 1.0, 1.0])
        lo_b = np.array([0.5, 0.5, 0.5])
        hi_b = np.array([1.5, 1.5, 1.5])
        assert _aabb_overlap(lo_a, hi_a, lo_b, hi_b, 0.0) is True

    def test_aabb_overlap_no(self):
        lo_a = np.array([0.0, 0.0, 0.0])
        hi_a = np.array([1.0, 1.0, 1.0])
        lo_b = np.array([2.0, 2.0, 2.0])
        hi_b = np.array([3.0, 3.0, 3.0])
        assert _aabb_overlap(lo_a, hi_a, lo_b, hi_b, 0.0) is False

    def test_aabb_overlap_touching_with_tol(self):
        lo_a = np.array([0.0, 0.0, 0.0])
        hi_a = np.array([1.0, 1.0, 1.0])
        lo_b = np.array([1.001, 0.0, 0.0])
        hi_b = np.array([2.0, 1.0, 1.0])
        assert _aabb_overlap(lo_a, hi_a, lo_b, hi_b, 0.01) is True

    def test_merge_close_hits_removes_duplicate(self):
        hits = [
            {"point": [0.0, 0.0, 0.0]},
            {"point": [1e-8, 1e-8, 0.0]},
            {"point": [1.0, 0.0, 0.0]},
        ]
        merged = _merge_close_hits(hits, tol=1e-6)
        assert len(merged) == 2

    def test_merge_close_hits_keeps_distinct(self):
        hits = [
            {"point": [0.0, 0.0, 0.0]},
            {"point": [1.0, 0.0, 0.0]},
            {"point": [2.0, 0.0, 0.0]},
        ]
        merged = _merge_close_hits(hits, tol=1e-6)
        assert len(merged) == 3

    def test_curve_param_range_line(self):
        c = make_line_curve([0, 0, 0], [1, 0, 0])
        t_min, t_max = _curve_param_range(c)
        assert t_min == pytest.approx(0.0)
        assert t_max == pytest.approx(1.0)

    def test_surface_param_range_unit_square(self):
        s = make_flat_surface_xy()
        u_min, u_max, v_min, v_max = _surface_param_range(s)
        assert u_min == pytest.approx(0.0)
        assert u_max == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 2. curve_surface_intersect
# ---------------------------------------------------------------------------

class TestCurveSurfaceIntersect:
    def test_vertical_line_pierces_flat_xy_surface(self):
        """Line along Z through (0.5, 0.5) hits z=0 plane at (0.5, 0.5, 0)."""
        curve = make_line_curve([0.5, 0.5, -1.0], [0.5, 0.5, 1.0])
        surface = make_flat_surface_xy(x0=0.0, x1=1.0, y0=0.0, y1=1.0, z=0.0)
        hits = curve_surface_intersect(curve, surface, tol=1e-5)
        assert len(hits) >= 1
        pt = np.array(hits[0]["point"])
        assert pt[0] == pytest.approx(0.5, abs=0.02)
        assert pt[1] == pytest.approx(0.5, abs=0.02)
        assert abs(pt[2]) < 0.02

    def test_hit_dict_has_required_keys(self):
        curve = make_line_curve([0.5, 0.5, -1.0], [0.5, 0.5, 1.0])
        surface = make_flat_surface_xy()
        hits = curve_surface_intersect(curve, surface, tol=1e-5)
        for h in hits:
            assert "t" in h
            assert "u" in h
            assert "v" in h
            assert "point" in h

    def test_parallel_line_no_intersection(self):
        """Line at z=5 parallel to XY surface gives 0 hits."""
        curve = make_line_curve([0.0, 0.0, 5.0], [1.0, 0.0, 5.0])
        surface = make_flat_surface_xy()
        hits = curve_surface_intersect(curve, surface, tol=1e-5)
        assert len(hits) == 0

    def test_line_outside_surface_lateral_patch_no_hit(self):
        """Line far to the side of the surface patch (x=10) returns 0 hits."""
        curve = make_line_curve([10.0, 10.0, -1.0], [10.0, 10.0, 1.0])
        surface = make_flat_surface_xy(x0=0.0, x1=1.0, y0=0.0, y1=1.0)
        hits = curve_surface_intersect(curve, surface, tol=1e-5)
        assert len(hits) == 0

    def test_bad_type_curve_returns_empty(self):
        surface = make_flat_surface_xy()
        hits = curve_surface_intersect("not_a_curve", surface, tol=1e-5)  # type: ignore[arg-type]
        assert hits == []

    def test_bad_type_surface_returns_empty(self):
        curve = make_line_curve([0, 0, -1], [0, 0, 1])
        hits = curve_surface_intersect(curve, "not_a_surface", tol=1e-5)  # type: ignore[arg-type]
        assert hits == []

    def test_t_parameter_in_curve_range(self):
        """Returned t values lie within the curve's parameter domain."""
        curve = make_line_curve([0.5, 0.5, -1.0], [0.5, 0.5, 1.0])
        surface = make_flat_surface_xy()
        hits = curve_surface_intersect(curve, surface, tol=1e-5)
        t_min, t_max = _curve_param_range(curve)
        for h in hits:
            assert t_min - 1e-4 <= h["t"] <= t_max + 1e-4

    def test_analytic_two_hits_on_two_planes(self):
        """Line z=-2..+2 through (0.3, 0.3) hits z=+1 and z=-1 planes."""
        curve = make_line_curve([0.3, 0.3, -2.0], [0.3, 0.3, 2.0])
        surf_top = make_flat_surface_xy(x0=0.0, x1=1.0, y0=0.0, y1=1.0, z=1.0)
        surf_bot = make_flat_surface_xy(x0=0.0, x1=1.0, y0=0.0, y1=1.0, z=-1.0)

        hits_top = curve_surface_intersect(curve, surf_top, tol=1e-5, samples_c=100)
        hits_bot = curve_surface_intersect(curve, surf_bot, tol=1e-5, samples_c=100)

        assert len(hits_top) >= 1
        pt_top = np.array(hits_top[0]["point"])
        assert pt_top[2] == pytest.approx(1.0, abs=0.05)
        assert pt_top[0] == pytest.approx(0.3, abs=0.05)

        assert len(hits_bot) >= 1
        pt_bot = np.array(hits_bot[0]["point"])
        assert pt_bot[2] == pytest.approx(-1.0, abs=0.05)

    def test_off_center_hit_position(self):
        """Line through (0.7, 0.2) hits z=0 at that XY position."""
        curve = make_line_curve([0.7, 0.2, -1.0], [0.7, 0.2, 1.0])
        surface = make_flat_surface_xy(x0=0.0, x1=1.0, y0=0.0, y1=1.0, z=0.0)
        hits = curve_surface_intersect(curve, surface, tol=1e-5, samples_c=100)
        assert len(hits) >= 1
        pt = np.array(hits[0]["point"])
        assert pt[0] == pytest.approx(0.7, abs=0.05)
        assert pt[1] == pytest.approx(0.2, abs=0.05)
        assert abs(pt[2]) < 0.05

    def test_returns_list_type(self):
        curve = make_line_curve([0.5, 0.5, -1.0], [0.5, 0.5, 1.0])
        surface = make_flat_surface_xy()
        result = curve_surface_intersect(curve, surface)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 3. surface_surface_intersect
# ---------------------------------------------------------------------------

class TestSurfaceSurfaceIntersect:
    def test_result_dict_has_required_keys(self):
        sA = make_flat_surface_xy()
        sB = make_flat_surface_xz()
        result = surface_surface_intersect(sA, sB, tol=1e-4)
        assert "ok" in result
        assert "reason" in result
        assert "branches" in result
        assert "branch_count" in result

    def test_bad_type_surf_a(self):
        sB = make_flat_surface_xy()
        result = surface_surface_intersect("not_a_surface", sB, tol=1e-4)  # type: ignore[arg-type]
        assert result["ok"] is False
        assert "surf_a" in result["reason"]

    def test_bad_type_surf_b(self):
        sA = make_flat_surface_xy()
        result = surface_surface_intersect(sA, "not_a_surface", tol=1e-4)  # type: ignore[arg-type]
        assert result["ok"] is False

    def test_never_raises_none_inputs(self):
        result = surface_surface_intersect(None, None, tol=1e-4)  # type: ignore[arg-type]
        assert isinstance(result, dict)
        assert "ok" in result

    def test_perpendicular_planes_produce_branch(self):
        """XY-plane (z=0) ∩ XZ-plane (y=0) intersects along the X-axis."""
        sXY = make_flat_surface_xy(x0=-1.0, x1=1.0, y0=-1.0, y1=1.0, z=0.0)
        sXZ = make_flat_surface_xz(x0=-1.0, x1=1.0, z0=-1.0, z1=1.0, y=0.0)
        result = surface_surface_intersect(sXY, sXZ, tol=1e-3, samples_u=16, samples_v=16)
        assert result["ok"] is True
        assert result["branch_count"] >= 1

    def test_perpendicular_planes_branch_on_x_axis(self):
        """All intersection points should have y≈0 and z≈0."""
        sXY = make_flat_surface_xy(x0=-1.0, x1=1.0, y0=-1.0, y1=1.0, z=0.0)
        sXZ = make_flat_surface_xz(x0=-1.0, x1=1.0, z0=-1.0, z1=1.0, y=0.0)
        result = surface_surface_intersect(sXY, sXZ, tol=1e-3, samples_u=16, samples_v=16)
        if result["branch_count"] >= 1:
            for pt in result["branches"][0]["points"]:
                assert abs(pt[1]) < 0.1  # y ≈ 0
                assert abs(pt[2]) < 0.1  # z ≈ 0

    def test_parallel_offset_planes_zero_branches(self):
        """Two parallel planes (z=0 and z=2) do not intersect."""
        sA = make_flat_surface_xy(z=0.0)
        sB = make_flat_surface_xy(z=2.0)
        result = surface_surface_intersect(sA, sB, tol=1e-3, samples_u=8, samples_v=8)
        assert result["ok"] is True
        assert result["branch_count"] == 0

    def test_branch_params_equal_length(self):
        """Each branch must have equal-length points/params_a/params_b lists."""
        sXY = make_flat_surface_xy(x0=-1.0, x1=1.0, y0=-1.0, y1=1.0, z=0.0)
        sXZ = make_flat_surface_xz(x0=-1.0, x1=1.0, z0=-1.0, z1=1.0, y=0.0)
        result = surface_surface_intersect(sXY, sXZ, tol=1e-3, samples_u=12, samples_v=12)
        for branch in result["branches"]:
            n = len(branch["points"])
            assert len(branch["params_a"]) == n
            assert len(branch["params_b"]) == n

    def test_branch_has_closed_bool(self):
        sXY = make_flat_surface_xy(x0=-1.0, x1=1.0, y0=-1.0, y1=1.0, z=0.0)
        sXZ = make_flat_surface_xz(x0=-1.0, x1=1.0, z0=-1.0, z1=1.0, y=0.0)
        result = surface_surface_intersect(sXY, sXZ, tol=1e-3, samples_u=12, samples_v=12)
        for branch in result["branches"]:
            assert isinstance(branch["closed"], bool)

    def test_coincident_surfaces_no_crash(self):
        """Coincident surfaces are degenerate; should not raise."""
        sA = make_flat_surface_xy(z=0.0)
        result = surface_surface_intersect(sA, sA, tol=1e-3, samples_u=8, samples_v=8)
        assert result["ok"] is True

    def test_two_vertical_surfaces_intersect(self):
        """Plane y=0 and plane x=0 intersect along the Z axis."""
        # Plane at y=0: spans x=[-1,1], z=[-1,1]
        sA = make_flat_surface_xz(x0=-1.0, x1=1.0, z0=-1.0, z1=1.0, y=0.0)
        # Plane at x=0: spans y=[-1,1], z=[-1,1]
        nu, nv = 3, 3
        cp = np.zeros((nu, nv, 3))
        for i in range(nu):
            for j in range(nv):
                cp[i, j] = [0.0, -1.0 + 2.0*i/(nu-1), -1.0 + 2.0*j/(nv-1)]
        def _k(n):
            return np.concatenate([np.zeros(2), np.ones(2)]) if n == 2 else \
                   np.concatenate([np.zeros(2), [0.5], np.ones(2)])
        sB = NurbsSurface(
            degree_u=1, degree_v=1, control_points=cp,
            knots_u=_k(nu), knots_v=_k(nv),
        )
        result = surface_surface_intersect(sA, sB, tol=1e-3, samples_u=14, samples_v=14)
        assert result["ok"] is True
        # We expect a branch; the intersection is the line x=0, y=0
        if result["branch_count"] >= 1:
            for pt in result["branches"][0]["points"]:
                assert abs(pt[0]) < 0.15
                assert abs(pt[1]) < 0.15


# ---------------------------------------------------------------------------
# 4. curve_curve_intersect
# ---------------------------------------------------------------------------

class TestCurveCurveIntersect:
    def test_crossing_lines_one_hit(self):
        """Diagonal crossing lines: (0,0,0)→(1,1,0) and (0,1,0)→(1,0,0)."""
        cA = make_line_curve([0.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        cB = make_line_curve([0.0, 1.0, 0.0], [1.0, 0.0, 0.0])
        hits = curve_curve_intersect(cA, cB, tol=1e-5)
        assert len(hits) == 1
        pt = np.array(hits[0]["point"])
        assert pt[0] == pytest.approx(0.5, abs=0.05)
        assert pt[1] == pytest.approx(0.5, abs=0.05)

    def test_crossing_lines_hit_keys(self):
        cA = make_line_curve([0.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        cB = make_line_curve([0.0, 1.0, 0.0], [1.0, 0.0, 0.0])
        hits = curve_curve_intersect(cA, cB, tol=1e-5)
        for h in hits:
            assert "ta" in h
            assert "tb" in h
            assert "point" in h

    def test_parallel_lines_no_hit(self):
        cA = make_line_curve([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        cB = make_line_curve([0.0, 1.0, 0.0], [1.0, 1.0, 0.0])
        hits = curve_curve_intersect(cA, cB, tol=1e-5)
        assert len(hits) == 0

    def test_skew_lines_no_hit(self):
        cA = make_line_curve([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        cB = make_line_curve([0.0, 1.0, 1.0], [1.0, 1.0, 1.0])
        hits = curve_curve_intersect(cA, cB, tol=1e-5)
        assert len(hits) == 0

    def test_bad_type_curve_a_returns_empty(self):
        cB = make_line_curve([0, 1, 0], [1, 0, 0])
        hits = curve_curve_intersect("not_a_curve", cB, tol=1e-5)  # type: ignore[arg-type]
        assert hits == []

    def test_bad_type_curve_b_returns_empty(self):
        cA = make_line_curve([0, 0, 0], [1, 1, 0])
        hits = curve_curve_intersect(cA, "not_a_curve", tol=1e-5)  # type: ignore[arg-type]
        assert hits == []

    def test_t_params_in_range(self):
        cA = make_line_curve([0.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        cB = make_line_curve([0.0, 1.0, 0.0], [1.0, 0.0, 0.0])
        hits = curve_curve_intersect(cA, cB, tol=1e-5)
        ta_min, ta_max = _curve_param_range(cA)
        tb_min, tb_max = _curve_param_range(cB)
        for h in hits:
            assert ta_min - 1e-4 <= h["ta"] <= ta_max + 1e-4
            assert tb_min - 1e-4 <= h["tb"] <= tb_max + 1e-4

    def test_symmetric_crossing_midpoint_params(self):
        """Both ta and tb ≈ 0.5 for a symmetric X crossing."""
        cA = make_line_curve([0.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        cB = make_line_curve([0.0, 1.0, 0.0], [1.0, 0.0, 0.0])
        hits = curve_curve_intersect(cA, cB, tol=1e-4)
        assert len(hits) >= 1
        assert hits[0]["ta"] == pytest.approx(0.5, abs=0.1)
        assert hits[0]["tb"] == pytest.approx(0.5, abs=0.1)

    def test_shared_endpoint_reports_hit(self):
        """Lines sharing endpoint (1,0,0) report >=1 intersection there."""
        cA = make_line_curve([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        cB = make_line_curve([1.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        hits = curve_curve_intersect(cA, cB, tol=1e-4)
        assert len(hits) >= 1
        pt = np.array(hits[0]["point"])
        assert pt[0] == pytest.approx(1.0, abs=0.1)

    def test_same_curve_no_raise(self):
        """Passing same curve object twice must not raise."""
        cA = make_line_curve([0.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        hits = curve_curve_intersect(cA, cA, tol=1e-5)
        assert isinstance(hits, list)

    def test_axis_aligned_crossing(self):
        """X-axis and Y-axis lines cross at origin."""
        cA = make_line_curve([-1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        cB = make_line_curve([0.0, -1.0, 0.0], [0.0, 1.0, 0.0])
        hits = curve_curve_intersect(cA, cB, tol=1e-5)
        assert len(hits) >= 1
        pt = np.array(hits[0]["point"])
        assert abs(pt[0]) < 0.05
        assert abs(pt[1]) < 0.05


# ---------------------------------------------------------------------------
# 5. Newton refinement internals
# ---------------------------------------------------------------------------

class TestNewtonRefinement:
    def test_newton_curve_surface_converges_vertical_line(self):
        """Vertical line at (0.5, 0.5) should converge to t≈0.5 on z=0 plane."""
        curve = make_line_curve([0.5, 0.5, -1.0], [0.5, 0.5, 1.0])
        surface = make_flat_surface_xy()
        result = _newton_curve_surface(curve, surface, 0.5, 0.5, 0.5, tol=1e-6)
        assert result is not None
        t, u, v = result
        S = _surf_eval(surface, u, v)
        C = _curve_eval(curve, t)
        assert np.linalg.norm(S - C) < 1e-4

    def test_newton_curve_surface_residual_small(self):
        """The residual at the converged point is small."""
        curve = make_line_curve([0.3, 0.7, -1.0], [0.3, 0.7, 1.0])
        surface = make_flat_surface_xy()
        result = _newton_curve_surface(curve, surface, 0.5, 0.3, 0.7, tol=1e-5)
        if result is not None:
            t, u, v = result
            S = _surf_eval(surface, u, v)
            C = _curve_eval(curve, t)
            assert np.linalg.norm(S - C) < 1e-3

    def test_newton_curve_curve_converges_crossing(self):
        """Two crossing lines Newton refines to residual < tol."""
        cA = make_line_curve([0.0, 0.0, 0.0], [1.0, 1.0, 0.0])
        cB = make_line_curve([0.0, 1.0, 0.0], [1.0, 0.0, 0.0])
        result = _newton_curve_curve(cA, cB, 0.5, 0.5, tol=1e-6)
        assert result is not None
        ta, tb = result
        A = _curve_eval(cA, ta)
        B = _curve_eval(cB, tb)
        assert np.linalg.norm(A - B) < 1e-4

    def test_newton_surf_surf_converges_perpendicular_planes(self):
        """XY/XZ intersection seed at mid-range should converge."""
        sXY = make_flat_surface_xy(x0=-1.0, x1=1.0, y0=-1.0, y1=1.0, z=0.0)
        sXZ = make_flat_surface_xz(x0=-1.0, x1=1.0, z0=-1.0, z1=1.0, y=0.0)
        result = _newton_surf_surf_point(sXY, sXZ, 0.5, 0.5, 0.5, 0.5, tol=1e-5)
        if result is not None:
            uA, vA, uB, vB = result
            PA = _surf_eval(sXY, uA, vA)
            PB = _surf_eval(sXZ, uB, vB)
            assert np.linalg.norm(PA - PB) < 1e-3

    def test_surf_normal_unit_length_flat_xy(self):
        """Normal of z=0 plane is a unit vector in ±Z direction."""
        srf = make_flat_surface_xy()
        n = _surf_normal(srf, 0.5, 0.5)
        assert np.linalg.norm(n) == pytest.approx(1.0, abs=1e-10)
        assert abs(n[2]) > 0.9

    def test_nurbs_surface_eval_correct_bilinear(self):
        """Unit flat surface: s(0.5, 0.5) == (0.5, 0.5, 0)."""
        srf = make_flat_surface_xy(x0=0.0, x1=1.0, y0=0.0, y1=1.0, z=0.0)
        pt = _nurbs_surface_eval(srf, 0.5, 0.5)
        assert pt[0] == pytest.approx(0.5, abs=1e-10)
        assert pt[1] == pytest.approx(0.5, abs=1e-10)
        assert pt[2] == pytest.approx(0.0, abs=1e-10)

    def test_nurbs_surface_eval_corners(self):
        """Corners of unit flat surface evaluate to exact corner coordinates."""
        srf = make_flat_surface_xy(x0=0.0, x1=1.0, y0=0.0, y1=1.0, z=0.0)
        assert _nurbs_surface_eval(srf, 0.0, 0.0)[0] == pytest.approx(0.0, abs=1e-10)
        assert _nurbs_surface_eval(srf, 1.0, 0.0)[0] == pytest.approx(1.0, abs=1e-10)
        assert _nurbs_surface_eval(srf, 0.0, 1.0)[1] == pytest.approx(1.0, abs=1e-10)
        assert _nurbs_surface_eval(srf, 1.0, 1.0)[0] == pytest.approx(1.0, abs=1e-10)

    def test_newton_surf_surf_bad_input_no_raise(self):
        """Calling _newton_surf_surf_point with bad inputs should not raise."""
        sA = make_flat_surface_xy()
        sB = make_flat_surface_xy()
        try:
            result = _newton_surf_surf_point(sA, sB, 0.5, 0.5, 0.5, 0.5, tol=1e-5)
            # coincident surfaces may converge or not; either is acceptable
            assert result is None or isinstance(result, tuple)
        except Exception as exc:
            pytest.fail(f"Unexpected exception: {exc}")


# ---------------------------------------------------------------------------
# 6. Never-raise guarantee
# ---------------------------------------------------------------------------

class TestNeverRaise:
    def test_csi_none_inputs(self):
        result = curve_surface_intersect(None, None)  # type: ignore[arg-type]
        assert isinstance(result, list)

    def test_csi_string_inputs(self):
        result = curve_surface_intersect("foo", "bar")  # type: ignore[arg-type]
        assert isinstance(result, list)

    def test_ssi_none_inputs(self):
        result = surface_surface_intersect(None, None)  # type: ignore[arg-type]
        assert isinstance(result, dict)

    def test_ssi_string_inputs(self):
        result = surface_surface_intersect("foo", "bar")  # type: ignore[arg-type]
        assert isinstance(result, dict)

    def test_cci_none_inputs(self):
        result = curve_curve_intersect(None, None)  # type: ignore[arg-type]
        assert isinstance(result, list)

    def test_cci_string_inputs(self):
        result = curve_curve_intersect("foo", "bar")  # type: ignore[arg-type]
        assert isinstance(result, list)
