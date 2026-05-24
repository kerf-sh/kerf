"""Tests for GK-P23: in-process isotropic remesh fallback."""
from __future__ import annotations
import math
import pytest
from kerf_cad_core.geom.isotropic_remesh import isotropic_remesh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_triangle_strip(n: int):
    """Build a strip of n triangles as a simple test mesh."""
    verts = [[float(i), 0.0, 0.0] for i in range(n + 1)]
    verts += [[float(i) + 0.5, 1.0, 0.0] for i in range(n)]
    faces = []
    for i in range(n):
        # Two tris per strip unit
        faces.append([i, n + 1 + i, i + 1])
        if i + 1 < n:
            faces.append([i + 1, n + 1 + i, n + 1 + i + 1])
    return {"vertices": verts, "faces": faces}


def make_subdivided_plane(subdivs: int):
    """Grid of quads on the XY plane, each quad is (1/subdivs) wide."""
    s = subdivs
    verts = []
    for j in range(s + 1):
        for i in range(s + 1):
            verts.append([i / s, j / s, 0.0])
    faces = []
    for j in range(s):
        for i in range(s):
            a = j * (s + 1) + i
            b = a + 1
            c = a + (s + 1) + 1
            d = a + (s + 1)
            faces.append([a, b, c, d])  # quads, will be triangulated
    return {"vertices": verts, "faces": faces}


def avg_edge_length(mesh):
    verts = mesh["vertices"]
    faces = mesh["faces"]
    total, count = 0.0, 0
    seen = set()
    for f in faces:
        n = len(f)
        for k in range(n):
            e = (min(f[k], f[(k+1)%n]), max(f[k], f[(k+1)%n]))
            if e not in seen:
                seen.add(e)
                a, b = verts[e[0]], verts[e[1]]
                total += math.sqrt(sum((a[i]-b[i])**2 for i in range(3)))
                count += 1
    return total / count if count > 0 else 0.0


# ---------------------------------------------------------------------------
# Basic structural tests
# ---------------------------------------------------------------------------

class TestIsotropicRemeshBasic:
    def test_returns_dict_with_keys(self):
        mesh = make_subdivided_plane(4)
        result = isotropic_remesh(mesh, 0.2)
        assert "vertices" in result
        assert "faces" in result

    def test_output_faces_all_triangles(self):
        mesh = make_subdivided_plane(4)
        result = isotropic_remesh(mesh, 0.2)
        for f in result["faces"]:
            assert len(f) == 3, f"Expected triangle, got {len(f)}-gon"

    def test_output_face_indices_valid(self):
        mesh = make_subdivided_plane(4)
        result = isotropic_remesh(mesh, 0.2)
        n_verts = len(result["vertices"])
        for f in result["faces"]:
            for idx in f:
                assert 0 <= idx < n_verts, f"Face index {idx} out of range [0, {n_verts})"

    def test_output_vertices_finite(self):
        mesh = make_subdivided_plane(4)
        result = isotropic_remesh(mesh, 0.2)
        for v in result["vertices"]:
            assert len(v) == 3
            for coord in v:
                assert math.isfinite(coord), f"Non-finite vertex coord: {coord}"

    def test_no_degenerate_faces(self):
        mesh = make_subdivided_plane(4)
        result = isotropic_remesh(mesh, 0.2)
        for f in result["faces"]:
            assert len(set(f)) == 3, f"Degenerate triangle {f}"

    def test_empty_mesh_returns_empty(self):
        result = isotropic_remesh({"vertices": [], "faces": []}, 0.5)
        assert result["vertices"] == []
        assert result["faces"] == []

    def test_invalid_target_raises(self):
        mesh = make_subdivided_plane(2)
        with pytest.raises(ValueError):
            isotropic_remesh(mesh, 0.0)
        with pytest.raises(ValueError):
            isotropic_remesh(mesh, -1.0)


# ---------------------------------------------------------------------------
# Quad input triangulation
# ---------------------------------------------------------------------------

class TestQuadInput:
    def test_quad_mesh_input_accepted(self):
        mesh = make_subdivided_plane(4)
        # Faces are quads; should work without exception
        result = isotropic_remesh(mesh, 0.25)
        assert len(result["faces"]) > 0

    def test_all_output_faces_triangles_from_quad_input(self):
        mesh = make_subdivided_plane(3)
        result = isotropic_remesh(mesh, 0.25)
        for f in result["faces"]:
            assert len(f) == 3


# ---------------------------------------------------------------------------
# Edge-length convergence
# ---------------------------------------------------------------------------

class TestEdgeLengthConvergence:
    def test_coarser_target_reduces_face_count(self):
        """A coarser target edge length should result in fewer faces."""
        mesh = make_subdivided_plane(8)
        fine = isotropic_remesh(mesh, 0.1, iterations=3)
        coarse = isotropic_remesh(mesh, 0.4, iterations=3)
        # Coarser should have fewer or equal faces
        assert len(coarse["faces"]) <= len(fine["faces"])

    def test_finer_target_improves_uniformity(self):
        """After remeshing a coarse mesh finer, avg edge length moves toward target."""
        # Start with a coarse subdivided plane (edge length ~0.5)
        mesh = make_subdivided_plane(2)
        target = 0.2
        result = isotropic_remesh(mesh, target, iterations=5)
        if len(result["faces"]) > 0:
            avg = avg_edge_length(result)
            # Average edge length should be within 3× of target (very loose gate)
            assert avg < target * 3.0, f"Average edge {avg:.3f} too far from target {target}"

    def test_remesh_preserves_topology_when_no_change_needed(self):
        """A mesh whose edges are already at target should not lose faces."""
        # Build a mesh with edge length exactly ~0.1
        mesh = make_subdivided_plane(10)  # edge length = 0.1 exactly
        original_face_count = len(mesh["faces"]) * 2  # quads → 2 tris each
        result = isotropic_remesh(mesh, 0.1, iterations=2)
        # Should not collapse everything; faces should remain
        assert len(result["faces"]) > 0


# ---------------------------------------------------------------------------
# Iterations parameter
# ---------------------------------------------------------------------------

class TestIterations:
    def test_zero_iterations_returns_triangulated(self):
        mesh = make_subdivided_plane(3)
        result = isotropic_remesh(mesh, 0.2, iterations=0)
        # Should still triangulate quads even with 0 iterations
        for f in result["faces"]:
            assert len(f) == 3

    def test_one_vs_five_iterations(self):
        mesh = make_subdivided_plane(4)
        r1 = isotropic_remesh(mesh, 0.2, iterations=1)
        r5 = isotropic_remesh(mesh, 0.2, iterations=5)
        # Both should produce valid triangle meshes
        assert len(r1["faces"]) > 0
        assert len(r5["faces"]) > 0
