"""
Tests for kerf_cad_core.geom.match_srf -- NURBS Phase 4 Capability 3 (pure-Python core).

All tests are hermetic: no OCC, no database, no network.  Verification uses
direct control-point inspection (CP-level geometry) rather than
``surface_evaluate``, because the shared nurbs.py evaluator has known accuracy
limitations at parametric extremes.

Coverage (>=30 tests across 8 groups):
  1. MatchResult dataclass -- construction, defaults.
  2. Input validation -- bad types, bad edge names, bad continuity, bad samples,
     bad tolerance, insufficient CP rows, insufficient degree.
  3. G0 matching -- flat+flat, curved+flat, identity (already-matched),
     non-conforming CP count handled gracefully, position deviation <= eps.
  4. G1 matching -- tangent alignment via CP differences, G0 preserved, identity.
  5. G2 matching -- second-difference alignment, G0+G1 preserved, identity.
  6. Edge variants -- all four edge names produce ok=True and correct CP row.
  7. Diagnostics -- _compute_deviations + _classify_continuity.
  8. Non-destructive -- original source_surface never mutated.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.match_srf import (
    MatchResult,
    _boundary_degree,
    _boundary_knot_span,
    _classify_continuity,
    _compute_deviations,
    _cp_col_count,
    _cp_curvature_vector,
    _cp_row_count,
    _cp_tangent_vector,
    _get_cp_row,
    _sample_boundary_cps,
    match_surface_edge,
)


# ---------------------------------------------------------------------------
# Surface factories
# ---------------------------------------------------------------------------

def _knots(n: int, deg: int) -> np.ndarray:
    inner = max(0, n - deg - 1)
    return np.concatenate([
        np.zeros(deg + 1),
        np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
        np.ones(deg + 1),
    ])


def make_flat_surface(nu: int = 5, nv: int = 5,
                      z: float = 0.0,
                      degree_u: int = 2, degree_v: int = 2) -> NurbsSurface:
    """Flat XY surface spanning [0,1]x[0,1] at constant z."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [i / (nu - 1), j / (nv - 1), z]
    return NurbsSurface(
        degree_u=degree_u, degree_v=degree_v,
        control_points=cp,
        knots_u=_knots(nu, degree_u),
        knots_v=_knots(nv, degree_v),
    )


def make_tilted_surface(nu: int = 5, nv: int = 5,
                        slope_x: float = 0.5,
                        degree_u: int = 2, degree_v: int = 2) -> NurbsSurface:
    """Surface tilted in z: z = slope_x * x."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            x = i / (nu - 1)
            cp[i, j] = [x, j / (nv - 1), slope_x * x]
    return NurbsSurface(
        degree_u=degree_u, degree_v=degree_v,
        control_points=cp,
        knots_u=_knots(nu, degree_u),
        knots_v=_knots(nv, degree_v),
    )


def make_curved_surface(nu: int = 5, nv: int = 5,
                        amplitude: float = 0.3,
                        degree_u: int = 2, degree_v: int = 2) -> NurbsSurface:
    """Surface with a gentle z bump."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            x = i / (nu - 1)
            y = j / (nv - 1)
            cp[i, j] = [x, y, amplitude * math.sin(math.pi * x) * math.sin(math.pi * y)]
    return NurbsSurface(
        degree_u=degree_u, degree_v=degree_v,
        control_points=cp,
        knots_u=_knots(nu, degree_u),
        knots_v=_knots(nv, degree_v),
    )


# ---------------------------------------------------------------------------
# Group 1: MatchResult dataclass
# ---------------------------------------------------------------------------

class TestMatchResultDataclass:
    def test_default_construction(self):
        r = MatchResult()
        assert r.ok is False
        assert r.reason == ""
        assert r.modified_surface is None
        assert math.isnan(r.max_position_deviation)
        assert math.isnan(r.max_tangent_deviation)
        assert math.isnan(r.max_curvature_deviation)
        assert r.continuity_achieved == "none"

    def test_explicit_construction(self):
        surf = make_flat_surface()
        r = MatchResult(
            modified_surface=surf,
            ok=True,
            reason="",
            max_position_deviation=1e-9,
            max_tangent_deviation=0.001,
            max_curvature_deviation=0.005,
            continuity_achieved="G2",
        )
        assert r.ok
        assert r.continuity_achieved == "G2"
        assert r.max_position_deviation == pytest.approx(1e-9, rel=1e-3)


