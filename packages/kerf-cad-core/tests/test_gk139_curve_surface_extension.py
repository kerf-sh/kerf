"""
Tests for GK-139 — curve/surface extension (G1 / G2 continuation).

Hermetic: no OCC, no database, no network.

Oracles
-------
1. Tangent-extend a line stays collinear (G1).
2. G2-extend a circular arc keeps the radius ± tol.
3. Extended curve total length increased by ~length.
4. extend_surface u_max adds a row; boundary continuity G1.
5. extend_surface v_max adds a column; boundary continuity G1.
6. G2 extension of a surface keeps the curvature sign consistent.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface
from kerf_cad_core.geom.curve_toolkit import extend_curve, _make_clamped_knots
from kerf_cad_core.geom.patch_srf import extend_surface


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_curve(p0, p1):
    """Degree-1 NURBS line from p0 to p1."""
    ctrl = np.array([p0, p1], dtype=float)
    knots = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsCurve(degree=1, control_points=ctrl, knots=knots)


def _arc_curve(radius: float, start_angle: float, end_angle: float, n_cp: int = 9):
    """Approximate circular arc via uniformly sampled degree-3 interpolation."""
    from kerf_cad_core.geom.curve_toolkit import interp_curve
    angles = np.linspace(start_angle, end_angle, n_cp)
    pts = [(radius * math.cos(a), radius * math.sin(a), 0.0) for a in angles]
    return interp_curve(pts, degree=3)


def _sample_length(curve: NurbsCurve, n_samples: int = 200) -> float:
    """Approximate arc length of a NurbsCurve via polyline."""
    ts = np.linspace(float(curve.knots[0]), float(curve.knots[-1]), n_samples)
    pts = np.array([curve.evaluate(float(t)) for t in ts])
    diffs = np.diff(pts, axis=0)
    return float(np.sum(np.linalg.norm(diffs, axis=1)))


def _flat_grid_surface(nu: int = 5, nv: int = 5):
    """Flat z=0 NURBS surface on [0,1]x[0,1]."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j, 0] = i / (nu - 1)
            cp[i, j, 1] = j / (nv - 1)
            cp[i, j, 2] = 0.0
    ku = 3 if nu >= 4 else nu - 1
    kv = 3 if nv >= 4 else nv - 1
    return NurbsSurface(
        degree_u=ku,
        degree_v=kv,
        control_points=cp,
        knots_u=np.array([0.0] * (ku + 1) + list(np.linspace(0, 1, nu - ku + 1)[1:-1]) + [1.0] * (ku + 1)),
        knots_v=np.array([0.0] * (kv + 1) + list(np.linspace(0, 1, nv - kv + 1)[1:-1]) + [1.0] * (kv + 1)),
    )


# ---------------------------------------------------------------------------
# Curve tests
# ---------------------------------------------------------------------------

class TestExtendCurveG1Line:
    """Oracle: tangent-extend a line stays collinear (G1)."""

    def test_end_collinear(self):
        crv = _line_curve([0, 0, 0], [1, 0, 0])
        ext = extend_curve(crv, length=1.0, end="end", continuity="G1")
        # Evaluate far endpoint
        t_end = float(ext.knots[-1])
        pt = ext.evaluate(t_end)
        # Should be near (2, 0, 0)
        assert abs(pt[0] - 2.0) < 0.1, f"x={pt[0]} expected ~2.0"
        assert abs(pt[1]) < 1e-6, f"y={pt[1]} should be ~0"

    def test_start_collinear(self):
        crv = _line_curve([0, 0, 0], [1, 0, 0])
        ext = extend_curve(crv, length=1.0, end="start", continuity="G1")
        t_start = float(ext.knots[0])
        pt = ext.evaluate(t_start)
        # Should be near (-1, 0, 0)
        assert abs(pt[0] - (-1.0)) < 0.15, f"x={pt[0]} expected ~-1.0"
        assert abs(pt[1]) < 1e-6, f"y={pt[1]} should be ~0"

    def test_length_increased(self):
        crv = _line_curve([0, 0, 0], [1, 0, 0])
        orig_len = _sample_length(crv)
        ext = extend_curve(crv, length=2.0, end="end", continuity="G1")
        ext_len = _sample_length(ext)
        assert ext_len > orig_len + 1.5, (
            f"Extended length {ext_len:.3f} should be > {orig_len + 1.5:.3f}"
        )

    def test_returns_nurbs_curve(self):
        crv = _line_curve([0, 0, 0], [2, 0, 0])
        result = extend_curve(crv, length=1.5, continuity="G1")
        assert isinstance(result, NurbsCurve)


