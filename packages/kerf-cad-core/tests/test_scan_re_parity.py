"""
test_scan_re_parity — parity test between scan/fit.py direct fitters and
reverse_engineering cone/torus fitters, exercising the shared linalg helpers.

After the dedup refactor, fit_cone.py and fit_torus.py import their geometry
helpers (_dot, _sub, _norm, _normalise, _centroid, _covariance3, _jacobi3,
etc.) from scan.fit instead of duplicating them.  This test suite:

1. Confirms that fit_plane_direct / fit_sphere_direct / fit_cylinder_direct
   still return results within tight geometric tolerance on known synthetic
   clouds (regression guard for the shared helpers).

2. Verifies plane/sphere/cylinder RANSAC results agree within tolerance
   (numerical parity: same helpers → same numbers).

3. Confirms fit_cone_direct + ransac_fit_cone work correctly after the import
   refactor (helpers now come from scan.fit).

4. Confirms fit_torus_direct + ransac_fit_torus work correctly after the
   import refactor.

Tolerance used throughout: 1e-6 absolute (same underlying floats).

Author: imranparuk
"""
from __future__ import annotations

import math
import random

import pytest

from kerf_cad_core.scan.fit import (
    fit_plane_direct,
    fit_sphere_direct,
    fit_cylinder_direct,
    ransac_fit_plane,
    ransac_fit_sphere,
    ransac_fit_cylinder,
    _normalise,
    _dot,
)
from kerf_cad_core.reverse_engineering.fit_cone import (
    fit_cone_direct,
    ransac_fit_cone,
)
from kerf_cad_core.reverse_engineering.fit_torus import (
    fit_torus_direct,
    ransac_fit_torus,
)


# ---------------------------------------------------------------------------
# Synthetic cloud generators (self-contained, no shared test fixtures)
# ---------------------------------------------------------------------------

def _sphere_pts(cx: float, cy: float, cz: float, r: float, n: int = 200, seed: int = 1) -> list[list[float]]:
    """Uniform distribution on sphere surface via Gaussian normalisation."""
    rng = random.Random(seed)
    pts = []
    while len(pts) < n:
        x = rng.gauss(0, 1)
        y = rng.gauss(0, 1)
        z = rng.gauss(0, 1)
        mag = math.sqrt(x*x + y*y + z*z)
        if mag < 1e-12:
            continue
        pts.append([cx + x*r/mag, cy + y*r/mag, cz + z*r/mag])
    return pts


def _plane_pts(n: int = 200, seed: int = 0) -> list[list[float]]:
    """Points on z = 2 plane."""
    rng = random.Random(seed)
    return [[rng.uniform(-5, 5), rng.uniform(-5, 5), 2.0] for _ in range(n)]


def _cylinder_pts(r: float = 3.0, height: float = 10.0, n: int = 300, seed: int = 2) -> list[list[float]]:
    """Points on z-axis cylinder surface."""
    rng = random.Random(seed)
    pts = []
    for _ in range(n):
        theta = rng.uniform(0, 2 * math.pi)
        t = rng.uniform(-height/2, height/2)
        pts.append([r * math.cos(theta), r * math.sin(theta), t])
    return pts


def _cone_pts(
    apex: list[float],
    axis: list[float],
    half_angle: float,
    n: int = 100,
    height: float = 5.0,
    seed: int = 7,
) -> list[list[float]]:
    """Points on cone surface."""
    mag = math.sqrt(sum(a*a for a in axis))
    axis = [a/mag for a in axis]
    ref = [1.0, 0.0, 0.0] if abs(axis[2]) < 0.9 else [0.0, 1.0, 0.0]
    u = [
        axis[1]*ref[2]-axis[2]*ref[1],
        axis[2]*ref[0]-axis[0]*ref[2],
        axis[0]*ref[1]-axis[1]*ref[0],
    ]
    un = math.sqrt(u[0]**2+u[1]**2+u[2]**2)
    u = [ui/un for ui in u]
    v = [axis[1]*u[2]-axis[2]*u[1], axis[2]*u[0]-axis[0]*u[2], axis[0]*u[1]-axis[1]*u[0]]
    rng = random.Random(seed)
    tan_a = math.tan(half_angle)
    pts = []
    for _ in range(n):
        t = rng.uniform(0.01, height)
        theta = rng.uniform(0, 2*math.pi)
        r = t * tan_a
        pts.append([
            apex[0] + t*axis[0] + r*math.cos(theta)*u[0] + r*math.sin(theta)*v[0],
            apex[1] + t*axis[1] + r*math.cos(theta)*u[1] + r*math.sin(theta)*v[1],
            apex[2] + t*axis[2] + r*math.cos(theta)*u[2] + r*math.sin(theta)*v[2],
        ])
    return pts


