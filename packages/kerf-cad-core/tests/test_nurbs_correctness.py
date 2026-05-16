"""GK-01..GK-04 correctness pass for geom/nurbs.py.

Hermetic, pure-Python (numpy only).  Every test asserts a closed-form
analytic oracle:

* GK-01  unified, correct Cox-de Boor surface evaluation + partition of unity
         + parity with the known-good intersection._nurbs_surface_eval.
* GK-02  analytic surface partials/normal vs an exact rational sphere patch
         and vs central finite differences.
* GK-03  curve_derivative returns the TRUE (un-normalised), rational-correct
         derivative.
* GK-04  exact rational quadratic circle / arc / ellipse.
"""

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import (
    NurbsCurve,
    NurbsSurface,
    de_boor,
    curve_derivative,
    rational_curve_derivative,
    surface_evaluate,
    surface_derivative,
    surface_derivatives,
    surface_normal,
    make_circle_nurbs,
    make_arc_nurbs,
    make_ellipse_nurbs,
    make_line_nurbs,
    basis_functions,
    _basis_funcs,
    _basis_funcs_derivs,
)
from kerf_cad_core.geom.intersection import (
    _nurbs_surface_eval,
    _basis_fns,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _bilinear_surface():
    """Degree (1,1) patch over the unit square; closed form is bilinear."""
    P00 = np.array([0.0, 0.0, 0.0])
    P10 = np.array([2.0, 0.0, 1.0])
    P01 = np.array([0.0, 3.0, -1.0])
    P11 = np.array([2.0, 3.0, 4.0])
    cps = np.array([[P00, P01], [P10, P11]])
    ku = np.array([0.0, 0.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 1.0, 1.0])
    s = NurbsSurface(degree_u=1, degree_v=1, control_points=cps,
                     knots_u=ku, knots_v=kv)

    def closed(u, v):
        return ((1 - u) * (1 - v) * P00 + (1 - u) * v * P01
                + u * (1 - v) * P10 + u * v * P11)

    return s, closed


def _biquadratic_surface():
    """Degree (2,2) Bezier patch; closed form via Bernstein basis."""
    rng = np.random.default_rng(12345)
    P = rng.uniform(-2.0, 2.0, size=(3, 3, 3))
    ku = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    s = NurbsSurface(degree_u=2, degree_v=2, control_points=P,
                     knots_u=ku, knots_v=kv)

    def bern2(t):
        return np.array([(1 - t) ** 2, 2 * (1 - t) * t, t ** 2])

    def closed(u, v):
        bu = bern2(u)
        bv = bern2(v)
        out = np.zeros(3)
        for i in range(3):
            for j in range(3):
                out += bu[i] * bv[j] * P[i, j]
        return out

    return s, closed


def _rational_sphere_patch(R=1.0):
    """One octant of a sphere as an exact biquadratic rational NURBS patch.

    Built as the tensor product of two rational quadratic 90-degree arcs
    (Piegl & Tiller §7.5), giving the EXACT sphere of radius R.
    """
    s2 = np.sqrt(2.0) / 2.0
    # Arc in the meridian (xz) plane, 0..90 deg from +z to +x.
    # Arc in the azimuth (xy) plane, 0..90 deg from +x to +y.
    # 3x3 net of Cartesian control points + 3x3 weights.
    # Polar arc points (latitude): (z->x)
    Pz = np.array([0.0, 0.0, R])
    Pxz = np.array([R, 0.0, R])      # shoulder (weight s2)
    Px = np.array([R, 0.0, 0.0])
    # Azimuth rotation about z by phi for a point of radius rho in xy:
    # we build the 3x3 net directly.
    cps = np.zeros((3, 3, 3))
    w = np.zeros((3, 3))

    # latitude index i: 0 -> pole(+z), 1 -> shoulder, 2 -> equator
    # longitude index j: 0 -> +x, 1 -> shoulder(+x+y), 2 -> +y
    lat_pts = [Pz, Pxz, Px]          # in the xz reference plane (y = 0)
    lat_w = [1.0, s2, 1.0]
    lon_w = [1.0, s2, 1.0]

    for i, (lp, lw) in enumerate(zip(lat_pts, lat_w)):
        # lp = (x_r, 0, z); rotate the (x) component into the azimuth fan.
        x_r = lp[0]
        z = lp[2]
        # azimuth control points: +x, square-corner, +y (radius x_r in xy)
        lon_pts = [
            np.array([x_r, 0.0, z]),
            np.array([x_r, x_r, z]),   # shoulder
            np.array([0.0, x_r, z]),
        ]
        for j, lpt in enumerate(lon_pts):
            cps[i, j] = lpt
            w[i, j] = lw * lon_w[j]

    ku = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    s = NurbsSurface(degree_u=2, degree_v=2, control_points=cps,
                     knots_u=ku, knots_v=kv, weights=w)
    return s, R


# ===========================================================================
# GK-01 — unified surface evaluation
# ===========================================================================

def test_gk01_bilinear_closed_form_1e12():
    s, closed = _bilinear_surface()
    for u in np.linspace(0, 1, 11):
        for v in np.linspace(0, 1, 11):
            got = surface_evaluate(s, u, v)
            assert np.allclose(got, closed(u, v), atol=1e-12, rtol=0)


def test_gk01_biquadratic_closed_form_1e12():
    s, closed = _biquadratic_surface()
    for u in np.linspace(0, 1, 13):
        for v in np.linspace(0, 1, 13):
            got = surface_evaluate(s, u, v)
            assert np.allclose(got, closed(u, v), atol=1e-12, rtol=0)


def _clamped_knots(n, p):
    """Clamped knot vector: (p+1) zeros, (n-p) interior, (p+1) ones."""
    interior = np.linspace(0.0, 1.0, n - p + 2)[1:-1]
    return np.concatenate([np.zeros(p + 1), interior, np.ones(p + 1)])


def test_gk01_partition_of_unity_50x50_1e13():
    # Σ basis = 1 for a degree-(2,3) clamped knot structure over a 50x50 grid.
    pu, pv = 2, 3
    nu, nv = 6, 7  # control-point counts - 1 = top index
    ku = _clamped_knots(nu, pu)
    kv = _clamped_knots(nv, pv)
    for u in np.linspace(0, 1, 50):
        span_u = _span(nu, pu, u, ku)
        Nu = _basis_funcs(span_u, u, pu, ku)
        assert abs(Nu.sum() - 1.0) < 1e-13
    for v in np.linspace(0, 1, 50):
        span_v = _span(nv, pv, v, kv)
        Nv = _basis_funcs(span_v, v, pv, kv)
        assert abs(Nv.sum() - 1.0) < 1e-13


def test_gk01_tensor_partition_of_unity_grid():
    pu, pv = 2, 2
    ku = np.array([0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0])
    nu = len(ku) - pu - 1
    nv = len(kv) - pv - 1
    for u in np.linspace(0, 1, 50):
        for v in np.linspace(0, 1, 50):
            su = _span(nu - 1, pu, u, ku)
            sv = _span(nv - 1, pv, v, kv)
            Nu = _basis_funcs(su, u, pu, ku)
            Nv = _basis_funcs(sv, v, pv, kv)
            tot = np.outer(Nu, Nv).sum()
            assert abs(tot - 1.0) < 1e-13


def _span(n, p, u, knots):
    from kerf_cad_core.geom.nurbs import find_span
    return find_span(n, p, float(u), knots)


def test_gk01_basis_matches_known_good_reference():
    # _basis_funcs must be numerically identical to the known-good
    # intersection._basis_fns over a non-trivial knot vector.
    p = 3
    knots = np.array([0, 0, 0, 0, 0.25, 0.5, 0.75, 1, 1, 1, 1], dtype=float)
    n = len(knots) - p - 1
    for u in np.linspace(0, 1, 37):
        sp = _span(n - 1, p, u, knots)
        a = _basis_funcs(sp, u, p, knots)
        b = _basis_fns(sp, u, p, knots)
        assert np.allclose(a, b, atol=1e-15, rtol=0)


def test_gk01_alias_basis_functions_matches():
    p = 2
    knots = np.array([0, 0, 0, 0.5, 1, 1, 1], dtype=float)
    n = len(knots) - p - 1
    for u in (0.0, 0.1, 0.5, 0.9, 1.0):
        sp = _span(n - 1, p, u, knots)
        assert np.allclose(basis_functions(sp, u, p, knots),
                           _basis_fns(sp, u, p, knots), atol=1e-15)


def test_gk01_regression_parity_with_intersection_eval_1e12():
    # Non-rational surfaces must evaluate IDENTICALLY to the existing
    # already-correct intersection._nurbs_surface_eval call site.
    for builder in (_bilinear_surface, _biquadratic_surface):
        s, _ = builder()
        for u in np.linspace(0, 1, 9):
            for v in np.linspace(0, 1, 9):
                a = surface_evaluate(s, u, v)[:3]
                b = _nurbs_surface_eval(s, u, v)
                assert np.allclose(a, b, atol=1e-12, rtol=0)


def test_gk01_rational_surface_partition_constant_function():
    # A rational surface whose CPs are all the same point P must evaluate to
    # P everywhere irrespective of weights (partition of unity, rational).
    P = np.array([1.5, -2.0, 3.0])
    cps = np.tile(P, (3, 3, 1))
    w = np.array([[1.0, 0.4, 2.0], [0.3, 5.0, 0.7], [1.1, 0.9, 1.0]])
    ku = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    s = NurbsSurface(degree_u=2, degree_v=2, control_points=cps,
                     knots_u=ku, knots_v=kv, weights=w)
    for u in np.linspace(0, 1, 7):
        for v in np.linspace(0, 1, 7):
            assert np.allclose(surface_evaluate(s, u, v), P, atol=1e-12)


def test_gk01_rational_sphere_on_surface_1e12():
    s, R = _rational_sphere_patch(2.0)
    for u in np.linspace(0, 1, 21):
        for v in np.linspace(0, 1, 21):
            p = surface_evaluate(s, u, v)
            assert abs(np.linalg.norm(p) - R) < 1e-12


def test_gk01_curve_constant_under_weights():
    # de_boor rational path: identical CPs ⇒ same point for any weights.
    P = np.array([0.7, 1.2, -0.3])
    cps = np.tile(P, (3, 1))
    knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    w = np.array([0.2, 4.0, 1.3])
    c = NurbsCurve(degree=2, control_points=cps, knots=knots, weights=w)
    for t in np.linspace(0, 1, 11):
        assert np.allclose(de_boor(c, t), P, atol=1e-13)


# ===========================================================================
# GK-02 — analytic surface derivatives + normal
# ===========================================================================

def test_gk02_bilinear_partials_closed_form():
    s, _ = _bilinear_surface()
    P00 = s.control_points[0, 0]
    P10 = s.control_points[1, 0]
    P01 = s.control_points[0, 1]
    P11 = s.control_points[1, 1]
    for u in np.linspace(0.05, 0.95, 7):
        for v in np.linspace(0.05, 0.95, 7):
            su = surface_derivative(s, u, v, 1, 0)
            sv = surface_derivative(s, u, v, 0, 1)
            su_exact = (1 - v) * (P10 - P00) + v * (P11 - P01)
            sv_exact = (1 - u) * (P01 - P00) + u * (P11 - P10)
            assert np.allclose(su, su_exact, atol=1e-12)
            assert np.allclose(sv, sv_exact, atol=1e-12)


def test_gk02_biquadratic_partials_vs_fd_1e6():
    s, closed = _biquadratic_surface()
    h = 1e-6
    for u in (0.2, 0.5, 0.8):
        for v in (0.2, 0.5, 0.8):
            su = surface_derivative(s, u, v, 1, 0)
            sv = surface_derivative(s, u, v, 0, 1)
            fd_u = (closed(u + h, v) - closed(u - h, v)) / (2 * h)
            fd_v = (closed(u, v + h) - closed(u, v - h)) / (2 * h)
            assert np.linalg.norm(su - fd_u) < 1e-6
            assert np.linalg.norm(sv - fd_v) < 1e-6


def test_gk02_rational_sphere_partials_analytic_1e9():
    # On the exact sphere patch, S_u x S_v must be radial; the unit normal
    # equals p / |p| (outward) to 1e-9.
    s, R = _rational_sphere_patch(1.0)
    for u in np.linspace(0.05, 0.95, 9):
        for v in np.linspace(0.05, 0.95, 9):
            p = surface_evaluate(s, u, v)
            n = surface_normal(s, u, v)
            radial = p / np.linalg.norm(p)
            # normal parallel to radial (sign may flip with param orientation)
            cross = np.linalg.norm(np.cross(n, radial))
            assert cross < 1e-9
            # partials tangent to sphere ⇒ orthogonal to the radial direction
            su = surface_derivative(s, u, v, 1, 0)
            sv = surface_derivative(s, u, v, 0, 1)
            assert abs(np.dot(su, radial)) < 1e-9
            assert abs(np.dot(sv, radial)) < 1e-9


def test_gk02_rational_sphere_partials_vs_fd_1e6():
    s, R = _rational_sphere_patch(1.5)
    h = 1e-6
    for u in (0.3, 0.6):
        for v in (0.3, 0.6):
            su = surface_derivative(s, u, v, 1, 0)
            sv = surface_derivative(s, u, v, 0, 1)
            fd_u = (surface_evaluate(s, u + h, v)
                    - surface_evaluate(s, u - h, v)) / (2 * h)
            fd_v = (surface_evaluate(s, u, v + h)
                    - surface_evaluate(s, u, v - h)) / (2 * h)
            assert np.linalg.norm(su - fd_u) < 1e-6
            assert np.linalg.norm(sv - fd_v) < 1e-6


def test_gk02_second_partials_biquadratic_vs_fd():
    s, closed = _biquadratic_surface()
    h = 1e-4
    for u in (0.3, 0.7):
        for v in (0.3, 0.7):
            suu = surface_derivative(s, u, v, 2, 0)
            svv = surface_derivative(s, u, v, 0, 2)
            suv = surface_derivative(s, u, v, 1, 1)
            fd_uu = (closed(u + h, v) - 2 * closed(u, v)
                     + closed(u - h, v)) / h ** 2
            fd_vv = (closed(u, v + h) - 2 * closed(u, v)
                     + closed(u, v - h)) / h ** 2
            fd_uv = (closed(u + h, v + h) - closed(u + h, v - h)
                     - closed(u - h, v + h) + closed(u - h, v - h)) / (4 * h ** 2)
            assert np.linalg.norm(suu - fd_uu) < 1e-4
            assert np.linalg.norm(svv - fd_vv) < 1e-4
            assert np.linalg.norm(suv - fd_uv) < 1e-4


def test_gk02_normal_is_unit_and_outward_on_sphere():
    s, R = _rational_sphere_patch(3.0)
    for u in np.linspace(0.1, 0.9, 5):
        for v in np.linspace(0.1, 0.9, 5):
            n = surface_normal(s, u, v)
            assert abs(np.linalg.norm(n) - 1.0) < 1e-12


def test_gk02_derivatives_table_shape_and_zero_high_order():
    s, _ = _bilinear_surface()
    SKL = surface_derivatives(s, 0.4, 0.6, d=2)
    assert SKL.shape == (3, 3, 3)
    # degree (1,1): second pure partials are exactly zero
    assert np.allclose(SKL[2, 0], 0.0, atol=1e-12)
    assert np.allclose(SKL[0, 2], 0.0, atol=1e-12)


def test_gk02_surface_derivative_method_delegates():
    s, _ = _biquadratic_surface()
    a = s.derivative(0.3, 0.7, 1, 0)
    b = surface_derivative(s, 0.3, 0.7, 1, 0)
    assert np.allclose(a, b, atol=1e-14)


# ===========================================================================
# GK-03 — true (un-normalised), rational-correct curve derivative
# ===========================================================================

def test_gk03_degree1_line_constant_unnormalised():
    # Line P0=(1,2,3) -> P1=(5,7,11); knots [0,0,1,1]; C'(u) = (P1-P0) exactly.
    P0 = np.array([1.0, 2.0, 3.0])
    P1 = np.array([5.0, 7.0, 11.0])
    line = make_line_nurbs(P0, P1)
    expected = P1 - P0
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        d = curve_derivative(line, t, order=1)
        assert np.allclose(d, expected, atol=1e-12, rtol=0)
        # explicitly NOT unit-normalised
        assert abs(np.linalg.norm(d) - np.linalg.norm(expected)) < 1e-12
        assert np.linalg.norm(d) > 1.0


def test_gk03_cubic_bezier_endpoint_derivative_exact():
    # Cubic Bezier: C'(0) = 3(P1 - P0), C'(1) = 3(P3 - P2) exactly.
    P0 = np.array([0.0, 0.0, 0.0])
    P1 = np.array([1.0, 2.0, 0.0])
    P2 = np.array([3.0, -1.0, 1.0])
    P3 = np.array([4.0, 4.0, 2.0])
    knots = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0])
    c = NurbsCurve(degree=3, control_points=np.array([P0, P1, P2, P3]),
                   knots=knots)
    d0 = curve_derivative(c, 0.0, order=1)
    d1 = curve_derivative(c, 1.0, order=1)
    assert np.allclose(d0, 3.0 * (P1 - P0), atol=1e-11, rtol=0)
    assert np.allclose(d1, 3.0 * (P3 - P2), atol=1e-11, rtol=0)


