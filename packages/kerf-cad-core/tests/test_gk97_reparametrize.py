"""GK-97: Reparametrize curve / surface — hermetic pytest oracle.

Oracles
-------
1. normalize_knots(curve) -> knots in [0, 1], identical point set
   (evaluate at remapped params matches original).
2. normalize_knots(surface) -> both knot vectors in [0, 1].
3. reparametrize_curve(curve, 0, 2) -> domain [0, 2], geometry preserved
   (evaluate at remapped params matches original).
4. reparametrize_arclength(curve) -> domain [0, 1]; uniform arc-length
   steps advance the curve equally in Euclidean distance (speed ≈ const).
5. Public façade exports normalize_knots, reparametrize_curve,
   reparametrize_arclength.
"""

from __future__ import annotations

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import (
    NurbsCurve,
    NurbsSurface,
    normalize_knots,
    reparametrize_curve,
    reparametrize_arclength,
    curve_derivative,
)
import kerf_cad_core.geom as _geom_pkg


TOL = 1e-10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_curve() -> NurbsCurve:
    """Degree-1 curve from (0,0,0) to (3,0,0), domain [2, 5]."""
    cp = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]])
    knots = np.array([2.0, 2.0, 5.0, 5.0])
    return NurbsCurve(degree=1, control_points=cp, knots=knots)


def _cubic_curve() -> NurbsCurve:
    """Degree-3 B-spline with 5 CPs, non-normalised domain [10, 20]."""
    cp = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 2.0, 0.0],
        [2.0, 0.0, 1.0],
        [3.0, 2.0, 0.0],
        [4.0, 0.0, 0.0],
    ])
    # domain [10, 20]
    knots = np.array([10.0, 10.0, 10.0, 10.0, 15.0, 20.0, 20.0, 20.0, 20.0])
    return NurbsCurve(degree=3, control_points=cp, knots=knots)


def _circular_arc() -> NurbsCurve:
    """Exact rational quarter-circle in XY plane, domain [0, pi/2]."""
    from kerf_cad_core.geom.nurbs import make_arc_nurbs
    return make_arc_nurbs(center=np.zeros(3), radius=1.0,
                          start_angle=0.0, end_angle=np.pi / 2)


def _bilinear_surface() -> NurbsSurface:
    """Degree-1 x degree-1 surface with domain [3,7] x [1,4]."""
    cp = np.array([
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [[1.0, 0.0, 0.5], [1.0, 1.0, 0.5]],
    ])
    knots_u = np.array([3.0, 3.0, 7.0, 7.0])
    knots_v = np.array([1.0, 1.0, 4.0, 4.0])
    return NurbsSurface(degree_u=1, degree_v=1,
                        control_points=cp, knots_u=knots_u, knots_v=knots_v)


# ---------------------------------------------------------------------------
# 1. Public export check
# ---------------------------------------------------------------------------

def test_public_exports():
    assert hasattr(_geom_pkg, "normalize_knots"), "normalize_knots missing from geom facade"
    assert hasattr(_geom_pkg, "reparametrize_curve"), "reparametrize_curve missing from geom facade"
    assert hasattr(_geom_pkg, "reparametrize_arclength"), "reparametrize_arclength missing from geom facade"
    assert _geom_pkg.normalize_knots is normalize_knots
    assert _geom_pkg.reparametrize_curve is reparametrize_curve
    assert _geom_pkg.reparametrize_arclength is reparametrize_arclength


# ---------------------------------------------------------------------------
# 2. normalize_knots — curve
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make_curve", [_line_curve, _cubic_curve])
def test_normalize_knots_curve_domain(make_curve):
    """After normalization knot vector spans [0, 1]."""
    c = make_curve()
    nc = normalize_knots(c)
    assert nc.knots[0] == pytest.approx(0.0, abs=TOL)
    assert nc.knots[-1] == pytest.approx(1.0, abs=TOL)


