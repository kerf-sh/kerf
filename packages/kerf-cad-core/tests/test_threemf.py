"""Tests for 3MF read/write — GK-78.

Oracles:
1. write→read round-trip preserves V (vertices), F (faces), and per-face
   material id.
2. Thumbnail PNG bytes round-trip exactly.
3. A mesh with no materials/colours round-trips cleanly.
4. Colour-only (no materials) round-trip.
5. Top-level exports accessible from geom.__init__ and geom.io.__init__.
6. ThreeMFReadError raised on corrupt input.
"""

from __future__ import annotations

import pathlib
import struct
import tempfile
import zlib

import pytest

from kerf_cad_core.geom.io.threemf import (
    ThreeMFReadError,
    ThreeMFWriteError,
    read_threemf,
    write_threemf,
)
# Verify top-level re-exports
from kerf_cad_core.geom import (
    ThreeMFReadError as _ReadErrGeom,
    ThreeMFWriteError as _WriteErrGeom,
    read_threemf as _read_geom,
    write_threemf as _write_geom,
)
from kerf_cad_core.geom.io import (
    ThreeMFReadError as _ReadErrIO,
    ThreeMFWriteError as _WriteErrIO,
    read_threemf as _read_io,
    write_threemf as _write_io,
)


# ---------------------------------------------------------------------------
# Fixture: minimal unit-cube mesh (8 verts, 12 triangles)
# ---------------------------------------------------------------------------

_CUBE_VERTS = [
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [1.0, 1.0, 0.0],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0],
    [1.0, 0.0, 1.0],
    [1.0, 1.0, 1.0],
    [0.0, 1.0, 1.0],
]

_CUBE_FACES = [
    # bottom
    [0, 2, 1], [0, 3, 2],
    # top
    [4, 5, 6], [4, 6, 7],
    # front
    [0, 1, 5], [0, 5, 4],
    # back
    [2, 3, 7], [2, 7, 6],
    # left
    [0, 4, 7], [0, 7, 3],
    # right
    [1, 2, 6], [1, 6, 5],
]


