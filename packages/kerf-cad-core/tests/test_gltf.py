"""Tests for glTF 2.0 / GLB read + write — GK-79.

Oracle: write a unit cube with metallic-roughness → read back vertex count +
base-colour + roughness within ε.  Round-trip GLB (binary) AND .gltf (separate
buffer).

All tests are pure-Python and hermetic (no OCCT, no external files).
"""

from __future__ import annotations

import math
import pathlib
import tempfile

import pytest

from kerf_cad_core.geom.io.gltf import (
    GltfReadError,
    GltfWriteError,
    read_gltf,
    write_gltf,
)
# Also verify the re-export paths work.
from kerf_cad_core.geom.io import (
    GltfReadError as _GltfReadError2,
    GltfWriteError as _GltfWriteError2,
    read_gltf as _read_gltf2,
    write_gltf as _write_gltf2,
)
from kerf_cad_core.geom import (
    GltfReadError as _GltfReadError3,
    GltfWriteError as _GltfWriteError3,
    read_gltf as _read_gltf3,
    write_gltf as _write_gltf3,
)


# ---------------------------------------------------------------------------
# Test mesh: unit cube (8 vertices, 12 triangles)
# ---------------------------------------------------------------------------

# Vertices of a unit cube [0..1]^3
_CUBE_VERTS = [
    [0.0, 0.0, 0.0],  # 0
    [1.0, 0.0, 0.0],  # 1
    [1.0, 1.0, 0.0],  # 2
    [0.0, 1.0, 0.0],  # 3
    [0.0, 0.0, 1.0],  # 4
    [1.0, 0.0, 1.0],  # 5
    [1.0, 1.0, 1.0],  # 6
    [0.0, 1.0, 1.0],  # 7
]

# 12 triangles (2 per face × 6 faces)
_CUBE_FACES = [
    # Bottom (-Z)
    [0, 2, 1], [0, 3, 2],
    # Top (+Z)
    [4, 5, 6], [4, 6, 7],
    # Front (-Y)
    [0, 1, 5], [0, 5, 4],
    # Back (+Y)
    [2, 3, 7], [2, 7, 6],
    # Left (-X)
    [0, 4, 7], [0, 7, 3],
    # Right (+X)
    [1, 2, 6], [1, 6, 5],
]

_CUBE_MESH = {"verts": _CUBE_VERTS, "faces": _CUBE_FACES}

_PBR_MAT = {
    "name": "cube_pbr",
    "base_color": [0.8, 0.2, 0.1, 1.0],
    "metallic": 0.3,
    "roughness": 0.6,
    "emissive": [0.0, 0.0, 0.0],
    "double_sided": False,
    "alpha_mode": "OPAQUE",
}

_EPS = 1e-5  # tolerance for float comparisons


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _close(a: float, b: float, eps: float = _EPS) -> bool:
    return math.fabs(a - b) <= eps


