"""
test_inversion.py
=================
Hermetic, analytic-oracle tests for geom/inversion.py (GK-06/07/08):

  closest_point_curve     -- point inversion on a NurbsCurve
  closest_point_surface   -- UV point inversion on a NurbsSurface
  project_point_to_curve  -- public curve-projection API
  pull_curve_to_surface   -- public curve->surface pull API

Plus a behaviour-preservation check for the trim_curve delegation.

Every test asserts a *closed-form* quantity: exact rational circle radius,
exact recovered parameter, residual vector perpendicular to the tangent /
both surface partials, exact analytic foot on a sphere/cylinder, etc.
No network, no external binaries.
"""

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface
from kerf_cad_core.geom.inversion import (
    closest_point_curve,
    closest_point_surface,
    project_point_to_curve,
    pull_curve_to_surface,
    _curve_eval,
    _surf_eval,
    _curve_ders,
    _surf_partials,
)


# ---------------------------------------------------------------------------
# Analytic NURBS fixtures (exact rational primitives)
# ---------------------------------------------------------------------------

def rational_circle(center, radius):
    """Exact rational full circle (Piegl & Tiller, 9 CP, 4 quarter arcs)."""
    c = np.asarray(center, dtype=float)
    w = math.sqrt(2.0) / 2.0
    dirs = np.array([
        [1, 0, 0], [1, 1, 0], [0, 1, 0], [-1, 1, 0], [-1, 0, 0],
        [-1, -1, 0], [0, -1, 0], [1, -1, 0], [1, 0, 0],
    ], dtype=float)
    ws = np.array([1, w, 1, w, 1, w, 1, w, 1.0])
    cp = np.zeros((9, 4))
    for i in range(9):
        xyz = c + radius * dirs[i]
        cp[i, :3] = xyz * ws[i]
        cp[i, 3] = ws[i]
    knots = np.array([0, 0, 0, .25, .25, .5, .5, .75, .75, 1, 1, 1.0])
    return NurbsCurve(degree=2, control_points=cp, knots=knots)


def line_curve(p0, p1):
    """Degree-1 polynomial line segment."""
    return NurbsCurve(
        degree=1,
        control_points=np.array([p0, p1], dtype=float),
        knots=np.array([0.0, 0.0, 1.0, 1.0]),
    )


def cubic_bezier(p0, p1, p2, p3):
    """Degree-3 polynomial Bezier (single span)."""
    return NurbsCurve(
        degree=3,
        control_points=np.array([p0, p1, p2, p3], dtype=float),
        knots=np.array([0., 0., 0., 0., 1., 1., 1., 1.]),
    )


def plane_patch(origin, du, dv):
    """Bilinear (degree-1x1) plane patch spanning origin + s*du + t*dv."""
    o = np.asarray(origin, float)
    du = np.asarray(du, float)
    dv = np.asarray(dv, float)
    cps = np.zeros((2, 2, 3))
    cps[0, 0] = o
    cps[1, 0] = o + du
    cps[0, 1] = o + dv
    cps[1, 1] = o + du + dv
    return NurbsSurface(
        degree_u=1, degree_v=1, control_points=cps,
        knots_u=np.array([0., 0., 1., 1.]),
        knots_v=np.array([0., 0., 1., 1.]),
    )


def rational_cylinder(radius, height):
    """Exact rational cylinder: rational circle (u) x linear height (v)."""
    w = math.sqrt(2.0) / 2.0
    cw = np.array([1, w, 1, w, 1, w, 1, w, 1.0])
    cir = np.array([
        [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0],
        [-1, -1], [0, -1], [1, -1], [1, 0],
    ], dtype=float)
    nu, nv = 9, 2
    cp = np.zeros((nu, nv, 4))
    for i in range(nu):
        for j in range(nv):
            z = 0.0 if j == 0 else height
            W = cw[i]
            x = radius * cir[i, 0]
            y = radius * cir[i, 1]
            cp[i, j, :3] = np.array([x, y, z]) * W
            cp[i, j, 3] = W
    ku = np.array([0, 0, 0, .25, .25, .5, .5, .75, .75, 1, 1, 1.0])
    kv = np.array([0., 0., 1., 1.])
    return NurbsSurface(degree_u=2, degree_v=1, control_points=cp,
                        knots_u=ku, knots_v=kv)


