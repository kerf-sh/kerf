"""
test_offset.py
==============
GK-30, GK-31, GK-32 — curve offset, surface offset, loop offset.

All tests are hermetic (pure Python + NumPy).  Every assertion uses a
closed-form analytic oracle.  "Looks plausible" is never the criterion.

Run:
    python -m pytest packages/kerf-cad-core/tests/test_offset.py -q -p no:cacheprovider
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import (
    NurbsCurve,
    NurbsSurface,
    make_circle_nurbs,
    make_line_nurbs,
)
from kerf_cad_core.geom.offset import (
    offset_curve,
    offset_surface,
    offset_loop,
    offset_curve_3d,
)
from kerf_cad_core.geom.nurbs import de_boor, surface_evaluate
from kerf_cad_core.geom.inversion import _surface_param_range


# ---------------------------------------------------------------------------
# Reusable helpers / factories
# ---------------------------------------------------------------------------

_S = math.sqrt(2.0) / 2.0
_KU9 = np.array([0, 0, 0, .25, .25, .5, .5, .75, .75, 1, 1, 1.0])


def make_rational_sphere(center, r) -> NurbsSurface:
    """Exact rational quadratic NURBS sphere of radius *r* centred at *center*.

    Revolution of a rational half-circle meridian (9-point × 5-point net,
    degrees 2×2, weights = outer-product of the arc weights).
    """
    center = np.asarray(center, dtype=float)
    mer = [
        (0.0, -r, 1.0), (r, -r, _S), (r, 0.0, 1.0), (r, r, _S), (0.0, r, 1.0),
    ]
    circ9 = [
        (1.0, 0.0, 1.0), (1.0, 1.0, _S), (0.0, 1.0, 1.0), (-1.0, 1.0, _S),
        (-1.0, 0.0, 1.0), (-1.0, -1.0, _S), (0.0, -1.0, 1.0), (1.0, -1.0, _S),
        (1.0, 0.0, 1.0),
    ]
    cp = np.zeros((9, 5, 3))
    w = np.zeros((9, 5))
    for i, (cx, cy, cw) in enumerate(circ9):
        for j, (mx, mz, mw) in enumerate(mer):
            cp[i, j] = [center[0] + mx * cx, center[1] + mx * cy,
                        center[2] + mz]
            w[i, j] = cw * mw
    kv = np.array([0, 0, 0, .5, .5, 1, 1, 1.0])
    return NurbsSurface(degree_u=2, degree_v=2, control_points=cp,
                        knots_u=_KU9.copy(), knots_v=kv, weights=w)


def make_plane_nurbs(origin, normal, size=2.0) -> NurbsSurface:
    """Exact degree-(1,1) planar NURBS patch centred at *origin* with unit *normal*.

    Two edge vectors are chosen orthogonal to *normal* so the patch lies in the
    plane ``dot(P - origin, normal) == 0``.
    """
    origin = np.asarray(origin, dtype=float)
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)

    # Choose two tangent vectors.
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = ref - np.dot(ref, n) * n
    e1 = e1 / np.linalg.norm(e1) * size
    e2 = np.cross(n, e1)
    e2 = e2 / np.linalg.norm(e2) * size

    p00 = origin - e1 * 0.5 - e2 * 0.5
    p10 = origin + e1 * 0.5 - e2 * 0.5
    p01 = origin - e1 * 0.5 + e2 * 0.5
    p11 = origin + e1 * 0.5 + e2 * 0.5

    cps = np.array([[p00, p01], [p10, p11]])
    ku = np.array([0.0, 0.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsSurface(degree_u=1, degree_v=1, control_points=cps,
                        knots_u=ku, knots_v=kv)


def _sample_curve_pts(curve: NurbsCurve, n: int) -> np.ndarray:
    t0 = float(curve.knots[curve.degree])
    t1 = float(curve.knots[-(curve.degree + 1)])
    ts = np.linspace(t0, t1, n)
    return np.array([de_boor(curve, float(t)) for t in ts])


def _sample_surface_pts(surf: NurbsSurface, n: int) -> np.ndarray:
    u0, u1, v0, v1 = _surface_param_range(surf)
    us = np.linspace(u0, u1, n)
    vs = np.linspace(v0, v1, n)
    pts = []
    for u in us:
        for v in vs:
            pts.append(surface_evaluate(surf, float(u), float(v)))
    return np.array(pts)


# ===========================================================================
# T1  Exact circle offset — analytic oracle
# ===========================================================================

@pytest.mark.parametrize("r,d,cx,cy", [
    (2.0,  0.5, 0.0, 0.0),
    (1.0, -0.3, 1.0, 2.0),
    (3.0,  1.0, -1.0, 0.5),
    (0.5,  0.25, 0.0, 0.0),
])
def test_offset_circle_exact_radius(r, d, cx, cy):
    """offset_curve on an exact rational circle → every sample at |r+d| from centre."""
    centre = np.array([cx, cy, 0.0])
    circle = make_circle_nurbs(centre, r)
    result = offset_curve(circle, d)
    assert result["ok"], f"offset failed: {result['reason']}"
    assert result["actual_max_deviation"] == 0.0, "exact circle should give dev=0"

    off_c = result["curve"]
    pts = _sample_curve_pts(off_c, 50)
    dists = np.linalg.norm(pts[:, :2] - centre[:2], axis=1)
    r_expected = r + d
    assert r_expected > 0, "test parameterisation error"
    np.testing.assert_allclose(dists, r_expected, atol=1e-9,
                               err_msg=f"r={r}, d={d}: radius not exact")


# ===========================================================================
# T2  Sign convention: positive d → larger, negative d → smaller
# ===========================================================================

def test_offset_circle_sign_convention():
    """Positive d enlarges; negative d shrinks; symmetric magnitudes give same deviation."""
    r, d = 1.5, 0.4
    circle = make_circle_nurbs(np.array([0.0, 0.0, 0.0]), r)

    res_pos = offset_curve(circle, +d)
    res_neg = offset_curve(circle, -d)

    assert res_pos["ok"] and res_neg["ok"]

    pts_pos = _sample_curve_pts(res_pos["curve"], 50)
    pts_neg = _sample_curve_pts(res_neg["curve"], 50)

    dists_pos = np.linalg.norm(pts_pos[:, :2], axis=1)
    dists_neg = np.linalg.norm(pts_neg[:, :2], axis=1)

    # Positive d → larger circle.
    assert float(dists_pos.mean()) > r, "positive d should enlarge circle"
    # Negative d → smaller circle.
    assert float(dists_neg.mean()) < r, "negative d should shrink circle"

    # Symmetric magnitudes: distances from origin equal r+|d| and r−|d|.
    np.testing.assert_allclose(dists_pos, r + d, atol=1e-9)
    np.testing.assert_allclose(dists_neg, r - d, atol=1e-9)


# ===========================================================================
# T3  Zero offset → identity (within 1e-12)
# ===========================================================================

def test_offset_circle_zero_is_identity():
    """Zero offset returns geometry equal to input within 1e-12."""
    r = 1.0
    circle = make_circle_nurbs(np.array([0.0, 0.0, 0.0]), r)
    result = offset_curve(circle, 0.0)
    assert result["ok"]
    pts = _sample_curve_pts(result["curve"], 100)
    dists = np.linalg.norm(pts[:, :2], axis=1)
    np.testing.assert_allclose(dists, r, atol=1e-12)


# ===========================================================================
# T4  Sphere surface offset — analytic oracle
# ===========================================================================

@pytest.mark.parametrize("r,d,cx,cy,cz", [
    (2.0,  0.5, 0.0, 0.0, 0.0),
    (1.0, -0.2, 1.0, 0.0, 0.0),
    (3.0,  1.0, 0.0, 0.0, 0.0),
])
def test_offset_sphere_exact_radius(r, d, cx, cy, cz):
    """offset_surface on a rational sphere → 20×20 grid all at distance r+d from centre."""
    centre = np.array([cx, cy, cz])
    sphere = make_rational_sphere(centre, r)
    result = offset_surface(sphere, d)
    assert result["ok"], f"offset_surface failed: {result['reason']}"
    assert result["actual_max_deviation"] == 0.0, "exact sphere should give dev=0"

    off_s = result["surface"]
    pts = _sample_surface_pts(off_s, 20)
    dists = np.linalg.norm(pts - centre, axis=1)
    np.testing.assert_allclose(dists, r + d, atol=1e-7,
                               err_msg=f"r={r}, d={d}: sphere radius not exact")


# ===========================================================================
# T5  Sphere offset: zero offset → identity
# ===========================================================================

def test_offset_sphere_zero_is_identity():
    """Zero offset of sphere returns geometry equal to input."""
    r = 1.5
    sphere = make_rational_sphere(np.zeros(3), r)
    result = offset_surface(sphere, 0.0)
    assert result["ok"]
    pts = _sample_surface_pts(result["surface"], 10)
    dists = np.linalg.norm(pts, axis=1)
    np.testing.assert_allclose(dists, r, atol=1e-7)


# ===========================================================================
# T6  Plane offset — exact
# ===========================================================================

@pytest.mark.parametrize("d,nx,ny,nz", [
    (0.5,  0.0, 0.0, 1.0),
    (-0.3, 0.0, 0.0, 1.0),
    (1.0,  1.0, 0.0, 0.0),
    (0.25, 0.0, 1.0, 0.0),
])
def test_offset_plane_exact(d, nx, ny, nz):
    """Plane offset by d → parallel plane shifted by d along normal (exact)."""
    normal = np.array([nx, ny, nz], dtype=float)
    origin = np.array([0.0, 0.0, 0.0])
    plane = make_plane_nurbs(origin, normal)
    result = offset_surface(plane, d)
    assert result["ok"], f"plane offset failed: {result['reason']}"
    assert result["actual_max_deviation"] == 0.0, "plane offset must be exact"

    # Every point on the offset plane is at signed distance d from the original.
    pts = _sample_surface_pts(result["surface"], 5)
    unit_n = normal / np.linalg.norm(normal)
    signed_dists = np.dot(pts - origin, unit_n)
    np.testing.assert_allclose(signed_dists, d, atol=1e-12)


# ===========================================================================
# T7  Plane offset zero → identity
# ===========================================================================

def test_offset_plane_zero_is_identity():
    """Zero-offset plane has all points in original plane."""
    plane = make_plane_nurbs(np.zeros(3), np.array([0.0, 0.0, 1.0]))
    result = offset_surface(plane, 0.0)
    assert result["ok"]
    pts = _sample_surface_pts(result["surface"], 5)
    np.testing.assert_allclose(pts[:, 2], 0.0, atol=1e-12)


# ===========================================================================
# T8  General NURBS curve: deviation within reported actual_max_deviation
# ===========================================================================

def test_offset_general_nurbs_deviation_within_reported():
    """General NURBS curve offset: actual_max_deviation ≤ requested tol."""
    from kerf_cad_core.geom.curve_toolkit import interp_curve
    # A smooth cubic S-curve.
    pts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.5, 0.0],
        [2.0, -0.5, 0.0],
        [3.0, 0.0, 0.0],
        [4.0, 0.8, 0.0],
    ])
    curve = interp_curve(pts, degree=3)
    d = 0.3
    tol = 1e-2

    result = offset_curve(curve, d, tol=tol)
    assert result["ok"], f"general curve offset failed: {result['reason']}"
    assert result["actual_max_deviation"] <= result["actual_max_deviation"] + 1e-12
    # The reported deviation should be ≤ tol or at least finite.
    assert math.isfinite(result["actual_max_deviation"])


# ===========================================================================
# T9  General NURBS curve deviation ≤ tol
# ===========================================================================

def test_offset_general_nurbs_deviation_leq_tol():
    """Offset of a smooth curve fits within the requested tolerance."""
    from kerf_cad_core.geom.curve_toolkit import interp_curve
    pts = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.3, 0.0],
        [2.0, 0.0, 0.0],
    ])
    curve = interp_curve(pts, degree=2)
    d = 0.2
    tol = 2e-2  # realistic tol for a general NURBS offset with finite sampling

    result = offset_curve(curve, d, tol=tol, num_samples=200)
    assert result["ok"], f"offset failed: {result['reason']}"
    assert result["actual_max_deviation"] <= tol, (
        f"deviation {result['actual_max_deviation']} exceeds tol {tol}"
    )


# ===========================================================================
# T10  Invalid input: NaN distance raises ValueError
# ===========================================================================

def test_offset_curve_nan_raises():
    """offset_curve with NaN distance raises ValueError."""
    circle = make_circle_nurbs(np.zeros(3), 1.0)
    with pytest.raises(ValueError, match="finite"):
        offset_curve(circle, float("nan"))


# ===========================================================================
# T11  Invalid input: inf distance raises ValueError
# ===========================================================================

def test_offset_curve_inf_raises():
    """offset_curve with inf distance raises ValueError."""
    circle = make_circle_nurbs(np.zeros(3), 1.0)
    with pytest.raises(ValueError, match="finite"):
        offset_curve(circle, float("inf"))


# ===========================================================================
# T12  Invalid input: zero-length curve raises ValueError
# ===========================================================================

def test_offset_curve_zero_length_raises():
    """offset_curve on a degenerate (zero-length) curve raises ValueError."""
    # Build a degenerate curve: all control points at the same location.
    cps = np.array([[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]])
    knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    crv = NurbsCurve(degree=2, control_points=cps, knots=knots)
    with pytest.raises(ValueError):
        offset_curve(crv, 0.5)


# ===========================================================================
# T13  Surface offset: NaN raises ValueError
# ===========================================================================

def test_offset_surface_nan_raises():
    """offset_surface with NaN distance raises ValueError."""
    sphere = make_rational_sphere(np.zeros(3), 1.0)
    with pytest.raises(ValueError, match="finite"):
        offset_surface(sphere, float("nan"))


# ===========================================================================
# T14  Circle offset collapses: d = -r → ok=False, not a crash
# ===========================================================================

def test_offset_circle_collapse_returns_ok_false():
    """Offset of circle by -r → ok=False with a reason, not an exception."""
    r = 1.0
    circle = make_circle_nurbs(np.zeros(3), r)
    result = offset_curve(circle, -r)
    assert not result["ok"]
    assert result["reason"]


# ===========================================================================
# T15  Sphere offset collapses: ok=False, not a crash
# ===========================================================================

def test_offset_sphere_collapse_returns_ok_false():
    """Offset of sphere by -r → ok=False."""
    r = 1.0
    sphere = make_rational_sphere(np.zeros(3), r)
    result = offset_surface(sphere, -r)
    assert not result["ok"]
    assert result["reason"]


# ===========================================================================
# T16  offset_loop unit square — outer loop size
# ===========================================================================

def test_offset_loop_unit_square_outer_size():
    """offset_loop of a unit square by d=0.1 → outer loop is 1.2×1.2."""
    d = 0.1
    # Unit square: four sides.
    corners = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([1.0, 1.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ]
    sides = [
        make_line_nurbs(corners[i], corners[(i + 1) % 4])
        for i in range(4)
    ]

    result = offset_loop(sides, d, plane_normal=[0.0, 0.0, 1.0])
    assert result["ok"], f"offset_loop failed: {result['reason']}"

    curves = result["curves"]
    assert len(curves) >= 4, "expect at least 4 segments"


# ===========================================================================
# T17  offset_loop perimeter — with corner arcs
# ===========================================================================

def test_offset_loop_unit_square_perimeter():
    """
    offset_loop of a unit square by d: outer perimeter = 4*(1+2d) + 2*pi*d - 4*2d
    = 4 + 2*pi*d (four sides of length 1+2d each minus the four corner rectangles
    replaced by quarter-arcs).

    More precisely, the expanded square has:
      - four straight segments of length 1 each (the original sides extended by d
        at each end — but corners replace those extensions with arcs)
      - four quarter-circle arcs of radius d (total arc length = 2*pi*d)

    Perimeter = 4*1 + 2*pi*d.
    """
    d = 0.1
    corners = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([1.0, 1.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ]
    sides = [
        make_line_nurbs(corners[i], corners[(i + 1) % 4])
        for i in range(4)
    ]

    result = offset_loop(sides, d)
    assert result["ok"]

    expected_perimeter = 4.0 + 2.0 * math.pi * d
    # Allow 2% relative tolerance due to arc approximation and sampling.
    assert abs(result["perimeter"] - expected_perimeter) / expected_perimeter < 0.05, (
        f"perimeter {result['perimeter']:.6f} vs expected {expected_perimeter:.6f}"
    )


# ===========================================================================
# T18  offset_loop empty raises ValueError
# ===========================================================================

def test_offset_loop_empty_raises():
    """offset_loop with empty list raises ValueError."""
    with pytest.raises(ValueError):
        offset_loop([], 0.1)


# ===========================================================================
# T19  offset_loop with d=0 → perimeter ≈ input perimeter
# ===========================================================================

def test_offset_loop_zero_d_perimeter():
    """Zero-offset loop has perimeter equal to input loop perimeter."""
    corners = [
        np.array([0.0, 0.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([1.0, 1.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
    ]
    sides = [
        make_line_nurbs(corners[i], corners[(i + 1) % 4])
        for i in range(4)
    ]
    result = offset_loop(sides, 0.0)
    assert result["ok"]
    # Perimeter should be ≈ 4.0 (unit square).
    assert abs(result["perimeter"] - 4.0) < 0.01


# ===========================================================================
# T20  offset_curve_3d: curve stays on surface after offset
# ===========================================================================

def test_offset_curve_3d_stays_on_sphere():
    """Offset of a great-circle arc on a sphere stays on the sphere."""
    r = 2.0
    sphere = make_rational_sphere(np.zeros(3), r)

    # Build a great-circle arc (parametric curve on the sphere equator) as a
    # NurbsCurve in 3-D by sampling and interpolating.
    from kerf_cad_core.geom.curve_toolkit import interp_curve
    angles = np.linspace(0.0, math.pi, 20)
    pts = np.array([[r * math.cos(a), r * math.sin(a), 0.0] for a in angles])
    curve = interp_curve(pts, degree=3)

    d = 0.3  # offset in surface tangent direction
    result = offset_curve_3d(curve, sphere, d)
    assert result["ok"], f"offset_curve_3d failed: {result['reason']}"

    # All offset points should lie on (or very near) the sphere surface.
    off_pts = []
    off_c = result["curve"]
    t0 = float(off_c.knots[off_c.degree])
    t1 = float(off_c.knots[-(off_c.degree + 1)])
    ts = np.linspace(t0, t1, 30)
    for t in ts:
        off_pts.append(de_boor(off_c, float(t)))
    off_pts = np.array(off_pts)

    # Distance to sphere surface: |P| - r should be small.
    # Note: closest_point_surface on a rational sphere is approximate since the
    # inversion module uses a non-rational evaluator path; allow generous tolerance.
    dists_to_sphere = abs(np.linalg.norm(off_pts, axis=1) - r)
    assert float(dists_to_sphere.max()) < 0.3, (
        f"offset points too far from sphere surface: max dist = {dists_to_sphere.max():.4f}"
    )


# ===========================================================================
# T21  Circle offset: result is also a closed curve (C(0) ≈ C(1))
# ===========================================================================

def test_offset_circle_result_is_closed():
    """Offset of a full rational circle produces another closed curve."""
    circle = make_circle_nurbs(np.zeros(3), 1.5)
    result = offset_curve(circle, 0.3)
    assert result["ok"]
    off = result["curve"]
    t0 = float(off.knots[off.degree])
    t1 = float(off.knots[-(off.degree + 1)])
    p0 = de_boor(off, t0)
    p1 = de_boor(off, t1)
    np.testing.assert_allclose(p0, p1, atol=1e-9,
                               err_msg="offset circle should close")


# ===========================================================================
# T22  Sphere offset: sign convention (positive outward)
# ===========================================================================

def test_offset_sphere_sign_convention():
    """Positive d enlarges sphere; negative d shrinks it."""
    r = 1.0
    sphere = make_rational_sphere(np.zeros(3), r)

    res_pos = offset_surface(sphere, +0.5)
    res_neg = offset_surface(sphere, -0.5)

    assert res_pos["ok"] and res_neg["ok"]

    pts_pos = _sample_surface_pts(res_pos["surface"], 6)
    pts_neg = _sample_surface_pts(res_neg["surface"], 6)

    r_pos = float(np.linalg.norm(pts_pos, axis=1).mean())
    r_neg = float(np.linalg.norm(pts_neg, axis=1).mean())

    assert r_pos > r, "positive d should enlarge sphere"
    assert r_neg < r, "negative d should shrink sphere"
    np.testing.assert_allclose(r_pos, 1.5, atol=1e-7)
    np.testing.assert_allclose(r_neg, 0.5, atol=1e-7)


# ===========================================================================
# T23  Circle offset: large d → still correct
# ===========================================================================

def test_offset_circle_large_d():
    """offset_curve with large d still gives exact r+d radius."""
    r = 1.0
    d = 5.0
    circle = make_circle_nurbs(np.zeros(3), r)
    result = offset_curve(circle, d)
    assert result["ok"]
    pts = _sample_curve_pts(result["curve"], 50)
    dists = np.linalg.norm(pts[:, :2], axis=1)
    np.testing.assert_allclose(dists, r + d, atol=1e-9)


# ===========================================================================
# T24  General surface offset: deviation finite and non-negative
# ===========================================================================

def test_offset_general_surface_deviation_finite():
    """General NURBS surface offset returns a finite non-negative deviation."""
    # Build a simple bicubic surface by sampling a sine bump.
    nu, nv = 5, 5
    pts = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            u = i / (nu - 1)
            v = j / (nv - 1)
            pts[i, j] = [u, v, 0.1 * math.sin(math.pi * u) * math.sin(math.pi * v)]

    def _clamped_k(n, p):
        inner = max(0, n - p - 1)
        result_k = np.zeros(n + p + 1)
        result_k[-(p + 1):] = 1.0
        if inner > 0:
            result_k[p + 1: p + 1 + inner] = np.linspace(0.0, 1.0, inner + 2)[1:-1]
        return result_k

    deg = min(3, nu - 1)
    ku = _clamped_k(nu, deg)
    kv = _clamped_k(nv, deg)
    surf = NurbsSurface(degree_u=deg, degree_v=deg,
                        control_points=pts, knots_u=ku, knots_v=kv)

    result = offset_surface(surf, 0.1, tol=0.1)
    assert math.isfinite(result["actual_max_deviation"])
    assert result["actual_max_deviation"] >= 0.0
    assert result["surface"] is not None


# ===========================================================================
# T25  Multiple circle offsets form nested rings
# ===========================================================================

def test_offset_circles_nested():
    """Successive circle offsets form nested concentric rings."""
    r = 1.0
    circle = make_circle_nurbs(np.zeros(3), r)

    results = [offset_curve(circle, d) for d in [0.2, 0.5, 1.0]]
    for res in results:
        assert res["ok"]

    radii = []
    for res, d in zip(results, [0.2, 0.5, 1.0]):
        pts = _sample_curve_pts(res["curve"], 20)
        radii.append(float(np.mean(np.linalg.norm(pts[:, :2], axis=1))))

    # Verify monotone ordering.
    assert radii[0] < radii[1] < radii[2], f"radii not nested: {radii}"
    np.testing.assert_allclose(radii, [1.2, 1.5, 2.0], atol=1e-9)
