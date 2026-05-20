"""Tests for geom/mass_props.py — Body volume + centroid via divergence theorem.

Oracles
-------
- Sphere:    V = 4/3 π r³,   centroid = center,  tol ≤ 1e-6 (relative for V)
- Box:       V = lx·ly·lz,   centroid = origin + size/2
- Cylinder:  V = π r² h,     centroid = center + h/2 * axis
- Tetra:     V = |det[b-a,c-a,d-a]| / 6, centroid = mean of vertices
"""

import math
import numpy as np
import pytest

from kerf_cad_core.geom.brep import (
    make_box,
    make_sphere,
    make_cylinder,
    make_tetra,
)
from kerf_cad_core.geom.mass_props import body_mass_props


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rel_err(got, expected):
    """Relative error |got - expected| / |expected|."""
    return abs(got - expected) / max(abs(expected), 1e-30)


# ---------------------------------------------------------------------------
# Sphere
# ---------------------------------------------------------------------------

class TestSphereVolume:
    def test_unit_sphere_volume(self):
        body = make_sphere(center=(0, 0, 0), radius=1.0)
        props = body_mass_props(body)
        expected = 4.0 / 3.0 * math.pi
        assert _rel_err(props["volume"], expected) < 1e-6, (
            f"sphere volume {props['volume']:.10f} != {expected:.10f}"
        )

    def test_unit_sphere_centroid_at_origin(self):
        body = make_sphere(center=(0, 0, 0), radius=1.0)
        props = body_mass_props(body)
        c = props["centroid"]
        assert np.allclose(c, [0, 0, 0], atol=1e-6), (
            f"unit sphere centroid {c} should be [0,0,0]"
        )

    def test_sphere_radius_2(self):
        r = 2.0
        body = make_sphere(center=(0, 0, 0), radius=r)
        props = body_mass_props(body)
        expected = 4.0 / 3.0 * math.pi * r**3
        assert _rel_err(props["volume"], expected) < 1e-6, (
            f"r=2 sphere volume relative error too large"
        )

    def test_sphere_offset_center_volume(self):
        r = 1.5
        cx, cy, cz = 3.0, -2.0, 1.0
        body = make_sphere(center=(cx, cy, cz), radius=r)
        props = body_mass_props(body)
        expected_V = 4.0 / 3.0 * math.pi * r**3
        assert _rel_err(props["volume"], expected_V) < 1e-6
        c = props["centroid"]
        assert np.allclose(c, [cx, cy, cz], atol=1e-5), (
            f"offset sphere centroid {c} != [{cx},{cy},{cz}]"
        )

    def test_sphere_various_radii(self):
        for r in (0.5, 1.0, 3.0, 10.0):
            body = make_sphere(center=(0, 0, 0), radius=r)
            props = body_mass_props(body)
            expected = 4.0 / 3.0 * math.pi * r**3
            assert _rel_err(props["volume"], expected) < 1e-6, (
                f"sphere r={r} volume relative error > 1e-6"
            )


# ---------------------------------------------------------------------------
# Box
# ---------------------------------------------------------------------------

class TestBoxVolume:
    def test_unit_box_volume(self):
        body = make_box(origin=(0, 0, 0), size=(1, 1, 1))
        props = body_mass_props(body)
        assert abs(props["volume"] - 1.0) < 1e-10, (
            f"unit box volume {props['volume']} != 1.0"
        )

    def test_unit_box_centroid(self):
        body = make_box(origin=(0, 0, 0), size=(1, 1, 1))
        props = body_mass_props(body)
        assert np.allclose(props["centroid"], [0.5, 0.5, 0.5], atol=1e-10), (
            f"unit box centroid {props['centroid']} != [0.5,0.5,0.5]"
        )

    def test_box_arbitrary_size(self):
        lx, ly, lz = 2.0, 3.0, 5.0
        body = make_box(origin=(0, 0, 0), size=(lx, ly, lz))
        props = body_mass_props(body)
        expected = lx * ly * lz
        assert abs(props["volume"] - expected) < 1e-8, (
            f"box {lx}x{ly}x{lz} volume {props['volume']} != {expected}"
        )
        assert np.allclose(
            props["centroid"], [lx / 2, ly / 2, lz / 2], atol=1e-10
        )

    def test_box_offset_origin(self):
        ox, oy, oz = 1.0, 2.0, 3.0
        lx, ly, lz = 1.0, 1.0, 1.0
        body = make_box(origin=(ox, oy, oz), size=(lx, ly, lz))
        props = body_mass_props(body)
        assert abs(props["volume"] - 1.0) < 1e-10
        expected_c = np.array([ox + lx/2, oy + ly/2, oz + lz/2])
        assert np.allclose(props["centroid"], expected_c, atol=1e-10), (
            f"offset box centroid {props['centroid']} != {expected_c}"
        )

    def test_box_volume_positive(self):
        """Volume should be positive for outward-facing normals."""
        body = make_box(origin=(0, 0, 0), size=(2, 2, 2))
        props = body_mass_props(body)
        assert props["volume"] > 0, "box volume must be positive"


