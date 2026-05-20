"""
Tests for kerf_cad_core.reverse_engineering — reverse-engineering pipeline.

All tests are pure-Python, hermetic: no OCC, no DB, no network.

Coverage:
  - PCD / PLY file I/O (ASCII)
  - UnsupportedFormatError for binary variants
  - Cone fitting (RANSAC + closed-form)
  - Sequential RANSAC segmentation
  - Feature tree mapping (segment → feature node)
  - Round-trip: synthetic cube + cylinder cloud → recognize → re-sample
    → Hausdorff distance ≤ 1e-3 vs original surface
  - hausdorff_distance utility

Author: imranparuk
"""
from __future__ import annotations

import math
import random

import pytest

from kerf_cad_core.reverse_engineering.io import (
    UnsupportedFormatError,
    load_pcd,
    load_ply,
    load_point_cloud,
)
from kerf_cad_core.reverse_engineering.segmentation import (
    fit_cone_direct,
    ransac_fit_cone,
    sequential_ransac,
    _dist_to_cone,
)
from kerf_cad_core.reverse_engineering.feature_map import (
    segment_to_feature,
    segments_to_feature_tree,
)
from kerf_cad_core.reverse_engineering.pipeline import (
    recognize,
    sample_feature_tree,
    hausdorff_distance,
    max_point_to_surface_distance,
)


# ===========================================================================
# Helpers / Fixtures
# ===========================================================================

def _normalise(v):
    n = math.sqrt(sum(x*x for x in v))
    return [x/n for x in v]


def _cube_surface_pts(side: float = 10.0, n_per_face: int = 40) -> list[list[float]]:
    """Sample n_per_face points uniformly on each face of an axis-aligned cube.

    The cube spans [0, side]^3.  6 faces × n_per_face = 6*n_per_face total.
    Each face is on a coordinate plane with z/y/x fixed at 0 or side.
    """
    rng = random.Random(1)
    pts: list[list[float]] = []
    for _ in range(n_per_face):
        u = rng.uniform(0, side)
        v = rng.uniform(0, side)
        # Six faces
        pts.append([u, v, 0.0])          # z=0
        pts.append([u, v, side])         # z=side
        pts.append([u, 0.0, v])          # y=0
        pts.append([u, side, v])         # y=side
        pts.append([0.0, u, v])          # x=0
        pts.append([side, u, v])         # x=side
    return pts


def _cylinder_pts(
    cx: float = 5.0, cy: float = 5.0, r: float = 2.0,
    z_min: float = 2.0, z_max: float = 8.0, n: int = 200,
) -> list[list[float]]:
    """Sample n points on the lateral surface of a vertical cylinder."""
    rng = random.Random(2)
    pts = []
    for _ in range(n):
        theta = rng.uniform(0.0, 2.0 * math.pi)
        z = rng.uniform(z_min, z_max)
        pts.append([cx + r * math.cos(theta), cy + r * math.sin(theta), z])
    return pts


def _cone_pts(
    apex=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0),
    half_angle_deg: float = 30.0, height: float = 5.0, n: int = 80,
) -> list[list[float]]:
    """Sample n points on a cone lateral surface."""
    rng = random.Random(3)
    ax = _normalise(list(axis))
    ref = [1.0, 0.0, 0.0]
    if abs(ax[0]) > 0.9:
        ref = [0.0, 1.0, 0.0]
    # Build u, v
    u = _normalise([
        ax[1]*ref[2] - ax[2]*ref[1],
        ax[2]*ref[0] - ax[0]*ref[2],
        ax[0]*ref[1] - ax[1]*ref[0],
    ])
    v = [
        ax[1]*u[2] - ax[2]*u[1],
        ax[2]*u[0] - ax[0]*u[2],
        ax[0]*u[1] - ax[1]*u[0],
    ]
    tan_ha = math.tan(math.radians(half_angle_deg))
    pts = []
    for _ in range(n):
        h = rng.uniform(0.1, height)  # skip apex exactly (r=0 is degenerate)
        r = h * tan_ha
        theta = rng.uniform(0.0, 2.0 * math.pi)
        p = [
            apex[0] + ax[0]*h + r*math.cos(theta)*u[0] + r*math.sin(theta)*v[0],
            apex[1] + ax[1]*h + r*math.cos(theta)*u[1] + r*math.sin(theta)*v[1],
            apex[2] + ax[2]*h + r*math.cos(theta)*u[2] + r*math.sin(theta)*v[2],
        ]
        pts.append(p)
    return pts


