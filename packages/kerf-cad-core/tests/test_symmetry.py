"""Tests for geom/symmetry.py — GK-93 symmetry detection.

Oracles
-------
- Box (axis-aligned unit cube centred at origin):
  * 3 mirror planes (xy, xz, yz)
  * 3 rotation axes of order 2 (x, y, z axes)
  * spherical: False
- Cylinder (axis along z):
  * axisymmetric: True  (rotation_axes contains an entry with order ≥ 36)
  * spherical: False
- Sphere:
  * spherical: True
  * axisymmetric: True
"""

import math
import numpy as np
import pytest

from kerf_cad_core.geom.brep import make_box, make_cylinder, make_sphere
from kerf_cad_core.geom.symmetry import detect_symmetry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_plane_near(planes, normal_target, tol=0.05):
    """Check that *planes* contains an entry whose normal is ∥ normal_target."""
    nt = np.asarray(normal_target, dtype=float)
    nt /= np.linalg.norm(nt)
    for _, n in planes:
        if abs(abs(float(n @ nt)) - 1.0) < tol:
            return True
    return False


def _has_axis_near(axes, direction_target, tol=0.05):
    """Check that *axes* contains an entry whose axis is ∥ direction_target."""
    dt = np.asarray(direction_target, dtype=float)
    dt /= np.linalg.norm(dt)
    for _, ax, _ in axes:
        if abs(abs(float(ax @ dt)) - 1.0) < tol:
            return True
    return False


# ---------------------------------------------------------------------------
# Box
# ---------------------------------------------------------------------------

class TestBoxSymmetry:
    """A unit cube centred at origin has 3 mirror planes and 3 C2 axes."""

    @pytest.fixture(scope="class")
    def result(self):
        body = make_box(origin=(-0.5, -0.5, -0.5), size=(1.0, 1.0, 1.0))
        return detect_symmetry(body, tol=1e-3, n_quad=6)

    def test_not_spherical(self, result):
        assert result["spherical"] is False

    def test_three_mirror_planes(self, result):
        planes = result["mirror_planes"]
        assert len(planes) == 3, f"Expected 3 mirror planes, got {len(planes)}"

    def test_mirror_plane_xy(self, result):
        assert _has_plane_near(result["mirror_planes"], [0, 0, 1]), \
            "Missing xy-plane (normal ∥ z)"

    def test_mirror_plane_xz(self, result):
        assert _has_plane_near(result["mirror_planes"], [0, 1, 0]), \
            "Missing xz-plane (normal ∥ y)"

    def test_mirror_plane_yz(self, result):
        assert _has_plane_near(result["mirror_planes"], [1, 0, 0]), \
            "Missing yz-plane (normal ∥ x)"

    def test_three_rotation_axes(self, result):
        axes = result["rotation_axes"]
        assert len(axes) >= 3, f"Expected ≥ 3 rotation axes, got {len(axes)}"

    def test_rotation_axes_order_2(self, result):
        orders = [order for (_, _, order) in result["rotation_axes"]]
        assert all(o == 2 for o in orders), \
            f"Box axes should all be order 2, got orders: {orders}"

    def test_rotation_axis_x(self, result):
        assert _has_axis_near(result["rotation_axes"], [1, 0, 0]), \
            "Missing C2 axis along x"

    def test_rotation_axis_y(self, result):
        assert _has_axis_near(result["rotation_axes"], [0, 1, 0]), \
            "Missing C2 axis along y"

    def test_rotation_axis_z(self, result):
        assert _has_axis_near(result["rotation_axes"], [0, 0, 1]), \
            "Missing C2 axis along z"


# ---------------------------------------------------------------------------
# Cylinder
# ---------------------------------------------------------------------------

class TestCylinderSymmetry:
    """A cylinder is axisymmetric — any rotation about its axis is a symmetry."""

    @pytest.fixture(scope="class")
    def result(self):
        body = make_cylinder(center=(0, 0, 0), axis=(0, 0, 1), radius=1.0, height=2.0)
        return detect_symmetry(body, tol=1e-3, n_quad=8)

    def test_not_spherical(self, result):
        assert result["spherical"] is False

    def test_axisymmetric(self, result):
        assert result["axisymmetric"] is True, \
            "Cylinder should be detected as axisymmetric"

    def test_high_order_or_axisymmetric_axis(self, result):
        """rotation_axes should contain an entry with order ≥ 36 or axisymmetric."""
        high_order_axes = [
            (p, ax, o) for (p, ax, o) in result["rotation_axes"] if o >= 36
        ]
        assert len(high_order_axes) >= 1 or result["axisymmetric"], \
            "No high-order axis detected for cylinder"

    def test_rotation_axis_direction(self, result):
        """The cylinder's z-axis should appear in rotation_axes."""
        assert _has_axis_near(result["rotation_axes"], [0, 0, 1]), \
            "Cylinder z-axis should appear in rotation_axes"


# ---------------------------------------------------------------------------
# Sphere
# ---------------------------------------------------------------------------

class TestSphereSymmetry:
    """A sphere is spherically symmetric."""

    @pytest.fixture(scope="class")
    def result(self):
        body = make_sphere(center=(0, 0, 0), radius=1.0)
        return detect_symmetry(body, tol=1e-4)

    def test_spherical(self, result):
        assert result["spherical"] is True, "Sphere must be flagged spherical"

    def test_axisymmetric(self, result):
        assert result["axisymmetric"] is True, "Sphere is also axisymmetric"
