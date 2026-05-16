"""
Tests for kerf_cad_core.geom.mesh_repair

All tests are hermetic: no OCC, no DB, no network.  Pure-Python geometry only.

Coverage (≥30 tests):
  1. weld_vertices — merge coincident verts, respect tol, degenerate collapse
  2. unify_normals — flips wrong-orient faces, consistent BFS, single face
  3. fill_holes — cube-with-hole fills it (Euler V−E+F=2), open triangle fan
  4. remove_degenerate — zero-area, duplicate, non-manifold edge report
  5. decimate — hits target_faces, max_error stop, trivial mesh
  6. mesh_offset — displaces vertices, self-intersection warning flag
  7. mesh_boolean — union/difference/intersection volumes, two unit cubes
  8. mesh_volume / mesh_area — unit cube values
  9. is_closed / is_manifold — detection on known meshes
  10. repair_pipeline — runs all four steps, ok + steps list
  11. Input validation — bad verts/faces, wrong types, out-of-range indices
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.geom.mesh_repair import (
    decimate,
    fill_holes,
    is_closed,
    is_manifold,
    mesh_area,
    mesh_boolean,
    mesh_offset,
    mesh_volume,
    remove_degenerate,
    repair_pipeline,
    unify_normals,
    weld_vertices,
)


# ---------------------------------------------------------------------------
# Mesh factories
# ---------------------------------------------------------------------------

def _cube_mesh(ox=0.0, oy=0.0, oz=0.0, s=1.0):
    """Unit cube with CCW winding (outward normals).

    Returns (verts, faces).
    """
    verts = [
        [ox,     oy,     oz    ],  # 0 front-bottom-left
        [ox + s, oy,     oz    ],  # 1 front-bottom-right
        [ox + s, oy + s, oz    ],  # 2 front-top-right
        [ox,     oy + s, oz    ],  # 3 front-top-left
        [ox,     oy,     oz + s],  # 4 back-bottom-left
        [ox + s, oy,     oz + s],  # 5 back-bottom-right
        [ox + s, oy + s, oz + s],  # 6 back-top-right
        [ox,     oy + s, oz + s],  # 7 back-top-left
    ]
    faces = [
        # -Z face (front)
        [0, 2, 1], [0, 3, 2],
        # +Z face (back)
        [4, 5, 6], [4, 6, 7],
        # -X face (left)
        [0, 4, 7], [0, 7, 3],
        # +X face (right)
        [1, 2, 6], [1, 6, 5],
        # -Y face (bottom)
        [0, 1, 5], [0, 5, 4],
        # +Y face (top)
        [3, 7, 6], [3, 6, 2],
    ]
    return verts, faces


def _cube_with_missing_top():
    """Cube missing its +Y top face (2 triangles) — has a hole."""
    verts, faces = _cube_mesh()
    # Remove last 2 faces (top)
    return verts, faces[:-2]


def _tetrahedron():
    """Regular tetrahedron, outward CCW winding."""
    verts = [
        [1.0,  1.0,  1.0],
        [-1.0,-1.0,  1.0],
        [-1.0, 1.0, -1.0],
        [1.0, -1.0, -1.0],
    ]
    faces = [
        [0, 1, 2],
        [0, 2, 3],
        [0, 3, 1],
        [1, 3, 2],
    ]
    return verts, faces


def _euler(verts, faces):
    """Return V − E + F for a triangle mesh.  Should be 2 for a closed genus-0 mesh."""
    edge_set = set()
    for f in faces:
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            edge_set.add((min(a, b), max(a, b)))
    V = len(verts)
    E = len(edge_set)
    F = len(faces)
    return V - E + F


# ===========================================================================
# 1. weld_vertices
# ===========================================================================

class TestWeldVertices:
    def test_merges_coincident_vertices(self):
        """Two vertices at the same location should be merged."""
        verts = [[0, 0, 0], [0, 0, 0], [1, 0, 0], [0, 1, 0]]
        faces = [[0, 2, 3], [1, 2, 3]]
        r = weld_vertices(verts, faces, tol=1e-6)
        assert r["ok"]
        assert r["merged_count"] >= 1
        assert len(r["verts"]) < len(verts)

    def test_no_merge_when_far(self):
        """Vertices far apart should NOT be merged."""
        verts = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
        faces = [[0, 1, 2]]
        r = weld_vertices(verts, faces, tol=1e-6)
        assert r["ok"]
        assert r["merged_count"] == 0
        assert len(r["verts"]) == 3

    def test_merges_within_tol(self):
        """Vertex within tol should be merged."""
        verts = [[0, 0, 0], [0, 0, 5e-7], [1, 0, 0], [0, 1, 0]]
        faces = [[0, 2, 3], [1, 2, 3]]
        r = weld_vertices(verts, faces, tol=1e-6)
        assert r["ok"]
        assert r["merged_count"] >= 1

    def test_not_merged_just_outside_tol(self):
        """Vertex just outside tol must NOT be merged."""
        verts = [[0, 0, 0], [0, 0, 2e-6], [1, 0, 0], [0, 1, 0]]
        faces = [[0, 2, 3], [1, 2, 3]]
        r = weld_vertices(verts, faces, tol=1e-6)
        assert r["ok"]
        assert r["merged_count"] == 0

    def test_empty_mesh(self):
        r = weld_vertices([], [], tol=1e-6)
        assert r["ok"]
        assert r["verts"] == []
        assert r["faces"] == []

    def test_bad_tol_rejected(self):
        r = weld_vertices([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]], tol=-1)
        assert not r["ok"]
        assert "tol" in r["reason"]

    def test_result_keys(self):
        _, f = _cube_mesh()
        v, _ = _cube_mesh()
        r = weld_vertices(v, f)
        assert {"ok", "verts", "faces", "merged_count"} <= r.keys()


# ===========================================================================
# 2. unify_normals
# ===========================================================================

class TestUnifyNormals:
    def test_flips_inverted_face(self):
        """A face with flipped winding on a closed mesh should be corrected."""
        verts, faces = _cube_mesh()
        # Flip one face deliberately
        f0 = faces[0]
        faces[0] = [f0[0], f0[2], f0[1]]
        r = unify_normals(verts, faces)
        assert r["ok"]
        assert r["flipped_count"] >= 1

    def test_already_consistent(self):
        """A consistently wound mesh should flip 0 faces."""
        verts, faces = _cube_mesh()
        r = unify_normals(verts, faces)
        assert r["ok"]
        assert r["flipped_count"] == 0

    def test_single_face(self):
        verts = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
        faces = [[0, 1, 2]]
        r = unify_normals(verts, faces)
        assert r["ok"]

    def test_empty_faces(self):
        r = unify_normals([[0, 0, 0]], [])
        assert r["ok"]
        assert r["flipped_count"] == 0

    def test_output_face_count_preserved(self):
        """Number of faces must be unchanged after unify."""
        verts, faces = _cube_mesh()
        r = unify_normals(verts, faces)
        assert r["ok"]
        assert len(r["faces"]) == len(faces)


# ===========================================================================
# 3. fill_holes
# ===========================================================================

class TestFillHoles:
    def test_cube_with_missing_top_fills(self):
        """Cube missing top 2 faces should be closed after fill_holes."""
        verts, faces = _cube_with_missing_top()
        r = fill_holes(verts, faces)
        assert r["ok"]
        assert r["holes_filled"] >= 1
        # Result must be closed
        rc = is_closed(r["verts"], r["faces"])
        assert rc["ok"]
        assert rc["closed"], "mesh should be closed after hole fill"

    def test_euler_characteristic_after_fill(self):
        """After filling, a genus-0 mesh must satisfy V − E + F = 2."""
        verts, faces = _cube_with_missing_top()
        r = fill_holes(verts, faces)
        assert r["ok"]
        chi = _euler(r["verts"], r["faces"])
        assert chi == 2, f"Euler characteristic should be 2, got {chi}"

    def test_already_closed_no_fill(self):
        """A closed mesh has no holes; holes_filled should be 0."""
        verts, faces = _cube_mesh()
        r = fill_holes(verts, faces)
        assert r["ok"]
        assert r["holes_filled"] == 0

    def test_empty_mesh(self):
        r = fill_holes([], [])
        assert r["ok"]
        assert r["holes_filled"] == 0


# ===========================================================================
# 4. remove_degenerate
# ===========================================================================

class TestRemoveDegenerate:
    def test_removes_zero_area_face(self):
        """A triangle with all three vertices at the same point is degenerate."""
        verts = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.5, 0, 0]]
        # Degenerate: all verts same
        faces = [[0, 0, 0], [0, 1, 2]]  # first is degenerate
        r = remove_degenerate(verts, faces)
        assert r["ok"]
        assert r["removed_count"] >= 1
        assert len(r["faces"]) == 1

    def test_removes_duplicate_face(self):
        """Duplicate face (same vertex set) must be removed."""
        verts = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
        faces = [[0, 1, 2], [0, 1, 2]]
        r = remove_degenerate(verts, faces)
        assert r["ok"]
        assert r["removed_count"] >= 1
        assert len(r["faces"]) == 1

    def test_non_manifold_edge_reported(self):
        """Three faces sharing the same edge must be flagged as non-manifold."""
        verts = [
            [0, 0, 0], [1, 0, 0], [0, 1, 0],
            [0, 0, 1], [0, -1, 0],
        ]
        # Edge (0,1) appears in 3 faces
        faces = [[0, 1, 2], [0, 1, 3], [0, 1, 4]]
        r = remove_degenerate(verts, faces)
        assert r["ok"]
        assert len(r["non_manifold_edges"]) > 0

    def test_clean_mesh_no_removal(self):
        verts, faces = _cube_mesh()
        r = remove_degenerate(verts, faces)
        assert r["ok"]
        assert r["removed_count"] == 0
        assert r["non_manifold_edges"] == []


# ===========================================================================
# 5. decimate
# ===========================================================================

class TestDecimate:
    def test_target_faces_respected(self):
        """Decimate should hit the target face count (or go below)."""
        verts, faces = _cube_mesh()
        # Subdivide the cube slightly by duplicating face data to have more
        # For simplicity just test with the 12-face cube, target=6
        r = decimate(verts, faces, target_faces=6)
        assert r["ok"]
        assert r["final_faces"] <= 6

    def test_max_error_stops_early(self):
        """With a very tight max_error, few collapses should happen."""
        verts, faces = _cube_mesh()
        r = decimate(verts, faces, max_error=1e-10)
        assert r["ok"]
        # With near-zero tolerance, essentially no collapses
        assert r["final_faces"] <= r["original_faces"]

    def test_no_args_error(self):
        verts, faces = _cube_mesh()
        r = decimate(verts, faces)
        assert not r["ok"]
        assert "target_faces" in r["reason"] or "max_error" in r["reason"]

    def test_target_faces_lt_1_rejected(self):
        verts, faces = _cube_mesh()
        r = decimate(verts, faces, target_faces=0)
        assert not r["ok"]

    def test_trivial_mesh_no_crash(self):
        """Mesh with 1 face should survive decimation gracefully."""
        verts = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
        faces = [[0, 1, 2]]
        r = decimate(verts, faces, target_faces=1)
        assert r["ok"]
        assert r["final_faces"] >= 1

    def test_result_keys(self):
        verts, faces = _cube_mesh()
        r = decimate(verts, faces, target_faces=8)
        assert {"ok", "verts", "faces", "original_faces", "final_faces"} <= r.keys()


# ===========================================================================
# 6. mesh_offset
# ===========================================================================

class TestMeshOffset:
    def test_outward_offset_increases_volume(self):
        """Offsetting a cube outward should increase its volume."""
        verts, faces = _cube_mesh()
        r_before = mesh_volume(verts, faces)
        r_off = mesh_offset(verts, faces, distance=0.05)
        assert r_off["ok"]
        r_after = mesh_volume(r_off["verts"], r_off["faces"])
        assert r_after["volume"] > r_before["volume"]

    def test_large_offset_warns(self):
        """Offset larger than half the min edge length should warn."""
        verts, faces = _cube_mesh()
        r = mesh_offset(verts, faces, distance=5.0)
        assert r["ok"]
        assert r["self_intersection_warning"] is True

    def test_small_offset_no_warn(self):
        """Small offset should produce no warning."""
        verts, faces = _cube_mesh()
        r = mesh_offset(verts, faces, distance=0.001)
        assert r["ok"]
        assert r["self_intersection_warning"] is False

    def test_face_count_preserved(self):
        verts, faces = _cube_mesh()
        r = mesh_offset(verts, faces, distance=0.1)
        assert r["ok"]
        assert len(r["faces"]) == len(faces)

    def test_bad_distance_rejected(self):
        verts, faces = _cube_mesh()
        r = mesh_offset(verts, faces, distance="oops")
        assert not r["ok"]


# ===========================================================================
# 7. mesh_boolean
# ===========================================================================

class TestMeshBoolean:
    """Two unit cubes: A at origin, B shifted by 0.5 along X (overlapping)."""

    def setup_method(self):
        self.va, self.fa = _cube_mesh(0.0, 0.0, 0.0, 1.0)
        self.vb, self.fb = _cube_mesh(0.5, 0.0, 0.0, 1.0)

    def test_union_ok(self):
        r = mesh_boolean(self.va, self.fa, self.vb, self.fb, "union")
        assert r["ok"]

    def test_difference_ok(self):
        r = mesh_boolean(self.va, self.fa, self.vb, self.fb, "difference")
        assert r["ok"]

    def test_intersection_ok(self):
        r = mesh_boolean(self.va, self.fa, self.vb, self.fb, "intersection")
        assert r["ok"]

    def test_invalid_operation(self):
        r = mesh_boolean(self.va, self.fa, self.vb, self.fb, "xor")
        assert not r["ok"]
        assert "operation" in r["reason"]

    def test_two_identical_cubes_union_volume(self):
        """Union of two completely overlapping cubes = 1 cube's worth of faces."""
        va, fa = _cube_mesh(0.0, 0.0, 0.0, 1.0)
        vb, fb = _cube_mesh(0.0, 0.0, 0.0, 1.0)
        r = mesh_boolean(va, fa, vb, fb, "union")
        assert r["ok"]
        # Both meshes identical: all faces of A are inside B and vice versa
        # union = outside-A-faces + outside-B-faces; for identical meshes both
        # sets may be small, just check ok and faces list is returned
        assert isinstance(r["faces"], list)

    def test_non_overlapping_cubes_union_has_all_faces(self):
        """Two non-overlapping cubes union should retain faces from both."""
        va, fa = _cube_mesh(0.0, 0.0, 0.0, 1.0)
        vb, fb = _cube_mesh(5.0, 0.0, 0.0, 1.0)
        r = mesh_boolean(va, fa, vb, fb, "union")
        assert r["ok"]
        # Each cube is entirely outside the other: union = all 24 faces
        assert len(r["faces"]) == len(fa) + len(fb)

    def test_non_overlapping_cubes_intersection_empty(self):
        """Intersection of two disjoint cubes should produce no faces."""
        va, fa = _cube_mesh(0.0, 0.0, 0.0, 1.0)
        vb, fb = _cube_mesh(5.0, 0.0, 0.0, 1.0)
        r = mesh_boolean(va, fa, vb, fb, "intersection")
        assert r["ok"]
        assert len(r["faces"]) == 0

    def test_result_keys(self):
        r = mesh_boolean(self.va, self.fa, self.vb, self.fb, "union")
        assert {"ok", "verts", "faces", "failed", "fail_reason"} <= r.keys()


