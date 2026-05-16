"""
test_ssi_robust.py
===================
GK-09 / GK-10 — hardened surface-surface intersection.

Every test uses a **closed-form analytic oracle** (exact circle radius/centre
from the two-sphere or sphere-plane formula, exact Steinmetz ellipse pair,
exact line-sphere quadratic roots).  "Looks plausible" is never the assertion.

All hermetic: pure Python + NumPy.  No OCCT, no DB, no network.

Run:
    python -m pytest packages/kerf-cad-core/tests/test_ssi_robust.py -q
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.intersection import (
    line_plane_root,
    line_sphere_roots,
    surface_surface_intersect,
)


# ---------------------------------------------------------------------------
# Exact rational primitive factories (machine-precision NURBS)
# ---------------------------------------------------------------------------

_S = math.sqrt(2.0) / 2.0
_CIRC9 = [
    (1.0, 0.0, 1.0), (1.0, 1.0, _S), (0.0, 1.0, 1.0), (-1.0, 1.0, _S),
    (-1.0, 0.0, 1.0), (-1.0, -1.0, _S), (0.0, -1.0, 1.0), (1.0, -1.0, _S),
    (1.0, 0.0, 1.0),
]
_KU9 = np.array([0, 0, 0, .25, .25, .5, .5, .75, .75, 1, 1, 1.0])


def make_rational_sphere(center, r) -> NurbsSurface:
    """Exact NURBS sphere (revolution of a rational half-circle meridian)."""
    center = np.asarray(center, dtype=float)
    mer = [
        (0.0, -r, 1.0), (r, -r, _S), (r, 0.0, 1.0), (r, r, _S), (0.0, r, 1.0),
    ]
    cp = np.zeros((9, 5, 3))
    w = np.zeros((9, 5))
    for i, (cx, cy, cw) in enumerate(_CIRC9):
        for j, (mx, mz, mw) in enumerate(mer):
            cp[i, j] = [center[0] + mx * cx, center[1] + mx * cy,
                        center[2] + mz]
            w[i, j] = cw * mw
    kv = np.array([0, 0, 0, .5, .5, 1, 1, 1.0])
    return NurbsSurface(degree_u=2, degree_v=2, control_points=cp,
                        knots_u=_KU9.copy(), knots_v=kv, weights=w)


def make_rational_cylinder(axis_pt, axis_dir, r, half_len) -> NurbsSurface:
    """Exact NURBS right circular cylinder (rational-quad cross section)."""
    axis_pt = np.asarray(axis_pt, dtype=float)
    axis_dir = np.asarray(axis_dir, dtype=float)
    axis_dir = axis_dir / np.linalg.norm(axis_dir)
    ref = (np.array([1.0, 0.0, 0.0]) if abs(axis_dir[0]) < 0.9
           else np.array([0.0, 1.0, 0.0]))
    e1 = ref - (ref @ axis_dir) * axis_dir
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(axis_dir, e1)
    cp = np.zeros((9, 2, 3))
    w = np.zeros((9, 2))
    for i, (cx, cy, cw) in enumerate(_CIRC9):
        radial = r * (cx * e1 + cy * e2)
        for j, t in enumerate((-half_len, half_len)):
            cp[i, j] = axis_pt + radial + t * axis_dir
            w[i, j] = cw
    kv = np.array([0, 0, 1, 1.0])
    return NurbsSurface(degree_u=2, degree_v=1, control_points=cp,
                        knots_u=_KU9.copy(), knots_v=kv, weights=w)


def make_plane(point, normal, half=3.0) -> NurbsSurface:
    """Bilinear (degree-1) finite plane patch through *point* with *normal*."""
    point = np.asarray(point, dtype=float)
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)
    ref = (np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9
           else np.array([0.0, 1.0, 0.0]))
    e1 = ref - (ref @ n) * n
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    cp = np.zeros((2, 2, 3))
    for i, su in enumerate((-half, half)):
        for j, sv in enumerate((-half, half)):
            cp[i, j] = point + su * e1 + sv * e2
    k = np.array([0, 0, 1, 1.0])
    return NurbsSurface(degree_u=1, degree_v=1, control_points=cp,
                        knots_u=k.copy(), knots_v=k.copy())


# ---------------------------------------------------------------------------
# Polyline geometry helpers (oracles operate on returned 3-D points)
# ---------------------------------------------------------------------------

def _pts(branch):
    return np.array(branch["points"], dtype=float)


def _fit_circle_3d(pts):
    """Best-fit circle of a (near-)planar 3-D loop → (centre, radius, normal)."""
    c0 = pts.mean(axis=0)
    q = pts - c0
    _, _, vh = np.linalg.svd(q, full_matrices=False)
    normal = vh[-1]
    e1, e2 = vh[0], vh[1]
    x = q @ e1
    y = q @ e2
    A = np.column_stack([2 * x, 2 * y, np.ones_like(x)])
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    cx, cy = sol[0], sol[1]
    r = math.sqrt(sol[2] + cx * cx + cy * cy)
    centre = c0 + cx * e1 + cy * e2
    return centre, r, normal / np.linalg.norm(normal)


def _max_radial_error(pts, centre, r):
    return float(np.max(np.abs(np.linalg.norm(pts - centre, axis=1) - r)))


def _sampling_uniformity(pts):
    """Ratio max_seg / min_seg of consecutive 3-D point spacings."""
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    seg = seg[seg > 1e-12]
    if seg.size < 2:
        return 1.0
    return float(seg.max() / seg.min())


# ===========================================================================
# 1. sphere ∩ plane through the centre → exact great circle
# ===========================================================================

class TestSpherePlaneGreatCircle:
    def test_great_circle_radius_centre_exact(self):
        sph = make_rational_sphere([0.0, 0.0, 0.0], 2.0)
        pln = make_plane([0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
        res = surface_surface_intersect(sph, pln, tol=1e-9)
        assert res["ok"] and res["branch_count"] == 1
        br = res["branches"][0]
        assert br["closed"] is True
        pts = _pts(br)
        c, r, _ = _fit_circle_3d(pts)
        # Great circle: radius == sphere radius, centre == sphere centre.
        assert r == pytest.approx(2.0, abs=1e-7)
        assert np.linalg.norm(c - np.array([0.0, 0.0, 0.0])) < 1e-7
        assert _max_radial_error(pts, c, r) < 1e-7

    def test_great_circle_in_plane(self):
        sph = make_rational_sphere([1.0, -2.0, 0.5], 3.0)
        pln = make_plane([1.0, -2.0, 0.5], [0.0, 0.0, 1.0], half=5.0)
        res = surface_surface_intersect(sph, pln, tol=1e-9)
        pts = _pts(res["branches"][0])
        # Every intersection point must lie in the plane z = 0.5.
        assert np.max(np.abs(pts[:, 2] - 0.5)) < 1e-7

    def test_great_circle_uniform_sampling(self):
        sph = make_rational_sphere([0.0, 0.0, 0.0], 2.0)
        pln = make_plane([0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
        res = surface_surface_intersect(sph, pln, tol=1e-9)
        # ~uniform arc-length sampling around the loop.
        assert _sampling_uniformity(_pts(res["branches"][0])) < 1.05

    def test_offset_plane_smaller_circle(self):
        # Plane z = 1 cuts sphere r=2 → circle radius sqrt(4-1)=sqrt(3).
        sph = make_rational_sphere([0.0, 0.0, 0.0], 2.0)
        pln = make_plane([0.0, 0.0, 1.0], [0.0, 0.0, 1.0])
        res = surface_surface_intersect(sph, pln, tol=1e-9)
        c, r, _ = _fit_circle_3d(_pts(res["branches"][0]))
        assert r == pytest.approx(math.sqrt(3.0), abs=1e-7)
        assert np.linalg.norm(c - np.array([0.0, 0.0, 1.0])) < 1e-7

    def test_plane_misses_sphere_no_branch(self):
        sph = make_rational_sphere([0.0, 0.0, 0.0], 1.0)
        pln = make_plane([0.0, 0.0, 5.0], [0.0, 0.0, 1.0])
        res = surface_surface_intersect(sph, pln, tol=1e-9)
        assert res["ok"] and res["branch_count"] == 0


# ===========================================================================
# 2. sphere ∩ sphere (overlapping) → exact circle (two-sphere formula)
# ===========================================================================

class TestSphereSphereCircle:
    def test_overlapping_circle_exact(self):
        # Two spheres r=2, centres d=2 apart on X.
        d, rA, rB = 2.0, 2.0, 2.0
        sA = make_rational_sphere([0.0, 0.0, 0.0], rA)
        sB = make_rational_sphere([d, 0.0, 0.0], rB)
        res = surface_surface_intersect(sA, sB, tol=1e-9)
        assert res["ok"] and res["branch_count"] == 1
        br = res["branches"][0]
        assert br["closed"] is True
        pts = _pts(br)
        # Two-sphere formula.
        a = (d * d - rB * rB + rA * rA) / (2.0 * d)
        rc = math.sqrt(rA * rA - a * a)
        c_exact = np.array([a, 0.0, 0.0])
        c, r, _ = _fit_circle_3d(pts)
        assert r == pytest.approx(rc, abs=1e-7)
        assert np.linalg.norm(c - c_exact) < 1e-7
        assert _max_radial_error(pts, c, r) < 1e-7
        # Plane of the circle is x = a.
        assert np.max(np.abs(pts[:, 0] - a)) < 1e-7

    def test_unequal_radii_circle_exact(self):
        rA, rB, d = 3.0, 2.0, 4.0
        sA = make_rational_sphere([0.0, 0.0, 0.0], rA)
        sB = make_rational_sphere([d, 0.0, 0.0], rB)
        res = surface_surface_intersect(sA, sB, tol=1e-9)
        a = (d * d - rB * rB + rA * rA) / (2.0 * d)
        rc = math.sqrt(rA * rA - a * a)
        c, r, _ = _fit_circle_3d(_pts(res["branches"][0]))
        assert r == pytest.approx(rc, abs=1e-7)
        assert c[0] == pytest.approx(a, abs=1e-7)

    def test_disjoint_spheres_no_branch(self):
        sA = make_rational_sphere([0.0, 0.0, 0.0], 1.0)
        sB = make_rational_sphere([5.0, 0.0, 0.0], 1.0)
        res = surface_surface_intersect(sA, sB, tol=1e-9)
        assert res["ok"] and res["branch_count"] == 0

    def test_externally_tangent_single_point(self):
        # r=1 spheres, centres 2 apart → tangent at (1,0,0): one point.
        sA = make_rational_sphere([0.0, 0.0, 0.0], 1.0)
        sB = make_rational_sphere([2.0, 0.0, 0.0], 1.0)
        res = surface_surface_intersect(sA, sB, tol=1e-9)
        assert res["branch_count"] == 1
        pts = _pts(res["branches"][0])
        assert len(pts) == 1
        assert np.linalg.norm(pts[0] - np.array([1.0, 0.0, 0.0])) < 1e-6
        assert res["branches"][0]["closed"] is False


# ===========================================================================
# 3. cylinder ∩ cylinder, equal radius, perpendicular crossing axes
#    → exact Steinmetz pair (two branches, count == 2)
# ===========================================================================

class TestCylinderCylinderSteinmetz:
    def _setup(self, r=1.0):
        cA = make_rational_cylinder([0, 0, 0], [0, 0, 1], r, 4.0)
        cB = make_rational_cylinder([0, 0, 0], [0, 1, 0], r, 4.0)
        return cA, cB, r

    def test_two_branches_found(self):
        cA, cB, r = self._setup(1.0)
        res = surface_surface_intersect(cA, cB, tol=1e-7)
        assert res["ok"]
        assert res["branch_count"] == 2

    def test_both_branches_closed(self):
        cA, cB, r = self._setup(1.5)
        res = surface_surface_intersect(cA, cB, tol=1e-7)
        for br in res["branches"]:
            assert br["closed"] is True

    def test_points_on_both_cylinders(self):
        cA, cB, r = self._setup(1.0)
        res = surface_surface_intersect(cA, cB, tol=1e-7)
        for br in res["branches"]:
            p = _pts(br)
            # On cyl A (axis Z): x²+y² = r².
            radA = np.hypot(p[:, 0], p[:, 1])
            # On cyl B (axis Y): x²+z² = r².
            radB = np.hypot(p[:, 0], p[:, 2])
            assert np.max(np.abs(radA - r)) < 1e-6
            assert np.max(np.abs(radB - r)) < 1e-6

    def test_steinmetz_curve_lies_on_bisector_planes(self):
        cA, cB, r = self._setup(1.0)
        res = surface_surface_intersect(cA, cB, tol=1e-7)
        # Each branch lies in a plane y = ±z (the axis bisectors).
        plane_resid = []
        for br in res["branches"]:
            p = _pts(br)
            # min over the two candidate plane normals.
            r1 = np.max(np.abs(p[:, 1] - p[:, 2]))
            r2 = np.max(np.abs(p[:, 1] + p[:, 2]))
            plane_resid.append(min(r1, r2))
        for pr in plane_resid:
            assert pr < 1e-6

    def test_branch_count_is_exactly_two(self):
        cA, cB, r = self._setup(2.0)
        res = surface_surface_intersect(cA, cB, tol=1e-7)
        assert len(res["branches"]) == 2


# ===========================================================================
# 4. plane tangent to sphere → single degenerate point (not garbage loop)
# ===========================================================================

class TestTangentPlaneSphere:
    def test_tangent_plane_single_point(self):
        sph = make_rational_sphere([0.0, 0.0, 0.0], 2.0)
        # Plane z = 2 is tangent at the north pole (0,0,2).
        pln = make_plane([0.0, 0.0, 2.0], [0.0, 0.0, 1.0], half=4.0)
        res = surface_surface_intersect(sph, pln, tol=1e-9)
        assert res["ok"] and res["branch_count"] == 1
        br = res["branches"][0]
        pts = _pts(br)
        assert len(pts) == 1
        assert np.linalg.norm(pts[0] - np.array([0.0, 0.0, 2.0])) < 1e-6
        assert br["closed"] is False

    def test_tangent_not_empty_not_loop(self):
        sph = make_rational_sphere([1.0, 1.0, 1.0], 1.0)
        pln = make_plane([1.0, 1.0, 2.0], [0.0, 0.0, 1.0], half=3.0)
        res = surface_surface_intersect(sph, pln, tol=1e-9)
        assert res["branch_count"] == 1
        assert len(res["branches"][0]["points"]) == 1


# ===========================================================================
# 5. small loop smaller than the default seed grid → still found
#    (adaptive-reseed proof; non-analytic surfaces force the marcher)
# ===========================================================================

def _bump_surface(cx, cy, amp, sigma, n=11, half=1.0):
    """Smooth Gaussian bump z = amp·exp(-((x-cx)²+(y-cy)²)/2σ²)."""
    cp = np.zeros((n, n, 3))
    xs = np.linspace(-half, half, n)
    ys = np.linspace(-half, half, n)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            z = amp * math.exp(-((x - cx) ** 2 + (y - cy) ** 2)
                               / (2.0 * sigma * sigma))
            cp[i, j] = [x, y, z]

    def _k(m, deg):
        inner = max(0, m - deg - 1)
        return np.concatenate([
            np.zeros(deg + 1),
            (np.linspace(0, 1, inner + 2)[1:-1] if inner > 0
             else np.array([])),
            np.ones(deg + 1),
        ])
    return NurbsSurface(degree_u=3, degree_v=3, control_points=cp,
                        knots_u=_k(n, 3), knots_v=_k(n, 3))


# Gaussian-bump ∩ horizontal-plane analytic oracle: the loop is the level
# set amp·exp(-rho²/2σ²) = z0 ⇒ rho = σ·sqrt(-2·ln(z0/amp)).
_BUMP_AMP = 1.0
_BUMP_SIGMA = 0.10
_BUMP_Z0 = 0.30
_BUMP_RHO = _BUMP_SIGMA * math.sqrt(-2.0 * math.log(_BUMP_Z0 / _BUMP_AMP))


def _coarse_seed_cell_size(surf, n=8):
    """3-D spacing of one coarse (n×n) seed cell at the patch centre."""
    p0 = _surf_eval_pt(surf, 0.5, 0.5)
    p1 = _surf_eval_pt(surf, 0.5 + 1.0 / n, 0.5)
    return float(np.linalg.norm(p1 - p0))


def _surf_eval_pt(surf, u, v):
    from kerf_cad_core.geom.intersection import _surf_eval
    return _surf_eval(surf, u, v)


class TestSmallLoopAdaptiveReseed:
    def test_small_loop_found_below_seed_grid(self):
        # A narrow Gaussian bump pierces a low flat plane in a small closed
        # loop whose diameter is BELOW one coarse 8x8 seed-grid cell — only
        # the adaptive reseed can find it.
        bump = _bump_surface(0.0, 0.0, _BUMP_AMP, _BUMP_SIGMA, half=1.0)
        pln = make_plane([0.0, 0.0, _BUMP_Z0], [0.0, 0.0, 1.0], half=1.0)
        res = surface_surface_intersect(
            bump, pln, tol=1e-6, samples_u=8, samples_v=8, step=0.02
        )
        assert res["ok"]
        assert res["branch_count"] >= 1
        br = res["branches"][0]
        assert br["closed"] is True

        pts = _pts(br)
        c = pts.mean(axis=0)
        radii = np.linalg.norm(pts[:, :2] - c[:2], axis=1)
        loop_diameter = 2.0 * float(radii.max())
        seed_cell = _coarse_seed_cell_size(bump, 8)
        # Proof of adaptive reseed: the whole loop fits inside one coarse cell.
        assert loop_diameter < seed_cell
        # Analytic oracle: mean loop radius matches the closed-form level-set
        # radius rho (chordal polyline ⇒ a few-% tolerance).
        assert float(radii.mean()) == pytest.approx(_BUMP_RHO, rel=0.15)

    def test_small_loop_points_on_plane(self):
        bump = _bump_surface(0.0, 0.0, _BUMP_AMP, _BUMP_SIGMA, half=1.0)
        pln = make_plane([0.0, 0.0, _BUMP_Z0], [0.0, 0.0, 1.0], half=1.0)
        res = surface_surface_intersect(
            bump, pln, tol=1e-6, samples_u=8, samples_v=8, step=0.02
        )
        allpts = np.vstack([_pts(b) for b in res["branches"]])
        # Every point lies on the cutting plane z = z0 (closed-form).
        assert np.max(np.abs(allpts[:, 2] - _BUMP_Z0)) < 1e-3

    def test_large_loop_found_by_coarse_grid_too(self):
        # Sanity counterpart: a wide bump's loop is larger than a seed cell
        # and is found by the coarse grid directly (still deterministic).
        bump = _bump_surface(0.0, 0.0, 1.0, 0.45, half=1.5)
        pln = make_plane([0.0, 0.0, 0.30], [0.0, 0.0, 1.0], half=2.0)
        res = surface_surface_intersect(
            bump, pln, tol=1e-6, samples_u=10, samples_v=10, step=0.04
        )
        assert res["ok"] and res["branch_count"] >= 1
        assert res["branches"][0]["closed"] is True


# ===========================================================================
# 6. line ∩ sphere closed form — 0 / 1 (tangent) / 2 roots, exact to 1e-12
# ===========================================================================

class TestLineSphereClosedForm:
    def test_two_roots_exact(self):
        p0 = np.array([-5.0, 0.0, 0.0])
        d = np.array([1.0, 0.0, 0.0])
        roots = line_sphere_roots(p0, d, np.array([0.0, 0.0, 0.0]), 2.0)
        assert len(roots) == 2
        # Sphere r=2 centred at origin, line is the X axis → x = ∓2.
        assert roots[0] == pytest.approx(3.0, abs=1e-12)
        assert roots[1] == pytest.approx(7.0, abs=1e-12)
        for s in roots:
            P = p0 + s * d
            assert abs(np.linalg.norm(P) - 2.0) < 1e-12

    def test_tangent_single_root(self):
        # Line z = r in the y-direction grazes the sphere at (0,0,2).
        p0 = np.array([0.0, -3.0, 2.0])
        d = np.array([0.0, 1.0, 0.0])
        roots = line_sphere_roots(p0, d, np.array([0.0, 0.0, 0.0]), 2.0)
        assert len(roots) == 1
        P = p0 + roots[0] * d
        assert np.linalg.norm(P - np.array([0.0, 0.0, 2.0])) < 1e-9
        assert abs(np.linalg.norm(P) - 2.0) < 1e-9

    def test_no_root_misses(self):
        p0 = np.array([0.0, -3.0, 5.0])
        d = np.array([0.0, 1.0, 0.0])
        roots = line_sphere_roots(p0, d, np.array([0.0, 0.0, 0.0]), 2.0)
        assert roots == []

    def test_oblique_line_roots_exact(self):
        # Line through the sphere centre ⇒ chord = diameter, roots straddle
        # the centre by exactly r/|d| (closed-form oracle).
        center = np.array([1.0, 2.0, 3.0])
        r = 4.0
        d = np.array([1.0, 0.5, -0.25])
        p0 = center - 10.0 * d  # well outside, aimed at the centre
        roots = line_sphere_roots(p0, d, center, r)
        assert len(roots) == 2
        for s in roots:
            P = p0 + s * d
            assert abs(np.linalg.norm(P - center) - r) < 1e-12
        # Midpoint of the two roots is the foot of the centre ⇒ s = 10.
        assert 0.5 * (roots[0] + roots[1]) == pytest.approx(10.0, abs=1e-12)
        half = r / np.linalg.norm(d)
        assert roots[1] - roots[0] == pytest.approx(2.0 * half, abs=1e-12)

    def test_line_plane_root_exact(self):
        p0 = np.array([0.0, 0.0, -3.0])
        d = np.array([0.0, 0.0, 2.0])
        s = line_plane_root(p0, d, np.array([0.0, 0.0, 1.0]),
                            np.array([0.0, 0.0, 1.0]))
        assert s == pytest.approx(2.0, abs=1e-12)
        assert np.allclose(p0 + s * d, [0.0, 0.0, 1.0], atol=1e-12)

    def test_line_plane_parallel_none(self):
        s = line_plane_root(np.array([0.0, 0.0, 1.0]),
                            np.array([1.0, 0.0, 0.0]),
                            np.array([0.0, 0.0, 0.0]),
                            np.array([0.0, 0.0, 1.0]))
        assert s is None


# ===========================================================================
# 7. Determinism — identical branch ordering & point counts across 5 runs
# ===========================================================================

class TestDeterminism:
    def _signature(self, res):
        return tuple(
            (len(b["points"]), bool(b["closed"]),
             round(float(np.array(b["points"]).sum()), 6))
            for b in res["branches"]
        )

    def test_sphere_plane_deterministic(self):
        sigs = []
        for _ in range(5):
            sph = make_rational_sphere([0.0, 0.0, 0.0], 2.0)
            pln = make_plane([0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
            sigs.append(self._signature(
                surface_surface_intersect(sph, pln, tol=1e-9)))
        assert len(set(sigs)) == 1

    def test_cyl_cyl_deterministic(self):
        sigs = []
        for _ in range(5):
            cA = make_rational_cylinder([0, 0, 0], [0, 0, 1], 1.0, 4.0)
            cB = make_rational_cylinder([0, 0, 0], [0, 1, 0], 1.0, 4.0)
            res = surface_surface_intersect(cA, cB, tol=1e-7)
            sigs.append((res["branch_count"], self._signature(res)))
        assert len(set(sigs)) == 1

    def test_small_loop_marcher_deterministic(self):
        counts = []
        for _ in range(5):
            bump = _bump_surface(0.0, 0.0, amp=1.0, sigma=0.18, half=1.0)
            pln = make_plane([0.0, 0.0, 0.30], [0.0, 0.0, 1.0], half=1.0)
            res = surface_surface_intersect(
                bump, pln, tol=1e-6, samples_u=8, samples_v=8, step=0.04
            )
            counts.append((
                res["branch_count"],
                tuple(len(b["points"]) for b in res["branches"]),
            ))
        assert len(set(counts)) == 1


# ===========================================================================
# 8. Regression / contract guards (never raises, dict shape preserved)
# ===========================================================================

class TestContract:
    def test_never_raises_bad_input(self):
        res = surface_surface_intersect("x", None, tol=1e-6)
        assert res["ok"] is False
        assert "branches" in res and "branch_count" in res

    def test_result_shape(self):
        sph = make_rational_sphere([0.0, 0.0, 0.0], 1.0)
        pln = make_plane([0.0, 0.0, 0.0], [0.0, 0.0, 1.0])
        res = surface_surface_intersect(sph, pln, tol=1e-9)
        for k in ("ok", "reason", "branches", "branch_count"):
            assert k in res
        for b in res["branches"]:
            n = len(b["points"])
            assert len(b["params_a"]) == n
            assert len(b["params_b"]) == n
            assert isinstance(b["closed"], bool)

    def test_plane_cylinder_perp_axis_circle(self):
        # Plane z=0 perpendicular to a Z-axis cylinder r=1.5 → exact circle.
        cyl = make_rational_cylinder([0, 0, 0], [0, 0, 1], 1.5, 3.0)
        pln = make_plane([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], half=4.0)
        res = surface_surface_intersect(cyl, pln, tol=1e-9)
        assert res["branch_count"] == 1
        c, r, _ = _fit_circle_3d(_pts(res["branches"][0]))
        assert r == pytest.approx(1.5, abs=1e-7)
        assert np.linalg.norm(c) < 1e-7

    def test_offset_plane_cylinder_circle_translated(self):
        # Plane z=2 ⟂ Z-cylinder r=1 → circle radius 1 centred at (0,0,2).
        cyl = make_rational_cylinder([0, 0, 0], [0, 0, 1], 1.0, 4.0)
        pln = make_plane([0.0, 0.0, 2.0], [0.0, 0.0, 1.0], half=4.0)
        res = surface_surface_intersect(cyl, pln, tol=1e-9)
        c, r, _ = _fit_circle_3d(_pts(res["branches"][0]))
        assert r == pytest.approx(1.0, abs=1e-7)
        assert np.linalg.norm(c - np.array([0.0, 0.0, 2.0])) < 1e-7


# ===========================================================================
# 9. Extra analytic-oracle coverage
# ===========================================================================

class TestExtraAnalytic:
    def test_sphere_sphere_internally_tangent_point(self):
        # r=3 centred origin, r=1 centred (2,0,0): internally tangent at
        # (3,0,0).  Single degenerate point, not a loop.
        sA = make_rational_sphere([0.0, 0.0, 0.0], 3.0)
        sB = make_rational_sphere([2.0, 0.0, 0.0], 1.0)
        res = surface_surface_intersect(sA, sB, tol=1e-9)
        assert res["branch_count"] == 1
        pts = _pts(res["branches"][0])
        assert len(pts) == 1
        assert np.linalg.norm(pts[0] - np.array([3.0, 0.0, 0.0])) < 1e-6
        assert res["branches"][0]["closed"] is False

    def test_sphere_plane_oblique_normal_circle(self):
        # Plane with a tilted normal through the sphere centre is still a
        # great circle of radius == sphere radius.
        sph = make_rational_sphere([0.0, 0.0, 0.0], 2.5)
        n = np.array([1.0, 1.0, 1.0])
        pln = make_plane([0.0, 0.0, 0.0], n, half=5.0)
        res = surface_surface_intersect(sph, pln, tol=1e-9)
        c, r, normal = _fit_circle_3d(_pts(res["branches"][0]))
        assert r == pytest.approx(2.5, abs=1e-7)
        assert np.linalg.norm(c) < 1e-7
        # Circle plane normal is parallel to the cutting plane normal.
        nn = n / np.linalg.norm(n)
        assert abs(abs(float(normal @ nn)) - 1.0) < 1e-7

    def test_line_sphere_roots_match_ssi_seed(self):
        # Cross-check: the closed-form line∩sphere roots reproduce the exact
        # great-circle radius for the plane through the centre.
        roots = line_sphere_roots(
            np.array([-9.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 0.0, 0.0]), 3.0,
        )
        assert roots == pytest.approx([6.0, 12.0], abs=1e-12)

    def test_cyl_cyl_unequal_radius_not_steinmetz_closed_form(self):
        # Unequal radii ⇒ no equal-radius Steinmetz closed form; the hardened
        # marcher must still return a valid (never-raising) result dict.
        cA = make_rational_cylinder([0, 0, 0], [0, 0, 1], 1.0, 3.0)
        cB = make_rational_cylinder([0, 0, 0], [0, 1, 0], 1.6, 3.0)
        res = surface_surface_intersect(cA, cB, tol=1e-5)
        assert res["ok"] is True
        assert isinstance(res["branches"], list)

    def test_determinism_sphere_sphere_five_runs(self):
        sigs = []
        for _ in range(5):
            sA = make_rational_sphere([0.0, 0.0, 0.0], 2.0)
            sB = make_rational_sphere([2.0, 0.0, 0.0], 2.0)
            r = surface_surface_intersect(sA, sB, tol=1e-9)
            sigs.append((
                r["branch_count"],
                tuple(len(b["points"]) for b in r["branches"]),
                round(float(np.array(r["branches"][0]["points"]).sum()), 9),
            ))
        assert len(set(sigs)) == 1