@pytest.mark.parametrize("make_curve", [_line_curve, _cubic_curve])
def test_normalize_knots_curve_geometry(make_curve):
    """Points on normalized curve match original at remapped parameters."""
    c = make_curve()
    nc = normalize_knots(c)
    a_orig = float(c.knots[c.degree])
    b_orig = float(c.knots[-(c.degree + 1)])
    a_new = float(nc.knots[nc.degree])
    b_new = float(nc.knots[-(nc.degree + 1)])

    for s in np.linspace(0.0, 1.0, 17):
        t_orig = a_orig + s * (b_orig - a_orig)
        t_new = a_new + s * (b_new - a_new)
        pt_orig = c.evaluate(t_orig)
        pt_new = nc.evaluate(t_new)
        assert np.allclose(pt_orig, pt_new, atol=TOL), (
            f"Geometry mismatch at s={s}: orig={pt_orig}, normalized={pt_new}"
        )


def test_normalize_knots_curve_control_points_unchanged():
    """Control points are copied verbatim, not modified."""
    c = _cubic_curve()
    nc = normalize_knots(c)
    assert np.allclose(nc.control_points, c.control_points, atol=TOL)


def test_normalize_knots_already_normalized_is_idempotent():
    """Calling normalize_knots on an already-[0,1] curve is a no-op."""
    cp = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    knots = np.array([0.0, 0.0, 1.0, 1.0])
    c = NurbsCurve(degree=1, control_points=cp, knots=knots)
    nc = normalize_knots(c)
    assert np.allclose(nc.knots, c.knots, atol=TOL)


# ---------------------------------------------------------------------------
# 3. normalize_knots — surface
# ---------------------------------------------------------------------------

def test_normalize_knots_surface_domain():
    """After normalization both knot vectors span [0, 1]."""
    s = _bilinear_surface()
    ns = normalize_knots(s)
    assert ns.knots_u[0] == pytest.approx(0.0, abs=TOL)
    assert ns.knots_u[-1] == pytest.approx(1.0, abs=TOL)
    assert ns.knots_v[0] == pytest.approx(0.0, abs=TOL)
    assert ns.knots_v[-1] == pytest.approx(1.0, abs=TOL)


def test_normalize_knots_surface_geometry():
    """Points on normalized surface match original at remapped parameters."""
    s = _bilinear_surface()
    ns = normalize_knots(s)
    # map (u_orig, v_orig) -> (u_new, v_new) and compare evaluate
    au = float(s.knots_u[s.degree_u])
    bu = float(s.knots_u[-(s.degree_u + 1)])
    av = float(s.knots_v[s.degree_v])
    bv = float(s.knots_v[-(s.degree_v + 1)])
    for su in np.linspace(0.0, 1.0, 5):
        for sv in np.linspace(0.0, 1.0, 5):
            u_orig = au + su * (bu - au)
            v_orig = av + sv * (bv - av)
            u_new = su
            v_new = sv
            pt_orig = s.evaluate(u_orig, v_orig)
            pt_new = ns.evaluate(u_new, v_new)
            assert np.allclose(pt_orig, pt_new, atol=TOL), (
                f"Surface geometry mismatch at (su={su}, sv={sv})"
            )


def test_normalize_knots_type_error():
    with pytest.raises(TypeError):
        normalize_knots("not a nurbs object")


# ---------------------------------------------------------------------------
# 4. reparametrize_curve — domain rescale
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make_curve", [_line_curve, _cubic_curve])
def test_reparametrize_curve_domain(make_curve):
    """After reparametrization the domain is [t0, t1]."""
    c = make_curve()
    rc = reparametrize_curve(c, t0=0.0, t1=2.0)
    p = rc.degree
    assert rc.knots[p] == pytest.approx(0.0, abs=TOL)
    assert rc.knots[-(p + 1)] == pytest.approx(2.0, abs=TOL)


@pytest.mark.parametrize("make_curve", [_line_curve, _cubic_curve])
def test_reparametrize_curve_geometry_preserved(make_curve):
    """reparametrize_curve to [0, 2] preserves geometry."""
    c = make_curve()
    t0_new, t1_new = 0.0, 2.0
    rc = reparametrize_curve(c, t0=t0_new, t1=t1_new)

    a_orig = float(c.knots[c.degree])
    b_orig = float(c.knots[-(c.degree + 1)])
    p = rc.degree
    a_new = float(rc.knots[p])
    b_new = float(rc.knots[-(p + 1)])

    for s in np.linspace(0.0, 1.0, 13):
        t_orig = a_orig + s * (b_orig - a_orig)
        t_new = a_new + s * (b_new - a_new)
        pt_orig = c.evaluate(t_orig)
        pt_new = rc.evaluate(t_new)
        assert np.allclose(pt_orig, pt_new, atol=TOL), (
            f"Geometry mismatch at s={s}: orig={pt_orig}, reparam={pt_new}"
        )


