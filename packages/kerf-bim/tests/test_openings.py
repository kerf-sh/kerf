"""
test_openings.py
================

Hermetic tests for kerf_bim.openings — Door and Window parametric primitives.

Oracles
-------
- Door cut volume  = door_width × door_height × wall_thickness
- Window cut volume = window_width × window_height × wall_thickness
- Net wall volume after door = gross_wall_volume − door_cut_volume
- Net wall volume after window = gross_wall_volume − window_cut_volume
- Glazing area = (window_width − 2·frame) × (window_height − 2·frame)
"""

from __future__ import annotations

import importlib.util
import math
import pathlib
import sys

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
_opn = _load("openings")

Wall         = _env.Wall
WallLayer    = _env.WallLayer
Door         = _opn.Door
Window       = _opn.Window
JambProfile  = _opn.JambProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wall(length: float = 5.0, height: float = 3.0,
          thickness: float = 0.2) -> Wall:
    return Wall(start=(0.0, 0.0), end=(length, 0.0),
                height=height, thickness=thickness)


# ===========================================================================
# JambProfile tests
# ===========================================================================

class TestJambProfile:
    def test_section_area(self):
        jp = JambProfile(width=0.05, depth=0.2)
        assert abs(jp.section_area() - 0.05 * 0.2) < 1e-12

    def test_as_section_profile_4_verts(self):
        jp = JambProfile(width=0.05, depth=0.2)
        prof = jp.as_section_profile()
        assert len(prof.vertices) == 4

    def test_zero_width_raises(self):
        with pytest.raises(ValueError):
            JambProfile(width=0.0, depth=0.2)

    def test_zero_depth_raises(self):
        with pytest.raises(ValueError):
            JambProfile(width=0.05, depth=0.0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            JambProfile(width=-0.05, depth=0.2)


# ===========================================================================
# Door tests
# ===========================================================================

class TestDoorCutVolume:
    """Oracle: door cut volume = width × height × wall_thickness."""

    def _door(self, wall=None, pos=2.5, width=0.9, height=2.1) -> Door:
        if wall is None:
            wall = _wall()
        return Door(host_wall=wall, position_along=pos,
                    width=width, height=height)

    def test_cut_volume(self):
        w = _wall(length=5.0, thickness=0.2)
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1)
        expected = 0.9 * 2.1 * 0.2
        assert abs(d.cut_volume() - expected) < 1e-12

    def test_cut_volume_thick_wall(self):
        w = _wall(length=5.0, thickness=0.4)
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1)
        expected = 0.9 * 2.1 * 0.4
        assert abs(d.cut_volume() - expected) < 1e-12

    def test_cut_volume_narrow_door(self):
        w = _wall(length=5.0, thickness=0.3)
        d = Door(host_wall=w, position_along=2.5, width=0.8, height=2.0)
        expected = 0.8 * 2.0 * 0.3
        assert abs(d.cut_volume() - expected) < 1e-12

    def test_wall_net_volume_after_door(self):
        """Net wall volume = gross - door_cut_volume."""
        w = _wall(length=5.0, height=3.0, thickness=0.2)
        gross = w.gross_volume()
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1)
        cut = 0.9 * 2.1 * 0.2
        assert abs(w.net_volume() - (gross - cut)) < 1e-12

    def test_door_registers_with_host(self):
        w = _wall()
        assert len(w.openings) == 0
        Door(host_wall=w, position_along=2.5, width=0.9, height=2.1)
        assert len(w.openings) == 1

    def test_two_doors_register(self):
        w = _wall(length=10.0)
        Door(host_wall=w, position_along=2.0, width=0.9, height=2.1)
        Door(host_wall=w, position_along=7.0, width=0.9, height=2.1)
        assert len(w.openings) == 2

    def test_two_doors_cumulative_cut(self):
        w = _wall(length=10.0, height=3.0, thickness=0.2)
        gross = w.gross_volume()
        Door(host_wall=w, position_along=2.0, width=0.9, height=2.1)
        Door(host_wall=w, position_along=7.0, width=0.9, height=2.1)
        expected_cut = 2 * (0.9 * 2.1 * 0.2)
        assert abs(w.net_volume() - (gross - expected_cut)) < 1e-12


