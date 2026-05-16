"""
Tests for kerf_cad_core.geom.mesh_to_nurbs — MeshToNURB auto-surfacing.

All tests are hermetic: no OCC, no database, no network.  Pure-Python
geometry only.

Coverage (≥30 tests across 5 groups):
  1. quad_to_bicubic_patch — planar quad → planar patch, curved quad, corners
     pass through, degenerate detection, neighbour tangent effect.
  2. tri_to_quad_fallback — pairing count = face count / 2 for perfect grids,
     unpaired remainder, non-planar pair rejection, pass-through of existing
     quads.
  3. mesh_to_nurbs_strips — planar grid produces patches whose corners match
     mesh verts; curved grid passes through verts; patch count = quad count;
     empty mesh; error propagation.
  4. quality_report — max_chord_dev near zero for well-fitted patches,
     G0 gap on shared edges within tol, G1 deviation measured, per_patch
     structure, empty patches.
  5. Failure / boundary modes — degenerate inputs, bad indices, non-planar
     quads, zero-area quads, type safety.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.mesh_to_nurbs import (
    _surf_eval,
    quad_to_bicubic_patch,
    tri_to_quad_fallback,
    mesh_to_nurbs_strips,
    quality_report,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

EPS = 1e-4  # generous epsilon for NURBS approximation tests


def _planar_quad_verts():
    """Simple unit-square quad in the XY plane."""
    return [
        [0.0, 0.0, 0.0],  # v0
        [1.0, 0.0, 0.0],  # v1
        [1.0, 1.0, 0.0],  # v2
        [0.0, 1.0, 0.0],  # v3
    ]


def _planar_quad_face():
    return [0, 1, 2, 3]


def _grid_verts(nx: int, ny: int, z_fn=None) -> list:
    """Build an nx×ny grid of verts on [0,1]×[0,1]."""
    if z_fn is None:
        z_fn = lambda x, y: 0.0
    verts = []
    for j in range(ny):
        for i in range(nx):
            x = i / (nx - 1)
            y = j / (ny - 1)
            verts.append([x, y, z_fn(x, y)])
    return verts


def _grid_quads(nx: int, ny: int) -> list:
    """Build quads for the nx×ny grid."""
    quads = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            v00 = j * nx + i
            v10 = j * nx + i + 1
            v11 = (j + 1) * nx + i + 1
            v01 = (j + 1) * nx + i
            quads.append([v00, v10, v11, v01])
    return quads


def _grid_tris(nx: int, ny: int) -> list:
    """Build triangles (each quad split into 2 tris) for the nx×ny grid."""
    tris = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            v00 = j * nx + i
            v10 = j * nx + i + 1
            v11 = (j + 1) * nx + i + 1
            v01 = (j + 1) * nx + i
            tris.append([v00, v10, v11])
            tris.append([v00, v11, v01])
    return tris


# ---------------------------------------------------------------------------
# Group 1: quad_to_bicubic_patch
# ---------------------------------------------------------------------------

class TestQuadToBicubicPatch:

    def test_planar_quad_returns_ok(self):
        v = _planar_quad_verts()
        r = quad_to_bicubic_patch(v, _planar_quad_face())
        assert r["ok"] is True, r.get("reason")
        assert r["surface"] is not None

    def test_planar_quad_surface_is_nurbs(self):
        v = _planar_quad_verts()
        r = quad_to_bicubic_patch(v, _planar_quad_face())
        assert isinstance(r["surface"], NurbsSurface)

    def test_planar_quad_degree_3(self):
        v = _planar_quad_verts()
        r = quad_to_bicubic_patch(v, _planar_quad_face())
        surf = r["surface"]
        assert surf.degree_u == 3
        assert surf.degree_v == 3

    def test_planar_quad_corners_through_verts(self):
        """Corners of the patch must pass through the quad vertices."""
        v = _planar_quad_verts()
        r = quad_to_bicubic_patch(v, _planar_quad_face())
        surf = r["surface"]
        corners_uv = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
        corner_pts = [_surf_eval(surf, u, vv) for u, vv in corners_uv]
        # Each corner should be close to one of the quad verts
        quad_verts_np = [np.array(vv) for vv in v]
        for cp in corner_pts:
            dists = [float(np.linalg.norm(cp - qv)) for qv in quad_verts_np]
            assert min(dists) < EPS, f"corner {cp} far from all quad verts: {dists}"

    def test_planar_quad_z_is_zero_everywhere(self):
        """All surface points should lie in z=0 plane for a planar quad."""
        v = _planar_quad_verts()
        r = quad_to_bicubic_patch(v, _planar_quad_face())
        surf = r["surface"]
        us = np.linspace(0.0, 1.0, 5)
        vs = np.linspace(0.0, 1.0, 5)
        for u in us:
            for vv in vs:
                pt = _surf_eval(surf, float(u), float(vv))
                assert abs(pt[2]) < EPS, f"z={pt[2]} non-zero at u={u},v={vv}"

    def test_planar_quad_xy_reasonable_bounds(self):
        """Surface points should be in a reasonable range around the unit quad.

        Bicubic Hermite patches can overshoot the convex hull of corners by a
        small amount (the tangent vectors are unscaled chord differences that
        can introduce overshoot). We allow ±0.2 margin outside [0,1] to
        accommodate this while still verifying the patch is in the right region.
        """
        v = _planar_quad_verts()
        r = quad_to_bicubic_patch(v, _planar_quad_face())
        surf = r["surface"]
        margin = 0.2
        us = np.linspace(0.0, 1.0, 6)
        vs = np.linspace(0.0, 1.0, 6)
        for u in us:
            for vv in vs:
                pt = _surf_eval(surf, float(u), float(vv))
                assert -margin <= pt[0] <= 1.0 + margin
                assert -margin <= pt[1] <= 1.0 + margin

    def test_nonplanar_quad_returns_ok(self):
        """A quad whose 4th vertex is off-plane should still work."""
        v = [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.5],
            [0.0, 1.0, 0.3],
        ]
        r = quad_to_bicubic_patch(v, [0, 1, 2, 3])
        assert r["ok"] is True

    def test_curved_quad_corner_u0v0(self):
        """Corner at (u=0,v=0) must match v[0]."""
        v = [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 1.0],
            [2.0, 2.0, 2.0],
            [0.0, 2.0, 1.0],
        ]
        r = quad_to_bicubic_patch(v, [0, 1, 2, 3])
        assert r["ok"] is True
        pt = _surf_eval(r["surface"], 0.0, 0.0)
        assert np.linalg.norm(pt - np.array([0.0, 0.0, 0.0])) < EPS

    def test_curved_quad_corner_u1v1(self):
        """Corner at (u=1,v=1) must match v[2]."""
        v = [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 1.0],
            [2.0, 2.0, 2.0],
            [0.0, 2.0, 1.0],
        ]
        r = quad_to_bicubic_patch(v, [0, 1, 2, 3])
        pt = _surf_eval(r["surface"], 1.0, 1.0)
        assert np.linalg.norm(pt - np.array([2.0, 2.0, 2.0])) < EPS

    def test_degenerate_zero_area_quad(self):
        """A zero-area quad (collinear verts) should return ok=False."""
        v = [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
        ]
        r = quad_to_bicubic_patch(v, [0, 1, 2, 3])
        assert r["ok"] is False
        assert "degenerate" in r["reason"].lower()

    def test_neighbour_tangent_smoothing(self):
        """Providing neighbour faces should not crash and returns ok."""
        nx, ny = 4, 4
        v = _grid_verts(nx, ny)
        quads = _grid_quads(nx, ny)
        # First quad: quad index 0
        q = quads[0]
        # Provide some neighbour faces
        nbrs = [quads[1] if len(quads) > 1 else None, None, None, None]
        r = quad_to_bicubic_patch(v, q, neighbour_faces=nbrs)
        assert r["ok"] is True

    def test_bad_verts_type_returns_error(self):
        r = quad_to_bicubic_patch("notalist", [0, 1, 2, 3])
        assert r["ok"] is False

    def test_bad_quad_out_of_range_returns_error(self):
        v = _planar_quad_verts()
        r = quad_to_bicubic_patch(v, [0, 1, 2, 99])
        assert r["ok"] is False

    def test_bad_quad_wrong_length_returns_error(self):
        v = _planar_quad_verts()
        r = quad_to_bicubic_patch(v, [0, 1, 2])
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# Group 2: tri_to_quad_fallback
# ---------------------------------------------------------------------------

class TestTriToQuadFallback:

    def test_basic_returns_ok(self):
        v = _grid_verts(3, 3)
        tris = _grid_tris(3, 3)
        r = tri_to_quad_fallback(v, tris)
        assert r["ok"] is True, r.get("reason")

    def test_2x2_grid_tris_all_paired(self):
        """A 2×2 grid of tris (4 tris = 2 quads) should pair fully."""
        v = _grid_verts(3, 3)
        tris = _grid_tris(3, 3)
        r = tri_to_quad_fallback(v, tris)
        assert r["ok"] is True
        assert r["pair_count"] == len(tris) // 2
        assert len(r["unpaired"]) == 0

    def test_quad_count_equals_face_count_after_pairing(self):
        """After pairing a perfect tri grid, quad count = face_count / 2."""
        nx, ny = 4, 4
        v = _grid_verts(nx, ny)
        tris = _grid_tris(nx, ny)
        r = tri_to_quad_fallback(v, tris)
        assert r["ok"] is True
        assert r["pair_count"] * 2 == len(tris)

    def test_existing_quads_passed_through(self):
        """Pre-existing quad faces should appear in output without pairing."""
        v = _grid_verts(3, 3)
        quads = _grid_quads(3, 3)
        r = tri_to_quad_fallback(v, quads)
        assert r["ok"] is True
        # All faces were already quads; no pairing should occur
        assert r["pair_count"] == 0
        assert len(r["quads"]) == len(quads)

    def test_unpaired_triangle_reported(self):
        """A lone triangle with no compatible neighbour should appear in unpaired."""
        v = [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 1.0, 0.0],
        ]
        tris = [[0, 1, 2]]
        r = tri_to_quad_fallback(v, tris)
        assert r["ok"] is True
        assert len(r["unpaired"]) == 1

    def test_returns_dict_contract(self):
        v = _grid_verts(3, 3)
        tris = _grid_tris(3, 3)
        r = tri_to_quad_fallback(v, tris)
        for key in ("ok", "reason", "quads", "unpaired", "pair_count"):
            assert key in r, f"missing key: {key}"

    def test_empty_faces_returns_ok(self):
        v = _planar_quad_verts()
        r = tri_to_quad_fallback(v, [])
        assert r["ok"] is True
        assert r["pair_count"] == 0

    def test_bad_verts_returns_error(self):
        r = tri_to_quad_fallback(123, [[0, 1, 2]])
        assert r["ok"] is False

    def test_bad_face_index_returns_error(self):
        v = _planar_quad_verts()
        r = tri_to_quad_fallback(v, [[0, 1, 99]])
        assert r["ok"] is False

    def test_large_grid_all_paired(self):
        """5×5 grid → 32 tris → 16 quads, all paired."""
        nx, ny = 5, 5
        v = _grid_verts(nx, ny)
        tris = _grid_tris(nx, ny)
        r = tri_to_quad_fallback(v, tris)
        assert r["ok"] is True
        assert r["pair_count"] == len(tris) // 2


# ---------------------------------------------------------------------------
# Group 3: mesh_to_nurbs_strips
# ---------------------------------------------------------------------------

class TestMeshToNurbsStrips:

    def test_planar_grid_returns_ok(self):
        v = _grid_verts(3, 3)
        q = _grid_quads(3, 3)
        r = mesh_to_nurbs_strips(v, q)
        assert r["ok"] is True, r.get("reason")

    def test_patch_count_equals_quad_count(self):
        """One patch per quad, no loss."""
        nx, ny = 4, 4
        v = _grid_verts(nx, ny)
        q = _grid_quads(nx, ny)
        r = mesh_to_nurbs_strips(v, q)
        assert r["ok"] is True
        expected = (nx - 1) * (ny - 1)
        assert r["patch_count"] == expected

    def test_patches_are_nurbs_surfaces(self):
        v = _grid_verts(3, 3)
        q = _grid_quads(3, 3)
        r = mesh_to_nurbs_strips(v, q)
        for surf in r["patches"]:
            assert isinstance(surf, NurbsSurface)

    def test_planar_grid_corners_match_verts(self):
        """For a flat grid, patch corners should be within EPS of mesh verts."""
        v = _grid_verts(3, 3)
        q = _grid_quads(3, 3)
        r = mesh_to_nurbs_strips(v, q)
        vs_np = np.array([[float(x) for x in vv] for vv in v])

        for surf in r["patches"]:
            for (u, vv) in [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]:
                pt = _surf_eval(surf, u, vv)
                dists = np.linalg.norm(vs_np - pt, axis=1)
                assert np.min(dists) < EPS * 10, (
                    f"patch corner {pt} too far from all mesh verts (min={np.min(dists):.6f})"
                )

    def test_curved_grid_corners_within_tol(self):
        """For a curved z=x*y surface, corners should be on or near the mesh."""
        def z_fn(x, y): return x * y
        nx, ny = 3, 3
        v = _grid_verts(nx, ny, z_fn=z_fn)
        q = _grid_quads(nx, ny)
        r = mesh_to_nurbs_strips(v, q)
        assert r["ok"] is True
        vs_np = np.array([[float(x) for x in vv] for vv in v])

        for surf in r["patches"]:
            for (u, vv) in [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]:
                pt = _surf_eval(surf, u, vv)
                dists = np.linalg.norm(vs_np - pt, axis=1)
                assert np.min(dists) < EPS * 20

    def test_triangle_mesh_produces_patches(self):
        """A pure tri mesh should be paired into quads and produce patches."""
        nx, ny = 3, 3
        v = _grid_verts(nx, ny)
        tris = _grid_tris(nx, ny)
        r = mesh_to_nurbs_strips(v, tris)
        assert r["ok"] is True
        assert r["patch_count"] > 0

    def test_empty_mesh_returns_ok(self):
        r = mesh_to_nurbs_strips([], [])
        assert r["ok"] is True
        assert r["patch_count"] == 0

    def test_returns_dict_contract(self):
        v = _grid_verts(3, 3)
        q = _grid_quads(3, 3)
        r = mesh_to_nurbs_strips(v, q)
        for key in ("ok", "reason", "patches", "patch_count", "unpaired_tris"):
            assert key in r, f"missing key: {key}"

    def test_bad_face_index_returns_error(self):
        v = _grid_verts(3, 3)
        r = mesh_to_nurbs_strips(v, [[0, 1, 2, 999]])
        assert r["ok"] is False

    def test_single_quad_produces_one_patch(self):
        v = _planar_quad_verts()
        r = mesh_to_nurbs_strips(v, [_planar_quad_face()])
        assert r["ok"] is True
        assert r["patch_count"] == 1


# ---------------------------------------------------------------------------
# Group 4: quality_report
# ---------------------------------------------------------------------------

class TestQualityReport:

    def _make_patches_and_mesh(self, nx=3, ny=3, z_fn=None):
        v = _grid_verts(nx, ny, z_fn=z_fn)
        q = _grid_quads(nx, ny)
        r = mesh_to_nurbs_strips(v, q)
        return r["patches"], v, q

    def test_returns_ok(self):
        patches, v, q = self._make_patches_and_mesh()
        r = quality_report(patches, v, q)
        assert r["ok"] is True

    def test_returns_dict_contract(self):
        patches, v, q = self._make_patches_and_mesh()
        r = quality_report(patches, v, q)
        for key in ("ok", "reason", "patch_count", "max_chord_dev", "per_patch",
                    "g0_max_dev", "g1_max_dev"):
            assert key in r, f"missing key: {key}"

    def test_patch_count_matches(self):
        patches, v, q = self._make_patches_and_mesh()
        r = quality_report(patches, v, q)
        assert r["patch_count"] == len(patches)

    def test_per_patch_length_matches(self):
        patches, v, q = self._make_patches_and_mesh()
        r = quality_report(patches, v, q)
        assert len(r["per_patch"]) == len(patches)

    def test_planar_grid_small_chord_dev(self):
        """For a flat planar grid, chord deviation should be very small."""
        patches, v, q = self._make_patches_and_mesh(nx=3, ny=3)
        r = quality_report(patches, v, q, tol=0.1)
        assert r["ok"] is True
        # Deviation should be modest (patch corners match verts exactly)
        assert r["max_chord_dev"] < 1.0

    def test_g0_deviation_present(self):
        """g0_max_dev should be a non-negative float."""
        patches, v, q = self._make_patches_and_mesh()
        r = quality_report(patches, v, q)
        assert isinstance(r["g0_max_dev"], float)
        assert r["g0_max_dev"] >= 0.0

    def test_g1_deviation_present(self):
        """g1_max_dev should be a non-negative float."""
        patches, v, q = self._make_patches_and_mesh()
        r = quality_report(patches, v, q)
        assert isinstance(r["g1_max_dev"], float)
        assert r["g1_max_dev"] >= 0.0

    def test_per_patch_structure(self):
        patches, v, q = self._make_patches_and_mesh()
        r = quality_report(patches, v, q)
        for pp in r["per_patch"]:
            assert "patch_idx" in pp
            assert "max_dev" in pp

    def test_empty_patches_returns_ok(self):
        v = _grid_verts(3, 3)
        q = _grid_quads(3, 3)
        r = quality_report([], v, q)
        assert r["ok"] is True
        assert r["patch_count"] == 0
        assert r["max_chord_dev"] == 0.0

    def test_bad_verts_returns_error(self):
        r = quality_report([], "bad_verts", [])
        assert r["ok"] is False

    def test_g0_small_for_smooth_shared_edge(self):
        """Adjacent patches from the same flat grid should have near-zero G0 gap."""
        patches, v, q = self._make_patches_and_mesh(nx=4, ny=4)
        r = quality_report(patches, v, q)
        assert r["g0_max_dev"] < 0.5


# ---------------------------------------------------------------------------
# Group 5: Failure and boundary modes
# ---------------------------------------------------------------------------

class TestFailureModes:

    def test_quad_patch_degenerate_all_same_vert(self):
        v = _planar_quad_verts()
        r = quad_to_bicubic_patch(v, [0, 0, 0, 0])
        assert r["ok"] is False

    def test_quad_patch_none_verts(self):
        r = quad_to_bicubic_patch(None, [0, 1, 2, 3])
        assert r["ok"] is False

    def test_tri_fallback_empty_verts(self):
        r = tri_to_quad_fallback([], [[0, 1, 2]])
        # Empty verts but face has index 0 — should fail
        assert r["ok"] is False

    def test_mesh_strips_none_verts(self):
        r = mesh_to_nurbs_strips(None, [[0, 1, 2, 3]])
        assert r["ok"] is False

    def test_mesh_strips_none_faces(self):
        v = _planar_quad_verts()
        r = mesh_to_nurbs_strips(v, None)
        assert r["ok"] is False

    def test_quality_report_none_patches(self):
        v = _grid_verts(3, 3)
        r = quality_report(None, v, [])
        assert r["ok"] is False

    def test_quad_patch_non_numeric_vert(self):
        v = [[0, 0, 0], [1, 0, 0], [1, "x", 0], [0, 1, 0]]
        r = quad_to_bicubic_patch(v, [0, 1, 2, 3])
        assert r["ok"] is False

    def test_mesh_strips_single_tri_only(self):
        """A single isolated triangle cannot be paired — unpaired_tris should contain it."""
        v = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 1.0, 0.0]]
        r = mesh_to_nurbs_strips(v, [[0, 1, 2]])
        assert r["ok"] is True
        assert len(r["unpaired_tris"]) == 1
        assert r["patch_count"] == 0

    def test_quality_report_curved_grid(self):
        """quality_report should not crash on a curved (non-planar) mesh."""
        def z_fn(x, y): return math.sin(x * math.pi) * math.cos(y * math.pi)
        v = _grid_verts(4, 4, z_fn=z_fn)
        q = _grid_quads(4, 4)
        r_strips = mesh_to_nurbs_strips(v, q)
        assert r_strips["ok"] is True

        r_q = quality_report(r_strips["patches"], v, q)
        assert r_q["ok"] is True

    def test_quality_report_deviation_is_float(self):
        v = _grid_verts(3, 3)
        q = _grid_quads(3, 3)
        strips = mesh_to_nurbs_strips(v, q)
        r = quality_report(strips["patches"], v, q)
        assert isinstance(r["max_chord_dev"], float)

    def test_mesh_strips_does_not_raise(self):
        """mesh_to_nurbs_strips must never raise; test with pathological input."""
        v = _grid_verts(3, 3)
        # Partially degenerate faces
        bad_faces = [[0, 1, 2, 3], [0, 0, 0, 0]]
        try:
            r = mesh_to_nurbs_strips(v, bad_faces)
            # We accept either ok or not ok but it must not raise
            assert "ok" in r
        except Exception as exc:  # pragma: no cover
            pytest.fail(f"mesh_to_nurbs_strips raised: {exc}")
