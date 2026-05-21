"""GK-96: Reverse curve / reverse surface direction — hermetic pytest oracle.

Oracles
-------
1. reverse_curve(reverse_curve(c)) == c  (double-reverse is identity)
2. reversed_curve.evaluate(t) == original_curve.evaluate(a + b - t)  for t in domain
3. reverse_surface(reverse_surface(s, d), d) == s  (double-reverse is identity)
4. reversed_surface.evaluate(u, v) == original_surface.evaluate(1-u, v)  (u-reverse)
5. reversed_surface.evaluate(u, v) == original_surface.evaluate(u, 1-v)  (v-reverse)
6. Public façade exports reverse_curve and reverse_surface.
"""

from __future__ import annotations

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import (
    NurbsCurve,
    NurbsSurface,
    reverse_curve,
    reverse_surface,
)
import kerf_cad_core.geom as _geom_pkg


TOL = 1e-12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_curve() -> NurbsCurve:
    """Degree-1 curve from (0,0,0) to (1,1,0), domain [0,1]."""
    cp = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]])
    knots = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsCurve(degree=1, control_points=cp, knots=knots)


def _cubic_curve() -> NurbsCurve:
    """Degree-3 B-spline with 5 control points, domain [0,1]."""
    cp = np.array([
        [0.0, 0.0, 0.0],
        [0.25, 1.0, 0.0],
        [0.5, 0.5, 1.0],
        [0.75, 1.0, 0.0],
        [1.0, 0.0, 0.0],
    ])
    knots = np.array([0.0, 0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0, 1.0])
    return NurbsCurve(degree=3, control_points=cp, knots=knots)


def _bilinear_surface() -> NurbsSurface:
    """Degree-1 x degree-1 surface over [0,1]x[0,1]."""
    cp = np.array([
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [[1.0, 0.0, 0.5], [1.0, 1.0, 0.5]],
    ])
    knots_u = np.array([0.0, 0.0, 1.0, 1.0])
    knots_v = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsSurface(degree_u=1, degree_v=1,
                        control_points=cp, knots_u=knots_u, knots_v=knots_v)


def _biquadratic_surface() -> NurbsSurface:
    """Degree-2 x degree-2 surface with 3x3 CPs, domain [0,1]x[0,1]."""
    cp = np.zeros((3, 3, 3))
    for i in range(3):
        for j in range(3):
            cp[i, j] = [i * 0.5, j * 0.5, float(i + j) * 0.1]
    knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    return NurbsSurface(degree_u=2, degree_v=2,
                        control_points=cp,
                        knots_u=knots.copy(), knots_v=knots.copy())


# ---------------------------------------------------------------------------
# Public export check
# ---------------------------------------------------------------------------

def test_public_exports():
    assert hasattr(_geom_pkg, "reverse_curve"), "reverse_curve missing from geom façade"
    assert hasattr(_geom_pkg, "reverse_surface"), "reverse_surface missing from geom façade"
    assert _geom_pkg.reverse_curve is reverse_curve
    assert _geom_pkg.reverse_surface is reverse_surface


# ---------------------------------------------------------------------------
# reverse_curve: double-reverse identity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make_curve", [_line_curve, _cubic_curve])
def test_reverse_curve_double_reverse_identity(make_curve):
    c = make_curve()
    rr = reverse_curve(reverse_curve(c))
    assert np.allclose(rr.knots, c.knots, atol=TOL), "knots differ after double reverse"
    assert np.allclose(rr.control_points, c.control_points, atol=TOL), "CPs differ after double reverse"


# ---------------------------------------------------------------------------
# reverse_curve: evaluate(reversed, t) == evaluate(orig, a+b-t)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make_curve", [_line_curve, _cubic_curve])
def test_reverse_curve_evaluate_oracle(make_curve):
    c = make_curve()
    rc = reverse_curve(c)
    a = c.knots[0]
    b = c.knots[-1]
    for t in np.linspace(a, b, 15):
        pt_rev = rc.evaluate(t)
        pt_orig = c.evaluate(a + b - t)
        assert np.allclose(pt_rev, pt_orig, atol=TOL), (
            f"evaluate mismatch at t={t}: reversed={pt_rev}, orig_mirror={pt_orig}"
        )


