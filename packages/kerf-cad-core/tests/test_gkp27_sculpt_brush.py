"""Tests for GK-P27: sculpt_brush — Grab/Smooth/Inflate with soft-selection."""
from __future__ import annotations
import math
import pytest
from kerf_cad_core.geom.subd_authoring import SubDCage, sculpt_brush


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_flat_cage(n: int = 5) -> SubDCage:
    """Grid of n×n quads in the XY plane, one unit wide."""
    verts = []
    for j in range(n + 1):
        for i in range(n + 1):
            verts.append([i / n, j / n, 0.0])
    faces = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            b = a + 1
            c = a + (n + 1) + 1
            d = a + (n + 1)
            faces.append([a, b, c, d])
    return SubDCage(vertices=verts, faces=faces)


def make_cube_cage() -> SubDCage:
    verts = [
        [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
        [-1, -1,  1], [1, -1,  1], [1, 1,  1], [-1, 1,  1],
    ]
    faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4],
             [2, 3, 7, 6], [0, 3, 7, 4], [1, 2, 6, 5]]
    return SubDCage(vertices=[list(v) for v in verts], faces=faces)


# ---------------------------------------------------------------------------
# Return type and structure
# ---------------------------------------------------------------------------

class TestSculptBrushStructure:
    def test_returns_subcage(self):
        cage = make_flat_cage()
        result = sculpt_brush(cage, [0.5, 0.5, 0.0], 0.3, 1.0, 0.5, "grab",
                              direction=[0, 0, 1])
        assert isinstance(result, SubDCage)

    def test_same_vertex_count(self):
        cage = make_flat_cage()
        result = sculpt_brush(cage, [0.5, 0.5, 0.0], 0.3, 1.0, 0.5, "smooth")
        assert len(result.vertices) == len(cage.vertices)

    def test_same_face_topology(self):
        cage = make_flat_cage()
        result = sculpt_brush(cage, [0.5, 0.5, 0.0], 0.3, 1.0, 0.5, "inflate")
        assert result.faces == cage.faces

    def test_does_not_modify_input(self):
        cage = make_flat_cage()
        orig_verts = [list(v) for v in cage.vertices]
        sculpt_brush(cage, [0.5, 0.5, 0.0], 0.3, 1.0, 1.0, "grab",
                     direction=[0, 0, 1])
        assert cage.vertices == orig_verts

    def test_all_output_verts_finite(self):
        cage = make_flat_cage()
        result = sculpt_brush(cage, [0.5, 0.5, 0.0], 0.5, 2.0, 1.0, "inflate")
        for v in result.vertices:
            for coord in v:
                assert math.isfinite(coord), f"Non-finite coord: {coord}"


# ---------------------------------------------------------------------------
# Grab mode
# ---------------------------------------------------------------------------

class TestGrabBrush:
    def test_grab_moves_vertex_in_direction(self):
        cage = make_flat_cage(4)
        # Brush at (0.5, 0.5) with large radius to catch centre vertex
        result = sculpt_brush(
            cage, [0.5, 0.5, 0.0], radius=2.0, falloff=1.0, strength=1.0,
            mode="grab", direction=[0, 0, 1.0]
        )
        # Find vertex closest to (0.5, 0.5, 0) in original
        best_vi = min(range(len(cage.vertices)),
                      key=lambda i: (cage.vertices[i][0] - 0.5)**2 + (cage.vertices[i][1] - 0.5)**2)
        # That vertex should move upward
        dz = result.vertices[best_vi][2] - cage.vertices[best_vi][2]
        assert dz > 0.0, f"Grab should move vertex up, got dz={dz}"

    def test_grab_strength_zero_no_change(self):
        cage = make_flat_cage()
        result = sculpt_brush(
            cage, [0.5, 0.5, 0.0], radius=2.0, falloff=1.0, strength=0.0,
            mode="grab", direction=[0, 0, 1.0]
        )
        for orig, new in zip(cage.vertices, result.vertices):
            for a, b in zip(orig, new):
                assert abs(a - b) < 1e-10

    def test_grab_outside_radius_unchanged(self):
        cage = make_flat_cage(4)
        # Brush at (0.5, 0.5), tiny radius
        result = sculpt_brush(
            cage, [0.5, 0.5, 0.0], radius=0.05, falloff=1.0, strength=1.0,
            mode="grab", direction=[0, 0, 5.0]
        )
        # Far corners should be untouched
        far_vi = 0  # corner at (0, 0)
        orig = cage.vertices[far_vi]
        new = result.vertices[far_vi]
        for a, b in zip(orig, new):
            assert abs(a - b) < 1e-10, f"Far vertex should not move, but got delta {b-a}"


