"""Tests for GK-P24: LSCM UV unwrap."""
from __future__ import annotations
import math
import pytest
from kerf_cad_core.geom.uv_unwrap import lscm_unwrap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_flat_quad_mesh(n: int = 4):
    """Grid of n×n quads, triangulated, all in the XY plane.
    Edge length = 1/(n).
    """
    verts = []
    for j in range(n + 1):
        for i in range(n + 1):
            verts.append([i / n, j / n, 0.0])
    faces = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            b = a + 1
            c = a + (n + 1) + 1
            d = a + (n + 1)
            faces.append([a, b, c])
            faces.append([a, c, d])
    return {"vertices": verts, "faces": faces}


def make_single_triangle():
    verts = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 1.0, 0.0]]
    faces = [[0, 1, 2]]
    return {"vertices": verts, "faces": faces}


# ---------------------------------------------------------------------------
# Basic structure tests
# ---------------------------------------------------------------------------

class TestLscmUnwrapStructure:
    def test_returns_dict_with_uv_key(self):
        mesh = make_flat_quad_mesh(3)
        result = lscm_unwrap(mesh)
        assert "uv" in result

    def test_uv_length_equals_vertex_count(self):
        mesh = make_flat_quad_mesh(3)
        result = lscm_unwrap(mesh)
        assert len(result["uv"]) == len(mesh["vertices"])

    def test_each_uv_is_2d(self):
        mesh = make_flat_quad_mesh(3)
        result = lscm_unwrap(mesh)
        for uv in result["uv"]:
            assert len(uv) == 2, f"Expected [u, v], got {uv}"

    def test_all_uv_finite(self):
        mesh = make_flat_quad_mesh(3)
        result = lscm_unwrap(mesh)
        for uv in result["uv"]:
            for coord in uv:
                assert math.isfinite(coord), f"Non-finite UV coord: {coord}"

    def test_empty_mesh_returns_empty(self):
        result = lscm_unwrap({"vertices": [], "faces": []})
        assert result["uv"] == []

    def test_single_triangle(self):
        mesh = make_single_triangle()
        result = lscm_unwrap(mesh)
        assert len(result["uv"]) == 3
        for uv in result["uv"]:
            assert len(uv) == 2
            for c in uv:
                assert math.isfinite(c)


# ---------------------------------------------------------------------------
# Pin constraints honoured
# ---------------------------------------------------------------------------

class TestLscmPins:
    def test_pinned_vertex_uv_exactly_at_pin(self):
        mesh = make_flat_quad_mesh(4)
        pins = [(0, 0.0, 0.0), (4, 1.0, 0.0)]  # corner vertices
        result = lscm_unwrap(mesh, fixed_pins=pins)
        uv0 = result["uv"][0]
        uv4 = result["uv"][4]
        assert abs(uv0[0] - 0.0) < 1e-8 and abs(uv0[1] - 0.0) < 1e-8
        assert abs(uv4[0] - 1.0) < 1e-8 and abs(uv4[1] - 0.0) < 1e-8

    def test_two_pins_produce_nondegenerate_uv(self):
        """With two pins, the free vertices should spread out (not all zero)."""
        mesh = make_flat_quad_mesh(4)
        n = len(mesh["vertices"])
        pins = [(0, 0.0, 0.0), (n - 1, 1.0, 1.0)]
        result = lscm_unwrap(mesh, fixed_pins=pins)
        uvs = result["uv"]
        # Not all the same — compute variance
        us = [uv[0] for uv in uvs]
        vs = [uv[1] for uv in uvs]
        assert max(us) - min(us) > 0.1, "U values all collapsed"
        assert max(vs) - min(vs) > 0.1, "V values all collapsed"

    def test_invalid_pin_index_falls_back_gracefully(self):
        mesh = make_flat_quad_mesh(2)
        pins = [(9999, 0.0, 0.0), (9998, 1.0, 0.0)]  # out of range
        result = lscm_unwrap(mesh, fixed_pins=pins)
        # Should not raise; should return something valid
        assert len(result["uv"]) == len(mesh["vertices"])


# ---------------------------------------------------------------------------
# Conformal quality (flat mesh should map near-isometrically)
# ---------------------------------------------------------------------------

class TestLscmConformalQuality:
    def test_flat_mesh_uv_spans_nonzero_range(self):
        """A flat grid unwrapped should have UVs spread over a nonzero range."""
        mesh = make_flat_quad_mesh(5)
        result = lscm_unwrap(mesh)
        uvs = result["uv"]
        us = [uv[0] for uv in uvs]
        vs = [uv[1] for uv in uvs]
        assert max(us) - min(us) > 0.05, f"U range too small: {max(us)-min(us)}"
        assert max(vs) - min(vs) > 0.05, f"V range too small: {max(vs)-min(vs)}"

    def test_flat_mesh_relative_ordering_preserved(self):
        """For a flat grid with pinned corners, top-right vertex should have
        higher u+v sum than bottom-left vertex."""
        mesh = make_flat_quad_mesh(4)
        n_side = 4 + 1  # 5 per row
        # Bottom-left = 0, top-right = last vertex
        n_verts = len(mesh["vertices"])
        pins = [(0, 0.0, 0.0), (n_verts - 1, 1.0, 1.0)]
        result = lscm_unwrap(mesh, fixed_pins=pins)
        uvs = result["uv"]
        sum_bl = uvs[0][0] + uvs[0][1]
        sum_tr = uvs[n_verts - 1][0] + uvs[n_verts - 1][1]
        assert sum_tr > sum_bl, "Top-right should have higher u+v than bottom-left"

    def test_single_triangle_auto_pins(self):
        """Single triangle with automatic pin selection should produce finite UVs."""
        mesh = make_single_triangle()
        result = lscm_unwrap(mesh)
        for uv in result["uv"]:
            for c in uv:
                assert math.isfinite(c)
