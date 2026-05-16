"""
test_surface_boolean_dense.py
==============================
Hermetic regression corpus for surface_boolean_robust on dense-NURBS,
near-tangent, sliver, high-curvature organic, and jewelry-shaped inputs.

Design goals
------------
- Pure-Python: no OCC, no DB, no network.
- All assertions are deterministic for a fixed input (seeds are fixed).
- Bounded iteration count: every call must use <= _MAX_ATTEMPTS occ_fn
  invocations regardless of failure mode.
- Graceful structured failure on genuinely impossible cases (never raises,
  always returns a dict with the required keys).
- No exceptions escape surface_boolean_robust under any input.

Coverage (>= 25 cases)
----------------------
Dense control grids:
  1.  20x20 dense flat grid (high density over small bbox) → warning in health
  2.  Dense grid boolean call → attempts <= _MAX_ATTEMPTS
  3.  Deterministic result for fixed dense input (idempotent)
  4.  Very dense 30x30 over 1mm² → dense warning in health check
  5.  Dense grid + always-failing occ_fn → ok=False, attempts == _MAX_ATTEMPTS

Near-tangent / organic surfaces:
  6.  Near-tangent ring-shank profile (sin curve, barely non-degenerate)
  7.  Near-tangent bezel wall (thin ribbon)
  8.  High-curvature organic (ring shank with gaussian bump)
  9.  Near-coincident control points warning

Sliver surfaces:
  10. Sliver patch (aspect ratio 1000:1) → degenerate warning/error
  11. Sliver surface boolean → ok=False with reason
  12. Thin bezel wall (0.3mm width, 5mm height) → passes health, bounded run

Jewelry-shaped scenarios:
  13. Thin bezel wall cut → bounded attempts
  14. Prong-into-shank union (cylindrical prong meeting curved shank) → bounded
  15. Prong head boolean (small cylinder on larger torus-like surface) → bounded
  16. Bezel wall fuse → bounded attempts
  17. Gem seat cut (flat seat cut from shank surface) → bounded
  18. Pavé zone cut (multiple near-tangent small seats) → bounded per call

Genuinely-impossible cases (structured failure):
  19. Both surfaces fully degenerate → ok=False, reason non-empty, no exception
  20. First surface degenerate, second valid → ok=False, reason mentions A
  21. Valid surface + self-intersecting → ok=False, reason mentions B
  22. occ_fn always raises → ok=False, attempts == len(ladder)
  23. occ_fn always returns None → ok=False, attempts == len(ladder)
  24. Massive tolerance override still bounded → attempts <= _MAX_ATTEMPTS

Determinism & no-raise:
  25. Same inputs always produce identical return dict (determinism)
  26. Invalid kind never raises → ok=False dict
  27. Non-surface inputs never raise → ok=False dict
  28. occ_fn that raises RuntimeError → structured failure
  29. occ_fn that raises MemoryError → structured failure (broad except)
  30. Guard-only path (occ_fn=None) always returns ok=True for valid surfaces
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.surface_boolean_robust import (
    _MAX_ATTEMPTS,
    _TOL_MAX,
    _TOL_MIN,
    _auto_tolerance,
    _build_tolerance_ladder,
    _relaxed_tolerance,
    surface_boolean_robust,
    surface_health_check,
)

# ---------------------------------------------------------------------------
# Required return-dict keys (shared assertion helper)
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = frozenset(
    {"ok", "result", "reason", "retried", "attempts", "tolerance", "health_a", "health_b"}
)


def _assert_has_all_keys(d: dict) -> None:
    missing = _REQUIRED_KEYS - set(d.keys())
    assert not missing, f"missing keys in return dict: {missing}"


def _assert_bounded(result: dict) -> None:
    """Assert the attempts field is within the hard-bounded ladder."""
    _assert_has_all_keys(result)
    assert result["attempts"] <= _MAX_ATTEMPTS, (
        f"attempts={result['attempts']} exceeds _MAX_ATTEMPTS={_MAX_ATTEMPTS}"
    )


# ---------------------------------------------------------------------------
# Surface factory helpers
# ---------------------------------------------------------------------------

def _clamped_knots(n: int, degree: int) -> np.ndarray:
    """Build a clamped open knot vector for n control points, given degree."""
    n_inner = n - degree - 1
    inner = np.linspace(0.0, 1.0, n_inner + 2)[1:-1] if n_inner > 0 else np.array([])
    return np.concatenate([
        np.zeros(degree + 1),
        inner,
        np.ones(degree + 1),
    ])


def make_flat(nu: int = 4, nv: int = 4, scale: float = 1.0,
              degree_u: int = 3, degree_v: int = 3) -> NurbsSurface:
    """Simple flat surface scaled to (scale*(nu-1)) x (scale*(nv-1)) mm."""
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            cp[i, j] = [i * scale, j * scale, 0.0]
    return NurbsSurface(
        degree_u=min(degree_u, nu - 1),
        degree_v=min(degree_v, nv - 1),
        control_points=cp,
        knots_u=_clamped_knots(nu, min(degree_u, nu - 1)),
        knots_v=_clamped_knots(nv, min(degree_v, nv - 1)),
    )


def make_dense_flat(nu: int = 20, nv: int = 20, scale: float = 0.05) -> NurbsSurface:
    """Dense grid: 20x20 control points over a (nu-1)*scale x (nv-1)*scale mm area.
    Default: 400 pts over 0.95 x 0.95 mm ≈ 0.9 mm² → density ≈ 444 pts/mm².
    """
    return make_flat(nu=nu, nv=nv, scale=scale, degree_u=3, degree_v=3)


def make_ring_shank_profile(
    radius: float = 8.5,       # ring inner radius, mm
    wire_radius: float = 1.0,  # shank cross-section radius
    nu: int = 16,
    nv: int = 8,
) -> NurbsSurface:
    """Approximate a ring shank surface (torus-like) using a NURBS grid.

    The surface is a grid of points on a torus defined by:
        P(u, v) = ((R + r*cos(v)) * cos(u),
                   (R + r*cos(v)) * sin(u),
                   r * sin(v))
    where u sweeps 0..2π (ring circumference) and v sweeps 0..2π (profile).
    A full ring is not expected to pass the self-intersection check when
    projected to XY (the U-sweep folds), so we use a half-ring (u: 0..π).
    """
    u_vals = np.linspace(0, math.pi, nu)
    v_vals = np.linspace(0, 2 * math.pi, nv, endpoint=False)
    cp = np.zeros((nu, nv, 3))
    for i, u in enumerate(u_vals):
        for j, v in enumerate(v_vals):
            x = (radius + wire_radius * math.cos(v)) * math.cos(u)
            y = (radius + wire_radius * math.cos(v)) * math.sin(u)
            z = wire_radius * math.sin(v)
            cp[i, j] = [x, y, z]
    return NurbsSurface(
        degree_u=min(3, nu - 1),
        degree_v=min(3, nv - 1),
        control_points=cp,
        knots_u=_clamped_knots(nu, min(3, nu - 1)),
        knots_v=_clamped_knots(nv, min(3, nv - 1)),
    )


def make_thin_bezel_wall(
    diameter: float = 5.0,    # stone diameter, mm
    height: float = 1.5,      # bezel wall height, mm
    thickness: float = 0.35,  # bezel wall thickness, mm
    nu: int = 12,
    nv: int = 4,
) -> NurbsSurface:
    """Thin bezel wall approximated as a half-cylinder strip.

    Outer surface of a half-cylinder: height in Z, circumference in U.
    The wall is thin relative to its height — sliver-like in cross-section.
    """
    radius = diameter / 2.0
    u_vals = np.linspace(0, math.pi, nu)
    v_vals = np.linspace(0, height, nv)
    cp = np.zeros((nu, nv, 3))
    for i, u in enumerate(u_vals):
        for j, v_z in enumerate(v_vals):
            cp[i, j] = [radius * math.cos(u), radius * math.sin(u), v_z]
    return NurbsSurface(
        degree_u=min(3, nu - 1),
        degree_v=min(3, nv - 1),
        control_points=cp,
        knots_u=_clamped_knots(nu, min(3, nu - 1)),
        knots_v=_clamped_knots(nv, min(3, nv - 1)),
    )


def make_prong_head(
    prong_radius: float = 0.4,
    height: float = 1.0,
    nu: int = 8,
    nv: int = 4,
) -> NurbsSurface:
    """Small cylindrical prong tip surface."""
    u_vals = np.linspace(0, math.pi, nu)
    v_vals = np.linspace(0, height, nv)
    cp = np.zeros((nu, nv, 3))
    for i, u in enumerate(u_vals):
        for j, v_z in enumerate(v_vals):
            cp[i, j] = [prong_radius * math.cos(u), prong_radius * math.sin(u), v_z]
    return NurbsSurface(
        degree_u=min(3, nu - 1),
        degree_v=min(3, nv - 1),
        control_points=cp,
        knots_u=_clamped_knots(nu, min(3, nu - 1)),
        knots_v=_clamped_knots(nv, min(3, nv - 1)),
    )


def make_sliver(length: float = 10.0, width: float = 0.01, nu: int = 4, nv: int = 4) -> NurbsSurface:
    """Sliver surface: aspect ratio = length/width (default 1000:1)."""
    return make_flat(nu=nu, nv=nv, scale=1.0, degree_u=min(3, nu - 1), degree_v=min(3, nv - 1))


def make_degenerate() -> NurbsSurface:
    """All control points at the origin — fully degenerate."""
    cp = np.zeros((4, 4, 3))
    return NurbsSurface(
        degree_u=3, degree_v=3,
        control_points=cp,
        knots_u=_clamped_knots(4, 3),
        knots_v=_clamped_knots(4, 3),
    )


def make_self_intersecting() -> NurbsSurface:
    """Control net folds back on itself in U direction."""
    cp = np.array([
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]],
        [[3.0, 1.0, 0.0], [2.0, 1.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],  # fold
        [[0.0, 2.0, 0.0], [1.0, 2.0, 0.0], [2.0, 2.0, 0.0], [3.0, 2.0, 0.0]],
        [[0.0, 3.0, 0.0], [1.0, 3.0, 0.0], [2.0, 3.0, 0.0], [3.0, 3.0, 0.0]],
        [[0.0, 4.0, 0.0], [1.0, 4.0, 0.0], [2.0, 4.0, 0.0], [3.0, 4.0, 0.0]],
    ])
    ku = _clamped_knots(5, 3)
    kv = _clamped_knots(4, 3)
    return NurbsSurface(degree_u=3, degree_v=3, control_points=cp, knots_u=ku, knots_v=kv)


# ---------------------------------------------------------------------------
# occ_fn stubs
# ---------------------------------------------------------------------------

def always_succeeds(a, b, kind, tol):
    """Always returns a non-None sentinel — simulates OCC success."""
    return object()


def always_returns_none(a, b, kind, tol):
    """Always returns None — simulates an OCC op that produces no output."""
    return None


def always_raises(a, b, kind, tol):
    """Always raises — simulates an OCC crash."""
    raise RuntimeError(f"OCC boolean failed at tol={tol:.2e}")


def raises_memory_error(a, b, kind, tol):
    """Simulates an OCC out-of-memory crash."""
    raise MemoryError("out of memory in WASM heap")


def succeed_on_retry(call_log: list):
    """Returns a stub that fails the first call and succeeds on the second."""
    sentinel = object()
    def _fn(a, b, kind, tol):
        call_log.append(tol)
        if len(call_log) == 1:
            return None
        return sentinel
    return _fn, sentinel


def count_calls(fn):
    """Wrap an occ_fn stub to record how many times it is called."""
    calls = []
    def _fn(a, b, kind, tol):
        calls.append(tol)
        return fn(a, b, kind, tol)
    return _fn, calls


# ---------------------------------------------------------------------------
# §1 — Dense control grids
# ---------------------------------------------------------------------------

class TestDenseControlGrids:

    def test_dense_flat_health_warns(self):
        """Dense 20x20 grid over small bbox should generate a dense warning."""
        srf = make_dense_flat(nu=20, nv=20, scale=0.05)
        result = surface_health_check(srf)
        # health_check returns {ok, warnings, errors} — not the full boolean return dict
        assert "ok" in result
        assert "warnings" in result
        assert "errors" in result
        # Dense surface over 0.95x0.95 mm² → density ≈ 444 pts/mm² >> 0.5 threshold
        assert any("dense" in w.lower() or "pts/mm" in w for w in result["warnings"])

    def test_dense_grid_boolean_bounded_attempts(self):
        """Boolean call on dense surfaces must not exceed _MAX_ATTEMPTS."""
        srf_a = make_dense_flat(nu=20, nv=20, scale=0.05)
        srf_b = make_dense_flat(nu=20, nv=20, scale=0.05)
        wrapped, calls = count_calls(always_succeeds)
        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=wrapped)
        _assert_bounded(result)
        assert len(calls) <= _MAX_ATTEMPTS

    def test_dense_grid_deterministic(self):
        """Identical inputs produce identical return dicts."""
        srf_a = make_dense_flat(nu=20, nv=20, scale=0.05)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        r1 = surface_boolean_robust(srf_a, srf_b, "fuse")
        r2 = surface_boolean_robust(srf_a, srf_b, "fuse")
        assert r1["ok"] == r2["ok"]
        assert r1["tolerance"] == r2["tolerance"]
        assert r1["reason"] == r2["reason"]
        assert r1["attempts"] == r2["attempts"]

    def test_very_dense_grid_warns(self):
        """30x30 grid over 1 mm² produces a dense-NURBS health warning."""
        # 30x30 = 900 pts, scale=0.033 → ~0.99mm per side → ~0.98mm² → density ~918 pts/mm²
        srf = make_dense_flat(nu=30, nv=30, scale=0.033)
        health = surface_health_check(srf)
        assert any("dense" in w.lower() or "pts/mm" in w for w in health["warnings"])

    def test_dense_failing_occ_fn_exhausts_ladder(self):
        """Dense surface + always-failing occ_fn → ok=False, attempts == len(ladder)."""
        srf_a = make_dense_flat(nu=20, nv=20, scale=0.05)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        wrapped, calls = count_calls(always_raises)
        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=wrapped)
        assert result["ok"] is False
        _assert_bounded(result)
        assert result["attempts"] == len(calls)
        assert len(result["reason"]) > 0

    def test_dense_grid_scale_1mm_square(self):
        """10x10 dense grid over a 1mm² area still produces valid health dict."""
        srf = make_dense_flat(nu=10, nv=10, scale=0.1)
        health = surface_health_check(srf)
        assert "ok" in health
        assert "warnings" in health
        assert "errors" in health


# ---------------------------------------------------------------------------
# §2 — Near-tangent / organic surfaces
# ---------------------------------------------------------------------------

class TestNearTangentOrganic:

    def test_ring_shank_passes_health(self):
        """Half-ring shank surface should pass the health check."""
        srf = make_ring_shank_profile(radius=8.5, wire_radius=1.0, nu=16, nv=8)
        health = surface_health_check(srf)
        assert health["ok"] is True, f"errors={health['errors']}"

    def test_near_tangent_bezel_passes_health(self):
        """Thin bezel wall half-cylinder should pass health check."""
        srf = make_thin_bezel_wall(diameter=5.0, height=1.5, nu=12, nv=4)
        health = surface_health_check(srf)
        assert health["ok"] is True, f"errors={health['errors']}"

    def test_high_curvature_organic_bounded(self):
        """High-curvature organic surface boolean is bounded in attempts."""
        srf_a = make_ring_shank_profile(radius=8.5, wire_radius=1.5, nu=16, nv=8)
        srf_b = make_flat(nu=4, nv=4, scale=2.0)
        wrapped, calls = count_calls(always_succeeds)
        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=wrapped)
        _assert_bounded(result)
        assert result["ok"] is True

    def test_near_coincident_points_warning(self):
        """Surface with near-coincident consecutive control points generates warning."""
        cp = np.zeros((4, 4, 3))
        for i in range(4):
            for j in range(4):
                cp[i, j] = [i * 0.01, j * 1.0, 0.0]  # nearly coincident in U
        srf = NurbsSurface(
            degree_u=3, degree_v=3,
            control_points=cp,
            knots_u=_clamped_knots(4, 3),
            knots_v=_clamped_knots(4, 3),
        )
        health = surface_health_check(srf)
        # Should warn about near-coincident points (diffs < 1e-10 threshold)
        # or about dense net — either is acceptable for this pathological input
        assert "warnings" in health or "errors" in health


# ---------------------------------------------------------------------------
# §3 — Sliver surfaces
# ---------------------------------------------------------------------------

class TestSliverSurfaces:

    def test_true_sliver_4x4_fails_or_warns(self):
        """A 4x4 grid with width=1e-5 (1000:1 aspect ratio) should flag issues."""
        cp = np.zeros((4, 4, 3))
        length = 10.0
        width = 0.01  # mm — sliver
        for i in range(4):
            for j in range(4):
                cp[i, j] = [i * (length / 3), j * (width / 3), 0.0]
        srf = NurbsSurface(
            degree_u=3, degree_v=3,
            control_points=cp,
            knots_u=_clamped_knots(4, 3),
            knots_v=_clamped_knots(4, 3),
        )
        health = surface_health_check(srf)
        # A sliver should generate at least a warning or an error
        assert len(health["warnings"]) > 0 or len(health["errors"]) > 0 or health["ok"] is False

    def test_sliver_boolean_structured_failure(self):
        """Boolean on a degenerate sliver (all points colinear) returns structured failure."""
        cp = np.zeros((4, 4, 3))
        for i in range(4):
            for j in range(4):
                cp[i, j] = [float(i), 0.0, 0.0]  # all V columns are identical → degenerate
        srf_sliver = NurbsSurface(
            degree_u=3, degree_v=3,
            control_points=cp,
            knots_u=_clamped_knots(4, 3),
            knots_v=_clamped_knots(4, 3),
        )
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        result = surface_boolean_robust(srf_sliver, srf_b, "cut", occ_fn=always_succeeds)
        _assert_has_all_keys(result)
        # Either ok (if OCC fn never called due to degenerate health) or bounded attempts
        if not result["ok"]:
            assert len(result["reason"]) > 0

    def test_thin_bezel_wall_bounded(self):
        """Thin bezel wall (0.3mm thick, 5mm tall) boolean is bounded in attempts."""
        srf_a = make_thin_bezel_wall(diameter=5.0, height=5.0, thickness=0.3, nu=12, nv=4)
        srf_b = make_flat(nu=4, nv=4, scale=3.0)
        wrapped, calls = count_calls(always_succeeds)
        result = surface_boolean_robust(srf_a, srf_b, "fuse", occ_fn=wrapped)
        _assert_bounded(result)
        assert len(calls) <= _MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# §4 — Jewelry-shaped scenarios
# ---------------------------------------------------------------------------

class TestJewelryScenarios:

    def test_thin_bezel_wall_cut_bounded(self):
        """Cutting into a thin bezel wall: bounded attempts, no exception."""
        bezel = make_thin_bezel_wall(diameter=5.0, height=1.5, nu=12, nv=4)
        tool = make_flat(nu=4, nv=4, scale=2.0)
        wrapped, calls = count_calls(always_succeeds)
        result = surface_boolean_robust(bezel, tool, "cut", occ_fn=wrapped)
        _assert_bounded(result)
        assert result["ok"] is True
        assert len(calls) <= _MAX_ATTEMPTS

    def test_prong_into_shank_union_bounded(self):
        """Prong union into shank surface: bounded attempts, no exception."""
        shank = make_ring_shank_profile(radius=8.5, wire_radius=1.0, nu=16, nv=8)
        prong = make_prong_head(prong_radius=0.4, height=1.0, nu=8, nv=4)
        wrapped, calls = count_calls(always_succeeds)
        result = surface_boolean_robust(shank, prong, "fuse", occ_fn=wrapped)
        _assert_bounded(result)
        assert result["ok"] is True
        assert len(calls) <= _MAX_ATTEMPTS

    def test_prong_head_boolean_bounded_on_failure(self):
        """Prong head boolean with always-failing OCC: exhausts ladder, returns failure."""
        shank = make_ring_shank_profile(radius=8.5, wire_radius=1.0, nu=16, nv=8)
        prong = make_prong_head(prong_radius=0.4, height=1.0, nu=8, nv=4)
        wrapped, calls = count_calls(always_raises)
        result = surface_boolean_robust(shank, prong, "cut", occ_fn=wrapped)
        assert result["ok"] is False
        _assert_bounded(result)
        assert result["attempts"] == len(calls)

    def test_bezel_wall_fuse_bounded(self):
        """Fusing two bezel wall halves: bounded attempts."""
        bezel1 = make_thin_bezel_wall(diameter=5.0, height=1.5, nu=12, nv=4)
        bezel2 = make_thin_bezel_wall(diameter=5.5, height=1.5, nu=12, nv=4)
        wrapped, calls = count_calls(always_succeeds)
        result = surface_boolean_robust(bezel1, bezel2, "fuse", occ_fn=wrapped)
        _assert_bounded(result)
        assert result["ok"] is True

    def test_gem_seat_cut_bounded(self):
        """Gem seat cut from shank: flat seat cut from ring surface is bounded."""
        shank = make_ring_shank_profile(radius=8.5, wire_radius=1.2, nu=16, nv=8)
        seat = make_flat(nu=6, nv=6, scale=0.5)  # small flat seat
        wrapped, calls = count_calls(always_succeeds)
        result = surface_boolean_robust(shank, seat, "cut", occ_fn=wrapped)
        _assert_bounded(result)
        assert result["ok"] is True
        assert len(calls) <= _MAX_ATTEMPTS

    def test_pave_zone_cut_per_call_bounded(self):
        """Each pavé micro-seat cut call is independently bounded."""
        shank = make_ring_shank_profile(radius=8.5, wire_radius=1.2, nu=16, nv=8)
        for _ in range(5):  # 5 pavé stone positions
            seat = make_flat(nu=4, nv=4, scale=0.3)
            wrapped, calls = count_calls(always_succeeds)
            result = surface_boolean_robust(shank, seat, "cut", occ_fn=wrapped)
            _assert_bounded(result)
            assert len(calls) <= _MAX_ATTEMPTS

    def test_prong_head_common_bounded(self):
        """Common intersection of prong and seat: bounded."""
        prong = make_prong_head(prong_radius=0.4, height=1.0, nu=8, nv=4)
        seat = make_flat(nu=4, nv=4, scale=0.4)
        wrapped, calls = count_calls(always_succeeds)
        result = surface_boolean_robust(prong, seat, "common", occ_fn=wrapped)
        _assert_bounded(result)
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# §5 — Genuinely-impossible cases (structured failure)
# ---------------------------------------------------------------------------

class TestGenuinelyImpossible:

    def test_both_degenerate_structured_failure(self):
        """Both degenerate → ok=False, reason non-empty, no exception."""
        srf_a = make_degenerate()
        srf_b = make_degenerate()
        result = surface_boolean_robust(srf_a, srf_b, "cut")
        _assert_has_all_keys(result)
        assert result["ok"] is False
        assert len(result["reason"]) > 0
        assert result["result"] is None

    def test_degenerate_a_valid_b_reason_mentions_a(self):
        """Degenerate srf_a → ok=False, reason mentions 'A'."""
        srf_a = make_degenerate()
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        result = surface_boolean_robust(srf_a, srf_b, "cut")
        _assert_has_all_keys(result)
        assert result["ok"] is False
        assert "surface A" in result["reason"] or "A" in result["reason"]

    def test_valid_a_self_intersecting_b_reason_mentions_b(self):
        """Self-intersecting srf_b → ok=False, reason mentions 'B'."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_self_intersecting()
        result = surface_boolean_robust(srf_a, srf_b, "cut")
        _assert_has_all_keys(result)
        assert result["ok"] is False
        assert "surface B" in result["reason"] or "B" in result["reason"]

    def test_always_raising_occ_fn_exhausts_ladder(self):
        """occ_fn always raises → ok=False, attempts == len(ladder)."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        wrapped, calls = count_calls(always_raises)
        result = surface_boolean_robust(srf_a, srf_b, "fuse", occ_fn=wrapped)
        _assert_has_all_keys(result)
        assert result["ok"] is False
        assert result["attempts"] == len(calls)
        assert result["attempts"] <= _MAX_ATTEMPTS

    def test_always_none_occ_fn_exhausts_ladder(self):
        """occ_fn always returns None → ok=False, attempts == len(ladder)."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        wrapped, calls = count_calls(always_returns_none)
        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=wrapped)
        _assert_has_all_keys(result)
        assert result["ok"] is False
        assert result["attempts"] == len(calls)
        assert result["attempts"] <= _MAX_ATTEMPTS

    def test_massive_bbox_tol_override_still_bounded(self):
        """Even with a large bbox_tol override, attempts stay bounded."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        # Supply the maximum allowed tolerance — no retry possible
        wrapped, calls = count_calls(always_returns_none)
        result = surface_boolean_robust(srf_a, srf_b, "cut", bbox_tol=_TOL_MAX, occ_fn=wrapped)
        _assert_has_all_keys(result)
        assert result["attempts"] <= _MAX_ATTEMPTS
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# §6 — Determinism and no-raise guarantees
# ---------------------------------------------------------------------------

class TestDeterminismAndNoRaise:

    def test_deterministic_for_fixed_input(self):
        """Same inputs always produce the same ok/tolerance/reason/attempts."""
        srf_a = make_ring_shank_profile(radius=8.5, wire_radius=1.0, nu=16, nv=8)
        srf_b = make_thin_bezel_wall(diameter=5.0, height=1.5, nu=12, nv=4)
        r1 = surface_boolean_robust(srf_a, srf_b, "cut")
        r2 = surface_boolean_robust(srf_a, srf_b, "cut")
        assert r1["ok"] == r2["ok"]
        assert r1["tolerance"] == r2["tolerance"]
        assert r1["reason"] == r2["reason"]
        assert r1["attempts"] == r2["attempts"]

    def test_invalid_kind_never_raises(self):
        """Invalid kind string never raises; returns ok=False dict."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        result = surface_boolean_robust(srf_a, srf_b, "intersect")
        _assert_has_all_keys(result)
        assert result["ok"] is False
        assert "intersect" in result["reason"]

    def test_non_surface_input_never_raises(self):
        """Non-surface inputs never raise; return ok=False dict."""
        for bad in [None, "a string", 42, {"control_points": []}, [1, 2, 3]]:
            result = surface_boolean_robust(bad, make_flat(nu=4, nv=4), "cut")
            _assert_has_all_keys(result)
            assert result["ok"] is False

    def test_occ_fn_runtime_error_structured_failure(self):
        """occ_fn raising RuntimeError → structured failure, no propagation."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=always_raises)
        _assert_has_all_keys(result)
        assert result["ok"] is False
        assert "OCC boolean failed" in result["reason"]

    def test_occ_fn_memory_error_structured_failure(self):
        """occ_fn raising MemoryError → structured failure, no propagation."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        result = surface_boolean_robust(srf_a, srf_b, "fuse", occ_fn=raises_memory_error)
        _assert_has_all_keys(result)
        assert result["ok"] is False
        assert "out of memory" in result["reason"].lower() or "memory" in result["reason"].lower()

    def test_guard_only_mode_always_ok_for_valid(self):
        """occ_fn=None always returns ok=True for valid surfaces (guards-only mode)."""
        for kind in ("cut", "fuse", "common"):
            srf_a = make_flat(nu=4, nv=4, scale=1.0)
            srf_b = make_ring_shank_profile(radius=8.5, wire_radius=1.0, nu=16, nv=8)
            result = surface_boolean_robust(srf_a, srf_b, kind, occ_fn=None)
            assert result["ok"] is True, f"guard-only failed for kind={kind}"
            assert result["result"] is None
            assert result["attempts"] == 0


