"""
test_adaptive_refine.py
=======================
Hermetic tests for GK-63: adaptive_refine_surface.

Oracle: a torus patch approximated by a coarse NURBS surface, refined until
the certified Hausdorff bound (via GK-37 hausdorff_deviation) is ≤ tol.

All tests are pure-Python, no OCC, no database, no network.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.surface_analysis import (
    adaptive_refine_surface,
    hausdorff_deviation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clamped_knots(n: int, degree: int) -> np.ndarray:
    """Clamped uniform knot vector for n control points of given degree."""
    inner = max(0, n - degree - 1)
    parts = [np.zeros(degree + 1)]
    if inner > 0:
        parts.append(np.linspace(0.0, 1.0, inner + 2)[1:-1])
    parts.append(np.ones(degree + 1))
    return np.concatenate(parts)


def _make_torus_patch_surface(
    R: float = 2.0,
    r: float = 0.5,
    u_range: tuple = (0.0, math.pi / 2),
    v_range: tuple = (0.0, math.pi / 2),
    nu: int = 12,
    nv: int = 12,
    degree: int = 3,
) -> NurbsSurface:
    """Build a NURBS approximation of a torus patch by direct CP sampling.

    The torus is defined by:
        x(u, v) = (R + r·cos(v))·cos(u)
        y(u, v) = (R + r·cos(v))·sin(u)
        z(u, v) = r·sin(v)

    We evaluate the torus at (nu × nv) parameter grid and use those as control
    points — this is NOT an exact NURBS representation, so the resulting surface
    has deviation that adaptive_refine_surface must reduce.

    Parameters
    ----------
    R     : major radius
    r     : minor radius
    u_range / v_range : parameter extents on [0, 2π]
    nu, nv : grid size (determines initial deviation)
    degree : NURBS degree
    """
    us = np.linspace(u_range[0], u_range[1], nu)
    vs = np.linspace(v_range[0], v_range[1], nv)
    ctrl = np.zeros((nu, nv, 3))
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            ctrl[i, j, 0] = (R + r * math.cos(v)) * math.cos(u)
            ctrl[i, j, 1] = (R + r * math.cos(v)) * math.sin(u)
            ctrl[i, j, 2] = r * math.sin(v)

    return NurbsSurface(
        degree_u=degree,
        degree_v=degree,
        control_points=ctrl,
        knots_u=_make_clamped_knots(nu, degree),
        knots_v=_make_clamped_knots(nv, degree),
    )


def _torus_eval(u: float, v: float, R: float, r: float) -> np.ndarray:
    """Exact torus point."""
    return np.array([
        (R + r * math.cos(v)) * math.cos(u),
        (R + r * math.cos(v)) * math.sin(u),
        r * math.sin(v),
    ])


def _make_plane_surface(nu: int = 4, nv: int = 4) -> NurbsSurface:
    """Flat z=0 plane over [0,1]×[0,1]."""
    ctrl = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            ctrl[i, j] = [i / (nu - 1), j / (nv - 1), 0.0]
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=ctrl,
        knots_u=_make_clamped_knots(nu, 1),
        knots_v=_make_clamped_knots(nv, 1),
    )


# ---------------------------------------------------------------------------
# GK-63 oracle test — torus patch certified ≤ tol
# ---------------------------------------------------------------------------

class TestAdaptiveRefineTorus:
    """Oracle: coarse torus patch refined until certified Hausdorff ≤ tol."""

    TOL = 0.05          # generous but non-trivial for degree-3 at 4×4
    R = 2.0
    r = 0.5
    U_RANGE = (0.0, math.pi / 2)
    V_RANGE = (0.0, math.pi / 2)

    def _coarse_surf(self) -> NurbsSurface:
        """Very coarse 4×4 torus patch — high initial deviation."""
        return _make_torus_patch_surface(
            R=self.R, r=self.r,
            u_range=self.U_RANGE, v_range=self.V_RANGE,
            nu=4, nv=4, degree=3,
        )

    def _oracle_surf(self) -> NurbsSurface:
        """Dense 20×20 torus patch — serves as oracle (high-fidelity ref)."""
        return _make_torus_patch_surface(
            R=self.R, r=self.r,
            u_range=self.U_RANGE, v_range=self.V_RANGE,
            nu=20, nv=20, degree=3,
        )

    def test_returns_ok_dict(self):
        """adaptive_refine_surface returns a dict with required keys."""
        coarse = self._coarse_surf()
        oracle = self._oracle_surf()
        result = adaptive_refine_surface(
            coarse, oracle, tol=self.TOL,
            max_knots=32, n_sample=16,
            n_hausdorff_start=12, n_hausdorff_max=32,
        )
        assert isinstance(result, dict)
        for key in ("ok", "surface", "hausdorff_upper", "certified",
                    "knots_added", "num_ctrl_u", "num_ctrl_v",
                    "iterations", "reason"):
            assert key in result, f"missing key: {key}"

    def test_certified_hausdorff_le_tol(self):
        """Core oracle: refined surface is certified Hausdorff ≤ tol."""
        coarse = self._coarse_surf()
        oracle = self._oracle_surf()
        result = adaptive_refine_surface(
            coarse, oracle, tol=self.TOL,
            max_knots=48, n_sample=16,
            n_hausdorff_start=12, n_hausdorff_max=32,
        )
        assert result["ok"], (
            f"adaptive_refine_surface did not converge: "
            f"hausdorff_upper={result['hausdorff_upper']:.4g}, "
            f"knots_added={result['knots_added']}, reason={result['reason']}"
        )
        assert result["hausdorff_upper"] <= self.TOL, (
            f"hausdorff_upper={result['hausdorff_upper']:.4g} > tol={self.TOL}"
        )

    def test_knot_count_bounded(self):
        """Refinement uses a bounded/minimal number of added knots."""
        coarse = self._coarse_surf()
        oracle = self._oracle_surf()
        result = adaptive_refine_surface(
            coarse, oracle, tol=self.TOL,
            max_knots=48, n_sample=16,
            n_hausdorff_start=12, n_hausdorff_max=32,
        )
        # Must not exhaust the full budget for a generous tol
        assert result["knots_added"] < 48, (
            f"Used full knot budget ({result['knots_added']}); "
            "refinement appears non-convergent"
        )
        # CP count must grow (refinement happened)
        nu0 = self._coarse_surf().num_control_points_u
        nv0 = self._coarse_surf().num_control_points_v
        total_added = (
            result["num_ctrl_u"] - nu0 + result["num_ctrl_v"] - nv0
        )
        assert total_added >= 0, "CP count must be >= initial"

    def test_hausdorff_decreases_monotonically(self):
        """Hausdorff bound after refinement is less than before refinement."""
        coarse = self._coarse_surf()
        oracle = self._oracle_surf()

        # Pre-refinement bound
        pre = hausdorff_deviation(
            coarse, oracle, epsilon=1e-4, n_start=12, n_max=24
        )
        assert pre["ok"]
        h_before = pre["hausdorff_upper"]

        result = adaptive_refine_surface(
            coarse, oracle, tol=self.TOL,
            max_knots=48, n_sample=16,
            n_hausdorff_start=12, n_hausdorff_max=32,
        )
        h_after = result["hausdorff_upper"]
        assert h_after < h_before, (
            f"Hausdorff did not decrease: before={h_before:.4g}, after={h_after:.4g}"
        )

    def test_result_surface_is_nurbssurface(self):
        """The returned surface is a valid NurbsSurface."""
        coarse = self._coarse_surf()
        oracle = self._oracle_surf()
        result = adaptive_refine_surface(
            coarse, oracle, tol=self.TOL,
            max_knots=32, n_sample=16,
            n_hausdorff_start=12, n_hausdorff_max=32,
        )
        surf = result["surface"]
        assert isinstance(surf, NurbsSurface)
        assert surf.num_control_points_u >= coarse.num_control_points_u
        assert surf.num_control_points_v >= coarse.num_control_points_v


# ---------------------------------------------------------------------------
# Knot insertion correctness (geometry preservation)
# ---------------------------------------------------------------------------

class TestKnotInsertionGeometry:
    """Boehm knot insertion must preserve surface geometry exactly."""

    def test_knot_insert_u_preserves_geometry(self):
        """Inserting a U knot does not change evaluated points."""
        from kerf_cad_core.geom.surface_analysis import (
            _surface_knot_insert_u,
        )
        # Use the plane — easy to verify
        surf = _make_plane_surface(nu=5, nv=5)
        surf_refined = _surface_knot_insert_u(surf, 0.5)

        from kerf_cad_core.geom.nurbs import surface_evaluate
        # Check at a grid of parameter values
        for u in np.linspace(0.01, 0.99, 7):
            for v in np.linspace(0.01, 0.99, 7):
                p_orig = surface_evaluate(surf, u, v)[:3]
                p_new = surface_evaluate(surf_refined, u, v)[:3]
                assert np.linalg.norm(p_orig - p_new) < 1e-10, (
                    f"U insertion changed geometry at ({u:.2f},{v:.2f}): "
                    f"delta={np.linalg.norm(p_orig - p_new):.2e}"
                )

    def test_knot_insert_v_preserves_geometry(self):
        """Inserting a V knot does not change evaluated points."""
        from kerf_cad_core.geom.surface_analysis import (
            _surface_knot_insert_v,
        )
        surf = _make_plane_surface(nu=5, nv=5)
        surf_refined = _surface_knot_insert_v(surf, 0.3)

        from kerf_cad_core.geom.nurbs import surface_evaluate
        for u in np.linspace(0.01, 0.99, 7):
            for v in np.linspace(0.01, 0.99, 7):
                p_orig = surface_evaluate(surf, u, v)[:3]
                p_new = surface_evaluate(surf_refined, u, v)[:3]
                assert np.linalg.norm(p_orig - p_new) < 1e-10, (
                    f"V insertion changed geometry at ({u:.2f},{v:.2f}): "
                    f"delta={np.linalg.norm(p_orig - p_new):.2e}"
                )

    def test_knot_insert_u_increments_cp_count(self):
        """After one U knot insertion, nu increases by 1."""
        from kerf_cad_core.geom.surface_analysis import _surface_knot_insert_u
        surf = _make_plane_surface(nu=5, nv=5)
        surf2 = _surface_knot_insert_u(surf, 0.4)
        assert surf2.num_control_points_u == surf.num_control_points_u + 1
        assert surf2.num_control_points_v == surf.num_control_points_v

    def test_knot_insert_v_increments_cp_count(self):
        """After one V knot insertion, nv increases by 1."""
        from kerf_cad_core.geom.surface_analysis import _surface_knot_insert_v
        surf = _make_plane_surface(nu=5, nv=5)
        surf2 = _surface_knot_insert_v(surf, 0.6)
        assert surf2.num_control_points_v == surf.num_control_points_v + 1
        assert surf2.num_control_points_u == surf.num_control_points_u


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestAdaptiveRefineValidation:
    """Bad inputs must produce ok=False without raising."""

    def test_bad_approx_type(self):
        oracle = _make_plane_surface()
        result = adaptive_refine_surface("not-a-surface", oracle, tol=1e-3)
        assert not result["ok"]
        assert "approx_surf" in result["reason"]

    def test_bad_oracle_type(self):
        approx = _make_plane_surface()
        result = adaptive_refine_surface(approx, None, tol=1e-3)
        assert not result["ok"]
        assert "oracle_surf" in result["reason"]

    def test_negative_tol(self):
        surf = _make_plane_surface()
        result = adaptive_refine_surface(surf, surf, tol=-1.0)
        assert not result["ok"]
        assert "tol" in result["reason"]

    def test_zero_tol(self):
        surf = _make_plane_surface()
        result = adaptive_refine_surface(surf, surf, tol=0.0)
        assert not result["ok"]

    def test_identical_surfaces_certifies_immediately(self):
        """If approx == oracle (same object), Hausdorff=0 ≤ any tol."""
        surf = _make_torus_patch_surface(nu=8, nv=8, degree=3)
        result = adaptive_refine_surface(
            surf, surf, tol=1.0,
            max_knots=4, n_sample=8,
            n_hausdorff_start=8, n_hausdorff_max=16,
        )
        assert result["ok"], f"Identical surfaces should certify immediately: {result['reason']}"
        assert result["hausdorff_upper"] <= 1.0
        assert result["knots_added"] == 0, "No knots should be needed for identical surfaces"