# ===========================================================================
# SECTION 1: PCD I/O
# ===========================================================================

class TestLoadPcd:
    def test_minimal_pcd(self):
        content = b"""\
# .PCD v0.7
VERSION 0.7
FIELDS x y z
SIZE 4 4 4
TYPE F F F
COUNT 1 1 1
WIDTH 3
HEIGHT 1
POINTS 3
DATA ascii
1.0 2.0 3.0
4.0 5.0 6.0
7.0 8.0 9.0
"""
        pts = load_pcd(content)
        assert len(pts) == 3
        assert pts[0] == [1.0, 2.0, 3.0]
        assert pts[1] == [4.0, 5.0, 6.0]
        assert pts[2] == [7.0, 8.0, 9.0]

    def test_extra_fields_ignored(self):
        content = b"""\
VERSION 0.7
FIELDS x y z intensity
SIZE 4 4 4 4
TYPE F F F F
COUNT 1 1 1 1
WIDTH 2
HEIGHT 1
POINTS 2
DATA ascii
1.0 2.0 3.0 0.5
4.0 5.0 6.0 0.8
"""
        pts = load_pcd(content)
        assert len(pts) == 2
        assert pts[0] == [1.0, 2.0, 3.0]

    def test_binary_raises(self):
        content = b"""\
VERSION 0.7
FIELDS x y z
SIZE 4 4 4
TYPE F F F
COUNT 1 1 1
WIDTH 1
HEIGHT 1
POINTS 1
DATA binary
\x00\x00\x80\x3f\x00\x00\x00\x40\x00\x00\x40\x40
"""
        with pytest.raises(UnsupportedFormatError):
            load_pcd(content)

    def test_missing_data_raises(self):
        content = b"VERSION 0.7\nFIELDS x y z\n"
        with pytest.raises(ValueError):
            load_pcd(content)

    def test_xyz_fields_required(self):
        content = b"""\
VERSION 0.7
FIELDS a b c
SIZE 4 4 4
TYPE F F F
COUNT 1 1 1
WIDTH 1
HEIGHT 1
POINTS 1
DATA ascii
1 2 3
"""
        with pytest.raises(ValueError, match="x/y/z"):
            load_pcd(content)

    def test_empty_data(self):
        content = b"""\
VERSION 0.7
FIELDS x y z
SIZE 4 4 4
TYPE F F F
COUNT 1 1 1
WIDTH 0
HEIGHT 1
POINTS 0
DATA ascii
"""
        pts = load_pcd(content)
        assert pts == []

    def test_negative_coords(self):
        content = b"""\
VERSION 0.7
FIELDS x y z
SIZE 4 4 4
TYPE F F F
COUNT 1 1 1
WIDTH 2
HEIGHT 1
POINTS 2
DATA ascii
-1.5 -2.5 -3.5
0.0 0.0 0.0
"""
        pts = load_pcd(content)
        assert pts[0][0] == -1.5
        assert pts[0][2] == -3.5


# ===========================================================================
# SECTION 2: PLY I/O
# ===========================================================================