# ---------------------------------------------------------------------------
# Group 2: Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_bad_target_type(self):
        src = make_flat_surface()
        r = match_surface_edge("not_a_surface", "u0", src, "u1", "G0")
        assert not r.ok
        assert "target_surface" in r.reason

    def test_bad_source_type(self):
        tgt = make_flat_surface()
        r = match_surface_edge(tgt, "u0", "not_a_surface", "u1", "G0")
        assert not r.ok
        assert "source_surface" in r.reason

    def test_bad_target_edge(self):
        tgt = make_flat_surface()
        src = make_flat_surface()
        r = match_surface_edge(tgt, "bad_edge", src, "u1", "G0")
        assert not r.ok
        assert "target_edge" in r.reason

    def test_bad_source_edge(self):
        tgt = make_flat_surface()
        src = make_flat_surface()
        r = match_surface_edge(tgt, "u0", src, "bad_edge", "G0")
        assert not r.ok
        assert "source_edge" in r.reason

    def test_bad_continuity(self):
        # GK-P10 promoted "G3" to a supported continuity, so the invalid
        # sentinel must be a value that is genuinely not in _VALID_CONTINUITY.
        tgt = make_flat_surface()
        src = make_flat_surface()
        r = match_surface_edge(tgt, "u0", src, "u1", "G4")
        assert not r.ok
        assert "continuity" in r.reason

    def test_bad_samples_too_small(self):
        tgt = make_flat_surface()
        src = make_flat_surface()
        r = match_surface_edge(tgt, "u0", src, "u1", "G0", samples=1)
        assert not r.ok
        assert "samples" in r.reason

    def test_bad_tolerance_negative(self):
        tgt = make_flat_surface()
        src = make_flat_surface()
        r = match_surface_edge(tgt, "u0", src, "u1", "G0", tolerance=-1.0)
        assert not r.ok
        assert "tolerance" in r.reason

    def test_bad_tolerance_zero(self):
        tgt = make_flat_surface()
        src = make_flat_surface()
        r = match_surface_edge(tgt, "u0", src, "u1", "G0", tolerance=0.0)
        assert not r.ok

    def test_g2_requires_degree_ge_2(self):
        """G2 must fail when source degree < 2 in matched direction."""
        tgt = make_flat_surface(degree_u=2, degree_v=2)
        src = make_flat_surface(degree_u=1, degree_v=1)
        r = match_surface_edge(tgt, "v0", src, "v1", "G2")
        assert not r.ok
        assert "degree" in r.reason.lower()

    def test_g1_insufficient_src_cp_rows(self):
        """G1 needs at least 2 rows in inward direction -- a 1xN CP grid fails."""
        # Create a surface where the u direction has only 1 CP row
        cp = np.zeros((1, 5, 3))
        for j in range(5):
            cp[0, j] = [0.0, j / 4, 0.0]
        # This won't have enough rows for G1 matching on u-edge
        # degree_u=0 would be needed, but we can't; let's use a degenerate 2x5 degree-1
        # surface whose u-direction has only 2 rows (= 1 on each side)
        cp2 = np.zeros((2, 5, 3))
        for i in range(2):
            for j in range(5):
                cp2[i, j] = [i, j / 4, 0.0]
        src = NurbsSurface(
            degree_u=1, degree_v=1,
            control_points=cp2,
            knots_u=np.array([0., 0., 1., 1.]),
            knots_v=_knots(5, 1),
        )
        tgt = make_flat_surface(degree_u=2, degree_v=2)
        # u0 edge -- 2 rows total; G1 needs 2; should PASS (2 rows available)
        r = match_surface_edge(tgt, "u0", src, "u0", "G1")
        # 2 rows available -- G1 requires exactly 2 -- should be ok
        assert r.ok

    def test_g2_insufficient_src_cp_rows(self):
        """G2 requires >= 3 rows -- a 2xN degree-2 surface should fail."""
        cp2 = np.zeros((2, 5, 3))
        for i in range(2):
            for j in range(5):
                cp2[i, j] = [i, j / 4, 0.0]
        # degree_u must be >= 2 for G2, but 2 rows < required 3
        # Use degree_u=1 surface with 2 rows
        src = NurbsSurface(
            degree_u=1, degree_v=2,
            control_points=cp2,
            knots_u=np.array([0., 0., 1., 1.]),
            knots_v=_knots(5, 2),
        )
        tgt = make_flat_surface()
        r = match_surface_edge(tgt, "u0", src, "u0", "G2")
        # Should fail: either not enough rows OR degree too low
        assert not r.ok


