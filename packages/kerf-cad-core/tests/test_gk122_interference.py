"""GK-122: Hermetic, analytic-oracle tests for interference / collision detection.

All tests are pure-Python (no OCCT, no network, no DB).  The oracles are
analytic: two overlapping axis-aligned boxes produce a known intersection
volume that can be computed by hand.
"""

from __future__ import annotations

import math

import pytest

from kerf_cad_core.geom.brep_build import box_to_body
from kerf_cad_core.geom.assembly import interference
# Also verify the public façade export.
from kerf_cad_core.geom import interference as interference_public


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _box_vol(dx: float, dy: float, dz: float) -> float:
    return dx * dy * dz


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInterferenceOverlapping:
    """Two boxes that partially overlap — interference must be detected."""

    def test_overlapping_interferes_true(self):
        # Box A: (0,0,0) → (2,2,2)  vol = 8
        # Box B: (1,1,1) → (3,3,3)  vol = 8
        # Overlap: (1,1,1) → (2,2,2)  vol = 1
        a = box_to_body(corner=(0, 0, 0), dx=2, dy=2, dz=2)
        b = box_to_body(corner=(1, 1, 1), dx=2, dy=2, dz=2)
        result = interference(a, b)
        assert result["interferes"] is True

    def test_overlapping_volume_analytic(self):
        a = box_to_body(corner=(0, 0, 0), dx=2, dy=2, dz=2)
        b = box_to_body(corner=(1, 1, 1), dx=2, dy=2, dz=2)
        result = interference(a, b)
        expected_vol = _box_vol(1, 1, 1)  # 1.0
        assert math.isclose(result["volume"], expected_vol, rel_tol=1e-6), (
            f"Expected volume {expected_vol}, got {result['volume']}"
        )

    def test_overlapping_region_is_body(self):
        from kerf_cad_core.geom.brep import Body
        a = box_to_body(corner=(0, 0, 0), dx=2, dy=2, dz=2)
        b = box_to_body(corner=(1, 1, 1), dx=2, dy=2, dz=2)
        result = interference(a, b)
        assert isinstance(result["region"], Body)

    def test_larger_overlap_volume(self):
        # Box A: (0,0,0) → (4,3,5)
        # Box B: (1,1,1) → (5,4,6)  (extends beyond A on all sides)
        # Overlap: (1,1,1) → (4,3,5)  → 3×2×4 = 24
        a = box_to_body(corner=(0, 0, 0), dx=4, dy=3, dz=5)
        b = box_to_body(corner=(1, 1, 1), dx=4, dy=3, dz=5)
        result = interference(a, b)
        expected_vol = _box_vol(3, 2, 4)  # 24.0
        assert result["interferes"] is True
        assert math.isclose(result["volume"], expected_vol, rel_tol=1e-6), (
            f"Expected volume {expected_vol}, got {result['volume']}"
        )


class TestInterferenceDisjoint:
    """Two boxes with no overlap — no interference."""

    def test_disjoint_interferes_false(self):
        a = box_to_body(corner=(0, 0, 0), dx=1, dy=1, dz=1)
        b = box_to_body(corner=(2, 0, 0), dx=1, dy=1, dz=1)
        result = interference(a, b)
        assert result["interferes"] is False

    def test_disjoint_volume_zero(self):
        a = box_to_body(corner=(0, 0, 0), dx=1, dy=1, dz=1)
        b = box_to_body(corner=(2, 0, 0), dx=1, dy=1, dz=1)
        result = interference(a, b)
        assert result["volume"] == 0.0

    def test_disjoint_region_none(self):
        a = box_to_body(corner=(0, 0, 0), dx=1, dy=1, dz=1)
        b = box_to_body(corner=(2, 0, 0), dx=1, dy=1, dz=1)
        result = interference(a, b)
        assert result["region"] is None

    def test_disjoint_along_y(self):
        a = box_to_body(corner=(0, 0, 0), dx=2, dy=1, dz=2)
        b = box_to_body(corner=(0, 5, 0), dx=2, dy=1, dz=2)
        result = interference(a, b)
        assert result["interferes"] is False
        assert result["volume"] == 0.0

    def test_far_apart(self):
        a = box_to_body(corner=(0, 0, 0), dx=1, dy=1, dz=1)
        b = box_to_body(corner=(100, 100, 100), dx=1, dy=1, dz=1)
        result = interference(a, b)
        assert result["interferes"] is False


class TestInterferencePublicExport:
    """Verify `interference` is reachable from the kerf_cad_core.geom façade."""

    def test_public_export_identical_result(self):
        a = box_to_body(corner=(0, 0, 0), dx=2, dy=2, dz=2)
        b = box_to_body(corner=(1, 1, 1), dx=2, dy=2, dz=2)
        r1 = interference(a, b)
        r2 = interference_public(a, b)
        assert r1["interferes"] == r2["interferes"]
        assert math.isclose(r1["volume"], r2["volume"], rel_tol=1e-9)


class TestInterferenceReturnShape:
    """Verify the dict contract (keys always present with correct types)."""

    def test_keys_present_overlapping(self):
        a = box_to_body(corner=(0, 0, 0), dx=2, dy=2, dz=2)
        b = box_to_body(corner=(1, 1, 1), dx=2, dy=2, dz=2)
        result = interference(a, b)
        assert set(result.keys()) == {"interferes", "volume", "region"}

    def test_keys_present_disjoint(self):
        a = box_to_body(corner=(0, 0, 0), dx=1, dy=1, dz=1)
        b = box_to_body(corner=(5, 5, 5), dx=1, dy=1, dz=1)
        result = interference(a, b)
        assert set(result.keys()) == {"interferes", "volume", "region"}

    def test_volume_non_negative(self):
        a = box_to_body(corner=(0, 0, 0), dx=2, dy=2, dz=2)
        b = box_to_body(corner=(1, 1, 1), dx=2, dy=2, dz=2)
        result = interference(a, b)
        assert result["volume"] >= 0.0