# ---------------------------------------------------------------------------
# Cylinder
# ---------------------------------------------------------------------------

class TestCylinderVolume:
    def test_unit_cylinder_volume(self):
        body = make_cylinder(center=(0, 0, 0), axis=(0, 0, 1), radius=1.0, height=1.0)
        props = body_mass_props(body)
        expected = math.pi * 1.0**2 * 1.0
        assert _rel_err(props["volume"], expected) < 1e-4, (
            f"unit cylinder volume {props['volume']:.8f} != {expected:.8f}"
        )

    def test_unit_cylinder_centroid(self):
        body = make_cylinder(center=(0, 0, 0), axis=(0, 0, 1), radius=1.0, height=1.0)
        props = body_mass_props(body)
        expected_c = np.array([0.0, 0.0, 0.5])
        assert np.allclose(props["centroid"], expected_c, atol=1e-4), (
            f"unit cylinder centroid {props['centroid']} != {expected_c}"
        )

    def test_cylinder_r2_h3(self):
        r, h = 2.0, 3.0
        body = make_cylinder(center=(0, 0, 0), axis=(0, 0, 1), radius=r, height=h)
        props = body_mass_props(body)
        expected = math.pi * r**2 * h
        assert _rel_err(props["volume"], expected) < 1e-4, (
            f"cylinder r={r} h={h} volume relative error > 1e-4"
        )

    def test_cylinder_offset_center(self):
        cx, cy, cz = 1.0, 2.0, 0.0
        r, h = 1.0, 2.0
        body = make_cylinder(
            center=(cx, cy, cz), axis=(0, 0, 1), radius=r, height=h
        )
        props = body_mass_props(body)
        expected_V = math.pi * r**2 * h
        assert _rel_err(props["volume"], expected_V) < 1e-4
        expected_c = np.array([cx, cy, cz + h / 2])
        assert np.allclose(props["centroid"], expected_c, atol=1e-4), (
            f"offset cylinder centroid {props['centroid']} != {expected_c}"
        )

    def test_cylinder_volume_positive(self):
        body = make_cylinder(center=(0, 0, 0), axis=(0, 0, 1), radius=1.0, height=2.0)
        props = body_mass_props(body)
        assert props["volume"] > 0


# ---------------------------------------------------------------------------
# Tetrahedron
# ---------------------------------------------------------------------------

class TestTetraVolume:
    def _tet_volume(self, p0, p1, p2, p3):
        a = np.asarray(p1) - np.asarray(p0)
        b = np.asarray(p2) - np.asarray(p0)
        c = np.asarray(p3) - np.asarray(p0)
        return abs(float(np.dot(a, np.cross(b, c)))) / 6.0

    def test_unit_tetra_volume(self):
        p0 = (0, 0, 0)
        p1 = (1, 0, 0)
        p2 = (0, 1, 0)
        p3 = (0, 0, 1)
        body = make_tetra(p0, p1, p2, p3)
        props = body_mass_props(body)
        expected = self._tet_volume(p0, p1, p2, p3)  # = 1/6
        assert abs(props["volume"] - expected) < 1e-10, (
            f"tetra volume {props['volume']} != {expected}"
        )

    def test_tetra_centroid(self):
        p0 = np.array([0.0, 0.0, 0.0])
        p1 = np.array([1.0, 0.0, 0.0])
        p2 = np.array([0.0, 1.0, 0.0])
        p3 = np.array([0.0, 0.0, 1.0])
        body = make_tetra(p0, p1, p2, p3)
        props = body_mass_props(body)
        expected_c = (p0 + p1 + p2 + p3) / 4.0
        assert np.allclose(props["centroid"], expected_c, atol=1e-10), (
            f"tetra centroid {props['centroid']} != {expected_c}"
        )

    def test_tetra_volume_positive(self):
        body = make_tetra((0,0,0), (1,0,0), (0,1,0), (0,0,1))
        props = body_mass_props(body)
        assert props["volume"] > 0


# ---------------------------------------------------------------------------
# Return-type contract
# ---------------------------------------------------------------------------

class TestReturnContract:
    def test_returns_dict_with_volume_and_centroid(self):
        body = make_box(origin=(0, 0, 0), size=(1, 1, 1))
        props = body_mass_props(body)
        assert "volume" in props
        assert "centroid" in props
        assert isinstance(props["volume"], float)
        assert isinstance(props["centroid"], np.ndarray)
        assert props["centroid"].shape == (3,)

    def test_centroid_is_numpy_array(self):
        body = make_sphere(center=(1, 2, 3), radius=0.5)
        props = body_mass_props(body)
        assert props["centroid"].dtype == np.float64 or np.issubdtype(
            props["centroid"].dtype, np.floating
        )