class TestLoadPly:
    def _make_ascii_ply(self, pts: list) -> bytes:
        lines = [
            "ply",
            "format ascii 1.0",
            f"element vertex {len(pts)}",
            "property float x",
            "property float y",
            "property float z",
            "end_header",
        ]
        for p in pts:
            lines.append(f"{p[0]} {p[1]} {p[2]}")
        return "\n".join(lines).encode()

    def test_basic_ply(self):
        content = self._make_ascii_ply([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        pts = load_ply(content)
        assert len(pts) == 2
        assert pts[0] == [1.0, 2.0, 3.0]

    def test_extra_properties_ignored(self):
        content = (
            b"ply\nformat ascii 1.0\n"
            b"element vertex 2\n"
            b"property float x\n"
            b"property float y\n"
            b"property float z\n"
            b"property uchar red\n"
            b"property uchar green\n"
            b"property uchar blue\n"
            b"end_header\n"
            b"1.0 2.0 3.0 255 0 0\n"
            b"4.0 5.0 6.0 0 255 0\n"
        )
        pts = load_ply(content)
        assert pts[0] == [1.0, 2.0, 3.0]

    def test_binary_ply_raises(self):
        content = (
            b"ply\nformat binary_little_endian 1.0\n"
            b"element vertex 1\n"
            b"property float x\n"
            b"property float y\n"
            b"property float z\n"
            b"end_header\n"
            b"\x00\x00\x80\x3f\x00\x00\x00\x40\x00\x00\x40\x40"
        )
        with pytest.raises(UnsupportedFormatError):
            load_ply(content)

    def test_not_ply_raises(self):
        with pytest.raises(ValueError, match="ply"):
            load_ply(b"not a ply file\n")

    def test_missing_xyz_raises(self):
        content = (
            b"ply\nformat ascii 1.0\n"
            b"element vertex 1\n"
            b"property float a\n"
            b"property float b\n"
            b"end_header\n"
            b"1 2\n"
        )
        with pytest.raises(ValueError, match="x, y, z"):
            load_ply(content)

    def test_zero_vertex_count(self):
        content = (
            b"ply\nformat ascii 1.0\n"
            b"element vertex 0\n"
            b"property float x\n"
            b"property float y\n"
            b"property float z\n"
            b"end_header\n"
        )
        pts = load_ply(content)
        assert pts == []


# ===========================================================================
# SECTION 3: load_point_cloud dispatch
# ===========================================================================

class TestLoadPointCloud:
    def test_dispatch_pcd_bytes(self):
        content = (
            b"VERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\n"
            b"COUNT 1 1 1\nWIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA ascii\n1 2 3\n"
        )
        pts = load_point_cloud(content)
        assert pts == [[1.0, 2.0, 3.0]]

    def test_dispatch_ply_bytes(self):
        content = (
            b"ply\nformat ascii 1.0\nelement vertex 1\n"
            b"property float x\nproperty float y\nproperty float z\n"
            b"end_header\n5 6 7\n"
        )
        pts = load_point_cloud(content)
        assert pts == [[5.0, 6.0, 7.0]]


# ===========================================================================
# SECTION 4: Cone fitting
# ===========================================================================

class TestFitConeDirect:
    def test_basic_cone(self):
        pts = _cone_pts(
            apex=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0),
            half_angle_deg=30.0, height=5.0, n=80,
        )
        r = fit_cone_direct(pts)
        assert r["ok"] is True, f"cone fit failed: {r.get('reason')}"
        assert r["primitive"] == "cone"
        assert abs(math.degrees(r["half_angle"]) - 30.0) < 5.0
        # Apex should be near origin
        apex = r["apex"]
        apex_dist = math.sqrt(sum(x*x for x in apex))
        assert apex_dist < 1.0, f"Apex far from origin: {apex}"

    def test_too_few_points(self):
        r = fit_cone_direct([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[1,1,0]])
        assert r["ok"] is False
        assert "6" in r["reason"]

    def test_residual_small_for_exact_cone(self):
        pts = _cone_pts(half_angle_deg=20.0, height=4.0, n=100)
        r = fit_cone_direct(pts)
        assert r["ok"] is True
        assert r["residual"] < 0.2  # closed-form fit, not RANSAC

    def test_dist_to_cone_zero_on_surface(self):
        # A point on the cone surface: at height h, radius h * tan(30°)
        h = 2.0
        half_angle = math.radians(30.0)
        r_at_h = h * math.tan(half_angle)
        # apex at origin, axis = z
        apex = [0.0, 0.0, 0.0]
        axis = [0.0, 0.0, 1.0]
        p = [r_at_h, 0.0, h]
        d = _dist_to_cone(p, apex, axis, half_angle)
        assert d < 1e-10, f"dist should be 0 on surface, got {d}"


class TestRansacFitCone:
    def test_clean_cone(self):
        pts = _cone_pts(
            apex=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0),
            half_angle_deg=25.0, height=6.0, n=100,
        )
        # Use a looser threshold (0.2) — the pure-Python linear cone fitter has
        # ~0.8° accuracy, causing ~0.05–0.15 residuals per point for typical
        # heights.  A threshold of 0.2 captures ≥ 70% of the inliers.
        r = ransac_fit_cone(pts, threshold=0.2, seed=42)
        assert r["ok"] is True
        assert r["inlier_ratio"] > 0.7
        assert abs(math.degrees(r["half_angle"]) - 25.0) < 8.0

    def test_too_few_points(self):
        r = ransac_fit_cone([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[1,1,0]])
        assert r["ok"] is False

    def test_deterministic(self):
        pts = _cone_pts(n=80)
        r1 = ransac_fit_cone(pts, seed=99)
        r2 = ransac_fit_cone(pts, seed=99)
        assert r1["half_angle"] == r2["half_angle"]
        assert r1["inlier_ratio"] == r2["inlier_ratio"]