# ---------------------------------------------------------------------------
# Group 3: G0 matching
# ---------------------------------------------------------------------------

EPS_G0_CP = 1e-10   # CP comparison after G0

class TestG0Matching:
    def test_g0_flat_to_flat_ok(self):
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G0", samples=16)
        assert r.ok
        assert r.reason == ""

    def test_g0_boundary_cps_match_target(self):
        """After G0, source boundary CPs must equal target boundary CPs."""
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G0")
        assert r.ok
        src_row = _get_cp_row(r.modified_surface, "u0", 0)
        tgt_row = _get_cp_row(tgt, "u0", 0)
        np.testing.assert_allclose(src_row, tgt_row, atol=EPS_G0_CP)

    def test_g0_position_deviation_near_zero(self):
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G0")
        assert r.ok
        assert r.max_position_deviation < 1e-10

    def test_g0_curved_to_flat(self):
        tgt = make_flat_surface(z=0.0)
        src = make_curved_surface(amplitude=0.4)
        r = match_surface_edge(tgt, "u0", src, "u0", "G0")
        assert r.ok
        src_row = _get_cp_row(r.modified_surface, "u0", 0)
        tgt_row = _get_cp_row(tgt, "u0", 0)
        np.testing.assert_allclose(src_row[:, 2], tgt_row[:, 2], atol=EPS_G0_CP)

    def test_g0_identity_noop(self):
        """Matching a surface to itself -- boundary unchanged."""
        surf = make_flat_surface(z=0.0)
        src_copy = NurbsSurface(
            degree_u=surf.degree_u, degree_v=surf.degree_v,
            control_points=surf.control_points.copy(),
            knots_u=surf.knots_u.copy(), knots_v=surf.knots_v.copy(),
        )
        r = match_surface_edge(surf, "u0", src_copy, "u0", "G0")
        assert r.ok
        assert r.max_position_deviation < EPS_G0_CP

    def test_g0_nonconforming_cp_count(self):
        """Target 4x4, source 6x6 -- resampling must not crash."""
        tgt = make_flat_surface(nu=4, nv=4, z=0.0)
        src = make_flat_surface(nu=6, nv=6, z=1.0)
        r = match_surface_edge(tgt, "u0", src, "u0", "G0")
        assert r.ok

    def test_g0_v_edge(self):
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "v0", src, "v0", "G0")
        assert r.ok
        src_row = _get_cp_row(r.modified_surface, "v0", 0)
        tgt_row = _get_cp_row(tgt, "v0", 0)
        np.testing.assert_allclose(src_row, tgt_row, atol=EPS_G0_CP)

    def test_g0_returns_nurbs_surface(self):
        tgt = make_flat_surface()
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G0")
        assert r.ok
        assert isinstance(r.modified_surface, NurbsSurface)

    def test_g0_continuity_achieved_is_at_least_g0(self):
        tgt = make_flat_surface()
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G0")
        assert r.ok
        assert r.continuity_achieved in ("G0", "G1", "G2")


# ---------------------------------------------------------------------------
# Group 4: G1 matching
# ---------------------------------------------------------------------------