def test_reparametrize_curve_bad_range():
    c = _line_curve()
    with pytest.raises(ValueError):
        reparametrize_curve(c, t0=1.0, t1=0.0)


def test_reparametrize_curve_default_is_normalize():
    """reparametrize_curve(c) with defaults [0,1] equals normalize_knots."""
    c = _cubic_curve()
    r1 = reparametrize_curve(c, 0.0, 1.0)
    r2 = normalize_knots(c)
    assert np.allclose(r1.knots, r2.knots, atol=TOL)
    assert np.allclose(r1.control_points, r2.control_points, atol=TOL)


# ---------------------------------------------------------------------------
# 5. reparametrize_arclength — arc-length reparam
# ---------------------------------------------------------------------------

def test_reparametrize_arclength_domain():
    """Arc-length-reparametrized curve has domain [0, 1]."""
    c = _cubic_curve()
    ac = reparametrize_arclength(c, n=64)
    p = ac.degree
    assert ac.knots[p] == pytest.approx(0.0, abs=1e-12)
    assert ac.knots[-(p + 1)] == pytest.approx(1.0, abs=1e-12)


def test_reparametrize_arclength_geometry_preserved():
    """Arc-length reparam preserves the point set (start and end points match)."""
    c = _cubic_curve()
    ac = reparametrize_arclength(c, n=64)

    # Start and end points must match within reasonable tolerance
    a_orig = float(c.knots[c.degree])
    b_orig = float(c.knots[-(c.degree + 1)])
    start_orig = c.evaluate(a_orig)
    end_orig = c.evaluate(b_orig)

    p = ac.degree
    start_new = ac.evaluate(float(ac.knots[p]))
    end_new = ac.evaluate(float(ac.knots[-(p + 1)]))

    assert np.allclose(start_orig, start_new, atol=1e-3), (
        f"Start point mismatch: {start_orig} vs {start_new}"
    )
    assert np.allclose(end_orig, end_new, atol=1e-3), (
        f"End point mismatch: {end_orig} vs {end_new}"
    )


def test_reparametrize_arclength_uniform_speed():
    """Uniform arc-length steps should advance the curve at approximately equal distances.

    We sample the re-parametrized curve at equal parameter intervals and verify
    the point-to-point chord lengths are approximately equal (CV <= 0.15).
    """
    c = _cubic_curve()
    ac = reparametrize_arclength(c, n=128)

    # Sample at 33 uniform parameter values in [0, 1]
    p = ac.degree
    t0 = float(ac.knots[p])
    t1 = float(ac.knots[-(p + 1)])
    t_vals = np.linspace(t0, t1, 33)
    pts = np.array([ac.evaluate(t) for t in t_vals])
    dists = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    mean_d = float(np.mean(dists))
    if mean_d > 1e-12:
        cv = float(np.std(dists) / mean_d)
        assert cv < 0.15, (
            f"Arc-length reparam not sufficiently uniform: CV={cv:.4f} "
            f"(expected < 0.15)"
        )


def test_reparametrize_arclength_line_perfect():
    """For a straight line, arc-length reparam should give near-perfect uniformity."""
    # Straight line — speed is already constant so reparam should be almost perfect.
    cp = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    c = NurbsCurve(degree=2, control_points=cp, knots=knots)
    ac = reparametrize_arclength(c, n=64)

    p = ac.degree
    t0 = float(ac.knots[p])
    t1 = float(ac.knots[-(p + 1)])
    t_vals = np.linspace(t0, t1, 17)
    pts = np.array([ac.evaluate(t) for t in t_vals])
    dists = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    mean_d = float(np.mean(dists))
    if mean_d > 1e-12:
        cv = float(np.std(dists) / mean_d)
        assert cv < 0.05, (
            f"Line arc-length reparam has high CV={cv:.4f} (expected < 0.05)"
        )


def test_reparametrize_arclength_returns_nurbs_curve():
    c = _cubic_curve()
    ac = reparametrize_arclength(c, n=32)
    assert isinstance(ac, NurbsCurve)