# ===========================================================================
# SECTION 5: Sequential RANSAC
# ===========================================================================

class TestSequentialRansac:
    def test_pure_cylinder_cloud(self):
        pts = _cylinder_pts(n=200)
        r = sequential_ransac(pts, primitives=["cylinder"], threshold=0.05, seed=42)
        assert r["ok"] is True
        assert r["segment_count"] >= 1
        found = [s["primitive"] for s in r["segments"]]
        assert "cylinder" in found

    def test_pure_sphere_cloud(self):
        from kerf_cad_core.scan.fit import _normalise
        import math
        # Unit sphere at origin
        golden = math.pi * (3 - math.sqrt(5))
        n = 80
        pts = []
        for i in range(n):
            y_f = 1 - (i / (n - 1)) * 2
            rad = math.sqrt(max(0, 1 - y_f*y_f))
            theta = golden * i
            pts.append([math.cos(theta) * rad * 5.0, y_f * 5.0, math.sin(theta) * rad * 5.0])
        r = sequential_ransac(pts, primitives=["sphere"], threshold=0.1, seed=42)
        assert r["ok"] is True
        assert r["segment_count"] >= 1

    def test_plane_plus_cylinder(self):
        """Mixed cloud: plane z=0 + cylinder at (20,20) r=2."""
        plane_pts = [[float(i), float(j), 0.0] for i in range(10) for j in range(10)]
        cyl_pts = _cylinder_pts(cx=20.0, cy=20.0, r=2.0, z_min=0.0, z_max=10.0, n=150)
        all_pts = plane_pts + cyl_pts
        r = sequential_ransac(
            all_pts,
            primitives=["plane", "cylinder"],
            threshold=0.05, seed=42,
        )
        assert r["ok"] is True
        found = {s["primitive"] for s in r["segments"]}
        # At least one primitive found
        assert len(found) >= 1

    def test_too_few_points(self):
        r = sequential_ransac([[0, 0, 0], [1, 0, 0]])
        assert r["ok"] is False

    def test_count_consistency(self):
        pts = _cube_surface_pts(side=10.0, n_per_face=20)
        r = sequential_ransac(pts, primitives=["plane"], threshold=0.05, seed=42)
        assert r["ok"] is True
        assigned = sum(s["inlier_count"] for s in r["segments"])
        assert assigned + len(r["unassigned"]) == r["total_count"]

    def test_segment_has_required_fields(self):
        pts = _cylinder_pts(n=100)
        r = sequential_ransac(pts, primitives=["cylinder"], threshold=0.05, seed=42)
        assert r["ok"] is True
        if r["segments"]:
            seg = r["segments"][0]
            assert "primitive" in seg
            assert "inlier_count" in seg
            assert "inlier_fraction" in seg
            assert "residual" in seg
            assert "axis" in seg
            assert "radius" in seg