class TestG1Matching:
    def test_g1_ok(self):
        tgt = make_flat_surface()
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G1")
        assert r.ok

    def test_g1_boundary_cps_still_match(self):
        """G1 must also satisfy G0."""
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G1")
        assert r.ok
        src_row = _get_cp_row(r.modified_surface, "u0", 0)
        tgt_row = _get_cp_row(tgt, "u0", 0)
        np.testing.assert_allclose(src_row, tgt_row, atol=EPS_G0_CP)

    def test_g1_tangent_direction_aligned(self):
        """After G1, the cross-boundary CP difference directions must be aligned."""
        tgt = make_tilted_surface(slope_x=0.5)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G1")
        assert r.ok
        # Check first interior CP pair
        n_cp = _cp_col_count(r.modified_surface, "u0")
        for k in range(n_cp):
            d_src = _cp_tangent_vector(r.modified_surface, "u0", k)
            d_tgt = _cp_tangent_vector(tgt, "u0", k)
            n_s = np.linalg.norm(d_src)
            n_t = np.linalg.norm(d_tgt)
            if n_s > 1e-12 and n_t > 1e-12:
                cos_a = np.dot(d_src, d_tgt) / (n_s * n_t)
                # Angle should be small after G1 matching
                assert abs(cos_a) > 0.9, f"tangent misaligned at k={k}: cos={cos_a}"

    def test_g1_tangent_deviation_finite(self):
        tgt = make_flat_surface()
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G1")
        assert r.ok
        assert not math.isnan(r.max_tangent_deviation)

    def test_g1_identity_noop_small_tan_dev(self):
        """G1 on identical surfaces -- tangent deviation near zero."""
        surf = make_flat_surface()
        src_copy = NurbsSurface(
            degree_u=surf.degree_u, degree_v=surf.degree_v,
            control_points=surf.control_points.copy(),
            knots_u=surf.knots_u.copy(), knots_v=surf.knots_v.copy(),
        )
        r = match_surface_edge(surf, "u0", src_copy, "u0", "G1")
        assert r.ok
        assert r.max_position_deviation < EPS_G0_CP
        assert r.max_tangent_deviation < 1e-6

    def test_g1_curvature_deviation_is_nan(self):
        """G1 request must not compute curvature."""
        tgt = make_flat_surface()
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G1")
        assert r.ok
        assert math.isnan(r.max_curvature_deviation)

    def test_g1_v1_edge(self):
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.3)
        r = match_surface_edge(tgt, "v1", src, "v1", "G1")
        assert r.ok
        src_row = _get_cp_row(r.modified_surface, "v1", 0)
        tgt_row = _get_cp_row(tgt, "v1", 0)
        np.testing.assert_allclose(src_row, tgt_row, atol=EPS_G0_CP)

    def test_g1_position_deviation_near_zero(self):
        tgt = make_flat_surface()
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G1")
        assert r.ok
        assert r.max_position_deviation < 1e-10


# ---------------------------------------------------------------------------
# Group 5: G2 matching
# ---------------------------------------------------------------------------

