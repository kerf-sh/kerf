"""Tests for kerf_silicon.gds.shapes — KLayout-compatible data model."""

from __future__ import annotations

import pytest

from kerf_silicon.gds.shapes import (
    Box, Cell, Library, Path, Point, Polygon, Reference, Text,
)


# ---------------------------------------------------------------------------
# Point
# ---------------------------------------------------------------------------

class TestPoint:
    def test_iteration(self):
        p = Point(3, 7)
        x, y = p
        assert x == 3 and y == 7

    def test_equality(self):
        assert Point(1, 2) == Point(1, 2)
        assert Point(1, 2) != Point(2, 1)

    def test_frozen(self):
        p = Point(0, 0)
        with pytest.raises((AttributeError, TypeError)):
            p.x = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Box
# ---------------------------------------------------------------------------

class TestBox:
    def test_polygon_points_count(self):
        b = Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(100, 50))
        pts = b.to_polygon_points()
        assert len(pts) == 5

    def test_polygon_points_closed(self):
        b = Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(100, 50))
        pts = b.to_polygon_points()
        assert pts[0] == pts[-1]

    def test_polygon_points_corners(self):
        b = Box(layer=2, datatype=1, p1=Point(10, 20), p2=Point(30, 40))
        pts = b.to_polygon_points()
        xs = {p.x for p in pts}
        ys = {p.y for p in pts}
        assert xs == {10, 30}
        assert ys == {20, 40}

    def test_layer_and_datatype(self):
        b = Box(layer=5, datatype=3, p1=Point(0, 0), p2=Point(1, 1))
        assert b.layer == 5
        assert b.datatype == 3


# ---------------------------------------------------------------------------
# Polygon
# ---------------------------------------------------------------------------

class TestPolygon:
    def test_closed_points_already_closed(self):
        pts = [Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 0)]
        poly = Polygon(layer=1, datatype=0, points=pts)
        closed = poly.closed_points()
        assert closed[-1] == closed[0]
        assert len(closed) == 4  # no extra point added when already closed

    def test_closed_points_open(self):
        pts = [Point(0, 0), Point(1, 0), Point(1, 1)]
        poly = Polygon(layer=1, datatype=0, points=pts)
        closed = poly.closed_points()
        assert len(closed) == 4
        assert closed[-1] == closed[0]

    def test_layer_and_datatype(self):
        poly = Polygon(layer=7, datatype=2, points=[Point(0, 0)])
        assert poly.layer == 7
        assert poly.datatype == 2


# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------

class TestPath:
    def test_defaults(self):
        path = Path(layer=3, datatype=0, points=[Point(0, 0), Point(100, 0)])
        assert path.width == 0

    def test_custom_width(self):
        path = Path(layer=3, datatype=0, points=[Point(0, 0), Point(100, 0)], width=20)
        assert path.width == 20


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

class TestText:
    def test_defaults(self):
        t = Text(layer=10)
        assert t.text == ""
        assert t.position == Point(0, 0)
        assert t.texttype == 0

    def test_custom_values(self):
        t = Text(layer=10, datatype=1, text="hello", position=Point(5, 10), texttype=2)
        assert t.text == "hello"
        assert t.position.x == 5 and t.position.y == 10


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------

class TestReference:
    def test_defaults(self):
        ref = Reference(cell_name="CELL_A")
        assert ref.position == Point(0, 0)
        assert ref.rotation == 0.0
        assert ref.magnification == 1.0
        assert ref.mirror_x is False

    def test_custom_values(self):
        ref = Reference(
            cell_name="CELL_B",
            position=Point(100, 200),
            rotation=90.0,
            magnification=2.5,
            mirror_x=True,
        )
        assert ref.cell_name == "CELL_B"
        assert ref.position == Point(100, 200)
        assert ref.rotation == 90.0
        assert ref.magnification == 2.5
        assert ref.mirror_x is True


# ---------------------------------------------------------------------------
# Cell / Library containers
# ---------------------------------------------------------------------------

class TestCell:
    def test_add_returns_self(self):
        c = Cell(name="TOP")
        result = c.add(Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(1, 1)))
        assert result is c

    def test_shapes_collected(self):
        c = Cell(name="TOP")
        c.add(Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(1, 1)))
        c.add(Text(layer=2, text="label"))
        assert len(c.shapes) == 2


class TestLibrary:
    def test_add_cell_returns_self(self):
        lib = Library(name="LIB")
        cell = Cell(name="TOP")
        result = lib.add_cell(cell)
        assert result is lib

    def test_cells_collected(self):
        lib = Library(name="LIB")
        lib.add_cell(Cell(name="A"))
        lib.add_cell(Cell(name="B"))
        assert len(lib.cells) == 2

    def test_default_units(self):
        lib = Library()
        assert lib.user_unit == pytest.approx(1e-6)
        assert lib.db_unit == pytest.approx(1e-9)