class TestDoorGeometry:
    def test_section_profile_4_verts(self):
        w = _wall()
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1)
        prof = d.section_profile()
        assert len(prof.vertices) == 4

    def test_section_profile_spans_wall_thickness(self):
        w = _wall(thickness=0.25)
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1)
        prof = d.section_profile()
        us = [v[0] for v in prof.vertices]
        assert abs(max(us) - 0.25) < 1e-12

    def test_section_profile_height(self):
        w = _wall()
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1)
        prof = d.section_profile()
        zs = [v[1] for v in prof.vertices]
        assert abs(max(zs) - 2.1) < 1e-12

    def test_swing_geometry_returns_points(self):
        w = _wall()
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1)
        pts = d.swing_geometry()
        assert len(pts) > 2

    def test_swing_geometry_90_deg(self):
        """Final arc point is at 90° from start → x == hinge_x, y == radius."""
        w = _wall()
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1,
                 swing_angle=90.0)
        pts = d.swing_geometry()
        last = pts[-1]
        # At 90° from hinge: x stays at hinge_x + r*cos(90°)=hinge_x,
        # y = hinge_y + r*sin(90°) = radius
        hinge_x = 2.5 - 0.9 / 2.0
        assert abs(last[0] - hinge_x) < 1e-6
        assert abs(last[1] - 0.9) < 1e-6

    def test_jamb_profile_depth_equals_thickness(self):
        w = _wall(thickness=0.2)
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1)
        jp = d.jamb_profile()
        assert abs(jp.depth - 0.2) < 1e-12

    def test_family_stored(self):
        w = _wall()
        d = Door(host_wall=w, position_along=2.5, width=0.9, height=2.1,
                 family="double_panel")
        assert d.family == "double_panel"


class TestDoorValidation:
    def test_zero_width_raises(self):
        w = _wall()
        with pytest.raises(ValueError):
            Door(host_wall=w, position_along=2.5, width=0.0, height=2.1)

    def test_zero_height_raises(self):
        w = _wall()
        with pytest.raises(ValueError):
            Door(host_wall=w, position_along=2.5, width=0.9, height=0.0)

    def test_door_at_wall_end_raises(self):
        w = _wall(length=5.0)
        with pytest.raises(ValueError):
            Door(host_wall=w, position_along=5.0, width=0.9, height=2.1)

    def test_door_at_wall_start_raises(self):
        w = _wall(length=5.0)
        with pytest.raises(ValueError):
            Door(host_wall=w, position_along=0.0, width=0.9, height=2.1)

    def test_door_extends_beyond_wall_raises(self):
        w = _wall(length=5.0)
        with pytest.raises(ValueError):
            Door(host_wall=w, position_along=4.9, width=0.9, height=2.1)

    def test_door_taller_than_wall_raises(self):
        w = _wall(height=2.0)
        with pytest.raises(ValueError):
            Door(host_wall=w, position_along=2.5, width=0.9, height=2.5)


# ===========================================================================
# Window tests
# ===========================================================================

class TestWindowCutVolume:
    """Oracle: window cut volume = width × height × wall_thickness."""

    def test_cut_volume(self):
        w = _wall(length=5.0, thickness=0.2)
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                     sill_height=0.9)
        expected = 1.2 * 1.2 * 0.2
        assert abs(win.cut_volume() - expected) < 1e-12

    def test_cut_volume_thick_wall(self):
        w = _wall(length=5.0, thickness=0.35)
        win = Window(host_wall=w, position_along=2.5, width=1.0, height=1.0,
                     sill_height=0.9)
        expected = 1.0 * 1.0 * 0.35
        assert abs(win.cut_volume() - expected) < 1e-12

    def test_net_wall_volume_after_window(self):
        w = _wall(length=5.0, height=3.0, thickness=0.2)
        gross = w.gross_volume()
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                     sill_height=0.9)
        cut = 1.2 * 1.2 * 0.2
        assert abs(w.net_volume() - (gross - cut)) < 1e-12

    def test_window_registers_with_host(self):
        w = _wall()
        Window(host_wall=w, position_along=2.5, width=1.2, height=1.2)
        assert len(w.openings) == 1

    def test_mixed_openings_cumulative(self):
        """Wall with one door and one window."""
        w = _wall(length=8.0, height=3.0, thickness=0.2)
        gross = w.gross_volume()
        Door(host_wall=w, position_along=1.5, width=0.9, height=2.1)
        Window(host_wall=w, position_along=5.0, width=1.2, height=1.2,
               sill_height=0.9)
        door_cut   = 0.9 * 2.1 * 0.2
        window_cut = 1.2 * 1.2 * 0.2
        assert abs(w.net_volume() - (gross - door_cut - window_cut)) < 1e-12


