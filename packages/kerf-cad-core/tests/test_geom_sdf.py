"""GK-112 — Hermetic tests for geom/sdf.py.

Oracle
------
SDF of a unit sphere (centre = origin, radius = 1) at a point distance *d*
from the centre should return ``d − 1 ± grid_tol``.

Sign convention: **negative inside** the body, positive outside.

Pure-Python / numpy only — no OCC, no DB, no network.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import make_sphere, make_box
from kerf_cad_core.geom.sdf import body_sdf, sdf_sample
from kerf_cad_core.geom import body_sdf as body_sdf_pub, sdf_sample as sdf_sample_pub


# ---------------------------------------------------------------------------
# Shared fixture: unit sphere SDF at resolution=32
# ---------------------------------------------------------------------------

_RESOLUTION = 32
_RADIUS = 1.0
# Padding chosen so the grid covers up to d=2.1 from the centre.
# bbox diagonal of unit sphere = 2*sqrt(3) ≈ 3.46; pad = 0.32 → adds
# 0.32 * 3.46 ≈ 1.1 to each side of the [-1,1]³ box → hi ≈ 2.1.
_PADDING = 0.32


@pytest.fixture(scope="module")
def unit_sphere_sdf():
    body = make_sphere(center=(0.0, 0.0, 0.0), radius=_RADIUS)
    return body_sdf(body, resolution=_RESOLUTION, padding=_PADDING)


# ---------------------------------------------------------------------------
# Grid tolerance: distance between adjacent grid nodes plus a small factor.
# For a sphere of radius 1 in a padded box of ~[−1.35, 1.35]³ at res=32:
#   spacing ≈ 2.7 / 31 ≈ 0.087 → grid_tol ≈ 0.18 (2 cells)
# ---------------------------------------------------------------------------

def _grid_tol(sdf_dict: dict) -> float:
    """Two-cell grid tolerance."""
    return 2.0 * float(np.max(sdf_dict["spacing"]))


# ===========================================================================
# 1. Return structure
# ===========================================================================

class TestBodySdfStructure:
    def test_keys_present(self, unit_sphere_sdf):
        assert {"grid", "origin", "spacing", "dims"} <= set(unit_sphere_sdf.keys())

    def test_dims_correct(self, unit_sphere_sdf):
        nx, ny, nz = unit_sphere_sdf["dims"]
        assert nx == _RESOLUTION
        assert ny == _RESOLUTION
        assert nz == _RESOLUTION

    def test_grid_shape(self, unit_sphere_sdf):
        g = unit_sphere_sdf["grid"]
        assert g.shape == (_RESOLUTION, _RESOLUTION, _RESOLUTION)

    def test_grid_dtype(self, unit_sphere_sdf):
        assert unit_sphere_sdf["grid"].dtype == np.float64

    def test_spacing_positive(self, unit_sphere_sdf):
        s = unit_sphere_sdf["spacing"]
        assert np.all(s > 0)

    def test_origin_shape(self, unit_sphere_sdf):
        assert len(unit_sphere_sdf["origin"]) == 3


# ===========================================================================
# 2. Oracle: SDF at distance d from centre ≈ d − 1 ± grid_tol
# ===========================================================================

class TestSphereSdfOracle:
    """Main oracle test: value at distance d should be d − 1 ± grid_tol."""

    @pytest.mark.parametrize("d", [0.0, 0.5, 1.0, 1.5, 2.0])
    def test_on_axis_x(self, unit_sphere_sdf, d):
        tol = _grid_tol(unit_sphere_sdf)
        point = [d, 0.0, 0.0]
        val = sdf_sample(unit_sphere_sdf, point)
        expected = d - _RADIUS
        assert abs(val - expected) < tol, (
            f"d={d}: sdf_sample={val:.4f}, expected={expected:.4f}, tol={tol:.4f}"
        )

    @pytest.mark.parametrize("d", [0.3, 0.8, 1.2, 1.8])
    def test_on_axis_y(self, unit_sphere_sdf, d):
        tol = _grid_tol(unit_sphere_sdf)
        point = [0.0, d, 0.0]
        val = sdf_sample(unit_sphere_sdf, point)
        expected = d - _RADIUS
        assert abs(val - expected) < tol, (
            f"d={d}: sdf_sample={val:.4f}, expected={expected:.4f}, tol={tol:.4f}"
        )

    @pytest.mark.parametrize("d", [0.2, 0.7, 1.1, 1.6])
    def test_on_axis_z(self, unit_sphere_sdf, d):
        tol = _grid_tol(unit_sphere_sdf)
        point = [0.0, 0.0, d]
        val = sdf_sample(unit_sphere_sdf, point)
        expected = d - _RADIUS
        assert abs(val - expected) < tol, (
            f"d={d}: sdf_sample={val:.4f}, expected={expected:.4f}, tol={tol:.4f}"
        )

    @pytest.mark.parametrize("d", [0.4, 1.0, 1.5])
    def test_diagonal(self, unit_sphere_sdf, d):
        """Point along (1,1,1) / sqrt(3) direction at distance d."""
        tol = _grid_tol(unit_sphere_sdf)
        inv_sqrt3 = 1.0 / math.sqrt(3.0)
        point = [d * inv_sqrt3, d * inv_sqrt3, d * inv_sqrt3]
        val = sdf_sample(unit_sphere_sdf, point)
        expected = d - _RADIUS
        assert abs(val - expected) < tol, (
            f"d={d}: sdf_sample={val:.4f}, expected={expected:.4f}, tol={tol:.4f}"
        )


# ===========================================================================
# 3. Sign convention: negative inside, positive outside
# ===========================================================================

class TestSphereSdfSign:
    def test_origin_is_negative(self, unit_sphere_sdf):
        """Origin is deep inside the unit sphere → SDF must be negative."""
        val = sdf_sample(unit_sphere_sdf, [0.0, 0.0, 0.0])
        assert val < 0.0, f"expected negative inside, got {val}"

    def test_far_point_is_positive(self, unit_sphere_sdf):
        """Point far outside → SDF must be positive."""
        val = sdf_sample(unit_sphere_sdf, [3.0, 0.0, 0.0])
        assert val > 0.0, f"expected positive outside, got {val}"

    def test_surface_near_zero(self, unit_sphere_sdf):
        """Point on (or very near) the sphere surface → SDF ≈ 0."""
        tol = _grid_tol(unit_sphere_sdf)
        val = sdf_sample(unit_sphere_sdf, [_RADIUS, 0.0, 0.0])
        assert abs(val) < tol, f"|sdf| at surface = {abs(val):.4f}, tol={tol:.4f}"

    def test_sign_flips_at_surface(self, unit_sphere_sdf):
        """SDF is negative just inside and positive just outside."""
        tol = _grid_tol(unit_sphere_sdf)
        inside = sdf_sample(unit_sphere_sdf, [_RADIUS - tol, 0.0, 0.0])
        outside = sdf_sample(unit_sphere_sdf, [_RADIUS + tol, 0.0, 0.0])
        assert inside < 0.0, f"inside should be negative, got {inside}"
        assert outside > 0.0, f"outside should be positive, got {outside}"


# ===========================================================================
# 4. sdf_sample trilinear interpolation
# ===========================================================================

class TestSdfSampleTrilinear:
    def test_exact_grid_point(self, unit_sphere_sdf):
        """Sampling at an exact grid point matches the grid value."""
        origin = unit_sphere_sdf["origin"]
        spacing = unit_sphere_sdf["spacing"]
        i, j, k = 5, 7, 11
        exact = np.array([
            origin[0] + i * spacing[0],
            origin[1] + j * spacing[1],
            origin[2] + k * spacing[2],
        ])
        val = sdf_sample(unit_sphere_sdf, exact)
        expected = float(unit_sphere_sdf["grid"][i, j, k])
        assert abs(val - expected) < 1e-12, (
            f"at exact grid point: got {val}, expected {expected}"
        )

    def test_clamp_outside_grid(self, unit_sphere_sdf):
        """Points far outside the grid should not raise and return a finite value."""
        val = sdf_sample(unit_sphere_sdf, [1e6, 0.0, 0.0])
        assert math.isfinite(val)

    def test_bad_dict_raises(self):
        with pytest.raises(ValueError, match="missing keys"):
            sdf_sample({"grid": np.zeros((4, 4, 4))}, [0, 0, 0])


# ===========================================================================
# 5. Error handling
# ===========================================================================

class TestBodySdfErrors:
    def test_low_resolution_raises(self):
        body = make_sphere(center=(0, 0, 0), radius=1.0)
        with pytest.raises(ValueError, match="resolution"):
            body_sdf(body, resolution=1)

    def test_resolution_2_ok(self):
        body = make_sphere(center=(0, 0, 0), radius=1.0)
        result = body_sdf(body, resolution=2)
        assert result["dims"] == (2, 2, 2)


# ===========================================================================
# 6. Public re-export from kerf_cad_core.geom
# ===========================================================================

class TestPublicExport:
    def test_body_sdf_exported(self):
        assert body_sdf_pub is body_sdf

    def test_sdf_sample_exported(self):
        assert sdf_sample_pub is sdf_sample


# ===========================================================================
# 7. Box body — sign check (simpler topology)
# ===========================================================================

class TestBoxSdf:
    @pytest.fixture(scope="class")
    def box_sdf(self):
        body = make_box(origin=(0.0, 0.0, 0.0), size=(2.0, 2.0, 2.0))
        return body_sdf(body, resolution=24, padding=0.2)

    def test_center_is_negative(self, box_sdf):
        val = sdf_sample(box_sdf, [1.0, 1.0, 1.0])
        assert val < 0.0, f"box centre should be inside (negative), got {val}"

    def test_far_outside_is_positive(self, box_sdf):
        val = sdf_sample(box_sdf, [5.0, 5.0, 5.0])
        assert val > 0.0, f"far outside box should be positive, got {val}"
