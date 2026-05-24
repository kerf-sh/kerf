"""Tests for GK-P26: MultiresStack — base cage + per-level displacement stack."""
from __future__ import annotations
import math
import pytest
from kerf_cad_core.geom.subd_authoring import SubDCage, MultiresStack, MAX_MULTIRES_LEVELS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cube_cage() -> SubDCage:
    verts = [
        [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
        [-1, -1,  1], [1, -1,  1], [1, 1,  1], [-1, 1,  1],
    ]
    faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4],
             [2, 3, 7, 6], [0, 3, 7, 4], [1, 2, 6, 5]]
    return SubDCage(vertices=[list(v) for v in verts], faces=faces)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestMultiresStackConstruction:
    def test_creation(self):
        cage = make_cube_cage()
        stack = MultiresStack(cage=cage, max_levels=2)
        assert stack.cage is cage
        assert stack.max_levels == 2

    def test_max_levels_capped_at_six(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=99)
        assert stack.max_levels == MAX_MULTIRES_LEVELS

    def test_max_levels_minimum_one(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=0)
        assert stack.max_levels >= 1

    def test_no_displacements_by_default(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        assert stack.get_displacement(0, 0) == [0.0, 0.0, 0.0]
        assert stack.get_displacement(1, 0) == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# level_mesh
# ---------------------------------------------------------------------------

class TestLevelMesh:
    def test_level_zero_returns_base_verts(self):
        cage = make_cube_cage()
        stack = MultiresStack(cage=cage, max_levels=2)
        mesh0 = stack.level_mesh(0)
        assert len(mesh0.vertices) == len(cage.vertices)

    def test_level_one_has_more_verts_than_base(self):
        cage = make_cube_cage()
        stack = MultiresStack(cage=cage, max_levels=2)
        mesh0 = stack.level_mesh(0)
        mesh1 = stack.level_mesh(1)
        assert len(mesh1.vertices) > len(mesh0.vertices)

    def test_level_two_has_more_verts_than_one(self):
        cage = make_cube_cage()
        stack = MultiresStack(cage=cage, max_levels=2)
        mesh1 = stack.level_mesh(1)
        mesh2 = stack.level_mesh(2)
        assert len(mesh2.vertices) > len(mesh1.vertices)

    def test_level_clamped_to_max(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        mesh2 = stack.level_mesh(2)
        mesh99 = stack.level_mesh(99)
        # Both should return the same mesh (level 2 is max)
        assert len(mesh2.vertices) == len(mesh99.vertices)


# ---------------------------------------------------------------------------
# Displacement get/set
# ---------------------------------------------------------------------------

class TestDisplacementGetSet:
    def test_set_and_get_displacement(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        mesh0 = stack.level_mesh(0)
        n = len(mesh0.vertices)
        stack.set_displacement(0, 0, [0.1, 0.2, 0.3])
        d = stack.get_displacement(0, 0)
        assert abs(d[0] - 0.1) < 1e-10
        assert abs(d[1] - 0.2) < 1e-10
        assert abs(d[2] - 0.3) < 1e-10

    def test_get_unset_vertex_returns_zero(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        d = stack.get_displacement(1, 3)
        assert d == [0.0, 0.0, 0.0]

    def test_out_of_range_vertex_ignored(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        # Should not raise
        stack.set_displacement(0, 9999, [1.0, 0.0, 0.0])
        d = stack.get_displacement(0, 9999)
        assert d == [0.0, 0.0, 0.0]

    def test_out_of_range_level_clamped(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        # level 99 → clamped to max_levels=2
        stack.set_displacement(99, 0, [1.0, 0.0, 0.0])
        d = stack.get_displacement(2, 0)
        assert abs(d[0] - 1.0) < 1e-10

    def test_clear_level_removes_displacements(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        stack.set_displacement(1, 0, [1.0, 0.0, 0.0])
        stack.clear_level(1)
        assert stack.get_displacement(1, 0) == [0.0, 0.0, 0.0]

    def test_clear_all_removes_all(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        stack.set_displacement(0, 0, [1.0, 0.0, 0.0])
        stack.set_displacement(1, 0, [0.0, 1.0, 0.0])
        stack.clear_all()
        assert stack.get_displacement(0, 0) == [0.0, 0.0, 0.0]
        assert stack.get_displacement(1, 0) == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------

class TestEvaluate:
    def test_evaluate_no_displacement_matches_level_mesh(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        mesh_plain = stack.level_mesh(1)
        mesh_eval = stack.evaluate(1)
        assert len(mesh_eval.vertices) == len(mesh_plain.vertices)

    def test_evaluate_displacement_applied(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        mesh0 = stack.level_mesh(0)
        # Displace vertex 0 by (5, 0, 0)
        stack.set_displacement(0, 0, [5.0, 0.0, 0.0])
        mesh_eval = stack.evaluate(0)
        orig_x = mesh0.vertices[0][0]
        new_x = mesh_eval.vertices[0][0]
        assert abs(new_x - (orig_x + 5.0)) < 1e-10

    def test_evaluate_returns_subd_mesh(self):
        from kerf_cad_core.geom.subd import SubDMesh
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        result = stack.evaluate(1)
        assert hasattr(result, "vertices")
        assert hasattr(result, "faces")

    def test_evaluate_vertices_all_finite(self):
        stack = MultiresStack(cage=make_cube_cage(), max_levels=2)
        stack.set_displacement(1, 2, [0.1, -0.2, 0.3])
        mesh = stack.evaluate(1)
        for v in mesh.vertices:
            for c in v:
                assert math.isfinite(c), f"Non-finite coord in evaluated mesh: {c}"


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

class TestSerialisaion:
    def test_round_trip(self):
        cage = make_cube_cage()
        stack = MultiresStack(cage=cage, max_levels=2)
        stack.set_displacement(0, 0, [0.5, -0.5, 1.0])
        stack.set_displacement(1, 3, [0.0, 0.1, 0.0])

        d = stack.to_dict()
        stack2 = MultiresStack.from_dict(d)

        assert len(stack2.cage.vertices) == len(cage.vertices)
        assert stack2.max_levels == 2

        d0 = stack2.get_displacement(0, 0)
        assert abs(d0[0] - 0.5) < 1e-10

        d1 = stack2.get_displacement(1, 3)
        assert abs(d1[1] - 0.1) < 1e-10

    def test_empty_displacements_round_trip(self):
        cage = make_cube_cage()
        stack = MultiresStack(cage=cage, max_levels=3)
        d = stack.to_dict()
        stack2 = MultiresStack.from_dict(d)
        assert stack2.get_displacement(0, 0) == [0.0, 0.0, 0.0]