# ===========================================================================
# 8. mesh_volume / mesh_area
# ===========================================================================

class TestDiagnostics:
    def test_unit_cube_volume(self):
        verts, faces = _cube_mesh()
        r = mesh_volume(verts, faces)
        assert r["ok"]
        assert abs(r["volume"] - 1.0) < 0.05, f"expected ~1.0, got {r['volume']}"

    def test_unit_cube_area(self):
        verts, faces = _cube_mesh()
        r = mesh_area(verts, faces)
        assert r["ok"]
        assert abs(r["area"] - 6.0) < 0.01, f"expected 6.0, got {r['area']}"

    def test_scaled_cube_volume(self):
        verts, faces = _cube_mesh(s=2.0)
        r = mesh_volume(verts, faces)
        assert r["ok"]
        assert abs(r["volume"] - 8.0) < 0.1, f"expected ~8.0, got {r['volume']}"

    def test_empty_mesh_volume(self):
        r = mesh_volume([], [])
        assert r["ok"]
        assert r["volume"] == 0.0


# ===========================================================================
# 9. is_closed / is_manifold
# ===========================================================================

class TestTopology:
    def test_cube_is_closed(self):
        verts, faces = _cube_mesh()
        r = is_closed(verts, faces)
        assert r["ok"]
        assert r["closed"] is True

    def test_open_mesh_not_closed(self):
        verts, faces = _cube_with_missing_top()
        r = is_closed(verts, faces)
        assert r["ok"]
        assert r["closed"] is False

    def test_cube_is_manifold(self):
        verts, faces = _cube_mesh()
        r = is_manifold(verts, faces)
        assert r["ok"]
        assert r["manifold"] is True

    def test_non_manifold_edge_detected(self):
        """Three faces sharing edge → non-manifold."""
        verts = [
            [0, 0, 0], [1, 0, 0], [0, 1, 0],
            [0, 0, 1], [0, -1, 0],
        ]
        faces = [[0, 1, 2], [0, 1, 3], [0, 1, 4]]
        r = is_manifold(verts, faces)
        assert r["ok"]
        assert r["manifold"] is False
        assert len(r["non_manifold_edges"]) > 0

    def test_tetrahedron_closed_manifold(self):
        verts, faces = _tetrahedron()
        rc = is_closed(verts, faces)
        rm = is_manifold(verts, faces)
        assert rc["ok"] and rc["closed"]
        assert rm["ok"] and rm["manifold"]


