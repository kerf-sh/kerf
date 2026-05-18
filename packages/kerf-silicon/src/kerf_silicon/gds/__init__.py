"""kerf_silicon.gds — Pure-Python GDS-II (Calma stream format) reader/writer.

Quick-start example::

    from kerf_silicon.gds import Library, Cell, Box, Point, write_library, read_library

    lib = Library(name="MYLIB")
    cell = Cell(name="TOP")
    cell.add(Box(layer=1, datatype=0, p1=Point(0, 0), p2=Point(1000, 500)))
    lib.add_cell(cell)

    gds_bytes = write_library(lib)
    lib2 = read_library(gds_bytes)
"""

from .shapes import Box, Polygon, Path, Text, Reference, Cell, Library, Point
from .writer import write_library
from .reader import read_library
from .records import (
    RecordType,
    DataType,
    float_to_gds_real,
    gds_real_to_float,
    GDSRecord,
    iter_records,
)

__all__ = [
    # shapes
    "Point",
    "Box",
    "Polygon",
    "Path",
    "Text",
    "Reference",
    "Cell",
    "Library",
    # I/O
    "write_library",
    "read_library",
    # low-level
    "RecordType",
    "DataType",
    "float_to_gds_real",
    "gds_real_to_float",
    "GDSRecord",
    "iter_records",
]
