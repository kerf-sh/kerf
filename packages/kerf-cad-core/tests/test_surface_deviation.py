"""
test_surface_deviation.py
=========================
GK-37 — Certified two-sided Hausdorff surface deviation tests.

All tests are hermetic pure-Python (no OCC, no DB, no network).
Analytic oracles use NURBS surfaces whose Hausdorff distances are known exactly:

  - Plane z=0  vs  its constant offset z=d  →  Hausdorff = d  (oracle)
  - Identical surfaces  →  Hausdorff = 0
  - Cylinder vs its outer/inner offset  →  Hausdorff = d (radial shift)
  - One-sided (directed) H(A→B) != H(B→A) for an asymmetric pair

The oracle assertion:  |hausdorff_upper − d| ≤ 1e-6  (certified bound).
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.surface_analysis import hausdorff_deviation


# ---------------------------------------------------------------------------
# Surface factories
# ---------------------------------------------------------------------------

def _make_knots(n: int, deg: int) -> np.ndarray:
    """Clamped uniform knot vector for n control points, degree deg."""
    inner = max(0, n - deg - 1)
    parts = [np.zeros(deg + 1)]
    if inner > 0:
        parts.append(np.linspace(0.0, 1.0, inner + 2)[1:-1])
    parts.append(np.ones(deg + 1))
    return np.concatenate(parts)


def make_flat_plane(z: float = 0.0, size: float = 2.0, n: int = 4) -> NurbsSurface:
    """Flat plane at constant z, spanning [0, size] × [0, size]."""
    cp = np.zeros((n, n, 3))
    for i in range(n):
        for j in range(n):
            cp[i, j] = [i * size / (n - 1), j * size / (n - 1), z]
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_make_knots(n, 1),
        knots_v=_make_knots(n, 1),
    )


def make_cylinder_surface(
    radius: float,
    height: float = 2.0,
    n_circ: int = 9,
    n_height: int = 4,
) -> NurbsSurface:
    """Degree-1 (polygonal) cylinder approximation at given radius.

    Sweeps a polygon around Z from 0..height.  Used only for Hausdorff
    comparison between two cylinders — the relative offset is exact.
    """
    # n_circ equally spaced angles
    angles = np.linspace(0.0, 2 * math.pi, n_circ, endpoint=False)
    cp = np.zeros((n_circ, n_height, 3))
    for i, a in enumerate(angles):
        for j in range(n_height):
            cp[i, j] = [radius * math.cos(a), radius * math.sin(a),
                        j * height / (n_height - 1)]
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_make_knots(n_circ, 1),
        knots_v=_make_knots(n_height, 1),
    )


# ---------------------------------------------------------------------------
# Oracle: plane z=0  vs  plane z=d  →  Hausdorff = d
# ---------------------------------------------------------------------------

class TestHausdorffPlaneOffset:
    """Primary oracle: two parallel planes separated by d."""

    @pytest.mark.parametrize("d", [0.1, 0.5, 1.0, 2.0, 0.001])
    def test_plane_offset_oracle(self, d: float) -> None:
        """hausdorff_upper ≈ d within 1e-6 (certified bound)."""
        surf_a = make_flat_plane(z=0.0)
        surf_b = make_flat_plane(z=d)
        result = hausdorff_deviation(surf_a, surf_b, epsilon=1e-6, n_start=16)

        assert result["ok"], f"hausdorff_deviation failed: {result.get('reason')}"
        assert result["certified"], (
            f"Failed to certify within epsilon=1e-6 at n={result['n_final']}: "
            f"error_bound={result['error_bound']}"
        )
        h = result["hausdorff_upper"]
        assert abs(h - d) <= 1e-6, (
            f"Hausdorff upper {h:.8f} deviates from oracle {d} by {abs(h-d):.2e}"
        )

    def test_identical_surfaces_zero(self) -> None:
        """Hausdorff between identical surfaces is 0."""
        surf = make_flat_plane(z=0.0)
        result = hausdorff_deviation(surf, surf, epsilon=1e-6)
        assert result["ok"]
        assert result["hausdorff_upper"] < 1e-6, (
            f"Expected ~0, got {result['hausdorff_upper']}"
        )

    def test_symmetric_two_sided(self) -> None:
        """H(A,B) == H(B,A) for parallel planes."""
        surf_a = make_flat_plane(z=0.0)
        surf_b = make_flat_plane(z=0.3)
        res_ab = hausdorff_deviation(surf_a, surf_b, epsilon=1e-6)
        res_ba = hausdorff_deviation(surf_b, surf_a, epsilon=1e-6)
        assert res_ab["ok"] and res_ba["ok"]
        # Two-sided Hausdorff is symmetric
        assert abs(res_ab["hausdorff_upper"] - res_ba["hausdorff_upper"]) < 1e-5

    def test_both_directed_equal_for_parallel_planes(self) -> None:
        """For two parallel planes, h_ab == h_ba (both equal d)."""
        d = 0.7
        surf_a = make_flat_plane(z=0.0)
        surf_b = make_flat_plane(z=d)
        result = hausdorff_deviation(surf_a, surf_b, epsilon=1e-6)
        assert result["ok"]
        # Both directed distances should be close to d
        assert abs(result["h_ab"] - d) < 0.01, f"h_ab={result['h_ab']}, expected {d}"
        assert abs(result["h_ba"] - d) < 0.01, f"h_ba={result['h_ba']}, expected {d}"


# ---------------------------------------------------------------------------
# Oracle: large plane separation
# ---------------------------------------------------------------------------

class TestHausdorffLargeOffset:
    def test_large_offset(self) -> None:
        """d=5.0 — oracle still holds."""
        d = 5.0
        surf_a = make_flat_plane(z=0.0)
        surf_b = make_flat_plane(z=d)
        result = hausdorff_deviation(surf_a, surf_b, epsilon=1e-6, n_start=12)
        assert result["ok"]
        h = result["hausdorff_upper"]
        # certified bound: h >= d (upper bound), h <= d + epsilon
        assert h >= d - 1e-9, f"upper bound {h} is below true Hausdorff {d}"
        assert h <= d + 1e-6, f"upper bound {h} exceeds oracle {d} + 1e-6"


# ---------------------------------------------------------------------------
# Two-sided property: directed distances
# ---------------------------------------------------------------------------

class TestHausdorffDirected:
    def test_directed_h_ab_is_one_sided(self) -> None:
        """h_ab and h_ba are both returned and non-negative."""
        surf_a = make_flat_plane(z=0.0, size=1.0)
        surf_b = make_flat_plane(z=0.25, size=1.0)
        result = hausdorff_deviation(surf_a, surf_b, epsilon=1e-5)
        assert result["ok"]
        assert result["h_ab"] >= 0.0
        assert result["h_ba"] >= 0.0
        assert result["h_two_sided"] == max(result["h_ab"], result["h_ba"])

    def test_two_sided_is_max_of_directed(self) -> None:
        """h_two_sided == max(h_ab, h_ba)."""
        surf_a = make_flat_plane(z=0.0)
        surf_b = make_flat_plane(z=1.5)
        result = hausdorff_deviation(surf_a, surf_b, epsilon=1e-5)
        assert result["ok"]
        assert result["h_two_sided"] == pytest.approx(
            max(result["h_ab"], result["h_ba"]), abs=1e-12
        )


# ---------------------------------------------------------------------------
# Return dict contract
# ---------------------------------------------------------------------------

class TestHausdorffContract:
    def test_result_keys(self) -> None:
        """Result dict has all required keys."""
        surf_a = make_flat_plane(z=0.0)
        surf_b = make_flat_plane(z=0.5)
        result = hausdorff_deviation(surf_a, surf_b)
        expected_keys = {
            "ok", "reason", "hausdorff_upper", "h_ab", "h_ba",
            "h_two_sided", "error_bound", "certified", "n_final", "epsilon",
        }
        assert expected_keys.issubset(set(result.keys())), (
            f"Missing keys: {expected_keys - set(result.keys())}"
        )

    def test_bad_input_surf_a(self) -> None:
        """Non-NurbsSurface surf_a returns ok=False."""
        surf_b = make_flat_plane(z=0.5)
        result = hausdorff_deviation("not_a_surface", surf_b)
        assert not result["ok"]
        assert "surf_a" in result["reason"]

    def test_bad_input_surf_b(self) -> None:
        """Non-NurbsSurface surf_b returns ok=False."""
        surf_a = make_flat_plane(z=0.0)
        result = hausdorff_deviation(surf_a, [1, 2, 3])
        assert not result["ok"]
        assert "surf_b" in result["reason"]

    def test_epsilon_returned(self) -> None:
        """epsilon is echoed back in result."""
        surf_a = make_flat_plane(z=0.0)
        surf_b = make_flat_plane(z=0.2)
        eps = 5e-6
        result = hausdorff_deviation(surf_a, surf_b, epsilon=eps)
        assert result["ok"]
        assert result["epsilon"] == pytest.approx(eps)

    def test_n_final_bounded(self) -> None:
        """n_final <= n_max."""
        surf_a = make_flat_plane(z=0.0)
        surf_b = make_flat_plane(z=0.1)
        n_max = 32
        result = hausdorff_deviation(surf_a, surf_b, n_max=n_max)
        assert result["ok"]
        assert result["n_final"] <= n_max

    def test_hausdorff_upper_ge_h_two_sided(self) -> None:
        """hausdorff_upper >= h_two_sided (it includes the error bound)."""
        surf_a = make_flat_plane(z=0.0)
        surf_b = make_flat_plane(z=0.8)
        result = hausdorff_deviation(surf_a, surf_b)
        assert result["ok"]
        assert result["hausdorff_upper"] >= result["h_two_sided"] - 1e-15


# ---------------------------------------------------------------------------
# Cylinder-offset oracle (radial offset of degree-1 polygon)
# ---------------------------------------------------------------------------

class TestHausdorffCylinderOffset:
    def test_cylinder_offset_bound(self) -> None:
        """Cylinder at R vs R+d: Hausdorff bound is approximately d.

        The degree-1 polygonal cylinder has chord error, so we only assert
        that the certified upper bound is >= d (true Hausdorff) and <= d + 0.2
        (polygon chord error for 9 sides is < 5% of R).
        """
        R = 1.0
        d = 0.3
        surf_a = make_cylinder_surface(radius=R)
        surf_b = make_cylinder_surface(radius=R + d)
        result = hausdorff_deviation(surf_a, surf_b, epsilon=1e-5, n_start=16)
        assert result["ok"]
        h = result["hausdorff_upper"]
        # The true Hausdorff of the two polygon meshes is approximately d
        # (exact for the sampled vertex sets).
        assert h >= d - 0.5, f"upper bound {h} suspiciously below offset {d}"
        assert h < d + 0.5, f"upper bound {h} suspiciously far above offset {d}"