# ===========================================================================
# SECTION 6: Feature mapping
# ===========================================================================

class TestSegmentToFeature:
    def _plane_seg(self):
        return {
            "primitive": "plane",
            "normal": [0.0, 0.0, 1.0],
            "d": 5.0,
            "centre": [2.0, 3.0, 5.0],
            "extent": 2.0,
            "inlier_count": 50,
            "residual": 0.001,
        }

    def _cylinder_seg(self):
        return {
            "primitive": "cylinder",
            "axis": [0.0, 0.0, 1.0],
            "axis_point": [0.0, 0.0, 0.0],
            "radius": 3.0,
            "height": 10.0,
            "inlier_count": 100,
            "residual": 0.002,
        }

    def _sphere_seg(self):
        return {
            "primitive": "sphere",
            "centre": [1.0, 2.0, 3.0],
            "radius": 4.0,
            "inlier_count": 60,
            "residual": 0.001,
        }

    def _cone_seg(self):
        return {
            "primitive": "cone",
            "apex": [0.0, 0.0, 0.0],
            "axis": [0.0, 0.0, 1.0],
            "half_angle": math.radians(30.0),
            "height": 5.0,
            "inlier_count": 40,
            "residual": 0.003,
        }

    def test_plane_to_extrude(self):
        node = segment_to_feature(self._plane_seg(), 0)
        assert node["id"] == "plane-0"
        assert node["op"] == "extrude"
        assert node["normal"] == [0.0, 0.0, 1.0]
        assert node["d"] == 5.0
        assert node["source"] == "reverse_engineering_v1"

    def test_cylinder_to_revolve(self):
        node = segment_to_feature(self._cylinder_seg(), 1)
        assert node["id"] == "cylinder-1"
        assert node["op"] == "revolve"
        assert node["radius"] == 3.0
        assert node["height"] == 10.0

    def test_sphere_node(self):
        node = segment_to_feature(self._sphere_seg(), 2)
        assert node["id"] == "sphere-2"
        assert node["op"] == "sphere"
        assert node["radius"] == 4.0
        assert node["centre"] == [1.0, 2.0, 3.0]

    def test_cone_node(self):
        node = segment_to_feature(self._cone_seg(), 3)
        assert node["id"] == "cone-3"
        assert node["op"] == "cone"
        assert abs(node["half_angle_deg"] - 30.0) < 0.001
        assert node["height"] == 5.0

    def test_unknown_primitive_raises(self):
        with pytest.raises(ValueError, match="unrecognised primitive"):
            segment_to_feature({"primitive": "torus", "inlier_count": 10, "residual": 0.01}, 0)

    def test_tree_ordering(self):
        segs = [
            self._plane_seg(),
            self._cylinder_seg(),
            self._sphere_seg(),
        ]
        tree = segments_to_feature_tree(segs)
        assert tree[0]["id"] == "plane-0"
        assert tree[1]["id"] == "cylinder-1"
        assert tree[2]["id"] == "sphere-2"

    def test_inlier_count_preserved(self):
        node = segment_to_feature(self._plane_seg(), 0)
        assert node["inlier_count"] == 50

    def test_residual_preserved(self):
        node = segment_to_feature(self._cylinder_seg(), 0)
        assert node["residual"] == 0.002


# ===========================================================================
# SECTION 7: Pipeline recognize()
# ===========================================================================

class TestRecognize:
    def test_cylinder_cloud(self):
        pts = _cylinder_pts(n=200)
        res = recognize(pts, primitives=["cylinder"], threshold=0.05, seed=42)
        assert res["ok"] is True
        assert res["segment_count"] >= 1
        assert len(res["feature_tree"]) >= 1
        ft = res["feature_tree"]
        assert any(n["op"] == "revolve" for n in ft)

    def test_feature_tree_has_ids(self):
        pts = _cylinder_pts(n=100)
        res = recognize(pts, primitives=["cylinder"], threshold=0.05, seed=42)
        assert res["ok"] is True
        for node in res["feature_tree"]:
            assert "id" in node
            assert "op" in node
            assert "source" in node

    def test_too_few_points(self):
        res = recognize([[0, 0, 0], [1, 0, 0]])
        assert res["ok"] is False

    def test_unassigned_count_consistent(self):
        pts = _cube_surface_pts(side=5.0, n_per_face=15) + _cylinder_pts(
            cx=20.0, cy=20.0, r=2.0, z_min=0, z_max=5, n=100
        )
        res = recognize(pts, primitives=["plane", "cylinder"], threshold=0.05, seed=42)
        assert res["ok"] is True
        assert res["unassigned_count"] + sum(
            n["inlier_count"] for n in res["feature_tree"]
        ) == res["total_count"]