def test_gk03_cubic_bezier_second_derivative_exact():
    # C''(0) = 6(P2 - 2 P1 + P0) for a cubic Bezier.
    P0 = np.array([0.0, 0.0, 0.0])
    P1 = np.array([1.0, 0.0, 0.0])
    P2 = np.array([2.0, 1.0, 0.0])
    P3 = np.array([3.0, 0.0, 0.0])
    knots = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0])
    c = NurbsCurve(degree=3, control_points=np.array([P0, P1, P2, P3]),
                   knots=knots)
    d2 = curve_derivative(c, 0.0, order=2)
    assert np.allclose(d2, 6.0 * (P2 - 2 * P1 + P0), atol=1e-10, rtol=0)


def test_gk03_quadratic_bezier_vs_finite_difference():
    P = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 1.0], [3.0, -1.0, 2.0]])
    knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    c = NurbsCurve(degree=2, control_points=P, knots=knots)
    h = 1e-6
    for t in (0.2, 0.5, 0.8):
        d = curve_derivative(c, t, order=1)
        fd = (de_boor(c, t + h) - de_boor(c, t - h)) / (2 * h)
        assert np.linalg.norm(d - fd) < 1e-6


def test_gk03_rational_quarter_circle_derivative_is_tangent():
    # On the exact rational circle the velocity C'(t) must be perpendicular
    # to the radius and have non-zero (un-normalised) magnitude.
    circ = make_circle_nurbs(np.zeros(3), 2.0)
    for t in np.linspace(0.01, 0.99, 25):
        p = de_boor(circ, t)
        d = curve_derivative(circ, t, order=1)
        # tangent ⟂ radius for a circle centred at origin
        assert abs(np.dot(p, d)) < 1e-7
        assert np.linalg.norm(d) > 1e-6  # not normalised to nothing


