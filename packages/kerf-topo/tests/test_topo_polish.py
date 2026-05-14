"""
Topology optimisation polish tests — Phase 3.

Covers:
1. NURBS round-trip: STEP produced with NURBS fitting is <= size of faceted STEP.
2. Smoothing: Laplacian smoothing reduces vertex deviation from analytical surface.
3. Multi-body: two-body request produces distinct density fields per body.

All heavy deps (dolfinx, gmsh, OCC.Core, scipy) are individually skipped via
pytest.importorskip when not installed.

Run:
    pytest pyworker/tests/test_topo_polish.py -v
"""

import base64
import math
import sys
import tempfile
from pathlib import Path

import pytest

# ── dep guards ─────────────────────────────────────────────────────────────────

numpy_mod = pytest.importorskip("numpy", reason="numpy not installed")
import numpy as np  # noqa: E402 — after importorskip

occ_step = pytest.importorskip("OCC.Core.STEPControl", reason="pythonOCC not installed")

from kerf_topo.routes import (  # noqa: E402
    _density_field_to_grid,
    _laplacian_smooth,
    _connected_components,
    _marching_cubes_to_step,
    BoundaryCondition,
    Load,
    TopoRequest,
    BodyVolumeFraction,
    BodyFilterRadius,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _sphere_density_field(N=12, radius=0.35, center=(0.5, 0.5, 0.5)):
    """Generate a density field that is 1 inside a sphere, 0 outside."""
    pts = []
    rhos = []
    cx, cy, cz = center
    for ix in range(N):
        for iy in range(N):
            for iz in range(N):
                x = ix / (N - 1)
                y = iy / (N - 1)
                z = iz / (N - 1)
                pts.append([x, y, z])
                inside = math.sqrt((x - cx)**2 + (y - cy)**2 + (z - cz)**2) <= radius
                rhos.append(1.0 if inside else 0.0)
    return pts, rhos


def _make_request(**overrides) -> TopoRequest:
    defaults = dict(
        project_id="00000000-0000-0000-0000-000000000001",
        topo_file_id="00000000-0000-0000-0000-000000000002",
        feature_file_id="00000000-0000-0000-0000-000000000003",
        material_file_id="00000000-0000-0000-0000-000000000004",
        volume_fraction=0.4,
        penalization_power=3,
        filter_radius_mm=2.0,
        max_iterations=3,
        convergence_tolerance=1e-3,
    )
    defaults.update(overrides)
    return TopoRequest(**defaults)


# ── 1. NURBS round-trip ────────────────────────────────────────────────────────

class TestNURBSRoundTrip:
    """STEP produced with NURBS fitting must be a valid STEP file and <= faceted size."""

    def test_nurbs_step_is_valid_iso10303(self):
        """STEP output with NURBS fitting starts with the ISO-10303-21 header."""
        scipy_mod = pytest.importorskip("scipy", reason="scipy not installed (needed for NURBS fitting)")
        coords, rhos = _sphere_density_field(N=10)
        step_bytes = _marching_cubes_to_step(coords, rhos, threshold=0.5, smoothing_iterations=0)
        text = step_bytes.decode(errors="replace")
        assert "ISO-10303-21" in text

    def test_nurbs_step_readable_by_occ(self):
        """The STEP produced by the NURBS path is readable by STEPControl_Reader."""
        pytest.importorskip("scipy", reason="scipy not installed")
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.IFSelect import IFSelect_RetDone

        coords, rhos = _sphere_density_field(N=10)
        step_bytes = _marching_cubes_to_step(coords, rhos, threshold=0.5, smoothing_iterations=0)

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            f.write(step_bytes)
            tmp = f.name
        try:
            reader = STEPControl_Reader()
            status = reader.ReadFile(tmp)
            assert status == IFSelect_RetDone
            reader.TransferRoots()
            shape = reader.OneShape()
            assert not shape.IsNull()
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_nurbs_step_no_larger_than_faceted(self):
        """
        STEP file with NURBS fitting must not be larger than the pure-faceted equivalent.

        NURBS surfaces replace many triangular faces with a single parametric
        surface, so the STEP file should be smaller or equal in size.
        """
        pytest.importorskip("scipy", reason="scipy not installed")
        coords, rhos = _sphere_density_field(N=12)

        # Faceted: smoothing=0 and force fallback by temporarily making scipy invisible
        # We compare against the case where NURBS fitting is bypassed via monkeypatching.
        import unittest.mock as mock

        with mock.patch("routes.topo._fit_nurbs_face", side_effect=RuntimeError("forced fallback")):
            faceted_bytes = _marching_cubes_to_step(coords, rhos, threshold=0.5, smoothing_iterations=0)

        nurbs_bytes = _marching_cubes_to_step(coords, rhos, threshold=0.5, smoothing_iterations=0)

        assert len(nurbs_bytes) <= len(faceted_bytes), (
            f"NURBS STEP ({len(nurbs_bytes)} B) is larger than faceted STEP ({len(faceted_bytes)} B)"
        )

    def test_nurbs_fallback_on_small_component(self):
        """Components with < 9 vertices fall back gracefully to faceted export."""
        coords = [[float(i), 0.0, 0.0] for i in range(6)]
        # Provide a gradient that crosses 0.5 so marching cubes fires
        for _ in range(6):
            coords.append([float(_ / 5), float(_ / 5), 0.0])
        rhos_grad = [float(i) / (len(coords) - 1) for i in range(len(coords))]
        # This should not raise even if NURBS fitting can't run
        step_bytes = _marching_cubes_to_step(coords, rhos_grad, threshold=0.5, smoothing_iterations=0)
        assert len(step_bytes) > 0


# ── 2. Contour smoothing ───────────────────────────────────────────────────────

class TestLaplacianSmoothing:
    """Laplacian smoothing reduces staircase deviation against an analytical surface."""

    def _sphere_mesh_verts_faces(self, grid_n=20):
        """Marching-cubes mesh of a unit sphere at grid resolution grid_n."""
        from skimage.measure import marching_cubes
        coords, rhos = _sphere_density_field(N=grid_n)
        grid, spacing, origin = _density_field_to_grid(coords, rhos, grid_n=grid_n)
        verts, faces, _, _ = marching_cubes(grid, level=0.5, spacing=tuple(spacing))
        verts = verts + origin
        return verts, faces

    def _rms_deviation_from_sphere(self, verts, center=(0.5, 0.5, 0.5), radius=0.35):
        """RMS distance of each vertex from the analytical sphere surface."""
        cx, cy, cz = center
        dists = np.sqrt((verts[:, 0] - cx)**2 + (verts[:, 1] - cy)**2 + (verts[:, 2] - cz)**2)
        return float(np.sqrt(np.mean((dists - radius)**2)))

    def test_smoothing_reduces_rms_deviation(self):
        """3 iterations of smoothing must reduce RMS deviation from the sphere surface."""
        pytest.importorskip("skimage", reason="scikit-image not installed")
        verts, faces = self._sphere_mesh_verts_faces(grid_n=20)
        rms_before = self._rms_deviation_from_sphere(verts)
        smoothed = _laplacian_smooth(verts, faces, iterations=3)
        rms_after = self._rms_deviation_from_sphere(smoothed)
        assert rms_after < rms_before, (
            f"Smoothing did not reduce RMS deviation: before={rms_before:.4f}, after={rms_after:.4f}"
        )

    def test_smoothing_preserves_vertex_count(self):
        """Smoothing must not change the number of vertices."""
        pytest.importorskip("skimage", reason="scikit-image not installed")
        verts, faces = self._sphere_mesh_verts_faces(grid_n=15)
        smoothed = _laplacian_smooth(verts, faces, iterations=5)
        assert len(smoothed) == len(verts)

    def test_zero_iterations_noop(self):
        """smoothing_iterations=0 must leave mesh unchanged."""
        pytest.importorskip("skimage", reason="scikit-image not installed")
        verts, faces = self._sphere_mesh_verts_faces(grid_n=15)
        smoothed = _laplacian_smooth(verts, faces, iterations=0)
        np.testing.assert_array_equal(smoothed, verts)

    def test_step_with_smoothing_is_valid(self):
        """_marching_cubes_to_step with smoothing_iterations=3 produces valid STEP."""
        coords, rhos = _sphere_density_field(N=12)
        step_bytes = _marching_cubes_to_step(coords, rhos, threshold=0.5, smoothing_iterations=3)
        assert b"ISO-10303-21" in step_bytes


# ── 3. Multi-body optimization ─────────────────────────────────────────────────

class TestMultiBody:
    """Per-body volume fractions and filter radii; per-body OC updates produce distinct fields."""

    def test_request_scalar_volume_fraction_compat(self):
        """Scalar volume_fraction still accepted (backwards compat)."""
        req = _make_request(volume_fraction=0.3, filter_radius_mm=2.0)
        assert req.volume_fraction_for_body(None) == pytest.approx(0.3)

    def test_request_per_body_volume_fraction(self):
        """List of BodyVolumeFraction accepted; lookup by body_tag works."""
        req = _make_request(
            volume_fraction=[
                BodyVolumeFraction(body_tag=1, volume_fraction=0.3),
                BodyVolumeFraction(body_tag=2, volume_fraction=0.5),
            ],
            filter_radius_mm=2.0,
        )
        assert req.volume_fraction_for_body(1) == pytest.approx(0.3)
        assert req.volume_fraction_for_body(2) == pytest.approx(0.5)

    def test_request_per_body_filter_radius(self):
        """List of BodyFilterRadius accepted; lookup by body_tag works."""
        req = _make_request(
            volume_fraction=0.4,
            filter_radius_mm=[
                BodyFilterRadius(body_tag=1, filter_radius_mm=1.0),
                BodyFilterRadius(body_tag=2, filter_radius_mm=3.0),
            ],
        )
        assert req.filter_radius_for_body(1) == pytest.approx(1.0)
        assert req.filter_radius_for_body(2) == pytest.approx(3.0)

    def test_volume_fraction_fallback_unknown_body(self):
        """Unknown body_tag falls back to first list entry."""
        req = _make_request(
            volume_fraction=[BodyVolumeFraction(body_tag=1, volume_fraction=0.25)],
            filter_radius_mm=2.0,
        )
        assert req.volume_fraction_for_body(99) == pytest.approx(0.25)

    def test_multi_body_simp_distinct_density_fields(self):
        """
        Two-body SIMP (unit-cube fallback, split at x=0.5) with different
        V_targets produces density fields that differ in mean between the
        two halves after OC updates.

        This test exercises the per-body OC branch in _run_fenicsx_simp by
        directly invoking the internal logic on a small synthetic body_cell_map.
        It does not require gmsh — we build the cell map from the unit-cube mesh.
        """
        dolfinx_mod = pytest.importorskip("dolfinx", reason="dolfinx not installed")
        import dolfinx
        import dolfinx.mesh
        import dolfinx.fem
        from mpi4py import MPI

        from kerf_topo.routes import _oc_update, _heaviside_filter

        comm = MPI.COMM_WORLD
        mesh = dolfinx.mesh.create_unit_cube(comm, 6, 6, 6)
        Q = dolfinx.fem.functionspace(mesh, ("DG", 0))
        coords = Q.tabulate_dof_coordinates()
        n_cells = len(coords)

        # Split at x = 0.5 to form two synthetic bodies
        body1_idx = np.where(coords[:, 0] < 0.5)[0]
        body2_idx = np.where(coords[:, 0] >= 0.5)[0]

        assert len(body1_idx) > 0 and len(body2_idx) > 0

        vf1, vf2 = 0.2, 0.7
        rho = np.full(n_cells, 0.4)
        rho[body1_idx] = vf1
        rho[body2_idx] = vf2

        # Simulate one OC step per body with a uniform sensitivity
        sens = [-1.0] * n_cells

        for (idx, vf) in [(body1_idx, vf1), (body2_idx, vf2)]:
            bdy_rho = [rho[i] for i in idx]
            bdy_sens = [sens[i] for i in idx]
            bdy_coords = [coords[i].tolist() for i in idx]
            R = 0.15
            filtered = _heaviside_filter(bdy_rho, bdy_coords, R)
            updated = _oc_update(filtered, bdy_sens, vf, len(idx) * vf)
            for local_j, global_i in enumerate(idx):
                rho[global_i] = updated[local_j]

        mean_body1 = float(np.mean(rho[body1_idx]))
        mean_body2 = float(np.mean(rho[body2_idx]))

        # Both bodies should have updated from their different starting points
        # The means should differ by more than a trivial amount
        assert abs(mean_body1 - mean_body2) > 0.05, (
            f"Distinct V_targets did not produce distinct density fields: "
            f"mean_body1={mean_body1:.3f}, mean_body2={mean_body2:.3f}"
        )

    def test_smoothing_iterations_field_in_request(self):
        """smoothing_iterations field round-trips through the request model."""
        req = _make_request(smoothing_iterations=5)
        assert req.smoothing_iterations == 5

    def test_smoothing_iterations_defaults_to_3(self):
        """smoothing_iterations defaults to 3 when not provided."""
        req = _make_request()
        assert req.smoothing_iterations == 3
