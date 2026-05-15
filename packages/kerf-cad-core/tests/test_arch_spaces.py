"""
Tests for kerf_cad_core.arch.spaces and arch.spaces_tools.

Pure-Python, hermetic — no OCC, no DB, no network, no on-disk fixtures.
All dimensions in millimetres; areas in mm².

Covers
------
Geometry helpers:
  T01  rectangle shoelace area = L × W  (CCW)
  T02  rectangle shoelace area = L × W  (CW — same result)
  T03  L-shaped room area correct (decomposition check)
  T04  polygon_perimeter correct for axis-aligned rectangle
  T05  is_self_intersecting returns False for convex polygon
  T06  is_self_intersecting returns True for bow-tie (butterfly) polygon

compute_room:
  T07  gross_area_mm2 == L × W for rectangle room
  T08  net area == gross when wall_thickness == 0
  T09  net area < gross when wall_thickness > 0 (band subtraction)
  T10  net area approximation: net = gross − perimeter × (thickness/2)
  T11  occupant_load == ceil(net_area_m2 / factor)  — business occupancy
  T12  occupant_load == ceil(net_area_m2 / factor)  — assembly_concentrated
  T13  egress_width stairways = load × 0.3 mm
  T14  egress_width other_means = load × 0.2 mm
  T15  level label propagated to output
  T16  error on polygon with < 3 vertices
  T17  error on zero-area (degenerate) polygon
  T18  error on self-intersecting polygon — friendly {ok:false, errors}
  T19  error on unknown occupancy type
  T20  error on invalid wall_thickness (negative)
  T21  L-shaped room area via compute_room matches manual sum

compute_area_schedule:
  T22  empty rooms list → schedule with zero totals
  T23  single room schedule totals match room values
  T24  multi-room by_level rollup sums correctly
  T25  multi-room by_occupancy rollup sums correctly
  T26  total_occupant_load == sum of individual room loads
  T27  total_gross_area_m2 == total_gross_area_mm2 / 1e6
  T28  rooms with ok=false are rejected with errors
  T29  non-dict entry in rooms list raises error gracefully

compute_occupancy_load:
  T30  occupant_load == ceil(area_m2 / factor) for mercantile
  T31  occupant_load == ceil(area_m2 / factor) for residential
  T32  area_type label reflects use_net flag
  T33  zero area → 0 occupants
  T34  error on negative area
  T35  error on unknown occupancy

LLM tool wrappers (async):
  T36  run_arch_room returns ok payload for valid rectangle
  T37  run_arch_room returns err payload for self-intersecting polygon
  T38  run_arch_area_schedule returns ok payload for two rooms
  T39  run_arch_occupancy_load returns ok payload for business
  T40  run_arch_occupancy_load returns err payload for bad occupancy
  T41  plugin._TOOL_MODULES includes spaces_tools

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.arch.spaces import (
    OCCUPANCY_LOAD_FACTORS,
    shoelace_area,
    polygon_perimeter,
    is_self_intersecting,
    compute_room,
    compute_area_schedule,
    compute_occupancy_load,
    _net_area_mm2,
    _MM2_PER_M2,
)
from kerf_cad_core.arch.spaces_tools import (
    run_arch_room,
    run_arch_area_schedule,
    run_arch_occupancy_load,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_ctx():
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    return ProjectCtx(
        pool=None,
        storage=None,
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )


def _rect(w_mm: float, h_mm: float, ox: float = 0.0, oy: float = 0.0) -> list:
    """Axis-aligned rectangle polygon, CCW."""
    return [
        [ox, oy],
        [ox + w_mm, oy],
        [ox + w_mm, oy + h_mm],
        [ox, oy + h_mm],
    ]


def _rect_cw(w_mm: float, h_mm: float) -> list:
    """Axis-aligned rectangle polygon, CW."""
    return [
        [0.0, 0.0],
        [0.0, h_mm],
        [w_mm, h_mm],
        [w_mm, 0.0],
    ]


def _l_shape(a: float, b: float, c: float, d: float) -> list:
    """
    L-shape: main rectangle (a × b) minus upper-right corner (c × d).
    Vertices ordered CCW.

        (0,b)---(a-c,b)
          |         |
       (0,b-d)--(a-c,b-d)--(a,b-d)
          |                   |
        (0,0)--------------(a,0)
    """
    return [
        [0.0, 0.0],
        [a, 0.0],
        [a, b - d],
        [a - c, b - d],
        [a - c, b],
        [0.0, b],
    ]


# ---------------------------------------------------------------------------
# T01 – T06: Geometry helpers
# ---------------------------------------------------------------------------

class TestGeometryHelpers:
    def test_T01_rectangle_shoelace_ccw(self):
        poly = _rect(6000.0, 4000.0)
        area = shoelace_area(poly)
        assert area == pytest.approx(6000.0 * 4000.0, rel=1e-9)

    def test_T02_rectangle_shoelace_cw(self):
        poly = _rect_cw(6000.0, 4000.0)
        area = shoelace_area(poly)
        assert area == pytest.approx(6000.0 * 4000.0, rel=1e-9)

    def test_T03_l_shape_area(self):
        # Main: 8000×5000, cut: 3000×2000 → area = 40_000_000 − 6_000_000
        poly = _l_shape(8000.0, 5000.0, 3000.0, 2000.0)
        expected = 8000.0 * 5000.0 - 3000.0 * 2000.0
        assert shoelace_area(poly) == pytest.approx(expected, rel=1e-9)

    def test_T04_rectangle_perimeter(self):
        poly = _rect(6000.0, 4000.0)
        expected = 2 * (6000.0 + 4000.0)
        assert polygon_perimeter(poly) == pytest.approx(expected, rel=1e-9)

    def test_T05_convex_not_self_intersecting(self):
        poly = _rect(3000.0, 2000.0)
        assert is_self_intersecting(poly) is False

    def test_T06_bow_tie_self_intersecting(self):
        # Bow-tie (figure-8) — edges cross diagonally
        poly = [
            [0.0, 0.0],
            [2000.0, 2000.0],
            [2000.0, 0.0],
            [0.0, 2000.0],
        ]
        assert is_self_intersecting(poly) is True


# ---------------------------------------------------------------------------
# T07 – T21: compute_room
# ---------------------------------------------------------------------------

class TestComputeRoom:
    def test_T07_gross_area_rectangle(self):
        r = compute_room(_rect(5000.0, 3000.0), "Office", "business")
        assert r["ok"] is True
        assert r["gross_area_mm2"] == pytest.approx(5000.0 * 3000.0, rel=1e-9)

    def test_T08_net_equals_gross_zero_thickness(self):
        r = compute_room(_rect(5000.0, 3000.0), "Office", "business", wall_thickness=0.0)
        assert r["ok"] is True
        assert r["net_area_mm2"] == pytest.approx(r["gross_area_mm2"], rel=1e-9)

    def test_T09_net_less_than_gross_with_thickness(self):
        r = compute_room(_rect(5000.0, 3000.0), "Office", "business", wall_thickness=200.0)
        assert r["ok"] is True
        assert r["net_area_mm2"] < r["gross_area_mm2"]

    def test_T10_net_area_band_formula(self):
        w, h, t = 5000.0, 3000.0, 200.0
        poly = _rect(w, h)
        r = compute_room(poly, "Office", "business", wall_thickness=t)
        gross = w * h
        perim = 2 * (w + h)
        expected_net = gross - perim * (t / 2.0)
        assert r["net_area_mm2"] == pytest.approx(expected_net, rel=1e-9)

    def test_T11_occupant_load_business(self):
        # 10 m × 10 m room = 100 m², factor 9.3 → ceil(100/9.3) = 11
        w = h = 10_000.0  # mm
        r = compute_room(_rect(w, h), "BigOffice", "business")
        factor = OCCUPANCY_LOAD_FACTORS["business"]
        area_m2 = (w * h) / _MM2_PER_M2
        expected_load = math.ceil(area_m2 / factor)
        assert r["ok"] is True
        assert r["occupant_load"] == expected_load

    def test_T12_occupant_load_assembly_concentrated(self):
        # 15 m × 10 m = 150 m², factor 0.65 → ceil(150/0.65) = 231
        w, h = 15_000.0, 10_000.0
        r = compute_room(_rect(w, h), "Hall", "assembly_concentrated")
        factor = OCCUPANCY_LOAD_FACTORS["assembly_concentrated"]
        area_m2 = (w * h) / _MM2_PER_M2
        expected_load = math.ceil(area_m2 / factor)
        assert r["ok"] is True
        assert r["occupant_load"] == expected_load

    def test_T13_egress_stairways(self):
        r = compute_room(_rect(5000.0, 3000.0), "Office", "business")
        load = r["occupant_load"]
        assert r["egress_width"]["stairways_mm"] == pytest.approx(load * 0.3, rel=1e-9)

    def test_T14_egress_other_means(self):
        r = compute_room(_rect(5000.0, 3000.0), "Office", "business")
        load = r["occupant_load"]
        assert r["egress_width"]["other_means_mm"] == pytest.approx(load * 0.2, rel=1e-9)

    def test_T15_level_propagated(self):
        r = compute_room(_rect(4000.0, 3000.0), "Room A", "business", level="Level 2")
        assert r["ok"] is True
        assert r["level"] == "Level 2"

    def test_T16_error_too_few_vertices(self):
        r = compute_room([[0, 0], [1000, 0]], "Room", "business")
        assert r["ok"] is False
        assert any("3" in e or "vertices" in e.lower() for e in r["errors"])

    def test_T17_error_zero_area_polygon(self):
        # All collinear — zero area
        poly = [[0, 0], [1000, 0], [2000, 0]]
        r = compute_room(poly, "Room", "business")
        assert r["ok"] is False
        assert any("degenerate" in e.lower() or "zero" in e.lower() for e in r["errors"])

    def test_T18_error_self_intersecting(self):
        bow_tie = [
            [0.0, 0.0],
            [2000.0, 2000.0],
            [2000.0, 0.0],
            [0.0, 2000.0],
        ]
        r = compute_room(bow_tie, "Twisted", "business")
        assert r["ok"] is False
        assert any("self-intersecting" in e.lower() or "intersect" in e.lower()
                   for e in r["errors"])

    def test_T19_error_unknown_occupancy(self):
        r = compute_room(_rect(3000.0, 3000.0), "Room", "disco")
        assert r["ok"] is False
        assert any("occupancy" in e.lower() or "disco" in e for e in r["errors"])

    def test_T20_error_negative_wall_thickness(self):
        r = compute_room(_rect(3000.0, 3000.0), "Room", "business", wall_thickness=-50.0)
        assert r["ok"] is False
        assert any("wall_thickness" in e.lower() for e in r["errors"])

    def test_T21_l_shape_room_area(self):
        # Main 12 m × 8 m, cut 4 m × 3 m (upper-right corner)
        a, b, c, d = 12_000.0, 8_000.0, 4_000.0, 3_000.0
        poly = _l_shape(a, b, c, d)
        expected_m2 = (a * b - c * d) / _MM2_PER_M2
        r = compute_room(poly, "L-Office", "business")
        assert r["ok"] is True
        assert r["gross_area_m2"] == pytest.approx(expected_m2, rel=1e-9)


# ---------------------------------------------------------------------------
# T22 – T29: compute_area_schedule
# ---------------------------------------------------------------------------

class TestAreaSchedule:
    def _make_room(self, w, h, name, occ, level="L1"):
        return compute_room(_rect(w, h), name, occ, level=level)

    def test_T22_empty_rooms(self):
        s = compute_area_schedule([])
        assert s["ok"] is True
        assert s["total_gross_area_mm2"] == 0.0
        assert s["total_net_area_mm2"] == 0.0
        assert s["total_occupant_load"] == 0

    def test_T23_single_room_totals(self):
        room = self._make_room(5000.0, 4000.0, "Room A", "business", "L1")
        s = compute_area_schedule([room])
        assert s["ok"] is True
        assert s["total_gross_area_mm2"] == pytest.approx(room["gross_area_mm2"], rel=1e-9)
        assert s["total_net_area_mm2"] == pytest.approx(room["net_area_mm2"], rel=1e-9)
        assert s["total_occupant_load"] == room["occupant_load"]

    def test_T24_multi_room_by_level_rollup(self):
        r1 = self._make_room(6000.0, 4000.0, "A", "business", "L1")
        r2 = self._make_room(5000.0, 3000.0, "B", "business", "L1")
        r3 = self._make_room(4000.0, 4000.0, "C", "business", "L2")
        s = compute_area_schedule([r1, r2, r3])
        assert s["ok"] is True
        l1_gross = r1["gross_area_mm2"] + r2["gross_area_mm2"]
        assert s["by_level"]["L1"]["gross_area_mm2"] == pytest.approx(l1_gross, rel=1e-9)
        assert s["by_level"]["L2"]["gross_area_mm2"] == pytest.approx(
            r3["gross_area_mm2"], rel=1e-9
        )

    def test_T25_multi_room_by_occupancy_rollup(self):
        r1 = self._make_room(6000.0, 4000.0, "Office", "business", "L1")
        r2 = self._make_room(3000.0, 2000.0, "Shop", "mercantile", "L1")
        r3 = self._make_room(5000.0, 3000.0, "Office 2", "business", "L1")
        s = compute_area_schedule([r1, r2, r3])
        assert s["ok"] is True
        biz_gross = r1["gross_area_mm2"] + r3["gross_area_mm2"]
        assert s["by_occupancy"]["business"]["gross_area_mm2"] == pytest.approx(
            biz_gross, rel=1e-9
        )
        assert s["by_occupancy"]["mercantile"]["gross_area_mm2"] == pytest.approx(
            r2["gross_area_mm2"], rel=1e-9
        )

    def test_T26_total_occupant_load_sum(self):
        r1 = self._make_room(8000.0, 6000.0, "Hall", "assembly_unconcentrated", "L1")
        r2 = self._make_room(5000.0, 4000.0, "Office", "business", "L1")
        s = compute_area_schedule([r1, r2])
        assert s["total_occupant_load"] == r1["occupant_load"] + r2["occupant_load"]

    def test_T27_total_gross_area_m2_conversion(self):
        r1 = self._make_room(5000.0, 3000.0, "Room", "business")
        r2 = self._make_room(4000.0, 2000.0, "Room 2", "business")
        s = compute_area_schedule([r1, r2])
        assert s["total_gross_area_m2"] == pytest.approx(
            s["total_gross_area_mm2"] / _MM2_PER_M2, rel=1e-9
        )

    def test_T28_invalid_room_triggers_error(self):
        bad_room = {"ok": False, "errors": ["bad polygon"]}
        s = compute_area_schedule([bad_room])
        assert s["ok"] is False
        assert len(s["errors"]) > 0

    def test_T29_non_dict_in_rooms_list(self):
        s = compute_area_schedule(["not_a_dict"])
        assert s["ok"] is False
        assert any("not a dict" in e or "is not" in e for e in s["errors"])


# ---------------------------------------------------------------------------
# T30 – T35: compute_occupancy_load
# ---------------------------------------------------------------------------

class TestComputeOccupancyLoad:
    def test_T30_mercantile_load(self):
        # 200 m², factor 2.79 → ceil(200/2.79) = 72
        r = compute_occupancy_load(200.0, "mercantile")
        factor = OCCUPANCY_LOAD_FACTORS["mercantile"]
        expected = math.ceil(200.0 / factor)
        assert r["ok"] is True
        assert r["occupant_load"] == expected

    def test_T31_residential_load(self):
        # 300 m², factor 18.58 → ceil(300/18.58) = 17
        r = compute_occupancy_load(300.0, "residential")
        factor = OCCUPANCY_LOAD_FACTORS["residential"]
        expected = math.ceil(300.0 / factor)
        assert r["ok"] is True
        assert r["occupant_load"] == expected

    def test_T32_use_net_label(self):
        r_net = compute_occupancy_load(100.0, "business", use_net=True)
        r_gross = compute_occupancy_load(100.0, "business", use_net=False)
        assert r_net["area_type"] == "net"
        assert r_gross["area_type"] == "gross"

    def test_T33_zero_area_zero_occupants(self):
        r = compute_occupancy_load(0.0, "business")
        assert r["ok"] is True
        assert r["occupant_load"] == 0

    def test_T34_error_negative_area(self):
        r = compute_occupancy_load(-10.0, "business")
        assert r["ok"] is False
        assert any("area_m2" in e.lower() or ">= 0" in e for e in r["errors"])

    def test_T35_error_unknown_occupancy(self):
        r = compute_occupancy_load(100.0, "nightclub")
        assert r["ok"] is False
        assert any("occupancy" in e.lower() or "nightclub" in e for e in r["errors"])


# ---------------------------------------------------------------------------
# T36 – T41: LLM tool wrappers (async)
# ---------------------------------------------------------------------------

class TestToolWrappers:
    def test_T36_run_arch_room_ok(self):
        ctx = _make_ctx()
        args = json.dumps({
            "polygon": _rect(5000.0, 4000.0),
            "name": "Office 101",
            "occupancy": "business",
            "level": "L1",
        }).encode()
        raw = _run(run_arch_room(ctx, args))
        payload = json.loads(raw)
        assert payload["ok"] is True
        assert payload["gross_area_mm2"] == pytest.approx(5000.0 * 4000.0, rel=1e-9)

    def test_T37_run_arch_room_self_intersecting(self):
        ctx = _make_ctx()
        bow_tie = [
            [0.0, 0.0],
            [2000.0, 2000.0],
            [2000.0, 0.0],
            [0.0, 2000.0],
        ]
        args = json.dumps({
            "polygon": bow_tie,
            "name": "Twisted Room",
            "occupancy": "business",
        }).encode()
        raw = _run(run_arch_room(ctx, args))
        payload = json.loads(raw)
        # err_payload returns {"error": ..., "code": ...}
        assert "error" in payload
        assert payload.get("code") == "BAD_ARGS"

    def test_T38_run_arch_area_schedule_two_rooms(self):
        ctx = _make_ctx()
        r1 = compute_room(_rect(6000.0, 4000.0), "R1", "business", level="L1")
        r2 = compute_room(_rect(5000.0, 3000.0), "R2", "mercantile", level="L1")
        args = json.dumps({"rooms": [r1, r2]}).encode()
        raw = _run(run_arch_area_schedule(ctx, args))
        payload = json.loads(raw)
        assert payload["ok"] is True
        expected_gross = r1["gross_area_mm2"] + r2["gross_area_mm2"]
        assert payload["total_gross_area_mm2"] == pytest.approx(expected_gross, rel=1e-9)

    def test_T39_run_arch_occupancy_load_business(self):
        ctx = _make_ctx()
        args = json.dumps({"area_m2": 100.0, "occupancy": "business"}).encode()
        raw = _run(run_arch_occupancy_load(ctx, args))
        payload = json.loads(raw)
        assert payload["ok"] is True
        factor = OCCUPANCY_LOAD_FACTORS["business"]
        assert payload["occupant_load"] == math.ceil(100.0 / factor)

    def test_T40_run_arch_occupancy_load_bad_occupancy(self):
        ctx = _make_ctx()
        args = json.dumps({"area_m2": 100.0, "occupancy": "spaceship"}).encode()
        raw = _run(run_arch_occupancy_load(ctx, args))
        payload = json.loads(raw)
        # err_payload returns {"error": ..., "code": ...}
        assert "error" in payload
        assert payload.get("code") == "BAD_ARGS"

    def test_T41_spaces_tools_in_tool_modules(self):
        from kerf_cad_core.plugin import _TOOL_MODULES
        assert "kerf_cad_core.arch.spaces_tools" in _TOOL_MODULES