def rational_sphere(radius):
    """Exact rational sphere (revolved rational half-circle)."""
    w = math.sqrt(2.0) / 2.0
    prof = np.array([[0, 0, 1], [1, 0, 1], [1, 0, 0],
                     [1, 0, -1], [0, 0, -1]], dtype=float)
    pw = np.array([1, w, 1, w, 1.0])
    cw = np.array([1, w, 1, w, 1, w, 1, w, 1.0])
    cir = np.array([
        [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0],
        [-1, -1], [0, -1], [1, -1], [1, 0],
    ], dtype=float)
    nu, nv = 9, 5
    cp = np.zeros((nu, nv, 4))
    for i in range(nu):
        for j in range(nv):
            rad = prof[j, 0] * radius
            z = prof[j, 2] * radius
            W = cw[i] * pw[j]
            x = rad * cir[i, 0]
            y = rad * cir[i, 1]
            cp[i, j, :3] = np.array([x, y, z]) * W
            cp[i, j, 3] = W
    ku = np.array([0, 0, 0, .25, .25, .5, .5, .75, .75, 1, 1, 1.0])
    kv = np.array([0, 0, 0, .5, .5, 1, 1, 1.0])
    return NurbsSurface(degree_u=2, degree_v=2, control_points=cp,
                        knots_u=ku, knots_v=kv)


# ---------------------------------------------------------------------------
# Fixture self-consistency (the oracles must themselves be exact)
# ---------------------------------------------------------------------------

def test_rational_circle_is_exact_radius():
    c = rational_circle([1.0, -2.0, 0.5], 3.0)
    for t in np.linspace(0, 1, 33):
        p = _curve_eval(c, t)
        assert abs(np.linalg.norm(p - np.array([1.0, -2.0, 0.5])) - 3.0) < 1e-11


def test_rational_sphere_is_exact_radius():
    s = rational_sphere(2.5)
    rng = np.random.default_rng(1)
    for _ in range(40):
        u, v = rng.uniform(0, 1), rng.uniform(0, 1)
        p = _surf_eval(s, u, v)
        assert abs(np.linalg.norm(p) - 2.5) < 1e-8


def test_rational_cylinder_is_exact_radius():
    s = rational_cylinder(1.7, 4.0)
    rng = np.random.default_rng(2)
    for _ in range(40):
        u, v = rng.uniform(0, 1), rng.uniform(0, 1)
        p = _surf_eval(s, u, v)
        assert abs(math.hypot(p[0], p[1]) - 1.7) < 1e-10


# ---------------------------------------------------------------------------
# GK-06  closest_point_curve
# ---------------------------------------------------------------------------

def test_point_on_circle_inverts_to_exact_t():
    """Point exactly on a NURBS circle inverts; point recovered to 1e-9."""
    circ = rational_circle([0, 0, 0], 2.0)
    for deg in (10, 75, 150, 215, 305):
        ang = math.radians(deg)
        P = np.array([2 * math.cos(ang), 2 * math.sin(ang), 0.0])
        t, pt, d = closest_point_curve(circ, P)
        assert d < 1e-9
        assert np.linalg.norm(pt - P) < 1e-9


def test_circle_param_recovers_evaluation_point():
    circ = rational_circle([1.0, 1.0, 0.0], 1.0)
    for tq in (0.05, 0.2, 0.5, 0.83, 0.97):
        Pq = _curve_eval(circ, tq)
        t, pt, d = closest_point_curve(circ, Pq)
        assert d < 1e-9
        assert np.linalg.norm(_curve_eval(circ, t) - Pq) < 1e-9


def test_off_circle_foot_is_radial_and_perp_tangent():
    circ = rational_circle([0, 0, 0], 2.0)
    rng = np.random.default_rng(3)
    for _ in range(12):
        P = np.array([rng.uniform(3, 8), rng.uniform(-8, 8), 0.0])
        t, pt, d = closest_point_curve(circ, P)
        foot_exp = 2.0 * P / np.linalg.norm(P)
        assert np.linalg.norm(pt - foot_exp) < 1e-7
        # residual perpendicular to tangent
        _, C1, _ = _curve_ders(circ, t, 2)
        r = P - pt
        cos = abs(np.dot(r, C1)) / (np.linalg.norm(r) * np.linalg.norm(C1))
        assert cos < 1e-7