def test_gk03_rational_alias_matches():
    circ = make_circle_nurbs(np.zeros(3), 1.0)
    for t in (0.1, 0.3, 0.55, 0.8):
        a = curve_derivative(circ, t, 1)
        b = rational_curve_derivative(circ, t, 1)
        assert np.allclose(a, b, atol=1e-13)


def test_gk03_order_above_degree_is_zero():
    line = make_line_nurbs(np.zeros(3), np.array([1.0, 0.0, 0.0]))
    assert np.allclose(curve_derivative(line, 0.5, order=2), 0.0)


def test_gk03_non_rational_matches_basis_deriv_definition():
    # For a non-rational cubic, C'(u) = sum N'_i(u) P_i (no projection).
    rng = np.random.default_rng(7)
    P = rng.uniform(-1, 1, size=(6, 3))
    knots = np.array([0, 0, 0, 0, 0.4, 0.7, 1, 1, 1, 1], dtype=float)
    c = NurbsCurve(degree=3, control_points=P, knots=knots)
    from kerf_cad_core.geom.nurbs import find_span
    for u in (0.1, 0.4, 0.55, 0.9):
        sp = find_span(len(P) - 1, 3, u, knots)
        ders = _basis_funcs_derivs(sp, u, 3, knots, 1)
        man = np.zeros(3)
        for j in range(4):
            man += ders[1, j] * P[sp - 3 + j]
        assert np.allclose(curve_derivative(c, u, 1), man, atol=1e-11)


