"""
test_envelope.py
================

Hermetic tests for kerf_bim.envelope — Wall, Slab, Roof parametric primitives.

All numeric oracles are derived from closed-form geometry; tolerances are
tight (1e-12 absolute) unless otherwise noted.

Oracle sources
--------------
- Wall volume     = length × height × thickness
- Slab volume     = boundary_area × thickness  (shoelace + extrusion)
- Gable ridge len = footprint span along ridge direction
- Hip ridge len   = along_span − perp_span (both hips combined reduction)
- Gable ridge height = slope × (perp_span / 2)
- Shed ridge height  = slope × perp_span
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
import pathlib

import pytest

# ---------------------------------------------------------------------------
# Direct import (no pip-install needed)
# ---------------------------------------------------------------------------

_PKG = pathlib.Path(__file__).parent.parent / "src" / "kerf_bim"


def _load(name: str):
    path = _PKG / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"kerf_bim.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"kerf_bim.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_env = _load("envelope")

Wall         = _env.Wall
WallLayer    = _env.WallLayer
Slab         = _env.Slab
Roof         = _env.Roof
SectionProfile = _env.SectionProfile
ROOF_FLAT    = _env.ROOF_FLAT
ROOF_SHED    = _env.ROOF_SHED
ROOF_GABLE   = _env.ROOF_GABLE
ROOF_HIP     = _env.ROOF_HIP


# ===========================================================================
# Helpers
# ===========================================================================

def _simple_wall(length: float = 5.0, height: float = 3.0,
                 thickness: float = 0.2) -> Wall:
    """Axis-aligned wall from (0,0) to (length,0)."""
    return Wall(start=(0.0, 0.0), end=(length, 0.0),
                height=height, thickness=thickness)


def _layered_wall(length: float = 6.0, height: float = 2.8) -> Wall:
    """Compound wall: 200 mm structural + 100 mm insulation + 12.5 mm drywall."""
    layers = [
        WallLayer("concrete_reinforced", 0.200, "structure"),
        WallLayer("insulation_rockwool", 0.100, "insulation"),
        WallLayer("board_drywall_gypsum", 0.0125, "finish"),
    ]
    return Wall(start=(0.0, 0.0), end=(length, 0.0),
                height=height, thickness=0.3125, layers=layers)


def _rect_slab(w: float = 10.0, h: float = 8.0, t: float = 0.2) -> Slab:
    """Axis-aligned rectangular slab."""
    return Slab(boundary_loop=[(0, 0), (w, 0), (w, h), (0, h)], thickness=t)


def _rect_footprint(w: float = 12.0, d: float = 8.0):
    return [(0, 0), (w, 0), (w, d), (0, d)]


# ===========================================================================
# WallLayer tests
# ===========================================================================

class TestWallLayer:
    def test_basic_creation(self):
        la = WallLayer("concrete_reinforced", 0.2)
        assert la.material == "concrete_reinforced"
        assert la.thickness == 0.2
        assert la.function == "structure"

    def test_custom_function(self):
        la = WallLayer("insulation_rockwool", 0.1, "insulation")
        assert la.function == "insulation"

    def test_zero_thickness_raises(self):
        with pytest.raises(ValueError):
            WallLayer("concrete_reinforced", 0.0)

    def test_negative_thickness_raises(self):
        with pytest.raises(ValueError):
            WallLayer("concrete_reinforced", -0.05)

    def test_invalid_function_raises(self):
        with pytest.raises(ValueError):
            WallLayer("concrete_reinforced", 0.1, "bad_function")

    def test_all_valid_functions(self):
        for fn in ("structure", "substrate", "insulation", "finish", "membrane"):
            la = WallLayer("concrete_reinforced", 0.1, fn)
            assert la.function == fn


# ===========================================================================
# Wall tests
# ===========================================================================

class TestWallLength:
    """Oracle: wall length == Euclidean distance between start and end."""

    def test_axis_aligned_length(self):
        w = _simple_wall(length=5.0)
        assert abs(w.length() - 5.0) < 1e-12

    def test_diagonal_wall_length(self):
        """3-4-5 triangle wall."""
        w = Wall(start=(0.0, 0.0), end=(3.0, 4.0), height=3.0, thickness=0.2)
        assert abs(w.length() - 5.0) < 1e-12

    def test_unit_wall_length(self):
        w = Wall(start=(1.0, 1.0), end=(2.0, 1.0), height=3.0, thickness=0.2)
        assert abs(w.length() - 1.0) < 1e-12

    def test_length_non_zero(self):
        w = _simple_wall(length=7.5)
        assert w.length() > 0.0

    def test_length_independent_of_height(self):
        w1 = _simple_wall(length=4.0, height=2.5)
        w2 = _simple_wall(length=4.0, height=5.0)
        assert abs(w1.length() - w2.length()) < 1e-12


class TestWallVolume:
    def test_gross_volume(self):
        """Gross volume = length × height × thickness."""
        w = _simple_wall(length=5.0, height=3.0, thickness=0.2)
        expected = 5.0 * 3.0 * 0.2
        assert abs(w.gross_volume() - expected) < 1e-12

    def test_net_volume_no_openings(self):
        """Net volume equals gross volume when there are no openings."""
        w = _simple_wall(length=5.0, height=3.0, thickness=0.2)
        assert abs(w.net_volume() - w.gross_volume()) < 1e-12

    def test_face_area(self):
        w = _simple_wall(length=5.0, height=3.0)
        assert abs(w.face_area() - 15.0) < 1e-12

    def test_opening_volume_zero_initially(self):
        w = _simple_wall()
        assert w.opening_volume() == 0.0


class TestWallLayers:
    def test_layered_thickness_sum(self):
        """Total thickness equals the sum of layer thicknesses."""
        w = _layered_wall()
        expected = 0.200 + 0.100 + 0.0125
        assert abs(w.thickness - expected) < 1e-12

    def test_layer_count(self):
        w = _layered_wall()
        assert len(w.layers) == 3

    def test_layer_materials(self):
        w = _layered_wall()
        assert w.layers[0].material == "concrete_reinforced"
        assert w.layers[1].material == "insulation_rockwool"
        assert w.layers[2].material == "board_drywall_gypsum"

    def test_layer_functions(self):
        w = _layered_wall()
        assert w.layers[0].function == "structure"
        assert w.layers[1].function == "insulation"
        assert w.layers[2].function == "finish"

    def test_layer_section_profiles_count(self):
        w = _layered_wall()
        profiles = w.layer_section_profiles()
        assert len(profiles) == 3

    def test_layer_section_u_spans(self):
        """Each layer profile spans a contiguous u interval."""
        w = _layered_wall()
        profiles = w.layer_section_profiles()
        thicknesses = [la.thickness for la in w.layers]
        u = 0.0
        for i, prof in enumerate(profiles):
            xs = [v[0] for v in prof.vertices]
            assert abs(min(xs) - u) < 1e-12
            u += thicknesses[i]
            assert abs(max(xs) - u) < 1e-12

    def test_auto_single_layer_no_layers_given(self):
        """Wall with no layers argument gets one auto structural layer."""
        w = Wall(start=(0, 0), end=(4, 0), height=3, thickness=0.2)
        assert len(w.layers) == 1
        assert w.layers[0].function == "structure"

    def test_auto_layer_thickness_matches(self):
        w = Wall(start=(0, 0), end=(4, 0), height=3, thickness=0.25)
        assert abs(w.layers[0].thickness - 0.25) < 1e-12


class TestWallSectionProfile:
    def test_section_profile_is_rectangle(self):
        w = _simple_wall(height=3.0, thickness=0.2)
        prof = w.section_profile()
        xs = [v[0] for v in prof.vertices]
        zs = [v[1] for v in prof.vertices]
        assert abs(max(xs) - 0.2) < 1e-12
        assert abs(max(zs) - 3.0) < 1e-12
        assert abs(min(xs)) < 1e-12
        assert abs(min(zs)) < 1e-12

    def test_section_profile_area(self):
        w = _simple_wall(height=3.0, thickness=0.2)
        prof = w.section_profile()
        assert abs(prof.area() - 3.0 * 0.2) < 1e-12


class TestWallValidation:
    def test_zero_height_raises(self):
        with pytest.raises(ValueError):
            Wall(start=(0, 0), end=(5, 0), height=0.0, thickness=0.2)

    def test_negative_height_raises(self):
        with pytest.raises(ValueError):
            Wall(start=(0, 0), end=(5, 0), height=-1.0, thickness=0.2)

    def test_zero_thickness_raises(self):
        with pytest.raises(ValueError):
            Wall(start=(0, 0), end=(5, 0), height=3.0, thickness=0.0)

    def test_same_start_end_raises(self):
        with pytest.raises(ValueError):
            Wall(start=(1, 1), end=(1, 1), height=3.0, thickness=0.2)


# ===========================================================================
# Slab tests
# ===========================================================================

class TestSlabVolume:
    """Oracle: slab volume = boundary_area × thickness (regardless of slope)."""

    def test_rectangular_slab_volume(self):
        """10 × 8 m slab with 200 mm thickness."""
        s = _rect_slab(w=10.0, h=8.0, t=0.2)
        expected = 10.0 * 8.0 * 0.2
        assert abs(s.volume() - expected) < 1e-12

    def test_plan_area_shoelace(self):
        """Plan area matches shoelace formula for rectangle."""
        s = _rect_slab(w=6.0, h=4.0)
        assert abs(s.plan_area() - 24.0) < 1e-12

    def test_triangular_slab_volume(self):
        """Right-triangle slab: area = 0.5 × base × height."""
        s = Slab(boundary_loop=[(0, 0), (3, 0), (0, 4)], thickness=0.15)
        expected = 0.5 * 3.0 * 4.0 * 0.15  # 0.9 m³
        assert abs(s.volume() - expected) < 1e-12

    def test_sloped_slab_same_volume(self):
        """Sloped slab has the same volume as level slab."""
        level  = _rect_slab(w=10.0, h=8.0, t=0.25)
        sloped = Slab(boundary_loop=[(0, 0), (10, 0), (10, 8), (0, 8)],
                      thickness=0.25, slope=0.05)
        assert abs(sloped.volume() - level.volume()) < 1e-12

    def test_volume_scales_with_thickness(self):
        """Doubling thickness doubles volume."""
        s1 = _rect_slab(t=0.2)
        s2 = _rect_slab(t=0.4)
        assert abs(s2.volume() - 2.0 * s1.volume()) < 1e-12

    def test_volume_scales_with_area(self):
        """Doubling both dimensions quadruples volume."""
        s1 = _rect_slab(w=5.0, h=4.0, t=0.2)
        s2 = _rect_slab(w=10.0, h=8.0, t=0.2)
        assert abs(s2.volume() - 4.0 * s1.volume()) < 1e-12


class TestSlabSlope:
    def test_flat_elevation_constant(self):
        s = _rect_slab()
        z0 = s.elevation_at(0.0)
        z1 = s.elevation_at(10.0)
        assert abs(z1 - z0) < 1e-12

    def test_sloped_elevation_at_x(self):
        """z(x) = base_elevation + slope * x."""
        s = Slab(boundary_loop=[(0, 0), (10, 0), (10, 8), (0, 8)],
                 thickness=0.2, slope=0.1, base_elevation=1.0)
        assert abs(s.elevation_at(0.0) - 1.0) < 1e-12
        assert abs(s.elevation_at(10.0) - 2.0) < 1e-12
        assert abs(s.elevation_at(5.0) - 1.5) < 1e-12


class TestSlabValidation:
    def test_too_few_points_raises(self):
        with pytest.raises(ValueError):
            Slab(boundary_loop=[(0, 0), (1, 0)], thickness=0.2)

    def test_zero_thickness_raises(self):
        with pytest.raises(ValueError):
            Slab(boundary_loop=[(0, 0), (1, 0), (1, 1)], thickness=0.0)

    def test_negative_thickness_raises(self):
        with pytest.raises(ValueError):
            Slab(boundary_loop=[(0, 0), (1, 0), (1, 1)], thickness=-0.1)


class TestSlabSection:
    def test_section_profile_has_4_verts(self):
        s = _rect_slab(t=0.25)
        prof = s.section_profile()
        assert len(prof.vertices) == 4


# ===========================================================================
# Roof tests
# ===========================================================================

class TestRoofGable:
    """Gable roof on a 12 × 8 m rectangular footprint, ridge_direction='x'."""

    def _gable(self, slope=0.5):
        return Roof(footprint=_rect_footprint(12, 8),
                    slope=slope, ridge_direction="x", roof_type=ROOF_GABLE)

    def test_ridge_length_equals_footprint_along_span(self):
        """For a gable roof the ridge length == footprint span along X."""
        r = self._gable()
        assert abs(r.ridge_length() - 12.0) < 1e-12

    def test_ridge_height(self):
        """ridge_height = slope × (perp_span / 2) = 0.5 × 4 = 2.0."""
        r = self._gable(slope=0.5)
        assert abs(r.ridge_height() - 2.0) < 1e-12

    def test_ridge_height_steeper(self):
        r = self._gable(slope=1.0)
        assert abs(r.ridge_height() - 4.0) < 1e-12

    def test_section_profile_triangle(self):
        """Gable section profile is a triangle with 3 vertices."""
        r = self._gable()
        prof = r.section_profile()
        assert len(prof.vertices) == 3

    def test_footprint_area(self):
        r = self._gable()
        assert abs(r.footprint_area() - 96.0) < 1e-12

    def test_ridge_direction_y(self):
        """With ridge_direction='y', ridge length = footprint Y span."""
        r = Roof(footprint=_rect_footprint(12, 8),
                 slope=0.5, ridge_direction="y", roof_type=ROOF_GABLE)
        assert abs(r.ridge_length() - 8.0) < 1e-12


class TestRoofHip:
    """Hip roof on a 12 × 8 m footprint."""

    def _hip(self, slope=0.5):
        return Roof(footprint=_rect_footprint(12, 8),
                    slope=slope, ridge_direction="x", roof_type=ROOF_HIP)

    def test_ridge_length_hip(self):
        """Hip ridge = along (12) − 2 × hip_offset (4) = 4 m.
        hip_offset = perp_span / 2 = 8 / 2 = 4."""
        r = self._hip()
        assert abs(r.ridge_length() - 4.0) < 1e-12

    def test_hip_ridge_shorter_than_gable(self):
        gable = Roof(footprint=_rect_footprint(12, 8),
                     slope=0.5, ridge_direction="x", roof_type=ROOF_GABLE)
        hip = self._hip()
        assert hip.ridge_length() < gable.ridge_length()

    def test_square_hip_ridge_zero(self):
        """Square 8×8 hip roof: ridge = 8 − 2×4 = 0."""
        r = Roof(footprint=_rect_footprint(8, 8),
                 slope=0.5, ridge_direction="x", roof_type=ROOF_HIP)
        assert abs(r.ridge_length()) < 1e-12


class TestRoofShed:
    def _shed(self):
        return Roof(footprint=_rect_footprint(12, 8),
                    slope=0.25, ridge_direction="x", roof_type=ROOF_SHED)

    def test_shed_ridge_length(self):
        """Shed ridge = full along span = 12."""
        r = self._shed()
        assert abs(r.ridge_length() - 12.0) < 1e-12

    def test_shed_height(self):
        """Shed ridge height = slope × perp_span = 0.25 × 8 = 2."""
        r = self._shed()
        assert abs(r.ridge_height() - 2.0) < 1e-12

    def test_shed_section_has_3_verts(self):
        r = self._shed()
        prof = r.section_profile()
        assert len(prof.vertices) == 3


class TestRoofFlat:
    def test_flat_ridge_length_zero(self):
        r = Roof(footprint=_rect_footprint(10, 10),
                 slope=0.0, roof_type=ROOF_FLAT)
        assert r.ridge_length() == 0.0

    def test_flat_ridge_height_zero(self):
        r = Roof(footprint=_rect_footprint(10, 10),
                 slope=0.0, roof_type=ROOF_FLAT)
        assert r.ridge_height() == 0.0

    def test_flat_volume_zero(self):
        r = Roof(footprint=_rect_footprint(10, 10),
                 slope=0.0, roof_type=ROOF_FLAT)
        assert r.volume() == 0.0

    def test_flat_section_2_verts(self):
        r = Roof(footprint=_rect_footprint(10, 10),
                 slope=0.0, roof_type=ROOF_FLAT)
        prof = r.section_profile()
        assert len(prof.vertices) == 2


class TestRoofValidation:
    def test_negative_slope_raises(self):
        with pytest.raises(ValueError):
            Roof(footprint=_rect_footprint(), slope=-0.1)

    def test_invalid_roof_type_raises(self):
        with pytest.raises(ValueError):
            Roof(footprint=_rect_footprint(), slope=0.5, roof_type="mansard")

    def test_invalid_ridge_direction_raises(self):
        with pytest.raises(ValueError):
            Roof(footprint=_rect_footprint(), slope=0.5, ridge_direction="z")

    def test_too_few_footprint_points_raises(self):
        with pytest.raises(ValueError):
            Roof(footprint=[(0, 0), (1, 0)], slope=0.5)


class TestRoofVolume:
    def test_gable_volume_positive(self):
        r = Roof(footprint=_rect_footprint(12, 8),
                 slope=0.5, roof_type=ROOF_GABLE)
        assert r.volume() > 0.0

    def test_gable_volume_formula(self):
        """Gable volume = 0.5 × perp × ridge_height × along.
        12×8, slope=0.5: ridge_height=2, volume=0.5×8×2×12=96."""
        r = Roof(footprint=_rect_footprint(12, 8),
                 slope=0.5, ridge_direction="x", roof_type=ROOF_GABLE)
        expected = 0.5 * 8.0 * 2.0 * 12.0  # 96 m³
        assert abs(r.volume() - expected) < 1e-12

    def test_flat_zero_volume(self):
        r = Roof(footprint=_rect_footprint(12, 8),
                 slope=0.0, roof_type=ROOF_FLAT)
        assert r.volume() == 0.0
