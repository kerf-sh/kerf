"""GK-135: Degree reduction — hermetic oracle tests.

Oracle: elevate a curve/surface by 1 degree then reduce_degree_* recovers the
original degree and control-point geometry within tol.

Extra cases:
- A genuinely degree-3 cubic (S-curve) that CANNOT reduce returns unchanged.
- degree <= 1 guard returns unchanged.

NOTE: The legacy ``degree_elevation`` function in nurbs.py has a known
implementation defect (wrong control points + knots).  GK-135 ships its own
correct Bezier-based elevation helper ``_elevate_curve_bspline`` (also in
nurbs.py) which is used here as the oracle's forward pass.
"""
import importlib.util
import os
import numpy as np
import pytest

# Load nurbs.py directly to avoid triggering geom/__init__.py which may
# import optional modules (e.g. lattice) that are not yet present.
_nurbs_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__),
                 "../src/kerf_cad_core/geom/nurbs.py")
)
_spec = importlib.util.spec_from_file_location("kerf_cad_core.geom.nurbs", _nurbs_path)
_nurbs_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_nurbs_mod)

NurbsCurve = _nurbs_mod.NurbsCurve
NurbsSurface = _nurbs_mod.NurbsSurface
reduce_degree_curve = _nurbs_mod.reduce_degree_curve
reduce_degree_surface = _nurbs_mod.reduce_degree_surface
_elevate_curve_bspline = _nurbs_mod._elevate_curve_bspline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_line(p0, p1):
    """Degree-1 clamped line."""
    pts = np.array([p0, p1], dtype=float)
    knots = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsCurve(degree=1, control_points=pts, knots=knots)


def _make_quadratic_bezier(p0, p1, p2):
    """Degree-2 Bezier (single segment)."""
    pts = np.array([p0, p1, p2], dtype=float)
    knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    return NurbsCurve(degree=2, control_points=pts, knots=knots)


def _make_cubic_bezier(p0, p1, p2, p3):
    """Degree-3 Bezier (single segment)."""
    pts = np.array([p0, p1, p2, p3], dtype=float)
    knots = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0])
    return NurbsCurve(degree=3, control_points=pts, knots=knots)


def _sample_curve(curve, n=50):
    """Sample n+1 points uniformly over the curve domain."""
    a = curve.knots[curve.degree]
    b = curve.knots[-curve.degree - 1]
    us = np.linspace(a, b, n + 1)
    return np.array([curve.evaluate(u) for u in us])


def _sample_surface(surf, n=20):
    """Sample n×n points uniformly over the surface domain."""
    au = surf.knots_u[surf.degree_u]
    bu = surf.knots_u[-surf.degree_u - 1]
    av = surf.knots_v[surf.degree_v]
    bv = surf.knots_v[-surf.degree_v - 1]
    us = np.linspace(au, bu, n + 1)
    vs = np.linspace(av, bv, n + 1)
    pts = []
    for u in us:
        for v in vs:
            pts.append(surf.evaluate(u, v))
    return np.array(pts)


def _hausdorff(pts_a, pts_b):
    """Max point-to-point distance between two same-sized sample arrays."""
    diffs = np.linalg.norm(pts_a - pts_b, axis=1)
    return float(np.max(diffs))


def _elevate_surface_u(surf: NurbsSurface, times: int = 1) -> NurbsSurface:
    """Elevate surface degree_u by *times* using correct Bezier elevation."""
    nv = surf.num_control_points_v
    dim = surf.control_points.shape[2]
    W = surf.weights
    elevated_cols = []
    new_ku = None
    for j in range(nv):
        col_pts = surf.control_points[:, j, :].copy()
        col_w = W[:, j].copy() if W is not None else None
        col_curve = NurbsCurve(
            degree=surf.degree_u,
            control_points=col_pts,
            knots=surf.knots_u.copy(),
            weights=col_w,
        )
        elev = _elevate_curve_bspline(col_curve, times)
        elevated_cols.append(elev)
        if new_ku is None:
            new_ku = elev.knots.copy()
    new_nu = elevated_cols[0].num_control_points
    new_cp = np.zeros((new_nu, nv, dim))
    new_W = np.zeros((new_nu, nv)) if W is not None else None
    for j, ec in enumerate(elevated_cols):
        new_cp[:, j, :] = ec.control_points
        if W is not None:
            new_W[:, j] = ec.weights if ec.weights is not None else np.ones(new_nu)
    return NurbsSurface(
        degree_u=surf.degree_u + times,
        degree_v=surf.degree_v,
        control_points=new_cp,
        knots_u=new_ku,
        knots_v=surf.knots_v.copy(),
        weights=new_W,
    )


