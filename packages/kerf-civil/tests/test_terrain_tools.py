"""
Dispatch tests for civil_tin_terrain and civil_crs_transform LLM tools.

civil_tin_terrain wraps kerf_civil.tin (Delaunay TIN, contour extraction,
slope/aspect, volume).

civil_crs_transform wraps kerf_civil.crs (WGS-84 ↔ UTM, EPSG codes).

Reference values
----------------
TIN volume above z=0 for a pyramid of 4 corner points at z=0 and apex at z=5:
  base area ≈ (10×10)/2 = 50 m² per half; exact volume depends on triangulation.

CRS: WGS-84 (4326) → UTM Zone 32N (32632)
  Greenwich meridian (lon=15, lat=51) → easting ≈ 500 000 m (central meridian 15°)
"""

from __future__ import annotations

import asyncio
import json
import math
import pytest

from kerf_civil.tools_terrain import (
    civil_tin_terrain_spec,
    civil_crs_transform_spec,
    run_civil_tin_terrain,
    run_civil_crs_transform,
)


def _run(coro):
    return asyncio.run(coro)


def _ctx():
    try:
        from kerf_civil._compat import ProjectCtx
    except ImportError:
        from types import SimpleNamespace
        return SimpleNamespace(pool=None, project_id=None)
    return ProjectCtx()


def _call(handler, payload: dict) -> dict:
    raw = _run(handler(payload, _ctx()))
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Fixture terrain: flat 10×10 m square at z=0, with central high point z=5
# ---------------------------------------------------------------------------

FLAT_SQUARE = [
    [0.0, 0.0, 0.0],
    [10.0, 0.0, 0.0],
    [10.0, 10.0, 0.0],
    [0.0, 10.0, 0.0],
    [5.0, 5.0, 5.0],  # apex
]

# ---------------------------------------------------------------------------
# Spec smoke tests
# ---------------------------------------------------------------------------

class TestSpecRegistration:
    def test_tin_spec_name(self):
        assert civil_tin_terrain_spec.name == "civil_tin_terrain"

    def test_crs_spec_name(self):
        assert civil_crs_transform_spec.name == "civil_crs_transform"

    def test_tin_spec_required(self):
        assert "points" in civil_tin_terrain_spec.input_schema.get("required", [])
        assert "op" in civil_tin_terrain_spec.input_schema.get("required", [])

    def test_crs_spec_required(self):
        assert "from_crs" in civil_crs_transform_spec.input_schema.get("required", [])
        assert "to_crs" in civil_crs_transform_spec.input_schema.get("required", [])


# ---------------------------------------------------------------------------
# civil_tin_terrain — contours op
# ---------------------------------------------------------------------------

class TestTINContours:
    def test_contours_at_interval_2(self):
        result = _call(run_civil_tin_terrain, {
            "points": FLAT_SQUARE,
            "op": "contours",
            "interval": 2.0,
        })
        assert result.get("ok") is True
        assert result["n_triangles"] > 0
        assert "polylines" in result
        # At z=2 and z=4 there should be contour polylines crossing the apex
        assert result["contour_count"] > 0

    def test_contours_z_range_filter(self):
        result = _call(run_civil_tin_terrain, {
            "points": FLAT_SQUARE,
            "op": "contours",
            "interval": 1.0,
            "z_min": 3.0,
            "z_max": 4.0,
        })
        assert result.get("ok") is True
        # Only contours at z=3 and z=4
        assert result["contour_count"] <= 2

    def test_contours_invalid_interval(self):
        result = _call(run_civil_tin_terrain, {
            "points": FLAT_SQUARE,
            "op": "contours",
            "interval": -1.0,
        })
        assert "error" in result

    def test_contours_too_few_points(self):
        result = _call(run_civil_tin_terrain, {
            "points": [[0, 0, 0], [1, 0, 0]],  # only 2 points
            "op": "contours",
            "interval": 1.0,
        })
        assert "error" in result


# ---------------------------------------------------------------------------
# civil_tin_terrain — stats op
# ---------------------------------------------------------------------------

