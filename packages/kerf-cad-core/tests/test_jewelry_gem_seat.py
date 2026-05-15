"""
Tests for kerf_cad_core.jewelry.gem_seat.

All tests are pure-Python — no database, no OCC.
OCC-gated geometry tests are skipped cleanly when pythonOCC is absent.

Coverage:
  - seat_geometry(): dimensions, clearances, through-hole
  - seat_geometry(): total_cutter_depth_mm accumulates all layers
  - seat_geometry(): edge cases (zero clearances allowed)
  - seat_geometry(): fancy-cut girdle profile stored when provided
  - fancy_cut_girdle_profile(): per-cut profile shapes, aspect ratios, corner radii
  - channel_seat_geometry(): positions, groove dimensions, spacing validation
  - bezel_seat_geometry(): cylindrical and tapered bore geometry
  - fishtail_seat_geometry(): bright-cut radius, facet count
  - multi_stone_seat_geometry(): center + side geometry, positions, pitch validation
  - LLM tool spec: name, required fields, cut enum — for all 5 tools
  - LLM tool runner: success path, node shape in feature doc
  - LLM tool runner: auto_cut_host_id chains a boolean cut node — for each tool
  - LLM tool runner: error paths (BAD_ARGS, NOT_FOUND)
  - Channel tool: spacing validation (pitch <= diameter rejected)
  - Multi-stone tool: odd n_side_stones, insufficient pitch all rejected
  - Existing single-round-seat behaviour preserved (back-compat)
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.jewelry.gem_seat import (
    seat_geometry,
    fancy_cut_girdle_profile,
    channel_seat_geometry,
    bezel_seat_geometry,
    fishtail_seat_geometry,
    multi_stone_seat_geometry,
    # Specs
    jewelry_cut_gem_seat_spec,
    jewelry_cut_channel_seat_spec,
    jewelry_cut_bezel_seat_spec,
    jewelry_cut_fishtail_seat_spec,
    jewelry_cut_multi_stone_seat_spec,
    # Runners
    run_jewelry_cut_gem_seat,
    run_jewelry_cut_channel_seat,
    run_jewelry_cut_bezel_seat,
    run_jewelry_cut_fishtail_seat,
    run_jewelry_cut_multi_stone_seat,
)
from kerf_cad_core.jewelry.gemstones import GEMSTONE_CUTS, gemstone_proportions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(initial_content: str = "", kind: str = "feature"):
    store = {
        "content": initial_content or json.dumps({"version": 1, "features": []}),
        "kind": kind,
    }
    project_id = uuid.uuid4()
    file_id    = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            if store["kind"] == "NOT_FOUND":
                return None
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            if args:
                store["content"] = args[0]

    from kerf_core.utils.context import ProjectCtx
    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, store, file_id


def run_tool(runner, ctx, file_id, **kwargs):
    args = {"file_id": str(file_id), **kwargs}
    loop = asyncio.new_event_loop()
    try:
        raw = loop.run_until_complete(runner(ctx, json.dumps(args).encode()))
    finally:
        loop.close()
    return json.loads(raw)


def _props(cut="round_brilliant", diameter_mm=6.5):
    return gemstone_proportions(cut, diameter_mm=diameter_mm)


# Convenience wrappers that keep the same signature as the old run_tool helper
def run_gem_seat(ctx, fid, **kw):
    return run_tool(run_jewelry_cut_gem_seat, ctx, fid, **kw)

def run_channel(ctx, fid, **kw):
    return run_tool(run_jewelry_cut_channel_seat, ctx, fid, **kw)

def run_bezel(ctx, fid, **kw):
    return run_tool(run_jewelry_cut_bezel_seat, ctx, fid, **kw)

def run_fishtail(ctx, fid, **kw):
    return run_tool(run_jewelry_cut_fishtail_seat, ctx, fid, **kw)

def run_multi(ctx, fid, **kw):
    return run_tool(run_jewelry_cut_multi_stone_seat, ctx, fid, **kw)


# ---------------------------------------------------------------------------
# seat_geometry() — pure-math tests (no OCC, no DB)
# ---------------------------------------------------------------------------

class TestSeatGeometry:
    def test_girdle_radius_includes_clearance(self):
        props = _props()
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            girdle_clearance_mm=0.05,
        )
        assert geom["girdle_radius_mm"] == pytest.approx(
            props.diameter_mm / 2.0 + 0.05, abs=1e-4
        )

    def test_pavilion_depth_from_pct(self):
        props = _props()
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
        )
        expected = props.diameter_mm * props.pavilion_depth_pct / 100.0
        assert geom["pavilion_depth_mm"] == pytest.approx(expected, rel=1e-4)

    def test_total_cutter_depth_components(self):
        props = _props()
        cc = 0.10
        sa = 0.02
        cr = 0.30
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            culet_clearance_mm=cc,
            seat_allowance_mm=sa,
            crown_relief_mm=cr,
        )
        expected_total = (
            geom["pavilion_depth_mm"]
            + cc
            + geom["girdle_height_mm"]
            + cr
        )
        assert geom["total_cutter_depth_mm"] == pytest.approx(expected_total, abs=1e-4)

    def test_through_hole_false_by_default(self):
        props = _props()
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
        )
        assert geom["through_hole"] is False
        assert geom["through_hole_radius_mm"] == 0.0

    def test_through_hole_enabled(self):
        props = _props()
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            through_hole=True,
            through_hole_radius_mm=0.5,
        )
        assert geom["through_hole"] is True
        assert geom["through_hole_radius_mm"] == pytest.approx(0.5)

    def test_through_hole_default_radius_positive(self):
        props = _props()
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            through_hole=True,
        )
        assert geom["through_hole_radius_mm"] > 0

    def test_crown_relief_half_angle_is_half_crown_angle(self):
        props = _props()
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=40.0,
        )
        assert geom["crown_relief_half_angle"] == pytest.approx(20.0)

    def test_bearing_cone_top_radius_equals_girdle_radius(self):
        props = _props()
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            girdle_clearance_mm=0.05,
        )
        assert geom["bearing_cone_top_radius"] == pytest.approx(
            geom["girdle_radius_mm"]
        )

    def test_zero_clearances_accepted(self):
        props = _props()
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            girdle_clearance_mm=0.0,
            culet_clearance_mm=0.0,
            seat_allowance_mm=0.0,
            crown_relief_mm=0.0,
        )
        assert geom["total_cutter_depth_mm"] > 0

    def test_girdle_profile_stored_when_provided(self):
        props = _props("oval", diameter_mm=8.0)
        gp = fancy_cut_girdle_profile("oval", props.diameter_mm)
        geom = seat_geometry(
            cut="oval",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            girdle_profile=gp,
        )
        assert "girdle_profile" in geom
        assert geom["girdle_profile"]["cut"] == "oval"

    def test_girdle_profile_absent_by_default(self):
        props = _props()
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
        )
        assert "girdle_profile" not in geom

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_produce_valid_geometry(self, cut):
        props = gemstone_proportions(cut, diameter_mm=5.0)
        geom = seat_geometry(
            cut=cut,
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
        )
        assert geom["girdle_radius_mm"] > 0
        assert geom["pavilion_depth_mm"] > 0
        assert geom["total_cutter_depth_mm"] > 0
        assert "through_hole" in geom


# ---------------------------------------------------------------------------
# fancy_cut_girdle_profile() — pure-math tests
# ---------------------------------------------------------------------------

class TestFancyCutGirdleProfile:
    def test_round_brilliant_is_circle(self):
        gp = fancy_cut_girdle_profile("round_brilliant", 6.5)
        assert gp["profile_shape"] == "circle"
        assert gp["corner_radius_mm"] == 0.0
        assert gp["aspect_ratio"] == pytest.approx(1.0)

    def test_oval_is_ellipse(self):
        gp = fancy_cut_girdle_profile("oval", 8.0)
        assert gp["profile_shape"] == "ellipse"
        assert gp["long_axis_mm"] > gp["short_axis_mm"]

    def test_marquise_is_stadium(self):
        gp = fancy_cut_girdle_profile("marquise", 10.0)
        assert gp["profile_shape"] == "stadium"

    def test_pear_is_pear(self):
        gp = fancy_cut_girdle_profile("pear", 8.0)
        assert gp["profile_shape"] == "pear"

    def test_emerald_is_rect_chamfer(self):
        gp = fancy_cut_girdle_profile("emerald", 7.0)
        assert gp["profile_shape"] == "rect_chamfer"
        assert gp["corner_radius_mm"] > 0

    def test_cushion_is_rect_chamfer_with_corner(self):
        gp = fancy_cut_girdle_profile("cushion", 5.5)
        assert gp["profile_shape"] == "rect_chamfer"
        assert gp["corner_radius_mm"] > 0

    def test_princess_is_square(self):
        gp = fancy_cut_girdle_profile("princess", 5.5)
        assert gp["profile_shape"] == "square"

    def test_clearance_increases_axes(self):
        gp0 = fancy_cut_girdle_profile("oval", 8.0, girdle_clearance_mm=0.0)
        gp1 = fancy_cut_girdle_profile("oval", 8.0, girdle_clearance_mm=0.1)
        assert gp1["long_axis_mm"] > gp0["long_axis_mm"]
        assert gp1["short_axis_mm"] > gp0["short_axis_mm"]

    def test_aspect_ratio_override(self):
        gp = fancy_cut_girdle_profile("oval", 8.0, aspect_ratio=0.8)
        assert gp["aspect_ratio"] == pytest.approx(0.8)

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_return_valid_profile(self, cut):
        gp = fancy_cut_girdle_profile(cut, 6.0)
        assert gp["long_axis_mm"] > 0
        assert gp["short_axis_mm"] > 0
        assert "profile_shape" in gp
        assert gp["cut"] == cut


# ---------------------------------------------------------------------------
# channel_seat_geometry() — pure-math tests
# ---------------------------------------------------------------------------

class TestChannelSeatGeometry:
    def _geom(self, n=3, pitch=2.5, diam=2.0):
        props = _props("round_brilliant", diameter_mm=diam)
        return channel_seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            n_stones=n,
            pitch_mm=pitch,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
        )

    def test_stone_count(self):
        g = self._geom(n=5)
        assert g["n_stones"] == 5
        assert len(g["stone_positions"]) == 5

    def test_pitch_stored(self):
        g = self._geom(pitch=3.0)
        assert g["pitch_mm"] == pytest.approx(3.0)

    def test_positions_spaced_correctly(self):
        g = self._geom(n=4, pitch=3.0)
        xs = [p[0] for p in g["stone_positions"]]
        for i in range(1, len(xs)):
            assert xs[i] - xs[i - 1] == pytest.approx(3.0, abs=1e-4)

    def test_groove_length_covers_row(self):
        g = self._geom(n=3, pitch=3.0, diam=2.0)
        # length = (n-1)*pitch + 2*girdle_radius
        expected_min = (3 - 1) * 3.0
        assert g["groove_length_mm"] > expected_min

    def test_groove_width_is_twice_girdle_radius(self):
        g = self._geom(diam=2.0)
        assert g["groove_width_mm"] == pytest.approx(
            2.0 * g["per_stone_geom"]["girdle_radius_mm"], abs=1e-4
        )

    def test_total_depth_matches_per_stone(self):
        g = self._geom()
        assert g["total_cutter_depth_mm"] == pytest.approx(
            g["per_stone_geom"]["total_cutter_depth_mm"], abs=1e-4
        )

    def test_spacing_must_exceed_diameter(self):
        props = _props("round_brilliant", diameter_mm=2.0)
        with pytest.raises(ValueError, match="pitch_mm"):
            channel_seat_geometry(
                cut="round_brilliant",
                diameter_mm=props.diameter_mm,
                n_stones=3,
                pitch_mm=1.5,   # less than diameter
                pavilion_angle_deg=props.pavilion_angle_deg,
                pavilion_depth_pct=props.pavilion_depth_pct,
                girdle_pct=props.girdle_pct,
                crown_angle_deg=props.crown_angle_deg,
            )

    def test_single_stone_channel(self):
        g = self._geom(n=1)
        assert len(g["stone_positions"]) == 1

    def test_axis_direction_custom(self):
        props = _props("round_brilliant", diameter_mm=2.0)
        g = channel_seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            n_stones=3,
            pitch_mm=2.5,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            axis_direction=[0.0, 1.0, 0.0],
        )
        # Y-axis: x stays 0, y increases
        assert g["stone_positions"][0][0] == pytest.approx(0.0)
        assert g["stone_positions"][1][1] == pytest.approx(2.5, abs=1e-4)


# ---------------------------------------------------------------------------
# bezel_seat_geometry() — pure-math tests
# ---------------------------------------------------------------------------

class TestBezealSeatGeometry:
    def _geom(self, cut="round_brilliant", diam=6.5, **kw):
        props = _props(cut, diameter_mm=diam)
        return bezel_seat_geometry(
            cut=cut,
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            **kw,
        )

    def test_seat_type_is_bezel(self):
        g = self._geom()
        assert g["seat_type"] == "bezel"

    def test_non_tapered_bore_equal_radii(self):
        g = self._geom(tapered=False)
        assert g["inner_bore_top_radius"] == pytest.approx(g["inner_bore_bottom_radius"])

    def test_tapered_bore_bottom_smaller(self):
        g = self._geom(tapered=True, taper_angle_deg=10.0, bezel_wall_height_mm=1.0)
        assert g["inner_bore_bottom_radius"] < g["inner_bore_top_radius"]

    def test_taper_angle_zero_when_not_tapered(self):
        g = self._geom(tapered=False)
        assert g["taper_angle_deg"] == pytest.approx(0.0)

    def test_wall_height_stored(self):
        g = self._geom(bezel_wall_height_mm=1.5)
        assert g["bezel_wall_height_mm"] == pytest.approx(1.5)

    def test_through_hole_propagates(self):
        g = self._geom(through_hole=True, through_hole_radius_mm=0.4)
        assert g["through_hole"] is True
        assert g["through_hole_radius_mm"] == pytest.approx(0.4)

    def test_girdle_profile_propagated_for_oval(self):
        props = _props("oval", diameter_mm=8.0)
        gp = fancy_cut_girdle_profile("oval", props.diameter_mm)
        g = bezel_seat_geometry(
            cut="oval",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            girdle_profile=gp,
        )
        assert "girdle_profile" in g
        assert g["girdle_profile"]["profile_shape"] == "ellipse"


# ---------------------------------------------------------------------------
# fishtail_seat_geometry() — pure-math tests
# ---------------------------------------------------------------------------

class TestFishtailSeatGeometry:
    def _geom(self, cut="round_brilliant", diam=2.5, **kw):
        props = _props(cut, diameter_mm=diam)
        return fishtail_seat_geometry(
            cut=cut,
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            **kw,
        )

    def test_seat_type_is_fishtail(self):
        g = self._geom()
        assert g["seat_type"] == "fishtail"

    def test_bright_cut_radius_exceeds_girdle(self):
        g = self._geom()
        assert g["bright_cut_radius_mm"] > g["girdle_radius_mm"]

    def test_n_bright_facets_stored(self):
        g = self._geom(n_bright_facets=6)
        assert g["n_bright_facets"] == 6

    def test_bright_cut_depth_stored(self):
        g = self._geom(bright_cut_depth_mm=0.20)
        assert g["bright_cut_depth_mm"] == pytest.approx(0.20)

    def test_bright_cut_angle_stored(self):
        g = self._geom(bright_cut_angle_deg=30.0)
        assert g["bright_cut_angle_deg"] == pytest.approx(30.0)

    def test_radius_formula(self):
        import math
        angle = 45.0
        depth = 0.15
        props = _props(diameter_mm=2.5)
        g = fishtail_seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=props.girdle_pct,
            crown_angle_deg=props.crown_angle_deg,
            bright_cut_angle_deg=angle,
            bright_cut_depth_mm=depth,
        )
        expected_extra = depth * math.tan(math.radians(angle))
        expected_radius = g["girdle_radius_mm"] + expected_extra
        assert g["bright_cut_radius_mm"] == pytest.approx(expected_radius, abs=1e-4)

    def test_through_hole_propagates(self):
        g = self._geom(through_hole=True, through_hole_radius_mm=0.3)
        assert g["through_hole"] is True


# ---------------------------------------------------------------------------
# multi_stone_seat_geometry() — pure-math tests
# ---------------------------------------------------------------------------

class TestMultiStoneSeatGeometry:
    def _geom(self, cut="round_brilliant", center_diam=6.5, side_diam=4.0,
              n_side=2, pitch=7.5):
        center_props = _props(cut, diameter_mm=center_diam)
        side_props   = _props(cut, diameter_mm=side_diam)
        return multi_stone_seat_geometry(
            cut=cut,
            center_diameter_mm=center_props.diameter_mm,
            side_diameter_mm=side_props.diameter_mm,
            n_side_stones=n_side,
            side_pitch_mm=pitch,
            center_pavilion_angle_deg=center_props.pavilion_angle_deg,
            center_pavilion_depth_pct=center_props.pavilion_depth_pct,
            center_girdle_pct=center_props.girdle_pct,
            center_crown_angle_deg=center_props.crown_angle_deg,
            side_pavilion_angle_deg=side_props.pavilion_angle_deg,
            side_pavilion_depth_pct=side_props.pavilion_depth_pct,
            side_girdle_pct=side_props.girdle_pct,
            side_crown_angle_deg=side_props.crown_angle_deg,
        )

    def test_seat_type_is_multi_stone(self):
        g = self._geom()
        assert g["seat_type"] == "multi_stone"

    def test_side_positions_symmetric(self):
        g = self._geom(n_side=2, pitch=7.5)
        xs = sorted(p[0] for p in g["side_positions"])
        assert xs[0] == pytest.approx(-xs[-1], abs=1e-4)

    def test_n_side_stones_count(self):
        g = self._geom(n_side=4, pitch=7.5)
        assert len(g["side_positions"]) == 4

    def test_center_position_is_origin(self):
        g = self._geom()
        assert g["center_position"] == [0.0, 0.0, 0.0]

    def test_total_depth_is_max(self):
        g = self._geom()
        assert g["total_cutter_depth_mm"] == pytest.approx(
            max(
                g["center_seat_geom"]["total_cutter_depth_mm"],
                g["side_seat_geom"]["total_cutter_depth_mm"],
            ),
            abs=1e-4,
        )

    def test_odd_n_side_rejected(self):
        with pytest.raises(ValueError, match="even"):
            self._geom(n_side=3)

    def test_n_side_less_than_2_rejected(self):
        with pytest.raises(ValueError, match="n_side_stones"):
            self._geom(n_side=0)

    def test_pitch_too_small_rejected(self):
        with pytest.raises(ValueError, match="side_pitch_mm"):
            self._geom(center_diam=6.5, side_diam=4.0, pitch=3.0)

    def test_through_hole_center_propagates(self):
        center_props = _props(diameter_mm=6.5)
        side_props   = _props(diameter_mm=4.0)
        g = multi_stone_seat_geometry(
            cut="round_brilliant",
            center_diameter_mm=center_props.diameter_mm,
            side_diameter_mm=side_props.diameter_mm,
            n_side_stones=2,
            side_pitch_mm=7.5,
            center_pavilion_angle_deg=center_props.pavilion_angle_deg,
            center_pavilion_depth_pct=center_props.pavilion_depth_pct,
            center_girdle_pct=center_props.girdle_pct,
            center_crown_angle_deg=center_props.crown_angle_deg,
            side_pavilion_angle_deg=side_props.pavilion_angle_deg,
            side_pavilion_depth_pct=side_props.pavilion_depth_pct,
            side_girdle_pct=side_props.girdle_pct,
            side_crown_angle_deg=side_props.crown_angle_deg,
            through_hole_center=True,
            through_hole_radius_mm=0.4,
        )
        assert g["center_seat_geom"]["through_hole"] is True
        assert g["side_seat_geom"]["through_hole"] is False


# ---------------------------------------------------------------------------
# LLM tool specs — structural checks
# ---------------------------------------------------------------------------

class TestToolSpecs:
    @pytest.mark.parametrize("spec,expected_name", [
        (jewelry_cut_gem_seat_spec,        "jewelry_cut_gem_seat"),
        (jewelry_cut_channel_seat_spec,    "jewelry_cut_channel_seat"),
        (jewelry_cut_bezel_seat_spec,      "jewelry_cut_bezel_seat"),
        (jewelry_cut_fishtail_seat_spec,   "jewelry_cut_fishtail_seat"),
        (jewelry_cut_multi_stone_seat_spec,"jewelry_cut_multi_stone_seat"),
    ])
    def test_name(self, spec, expected_name):
        assert spec.name == expected_name

    def test_gem_seat_required_fields(self):
        req = jewelry_cut_gem_seat_spec.input_schema.get("required", [])
        assert "file_id" in req
        assert "cut" in req

    def test_channel_seat_required_includes_n_stones_and_pitch(self):
        req = jewelry_cut_channel_seat_spec.input_schema.get("required", [])
        assert "n_stones" in req
        assert "pitch_mm" in req

    def test_multi_stone_required_includes_pitch(self):
        req = jewelry_cut_multi_stone_seat_spec.input_schema.get("required", [])
        assert "side_pitch_mm" in req

    def test_cut_enum_matches_registry(self):
        props = jewelry_cut_gem_seat_spec.input_schema["properties"]
        enum = set(props["cut"].get("enum", []))
        assert enum == GEMSTONE_CUTS

    def test_optional_clearance_fields_in_gem_seat(self):
        props = jewelry_cut_gem_seat_spec.input_schema["properties"]
        for field in ("girdle_clearance_mm", "culet_clearance_mm",
                      "crown_relief_mm", "through_hole"):
            assert field in props

    def test_gem_seat_has_girdle_shape_param(self):
        props = jewelry_cut_gem_seat_spec.input_schema["properties"]
        assert "girdle_shape" in props

    def test_bezel_seat_has_tapered_param(self):
        props = jewelry_cut_bezel_seat_spec.input_schema["properties"]
        assert "tapered" in props
        assert "bezel_wall_height_mm" in props

    def test_fishtail_seat_has_bright_cut_params(self):
        props = jewelry_cut_fishtail_seat_spec.input_schema["properties"]
        assert "bright_cut_angle_deg" in props
        assert "n_bright_facets" in props


# ---------------------------------------------------------------------------
# LLM tool runner — success paths: existing single-seat (back-compat)
# ---------------------------------------------------------------------------

class TestRunJewelryCutGemSeat:
    def test_basic_round_brilliant_by_carat(self):
        ctx, store, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut="round_brilliant", carat=1.0)
        assert result.get("error") is None, result
        assert result["op"] == "gem_seat"
        assert result["cut"] == "round_brilliant"
        assert result["diameter_mm"] == pytest.approx(6.5, rel=1e-4)
        assert result["total_cutter_depth_mm"] > 0

    def test_node_appended_to_feature_doc(self):
        ctx, store, fid = make_ctx()
        run_gem_seat(ctx, fid, cut="princess", diameter_mm=5.5)
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1
        node = doc["features"][0]
        assert node["op"] == "gem_seat"

    def test_node_id_starts_with_gem_seat(self):
        ctx, store, fid = make_ctx()
        run_gem_seat(ctx, fid, cut="oval", diameter_mm=7.0)
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"].startswith("gem_seat-")

    def test_explicit_id_stored(self):
        ctx, store, fid = make_ctx()
        run_gem_seat(ctx, fid, cut="emerald", diameter_mm=7.0, id="seat-custom")
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"] == "seat-custom"

    def test_geometry_keys_stored_in_node(self):
        ctx, store, fid = make_ctx()
        run_gem_seat(ctx, fid, cut="round_brilliant", diameter_mm=6.5)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        for key in ("girdle_radius_mm", "pavilion_depth_mm", "total_cutter_depth_mm"):
            assert key in node, f"Missing key: {key}"

    def test_through_hole_stored_when_true(self):
        ctx, store, fid = make_ctx()
        run_gem_seat(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                     through_hole=True, through_hole_radius_mm=0.5)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["through_hole"] is True
        assert node["through_hole_radius_mm"] == pytest.approx(0.5)

    def test_position_stored_in_node(self):
        ctx, store, fid = make_ctx()
        run_gem_seat(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                     position=[0.0, 0.0, 5.0])
        doc = json.loads(store["content"])
        assert doc["features"][0]["position"] == [0.0, 0.0, 5.0]

    def test_auto_cut_appends_boolean_node(self):
        initial_doc = {
            "version": 1,
            "features": [{"id": "sweep1-1", "op": "sweep1",
                           "profile_sketch_path": "/p.sketch",
                           "path_sketch_path": "/r.sketch"}],
        }
        ctx, store, fid = make_ctx(json.dumps(initial_doc))
        result = run_gem_seat(ctx, fid, cut="round_brilliant", carat=1.0,
                              auto_cut_host_id="sweep1-1")
        assert result.get("error") is None, result
        assert "seat_id" in result
        assert "boolean_id" in result

        doc = json.loads(store["content"])
        ops = [n["op"] for n in doc["features"]]
        assert "gem_seat" in ops
        assert "boolean" in ops

        bool_node = next(n for n in doc["features"] if n["op"] == "boolean")
        assert bool_node["kind"] == "cut"
        assert bool_node["target_a_id"] == "sweep1-1"
        assert bool_node["target_b_id"] == result["seat_id"]

    def test_fancy_cut_girdle_profile_stored_for_oval(self):
        ctx, store, fid = make_ctx()
        run_gem_seat(ctx, fid, cut="oval", diameter_mm=8.0)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert "girdle_profile" in node
        assert node["girdle_profile"]["profile_shape"] == "ellipse"

    def test_round_brilliant_no_girdle_profile_by_default(self):
        ctx, store, fid = make_ctx()
        run_gem_seat(ctx, fid, cut="round_brilliant", diameter_mm=6.5)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert "girdle_profile" not in node

    def test_girdle_shape_override(self):
        ctx, store, fid = make_ctx()
        # Use round_brilliant cut proportions but oval girdle profile
        run_gem_seat(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                     girdle_shape="oval")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert "girdle_profile" in node
        assert node["girdle_profile"]["profile_shape"] == "ellipse"

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_succeed(self, cut):
        ctx, store, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut=cut, diameter_mm=5.0)
        assert result.get("error") is None, f"{cut}: {result}"


# ---------------------------------------------------------------------------
# LLM tool runner — success paths: channel seat
# ---------------------------------------------------------------------------

class TestRunChannelSeat:
    def test_basic_channel_succeeds(self):
        ctx, store, fid = make_ctx()
        result = run_channel(ctx, fid, cut="round_brilliant", diameter_mm=2.0,
                             n_stones=5, pitch_mm=2.5)
        assert result.get("error") is None, result
        assert result["op"] == "channel_seat"
        assert result["n_stones"] == 5

    def test_node_stored_in_feature_doc(self):
        ctx, store, fid = make_ctx()
        run_channel(ctx, fid, cut="round_brilliant", diameter_mm=2.0,
                    n_stones=3, pitch_mm=2.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "channel_seat"

    def test_node_id_starts_with_channel_seat(self):
        ctx, store, fid = make_ctx()
        run_channel(ctx, fid, cut="round_brilliant", diameter_mm=2.0,
                    n_stones=3, pitch_mm=2.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"].startswith("channel_seat-")

    def test_stone_positions_in_node(self):
        ctx, store, fid = make_ctx()
        run_channel(ctx, fid, cut="round_brilliant", diameter_mm=2.0,
                    n_stones=3, pitch_mm=2.5)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert len(node["stone_positions"]) == 3

    def test_auto_cut_chains_boolean(self):
        initial_doc = {
            "version": 1,
            "features": [{"id": "band-1", "op": "sweep1",
                           "profile_sketch_path": "/p.sketch",
                           "path_sketch_path": "/r.sketch"}],
        }
        ctx, store, fid = make_ctx(json.dumps(initial_doc))
        result = run_channel(ctx, fid, cut="round_brilliant", diameter_mm=2.0,
                             n_stones=3, pitch_mm=2.5,
                             auto_cut_host_id="band-1")
        assert "seat_id" in result
        assert "boolean_id" in result

    def test_pitch_equal_to_diameter_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_channel(ctx, fid, cut="round_brilliant", diameter_mm=2.0,
                             n_stones=3, pitch_mm=2.0)  # pitch == diameter
        assert result.get("code") == "BAD_ARGS"

    def test_pitch_less_than_diameter_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_channel(ctx, fid, cut="round_brilliant", diameter_mm=2.0,
                             n_stones=3, pitch_mm=1.5)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_n_stones_defaults_to_error(self):
        ctx, store, fid = make_ctx()
        result = run_channel(ctx, fid, cut="round_brilliant", diameter_mm=2.0,
                             pitch_mm=2.5)
        # n_stones defaults to 0 -> should fail
        assert result.get("code") == "BAD_ARGS"

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_channel_succeed(self, cut):
        ctx, store, fid = make_ctx()
        result = run_channel(ctx, fid, cut=cut, diameter_mm=2.0,
                             n_stones=3, pitch_mm=2.5)
        assert result.get("error") is None, f"{cut}: {result}"


# ---------------------------------------------------------------------------
# LLM tool runner — success paths: bezel seat
# ---------------------------------------------------------------------------

class TestRunBezealSeat:
    def test_basic_bezel_succeeds(self):
        ctx, store, fid = make_ctx()
        result = run_bezel(ctx, fid, cut="round_brilliant", diameter_mm=6.5)
        assert result.get("error") is None, result
        assert result["op"] == "bezel_seat"

    def test_node_stored_in_feature_doc(self):
        ctx, store, fid = make_ctx()
        run_bezel(ctx, fid, cut="round_brilliant", diameter_mm=6.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "bezel_seat"

    def test_node_id_starts_with_bezel_seat(self):
        ctx, store, fid = make_ctx()
        run_bezel(ctx, fid, cut="round_brilliant", diameter_mm=6.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"].startswith("bezel_seat-")

    def test_tapered_stored(self):
        ctx, store, fid = make_ctx()
        result = run_bezel(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                           tapered=True, taper_angle_deg=8.0)
        assert result["tapered"] is True
        doc = json.loads(store["content"])
        assert doc["features"][0]["tapered"] is True

    def test_fancy_cut_oval_stores_girdle_profile(self):
        ctx, store, fid = make_ctx()
        run_bezel(ctx, fid, cut="oval", diameter_mm=8.0)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert "girdle_profile" in node

    def test_auto_cut_chains_boolean(self):
        initial_doc = {
            "version": 1,
            "features": [{"id": "bezel-shell-1", "op": "sweep1",
                           "profile_sketch_path": "/p.sketch",
                           "path_sketch_path": "/r.sketch"}],
        }
        ctx, store, fid = make_ctx(json.dumps(initial_doc))
        result = run_bezel(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                           auto_cut_host_id="bezel-shell-1")
        assert "seat_id" in result
        assert "boolean_id" in result

    def test_negative_bezel_wall_height_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_bezel(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                           bezel_wall_height_mm=-0.5)
        assert result.get("code") == "BAD_ARGS"

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_bezel_succeed(self, cut):
        ctx, store, fid = make_ctx()
        result = run_bezel(ctx, fid, cut=cut, diameter_mm=5.0)
        assert result.get("error") is None, f"{cut}: {result}"


# ---------------------------------------------------------------------------
# LLM tool runner — success paths: fishtail seat
# ---------------------------------------------------------------------------

class TestRunFishtailSeat:
    def test_basic_fishtail_succeeds(self):
        ctx, store, fid = make_ctx()
        result = run_fishtail(ctx, fid, cut="round_brilliant", diameter_mm=2.5)
        assert result.get("error") is None, result
        assert result["op"] == "fishtail_seat"

    def test_node_stored_in_feature_doc(self):
        ctx, store, fid = make_ctx()
        run_fishtail(ctx, fid, cut="round_brilliant", diameter_mm=2.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "fishtail_seat"

    def test_node_id_starts_with_fishtail_seat(self):
        ctx, store, fid = make_ctx()
        run_fishtail(ctx, fid, cut="round_brilliant", diameter_mm=2.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"].startswith("fishtail_seat-")

    def test_n_bright_facets_stored(self):
        ctx, store, fid = make_ctx()
        run_fishtail(ctx, fid, cut="round_brilliant", diameter_mm=2.5,
                     n_bright_facets=6)
        doc = json.loads(store["content"])
        assert doc["features"][0]["n_bright_facets"] == 6

    def test_bright_cut_radius_in_result(self):
        ctx, store, fid = make_ctx()
        result = run_fishtail(ctx, fid, cut="round_brilliant", diameter_mm=2.5)
        assert "bright_cut_radius_mm" in result
        assert result["bright_cut_radius_mm"] > 0

    def test_auto_cut_chains_boolean(self):
        initial_doc = {
            "version": 1,
            "features": [{"id": "shank-1", "op": "sweep1",
                           "profile_sketch_path": "/p.sketch",
                           "path_sketch_path": "/r.sketch"}],
        }
        ctx, store, fid = make_ctx(json.dumps(initial_doc))
        result = run_fishtail(ctx, fid, cut="round_brilliant", diameter_mm=2.5,
                              auto_cut_host_id="shank-1")
        assert "seat_id" in result
        assert "boolean_id" in result

    def test_zero_n_bright_facets_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_fishtail(ctx, fid, cut="round_brilliant", diameter_mm=2.5,
                              n_bright_facets=0)
        assert result.get("code") == "BAD_ARGS"

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_fishtail_succeed(self, cut):
        ctx, store, fid = make_ctx()
        result = run_fishtail(ctx, fid, cut=cut, diameter_mm=2.5)
        assert result.get("error") is None, f"{cut}: {result}"


# ---------------------------------------------------------------------------
# LLM tool runner — success paths: multi-stone seat
# ---------------------------------------------------------------------------

class TestRunMultiStoneSeat:
    def test_basic_three_stone_succeeds(self):
        ctx, store, fid = make_ctx()
        result = run_multi(ctx, fid, cut="round_brilliant",
                           center_diameter_mm=6.5, side_diameter_mm=4.0,
                           n_side_stones=2, side_pitch_mm=7.5)
        assert result.get("error") is None, result
        assert result["op"] == "multi_stone_seat"
        assert result["n_side_stones"] == 2

    def test_node_stored_in_feature_doc(self):
        ctx, store, fid = make_ctx()
        run_multi(ctx, fid, cut="round_brilliant",
                  center_diameter_mm=6.5, side_diameter_mm=4.0,
                  n_side_stones=2, side_pitch_mm=7.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "multi_stone_seat"

    def test_node_id_starts_with_multi_stone_seat(self):
        ctx, store, fid = make_ctx()
        run_multi(ctx, fid, cut="round_brilliant",
                  center_diameter_mm=6.5, side_diameter_mm=4.0,
                  n_side_stones=2, side_pitch_mm=7.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"].startswith("multi_stone_seat-")

    def test_side_positions_in_result_and_node(self):
        ctx, store, fid = make_ctx()
        result = run_multi(ctx, fid, cut="round_brilliant",
                           center_diameter_mm=6.5, side_diameter_mm=4.0,
                           n_side_stones=2, side_pitch_mm=7.5)
        assert len(result["side_positions"]) == 2
        doc = json.loads(store["content"])
        assert len(doc["features"][0]["side_positions"]) == 2

    def test_auto_cut_chains_boolean(self):
        initial_doc = {
            "version": 1,
            "features": [{"id": "ring-1", "op": "sweep1",
                           "profile_sketch_path": "/p.sketch",
                           "path_sketch_path": "/r.sketch"}],
        }
        ctx, store, fid = make_ctx(json.dumps(initial_doc))
        result = run_multi(ctx, fid, cut="round_brilliant",
                           center_diameter_mm=6.5, side_diameter_mm=4.0,
                           n_side_stones=2, side_pitch_mm=7.5,
                           auto_cut_host_id="ring-1")
        assert "seat_id" in result
        assert "boolean_id" in result

    def test_odd_n_side_stones_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_multi(ctx, fid, cut="round_brilliant",
                           center_diameter_mm=6.5, side_diameter_mm=4.0,
                           n_side_stones=3, side_pitch_mm=7.5)
        assert result.get("code") == "BAD_ARGS"

    def test_n_side_less_than_2_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_multi(ctx, fid, cut="round_brilliant",
                           center_diameter_mm=6.5, side_diameter_mm=4.0,
                           n_side_stones=0, side_pitch_mm=7.5)
        assert result.get("code") == "BAD_ARGS"

    def test_pitch_too_small_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_multi(ctx, fid, cut="round_brilliant",
                           center_diameter_mm=6.5, side_diameter_mm=4.0,
                           n_side_stones=2, side_pitch_mm=3.0)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_center_size_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_multi(ctx, fid, cut="round_brilliant",
                           side_diameter_mm=4.0,
                           n_side_stones=2, side_pitch_mm=7.5)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_side_size_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_multi(ctx, fid, cut="round_brilliant",
                           center_diameter_mm=6.5,
                           n_side_stones=2, side_pitch_mm=7.5)
        assert result.get("code") == "BAD_ARGS"

    def test_five_stone_setting(self):
        ctx, store, fid = make_ctx()
        result = run_multi(ctx, fid, cut="round_brilliant",
                           center_diameter_mm=6.5, side_diameter_mm=4.0,
                           n_side_stones=4, side_pitch_mm=7.5)
        assert result.get("error") is None, result
        assert len(result["side_positions"]) == 4

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_multi_stone_succeed(self, cut):
        ctx, store, fid = make_ctx()
        result = run_multi(ctx, fid, cut=cut,
                           center_diameter_mm=5.0, side_diameter_mm=3.5,
                           n_side_stones=2, side_pitch_mm=6.0)
        assert result.get("error") is None, f"{cut}: {result}"


# ---------------------------------------------------------------------------
# LLM tool runner — shared error paths
# ---------------------------------------------------------------------------

class TestRunJewelryCutGemSeatErrors:
    def test_invalid_json(self):
        ctx, _, _ = make_ctx()
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(
            run_jewelry_cut_gem_seat(ctx, b"not json")
        )
        loop.close()
        assert json.loads(raw).get("code") == "BAD_ARGS"

    def test_missing_file_id(self):
        ctx, _, _ = make_ctx()
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(
            run_jewelry_cut_gem_seat(ctx, json.dumps({
                "cut": "round_brilliant", "carat": 1.0
            }).encode())
        )
        loop.close()
        assert json.loads(raw).get("code") == "BAD_ARGS"

    def test_unknown_cut(self):
        ctx, _, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut="kite", diameter_mm=5.0)
        assert result.get("code") == "BAD_ARGS"

    def test_negative_carat(self):
        ctx, _, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut="round_brilliant", carat=-1.0)
        assert result.get("code") == "BAD_ARGS"

    def test_zero_diameter(self):
        ctx, _, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut="round_brilliant", diameter_mm=0.0)
        assert result.get("code") == "BAD_ARGS"

    def test_both_carat_and_diameter(self):
        ctx, _, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut="round_brilliant",
                              carat=1.0, diameter_mm=6.5)
        assert result.get("code") == "BAD_ARGS"

    def test_neither_carat_nor_diameter(self):
        ctx, _, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut="round_brilliant")
        assert result.get("code") == "BAD_ARGS"

    def test_non_uuid_file_id(self):
        ctx, _, _ = make_ctx()
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(
            run_jewelry_cut_gem_seat(ctx, json.dumps({
                "file_id": "bad-uuid", "cut": "round_brilliant", "carat": 1.0
            }).encode())
        )
        loop.close()
        assert json.loads(raw).get("code") == "BAD_ARGS"

    def test_non_existent_file(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        result = run_gem_seat(ctx, fid, cut="round_brilliant", carat=1.0)
        assert result.get("code") == "NOT_FOUND"

    def test_negative_girdle_clearance(self):
        ctx, _, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                              girdle_clearance_mm=-0.1)
        assert result.get("code") == "BAD_ARGS"

    def test_negative_through_hole_radius(self):
        ctx, _, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                              through_hole=True, through_hole_radius_mm=-0.5)
        assert result.get("code") == "BAD_ARGS"

    def test_invalid_girdle_shape(self):
        ctx, _, fid = make_ctx()
        result = run_gem_seat(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                              girdle_shape="kite")
        assert result.get("code") == "BAD_ARGS"