class TestWindowGeometry:
    def test_head_height(self):
        w = _wall(height=3.0)
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                     sill_height=0.9)
        assert abs(win.head_height() - (0.9 + 1.2)) < 1e-12

    def test_glazing_area(self):
        """Glazing = (width − 2×frame) × (height − 2×frame)."""
        w = _wall()
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                     sill_height=0.9, frame_thickness=0.06)
        expected = (1.2 - 2 * 0.06) * (1.2 - 2 * 0.06)
        assert abs(win.glazing_area() - expected) < 1e-12

    def test_glazing_area_less_than_opening(self):
        w = _wall()
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2)
        assert win.glazing_area() < win.width * win.height

    def test_section_profile_4_verts(self):
        w = _wall()
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                     sill_height=0.9)
        prof = win.section_profile()
        assert len(prof.vertices) == 4

    def test_section_profile_z_range(self):
        w = _wall()
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                     sill_height=0.9)
        prof = win.section_profile()
        zs = [v[1] for v in prof.vertices]
        assert abs(min(zs) - 0.9) < 1e-12
        assert abs(max(zs) - (0.9 + 1.2)) < 1e-12

    def test_section_profile_u_spans_thickness(self):
        w = _wall(thickness=0.3)
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2)
        prof = win.section_profile()
        us = [v[0] for v in prof.vertices]
        assert abs(max(us) - 0.3) < 1e-12

    def test_frame_profile_depth_equals_thickness(self):
        w = _wall(thickness=0.25)
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2)
        fp = win.frame_profile()
        assert abs(fp.depth - 0.25) < 1e-12

    def test_sill_height_default(self):
        w = _wall()
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2)
        assert win.sill_height == 0.9

    def test_glazing_material_default(self):
        w = _wall()
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2)
        assert win.glazing_material == "glass_annealed_float"

    def test_family_stored(self):
        w = _wall()
        win = Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                     family="fixed_picture")
        assert win.family == "fixed_picture"


class TestWindowValidation:
    def test_zero_width_raises(self):
        w = _wall()
        with pytest.raises(ValueError):
            Window(host_wall=w, position_along=2.5, width=0.0, height=1.2)

    def test_zero_height_raises(self):
        w = _wall()
        with pytest.raises(ValueError):
            Window(host_wall=w, position_along=2.5, width=1.2, height=0.0)

    def test_negative_sill_raises(self):
        w = _wall()
        with pytest.raises(ValueError):
            Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                   sill_height=-0.1)

    def test_top_above_wall_raises(self):
        w = _wall(height=2.5)
        with pytest.raises(ValueError):
            Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                   sill_height=1.5)  # top = 2.7 > 2.5

    def test_window_at_wall_end_raises(self):
        w = _wall(length=5.0)
        with pytest.raises(ValueError):
            Window(host_wall=w, position_along=5.0, width=1.2, height=1.2)

    def test_window_at_wall_start_raises(self):
        w = _wall(length=5.0)
        with pytest.raises(ValueError):
            Window(host_wall=w, position_along=0.0, width=1.2, height=1.2)

    def test_window_extends_beyond_wall_raises(self):
        w = _wall(length=5.0)
        with pytest.raises(ValueError):
            Window(host_wall=w, position_along=4.9, width=1.2, height=1.2)

    def test_zero_frame_thickness_raises(self):
        w = _wall()
        with pytest.raises(ValueError):
            Window(host_wall=w, position_along=2.5, width=1.2, height=1.2,
                   frame_thickness=0.0)


# ===========================================================================
# Integration: compound layered wall with openings
# ===========================================================================

class TestLayeredWallWithOpenings:
    def _build(self):
        layers = [
            WallLayer("concrete_reinforced", 0.20, "structure"),
            WallLayer("insulation_rockwool", 0.10, "insulation"),
            WallLayer("board_drywall_gypsum", 0.0125, "finish"),
        ]
        w = Wall(start=(0, 0), end=(6.0, 0), height=3.0,
                 thickness=0.3125, layers=layers)
        return w

    def test_layered_wall_thickness(self):
        w = self._build()
        assert abs(w.thickness - 0.3125) < 1e-12

    def test_door_cut_uses_total_thickness(self):
        """Door cut volume uses the full compound wall thickness."""
        w = self._build()
        d = Door(host_wall=w, position_along=2.0, width=0.9, height=2.1)
        expected = 0.9 * 2.1 * 0.3125
        assert abs(d.cut_volume() - expected) < 1e-12

    def test_window_cut_uses_total_thickness(self):
        w = self._build()
        win = Window(host_wall=w, position_along=4.5, width=1.2, height=1.2,
                     sill_height=0.9)
        expected = 1.2 * 1.2 * 0.3125
        assert abs(win.cut_volume() - expected) < 1e-12

    def test_net_volume_with_door_and_window(self):
        w = self._build()
        gross = w.gross_volume()
        Door(host_wall=w, position_along=1.5, width=0.9, height=2.1)
        Window(host_wall=w, position_along=4.5, width=1.2, height=1.2,
               sill_height=0.9)
        door_cut   = 0.9 * 2.1 * 0.3125
        window_cut = 1.2 * 1.2 * 0.3125
        assert abs(w.net_volume() - (gross - door_cut - window_cut)) < 1e-12
