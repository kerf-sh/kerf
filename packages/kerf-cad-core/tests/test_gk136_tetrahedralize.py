"""Tests for GK-136 — tetrahedralize (Delaunay volume mesh of a closed Body).

Oracles
-------
1. Tet-mesh a unit cube → sum of tet volumes = 1.0 ± tol.
2. All tets are positively oriented: signed_volume > 0 for every tet.
3. Public import path works: kerf_cad_core.geom.tetrahedralize.
4. Output dict has the required keys and correct dtypes / shapes.
"""

import math
import numpy as np
import pytest

from kerf_cad_core.geom.brep import make_box
from kerf_cad_core.geom.tetmesh import tetrahedralize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tet_signed_volume(nodes, tet):
    a, b, c, d = nodes[tet[0]], nodes[tet[1]], nodes[tet[2]], nodes[tet[3]]
    m = np.array([b - a, c - a, d - a])
    return float(np.linalg.det(m)) / 6.0


# ---------------------------------------------------------------------------
# Unit-cube oracle
# ---------------------------------------------------------------------------

class TestUnitCubeTetrahedralize:
    """The primary oracle: tet-mesh a unit cube and verify volume + orientation."""

    @pytest.fixture(scope="class")
    def cube_mesh(self):
        body = make_box((0, 0, 0), (1, 1, 1))
        return tetrahedralize(body)

    def test_returns_dict_with_required_keys(self, cube_mesh):
        assert "nodes" in cube_mesh, "missing key 'nodes'"
        assert "tets" in cube_mesh, "missing key 'tets'"

    def test_nodes_shape_and_dtype(self, cube_mesh):
        nodes = cube_mesh["nodes"]
        assert isinstance(nodes, np.ndarray)
        assert nodes.ndim == 2 and nodes.shape[1] == 3, (
            f"expected (N, 3) nodes array, got {nodes.shape}"
        )
        assert nodes.dtype == np.float64

    def test_tets_shape_and_dtype(self, cube_mesh):
        tets = cube_mesh["tets"]
        assert isinstance(tets, np.ndarray)
        assert tets.ndim == 2 and tets.shape[1] == 4, (
            f"expected (T, 4) tets array, got {tets.shape}"
        )
        assert tets.dtype == np.int64

    def test_at_least_one_tet(self, cube_mesh):
        assert len(cube_mesh["tets"]) >= 1, "no tetrahedra produced"

    def test_total_volume_equals_one(self, cube_mesh):
        """Sum of all tet volumes ≈ 1.0 (volume of the unit cube)."""
        nodes = cube_mesh["nodes"]
        tets = cube_mesh["tets"]
        total_vol = sum(abs(_tet_signed_volume(nodes, t)) for t in tets)
        assert abs(total_vol - 1.0) < 0.05, (
            f"total tet volume {total_vol:.6f} not within 5% of 1.0"
        )

    def test_all_tets_positive_orientation(self, cube_mesh):
        """Every tet must have strictly positive signed volume."""
        nodes = cube_mesh["nodes"]
        tets = cube_mesh["tets"]
        negatives = []
        for i, tet in enumerate(tets):
            sv = _tet_signed_volume(nodes, tet)
            if sv <= 0.0:
                negatives.append((i, sv))
        assert not negatives, (
            f"{len(negatives)} tets have non-positive signed volume: "
            f"{negatives[:5]!r}…"
        )

    def test_tet_indices_in_range(self, cube_mesh):
        """All tet vertex indices must be valid indices into nodes."""
        n_nodes = len(cube_mesh["nodes"])
        tets = cube_mesh["tets"]
        assert int(tets.min()) >= 0, "negative tet index"
        assert int(tets.max()) < n_nodes, (
            f"tet index {int(tets.max())} out of range (n_nodes={n_nodes})"
        )

    def test_public_import(self):
        """The symbol is re-exported from kerf_cad_core.geom."""
        from kerf_cad_core.geom import tetrahedralize as _tf  # noqa: F401
        assert callable(_tf)

    def test_tight_volume_tolerance(self, cube_mesh):
        """Stricter check: sum of tet volumes = 1.0 ± 0.02."""
        nodes = cube_mesh["nodes"]
        tets = cube_mesh["tets"]
        total_vol = sum(abs(_tet_signed_volume(nodes, t)) for t in tets)
        assert abs(total_vol - 1.0) < 0.02, (
            f"total tet volume {total_vol:.8f} differs from 1.0 by more than 2 %"
        )


# ---------------------------------------------------------------------------
# max_volume parameter
# ---------------------------------------------------------------------------

class TestMaxVolume:
    def test_max_volume_produces_more_tets(self):
        body = make_box((0, 0, 0), (1, 1, 1))
        coarse = tetrahedralize(body)
        fine = tetrahedralize(body, max_volume=0.05)
        # Fine mesh should have at least as many tets as coarse
        assert len(fine["tets"]) >= len(coarse["tets"]), (
            f"refined mesh has fewer tets ({len(fine['tets'])}) than coarse "
            f"({len(coarse['tets'])})"
        )

    def test_max_volume_all_positive_orientation(self):
        body = make_box((0, 0, 0), (1, 1, 1))
        mesh = tetrahedralize(body, max_volume=0.05)
        nodes, tets = mesh["nodes"], mesh["tets"]
        for i, tet in enumerate(tets):
            sv = _tet_signed_volume(nodes, tet)
            assert sv > 0.0, f"tet {i} has non-positive signed volume {sv}"
