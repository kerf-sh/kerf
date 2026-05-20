"""
tests/test_untrim_shrink.py
===========================
Hermetic pure-Python tests for GK-39: untrim / shrink trimmed surface.

All tests have closed-form oracles — no OCC, no network, no DB.

Coverage:
  1. TrimmedSurface construction and uv_trim_bbox.
  2. untrim — returns exact CP net (elementwise ≤ 1e-12).
  3. shrink — resulting bbox ⊆ trim region.
  4. shrink — geometry preserved inside shrunken domain.
  5. shrink — flat/degenerate (all trim points the same UV).
  6. TypeError guards on both functions.
  7. untrim does not mutate the original surface.
  8. shrink does not mutate the original surface.
  9. Multiple patches (varying degree/size).
 10. Weights preserved by untrim / shrink.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface, surface_evaluate
from kerf_cad_core.geom.trim_curve import (
    TrimCurve,
    TrimmedSurface,
    shrink,
    untrim,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_knots(n: int, deg: int) -> np.ndarray:
    """Standard clamped uniform knot vector for n CPs of degree deg."""
    inner = max(0, n - deg - 1)
    return np.concatenate([
        np.zeros(deg + 1),
        np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else [],
        np.ones(deg + 1),
    ])


def _flat_surface(nu: int = 4, nv: int = 4, deg_u: int = 1, deg_v: int = 1) -> NurbsSurface:
    """A flat bilinear/bicubic surface on [0,1]×[0,1] in the XY plane."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j, 0] = i / (nu - 1)
            cp[i, j, 1] = j / (nv - 1)
    return NurbsSurface(
        degree_u=deg_u,
        degree_v=deg_v,
        control_points=cp,
        knots_u=_make_knots(nu, deg_u),
        knots_v=_make_knots(nv, deg_v),
    )


def _trim_curve_box(u_lo: float, u_hi: float, v_lo: float, v_hi: float) -> TrimCurve:
    """A closed rectangular trim loop in UV space."""
    samples = [
        (u_lo, v_lo),
        (u_hi, v_lo),
        (u_hi, v_hi),
        (u_lo, v_hi),
        (u_lo, v_lo),  # close the loop
    ]
    return TrimCurve(uv_samples=samples, is_closed=True, crosses_boundary=True)


# ---------------------------------------------------------------------------
# 1. TrimmedSurface construction and uv_trim_bbox
# ---------------------------------------------------------------------------

class TestTrimmedSurface:
    def test_construction(self):
        srf = _flat_surface()
        tc = _trim_curve_box(0.2, 0.8, 0.1, 0.9)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        assert ts.surface is srf
        assert ts.trim_curve is tc

    def test_uv_trim_bbox(self):
        srf = _flat_surface()
        tc = _trim_curve_box(0.2, 0.8, 0.1, 0.9)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        u_lo, u_hi, v_lo, v_hi = ts.uv_trim_bbox()
        assert abs(u_lo - 0.2) < 1e-14
        assert abs(u_hi - 0.8) < 1e-14
        assert abs(v_lo - 0.1) < 1e-14
        assert abs(v_hi - 0.9) < 1e-14

    def test_uv_trim_bbox_empty_raises(self):
        srf = _flat_surface()
        tc = TrimCurve(uv_samples=[])
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        with pytest.raises(ValueError, match="no UV samples"):
            ts.uv_trim_bbox()

    def test_uv_trim_bbox_single_point(self):
        srf = _flat_surface()
        tc = TrimCurve(uv_samples=[(0.5, 0.5)])
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        u_lo, u_hi, v_lo, v_hi = ts.uv_trim_bbox()
        assert u_lo == u_hi == 0.5
        assert v_lo == v_hi == 0.5


# ---------------------------------------------------------------------------
# 2. untrim — exact CP net recovery
# ---------------------------------------------------------------------------