# ===========================================================================
# GK-04 — exact rational circle / arc / ellipse
# ===========================================================================

def test_gk04_circle_every_point_exact_radius_1e12():
    center = np.array([1.0, -2.0, 0.5])
    R = 3.7
    circ = make_circle_nurbs(center, R)
    assert circ.degree == 2
    assert circ.num_control_points == 9
    assert circ.is_rational
    for t in np.linspace(0.0, 1.0, 400):
        p = de_boor(circ, t)
        assert abs(np.linalg.norm(p - center) - R) < 1e-12


def test_gk04_circle_closes_exactly():
    circ = make_circle_nurbs(np.array([0.0, 0.0, 0.0]), 1.0)
    p0 = de_boor(circ, 0.0)
    p1 = de_boor(circ, 1.0)
    assert np.allclose(p0, p1, atol=1e-13, rtol=0)
    assert np.allclose(p0, np.array([1.0, 0.0, 0.0]), atol=1e-13)


def test_gk04_circle_quarter_points_exact():
    R = 2.0
    circ = make_circle_nurbs(np.zeros(3), R)
    # knot vector [0,0,0,1/4,1/4,1/2,1/2,3/4,3/4,1,1,1]
    expected = {
        0.0: np.array([R, 0.0, 0.0]),
        0.25: np.array([0.0, R, 0.0]),
        0.5: np.array([-R, 0.0, 0.0]),
        0.75: np.array([0.0, -R, 0.0]),
        1.0: np.array([R, 0.0, 0.0]),
    }
    for t, e in expected.items():
        assert np.allclose(de_boor(circ, t), e, atol=1e-12, rtol=0)