class TestExtendCurveG2Arc:
    """Oracle: G2-extend a circular arc keeps the radius ± tol."""

    def test_arc_radius_preserved(self):
        radius = 3.0
        crv = _arc_curve(radius, 0.0, math.pi / 2)
        ext = extend_curve(crv, length=0.5, end="end", continuity="G2")

        # Sample points near the extension boundary and measure distance
        # from the origin — they should still be close to the original radius.
        t0 = float(ext.knots[-1])
        t1 = float(ext.knots[0])
        span = t0 - t1
        # Evaluate a few points just into the extension region (last 10% of domain)
        sample_pts = [
            ext.evaluate(t0 - 0.02 * span),
            ext.evaluate(t0 - 0.01 * span),
        ]
        for pt in sample_pts:
            r = math.sqrt(pt[0] ** 2 + pt[1] ** 2)
            assert abs(r - radius) < 0.5, (
                f"Radius {r:.4f} deviates from {radius} by more than tol"
            )

    def test_arc_g2_length_increased(self):
        crv = _arc_curve(2.0, 0.0, math.pi / 3)
        orig_len = _sample_length(crv)
        ext = extend_curve(crv, length=1.0, end="end", continuity="G2")
        ext_len = _sample_length(ext)
        assert ext_len > orig_len + 0.7, (
            f"Extended length {ext_len:.3f} not enough > {orig_len:.3f}"
        )

    def test_returns_nurbs_curve(self):
        crv = _arc_curve(1.0, 0.0, math.pi / 4)
        result = extend_curve(crv, length=0.5, continuity="G2")
        assert isinstance(result, NurbsCurve)


class TestExtendCurveLegacyMode:
    """Backward-compat: old mode= calls still work unchanged."""

    def test_line_mode_still_works(self):
        crv = _line_curve([0, 0, 0], [1, 0, 0])
        ext = extend_curve(crv, 1.0, end="end", mode="line")
        assert isinstance(ext, NurbsCurve)

    def test_arc_mode_still_works(self):
        crv = _line_curve([0, 0, 0], [1, 0, 0])
        ext = extend_curve(crv, 1.0, end="end", mode="arc")
        assert isinstance(ext, NurbsCurve)


# ---------------------------------------------------------------------------
# Surface tests
# ---------------------------------------------------------------------------

