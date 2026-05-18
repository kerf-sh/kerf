"""test_routes_silicon.py — Hermetic pytest suite for POST /api/silicon/gds/parse.

Generates a synthetic 1-cell GDS-II fixture using the kerf_silicon writer,
POSTs it to the route via FastAPI TestClient, and verifies the returned
layout-shapes JSON matches expectations.

No database, no filesystem, no external services required.

Run:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-silicon/src:packages/kerf-api/src \
        python3 -m pytest packages/kerf-api/tests/test_routes_silicon.py -x
"""

from __future__ import annotations

import io
import sys
import pathlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# sys.path bootstrap (mirrors conftest.py)
# ---------------------------------------------------------------------------

_HERE = pathlib.Path(__file__).parent
_PACKAGES_ROOT = _HERE.parent.parent

for _entry in _PACKAGES_ROOT.iterdir():
    if not _entry.name.startswith("kerf-"):
        continue
    _src = _entry / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))


# ---------------------------------------------------------------------------
# Test app — silicon router only, no DB
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    from kerf_api.routes_silicon import router as silicon_router

    app = FastAPI()
    app.include_router(silicon_router, prefix="/api", tags=["silicon"])
    return app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_build_app())


# ---------------------------------------------------------------------------
# GDS fixture builder
# ---------------------------------------------------------------------------