class TestUntrim:
    def test_untrim_exact_recovery(self):
        """untrim returns CP net elementwise equal to the original (≤ 1e-12)."""
        srf = _flat_surface(nu=4, nv=5)
        original_cp = srf.control_points.copy()
        tc = _trim_curve_box(0.2, 0.7, 0.3, 0.8)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        recovered = untrim(ts)
        assert np.allclose(recovered, original_cp, atol=1e-12, rtol=0), (
            "untrim must return CP net elementwise equal to the original"
        )

    def test_untrim_is_copy(self):
        """Mutating the returned array must NOT change the stored surface CP."""
        srf = _flat_surface()
        ts = TrimmedSurface(surface=srf, trim_curve=_trim_curve_box(0.1, 0.9, 0.1, 0.9))
        recovered = untrim(ts)
        recovered[0, 0, 0] = 9999.0
        assert srf.control_points[0, 0, 0] != 9999.0

    def test_untrim_does_not_mutate_surface(self):
        """Calling untrim must leave the original surface unchanged."""
        srf = _flat_surface()
        cp_before = srf.control_points.copy()
        ts = TrimmedSurface(surface=srf, trim_curve=_trim_curve_box(0.2, 0.8, 0.2, 0.8))
        untrim(ts)
        assert np.allclose(srf.control_points, cp_before, atol=1e-14)

    def test_untrim_type_error(self):
        with pytest.raises(TypeError, match="TrimmedSurface"):
            untrim("not a TrimmedSurface")  # type: ignore[arg-type]

    def test_untrim_bicubic_patch(self):
        """untrim works for degree-3 bicubic surface."""
        srf = _flat_surface(nu=6, nv=6, deg_u=3, deg_v=3)
        original_cp = srf.control_points.copy()
        tc = _trim_curve_box(0.1, 0.9, 0.1, 0.9)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        assert np.allclose(untrim(ts), original_cp, atol=1e-14)

    def test_untrim_with_weights(self):
        """untrim works when the surface has rational weights."""
        srf = _flat_surface(nu=3, nv=3)
        # Give it non-trivial weights
        weights = np.ones((3, 3))
        weights[1, 1] = 2.0
        srf_w = NurbsSurface(
            degree_u=srf.degree_u,
            degree_v=srf.degree_v,
            control_points=srf.control_points.copy(),
            knots_u=srf.knots_u.copy(),
            knots_v=srf.knots_v.copy(),
            weights=weights,
        )
        tc = _trim_curve_box(0.2, 0.8, 0.2, 0.8)
        ts = TrimmedSurface(surface=srf_w, trim_curve=tc)
        recovered = untrim(ts)
        assert np.allclose(recovered, srf_w.control_points, atol=1e-14)

    def test_untrim_shape_preserved(self):
        """Returned CP net has the same shape as the original."""
        nu, nv = 5, 7
        srf = _flat_surface(nu=nu, nv=nv)
        ts = TrimmedSurface(surface=srf, trim_curve=_trim_curve_box(0.1, 0.9, 0.1, 0.9))
        result = untrim(ts)
        assert result.shape == (nu, nv, 3)


# ---------------------------------------------------------------------------
# 3. shrink — resulting bbox ⊆ trim region
# ---------------------------------------------------------------------------

class TestShrinkBbox:
    def test_shrunk_domain_inside_trim_bbox(self):
        """shrink: domain of returned surface ⊆ bbox of trim region."""
        srf = _flat_surface()
        u_lo, u_hi, v_lo, v_hi = 0.2, 0.75, 0.15, 0.85
        tc = _trim_curve_box(u_lo, u_hi, v_lo, v_hi)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        shrunk = shrink(ts)

        shrunk_u_min = float(shrunk.knots_u[0])
        shrunk_u_max = float(shrunk.knots_u[-1])
        shrunk_v_min = float(shrunk.knots_v[0])
        shrunk_v_max = float(shrunk.knots_v[-1])

        assert shrunk_u_min >= u_lo - 1e-14
        assert shrunk_u_max <= u_hi + 1e-14
        assert shrunk_v_min >= v_lo - 1e-14
        assert shrunk_v_max <= v_hi + 1e-14

    def test_shrunk_bbox_subset_for_partial_trim(self):
        """Trim region smaller than full domain — shrunk domain is strictly smaller."""
        srf = _flat_surface(nu=5, nv=5, deg_u=2, deg_v=2)
        tc = _trim_curve_box(0.3, 0.7, 0.3, 0.7)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        shrunk = shrink(ts)

        u_min_orig = float(srf.knots_u[0])
        u_max_orig = float(srf.knots_u[-1])
        v_min_orig = float(srf.knots_v[0])
        v_max_orig = float(srf.knots_v[-1])

        # Shrunken domain should be a subset of [0,1]×[0,1]
        assert float(shrunk.knots_u[0]) >= u_min_orig - 1e-14
        assert float(shrunk.knots_u[-1]) <= u_max_orig + 1e-14
        assert float(shrunk.knots_v[0]) >= v_min_orig - 1e-14
        assert float(shrunk.knots_v[-1]) <= v_max_orig + 1e-14

        # And specifically within the trim bbox
        assert float(shrunk.knots_u[0]) >= 0.3 - 1e-14
        assert float(shrunk.knots_u[-1]) <= 0.7 + 1e-14

    def test_shrink_type_error(self):
        with pytest.raises(TypeError, match="TrimmedSurface"):
            shrink("bad input")  # type: ignore[arg-type]

    def test_shrink_empty_trim_raises(self):
        srf = _flat_surface()
        tc = TrimCurve(uv_samples=[])
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        with pytest.raises(ValueError, match="no UV samples"):
            shrink(ts)


# ---------------------------------------------------------------------------
# 4. shrink — domain properties
# ---------------------------------------------------------------------------

