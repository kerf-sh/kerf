"""
Tests for kerf_cad_core.scan — point-cloud ingestion and primitive fitting.

All tests are pure-Python, hermetic: no OCC, no DB, no network, no fixtures
from disk. Tests run deterministically with fixed numeric inputs.

Coverage:
  - cloud_stats (scan_load backing function)
  - fit_plane_direct / ransac_fit_plane
  - fit_sphere_direct / ransac_fit_sphere
  - fit_cylinder_direct / ransac_fit_cylinder
  - greedy_segment
  - LLM tool wrappers (run_scan_load, run_scan_fit_plane, etc.)
  - Edge cases: <3 pts, collinear, degenerate, noisy data, RANSAC reproducibility

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.scan.fit import (
    cloud_stats,
    fit_plane_direct,
    fit_sphere_direct,
    fit_cylinder_direct,
    ransac_fit_plane,
    ransac_fit_sphere,
    ransac_fit_cylinder,
    greedy_segment,
    _centroid,
    _norm,
    _normalise,
    _dot,
)
from kerf_cad_core.scan.tools import (
    run_scan_load,
    run_scan_fit_plane,
    run_scan_fit_sphere,
    run_scan_fit_cylinder,
    run_scan_segment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_ctx():
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    return ProjectCtx(
        pool=None, storage=None,
        project_id=uuid.uuid4(), user_id=uuid.uuid4(),
        role="owner", http_client=None,
    )


def _ok(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err(raw: str) -> dict:
    """Accept either {ok:False,...} or err_payload-style {"error":...,"code":...}."""
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


# ---------------------------------------------------------------------------
# Synthetic cloud generators
# ---------------------------------------------------------------------------

def _plane_pts(n: int = 50, noise: float = 0.0, seed: int = 0) -> list[list[float]]:
    """Points on the plane z = 2 with optional Gaussian noise."""
    import random
    rng = random.Random(seed)
    pts = []
    for i in range(n):
        x = rng.uniform(-5, 5)
        y = rng.uniform(-5, 5)
        z = 2.0 + (rng.gauss(0, noise) if noise else 0.0)
        pts.append([x, y, z])
    return pts


def _sphere_pts(cx=1.0, cy=2.0, cz=3.0, r=5.0, n: int = 60, noise: float = 0.0, seed: int = 1) -> list[list[float]]:
    """Points on the surface of a sphere (golden-angle distribution + noise)."""
    import random
    rng = random.Random(seed)
    pts = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y_f = 1 - (i / (n - 1)) * 2
        rad = math.sqrt(max(0, 1 - y_f*y_f))
        theta = golden * i
        x_f = math.cos(theta) * rad
        z_f = math.sin(theta) * rad
        nr = r + (rng.gauss(0, noise) if noise else 0.0)
        pts.append([cx + x_f*nr, cy + y_f*nr, cz + z_f*nr])
    return pts


def _cylinder_pts(
    ax=0.0, ay=0.0, az=1.0,  # unit axis
    ox=0.0, oy=0.0, oz=0.0,  # point on axis
    r=3.0, height=10.0, n: int = 80, noise: float = 0.0, seed: int = 2
) -> list[list[float]]:
    """Points on the surface of a cylinder along given axis.

    Both theta and the axial position t are drawn from the RNG so that
    there is no deterministic correlation between angle and z-height
    (which would bias the covariance matrix and destabilise PCA-axis recovery).
    """
    import random
    rng = random.Random(seed)
    axis = _normalise([ax, ay, az])
    # Build orthonormal basis
    ref = [1.0, 0.0, 0.0] if abs(axis[2]) > 0.9 else [0.0, 0.0, 1.0]
    u = _normalise([
        axis[1]*ref[2] - axis[2]*ref[1],
        axis[2]*ref[0] - axis[0]*ref[2],
        axis[0]*ref[1] - axis[1]*ref[0],
    ])
    v = [
        axis[1]*u[2] - axis[2]*u[1],
        axis[2]*u[0] - axis[0]*u[2],
        axis[0]*u[1] - axis[1]*u[0],
    ]
    pts = []
    for _ in range(n):
        # Use random theta to avoid RNG-angle correlation bias
        theta = rng.uniform(0, 2 * math.pi)
        t = rng.uniform(-height/2, height/2)
        nr = r + (rng.gauss(0, noise) if noise else 0.0)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        p = [
            ox + cos_t*nr*u[0] + sin_t*nr*v[0] + t*axis[0],
            oy + cos_t*nr*u[1] + sin_t*nr*v[1] + t*axis[1],
            oz + cos_t*nr*u[2] + sin_t*nr*v[2] + t*axis[2],
        ]
        pts.append(p)
    return pts


# ===========================================================================
# SECTION 1: cloud_stats
# ===========================================================================

class TestCloudStats:
    def test_basic_stats(self):
        pts = [[0, 0, 0], [2, 4, 6], [1, 2, 3]]
        r = cloud_stats(pts)
        assert r["ok"] is True
        assert r["count"] == 3
        assert r["bbox"]["x_min"] == 0.0
        assert r["bbox"]["x_max"] == 2.0
        assert r["bbox"]["y_min"] == 0.0
        assert r["bbox"]["y_max"] == 4.0
        assert r["bbox"]["z_min"] == 0.0
        assert r["bbox"]["z_max"] == 6.0
        assert r["centroid"] == [1.0, 2.0, 3.0]

    def test_empty_cloud(self):
        r = cloud_stats([])
        assert r["ok"] is False
        assert "empty" in r["reason"].lower()

    def test_single_point(self):
        r = cloud_stats([[3.0, 4.0, 5.0]])
        assert r["ok"] is True
        assert r["count"] == 1
        assert r["centroid"] == [3.0, 4.0, 5.0]

    def test_negative_coords(self):
        pts = [[-1, -2, -3], [1, 2, 3]]
        r = cloud_stats(pts)
        assert r["ok"] is True
        assert r["bbox"]["x_min"] == -1.0
        assert r["bbox"]["x_max"] == 1.0


# ===========================================================================
# SECTION 2: fit_plane_direct
# ===========================================================================

class TestFitPlaneDirect:
    def test_exact_plane_z_equals_2(self):
        pts = _plane_pts(n=20, noise=0.0)
        r = fit_plane_direct(pts)
        assert r["ok"] is True
        assert r["primitive"] == "plane"
        # Normal should be (close to) [0,0,1] or [0,0,-1]
        n = r["normal"]
        assert abs(abs(n[2]) - 1.0) < 1e-6, f"Expected normal ≈ [0,0,±1], got {n}"
        # d = normal · centroid ≈ ±2
        assert abs(abs(r["d"]) - 2.0) < 1e-6
        assert r["residual"] < 1e-10

    def test_tilted_plane(self):
        # Plane: x + y + z = 3  → normal = [1/√3, 1/√3, 1/√3]
        pts = []
        for i in range(20):
            x = float(i)
            y = float(i % 5)
            z = 3.0 - x - y
            pts.append([x, y, z])
        r = fit_plane_direct(pts)
        assert r["ok"] is True
        n = r["normal"]
        expected = 1.0 / math.sqrt(3)
        # Check that normal is parallel to [1,1,1]
        dot_abs = abs(_dot(n, [1, 1, 1])) / math.sqrt(3)
        assert dot_abs > 0.9999, f"Normal not parallel to [1,1,1]: {n}"

    def test_too_few_points(self):
        r = fit_plane_direct([[0, 0, 0], [1, 0, 0]])
        assert r["ok"] is False
        assert "3" in r["reason"]

    def test_collinear_points(self):
        pts = [[float(i), 0.0, 0.0] for i in range(10)]
        r = fit_plane_direct(pts)
        assert r["ok"] is False
        assert "collinear" in r["reason"].lower() or "degenerate" in r["reason"].lower()

    def test_all_identical_points(self):
        pts = [[1.0, 2.0, 3.0]] * 10
        r = fit_plane_direct(pts)
        assert r["ok"] is False

    def test_inlier_ratio_is_1(self):
        pts = _plane_pts(n=30)
        r = fit_plane_direct(pts)
        assert r["ok"] is True
        assert r["inlier_ratio"] == 1.0


# ===========================================================================
# SECTION 3: ransac_fit_plane
# ===========================================================================

class TestRansacFitPlane:
    def test_clean_plane(self):
        pts = _plane_pts(n=50, noise=0.0)
        r = ransac_fit_plane(pts, threshold=0.01, seed=42)
        assert r["ok"] is True
        n = r["normal"]
        assert abs(abs(n[2]) - 1.0) < 0.01
        assert abs(abs(r["d"]) - 2.0) < 0.01

    def test_noisy_plane(self):
        pts = _plane_pts(n=100, noise=0.005, seed=7)
        r = ransac_fit_plane(pts, threshold=0.02, seed=42)
        assert r["ok"] is True
        assert r["inlier_ratio"] > 0.8
        # Normal should still be close to z-axis
        n = r["normal"]
        assert abs(abs(n[2]) - 1.0) < 0.1

    def test_deterministic_same_seed(self):
        pts = _plane_pts(n=40, noise=0.005, seed=3)
        r1 = ransac_fit_plane(pts, threshold=0.02, seed=99)
        r2 = ransac_fit_plane(pts, threshold=0.02, seed=99)
        assert r1["normal"] == r2["normal"]
        assert r1["d"] == r2["d"]
        assert r1["inlier_ratio"] == r2["inlier_ratio"]

    def test_different_seeds_may_differ(self):
        # With heavy noise, different seeds can produce different results
        # (Not guaranteed, but at least check it runs without error)
        pts = _plane_pts(n=30, noise=0.05, seed=5)
        r1 = ransac_fit_plane(pts, threshold=0.02, seed=1)
        r2 = ransac_fit_plane(pts, threshold=0.02, seed=9999)
        assert r1["ok"] is True
        assert r2["ok"] is True

    def test_too_few_points(self):
        r = ransac_fit_plane([[0, 0, 0], [1, 1, 1]])
        assert r["ok"] is False

    def test_plane_normal_within_tolerance(self):
        # Exact plane z = 0: all pts have z=0
        pts = [[float(i), float(j), 0.0] for i in range(5) for j in range(5)]
        r = ransac_fit_plane(pts, threshold=0.001, seed=42)
        assert r["ok"] is True
        n = r["normal"]
        assert abs(abs(n[2]) - 1.0) < 0.001
        assert abs(r["d"]) < 0.001


# ===========================================================================
# SECTION 4: fit_sphere_direct
# ===========================================================================

class TestFitSphereDirect:
    def test_exact_sphere(self):
        pts = _sphere_pts(cx=1.0, cy=2.0, cz=3.0, r=5.0, n=50, noise=0.0)
        r = fit_sphere_direct(pts)
        assert r["ok"] is True
        assert r["primitive"] == "sphere"
        c = r["centre"]
        assert abs(c[0] - 1.0) < 0.01
        assert abs(c[1] - 2.0) < 0.01
        assert abs(c[2] - 3.0) < 0.01
        assert abs(r["radius"] - 5.0) < 0.01
        assert r["residual"] < 0.01

    def test_too_few_points(self):
        r = fit_sphere_direct([[0,0,0],[1,0,0],[0,1,0]])
        assert r["ok"] is False
        assert "4" in r["reason"]

    def test_unit_sphere(self):
        # Unit sphere centred at origin
        pts = _sphere_pts(cx=0.0, cy=0.0, cz=0.0, r=1.0, n=60, noise=0.0)
        r = fit_sphere_direct(pts)
        assert r["ok"] is True
        c = r["centre"]
        assert abs(c[0]) < 0.01
        assert abs(c[1]) < 0.01
        assert abs(c[2]) < 0.01
        assert abs(r["radius"] - 1.0) < 0.01

    def test_inlier_ratio_is_1(self):
        pts = _sphere_pts(n=40)
        r = fit_sphere_direct(pts)
        assert r["ok"] is True
        assert r["inlier_ratio"] == 1.0


# ===========================================================================
# SECTION 5: ransac_fit_sphere
# ===========================================================================

class TestRansacFitSphere:
    def test_clean_sphere(self):
        pts = _sphere_pts(cx=0.0, cy=0.0, cz=0.0, r=3.0, n=60, noise=0.0)
        r = ransac_fit_sphere(pts, threshold=0.05, seed=42)
        assert r["ok"] is True
        c = r["centre"]
        assert abs(c[0]) < 0.1
        assert abs(c[1]) < 0.1
        assert abs(c[2]) < 0.1
        assert abs(r["radius"] - 3.0) < 0.1

    def test_noisy_sphere_centre_within_tol(self):
        pts = _sphere_pts(cx=2.0, cy=-1.0, cz=4.0, r=4.0, n=100, noise=0.02, seed=10)
        r = ransac_fit_sphere(pts, threshold=0.1, seed=42)
        assert r["ok"] is True
        c = r["centre"]
        assert abs(c[0] - 2.0) < 0.3
        assert abs(c[1] - (-1.0)) < 0.3
        assert abs(c[2] - 4.0) < 0.3
        assert abs(r["radius"] - 4.0) < 0.3

    def test_deterministic(self):
        pts = _sphere_pts(cx=1.0, cy=1.0, cz=1.0, r=2.0, n=50, noise=0.01)
        r1 = ransac_fit_sphere(pts, seed=77)
        r2 = ransac_fit_sphere(pts, seed=77)
        assert r1["centre"] == r2["centre"]
        assert r1["radius"] == r2["radius"]

    def test_too_few_points(self):
        r = ransac_fit_sphere([[0,0,0],[1,0,0],[0,1,0]])
        assert r["ok"] is False

    def test_inlier_ratio_noisy(self):
        # Add some outlier points far from the sphere
        pts = _sphere_pts(cx=0.0, cy=0.0, cz=0.0, r=5.0, n=80, noise=0.0)
        outliers = [[100.0, 100.0, 100.0]] * 5
        r = ransac_fit_sphere(pts + outliers, threshold=0.05, seed=42)
        assert r["ok"] is True
        # inlier_ratio should reflect that outliers are excluded
        assert r["inlier_ratio"] < 1.0


# ===========================================================================
# SECTION 6: fit_cylinder_direct
# ===========================================================================

class TestFitCylinderDirect:
    def test_exact_cylinder_z_axis(self):
        pts = _cylinder_pts(ax=0, ay=0, az=1, ox=0, oy=0, oz=0, r=3.0, height=10.0, n=80, noise=0.0)
        r = fit_cylinder_direct(pts)
        assert r["ok"] is True
        assert r["primitive"] == "cylinder"
        ax = r["axis"]
        # Axis should be close to [0,0,1] or [0,0,-1]
        assert abs(abs(ax[2]) - 1.0) < 0.05, f"Expected axis ≈ z, got {ax}"
        assert abs(r["radius"] - 3.0) < 0.1

    def test_too_few_points(self):
        r = fit_cylinder_direct([[1,0,0],[0,1,0],[0,0,1],[1,1,0],[1,0,1]])
        assert r["ok"] is False
        assert "6" in r["reason"]

    def test_cylinder_tilted_axis(self):
        # Cylinder along [1,1,0]/sqrt(2)
        pts = _cylinder_pts(ax=1, ay=1, az=0, ox=0, oy=0, oz=0, r=2.0, height=8.0, n=80, noise=0.0)
        r = fit_cylinder_direct(pts)
        assert r["ok"] is True
        ax = r["axis"]
        # Axis should be parallel to [1,1,0]
        expected = _normalise([1.0, 1.0, 0.0])
        dot = abs(_dot(ax, expected))
        assert dot > 0.97, f"Axis not parallel to [1,1,0]: {ax}, dot={dot}"
        assert abs(r["radius"] - 2.0) < 0.1

    def test_inlier_ratio_is_1(self):
        pts = _cylinder_pts(n=40, noise=0.0)
        r = fit_cylinder_direct(pts)
        assert r["ok"] is True
        assert r["inlier_ratio"] == 1.0


# ===========================================================================
# SECTION 7: ransac_fit_cylinder
# ===========================================================================

class TestRansacFitCylinder:
    def test_clean_cylinder(self):
        pts = _cylinder_pts(ax=0, ay=0, az=1, r=2.0, n=80, noise=0.0)
        r = ransac_fit_cylinder(pts, threshold=0.05, seed=42)
        assert r["ok"] is True
        ax = r["axis"]
        assert abs(abs(ax[2]) - 1.0) < 0.1
        assert abs(r["radius"] - 2.0) < 0.1

    def test_noisy_cylinder_axis_recovered(self):
        # Centred cylinder with light noise — axis must be z
        pts = _cylinder_pts(ax=0, ay=0, az=1, ox=0.0, oy=0.0, oz=0.0, r=4.0, height=12.0, n=100, noise=0.005)
        r = ransac_fit_cylinder(pts, threshold=0.1, seed=42)
        assert r["ok"] is True
        ax = r["axis"]
        assert abs(abs(ax[2]) - 1.0) < 0.1, f"Expected z-axis, got {ax}"
        assert abs(r["radius"] - 4.0) < 0.3

    def test_deterministic(self):
        pts = _cylinder_pts(n=60, noise=0.01, seed=5)
        r1 = ransac_fit_cylinder(pts, seed=13)
        r2 = ransac_fit_cylinder(pts, seed=13)
        assert r1["axis"] == r2["axis"]
        assert r1["radius"] == r2["radius"]
        assert r1["inlier_ratio"] == r2["inlier_ratio"]

    def test_too_few_points(self):
        r = ransac_fit_cylinder([[1,0,0],[0,1,0],[0,0,1],[1,1,0],[1,0,1]])
        assert r["ok"] is False

    def test_outlier_rejection(self):
        pts = _cylinder_pts(ax=0, ay=0, az=1, r=3.0, n=70, noise=0.0)
        outliers = [[50.0, 50.0, 50.0]] * 5
        r = ransac_fit_cylinder(pts + outliers, threshold=0.05, seed=42)
        assert r["ok"] is True
        assert r["inlier_ratio"] < 1.0


# ===========================================================================
# SECTION 8: greedy_segment
# ===========================================================================

class TestGreedySegment:
    def test_pure_plane_cloud(self):
        pts = _plane_pts(n=60, noise=0.001)
        r = greedy_segment(pts, primitives=["plane"], threshold=0.01, seed=42)
        assert r["ok"] is True
        assert len(r["segments"]) >= 1
        assert r["segments"][0]["primitive"] == "plane"

    def test_pure_sphere_cloud(self):
        pts = _sphere_pts(n=60, noise=0.0)
        r = greedy_segment(pts, primitives=["sphere"], threshold=0.05, seed=42)
        assert r["ok"] is True
        assert len(r["segments"]) >= 1
        assert r["segments"][0]["primitive"] == "sphere"

    def test_plane_plus_sphere(self):
        # Plane z=0, sphere centred at (20,20,20) radius 2
        plane_pts = [[float(i), float(j), 0.0] for i in range(8) for j in range(8)]
        sphere_pts = _sphere_pts(cx=20.0, cy=20.0, cz=20.0, r=2.0, n=50, noise=0.0)
        all_pts = plane_pts + sphere_pts
        r = greedy_segment(all_pts, primitives=["plane", "sphere"], threshold=0.05, seed=42)
        assert r["ok"] is True
        found_types = {seg["primitive"] for seg in r["segments"]}
        assert "plane" in found_types or "sphere" in found_types
        assert r["total_count"] == len(all_pts)

    def test_segment_counts_sum_correctly(self):
        pts = _plane_pts(n=50, noise=0.001)
        r = greedy_segment(pts, threshold=0.01, seed=42)
        assert r["ok"] is True
        assigned = sum(seg["inlier_count"] for seg in r["segments"])
        assert assigned + r["unassigned_count"] == r["total_count"]

    def test_too_few_points(self):
        r = greedy_segment([[0,0,0],[1,0,0]])
        assert r["ok"] is False

    def test_segment_splits_plane_and_sphere_cloud(self):
        """Mixed cloud: plane + sphere — greedy finds both."""
        # 50 pts on plane z=0, 50 pts on sphere at (30,30,30) r=3
        plane_pts = _plane_pts(n=50, noise=0.001, seed=10)
        # Force z=0 exactly
        plane_pts = [[p[0], p[1], 0.0] for p in plane_pts]
        sphere_pts = _sphere_pts(cx=30.0, cy=30.0, cz=30.0, r=3.0, n=50, noise=0.0)
        all_pts = plane_pts + sphere_pts
        r = greedy_segment(all_pts, primitives=["plane", "sphere"], threshold=0.05, seed=42)
        assert r["ok"] is True
        assert len(r["segments"]) >= 1
        found = {seg["primitive"] for seg in r["segments"]}
        # At least one primitive should be found
        assert len(found) >= 1

    def test_default_primitives(self):
        pts = _plane_pts(n=40)
        r = greedy_segment(pts, threshold=0.01, seed=42)  # no primitives arg
        assert r["ok"] is True

    def test_segment_fields_plane(self):
        pts = _plane_pts(n=40, noise=0.001)
        r = greedy_segment(pts, primitives=["plane"], threshold=0.02, seed=42)
        assert r["ok"] is True
        if r["segments"]:
            seg = r["segments"][0]
            assert "normal" in seg
            assert "d" in seg
            assert "centre" in seg
            assert "inlier_count" in seg
            assert "residual" in seg

    def test_segment_fields_sphere(self):
        pts = _sphere_pts(n=60, noise=0.0)
        r = greedy_segment(pts, primitives=["sphere"], threshold=0.05, seed=42)
        assert r["ok"] is True
        if r["segments"]:
            seg = r["segments"][0]
            assert "centre" in seg
            assert "radius" in seg

    def test_segment_fields_cylinder(self):
        pts = _cylinder_pts(n=80, noise=0.0)
        r = greedy_segment(pts, primitives=["cylinder"], threshold=0.05, seed=42)
        assert r["ok"] is True
        if r["segments"]:
            seg = r["segments"][0]
            assert "axis" in seg
            assert "axis_point" in seg
            assert "radius" in seg


# ===========================================================================
# SECTION 9: LLM tool wrappers
# ===========================================================================

class TestScanLoadTool:
    def test_basic(self):
        ctx = _make_ctx()
        pts = [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0], [2.0, 4.0, 6.0]]
        d = _ok(_run(run_scan_load(ctx, _args(points=pts))))
        assert d["count"] == 3
        assert d["bbox"]["x_min"] == 0.0
        assert d["centroid"] == [1.0, 2.0, 3.0]

    def test_bad_json(self):
        ctx = _make_ctx()
        d = _err(_run(run_scan_load(ctx, b"not json")))

    def test_empty_list(self):
        ctx = _make_ctx()
        d = _err(_run(run_scan_load(ctx, _args(points=[]))))

    def test_wrong_point_shape(self):
        ctx = _make_ctx()
        d = _err(_run(run_scan_load(ctx, _args(points=[[1, 2]]))))

    def test_missing_points_key(self):
        ctx = _make_ctx()
        d = _err(_run(run_scan_load(ctx, _args())))


class TestScanFitPlaneTool:
    def test_clean_plane(self):
        ctx = _make_ctx()
        pts = _plane_pts(n=30, noise=0.0)
        d = _ok(_run(run_scan_fit_plane(ctx, _args(points=pts, threshold=0.01, seed=42))))
        assert d["primitive"] == "plane"
        n = d["normal"]
        assert abs(abs(n[2]) - 1.0) < 0.01

    def test_too_few_points(self):
        ctx = _make_ctx()
        d = _err(_run(run_scan_fit_plane(ctx, _args(points=[[0,0,0],[1,1,1]]))))

    def test_collinear(self):
        ctx = _make_ctx()
        pts = [[float(i), 0.0, 0.0] for i in range(10)]
        d = _err(_run(run_scan_fit_plane(ctx, _args(points=pts))))

    def test_default_args(self):
        ctx = _make_ctx()
        pts = _plane_pts(n=20)
        d = _ok(_run(run_scan_fit_plane(ctx, _args(points=pts))))
        assert "inlier_ratio" in d

    def test_residual_field(self):
        ctx = _make_ctx()
        pts = _plane_pts(n=30, noise=0.0)
        d = _ok(_run(run_scan_fit_plane(ctx, _args(points=pts, seed=42))))
        assert d["residual"] < 1e-8


class TestScanFitSphereTool:
    def test_clean_sphere(self):
        ctx = _make_ctx()
        pts = _sphere_pts(cx=1.0, cy=2.0, cz=3.0, r=5.0, n=50, noise=0.0)
        d = _ok(_run(run_scan_fit_sphere(ctx, _args(points=pts, threshold=0.05, seed=42))))
        assert d["primitive"] == "sphere"
        c = d["centre"]
        assert abs(c[0] - 1.0) < 0.1
        assert abs(c[1] - 2.0) < 0.1
        assert abs(c[2] - 3.0) < 0.1
        assert abs(d["radius"] - 5.0) < 0.1

    def test_too_few_points(self):
        ctx = _make_ctx()
        d = _err(_run(run_scan_fit_sphere(ctx, _args(points=[[0,0,0],[1,0,0],[0,1,0]]))))

    def test_inlier_ratio_in_output(self):
        ctx = _make_ctx()
        pts = _sphere_pts(n=40)
        d = _ok(_run(run_scan_fit_sphere(ctx, _args(points=pts, seed=42))))
        assert 0.0 < d["inlier_ratio"] <= 1.0

    def test_noisy_sphere(self):
        ctx = _make_ctx()
        pts = _sphere_pts(cx=0.0, cy=0.0, cz=0.0, r=3.0, n=80, noise=0.01)
        d = _ok(_run(run_scan_fit_sphere(ctx, _args(points=pts, threshold=0.05, seed=42))))
        assert abs(d["radius"] - 3.0) < 0.3


class TestScanFitCylinderTool:
    def test_clean_cylinder(self):
        ctx = _make_ctx()
        pts = _cylinder_pts(ax=0, ay=0, az=1, r=2.0, n=80, noise=0.0)
        d = _ok(_run(run_scan_fit_cylinder(ctx, _args(points=pts, threshold=0.05, seed=42))))
        assert d["primitive"] == "cylinder"
        ax = d["axis"]
        assert abs(abs(ax[2]) - 1.0) < 0.1
        assert abs(d["radius"] - 2.0) < 0.1

    def test_too_few_points(self):
        ctx = _make_ctx()
        d = _err(_run(run_scan_fit_cylinder(ctx, _args(points=[[1,0,0],[0,1,0],[0,0,1],[1,1,0],[1,0,1]]))))

    def test_has_axis_point(self):
        ctx = _make_ctx()
        pts = _cylinder_pts(n=60, noise=0.0)
        d = _ok(_run(run_scan_fit_cylinder(ctx, _args(points=pts, seed=42))))
        assert "axis_point" in d
        assert len(d["axis_point"]) == 3

    def test_noisy_cylinder(self):
        ctx = _make_ctx()
        pts = _cylinder_pts(ax=0, ay=0, az=1, r=4.0, n=100, noise=0.005)
        d = _ok(_run(run_scan_fit_cylinder(ctx, _args(points=pts, threshold=0.1, seed=42))))
        assert abs(d["radius"] - 4.0) < 0.5


class TestScanSegmentTool:
    def test_plane_cloud(self):
        ctx = _make_ctx()
        pts = _plane_pts(n=50, noise=0.001)
        d = _ok(_run(run_scan_segment(ctx, _args(points=pts, primitives=["plane"], threshold=0.01, seed=42))))
        assert len(d["segments"]) >= 1

    def test_too_few_points(self):
        ctx = _make_ctx()
        d = _err(_run(run_scan_segment(ctx, _args(points=[[0,0,0],[1,0,0]]))))

    def test_total_count_matches(self):
        ctx = _make_ctx()
        pts = _plane_pts(n=40, noise=0.001)
        d = _ok(_run(run_scan_segment(ctx, _args(points=pts, seed=42))))
        assigned = sum(seg["inlier_count"] for seg in d["segments"])
        assert assigned + d["unassigned_count"] == d["total_count"]

    def test_bad_primitives_arg(self):
        ctx = _make_ctx()
        d = _err(_run(run_scan_segment(ctx, _args(points=[[0,0,0],[1,0,0],[0,1,0],[1,1,0]], primitives="plane"))))

    def test_default_primitives_runs(self):
        ctx = _make_ctx()
        pts = _sphere_pts(n=50, noise=0.0)
        d = _ok(_run(run_scan_segment(ctx, _args(points=pts, threshold=0.05, seed=42))))
        assert "segments" in d