def _close_list(a: list, b: list, eps: float = _EPS) -> bool:
    return len(a) == len(b) and all(_close(x, y, eps) for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# Tests — GLB round-trip
# ---------------------------------------------------------------------------

class TestGlbRoundTrip:
    """Write a unit cube as GLB and read it back."""

    def test_vertex_count(self, tmp_path):
        p = tmp_path / "cube.glb"
        write_gltf(p, _CUBE_MESH, [_PBR_MAT], binary=True)
        result = read_gltf(p)
        assert len(result["verts"]) == len(_CUBE_VERTS), (
            f"Expected {len(_CUBE_VERTS)} verts, got {len(result['verts'])}"
        )

    def test_face_count(self, tmp_path):
        p = tmp_path / "cube.glb"
        write_gltf(p, _CUBE_MESH, [_PBR_MAT], binary=True)
        result = read_gltf(p)
        assert len(result["faces"]) == len(_CUBE_FACES), (
            f"Expected {len(_CUBE_FACES)} faces, got {len(result['faces'])}"
        )

    def test_base_colour_within_eps(self, tmp_path):
        p = tmp_path / "cube.glb"
        write_gltf(p, _CUBE_MESH, [_PBR_MAT], binary=True)
        result = read_gltf(p)
        assert result["materials"], "No materials in read result"
        mat = result["materials"][0]
        expected = _PBR_MAT["base_color"]
        actual = mat["base_color"]
        assert _close_list(actual, expected), (
            f"base_color mismatch: expected {expected}, got {actual}"
        )

    def test_metallic_within_eps(self, tmp_path):
        p = tmp_path / "cube.glb"
        write_gltf(p, _CUBE_MESH, [_PBR_MAT], binary=True)
        result = read_gltf(p)
        mat = result["materials"][0]
        assert _close(mat["metallic"], _PBR_MAT["metallic"]), (
            f"metallic mismatch: {mat['metallic']} vs {_PBR_MAT['metallic']}"
        )

    def test_roughness_within_eps(self, tmp_path):
        p = tmp_path / "cube.glb"
        write_gltf(p, _CUBE_MESH, [_PBR_MAT], binary=True)
        result = read_gltf(p)
        mat = result["materials"][0]
        assert _close(mat["roughness"], _PBR_MAT["roughness"]), (
            f"roughness mismatch: {mat['roughness']} vs {_PBR_MAT['roughness']}"
        )

    def test_vertex_positions_preserved(self, tmp_path):
        p = tmp_path / "cube.glb"
        write_gltf(p, _CUBE_MESH, binary=True)
        result = read_gltf(p)
        for i, (orig, rt) in enumerate(zip(_CUBE_VERTS, result["verts"])):
            assert _close_list(rt, orig), (
                f"Vertex {i}: expected {orig}, got {rt}"
            )

    def test_face_indices_preserved(self, tmp_path):
        p = tmp_path / "cube.glb"
        write_gltf(p, _CUBE_MESH, binary=True)
        result = read_gltf(p)
        for i, (orig, rt) in enumerate(zip(_CUBE_FACES, result["faces"])):
            assert list(rt) == list(orig), (
                f"Face {i}: expected {orig}, got {rt}"
            )

    def test_glb_magic_bytes(self, tmp_path):
        """Verify GLB file has correct magic bytes."""
        import struct
        p = tmp_path / "cube.glb"
        write_gltf(p, _CUBE_MESH, binary=True)
        raw = p.read_bytes()
        magic = struct.unpack_from("<I", raw, 0)[0]
        assert magic == 0x46546C67, f"Bad GLB magic: 0x{magic:08X}"
        version = struct.unpack_from("<I", raw, 4)[0]
        assert version == 2

    def test_no_materials_ok(self, tmp_path):
        """Write without materials should still round-trip mesh."""
        p = tmp_path / "nomats.glb"
        write_gltf(p, _CUBE_MESH, binary=True)
        result = read_gltf(p)
        assert len(result["verts"]) == len(_CUBE_VERTS)
        assert len(result["faces"]) == len(_CUBE_FACES)

    def test_dict_with_string_path(self, tmp_path):
        """Accept str path."""
        p = str(tmp_path / "cube.glb")
        write_gltf(p, _CUBE_MESH, [_PBR_MAT])
        result = read_gltf(p)
        assert len(result["verts"]) == len(_CUBE_VERTS)


# ---------------------------------------------------------------------------
# Tests — .gltf + .bin round-trip (binary=False)
# ---------------------------------------------------------------------------

class TestGltfSeparateBuffer:
    """Write a unit cube as .gltf + .bin and read it back."""

    def test_vertex_count(self, tmp_path):
        p = tmp_path / "cube.gltf"
        write_gltf(p, _CUBE_MESH, [_PBR_MAT], binary=False)
        assert (tmp_path / "cube.bin").exists(), "Expected .bin file alongside .gltf"
        result = read_gltf(p)
        assert len(result["verts"]) == len(_CUBE_VERTS)

    def test_face_count(self, tmp_path):
        p = tmp_path / "cube.gltf"
        write_gltf(p, _CUBE_MESH, [_PBR_MAT], binary=False)
        result = read_gltf(p)
        assert len(result["faces"]) == len(_CUBE_FACES)

    def test_base_colour_within_eps(self, tmp_path):
        p = tmp_path / "cube.gltf"
        write_gltf(p, _CUBE_MESH, [_PBR_MAT], binary=False)
        result = read_gltf(p)
        mat = result["materials"][0]
        assert _close_list(mat["base_color"], _PBR_MAT["base_color"])

    def test_roughness_within_eps(self, tmp_path):
        p = tmp_path / "cube.gltf"
        write_gltf(p, _CUBE_MESH, [_PBR_MAT], binary=False)
        result = read_gltf(p)
        mat = result["materials"][0]
        assert _close(mat["roughness"], _PBR_MAT["roughness"])

    def test_gltf_is_json(self, tmp_path):
        """The .gltf file must be valid JSON with asset.version == "2.0"."""
        import json
        p = tmp_path / "cube.gltf"
        write_gltf(p, _CUBE_MESH, binary=False)
        data = json.loads(p.read_bytes())
        assert data["asset"]["version"] == "2.0"

    def test_vertex_positions_preserved(self, tmp_path):
        p = tmp_path / "cube.gltf"
        write_gltf(p, _CUBE_MESH, binary=False)
        result = read_gltf(p)
        for i, (orig, rt) in enumerate(zip(_CUBE_VERTS, result["verts"])):
            assert _close_list(rt, orig), f"Vertex {i}: {orig} != {rt}"


# ---------------------------------------------------------------------------
# Tests — normals and UVs
# ---------------------------------------------------------------------------

class TestNormalsAndUVs:
    def _make_mesh_with_normals(self):
        import math
        verts = _CUBE_VERTS
        # Flat normals pointing up for all vertices
        normals = [[0.0, 0.0, 1.0]] * len(verts)
        uvs = [[v[0], v[1]] for v in verts]
        return {
            "verts": verts,
            "faces": _CUBE_FACES,
            "normals": normals,
            "uvs": uvs,
        }

    def test_normals_roundtrip_glb(self, tmp_path):
        mesh = self._make_mesh_with_normals()
        p = tmp_path / "normals.glb"
        write_gltf(p, mesh, binary=True)
        result = read_gltf(p)
        assert len(result["normals"]) == len(mesh["normals"]), (
            f"normals count: {len(result['normals'])} vs {len(mesh['normals'])}"
        )
        for i, (orig, rt) in enumerate(zip(mesh["normals"], result["normals"])):
            assert _close_list(list(rt), orig), f"Normal {i}: {orig} != {rt}"

    def test_uvs_roundtrip_glb(self, tmp_path):
        mesh = self._make_mesh_with_normals()
        p = tmp_path / "uvs.glb"
        write_gltf(p, mesh, binary=True)
        result = read_gltf(p)
        assert len(result["uvs"]) == len(mesh["uvs"]), (
            f"uvs count: {len(result['uvs'])} vs {len(mesh['uvs'])}"
        )
        for i, (orig, rt) in enumerate(zip(mesh["uvs"], result["uvs"])):
            assert _close_list(list(rt), orig), f"UV {i}: {orig} != {rt}"

    def test_normals_roundtrip_gltf(self, tmp_path):
        mesh = self._make_mesh_with_normals()
        p = tmp_path / "normals.gltf"
        write_gltf(p, mesh, binary=False)
        result = read_gltf(p)
        assert len(result["normals"]) == len(mesh["normals"])


# ---------------------------------------------------------------------------
# Tests — duck-typed object input
# ---------------------------------------------------------------------------

class TestDuckTypedInput:
    class FakeMesh:
        def __init__(self, verts, faces):
            self.verts = verts
            self.faces = faces

    def test_object_with_verts_faces(self, tmp_path):
        obj = self.FakeMesh(_CUBE_VERTS, _CUBE_FACES)
        p = tmp_path / "duck.glb"
        write_gltf(p, obj, binary=True)
        result = read_gltf(p)
        assert len(result["verts"]) == len(_CUBE_VERTS)
        assert len(result["faces"]) == len(_CUBE_FACES)

    class FakeMeshVertices:
        def __init__(self, verts, faces):
            self.vertices = verts  # .vertices instead of .verts
            self.faces = faces

    def test_object_with_vertices_attr(self, tmp_path):
        obj = self.FakeMeshVertices(_CUBE_VERTS, _CUBE_FACES)
        p = tmp_path / "duck2.glb"
        write_gltf(p, obj, binary=True)
        result = read_gltf(p)
        assert len(result["verts"]) == len(_CUBE_VERTS)


# ---------------------------------------------------------------------------
# Tests — error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    def test_read_nonexistent_file(self, tmp_path):
        with pytest.raises(GltfReadError):
            read_gltf(tmp_path / "nonexistent.glb")

    def test_read_invalid_data(self, tmp_path):
        p = tmp_path / "bad.glb"
        p.write_bytes(b"not a gltf file at all")
        with pytest.raises(GltfReadError):
            read_gltf(p)

    def test_write_empty_verts(self, tmp_path):
        with pytest.raises(GltfWriteError):
            write_gltf(tmp_path / "bad.glb", {"verts": [], "faces": []})

    def test_write_empty_faces(self, tmp_path):
        with pytest.raises(GltfWriteError):
            write_gltf(
                tmp_path / "bad.glb",
                {"verts": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": []},
            )

    def test_write_face_out_of_range(self, tmp_path):
        mesh = {"verts": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": [[0, 1, 99]]}
        with pytest.raises(GltfWriteError):
            write_gltf(tmp_path / "bad.glb", mesh)

    def test_write_missing_verts_attr(self, tmp_path):
        class Bad:
            faces = [[0, 1, 2]]

        with pytest.raises(GltfWriteError):
            write_gltf(tmp_path / "bad.glb", Bad())

    def test_read_truncated_glb(self, tmp_path):
        """A file with valid magic but truncated body raises GltfReadError."""
        import struct
        p = tmp_path / "trunc.glb"
        # Valid magic + version, but claims large total_length
        p.write_bytes(struct.pack("<III", 0x46546C67, 2, 1000) + b"\x00" * 4)
        with pytest.raises(GltfReadError):
            read_gltf(p)


# ---------------------------------------------------------------------------
# Tests — re-export paths
# ---------------------------------------------------------------------------

class TestReExports:
    def test_geom_io_init_exports(self):
        assert _read_gltf2 is read_gltf
        assert _write_gltf2 is write_gltf
        assert _GltfReadError2 is GltfReadError
        assert _GltfWriteError2 is GltfWriteError

    def test_geom_init_exports(self):
        assert _read_gltf3 is read_gltf
        assert _write_gltf3 is write_gltf
        assert _GltfReadError3 is GltfReadError
        assert _GltfWriteError3 is GltfWriteError


# ---------------------------------------------------------------------------
# Tests — multiple materials
# ---------------------------------------------------------------------------

class TestMultipleMaterials:
    def test_multiple_materials_preserved(self, tmp_path):
        mats = [
            {
                "name": "mat_a",
                "base_color": [1.0, 0.0, 0.0, 1.0],
                "metallic": 0.0,
                "roughness": 1.0,
            },
            {
                "name": "mat_b",
                "base_color": [0.0, 0.0, 1.0, 1.0],
                "metallic": 1.0,
                "roughness": 0.0,
            },
        ]
        p = tmp_path / "multi.glb"
        # Use material_index 1 to exercise the index path
        mesh = dict(_CUBE_MESH)
        mesh["material_indices"] = [1]
        write_gltf(p, mesh, mats, binary=True)
        result = read_gltf(p)
        assert len(result["materials"]) == 2
        assert _close_list(result["materials"][0]["base_color"], [1.0, 0.0, 0.0, 1.0])
        assert _close_list(result["materials"][1]["base_color"], [0.0, 0.0, 1.0, 1.0])
        assert _close(result["materials"][1]["metallic"], 1.0)
        assert _close(result["materials"][1]["roughness"], 0.0)


# ---------------------------------------------------------------------------
# Tests — large mesh (> 65535 vertices → uint32 indices)
# ---------------------------------------------------------------------------

class TestLargeIndexRange:
    def _make_large_mesh(self, n: int = 70000) -> dict:
        """Generate n vertices on a line, with triangles every 3 verts."""
        verts = [[float(i), 0.0, 0.0] for i in range(n)]
        # Triangles from consecutive triplets
        faces = [[i, i + 1, i + 2] for i in range(0, n - 2, 3)]
        return {"verts": verts, "faces": faces}

    def test_large_mesh_roundtrip(self, tmp_path):
        mesh = self._make_large_mesh(70000)
        p = tmp_path / "large.glb"
        write_gltf(p, mesh, binary=True)
        result = read_gltf(p)
        assert len(result["verts"]) == len(mesh["verts"])
        assert len(result["faces"]) == len(mesh["faces"])