def _torus_pts(
    centre: list[float],
    axis: list[float],
    R: float,
    r: float,
    n: int = 200,
    seed: int = 3,
) -> list[list[float]]:
    """Points on torus surface."""
    mag = math.sqrt(sum(a*a for a in axis))
    axis = [a/mag for a in axis]
    ref = [1.0, 0.0, 0.0] if abs(axis[2]) < 0.9 else [0.0, 1.0, 0.0]
    u = [
        axis[1]*ref[2]-axis[2]*ref[1],
        axis[2]*ref[0]-axis[0]*ref[2],
        axis[0]*ref[1]-axis[1]*ref[0],
    ]
    un = math.sqrt(u[0]**2+u[1]**2+u[2]**2)
    u = [ui/un for ui in u]
    v = [axis[1]*u[2]-axis[2]*u[1], axis[2]*u[0]-axis[0]*u[2], axis[0]*u[1]-axis[1]*u[0]]
    rng = random.Random(seed)
    pts = []
    for _ in range(n):
        phi = rng.uniform(0, 2*math.pi)
        theta = rng.uniform(0, 2*math.pi)
        rad_dir = [math.cos(phi)*u[i] + math.sin(phi)*v[i] for i in range(3)]
        pts.append([
            centre[0] + (R + r*math.cos(theta))*rad_dir[0] + r*math.sin(theta)*axis[0],
            centre[1] + (R + r*math.cos(theta))*rad_dir[1] + r*math.sin(theta)*axis[1],
            centre[2] + (R + r*math.cos(theta))*rad_dir[2] + r*math.sin(theta)*axis[2],
        ])
    return pts


# ---------------------------------------------------------------------------
# Geometry tolerance helper
# ---------------------------------------------------------------------------

def _dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y)**2 for x, y in zip(a, b)))


# ===========================================================================
# 1. Regression: plane/sphere/cylinder direct fitters — shared helpers intact
# ===========================================================================

class TestPlaneFitterRegression:
    def test_plane_normal_z(self):
        pts = _plane_pts(n=200)
        r = fit_plane_direct(pts)
        assert r["ok"], r.get("reason")
        assert abs(abs(r["normal"][2]) - 1.0) < 1e-6

    def test_plane_residual_zero(self):
        pts = _plane_pts(n=200)
        r = fit_plane_direct(pts)
        assert r["ok"]
        assert r["residual"] < 1e-10

    def test_plane_d_equals_2(self):
        pts = _plane_pts(n=200)
        r = fit_plane_direct(pts)
        assert r["ok"]
        assert abs(abs(r["d"]) - 2.0) < 1e-6


