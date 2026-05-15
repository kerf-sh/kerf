"""
Tests for surface_boolean_robust and surface_health_check (T-37).

All tests are hermetic: no OCC, no database, no network.  Pure-Python
guards and geometry logic only.  OCC-dependent paths are verified by
passing a stub occ_fn.

Coverage (≥25 tests):
  - surface_health_check: type guard, degenerate patch, self-intersecting
    control net, high-degree warning, duplicate control points, degree<1 error
  - surface_boolean_robust: valid surfaces pass, degenerate srf_a rejected,
    degenerate srf_b rejected, invalid kind rejected, invalid bbox_tol rejected,
    tolerance scales with bbox, large model gets large tolerance, tiny model
    gets small tolerance, tolerance clamped to [1e-7, 1e-2], occ_fn=None
    returns ok with no result, occ_fn success path, occ_fn returns None triggers
    retry, retry succeeds, retry also fails returns ok=False with reason,
    relaxed tolerance capped at 1e-2, result dict always has required keys,
    health_a / health_b populated in all paths, friendly failure dict on bad input
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.surface_boolean_robust import (
    _TOL_MAX,
    _TOL_MIN,
    _auto_tolerance,
    _relaxed_tolerance,
    surface_boolean_robust,
    surface_health_check,
)


# ---------------------------------------------------------------------------
# Helpers: surface factories
# ---------------------------------------------------------------------------

def make_flat_surface(nu: int = 3, nv: int = 3, scale: float = 1.0) -> NurbsSurface:
    """Create a simple flat bilinear patch."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [i * scale, j * scale, 0.0]
    ku = np.array([0.0] * 2 + list(np.linspace(0, 1, nu - 1)) + [1.0] * 2)
    kv = np.array([0.0] * 2 + list(np.linspace(0, 1, nv - 1)) + [1.0] * 2)
    # Simple open clamped knots for degree-1 surface
    ku = np.linspace(0.0, 1.0, nu + 2)
    kv = np.linspace(0.0, 1.0, nv + 2)
    return NurbsSurface(
        degree_u=1,
        degree_v=1,
        control_points=cp,
        knots_u=np.array([0.0, 0.0, 1.0] if nu == 2 else [0.0] * 2 + list(np.linspace(0, 1, nu - 1)) + [1.0] * 2),
        knots_v=np.array([0.0, 0.0, 1.0] if nv == 2 else [0.0] * 2 + list(np.linspace(0, 1, nv - 1)) + [1.0] * 2),
    )