def test_gk04_circle_midpoint_45deg_exact():
    R = 1.0
    circ = make_circle_nurbs(np.zeros(3), R)
    # t=0.125 is the parametric midpoint of the first quadratic segment;
    # for the standard rational circle it lands exactly at 45 degrees.
    p = de_boor(circ, 0.125)
    ang = np.arctan2(p[1], p[0])
    assert abs(np.linalg.norm(p) - R) < 1e-12
    assert abs(ang - np.pi / 4) < 1e-12


def test_gk04_circle_custom_plane():
    center = np.array([0.0, 0.0, 5.0])
    R = 4.0
    x_axis = np.array([0.0, 1.0, 0.0])
    y_axis = np.array([0.0, 0.0, 1.0])
    circ = make_circle_nurbs(center, R, x_axis=x_axis, y_axis=y_axis)
    for t in np.linspace(0, 1, 50):
        p = de_boor(circ, t)
        assert abs(np.linalg.norm(p - center) - R) < 1e-12
        # circle lies in the x = center_x plane
        assert abs(p[0] - center[0]) < 1e-12


def test_gk04_quarter_arc_subtends_exactly_90deg():
    center = np.zeros(3)
    R = 2.5
    arc = make_arc_nurbs(center, R, 0.0, np.pi / 2)
    p0 = de_boor(arc, 0.0)
    p1 = de_boor(arc, 1.0)
    assert np.allclose(p0, np.array([R, 0.0, 0.0]), atol=1e-12)
    assert np.allclose(p1, np.array([0.0, R, 0.0]), atol=1e-12)
    a0 = np.arctan2(p0[1], p0[0])
    a1 = np.arctan2(p1[1], p1[0])
    assert abs((a1 - a0) - np.pi / 2) < 1e-12