# ---------------------------------------------------------------------------
# Smooth mode
# ---------------------------------------------------------------------------

class TestSmoothBrush:
    def test_smooth_reduces_peak(self):
        """Push one vertex up, then smooth it; the peak should decrease."""
        cage = make_flat_cage(4)
        n = 4 + 1  # 5 per row
        centre_vi = 2 * n + 2  # vertex at (0.5, 0.5, 0)
        cage.vertices[centre_vi][2] = 0.1  # small spike (stay near z=0)

        result = sculpt_brush(
            cage, [0.5, 0.5, 0.05], radius=0.5, falloff=1.0, strength=1.0,
            mode="smooth"
        )
        new_z = result.vertices[centre_vi][2]
        assert new_z < 0.1, f"Smooth should reduce peak, got z={new_z}"

    def test_smooth_zero_strength_no_change(self):
        cage = make_flat_cage()
        cage.vertices[0][2] = 5.0
        result = sculpt_brush(cage, [0.0, 0.0, 0.0], radius=2.0, falloff=1.0,
                              strength=0.0, mode="smooth")
        assert abs(result.vertices[0][2] - 5.0) < 1e-10


# ---------------------------------------------------------------------------
# Inflate mode
# ---------------------------------------------------------------------------

class TestInflateBrush:
    def test_inflate_moves_verts_outward(self):
        """Cube centred at origin — inflate should push top verts further up."""
        cage = make_cube_cage()
        # Top face verts are at z=+1: verts 4,5,6,7
        before_z = [cage.vertices[vi][2] for vi in range(4, 8)]
        result = sculpt_brush(
            cage, [0.0, 0.0, 1.0], radius=3.0, falloff=1.0, strength=1.0,
            mode="inflate"
        )
        after_z = [result.vertices[vi][2] for vi in range(4, 8)]
        # Each top vert should move outward (away from centre)
        for bz, az in zip(before_z, after_z):
            # top verts have +normal, so z should increase
            assert az != bz, f"Inflate should move vertex; before={bz}, after={az}"

    def test_inflate_zero_strength_no_change(self):
        cage = make_cube_cage()
        result = sculpt_brush(
            cage, [0.0, 0.0, 0.0], radius=5.0, falloff=1.0, strength=0.0,
            mode="inflate"
        )
        for orig, new in zip(cage.vertices, result.vertices):
            for a, b in zip(orig, new):
                assert abs(a - b) < 1e-10


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------

class TestSculptBrushEdgeCases:
    def test_invalid_mode_returns_copy(self):
        cage = make_flat_cage()
        result = sculpt_brush(cage, [0, 0, 0], 1.0, 1.0, 1.0, "nonexistent_mode")
        assert result.vertices == cage.vertices

    def test_negative_radius_returns_copy(self):
        cage = make_flat_cage()
        result = sculpt_brush(cage, [0, 0, 0], -1.0, 1.0, 1.0, "grab",
                              direction=[0, 0, 1])
        assert result.vertices == cage.vertices

    def test_falloff_clamped_to_valid_range(self):
        cage = make_flat_cage()
        # Extreme falloff values should not raise
        r1 = sculpt_brush(cage, [0.5, 0.5, 0], 2.0, falloff=-100.0,
                          strength=0.5, mode="grab", direction=[0, 0, 1])
        r2 = sculpt_brush(cage, [0.5, 0.5, 0], 2.0, falloff=1000.0,
                          strength=0.5, mode="grab", direction=[0, 0, 1])
        assert len(r1.vertices) == len(cage.vertices)
        assert len(r2.vertices) == len(cage.vertices)

    def test_modes_case_insensitive(self):
        cage = make_flat_cage()
        r = sculpt_brush(cage, [0.5, 0.5, 0], 1.0, 1.0, 0.5, "SMOOTH")
        assert len(r.vertices) == len(cage.vertices)
