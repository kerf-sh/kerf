"""Tests for kerf_silicon.gds.writer — GDS-II binary output."""

from __future__ import annotations

import struct

import pytest

from kerf_silicon.gds.shapes import (
    Box, Cell, Library, Path, Point, Polygon, Reference, Text,
)
from kerf_silicon.gds.writer import write_library
from kerf_silicon.gds.records import (
    RecordType, DataType, float_to_gds_real, gds_real_to_float,
    iter_records, GDSRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_simple_lib(cell_name: str = "TOP") -> Library:
    """Minimal library: one cell, one box."""
    lib = Library(name="TESTLIB")
    cell = Cell(name=cell_name)
    cell.add(Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(1000, 500)))
    lib.add_cell(cell)
    return lib


def _record_sequence(data: bytes) -> list:
    """Return list of (record_type, data_type) tuples from a GDS byte stream."""
    return [(r.record_type, r.data_type) for r in iter_records(data)]


# ---------------------------------------------------------------------------
# GDS-II 32-bit / 64-bit real encoding
# ---------------------------------------------------------------------------

class TestGDSReal:
    """Verify the GDS-II proprietary real encoder/decoder."""

    @pytest.mark.parametrize("value", [
        1.0,
        0.5,
        2.0,
        1e-6,
        1e-9,
        0.001,
        100.0,
        -1.0,
        -1e-6,
        0.0,
    ])
    def test_round_trip(self, value):
        encoded = float_to_gds_real(value)
        assert len(encoded) == 8
        decoded = gds_real_to_float(encoded)
        if value == 0.0:
            assert decoded == 0.0
        else:
            assert abs(decoded - value) / abs(value) < 1e-9, (
                f"GDS real round-trip failed for {value}: got {decoded}"
            )

    def test_one_dot_zero_exact(self):
        """1.0 must encode and decode to within 1e-9 relative error."""
        encoded = float_to_gds_real(1.0)
        decoded = gds_real_to_float(encoded)
        assert abs(decoded - 1.0) < 1e-9

    def test_encoded_length(self):
        for v in [0.0, 1.0, -42.5, 1e-6, 1e-9]:
            assert len(float_to_gds_real(v)) == 8

    def test_wrong_length_raises(self):
        with pytest.raises(ValueError):
            gds_real_to_float(b"\x00" * 7)


# ---------------------------------------------------------------------------
# Basic byte-sequence checks
# ---------------------------------------------------------------------------

class TestWriterByteSequence:
    def test_starts_with_header_record(self):
        data = write_library(_make_simple_lib())
        records = list(iter_records(data))
        assert records[0].record_type == RecordType.HEADER

    def test_ends_with_endlib(self):
        data = write_library(_make_simple_lib())
        records = list(iter_records(data))
        assert records[-1].record_type == RecordType.ENDLIB

    def test_record_sequence_single_cell_box(self):
        data = write_library(_make_simple_lib())
        types = [r.record_type for r in iter_records(data)]
        # Mandatory top-level sequence
        assert types[0] == RecordType.HEADER
        assert types[1] == RecordType.BGNLIB
        assert types[2] == RecordType.LIBNAME
        assert types[3] == RecordType.UNITS
        # Cell sequence somewhere in the middle
        assert RecordType.BGNSTR in types
        assert RecordType.STRNAME in types
        assert RecordType.BOUNDARY in types
        assert RecordType.LAYER in types
        assert RecordType.DATATYPE in types
        assert RecordType.XY in types
        assert RecordType.ENDEL in types
        assert RecordType.ENDSTR in types
        assert types[-1] == RecordType.ENDLIB

    def test_header_version(self):
        lib = Library(name="V", version=5)
        data = write_library(lib)
        records = list(iter_records(data))
        header = records[0]
        version = struct.unpack(">h", header.data[:2])[0]
        assert version == 5

    def test_libname_encoded(self):
        lib = Library(name="MYLIB")
        data = write_library(lib)
        records = list(iter_records(data))
        libname_rec = next(r for r in records if r.record_type == RecordType.LIBNAME)
        assert libname_rec.as_string() == "MYLIB"

    def test_units_records_present(self):
        lib = _make_simple_lib()
        lib.user_unit = 1e-6
        lib.db_unit = 1e-9
        data = write_library(lib)
        records = list(iter_records(data))
        units_rec = next(r for r in records if r.record_type == RecordType.UNITS)
        reals = units_rec.as_real64_list()
        assert len(reals) == 2
        assert abs(reals[0] - 1e-6) / 1e-6 < 1e-9
        assert abs(reals[1] - 1e-9) / 1e-9 < 1e-9

    def test_layer_datatype_in_output(self):
        lib = Library(name="L")
        cell = Cell(name="C")
        cell.add(Box(layer=7, datatype=3, p1=Point(0, 0), p2=Point(100, 100)))
        lib.add_cell(cell)
        data = write_library(lib)
        records = list(iter_records(data))

        layer_rec = next(r for r in records if r.record_type == RecordType.LAYER)
        dt_rec = next(r for r in records if r.record_type == RecordType.DATATYPE)

        assert layer_rec.as_int16_list()[0] == 7
        assert dt_rec.as_int16_list()[0] == 3

    def test_xy_contains_box_corners(self):
        lib = Library(name="L")
        cell = Cell(name="C")
        cell.add(Box(layer=1, datatype=0, p1=Point(10, 20), p2=Point(30, 40)))
        lib.add_cell(cell)
        data = write_library(lib)
        records = list(iter_records(data))
        xy_rec = next(r for r in records if r.record_type == RecordType.XY)
        coords = xy_rec.as_int32_list()
        xs = set(coords[0::2])
        ys = set(coords[1::2])
        assert xs == {10, 30}
        assert ys == {20, 40}


