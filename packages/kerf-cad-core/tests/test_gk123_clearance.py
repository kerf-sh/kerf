"""GK-123: Hermetic, analytic-oracle tests for clearance / minimum-gap analysis.

All tests are pure-Python (no OCCT, no network, no DB).  The primary oracle:
  two spheres with centre-distance D and radii r1, r2 → gap = D − r1 − r2.

We use :func:`sphere_to_body` (which builds a minimal 2-vertex / 1-edge B-rep
sphere) so the vertex/edge sample strategy picks up the poles and the meridian
seam — sufficient for tight analytic verification.  Box bodies are used for
the "overlapping → gap ≤ 0" check and for the public-export smoke test.
"""

from __future__ import annotations

import math

import pytest

from kerf_cad_core.geom.brep_build import sphere_to_body, box_to_body
from kerf_cad_core.geom.assembly import clearance
# Also verify the public façade export.
from kerf_cad_core.geom import clearance as clearance_public


# Tolerance used throughout: generous enough for the sample approximation.
TOL = 0.15  # sample-based; vertices + 8 interior edge pts on each meridian


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dist3(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


# ---------------------------------------------------------------------------
# Tests: two spheres — analytic oracle gap = D − r1 − r2
# ---------------------------------------------------------------------------


class TestClearanceSpheres:
    """Sphere-pair oracle: gap = centre_distance − r1 − r2."""

    def test_gap_analytic_simple(self):
        # Centres at (0,0,0) and (10,0,0), radii both 1 → gap = 8
        r1, r2, D = 1.0, 1.0, 10.0
        expected_gap = D - r1 - r2  # 8.0
        a = sphere_to_body([0.0, 0.0, 0.0], r1)
        b = sphere_to_body([D, 0.0, 0.0], r2)
        result = clearance(a, b)
        assert abs(result["gap"] - expected_gap) <= TOL, (
            f"Expected gap≈{expected_gap}, got {result['gap']}"
        )

    def test_gap_analytic_unequal_radii(self):
        # r1=2, r2=3, D=10 → gap=5
        r1, r2, D = 2.0, 3.0, 10.0
        expected_gap = D - r1 - r2  # 5.0
        a = sphere_to_body([0.0, 0.0, 0.0], r1)
        b = sphere_to_body([D, 0.0, 0.0], r2)
        result = clearance(a, b)
        assert abs(result["gap"] - expected_gap) <= TOL, (
            f"Expected gap≈{expected_gap}, got {result['gap']}"
        )

    def test_gap_small(self):
        # r1=r2=1, D=2.5 → gap=0.5
        r1, r2, D = 1.0, 1.0, 2.5
        expected_gap = D - r1 - r2  # 0.5
        a = sphere_to_body([0.0, 0.0, 0.0], r1)
        b = sphere_to_body([D, 0.0, 0.0], r2)
        result = clearance(a, b)
        assert abs(result["gap"] - expected_gap) <= TOL, (
            f"Expected gap≈{expected_gap}, got {result['gap']}"
        )

    def test_gap_along_z_axis(self):
        # Centres separated along Z
        r1, r2, D = 1.0, 1.5, 8.0
        expected_gap = D - r1 - r2  # 5.5
        a = sphere_to_body([0.0, 0.0, 0.0], r1)
        b = sphere_to_body([0.0, 0.0, D], r2)
        result = clearance(a, b)
        assert abs(result["gap"] - expected_gap) <= TOL, (
            f"Expected gap≈{expected_gap}, got {result['gap']}"
        )

    def test_gap_is_non_negative_for_disjoint(self):
        a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
        b = sphere_to_body([5.0, 0.0, 0.0], 1.0)
        result = clearance(a, b)
        assert result["gap"] >= 0.0

    def test_witness_points_returned(self):
        a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
        b = sphere_to_body([5.0, 0.0, 0.0], 1.0)
        result = clearance(a, b)
        assert len(result["witness_a"]) == 3
        assert len(result["witness_b"]) == 3

    def test_witness_distance_equals_gap(self):
        """For disjoint bodies the distance between witness points equals the gap."""
        a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
        b = sphere_to_body([5.0, 0.0, 0.0], 1.0)
        result = clearance(a, b)
        # These spheres are disjoint (gap ≈ 3), so no interference path.
        assert result["gap"] > 0.0
        d = _dist3(result["witness_a"], result["witness_b"])
        assert math.isclose(d, result["gap"], rel_tol=1e-9, abs_tol=1e-12)

    def test_witness_a_near_sphere_a_surface(self):
        """Witness A should lie on (or very near) sphere A's surface."""
        r1, D = 1.0, 6.0
        a = sphere_to_body([0.0, 0.0, 0.0], r1)
        b = sphere_to_body([D, 0.0, 0.0], 1.0)
        result = clearance(a, b)
        dist_from_centre_a = _dist3(result["witness_a"], [0.0, 0.0, 0.0])
        # Sample points are on vertices / edge — they are on the sphere surface
        assert abs(dist_from_centre_a - r1) <= 1e-9


# ---------------------------------------------------------------------------
# Tests: overlapping bodies → gap ≤ 0
# ---------------------------------------------------------------------------


class TestClearanceOverlapping:
    """When two bodies overlap the sample-based gap should be ≤ 0."""

    def test_overlapping_boxes_gap_le_zero(self):
        # Two unit boxes with large overlap
        a = box_to_body(corner=(0, 0, 0), dx=3, dy=3, dz=3)
        b = box_to_body(corner=(1, 1, 1), dx=3, dy=3, dz=3)
        result = clearance(a, b)
        assert result["gap"] <= 0.0, (
            f"Overlapping bodies should give gap ≤ 0, got {result['gap']}"
        )

    def test_identical_bodies_gap_is_zero(self):
        a = box_to_body(corner=(0, 0, 0), dx=2, dy=2, dz=2)
        b = box_to_body(corner=(0, 0, 0), dx=2, dy=2, dz=2)
        result = clearance(a, b)
        assert result["gap"] <= 0.0


# ---------------------------------------------------------------------------
# Tests: dict contract
# ---------------------------------------------------------------------------


class TestClearanceReturnShape:
    """Verify the dict contract (keys always present with correct types)."""

    def test_keys_present(self):
        a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
        b = sphere_to_body([5.0, 0.0, 0.0], 1.0)
        result = clearance(a, b)
        assert set(result.keys()) == {"gap", "witness_a", "witness_b"}

    def test_gap_is_float(self):
        a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
        b = sphere_to_body([5.0, 0.0, 0.0], 1.0)
        result = clearance(a, b)
        assert isinstance(result["gap"], float)

    def test_witness_a_is_list_of_3(self):
        a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
        b = sphere_to_body([5.0, 0.0, 0.0], 1.0)
        result = clearance(a, b)
        assert isinstance(result["witness_a"], list)
        assert len(result["witness_a"]) == 3

    def test_witness_b_is_list_of_3(self):
        a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
        b = sphere_to_body([5.0, 0.0, 0.0], 1.0)
        result = clearance(a, b)
        assert isinstance(result["witness_b"], list)
        assert len(result["witness_b"]) == 3


# ---------------------------------------------------------------------------
# Tests: public façade export
# ---------------------------------------------------------------------------


class TestClearancePublicExport:
    """Verify `clearance` is reachable from the kerf_cad_core.geom façade."""

    def test_public_export_same_result(self):
        a = sphere_to_body([0.0, 0.0, 0.0], 1.0)
        b = sphere_to_body([5.0, 0.0, 0.0], 1.0)
        r1 = clearance(a, b)
        r2 = clearance_public(a, b)
        assert math.isclose(r1["gap"], r2["gap"], rel_tol=1e-9)
        assert r1["witness_a"] == r2["witness_a"]
        assert r1["witness_b"] == r2["witness_b"]