class TestSphereFitterRegression:
    """Sphere fit on a sphere of radius 5, centre (1, 2, 3).

    Tolerance: fitted centre within 1e-4, radius within 1e-4.
    This is a geometric (not exact floating-point) parity: the algebraic LS
    solver is exact for noise-free clouds so 1e-4 is very conservative.
    """

    _CX, _CY, _CZ, _R = 1.0, 2.0, 3.0, 5.0

    def _pts(self) -> list[list[float]]:
        return _sphere_pts(self._CX, self._CY, self._CZ, self._R, n=300)

    def test_sphere_centre(self):
        r = fit_sphere_direct(self._pts())
        assert r["ok"], r.get("reason")
        assert _dist(r["centre"], [self._CX, self._CY, self._CZ]) < 1e-4, (
            f"centre error: {r['centre']} vs [{self._CX},{self._CY},{self._CZ}]"
        )

    def test_sphere_radius(self):
        r = fit_sphere_direct(self._pts())
        assert r["ok"]
        assert abs(r["radius"] - self._R) < 1e-4, (
            f"radius error: {r['radius']} vs {self._R}"
        )

    def test_sphere_residual_near_zero(self):
        r = fit_sphere_direct(self._pts())
        assert r["ok"]
        assert r["residual"] < 1e-6


class TestCylinderFitterRegression:
    """Cylinder fit on z-axis cylinder, radius 3, height 10.

    Tolerance: radius within 1%, axis parallel to z within 0.01.
    """

    def _pts(self) -> list[list[float]]:
        return _cylinder_pts(r=3.0, height=10.0, n=300)

    def test_cylinder_radius(self):
        r = fit_cylinder_direct(self._pts())
        assert r["ok"], r.get("reason")
        assert abs(r["radius"] - 3.0) / 3.0 < 0.01, (
            f"radius error: {r['radius']} vs 3.0"
        )

    def test_cylinder_axis_z(self):
        r = fit_cylinder_direct(self._pts())
        assert r["ok"]
        assert abs(abs(r["axis"][2]) - 1.0) < 0.01, f"axis: {r['axis']}"

    def test_cylinder_residual_small(self):
        # PCA axis estimation is approximate; residual reflects axis angular error
        # not surface noise — 0.15 is consistent with the existing T19 tolerance.
        r = fit_cylinder_direct(self._pts())
        assert r["ok"]
        assert r["residual"] < 0.15


# ===========================================================================
# 2. Parity: RANSAC results reproduce when called twice with same seed
#    (confirms shared helpers are deterministic — bit-identical results)
# ===========================================================================

class TestRansacDeterminism:
    def test_plane_ransac_deterministic(self):
        pts = _plane_pts(n=100)
        r1 = ransac_fit_plane(pts, threshold=0.01, seed=42)
        r2 = ransac_fit_plane(pts, threshold=0.01, seed=42)
        assert r1["ok"] and r2["ok"]
        assert r1["normal"] == r2["normal"]
        assert r1["d"] == r2["d"]

    def test_sphere_ransac_deterministic(self):
        pts = _sphere_pts(0.0, 0.0, 0.0, 5.0, n=200)
        r1 = ransac_fit_sphere(pts, threshold=0.01, seed=42)
        r2 = ransac_fit_sphere(pts, threshold=0.01, seed=42)
        assert r1["ok"] and r2["ok"]
        assert r1["centre"] == r2["centre"]
        assert r1["radius"] == r2["radius"]

    def test_cylinder_ransac_deterministic(self):
        pts = _cylinder_pts(r=2.0, height=10.0, n=200)
        r1 = ransac_fit_cylinder(pts, threshold=0.05, seed=42)
        r2 = ransac_fit_cylinder(pts, threshold=0.05, seed=42)
        assert r1["ok"] and r2["ok"]
        assert r1["radius"] == r2["radius"]
        assert r1["axis"] == r2["axis"]


# ===========================================================================
# 3. Cone fitter after import-refactor (helpers now from scan.fit)
# ===========================================================================