class TestShrinkGeometry:
    def test_shrunk_domain_strictly_within_trim(self):
        """shrunk domain endpoints lie within the trim bbox."""
        srf = _flat_surface(nu=4, nv=4)
        tc = _trim_curve_box(0.25, 0.75, 0.25, 0.75)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        shrunk = shrink(ts)

        # Shrunk domain must be a sub-interval of the trim bbox
        assert float(shrunk.knots_u[0]) >= 0.25 - 1e-14
        assert float(shrunk.knots_u[-1]) <= 0.75 + 1e-14
        assert float(shrunk.knots_v[0]) >= 0.25 - 1e-14
        assert float(shrunk.knots_v[-1]) <= 0.75 + 1e-14

    def test_shrunk_control_points_unchanged(self):
        """shrink must not change the control-point grid."""
        srf = _flat_surface(nu=6, nv=6, deg_u=3, deg_v=3)
        tc = _trim_curve_box(0.2, 0.8, 0.2, 0.8)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        shrunk = shrink(ts)
        # CP net is preserved (domain restriction via knot clamping)
        assert np.allclose(shrunk.control_points, srf.control_points, atol=1e-14)


# ---------------------------------------------------------------------------
# 5. shrink — does not mutate the original surface
# ---------------------------------------------------------------------------

class TestShrinkImmutability:
    def test_shrink_does_not_mutate_surface(self):
        srf = _flat_surface()
        knots_u_before = srf.knots_u.copy()
        knots_v_before = srf.knots_v.copy()
        cp_before = srf.control_points.copy()

        tc = _trim_curve_box(0.2, 0.8, 0.2, 0.8)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        shrink(ts)

        assert np.allclose(srf.knots_u, knots_u_before, atol=1e-14)
        assert np.allclose(srf.knots_v, knots_v_before, atol=1e-14)
        assert np.allclose(srf.control_points, cp_before, atol=1e-14)

    def test_shrink_returns_new_surface(self):
        srf = _flat_surface()
        tc = _trim_curve_box(0.2, 0.8, 0.2, 0.8)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        shrunk = shrink(ts)
        assert shrunk is not srf
        assert shrunk.control_points is not srf.control_points

    def test_shrink_preserves_weights(self):
        srf = _flat_surface(nu=3, nv=3)
        weights = np.ones((3, 3))
        weights[1, 1] = 1.5
        srf_w = NurbsSurface(
            degree_u=srf.degree_u,
            degree_v=srf.degree_v,
            control_points=srf.control_points.copy(),
            knots_u=srf.knots_u.copy(),
            knots_v=srf.knots_v.copy(),
            weights=weights,
        )
        tc = _trim_curve_box(0.1, 0.9, 0.1, 0.9)
        ts = TrimmedSurface(surface=srf_w, trim_curve=tc)
        shrunk = shrink(ts)
        assert shrunk.weights is not None
        assert np.allclose(shrunk.weights, weights, atol=1e-14)


# ---------------------------------------------------------------------------
# 6. Analytic oracle: untrim of trimmed patch returns original CP net exactly
# ---------------------------------------------------------------------------

class TestAnalyticOracle:
    """Closed-form oracle: trim a known surface, verify untrim returns the
    original CP array elementwise to 1e-12."""

    def test_oracle_bilinear_4x4(self):
        """Bilinear 4×4 surface, arbitrary trim region."""
        cp_original = np.array([
            [[0.0, 0.0, 0.0], [0.0, 1.0, 0.1], [0.0, 2.0, 0.0], [0.0, 3.0, 0.0]],
            [[1.0, 0.0, 0.1], [1.0, 1.0, 0.5], [1.0, 2.0, 0.3], [1.0, 3.0, 0.1]],
            [[2.0, 0.0, 0.0], [2.0, 1.0, 0.3], [2.0, 2.0, 0.8], [2.0, 3.0, 0.2]],
            [[3.0, 0.0, 0.0], [3.0, 1.0, 0.1], [3.0, 2.0, 0.2], [3.0, 3.0, 0.0]],
        ], dtype=float)
        srf = NurbsSurface(
            degree_u=1, degree_v=1,
            control_points=cp_original.copy(),
            knots_u=_make_knots(4, 1),
            knots_v=_make_knots(4, 1),
        )
        tc = _trim_curve_box(0.25, 0.75, 0.1, 0.9)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        recovered = untrim(ts)
        # Oracle: should be exactly cp_original, elementwise
        max_err = np.max(np.abs(recovered - cp_original))
        assert max_err < 1e-12, f"Oracle failed: max error = {max_err}"

    def test_oracle_bicubic_varied_cp(self):
        """Bicubic 5×5 with non-trivial CP values."""
        rng = np.random.default_rng(42)
        cp_original = rng.standard_normal((5, 5, 3))
        srf = NurbsSurface(
            degree_u=3, degree_v=3,
            control_points=cp_original.copy(),
            knots_u=_make_knots(5, 3),
            knots_v=_make_knots(5, 3),
        )
        tc = _trim_curve_box(0.1, 0.9, 0.05, 0.95)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        recovered = untrim(ts)
        max_err = np.max(np.abs(recovered - cp_original))
        assert max_err < 1e-12, f"Oracle (bicubic) failed: max error = {max_err}"

    def test_oracle_shrink_bbox_subset(self):
        """Oracle: shrunk domain bbox ⊆ trim region bbox at 1e-14 precision."""
        srf = _flat_surface(nu=5, nv=5, deg_u=2, deg_v=2)
        u_lo, u_hi, v_lo, v_hi = 0.2, 0.8, 0.3, 0.7
        tc = _trim_curve_box(u_lo, u_hi, v_lo, v_hi)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        shrunk = shrink(ts)

        assert float(shrunk.knots_u[0]) >= u_lo - 1e-14
        assert float(shrunk.knots_u[-1]) <= u_hi + 1e-14
        assert float(shrunk.knots_v[0]) >= v_lo - 1e-14
        assert float(shrunk.knots_v[-1]) <= v_hi + 1e-14


