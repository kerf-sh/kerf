"""
Tests for the parametric BIM primitives (kerf_cad_core.arch.*).

Pure-Python, hermetic — no OCC, no DB, no on-disk fixtures.
All dimensions in millimetres.

Covers:
  - Wall builder: basic quantities, layered thickness, bad inputs
  - Door builder: fit validation, opening volume, friendly errors
  - Window builder: fit validation (sill + height), opening volume
  - Slab builder: shoelace area, rectangle & L-shape, bad polygon
  - Opening builder: rectangular and arched volumes, fit checks
  - compose_wall_with_openings: net volume, bad opening propagation
  - LLM tool wrappers (async): ok/err payloads, JSON round-trip
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.arch.primitives import (
    build_wall,
    build_door,
    build_window,
    build_slab,
    build_opening,
    compose_wall_with_openings,
    _shoelace_area,
    _distance,
)
from kerf_cad_core.arch.tools import (
    run_arch_wall,
    run_arch_door,
    run_arch_window,
    run_arch_slab,
    run_arch_opening,
    run_arch_wall_with_openings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_ctx():
    """Minimal fake ProjectCtx — not used by pure tools."""
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    return ProjectCtx(
        pool=None,
        storage=None,
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )


def _ok(raw: str) -> dict:
    d = json.loads(raw)
    assert "error" not in d, f"Expected success payload, got error: {d}"
    return d


def _err(raw: str) -> dict:
    d = json.loads(raw)
    assert "error" in d, f"Expected error payload, got: {d}"
    return d


# ---------------------------------------------------------------------------
# _distance helper
# ---------------------------------------------------------------------------

class TestDistance:
    def test_horizontal(self):
        assert _distance((0, 0), (3000, 0)) == pytest.approx(3000.0)

    def test_vertical(self):
        assert _distance((0, 0), (0, 4000)) == pytest.approx(4000.0)

    def test_diagonal(self):
        # 3-4-5 triangle scaled to mm
        assert _distance((0, 0), (3000, 4000)) == pytest.approx(5000.0)

    def test_zero_length(self):
        assert _distance((100, 200), (100, 200)) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _shoelace_area helper
# ---------------------------------------------------------------------------

class TestShoelaceArea:
    def test_unit_square(self):
        pts = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert _shoelace_area(pts) == pytest.approx(1.0)

    def test_rectangle_3x4(self):
        pts = [(0, 0), (3000, 0), (3000, 4000), (0, 4000)]
        assert _shoelace_area(pts) == pytest.approx(12_000_000.0)

    def test_ccw_and_cw_equal(self):
        pts_cw  = [(0, 0), (0, 1), (1, 1), (1, 0)]
        pts_ccw = [(0, 0), (1, 0), (1, 1), (0, 1)]
        assert _shoelace_area(pts_cw) == pytest.approx(_shoelace_area(pts_ccw))


# ---------------------------------------------------------------------------
# build_wall
# ---------------------------------------------------------------------------

class TestBuildWall:
    WALL_PARAMS = dict(start=[0, 0], end=[5000, 0], height=3000, thickness=200)

    def test_basic_quantities(self):
        r = build_wall(**self.WALL_PARAMS)
        assert r["ok"] is True
        assert r["length_mm"] == pytest.approx(5000.0)
        assert r["gross_area_mm2"] == pytest.approx(5000.0 * 3000.0)
        assert r["gross_volume_mm3"] == pytest.approx(5000.0 * 3000.0 * 200.0)

    def test_thickness_stored(self):
        r = build_wall(**self.WALL_PARAMS)
        assert r["thickness_mm"] == pytest.approx(200.0)

    def test_op_field(self):
        r = build_wall(**self.WALL_PARAMS)
        assert r["op"] == "arch_wall"

    def test_id_stored(self):
        r = build_wall(**self.WALL_PARAMS, id="w-01")
        assert r["id"] == "w-01"

    def test_diagonal_wall_length(self):
        # 3000-4000-5000 right triangle → length 5000
        r = build_wall(start=[0, 0], end=[3000, 4000], height=2800, thickness=250)
        assert r["ok"] is True
        assert r["length_mm"] == pytest.approx(5000.0)

    def test_layered_wall_total_thickness(self):
        layers = [
            {"name": "brick", "thickness": 110},
            {"name": "insulation", "thickness": 75},
            {"name": "plaster", "thickness": 15},
        ]
        r = build_wall(start=[0, 0], end=[4000, 0], height=2700, layers=layers)
        assert r["ok"] is True
        assert r["thickness_mm"] == pytest.approx(200.0)  # 110+75+15
        assert len(r["layers"]) == 3

    def test_layered_wall_volume_uses_derived_thickness(self):
        layers = [
            {"name": "brick", "thickness": 100},
            {"name": "block", "thickness": 200},
        ]
        r = build_wall(start=[0, 0], end=[2000, 0], height=1000, layers=layers)
        assert r["ok"] is True
        assert r["gross_volume_mm3"] == pytest.approx(2000.0 * 1000.0 * 300.0)

    def test_missing_thickness_no_layers_error(self):
        r = build_wall(start=[0, 0], end=[5000, 0], height=3000)
        assert r["ok"] is False
        assert any("thickness" in e for e in r["errors"])

    def test_zero_height_error(self):
        r = build_wall(start=[0, 0], end=[5000, 0], height=0, thickness=200)
        assert r["ok"] is False
        assert any("height" in e for e in r["errors"])

    def test_negative_height_error(self):
        r = build_wall(start=[0, 0], end=[5000, 0], height=-100, thickness=200)
        assert r["ok"] is False

    def test_layer_zero_thickness_error(self):
        layers = [{"name": "brick", "thickness": 0}]
        r = build_wall(start=[0, 0], end=[5000, 0], height=3000, layers=layers)
        assert r["ok"] is False
        assert any("thickness" in e for e in r["errors"])


# ---------------------------------------------------------------------------
# build_door
# ---------------------------------------------------------------------------

_WALL_L = 5000.0
_WALL_H = 3000.0
_WALL_T = 200.0


def _door(**overrides):
    base = dict(
        width=900, height=2100,
        wall_ref="w-01",
        position_along_wall=500,
        wall_length=_WALL_L,
        wall_height=_WALL_H,
        wall_thickness=_WALL_T,
    )
    base.update(overrides)
    return build_door(**base)


class TestBuildDoor:
    def test_ok_basic(self):
        r = _door()
        assert r["ok"] is True

    def test_op_field(self):
        assert _door()["op"] == "arch_door"

    def test_opening_volume(self):
        r = _door()
        assert r["opening_volume_mm3"] == pytest.approx(900 * 2100 * _WALL_T)

    def test_cut_box_dimensions(self):
        r = _door()
        assert r["cut_box"]["width_mm"] == pytest.approx(900.0)
        assert r["cut_box"]["height_mm"] == pytest.approx(2100.0)
        assert r["cut_box"]["depth_mm"] == pytest.approx(_WALL_T)

    def test_panel_params_swing(self):
        r = _door(swing="double")
        assert r["panel_params"]["swing"] == "double"

    def test_door_too_wide_error(self):
        # position=4900 + width=900 = 5800 > wall_length=5000
        r = _door(position_along_wall=4900, width=900)
        assert r["ok"] is False
        assert any("fit" in e.lower() for e in r["errors"])

    def test_door_too_tall_error(self):
        r = _door(height=3500)  # > wall_height 3000
        assert r["ok"] is False
        assert any("fit" in e.lower() for e in r["errors"])

    def test_invalid_swing_error(self):
        r = _door(swing="revolving")
        assert r["ok"] is False
        assert any("swing" in e for e in r["errors"])

    def test_zero_width_error(self):
        r = _door(width=0)
        assert r["ok"] is False

    def test_missing_wall_ref_error(self):
        r = _door(wall_ref="")
        assert r["ok"] is False
        assert any("wall_ref" in e for e in r["errors"])


# ---------------------------------------------------------------------------
# build_window
# ---------------------------------------------------------------------------

def _window(**overrides):
    base = dict(
        width=1200, height=1500,
        sill_height=900,
        wall_ref="w-01",
        position_along_wall=1000,
        wall_length=_WALL_L,
        wall_height=_WALL_H,
        wall_thickness=_WALL_T,
    )
    base.update(overrides)
    return build_window(**base)


class TestBuildWindow:
    def test_ok_basic(self):
        r = _window()
        assert r["ok"] is True

    def test_op_field(self):
        assert _window()["op"] == "arch_window"

    def test_head_height(self):
        r = _window()
        assert r["head_height_mm"] == pytest.approx(900 + 1500)

    def test_opening_volume(self):
        r = _window()
        assert r["opening_volume_mm3"] == pytest.approx(1200 * 1500 * _WALL_T)

    def test_window_too_high_error(self):
        # sill=900 + height=2500 = 3400 > wall_height=3000
        r = _window(height=2500)
        assert r["ok"] is False
        assert any("fit" in e.lower() for e in r["errors"])

    def test_window_too_wide_error(self):
        r = _window(position_along_wall=4000, width=1200)  # 4000+1200=5200 > 5000
        assert r["ok"] is False

    def test_negative_sill_error(self):
        r = _window(sill_height=-10)
        assert r["ok"] is False

    def test_invalid_operation_error(self):
        r = _window(operation="guillotine")
        assert r["ok"] is False
        assert any("operation" in e for e in r["errors"])

    def test_sill_height_stored(self):
        r = _window(sill_height=800)
        assert r["sill_height_mm"] == pytest.approx(800.0)


# ---------------------------------------------------------------------------
# build_slab
# ---------------------------------------------------------------------------

class TestBuildSlab:
    def test_rectangle(self):
        outline = [[0, 0], [6000, 0], [6000, 4000], [0, 4000]]
        r = build_slab(outline=outline, thickness=200, level=0)
        assert r["ok"] is True
        assert r["area_mm2"] == pytest.approx(6000.0 * 4000.0)
        assert r["volume_mm3"] == pytest.approx(6000.0 * 4000.0 * 200.0)

    def test_square(self):
        outline = [[0, 0], [3000, 0], [3000, 3000], [0, 3000]]
        r = build_slab(outline=outline, thickness=150)
        assert r["area_mm2"] == pytest.approx(9_000_000.0)

    def test_level_stored(self):
        outline = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]
        r = build_slab(outline=outline, thickness=200, level=3000)
        assert r["level_mm"] == pytest.approx(3000.0)

    def test_l_shape_area(self):
        # L-shape: 4×4 minus 2×2 in corner → area = 12 units²
        # (0,0) (4,0) (4,2) (2,2) (2,4) (0,4)  scaled ×1000 mm
        s = 1000
        outline = [[0, 0], [4*s, 0], [4*s, 2*s], [2*s, 2*s], [2*s, 4*s], [0, 4*s]]
        r = build_slab(outline=outline, thickness=200)
        assert r["ok"] is True
        assert r["area_mm2"] == pytest.approx(12 * s * s)

    def test_op_field(self):
        outline = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]
        r = build_slab(outline=outline, thickness=200)
        assert r["op"] == "arch_slab"

    def test_too_few_vertices_error(self):
        r = build_slab(outline=[[0, 0], [1000, 0]], thickness=200)
        assert r["ok"] is False
        assert any("3" in e for e in r["errors"])

    def test_zero_thickness_error(self):
        outline = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]
        r = build_slab(outline=outline, thickness=0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# build_opening
# ---------------------------------------------------------------------------

def _opening(**overrides):
    base = dict(
        width=800, height=1000,
        wall_ref="w-01",
        position_along_wall=1000,
        wall_length=_WALL_L,
        wall_height=_WALL_H,
        wall_thickness=_WALL_T,
        sill_height=500,
        arch_type="rectangular",
    )
    base.update(overrides)
    return build_opening(**base)


class TestBuildOpening:
    def test_ok_rectangular(self):
        r = _opening()
        assert r["ok"] is True

    def test_rectangular_volume(self):
        r = _opening(width=800, height=1000)
        assert r["opening_volume_mm3"] == pytest.approx(800 * 1000 * _WALL_T)

    def test_arched_volume(self):
        # arched: area = rect + semicircle = width*height + pi*(width/2)^2/2
        width, height = 800, 1000
        r = _opening(width=width, height=height, arch_type="arched")
        assert r["ok"] is True
        expected = width * height + math.pi * (width / 2) ** 2 / 2
        assert r["opening_volume_mm3"] == pytest.approx(expected * _WALL_T, rel=1e-5)

    def test_arched_rise_stored(self):
        r = _opening(width=800, arch_type="arched")
        assert r["arch_rise_mm"] == pytest.approx(400.0)

    def test_rectangular_rise_zero(self):
        r = _opening(width=800, arch_type="rectangular")
        assert r["arch_rise_mm"] == pytest.approx(0.0)

    def test_opening_too_wide_error(self):
        r = _opening(position_along_wall=4800, width=800)  # 4800+800=5600 > 5000
        assert r["ok"] is False

    def test_opening_too_tall_error(self):
        # sill=500 + height=2600 = 3100 > wall_height=3000
        r = _opening(sill_height=500, height=2600)
        assert r["ok"] is False

    def test_arched_too_tall_includes_rise(self):
        # sill=0 + height=2700 + rise=400 = 3100 > 3000
        r = _opening(sill_height=0, height=2700, width=800, arch_type="arched")
        assert r["ok"] is False

    def test_invalid_arch_type_error(self):
        r = _opening(arch_type="pointed")
        assert r["ok"] is False
        assert any("arch_type" in e for e in r["errors"])

    def test_op_field(self):
        r = _opening()
        assert r["op"] == "arch_opening"


# ---------------------------------------------------------------------------
# compose_wall_with_openings
# ---------------------------------------------------------------------------

class TestComposeWallWithOpenings:
    def _make_wall(self):
        return build_wall(
            start=[0, 0], end=[_WALL_L, 0],
            height=_WALL_H, thickness=_WALL_T, id="w-01"
        )

    def test_no_openings_net_equals_gross(self):
        wall = self._make_wall()
        result = compose_wall_with_openings(wall, [])
        assert result["ok"] is True
        assert result["net_volume_mm3"] == pytest.approx(result["gross_volume_mm3"])

    def test_single_door_net_volume(self):
        wall = self._make_wall()
        door = _door()
        result = compose_wall_with_openings(wall, [door])
        assert result["ok"] is True
        door_vol = 900 * 2100 * _WALL_T
        expected_net = _WALL_L * _WALL_H * _WALL_T - door_vol
        assert result["net_volume_mm3"] == pytest.approx(expected_net)

    def test_door_and_window_net_volume(self):
        wall = self._make_wall()
        door = _door()
        win = _window()
        result = compose_wall_with_openings(wall, [door, win])
        assert result["ok"] is True
        total_opening_vol = door["opening_volume_mm3"] + win["opening_volume_mm3"]
        assert result["total_opening_volume_mm3"] == pytest.approx(total_opening_vol)
        expected_net = _WALL_L * _WALL_H * _WALL_T - total_opening_vol
        assert result["net_volume_mm3"] == pytest.approx(expected_net)

    def test_invalid_wall_fails(self):
        bad_wall = {"ok": False, "errors": ["bad wall"]}
        result = compose_wall_with_openings(bad_wall, [])
        assert result["ok"] is False
        assert any("invalid" in e.lower() for e in result["errors"])

    def test_invalid_opening_propagates(self):
        wall = self._make_wall()
        bad_door = {"ok": False, "errors": ["door too wide"]}
        result = compose_wall_with_openings(wall, [bad_door])
        assert result["ok"] is False
        assert any("door too wide" in e for e in result["errors"])

    def test_gross_volume_field_present(self):
        wall = self._make_wall()
        result = compose_wall_with_openings(wall, [])
        assert "gross_volume_mm3" in result

    def test_three_openings_net_volume(self):
        wall = self._make_wall()
        door1 = _door(position_along_wall=200)
        door2 = _door(position_along_wall=1500)
        win = _window(position_along_wall=3000)
        result = compose_wall_with_openings(wall, [door1, door2, win])
        assert result["ok"] is True
        total = sum(o["opening_volume_mm3"] for o in [door1, door2, win])
        assert result["net_volume_mm3"] == pytest.approx(
            _WALL_L * _WALL_H * _WALL_T - total
        )


# ---------------------------------------------------------------------------
# LLM tool wrappers — async round-trip
# ---------------------------------------------------------------------------

class TestArchWallTool:
    _CTX = None

    @classmethod
    def ctx(cls):
        if cls._CTX is None:
            cls._CTX = _make_ctx()
        return cls._CTX

    def _call(self, **kwargs):
        raw = _run(run_arch_wall(self.ctx(), json.dumps(kwargs).encode()))
        return raw

    def test_ok_returns_length(self):
        d = _ok(self._call(start=[0, 0], end=[6000, 0], height=3000, thickness=250))
        assert d["length_mm"] == pytest.approx(6000.0)

    def test_missing_height_returns_error(self):
        _err(self._call(start=[0, 0], end=[6000, 0]))

    def test_bad_json_returns_error(self):
        raw = _run(run_arch_wall(self.ctx(), b"{not json}"))
        _err(raw)

    def test_layered_wall_tool(self):
        layers = [
            {"name": "brick", "thickness": 110},
            {"name": "plaster", "thickness": 15},
        ]
        d = _ok(self._call(
            start=[0, 0], end=[4000, 0], height=2700, layers=layers
        ))
        assert d["thickness_mm"] == pytest.approx(125.0)


class TestArchDoorTool:
    _CTX = None

    @classmethod
    def ctx(cls):
        if cls._CTX is None:
            cls._CTX = _make_ctx()
        return cls._CTX

    def _call(self, **kwargs):
        return _run(run_arch_door(self.ctx(), json.dumps(kwargs).encode()))

    def test_ok_door(self):
        d = _ok(self._call(
            width=900, height=2100,
            wall_ref="w-01",
            position_along_wall=500,
            wall_length=5000, wall_height=3000, wall_thickness=200,
        ))
        assert d["op"] == "arch_door"

    def test_door_overflow_returns_error(self):
        _err(self._call(
            width=900, height=2100,
            wall_ref="w-01",
            position_along_wall=4500,
            wall_length=5000, wall_height=3000, wall_thickness=200,
        ))


class TestArchWindowTool:
    _CTX = None

    @classmethod
    def ctx(cls):
        if cls._CTX is None:
            cls._CTX = _make_ctx()
        return cls._CTX

    def _call(self, **kwargs):
        return _run(run_arch_window(self.ctx(), json.dumps(kwargs).encode()))

    def test_ok_window(self):
        d = _ok(self._call(
            width=1200, height=1500, sill_height=900,
            wall_ref="w-01",
            position_along_wall=500,
            wall_length=5000, wall_height=3000, wall_thickness=200,
        ))
        assert d["head_height_mm"] == pytest.approx(2400.0)

    def test_window_overflow_returns_error(self):
        _err(self._call(
            width=1200, height=2500, sill_height=900,
            wall_ref="w-01",
            position_along_wall=500,
            wall_length=5000, wall_height=3000, wall_thickness=200,
        ))


class TestArchSlabTool:
    _CTX = None

    @classmethod
    def ctx(cls):
        if cls._CTX is None:
            cls._CTX = _make_ctx()
        return cls._CTX

    def _call(self, **kwargs):
        return _run(run_arch_slab(self.ctx(), json.dumps(kwargs).encode()))

    def test_ok_slab(self):
        d = _ok(self._call(
            outline=[[0, 0], [6000, 0], [6000, 4000], [0, 4000]],
            thickness=200, level=3000,
        ))
        assert d["area_mm2"] == pytest.approx(24_000_000.0)

    def test_too_few_vertices(self):
        _err(self._call(outline=[[0, 0], [1000, 0]], thickness=200))


class TestArchOpeningTool:
    _CTX = None

    @classmethod
    def ctx(cls):
        if cls._CTX is None:
            cls._CTX = _make_ctx()
        return cls._CTX

    def _call(self, **kwargs):
        return _run(run_arch_opening(self.ctx(), json.dumps(kwargs).encode()))

    def test_ok_rectangular(self):
        d = _ok(self._call(
            width=800, height=1000,
            wall_ref="w-01",
            position_along_wall=500,
            wall_length=5000, wall_height=3000, wall_thickness=200,
            sill_height=500, arch_type="rectangular",
        ))
        assert d["opening_volume_mm3"] == pytest.approx(800 * 1000 * 200.0)

    def test_ok_arched(self):
        d = _ok(self._call(
            width=800, height=1000,
            wall_ref="w-01",
            position_along_wall=500,
            wall_length=5000, wall_height=3000, wall_thickness=200,
            sill_height=0, arch_type="arched",
        ))
        expected = (800 * 1000 + math.pi * 400 ** 2 / 2) * 200
        assert d["opening_volume_mm3"] == pytest.approx(expected, rel=1e-5)


class TestArchWallWithOpeningsTool:
    _CTX = None

    @classmethod
    def ctx(cls):
        if cls._CTX is None:
            cls._CTX = _make_ctx()
        return cls._CTX

    def _call(self, **kwargs):
        return _run(run_arch_wall_with_openings(self.ctx(), json.dumps(kwargs).encode()))

    def test_ok_no_openings(self):
        wall = build_wall(start=[0, 0], end=[5000, 0], height=3000, thickness=200)
        d = _ok(self._call(wall=wall, openings=[]))
        assert d["net_volume_mm3"] == pytest.approx(d["gross_volume_mm3"])

    def test_door_subtracted(self):
        wall = build_wall(start=[0, 0], end=[5000, 0], height=3000, thickness=200)
        door = _door()
        d = _ok(self._call(wall=wall, openings=[door]))
        door_vol = 900 * 2100 * 200.0
        assert d["net_volume_mm3"] == pytest.approx(5000 * 3000 * 200.0 - door_vol)

    def test_bad_json(self):
        raw = _run(run_arch_wall_with_openings(self.ctx(), b"{bad}"))
        _err(raw)

    def test_invalid_wall_dict_error(self):
        _err(self._call(wall={"ok": False, "errors": ["broken"]}, openings=[]))
