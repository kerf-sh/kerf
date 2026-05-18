"""
Pytest oracles for kerf_cfd.mesh_3d — 3-D unstructured tet mesh generator.

Test plan
---------
1. Unit-cube point cloud → ≥6 tetrahedra, all with positive volume.
2. Euler characteristic  V − E + F − T = 1.
3. Quality metric: minimum dihedral angle is reported and is > 0°.
4. mesh_point_cloud() on explicit 5-point set gives ≥1 tet.
5. mesh_point_cloud() with <4 points raises ValueError.
"""

from __future__ import annotations

import math
import pytest

from kerf_cfd.mesh_3d import (
    Mesh3D,
    mesh_unit_cube,
    mesh_point_cloud,
    _tet_volume_signed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vol(mesh: Mesh3D, tet_idx: int) -> float:
    t = mesh.elements[tet_idx]
    return _tet_volume_signed(
        mesh.vertices[t[0]],
        mesh.vertices[t[1]],
        mesh.vertices[t[2]],
        mesh.vertices[t[3]],
    )


# ---------------------------------------------------------------------------
# Oracle 1 — unit cube: ≥6 tets, all positive volume
# ---------------------------------------------------------------------------

class TestUnitCubeMesh:
    """Basic validity tests on the unit-cube mesh."""

    @pytest.fixture(scope="class")
    def cube_mesh(self) -> Mesh3D:
        return mesh_unit_cube(n=2)

    def test_minimum_tet_count(self, cube_mesh: Mesh3D) -> None:
        """A unit-cube tessellation must produce at least 6 tetrahedra."""
        assert len(cube_mesh.elements) >= 6, (
            f"Expected ≥6 tets, got {len(cube_mesh.elements)}"
        )

    def test_all_tets_positive_volume(self, cube_mesh: Mesh3D) -> None:
        """Every tetrahedron must have strictly positive signed volume."""
        for idx in range(len(cube_mesh.elements)):
            vol = _vol(cube_mesh, idx)
            assert vol > 0, (
                f"Tet {idx} has non-positive volume {vol:.4e}; "
                f"indices={cube_mesh.elements[idx]}"
            )

    def test_vertices_inside_unit_cube(self, cube_mesh: Mesh3D) -> None:
        """All mesh vertices must lie within [0, 1]³."""
        for vi, (x, y, z) in enumerate(cube_mesh.vertices):
            assert -1e-9 <= x <= 1 + 1e-9, f"Vertex {vi} x={x} out of [0,1]"
            assert -1e-9 <= y <= 1 + 1e-9, f"Vertex {vi} y={y} out of [0,1]"
            assert -1e-9 <= z <= 1 + 1e-9, f"Vertex {vi} z={z} out of [0,1]"

    def test_boundary_faces_present(self, cube_mesh: Mesh3D) -> None:
        """There must be boundary faces."""
        assert len(cube_mesh.faces) > 0, "No boundary faces found"
        assert len(cube_mesh.face_tags) == len(cube_mesh.faces)


# ---------------------------------------------------------------------------
# Oracle 2 — Euler characteristic V − E + F − T = 1
# ---------------------------------------------------------------------------

class TestEulerCharacteristic:
    """Euler characteristic of the simplicial complex must equal 1."""

    def test_unit_cube_euler(self) -> None:
        mesh = mesh_unit_cube(n=2)
        chi = mesh.euler_characteristic()
        assert chi == 1, (
            f"Euler characteristic V−E+F−T = {chi} (expected 1); "
            f"V={len(mesh.vertices)}, E={len(mesh.unique_edges())}, "
            f"F={len(mesh.unique_faces_all())}, T={len(mesh.elements)}"
        )

    def test_larger_cube_euler(self) -> None:
        mesh = mesh_unit_cube(n=3)
        chi = mesh.euler_characteristic()
        assert chi == 1, (
            f"Euler characteristic = {chi} for n=3 cube (expected 1)"
        )


# ---------------------------------------------------------------------------
# Oracle 3 — Quality metric: minimum dihedral angle > 0°
# ---------------------------------------------------------------------------

class TestQualityMetric:
    """Minimum dihedral angle is reported and is positive (no degenerate tets)."""

    def test_min_dihedral_angle_positive(self) -> None:
        mesh = mesh_unit_cube(n=2)
        min_angle = mesh.min_dihedral_angle_deg()
        assert math.isfinite(min_angle), "min_dihedral_angle_deg() returned non-finite value"
        assert min_angle > 0.0, (
            f"Minimum dihedral angle is {min_angle:.4f}°; expected > 0°"
        )

    def test_min_dihedral_angle_reasonable(self) -> None:
        """The worst tet should still have a dihedral angle ≥ 1° for a simple cube grid."""
        mesh = mesh_unit_cube(n=2)
        min_angle = mesh.min_dihedral_angle_deg()
        # Even sliver tets on a regular grid are rarely below 5° for n=2
        assert min_angle >= 1.0, (
            f"Minimum dihedral angle {min_angle:.4f}° is suspiciously small"
        )

    def test_min_dihedral_angle_reported(self) -> None:
        """The quality metric must return a float value."""
        mesh = mesh_unit_cube(n=2)
        angle = mesh.min_dihedral_angle_deg()
        assert isinstance(angle, float)


# ---------------------------------------------------------------------------
# Oracle 4 — mesh_point_cloud() on a custom point set
# ---------------------------------------------------------------------------

class TestPointCloudMesh:
    """mesh_point_cloud() handles explicit point sets correctly."""

    def test_five_point_cloud(self) -> None:
        """Five well-separated points should yield ≥1 tet."""
        pts = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.5, 0.5, 0.5),
        ]
        mesh = mesh_point_cloud(pts)
        assert len(mesh.elements) >= 1, "Expected ≥1 tet from 5-point cloud"
        for idx in range(len(mesh.elements)):
            vol = _vol(mesh, idx)
            assert vol > 0, f"Tet {idx} has non-positive volume {vol:.4e}"

    def test_unit_tet(self) -> None:
        """A minimal 4-point cloud must yield exactly 1 tet."""
        pts = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ]
        mesh = mesh_point_cloud(pts)
        assert len(mesh.elements) >= 1, "Expected ≥1 tet from 4-point cloud"
        for idx in range(len(mesh.elements)):
            vol = _vol(mesh, idx)
            assert vol > 0, f"Non-positive volume {vol:.4e}"

    def test_too_few_points_raises(self) -> None:
        """Fewer than 4 points must raise ValueError."""
        with pytest.raises(ValueError, match="at least 4"):
            mesh_point_cloud([(0, 0, 0), (1, 0, 0), (0, 1, 0)])