def _make_minimal_png() -> bytes:
    """Return a minimal valid 1×1 white PNG."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return length + tag + data + crc

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1×1 RGB8
    raw = b"\x00\xff\xff\xff"
    idat = zlib.compress(raw)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """write→read round-trip correctness."""

    def test_bare_mesh_verts_faces(self, tmp_path: pathlib.Path) -> None:
        """V and F counts are preserved with no materials."""
        p = str(tmp_path / "cube.3mf")
        mesh = {"verts": _CUBE_VERTS, "faces": _CUBE_FACES}
        write_threemf(p, mesh)
        result = read_threemf(p)
        assert len(result["verts"]) == len(_CUBE_VERTS)
        assert len(result["faces"]) == len(_CUBE_FACES)

    def test_vertex_coordinates_preserved(self, tmp_path: pathlib.Path) -> None:
        """Vertex coordinates survive the XML round-trip within float precision."""
        p = str(tmp_path / "cube.3mf")
        mesh = {"verts": _CUBE_VERTS, "faces": _CUBE_FACES}
        write_threemf(p, mesh)
        result = read_threemf(p)
        for orig, rt in zip(_CUBE_VERTS, result["verts"]):
            assert abs(rt[0] - orig[0]) < 1e-6
            assert abs(rt[1] - orig[1]) < 1e-6
            assert abs(rt[2] - orig[2]) < 1e-6

    def test_face_indices_preserved(self, tmp_path: pathlib.Path) -> None:
        """Face vertex indices survive the round-trip exactly."""
        p = str(tmp_path / "cube.3mf")
        mesh = {"verts": _CUBE_VERTS, "faces": _CUBE_FACES}
        write_threemf(p, mesh)
        result = read_threemf(p)
        for orig, rt in zip(_CUBE_FACES, result["faces"]):
            assert orig == rt

    def test_per_face_material_id_preserved(self, tmp_path: pathlib.Path) -> None:
        """Per-face material ids survive the round-trip."""
        materials = [
            {"name": "red",   "r": 255, "g": 0,   "b": 0},
            {"name": "green", "r": 0,   "g": 255, "b": 0},
            {"name": "blue",  "r": 0,   "g": 0,   "b": 255},
        ]
        # Assign material 0 to first 4 faces, material 1 to next 4, material 2 to last 4
        face_material_ids = [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2]
        p = str(tmp_path / "cube_mat.3mf")
        mesh = {
            "verts": _CUBE_VERTS,
            "faces": _CUBE_FACES,
            "face_material_ids": face_material_ids,
        }
        write_threemf(p, mesh, materials=materials)
        result = read_threemf(p)

        assert len(result["materials"]) == 3
        assert result["materials"][0].get("name") == "red"
        assert result["materials"][1].get("name") == "green"
        assert result["materials"][2].get("name") == "blue"

        rt_ids = result["face_material_ids"]
        assert len(rt_ids) == len(_CUBE_FACES)
        for orig_id, rt_id in zip(face_material_ids, rt_ids):
            assert orig_id == rt_id, (
                f"face material id mismatch: wrote {orig_id}, read back {rt_id}"
            )

    def test_thumbnail_png_roundtrip(self, tmp_path: pathlib.Path) -> None:
        """Thumbnail PNG bytes survive the round-trip exactly."""
        png_bytes = _make_minimal_png()
        p = str(tmp_path / "thumb.3mf")
        mesh = {"verts": _CUBE_VERTS, "faces": _CUBE_FACES}
        write_threemf(p, mesh, thumbnail_png=png_bytes)
        result = read_threemf(p)
        assert result["thumbnail_png"] == png_bytes

    def test_no_thumbnail_returns_none(self, tmp_path: pathlib.Path) -> None:
        """Without a thumbnail, thumbnail_png is None."""
        p = str(tmp_path / "nothumb.3mf")
        mesh = {"verts": _CUBE_VERTS, "faces": _CUBE_FACES}
        write_threemf(p, mesh)
        result = read_threemf(p)
        assert result["thumbnail_png"] is None

    def test_colours_roundtrip(self, tmp_path: pathlib.Path) -> None:
        """Per-face colour list survives write (no crash) and the face count is intact."""
        colours = ["#ff0000", "#00ff00", "#0000ff"] * 4  # 12 colours for 12 faces
        p = str(tmp_path / "coloured.3mf")
        mesh = {"verts": _CUBE_VERTS, "faces": _CUBE_FACES}
        write_threemf(p, mesh, colours=colours)
        result = read_threemf(p)
        assert len(result["faces"]) == len(_CUBE_FACES)

    def test_metadata_roundtrip(self, tmp_path: pathlib.Path) -> None:
        """Metadata key/value pairs survive the round-trip."""
        meta = {"Title": "Unit Cube", "Designer": "GK-78 Test"}
        p = str(tmp_path / "meta.3mf")
        mesh = {"verts": _CUBE_VERTS, "faces": _CUBE_FACES}
        write_threemf(p, mesh, metadata=meta)
        result = read_threemf(p)
        assert result["metadata"].get("Title") == "Unit Cube"
        assert result["metadata"].get("Designer") == "GK-78 Test"

    def test_object_with_verts_faces_attrs(self, tmp_path: pathlib.Path) -> None:
        """write_threemf accepts an object with .verts / .faces attributes."""
        class Mesh:
            verts = _CUBE_VERTS
            faces = _CUBE_FACES

        p = str(tmp_path / "obj_attr.3mf")
        write_threemf(p, Mesh())
        result = read_threemf(p)
        assert len(result["verts"]) == len(_CUBE_VERTS)
        assert len(result["faces"]) == len(_CUBE_FACES)


class TestErrors:
    def test_read_nonexistent_file_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(ThreeMFReadError):
            read_threemf(str(tmp_path / "ghost.3mf"))

    def test_read_corrupt_zip_raises(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "bad.3mf"
        p.write_bytes(b"this is not a zip file")
        with pytest.raises(ThreeMFReadError):
            read_threemf(str(p))

    def test_write_invalid_mesh_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(ThreeMFWriteError):
            write_threemf(str(tmp_path / "bad.3mf"), "not a mesh")


class TestExports:
    """Verify that all four symbols are accessible from both __init__ paths."""

    def test_geom_init_exports(self) -> None:
        assert _ReadErrGeom is ThreeMFReadError
        assert _WriteErrGeom is ThreeMFWriteError
        assert _read_geom is read_threemf
        assert _write_geom is write_threemf

    def test_geom_io_init_exports(self) -> None:
        assert _ReadErrIO is ThreeMFReadError
        assert _WriteErrIO is ThreeMFWriteError
        assert _read_io is read_threemf
        assert _write_io is write_threemf