# ===========================================================================
# SECTION 8: Hausdorff distance
# ===========================================================================

class TestHausdorffDistance:
    def test_identical_clouds(self):
        pts = [[float(i), 0.0, 0.0] for i in range(10)]
        assert hausdorff_distance(pts, pts) == 0.0

    def test_shifted_cloud(self):
        a = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
        b = [[0.5, 0.0, 0.0], [1.5, 0.0, 0.0]]
        # min dist from [0,0,0] to b is 0.5; from [1,0,0] to b is 0.5
        # min dist from [0.5,0,0] to a is 0.5; from [1.5,0,0] to a is 0.5
        h = hausdorff_distance(a, b)
        assert abs(h - 0.5) < 1e-10

    def test_unit_sphere_hausdorff_similar_samples(self):
        # Two sets of points on the unit sphere should have small hausdorff
        golden = math.pi * (3 - math.sqrt(5))
        n = 100
        def sphere_pts(offset):
            pts = []
            for i in range(n):
                y_f = 1 - (i / (n - 1)) * 2
                rad = math.sqrt(max(0, 1 - y_f*y_f))
                theta = golden * (i + offset)
                pts.append([math.cos(theta) * rad, y_f, math.sin(theta) * rad])
            return pts
        a = sphere_pts(0)
        b = sphere_pts(1)
        h = hausdorff_distance(a, b)
        # Two close samplings of unit sphere should be within 0.25
        assert h < 0.25

    def test_empty_cloud_returns_inf(self):
        pts = [[0.0, 0.0, 0.0]]
        assert hausdorff_distance([], pts) == float("inf")


# ===========================================================================
# SECTION 9: Round-trip oracle — cube + cylinder
# ===========================================================================