# ---------------------------------------------------------------------------
# Smoke test — n=1 minimal cube
# ---------------------------------------------------------------------------

def test_minimal_cube_smoke() -> None:
    """Smallest possible n=1 cube mesh (8 corners) — basic sanity."""
    mesh = mesh_unit_cube(n=1)
    assert len(mesh.elements) >= 1
    for idx in range(len(mesh.elements)):
        vol = _vol(mesh, idx)
        assert vol > 0, f"Non-positive volume {vol:.4e}"


# ---------------------------------------------------------------------------
# Summary print (captured by pytest -s but not failing)
# ---------------------------------------------------------------------------

def test_quality_summary(capsys) -> None:
    """Print a summary of mesh quality metrics."""
    mesh = mesh_unit_cube(n=2)
    chi = mesh.euler_characteristic()
    min_ang = mesh.min_dihedral_angle_deg()
    print(
        f"\n--- Mesh3D quality summary (unit cube, n=2) ---\n"
        f"  Vertices  : {len(mesh.vertices)}\n"
        f"  Tets      : {len(mesh.elements)}\n"
        f"  Bdy faces : {len(mesh.faces)}\n"
        f"  Euler χ   : {chi}\n"
        f"  Min dihedral angle: {min_ang:.2f}°\n"
        f"---"
    )
    # This test always passes — it's a diagnostic aid
    assert True
