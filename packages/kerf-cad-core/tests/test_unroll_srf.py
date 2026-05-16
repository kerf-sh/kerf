"""
test_unroll_srf.py
==================
Tests for geom/unroll_srf.py -- UnrollSrf Rhino-parity developable-surface
flatten.  All tests are hermetic (no DB, no OCCT, no network).

Coverage:
  - is_developable: plane, cylinder, cone, mesh (flat/curved)
  - unroll_developable: cylinder (exact rect), cone (exact sector), plane (identity)
  - unroll_strip: triangle mesh hinge-unfold; edge-length preservation; BFS coverage
  - smash: PCA flatten; distortion map; planar -> zero distortion
  - project_curves_to_unrolled: cylinder arc -> flat, cone, plane identity
  - surface_diagnostics: combined helper
  - error paths: bad inputs, missing fields, zero dims
"""

from __future__ import annotations

import math
import pytest
import numpy as np

from kerf_cad_core.geom.unroll_srf import (
    is_developable,
    unroll_developable,
    unroll_strip,
    smash,
    project_curves_to_unrolled,
    surface_diagnostics,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat_quad(w, h, nx=4, ny=4):
    """Build a flat rectangular mesh (nx*ny verts, 2*(nx-1)*(ny-1) tris)."""
    verts = []
    for j in range(ny):
        for i in range(nx):
            verts.append([i * w / (nx - 1), j * h / (ny - 1), 0.0])
    faces = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            b = a + 1
            c = (j + 1) * nx + i
            d = c + 1
            faces.append([a, b, d])
            faces.append([a, d, c])
    return verts, faces


def _cylinder_strip_mesh(R, H, n_theta=12, n_z=3):
    """Build a triangulated cylinder strip for near-developable tests."""
    verts = []
    for j in range(n_z):
        z = j * H / (n_z - 1)
        for i in range(n_theta):
            theta = 2 * math.pi * i / n_theta
            verts.append([R * math.cos(theta), R * math.sin(theta), z])
    faces = []
    for j in range(n_z - 1):
        for i in range(n_theta):
            a = j * n_theta + i
            b = j * n_theta + (i + 1) % n_theta
            c = (j + 1) * n_theta + i
            d = (j + 1) * n_theta + (i + 1) % n_theta
            faces.append([a, b, d])
            faces.append([a, d, c])
    return verts, faces


def _sphere_strip_mesh(R=1.0, n=8):
    """Sphere cap -- non-developable (K ~= 1/R^2)."""
    verts = []
    faces = []
    for i in range(n + 1):
        phi = math.pi / 2 * i / n
        for j in range(n + 1):
            theta = 2 * math.pi * j / n
            verts.append([
                R * math.cos(phi) * math.cos(theta),
                R * math.cos(phi) * math.sin(theta),
                R * math.sin(phi),
            ])
    for i in range(n):
        for j in range(n):
            a = i * (n + 1) + j
            b = a + 1
            c = (i + 1) * (n + 1) + j
            d = c + 1
            faces.append([a, b, d])
            faces.append([a, d, c])
    return verts, faces


# ---------------------------------------------------------------------------
# 1. is_developable -- analytical surfaces always developable
# ---------------------------------------------------------------------------

def test_cylinder_is_developable():
    result = is_developable({"type": "cylinder", "radius": 5.0, "height": 10.0, "sweep": math.pi})
    assert result["ok"]
    assert result["is_developable"] is True
    assert result["max_gaussian"] == pytest.approx(0.0)


def test_cone_is_developable():
    result = is_developable({"type": "cone", "base_radius": 3.0, "apex_height": 4.0, "sweep": 2 * math.pi})
    assert result["ok"]
    assert result["is_developable"] is True


def test_plane_is_developable():
    result = is_developable({"type": "plane"})
    assert result["ok"]
    assert result["is_developable"] is True
    assert result["max_gaussian"] == pytest.approx(0.0)


def test_flat_mesh_is_developable():
    verts, faces = _flat_quad(4.0, 3.0)
    result = is_developable({"type": "mesh", "vertices": verts, "faces": faces})
    assert result["ok"]
    # Interior vertices of a flat mesh have zero angle deficit; boundary vertices
    # are zeroed out. max_gaussian should be 0 or near 0.
    assert result["is_developable"] is True
    assert result["max_gaussian"] < 1e-10


def test_sphere_mesh_not_developable():
    verts, faces = _sphere_strip_mesh(R=1.0, n=8)
    result = is_developable({"type": "mesh", "vertices": verts, "faces": faces}, tol=1e-4)
    assert result["ok"]
    assert result["max_gaussian"] > 1e-4


def test_is_developable_unknown_type():
    result = is_developable({"type": "torus"})
    assert not result["ok"]
    assert "unknown" in result["reason"].lower()


# ---------------------------------------------------------------------------
# 2. unroll_developable -- cylinder exact
# ---------------------------------------------------------------------------

def test_cylinder_unroll_flat_width_exact():
    R, H, theta = 5.0, 10.0, math.pi / 2
    result = unroll_developable({"type": "cylinder", "radius": R, "height": H, "sweep": theta})
    assert result["ok"]
    assert result["surface_type"] == "cylinder"
    assert result["developed_width"] == pytest.approx(R * theta, rel=1e-9)


def test_cylinder_unroll_flat_height_exact():
    R, H, theta = 3.0, 7.5, math.pi
    result = unroll_developable({"type": "cylinder", "radius": R, "height": H, "sweep": theta})
    assert result["ok"]
    assert result["developed_height"] == pytest.approx(H, rel=1e-9)


def test_cylinder_unroll_full_circle():
    R, H = 2.0, 5.0
    result = unroll_developable({"type": "cylinder", "radius": R, "height": H, "sweep": 2 * math.pi})
    assert result["ok"]
    assert result["developed_width"] == pytest.approx(2 * math.pi * R, rel=1e-9)
    assert result["developed_height"] == pytest.approx(H, rel=1e-9)


def test_cylinder_unroll_vertices_count():
    result = unroll_developable({"type": "cylinder", "radius": 1.0, "height": 2.0, "sweep": math.pi})
    assert result["ok"]
    assert len(result["flat_vertices"]) == len(result["flat_vertices_3d"])
    assert len(result["flat_vertices"]) > 0


def test_cylinder_unroll_2d_is_rectangle():
    R, H, theta = 4.0, 6.0, math.pi / 3
    result = unroll_developable({"type": "cylinder", "radius": R, "height": H, "sweep": theta})
    assert result["ok"]
    fv = np.array(result["flat_vertices"])
    assert fv[:, 0].min() >= -1e-9
    assert fv[:, 0].max() <= R * theta + 1e-9
    assert fv[:, 1].min() >= -1e-9
    assert fv[:, 1].max() <= H + 1e-9


# ---------------------------------------------------------------------------
# 3. unroll_developable -- cone exact
# ---------------------------------------------------------------------------

def test_cone_unroll_slant_length():
    R, H = 3.0, 4.0
    result = unroll_developable({"type": "cone", "base_radius": R, "apex_height": H, "sweep": 2 * math.pi})
    assert result["ok"]
    assert result["slant_length"] == pytest.approx(5.0, rel=1e-9)


def test_cone_unroll_sector_angle():
    R, H, sweep = 3.0, 4.0, 2 * math.pi
    slant = math.sqrt(R ** 2 + H ** 2)
    expected_sector = sweep * (R / slant)
    result = unroll_developable({"type": "cone", "base_radius": R, "apex_height": H, "sweep": sweep})
    assert result["ok"]
    assert result["sector_angle"] == pytest.approx(expected_sector, rel=1e-9)


def test_cone_unroll_partial_sweep():
    R, H = 3.0, 4.0
    slant = math.sqrt(R ** 2 + H ** 2)
    sin_a = R / slant
    for sweep in [math.pi / 4, math.pi / 2, math.pi]:
        result = unroll_developable({"type": "cone", "base_radius": R, "apex_height": H, "sweep": sweep})
        assert result["ok"], f"sweep={sweep}: {result['reason']}"
        assert result["sector_angle"] == pytest.approx(sweep * sin_a, rel=1e-9)


def test_cone_unroll_developed_height_equals_slant():
    R, H = 5.0, 12.0
    slant = math.sqrt(R ** 2 + H ** 2)
    result = unroll_developable({"type": "cone", "base_radius": R, "apex_height": H, "sweep": 2 * math.pi})
    assert result["ok"]
    assert result["developed_height"] == pytest.approx(slant, rel=1e-9)


def test_cone_unroll_vertices_count():
    result = unroll_developable({"type": "cone", "base_radius": 2.0, "apex_height": 3.0, "sweep": math.pi})
    assert result["ok"]
    assert len(result["flat_vertices"]) == len(result["flat_vertices_3d"])
    assert len(result["flat_vertices"]) > 0


# ---------------------------------------------------------------------------
# 4. unroll_developable -- plane (identity)
# ---------------------------------------------------------------------------

def test_plane_unroll_identity():
    W, H = 5.0, 3.0
    result = unroll_developable({"type": "plane", "width": W, "height": H})
    assert result["ok"]
    fv = np.array(result["flat_vertices"])
    fv3 = np.array(result["flat_vertices_3d"])
    np.testing.assert_allclose(fv[:, 0], fv3[:, 0], atol=1e-12)
    np.testing.assert_allclose(fv[:, 1], fv3[:, 1], atol=1e-12)
    np.testing.assert_allclose(fv3[:, 2], 0.0, atol=1e-12)


def test_plane_unroll_dimensions():
    W, H = 7.0, 2.5
    result = unroll_developable({"type": "plane", "width": W, "height": H})
    assert result["ok"]
    assert result["developed_width"] == pytest.approx(W, rel=1e-9)
    assert result["developed_height"] == pytest.approx(H, rel=1e-9)


# ---------------------------------------------------------------------------
# 5. unroll_developable -- error paths
# ---------------------------------------------------------------------------

def test_unroll_cylinder_missing_field():
    result = unroll_developable({"type": "cylinder", "radius": 5.0})
    assert not result["ok"]


def test_unroll_cylinder_zero_radius():
    result = unroll_developable({"type": "cylinder", "radius": 0.0, "height": 5.0, "sweep": math.pi})
    assert not result["ok"]


def test_unroll_cone_zero_height():
    result = unroll_developable({"type": "cone", "base_radius": 3.0, "apex_height": 0.0, "sweep": math.pi})
    assert not result["ok"]


def test_unroll_unknown_type():
    result = unroll_developable({"type": "sphere"})
    assert not result["ok"]
    assert "unsupported" in result["reason"].lower() or "sphere" in result["reason"].lower()


def test_unroll_bad_sweep():
    result = unroll_developable({"type": "cylinder", "radius": 2.0, "height": 3.0, "sweep": -1.0})
    assert not result["ok"]


# ---------------------------------------------------------------------------
# 6. unroll_strip -- edge-length preservation on flat quad mesh
# ---------------------------------------------------------------------------

def test_strip_flat_mesh_zero_distortion():
    verts, faces = _flat_quad(4.0, 3.0, nx=5, ny=4)
    result = unroll_strip(verts, faces)
    assert result["ok"]
    assert result["max_length_distortion"] < 1e-9
    assert result["max_area_distortion"] < 1e-9


def test_strip_flat_mesh_dimensions():
    verts, faces = _flat_quad(4.0, 3.0, nx=5, ny=4)
    result = unroll_strip(verts, faces)
    assert result["ok"]
    assert result["total_developed_width"] == pytest.approx(4.0, rel=1e-3)
    assert result["total_developed_height"] == pytest.approx(3.0, rel=1e-3)


def test_strip_returns_flat_vertices_for_every_vertex():
    verts, faces = _flat_quad(2.0, 2.0, nx=4, ny=4)
    result = unroll_strip(verts, faces)
    assert result["ok"]
    assert len(result["flat_vertices"]) == len(verts)


def test_strip_distortion_list_length():
    verts, faces = _flat_quad(3.0, 2.0)
    result = unroll_strip(verts, faces)
    assert result["ok"]
    assert len(result["distortion"]) == len(faces)


def test_strip_flat_mesh_single_triangle():
    """A single triangle should unfold with zero distortion."""
    verts = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    faces = [[0, 1, 2]]
    result = unroll_strip(verts, faces)
    assert result["ok"]
    assert result["max_length_distortion"] < 1e-9


def test_strip_bad_input_empty_verts():
    result = unroll_strip([], [[0, 1, 2]])
    assert not result["ok"]


def test_strip_bad_input_no_faces():
    result = unroll_strip([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [])
    assert not result["ok"]


# ---------------------------------------------------------------------------
# 7. smash -- PCA flatten
# ---------------------------------------------------------------------------

def test_smash_flat_mesh_zero_distortion():
    verts, faces = _flat_quad(3.0, 2.0, nx=5, ny=4)
    result = smash(verts, faces)
    assert result["ok"]
    assert result["max_area_distortion"] < 1e-6


def test_smash_returns_correct_vertex_count():
    verts, faces = _flat_quad(2.0, 2.0)
    result = smash(verts, faces)
    assert result["ok"]
    assert len(result["flat_vertices"]) == len(verts)


def test_smash_distortion_map_length():
    verts, faces = _flat_quad(2.0, 2.0)
    result = smash(verts, faces, report_distortion=True)
    assert result["ok"]
    assert len(result["distortion_map"]) == len(faces)


def test_smash_no_distortion_report():
    verts, faces = _flat_quad(2.0, 2.0)
    result = smash(verts, faces, report_distortion=False)
    assert result["ok"]
    assert result["distortion_map"] == []


def test_smash_sphere_has_distortion():
    verts, faces = _sphere_strip_mesh(R=1.0, n=8)
    result = smash(verts, faces)
    assert result["ok"]
    assert result["max_area_distortion"] > 1e-4


def test_smash_bad_input():
    result = smash([], [])
    assert not result["ok"]


def test_smash_returns_2d_vertices():
    verts, faces = _flat_quad(1.0, 1.0)
    result = smash(verts, faces)
    assert result["ok"]
    flat = result["flat_vertices"]
    assert all(len(v) == 2 for v in flat)


# ---------------------------------------------------------------------------
# 8. project_curves_to_unrolled
# ---------------------------------------------------------------------------

def test_project_cylinder_horizontal_arc_length_preserved():
    R, sweep = 2.0, math.pi
    z = 3.0
    n = 100
    pts = [[R * math.cos(t), R * math.sin(t), z] for t in np.linspace(0, sweep, n)]
    result = project_curves_to_unrolled(
        {"type": "cylinder", "radius": R},
        [pts],
    )
    assert result["ok"]
    flat = np.array(result["flat_curves"][0])
    np.testing.assert_allclose(flat[:, 1], z, atol=1e-10)
    assert flat[:, 0].min() == pytest.approx(0.0, abs=1e-9)
    assert flat[:, 0].max() == pytest.approx(R * sweep, rel=1e-6)


def test_project_plane_identity():
    pts = [[1.0, 2.0, 5.0], [3.0, 4.0, 7.0]]
    result = project_curves_to_unrolled({"type": "plane"}, [pts])
    assert result["ok"]
    flat = result["flat_curves"][0]
    assert flat[0] == pytest.approx([1.0, 2.0], abs=1e-12)
    assert flat[1] == pytest.approx([3.0, 4.0], abs=1e-12)


def test_project_cone_apex_maps_to_origin():
    R, H = 3.0, 4.0
    pts = [[0.0, 0.0, H]]  # apex
    result = project_curves_to_unrolled(
        {"type": "cone", "base_radius": R, "apex_height": H, "sweep": 2 * math.pi},
        [pts],
    )
    assert result["ok"]
    flat = result["flat_curves"][0][0]
    assert math.hypot(flat[0], flat[1]) == pytest.approx(0.0, abs=1e-9)


def test_project_curves_empty_curve():
    result = project_curves_to_unrolled({"type": "plane"}, [[]])
    assert result["ok"]
    assert result["flat_curves"] == [[]]


def test_project_curves_multiple_curves():
    pts1 = [[1.0, 2.0, 0.0], [3.0, 4.0, 0.0]]
    pts2 = [[5.0, 6.0, 0.0]]
    result = project_curves_to_unrolled({"type": "plane"}, [pts1, pts2])
    assert result["ok"]
    assert len(result["flat_curves"]) == 2


# ---------------------------------------------------------------------------
# 9. surface_diagnostics
# ---------------------------------------------------------------------------

def test_diagnostics_cylinder():
    result = surface_diagnostics({"type": "cylinder", "radius": 5.0, "height": 8.0, "sweep": math.pi})
    assert result["ok"]
    assert result["is_developable"] is True
    assert result["developed_width"] == pytest.approx(5.0 * math.pi, rel=1e-9)
    assert result["developed_height"] == pytest.approx(8.0, rel=1e-9)


def test_diagnostics_cone():
    R, H = 3.0, 4.0
    slant = math.sqrt(R ** 2 + H ** 2)
    result = surface_diagnostics({"type": "cone", "base_radius": R, "apex_height": H, "sweep": 2 * math.pi})
    assert result["ok"]
    assert result["is_developable"] is True
    assert result["developed_height"] == pytest.approx(slant, rel=1e-9)


def test_diagnostics_unknown_type_fails():
    result = surface_diagnostics({"type": "donut"})
    assert not result["ok"]


# ---------------------------------------------------------------------------
# 10. arc-length along rulings preserved by cylinder unroll
# ---------------------------------------------------------------------------

def test_cylinder_ruling_arc_length_preserved():
    """A ruling on a cylinder (constant theta, varying z) has length H.
    After unrolling, the same ruling is a vertical line with length H."""
    R, H = 3.0, 6.0
    pts = [[R, 0.0, 0.0], [R, 0.0, H]]
    result = project_curves_to_unrolled(
        {"type": "cylinder", "radius": R, "height": H, "sweep": math.pi},
        [pts],
    )
    assert result["ok"]
    flat = np.array(result["flat_curves"][0])
    length_2d = float(np.linalg.norm(flat[1] - flat[0]))
    assert length_2d == pytest.approx(H, rel=1e-9)