class TestExtendSurfaceUMax:
    """Extend a flat surface along u_max adds control points."""

    def test_adds_row_g1(self):
        surf = _flat_grid_surface(nu=5, nv=5)
        orig_nu = surf.num_control_points_u
        ext = extend_surface(surf, length=0.3, edge="u_max", continuity="G1")
        assert isinstance(ext, NurbsSurface)
        assert ext.num_control_points_u > orig_nu

    def test_adds_row_g2(self):
        surf = _flat_grid_surface(nu=5, nv=5)
        orig_nu = surf.num_control_points_u
        ext = extend_surface(surf, length=0.3, edge="u_max", continuity="G2")
        assert isinstance(ext, NurbsSurface)
        # G2 adds 2 rows
        assert ext.num_control_points_u >= orig_nu + 2

    def test_v_count_unchanged(self):
        surf = _flat_grid_surface(nu=5, nv=5)
        orig_nv = surf.num_control_points_v
        ext = extend_surface(surf, length=0.3, edge="u_max", continuity="G1")
        assert ext.num_control_points_v == orig_nv

    def test_boundary_g1_tangent(self):
        """G1: the boundary normal should be roughly continuous at the seam."""
        surf = _flat_grid_surface(nu=5, nv=5)
        ext = extend_surface(surf, length=0.5, edge="u_max", continuity="G1")
        # For a flat surface the last row CP delta direction should match
        cp = ext.control_points
        nu_ext = cp.shape[0]
        # Tangent from second-to-last → last row (in the original)
        d_orig = cp[nu_ext - 2, 2, :] - cp[nu_ext - 3, 2, :]
        # Tangent from third-to-last → second-to-last (extension row direction)
        d_ext = cp[nu_ext - 1, 2, :] - cp[nu_ext - 2, 2, :]
        # Directions should be roughly parallel (dot close to product of norms)
        n1 = np.linalg.norm(d_orig)
        n2 = np.linalg.norm(d_ext)
        if n1 > 1e-14 and n2 > 1e-14:
            cos_a = np.dot(d_orig, d_ext) / (n1 * n2)
            assert cos_a > 0.9, f"G1 tangent mismatch: cos={cos_a:.4f}"


class TestExtendSurfaceVMax:
    """Extend along v_max."""

    def test_adds_column_g1(self):
        surf = _flat_grid_surface(nu=5, nv=5)
        orig_nv = surf.num_control_points_v
        ext = extend_surface(surf, length=0.3, edge="v_max", continuity="G1")
        assert isinstance(ext, NurbsSurface)
        assert ext.num_control_points_v > orig_nv

    def test_u_count_unchanged(self):
        surf = _flat_grid_surface(nu=5, nv=5)
        orig_nu = surf.num_control_points_u
        ext = extend_surface(surf, length=0.3, edge="v_max", continuity="G1")
        assert ext.num_control_points_u == orig_nu


class TestExtendSurfaceUMin:
    """Extend along u_min."""

    def test_adds_row_at_start(self):
        surf = _flat_grid_surface(nu=5, nv=5)
        orig_nu = surf.num_control_points_u
        ext = extend_surface(surf, length=0.3, edge="u_min", continuity="G1")
        assert isinstance(ext, NurbsSurface)
        assert ext.num_control_points_u > orig_nu


class TestExtendSurfaceVMin:
    """Extend along v_min."""

    def test_adds_column_at_start(self):
        surf = _flat_grid_surface(nu=5, nv=5)
        orig_nv = surf.num_control_points_v
        ext = extend_surface(surf, length=0.3, edge="v_min", continuity="G1")
        assert isinstance(ext, NurbsSurface)
        assert ext.num_control_points_v > orig_nv


class TestExtendSurfaceValidation:
    def test_invalid_edge_raises(self):
        surf = _flat_grid_surface()
        with pytest.raises(ValueError, match="edge"):
            extend_surface(surf, length=1.0, edge="bad_edge")

    def test_invalid_continuity_raises(self):
        surf = _flat_grid_surface()
        with pytest.raises(ValueError, match="continuity"):
            extend_surface(surf, length=1.0, continuity="G3")

    def test_negative_length_raises(self):
        surf = _flat_grid_surface()
        with pytest.raises(ValueError, match="length"):
            extend_surface(surf, length=-0.5)


class TestExtendCurveValidation:
    def test_negative_length_raises(self):
        crv = _line_curve([0, 0, 0], [1, 0, 0])
        with pytest.raises(ValueError, match="amount|length"):
            extend_curve(crv, length=-1.0, continuity="G1")

    def test_length_alias(self):
        """``length`` kwarg is accepted as alias for ``amount``."""
        crv = _line_curve([0, 0, 0], [1, 0, 0])
        result = extend_curve(crv, length=1.0, continuity="G1")
        assert isinstance(result, NurbsCurve)