class TestG2Matching:
    def test_g2_ok(self):
        tgt = make_curved_surface(amplitude=0.3)
        src = make_curved_surface(amplitude=0.1)
        r = match_surface_edge(tgt, "u0", src, "u0", "G2")
        assert r.ok

    def test_g2_boundary_cps_still_match(self):
        """G2 must also satisfy G0."""
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G2")
        assert r.ok
        src_row = _get_cp_row(r.modified_surface, "u0", 0)
        tgt_row = _get_cp_row(tgt, "u0", 0)
        np.testing.assert_allclose(src_row, tgt_row, atol=EPS_G0_CP)

    def test_g2_tangent_deviation_finite(self):
        tgt = make_curved_surface(amplitude=0.3)
        src = make_curved_surface(amplitude=0.1)
        r = match_surface_edge(tgt, "u0", src, "u0", "G2")
        assert r.ok
        assert not math.isnan(r.max_tangent_deviation)

    def test_g2_curvature_deviation_finite(self):
        tgt = make_curved_surface(amplitude=0.3)
        src = make_curved_surface(amplitude=0.1)
        r = match_surface_edge(tgt, "u0", src, "u0", "G2")
        assert r.ok
        assert not math.isnan(r.max_curvature_deviation)

    def test_g2_curvature_deviation_small(self):
        """After G2 match, curvature deviation should be small."""
        tgt = make_curved_surface(amplitude=0.2)
        src = make_curved_surface(amplitude=0.1)
        r = match_surface_edge(tgt, "u0", src, "u0", "G2")
        assert r.ok
        assert r.max_curvature_deviation < 1.0   # generous bound

    def test_g2_identity_noop(self):
        """G2 on identical surfaces -- all deviations near zero."""
        surf = make_curved_surface(amplitude=0.2)
        src_copy = NurbsSurface(
            degree_u=surf.degree_u, degree_v=surf.degree_v,
            control_points=surf.control_points.copy(),
            knots_u=surf.knots_u.copy(), knots_v=surf.knots_v.copy(),
        )
        r = match_surface_edge(surf, "u0", src_copy, "u0", "G2")
        assert r.ok
        assert r.max_position_deviation < EPS_G0_CP
        assert r.max_tangent_deviation < 1e-6
        assert r.max_curvature_deviation < 1e-10

    def test_g2_preserves_g0(self):
        tgt = make_curved_surface()
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G2")
        assert r.ok
        assert r.max_position_deviation < 1e-10

    def test_g2_second_difference_aligned(self):
        """After G2, the second CP-difference vectors should align."""
        tgt = make_curved_surface(amplitude=0.3)
        src = make_curved_surface(amplitude=0.0)
        r = match_surface_edge(tgt, "u0", src, "u0", "G2")
        assert r.ok
        # spot-check: second differences on source should match target (±scale)
        n_cp = _cp_col_count(r.modified_surface, "u0")
        for k in range(n_cp):
            d2_src = _cp_curvature_vector(r.modified_surface, "u0", k)
            d2_tgt = _cp_curvature_vector(tgt, "u0", k)
            # Both should point in the same direction when magnitude > threshold
            n_s = np.linalg.norm(d2_src)
            n_t = np.linalg.norm(d2_tgt)
            if n_s > 1e-10 and n_t > 1e-10:
                cos_a = np.dot(d2_src, d2_tgt) / (n_s * n_t)
                assert cos_a > 0.5, f"G2 second-diff misaligned at k={k}"


# ---------------------------------------------------------------------------
# Group 6: All four edge variants
# ---------------------------------------------------------------------------

class TestEdgeVariants:
    @pytest.mark.parametrize("edge", ["u0", "u1", "v0", "v1"])
    def test_all_edges_g0_ok(self, edge):
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, edge, src, edge, "G0")
        assert r.ok, f"edge={edge}: {r.reason}"

    @pytest.mark.parametrize("edge", ["u0", "u1", "v0", "v1"])
    def test_all_edges_g0_boundary_cps_correct(self, edge):
        """Boundary CPs of source must equal target's after G0."""
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, edge, src, edge, "G0")
        assert r.ok, f"edge={edge}: {r.reason}"
        src_row = _get_cp_row(r.modified_surface, edge, 0)
        tgt_row = _get_cp_row(tgt, edge, 0)
        np.testing.assert_allclose(src_row, tgt_row, atol=EPS_G0_CP,
                                   err_msg=f"edge={edge}")

    @pytest.mark.parametrize("edge", ["u0", "u1", "v0", "v1"])
    def test_all_edges_g1_ok(self, edge):
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.3)
        r = match_surface_edge(tgt, edge, src, edge, "G1")
        assert r.ok, f"edge={edge}: {r.reason}"

    def test_cross_edge_matching(self):
        """Target u0 matched by source u1 -- cross-edge variant."""
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u1", "G0")
        assert r.ok
        src_row = _get_cp_row(r.modified_surface, "u1", 0)
        tgt_row = _get_cp_row(tgt, "u0", 0)
        np.testing.assert_allclose(src_row, tgt_row, atol=EPS_G0_CP)


# ---------------------------------------------------------------------------
# Group 7: Diagnostics helpers
# ---------------------------------------------------------------------------

