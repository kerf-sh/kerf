"""
Tests for copper pour fill computation.

Tests the core geometry logic directly using shapely — no HTTP call needed.
The pour.py pyworker route is tested via its internal helpers reproduced here
so the test suite does not depend on the pyworker process being live.
"""
import math
import pytest

try:
    from shapely.geometry import Point, Polygon, LineString
    from shapely.ops import unary_union
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False


# ── Minimal reimplementation of core pour logic (mirrors pyworker/routes/pour.py) ─

def _clearance_union(traces, pads, pour_net, clearance_mm):
    obstacles = []
    for trace in traces:
        if trace.get("net_id") == pour_net:
            continue
        pts = trace.get("points", [])
        if len(pts) >= 2:
            coords = [(p["x"], p["y"]) for p in pts]
            obstacles.append(LineString(coords).buffer(clearance_mm))
    for pad in pads:
        if pad.get("net_id") == pour_net:
            continue
        r = pad.get("diameter_mm", 1.0) / 2.0 + clearance_mm
        obstacles.append(Point(pad["x"], pad["y"]).buffer(r))
    if not obstacles:
        return None
    return unary_union(obstacles)


def simple_pour_fill(polygon_pts, traces, pads, pour_net, clearance_mm):
    """Compute filled polygon; returns {"outer": [...], "holes": [...], "_shape": shapely_geom}."""
    if not SHAPELY_AVAILABLE:
        return {"outer": polygon_pts, "holes": [], "_shape": None}

    base = Polygon([(p["x"], p["y"]) for p in polygon_pts])
    clearance_geom = _clearance_union(traces, pads, pour_net, clearance_mm)

    filled = base if clearance_geom is None else base.difference(clearance_geom)

    if hasattr(filled, "geoms"):
        pieces = list(filled.geoms)
        filled = max(pieces, key=lambda g: g.area) if pieces else base

    outer = list(filled.exterior.coords) if hasattr(filled, "exterior") else []
    holes = [list(i.coords) for i in filled.interiors] if hasattr(filled, "interiors") else []
    # Keep the shapely object for area assertions (reconstructing from outer discards holes)
    return {"outer": outer, "holes": holes, "_shape": filled}


def _thermal_spokes(pad, spoke_count, gap, spoke_width):
    px, py = pad["x"], pad["y"]
    r = pad.get("diameter_mm", 1.0) / 2.0
    spokes = []
    for i in range(spoke_count):
        angle = math.radians(i * 360.0 / spoke_count)
        x1 = px + (r + gap) * math.cos(angle)
        y1 = py + (r + gap) * math.sin(angle)
        x2 = px + (r + gap + spoke_width * 4) * math.cos(angle)
        y2 = py + (r + gap + spoke_width * 4) * math.sin(angle)
        spokes.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return spokes


# ── Fixtures ──────────────────────────────────────────────────────────────────

SQUARE_10 = [
    {"x": 0, "y": 0},
    {"x": 10, "y": 0},
    {"x": 10, "y": 10},
    {"x": 0, "y": 10},
]


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="shapely not installed")
def test_empty_board_returns_full_polygon():
    """Pour with no obstacles returns approximately the original 100 sq mm area."""
    result = simple_pour_fill(SQUARE_10, [], [], "GND", 0.25)
    assert len(result["outer"]) >= 4
    assert result["holes"] == []
    assert result["_shape"].area == pytest.approx(100.0, abs=0.01)


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="shapely not installed")
def test_non_net_pad_punches_clearance_hole():
    """A pad not on the pour net reduces fill area by its clearance circle."""
    pads = [{"x": 5, "y": 5, "diameter_mm": 1.0, "net_id": "VCC"}]
    result = simple_pour_fill(SQUARE_10, [], pads, "GND", 0.25)
    # _shape includes holes — its area should be less than 100
    assert result["_shape"].area < 100.0
    # hole radius = 0.5 + 0.25 = 0.75 mm → hole area ≈ π*0.75² ≈ 1.77
    assert result["_shape"].area < 100.0 - 1.5
    # Holes are encoded separately (interior rings)
    assert len(result["holes"]) >= 1


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="shapely not installed")
def test_same_net_pad_does_not_reduce_fill():
    """A pad on the same net as the pour is NOT subtracted."""
    pads = [{"x": 5, "y": 5, "diameter_mm": 1.0, "net_id": "GND"}]
    result = simple_pour_fill(SQUARE_10, [], pads, "GND", 0.25)
    assert result["_shape"].area == pytest.approx(100.0, abs=0.01)
    assert result["holes"] == []


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="shapely not installed")
def test_trace_not_on_net_creates_clearance_strip():
    """A trace not on the pour net reduces the fill area."""
    traces = [{"net_id": "VCC", "points": [{"x": 3, "y": 5}, {"x": 7, "y": 5}]}]
    result = simple_pour_fill(SQUARE_10, traces, [], "GND", 0.25)
    assert result["_shape"].area < 100.0


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="shapely not installed")
def test_trace_on_same_net_not_subtracted():
    """A trace on the pour net does not create a clearance gap."""
    traces = [{"net_id": "GND", "points": [{"x": 3, "y": 5}, {"x": 7, "y": 5}]}]
    result = simple_pour_fill(SQUARE_10, traces, [], "GND", 0.25)
    assert result["_shape"].area == pytest.approx(100.0, abs=0.01)


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="shapely not installed")
def test_multiple_obstacles_combine():
    """Multiple obstacles from different nets all reduce fill area."""
    pads = [
        {"x": 2, "y": 2, "diameter_mm": 0.8, "net_id": "VCC"},
        {"x": 8, "y": 8, "diameter_mm": 0.8, "net_id": "NET1"},
    ]
    result = simple_pour_fill(SQUARE_10, [], pads, "GND", 0.25)
    assert result["_shape"].area < 100.0 - 2.0


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="shapely not installed")
def test_larger_clearance_removes_more_area():
    """Larger clearance_mm removes a larger area than smaller clearance."""
    pads = [{"x": 5, "y": 5, "diameter_mm": 1.0, "net_id": "VCC"}]
    r_small = simple_pour_fill(SQUARE_10, [], pads, "GND", 0.1)
    r_large = simple_pour_fill(SQUARE_10, [], pads, "GND", 0.5)
    assert r_large["_shape"].area < r_small["_shape"].area


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="shapely not installed")
def test_thermal_spokes_generates_correct_count():
    """Thermal spoke generator returns exactly spoke_count spokes."""
    pad = {"x": 5, "y": 5, "diameter_mm": 1.2, "net_id": "GND"}
    spokes = _thermal_spokes(pad, spoke_count=4, gap=0.25, spoke_width=0.5)
    assert len(spokes) == 4