def _elevate_surface_v(surf: NurbsSurface, times: int = 1) -> NurbsSurface:
    """Elevate surface degree_v by *times* using correct Bezier elevation."""
    nu = surf.num_control_points_u
    dim = surf.control_points.shape[2]
    W = surf.weights
    elevated_rows = []
    new_kv = None
    for i in range(nu):
        row_pts = surf.control_points[i, :, :].copy()
        row_w = W[i, :].copy() if W is not None else None
        row_curve = NurbsCurve(
            degree=surf.degree_v,
            control_points=row_pts,
            knots=surf.knots_v.copy(),
            weights=row_w,
        )
        elev = _elevate_curve_bspline(row_curve, times)
        elevated_rows.append(elev)
        if new_kv is None:
            new_kv = elev.knots.copy()
    new_nv = elevated_rows[0].num_control_points
    new_cp = np.zeros((nu, new_nv, dim))
    new_W = np.zeros((nu, new_nv)) if W is not None else None
    for i, er in enumerate(elevated_rows):
        new_cp[i, :, :] = er.control_points
        if W is not None:
            new_W[i, :] = er.weights if er.weights is not None else np.ones(new_nv)
    return NurbsSurface(
        degree_u=surf.degree_u,
        degree_v=surf.degree_v + times,
        control_points=new_cp,
        knots_u=surf.knots_u.copy(),
        knots_v=new_kv,
        weights=new_W,
    )


# ---------------------------------------------------------------------------
# Curve tests
# ---------------------------------------------------------------------------