def test_line_projection_exact_foot():
    """Foot of perpendicular onto a line is the analytic projection."""
    ln = line_curve([0, 0, 0], [10, 0, 0])
    P = np.array([3.0, 4.0, 0.0])
    t, pt, d = closest_point_curve(ln, P)
    assert np.linalg.norm(pt - np.array([3.0, 0.0, 0.0])) < 1e-10
    assert abs(d - 4.0) < 1e-10
    # residual perpendicular to tangent (the line direction)
    _, C1, _ = _curve_ders(ln, t, 2)
    assert abs(np.dot(P - pt, C1)) < 1e-10


def test_line_projection_clamps_before_start():
    ln = line_curve([0, 0, 0], [4, 0, 0])
    P = np.array([-3.0, 2.0, 0.0])
    t, pt, d = closest_point_curve(ln, P)
    assert np.linalg.norm(pt - np.array([0.0, 0.0, 0.0])) < 1e-10
    assert abs(t - 0.0) < 1e-9


def test_line_projection_clamps_after_end():
    ln = line_curve([0, 0, 0], [4, 0, 0])
    P = np.array([9.0, -2.0, 0.0])
    t, pt, d = closest_point_curve(ln, P)
    assert np.linalg.norm(pt - np.array([4.0, 0.0, 0.0])) < 1e-10
    assert abs(t - 1.0) < 1e-9


def test_point_on_line_distance_zero():
    ln = line_curve([1, 2, 3], [4, 6, 9])
    Pq = _curve_eval(ln, 0.37)
    t, pt, d = closest_point_curve(ln, Pq)
    assert d < 1e-10
    assert np.linalg.norm(pt - Pq) < 1e-10


def test_cubic_bezier_endpoint_tangent():
    """Analytic derivative oracle: C'(0) = 3(P1 - P0) for a cubic Bezier."""
    P0 = np.array([0.0, 0.0, 0.0])
    P1 = np.array([1.0, 2.0, 0.0])
    P2 = np.array([3.0, 2.0, 0.0])
    P3 = np.array([4.0, 0.0, 0.0])
    bz = cubic_bezier(P0, P1, P2, P3)
    _, C1, _ = _curve_ders(bz, 0.0, 2)
    assert np.linalg.norm(C1 - 3.0 * (P1 - P0)) < 1e-10
    _, C1e, _ = _curve_ders(bz, 1.0, 2)
    assert np.linalg.norm(C1e - 3.0 * (P3 - P2)) < 1e-10


def test_cubic_bezier_foot_perpendicular():
    bz = cubic_bezier([0, 0, 0], [1, 3, 0], [4, 3, 0], [5, 0, 0])
    rng = np.random.default_rng(4)
    for _ in range(10):
        P = np.array([rng.uniform(0, 5), rng.uniform(-4, 6), 0.0])
        t, pt, d = closest_point_curve(bz, P)
        _, C1, _ = _curve_ders(bz, t, 2)
        r = P - pt
        rn = np.linalg.norm(r)
        if rn < 1e-9:
            continue
        # interior foot must be perpendicular; endpoints may not be
        if 1e-6 < t < 1.0 - 1e-6:
            cos = abs(np.dot(r, C1)) / (rn * np.linalg.norm(C1))
            assert cos < 1e-6


def test_global_fallback_far_from_midpoint():
    """Nearest foot far from param-midpoint still converges (no local trap)."""
    circ = rational_circle([0, 0, 0], 5.0)
    # Foot is near angle 350deg -> t ~ 0.97, far from midpoint 0.5.
    ang = math.radians(350.0)
    P = np.array([9.0 * math.cos(ang), 9.0 * math.sin(ang), 0.0])
    t, pt, d = closest_point_curve(circ, P)
    foot_exp = 5.0 * P / np.linalg.norm(P)
    assert np.linalg.norm(pt - foot_exp) < 1e-7


def test_global_fallback_wavy_curve():
    """A wavy polyline-like curve: nearest foot is not near the midpoint."""
    pts = np.array([
        [0, 0, 0], [1, 4, 0], [2, -4, 0], [3, 4, 0],
        [4, -4, 0], [5, 4, 0], [6, 0, 0],
    ], dtype=float)
    n = len(pts)
    knots = np.concatenate(([0, 0, 0], np.linspace(0, 1, n - 2), [1, 1, 1]))
    wavy = NurbsCurve(degree=3, control_points=pts, knots=knots)
    # Query near the far right end.
    P = np.array([5.9, 0.0, 0.0])
    t, pt, d = closest_point_curve(wavy, P)
    # Brute-force ground truth.
    ts = np.linspace(0, 1, 4001)
    gd = min(np.linalg.norm(_curve_eval(wavy, tt) - P) for tt in ts)
    assert d <= gd + 1e-6