# ---------------------------------------------------------------------------
# reverse_curve: weights are handled correctly
# ---------------------------------------------------------------------------

def test_reverse_curve_rational():
    """Circle arc (rational): reverse preserves geometry."""
    c = _cubic_curve()
    # Give it non-trivial weights.
    weights = np.array([1.0, 0.5, 1.0, 0.5, 1.0])
    c_rat = NurbsCurve(degree=c.degree, control_points=c.control_points.copy(),
                       knots=c.knots.copy(), weights=weights)
    rc = reverse_curve(c_rat)
    a, b = c_rat.knots[0], c_rat.knots[-1]
    for t in np.linspace(a, b, 11):
        assert np.allclose(rc.evaluate(t), c_rat.evaluate(a + b - t), atol=1e-10)

    # Double-reverse identity for rational.
    rrc = reverse_curve(rc)
    assert np.allclose(rrc.control_points, c_rat.control_points, atol=TOL)
    assert np.allclose(rrc.weights, c_rat.weights, atol=TOL)


# ---------------------------------------------------------------------------
# reverse_surface: double-reverse identity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("direction", ["u", "v"])
@pytest.mark.parametrize("make_surf", [_bilinear_surface, _biquadratic_surface])
def test_reverse_surface_double_reverse_identity(make_surf, direction):
    s = make_surf()
    rrs = reverse_surface(reverse_surface(s, direction), direction)
    assert np.allclose(rrs.control_points, s.control_points, atol=TOL)
    assert np.allclose(rrs.knots_u, s.knots_u, atol=TOL)
    assert np.allclose(rrs.knots_v, s.knots_v, atol=TOL)


# ---------------------------------------------------------------------------
# reverse_surface u: evaluate(reversed, u, v) == evaluate(orig, a+b-u, v)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make_surf", [_bilinear_surface, _biquadratic_surface])
def test_reverse_surface_u_evaluate_oracle(make_surf):
    s = make_surf()
    rs = reverse_surface(s, direction='u')
    a_u = s.knots_u[0]
    b_u = s.knots_u[-1]
    a_v = s.knots_v[0]
    b_v = s.knots_v[-1]
    for u in np.linspace(a_u, b_u, 7):
        for v in np.linspace(a_v, b_v, 7):
            pt_rev = rs.evaluate(u, v)
            pt_orig = s.evaluate(a_u + b_u - u, v)
            assert np.allclose(pt_rev, pt_orig, atol=TOL), (
                f"u-reverse mismatch at (u={u}, v={v})"
            )


# ---------------------------------------------------------------------------
# reverse_surface v: evaluate(reversed, u, v) == evaluate(orig, u, a+b-v)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make_surf", [_bilinear_surface, _biquadratic_surface])
def test_reverse_surface_v_evaluate_oracle(make_surf):
    s = make_surf()
    rs = reverse_surface(s, direction='v')
    a_u = s.knots_u[0]
    b_u = s.knots_u[-1]
    a_v = s.knots_v[0]
    b_v = s.knots_v[-1]
    for u in np.linspace(a_u, b_u, 7):
        for v in np.linspace(a_v, b_v, 7):
            pt_rev = rs.evaluate(u, v)
            pt_orig = s.evaluate(u, a_v + b_v - v)
            assert np.allclose(pt_rev, pt_orig, atol=TOL), (
                f"v-reverse mismatch at (u={u}, v={v})"
            )


# ---------------------------------------------------------------------------
# reverse_surface: bad direction raises
# ---------------------------------------------------------------------------

def test_reverse_surface_bad_direction():
    s = _bilinear_surface()
    with pytest.raises(ValueError):
        reverse_surface(s, direction='w')
