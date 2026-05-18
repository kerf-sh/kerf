"""Tests for kerf_silicon.gds.reader — GDS-II binary parsing."""

from __future__ import annotations

import pytest

from kerf_silicon.gds.shapes import (
    Box, Cell, Library, Path, Point, Polygon, Reference, Text,
)
from kerf_silicon.gds.writer import write_library
from kerf_silicon.gds.reader import read_library


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_read(lib: Library) -> Library:
    """Write a library to bytes and parse it back."""
    return read_library(write_library(lib))


def _make_lib(*shapes, name: str = "TESTLIB", cell_name: str = "TOP") -> Library:
    lib = Library(name=name)
    cell = Cell(name=cell_name)
    for s in shapes:
        cell.add(s)
    lib.add_cell(cell)
    return lib


# ---------------------------------------------------------------------------
# Round-trip: write → read → byte-equal
# ---------------------------------------------------------------------------

class TestByteEqualRoundTrip:
    def test_single_box_byte_equal(self):
        """Write a 1-cell layout with 1 Box; round-trip must be byte-identical."""
        lib = _make_lib(
            Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(1000, 500))
        )
        original_bytes = write_library(lib)
        parsed_lib = read_library(original_bytes)
        re_encoded_bytes = write_library(parsed_lib)
        assert original_bytes == re_encoded_bytes, (
            "Round-trip did not produce byte-identical output for single-Box layout"
        )

    def test_empty_lib_byte_equal(self):
        lib = Library(name="EMPTY")
        original_bytes = write_library(lib)
        re_encoded_bytes = write_library(read_library(original_bytes))
        assert original_bytes == re_encoded_bytes

    def test_multi_cell_byte_equal(self):
        lib = Library(name="MULTI")
        for i in range(3):
            cell = Cell(name=f"CELL{i}")
            cell.add(Box(layer=i, datatype=0, p1=Point(0, 0), p2=Point(100 * (i + 1), 200)))
            lib.add_cell(cell)
        original = write_library(lib)
        assert write_library(read_library(original)) == original


# ---------------------------------------------------------------------------
# Structural checks after parsing
# ---------------------------------------------------------------------------

class TestLibraryParsing:
    def test_library_name(self):
        lib = _write_read(_make_lib(name="PARSEME"))
        assert lib.name == "PARSEME"

    def test_library_version(self):
        src = Library(name="V", version=5)
        lib = _write_read(src)
        assert lib.version == 5

    def test_library_units(self):
        src = Library(name="U", user_unit=1e-6, db_unit=1e-9)
        lib = _write_read(src)
        assert abs(lib.user_unit - 1e-6) / 1e-6 < 1e-9
        assert abs(lib.db_unit - 1e-9) / 1e-9 < 1e-9

    def test_cell_count(self):
        src = Library(name="C")
        src.add_cell(Cell(name="A"))
        src.add_cell(Cell(name="B"))
        lib = _write_read(src)
        assert len(lib.cells) == 2

    def test_cell_name(self):
        lib = _write_read(_make_lib(cell_name="MYCELLL"))
        assert lib.cells[0].name == "MYCELLL"


# ---------------------------------------------------------------------------
# Layer / datatype preservation
# ---------------------------------------------------------------------------

class TestLayerDatatypePersistence:
    @pytest.mark.parametrize("layer,datatype", [
        (0, 0),
        (1, 0),
        (63, 63),
        (255, 255),
        (10, 5),
    ])
    def test_box_layer_datatype(self, layer, datatype):
        lib = _make_lib(Box(layer=layer, datatype=datatype, p1=Point(0, 0), p2=Point(100, 100)))
        result = _write_read(lib)
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Box)
        assert shape.layer == layer
        assert shape.datatype == datatype

    def test_polygon_layer_datatype(self):
        pts = [Point(0, 0), Point(100, 0), Point(50, 100)]
        lib = _make_lib(Polygon(layer=11, datatype=7, points=pts))
        result = _write_read(lib)
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Polygon)
        assert shape.layer == 11
        assert shape.datatype == 7

    def test_path_layer_datatype(self):
        lib = _make_lib(
            Path(layer=9, datatype=2, points=[Point(0, 0), Point(500, 0)], width=25)
        )
        result = _write_read(lib)
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Path)
        assert shape.layer == 9
        assert shape.datatype == 2


# ---------------------------------------------------------------------------
# Shape round-trips
# ---------------------------------------------------------------------------