class TestTINStats:
    def test_stats_returns_triangle_list(self):
        result = _call(run_civil_tin_terrain, {
            "points": FLAT_SQUARE,
            "op": "stats",
        })
        assert result.get("ok") is True
        assert result["n_triangles"] > 0
        assert "triangles" in result
        assert len(result["triangles"]) == result["n_triangles"]
        for tri in result["triangles"]:
            assert "slope_deg" in tri
            assert "aspect_deg" in tri
            assert 0.0 <= tri["slope_deg"] <= 90.0
            assert 0.0 <= tri["aspect_deg"] < 360.0

    def test_stats_area_2d(self):
        result = _call(run_civil_tin_terrain, {
            "points": FLAT_SQUARE,
            "op": "stats",
        })
        assert result.get("ok") is True
        # Projected area of a 10×10 m square = 100 m²
        assert result["area_2d_m2"] == pytest.approx(100.0, rel=0.01)


# ---------------------------------------------------------------------------
# civil_tin_terrain — volume op
# ---------------------------------------------------------------------------

class TestTINVolume:
    def test_volume_above_zero(self):
        result = _call(run_civil_tin_terrain, {
            "points": FLAT_SQUARE,
            "op": "volume",
            "datum_z": 0.0,
        })
        assert result.get("ok") is True
        # Pyramid-like structure: volume > 0 (apex at z=5 over 100 m² base)
        # Average height ≈ 1 m (pyramid avg = h/3 = 5/3 ≈ 1.67 but TIN distributes it)
        assert result["volume_m3"] > 0

    def test_volume_above_apex_is_zero(self):
        result = _call(run_civil_tin_terrain, {
            "points": FLAT_SQUARE,
            "op": "volume",
            "datum_z": 6.0,
        })
        assert result.get("ok") is True
        assert result["volume_m3"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# civil_crs_transform — scalar mode
# ---------------------------------------------------------------------------

class TestCRSTransformScalar:
    def test_wgs84_to_utm_zone_32n(self):
        # lon=9°E is the central meridian of UTM Zone 32N (EPSG:32632)
        result = _call(run_civil_crs_transform, {
            "x": 9.0,
            "y": 51.0,
            "from_crs": 4326,
            "to_crs": 32632,
        })
        assert result.get("ok") is True
        # Easting at central meridian = 500 000 m (exact by UTM definition)
        assert abs(result["x"] - 500_000.0) < 100.0
        assert result["y"] > 0  # Northern hemisphere

    def test_utm_to_wgs84_roundtrip(self):
        # Forward
        fwd = _call(run_civil_crs_transform, {
            "x": 13.4050, "y": 52.5200,  # Berlin
            "from_crs": 4326, "to_crs": 32633,
        })
        assert fwd.get("ok") is True
        # Inverse
        inv = _call(run_civil_crs_transform, {
            "x": fwd["x"], "y": fwd["y"],
            "from_crs": 32633, "to_crs": 4326,
        })
        assert inv.get("ok") is True
        assert abs(inv["x"] - 13.4050) < 0.001
        assert abs(inv["y"] - 52.5200) < 0.001

    def test_with_elevation(self):
        result = _call(run_civil_crs_transform, {
            "x": 18.9553, "y": 69.6492, "z": 50.0,  # Tromso, Norway
            "from_crs": 4326, "to_crs": 32633,
        })
        assert result.get("ok") is True
        assert "z" in result


# ---------------------------------------------------------------------------
# civil_crs_transform — batch mode
# ---------------------------------------------------------------------------

class TestCRSTransformBatch:
    def test_batch_two_points(self):
        result = _call(run_civil_crs_transform, {
            "xs": [13.4050, 2.3490],
            "ys": [52.5200, 48.8534],
            "from_crs": 4326,
            "to_crs": 32633,
        })
        assert result.get("ok") is True
        assert len(result["xs"]) == 2
        assert len(result["ys"]) == 2

    def test_missing_both_xy_and_xs(self):
        result = _call(run_civil_crs_transform, {
            "from_crs": 4326,
            "to_crs": 32632,
        })
        assert "error" in result