class TestRoundTrip:
    """
    Key requirement from T-332 v1 DoD:

    A known synthetic cube + cylinder point cloud → recognise → re-evaluate
    the feature tree → max point-to-surface distance ≤ 1e-3 vs the original
    sampled surface.

    Oracle method: ``max_point_to_surface_distance(original_pts, feature_tree)``
    computes the exact analytic distance from each original point to its nearest
    fitted surface.  This is the correct round-trip metric because a finite-
    density re-sampling always has non-zero grid spacing, so comparing two
    sampled clouds would always give Hausdorff > grid_spacing/2.
    """

    def test_cylinder_round_trip(self):
        """Cylinder: sample → recognize → max point-to-surface distance ≤ 1e-3."""
        r = 3.0
        height = 10.0
        # Dense, noise-free sample on lateral surface
        n_theta, n_h = 50, 20
        pts = []
        for it in range(n_theta):
            theta = 2.0 * math.pi * it / n_theta
            for ih in range(n_h):
                h = ih * height / max(n_h - 1, 1)
                pts.append([r * math.cos(theta), r * math.sin(theta), h])

        res = recognize(pts, primitives=["cylinder"], threshold=0.05, seed=42)
        assert res["ok"] is True, f"recognize failed: {res.get('reason')}"
        assert len(res["feature_tree"]) >= 1, "no features recognised"

        # Find the cylinder feature
        cyl_nodes = [n for n in res["feature_tree"] if n["op"] == "revolve"]
        assert cyl_nodes, "no revolve feature in tree"

        node = cyl_nodes[0]
        # Recovered radius should be close
        assert abs(node["radius"] - r) < 0.05, f"radius mismatch: {node['radius']} vs {r}"

        # Max point-to-surface distance oracle
        d = max_point_to_surface_distance(pts, res["feature_tree"])
        assert d <= 1e-3, (
            f"Round-trip max-point-to-surface {d:.6f} > 1e-3 — "
            f"recovered radius={node['radius']:.4f} (expected {r}), "
            f"recovered axis={node['axis']}"
        )

    def test_plane_face_round_trip(self):
        """Single plane face: sample → recognize → max point-to-surface distance ≤ 1e-3."""
        # Dense grid on z=0 plane, [-5,5]²
        n_side = 20
        pts = []
        for i in range(n_side):
            for j in range(n_side):
                x = -5.0 + 10.0 * i / (n_side - 1)
                y = -5.0 + 10.0 * j / (n_side - 1)
                pts.append([x, y, 0.0])

        res = recognize(pts, primitives=["plane"], threshold=0.01, seed=42)
        assert res["ok"] is True
        assert any(n["op"] == "extrude" for n in res["feature_tree"])

        plane_nodes = [n for n in res["feature_tree"] if n["op"] == "extrude"]
        node = plane_nodes[0]
        # Normal should be (near) [0, 0, ±1]
        nz = abs(node["normal"][2])
        assert nz > 0.99, f"Plane normal not z-axis: {node['normal']}"

        d = max_point_to_surface_distance(pts, res["feature_tree"])
        assert d <= 1e-3, f"Plane round-trip max-pt-to-surface {d:.6f} > 1e-3"

    def test_sphere_round_trip(self):
        """Sphere: sample → recognize → max point-to-surface distance ≤ 1e-3."""
        r = 5.0
        golden = math.pi * (3 - math.sqrt(5))
        n = 200
        pts = []
        for i in range(n):
            y_f = 1.0 - (i / (n - 1)) * 2.0
            rad = math.sqrt(max(0.0, 1.0 - y_f * y_f))
            theta = golden * i
            pts.append([math.cos(theta) * rad * r, y_f * r, math.sin(theta) * rad * r])

        res = recognize(pts, primitives=["sphere"], threshold=0.05, seed=42)
        assert res["ok"] is True
        sphere_nodes = [n for n in res["feature_tree"] if n["op"] == "sphere"]
        assert sphere_nodes, "no sphere feature"
        node = sphere_nodes[0]
        assert abs(node["radius"] - r) < 0.1, f"radius off: {node['radius']}"

        d = max_point_to_surface_distance(pts, res["feature_tree"])
        assert d <= 1e-3, f"Sphere round-trip max-pt-to-surface {d:.6f} > 1e-3"

    def test_cube_plus_cylinder_round_trip(self):
        """
        Full T-332 v1 DoD oracle:
        Cube (6 faces) + cylinder (spatially separated) → recognize →
        max point-to-surface distance ≤ 1e-3 for each shape.

        The oracle is ``max_point_to_surface_distance``: for each original point
        we compute its exact distance to the nearest fitted surface.  A result
        ≤ 1e-3 means the pipeline recovered the surfaces to < 1 mm (or < 1 mm
        in whatever units the input is expressed in).
        """
        # ── Cube (10×10×10, faces sampled on a dense grid) ──
        side = 10.0
        n_face = 20  # per face
        cube_pts: list[list[float]] = []
        for i in range(n_face):
            for j in range(n_face):
                u = side * i / (n_face - 1)
                v = side * j / (n_face - 1)
                cube_pts.append([u, v, 0.0])    # z=0
                cube_pts.append([u, v, side])   # z=side
                cube_pts.append([u, 0.0, v])    # y=0
                cube_pts.append([u, side, v])   # y=side
                cube_pts.append([0.0, u, v])    # x=0
                cube_pts.append([side, u, v])   # x=side

        # ── Cylinder (spatially far from cube) ──
        cyl_r = 2.0
        cyl_height = 8.0
        n_theta, n_h = 40, 15
        cx, cy = 50.0, 50.0  # far from cube
        cyl_pts: list[list[float]] = []
        for it in range(n_theta):
            theta = 2.0 * math.pi * it / n_theta
            for ih in range(n_h):
                h = ih * cyl_height / max(n_h - 1, 1)
                cyl_pts.append([
                    cx + cyl_r * math.cos(theta),
                    cy + cyl_r * math.sin(theta),
                    h,
                ])

        all_pts = cube_pts + cyl_pts

        res = recognize(
            all_pts,
            primitives=["plane", "cylinder"],
            threshold=0.05,
            seed=42,
        )
        assert res["ok"] is True, f"recognize failed: {res.get('reason')}"
        assert res["segment_count"] >= 2, (
            f"Expected ≥2 segments; got {res['segment_count']}: "
            f"{[s['primitive'] for s in res['segments']]}"
        )

        found_ops = {n["op"] for n in res["feature_tree"]}
        assert "extrude" in found_ops, "No plane/extrude segment found in cube+cylinder cloud"
        assert "revolve" in found_ops, "No cylinder/revolve segment found in cube+cylinder cloud"

        # ── Oracle: max point-to-surface distance for cylinder points ──
        cyl_nodes = [n for n in res["feature_tree"] if n["op"] == "revolve"]
        assert cyl_nodes, "cylinder feature missing from tree"
        d_cyl = max_point_to_surface_distance(cyl_pts, cyl_nodes)
        assert d_cyl <= 1e-3, (
            f"Cylinder round-trip max-pt-to-surface {d_cyl:.6f} > 1e-3 "
            f"(radius={cyl_nodes[0]['radius']:.4f} vs {cyl_r})"
        )

        # ── Oracle: max point-to-surface distance for cube z=0 face points ──
        # Pick the extrude node with normal closest to [0,0,1] and d closest to 0
        plane_nodes = [n for n in res["feature_tree"] if n["op"] == "extrude"]
        assert plane_nodes, "no plane feature in tree"
        z0_node = min(
            plane_nodes,
            key=lambda n: abs(abs(n["normal"][2]) - 1.0) + abs(n["d"]),
        )
        z0_pts = [[side * i / (n_face - 1), side * j / (n_face - 1), 0.0]
                  for i in range(n_face) for j in range(n_face)]
        d_plane = max_point_to_surface_distance(z0_pts, [z0_node])
        assert d_plane <= 1e-3, (
            f"Plane round-trip max-pt-to-surface {d_plane:.6f} > 1e-3"
        )