def _make_gds_bytes() -> bytes:
    """Return a minimal 1-cell GDS-II byte stream with various shape kinds."""
    from kerf_silicon.gds.shapes import Library, Cell, Box, Polygon, Path, Text, Point
    from kerf_silicon.gds.writer import write_library

    lib = Library(name="TESTLIB", user_unit=1e-6, db_unit=1e-9)
    cell = Cell(name="TOP")

    # Box on met1 (layer 68, datatype 20)
    cell.add(Box(layer=68, datatype=20, p1=Point(0, 0), p2=Point(1000, 500)))

    # Polygon on poly (layer 66, datatype 20) — non-rectangular so reader keeps it as Polygon
    cell.add(Polygon(
        layer=66,
        datatype=20,
        points=[Point(100, 100), Point(250, 120), Point(300, 200), Point(150, 250), Point(80, 180)],
    ))

    # Path on li1 (layer 67, datatype 20)
    cell.add(Path(
        layer=67,
        datatype=20,
        points=[Point(0, 0), Point(500, 0), Point(500, 300)],
        width=50,
    ))

    # Text label
    cell.add(Text(layer=83, datatype=0, text="TOP_LABEL", position=Point(10, 10)))

    lib.cells.append(cell)
    return write_library(lib)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGdsParse:
    def test_returns_200(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"

    def test_response_has_cells_key(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        body = r.json()
        assert "cells" in body, f"missing 'cells' key: {body}"
        assert isinstance(body["cells"], list)
        assert len(body["cells"]) == 1

    def test_cell_name_is_top(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        body = r.json()
        assert body["cells"][0]["name"] == "TOP"

    def test_top_cell_is_top(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        body = r.json()
        assert body.get("topCell") == "TOP"

    def test_box_shape_present(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        body = r.json()
        shapes = body["cells"][0]["shapes"]
        boxes = [s for s in shapes if s["kind"] == "box"]
        assert len(boxes) >= 1, "expected at least one box shape"
        box = boxes[0]
        assert box["layer"] == 68
        assert box["w"] == 1000
        assert box["h"] == 500

    def test_polygon_shape_present(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        body = r.json()
        shapes = body["cells"][0]["shapes"]
        polys = [s for s in shapes if s["kind"] == "polygon"]
        assert len(polys) >= 1, "expected at least one polygon shape"
        assert polys[0]["layer"] == 66
        assert isinstance(polys[0]["points"], list)

    def test_path_shape_present(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        body = r.json()
        shapes = body["cells"][0]["shapes"]
        paths = [s for s in shapes if s["kind"] == "path"]
        assert len(paths) >= 1, "expected at least one path shape"
        assert paths[0]["layer"] == 67
        assert paths[0]["width"] == 50

    def test_text_shape_present(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        body = r.json()
        shapes = body["cells"][0]["shapes"]
        texts = [s for s in shapes if s["kind"] == "text"]
        assert len(texts) >= 1, "expected at least one text shape"
        assert texts[0]["label"] == "TOP_LABEL"
        assert texts[0]["layer"] == 83

    def test_layers_list(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        body = r.json()
        assert "layers" in body
        layer_nums = {lyr["layer"] for lyr in body["layers"]}
        # met1 (68), poly (66), li1 (67), text (83)
        assert 68 in layer_nums
        assert 66 in layer_nums
        assert 67 in layer_nums

    def test_units_in_response(self, client: TestClient):
        gds = _make_gds_bytes()
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("test.gds", io.BytesIO(gds), "application/octet-stream")},
        )
        body = r.json()
        assert "db_unit" in body
        assert "user_unit" in body
        assert body["db_unit"] == pytest.approx(1e-9)
        assert body["user_unit"] == pytest.approx(1e-6)

    def test_empty_file_returns_422(self, client: TestClient):
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("empty.gds", io.BytesIO(b""), "application/octet-stream")},
        )
        assert r.status_code == 422

    def test_invalid_bytes_returns_422(self, client: TestClient):
        r = client.post(
            "/api/silicon/gds/parse",
            files={"file": ("bad.gds", io.BytesIO(b"NOT GDS DATA"), "application/octet-stream")},
        )
        assert r.status_code == 422


class TestConvertShape:
    """Unit-test the shape-conversion helpers in isolation."""

    def test_box_conversion(self):
        from kerf_api.routes_silicon import _convert_shape
        from kerf_silicon.gds.shapes import Box, Point

        box = Box(layer=68, datatype=20, p1=Point(10, 20), p2=Point(110, 70))
        result = _convert_shape(box)
        assert result["kind"] == "box"
        assert result["layer"] == 68
        assert result["x"] == 10
        assert result["y"] == 20
        assert result["w"] == 100
        assert result["h"] == 50

    def test_polygon_conversion(self):
        from kerf_api.routes_silicon import _convert_shape
        from kerf_silicon.gds.shapes import Polygon, Point

        poly = Polygon(layer=66, datatype=20, points=[Point(0, 0), Point(10, 0), Point(10, 10)])
        result = _convert_shape(poly)
        assert result["kind"] == "polygon"
        assert result["layer"] == 66
        assert len(result["points"]) == 3
        assert result["points"][0] == {"x": 0, "y": 0}

    def test_path_conversion(self):
        from kerf_api.routes_silicon import _convert_shape
        from kerf_silicon.gds.shapes import Path, Point

        path = Path(layer=67, datatype=20, points=[Point(0, 0), Point(100, 0)], width=30)
        result = _convert_shape(path)
        assert result["kind"] == "path"
        assert result["width"] == 30
        assert len(result["points"]) == 2

    def test_text_conversion(self):
        from kerf_api.routes_silicon import _convert_shape
        from kerf_silicon.gds.shapes import Text, Point

        txt = Text(layer=83, datatype=0, text="HELLO", position=Point(5, 7))
        result = _convert_shape(txt)
        assert result["kind"] == "text"
        assert result["label"] == "HELLO"
        assert result["x"] == 5
        assert result["y"] == 7

    def test_reference_conversion(self):
        from kerf_api.routes_silicon import _convert_shape
        from kerf_silicon.gds.shapes import Reference, Point

        ref = Reference(cell_name="CHILD", position=Point(100, 200), rotation=90.0)
        result = _convert_shape(ref)
        assert result["kind"] == "ref"
        assert result["cell"] == "CHILD"
        assert result["x"] == 100
        assert result["y"] == 200
        assert result["rotation"] == pytest.approx(90.0)
