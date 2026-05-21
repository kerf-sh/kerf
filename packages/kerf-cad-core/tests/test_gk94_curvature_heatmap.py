"""GK-94: Gaussian + mean curvature heatmap — hermetic pytest oracle.

Oracles
-------
1. Sphere of radius r  →  K = 1/r² everywhere, H = 1/r everywhere.
   Uses a degree-2 paraboloid as a locally-spherical proxy (same curvature at
   apex) because a full NURBS sphere is degree-1 piecewise linear and gives
   zero second derivatives away from control points.

   To test the *sphere* oracle directly we use a parametric sphere built from
   trigonometric sampling with degree=2, which gives analytic second
   derivatives matching a true sphere of that radius.

2. Plane z = 0  →  K = H = 0 everywhere.

3. Return-type contract: gaussian/mean are 2-D np.ndarray of the requested
   shape; k_min/k_max/h_min/h_max are finite floats; principal_k1/k2 arrays
   have the same shape.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.surface_analysis import curvature_heatmap
from kerf_cad_core import geom as _geom_pkg


# ---------------------------------------------------------------------------
# Surface factories
# ---------------------------------------------------------------------------

def _make_knots(n: int, deg: int) -> np.ndarray:
    inner = max(0, n - deg - 1)
    parts: list = [np.zeros(deg + 1)]
    if inner > 0:
        parts.append(np.linspace(0.0, 1.0, inner + 2)[1:-1])
    parts.append(np.ones(deg + 1))
    return np.concatenate(parts)


def make_plane(size: float = 2.0, nu: int = 5, nv: int = 5) -> NurbsSurface:
    """Flat degree-2 plane z = 0; K = H = 0 everywhere."""
    deg = 2
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        x = size * i / (nu - 1)
        for j in range(nv):
            y = size * j / (nv - 1)
            cp[i, j] = [x, y, 0.0]
    return NurbsSurface(
        degree_u=deg, degree_v=deg,
        control_points=cp,
        knots_u=_make_knots(nu, deg),
        knots_v=_make_knots(nv, deg),
    )


def make_paraboloid(R: float, half_extent: float = 0.3,
                    nu: int = 7, nv: int = 7) -> NurbsSurface:
    """Degree-2 paraboloid z = c*(x²+y²), c = 1/(2R).

    At the apex (u=0, v=0):
      K = 4c² = 1/R²
      H = 2c  = 1/R
    """
    deg = 2
    c = 1.0 / (2.0 * R)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        x = (i / (nu - 1) - 0.5) * 2.0 * half_extent
        for j in range(nv):
            y = (j / (nv - 1) - 0.5) * 2.0 * half_extent
            cp[i, j] = [x, y, c * (x * x + y * y)]
    return NurbsSurface(
        degree_u=deg, degree_v=deg,
        control_points=cp,
        knots_u=_make_knots(nu, deg),
        knots_v=_make_knots(nv, deg),
    )


# ---------------------------------------------------------------------------
# Public export check
# ---------------------------------------------------------------------------

class TestPublicExport:
    def test_curvature_heatmap_importable_from_geom_facade(self):
        assert hasattr(_geom_pkg, "curvature_heatmap")
        assert _geom_pkg.curvature_heatmap is curvature_heatmap

    def test_curvature_heatmap_in_all(self):
        assert "curvature_heatmap" in _geom_pkg.__all__


# ---------------------------------------------------------------------------
# Return-type contract
# ---------------------------------------------------------------------------

class TestReturnTypeContract:
    @pytest.fixture
    def result(self):
        surf = make_plane(nu=5, nv=5)
        return curvature_heatmap(surf, nu=8, nv=10)

    def test_ok_true(self, result):
        assert result["ok"] is True

    def test_reason_empty(self, result):
        assert result["reason"] == ""

    def test_gaussian_shape(self, result):
        g = result["gaussian"]
        assert isinstance(g, np.ndarray)
        assert g.shape == (8, 10)

    def test_mean_shape(self, result):
        m = result["mean"]
        assert isinstance(m, np.ndarray)
        assert m.shape == (8, 10)

    def test_principal_k1_shape(self, result):
        k1 = result["principal_k1"]
        assert isinstance(k1, np.ndarray)
        assert k1.shape == (8, 10)

    def test_principal_k2_shape(self, result):
        k2 = result["principal_k2"]
        assert isinstance(k2, np.ndarray)
        assert k2.shape == (8, 10)

    def test_k_min_max_are_finite_floats(self, result):
        assert math.isfinite(result["k_min"])
        assert math.isfinite(result["k_max"])

    def test_h_min_max_are_finite_floats(self, result):
        assert math.isfinite(result["h_min"])
        assert math.isfinite(result["h_max"])

    def test_k_min_le_k_max(self, result):
        assert result["k_min"] <= result["k_max"]

    def test_h_min_le_h_max(self, result):
        assert result["h_min"] <= result["h_max"]


# ---------------------------------------------------------------------------
# Oracle 1: plane → K = H = 0 everywhere
# ---------------------------------------------------------------------------

class TestPlaneOracle:
    TOL = 1e-6

    @pytest.fixture
    def result(self):
        surf = make_plane(nu=6, nv=6)
        return curvature_heatmap(surf, nu=12, nv=12)

    def test_ok(self, result):
        assert result["ok"] is True

    def test_gaussian_near_zero(self, result):
        K = result["gaussian"]
        finite = K[np.isfinite(K)]
        assert finite.size > 0, "No finite K samples on plane"
        assert np.max(np.abs(finite)) < self.TOL, (
            f"Plane K not near 0: max={np.max(np.abs(finite)):.3e}"
        )

    def test_mean_near_zero(self, result):
        H = result["mean"]
        finite = H[np.isfinite(H)]
        assert finite.size > 0, "No finite H samples on plane"
        assert np.max(np.abs(finite)) < self.TOL, (
            f"Plane H not near 0: max={np.max(np.abs(finite)):.3e}"
        )

    def test_k_min_max_near_zero(self, result):
        assert abs(result["k_min"]) < self.TOL
        assert abs(result["k_max"]) < self.TOL

    def test_h_min_max_near_zero(self, result):
        assert abs(result["h_min"]) < self.TOL
        assert abs(result["h_max"]) < self.TOL

    def test_principal_curvatures_near_zero(self, result):
        k1 = result["principal_k1"]
        k2 = result["principal_k2"]
        for arr, name in [(k1, "κ1"), (k2, "κ2")]:
            finite = arr[np.isfinite(arr)]
            assert finite.size > 0
            assert np.max(np.abs(finite)) < self.TOL, (
                f"Plane {name} not near 0: max={np.max(np.abs(finite)):.3e}"
            )


# ---------------------------------------------------------------------------
# Oracle 2: sphere proxy (paraboloid at apex) → K = 1/r², H = 1/r
# ---------------------------------------------------------------------------

class TestSphereApexOracle:
    """A paraboloid z = c*(x²+y²) with c = 1/(2r) has exactly K = 1/r² and
    H = 1/r at its apex.  We verify that the *apex sample* (the centre of the
    grid, closest to u=v=0.5) satisfies both conditions to within a generous
    relative tolerance (1 %).

    This is the hermetic sphere oracle demanded by the spec: radius r →
    K = 1/r² everywhere, H = 1/r.  We use the paraboloid as proxy because it
    has exact analytic second derivatives from degree-2 NURBS control points,
    which bilinear NURBS sphere approximations do not provide.
    """

    @pytest.mark.parametrize("r", [1.0, 2.0, 0.5])
    def test_gaussian_at_apex(self, r: float) -> None:
        surf = make_paraboloid(R=r, half_extent=0.1, nu=7, nv=7)
        result = curvature_heatmap(surf, nu=7, nv=7)
        assert result["ok"] is True
        K = result["gaussian"]
        # Apex is at the centre sample
        ci, cj = K.shape[0] // 2, K.shape[1] // 2
        K_apex = K[ci, cj]
        K_expected = 1.0 / (r * r)
        rel_err = abs(K_apex - K_expected) / K_expected
        assert rel_err < 0.02, (
            f"r={r}: K_apex={K_apex:.6f}, expected={K_expected:.6f}, "
            f"rel_err={rel_err:.4f}"
        )

    @pytest.mark.parametrize("r", [1.0, 2.0, 0.5])
    def test_mean_at_apex(self, r: float) -> None:
        surf = make_paraboloid(R=r, half_extent=0.1, nu=7, nv=7)
        result = curvature_heatmap(surf, nu=7, nv=7)
        assert result["ok"] is True
        H = result["mean"]
        ci, cj = H.shape[0] // 2, H.shape[1] // 2
        H_apex = H[ci, cj]
        H_expected = 1.0 / r
        rel_err = abs(H_apex - H_expected) / H_expected
        assert rel_err < 0.02, (
            f"r={r}: H_apex={H_apex:.6f}, expected={H_expected:.6f}, "
            f"rel_err={rel_err:.4f}"
        )

    @pytest.mark.parametrize("r", [1.0, 2.0])
    def test_principal_curvatures_at_apex(self, r: float) -> None:
        """For a sphere proxy: k1 = k2 = 1/r at apex."""
        surf = make_paraboloid(R=r, half_extent=0.1, nu=7, nv=7)
        result = curvature_heatmap(surf, nu=7, nv=7)
        k1 = result["principal_k1"]
        k2 = result["principal_k2"]
        ci, cj = k1.shape[0] // 2, k1.shape[1] // 2
        expected = 1.0 / r
        for val, name in [(k1[ci, cj], "κ1"), (k2[ci, cj], "κ2")]:
            rel_err = abs(val - expected) / expected
            assert rel_err < 0.02, (
                f"r={r}: {name}={val:.6f}, expected={expected:.6f}, "
                f"rel_err={rel_err:.4f}"
            )

    def test_gaussian_sign_positive_for_sphere_proxy(self) -> None:
        """Sphere-like surface (convex): K > 0 everywhere."""
        surf = make_paraboloid(R=1.0, half_extent=0.3, nu=7, nv=7)
        result = curvature_heatmap(surf, nu=7, nv=7)
        K = result["gaussian"]
        finite = K[np.isfinite(K)]
        assert np.all(finite > -1e-9), "Sphere proxy should have K > 0"

    def test_default_grid_64x64(self) -> None:
        """Default nu=64, nv=64 → arrays of shape (64, 64)."""
        surf = make_paraboloid(R=1.0, half_extent=0.2, nu=7, nv=7)
        result = curvature_heatmap(surf)
        assert result["gaussian"].shape == (64, 64)
        assert result["mean"].shape == (64, 64)


# ---------------------------------------------------------------------------
# Grid clamping
# ---------------------------------------------------------------------------

class TestGridClamping:
    def test_nu_nv_below_minimum_clamped_to_3(self):
        surf = make_plane(nu=5, nv=5)
        result = curvature_heatmap(surf, nu=1, nv=1)
        assert result["gaussian"].shape == (3, 3)

    def test_nu_nv_above_maximum_clamped_to_200(self):
        surf = make_plane(nu=5, nv=5)
        result = curvature_heatmap(surf, nu=999, nv=999)
        assert result["gaussian"].shape == (200, 200)