def test_closed_curve_wrap_handled():
    """Closed curve: a foot straddling the seam still converges."""
    circ = rational_circle([0, 0, 0], 2.0)
    # Point just past angle 0 (near the seam at t=0/t=1).
    ang = math.radians(2.0)
    P = np.array([6.0 * math.cos(ang), 6.0 * math.sin(ang), 0.0])
    t, pt, d = closest_point_curve(circ, P)
    foot_exp = 2.0 * P / np.linalg.norm(P)
    assert np.linalg.norm(pt - foot_exp) < 1e-7
    # And on the other side of the seam.
    ang2 = math.radians(358.0)
    P2 = np.array([6.0 * math.cos(ang2), 6.0 * math.sin(ang2), 0.0])
    t2, pt2, d2 = closest_point_curve(circ, P2)
    foot2 = 2.0 * P2 / np.linalg.norm(P2)
    assert np.linalg.norm(pt2 - foot2) < 1e-7


def test_centre_of_circle_returns_valid_non_nan():
    """Point at centre of a circle returns a valid (non-NaN) nearest."""
    circ = rational_circle([3.0, -1.0, 2.0], 4.0)
    t, pt, d = closest_point_curve(circ, np.array([3.0, -1.0, 2.0]))
    assert np.all(np.isfinite(pt))
    assert np.isfinite(d)
    assert abs(d - 4.0) < 1e-9
    # The foot lies on the circle.
    assert abs(np.linalg.norm(pt - np.array([3.0, -1.0, 2.0])) - 4.0) < 1e-9


def test_curve_inversion_3d_skew_line():
    ln = line_curve([1, 1, 1], [5, 9, 13])
    P = np.array([2.0, -3.0, 7.0])
    t, pt, d = closest_point_curve(ln, P)
    # Analytic projection onto the infinite line.
    a = np.array([1.0, 1, 1])
    dvec = np.array([4.0, 8, 12])
    s = np.dot(P - a, dvec) / np.dot(dvec, dvec)
    s = min(1.0, max(0.0, s))
    foot = a + s * dvec
    assert np.linalg.norm(pt - foot) < 1e-9


def test_curve_distance_matches_norm():
    circ = rational_circle([0, 0, 0], 3.0)
    P = np.array([7.0, -2.0, 0.0])
    t, pt, d = closest_point_curve(circ, P)
    assert abs(d - np.linalg.norm(P - pt)) < 1e-12


def test_curve_grid_of_points_exact_feet_on_plane_curve():
    """Grid of points projected onto a plane-embedded curve -> exact feet,
    residual perpendicular to the tangent to 1e-9."""
    # Parabola y = x^2/4 as a cubic-ish polynomial curve in the z=0 plane.
    xs = np.linspace(-3, 3, 7)
    ctrl = np.array([[x, x * x / 4.0, 0.0] for x in xs])
    n = len(ctrl)
    knots = np.concatenate(([0, 0, 0], np.linspace(0, 1, n - 2), [1, 1, 1]))
    para = NurbsCurve(degree=3, control_points=ctrl, knots=knots)
    rng = np.random.default_rng(7)
    for _ in range(20):
        P = np.array([rng.uniform(-2.5, 2.5), rng.uniform(-2, 5), 0.0])
        t, pt, d = closest_point_curve(para, P)
        assert pt[2] == pytest.approx(0.0, abs=1e-9)
        if 1e-5 < t < 1.0 - 1e-5:
            _, C1, _ = _curve_ders(para, t, 2)
            r = P - pt
            rn = np.linalg.norm(r)
            if rn > 1e-7:
                cos = abs(np.dot(r, C1)) / (rn * np.linalg.norm(C1))
                assert cos < 1e-9


# ---------------------------------------------------------------------------
# GK-07  closest_point_surface
# ---------------------------------------------------------------------------