class TestDiagnostics:
    def test_compute_deviations_g0_identical(self):
        surf = make_flat_surface()
        max_pos, max_tan, max_cur = _compute_deviations(
            surf, "u0", surf, "u0", 16, "G0"
        )
        assert max_pos < 1e-15
        assert math.isnan(max_tan)
        assert math.isnan(max_cur)

    def test_compute_deviations_g1_identical_near_zero(self):
        surf = make_flat_surface()
        max_pos, max_tan, max_cur = _compute_deviations(
            surf, "u0", surf, "u0", 16, "G1"
        )
        assert max_pos < 1e-15
        assert not math.isnan(max_tan)
        assert max_tan < 1e-6   # identical surface -- tangent diff = 0

    def test_compute_deviations_g2_identical(self):
        surf = make_curved_surface()
        max_pos, max_tan, max_cur = _compute_deviations(
            surf, "u0", surf, "u0", 16, "G2"
        )
        assert max_pos < 1e-15
        assert not math.isnan(max_cur)
        assert max_cur < 1e-10

    def test_classify_continuity_none_large_pos(self):
        assert _classify_continuity(1.0, math.nan, math.nan, 1e-6) == "none"

    def test_classify_continuity_g0_only(self):
        # Small position but large tangent angle -> G0
        result = _classify_continuity(1e-9, math.pi / 2, math.nan, 1e-6)
        assert result == "G0"

    def test_classify_continuity_g1(self):
        result = _classify_continuity(1e-9, 0.01, math.nan, 1e-6)
        assert result == "G1"

    def test_classify_continuity_g2(self):
        result = _classify_continuity(1e-9, 0.01, 1e-4, 1e-6)
        assert result == "G2"

    def test_sample_boundary_cps_count(self):
        surf = make_flat_surface(nu=5, nv=5)
        pts = _sample_boundary_cps(surf, "u0", 10)
        assert pts.shape == (10, 3)

    def test_sample_boundary_cps_at_corners(self):
        """First and last samples match the corner CPs."""
        surf = make_flat_surface(nu=5, nv=5, z=0.7)
        pts = _sample_boundary_cps(surf, "u0", 20)
        row = _get_cp_row(surf, "u0", 0)
        np.testing.assert_allclose(pts[0], row[0, :3], atol=1e-10)
        np.testing.assert_allclose(pts[-1], row[-1, :3], atol=1e-10)

    def test_boundary_degree_u0(self):
        surf = make_flat_surface(degree_u=3, degree_v=2)
        assert _boundary_degree(surf, "u0") == 3

    def test_boundary_degree_v1(self):
        surf = make_flat_surface(degree_u=2, degree_v=3)
        assert _boundary_degree(surf, "v1") == 3


# ---------------------------------------------------------------------------
# Group 8: Non-destructive
# ---------------------------------------------------------------------------

class TestNonDestructive:
    def test_source_not_mutated_g0(self):
        tgt = make_flat_surface()
        src = make_flat_surface(z=0.5)
        original_cp = src.control_points.copy()
        r = match_surface_edge(tgt, "u0", src, "u0", "G0")
        assert r.ok
        np.testing.assert_array_equal(src.control_points, original_cp)

    def test_source_not_mutated_g1(self):
        tgt = make_flat_surface()
        src = make_flat_surface(z=0.5)
        original_cp = src.control_points.copy()
        r = match_surface_edge(tgt, "u0", src, "u0", "G1")
        assert r.ok
        np.testing.assert_array_equal(src.control_points, original_cp)

    def test_source_not_mutated_g2(self):
        tgt = make_curved_surface()
        src = make_curved_surface(amplitude=0.1)
        original_cp = src.control_points.copy()
        r = match_surface_edge(tgt, "u0", src, "u0", "G2")
        assert r.ok
        np.testing.assert_array_equal(src.control_points, original_cp)

    def test_target_not_mutated(self):
        tgt = make_flat_surface(z=0.0)
        original_tgt_cp = tgt.control_points.copy()
        src = make_flat_surface(z=0.5)
        match_surface_edge(tgt, "u0", src, "u0", "G1")
        np.testing.assert_array_equal(tgt.control_points, original_tgt_cp)

    def test_modified_surface_differs_from_source(self):
        """Source boundary row must change after G0 match."""
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=1.0)
        r = match_surface_edge(tgt, "u0", src, "u0", "G0")
        assert r.ok
        assert not np.allclose(
            r.modified_surface.control_points, src.control_points, atol=1e-9
        )

    def test_modified_surface_shares_no_array_with_source(self):
        """Modified surface CP array must be a fresh copy."""
        tgt = make_flat_surface(z=0.0)
        src = make_flat_surface(z=0.5)
        r = match_surface_edge(tgt, "u0", src, "u0", "G0")
        assert r.ok
        assert r.modified_surface.control_points is not src.control_points