class TestReduceDegreeCurve:

    def test_elevate_quadratic_then_reduce_recovers_degree(self):
        """Elevate quadratic Bezier to cubic, reduce back to quadratic."""
        c2 = _make_quadratic_bezier([0, 0, 0], [1, 2, 0], [2, 0, 0])
        c3 = _elevate_curve_bspline(c2)
        assert c3.degree == 3

        c2_back = reduce_degree_curve(c3, tol=1e-6)
        assert c2_back.degree == 2, (
            f"Expected degree 2 after reduction, got {c2_back.degree}"
        )

    def test_elevate_quadratic_then_reduce_geometry(self):
        """Geometry of the reduced curve matches the original within tol."""
        tol = 1e-6
        c2 = _make_quadratic_bezier([0, 0, 0], [0.5, 1.0, 0], [1, 0, 0])
        c3 = _elevate_curve_bspline(c2)
        c2_back = reduce_degree_curve(c3, tol=tol)

        pts_orig = _sample_curve(c2)
        pts_back = _sample_curve(c2_back)
        h = _hausdorff(pts_orig, pts_back)
        assert h < tol * 10, f"Hausdorff error {h} > {tol * 10}"

    def test_elevate_cubic_then_reduce_geometry(self):
        """Elevate cubic Bezier to degree-4, reduce back to cubic."""
        tol = 1e-6
        c3 = _make_cubic_bezier([0, 0, 0], [0.5, 1, 0], [1.5, 1, 0], [2, 0, 0])
        c4 = _elevate_curve_bspline(c3)
        assert c4.degree == 4

        c3_back = reduce_degree_curve(c4, tol=tol)
        assert c3_back.degree == 3

        pts_orig = _sample_curve(c3)
        pts_back = _sample_curve(c3_back)
        h = _hausdorff(pts_orig, pts_back)
        assert h < tol * 10, f"Hausdorff error {h} > {tol * 10}"

    def test_elevate_line_to_quad_then_reduce(self):
        """Elevate linear segment to quadratic, reduce back to linear."""
        tol = 1e-6
        c1 = _make_line([0, 0, 0], [3, 1, 0])
        c2 = _elevate_curve_bspline(c1)
        assert c2.degree == 2

        c1_back = reduce_degree_curve(c2, tol=tol)
        assert c1_back.degree == 1

        pts_orig = _sample_curve(c1)
        pts_back = _sample_curve(c1_back)
        h = _hausdorff(pts_orig, pts_back)
        assert h < tol * 10, f"Hausdorff error {h} > {tol * 10}"

    def test_reduce_degree1_returns_unchanged(self):
        """Cannot reduce degree-1 (linear) curve — return unchanged."""
        c1 = _make_line([0, 0, 0], [1, 0, 0])
        result = reduce_degree_curve(c1, tol=1e-6)
        assert result.degree == 1

    def test_genuine_cubic_cannot_reduce(self):
        """A genuinely degree-3 S-curve (not elevated) should not reduce.

        Cubic S-shape: the Bezier hull does NOT lie on any quadratic —
        the deviation gate should fire and return the original unchanged.
        """
        c3 = _make_cubic_bezier(
            [0, 0, 0], [0, 1, 0], [1, 0, 0], [1, 1, 0]
        )
        result = reduce_degree_curve(c3, tol=1e-6)
        # Either unchanged object OR same degree (reduction rejected)
        assert result.degree == 3, (
            "Genuine S-cubic should not reduce within 1e-6 tol"
        )

    def test_multi_segment_quadratic_elevate_reduce(self):
        """Multi-segment quadratic B-spline (standard 8-knot): elevate then reduce."""
        tol = 1e-6
        pts = np.array([
            [0, 0, 0],
            [0.25, 1, 0],
            [0.5, 0, 0],
            [0.75, 1, 0],
            [1, 0, 0],
        ], dtype=float)
        # Standard clamped quadratic with C^0 at 0.5: 8 knots (n+p+2 = 4+2+2 = 8)
        knots = np.array([0.0, 0.0, 0.0, 0.5, 0.5, 1.0, 1.0, 1.0])
        c2 = NurbsCurve(degree=2, control_points=pts, knots=knots)

        c3 = _elevate_curve_bspline(c2)
        assert c3.degree == 3

        c2_back = reduce_degree_curve(c3, tol=tol)
        assert c2_back.degree == 2

        pts_orig = _sample_curve(c2)
        pts_back = _sample_curve(c2_back)
        h = _hausdorff(pts_orig, pts_back)
        assert h < tol * 50, f"Hausdorff {h} > {tol * 50}"

    def test_reduce_preserves_endpoints(self):
        """Endpoints of the reduced curve must match the original exactly."""
        atol = 1e-8
        c2 = _make_quadratic_bezier([1.5, -2.0, 3.1], [0.0, 0.0, 0.0], [-1.0, 1.0, 0.5])
        c3 = _elevate_curve_bspline(c2)
        c2_back = reduce_degree_curve(c3, tol=1e-6)

        a = c2_back.knots[c2_back.degree]
        b = c2_back.knots[-c2_back.degree - 1]
        p_start = c2_back.evaluate(a)
        p_end = c2_back.evaluate(b)

        np.testing.assert_allclose(p_start, [1.5, -2.0, 3.1], atol=atol)
        np.testing.assert_allclose(p_end, [-1.0, 1.0, 0.5], atol=atol)

    def test_elevate_twice_reduce_once_yields_lower(self):
        """Elevate twice, reduce once: should yield degree+1 (not original)."""
        c2 = _make_quadratic_bezier([0, 0, 0], [1, 1, 0], [2, 0, 0])
        c4 = _elevate_curve_bspline(c2, times=2)
        assert c4.degree == 4

        c3 = reduce_degree_curve(c4, tol=1e-6)
        assert c3.degree == 3, f"Expected 3, got {c3.degree}"


# ---------------------------------------------------------------------------
# Surface tests
# ---------------------------------------------------------------------------

def _make_biquadratic_surface():
    """Degree-(2,2) flat surface (3×3 grid, z=0)."""
    cp = np.zeros((3, 3, 3), dtype=float)
    for i in range(3):
        for j in range(3):
            cp[i, j] = [i * 0.5, j * 0.5, 0.0]
    ku = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    return NurbsSurface(degree_u=2, degree_v=2, control_points=cp,
                        knots_u=ku, knots_v=kv)


