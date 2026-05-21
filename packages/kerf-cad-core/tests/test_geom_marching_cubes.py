"""GK-113 — Hermetic tests for marching_cubes in geom/sdf.py.

Oracle
------
marching_cubes of a sphere SDF (via body_sdf GK-112) →
  1. Closed manifold: every edge is shared by exactly 2 triangles.
  2. Euler characteristic χ = V - E + F = 2  (sphere topology).
  3. Volume = 4/3 · π · r³  ±  grid tolerance.

Pure-Python / numpy only — no OCC, no DB, no network.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import make_sphere
from kerf_cad_core.geom.sdf import body_sdf, marching_cubes
from kerf_cad_core.geom import marching_cubes as marching_cubes_pub


# ---------------------------------------------------------------------------
# Shared fixture: sphere SDF at sufficient resolution for volume accuracy
# ---------------------------------------------------------------------------

_RADIUS = 1.0
_RESOLUTION = 40   # higher res for volume accuracy
_PADDING = 0.3     # enough room around sphere


@pytest.fixture(scope="module")
def sphere_sdf():
    body = make_sphere(center=(0.0, 0.0, 0.0), radius=_RADIUS)
    return body_sdf(body, resolution=_RESOLUTION, padding=_PADDING)


@pytest.fixture(scope="module")
def sphere_mesh(sphere_sdf):
    return marching_cubes(sphere_sdf, iso=0.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mesh_volume(verts: np.ndarray, faces: np.ndarray) -> float:
    """Signed volume of a closed triangle mesh via divergence theorem."""
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    cross = np.cross(v1, v2)
    signed_vols = np.einsum("ij,ij->i", v0, cross)
    return abs(float(signed_vols.sum()) / 6.0)


def _mesh_euler(verts: np.ndarray, faces: np.ndarray) -> int:
    """Compute Euler characteristic χ = V - E + F for a triangle mesh."""
    V = len(verts)
    F = len(faces)
    # Build edge set
    edges = set()
    for f in faces:
        a, b, c = int(f[0]), int(f[1]), int(f[2])
        edges.add((min(a, b), max(a, b)))
        edges.add((min(b, c), max(b, c)))
        edges.add((min(a, c), max(a, c)))
    E = len(edges)
    return V - E + F


def _boundary_edges(faces: np.ndarray) -> int:
    """Return count of edges that are NOT shared by exactly 2 faces."""
    from collections import defaultdict
    edge_count: dict = defaultdict(int)
    for f in faces:
        a, b, c = int(f[0]), int(f[1]), int(f[2])
        for ea, eb in [(a, b), (b, c), (a, c)]:
            edge_count[(min(ea, eb), max(ea, eb))] += 1
    return sum(1 for cnt in edge_count.values() if cnt != 2)


# ===========================================================================
# 1. Return structure
# ===========================================================================

class TestMarchingCubesStructure:
    def test_keys_present(self, sphere_mesh):
        assert {"verts", "faces"} <= set(sphere_mesh.keys())

    def test_verts_shape(self, sphere_mesh):
        v = sphere_mesh["verts"]
        assert v.ndim == 2 and v.shape[1] == 3

    def test_faces_shape(self, sphere_mesh):
        f = sphere_mesh["faces"]
        assert f.ndim == 2 and f.shape[1] == 3

    def test_verts_dtype(self, sphere_mesh):
        assert sphere_mesh["verts"].dtype == np.float64

    def test_faces_dtype(self, sphere_mesh):
        assert sphere_mesh["faces"].dtype == np.int32

    def test_nonempty(self, sphere_mesh):
        assert len(sphere_mesh["verts"]) > 0
        assert len(sphere_mesh["faces"]) > 0

    def test_faces_valid_indices(self, sphere_mesh):
        V = len(sphere_mesh["verts"])
        F = sphere_mesh["faces"]
        assert int(F.min()) >= 0
        assert int(F.max()) < V


# ===========================================================================
# 2. Oracle: closed manifold (no boundary edges)
# ===========================================================================

class TestClosedManifold:
    def test_no_boundary_edges(self, sphere_mesh):
        """Every edge must be shared by exactly 2 triangles."""
        bad = _boundary_edges(sphere_mesh["faces"])
        assert bad == 0, f"Found {bad} boundary (non-manifold) edges"


# ===========================================================================
# 3. Oracle: Euler characteristic χ = 2 (sphere topology)
# ===========================================================================

class TestEulerCharacteristic:
    def test_euler_is_2(self, sphere_mesh):
        chi = _mesh_euler(sphere_mesh["verts"], sphere_mesh["faces"])
        assert chi == 2, f"Euler characteristic = {chi}, expected 2"


# ===========================================================================
# 4. Oracle: volume ≈ 4/3 · π · r³ ± grid tolerance
# ===========================================================================

class TestVolume:
    def test_sphere_volume(self, sphere_sdf, sphere_mesh):
        """Reconstructed sphere volume must be within 2 voxel-diagonals."""
        spacing = sphere_sdf["spacing"]
        voxel_diag = float(np.linalg.norm(spacing))
        # Surface area of sphere ~ 4πr²; volume error ~ SA * voxel_diag / 2
        # Allow 3× for safety
        tol = 4 * math.pi * _RADIUS ** 2 * voxel_diag * 1.5

        expected = (4.0 / 3.0) * math.pi * _RADIUS ** 3
        actual = _mesh_volume(sphere_mesh["verts"], sphere_mesh["faces"])

        assert abs(actual - expected) < tol, (
            f"sphere volume: got {actual:.4f}, expected {expected:.4f}, tol={tol:.4f}"
        )


# ===========================================================================
# 5. Raw grid dict (without body_sdf)
# ===========================================================================

class TestRawGridInput:
    def test_analytic_sphere_grid(self):
        """Directly pass a raw SDF grid (no Body) and check non-empty output."""
        n = 30
        origin = np.array([-1.5, -1.5, -1.5])
        spacing = np.array([3.0 / (n - 1)] * 3)
        xs = origin[0] + np.arange(n) * spacing[0]
        ys = origin[1] + np.arange(n) * spacing[1]
        zs = origin[2] + np.arange(n) * spacing[2]
        X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
        r = 1.0
        grid = np.sqrt(X ** 2 + Y ** 2 + Z ** 2) - r

        raw = {"grid": grid, "origin": origin, "spacing": spacing}
        mesh = marching_cubes(raw, iso=0.0)
        assert len(mesh["verts"]) > 0
        assert len(mesh["faces"]) > 0

        # Closed manifold
        bad = _boundary_edges(mesh["faces"])
        assert bad == 0, f"raw-grid mesh has {bad} boundary edges"

    def test_iso_nonzero(self):
        """iso parameter shifts the extracted surface."""
        n = 20
        origin = np.array([-2.0, -2.0, -2.0])
        spacing = np.array([4.0 / (n - 1)] * 3)
        xs = origin[0] + np.arange(n) * spacing[0]
        ys = origin[1] + np.arange(n) * spacing[1]
        zs = origin[2] + np.arange(n) * spacing[2]
        X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
        # Distance field from origin — iso=0.5 extracts sphere of radius 0.5
        grid = np.sqrt(X ** 2 + Y ** 2 + Z ** 2)
        raw = {"grid": grid, "origin": origin, "spacing": spacing}
        mesh = marching_cubes(raw, iso=0.5)
        assert len(mesh["verts"]) > 0


# ===========================================================================
# 6. Error handling
# ===========================================================================

class TestErrors:
    def test_non_dict_raises(self):
        with pytest.raises(ValueError, match="dict"):
            marching_cubes(np.zeros((4, 4, 4)))

    def test_missing_keys_raises(self):
        with pytest.raises(ValueError, match="missing"):
            marching_cubes({"grid": np.zeros((4, 4, 4))})

    def test_1d_grid_raises(self):
        with pytest.raises(ValueError, match="3-D"):
            marching_cubes({
                "grid": np.zeros(10),
                "origin": np.zeros(3),
                "spacing": np.ones(3),
            })

    def test_too_small_grid_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            marching_cubes({
                "grid": np.zeros((1, 4, 4)),
                "origin": np.zeros(3),
                "spacing": np.ones(3),
            })


# ===========================================================================
# 7. Public re-export from kerf_cad_core.geom
# ===========================================================================

class TestPublicExport:
    def test_marching_cubes_exported(self):
        assert marching_cubes_pub is marching_cubes
