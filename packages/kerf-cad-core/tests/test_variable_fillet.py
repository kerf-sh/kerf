"""
test_variable_fillet.py
=======================
Tests for GK-28: variable_radius_fillet_g1 — rolling-ball fillet with
G1 tangency along a varying radius law.

ORACLE asserts
--------------
1. radius_profile[k] == law(k / (n-1))  to ≤ 1e-7  for all k.
2. g1_residuals[k]   ≤ 1e-7             for all k  (rolling-ball G1 by
   construction).

All tests are hermetic: no OCC, no database, no network.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.surface_fillet import (
    _make_clamped_knots,
    variable_radius_fillet_g1,
)

# ---------------------------------------------------------------------------
# Surface factories (re-used from test_surface_fillet.py patterns)
# ---------------------------------------------------------------------------


def _make_clamped_knots_local(n: int, degree: int) -> np.ndarray:
    """Duplicate of the internal helper so tests are self-contained."""
    inner = max(0, n - degree - 1)
    parts = [np.zeros(degree + 1)]
    if inner > 0:
        parts.append(np.linspace(0.0, 1.0, inner + 2)[1:-1])
    parts.append(np.ones(degree + 1))
    return np.concatenate(parts)


def _make_xy_plane(z: float = 0.0, side: float = 2.0, nu: int = 4, nv: int = 4) -> NurbsSurface:
    cp = np.zeros((nu, nv, 3))
    xs = np.linspace(0.0, side, nu)
    ys = np.linspace(0.0, side, nv)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            cp[i, j] = [x, y, z]
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_make_clamped_knots_local(nu, 1),
        knots_v=_make_clamped_knots_local(nv, 1),
    )


def _make_xz_plane(y: float = 0.0, side: float = 2.0, nu: int = 4, nv: int = 4) -> NurbsSurface:
    cp = np.zeros((nu, nv, 3))
    xs = np.linspace(0.0, side, nu)
    zs = np.linspace(0.0, side, nv)
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            cp[i, j] = [x, y, z]
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_make_clamped_knots_local(nu, 1),
        knots_v=_make_clamped_knots_local(nv, 1),
    )


def _make_yz_plane(x: float = 0.0, side: float = 2.0, nu: int = 4, nv: int = 4) -> NurbsSurface:
    cp = np.zeros((nu, nv, 3))
    ys = np.linspace(0.0, side, nu)
    zs = np.linspace(0.0, side, nv)
    for i, y in enumerate(ys):
        for j, z in enumerate(zs):
            cp[i, j] = [x, y, z]
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_make_clamped_knots_local(nu, 1),
        knots_v=_make_clamped_knots_local(nv, 1),
    )


def _make_wavy_surface(nu: int = 5, nv: int = 5, amplitude: float = 0.2) -> NurbsSurface:
    """Non-planar surface: z = amplitude*sin(pi*x)*sin(pi*y) on [0,1]^2."""
    cp = np.zeros((nu, nv, 3))
    xs = np.linspace(0.0, 1.0, nu)
    ys = np.linspace(0.0, 1.0, nv)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            cp[i, j] = [x, y, amplitude * math.sin(math.pi * x) * math.sin(math.pi * y)]
    return NurbsSurface(
        degree_u=2, degree_v=2,
        control_points=cp,
        knots_u=_make_clamped_knots_local(nu, 2),
        knots_v=_make_clamped_knots_local(nv, 2),
    )


def _perp_planes() -> Tuple[NurbsSurface, NurbsSurface]:
    """Perpendicular planes: XY at z=0 and XZ at y=0."""
    return _make_xy_plane(), _make_xz_plane()


def _eval_law(t: float, law: List[Tuple[float, float]]) -> float:
    """Reference piecewise-linear law evaluation."""
    sorted_law = sorted(law, key=lambda x: x[0])
    if t <= sorted_law[0][0]:
        return sorted_law[0][1]
    if t >= sorted_law[-1][0]:
        return sorted_law[-1][1]
    for i in range(len(sorted_law) - 1):
        t0, r0 = sorted_law[i]
        t1, r1 = sorted_law[i + 1]
        if t0 <= t <= t1:
            alpha = (t - t0) / (t1 - t0)
            return r0 + alpha * (r1 - r0)
    return sorted_law[-1][1]


# ---------------------------------------------------------------------------
# Group 1 — Input validation
# ---------------------------------------------------------------------------

class TestVarFilletInputValidation:
    """variable_radius_fillet_g1 must never raise; always return ok=False dict."""

    def test_non_nurbs_surf1(self):
        s2 = _make_xy_plane()
        res = variable_radius_fillet_g1("bad", s2, [(0.0, 0.5), (1.0, 1.0)])
        assert res["ok"] is False
        assert "surf1" in res["reason"]

    def test_non_nurbs_surf2(self):
        s1 = _make_xy_plane()
        res = variable_radius_fillet_g1(s1, 42, [(0.0, 0.5), (1.0, 1.0)])
        assert res["ok"] is False
        assert "surf2" in res["reason"]

    def test_too_few_law_points(self):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, [(0.5, 1.0)])
        assert res["ok"] is False
        assert "2" in res["reason"] or "law" in res["reason"].lower()

    def test_empty_law(self):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, [])
        assert res["ok"] is False

    def test_out_of_range_t_above_1(self):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, [(0.0, 0.5), (1.5, 1.0)])
        assert res["ok"] is False
        assert "1.5" in res["reason"] or "outside" in res["reason"]

    def test_out_of_range_t_below_0(self):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, [(-0.1, 0.5), (1.0, 1.0)])
        assert res["ok"] is False

    def test_negative_radius_in_law(self):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, [(0.0, -0.5), (1.0, 1.0)])
        assert res["ok"] is False
        assert "radius" in res["reason"].lower() or "positive" in res["reason"].lower()

    def test_zero_radius_in_law(self):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, [(0.0, 0.0), (1.0, 1.0)])
        assert res["ok"] is False

    def test_non_pair_entry(self):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, [(0.0, 0.5, 99), (1.0, 1.0)])
        assert res["ok"] is False

    def test_result_dict_always_has_required_keys(self):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1("bad", s2, [(0.0, 1.0), (1.0, 1.0)])
        for key in ("ok", "reason", "fillet_surface", "rail_curve",
                    "trim_back_surf1", "trim_back_surf2",
                    "radius_profile", "g1_residuals", "diagnostics"):
            assert key in res, f"key '{key}' missing from error result"


# ---------------------------------------------------------------------------
# Group 2 — Oracle: radius_profile matches the input law to ≤ 1e-7
# ---------------------------------------------------------------------------

class TestRadiusOracle:
    """ORACLE: radius_profile[k] == law(k/(n-1)) to 1e-7 for all k."""

    _TOL = 1e-7

    def _check_law(self, law, samples=16):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, law, samples=samples)
        assert res["ok"] is True, res["reason"]
        rp = res["radius_profile"]
        n = len(rp)
        assert n == samples
        ts = np.linspace(0.0, 1.0, n)
        for k, (t, r_actual) in enumerate(zip(ts, rp)):
            r_expected = _eval_law(float(t), law)
            err = abs(r_actual - r_expected)
            assert err <= self._TOL, (
                f"k={k}: radius_profile[k]={r_actual} expected={r_expected} "
                f"error={err} > tol={self._TOL}"
            )

    def test_constant_law_0_5(self):
        self._check_law([(0.0, 0.5), (1.0, 0.5)])

    def test_constant_law_1_0(self):
        self._check_law([(0.0, 1.0), (1.0, 1.0)])

    def test_linear_increasing(self):
        """r increases from 0.3 to 0.8."""
        self._check_law([(0.0, 0.3), (1.0, 0.8)])

    def test_linear_decreasing(self):
        """r decreases from 0.9 to 0.2."""
        self._check_law([(0.0, 0.9), (1.0, 0.2)])

    def test_three_knots(self):
        """r: 0.5 → 1.0 → 0.4 (tent function)."""
        self._check_law([(0.0, 0.5), (0.5, 1.0), (1.0, 0.4)])

    def test_four_knots(self):
        """Four knots with arbitrary values."""
        self._check_law([(0.0, 0.3), (0.33, 0.7), (0.67, 0.5), (1.0, 0.9)])

    def test_many_knots(self):
        """Ten evenly-spaced knots."""
        ts = np.linspace(0.0, 1.0, 10)
        radii = [0.3 + 0.4 * abs(math.sin(math.pi * float(t))) for t in ts]
        law = list(zip(ts.tolist(), radii))
        self._check_law(law, samples=20)

    def test_samples_32(self):
        self._check_law([(0.0, 0.4), (0.5, 0.8), (1.0, 0.3)], samples=32)

    def test_samples_4_minimum(self):
        """samples clamped to minimum 4; law still respected."""
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(
            s1, s2, [(0.0, 0.5), (1.0, 0.9)], samples=4
        )
        assert res["ok"] is True
        assert len(res["radius_profile"]) == 4

    def test_law_sorted_internally(self):
        """Reversed-order law should produce same result as sorted law."""
        law_fwd = [(0.0, 0.5), (0.5, 0.8), (1.0, 0.3)]
        law_rev = [(1.0, 0.3), (0.5, 0.8), (0.0, 0.5)]
        s1, s2 = _perp_planes()
        res_fwd = variable_radius_fillet_g1(s1, s2, law_fwd, samples=10)
        res_rev = variable_radius_fillet_g1(s1, s2, law_rev, samples=10)
        assert res_fwd["ok"] is True
        assert res_rev["ok"] is True
        for a, b in zip(res_fwd["radius_profile"], res_rev["radius_profile"]):
            assert abs(a - b) < self._TOL

    def test_endpoint_radii_exact(self):
        """t=0 and t=1 endpoints match the law exactly."""
        law = [(0.0, 0.4), (1.0, 0.9)]
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, law, samples=8)
        assert res["ok"] is True
        rp = res["radius_profile"]
        assert abs(rp[0] - 0.4) < self._TOL
        assert abs(rp[-1] - 0.9) < self._TOL

    def test_midpoint_radius_exact(self):
        """At t=0.5 with a tent law, radius equals the peak."""
        law = [(0.0, 0.2), (0.5, 1.0), (1.0, 0.2)]
        s1, s2 = _perp_planes()
        # samples=9 → t=0.5 is the 5th station (index 4)
        res = variable_radius_fillet_g1(s1, s2, law, samples=9)
        assert res["ok"] is True
        rp = res["radius_profile"]
        # t[4] = 0.5 exactly for 9 samples
        assert abs(rp[4] - 1.0) < self._TOL


# ---------------------------------------------------------------------------
# Group 3 — Oracle: G1 tangency residuals ≤ 1e-7
# ---------------------------------------------------------------------------

class TestG1Oracle:
    """ORACLE: g1_residuals[k] ≤ 1e-7 for all k (rolling-ball G1)."""

    _TOL = 1e-7

    def _check_g1(self, s1, s2, law, samples=12):
        res = variable_radius_fillet_g1(s1, s2, law, samples=samples)
        assert res["ok"] is True, res["reason"]
        g1_res = res["g1_residuals"]
        assert len(g1_res) == samples
        for k, rv in enumerate(g1_res):
            assert rv <= self._TOL, (
                f"G1 residual at k={k}: {rv} > {self._TOL}"
            )

    def test_g1_constant_radius_perp_planes(self):
        s1, s2 = _perp_planes()
        self._check_g1(s1, s2, [(0.0, 0.5), (1.0, 0.5)])

    def test_g1_linear_increasing(self):
        s1, s2 = _perp_planes()
        self._check_g1(s1, s2, [(0.0, 0.3), (1.0, 0.8)])

    def test_g1_tent_law(self):
        s1, s2 = _perp_planes()
        self._check_g1(s1, s2, [(0.0, 0.3), (0.5, 0.8), (1.0, 0.3)])

    def test_g1_small_radius(self):
        s1, s2 = _perp_planes()
        self._check_g1(s1, s2, [(0.0, 0.1), (1.0, 0.2)])

    def test_g1_large_radius(self):
        s1, s2 = _perp_planes()
        self._check_g1(s1, s2, [(0.0, 1.5), (1.0, 2.0)])

    def test_g1_yz_xy_planes(self):
        """Different pair of planes."""
        s1 = _make_xy_plane()
        s2 = _make_yz_plane()
        self._check_g1(s1, s2, [(0.0, 0.4), (1.0, 0.6)])

    def test_g1_three_knots(self):
        s1, s2 = _perp_planes()
        self._check_g1(s1, s2, [(0.0, 0.5), (0.4, 1.0), (1.0, 0.3)])


# ---------------------------------------------------------------------------
# Group 4 — Return-dict contract
# ---------------------------------------------------------------------------

class TestReturnDictContract:

    def _res(self, law=None, samples=8):
        s1, s2 = _perp_planes()
        if law is None:
            law = [(0.0, 0.5), (1.0, 0.8)]
        return variable_radius_fillet_g1(s1, s2, law, samples=samples)

    def test_ok_true(self):
        assert self._res()["ok"] is True

    def test_reason_empty_on_success(self):
        assert self._res()["reason"] == ""

    def test_fillet_surface_is_nurbs(self):
        res = self._res()
        assert isinstance(res["fillet_surface"], NurbsSurface)

    def test_rail_curve_length(self):
        res = self._res(samples=8)
        assert len(res["rail_curve"]) == 8

    def test_trim_back_surf1_length(self):
        res = self._res(samples=8)
        assert len(res["trim_back_surf1"]) == 8

    def test_trim_back_surf2_length(self):
        res = self._res(samples=8)
        assert len(res["trim_back_surf2"]) == 8

    def test_radius_profile_length(self):
        res = self._res(samples=8)
        assert len(res["radius_profile"]) == 8

    def test_g1_residuals_length(self):
        res = self._res(samples=8)
        assert len(res["g1_residuals"]) == 8

    def test_diagnostics_keys(self):
        res = self._res()
        diag = res["diagnostics"]
        assert "max_g1_deviation" in diag
        assert "min_radius_violation" in diag
        assert "self_intersection" in diag

    def test_fillet_surface_degree_u_le_2(self):
        res = self._res()
        assert res["fillet_surface"].degree_u <= 2

    def test_fillet_cp_shape_3_rows(self):
        """Cross-section direction has 3 control rows (degree-2 arc)."""
        res = self._res(samples=8)
        cp = res["fillet_surface"].control_points
        assert cp.shape[0] == 3

    def test_fillet_cp_shape_v_matches_samples(self):
        """V direction has as many control points as samples."""
        res = self._res(samples=8)
        cp = res["fillet_surface"].control_points
        assert cp.shape[1] == 8

    def test_radius_profile_all_positive(self):
        res = self._res()
        assert all(r > 0.0 for r in res["radius_profile"])

    def test_g1_residuals_all_non_negative(self):
        res = self._res()
        assert all(r >= 0.0 for r in res["g1_residuals"])

    def test_rail_curve_points_are_3d(self):
        res = self._res()
        for pt in res["rail_curve"]:
            assert len(np.asarray(pt).ravel()) == 3

    def test_trim_back_surf1_points_are_3d(self):
        res = self._res()
        for pt in res["trim_back_surf1"]:
            assert len(np.asarray(pt).ravel()) == 3


# ---------------------------------------------------------------------------
# Group 5 — Radius profile monotonicity and scale
# ---------------------------------------------------------------------------

class TestRadiusProfileShape:

    def test_monotone_increasing(self):
        """Strictly increasing law → strictly increasing profile."""
        law = [(0.0, 0.3), (1.0, 0.9)]
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, law, samples=10)
        assert res["ok"] is True
        rp = res["radius_profile"]
        # Should be non-decreasing
        for i in range(len(rp) - 1):
            assert rp[i + 1] >= rp[i] - 1e-9

    def test_monotone_decreasing(self):
        law = [(0.0, 0.9), (1.0, 0.2)]
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, law, samples=10)
        assert res["ok"] is True
        rp = res["radius_profile"]
        for i in range(len(rp) - 1):
            assert rp[i + 1] <= rp[i] + 1e-9

    def test_wider_fillet_at_higher_radius(self):
        """Station with higher radius should have wider cross-section chord."""
        law = [(0.0, 0.3), (1.0, 0.9)]
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, law, samples=8)
        assert res["ok"] is True
        cp = res["fillet_surface"].control_points
        # chord at first station vs last station
        chord_0 = np.linalg.norm(cp[0, 0] - cp[2, 0])
        chord_n = np.linalg.norm(cp[0, -1] - cp[2, -1])
        # Last station has higher radius → wider chord
        assert chord_n > chord_0 - 1e-6

    def test_constant_law_gives_constant_profile(self):
        law = [(0.0, 0.6), (1.0, 0.6)]
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, law, samples=10)
        assert res["ok"] is True
        rp = res["radius_profile"]
        assert all(abs(r - 0.6) < 1e-7 for r in rp)


# ---------------------------------------------------------------------------
# Group 6 — General (non-planar) NURBS inputs
# ---------------------------------------------------------------------------

class TestVarFilletGeneralNurbs:

    def test_ok_true_wavy_surfaces(self):
        s1 = _make_wavy_surface()
        s2 = _make_xy_plane(z=-0.2)
        res = variable_radius_fillet_g1(
            s1, s2, [(0.0, 0.2), (1.0, 0.4)], samples=8
        )
        assert res["ok"] is True, res["reason"]

    def test_radius_oracle_wavy(self):
        """Radius oracle holds even for non-planar inputs."""
        s1 = _make_wavy_surface()
        s2 = _make_xy_plane(z=-0.2)
        law = [(0.0, 0.2), (0.5, 0.4), (1.0, 0.3)]
        res = variable_radius_fillet_g1(s1, s2, law, samples=10)
        assert res["ok"] is True
        ts = np.linspace(0.0, 1.0, 10)
        for t, r_actual in zip(ts, res["radius_profile"]):
            r_expected = _eval_law(float(t), law)
            assert abs(r_actual - r_expected) < 1e-7

    def test_fillet_surface_is_nurbs_wavy(self):
        s1 = _make_wavy_surface()
        s2 = _make_xy_plane(z=-0.2)
        res = variable_radius_fillet_g1(
            s1, s2, [(0.0, 0.2), (1.0, 0.4)], samples=8
        )
        assert isinstance(res["fillet_surface"], NurbsSurface)


# ---------------------------------------------------------------------------
# Group 7 — Never-raise contract
# ---------------------------------------------------------------------------

class TestNeverRaise:
    """All bad inputs must return ok=False, never raise."""

    @pytest.mark.parametrize("bad_surf1", [None, 42, "surf", [1, 2, 3]])
    def test_bad_surf1_never_raises(self, bad_surf1):
        s2 = _make_xy_plane()
        res = variable_radius_fillet_g1(bad_surf1, s2, [(0.0, 1.0), (1.0, 1.0)])
        assert res["ok"] is False

    @pytest.mark.parametrize("bad_surf2", [None, 42, "surf", [1, 2, 3]])
    def test_bad_surf2_never_raises(self, bad_surf2):
        s1 = _make_xy_plane()
        res = variable_radius_fillet_g1(s1, bad_surf2, [(0.0, 1.0), (1.0, 1.0)])
        assert res["ok"] is False

    @pytest.mark.parametrize("bad_law", [
        [],
        [(0.5, 1.0)],
        [(0.0, -1.0), (1.0, 1.0)],
        [(0.0, 0.0), (1.0, 1.0)],
        [(0.0, 1.0), (2.0, 1.0)],
        [(-0.5, 1.0), (1.0, 1.0)],
    ])
    def test_bad_law_never_raises(self, bad_law):
        s1, s2 = _perp_planes()
        res = variable_radius_fillet_g1(s1, s2, bad_law)
        assert res["ok"] is False