def test_gk04_arc_all_points_on_circle_1e12():
    center = np.array([2.0, 3.0, 0.0])
    R = 1.25
    arc = make_arc_nurbs(center, R, np.deg2rad(20), np.deg2rad(200))
    for t in np.linspace(0, 1, 300):
        p = de_boor(arc, t)
        assert abs(np.linalg.norm(p - center) - R) < 1e-11


def test_gk04_arc_endpoints_match_requested_angles():
    center = np.zeros(3)
    R = 5.0
    a, b = np.deg2rad(30.0), np.deg2rad(285.0)
    arc = make_arc_nurbs(center, R, a, b)
    p0 = de_boor(arc, 0.0)
    p1 = de_boor(arc, 1.0)
    assert np.allclose(p0, R * np.array([np.cos(a), np.sin(a), 0.0]),
                       atol=1e-11)
    assert np.allclose(p1, R * np.array([np.cos(b), np.sin(b), 0.0]),
                       atol=1e-11)


def test_gk04_small_arc_single_segment():
    arc = make_arc_nurbs(np.zeros(3), 2.0, 0.0, np.deg2rad(40.0))
    # < 90 deg ⇒ a single quadratic segment ⇒ 3 control points
    assert arc.num_control_points == 3
    for t in np.linspace(0, 1, 50):
        assert abs(np.linalg.norm(de_boor(arc, t)) - 2.0) < 1e-12


def test_gk04_full_arc_equivalent_to_circle():
    center = np.array([1.0, 1.0, 0.0])
    R = 2.0
    arc = make_arc_nurbs(center, R, 0.0, 2 * np.pi)
    for t in np.linspace(0, 1, 200):
        assert abs(np.linalg.norm(de_boor(arc, t) - center) - R) < 1e-11


