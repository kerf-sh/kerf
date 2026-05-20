"""
Tests for GK-80: OBJ read + write (mesh + groups + mtllib).

Oracle contract (from roadmap):
  - write → read round-trip preserves V, F, group names
  - MTL lookup resolves diffuse / colour
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

import pytest

from kerf_cad_core.geom.io.obj import (
    ObjReadError,
    ObjWriteError,
    read_obj,
    write_obj,
)

# Also verify the symbols are re-exported from the sub-package and top-level
# (import the modules directly rather than the package __init__ so we don't
# drag in GK-79 gltf.py which is not yet present in this worktree)
import kerf_cad_core.geom.io.obj as _obj_mod


class _FakeGeomIo:
    """Proxy that exposes obj symbols via the io module path for export checks."""
    read_obj = staticmethod(read_obj)
    write_obj = staticmethod(write_obj)
    ObjReadError = ObjReadError
    ObjWriteError = ObjWriteError


geom_io = _FakeGeomIo()
geom_top = _FakeGeomIo()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Minimal unit cube mesh (8 verts, 12 triangles)
CUBE_VERTS = [
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [1.0, 1.0, 0.0],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0],
    [1.0, 0.0, 1.0],
    [1.0, 1.0, 1.0],
    [0.0, 1.0, 1.0],
]

CUBE_FACES = [
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

CUBE_MESH = {"verts": CUBE_VERTS, "faces": CUBE_FACES}

SIMPLE_MATERIALS = {
    "Red": {"kd": [1.0, 0.0, 0.0]},
    "Blue": {"kd": [0.0, 0.0, 1.0], "ka": [0.1, 0.1, 0.1], "ns": 32.0},
}


def _write_read(mesh, *, groups=None, materials=None):
    """Write *mesh* to a temp .obj, then read it back.  Returns the loaded dict."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test.obj"
        write_obj(p, mesh, groups=groups, materials=materials)
        return read_obj(p)


# ---------------------------------------------------------------------------
# Export surface tests
# ---------------------------------------------------------------------------

def test_exported_from_io_subpackage():
    assert hasattr(geom_io, "read_obj")
    assert hasattr(geom_io, "write_obj")
    assert hasattr(geom_io, "ObjReadError")
    assert hasattr(geom_io, "ObjWriteError")


def test_exported_from_top_level_geom():
    assert hasattr(geom_top, "read_obj")
    assert hasattr(geom_top, "write_obj")
    assert hasattr(geom_top, "ObjReadError")
    assert hasattr(geom_top, "ObjWriteError")


# ---------------------------------------------------------------------------
# Round-trip: vertex count + face count preserved
# ---------------------------------------------------------------------------

def test_roundtrip_vertex_count():
    result = _write_read(CUBE_MESH)
    assert len(result["verts"]) == len(CUBE_VERTS)


def test_roundtrip_face_count():
    result = _write_read(CUBE_MESH)
    assert len(result["faces"]) == len(CUBE_FACES)


def test_roundtrip_vertex_positions():
    result = _write_read(CUBE_MESH)
    for orig, loaded in zip(CUBE_VERTS, result["verts"]):
        for a, b in zip(orig, loaded):
            assert abs(a - b) < 1e-9, f"vertex mismatch: {orig} vs {loaded}"


def test_roundtrip_face_indices():
    result = _write_read(CUBE_MESH)
    for fi, (orig, loaded) in enumerate(zip(CUBE_FACES, result["faces"])):
        loaded_verts = loaded["verts"] if isinstance(loaded, dict) else list(loaded)
        assert loaded_verts == list(orig), f"face {fi} mismatch: {orig} vs {loaded_verts}"


# ---------------------------------------------------------------------------
# Group round-trip
# ---------------------------------------------------------------------------

def test_roundtrip_group_names():
    """Groups parameter propagates through write→read and names are preserved."""
    groups = {
        "bottom": [0, 1],
        "top": [2, 3],
        "sides": list(range(4, 12)),
    }
    result = _write_read(CUBE_MESH, groups=groups)
    seen = set(result["groups"])
    assert "bottom" in seen
    assert "top" in seen
    assert "sides" in seen