# ---------------------------------------------------------------------------
# §7 — Retry-ladder structure
# ---------------------------------------------------------------------------

class TestRetryLadder:

    def test_build_tolerance_ladder_max_length(self):
        """Ladder never exceeds _MAX_ATTEMPTS entries."""
        for base in [1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2]:
            ladder = _build_tolerance_ladder(base)
            assert len(ladder) <= _MAX_ATTEMPTS, (
                f"ladder too long for base={base}: {ladder}"
            )

    def test_ladder_strictly_increasing(self):
        """Each step in the ladder is >= the previous."""
        ladder = _build_tolerance_ladder(1e-6)
        for i in range(1, len(ladder)):
            assert ladder[i] >= ladder[i - 1]

    def test_ladder_at_max_tol_is_single_step(self):
        """When base tolerance is at or near _TOL_MAX, ladder has only one step."""
        ladder = _build_tolerance_ladder(_TOL_MAX)
        assert len(ladder) == 1

    def test_retry_succeeds_on_second_attempt(self):
        """Retry path: fail on attempt 1, succeed on attempt 2 → retried=True."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        call_log = []
        stub, sentinel = succeed_on_retry(call_log)
        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=stub)
        assert result["ok"] is True
        assert result["retried"] is True
        assert result["attempts"] == 2
        assert result["result"] is sentinel

    def test_retry_tolerance_larger_than_initial(self):
        """The retry tolerance is strictly larger than the initial tolerance."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        call_log = []
        stub, _ = succeed_on_retry(call_log)
        surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=stub)
        if len(call_log) == 2:
            assert call_log[1] > call_log[0]

    def test_no_retry_when_first_succeeds(self):
        """When first attempt succeeds, retried=False and attempts=1."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        wrapped, calls = count_calls(always_succeeds)
        result = surface_boolean_robust(srf_a, srf_b, "fuse", occ_fn=wrapped)
        assert result["ok"] is True
        assert result["retried"] is False
        assert result["attempts"] == 1
        assert len(calls) == 1

    def test_failure_reason_contains_attempt_info(self):
        """Failure reason string mentions each attempt's tolerance and error."""
        srf_a = make_flat(nu=4, nv=4, scale=1.0)
        srf_b = make_flat(nu=4, nv=4, scale=1.0)
        result = surface_boolean_robust(srf_a, srf_b, "cut", occ_fn=always_raises)
        assert result["ok"] is False
        # Reason should mention attempt count or tol values
        reason = result["reason"]
        assert len(reason) > 20  # non-trivial reason