def _make_bilinear_surface():
    """Degree-(1,1) surface (bilinear patch)."""
    cp = np.array([
        [[0, 0, 0], [0, 1, 0]],
        [[1, 0, 0], [1, 1, 0]],
    ], dtype=float)
    ku = np.array([0.0, 0.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsSurface(degree_u=1, degree_v=1, control_points=cp,
                        knots_u=ku, knots_v=kv)


class TestReduceDegreeSurface:

    def test_elevate_u_then_reduce_u_degree(self):
        """Elevate biquadratic surface in U to degree 3, reduce back to 2."""
        s2 = _make_biquadratic_surface()
        s3 = _elevate_surface_u(s2)
        assert s3.degree_u == 3

        s2_back = reduce_degree_surface(s3, direction='u', tol=1e-6)
        assert s2_back.degree_u == 2, (
            f"Expected degree_u=2 after reduction, got {s2_back.degree_u}"
        )
        assert s2_back.degree_v == 2

    def test_elevate_u_then_reduce_u_geometry(self):
        """Geometry matches the original surface within tol after U round-trip."""
        tol = 1e-6
        s2 = _make_biquadratic_surface()
        s3 = _elevate_surface_u(s2)
        s2_back = reduce_degree_surface(s3, direction='u', tol=tol)

        pts_orig = _sample_surface(s2)
        pts_back = _sample_surface(s2_back)
        h = _hausdorff(pts_orig, pts_back)
        assert h < tol * 20, f"Hausdorff {h} > {tol * 20}"

    def test_elevate_v_then_reduce_v_degree(self):
        """Elevate biquadratic surface in V to degree 3, reduce back to 2."""
        s2 = _make_biquadratic_surface()
        s3 = _elevate_surface_v(s2)
        assert s3.degree_v == 3

        s2_back = reduce_degree_surface(s3, direction='v', tol=1e-6)
        assert s2_back.degree_v == 2, (
            f"Expected degree_v=2 after reduction, got {s2_back.degree_v}"
        )
        assert s2_back.degree_u == 2

    def test_elevate_v_then_reduce_v_geometry(self):
        """Geometry matches the original surface within tol after V round-trip."""
        tol = 1e-6
        s2 = _make_biquadratic_surface()
        s3 = _elevate_surface_v(s2)
        s2_back = reduce_degree_surface(s3, direction='v', tol=tol)

        pts_orig = _sample_surface(s2)
        pts_back = _sample_surface(s2_back)
        h = _hausdorff(pts_orig, pts_back)
        assert h < tol * 20, f"Hausdorff {h} > {tol * 20}"

    def test_reduce_degree_u_le1_returns_unchanged(self):
        """Cannot reduce degree-1 surface in U — return unchanged."""
        s = _make_bilinear_surface()
        result = reduce_degree_surface(s, direction='u', tol=1e-6)
        assert result.degree_u == 1

    def test_reduce_degree_v_le1_returns_unchanged(self):
        """Cannot reduce degree-1 surface in V — return unchanged."""
        s = _make_bilinear_surface()
        result = reduce_degree_surface(s, direction='v', tol=1e-6)
        assert result.degree_v == 1

    def test_invalid_direction_raises(self):
        """Invalid direction raises ValueError."""
        s = _make_biquadratic_surface()
        with pytest.raises(ValueError):
            reduce_degree_surface(s, direction='w')

    def test_non_reducible_surface_returns_unchanged(self):
        """A surface with genuine cubic geometry in U should not reduce."""
        # Build a truly cubic surface in U (S-curve columns)
        # Each column is the S-shaped cubic Bezier from the curve tests
        nv = 3
        dim = 3
        # Use the S-cubic: [0,0,0],[0,1,0],[1,0,0],[1,1,0] scaled by v
        cp = np.zeros((4, nv, dim), dtype=float)
        for j in range(nv):
            v_scale = j * 0.5 + 0.5
            cp[0, j] = [0.0, 0.0 * v_scale, 0.0]
            cp[1, j] = [0.0, 1.0 * v_scale, 0.0]
            cp[2, j] = [1.0, 0.0 * v_scale, 0.0]
            cp[3, j] = [1.0, 1.0 * v_scale, 0.0]
        ku = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0])
        kv = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
        s3 = NurbsSurface(degree_u=3, degree_v=2, control_points=cp,
                          knots_u=ku, knots_v=kv)
        result = reduce_degree_surface(s3, direction='u', tol=1e-6)
        assert result.degree_u == 3, "Genuine cubic surface in U should not reduce"