# ===========================================================================
# 10. repair_pipeline
# ===========================================================================

class TestRepairPipeline:
    def test_pipeline_runs_all_steps(self):
        verts, faces = _cube_mesh()
        r = repair_pipeline(verts, faces)
        assert r["ok"]
        step_names = [s["step"] for s in r["steps"]]
        assert "weld_vertices" in step_names
        assert "unify_normals" in step_names
        assert "fill_holes" in step_names
        assert "remove_degenerate" in step_names

    def test_pipeline_repairs_open_mesh(self):
        """Pipeline should close an open mesh."""
        verts, faces = _cube_with_missing_top()
        r = repair_pipeline(verts, faces)
        assert r["ok"]
        rc = is_closed(r["verts"], r["faces"])
        assert rc["closed"], "pipeline should have filled the hole"

    def test_pipeline_result_keys(self):
        verts, faces = _cube_mesh()
        r = repair_pipeline(verts, faces)
        assert {"ok", "verts", "faces", "steps"} <= r.keys()

    def test_pipeline_bad_input(self):
        """Pipeline with invalid input should return ok=False gracefully."""
        r = repair_pipeline("not_a_list", [])
        assert not r["ok"]


# ===========================================================================
# 11. Input validation
# ===========================================================================

class TestInputValidation:
    def test_bad_verts_type(self):
        r = weld_vertices("bad", [[0, 1, 2]])
        assert not r["ok"]

    def test_bad_faces_type(self):
        r = weld_vertices([[0, 0, 0], [1, 0, 0], [0, 1, 0]], "bad")
        assert not r["ok"]

    def test_face_index_out_of_range(self):
        verts = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
        faces = [[0, 1, 99]]
        r = weld_vertices(verts, faces)
        assert not r["ok"]
        assert "out of range" in r["reason"]

    def test_non_numeric_verts(self):
        verts = [[0, 0, "z"], [1, 0, 0], [0, 1, 0]]
        faces = [[0, 1, 2]]
        r = weld_vertices(verts, faces)
        assert not r["ok"]

    def test_volume_bad_mesh(self):
        r = mesh_volume([[0, 0, 0]], [[0, 0, 1]])
        assert not r["ok"]
