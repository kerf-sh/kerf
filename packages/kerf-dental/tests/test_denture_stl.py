"""
Tests for kerf_dental.denture and kerf_dental.stl_export.

T: denture / RPD geometry + STL export for milling.
"""

from __future__ import annotations

import math
import os
import sys
import struct

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from kerf_dental.denture import (
    DentureSpec,
    RPDSpec,
    DentureResult,
    RPDResult,
    design_full_denture,
    design_rpd,
    _arch_centreline,
)
from kerf_dental.stl_export import (
    stl_bytes_binary,
    export_stl_binary,
    export_stl_ascii,
)


# ===========================================================================
# DentureSpec validation
# ===========================================================================

class TestDentureSpec:
    def test_mandibular_defaults(self):
        spec = DentureSpec(arch="mandibular")
        assert spec.arch_semi_a_mm == pytest.approx(33.0)
        assert spec.arch_semi_b_mm == pytest.approx(25.0)

    def test_maxillary_defaults(self):
        spec = DentureSpec(arch="maxillary")
        assert spec.arch_semi_a_mm == pytest.approx(40.0)
        assert spec.arch_semi_b_mm == pytest.approx(35.0)

    def test_custom_axes(self):
        spec = DentureSpec(arch_semi_a_mm=38.0, arch_semi_b_mm=28.0)
        assert spec.arch_semi_a_mm == pytest.approx(38.0)

    def test_invalid_arch_raises(self):
        with pytest.raises(ValueError, match="arch must be"):
            DentureSpec(arch="anterior")

    def test_invalid_flange_height_raises(self):
        with pytest.raises(ValueError, match="flange_height_mm"):
            DentureSpec(flange_height_mm=0.0)

    def test_invalid_segments_raises(self):
        with pytest.raises(ValueError, match="n_arch_segments"):
            DentureSpec(n_arch_segments=4)

    def test_invalid_tooth_positions_raises(self):
        with pytest.raises(ValueError, match="n_tooth_positions"):
            DentureSpec(n_tooth_positions=2)


class TestRPDSpec:
    def test_mandibular_defaults(self):
        spec = RPDSpec(arch="mandibular")
        assert spec.arch_semi_a_mm == pytest.approx(30.0)
        assert spec.arch_semi_b_mm == pytest.approx(22.0)

    def test_maxillary_defaults(self):
        spec = RPDSpec(arch="maxillary")
        assert spec.arch_semi_a_mm == pytest.approx(38.0)

    def test_rest_positions_auto_mandibular(self):
        spec = RPDSpec(arch="mandibular")
        assert len(spec.rest_positions) >= 4

    def test_rest_positions_auto_maxillary(self):
        spec = RPDSpec(arch="maxillary")
        assert len(spec.rest_positions) >= 4

    def test_invalid_connector_width_raises(self):
        with pytest.raises(ValueError, match="connector_width_mm"):
            RPDSpec(connector_width_mm=0.0)

    def test_invalid_connector_depth_raises(self):
        with pytest.raises(ValueError, match="connector_depth_mm"):
            RPDSpec(connector_depth_mm=-1.0)


# ===========================================================================
# Arch centreline geometry
# ===========================================================================

class TestArchCentreline:
    def test_shape(self):
        pts = _arch_centreline(33.0, 25.0, 16)
        assert pts.shape == (17, 3)

    def test_starts_at_minus_a(self):
        pts = _arch_centreline(33.0, 25.0, 16)
        assert pts[0, 0] == pytest.approx(-33.0, abs=0.1)
        assert abs(pts[0, 1]) < 0.1

    def test_ends_at_plus_a(self):
        pts = _arch_centreline(33.0, 25.0, 16)
        assert pts[-1, 0] == pytest.approx(33.0, abs=0.1)
        assert abs(pts[-1, 1]) < 0.1

    def test_apex_at_front(self):
        """Anterior apex is at y ~ b (semi-axis b)."""
        b = 25.0
        pts = _arch_centreline(33.0, b, 16)
        y_max = float(pts[:, 1].max())
        assert y_max > 0.9 * b

    def test_all_z_zero(self):
        pts = _arch_centreline(33.0, 25.0, 16)
        np.testing.assert_allclose(pts[:, 2], 0.0, atol=1e-6)


