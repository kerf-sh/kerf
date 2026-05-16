"""
Tests for kerf_cad_core.jewelry.bezel_auto

Coverage (>=30 hermetic tests, pure Python — no OCC required):

  1.  Inner profile matches stone outline within tolerance.
  2.  Bezel wall >= min-wall rule.
  3.  Height proportional to stone size.
  4.  Tube setting: ID = girdle + clearance; OD = ID + 2·wall.
  5.  Tube volume = (OD² − ID²) × π/4 × h (exact formula).
  6.  Under-gallery cutout volume subtracts correctly.
  7.  Warning fires when explicit wall < min-wall.
  8.  Error dict returned (never raises) for bad inputs.
  9.  Style-specific geometry: bombe peak, scallop notches, half-bezel tabs,
      v_bezel taper, illusion plate.
 10.  Seat groove position and spec keys present.
 11.  Seat cutter compatible dict present (_seat_cutter key).
 12.  LLM tool runners: BAD_ARGS rejection + happy-path ok_payload.
 13.  All BEZEL_STYLES produce a node without error.
 14.  Multiple cuts produce correct profile_shape.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
import warnings

import pytest

from kerf_cad_core.jewelry.bezel_auto import (
    BEZEL_STYLES,
    EDGE_TREATMENTS,
    _MIN_WALL_TABLE,
    _HEIGHT_FACTOR,
    _min_wall_for_stone,
    _girdle_profile_shape,
    bezel_auto_from_stone,
    bezel_auto_node,
    tube_setting_auto,
    tube_setting_node,
    jewelry_bezel_auto_spec,
    jewelry_tube_setting_auto_spec,
    run_jewelry_bezel_auto_from_stone,
    run_jewelry_tube_setting_auto,
)

_PI = math.pi


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(initial_content: str = ""):
    store = {
        "content": initial_content or json.dumps({"version": 1, "features": []}),
        "kind": "feature",
    }
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            store["content"] = args[0]

    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    except ImportError:
        class ProjectCtx:  # type: ignore[no-redef]
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, store, file_id


def make_ctx_not_found():
    """Return a ctx where every fetchone returns None (file not found)."""
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePoolNotFound:
        def fetchone(self, query, *args):
            return None

        def execute(self, query, *args):
            pass

    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    except ImportError:
        class ProjectCtx:  # type: ignore[no-redef]
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

    ctx = ProjectCtx(
        pool=FakePoolNotFound(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, file_id


def run_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return json.loads(loop.run_until_complete(coro))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 1. Min-wall rule
# ---------------------------------------------------------------------------

class TestMinWallRule:
    def test_very_small_stone_uses_smallest_wall(self):
        assert _min_wall_for_stone(1.5) == 0.30

    def test_medium_stone_5mm(self):
        w = _min_wall_for_stone(5.0)
        assert w == 0.40

    def test_large_stone_10mm(self):
        w = _min_wall_for_stone(10.0)
        assert w == 0.50

    def test_huge_stone_25mm(self):
        w = _min_wall_for_stone(25.0)
        assert w == 0.70

    def test_wall_increases_with_stone(self):
        w_small = _min_wall_for_stone(2.0)
        w_large = _min_wall_for_stone(15.0)
        assert w_large >= w_small


# ---------------------------------------------------------------------------
# 2. Inner profile matches stone outline
# ---------------------------------------------------------------------------

class TestInnerProfile:
    def test_round_brilliant_inner_ge_stone_plus_clearance(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        assert "error" not in spec
        clearance = 0.05
        expected_inner = 6.5 + 2.0 * clearance
        assert abs(spec["inner_long_mm"] - expected_inner) < 1e-4

    def test_oval_inner_short_uses_aspect_ratio(self):
        spec = bezel_auto_from_stone("oval", 7.7, "straight")
        ar = spec["aspect_ratio"]
        expected_short = 7.7 * ar + 2.0 * 0.05
        assert abs(spec["inner_short_mm"] - expected_short) < 1e-4

    def test_emerald_profile_shape_is_rect_chamfer(self):
        spec = bezel_auto_from_stone("emerald", 7.0, "straight")
        assert spec["inner_profile_shape"] == "rect_chamfer"

    def test_round_brilliant_profile_is_circle(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        assert spec["inner_profile_shape"] == "circle"

    def test_princess_profile_is_polygon(self):
        spec = bezel_auto_from_stone("princess", 5.5, "straight")
        assert spec["inner_profile_shape"] == "polygon"

    def test_marquise_profile_is_stadium(self):
        spec = bezel_auto_from_stone("marquise", 10.0, "straight")
        assert spec["inner_profile_shape"] == "stadium"

    def test_trillion_profile_is_triangle(self):
        spec = bezel_auto_from_stone("trillion", 7.0, "straight")
        assert spec["inner_profile_shape"] == "triangle"

    def test_pear_profile_is_pear(self):
        spec = bezel_auto_from_stone("pear", 8.0, "straight")
        assert spec["inner_profile_shape"] == "pear"

    def test_custom_clearance_reflected_in_inner_long(self):
        clearance = 0.10
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                     girdle_clearance_mm=clearance)
        expected = 6.5 + 2.0 * clearance
        assert abs(spec["inner_long_mm"] - expected) < 1e-4


# ---------------------------------------------------------------------------
# 3. Bezel wall >= min-wall
# ---------------------------------------------------------------------------

class TestWallMinimum:
    def test_auto_wall_gte_min_wall_small_stone(self):
        spec = bezel_auto_from_stone("round_brilliant", 2.0, "straight")
        assert spec["wall_thickness_mm"] >= spec["min_wall_mm"]

    def test_auto_wall_gte_min_wall_large_stone(self):
        spec = bezel_auto_from_stone("emerald", 12.0, "straight")
        assert spec["wall_thickness_mm"] >= spec["min_wall_mm"]

    def test_explicit_wall_accepted(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                     wall_thickness=0.5)
        assert abs(spec["wall_thickness_mm"] - 0.5) < 1e-4

    def test_warning_when_wall_below_min(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                         wall_thickness=0.10)
        # Should have issued a warning
        assert any("below recommended minimum" in str(warning.message) for warning in w)
        # Spec is still returned (never raises)
        assert spec["wall_thickness_mm"] == pytest.approx(0.10, abs=1e-4)

    def test_outer_long_equals_inner_plus_two_walls(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                     wall_thickness=0.5)
        expected_outer = spec["inner_long_mm"] + 2.0 * spec["wall_thickness_mm"]
        assert abs(spec["outer_long_mm"] - expected_outer) < 1e-4


# ---------------------------------------------------------------------------
# 4. Height proportional to stone size
# ---------------------------------------------------------------------------

class TestHeight:
    def test_auto_height_is_factor_times_stone(self):
        stone_mm = 6.5
        spec = bezel_auto_from_stone("round_brilliant", stone_mm, "straight")
        expected_h = _HEIGHT_FACTOR * stone_mm
        assert abs(spec["bezel_height_mm"] - expected_h) < 1e-3

    def test_larger_stone_has_larger_height(self):
        h_small = bezel_auto_from_stone("round_brilliant", 4.0, "straight")["bezel_height_mm"]
        h_large = bezel_auto_from_stone("round_brilliant", 8.0, "straight")["bezel_height_mm"]
        assert h_large > h_small

    def test_explicit_height_respected(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                     bezel_height=1.5)
        assert abs(spec["bezel_height_mm"] - 1.5) < 1e-4

    def test_height_at_least_0_5mm(self):
        # Even for tiny stone the height floor is 0.5 mm.
        spec = bezel_auto_from_stone("single_cut", 1.0, "straight")
        assert spec["bezel_height_mm"] >= 0.5


# ---------------------------------------------------------------------------
# 5. Tube setting: ID and OD relationships
# ---------------------------------------------------------------------------

class TestTubeSetting:
    def test_id_equals_girdle_plus_clearance(self):
        stone_mm = 6.5
        clearance = 0.05
        spec = tube_setting_auto(stone_mm, girdle_clearance_mm=clearance)
        assert abs(spec["id_mm"] - (stone_mm + 2.0 * clearance)) < 1e-4

    def test_od_equals_id_plus_two_walls(self):
        spec = tube_setting_auto(6.5, wall_thickness=0.5)
        expected_od = spec["id_mm"] + 2.0 * spec["wall_thickness_mm"]
        assert abs(spec["od_mm"] - expected_od) < 1e-4

    def test_id_od_with_custom_clearance(self):
        clearance = 0.08
        spec = tube_setting_auto(5.0, girdle_clearance_mm=clearance)
        expected_id = 5.0 + 2.0 * clearance
        assert abs(spec["id_mm"] - expected_id) < 1e-4

    def test_tube_height_proportional(self):
        spec_small = tube_setting_auto(4.0)
        spec_large = tube_setting_auto(8.0)
        assert spec_large["tube_height_mm"] > spec_small["tube_height_mm"]

    def test_explicit_tube_height(self):
        spec = tube_setting_auto(6.5, tube_height=2.0)
        assert abs(spec["tube_height_mm"] - 2.0) < 1e-4

    def test_tube_wall_gte_min_wall(self):
        spec = tube_setting_auto(6.5)
        assert spec["wall_thickness_mm"] >= spec["min_wall_mm"]

    def test_tube_warning_below_min_wall(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tube_setting_auto(6.5, wall_thickness=0.05)
        assert any("below recommended minimum" in str(warning.message) for warning in w)


# ---------------------------------------------------------------------------
# 6. Tube volume exact formula
# ---------------------------------------------------------------------------

class TestTubeVolume:
    def test_volume_exact_annular_cylinder(self):
        spec = tube_setting_auto(6.5, wall_thickness=0.5, tube_height=3.0)
        od = spec["od_mm"]
        id_ = spec["id_mm"]
        h = spec["tube_height_mm"]
        expected_vol = (od ** 2 - id_ ** 2) * _PI / 4.0 * h
        assert abs(spec["_volume_mm3"] - expected_vol) < 1e-3

    def test_volume_increases_with_od(self):
        spec_thin = tube_setting_auto(6.5, wall_thickness=0.4, tube_height=2.0)
        spec_thick = tube_setting_auto(6.5, wall_thickness=0.8, tube_height=2.0)
        assert spec_thick["_volume_mm3"] > spec_thin["_volume_mm3"]

    def test_volume_increases_with_height(self):
        spec_short = tube_setting_auto(6.5, wall_thickness=0.5, tube_height=1.0)
        spec_tall = tube_setting_auto(6.5, wall_thickness=0.5, tube_height=3.0)
        assert spec_tall["_volume_mm3"] > spec_short["_volume_mm3"]


# ---------------------------------------------------------------------------
# 7. Under-gallery cutout volume
# ---------------------------------------------------------------------------

class TestUnderGalleryCutout:
    def test_cutout_volume_nonzero_when_enabled(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                     under_gallery_cutout=True)
        assert spec["gallery_cutout_volume_mm3"] > 0.0

    def test_cutout_volume_zero_when_disabled(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                     under_gallery_cutout=False)
        assert spec["gallery_cutout_volume_mm3"] == 0.0

    def test_volume_with_cutout_lt_volume_without(self):
        spec_no = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                        under_gallery_cutout=False)
        spec_yes = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                         under_gallery_cutout=True)
        assert spec_yes["_volume_mm3"] < spec_no["_volume_mm3"]

    def test_cutout_height_default_is_half_bezel_height(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                     under_gallery_cutout=True)
        expected_h = spec["bezel_height_mm"] * 0.5
        assert abs(spec["gallery_cutout_height_mm"] - expected_h) < 0.01

    def test_cutout_height_override(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                     under_gallery_cutout=True,
                                     gallery_cutout_height=0.8)
        assert abs(spec["gallery_cutout_height_mm"] - 0.8) < 1e-4


# ---------------------------------------------------------------------------
# 8. Error dict for bad inputs (never raises)
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_invalid_cut_returns_error_dict(self):
        spec = bezel_auto_from_stone("dragon_cut", 6.5, "straight")
        assert "error" in spec

    def test_negative_stone_mm_returns_error(self):
        spec = bezel_auto_from_stone("round_brilliant", -1.0, "straight")
        assert "error" in spec

    def test_zero_stone_mm_returns_error(self):
        spec = bezel_auto_from_stone("round_brilliant", 0.0, "straight")
        assert "error" in spec

    def test_invalid_style_returns_error(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "flying_saucer")
        assert "error" in spec

    def test_invalid_edge_treatment_returns_error(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight",
                                     edge_treatment="laser_cut")
        assert "error" in spec

    def test_tube_invalid_stone_mm_returns_error(self):
        spec = tube_setting_auto(-5.0)
        assert "error" in spec

    def test_tube_zero_stone_mm_returns_error(self):
        spec = tube_setting_auto(0)
        assert "error" in spec


# ---------------------------------------------------------------------------
# 9. Style-specific geometry
# ---------------------------------------------------------------------------

class TestStyleGeometry:
    def test_bombe_has_peak_od_gt_base_od(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "bombe",
                                     bombe_bulge_factor=1.15)
        assert spec["bombe_peak_od"] > spec["outer_long_mm"]

    def test_bombe_peak_od_proportional_to_factor(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "bombe",
                                     bombe_bulge_factor=1.20)
        expected = spec["outer_long_mm"] * 1.20
        assert abs(spec["bombe_peak_od"] - expected) < 1e-4

    def test_scallop_has_notch_positions(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "scallop",
                                     scallop_count=4)
        assert len(spec["scallop_positions"]) == 4

    def test_scallop_6_notches(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "scallop",
                                     scallop_count=6)
        assert len(spec["scallop_positions"]) == 6

    def test_half_bezel_has_tab_anchors(self):
        spec = bezel_auto_from_stone("oval", 7.7, "half_bezel")
        assert len(spec["tab_anchors"]) == 2
        angles = {t["angle_deg"] for t in spec["tab_anchors"]}
        assert 90.0 in angles
        assert 270.0 in angles

    def test_v_bezel_has_taper_angle(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "v_bezel",
                                     taper_angle_deg=8.0)
        assert abs(spec["taper_angle_deg"] - 8.0) < 1e-4

    def test_v_bezel_base_od_gt_top_od(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "v_bezel",
                                     taper_angle_deg=5.0)
        assert spec["base_outer_long"] > spec["outer_long_mm"]

    def test_illusion_outer_ge_stone_mm(self):
        spec = bezel_auto_from_stone("round_brilliant", 4.0, "illusion",
                                     illusion_factor=1.30)
        assert spec["illusion_outer_long"] >= 4.0 * 1.30 - 1e-6

    def test_straight_and_full_bezel_equivalent_structure(self):
        s1 = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        s2 = bezel_auto_from_stone("round_brilliant", 6.5, "full_bezel")
        # Both share same inner/outer geometry
        assert s1["inner_long_mm"] == pytest.approx(s2["inner_long_mm"])
        assert s1["outer_long_mm"] == pytest.approx(s2["outer_long_mm"])


# ---------------------------------------------------------------------------
# 10. Seat groove keys
# ---------------------------------------------------------------------------

class TestSeatGroove:
    def test_seat_groove_z_less_than_bezel_height(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        assert spec["seat_groove_z_mm"] < spec["bezel_height_mm"]

    def test_seat_groove_z_at_least_0_1mm(self):
        spec = bezel_auto_from_stone("single_cut", 1.0, "straight")
        assert spec["seat_groove_z_mm"] >= 0.10

    def test_seat_groove_depth_present(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        assert spec["seat_groove_depth_mm"] == pytest.approx(0.10, abs=1e-6)

    def test_seat_groove_half_angle_present(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        assert spec["seat_groove_half_angle_deg"] == pytest.approx(15.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 11. Seat cutter spec present
# ---------------------------------------------------------------------------

class TestSeatCutter:
    def test_bezel_has_seat_cutter_key(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        assert "_seat_cutter" in spec

    def test_seat_cutter_has_required_keys(self):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, "straight")
        sc = spec["_seat_cutter"]
        for key in ("op", "inner_long_mm", "inner_short_mm", "profile_shape",
                    "girdle_clearance_mm", "bearing_ledge_z"):
            assert key in sc, f"missing key: {key}"

    def test_tube_seat_cutter_present(self):
        spec = tube_setting_auto(6.5)
        assert "_seat_cutter" in spec
        sc = spec["_seat_cutter"]
        assert sc["profile_shape"] == "circle"


# ---------------------------------------------------------------------------
# 12. All BEZEL_STYLES produce a valid node
# ---------------------------------------------------------------------------

class TestAllStyles:
    @pytest.mark.parametrize("style", sorted(BEZEL_STYLES))
    def test_all_styles_produce_node(self, style):
        spec = bezel_auto_from_stone("round_brilliant", 6.5, style)
        assert "error" not in spec
        assert spec["style"] == style
        assert spec["bezel_height_mm"] > 0


# ---------------------------------------------------------------------------
# 13. LLM tool runners — BAD_ARGS + happy path
# ---------------------------------------------------------------------------

class TestLLMRunners:
    def test_bezel_auto_missing_cut_bad_args(self):
        ctx, store, file_id = make_ctx()
        result = run_sync(run_jewelry_bezel_auto_from_stone(
            {"file_id": str(file_id), "stone_mm": 6.5, "style": "straight"}, ctx
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_bezel_auto_invalid_style_bad_args(self):
        ctx, store, file_id = make_ctx()
        result = run_sync(run_jewelry_bezel_auto_from_stone(
            {"file_id": str(file_id), "cut": "round_brilliant",
             "stone_mm": 6.5, "style": "laser_etch"}, ctx
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_bezel_auto_happy_path_appends_node(self):
        ctx, store, file_id = make_ctx()
        result = run_sync(run_jewelry_bezel_auto_from_stone(
            {"file_id": str(file_id), "cut": "round_brilliant",
             "stone_mm": 6.5, "style": "straight"}, ctx
        ))
        # ok_payload returns flat data dict — no "ok" key, just the data
        assert "error" not in result
        assert "node_id" in result
        # Feature file was updated
        content = json.loads(store["content"])
        assert len(content["features"]) == 1

    def test_tube_auto_missing_stone_mm_bad_args(self):
        ctx, store, file_id = make_ctx()
        result = run_sync(run_jewelry_tube_setting_auto(
            {"file_id": str(file_id)}, ctx
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_tube_auto_negative_stone_mm_bad_args(self):
        ctx, store, file_id = make_ctx()
        result = run_sync(run_jewelry_tube_setting_auto(
            {"file_id": str(file_id), "stone_mm": -3.0}, ctx
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_tube_auto_happy_path_appends_node(self):
        ctx, store, file_id = make_ctx()
        result = run_sync(run_jewelry_tube_setting_auto(
            {"file_id": str(file_id), "stone_mm": 6.5}, ctx
        ))
        assert "error" not in result
        assert "node_id" in result
        content = json.loads(store["content"])
        assert len(content["features"]) == 1

    def test_bezel_auto_file_not_found_returns_not_found(self):
        ctx, file_id = make_ctx_not_found()
        result = run_sync(run_jewelry_bezel_auto_from_stone(
            {"file_id": str(file_id), "cut": "round_brilliant",
             "stone_mm": 6.5, "style": "straight"}, ctx
        ))
        assert result.get("code") == "NOT_FOUND"

    def test_tube_auto_file_not_found_returns_not_found(self):
        ctx, file_id = make_ctx_not_found()
        result = run_sync(run_jewelry_tube_setting_auto(
            {"file_id": str(file_id), "stone_mm": 6.5}, ctx
        ))
        assert result.get("code") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 14. ToolSpec structure
# ---------------------------------------------------------------------------

class TestToolSpecs:
    def test_bezel_auto_spec_name(self):
        assert jewelry_bezel_auto_spec.name == "jewelry_bezel_auto_from_stone"

    def test_tube_auto_spec_name(self):
        assert jewelry_tube_setting_auto_spec.name == "jewelry_tube_setting_auto"

    def test_bezel_auto_required_fields(self):
        required = jewelry_bezel_auto_spec.input_schema["required"]
        for f in ("file_id", "cut", "stone_mm", "style"):
            assert f in required

    def test_tube_auto_required_fields(self):
        required = jewelry_tube_setting_auto_spec.input_schema["required"]
        for f in ("file_id", "stone_mm"):
            assert f in required

    def test_bezel_style_enum_matches_constant(self):
        enum_vals = set(
            jewelry_bezel_auto_spec.input_schema["properties"]["style"]["enum"]
        )
        assert enum_vals == BEZEL_STYLES