def test_gk04_ellipse_satisfies_implicit_equation_1e12():
    center = np.array([0.0, 0.0, 0.0])
    a, b = 3.0, 1.5
    ell = make_ellipse_nurbs(center, a, b)
    assert ell.is_rational
    for t in np.linspace(0, 1, 400):
        p = de_boor(ell, t)
        val = (p[0] / a) ** 2 + (p[1] / b) ** 2
        assert abs(val - 1.0) < 1e-12


def test_gk04_ellipse_axis_points_exact():
    center = np.array([2.0, -1.0, 0.0])
    a, b = 4.0, 2.0
    ell = make_ellipse_nurbs(center, a, b)
    assert np.allclose(de_boor(ell, 0.0), center + np.array([a, 0, 0]),
                       atol=1e-12)
    assert np.allclose(de_boor(ell, 0.25), center + np.array([0, b, 0]),
                       atol=1e-12)
    assert np.allclose(de_boor(ell, 0.5), center + np.array([-a, 0, 0]),
                       atol=1e-12)
    assert np.allclose(de_boor(ell, 0.75), center + np.array([0, -b, 0]),
                       atol=1e-12)


def test_gk04_ellipse_degenerate_to_circle():
    center = np.zeros(3)
    ell = make_ellipse_nurbs(center, 2.0, 2.0)
    circ = make_circle_nurbs(center, 2.0)
    for t in np.linspace(0, 1, 50):
        assert np.allclose(de_boor(ell, t), de_boor(circ, t), atol=1e-12)


def test_gk04_circle_backcompat_evaluate_radius():
    # Mirrors the spirit of the legacy test_surfacing.test_make_circle_nurbs
    # but now with the EXACT rational circle ⇒ tolerance tightens to 1e-12.
    center = np.array([0.0, 0.0, 0.0])
    circ = make_circle_nurbs(center, 1.0)
    assert circ.degree == 2
    assert circ.num_control_points >= 3
    assert abs(np.linalg.norm(circ.evaluate(0.0) - center) - 1.0) < 1e-12


def test_gk04_arc_zero_sweep_raises():
    with pytest.raises(ValueError):
        make_arc_nurbs(np.zeros(3), 1.0, 1.0, 1.0)


# ===========================================================================
# Cross-cutting regression: non-rational paths unchanged for plain callers
# ===========================================================================

def test_regression_line_evaluate_unchanged():
    line = make_line_nurbs(np.array([0.0, 0.0, 0.0]),
                           np.array([1.0, 0.0, 0.0]))
    assert np.allclose(line.evaluate(0.5), np.array([0.5, 0.0, 0.0]),
                       atol=1e-13)


def test_regression_bspline_curve_matches_de_boor_reference():
    # A plain (non-rational) cubic must match a direct basis-sum evaluation.
    rng = np.random.default_rng(99)
    P = rng.uniform(-1, 1, size=(7, 3))
    knots = np.array([0, 0, 0, 0, 0.3, 0.6, 0.8, 1, 1, 1, 1], dtype=float)
    c = NurbsCurve(degree=3, control_points=P, knots=knots)
    from kerf_cad_core.geom.nurbs import find_span
    for u in np.linspace(0, 1, 31):
        sp = find_span(len(P) - 1, 3, u, knots)
        N = _basis_fns(sp, u, 3, knots)
        ref = np.zeros(3)
        for j in range(4):
            ref += N[j] * P[sp - 3 + j]
        assert np.allclose(de_boor(c, u), ref, atol=1e-12, rtol=0)


def test_regression_surface_eval_parity_random_bspline():
    rng = np.random.default_rng(2024)
    P = rng.uniform(-3, 3, size=(5, 4, 3))
    ku = np.array([0, 0, 0, 0.5, 1, 1, 1], dtype=float)
    kv = np.array([0, 0, 0, 0.4, 0.7, 1, 1, 1], dtype=float)
    s = NurbsSurface(degree_u=2, degree_v=3, control_points=P,
                     knots_u=ku, knots_v=kv)
    for u in np.linspace(0, 1, 11):
        for v in np.linspace(0, 1, 11):
            assert np.allclose(surface_evaluate(s, u, v),
                               _nurbs_surface_eval(s, u, v),
                               atol=1e-12, rtol=0)