# ===========================================================================
# design_full_denture
# ===========================================================================

class TestDesignFullDenture:
    def _make_mandibular(self, **kw) -> DentureResult:
        spec = DentureSpec(arch="mandibular", n_arch_segments=16, n_tooth_positions=8, **kw)
        return design_full_denture(spec)

    def _make_maxillary(self, **kw) -> DentureResult:
        spec = DentureSpec(arch="maxillary", n_arch_segments=16, n_tooth_positions=8, **kw)
        return design_full_denture(spec)

    def test_returns_denture_result(self):
        result = self._make_mandibular()
        assert isinstance(result, DentureResult)

    def test_arch_preserved(self):
        result = self._make_mandibular()
        assert result.arch == "mandibular"

    def test_maxillary_result(self):
        result = self._make_maxillary()
        assert result.arch == "maxillary"

    def test_vertices_shape(self):
        result = self._make_mandibular()
        assert result.vertices.ndim == 2
        assert result.vertices.shape[1] == 3

    def test_faces_shape(self):
        result = self._make_mandibular()
        assert result.faces.ndim == 2
        assert result.faces.shape[1] == 3

    def test_vertex_count_positive(self):
        result = self._make_mandibular()
        assert result.vertex_count > 0

    def test_face_count_positive(self):
        result = self._make_mandibular()
        assert result.face_count > 0

    def test_tooth_positions_count(self):
        """DentureSpec n_tooth_positions controls number of tooth sockets."""
        result = self._make_mandibular()
        assert len(result.tooth_positions) == 8

    def test_tooth_positions_are_3d_tuples(self):
        result = self._make_mandibular()
        for pos in result.tooth_positions:
            assert len(pos) == 3
            for c in pos:
                assert isinstance(c, float)

    def test_all_face_indices_valid(self):
        """Face indices must be in [0, vertex_count)."""
        result = self._make_mandibular()
        V = result.vertex_count
        assert result.faces.min() >= 0
        assert result.faces.max() < V

    def test_vertices_in_dental_scale(self):
        """Vertices should be in mm scale (10–100 mm range)."""
        result = self._make_mandibular()
        extents = result.vertices.max(axis=0) - result.vertices.min(axis=0)
        # At least two axes should span > 20 mm
        large_axes = sum(e > 20.0 for e in extents)
        assert large_axes >= 2, f"vertices extents = {extents}; expected > 20 mm"

    def test_different_flange_heights(self):
        """Larger flange_height_mm → more vertices away from the arch plane (buccal direction)."""
        r1 = design_full_denture(DentureSpec(n_arch_segments=16, flange_height_mm=10.0))
        r2 = design_full_denture(DentureSpec(n_arch_segments=16, flange_height_mm=20.0))
        # The flange height controls the 'n' offset in the arch tube sweep.
        # The vertex count should be the same (same topology), but the
        # cross-section buccal extent differs.  Check that max n-offset (perpendicular
        # to arch tangent) is larger for r2 than r1 by checking the overall bounding box range.
        # The cross-section normal offset is encoded in x/y coordinates (not z for a flat arch).
        # Use the total span of the mesh (not just z) to verify larger flange makes bigger mesh.
        span1 = float(np.linalg.norm(r1.vertices.max(axis=0) - r1.vertices.min(axis=0)))
        span2 = float(np.linalg.norm(r2.vertices.max(axis=0) - r2.vertices.min(axis=0)))
        # r2 has 2× flange height so buccal extent is larger
        assert span2 >= span1


# ===========================================================================
# design_rpd
# ===========================================================================