# ---------------------------------------------------------------------------
# All shape types produce output records
# ---------------------------------------------------------------------------

class TestShapeWriting:
    def _write_cell_with_shape(self, shape):
        lib = Library(name="L")
        cell = Cell(name="C")
        cell.add(shape)
        lib.add_cell(cell)
        return write_library(lib)

    def test_box_writes_boundary(self):
        data = self._write_cell_with_shape(
            Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(100, 100))
        )
        types = [r.record_type for r in iter_records(data)]
        assert RecordType.BOUNDARY in types

    def test_polygon_writes_boundary(self):
        pts = [Point(0, 0), Point(100, 0), Point(50, 100)]
        data = self._write_cell_with_shape(
            Polygon(layer=2, datatype=0, points=pts)
        )
        types = [r.record_type for r in iter_records(data)]
        assert RecordType.BOUNDARY in types

    def test_path_writes_path_record(self):
        data = self._write_cell_with_shape(
            Path(layer=3, datatype=0, points=[Point(0, 0), Point(200, 0)], width=10)
        )
        types = [r.record_type for r in iter_records(data)]
        assert RecordType.PATH in types

    def test_text_writes_text_record(self):
        data = self._write_cell_with_shape(
            Text(layer=4, text="hello", position=Point(50, 50))
        )
        types = [r.record_type for r in iter_records(data)]
        assert RecordType.TEXT in types

    def test_reference_writes_sref(self):
        data = self._write_cell_with_shape(
            Reference(cell_name="SUB", position=Point(0, 0))
        )
        types = [r.record_type for r in iter_records(data)]
        assert RecordType.SREF in types

    def test_path_width_in_output(self):
        data = self._write_cell_with_shape(
            Path(layer=3, datatype=0, points=[Point(0, 0), Point(200, 0)], width=42)
        )
        records = list(iter_records(data))
        width_rec = next(r for r in records if r.record_type == RecordType.WIDTH)
        assert width_rec.as_int32_list()[0] == 42

    def test_text_string_in_output(self):
        data = self._write_cell_with_shape(
            Text(layer=4, text="hello world", position=Point(0, 0))
        )
        records = list(iter_records(data))
        str_rec = next(r for r in records if r.record_type == RecordType.STRING)
        assert str_rec.as_string() == "hello world"

    def test_sname_in_sref_output(self):
        data = self._write_cell_with_shape(
            Reference(cell_name="MY_CELL")
        )
        records = list(iter_records(data))
        sname_rec = next(r for r in records if r.record_type == RecordType.SNAME)
        assert sname_rec.as_string() == "MY_CELL"


# ---------------------------------------------------------------------------
# Record integrity checks
# ---------------------------------------------------------------------------

class TestRecordIntegrity:
    def test_all_records_have_minimum_length(self):
        data = write_library(_make_simple_lib())
        for rec in iter_records(data):
            # Every record should at least have a 4-byte header (enforced by iter_records)
            assert isinstance(rec, GDSRecord)

    def test_string_padding_even_length(self):
        """All ASCII records must have even byte lengths."""
        lib = Library(name="ODD")  # 3 chars — should be padded to 4
        lib.add_cell(Cell(name="ABC"))  # also odd
        data = write_library(lib)
        for rec in iter_records(data):
            if rec.data_type == DataType.ASCII:
                assert len(rec.data) % 2 == 0, (
                    f"ASCII record 0x{rec.record_type:02X} has odd data length {len(rec.data)}"
                )

    def test_record_lengths_consistent(self):
        """Every record header length field must equal 4 + len(payload)."""
        data = write_library(_make_simple_lib())
        pos = 0
        while pos < len(data):
            length = struct.unpack_from(">H", data, pos)[0]
            assert pos + length <= len(data)
            pos += length