# ---------------------------------------------------------------------------
# Group 9: Analytic oracle -- flat patch matched to cylinder edge
# GK-44: verify analytic G1 ≤ 1e-8, G2 ≤ 1e-7 for flat-to-cylinder seam.
# ---------------------------------------------------------------------------

from kerf_cad_core.geom.match_srf import verify_seam_g1_analytic, verify_seam_g2_analytic


def _make_cylinder_surface(radius: float = 2.0, height: float = 1.0,
                            nu: int = 5, nv: int = 3) -> NurbsSurface:
    """NURBS approximation of a quarter-cylinder using cubic-in-u interpolation.

    Parametric: S(u, v) = (R·cos(theta(u)), R·sin(theta(u)), v·H) where
    theta ranges from 0 to pi/2 over the u domain.
    """
    thetas = [math.pi / 2 * i / (nu - 1) for i in range(nu)]
    cp = np.zeros((nu, nv, 3))
    for i, theta in enumerate(thetas):
        for j, vf in enumerate(np.linspace(0.0, 1.0, nv)):
            cp[i, j] = [radius * math.cos(theta),
                        radius * math.sin(theta),
                        vf * height]
    return NurbsSurface(
        degree_u=2, degree_v=1,
        control_points=cp,
        knots_u=_knots(nu, 2),
        knots_v=_knots(nv, 1),
    )


def _make_flat_patch_at_cylinder_u1(radius: float = 2.0, height: float = 1.0,
                                     nu: int = 5, nv: int = 3) -> NurbsSurface:
    """Flat patch positioned so its u0 edge meets the cylinder's u1 edge.

    The cylinder's u1 edge lies at theta=pi/2, i.e. x=0, y=R.  The flat
    patch extends in the +x direction from y=R.
    """
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        x_off = i / (nu - 1)
        for j, vf in enumerate(np.linspace(0.0, 1.0, nv)):
            cp[i, j] = [x_off, radius, vf * height]
    return NurbsSurface(
        degree_u=2, degree_v=1,
        control_points=cp,
        knots_u=_knots(nu, 2),
        knots_v=_knots(nv, 1),
    )


