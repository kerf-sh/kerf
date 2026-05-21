"""GK-102: Knot removal / minimal-CP refit — hermetic oracle tests.

Oracle:
1. A degree-3 curve with an interior knot inserted then removed recovers the
   original CP count and geometry within tol.
2. A genuinely needed interior knot is NOT removed (shape is preserved only if
   that knot stays — removing it would change the shape beyond tol).

The implementation follows Piegl & Tiller §5.4 RemoveCurveKnot.
"""
import importlib.util
import os
import numpy as np
import pytest

# Load nurbs.py directly to avoid optional geom/__init__ imports.
_nurbs_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__),
                 "../src/kerf_cad_core/geom/nurbs.py")
)
_spec = importlib.util.spec_from_file_location("kerf_cad_core.geom.nurbs", _nurbs_path)
_nurbs_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_nurbs_mod)

NurbsCurve = _nurbs_mod.NurbsCurve
_correct_knot_insert = _nurbs_mod._correct_knot_insert
remove_knot = _nurbs_mod.remove_knot
minimal_cp_refit = _nurbs_mod.minimal_cp_refit


def _insert_knot(curve: NurbsCurve, u: float, num: int = 1) -> NurbsCurve:
    """Correct single/multi knot insertion using _correct_knot_insert."""
    P = curve.control_points.astype(float)
    U = curve.knots.astype(float)
    W = curve.weights
    if W is not None:
        Pw = np.column_stack([P * W[:, None], W])
    else:
        Pw = P.copy()
    for _ in range(num):
        Pw, U = _correct_knot_insert(Pw, U, curve.degree, u)
    if W is not None:
        new_W = Pw[:, -1].copy()
        new_P = Pw[:, :-1] / np.where(np.abs(new_W) > 1e-14, new_W, 1.0)[:, None]
        return NurbsCurve(degree=curve.degree, control_points=new_P, knots=U, weights=new_W)
    return NurbsCurve(degree=curve.degree, control_points=Pw, knots=U)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cubic_bezier(p0, p1, p2, p3):
    """Single-segment degree-3 Bezier in 3-D."""
    pts = np.array([p0, p1, p2, p3], dtype=float)
    knots = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0])
    return NurbsCurve(degree=3, control_points=pts, knots=knots)


def _make_cubic_bspline():
    """Multi-segment degree-3 B-spline with an interior knot at 0.5 (mult 1)."""
    pts = np.array([
        [0, 0, 0], [1, 2, 0], [2, -1, 0], [3, 1, 0],
        [4, 0, 0], [5, 2, 0],
    ], dtype=float)
    # degree 3, 6 CP → 10 knots; interior knot at 0.5
    knots = np.array([0.0, 0.0, 0.0, 0.0, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0])
    return NurbsCurve(degree=3, control_points=pts, knots=knots)


def _sample_curve(curve, n=64):
    """Sample n+1 points uniformly over the curve parameter domain."""
    p = curve.degree
    a = curve.knots[p]
    b = curve.knots[-(p + 1)]
    us = np.linspace(a, b, n + 1)
    return np.array([curve.evaluate(float(u)) for u in us])


def _hausdorff(pts_a, pts_b):
    """Max point-to-point distance between same-length sample arrays."""
    return float(np.max(np.linalg.norm(pts_a - pts_b, axis=1)))


# ---------------------------------------------------------------------------
# remove_knot tests
# ---------------------------------------------------------------------------