class TestShapeRoundTrip:
    def test_box_round_trip(self):
        src = Box(layer=1, datatype=0, p1=Point(10, 20), p2=Point(30, 40))
        result = _write_read(_make_lib(src))
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Box)
        assert shape.p1 == Point(10, 20)
        assert shape.p2 == Point(30, 40)

    def test_polygon_round_trip(self):
        pts = [Point(0, 0), Point(200, 0), Point(100, 150)]
        src = Polygon(layer=2, datatype=1, points=pts)
        result = _write_read(_make_lib(src))
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Polygon)
        # The polygon is stored closed; check the unique points match
        result_pts = shape.points
        # Remove closing duplicate if present
        if len(result_pts) > 1 and result_pts[0] == result_pts[-1]:
            result_pts = result_pts[:-1]
        assert set(result_pts) == set(pts)

    def test_path_round_trip(self):
        pts = [Point(0, 0), Point(500, 0), Point(500, 500)]
        src = Path(layer=3, datatype=0, points=pts, width=20)
        result = _write_read(_make_lib(src))
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Path)
        assert shape.width == 20
        assert shape.points == pts

    def test_text_round_trip(self):
        src = Text(layer=4, datatype=0, text="hello", position=Point(100, 200), texttype=1)
        result = _write_read(_make_lib(src))
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Text)
        assert shape.text == "hello"
        assert shape.position == Point(100, 200)
        assert shape.texttype == 1
        assert shape.layer == 4

    def test_reference_round_trip(self):
        src = Reference(
            cell_name="SUBCELL",
            position=Point(1000, 2000),
            rotation=90.0,
            magnification=2.0,
            mirror_x=True,
        )
        result = _write_read(_make_lib(src))
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Reference)
        assert shape.cell_name == "SUBCELL"
        assert shape.position == Point(1000, 2000)
        assert abs(shape.rotation - 90.0) < 1e-6
        assert abs(shape.magnification - 2.0) < 1e-6
        assert shape.mirror_x is True

    def test_reference_default_no_strans_flags(self):
        """A reference with default params (no mirror, no mag, no angle) round-trips."""
        src = Reference(cell_name="BASE", position=Point(0, 0))
        result = _write_read(_make_lib(src))
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Reference)
        assert shape.cell_name == "BASE"
        assert shape.mirror_x is False

    def test_multiple_shapes_order_preserved(self):
        shapes = [
            Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(100, 100)),
            Path(layer=2, datatype=0, points=[Point(0, 0), Point(100, 0)], width=5),
            Text(layer=3, text="lbl", position=Point(50, 50)),
        ]
        lib = _make_lib(*shapes)
        result = _write_read(lib)
        result_shapes = result.cells[0].shapes
        assert len(result_shapes) == 3
        assert isinstance(result_shapes[0], Box)
        assert isinstance(result_shapes[1], Path)
        assert isinstance(result_shapes[2], Text)


# ---------------------------------------------------------------------------
# Edge-cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_cell_round_trip(self):
        lib = Library(name="EMPTY_CELL")
        lib.add_cell(Cell(name="VOID"))
        result = _write_read(lib)
        assert len(result.cells) == 1
        assert len(result.cells[0].shapes) == 0

    def test_long_cell_name(self):
        # GDS-II cell names up to 32 chars
        name = "A" * 32
        lib = _make_lib(cell_name=name)
        result = _write_read(lib)
        assert result.cells[0].name == name

    def test_text_with_special_characters(self):
        # Printable ASCII only
        src = Text(layer=1, text="Test_Label-123", position=Point(0, 0))
        result = _write_read(_make_lib(src))
        assert result.cells[0].shapes[0].text == "Test_Label-123"

    def test_large_coordinates(self):
        # GDS-II uses int32 — max ~2.1 billion
        src = Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(2_000_000_000, 1_000_000_000))
        result = _write_read(_make_lib(src))
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Box)
        assert shape.p2.x == 2_000_000_000
        assert shape.p2.y == 1_000_000_000

    def test_negative_coordinates(self):
        src = Box(layer=1, datatype=0, p1=Point(-500, -300), p2=Point(500, 300))
        result = _write_read(_make_lib(src))
        shape = result.cells[0].shapes[0]
        assert isinstance(shape, Box)
        xs = {shape.p1.x, shape.p2.x}
        ys = {shape.p1.y, shape.p2.y}
        assert xs == {-500, 500}
        assert ys == {-300, 300}