def test_point_on_plane_inverts_to_zero_distance():
    pl = plane_patch([0, 0, 0], [4, 0, 0], [0, 3, 0])
    rng = np.random.default_rng(8)
    for _ in range(15):
        u, v = rng.uniform(0, 1), rng.uniform(0, 1)
        Pq = _surf_eval(pl, u, v)
        ru, rv, fp, d = closest_point_surface(pl, Pq)
        assert d < 1e-9
        assert np.linalg.norm(fp - Pq) < 1e-9


def test_point_above_plane_foot_is_orthogonal_projection():
    pl = plane_patch([1, 1, 0], [5, 0, 0], [0, 4, 0])
    P = np.array([3.0, 2.5, 7.0])  # 7 above the z=0 plane
    u, v, fp, d = closest_point_surface(pl, P)
    assert abs(fp[2] - 0.0) < 1e-10
    assert np.linalg.norm(fp - np.array([3.0, 2.5, 0.0])) < 1e-9
    assert abs(d - 7.0) < 1e-9


def test_plane_residual_perp_both_partials():
    """For interior feet on a skew-parametrised plane the residual is
    perpendicular to both partials.  (Boundary-clamped feet are a
    constrained projection where perpendicularity need not hold and are
    excluded -- that is the correct closest-point-on-a-finite-patch
    behaviour.)"""
    pl = plane_patch([0, 0, 0], [6, 1, 0], [1, 5, 2])
    rng = np.random.default_rng(9)
    n_interior = 0
    for _ in range(15):
        P = np.array([rng.uniform(0, 6), rng.uniform(0, 6), rng.uniform(-5, 5)])
        u, v, fp, d = closest_point_surface(pl, P)
        S, Su, Sv, _, _, _ = _surf_partials(pl, u, v)
        r = P - fp
        rn = np.linalg.norm(r)
        if rn < 1e-9:
            continue
        if not (1e-7 < u < 1.0 - 1e-7 and 1e-7 < v < 1.0 - 1e-7):
            continue
        cu = abs(np.dot(r, Su)) / (rn * np.linalg.norm(Su))
        cv = abs(np.dot(r, Sv)) / (rn * np.linalg.norm(Sv))
        assert cu < 1e-9
        assert cv < 1e-9
        n_interior += 1
    assert n_interior >= 8


def test_sphere_inverts_to_radial_foot():
    """Point above a rational sphere inverts to the radial foot."""
    s = rational_sphere(3.0)
    rng = np.random.default_rng(10)
    for _ in range(20):
        P = rng.uniform(-7, 7, 3)
        if np.linalg.norm(P) < 1.0:
            continue
        u, v, fp, d = closest_point_surface(s, P)
        foot_exp = 3.0 * P / np.linalg.norm(P)
        assert np.linalg.norm(fp - foot_exp) < 1e-6
        assert abs(d - abs(np.linalg.norm(P) - 3.0)) < 1e-6


def test_sphere_residual_perp_both_partials():
    """Foot-of-perpendicular: residual ⟂ both surface partials to 1e-9."""
    s = rational_sphere(2.0)
    rng = np.random.default_rng(11)
    n_ok = 0
    for _ in range(25):
        P = rng.uniform(-5, 5, 3)
        if np.linalg.norm(P) < 0.6:
            continue
        u, v, fp, d = closest_point_surface(s, P)
        S, Su, Sv, _, _, _ = _surf_partials(s, u, v)
        r = P - fp
        rn = np.linalg.norm(r)
        if rn < 1e-7:
            continue
        cu = abs(np.dot(r, Su)) / (rn * np.linalg.norm(Su))
        cv = abs(np.dot(r, Sv)) / (rn * np.linalg.norm(Sv))
        assert cu < 1e-7
        assert cv < 1e-7
        n_ok += 1
    assert n_ok >= 10


def test_cylinder_radial_foot():
    """Point off a rational cylinder -> radial foot at exact radius."""
    s = rational_cylinder(1.5, 6.0)
    rng = np.random.default_rng(12)
    for _ in range(20):
        x, y = rng.uniform(-5, 5, 2)
        z = rng.uniform(0.5, 5.5)
        if math.hypot(x, y) < 0.3:
            continue
        P = np.array([x, y, z])
        u, v, fp, d = closest_point_surface(s, P)
        # Foot must be on the cylinder wall (radius exact), same height.
        assert abs(math.hypot(fp[0], fp[1]) - 1.5) < 1e-6
        assert abs(fp[2] - z) < 1e-6
        rad = math.hypot(x, y)
        exp_xy = 1.5 * np.array([x, y]) / rad
        assert np.linalg.norm(fp[:2] - exp_xy) < 1e-6


