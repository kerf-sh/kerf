"""GDS-II binary stream reader — pure Python, Calma spec."""

from __future__ import annotations

from typing import List, Optional

from .records import (
    RecordType, DataType,
    GDSRecord, iter_records,
    gds_real_to_float,
)
from .shapes import Box, Polygon, Path, Text, Reference, Cell, Library, Point


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_library(data: bytes) -> Library:
    """Parse a GDS-II byte stream and return a :class:`~kerf_silicon.gds.shapes.Library`."""
    records = list(iter_records(data))
    parser = _GDSParser(records)
    return parser.parse()


# ---------------------------------------------------------------------------
# Internal parser
# ---------------------------------------------------------------------------

class _GDSParser:
    def __init__(self, records: List[GDSRecord]) -> None:
        self._records = records
        self._pos = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _peek(self) -> Optional[GDSRecord]:
        if self._pos < len(self._records):
            return self._records[self._pos]
        return None

    def _next(self) -> GDSRecord:
        rec = self._records[self._pos]
        self._pos += 1
        return rec

    def _expect(self, record_type: int) -> GDSRecord:
        rec = self._next()
        if rec.record_type != record_type:
            raise ValueError(
                f"Expected record type 0x{record_type:02X} but got "
                f"0x{rec.record_type:02X} at record index {self._pos - 1}"
            )
        return rec

    def _consume_optional(self, record_type: int) -> Optional[GDSRecord]:
        rec = self._peek()
        if rec is not None and rec.record_type == record_type:
            return self._next()
        return None

    # ------------------------------------------------------------------
    # Top-level library parse
    # ------------------------------------------------------------------

    def parse(self) -> Library:
        lib = Library()

        # HEADER
        rec = self._expect(RecordType.HEADER)
        versions = rec.as_int16_list()
        lib.version = versions[0] if versions else 5

        # BGNLIB
        rec = self._expect(RecordType.BGNLIB)
        ts = rec.as_int16_list()
        if len(ts) >= 12:
            (lib.mod_year, lib.mod_month, lib.mod_day,
             lib.mod_hour, lib.mod_minute, lib.mod_second,
             lib.acc_year, lib.acc_month, lib.acc_day,
             lib.acc_hour, lib.acc_minute, lib.acc_second) = ts[:12]

        # LIBNAME
        rec = self._expect(RecordType.LIBNAME)
        lib.name = rec.as_string()

        # Optional REFLIBS, FONTS, ATTRTABLE, GENERATIONS — skip them
        _SKIP_BEFORE_UNITS = {
            RecordType.REFLIBS, RecordType.FONTS, RecordType.ATTRTABLE,
            RecordType.GENERATIONS, RecordType.SPACING,
        }
        while self._peek() and self._peek().record_type in _SKIP_BEFORE_UNITS:
            self._next()

        # UNITS
        rec = self._expect(RecordType.UNITS)
        reals = rec.as_real64_list()
        if len(reals) >= 2:
            lib.user_unit = reals[0]
            lib.db_unit = reals[1]
        elif len(reals) == 1:
            lib.user_unit = reals[0]

        # Cells
        while self._peek() and self._peek().record_type == RecordType.BGNSTR:
            lib.cells.append(self._parse_cell())

        # ENDLIB
        self._expect(RecordType.ENDLIB)

        return lib

    # ------------------------------------------------------------------
    # Cell (structure) parse
    # ------------------------------------------------------------------

    def _parse_cell(self) -> Cell:
        cell = Cell(name="")

        rec = self._expect(RecordType.BGNSTR)
        ts = rec.as_int16_list()
        if len(ts) >= 12:
            (cell.mod_year, cell.mod_month, cell.mod_day,
             cell.mod_hour, cell.mod_minute, cell.mod_second,
             cell.acc_year, cell.acc_month, cell.acc_day,
             cell.acc_hour, cell.acc_minute, cell.acc_second) = ts[:12]

        rec = self._expect(RecordType.STRNAME)
        cell.name = rec.as_string()

        # Parse elements until ENDSTR
        while True:
            peek = self._peek()
            if peek is None:
                raise ValueError("Unexpected end of records while parsing cell")
            if peek.record_type == RecordType.ENDSTR:
                self._next()
                break

            rt = peek.record_type
            if rt == RecordType.BOUNDARY:
                cell.shapes.append(self._parse_boundary())
            elif rt == RecordType.PATH:
                cell.shapes.append(self._parse_path())
            elif rt == RecordType.TEXT:
                cell.shapes.append(self._parse_text())
            elif rt == RecordType.SREF:
                cell.shapes.append(self._parse_sref())
            elif rt == RecordType.AREF:
                # AREF — skip for now (not in scope)
                self._skip_element()
            else:
                # Unknown element — skip until ENDEL
                self._skip_element()

        return cell

    def _skip_element(self) -> None:
        """Consume records until (and including) ENDEL."""
        while True:
            rec = self._next()
            if rec.record_type == RecordType.ENDEL:
                break

    # ------------------------------------------------------------------
    # Element parsers
    # ------------------------------------------------------------------

    def _parse_boundary(self) -> Polygon:
        """Parse a BOUNDARY element into a Polygon (or Box if rectangular)."""
        self._expect(RecordType.BOUNDARY)

        layer = 0
        datatype = 0
        points: List[Point] = []

        # Consume element records until ENDEL
        while True:
            rec = self._next()
            if rec.record_type == RecordType.ENDEL:
                break
            elif rec.record_type == RecordType.LAYER:
                layer = rec.as_int16_list()[0]
            elif rec.record_type == RecordType.DATATYPE:
                datatype = rec.as_int16_list()[0]
            elif rec.record_type == RecordType.XY:
                coords = rec.as_int32_list()
                points = [
                    Point(coords[i], coords[i + 1])
                    for i in range(0, len(coords) - 1, 2)
                ]
            # Skip any other records (ELFLAGS, PLEX, etc.)

        # Detect if this was written as a Box (5-point rectangle)
        if _is_box_polygon(points):
            xs = [p.x for p in points[:4]]
            ys = [p.y for p in points[:4]]
            return Box(
                layer=layer,
                datatype=datatype,
                p1=Point(min(xs), min(ys)),
                p2=Point(max(xs), max(ys)),
            )

        return Polygon(layer=layer, datatype=datatype, points=points)

    def _parse_path(self) -> Path:
        self._expect(RecordType.PATH)

        layer = 0
        datatype = 0
        width = 0
        points: List[Point] = []

        while True:
            rec = self._next()
            if rec.record_type == RecordType.ENDEL:
                break
            elif rec.record_type == RecordType.LAYER:
                layer = rec.as_int16_list()[0]
            elif rec.record_type == RecordType.DATATYPE:
                datatype = rec.as_int16_list()[0]
            elif rec.record_type == RecordType.WIDTH:
                width = rec.as_int32_list()[0]
            elif rec.record_type == RecordType.XY:
                coords = rec.as_int32_list()
                points = [
                    Point(coords[i], coords[i + 1])
                    for i in range(0, len(coords) - 1, 2)
                ]

        return Path(layer=layer, datatype=datatype, points=points, width=width)

    def _parse_text(self) -> Text:
        self._expect(RecordType.TEXT)

        layer = 0
        datatype = 0
        texttype = 0
        position = Point(0, 0)
        string = ""

        while True:
            rec = self._next()
            if rec.record_type == RecordType.ENDEL:
                break
            elif rec.record_type == RecordType.LAYER:
                layer = rec.as_int16_list()[0]
            elif rec.record_type == RecordType.DATATYPE:
                datatype = rec.as_int16_list()[0]
            elif rec.record_type == RecordType.TEXTTYPE:
                texttype = rec.as_int16_list()[0]
            elif rec.record_type == RecordType.XY:
                coords = rec.as_int32_list()
                if len(coords) >= 2:
                    position = Point(coords[0], coords[1])
            elif rec.record_type == RecordType.STRING:
                string = rec.as_string()

        return Text(
            layer=layer,
            datatype=datatype,
            text=string,
            position=position,
            texttype=texttype,
        )

    def _parse_sref(self) -> Reference:
        self._expect(RecordType.SREF)

        cell_name = ""
        position = Point(0, 0)
        rotation = 0.0
        magnification = 1.0
        mirror_x = False

        while True:
            rec = self._next()
            if rec.record_type == RecordType.ENDEL:
                break
            elif rec.record_type == RecordType.SNAME:
                cell_name = rec.as_string()
            elif rec.record_type == RecordType.STRANS:
                flags = rec.as_bitarray()
                mirror_x = bool(flags & 0x8000)
            elif rec.record_type == RecordType.MAG:
                reals = rec.as_real64_list()
                if reals:
                    magnification = reals[0]
            elif rec.record_type == RecordType.ANGLE:
                reals = rec.as_real64_list()
                if reals:
                    rotation = reals[0]
            elif rec.record_type == RecordType.XY:
                coords = rec.as_int32_list()
                if len(coords) >= 2:
                    position = Point(coords[0], coords[1])

        return Reference(
            cell_name=cell_name,
            position=position,
            rotation=rotation,
            magnification=magnification,
            mirror_x=mirror_x,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_box_polygon(points: List[Point]) -> bool:
    """Return True if the point list is a closed axis-aligned rectangle (5 pts)."""
    # A Box written by this library produces exactly 5 points where first==last
    # and the 4 unique points form an axis-aligned rectangle.
    if len(points) != 5:
        return False
    if points[0] != points[4]:
        return False
    pts = points[:4]
    xs = {p.x for p in pts}
    ys = {p.y for p in pts}
    return len(xs) == 2 and len(ys) == 2