# ===========================================================================
# SECTION 10: Fixture file I/O (write synthetic .pcd / .ply to disk + reload)
# ===========================================================================

class TestFixtureFiles:
    """Write synthetic fixtures to disk and reload them via load_point_cloud."""

    def test_pcd_file_roundtrip(self, tmp_path):
        pts_orig = [[1.0, 2.0, 3.0], [-4.0, 5.5, 0.0], [0.0, 0.0, 0.0]]
        pcd_path = tmp_path / "test.pcd"
        lines = [
            "# .PCD v0.7 — generated by test suite",
            "VERSION 0.7",
            "FIELDS x y z",
            "SIZE 4 4 4",
            "TYPE F F F",
            "COUNT 1 1 1",
            f"WIDTH {len(pts_orig)}",
            "HEIGHT 1",
            f"POINTS {len(pts_orig)}",
            "DATA ascii",
        ]
        for p in pts_orig:
            lines.append(f"{p[0]} {p[1]} {p[2]}")
        pcd_path.write_text("\n".join(lines))

        pts = load_point_cloud(pcd_path)
        assert pts == pts_orig

    def test_ply_file_roundtrip(self, tmp_path):
        pts_orig = [[0.5, 1.5, 2.5], [3.0, 4.0, 5.0]]
        ply_path = tmp_path / "test.ply"
        lines = [
            "ply",
            "format ascii 1.0",
            f"element vertex {len(pts_orig)}",
            "property float x",
            "property float y",
            "property float z",
            "end_header",
        ]
        for p in pts_orig:
            lines.append(f"{p[0]} {p[1]} {p[2]}")
        ply_path.write_text("\n".join(lines))

        pts = load_point_cloud(ply_path)
        assert pts == pts_orig
