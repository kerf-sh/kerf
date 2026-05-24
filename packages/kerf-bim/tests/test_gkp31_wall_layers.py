"""Tests for GK-P31 — wall compound-layer offset (per-layer face geometry).

DoD: make_wall_instance for a compound wall emits per-layer WallLayerGeometry
with correct offsets from the centreline, 8 corner points per layer, and
summed thickness = total wall thickness.
"""
from __future__ import annotations
import math
import pytest

from kerf_bim.walls import (
    make_compound_wall,
    make_wall_instance,
    wall_layer_faces,
    wall_to_ifc_dict,
    WallLayerGeometry,
)


def _simple_wall():
    wt = make_compound_wall(
        "Test Wall",
        [
            ("brick_clay",    100.0, "structure"),
            ("insulation_xps", 50.0, "thermal"),
            ("board_drywall_gypsum", 13.0, "finish2"),
        ],
    )
    return make_wall_instance(wt, [0.0, 0.0], [4000.0, 0.0], height=3000.0)


class TestWallLayerFaces:
    def test_layer_count(self):
        inst = _simple_wall()
        geom = wall_layer_faces(inst)
        assert len(geom) == 3

    def test_total_thickness_spans(self):
        """Outermost outer_offset - innermost inner_offset == total thickness."""
        inst = _simple_wall()
        geom = wall_layer_faces(inst)
        outer_most = geom[0].outer_offset
        inner_most = geom[-1].inner_offset
        assert abs((outer_most - inner_most) - inst.thickness) < 1e-6

    def test_layer_thicknesses_match(self):
        inst = _simple_wall()
        geom = wall_layer_faces(inst)
        for lg in geom:
            computed = lg.outer_offset - lg.inner_offset
            assert abs(computed - lg.layer.thickness) < 1e-6, (
                f"Layer {lg.layer_index}: expected {lg.layer.thickness}mm, "
                f"got offset span {computed:.6f}mm"
            )

    def test_symmetry_about_centreline(self):
        """Exterior and interior offsets should be symmetric (half_t each side)."""
        inst = _simple_wall()
        geom = wall_layer_faces(inst)
        half_t = inst.thickness / 2.0
        assert abs(geom[0].outer_offset - half_t) < 1e-6
        assert abs(geom[-1].inner_offset + half_t) < 1e-6

    def test_corners_8_points_per_layer(self):
        inst = _simple_wall()
        geom = wall_layer_faces(inst)
        for lg in geom:
            assert len(lg.corners) == 8, f"expected 8 corners, got {len(lg.corners)}"

    def test_corners_span_correct_height(self):
        inst = _simple_wall()
        geom = wall_layer_faces(inst)
        for lg in geom:
            # corners 0-3 are at base_z, corners 4-7 are at base_z + height
            base_z = inst.base_offset
            top_z = inst.base_offset + inst.effective_height
            # base corners (indices 0,1,4,5 have z=base_z)
            for i in (0, 1):
                assert abs(lg.corners[i][2] - base_z) < 1e-6
            # top corners (indices 2,3,6,7 have z=top_z)
            for i in (2, 3):
                assert abs(lg.corners[i][2] - top_z) < 1e-6

    def test_perpendicular_offset_correct_direction(self):
        """Wall along X axis — layer faces should offset along Y."""
        inst = _simple_wall()  # wall along X
        geom = wall_layer_faces(inst)
        # Wall tangent = (1,0,0); exterior perp = (0,1,0) ... actually
        # perp is rotate 90° CCW from tangent, but direction depends on formula.
        # What matters: outer_offset > inner_offset and corners are offset in Y.
        for lg in geom:
            # check Y offset at start point matches outer_offset
            y_outer = lg.corners[0][1]  # base outer start Y
            assert abs(y_outer - lg.outer_offset) < 1e-6

    def test_ifc_dict_has_layer_faces(self):
        inst = _simple_wall()
        d = wall_to_ifc_dict(inst)
        assert "layer_faces" in d
        assert len(d["layer_faces"]) == 3
        for lf in d["layer_faces"]:
            assert len(lf["corners"]) == 8

    def test_zero_length_wall_returns_empty(self):
        wt = make_compound_wall("T", [("brick_clay", 200.0, "structure")])
        inst = make_wall_instance(wt, [0.0, 0.0], [0.0, 0.0], height=3000.0)
        geom = wall_layer_faces(inst)
        assert geom == []

    def test_layers_contiguous_no_gap(self):
        """Adjacent layers share interface offset (no gaps or overlaps)."""
        inst = _simple_wall()
        geom = wall_layer_faces(inst)
        for i in range(len(geom) - 1):
            assert abs(geom[i].inner_offset - geom[i + 1].outer_offset) < 1e-6
