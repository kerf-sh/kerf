"""Tests for GK-P21: subd_extrude_along — extrude face along curve."""
from __future__ import annotations
import math
import pytest
from kerf_cad_core.geom.subd_authoring import SubDCage, subd_extrude_along


def make_quad_cage() -> SubDCage:
    """Simple 2-face cage for testing extrusion."""
    verts = [
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [2, 0, 0], [2, 1, 0],
    ]
    faces = [[0, 1, 2, 3], [1, 4, 5, 2]]
    return SubDCage(vertices=[list(v) for v in verts], faces=faces)


class TestSubdExtrudeAlong:
    def test_extrude_straight_adds_vertices(self):
        cage = make_quad_cage()
        # Extrude face 0 (quad, 4 verts) along 3 points → 2 extra rings
        curve = [[0,0,0],[0,0,1],[0,0,2]]
        result = subd_extrude_along(cage, 0, curve)
        # Original 6 verts + 2 rings * 4 = 14 verts
        assert len(result.vertices) == 14

    def test_extrude_straight_face_count(self):
        cage = make_quad_cage()
        curve = [[0,0,0],[0,0,1],[0,0,2]]
        result = subd_extrude_along(cage, 0, curve)
        # Keeps face 1 (1 face)
        # 2 segments × 4 side quads = 8 side quads
        # 1 cap = 1 face
        # Total = 1 + 8 + 1 = 10
        assert len(result.faces) == 10

    def test_extrude_cap_at_end(self):
        cage = make_quad_cage()
        curve = [[0,0,0],[0,0,1]]
        result = subd_extrude_along(cage, 0, curve)
        # Last face should be the cap (reversed ring)
        cap = result.faces[-1]
        assert len(cap) == 4

    def test_extrude_removes_original_face(self):
        cage = make_quad_cage()
        curve = [[0,0,0],[0,0,1]]
        result = subd_extrude_along(cage, 0, curve)
        # Face 0 should not appear in result
        orig_face = cage.faces[0]
        for f in result.faces:
            assert sorted(f) != sorted(orig_face), "Original face still present"

    def test_extrude_side_quads_topology(self):
        cage = SubDCage(
            vertices=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],
            faces=[[0,1,2,3]],
        )
        curve = [[0,0,0],[0,0,1]]
        result = subd_extrude_along(cage, 0, curve)
        # 4 side quads + 1 cap = 5 faces (original removed)
        assert len(result.faces) == 5
        # All side quads should be quads
        for f in result.faces[:-1]:  # all but last cap
            assert len(f) == 4

    def test_extrude_invalid_face_returns_copy(self):
        cage = make_quad_cage()
        result = subd_extrude_along(cage, 99, [[0,0,0],[0,0,1]])
        assert result.vertices == cage.vertices

    def test_extrude_single_curve_point_returns_copy(self):
        cage = make_quad_cage()
        result = subd_extrude_along(cage, 0, [[0,0,0]])
        assert result.vertices == cage.vertices

    def test_extrude_curved_path(self):
        """Extrude along a curved path (L-shape)."""
        cage = SubDCage(
            vertices=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],
            faces=[[0,1,2,3]],
        )
        # L-shaped path: straight then turn
        curve = [[0,0,0],[0,0,1],[0,1,1]]
        result = subd_extrude_along(cage, 0, curve)
        # 4 verts + 2 rings of 4 = 12 verts
        assert len(result.vertices) == 12
        assert len(result.faces) > 0