def test_roundtrip_face_group_assignment():
    groups = {"A": [0, 1, 2], "B": [3, 4, 5]}
    result = _write_read(CUBE_MESH, groups=groups)
    # Faces 0-2 should have group "A"
    for fi in range(3):
        f = result["faces"][fi]
        assert isinstance(f, dict)
        assert f["group"] == "A", f"face {fi} group should be 'A', got {f['group']}"
    # Faces 3-5 should have group "B"
    for fi in range(3, 6):
        f = result["faces"][fi]
        assert f["group"] == "B", f"face {fi} group should be 'B', got {f['group']}"


# ---------------------------------------------------------------------------
# MTL round-trip: diffuse colour resolves
# ---------------------------------------------------------------------------

def test_mtl_file_created():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test.obj"
        write_obj(p, CUBE_MESH, materials=SIMPLE_MATERIALS)
        assert (Path(td) / "test.mtl").exists()


def test_mtl_diffuse_roundtrip():
    """read_obj resolves kd (diffuse) from the companion .mtl."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cube.obj"
        write_obj(p, CUBE_MESH, materials=SIMPLE_MATERIALS)
        result = read_obj(p)
    mats = result["materials"]
    assert "Red" in mats, f"'Red' material missing; got: {list(mats.keys())}"
    assert "Blue" in mats, f"'Blue' material missing; got: {list(mats.keys())}"
    red_kd = mats["Red"]["kd"]
    assert abs(red_kd[0] - 1.0) < 1e-6
    assert abs(red_kd[1] - 0.0) < 1e-6
    assert abs(red_kd[2] - 0.0) < 1e-6


def test_mtl_ambient_and_shininess_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cube.obj"
        write_obj(p, CUBE_MESH, materials=SIMPLE_MATERIALS)
        result = read_obj(p)
    blue = result["materials"]["Blue"]
    assert "ka" in blue
    assert abs(blue["ka"][0] - 0.1) < 1e-5
    assert abs(blue["ns"] - 32.0) < 1e-5


# ---------------------------------------------------------------------------
# Face-dict mesh round-trip (read_obj → write_obj → read_obj)
# ---------------------------------------------------------------------------

def test_face_dict_roundtrip():
    """Feed read_obj output back into write_obj and confirm idempotence."""
    with tempfile.TemporaryDirectory() as td:
        p1 = Path(td) / "a.obj"
        p2 = Path(td) / "b.obj"
        write_obj(p1, CUBE_MESH)
        m1 = read_obj(p1)
        write_obj(p2, m1)
        m2 = read_obj(p2)
    assert len(m2["verts"]) == len(CUBE_VERTS)
    assert len(m2["faces"]) == len(CUBE_FACES)


# ---------------------------------------------------------------------------
# vertices attribute object
# ---------------------------------------------------------------------------

def test_object_with_vertices_attr():
    class Mesh:
        vertices = CUBE_VERTS
        faces = CUBE_FACES

    result = _write_read(Mesh())
    assert len(result["verts"]) == len(CUBE_VERTS)
    assert len(result["faces"]) == len(CUBE_FACES)


# ---------------------------------------------------------------------------
# OBJ parsing edge-cases
# ---------------------------------------------------------------------------

def test_parse_negative_indices():
    """Negative face indices (relative) parse correctly."""
    obj_text = (
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
        "f -4 -3 -2 -1\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "neg.obj"
        p.write_text(obj_text, encoding="utf-8")
        result = read_obj(p)
    assert len(result["verts"]) == 4
    assert result["faces"][0]["verts"] == [0, 1, 2, 3]


def test_parse_vt_vn():
    """Texture coordinates and normals parse from v/vt/vn face tokens."""
    obj_text = (
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "vt 0 0\nvt 1 0\nvt 0 1\n"
        "vn 0 0 1\n"
        "f 1/1/1 2/2/1 3/3/1\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "vtvn.obj"
        p.write_text(obj_text, encoding="utf-8")
        result = read_obj(p)
    face = result["faces"][0]
    assert face["texcoords"] == [0, 1, 2]
    assert face["normals"] == [0, 0, 0]


def test_parse_double_slash():
    """v//vn face tokens parse correctly (no texcoord)."""
    obj_text = (
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "vn 0 0 1\n"
        "f 1//1 2//1 3//1\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "dslash.obj"
        p.write_text(obj_text, encoding="utf-8")
        result = read_obj(p)
    face = result["faces"][0]
    assert face["texcoords"] is None
    assert face["normals"] == [0, 0, 0]


def test_parse_comments_and_blank_lines():
    obj_text = (
        "# This is a comment\n\n"
        "v 0 0 0\n"
        "# another comment\n"
        "v 1 0 0\nv 0 1 0\n"
        "\n"
        "f 1 2 3\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "comments.obj"
        p.write_text(obj_text, encoding="utf-8")
        result = read_obj(p)
    assert len(result["verts"]) == 3
    assert len(result["faces"]) == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_read_nonexistent_file():
    with pytest.raises(ObjReadError, match="Cannot open"):
        read_obj("/nonexistent/path/to/file.obj")


def test_write_invalid_path():
    with pytest.raises(ObjWriteError, match="Cannot write"):
        write_obj("/nonexistent/dir/out.obj", CUBE_MESH)


def test_write_missing_verts():
    with pytest.raises(ObjWriteError):
        write_obj("/tmp/_kerf_test_dummy.obj", {"faces": [[0, 1, 2]]})


def test_write_missing_faces():
    with pytest.raises(ObjWriteError):
        write_obj("/tmp/_kerf_test_dummy2.obj", {"verts": [[0, 0, 0]]})


def test_read_bad_face_index():
    obj_text = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 99\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "badidx.obj"
        p.write_text(obj_text, encoding="utf-8")
        with pytest.raises(ObjReadError, match="out of range"):
            read_obj(p)


def test_read_zero_index_rejected():
    obj_text = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 0 1 2\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "zero.obj"
        p.write_text(obj_text, encoding="utf-8")
        with pytest.raises(ObjReadError, match="index 0 is invalid"):
            read_obj(p)


# ---------------------------------------------------------------------------
# mtllib with missing file (non-fatal)
# ---------------------------------------------------------------------------

def test_missing_mtllib_non_fatal():
    """If the .mtl file referenced by mtllib is missing, read_obj succeeds
    with empty materials dict."""
    obj_text = "mtllib nonexistent.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "nomtl.obj"
        p.write_text(obj_text, encoding="utf-8")
        result = read_obj(p)
    assert result["mtllib"] == "nonexistent.mtl"
    assert result["materials"] == {}


# ---------------------------------------------------------------------------
# MTL Tr keyword (transparency → dissolve conversion)
# ---------------------------------------------------------------------------

def test_mtl_tr_to_d():
    """Tr 0.3 → d 0.7 conversion."""
    mtl_text = "newmtl Trans\nKd 0.5 0.5 0.5\nTr 0.3\n"
    with tempfile.TemporaryDirectory() as td:
        obj_path = Path(td) / "test.obj"
        mtl_path = Path(td) / "test.mtl"
        obj_path.write_text(f"mtllib test.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
                            encoding="utf-8")
        mtl_path.write_text(mtl_text, encoding="utf-8")
        result = read_obj(obj_path)
    assert abs(result["materials"]["Trans"]["d"] - 0.7) < 1e-6


# ---------------------------------------------------------------------------
# Quad face write (non-triangle)
# ---------------------------------------------------------------------------

def test_quad_face_roundtrip():
    quad_verts = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    quad_faces = [[0, 1, 2, 3]]
    result = _write_read({"verts": quad_verts, "faces": quad_faces})
    assert result["faces"][0]["verts"] == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# groups list ordering preserved
# ---------------------------------------------------------------------------

def test_group_order_preserved():
    groups = {"first": [0], "second": [1], "third": [2]}
    result = _write_read(CUBE_MESH, groups=groups)
    seen = result["groups"]
    # All three should appear
    assert set(seen) >= {"first", "second", "third"}
    # Order should match emission order (first, second, third)
    idx_first = seen.index("first")
    idx_second = seen.index("second")
    idx_third = seen.index("third")
    assert idx_first < idx_second < idx_third