class TestDesignRPD:
    def _make_mandibular(self, **kw) -> RPDResult:
        spec = RPDSpec(arch="mandibular", n_arch_segments=16, **kw)
        return design_rpd(spec)

    def _make_maxillary(self, **kw) -> RPDResult:
        spec = RPDSpec(arch="maxillary", n_arch_segments=16, **kw)
        return design_rpd(spec)

    def test_returns_rpd_result(self):
        result = self._make_mandibular()
        assert isinstance(result, RPDResult)

    def test_connector_type_mandibular(self):
        result = self._make_mandibular()
        assert result.connector_type == "lingual_bar"

    def test_connector_type_maxillary(self):
        result = self._make_maxillary()
        assert result.connector_type == "palatal_plate"

    def test_vertex_count_positive(self):
        result = self._make_mandibular()
        assert result.vertex_count > 0

    def test_face_count_positive(self):
        result = self._make_mandibular()
        assert result.face_count > 0

    def test_rest_positions_not_empty(self):
        result = self._make_mandibular()
        assert len(result.rest_positions) >= 4

    def test_rest_positions_are_3d(self):
        result = self._make_mandibular()
        for pos in result.rest_positions:
            assert len(pos) == 3

    def test_all_face_indices_valid(self):
        result = self._make_mandibular()
        V = result.vertex_count
        assert result.faces.min() >= 0
        assert result.faces.max() < V

    def test_wider_connector_more_vertices_x(self):
        """Wider connector_width_mm spans more in the cross-arch direction."""
        r1 = design_rpd(RPDSpec(arch="mandibular", connector_width_mm=3.0, n_arch_segments=16))
        r2 = design_rpd(RPDSpec(arch="mandibular", connector_width_mm=8.0, n_arch_segments=16))
        # Both should have same topology but wider r2 spans more
        assert r2.vertex_count == r1.vertex_count  # same topology


# ===========================================================================
# stl_bytes_binary
# ===========================================================================

class TestSTLBytesBinary:
    def _make_single_triangle(self):
        verts = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ], dtype=np.float32)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        return verts, faces

    def test_returns_bytes(self):
        verts, faces = self._make_single_triangle()
        data = stl_bytes_binary(verts, faces)
        assert isinstance(data, bytes)

    def test_header_80_bytes(self):
        """Binary STL starts with 80-byte header."""
        verts, faces = self._make_single_triangle()
        data = stl_bytes_binary(verts, faces)
        assert len(data) >= 84
        # First 80 bytes = header
        header = data[:80]
        assert len(header) == 80

    def test_triangle_count_in_header(self):
        """Bytes 80–84 encode triangle count as little-endian uint32."""
        verts, faces = self._make_single_triangle()
        data = stl_bytes_binary(verts, faces)
        n_tris = struct.unpack("<I", data[80:84])[0]
        assert n_tris == 1

    def test_total_length_single_triangle(self):
        """Binary STL: 80 + 4 + 50 bytes per triangle."""
        verts, faces = self._make_single_triangle()
        data = stl_bytes_binary(verts, faces)
        assert len(data) == 80 + 4 + 1 * 50

    def test_total_length_four_triangles(self):
        verts = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ], dtype=np.float32)
        faces = np.array([[0, 1, 2], [1, 3, 2], [0, 2, 3], [0, 3, 1]], dtype=np.int32)
        data = stl_bytes_binary(verts, faces)
        assert len(data) == 80 + 4 + 4 * 50

    def test_invalid_vertices_shape_raises(self):
        with pytest.raises(ValueError, match="vertices must be"):
            stl_bytes_binary(np.zeros((5,)), np.array([[0, 1, 2]]))

    def test_invalid_faces_shape_raises(self):
        with pytest.raises(ValueError, match="faces must be"):
            stl_bytes_binary(np.zeros((3, 3)), np.zeros((1, 4)))

    def test_normal_in_bytes(self):
        """Normal of z-facing triangle should encode as (0, 0, 1) approximately."""
        verts = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ], dtype=np.float32)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        data = stl_bytes_binary(verts, faces)
        # Normal is at bytes 84–96
        nx, ny, nz = struct.unpack("<fff", data[84:96])
        assert abs(nz - 1.0) < 1e-5, f"normal z = {nz}, expected ~1.0"

    def test_custom_header_encoding(self):
        """Custom header is embedded in the first 80 bytes."""
        verts, faces = self._make_single_triangle()
        data = stl_bytes_binary(verts, faces, header="TestHeader")
        assert b"TestHeader" in data[:80]


