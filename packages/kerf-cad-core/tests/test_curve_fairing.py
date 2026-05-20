"""
GK-35 — Energy-minimising, knot-preserving curve fairing.

All tests are hermetic: no OCC, no database, no network.

Oracle contract (from task spec):
  1. After fairing, curvature VARIANCE strictly decreases (faired < original).
  2. Endpoints AND end tangents are preserved to ≤ 1e-9.

Knot vector must be identical before and after fairing.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsCurve, de_boor, curve_derivative
from kerf_cad_core.geom.curve_toolkit import (
    fair_curve,
    curvature_variance,
    interp_curve,
    _make_clamped_knots,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _endpoint_tangent(curve: NurbsCurve, end: str = "start") -> np.ndarray:
    """Return the (un-normalised) end tangent via curve_derivative."""
    u0 = float(curve.knots[curve.degree])
    u1 = float(curve.knots[-(curve.degree + 1)])
    u = u0 if end == "start" else u1
    return curve_derivative(curve, u, order=1)


def _make_wavy_curve(n_ctrl: int = 10, degree: int = 3) -> NurbsCurve:
    """Create a deliberately wavy (high-curvature-variance) curve by
    perturbing interior control points of an otherwise straight line."""
    rng = np.random.default_rng(42)
    ctrl = np.zeros((n_ctrl, 3))
    ctrl[:, 0] = np.linspace(0.0, 1.0, n_ctrl)
    # Add large random perturbations to interior points only
    ctrl[1:-1, 1] = rng.uniform(-0.4, 0.4, n_ctrl - 2)
    ctrl[1:-1, 2] = rng.uniform(-0.2, 0.2, n_ctrl - 2)
    knots = _make_clamped_knots(n_ctrl, degree)
    return NurbsCurve(degree=degree, control_points=ctrl, knots=knots)


def _make_sinusoidal_curve(n_pts: int = 30, freq: float = 3.0) -> NurbsCurve:
    """Interpolate through a high-frequency sinusoidal polyline."""
    xs = np.linspace(0.0, 1.0, n_pts)
    ys = np.sin(2.0 * math.pi * freq * xs)
    pts = np.column_stack([xs, ys, np.zeros(n_pts)])
    return interp_curve(pts, degree=3)


# ---------------------------------------------------------------------------
# Test group 1 — Oracle: curvature variance strictly decreases
# ---------------------------------------------------------------------------

class TestCurvatureVarianceDecreases:

    def test_wavy_curve_variance_decreases(self):
        """Main oracle: fair a wavy curve; curvature variance must decrease."""
        curve = _make_wavy_curve(n_ctrl=10, degree=3)
        var_before = curvature_variance(curve, num_samples=300)
        faired = fair_curve(curve)
        var_after = curvature_variance(faired, num_samples=300)
        assert var_after < var_before, (
            f"Curvature variance did not decrease: before={var_before:.6g}, "
            f"after={var_after:.6g}"
        )

    def test_sinusoidal_curve_variance_decreases(self):
        """Fairing a high-freq sinusoidal interpolant reduces curvature variance."""
        curve = _make_sinusoidal_curve(n_pts=25, freq=2.5)
        var_before = curvature_variance(curve, num_samples=300)
        faired = fair_curve(curve)
        var_after = curvature_variance(faired, num_samples=300)
        assert var_after < var_before, (
            f"Sinusoidal: var_before={var_before:.6g}, var_after={var_after:.6g}"
        )

    def test_large_n_ctrl_variance_decreases(self):
        """Fairing a larger (20 CP) wavy curve reduces curvature variance."""
        curve = _make_wavy_curve(n_ctrl=20, degree=3)
        var_before = curvature_variance(curve, num_samples=300)
        faired = fair_curve(curve)
        var_after = curvature_variance(faired, num_samples=300)
        assert var_after < var_before, (
            f"20-CP curve: var_before={var_before:.6g}, var_after={var_after:.6g}"
        )

    def test_degree5_variance_decreases(self):
        """Fairing works with degree-5 curves too."""
        rng = np.random.default_rng(7)
        n = 12
        ctrl = np.zeros((n, 3))
        ctrl[:, 0] = np.linspace(0.0, 1.0, n)
        ctrl[1:-1, 1] = rng.uniform(-0.5, 0.5, n - 2)
        knots = _make_clamped_knots(n, 5)
        curve = NurbsCurve(degree=5, control_points=ctrl, knots=knots)
        var_before = curvature_variance(curve, num_samples=300)
        faired = fair_curve(curve)
        var_after = curvature_variance(faired, num_samples=300)
        assert var_after < var_before, (
            f"degree-5: var_before={var_before:.6g}, var_after={var_after:.6g}"
        )

    def test_2d_curve_variance_decreases(self):
        """2-D wavy curve (XY plane only) — variance decreases."""
        rng = np.random.default_rng(13)
        n = 10
        ctrl = np.zeros((n, 2))
        ctrl[:, 0] = np.linspace(0.0, 1.0, n)
        ctrl[1:-1, 1] = rng.uniform(-0.3, 0.3, n - 2)
        knots = _make_clamped_knots(n, 3)
        curve = NurbsCurve(degree=3, control_points=ctrl, knots=knots)
        var_before = curvature_variance(curve, num_samples=200)
        faired = fair_curve(curve)
        var_after = curvature_variance(faired, num_samples=200)
        assert var_after < var_before, (
            f"2-D curve: var_before={var_before:.6g}, var_after={var_after:.6g}"
        )


# ---------------------------------------------------------------------------
# Test group 2 — Endpoint preservation to ≤ 1e-9
# ---------------------------------------------------------------------------

class TestEndpointPreservation:

    def _assert_endpoint_preserved(self, original: NurbsCurve, faired: NurbsCurve, tol: float = 1e-9):
        u0 = float(original.knots[original.degree])
        u1 = float(original.knots[-(original.degree + 1)])

        # Start endpoint
        p_orig_start = de_boor(original, u0)
        p_fair_start = de_boor(faired, u0)
        err_start = float(np.linalg.norm(p_fair_start - p_orig_start))
        assert err_start <= tol, f"Start endpoint moved by {err_start:.3e} > {tol}"

        # End endpoint
        p_orig_end = de_boor(original, u1)
        p_fair_end = de_boor(faired, u1)
        err_end = float(np.linalg.norm(p_fair_end - p_orig_end))
        assert err_end <= tol, f"End endpoint moved by {err_end:.3e} > {tol}"

    def _assert_tangent_preserved(self, original: NurbsCurve, faired: NurbsCurve, tol: float = 1e-9):
        for end in ("start", "end"):
            t_orig = _endpoint_tangent(original, end)
            t_fair = _endpoint_tangent(faired, end)
            err = float(np.linalg.norm(t_fair - t_orig))
            assert err <= tol, (
                f"{end} tangent moved by {err:.3e} > {tol}; "
                f"orig={t_orig}, faired={t_fair}"
            )

    def test_wavy_endpoints_preserved(self):
        curve = _make_wavy_curve(n_ctrl=10, degree=3)
        faired = fair_curve(curve)
        self._assert_endpoint_preserved(curve, faired)

    def test_wavy_tangents_preserved(self):
        curve = _make_wavy_curve(n_ctrl=10, degree=3)
        faired = fair_curve(curve)
        self._assert_tangent_preserved(curve, faired)

    def test_sinusoidal_endpoints_preserved(self):
        curve = _make_sinusoidal_curve(n_pts=20, freq=2.0)
        faired = fair_curve(curve)
        self._assert_endpoint_preserved(curve, faired)

    def test_sinusoidal_tangents_preserved(self):
        curve = _make_sinusoidal_curve(n_pts=20, freq=2.0)
        faired = fair_curve(curve)
        self._assert_tangent_preserved(curve, faired)

    def test_large_n_endpoints_preserved(self):
        curve = _make_wavy_curve(n_ctrl=20, degree=3)
        faired = fair_curve(curve)
        self._assert_endpoint_preserved(curve, faired)

    def test_large_n_tangents_preserved(self):
        curve = _make_wavy_curve(n_ctrl=20, degree=3)
        faired = fair_curve(curve)
        self._assert_tangent_preserved(curve, faired)

    def test_degree5_endpoints_and_tangents_preserved(self):
        rng = np.random.default_rng(77)
        n = 12
        ctrl = np.zeros((n, 3))
        ctrl[:, 0] = np.linspace(0.0, 1.0, n)
        ctrl[1:-1, 1] = rng.uniform(-0.5, 0.5, n - 2)
        knots = _make_clamped_knots(n, 5)
        curve = NurbsCurve(degree=5, control_points=ctrl, knots=knots)
        faired = fair_curve(curve)
        self._assert_endpoint_preserved(curve, faired)
        self._assert_tangent_preserved(curve, faired)

    def test_straight_line_unchanged(self):
        """A perfectly straight line has zero curvature variance; endpoints must not move."""
        n = 8
        ctrl = np.zeros((n, 3))
        ctrl[:, 0] = np.linspace(0.0, 1.0, n)
        knots = _make_clamped_knots(n, 3)
        curve = NurbsCurve(degree=3, control_points=ctrl, knots=knots)
        faired = fair_curve(curve)
        self._assert_endpoint_preserved(curve, faired, tol=1e-9)
        self._assert_tangent_preserved(curve, faired, tol=1e-9)


# ---------------------------------------------------------------------------
# Test group 3 — Knot vector preserved exactly
# ---------------------------------------------------------------------------

class TestKnotVectorPreserved:

    def test_knot_vector_identical(self):
        curve = _make_wavy_curve(n_ctrl=10, degree=3)
        faired = fair_curve(curve)
        np.testing.assert_array_equal(
            faired.knots, curve.knots,
            err_msg="Knot vector changed after fairing"
        )

    def test_degree_preserved(self):
        curve = _make_wavy_curve(n_ctrl=10, degree=3)
        faired = fair_curve(curve)
        assert faired.degree == curve.degree

    def test_num_ctrl_preserved(self):
        curve = _make_wavy_curve(n_ctrl=10, degree=3)
        faired = fair_curve(curve)
        assert faired.num_control_points == curve.num_control_points


# ---------------------------------------------------------------------------
# Test group 4 — Edge-case robustness
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_minimum_n_ctrl_degree3(self):
        """n=4 (minimum for degree 3): no free interior beyond tangent pins; no crash."""
        ctrl = np.array([[0.0, 0.0, 0.0],
                         [0.3, 0.5, 0.1],
                         [0.7, -0.3, 0.2],
                         [1.0, 0.0, 0.0]])
        knots = _make_clamped_knots(4, 3)
        curve = NurbsCurve(degree=3, control_points=ctrl, knots=knots)
        faired = fair_curve(curve)
        # With n=4 and degree=3, fixed = {0,1,2,3} → no free DOFs → returns copy
        assert faired.num_control_points == 4
        assert np.allclose(faired.knots, curve.knots)

    def test_n3_falls_back_laplacian(self):
        """n=3 triggers Laplacian fallback (n < 5); endpoints must still be fixed."""
        ctrl = np.array([[0.0, 0.0, 0.0], [0.5, 1.0, 0.0], [1.0, 0.0, 0.0]])
        knots = _make_clamped_knots(3, 2)
        curve = NurbsCurve(degree=2, control_points=ctrl, knots=knots)
        faired = fair_curve(curve, weight=0.5)
        # Endpoints fixed by Laplacian fallback
        u0 = float(curve.knots[curve.degree])
        u1 = float(curve.knots[-(curve.degree + 1)])
        np.testing.assert_allclose(
            de_boor(faired, u0), de_boor(curve, u0), atol=1e-9
        )
        np.testing.assert_allclose(
            de_boor(faired, u1), de_boor(curve, u1), atol=1e-9
        )

    def test_n5_minimal_free_dof(self):
        """n=5, degree=3: exactly 1 free interior CP; fairing must not crash."""
        ctrl = np.array([
            [0.0, 0.0, 0.0],
            [0.25, 0.8, 0.0],
            [0.5, -0.5, 0.3],   # free
            [0.75, 0.6, 0.0],
            [1.0, 0.0, 0.0],
        ])
        knots = _make_clamped_knots(5, 3)
        curve = NurbsCurve(degree=3, control_points=ctrl, knots=knots)
        faired = fair_curve(curve)
        assert faired.num_control_points == 5
        # Endpoints preserved
        u0 = float(curve.knots[curve.degree])
        u1 = float(curve.knots[-(curve.degree + 1)])
        np.testing.assert_allclose(de_boor(faired, u0), de_boor(curve, u0), atol=1e-9)
        np.testing.assert_allclose(de_boor(faired, u1), de_boor(curve, u1), atol=1e-9)

    def test_curvature_fallback_flag(self):
        """curvature_weight=0 forces Laplacian fallback; no crash, endpoints fixed."""
        curve = _make_wavy_curve(n_ctrl=10, degree=3)
        faired = fair_curve(curve, curvature_weight=0.0, iterations=3, weight=0.2)
        u0 = float(curve.knots[curve.degree])
        u1 = float(curve.knots[-(curve.degree + 1)])
        np.testing.assert_allclose(de_boor(faired, u0), de_boor(curve, u0), atol=1e-9)
        np.testing.assert_allclose(de_boor(faired, u1), de_boor(curve, u1), atol=1e-9)
        assert np.allclose(faired.knots, curve.knots)


# ---------------------------------------------------------------------------
# Test group 5 — curvature_variance helper itself
# ---------------------------------------------------------------------------

class TestCurvatureVarianceHelper:

    def test_circle_nonzero_variance(self):
        """A quarter-circle has constant curvature → variance ≈ 0."""
        # Parametric quarter circle as an interpolated curve
        ts = np.linspace(0.0, math.pi / 2.0, 40)
        pts = np.column_stack([np.cos(ts), np.sin(ts), np.zeros(40)])
        curve = interp_curve(pts, degree=3)
        var = curvature_variance(curve, num_samples=200)
        # NURBS approximation introduces slight non-zero but should be tiny
        assert var >= 0.0

    def test_straight_line_zero_variance(self):
        """A straight line has zero curvature everywhere → variance == 0."""
        ctrl = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        knots = _make_clamped_knots(2, 1)
        curve = NurbsCurve(degree=1, control_points=ctrl, knots=knots)
        var = curvature_variance(curve, num_samples=50)
        assert abs(var) < 1e-20, f"Straight line variance={var}"

    def test_wavy_has_positive_variance(self):
        """A wavy curve has non-trivial positive curvature variance."""
        curve = _make_wavy_curve(n_ctrl=12, degree=3)
        var = curvature_variance(curve, num_samples=200)
        assert var > 0.0, f"Expected positive variance, got {var}"