@pytest.mark.skipif(not SHAPELY_AVAILABLE, reason="shapely not installed")
def test_thermal_spokes_are_evenly_spaced():
    """Spokes at 4-count should be separated by 90° (π/2 rad)."""
    pad = {"x": 0, "y": 0, "diameter_mm": 1.0, "net_id": "GND"}
    spokes = _thermal_spokes(pad, spoke_count=4, gap=0.25, spoke_width=0.5)
    # Each spoke starts from the pad; compute the angle of each start point
    angles = [math.atan2(s["y1"] - 0, s["x1"] - 0) for s in spokes]
    angles.sort()
    diffs = [angles[i + 1] - angles[i] for i in range(len(angles) - 1)]
    for d in diffs:
        assert d == pytest.approx(math.pi / 2, abs=0.01)


def test_no_shapely_fallback():
    """Without shapely the function must return the original boundary polygon unchanged."""
    if SHAPELY_AVAILABLE:
        pytest.skip("shapely is installed; fallback path not exercised")
    result = simple_pour_fill(SQUARE_10, [], [], "GND", 0.25)
    assert result["outer"] == SQUARE_10
    assert result["holes"] == []


# ── LLM tool tests ────────────────────────────────────────────────────────────

import json
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kerf_electronics.tools.pour import (
    add_copper_pour,
    delete_copper_pour,
    set_pour_net,
    set_pour_clearance,
)

_POLYGON = [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 40}, {"x": 0, "y": 40}]


def _run(coro):
    return asyncio.run(coro)


def test_add_copper_pour_happy_path():
    args = json.dumps({
        "file_id": "board.circuit.tsx",
        "pour": {
            "polygon": _POLYGON,
            "layer": "top_copper",
            "net_id": "GND",
            "clearance_mm": 0.25,
        },
    })
    result = json.loads(_run(add_copper_pour(None, args.encode())))
    assert result.get("added") is True
    assert result["net_id"] == "GND"
    assert result["layer"] == "top_copper"
    assert result["vertex_count"] == 4


def test_add_copper_pour_missing_file_id():
    args = json.dumps({"pour": {"polygon": _POLYGON, "layer": "top_copper", "net_id": "GND"}})
    result = json.loads(_run(add_copper_pour(None, args.encode())))
    assert "error" in result


def test_add_copper_pour_bad_polygon():
    args = json.dumps({
        "file_id": "board.circuit.tsx",
        "pour": {"polygon": [{"x": 0, "y": 0}], "layer": "top_copper", "net_id": "GND"},
    })
    result = json.loads(_run(add_copper_pour(None, args.encode())))
    assert "error" in result


def test_delete_copper_pour_by_index():
    args = json.dumps({"file_id": "board.circuit.tsx", "pour_index": 0})
    result = json.loads(_run(delete_copper_pour(None, args.encode())))
    assert result.get("deleted") is True
    assert result["pour_index"] == 0


def test_delete_copper_pour_by_net_layer():
    args = json.dumps({"file_id": "board.circuit.tsx", "net_id": "GND", "layer": "top_copper"})
    result = json.loads(_run(delete_copper_pour(None, args.encode())))
    assert result.get("deleted") is True
    assert result["net_id"] == "GND"


def test_delete_copper_pour_missing_identifier():
    args = json.dumps({"file_id": "board.circuit.tsx"})
    result = json.loads(_run(delete_copper_pour(None, args.encode())))
    assert "error" in result


def test_set_pour_net_happy_path():
    args = json.dumps({"file_id": "board.circuit.tsx", "pour_index": 0, "net_id": "VCC"})
    result = json.loads(_run(set_pour_net(None, args.encode())))
    assert result.get("updated") is True
    assert result["net_id"] == "VCC"


def test_set_pour_clearance_happy_path():
    args = json.dumps({"file_id": "board.circuit.tsx", "pour_index": 0, "clearance_mm": 0.5})
    result = json.loads(_run(set_pour_clearance(None, args.encode())))
    assert result.get("updated") is True
    assert result["clearance_mm"] == pytest.approx(0.5)
    assert result["pour_index"] == 0
    assert "recompute" in result.get("note", "")


def test_set_pour_clearance_negative_rejected():
    args = json.dumps({"file_id": "board.circuit.tsx", "pour_index": 0, "clearance_mm": -0.1})
    result = json.loads(_run(set_pour_clearance(None, args.encode())))
    assert "error" in result


def test_set_pour_clearance_missing_clearance():
    args = json.dumps({"file_id": "board.circuit.tsx", "pour_index": 0})
    result = json.loads(_run(set_pour_clearance(None, args.encode())))
    assert "error" in result