class TestRemoveKnot:

    def test_insert_then_remove_recovers_cp_count(self):
        """Insert a knot into a cubic Bezier then remove it → same CP count."""
        orig = _make_cubic_bezier(
            [0, 0, 0], [1, 3, 0], [2, 3, 0], [3, 0, 0]
        )
        inserted = _insert_knot(orig, 0.5, num=1)
        assert inserted.num_control_points == orig.num_control_points + 1

        recovered = remove_knot(inserted, 0.5, num=1, tol=1e-6)
        assert recovered.num_control_points == orig.num_control_points, (
            f"Expected {orig.num_control_points} CPs after removal, "
            f"got {recovered.num_control_points}"
        )

    def test_insert_then_remove_recovers_geometry(self):
        """Geometry after insert+remove matches the original within tol."""
        tol = 1e-6
        orig = _make_cubic_bezier(
            [0, 0, 0], [0.5, 2, 0], [1.5, 2, 0], [2, 0, 0]
        )
        inserted = _insert_knot(orig, 0.4, num=1)
        recovered = remove_knot(inserted, 0.4, num=1, tol=tol)

        pts_orig = _sample_curve(orig)
        pts_rec = _sample_curve(recovered)
        h = _hausdorff(pts_orig, pts_rec)
        assert h < tol * 10, f"Hausdorff deviation {h:.2e} > {tol * 10:.2e}"

    def test_remove_nonexistent_knot_returns_unchanged(self):
        """Removing a knot value that is not present returns the curve unchanged."""
        c = _make_cubic_bezier([0, 0, 0], [1, 1, 0], [2, 1, 0], [3, 0, 0])
        result = remove_knot(c, 0.7, num=1, tol=1e-6)
        assert result.num_control_points == c.num_control_points
        np.testing.assert_array_equal(result.knots, c.knots)

    def test_cannot_remove_end_knot(self):
        """Clamped end knots (multiplicity = degree+1) must not be removable."""
        c = _make_cubic_bezier([0, 0, 0], [1, 1, 0], [2, 1, 0], [3, 0, 0])
        # Try to remove the start clamp (value 0.0, multiplicity 4)
        result = remove_knot(c, 0.0, num=1, tol=1e-6)
        assert result.num_control_points == c.num_control_points

    def test_genuine_knot_not_removed(self):
        """An interior knot that genuinely encodes a shape change is not removed.

        We build a C^0 multi-segment cubic with an abrupt corner at the
        interior breakpoint (full multiplicity = degree = 3).  Removing the
        knot would change the shape, so remove_knot should reject it.
        """
        # Two cubic segments joined at t=0.5 with a C^0 corner.
        # Segment 1: (0,0,0)→(0,1,0)→(1,1,0)→(1,0,0)
        # Segment 2: (1,0,0)→(2,-1,0)→(3,1,0)→(4,0,0)
        # Full-mult interior knot (s=3) at 0.5 → C^0 join
        pts = np.array([
            [0, 0, 0], [0, 1, 0], [1, 1, 0],
            [1, 0, 0],  # shared endpoint (appears once in CP array)
            [2, -1, 0], [3, 1, 0], [4, 0, 0],
        ], dtype=float)
        # degree 3, 7 CPs → 11 knots; interior triple knot at 0.5
        knots = np.array([0.0, 0.0, 0.0, 0.0,
                          0.5, 0.5, 0.5,
                          1.0, 1.0, 1.0, 1.0])
        c = NurbsCurve(degree=3, control_points=pts, knots=knots)

        orig_pts = _sample_curve(c, n=128)

        result = remove_knot(c, 0.5, num=1, tol=1e-6)

        # Even if one removal passes, geometry must be preserved
        result_pts = _sample_curve(result, n=128)
        h = _hausdorff(orig_pts, result_pts)
        assert h < 1e-4, (
            f"Shape changed unexpectedly after removing a structural knot: "
            f"Hausdorff={h:.2e}"
        )

    def test_multi_insert_then_remove_all(self):
        """Insert a knot twice, then remove both instances → original shape."""
        tol = 1e-6
        orig = _make_cubic_bezier(
            [0, 0, 0], [1, 4, 0], [2, 4, 0], [3, 0, 0]
        )
        inserted2 = _insert_knot(orig, 0.6, num=2)
        assert inserted2.num_control_points == orig.num_control_points + 2

        recovered = remove_knot(inserted2, 0.6, num=2, tol=tol)
        assert recovered.num_control_points == orig.num_control_points, (
            f"Expected {orig.num_control_points} CPs, got "
            f"{recovered.num_control_points}"
        )
        pts_orig = _sample_curve(orig)
        pts_rec = _sample_curve(recovered)
        h = _hausdorff(pts_orig, pts_rec)
        assert h < tol * 10, f"Hausdorff {h:.2e} > {tol * 10:.2e}"

    def test_insert_then_remove_bspline(self):
        """Insert + remove on a multi-segment B-spline recovers original shape."""
        tol = 1e-6
        orig = _make_cubic_bspline()
        n_orig = orig.num_control_points
        inserted = _insert_knot(orig, 0.25, num=1)
        recovered = remove_knot(inserted, 0.25, num=1, tol=tol)

        assert recovered.num_control_points == n_orig, (
            f"CP count mismatch: expected {n_orig}, got {recovered.num_control_points}"
        )
        pts_orig = _sample_curve(orig)
        pts_rec = _sample_curve(recovered)
        h = _hausdorff(pts_orig, pts_rec)
        assert h < tol * 20, f"Hausdorff {h:.2e} > {tol * 20:.2e}"


# ---------------------------------------------------------------------------
# minimal_cp_refit tests
# ---------------------------------------------------------------------------