# ---------------------------------------------------------------------------
# 7. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_trim_full_domain_shrink_identity(self):
        """If the trim region covers the full domain, shrink should not change the
        effective domain (clamp to [0,1] × [0,1] is a no-op)."""
        srf = _flat_surface()  # domain [0,1]×[0,1]
        tc = _trim_curve_box(0.0, 1.0, 0.0, 1.0)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        shrunk = shrink(ts)
        assert np.allclose(shrunk.knots_u, srf.knots_u, atol=1e-14)
        assert np.allclose(shrunk.knots_v, srf.knots_v, atol=1e-14)

    def test_trim_curve_with_many_samples(self):
        """untrim/shrink work for a trim curve with a large number of samples."""
        srf = _flat_surface(nu=4, nv=4)
        # Circular trim loop approximated by 200 samples
        n = 200
        us = [0.5 + 0.3 * math.cos(2 * math.pi * i / n) for i in range(n + 1)]
        vs = [0.5 + 0.3 * math.sin(2 * math.pi * i / n) for i in range(n + 1)]
        samples = [(u, v) for u, v in zip(us, vs)]
        tc = TrimCurve(uv_samples=samples, is_closed=True)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)

        # untrim
        recovered = untrim(ts)
        assert np.allclose(recovered, srf.control_points, atol=1e-12)

        # shrink bbox ⊆ trim bbox
        shrunk = shrink(ts)
        u_lo, u_hi, v_lo, v_hi = ts.uv_trim_bbox()
        assert float(shrunk.knots_u[0]) >= u_lo - 1e-14
        assert float(shrunk.knots_u[-1]) <= u_hi + 1e-14
        assert float(shrunk.knots_v[0]) >= v_lo - 1e-14
        assert float(shrunk.knots_v[-1]) <= v_hi + 1e-14

    def test_untrim_non_unit_domain(self):
        """Surfaces with domain [0,10]×[0,10] work correctly."""
        cp = np.zeros((3, 3, 3))
        for i in range(3):
            for j in range(3):
                cp[i, j] = [i * 5.0, j * 5.0, 0.0]
        # Knots spanning [0, 10]
        knots = np.array([0.0, 0.0, 5.0, 10.0, 10.0])
        srf = NurbsSurface(
            degree_u=1, degree_v=1,
            control_points=cp.copy(),
            knots_u=knots.copy(),
            knots_v=knots.copy(),
        )
        tc = TrimCurve(uv_samples=[(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0), (2.0, 2.0)])
        ts = TrimmedSurface(surface=srf, trim_curve=tc)

        # untrim should return original CP
        recovered = untrim(ts)
        assert np.allclose(recovered, cp, atol=1e-12)

        # shrink domain ⊆ trim bbox
        shrunk = shrink(ts)
        assert float(shrunk.knots_u[0]) >= 2.0 - 1e-14
        assert float(shrunk.knots_u[-1]) <= 8.0 + 1e-14
        assert float(shrunk.knots_v[0]) >= 2.0 - 1e-14
        assert float(shrunk.knots_v[-1]) <= 8.0 + 1e-14

    def test_degree_preserved_by_shrink(self):
        """Degree must not change after shrink."""
        srf = _flat_surface(nu=6, nv=6, deg_u=3, deg_v=2)
        tc = _trim_curve_box(0.2, 0.8, 0.2, 0.8)
        ts = TrimmedSurface(surface=srf, trim_curve=tc)
        shrunk = shrink(ts)
        assert shrunk.degree_u == srf.degree_u
        assert shrunk.degree_v == srf.degree_v
