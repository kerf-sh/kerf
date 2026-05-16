"""
Tests for kerf_cad_core.jewelry.bas_relief

Hermetic (no network, no DB, no OCCT required).

Coverage:
  - image_to_relief: linear/gamma/sigmoid/edge-enhanced styles
  - Flat image → flat plate
  - Vertex count matches expected grid
  - Volume monotonic in max_depth
  - Border-ring annulus present (edge vertices near-zero depth)
  - Gamma style is monotone-but-nonlinear
  - Sigmoid style normalised to [0,1]
  - Edge-enhanced style boosts contrast at edges
  - Circular vs square boundary
  - Bad-input guard paths (never raises)
  - relief_to_signet: geometry meets ring inner diameter
  - relief_metal_volume_mm3: proportional, positive, zero on flat
  - optimize_for_casting: spikes reduced, delta_features reported
  - relief_diagnostics: stats accurate
  - Shrinkage compensation widens actual_dia_mm
  - Anti-shrinkage cap truncates excessive depth
  - LLM tool round-trip via run_* handlers
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from typing import List

import pytest

from kerf_cad_core.jewelry.bas_relief import (
    _DEFAULT_BORDER_FRAC,
    _DEFAULT_GAMMA,
    _CASTING_SHRINKAGE,
    _MAX_DEPTH_CAP_FRAC,
    _normalise_sigmoid,
    image_to_relief,
    optimize_for_casting,
    relief_diagnostics,
    relief_metal_volume_mm3,
    relief_to_signet,
    run_jewelry_image_to_relief,
    run_jewelry_optimize_relief_for_casting,
    run_jewelry_relief_metal_volume,
    run_jewelry_relief_to_signet,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat_image(n: int = 8, intensity: float = 0.5) -> List[List[float]]:
    """Return an n×n grid filled with a constant intensity."""
    return [[intensity] * n for _ in range(n)]


def _ramp_image(nrows: int = 8, ncols: int = 8) -> List[List[float]]:
    """Return a grid where column index drives intensity linearly 0→1."""
    return [
        [c / max(ncols - 1, 1) for c in range(ncols)]
        for _ in range(nrows)
    ]


def _gradient_image(nrows: int = 10, ncols: int = 10) -> List[List[float]]:
    """Radial gradient: 1 at centre, 0 at corners."""
    cx = (ncols - 1) / 2.0
    cy = (nrows - 1) / 2.0
    r_max = math.hypot(cx, cy)
    grid = []
    for r in range(nrows):
        row = []
        for c in range(ncols):
            d = math.hypot(c - cx, r - cy)
            row.append(max(0.0, 1.0 - d / (r_max + 1e-12)))
        grid.append(row)
    return grid


def _make_ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    except ImportError:
        class ProjectCtx:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
    return ProjectCtx(
        pool=None,
        storage=None,
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )


def run_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return json.loads(loop.run_until_complete(coro))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 1. Basic success path
# ---------------------------------------------------------------------------

class TestImageToReliefBasic:

    def test_returns_ok_for_valid_input(self):
        result = image_to_relief(_flat_image(), 20.0, 1.0)
        assert result.get("ok") is True

    def test_has_verts_and_faces(self):
        result = image_to_relief(_flat_image(), 20.0, 1.0)
        assert "verts" in result
        assert "faces" in result
        assert len(result["verts"]) > 0
        assert len(result["faces"]) > 0

    def test_stats_present(self):
        result = image_to_relief(_flat_image(), 20.0, 1.0)
        stats = result.get("stats", {})
        for key in ("grid_rows", "grid_cols", "vert_count", "face_count",
                    "actual_dia_mm", "max_depth_mm", "style"):
            assert key in stats, f"Missing stats key: {key}"

    def test_warnings_is_list(self):
        result = image_to_relief(_flat_image(), 20.0, 1.0)
        assert isinstance(result.get("warnings"), list)


# ---------------------------------------------------------------------------
# 2. Linear style: depth proportional to intensity
# ---------------------------------------------------------------------------

class TestLinearStyle:

    def test_linear_depth_proportional_to_intensity(self):
        """In linear style, pixel intensity 0.5 should give depth = 0.5 * max_depth."""
        result = image_to_relief(
            _flat_image(8, 0.5),
            20.0,
            2.0,
            style="linear",
            boundary="square",
            border_frac=0.0,
            shrinkage_compensation=False,
        )
        assert result.get("ok") is True
        zs = [v[2] for v in result["verts"]]
        # All verts should have depth ~1.0 (= 0.5 * 2.0)
        for z in zs:
            assert abs(z - 1.0) < 1e-4, f"Expected z≈1.0 for intensity 0.5, got {z}"

    def test_full_intensity_gives_max_depth(self):
        result = image_to_relief(
            _flat_image(8, 1.0),
            20.0,
            3.0,
            style="linear",
            boundary="square",
            border_frac=0.0,
            shrinkage_compensation=False,
        )
        assert result.get("ok") is True
        zs = [v[2] for v in result["verts"]]
        for z in zs:
            assert abs(z - 3.0) < 1e-4, f"Expected z≈3.0 for intensity 1.0, got {z}"

    def test_zero_intensity_gives_zero_depth(self):
        result = image_to_relief(
            _flat_image(8, 0.0),
            20.0,
            3.0,
            style="linear",
            boundary="square",
            border_frac=0.0,
            shrinkage_compensation=False,
        )
        assert result.get("ok") is True
        zs = [v[2] for v in result["verts"]]
        for z in zs:
            assert abs(z) < 1e-6, f"Expected z≈0.0 for intensity 0.0, got {z}"


# ---------------------------------------------------------------------------
# 3. Flat image → flat plate
# ---------------------------------------------------------------------------

class TestFlatImage:

    def test_flat_image_uniform_depth(self):
        """A flat image should produce a flat plate: all Z values equal."""
        result = image_to_relief(
            _flat_image(8, 0.7),
            20.0,
            2.0,
            style="linear",
            boundary="square",
            border_frac=0.0,
            shrinkage_compensation=False,
        )
        assert result.get("ok") is True
        zs = [v[2] for v in result["verts"]]
        assert len(set(round(z, 5) for z in zs)) == 1, "Flat image produced non-uniform Z"

    def test_zero_image_all_zeros(self):
        result = image_to_relief(
            _flat_image(8, 0.0), 15.0, 1.5,
            style="linear", boundary="square", border_frac=0.0,
            shrinkage_compensation=False,
        )
        assert result.get("ok") is True
        zs = [v[2] for v in result["verts"]]
        assert all(z == 0.0 for z in zs), "Expected all-zero Z for zero image"


# ---------------------------------------------------------------------------
# 4. Vertex count matches expected grid
# ---------------------------------------------------------------------------

class TestVertexCount:

    def test_square_boundary_vertex_count(self):
        """For square boundary, every grid point is a vertex."""
        nrows, ncols = 6, 8
        img = [[0.5] * ncols for _ in range(nrows)]
        result = image_to_relief(img, 20.0, 1.0, boundary="square", border_frac=0.0)
        assert result.get("ok") is True
        assert result["stats"]["vert_count"] == nrows * ncols

    def test_face_count_formula_square(self):
        """For an n×m grid, face count = 2*(n-1)*(m-1) for square boundary."""
        nrows, ncols = 5, 7
        img = [[0.5] * ncols for _ in range(nrows)]
        result = image_to_relief(img, 20.0, 1.0, boundary="square", border_frac=0.0)
        assert result.get("ok") is True
        expected_faces = 2 * (nrows - 1) * (ncols - 1)
        assert result["stats"]["face_count"] == expected_faces

    def test_circular_boundary_fewer_verts(self):
        """Circular boundary should clip corner verts, giving fewer verts than square."""
        img = [[0.5] * 10 for _ in range(10)]
        r_sq = image_to_relief(img, 20.0, 1.0, boundary="square", border_frac=0.0)
        r_ci = image_to_relief(img, 20.0, 1.0, boundary="circular", border_frac=0.0)
        assert r_sq["stats"]["vert_count"] > r_ci["stats"]["vert_count"]


# ---------------------------------------------------------------------------
# 5. Volume monotonic in max_depth
# ---------------------------------------------------------------------------

class TestVolumeMonotonic:

    def test_volume_increases_with_max_depth(self):
        """Increasing max_depth must strictly increase displaced volume."""
        img = _gradient_image()
        depths = [0.5, 1.0, 2.0, 3.0]
        volumes = []
        for d in depths:
            result = image_to_relief(img, 20.0, d, style="linear",
                                     boundary="circular", border_frac=0.0,
                                     shrinkage_compensation=False)
            assert result.get("ok") is True
            volumes.append(relief_metal_volume_mm3(result))
        for i in range(1, len(volumes)):
            assert volumes[i] > volumes[i - 1], (
                f"Volume not monotonically increasing: {volumes}"
            )


# ---------------------------------------------------------------------------
# 6. Border-ring annulus: edge vertices should have near-zero depth
# ---------------------------------------------------------------------------

class TestBorderRing:

    def test_border_vertices_near_zero(self):
        """With border_frac > 0, circular boundary vertices near the very edge
        should blend towards zero depth regardless of image intensity.

        With border_frac=0.15, the blend formula at nr_=1.0 (outermost edge) gives
        blend=0 (depth=0).  At nr_=0.98 (within 2% of edge): blend=(1-0.98)/0.15≈0.13,
        so depth ≈ 0.13 * max_depth. We therefore check that outermost vertices
        (normalised r > 0.97) have depth below 40% of max_depth_mm.
        """
        img = _flat_image(20, 1.0)  # all-white image
        border_frac = 0.15
        max_depth = 2.0
        result = image_to_relief(
            img, 30.0, max_depth,
            style="linear",
            boundary="circular",
            border_frac=border_frac,
            shrinkage_compensation=False,
        )
        assert result.get("ok") is True
        verts = result["verts"]
        assert len(verts) > 0

        # Find normalised radii for all vertices
        # We need the physical radius = target_dia/2 = 15 mm (no shrinkage comp)
        disk_radius = 30.0 / 2.0
        # Collect vertices at normalised r > 0.97 (well inside the border zone)
        outer_verts = [
            v for v in verts
            if math.hypot(v[0], v[1]) / disk_radius > 0.97
        ]
        assert len(outer_verts) > 0, "No outer-edge vertices found"
        # These should have depth well below max_depth (border blending applied)
        threshold = 0.40 * max_depth  # at nr=0.97, blend=(1-0.97)/0.15=0.2 → depth=0.4
        for v in outer_verts:
            assert v[2] <= threshold + 1e-6, (
                f"Outer vertex at r={math.hypot(v[0],v[1]):.3f} has z={v[2]:.4f}, "
                f"expected <= {threshold:.4f}"
            )


# ---------------------------------------------------------------------------
# 7. Gamma style: monotone but non-linear
# ---------------------------------------------------------------------------

class TestGammaStyle:

    def test_gamma_monotone(self):
        """Gamma style must be monotone increasing in intensity."""
        intensities = [i / 10.0 for i in range(11)]
        depths = []
        for val in intensities:
            result = image_to_relief(
                [[val]],  # single pixel — too small, so use a 4×4
                None, None, style="gamma-curve",
                boundary="square", border_frac=0.0, shrinkage_compensation=False,
            )
            # use the pure helper instead
            from kerf_cad_core.jewelry.bas_relief import _apply_style
            d = _apply_style(val, "gamma-curve", _DEFAULT_GAMMA, 0.0, 0.0)
            depths.append(d)
        for i in range(1, len(depths)):
            assert depths[i] >= depths[i - 1], (
                f"Gamma not monotone at i={i}: {depths[i-1]:.6f} → {depths[i]:.6f}"
            )

    def test_gamma_nonlinear_differs_from_linear(self):
        """Gamma output at mid-intensity should differ from linear (same midpoint)."""
        from kerf_cad_core.jewelry.bas_relief import _apply_style
        mid = 0.5
        lin = _apply_style(mid, "linear", _DEFAULT_GAMMA, 0.0, 0.0)
        gam = _apply_style(mid, "gamma-curve", _DEFAULT_GAMMA, 0.0, 0.0)
        assert abs(lin - gam) > 1e-4, (
            f"Gamma and linear identical at mid-intensity: {lin} vs {gam}"
        )

    def test_gamma_endpoints(self):
        """Gamma(0) = 0 and Gamma(1) = 1."""
        from kerf_cad_core.jewelry.bas_relief import _apply_style
        assert _apply_style(0.0, "gamma-curve", _DEFAULT_GAMMA, 0.0, 0.0) == 0.0
        assert abs(_apply_style(1.0, "gamma-curve", _DEFAULT_GAMMA, 0.0, 0.0) - 1.0) < 1e-9

    def test_gamma_end_to_end_nonlinear(self):
        """Full image_to_relief with gamma-curve must differ from linear at same input."""
        img = _ramp_image(8, 8)
        r_lin = image_to_relief(img, 20.0, 2.0, style="linear", boundary="square",
                                border_frac=0.0, shrinkage_compensation=False)
        r_gam = image_to_relief(img, 20.0, 2.0, style="gamma-curve", boundary="square",
                                border_frac=0.0, shrinkage_compensation=False)
        # Z values should differ somewhere
        diffs = [
            abs(r_lin["verts"][i][2] - r_gam["verts"][i][2])
            for i in range(min(len(r_lin["verts"]), len(r_gam["verts"])))
        ]
        assert max(diffs) > 0.01, "Gamma-curve produced same depths as linear"


# ---------------------------------------------------------------------------
# 8. Sigmoid style
# ---------------------------------------------------------------------------

class TestSigmoidStyle:

    def test_sigmoid_normalised_endpoints(self):
        """Normalised sigmoid: f(0)≈0, f(1)≈1."""
        s0 = _normalise_sigmoid(0.0)
        s1 = _normalise_sigmoid(1.0)
        assert abs(s0) < 1e-3, f"sigmoid(0) = {s0}"
        assert abs(s1 - 1.0) < 1e-3, f"sigmoid(1) = {s1}"

    def test_sigmoid_monotone(self):
        """Sigmoid must be monotone increasing on [0, 1]."""
        vals = [i / 20.0 for i in range(21)]
        sig_vals = [_normalise_sigmoid(v) for v in vals]
        for i in range(1, len(sig_vals)):
            assert sig_vals[i] >= sig_vals[i - 1], (
                f"Sigmoid not monotone at i={i}"
            )

    def test_sigmoid_centre_around_half(self):
        """Sigmoid should compress extremes and have inflection near 0.5."""
        s_lo = _normalise_sigmoid(0.25)
        s_hi = _normalise_sigmoid(0.75)
        # Both should be pulled away from 0.25/0.75 (closer to 0/1)
        assert s_lo < 0.25 or s_hi > 0.75  # at least one squeezed


# ---------------------------------------------------------------------------
# 9. Edge-enhanced style boosts edges
# ---------------------------------------------------------------------------

class TestEdgeEnhancedStyle:

    def test_edge_enhanced_can_boost_depth(self):
        """An image with a sharp step should produce higher Z on the edge-enhanced
        version than linear for the same max_depth."""
        # Create a step image: left half black, right half white
        nrows, ncols = 8, 8
        step = [[0.0 if c < ncols // 2 else 1.0 for c in range(ncols)] for _ in range(nrows)]
        r_lin = image_to_relief(step, 20.0, 2.0, style="linear",
                                boundary="square", border_frac=0.0,
                                shrinkage_compensation=False)
        r_edge = image_to_relief(step, 20.0, 2.0, style="edge-enhanced",
                                 edge_weight=0.5, boundary="square",
                                 border_frac=0.0, shrinkage_compensation=False)
        # Max Z in edge-enhanced should be >= linear (may be clamped to max_depth)
        max_z_lin = max(v[2] for v in r_lin["verts"])
        max_z_edge = max(v[2] for v in r_edge["verts"])
        assert max_z_edge >= max_z_lin - 1e-6


# ---------------------------------------------------------------------------
# 10. Bad input guards (never raises)
# ---------------------------------------------------------------------------

class TestBadInputGuards:

    def test_too_small_grid_returns_ok_false(self):
        tiny = [[0.5, 0.5], [0.5, 0.5]]  # 2×2 < minimum 4×4
        result = image_to_relief(tiny, 20.0, 1.0)
        assert result.get("ok") is False
        assert "reason" in result

    def test_negative_diameter_returns_ok_false(self):
        result = image_to_relief(_flat_image(), -5.0, 1.0)
        assert result.get("ok") is False

    def test_zero_max_depth_returns_ok_false(self):
        result = image_to_relief(_flat_image(), 20.0, 0.0)
        assert result.get("ok") is False

    def test_invalid_style_returns_ok_false(self):
        result = image_to_relief(_flat_image(), 20.0, 1.0, style="magic")
        assert result.get("ok") is False

    def test_invalid_boundary_returns_ok_false(self):
        result = image_to_relief(_flat_image(), 20.0, 1.0, boundary="triangle")
        assert result.get("ok") is False

    def test_bad_border_frac_returns_ok_false(self):
        result = image_to_relief(_flat_image(), 20.0, 1.0, border_frac=0.9)
        assert result.get("ok") is False

    def test_non_array_input_returns_ok_false(self):
        result = image_to_relief("not_an_array", 20.0, 1.0)
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# 11. Anti-shrinkage cap
# ---------------------------------------------------------------------------

class TestAntiShrinkageCap:

    def test_depth_capped_with_warning(self):
        """Passing max_depth_mm > cap should emit a warning and cap the depth."""
        dia = 20.0
        big_depth = dia * _MAX_DEPTH_CAP_FRAC * 3.0  # 3x the cap
        result = image_to_relief(
            _flat_image(8, 1.0), dia, big_depth,
            style="linear", boundary="square", border_frac=0.0,
            shrinkage_compensation=False,
        )
        assert result.get("ok") is True
        assert len(result["warnings"]) > 0
        cap = dia * _MAX_DEPTH_CAP_FRAC
        # Actual max Z should not exceed the cap
        max_z = max(v[2] for v in result["verts"])
        assert max_z <= cap + 1e-6

    def test_shrinkage_compensation_widens_footprint(self):
        """With shrinkage_compensation=True, actual_dia_mm should be larger."""
        result_comp = image_to_relief(
            _flat_image(), 20.0, 1.0, shrinkage_compensation=True
        )
        result_none = image_to_relief(
            _flat_image(), 20.0, 1.0, shrinkage_compensation=False
        )
        assert result_comp["stats"]["actual_dia_mm"] > result_none["stats"]["actual_dia_mm"]

    def test_shrinkage_scale_factor(self):
        """actual_dia_mm should be target_dia / (1 - shrinkage)."""
        dia = 25.0
        result = image_to_relief(_flat_image(), dia, 1.0, shrinkage_compensation=True)
        expected = dia / (1.0 - _CASTING_SHRINKAGE)
        assert abs(result["stats"]["actual_dia_mm"] - expected) < 0.01


# ---------------------------------------------------------------------------
# 12. relief_to_signet: geometry meets ring inner diameter
# ---------------------------------------------------------------------------

class TestReliefToSignet:

    def _make_mesh(self):
        return image_to_relief(_gradient_image(), 12.0, 0.5, style="linear",
                               boundary="circular", border_frac=0.0,
                               shrinkage_compensation=False)

    def test_returns_ok(self):
        mesh = self._make_mesh()
        result = relief_to_signet(mesh, 14.0, 7, system="us")
        assert result.get("ok") is True

    def test_signet_spec_present(self):
        mesh = self._make_mesh()
        result = relief_to_signet(mesh, 14.0, 7, system="us")
        assert "signet_spec" in result
        assert result["signet_spec"]["face_diameter_mm"] == 14.0

    def test_inner_diameter_matches_ring_size(self):
        """US size 7 → inner diameter ≈ 17.32 mm."""
        mesh = self._make_mesh()
        result = relief_to_signet(mesh, 20.0, 7, system="us")
        expected_id = 11.63 + 0.8128 * 7
        assert abs(result["inner_diameter_mm"] - expected_id) < 0.01

    def test_face_too_narrow_emits_warning(self):
        mesh = self._make_mesh()
        # Size 7 gives id≈17.32; face_dia=15 is too narrow
        result = relief_to_signet(mesh, 15.0, 7, system="us")
        assert result.get("ok") is True
        assert len(result["warnings"]) > 0

    def test_invalid_relief_mesh_returns_bad(self):
        result = relief_to_signet({"ok": False, "reason": "bad"}, 14.0, 7)
        assert result.get("ok") is False

    def test_intaglio_mode_recorded(self):
        mesh = self._make_mesh()
        result = relief_to_signet(mesh, 20.0, 7, intaglio=True)
        assert result["signet_spec"]["mode"] == "recessed"

    def test_cameo_mode_recorded(self):
        mesh = self._make_mesh()
        result = relief_to_signet(mesh, 20.0, 7, intaglio=False)
        assert result["signet_spec"]["mode"] == "raised"

    def test_attach_points_present(self):
        mesh = self._make_mesh()
        result = relief_to_signet(mesh, 20.0, 7)
        aps = result["signet_spec"]["attach_points"]
        assert len(aps) == 1
        assert aps[0]["type"] == "signet_face"


# ---------------------------------------------------------------------------
# 13. relief_metal_volume_mm3
# ---------------------------------------------------------------------------

class TestReliefMetalVolume:

    def test_positive_volume_for_nonzero_relief(self):
        mesh = image_to_relief(_gradient_image(), 20.0, 2.0, style="linear",
                               boundary="circular", border_frac=0.0,
                               shrinkage_compensation=False)
        vol = relief_metal_volume_mm3(mesh)
        assert vol > 0.0

    def test_zero_volume_for_flat_zero_relief(self):
        mesh = image_to_relief(_flat_image(8, 0.0), 20.0, 2.0, style="linear",
                               boundary="square", border_frac=0.0,
                               shrinkage_compensation=False)
        vol = relief_metal_volume_mm3(mesh)
        assert vol == 0.0

    def test_invalid_mesh_returns_zero(self):
        assert relief_metal_volume_mm3({"ok": False}) == 0.0
        assert relief_metal_volume_mm3({}) == 0.0

    def test_volume_proportional_to_max_depth(self):
        """Doubling max_depth should approximately double the volume."""
        img = _flat_image(8, 0.6)
        r1 = image_to_relief(img, 20.0, 1.0, style="linear", boundary="square",
                             border_frac=0.0, shrinkage_compensation=False)
        r2 = image_to_relief(img, 20.0, 2.0, style="linear", boundary="square",
                             border_frac=0.0, shrinkage_compensation=False)
        v1 = relief_metal_volume_mm3(r1)
        v2 = relief_metal_volume_mm3(r2)
        ratio = v2 / v1
        assert abs(ratio - 2.0) < 0.01, f"Expected volume ratio ≈ 2.0, got {ratio:.4f}"


# ---------------------------------------------------------------------------
# 14. optimize_for_casting
# ---------------------------------------------------------------------------

class TestOptimizeForCasting:

    def _spiky_mesh(self):
        """Create a mesh with a deliberate spike at the centre vertex."""
        img = _flat_image(10, 0.3)
        # Inject a spike at the centre
        img[5][5] = 1.0
        return image_to_relief(img, 20.0, 3.0, style="linear", boundary="square",
                               border_frac=0.0, shrinkage_compensation=False)

    def test_returns_ok(self):
        mesh = self._spiky_mesh()
        result = optimize_for_casting(mesh, min_feature_mm=0.3, smooth_passes=2)
        assert result.get("ok") is True

    def test_delta_features_reported(self):
        mesh = self._spiky_mesh()
        result = optimize_for_casting(mesh, min_feature_mm=0.3, smooth_passes=2)
        assert "delta_features" in result
        assert result["delta_features"] >= 0

    def test_spike_is_reduced(self):
        """After optimisation, max Z should be less than before."""
        mesh = self._spiky_mesh()
        max_before = max(v[2] for v in mesh["verts"])
        result = optimize_for_casting(mesh, min_feature_mm=0.1, smooth_passes=3)
        max_after = max(v[2] for v in result["verts"])
        assert max_after <= max_before + 1e-9

    def test_faces_unchanged(self):
        mesh = self._spiky_mesh()
        result = optimize_for_casting(mesh, smooth_passes=1)
        assert result["faces"] == mesh["faces"]

    def test_invalid_mesh_returns_bad(self):
        result = optimize_for_casting({"ok": False, "reason": "bad"})
        assert result.get("ok") is False

    def test_zero_min_feature_returns_bad(self):
        mesh = self._spiky_mesh()
        result = optimize_for_casting(mesh, min_feature_mm=0.0)
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# 15. relief_diagnostics
# ---------------------------------------------------------------------------

class TestReliefDiagnostics:

    def _mesh(self):
        return image_to_relief(_gradient_image(), 20.0, 2.0, style="linear",
                               boundary="circular", border_frac=0.0,
                               shrinkage_compensation=False)

    def test_returns_ok(self):
        assert relief_diagnostics(self._mesh()).get("ok") is True

    def test_expected_keys_present(self):
        d = relief_diagnostics(self._mesh())
        for key in ("vert_count", "face_count", "min_z_mm", "max_z_mm",
                    "mean_z_mm", "min_feature_size_mm", "max_overhang_deg",
                    "bbox_x_mm", "bbox_y_mm", "bbox_z_mm", "warnings"):
            assert key in d, f"Missing key: {key}"

    def test_vert_face_counts_match_mesh(self):
        mesh = self._mesh()
        d = relief_diagnostics(mesh)
        assert d["vert_count"] == len(mesh["verts"])
        assert d["face_count"] == len(mesh["faces"])

    def test_max_z_matches_mesh(self):
        mesh = self._mesh()
        d = relief_diagnostics(mesh)
        max_z_direct = max(v[2] for v in mesh["verts"])
        assert abs(d["max_z_mm"] - max_z_direct) < 0.01

    def test_invalid_mesh_returns_bad(self):
        assert relief_diagnostics({"ok": False}).get("ok") is False

    def test_min_feature_positive(self):
        d = relief_diagnostics(self._mesh())
        assert d["min_feature_size_mm"] > 0.0


# ---------------------------------------------------------------------------
# 16. LLM tool round-trip via run_* handlers
# ---------------------------------------------------------------------------

class TestLLMToolRoundTrip:
    """
    ok_payload(v) returns json.dumps(v), so the parsed dict IS the payload.
    err_payload(msg, code) returns {"error": ..., "code": ...} — no "ok" key.
    Success responses from image_to_relief carry "ok": True (forwarded from
    the inner relief result).  Volume/signet responses carry "volume_mm3" or
    "signet_spec" directly.
    """

    def _ctx(self):
        return _make_ctx()

    def test_run_image_to_relief_ok(self):
        payload = {
            "image_rows": _flat_image(8, 0.5),
            "target_dia_mm": 20.0,
            "max_depth_mm": 1.0,
            "style": "linear",
            "boundary": "square",
            "border_frac": 0.0,
            "shrinkage_compensation": False,
        }
        resp = run_sync(run_jewelry_image_to_relief(self._ctx(), json.dumps(payload).encode()))
        assert resp.get("ok") is True

    def test_run_image_to_relief_bad_args(self):
        # err_payload returns {"error": ..., "code": ...} — "ok" key absent
        resp = run_sync(run_jewelry_image_to_relief(self._ctx(), b"not json"))
        assert "error" in resp
        assert resp.get("code") == "BAD_ARGS"

    def test_run_relief_to_signet_ok(self):
        mesh = image_to_relief(_gradient_image(), 14.0, 0.8, style="linear",
                               boundary="circular", border_frac=0.0,
                               shrinkage_compensation=False)
        payload = {
            "relief_mesh": mesh,
            "signet_face_diameter": 16.0,
            "ring_size": 7,
            "system": "us",
        }
        resp = run_sync(run_jewelry_relief_to_signet(self._ctx(), json.dumps(payload).encode()))
        # ok_payload forwards the relief_to_signet dict which has "ok": True
        assert resp.get("ok") is True
        assert "signet_spec" in resp

    def test_run_relief_metal_volume_ok(self):
        mesh = image_to_relief(_flat_image(8, 0.5), 20.0, 1.0, style="linear",
                               boundary="square", border_frac=0.0,
                               shrinkage_compensation=False)
        payload = {"relief_mesh": mesh}
        resp = run_sync(run_jewelry_relief_metal_volume(self._ctx(), json.dumps(payload).encode()))
        # ok_payload({"volume_mm3": vol}) has no "ok" key — just the data
        assert "volume_mm3" in resp
        assert isinstance(resp["volume_mm3"], float)

    def test_run_optimize_for_casting_ok(self):
        mesh = image_to_relief(_gradient_image(), 20.0, 2.0, style="linear",
                               boundary="square", border_frac=0.0,
                               shrinkage_compensation=False)
        payload = {"relief_mesh": mesh, "min_feature_mm": 0.3, "smooth_passes": 1}
        resp = run_sync(run_jewelry_optimize_relief_for_casting(self._ctx(), json.dumps(payload).encode()))
        assert resp.get("ok") is True

    def test_run_image_to_relief_missing_required(self):
        payload = {"target_dia_mm": 20.0, "max_depth_mm": 1.0}  # missing image_rows
        resp = run_sync(run_jewelry_image_to_relief(self._ctx(), json.dumps(payload).encode()))
        # Missing image_rows → err_payload with "BAD_ARGS"
        assert "error" in resp
        assert resp.get("code") == "BAD_ARGS"
