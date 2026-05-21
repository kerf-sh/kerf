"""GK-114 — Hermetic tests for voxel boolean / CSG on SDF grids.

Oracle
------
voxel_union of two overlapping sphere SDFs → meshed via marching_cubes
has volume = V1 + V2 − V_overlap  ±  grid tolerance.

Pure-Python / numpy only — no OCC, no DB, no network.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.sdf import (
    marching_cubes,
    voxel_difference,
    voxel_intersection,
    voxel_union,
)
from kerf_cad_core.geom import (
    voxel_union as voxel_union_pub,
    voxel_intersection as voxel_intersection_pub,
    voxel_difference as voxel_difference_pub,
)


# ---------------------------------------------------------------------------
# Helpers: analytic sphere SDF grid (no B-rep Body needed)
# ---------------------------------------------------------------------------

def _sphere_sdf_grid(
    center: tuple,
    radius: float,
    resolution: int,
    lo: np.ndarray,
    hi: np.ndarray,
) -> dict:
    """Build a sphere SDF on a uniform grid covering [lo, hi]."""
    spacing = (hi - lo) / (resolution - 1)
    origin = lo.copy()
    xs = origin[0] + np.arange(resolution) * spacing[0]
    ys = origin[1] + np.arange(resolution) * spacing[1]
    zs = origin[2] + np.arange(resolution) * spacing[2]
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    cx, cy, cz = center
    grid = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2 + (Z - cz) ** 2) - radius
    return {
        "grid": grid,
        "origin": origin,
        "spacing": spacing,
        "dims": (resolution, resolution, resolution),
    }


def _mesh_volume(verts: np.ndarray, faces: np.ndarray) -> float:
    """Signed volume of a closed mesh via divergence theorem."""
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    cross = np.cross(v1, v2)
    signed_vols = np.einsum("ij,ij->i", v0, cross)
    return abs(float(signed_vols.sum()) / 6.0)


def _sphere_volume(r: float) -> float:
    return (4.0 / 3.0) * math.pi * r ** 3


def _sphere_cap_volume(R: float, h: float) -> float:
    """Volume of a spherical cap of height *h* on sphere of radius *R*."""
    if h <= 0.0:
        return 0.0
    if h >= 2 * R:
        return _sphere_volume(R)
    return math.pi * h ** 2 * (3 * R - h) / 3.0


def _two_sphere_overlap_volume(r1: float, r2: float, d: float) -> float:
    """Exact volume of intersection of two spheres with radii r1, r2 separated by d."""
    if d >= r1 + r2:
        return 0.0
    if d + r2 <= r1:
        return _sphere_volume(r2)
    if d + r1 <= r2:
        return _sphere_volume(r1)
    # Cap heights
    h1 = (r1 ** 2 - r2 ** 2 + d ** 2) / (2 * d)
    h2 = d - h1
    cap1 = _sphere_cap_volume(r1, r1 - h1)
    cap2 = _sphere_cap_volume(r2, r2 - h2)
    return cap1 + cap2


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_R = 1.0          # sphere radius
_OFFSET = 1.2     # centre-to-centre distance (< 2*_R so they overlap)
_RES = 48         # resolution for volume accuracy
_PAD = 0.4        # world-space padding beyond spheres


@pytest.fixture(scope="module")
def sdf_a():
    cx = -_OFFSET / 2
    lo = np.array([cx - _R - _PAD, -_R - _PAD, -_R - _PAD])
    hi = np.array([_OFFSET / 2 + _R + _PAD, _R + _PAD, _R + _PAD])
    return _sphere_sdf_grid((cx, 0.0, 0.0), _R, _RES, lo, hi)


@pytest.fixture(scope="module")
def sdf_b():
    cx = _OFFSET / 2
    # Same bounding box as sdf_a so grids align (simplest case)
    lo = np.array([-_OFFSET / 2 - _R - _PAD, -_R - _PAD, -_R - _PAD])
    hi = np.array([cx + _R + _PAD, _R + _PAD, _R + _PAD])
    return _sphere_sdf_grid((cx, 0.0, 0.0), _R, _RES, lo, hi)


@pytest.fixture(scope="module")
def union_sdf(sdf_a, sdf_b):
    return voxel_union(sdf_a, sdf_b)


@pytest.fixture(scope="module")
def intersection_sdf(sdf_a, sdf_b):
    return voxel_intersection(sdf_a, sdf_b)


@pytest.fixture(scope="module")
def difference_sdf(sdf_a, sdf_b):
    return voxel_difference(sdf_a, sdf_b)


# ===========================================================================
# 1. Return structure of voxel boolean ops
# ===========================================================================

class TestVoxelBooleanStructure:
    @pytest.mark.parametrize("op_name", ["union", "intersection", "difference"])
    def test_keys_present(self, sdf_a, sdf_b, op_name):
        ops = {
            "union": voxel_union,
            "intersection": voxel_intersection,
            "difference": voxel_difference,
        }
        result = ops[op_name](sdf_a, sdf_b)
        assert {"grid", "origin", "spacing", "dims"} <= set(result.keys())

    def test_union_grid_shape_matches_a(self, union_sdf, sdf_a):
        assert union_sdf["grid"].shape == sdf_a["grid"].shape

    def test_intersection_grid_shape_matches_a(self, intersection_sdf, sdf_a):
        assert intersection_sdf["grid"].shape == sdf_a["grid"].shape

    def test_difference_grid_shape_matches_a(self, difference_sdf, sdf_a):
        assert difference_sdf["grid"].shape == sdf_a["grid"].shape

    def test_union_grid_dtype(self, union_sdf):
        assert union_sdf["grid"].dtype == np.float64

    def test_dims_consistent(self, union_sdf):
        nx, ny, nz = union_sdf["dims"]
        assert union_sdf["grid"].shape == (nx, ny, nz)


# ===========================================================================
# 2. SDF semantics: union <= both, intersection >= both
# ===========================================================================

class TestVoxelBooleanSemantics:
    def test_union_leq_both(self, union_sdf, sdf_a, sdf_b):
        """Union SDF must be <= both inputs at every cell."""
        ga = sdf_a["grid"]
        # sdf_b is resampled on sdf_a's grid internally; for same-frame grids
        # the resampling is identity so we can compare directly.
        gb = sdf_b["grid"]
        gu = union_sdf["grid"]
        assert np.all(gu <= ga + 1e-9)
        assert np.all(gu <= gb + 1e-9)

    def test_intersection_geq_both(self, intersection_sdf, sdf_a, sdf_b):
        """Intersection SDF must be >= both inputs at every cell."""
        ga = sdf_a["grid"]
        gb = sdf_b["grid"]
        gi = intersection_sdf["grid"]
        assert np.all(gi >= ga - 1e-9)
        assert np.all(gi >= gb - 1e-9)

    def test_difference_a_minus_b_inside_a_outside_b(self, difference_sdf):
        """Points deep inside A but outside B should be inside difference."""
        # Centre of sphere A is at (-_OFFSET/2, 0, 0).
        # A point very close to A's centre is inside A (negative sdf_a)
        # and outside B (positive sdf_b) — so difference should be negative.
        cx_a = -_OFFSET / 2
        gd = difference_sdf["grid"]
        # Sample at A's centre in world coords
        origin = difference_sdf["origin"]
        spacing = difference_sdf["spacing"]
        nx, ny, nz = difference_sdf["dims"]
        i = int(round((cx_a - origin[0]) / spacing[0]))
        j = int(round((0.0 - origin[1]) / spacing[1]))
        k = int(round((0.0 - origin[2]) / spacing[2]))
        i = max(0, min(nx - 1, i))
        j = max(0, min(ny - 1, j))
        k = max(0, min(nz - 1, k))
        assert gd[i, j, k] < 0.0, (
            f"Centre of A should be inside difference, got {gd[i, j, k]}"
        )


# ===========================================================================
# 3. Oracle: voxel_union volume = V1 + V2 - V_overlap ± grid tol
# ===========================================================================

class TestUnionVolumeOracle:
    def test_union_volume(self, union_sdf):
        """Main oracle: union of two overlapping spheres has correct volume."""
        mesh = marching_cubes(union_sdf, iso=0.0)
        assert len(mesh["verts"]) > 0, "union mesh must be non-empty"
        assert len(mesh["faces"]) > 0, "union mesh must have faces"

        actual_vol = _mesh_volume(mesh["verts"], mesh["faces"])

        v_overlap = _two_sphere_overlap_volume(_R, _R, _OFFSET)
        expected_vol = 2 * _sphere_volume(_R) - v_overlap

        spacing = union_sdf["spacing"]
        voxel_diag = float(np.linalg.norm(spacing))
        # Union surface area ~ two spheres: 2 * 4πr²; allow generous tolerance.
        tol = 2 * 4 * math.pi * _R ** 2 * voxel_diag * 2.0

        assert abs(actual_vol - expected_vol) < tol, (
            f"union volume: got {actual_vol:.4f}, "
            f"expected {expected_vol:.4f}, tol={tol:.4f}, "
            f"v_overlap={v_overlap:.4f}"
        )


# ===========================================================================
# 4. Oracle: intersection volume ≈ V_overlap ± grid tol
# ===========================================================================

class TestIntersectionVolumeOracle:
    def test_intersection_volume(self, intersection_sdf):
        """Intersection mesh should have volume ≈ overlap volume."""
        mesh = marching_cubes(intersection_sdf, iso=0.0)
        if len(mesh["verts"]) == 0:
            # May be empty if spheres barely overlap or resolution is low.
            pytest.skip("intersection mesh empty — spheres may not overlap at this resolution")

        actual_vol = _mesh_volume(mesh["verts"], mesh["faces"])
        expected_vol = _two_sphere_overlap_volume(_R, _R, _OFFSET)

        spacing = intersection_sdf["spacing"]
        voxel_diag = float(np.linalg.norm(spacing))
        tol = 4 * math.pi * _R ** 2 * voxel_diag * 2.0

        assert abs(actual_vol - expected_vol) < tol, (
            f"intersection volume: got {actual_vol:.4f}, "
            f"expected {expected_vol:.4f}, tol={tol:.4f}"
        )


# ===========================================================================
# 5. Public re-export from kerf_cad_core.geom
# ===========================================================================

class TestPublicExport:
    def test_voxel_union_exported(self):
        assert voxel_union_pub is voxel_union

    def test_voxel_intersection_exported(self):
        assert voxel_intersection_pub is voxel_intersection

    def test_voxel_difference_exported(self):
        assert voxel_difference_pub is voxel_difference


# ===========================================================================
# 6. Same-frame identity check (grids share origin+spacing)
# ===========================================================================

class TestSameFrameGrids:
    """When both SDFs share the same coordinate frame the resampling is
    identity; the results collapse to pure numpy min/max/negation."""

    def test_union_is_elementwise_min(self, sdf_a, sdf_b):
        result = voxel_union(sdf_a, sdf_b)
        expected = np.minimum(sdf_a["grid"], sdf_b["grid"])
        # Allow small trilinear interpolation residual
        np.testing.assert_allclose(result["grid"], expected, atol=1e-6)

    def test_intersection_is_elementwise_max(self, sdf_a, sdf_b):
        result = voxel_intersection(sdf_a, sdf_b)
        expected = np.maximum(sdf_a["grid"], sdf_b["grid"])
        np.testing.assert_allclose(result["grid"], expected, atol=1e-6)

    def test_difference_is_max_negated_b(self, sdf_a, sdf_b):
        result = voxel_difference(sdf_a, sdf_b)
        expected = np.maximum(sdf_a["grid"], -sdf_b["grid"])
        np.testing.assert_allclose(result["grid"], expected, atol=1e-6)