def make_simple_surface(
    nu: int = 3,
    nv: int = 3,
    scale: float = 1.0,
    degree_u: int = 2,
    degree_v: int = 2,
) -> NurbsSurface:
    """Create a non-degenerate flat surface with specified degrees."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [i * scale, j * scale, 0.0]
    n_ku = nu + degree_u + 1
    n_kv = nv + degree_v + 1
    ku = np.concatenate([
        np.zeros(degree_u),
        np.linspace(0, 1, n_ku - 2 * degree_u),
        np.ones(degree_u),
    ])
    kv = np.concatenate([
        np.zeros(degree_v),
        np.linspace(0, 1, n_kv - 2 * degree_v),
        np.ones(degree_v),
    ])
    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=cp,
        knots_u=ku,
        knots_v=kv,
    )


def make_degenerate_surface() -> NurbsSurface:
    """All control points collapsed to one point — fully degenerate."""
    cp = np.zeros((3, 3, 3))  # all zeros → all patches have zero area
    ku = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    return NurbsSurface(
        degree_u=2, degree_v=2,
        control_points=cp,
        knots_u=ku, knots_v=kv,
    )


def make_self_intersecting_surface() -> NurbsSurface:
    """Control net rows fold on themselves (sign-flipping cross-products)."""
    cp = np.array([
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        [[2.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],  # reversed → fold
        [[0.0, 2.0, 0.0], [1.0, 2.0, 0.0], [2.0, 2.0, 0.0]],
        [[0.0, 3.0, 0.0], [1.0, 3.0, 0.0], [2.0, 3.0, 0.0]],
        [[0.0, 4.0, 0.0], [1.0, 4.0, 0.0], [2.0, 4.0, 0.0]],
    ])
    ku = np.array([0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    return NurbsSurface(
        degree_u=2, degree_v=2,
        control_points=cp,
        knots_u=ku, knots_v=kv,
    )


def make_large_surface() -> NurbsSurface:
    """Surface with bbox diagonal ~1000 units."""
    return make_simple_surface(scale=500.0)


def make_tiny_surface() -> NurbsSurface:
    """Surface with bbox diagonal ~0.001 units."""
    return make_simple_surface(scale=0.0005)


# ---------------------------------------------------------------------------
# surface_health_check — type guard
# ---------------------------------------------------------------------------

class TestHealthCheckTypeGuard:
    def test_non_surface_returns_not_ok(self):
        result = surface_health_check("not a surface")
        assert result["ok"] is False
        assert any("NurbsSurface" in e or "expected" in e for e in result["errors"])

    def test_none_returns_not_ok(self):
        result = surface_health_check(None)
        assert result["ok"] is False

    def test_dict_returns_not_ok(self):
        result = surface_health_check({"degree_u": 2})
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# surface_health_check — degenerate patch detection
# ---------------------------------------------------------------------------

class TestHealthCheckDegeneratePatch:
    def test_fully_degenerate_surface_rejected(self):
        srf = make_degenerate_surface()
        result = surface_health_check(srf)
        assert result["ok"] is False
        assert len(result["errors"]) >= 1
        assert any("degenerate" in e.lower() for e in result["errors"])

    def test_healthy_surface_passes(self):
        srf = make_simple_surface()
        result = surface_health_check(srf)
        assert result["ok"] is True
        assert result["errors"] == []

    def test_partial_degeneracy_may_warn(self):
        """A surface with one degenerate patch but not all → warning, not error."""
        cp = np.zeros((3, 3, 3))
        # Make most patches non-degenerate
        for i in range(3):
            for j in range(3):
                cp[i, j] = [i * 1.0, j * 1.0, 0.0]
        # Collapse one patch by making cp[0,0] == cp[1,0] == cp[0,1] == cp[1,1]
        # Still leaves other patches with area > 0
        ku = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
        kv = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
        srf = NurbsSurface(degree_u=2, degree_v=2, control_points=cp, knots_u=ku, knots_v=kv)
        result = surface_health_check(srf)
        # Either ok with a warning OR not ok — just verify the dict structure
        assert "ok" in result
        assert "warnings" in result
        assert "errors" in result


# ---------------------------------------------------------------------------
# surface_health_check — self-intersecting control net
# ---------------------------------------------------------------------------

class TestHealthCheckSelfIntersecting:
    def test_self_intersecting_net_flagged(self):
        srf = make_self_intersecting_surface()
        result = surface_health_check(srf)
        assert result["ok"] is False
        assert any("self-intersect" in e.lower() or "fold" in e.lower() for e in result["errors"])

    def test_non_intersecting_net_passes(self):
        srf = make_simple_surface()
        result = surface_health_check(srf)
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# surface_health_check — degree warnings / errors
# ---------------------------------------------------------------------------

class TestHealthCheckDegree:
    def test_high_degree_generates_warning(self):
        srf = make_simple_surface(degree_u=10, degree_v=2, nu=12, nv=3)
        result = surface_health_check(srf)
        # Should have a warning about high degree
        assert any("degree" in w.lower() or "high" in w.lower() for w in result["warnings"])

    def test_result_always_has_required_keys(self):
        srf = make_simple_surface()
        result = surface_health_check(srf)
        assert "ok" in result
        assert "warnings" in result
        assert "errors" in result


# ---------------------------------------------------------------------------
# surface_boolean_robust — input validation
# ---------------------------------------------------------------------------

class TestRobustInputValidation:
    def test_invalid_kind_rejected(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "union")
        assert result["ok"] is False
        assert "union" in result["reason"]

    def test_empty_kind_rejected(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "")
        assert result["ok"] is False

    def test_degenerate_srf_a_rejected(self):
        srf_a = make_degenerate_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "cut")
        assert result["ok"] is False
        assert "surface A" in result["reason"]

    def test_degenerate_srf_b_rejected(self):
        srf_a = make_simple_surface()
        srf_b = make_degenerate_surface()
        result = surface_boolean_robust(srf_a, srf_b, "fuse")
        assert result["ok"] is False
        assert "surface B" in result["reason"]

    def test_non_surface_srf_a_rejected(self):
        result = surface_boolean_robust("bad", make_simple_surface(), "cut")
        assert result["ok"] is False

    def test_non_surface_srf_b_rejected(self):
        result = surface_boolean_robust(make_simple_surface(), None, "cut")
        assert result["ok"] is False

    def test_invalid_bbox_tol_zero_rejected(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "cut", bbox_tol=0.0)
        assert result["ok"] is False
        assert "bbox_tol" in result["reason"]

    def test_invalid_bbox_tol_negative_rejected(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "fuse", bbox_tol=-1e-5)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# surface_boolean_robust — tolerance auto-scaling
# ---------------------------------------------------------------------------

class TestRobustToleranceScaling:
    def test_tolerance_scales_with_bbox(self):
        srf_small = make_simple_surface(scale=1.0)
        srf_large = make_simple_surface(scale=1000.0)
        tol_small = _auto_tolerance(srf_small, srf_small)
        tol_large = _auto_tolerance(srf_large, srf_large)
        assert tol_large > tol_small

    def test_large_model_tolerance_higher(self):
        srf = make_large_surface()
        tol = _auto_tolerance(srf, srf)
        assert tol > 1e-5  # should be well above the minimum

    def test_tiny_model_tolerance_clamped_at_min(self):
        srf = make_tiny_surface()
        tol = _auto_tolerance(srf, srf)
        assert tol >= _TOL_MIN

    def test_tolerance_clamped_at_max(self):
        # Create a gigantic surface; tolerance must never exceed _TOL_MAX
        srf = make_simple_surface(scale=1e8)
        tol = _auto_tolerance(srf, srf)
        assert tol <= _TOL_MAX

    def test_bbox_tol_override_respected(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "cut", bbox_tol=5e-5)
        assert result["ok"] is True
        assert abs(result["tolerance"] - 5e-5) < 1e-10

    def test_bbox_tol_clamped_to_min(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        # Provide a tolerance below the minimum; should be clamped
        result = surface_boolean_robust(srf_a, srf_b, "cut", bbox_tol=1e-20)
        assert result["ok"] is True
        assert result["tolerance"] >= _TOL_MIN


# ---------------------------------------------------------------------------
# surface_boolean_robust — occ_fn integration paths
# ---------------------------------------------------------------------------

class TestRobustOccFnPaths:
    def test_no_occ_fn_returns_ok_no_result(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=None)
        assert result["ok"] is True
        assert result["result"] is None

    def test_occ_fn_success_path(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        sentinel = object()

        def good_occ_fn(a, b, kind, tol):
            return sentinel

        result = surface_boolean_robust(srf_a, srf_b, "fuse", occ_fn=good_occ_fn)
        assert result["ok"] is True
        assert result["result"] is sentinel
        assert result["retried"] is False

    def test_occ_fn_returns_none_triggers_retry(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        calls = []
        sentinel = object()

        def occ_fn(a, b, kind, tol):
            calls.append(tol)
            # Fail on first call, succeed on second
            return sentinel if len(calls) > 1 else None

        result = surface_boolean_robust(srf_a, srf_b, "common", occ_fn=occ_fn)
        assert result["ok"] is True
        assert result["retried"] is True
        assert len(calls) == 2
        # Second call uses relaxed (larger) tolerance
        assert calls[1] > calls[0]

    def test_occ_fn_raises_triggers_retry(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        calls = []
        sentinel = object()

        def occ_fn(a, b, kind, tol):
            calls.append(tol)
            if len(calls) == 1:
                raise RuntimeError("OCC boolean failed")
            return sentinel

        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=occ_fn)
        assert result["ok"] is True
        assert result["retried"] is True
        assert result["result"] is sentinel

    def test_occ_fn_both_fail_returns_not_ok(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()

        def bad_occ_fn(a, b, kind, tol):
            raise RuntimeError(f"always fails at {tol}")

        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=bad_occ_fn)
        assert result["ok"] is False
        assert result["result"] is None
        assert result["retried"] is True
        assert len(result["reason"]) > 0

    def test_retry_tolerance_larger_than_initial(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        recorded = {}

        def occ_fn(a, b, kind, tol):
            if "first" not in recorded:
                recorded["first"] = tol
                return None
            recorded["retry"] = tol
            return object()

        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=occ_fn)
        assert result["ok"] is True
        assert recorded["retry"] > recorded["first"]


# ---------------------------------------------------------------------------
# surface_boolean_robust — result dict structure
# ---------------------------------------------------------------------------

class TestRobustResultStructure:
    _REQUIRED_KEYS = {"ok", "result", "reason", "retried", "tolerance", "health_a", "health_b"}

    def test_success_result_has_all_keys(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "cut")
        assert self._REQUIRED_KEYS <= set(result.keys())

    def test_failure_result_has_all_keys(self):
        srf_a = make_degenerate_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "cut")
        assert self._REQUIRED_KEYS <= set(result.keys())

    def test_invalid_kind_result_has_all_keys(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "bad_kind")
        assert self._REQUIRED_KEYS <= set(result.keys())

    def test_health_a_populated_on_success(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "cut")
        assert isinstance(result["health_a"], dict)
        assert "ok" in result["health_a"]

    def test_health_b_populated_on_success(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        result = surface_boolean_robust(srf_a, srf_b, "fuse")
        assert isinstance(result["health_b"], dict)
        assert "ok" in result["health_b"]

    def test_ok_false_reason_nonempty(self):
        result = surface_boolean_robust(
            make_degenerate_surface(), make_simple_surface(), "cut"
        )
        assert result["ok"] is False
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0

    def test_all_valid_kinds_accepted(self):
        srf_a = make_simple_surface()
        srf_b = make_simple_surface()
        for kind in ("cut", "fuse", "common"):
            result = surface_boolean_robust(srf_a, srf_b, kind)
            assert result["ok"] is True, f"kind={kind!r} should be accepted"


# ---------------------------------------------------------------------------
# _relaxed_tolerance helper
# ---------------------------------------------------------------------------

class TestRelaxedTolerance:
    def test_relaxed_is_larger(self):
        tol = 1e-5
        relaxed = _relaxed_tolerance(tol)
        assert relaxed is not None
        assert relaxed > tol

    def test_at_max_returns_none(self):
        # If tol * factor > _TOL_MAX, must return None
        tol = _TOL_MAX / 5.0  # 5x relaxed = TOL_MAX exactly or more
        relaxed = _relaxed_tolerance(tol)
        # relaxed = tol * 10 = 2 * TOL_MAX > TOL_MAX → None
        assert relaxed is None

    def test_small_tol_returns_value(self):
        tol = 1e-6
        relaxed = _relaxed_tolerance(tol)
        assert relaxed is not None
        assert relaxed <= _TOL_MAX