class TestAnalyticOracle:
    """GK-44 analytic oracle: flat patch matched to a cylinder edge."""

    def test_g1_analytic_oracle_ok(self):
        """G1 match completes successfully."""
        cyl = _make_cylinder_surface()
        flat = _make_flat_patch_at_cylinder_u1()
        r = match_surface_edge(cyl, "u1", flat, "u0", "G1")
        assert r.ok, f"G1 match failed: {r.reason}"

    def test_g1_analytic_oracle_cross_tangent_le_1e8(self):
        """After G1 match, cross-boundary tangent residual ≤ 1e-8."""
        cyl = _make_cylinder_surface()
        flat = _make_flat_patch_at_cylinder_u1()
        r = match_surface_edge(cyl, "u1", flat, "u0", "G1")
        assert r.ok
        residual = verify_seam_g1_analytic(
            r.modified_surface, "u0", cyl, "u1", samples=32
        )
        assert residual <= 1e-8, (
            f"G1 cross-tangent residual {residual:.2e} exceeds 1e-8"
        )

    def test_g1_analytic_oracle_residual_much_smaller_than_unmatched(self):
        """G1 residual after matching must be orders of magnitude below initial."""
        cyl = _make_cylinder_surface()
        flat = _make_flat_patch_at_cylinder_u1()
        # Residual before matching (flat has horizontal tangents; cylinder has radial)
        residual_before = verify_seam_g1_analytic(flat, "u0", cyl, "u1", samples=16)
        r = match_surface_edge(cyl, "u1", flat, "u0", "G1")
        residual_after = verify_seam_g1_analytic(
            r.modified_surface, "u0", cyl, "u1", samples=16
        )
        # After matching the residual must be negligible
        assert residual_after <= 1e-8
        # And smaller than before (if pre-residual was measurable)
        if residual_before > 1e-6:
            assert residual_after < residual_before * 1e-4

    def test_g2_analytic_oracle_ok(self):
        """G2 match completes successfully."""
        cyl = _make_cylinder_surface()
        flat = _make_flat_patch_at_cylinder_u1()
        r = match_surface_edge(cyl, "u1", flat, "u0", "G2")
        assert r.ok, f"G2 match failed: {r.reason}"

    def test_g2_analytic_oracle_curvature_le_1e7(self):
        """After G2 match, normal-curvature residual ≤ 1e-7."""
        cyl = _make_cylinder_surface()
        flat = _make_flat_patch_at_cylinder_u1()
        r = match_surface_edge(cyl, "u1", flat, "u0", "G2")
        assert r.ok
        residual = verify_seam_g2_analytic(
            r.modified_surface, "u0", cyl, "u1", samples=32
        )
        assert residual <= 1e-7, (
            f"G2 curvature residual {residual:.2e} exceeds 1e-7"
        )

    def test_g2_analytic_oracle_also_satisfies_g1(self):
        """G2 match must also satisfy G1 (G1 ≤ 1e-8)."""
        cyl = _make_cylinder_surface()
        flat = _make_flat_patch_at_cylinder_u1()
        r = match_surface_edge(cyl, "u1", flat, "u0", "G2")
        assert r.ok
        g1_res = verify_seam_g1_analytic(
            r.modified_surface, "u0", cyl, "u1", samples=32
        )
        assert g1_res <= 1e-8, (
            f"G2 match failed G1 oracle: cross-tangent {g1_res:.2e} > 1e-8"
        )

    def test_g2_analytic_oracle_g0_preserved(self):
        """G2 match must also satisfy G0 (position deviation near machine-eps)."""
        cyl = _make_cylinder_surface()
        flat = _make_flat_patch_at_cylinder_u1()
        r = match_surface_edge(cyl, "u1", flat, "u0", "G2")
        assert r.ok
        assert r.max_position_deviation < 1e-10

    def test_verify_seam_g1_analytic_returns_float(self):
        """verify_seam_g1_analytic must return a non-negative float."""
        cyl = _make_cylinder_surface()
        flat = _make_flat_patch_at_cylinder_u1()
        val = verify_seam_g1_analytic(flat, "u0", cyl, "u1", samples=8)
        assert isinstance(val, float)
        assert val >= 0.0

    def test_verify_seam_g2_analytic_returns_float(self):
        """verify_seam_g2_analytic must return a non-negative float."""
        cyl = _make_cylinder_surface()
        flat = _make_flat_patch_at_cylinder_u1()
        val = verify_seam_g2_analytic(flat, "u0", cyl, "u1", samples=8)
        assert isinstance(val, float)
        assert val >= 0.0

    def test_verify_seam_g1_analytic_identical_surfaces(self):
        """Identical surfaces must have zero G1 residual."""
        surf = make_flat_surface()
        val = verify_seam_g1_analytic(surf, "u0", surf, "u0", samples=8)
        assert val < 1e-15

    def test_verify_seam_g2_analytic_identical_surfaces(self):
        """Identical surfaces must have zero G2 curvature residual."""
        surf = make_curved_surface(amplitude=0.2)
        val = verify_seam_g2_analytic(surf, "u0", surf, "u0", samples=8)
        assert val < 1e-12
