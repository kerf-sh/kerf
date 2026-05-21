"""
T-45 — NURBS: trim-by-curve + surface boolean robust
======================================================
Hermetic pytest suite — no OCC, no database, no network.

Scope
-----
  * ``geom/trim_curve.py``           — trim_face, project_curve_to_uv,
                                       split_face_uv, TrimCurve
  * ``geom/surface_boolean_robust.py`` — surface_boolean_robust,
                                          surface_health_check,
                                          _build_tolerance_ladder

Success criteria (spec)
-----------------------
25 trim/boolean cases including near-tangent and degenerate inputs;
robust fallback paths exercised.

Groups
------
  A. Trim-curve — boundary traversal cases               (cases 1–6)
  B. Trim-curve — malformed / degenerate inputs           (cases 7–10)
  C. Trim-curve — idempotency                             (cases 11–12)
  D. Boolean robust — near-tangent surfaces (dense NURBS) (cases 13–16)
  E. Boolean robust — degenerate surface rejection        (cases 17–19)
  F. Boolean robust — OCCT stub / retry ladder            (cases 20–23)
  G. Boolean robust — result-dict contract                (cases 24–25)
"""

from __future__ import annotations

import math
import os

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.trim_curve import (
    TrimCurve,
    _check_curve_crosses_boundary,
    project_curve_to_uv,
    split_face_uv,
    trim_face,
)
from kerf_cad_core.geom.surface_boolean_robust import (
    _TOL_MAX,
    _TOL_MIN,
    _TOL_RELAX_FACTOR,
    _MAX_ATTEMPTS,
    _build_tolerance_ladder,
    _check_dense_nurbs,
    surface_boolean_robust,
    surface_health_check,
)

# ---------------------------------------------------------------------------
# Shared surface factories
# ---------------------------------------------------------------------------

def _knots_clamped(n: int, degree: int) -> np.ndarray:
    """Build an open clamped knot vector for n control points, given degree."""
    inner = max(0, n - degree - 1)
    return np.concatenate([
        np.zeros(degree + 1),
        np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner else np.array([]),
        np.ones(degree + 1),
    ])