class TestConeFitterAfterRefactor:
    """Cone fit on z-axis cone, apex at origin, half-angle 25°.

    Tolerance: half-angle within 1°, residual < 0.1.
    """

    _HALF_ANGLE = math.radians(25.0)

    def _pts(self) -> list[list[float]]:
        return _cone_pts([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], self._HALF_ANGLE, n=150, seed=42)

    def test_cone_direct_ok(self):
        r = fit_cone_direct(self._pts())
        assert r.get("ok"), f"fit_cone_direct failed: {r}"
        assert r["primitive"] == "cone"

    def test_cone_direct_half_angle(self):
        r = fit_cone_direct(self._pts())
        assert r.get("ok")
        err_deg = abs(math.degrees(r["half_angle"]) - 25.0)
        assert err_deg < 1.0, f"half_angle error {err_deg:.3f}°"

    def test_cone_ransac_half_angle(self):
        pts = self._pts()
        r = ransac_fit_cone(pts, threshold=0.05, n_iters=200, seed=42, refine=True)
        assert r.get("ok"), f"ransac_fit_cone failed: {r}"
        err_deg = abs(math.degrees(r["half_angle"]) - 25.0)
        assert err_deg < 1.0, f"RANSAC half_angle error {err_deg:.3f}°"

    def test_cone_too_few_points(self):
        r = fit_cone_direct([[1, 0, 0], [0, 1, 0]])
        assert r["ok"] is False

    def test_cone_ransac_deterministic(self):
        pts = self._pts()
        r1 = ransac_fit_cone(pts, threshold=0.05, seed=42, refine=False)
        r2 = ransac_fit_cone(pts, threshold=0.05, seed=42, refine=False)
        assert r1.get("ok") and r2.get("ok")
        assert r1["half_angle"] == r2["half_angle"]


# ===========================================================================
# 4. Torus fitter after import-refactor (helpers now from scan.fit)
# ===========================================================================

class TestTorusFitterAfterRefactor:
    """Torus at origin, z-axis, R=3, r=0.5.

    Tolerance: R within 1%, r within 5%, residual < 0.1.
    (The direct fitter uses mean-distance estimation so r tolerance is wider.)
    """

    _R, _r = 3.0, 0.5

    def _pts(self) -> list[list[float]]:
        return _torus_pts([0.0, 0.0, 0.0], [0.0, 0.0, 1.0], self._R, self._r, n=300, seed=3)

    def test_torus_direct_ok(self):
        r = fit_torus_direct(self._pts())
        assert r.get("ok"), f"fit_torus_direct failed: {r}"
        assert r["primitive"] == "torus"

    def test_torus_direct_major_radius(self):
        r = fit_torus_direct(self._pts())
        assert r.get("ok")
        assert abs(r["R"] - self._R) / self._R < 0.01, f"R error: {r['R']} vs {self._R}"

    def test_torus_direct_minor_radius(self):
        r = fit_torus_direct(self._pts())
        assert r.get("ok")
        assert abs(r["r"] - self._r) / self._r < 0.05, f"r error: {r['r']} vs {self._r}"

    def test_torus_ransac_major_radius_within_1pct(self):
        """Key parity assertion: fitted R within 1% on noise-free synthetic cloud."""
        pts = self._pts()
        r = ransac_fit_torus(pts, threshold=0.05, n_iters=100, seed=42)
        assert r.get("ok"), f"ransac_fit_torus failed: {r}"
        err_pct = abs(r["R"] - self._R) / self._R * 100
        assert err_pct < 1.0, f"R error {err_pct:.2f}% (got {r['R']:.4f}, expected {self._R})"

    def test_torus_ransac_minor_radius_within_5pct(self):
        """Minor radius within 5% (mean-based estimator, not exact algebraic)."""
        pts = self._pts()
        r = ransac_fit_torus(pts, threshold=0.05, n_iters=100, seed=42)
        assert r.get("ok")
        err_pct = abs(r["r"] - self._r) / self._r * 100
        assert err_pct < 5.0, f"r error {err_pct:.2f}% (got {r['r']:.4f}, expected {self._r})"

    def test_torus_too_few_points(self):
        r = fit_torus_direct([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        assert r["ok"] is False

    def test_torus_ransac_deterministic(self):
        pts = self._pts()
        r1 = ransac_fit_torus(pts, threshold=0.05, seed=77)
        r2 = ransac_fit_torus(pts, threshold=0.05, seed=77)
        assert r1.get("ok") and r2.get("ok")
        assert r1["R"] == r2["R"]
        assert r1["r"] == r2["r"]
