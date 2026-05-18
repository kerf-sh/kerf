"""GDS-II binary stream writer — pure Python, Calma spec."""

from __future__ import annotations

import io
import struct
from typing import Union

from .records import (
    RecordType, DataType,
    pack_no_data, pack_int16, pack_int32, pack_real64, pack_ascii,
    pack_bitarray,
)
from .shapes import Box, Polygon, Path, Text, Reference, Cell, Library, Point


def _timestamp_words(
    year: int, month: int, day: int,
    hour: int, minute: int, second: int,
) -> list:
    return [year, month, day, hour, minute, second]


def write_library(library: Library) -> bytes:
    """Serialise a :class:`~kerf_silicon.gds.shapes.Library` to GDS-II bytes."""
    buf = io.BytesIO()

    def w(data: bytes) -> None:
        buf.write(data)

    # HEADER — version
    w(pack_int16(RecordType.HEADER, [library.version]))

    # BGNLIB — 12 int16 words: mod_datetime[6] + acc_datetime[6]
    lib_ts = _timestamp_words(
        library.mod_year, library.mod_month, library.mod_day,
        library.mod_hour, library.mod_minute, library.mod_second,
    ) + _timestamp_words(
        library.acc_year, library.acc_month, library.acc_day,
        library.acc_hour, library.acc_minute, library.acc_second,
    )
    w(pack_int16(RecordType.BGNLIB, lib_ts))

    # LIBNAME
    w(pack_ascii(RecordType.LIBNAME, library.name))

    # UNITS — two 8-byte GDS reals: user_unit/db_unit, db_unit (in metres)
    # First value: user unit in metres (e.g. 1e-6 for microns)
    # Second value: database unit in metres (precision)
    w(pack_real64(RecordType.UNITS, [library.user_unit, library.db_unit]))

    # Cells
    for cell in library.cells:
        _write_cell(buf, cell)

    # ENDLIB
    w(pack_no_data(RecordType.ENDLIB))

    return buf.getvalue()


def _write_cell(buf: io.BytesIO, cell: Cell) -> None:
    def w(data: bytes) -> None:
        buf.write(data)

    # BGNSTR — 12 int16 timestamp words
    cell_ts = _timestamp_words(
        cell.mod_year, cell.mod_month, cell.mod_day,
        cell.mod_hour, cell.mod_minute, cell.mod_second,
    ) + _timestamp_words(
        cell.acc_year, cell.acc_month, cell.acc_day,
        cell.acc_hour, cell.acc_minute, cell.acc_second,
    )
    w(pack_int16(RecordType.BGNSTR, cell_ts))

    # STRNAME
    w(pack_ascii(RecordType.STRNAME, cell.name))

    # Shapes
    for shape in cell.shapes:
        if isinstance(shape, Box):
            _write_box(buf, shape)
        elif isinstance(shape, Polygon):
            _write_polygon(buf, shape)
        elif isinstance(shape, Path):
            _write_path(buf, shape)
        elif isinstance(shape, Text):
            _write_text(buf, shape)
        elif isinstance(shape, Reference):
            _write_reference(buf, shape)
        else:
            raise TypeError(f"Unknown shape type: {type(shape)}")

    # ENDSTR
    w(pack_no_data(RecordType.ENDSTR))


def _flatten_xy(points: list) -> list:
    """Flatten a list of Points to [x0, y0, x1, y1, ...] int32 list."""
    flat = []
    for pt in points:
        flat.append(int(pt.x))
        flat.append(int(pt.y))
    return flat


def _write_box(buf: io.BytesIO, box: Box) -> None:
    def w(data: bytes) -> None:
        buf.write(data)

    w(pack_no_data(RecordType.BOUNDARY))
    w(pack_int16(RecordType.LAYER, [box.layer]))
    w(pack_int16(RecordType.DATATYPE, [box.datatype]))
    pts = box.to_polygon_points()
    w(pack_int32(RecordType.XY, _flatten_xy(pts)))
    w(pack_no_data(RecordType.ENDEL))


def _write_polygon(buf: io.BytesIO, poly: Polygon) -> None:
    def w(data: bytes) -> None:
        buf.write(data)

    w(pack_no_data(RecordType.BOUNDARY))
    w(pack_int16(RecordType.LAYER, [poly.layer]))
    w(pack_int16(RecordType.DATATYPE, [poly.datatype]))
    pts = poly.closed_points()
    w(pack_int32(RecordType.XY, _flatten_xy(pts)))
    w(pack_no_data(RecordType.ENDEL))


def _write_path(buf: io.BytesIO, path: Path) -> None:
    def w(data: bytes) -> None:
        buf.write(data)

    w(pack_no_data(RecordType.PATH))
    w(pack_int16(RecordType.LAYER, [path.layer]))
    w(pack_int16(RecordType.DATATYPE, [path.datatype]))
    w(pack_int32(RecordType.WIDTH, [path.width]))
    w(pack_int32(RecordType.XY, _flatten_xy(path.points)))
    w(pack_no_data(RecordType.ENDEL))


def _write_text(buf: io.BytesIO, text: Text) -> None:
    def w(data: bytes) -> None:
        buf.write(data)

    w(pack_no_data(RecordType.TEXT))
    w(pack_int16(RecordType.LAYER, [text.layer]))
    w(pack_int16(RecordType.TEXTTYPE, [text.texttype]))
    w(pack_int32(RecordType.XY, [text.position.x, text.position.y]))
    w(pack_ascii(RecordType.STRING, text.text))
    w(pack_no_data(RecordType.ENDEL))


def _write_reference(buf: io.BytesIO, ref: Reference) -> None:
    def w(data: bytes) -> None:
        buf.write(data)

    w(pack_no_data(RecordType.SREF))
    w(pack_ascii(RecordType.SNAME, ref.cell_name))

    # STRANS flags: bit 15 = mirror X, rest = 0
    strans = 0x8000 if ref.mirror_x else 0x0000
    w(pack_bitarray(RecordType.STRANS, strans))

    # MAG (magnification)
    if ref.magnification != 1.0:
        from .records import pack_real64 as _pr64
        w(_pr64(RecordType.MAG, [ref.magnification]))

    # ANGLE (rotation in degrees)
    if ref.rotation != 0.0:
        from .records import pack_real64 as _pr64
        w(_pr64(RecordType.ANGLE, [ref.rotation]))

    w(pack_int32(RecordType.XY, [ref.position.x, ref.position.y]))
    w(pack_no_data(RecordType.ENDEL))