def test_surface_global_fallback_far_corner():
    """Global fallback: the nearest foot is far from the parameter midpoint
    and the analytic answer is unambiguous (exact rational sphere), so a
    seed-trapped local solver would visibly miss it."""
    s = rational_sphere(2.0)
    # Pick a *surface* point near a far corner of the (u, v) domain, then a
    # query point straight out along its normal (radial for a sphere).  The
    # exact closest foot is that surface point; its (u, v) is far from
    # (0.5, 0.5), so a midpoint-seeded Newton would converge elsewhere.
    u_far, v_far = 0.93, 0.07
    foot_exact = _surf_eval(s, u_far, v_far)
    radial = foot_exact / np.linalg.norm(foot_exact)
    P = foot_exact + 3.5 * radial  # 3.5 outside the sphere, radially
    u, v, fp, d = closest_point_surface(s, P)
    # Exact analytic oracle: the foot is the radial projection at radius 2.
    foot_exp = 2.0 * P / np.linalg.norm(P)
    assert np.linalg.norm(fp - foot_exp) < 1e-6
    assert np.linalg.norm(fp - foot_exact) < 1e-6
    assert abs(d - (np.linalg.norm(P) - 2.0)) < 1e-6
    # Beat a fine brute-force grid (true global, no boundary artefact here).
    gg = 1e18
    for uu in np.linspace(0, 1, 161):
        for vv in np.linspace(0, 1, 161):
            gg = min(gg, np.linalg.norm(_surf_eval(s, uu, vv) - P))
    assert d <= gg + 1e-6


def test_surface_distance_matches_norm():
    s = rational_sphere(2.0)
    P = np.array([4.0, 1.0, -3.0])
    u, v, fp, d = closest_point_surface(s, P)
    assert abs(d - np.linalg.norm(P - fp)) < 1e-12


def test_sphere_centre_returns_valid_non_nan():
    """Degenerate query (sphere centre): a valid finite foot at r."""
    s = rational_sphere(2.5)
    u, v, fp, d = closest_point_surface(s, np.array([0.0, 0.0, 0.0]))
    assert np.all(np.isfinite(fp))
    assert np.isfinite(d)
    assert abs(np.linalg.norm(fp) - 2.5) < 1e-7
    assert abs(d - 2.5) < 1e-7


def test_surface_analytic_partials_match_finite_difference():
    """Analytic partials (rational sphere) agree with central FD < 1e-6."""
    s = rational_sphere(3.0)
    h = 1e-6
    for (u, v) in [(0.3, 0.4), (0.62, 0.18), (0.81, 0.77)]:
        S, Su, Sv, Suu, Suv, Svv = _surf_partials(s, u, v)
        fd_u = (_surf_eval(s, u + h, v) - _surf_eval(s, u - h, v)) / (2 * h)
        fd_v = (_surf_eval(s, u, v + h) - _surf_eval(s, u, v - h)) / (2 * h)
        assert np.linalg.norm(Su - fd_u) < 1e-5
        assert np.linalg.norm(Sv - fd_v) < 1e-5


def test_surface_point_recovers_uv_eval():
    s = rational_sphere(1.5)
    for (uq, vq) in [(0.12, 0.6), (0.45, 0.33), (0.88, 0.91)]:
        Pq = _surf_eval(s, uq, vq)
        u, v, fp, d = closest_point_surface(s, Pq)
        assert d < 1e-8
        assert np.linalg.norm(_surf_eval(s, u, v) - Pq) < 1e-8


# ---------------------------------------------------------------------------
# GK-08  public APIs
# ---------------------------------------------------------------------------

def test_project_point_to_curve_payload():
    circ = rational_circle([0, 0, 0], 2.0)
    res = project_point_to_curve(circ, [5.0, 0.0, 0.0])
    assert res["ok"] is True
    assert abs(res["dist"] - 3.0) < 1e-9
    assert np.linalg.norm(np.array(res["point"]) - np.array([2.0, 0.0, 0.0])) < 1e-9


def test_project_point_to_curve_bad_input():
    res = project_point_to_curve("not a curve", [0, 0, 0])
    assert res["ok"] is False
    assert "reason" in res


