"""GK-P15 — analytic surface derivatives + robust SSI.

Two deliverables:

1.  **Analytic derivatives.**  ``surface_derivative`` is the exact analytic
    Cox-de Boor / rational-quotient-rule derivative (Piegl & Tiller A3.6 / A4.4)
    — no finite differences.  These tests pin it against (a) a *closed-form*
    polynomial-Bezier reference whose partials are known by hand (machine
    precision) and (b) a Richardson-extrapolated central difference on a general
    bicubic (agreement < 1e-9 for first AND second partials), the DoD gate.

2.  **Robust SSI.**  ``surface_surface_intersect`` now runs a branch-stitching
    robustness pass (GK-P15) that merges over-seeded fragments of one
    intersection curve.  These tests verify a freeform x plane fixture yields a
    single stitched curve and analytic primitive intersections stay exact
    against their closed-form circle oracles.

Hermetic: pure Python + NumPy.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import (
    NurbsSurface,
    surface_derivative,
    surface_evaluate,
)
from kerf_cad_core.geom.intersection import surface_surface_intersect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _knots(n: int, deg: int) -> np.ndarray:
    inner = max(0, n - deg - 1)
    return np.concatenate([
        np.zeros(deg + 1),
        np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
        np.ones(deg + 1),
    ])


def _bezier_patch(coeffs) -> NurbsSurface:
    """A single bicubic Bezier patch (degree 3x3, 4x4 CPs, [0,1]^2)."""
    cp = np.array(coeffs, dtype=float)
    ku = np.array([0, 0, 0, 0, 1, 1, 1, 1.0])
    return NurbsSurface(degree_u=3, degree_v=3, control_points=cp,
                        knots_u=ku, knots_v=ku.copy())


def _richardson_partial(s, u, v, ku, kv):
    """Richardson-extrapolated central-difference partial (~1e-12 accurate).

    Two central differences at h and h/2, Richardson-combined to cancel the
    leading O(h^2) error, giving a high-accuracy numerical reference that
    beats raw single-h FD roundoff."""
    def _cd(h):
        if (ku, kv) == (1, 0):
            return (surface_evaluate(s, u + h, v)
                    - surface_evaluate(s, u - h, v)) / (2 * h)
        if (ku, kv) == (0, 1):
            return (surface_evaluate(s, u, v + h)
                    - surface_evaluate(s, u, v - h)) / (2 * h)
        if (ku, kv) == (2, 0):
            return (surface_evaluate(s, u + h, v)
                    - 2 * surface_evaluate(s, u, v)
                    + surface_evaluate(s, u - h, v)) / (h * h)
        if (ku, kv) == (0, 2):
            return (surface_evaluate(s, u, v + h)
                    - 2 * surface_evaluate(s, u, v)
                    + surface_evaluate(s, u, v - h)) / (h * h)
        # (1, 1) mixed
        return (surface_evaluate(s, u + h, v + h)
                - surface_evaluate(s, u + h, v - h)
                - surface_evaluate(s, u - h, v + h)
                + surface_evaluate(s, u - h, v - h)) / (4 * h * h)

    # First derivatives tolerate a small h; second derivatives amplify roundoff
    # by 1/h^2, so use a larger base step for them to keep the numerical
    # reference well-conditioned.  Two-level Richardson cancels the O(h^2) term.
    # (Sample points must stay strictly inside one knot span so the FD does not
    # straddle a C2 break at an interior knot.)
    second_order = (ku + kv) >= 2
    h = 4e-3 if second_order else 1e-3
    f_h = _cd(h)
    f_h2 = _cd(h / 2)
    return (4.0 * f_h2 - f_h) / 3.0


# ---------------------------------------------------------------------------
# 1. Analytic derivatives — closed-form reference
# ---------------------------------------------------------------------------


def test_analytic_first_partials_exact_on_polynomial():
    """For S(u,v) = [u, v, u^2 + u*v] expressed as a bicubic Bezier patch the
    partials are S_u = [1,0,2u+v], S_v = [0,1,u] exactly; the analytic
    derivative matches to machine precision."""
    # Build CPs so the patch interpolates z = u^2 + u*v on [0,1]^2.
    cp = np.zeros((4, 4, 3))
    uu = np.linspace(0, 1, 4)
    vv = np.linspace(0, 1, 4)
    # Use the Greville-grid trick: for a Bezier patch we instead set CPs from
    # the exact bilinear/quadratic control net of z = u^2 + u*v.
    # z(u,v)=u^2+u*v.  In Bernstein form the cubic CP heights along u for the
    # u^2 term are [0,0,1/3,1]; for the u*v cross term we set per-(i,j).
    for i in range(4):
        for j in range(4):
            cp[i, j, 0] = i / 3.0
            cp[i, j, 1] = j / 3.0
    # z control net for cubic-cubic Bezier of u^2 + u*v:
    #   u^2 (cubic Bernstein control values): [0, 0, 1/3, 1]
    #   u*v (bilinear, degree-elevated to cubic): control = u_i * v_j with
    #       u_i,v_j the cubic Bernstein abscissae [0,1/3,2/3,1].
    u2_net = np.array([0.0, 0.0, 1.0 / 3.0, 1.0])
    lin = np.array([0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0])
    for i in range(4):
        for j in range(4):
            cp[i, j, 2] = u2_net[i] + lin[i] * lin[j]
    s = _bezier_patch(cp)

    for (u, v) in [(0.2, 0.3), (0.5, 0.5), (0.8, 0.15), (0.95, 0.9)]:
        su = surface_derivative(s, u, v, 1, 0)[:3]
        sv = surface_derivative(s, u, v, 0, 1)[:3]
        assert np.allclose(su, [1.0, 0.0, 2 * u + v], atol=1e-9), (u, v, su)
        assert np.allclose(sv, [0.0, 1.0, u], atol=1e-9), (u, v, sv)
        # Second partials: S_uu=[0,0,2], S_uv=[0,0,1], S_vv=[0,0,0].
        suu = surface_derivative(s, u, v, 2, 0)[:3]
        suv = surface_derivative(s, u, v, 1, 1)[:3]
        svv = surface_derivative(s, u, v, 0, 2)[:3]
        assert np.allclose(suu, [0.0, 0.0, 2.0], atol=1e-9), (u, v, suu)
        assert np.allclose(suv, [0.0, 0.0, 1.0], atol=1e-9), (u, v, suv)
        assert np.allclose(svv, [0.0, 0.0, 0.0], atol=1e-9), (u, v, svv)


def test_analytic_vs_richardson_fd_below_1e9():
    """DoD: analytic first AND second partials agree with a high-accuracy
    (Richardson-extrapolated) finite difference to < 1e-9 on a general
    bicubic surface."""
    nu, nv = 6, 5
    ku, kv = _knots(nu, 3), _knots(nv, 3)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            x, y = i / (nu - 1), j / (nv - 1)
            cp[i, j] = [x, y, 0.4 * x ** 3 - 0.3 * x * y + 0.2 * y ** 2]
    s = NurbsSurface(degree_u=3, degree_v=3, control_points=cp,
                     knots_u=ku, knots_v=kv)

    # Sample strictly inside knot spans (avoid interior knots u,v=0.5 where the
    # second derivative has a legitimate C2 break that no FD can reference).
    for (u, v) in [(0.37, 0.61), (0.23, 0.18), (0.71, 0.83)]:
        for (kU, kV) in [(1, 0), (0, 1), (2, 0), (1, 1), (0, 2)]:
            ana = surface_derivative(s, u, v, kU, kV)[:3]
            ref = _richardson_partial(s, u, v, kU, kV)[:3]
            err = float(np.max(np.abs(ana - ref)))
            assert err < 1e-9, f"({kU},{kV}) at ({u},{v}): err {err}"


def test_analytic_rational_sphere_normal_exact():
    """Analytic first partials on an exact rational NURBS sphere give the exact
    radial unit normal (rational-correct path)."""
    import sys
    sys.path.insert(0, "tests")
    from test_ssi_robust import make_rational_sphere
    sph = make_rational_sphere([0.0, 0.0, 0.0], 2.0)
    for (u, v) in [(0.3, 0.4), (0.6, 0.55), (0.85, 0.2)]:
        su = surface_derivative(sph, u, v, 1, 0)[:3]
        sv = surface_derivative(sph, u, v, 0, 1)[:3]
        P = surface_evaluate(sph, u, v)[:3]
        n = np.cross(su, sv)
        n = n / (np.linalg.norm(n) + 1e-300)
        radial = P / (np.linalg.norm(P) + 1e-300)
        # Normal is parallel (or anti-parallel) to the radius vector.
        assert abs(abs(float(np.dot(n, radial))) - 1.0) < 1e-7, (u, v)


# ---------------------------------------------------------------------------
# 2. Robust SSI — branch stitching + analytic-oracle parity
# ---------------------------------------------------------------------------


def test_ssi_freeform_plane_single_stitched_curve():
    """A bicubic bump sliced by a tilted plane yields a single connected
    intersection curve after the GK-P15 stitching pass (no fragmentation)."""
    nu = nv = 6
    ku = kv = _knots(6, 3)
    cp = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            x, y = i / (nu - 1), j / (nv - 1)
            cp[i, j] = [x, y, 0.25 * x * x]   # monotone bump → one crossing
    A = NurbsSurface(3, 3, cp, ku, kv)
    pk = _knots(2, 1)
    pcp = np.zeros((2, 2, 3))
    for i in range(2):
        for j in range(2):
            pcp[i, j] = [i * 1.0, j * 1.0, 0.06 + 0.02 * i]
    B = NurbsSurface(1, 1, pcp, pk, pk.copy())
    r = surface_surface_intersect(A, B, tol=1e-7)
    assert r["ok"], r["reason"]
    assert r["branch_count"] == 1, (
        f"expected one stitched curve, got {r['branch_count']}"
    )
    assert len(r["branches"][0]["points"]) >= 4


def test_ssi_stitch_helper_joins_split_polyline():
    """The stitching helper merges two open halves of one curve into one."""
    from kerf_cad_core.geom.intersection import _stitch_branches
    # Two halves of a straight segment, sharing the midpoint (0.5,0,0).
    left = {"points": [[0, 0, 0], [0.25, 0, 0], [0.5, 0, 0]],
            "params_a": [[0, 0]] * 3, "params_b": [[0, 0]] * 3, "closed": False}
    right = {"points": [[0.5, 0, 0], [0.75, 0, 0], [1.0, 0, 0]],
             "params_a": [[0, 0]] * 3, "params_b": [[0, 0]] * 3, "closed": False}
    out = _stitch_branches([left, right], step=0.1)
    assert len(out) == 1
    pts = out[0]["points"]
    assert len(pts) == 5
    assert np.allclose(pts[0], [0, 0, 0])
    assert np.allclose(pts[-1], [1.0, 0, 0])


def test_ssi_analytic_sphere_plane_circle_oracle():
    """Plane ∩ sphere is a circle whose radius matches the closed-form oracle
    (the analytic SSI path must survive the stitching pass unchanged)."""
    import sys
    sys.path.insert(0, "tests")
    from test_ssi_robust import make_rational_sphere
    R = 2.0
    sph = make_rational_sphere([0.0, 0.0, 0.0], R)
    # Horizontal plane at z = d → circle radius sqrt(R^2 - d^2).
    d = 1.0
    pk = _knots(2, 1)
    pcp = np.zeros((2, 2, 3))
    span = 3.0
    for i in range(2):
        for j in range(2):
            pcp[i, j] = [(i - 0.5) * 2 * span, (j - 0.5) * 2 * span, d]
    plane = NurbsSurface(1, 1, pcp, pk, pk.copy())
    r = surface_surface_intersect(sph, plane, tol=1e-7)
    assert r["ok"], r["reason"]
    assert r["branch_count"] >= 1
    pts = np.array(r["branches"][0]["points"])
    radii = np.linalg.norm(pts[:, :2], axis=1)  # distance from z-axis
    expected = math.sqrt(R * R - d * d)
    assert abs(float(np.mean(radii)) - expected) < 1e-4, (
        f"circle radius {np.mean(radii)} != oracle {expected}"
    )
    # All points lie at z = d.
    assert np.allclose(pts[:, 2], d, atol=1e-4)