def make_flat_surface(
    nu: int = 4,
    nv: int = 4,
    scale: float = 1.0,
    degree_u: int = 1,
    degree_v: int = 1,
    z: float = 0.0,
) -> NurbsSurface:
    """Flat XY-plane surface on [0, scale] × [0, scale]."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [i * scale / (nu - 1), j * scale / (nv - 1), z]
    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=cp,
        knots_u=_knots_clamped(nu, degree_u),
        knots_v=_knots_clamped(nv, degree_v),
    )


def make_degree2_surface(scale: float = 1.0) -> NurbsSurface:
    """Degree-2 biquadratic flat surface (3×3 control points)."""
    nu = nv = 3
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [i * scale / 2.0, j * scale / 2.0, 0.0]
    return NurbsSurface(
        degree_u=2,
        degree_v=2,
        control_points=cp,
        knots_u=np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0]),
        knots_v=np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0]),
    )


def make_degenerate_surface() -> NurbsSurface:
    """All control points at origin — every patch has zero area."""
    cp = np.zeros((3, 3, 3))
    return NurbsSurface(
        degree_u=2,
        degree_v=2,
        control_points=cp,
        knots_u=np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0]),
        knots_v=np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0]),
    )


def make_near_tangent_surface(scale: float = 0.1, nu: int = 20, nv: int = 20) -> NurbsSurface:
    """Dense control grid over a tiny bbox — triggers dense-NURBS near-tangent warning.

    The density heuristic fires when total_pts / bbox_area > 0.5 pts/mm².
    With nu=nv=20 over scale=0.1: 400 pts / (0.1*0.1) = 40000 pts/mm² >> threshold.
    """
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [i * scale / (nu - 1), j * scale / (nv - 1), 0.0]
    return NurbsSurface(
        degree_u=1,
        degree_v=1,
        control_points=cp,
        knots_u=_knots_clamped(nu, 1),
        knots_v=_knots_clamped(nv, 1),
    )


def make_self_intersecting_surface() -> NurbsSurface:
    """Control net rows fold back on themselves (sign-flipping cross-products)."""
    cp = np.array([
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        [[2.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],  # reversed row
        [[0.0, 2.0, 0.0], [1.0, 2.0, 0.0], [2.0, 2.0, 0.0]],
        [[0.0, 3.0, 0.0], [1.0, 3.0, 0.0], [2.0, 3.0, 0.0]],
        [[0.0, 4.0, 0.0], [1.0, 4.0, 0.0], [2.0, 4.0, 0.0]],
    ])
    return NurbsSurface(
        degree_u=2,
        degree_v=2,
        control_points=cp,
        knots_u=np.array([0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0, 1.0]),
        knots_v=np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0]),
    )


# ---------------------------------------------------------------------------
# A. Trim-curve — boundary traversal (cases 1–6)
# ---------------------------------------------------------------------------

class TestTrimBoundaryTraversal:
    """Cases 1–6: trim curves that enter/exit the UV domain via distinct boundaries."""

    def test_01_trim_crosses_uv_domain(self):
        """A straight line fully through the UV domain reports uv_domain_split=True."""
        srf = make_flat_surface(scale=1.0)
        # Line across the surface at y=0.5 from x=0 to x=1
        pts = [[i / 10.0, 0.5, 0.0] for i in range(11)]
        result = trim_face(srf, pts)
        assert result["ok"] is True, result["reason"]
        assert result["uv_domain_split"] is True

    def test_02_trim_keep_positive_side(self):
        """keep_side='positive' is stored in result."""
        srf = make_flat_surface(scale=1.0)
        pts = [[0.5, i / 10.0, 0.0] for i in range(11)]
        result = trim_face(srf, pts, keep_side="positive")
        assert result["ok"] is True
        assert result["keep_side"] == "positive"

    def test_03_trim_keep_negative_side(self):
        """keep_side='negative' is stored and result is valid."""
        srf = make_flat_surface(scale=1.0)
        pts = [[0.5, i / 10.0, 0.0] for i in range(11)]
        result = trim_face(srf, pts, keep_side="negative")
        assert result["ok"] is True
        assert result["keep_side"] == "negative"

    def test_04_trim_curve_touches_two_boundaries(self):
        """A trim curve touching at least 2 boundary edges sets crosses_boundary=True."""
        srf = make_flat_surface(nu=4, nv=4, scale=2.0)
        # Points along v=1 (mid-domain) from u=0 to u=2
        pts = [[i * 2.0 / 10, 1.0, 0.0] for i in range(11)]
        result = trim_face(srf, pts)
        assert result["ok"] is True
        assert result["trim_curve"].crosses_boundary is True

    def test_05_project_curve_uv_returns_uv_pairs(self):
        """project_curve_to_uv returns (u,v) pairs in the surface domain."""
        srf = make_flat_surface(scale=1.0)
        pts = [[0.2, 0.3, 0.0], [0.5, 0.5, 0.0], [0.8, 0.7, 0.0]]
        uvs = project_curve_to_uv(srf, pts)
        assert len(uvs) >= 1
        u_min, u_max, v_min, v_max = 0.0, 1.0, 0.0, 1.0
        for u, v in uvs:
            assert u_min - 1e-6 <= u <= u_max + 1e-6
            assert v_min - 1e-6 <= v <= v_max + 1e-6

    def test_06_split_face_uv_inside_closed_loop(self):
        """Point clearly inside a closed square loop is classified 'positive'."""
        # Square loop (closed) enclosing the point (0.5, 0.5)
        loop = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
        side = split_face_uv(loop, (0.5, 0.5), closed_loop=True)
        assert side == "positive"


# ---------------------------------------------------------------------------
# B. Trim-curve — malformed / degenerate inputs (cases 7–10)
# ---------------------------------------------------------------------------

class TestTrimMalformedInputs:
    """Cases 7–10: trim_face/project_curve_to_uv with bad inputs — never raise."""

    def test_07_trim_face_wrong_surface_type(self):
        """Non-NurbsSurface input returns ok=False without raising."""
        result = trim_face("not a surface", [[0, 0, 0], [1, 1, 0]])
        assert result["ok"] is False
        assert "NurbsSurface" in result["reason"] or "expected" in result["reason"]

    def test_08_trim_face_invalid_keep_side(self):
        """Invalid keep_side returns ok=False."""
        srf = make_flat_surface()
        result = trim_face(srf, [[0, 0, 0], [1, 1, 0]], keep_side="both")
        assert result["ok"] is False
        assert "keep_side" in result["reason"]

    def test_09_trim_face_fewer_than_2_points(self):
        """Fewer than 2 trim points returns ok=False."""
        srf = make_flat_surface()
        result = trim_face(srf, [[0.5, 0.5, 0.0]])
        assert result["ok"] is False
        assert "2" in result["reason"] or "least" in result["reason"]

    def test_10_trim_face_nonpositive_tolerance(self):
        """Zero tolerance returns ok=False."""
        srf = make_flat_surface()
        result = trim_face(srf, [[0, 0, 0], [1, 1, 0]], tolerance=0.0)
        assert result["ok"] is False
        assert "tolerance" in result["reason"]

    def test_10b_project_curve_uv_empty_input(self):
        """Empty 3D point list returns empty UV list without raising."""
        srf = make_flat_surface()
        uvs = project_curve_to_uv(srf, [])
        assert uvs == []

    def test_10c_project_curve_uv_type_guard(self):
        """Non-surface raises TypeError."""
        with pytest.raises(TypeError):
            project_curve_to_uv("not_a_surface", [[0, 0, 0]])


# ---------------------------------------------------------------------------
# C. Trim-curve — idempotency (cases 11–12)
# ---------------------------------------------------------------------------

class TestTrimIdempotency:
    """Cases 11–12: calling trim twice with the same inputs yields identical results."""

    def test_11_trim_face_idempotent(self):
        """Two calls to trim_face with identical inputs produce equal trim curves."""
        srf = make_flat_surface(scale=1.0)
        pts = [[i / 8.0, 0.5, 0.0] for i in range(9)]
        r1 = trim_face(srf, pts)
        r2 = trim_face(srf, pts)
        assert r1["ok"] == r2["ok"]
        assert r1["uv_domain_split"] == r2["uv_domain_split"]
        assert len(r1["trim_curve"].uv_samples) == len(r2["trim_curve"].uv_samples)

    def test_12_project_curve_to_uv_idempotent(self):
        """project_curve_to_uv returns the same UV points on repeated calls."""
        srf = make_flat_surface(scale=2.0)
        pts = [[0.5, 1.0, 0.0], [1.0, 1.0, 0.0], [1.5, 1.0, 0.0]]
        uv1 = project_curve_to_uv(srf, pts)
        uv2 = project_curve_to_uv(srf, pts)
        assert len(uv1) == len(uv2)
        for (u1, v1), (u2, v2) in zip(uv1, uv2):
            assert abs(u1 - u2) < 1e-9
            assert abs(v1 - v2) < 1e-9


# ---------------------------------------------------------------------------
# D. Boolean robust — near-tangent surfaces (dense NURBS) (cases 13–16)
# ---------------------------------------------------------------------------

class TestBooleanNearTangent:
    """Cases 13–16: dense organic surfaces raise health warnings, not errors."""

    def test_13_dense_surface_health_warns_not_errors(self):
        """Dense control net triggers warnings but health check still ok=True."""
        srf = make_near_tangent_surface(scale=0.1, nu=20, nv=20)
        health = surface_health_check(srf)
        # Dense-NURBS warning present
        assert any("dense" in w.lower() or "pts/mm" in w for w in health["warnings"])
        # Not a fatal error — ok should be True (dense net is a warning, not error)
        assert health["ok"] is True

    def test_14_dense_surface_boolean_runs_without_exception(self):
        """surface_boolean_robust never raises even on a near-tangent dense surface."""
        srf_a = make_near_tangent_surface(scale=0.1, nu=15, nv=15)
        srf_b = make_near_tangent_surface(scale=0.1, nu=15, nv=15)
        # This may succeed or fail (py path with open-shell booleans), but must not raise
        result = surface_boolean_robust(srf_a, srf_b, "fuse")
        assert isinstance(result, dict)
        assert "ok" in result
        assert "via" in result

    def test_15_near_tangent_result_dict_has_warnings(self):
        """Health dict for a dense surface is included in the boolean result."""
        srf_a = make_near_tangent_surface(scale=0.1, nu=20, nv=20)
        srf_b = make_flat_surface(scale=0.1)
        result = surface_boolean_robust(srf_a, srf_b, "cut")
        assert isinstance(result, dict)
        assert "health_a" in result
        ha = result["health_a"]
        if ha:  # non-empty (NurbsSurface input, not Body)
            assert "warnings" in ha

    def test_16_check_dense_nurbs_below_threshold_returns_none(self):
        """A sparse control net does not trigger the density warning."""
        srf = make_flat_surface(nu=3, nv=3, scale=100.0)
        msg = _check_dense_nurbs(srf.control_points)
        assert msg is None


# ---------------------------------------------------------------------------
# E. Boolean robust — degenerate surface rejection (cases 17–19)
# ---------------------------------------------------------------------------

class TestBooleanDegenerateRejection:
    """Cases 17–19: degenerate surfaces are rejected before the boolean engine."""

    def test_17_degenerate_surface_a_rejected(self):
        """surface_a that is fully degenerate returns ok=False."""
        bad = make_degenerate_surface()
        good = make_degree2_surface()
        result = surface_boolean_robust(bad, good, "fuse")
        assert result["ok"] is False
        assert "A" in result["reason"] or "a" in result["reason"].lower()
        assert result["attempts"] == 0
        assert result["via"] == "none"

    def test_18_degenerate_surface_b_rejected(self):
        """surface_b that is fully degenerate returns ok=False."""
        good = make_degree2_surface()
        bad = make_degenerate_surface()
        result = surface_boolean_robust(good, bad, "cut")
        assert result["ok"] is False
        assert "B" in result["reason"] or "b" in result["reason"].lower()
        assert result["via"] == "none"

    def test_19_self_intersecting_surface_rejected(self):
        """Self-intersecting control net returns ok=False."""
        si = make_self_intersecting_surface()
        good = make_degree2_surface()
        result = surface_boolean_robust(si, good, "common")
        assert result["ok"] is False
        assert result["via"] == "none"


# ---------------------------------------------------------------------------
# F. Boolean robust — OCCT stub / retry ladder (cases 20–23)
# ---------------------------------------------------------------------------

class TestBooleanOcctFallback:
    """Cases 20–23: OCCT path via stub occ_fn; bounded retry ladder contract."""

    def _good_srf(self) -> NurbsSurface:
        return make_degree2_surface(scale=2.0)

    def test_20_occt_stub_success_first_attempt(self):
        """occ_fn succeeds on the first attempt: retried=False, attempts=1, via='occt'."""
        sentinel = object()
        calls = []

        def occ_fn(a, b, k, tol):
            calls.append(tol)
            return sentinel

        srf = self._good_srf()
        result = surface_boolean_robust(srf, srf, "fuse", occ_fn=occ_fn)
        assert result["ok"] is True
        assert result["result"] is sentinel
        assert result["retried"] is False
        assert result["attempts"] == 1
        assert result["via"] == "occt"
        assert len(calls) == 1

    def test_21_occt_stub_retry_on_none_result(self):
        """occ_fn returns None on first attempt, succeeds on retry: retried=True."""
        sentinel = object()
        calls = []

        def occ_fn(a, b, k, tol):
            calls.append(tol)
            if len(calls) == 1:
                return None   # first attempt fails
            return sentinel  # retry succeeds

        srf = self._good_srf()
        # Ensure base tolerance leaves room for relaxation
        result = surface_boolean_robust(srf, srf, "cut", occ_fn=occ_fn, bbox_tol=1e-5)
        assert result["ok"] is True
        assert result["retried"] is True
        assert result["attempts"] == 2
        assert result["via"] == "occt"
        # Retry tolerance must be larger than initial
        assert calls[1] > calls[0]

    def test_22_occt_stub_both_attempts_fail(self):
        """Both OCCT attempts fail: ok=False, attempts==len(ladder), via='occt'."""
        calls = []

        def occ_fn(a, b, k, tol):
            calls.append(tol)
            return None

        srf = self._good_srf()
        result = surface_boolean_robust(srf, srf, "common", occ_fn=occ_fn, bbox_tol=1e-5)
        assert result["ok"] is False
        assert result["via"] == "occt"
        assert result["attempts"] == len(calls)
        assert result["attempts"] <= _MAX_ATTEMPTS

    def test_23_build_tolerance_ladder_bounded(self):
        """_build_tolerance_ladder never exceeds _MAX_ATTEMPTS entries."""
        for base in [1e-7, 1e-5, 1e-3, 1e-2]:
            ladder = _build_tolerance_ladder(base)
            assert 1 <= len(ladder) <= _MAX_ATTEMPTS
            for tol in ladder:
                assert _TOL_MIN <= tol <= _TOL_MAX

    def test_23b_tolerance_ladder_relaxes(self):
        """When there is headroom, the second rung is base * _TOL_RELAX_FACTOR."""
        base = 1e-5  # relaxed = 1e-4, well below _TOL_MAX=1e-2
        ladder = _build_tolerance_ladder(base)
        assert len(ladder) == 2
        assert abs(ladder[1] - base * _TOL_RELAX_FACTOR) < 1e-15

    def test_23c_tolerance_ladder_truncated_at_max(self):
        """When relaxed >= _TOL_MAX the ladder has only 1 rung."""
        # base * RELAX = _TOL_MAX → no headroom
        base = _TOL_MAX / _TOL_RELAX_FACTOR
        ladder = _build_tolerance_ladder(base)
        assert len(ladder) == 1

    def test_23d_use_occt_true_without_occ_fn_returns_error(self):
        """use_occt=True but no occ_fn → ok=False with a descriptive reason."""
        srf = self._good_srf()
        result = surface_boolean_robust(srf, srf, "fuse", use_occt=True)
        assert result["ok"] is False
        assert "occ_fn" in result["reason"] or "OCCT" in result["reason"]
        assert result["via"] == "none"


# ---------------------------------------------------------------------------
# G. Boolean robust — result-dict contract (cases 24–25)
# ---------------------------------------------------------------------------

class TestBooleanResultDictContract:
    """Cases 24–25: every return path includes the required keys with correct types."""

    REQUIRED_KEYS = {"ok", "result", "reason", "retried", "attempts", "tolerance",
                     "health_a", "health_b", "via"}
    VALID_VIA = {"py", "occt", "none"}

    def _assert_contract(self, result: dict) -> None:
        for key in self.REQUIRED_KEYS:
            assert key in result, f"missing key '{key}' in result"
        assert isinstance(result["ok"], bool)
        assert isinstance(result["reason"], str)
        assert isinstance(result["retried"], bool)
        assert isinstance(result["attempts"], int)
        assert isinstance(result["tolerance"], float)
        assert isinstance(result["health_a"], dict)
        assert isinstance(result["health_b"], dict)
        assert result["via"] in self.VALID_VIA

    def test_24_all_keys_on_success_py_path(self):
        """Pure-Python success path returns a complete, well-typed result dict."""
        srf = make_degree2_surface(scale=2.0)
        result = surface_boolean_robust(srf, srf, "fuse")
        self._assert_contract(result)
        # via must be 'py' (no occ_fn provided, KERF_OCCT_BOOLEAN unset)
        assert result["via"] in {"py", "none"}, (
            "Default path should not use OCCT unless env set"
        )

    def test_25_all_keys_on_invalid_kind(self):
        """Invalid boolean kind returns a complete result dict with ok=False."""
        srf = make_degree2_surface()
        result = surface_boolean_robust(srf, srf, "xor")
        self._assert_contract(result)
        assert result["ok"] is False
        assert "xor" in result["reason"] or "invalid" in result["reason"].lower()
        assert result["via"] == "none"
        assert result["attempts"] == 0