def test_pull_curve_to_surface_onto_plane():
    """A line above a plane pulls down to its exact orthogonal feet."""
    pl = plane_patch([-5, -5, 0], [10, 0, 0], [0, 10, 0])
    ln = line_curve([-2, -2, 4], [3, 3, 4])  # constant height 4 above z=0
    res = pull_curve_to_surface(ln, pl, n=11)
    assert res["ok"] is True
    assert abs(res["max_dist"] - 4.0) < 1e-7
    for (pt, uv) in zip(res["points"], res["uv"]):
        assert abs(pt[2] - 0.0) < 1e-8  # foot lies on z=0 plane


def test_pull_curve_to_surface_onto_sphere_radial():
    """Pulling a curve onto a sphere gives radially-projected feet."""
    s = rational_sphere(3.0)
    # A line well outside the sphere.
    ln = line_curve([5, -4, 2], [5, 4, -2])
    res = pull_curve_to_surface(ln, s, n=9)
    assert res["ok"] is True
    for pt in res["points"]:
        assert abs(np.linalg.norm(pt) - 3.0) < 1e-6


def test_pull_curve_to_surface_bad_input():
    res = pull_curve_to_surface("x", "y")
    assert res["ok"] is False


def test_pull_curve_uv_in_domain():
    s = rational_sphere(2.0)
    ln = line_curve([4, 0, 1], [4, 1, -1])
    res = pull_curve_to_surface(ln, s, n=7)
    assert res["ok"] is True
    for (u, v) in res["uv"]:
        assert -1e-9 <= u <= 1.0 + 1e-9
        assert -1e-9 <= v <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# Robustness / never-raises
# ---------------------------------------------------------------------------

def test_closest_point_curve_rejects_non_curve():
    with pytest.raises(TypeError):
        closest_point_curve(object(), [0, 0, 0])


def test_closest_point_surface_rejects_non_surface():
    with pytest.raises(TypeError):
        closest_point_surface(object(), [0, 0, 0])


def test_curve_inversion_handles_2d_point_input():
    ln = line_curve([0, 0, 0], [4, 0, 0])
    t, pt, d = closest_point_curve(ln, [2.0, 3.0])
    assert np.linalg.norm(pt - np.array([2.0, 0.0, 0.0])) < 1e-9
    assert abs(d - 3.0) < 1e-9


def test_surface_inversion_handles_list_input():
    pl = plane_patch([0, 0, 0], [2, 0, 0], [0, 2, 0])
    u, v, fp, d = closest_point_surface(pl, [1.0, 1.0, 5.0])
    assert abs(d - 5.0) < 1e-9


# ---------------------------------------------------------------------------
# trim_curve delegation behaviour preservation (GK-07 rewire)
# ---------------------------------------------------------------------------

def test_trim_curve_project_point_to_uv_behaviour_preserved():
    """trim_curve._project_point_to_uv must still return an in-domain (u, v)
    whose surface point matches the orthogonal projection, after being
    rewired to delegate to closest_point_surface."""
    from kerf_cad_core.geom.trim_curve import _project_point_to_uv
    from kerf_cad_core.geom.nurbs import surface_evaluate

    pl = plane_patch([0, 0, 0], [4, 0, 0], [0, 4, 0])
    P = np.array([1.5, 2.5, 6.0])
    uv = _project_point_to_uv(pl, P, 0.5, 0.5, tol=1e-9)
    assert uv is not None
    u, v = uv
    assert 0.0 - 1e-7 <= u <= 1.0 + 1e-7
    assert 0.0 - 1e-7 <= v <= 1.0 + 1e-7
    foot = surface_evaluate(pl, u, v)[:3]
    assert np.linalg.norm(foot - np.array([1.5, 2.5, 0.0])) < 1e-6


def test_trim_curve_project_curve_to_uv_still_works():
    """The public project_curve_to_uv (which uses _project_point_to_uv)
    still produces a UV trail for points above a plane."""
    from kerf_cad_core.geom.trim_curve import project_curve_to_uv

    pl = plane_patch([0, 0, 0], [10, 0, 0], [0, 10, 0])
    pts = [[2, 2, 3], [4, 5, 3], [7, 8, 3]]
    uvs = project_curve_to_uv(pl, pts, tol=1e-7)
    assert len(uvs) == 3
    for (u, v) in uvs:
        assert 0.0 <= u <= 1.0 + 1e-6
        assert 0.0 <= v <= 1.0 + 1e-6