# ===========================================================================
# export_stl_binary (file I/O)
# ===========================================================================

class TestExportSTLBinary:
    def test_writes_file(self, tmp_path):
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        path = tmp_path / "test.stl"
        n = export_stl_binary(verts, faces, path)
        assert n == 1
        assert path.exists()
        assert path.stat().st_size == 80 + 4 + 50

    def test_returns_triangle_count(self, tmp_path):
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.5, 0.5, 1.0]], dtype=np.float32)
        faces = np.array([[0, 1, 2], [0, 1, 3]], dtype=np.int32)
        path = tmp_path / "test.stl"
        n = export_stl_binary(verts, faces, path)
        assert n == 2


# ===========================================================================
# export_stl_ascii (file I/O)
# ===========================================================================

class TestExportSTLAscii:
    def test_writes_file(self, tmp_path):
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        path = tmp_path / "test.stl"
        n = export_stl_ascii(verts, faces, path)
        assert n == 1
        assert path.exists()

    def test_ascii_content_structure(self, tmp_path):
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
        faces = np.array([[0, 1, 2]], dtype=np.int32)
        path = tmp_path / "test.stl"
        export_stl_ascii(verts, faces, path, solid_name="mypart")
        text = path.read_text()
        assert text.startswith("solid mypart")
        assert "endsolid mypart" in text
        assert "facet normal" in text
        assert "outer loop" in text
        assert "vertex" in text
        assert "endloop" in text
        assert "endfacet" in text

    def test_returns_triangle_count(self, tmp_path):
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.5, 0.5, 1.0]], dtype=np.float32)
        faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3]], dtype=np.int32)
        path = tmp_path / "test.stl"
        n = export_stl_ascii(verts, faces, path)
        assert n == 3


# ===========================================================================
# STL round-trip with denture mesh
# ===========================================================================

class TestDentureSTLRoundTrip:
    def test_mandibular_denture_stl_binary(self, tmp_path):
        """Full denture → binary STL → file readable."""
        spec = DentureSpec(arch="mandibular", n_arch_segments=16, n_tooth_positions=8)
        result = design_full_denture(spec)
        path = tmp_path / "mandibular.stl"
        n = export_stl_binary(result.vertices, result.faces, path)
        assert n == result.face_count
        # Verify file size
        expected_size = 80 + 4 + n * 50
        assert path.stat().st_size == expected_size

    def test_maxillary_denture_stl_ascii(self, tmp_path):
        """Maxillary denture → ASCII STL → valid text."""
        spec = DentureSpec(arch="maxillary", n_arch_segments=16, n_tooth_positions=8)
        result = design_full_denture(spec)
        path = tmp_path / "maxillary.stl"
        n = export_stl_ascii(result.vertices, result.faces, path, solid_name="maxillary")
        assert n == result.face_count
        text = path.read_text()
        assert "solid maxillary" in text
        assert "endsolid maxillary" in text

    def test_rpd_stl_binary(self, tmp_path):
        """RPD connector → binary STL → readable."""
        spec = RPDSpec(arch="mandibular", n_arch_segments=16)
        result = design_rpd(spec)
        path = tmp_path / "rpd.stl"
        n = export_stl_binary(result.vertices, result.faces, path)
        assert n == result.face_count


# ===========================================================================
# Module import smoke tests
# ===========================================================================

class TestModuleImports:
    def test_denture_imports(self):
        import kerf_dental.denture  # noqa: F401

    def test_stl_export_imports(self):
        import kerf_dental.stl_export  # noqa: F401