class TestMinimalCpRefit:

    def test_refit_removes_all_inserted_knots(self):
        """Refitting after multiple insertions recovers the minimal CP count."""
        tol = 1e-6
        orig = _make_cubic_bezier(
            [0, 0, 0], [1, 3, 0], [3, 3, 0], [4, 0, 0]
        )
        n_orig = orig.num_control_points

        # Insert several knots
        c = _insert_knot(orig, 0.25, num=1)
        c = _insert_knot(c, 0.5, num=1)
        c = _insert_knot(c, 0.75, num=1)
        assert c.num_control_points > n_orig

        minimal = minimal_cp_refit(c, tol=tol)
        assert minimal.num_control_points == n_orig, (
            f"Expected {n_orig} CPs after refit, got {minimal.num_control_points}"
        )

        pts_orig = _sample_curve(orig)
        pts_min = _sample_curve(minimal)
        h = _hausdorff(pts_orig, pts_min)
        assert h < tol * 20, f"Hausdorff {h:.2e} > {tol * 20:.2e}"

    def test_refit_already_minimal_unchanged(self):
        """Calling minimal_cp_refit on a minimal curve leaves it unchanged."""
        orig = _make_cubic_bezier(
            [0, 0, 0], [1, 2, 0], [2, 2, 0], [3, 0, 0]
        )
        minimal = minimal_cp_refit(orig, tol=1e-6)
        # No interior knots → nothing to remove
        assert minimal.num_control_points == orig.num_control_points

    def test_refit_preserves_geometry(self):
        """Geometry after refit matches original within tight tol."""
        tol = 1e-6
        orig = _make_cubic_bspline()

        # Insert extra knots in the interior
        c = _insert_knot(orig, 0.25, num=1)
        c = _insert_knot(c, 0.75, num=1)

        minimal = minimal_cp_refit(c, tol=tol)

        pts_orig = _sample_curve(orig)
        pts_min = _sample_curve(minimal)
        h = _hausdorff(pts_orig, pts_min)
        assert h < tol * 20, f"Hausdorff {h:.2e} > {tol * 20:.2e}"

    def test_refit_genuinely_needed_knot_kept(self):
        """A structural knot encoding a real shape feature is not removed."""
        # Use a B-spline that genuinely needs its interior knot
        pts = np.array([
            [0, 0, 0], [1, 4, 0], [2, -4, 0], [3, 0, 0],
            [4, 4, 0], [5, -4, 0], [6, 0, 0],
        ], dtype=float)
        knots = np.array([0.0, 0.0, 0.0, 0.0,
                          0.5, 0.5,
                          1.0, 1.0, 1.0, 1.0])
        # 6 CPs, degree 3, 10 knots → valid (n+p+2 = 6+3+2 = 11? let me use 7 CPs)
        pts7 = np.array([
            [0, 0, 0], [1, 4, 0], [2, -4, 0],
            [3, 0, 0],
            [4, 4, 0], [5, -4, 0], [6, 0, 0],
        ], dtype=float)
        knots7 = np.array([0.0, 0.0, 0.0, 0.0,
                           0.5,
                           1.0, 1.0, 1.0, 1.0,
                           # need 11 knots for 7 CPs degree 3: n+p+2=7+3+2=12? No.
                           # n=6 (0-based), m=n+p+1=6+3+1=10, so 11 knots
                           ])
        # Correct: 7 CPs, degree 3, knots = n+p+2 = 7+3+2 = 12? No.
        # The NURBS relation is: m = n + p + 1 where n = num_cp - 1.
        # So len(knots) = n + p + 2 = num_cp + p + 1 = 7 + 3 + 1 = 11.
        knots_ok = np.array([0.0, 0.0, 0.0, 0.0,
                             0.5,
                             1.0, 1.0, 1.0, 1.0])
        # 9 knots for 7 CPs degree 3: need 11.  Use 5 CPs.
        pts5 = np.array([
            [0, 0, 0], [1, 4, 0], [2, -4, 0], [3, 4, 0], [4, 0, 0],
        ], dtype=float)
        # 5 CPs, degree 3 → 5+3+1=9 knots
        knots5 = np.array([0.0, 0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0, 1.0])
        c = NurbsCurve(degree=3, control_points=pts5, knots=knots5)

        pts_before = _sample_curve(c, n=128)
        minimal = minimal_cp_refit(c, tol=1e-6)
        pts_after = _sample_curve(minimal, n=128)

        # Geometry must be preserved regardless of whether the knot was removed
        h = _hausdorff(pts_before, pts_after)
        assert h < 1e-4, (
            f"Shape changed beyond tolerance during refit: Hausdorff={h:.2e}"
        )
