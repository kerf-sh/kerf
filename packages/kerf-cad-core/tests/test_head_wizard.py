"""
Tests for kerf_cad_core.jewelry.head_wizard

Pure-Python section (always runs — no OCCT required):

  1.  Head-library catalogue — scaled prong dimensions, styles, cuts.
  2.  prong_angles_for_cut — even spacing for round; corner placement for
      fancy cuts; tip placement for pointed cuts.
  3.  girdle_contact_point — contact points are on or near the girdle circle
      for round stones.
  4.  stone_girdle_radius — scales with stone_mm.
  5.  build_head_node — node dict shape, derived hints, prong_angles_deg,
      contact_points_mm.
  6.  build_ring_builder_node — inner_dia from ring size, weight estimate,
      min-metal warnings.
  7.  LLM tool runners — bad-arg rejection (BAD_ARGS), happy-path ok payloads,
      file-not-found handling.  Uses in-memory fake pool / ctx following the
      same pattern as test_jewelry_ring.py.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

_PI = math.pi


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from kerf_cad_core.jewelry.head_wizard import (
    HEAD_STYLES,
    STONE_CUTS,
    _FANCY_CUTS_WITH_CORNERS,
    _POINTED_CUTS,
    _ROUND_OVAL_CUTS,
    _MIN_METAL_WALL_MM,
    _MIN_PRONG_WIRE_MM,
    _METAL_DENSITY,
    _ring_size_to_id_mm,
    _us_size_to_id_mm,
    girdle_contact_point,
    head_library_entry,
    prong_angles_for_cut,
    stone_girdle_radius,
    build_head_node,
    build_ring_builder_node,
    # LLM tool specs and runners
    jewelry_head_library_get_spec,
    jewelry_place_prongs_spec,
    jewelry_build_head_spec,
    jewelry_ring_builder_spec,
    run_jewelry_head_library_get,
    run_jewelry_place_prongs,
    run_jewelry_build_head,
    run_jewelry_ring_builder,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def make_ctx(initial_content: str = ""):
    """Return (ctx, store, file_id) with an in-memory fake pool."""
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


def run_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return json.loads(loop.run_until_complete(coro))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 1. Head library catalogue
# ---------------------------------------------------------------------------

class TestHeadLibraryEntry:
    def test_four_prong_round_returns_4_prongs(self):
        e = head_library_entry("four_prong_solitaire", "round_brilliant", 6.5)
        assert e["prong_count"] == 4

    def test_six_prong_round_returns_6_prongs(self):
        e = head_library_entry("six_prong_solitaire", "round_brilliant", 6.5)
        assert e["prong_count"] == 6

    def test_basket_round_has_gallery_rail(self):
        e = head_library_entry("basket", "round_brilliant", 7.0)
        assert e["gallery_rail"] is True

    def test_full_bezel_no_prongs(self):
        e = head_library_entry("full_bezel", "round_brilliant", 6.5)
        assert e["prong_count"] == 0

    def test_tension_no_prongs(self):
        e = head_library_entry("tension", "round_brilliant", 5.0)
        assert e["prong_count"] == 0

    def test_v_prong_marquise_prong_count(self):
        e = head_library_entry("v_prong", "marquise", 8.0)
        assert e["prong_count"] == 2  # two V-tips for marquise

    def test_prong_wire_scales_with_stone_mm(self):
        small = head_library_entry("four_prong_solitaire", "round_brilliant", 4.0)
        large = head_library_entry("four_prong_solitaire", "round_brilliant", 8.0)
        assert large["prong_wire_dia"] > small["prong_wire_dia"]

    def test_bezel_height_proportional_to_stone(self):
        e = head_library_entry("full_bezel", "emerald", 7.0)
        assert abs(e["bezel_height"] - 0.4 * 7.0) < 0.01

    def test_bezel_wall_minimum_enforced(self):
        # Very small stone: bezel wall should not go below _MIN_METAL_WALL_MM.
        e = head_library_entry("full_bezel", "round_brilliant", 2.0)
        assert e["bezel_wall"] >= 0.3

    def test_invalid_head_style_raises(self):
        with pytest.raises(ValueError, match="head_style"):
            head_library_entry("trapezoid_prong", "round_brilliant", 6.5)

    def test_invalid_cut_raises(self):
        with pytest.raises(ValueError, match="cut"):
            head_library_entry("basket", "dragon_cut", 6.5)

    def test_invalid_stone_mm_raises(self):
        with pytest.raises(ValueError):
            head_library_entry("basket", "round_brilliant", 0)


# ---------------------------------------------------------------------------
# 2. Prong angular placement
# ---------------------------------------------------------------------------

class TestProngAnglesForCut:
    def test_round_4_prong_even_90deg_spacing(self):
        angles = prong_angles_for_cut("round_brilliant", 4, 0.0)
        assert len(angles) == 4
        # Even spacing: differences should all be 90°.
        diffs = [
            abs((angles[(i + 1) % 4] - angles[i] + 360) % 360)
            for i in range(4)
        ]
        for d in diffs:
            assert abs(d - 90.0) < 1e-6, f"Expected 90° spacing, got {d}"

    def test_round_6_prong_even_60deg_spacing(self):
        angles = prong_angles_for_cut("round_brilliant", 6, 0.0)
        assert len(angles) == 6
        sorted_a = sorted(angles)
        for i in range(6):
            diff = (sorted_a[(i + 1) % 6] - sorted_a[i] + 360) % 360
            assert abs(diff - 60.0) < 1e-6, f"Expected 60° spacing, got {diff}"

    def test_round_prongs_on_girdle_circle(self):
        stone_mm = 6.5
        prong_count = 4
        angles = prong_angles_for_cut("round_brilliant", prong_count)
        r = stone_mm / 2.0
        for ang in angles:
            x, y = girdle_contact_point("round_brilliant", stone_mm, ang)
            dist = math.sqrt(x ** 2 + y ** 2)
            assert abs(dist - r) < 1e-4, f"Contact point {dist:.4f} not on girdle r={r}"

    def test_princess_4_prong_corner_placement(self):
        # Princess corners are at 45°, 135°, 225°, 315° (square, rotated 45° from axis)
        angles = prong_angles_for_cut("princess", 4, 0.0)
        assert len(angles) == 4
        expected = sorted([45.0, 135.0, 225.0, 315.0])
        for got, exp in zip(sorted(angles), expected):
            assert abs(got - exp) < 1e-6, f"Expected corner at {exp}°, got {got}°"

    def test_emerald_4_prong_corner_placement(self):
        angles = prong_angles_for_cut("emerald", 4, 0.0)
        assert len(angles) == 4
        # All at 45° offsets from the cardinal axes.
        for a in angles:
            a_mod = a % 90.0
            assert abs(a_mod - 45.0) < 1e-6, f"Emerald corner expected at 45° mod 90°, got {a_mod}°"

    def test_marquise_2_prong_at_tips(self):
        angles = prong_angles_for_cut("marquise", 2, 0.0)
        assert len(angles) == 2
        # Should be at 0° and 180° (the two pointed tips).
        assert abs(min(angles) - 0.0) < 1e-6
        assert abs(max(angles) - 180.0) < 1e-6

    def test_trillion_3_prong_at_tips(self):
        angles = prong_angles_for_cut("trillion", 3, 0.0)
        assert len(angles) == 3
        # Three tips at 120° intervals.
        sorted_a = sorted(angles)
        for i in range(3):
            diff = (sorted_a[(i + 1) % 3] - sorted_a[i] + 360) % 360
            assert abs(diff - 120.0) < 1e-6, f"Expected 120° spacing, got {diff}"

    def test_zero_prong_count_returns_empty(self):
        assert prong_angles_for_cut("round_brilliant", 0) == []

    def test_start_angle_offset_round(self):
        angles_0 = prong_angles_for_cut("round_brilliant", 4, 0.0)
        angles_45 = prong_angles_for_cut("round_brilliant", 4, 45.0)
        for a0, a45 in zip(sorted(angles_0), sorted(angles_45)):
            assert abs((a45 - a0 + 360) % 360 - 45.0) < 1e-6

    def test_oval_6_prong_even_spacing(self):
        angles = prong_angles_for_cut("oval", 6)
        assert len(angles) == 6
        sorted_a = sorted(angles)
        for i in range(6):
            diff = (sorted_a[(i + 1) % 6] - sorted_a[i] + 360) % 360
            assert abs(diff - 60.0) < 1e-6


# ---------------------------------------------------------------------------
# 3. Girdle contact points
# ---------------------------------------------------------------------------

class TestGirdleContactPoint:
    def test_round_contact_on_circle(self):
        r = 3.25  # 6.5 mm stone
        for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
            x, y = girdle_contact_point("round_brilliant", 6.5, angle)
            dist = math.sqrt(x ** 2 + y ** 2)
            assert abs(dist - r) < 1e-4, f"angle {angle}°: dist={dist:.4f} expected {r}"

    def test_oval_contact_at_east_west(self):
        # At 90° (east), x should be positive and roughly r.
        x, y = girdle_contact_point("oval", 8.0, 90.0)
        assert x > 0
        assert abs(y) < 0.01  # on the east axis

    def test_princess_contact_at_corner(self):
        # At 45° from north, princess corner should be at the square corner.
        x, y = girdle_contact_point("princess", 6.0, 45.0)
        half = 3.0  # stone_mm / 2
        # Both |x| and |y| should equal half (on the corner of the square).
        assert abs(abs(x) - half) < 1e-3 or abs(abs(y) - half) < 1e-3

    def test_marquise_contact_at_tip(self):
        # At 0° (north/top), marquise tip — y should be positive (pointing up).
        x, y = girdle_contact_point("marquise", 10.0, 0.0)
        assert y > 0
        assert abs(x) < 0.01

    def test_trillion_contact_nonzero(self):
        x, y = girdle_contact_point("trillion", 7.0, 30.0)
        assert math.sqrt(x ** 2 + y ** 2) > 0.1


# ---------------------------------------------------------------------------
# 4. stone_girdle_radius
# ---------------------------------------------------------------------------

class TestStoneGirdleRadius:
    def test_round_radius_is_half_diameter(self):
        r = stone_girdle_radius("round_brilliant", 6.5)
        assert abs(r - 3.25) < 1e-9

    def test_fancy_cut_radius_larger_than_round(self):
        # Fancy cuts: radius = half_diagonal > simple half.
        r_princess = stone_girdle_radius("princess", 6.5)
        r_round = stone_girdle_radius("round_brilliant", 6.5)
        assert r_princess > r_round

    def test_radius_scales_with_stone_mm(self):
        r5 = stone_girdle_radius("round_brilliant", 5.0)
        r10 = stone_girdle_radius("round_brilliant", 10.0)
        assert abs(r10 / r5 - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# 5. build_head_node
# ---------------------------------------------------------------------------

class TestBuildHeadNode:
    def test_node_op_field(self):
        node = build_head_node(
            node_id="hw-1",
            head_style="four_prong_solitaire",
            cut="round_brilliant",
            stone_mm=6.5,
            prong_count=4,
            prong_wire_dia=0.9,
            claw_length=2.0,
            claw_tip_radius=0.45,
            seat_angle_deg=15.0,
            gallery_rail=True,
            bezel_wall=0.35,
            bezel_height=2.6,
            start_angle_deg=0.0,
        )
        assert node["op"] == "jewelry_head_wizard"
        assert node["id"] == "hw-1"

    def test_prong_angles_deg_count_matches(self):
        node = build_head_node(
            node_id="hw-2",
            head_style="six_prong_solitaire",
            cut="round_brilliant",
            stone_mm=6.5,
            prong_count=6,
            prong_wire_dia=0.8,
            claw_length=1.8,
            claw_tip_radius=0.40,
            seat_angle_deg=15.0,
            gallery_rail=True,
            bezel_wall=0.33,
            bezel_height=2.6,
            start_angle_deg=0.0,
        )
        assert len(node["prong_angles_deg"]) == 6

    def test_contact_points_count_matches_prong_count(self):
        node = build_head_node(
            node_id="hw-3",
            head_style="basket",
            cut="princess",
            stone_mm=5.5,
            prong_count=4,
            prong_wire_dia=0.9,
            claw_length=2.0,
            claw_tip_radius=0.45,
            seat_angle_deg=15.0,
            gallery_rail=True,
            bezel_wall=0.3,
            bezel_height=2.2,
            start_angle_deg=0.0,
        )
        assert len(node["contact_points_mm"]) == 4

    def test_head_outer_dia_derived_hint(self):
        stone_mm = 6.5
        wire_dia = 0.9
        node = build_head_node(
            node_id="hw-4",
            head_style="four_prong_solitaire",
            cut="round_brilliant",
            stone_mm=stone_mm,
            prong_count=4,
            prong_wire_dia=wire_dia,
            claw_length=2.0,
            claw_tip_radius=0.45,
            seat_angle_deg=15.0,
            gallery_rail=True,
            bezel_wall=0.35,
            bezel_height=2.6,
            start_angle_deg=0.0,
        )
        expected_outer = stone_mm + 2 * wire_dia
        assert abs(node["_head_outer_dia"] - expected_outer) < 1e-3

    def test_full_bezel_no_prong_angles(self):
        node = build_head_node(
            node_id="hw-5",
            head_style="full_bezel",
            cut="oval",
            stone_mm=9.0,
            prong_count=0,
            prong_wire_dia=0.0,
            claw_length=0.0,
            claw_tip_radius=0.0,
            seat_angle_deg=15.0,
            gallery_rail=False,
            bezel_wall=0.45,
            bezel_height=3.6,
            start_angle_deg=0.0,
        )
        assert len(node["prong_angles_deg"]) == 0
        assert len(node["contact_points_mm"]) == 0


# ---------------------------------------------------------------------------
# 6. build_ring_builder_node
# ---------------------------------------------------------------------------

class TestBuildRingBuilderNode:
    def test_inner_dia_us7(self):
        node = build_ring_builder_node(
            node_id="rb-1",
            head_node_id="hw-1",
            shank_profile="comfort_fit",
            band_width=3.0,
            band_thickness=1.5,
            ring_size=7.0,
            size_system="us",
            metal="18k_yellow",
            seat_height_mm=0.0,
        )
        # US 7: 11.63 + 0.8128 * 7 = 17.3196 mm
        expected_id = 11.63 + 0.8128 * 7.0
        assert abs(node["_inner_dia_mm"] - expected_id) < 0.001

    def test_inner_dia_us0(self):
        node = build_ring_builder_node(
            node_id="rb-2",
            head_node_id="hw-1",
            shank_profile="flat",
            band_width=2.5,
            band_thickness=1.2,
            ring_size=0.0,
            size_system="us",
            metal="platinum",
            seat_height_mm=0.0,
        )
        assert abs(node["_inner_dia_mm"] - 11.63) < 1e-9

    def test_weight_positive(self):
        node = build_ring_builder_node(
            node_id="rb-3",
            head_node_id="hw-1",
            shank_profile="comfort_fit",
            band_width=4.0,
            band_thickness=1.8,
            ring_size=7.0,
            size_system="us",
            metal="18k_yellow",
            seat_height_mm=0.0,
        )
        assert node["_weight_g"] > 0.0

    def test_thin_band_triggers_warning(self):
        node = build_ring_builder_node(
            node_id="rb-4",
            head_node_id="hw-1",
            shank_profile="knife_edge",
            band_width=2.0,
            band_thickness=0.1,  # below minimum
            ring_size=6.0,
            size_system="us",
            metal="14k_white",
            seat_height_mm=0.0,
        )
        assert len(node["_warnings"]) > 0
        assert "band_thickness" in node["_warnings"][0]

    def test_normal_thickness_no_warning(self):
        node = build_ring_builder_node(
            node_id="rb-5",
            head_node_id="hw-1",
            shank_profile="d_shape",
            band_width=3.5,
            band_thickness=1.5,
            ring_size=5.0,
            size_system="us",
            metal="platinum",
            seat_height_mm=0.5,
        )
        assert len(node["_warnings"]) == 0

    def test_inner_dia_ring_size_lookup_us_various(self):
        for size, expected_id in [(5, 11.63 + 0.8128 * 5), (10, 11.63 + 0.8128 * 10)]:
            node = build_ring_builder_node(
                node_id="rb-x",
                head_node_id="hw-x",
                shank_profile="flat",
                band_width=3.0,
                band_thickness=1.2,
                ring_size=size,
                size_system="us",
                metal="18k_yellow",
                seat_height_mm=0.0,
            )
            assert abs(node["_inner_dia_mm"] - expected_id) < 0.001, \
                f"US {size}: expected {expected_id:.4f}, got {node['_inner_dia_mm']:.4f}"


# ---------------------------------------------------------------------------
# 7a. LLM tool runner: run_jewelry_head_library_get
# ---------------------------------------------------------------------------

class TestRunJewelryHeadLibraryGet:
    def _ctx(self):
        ctx, _, _ = make_ctx()
        return ctx

    def test_happy_path_returns_ok(self):
        result = run_sync(run_jewelry_head_library_get(
            self._ctx(),
            json.dumps({"head_style": "four_prong_solitaire", "cut": "round_brilliant", "stone_mm": 6.5}).encode(),
        ))
        assert result.get("error") is None, result
        assert result["prong_count"] == 4

    def test_bad_head_style_returns_bad_args(self):
        result = run_sync(run_jewelry_head_library_get(
            self._ctx(),
            json.dumps({"head_style": "nonsense", "cut": "round_brilliant", "stone_mm": 6.5}).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_bad_cut_returns_bad_args(self):
        result = run_sync(run_jewelry_head_library_get(
            self._ctx(),
            json.dumps({"head_style": "basket", "cut": "unicorn_cut", "stone_mm": 5.0}).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_negative_stone_mm_returns_bad_args(self):
        result = run_sync(run_jewelry_head_library_get(
            self._ctx(),
            json.dumps({"head_style": "basket", "cut": "round_brilliant", "stone_mm": -1.0}).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_full_bezel_no_prongs(self):
        result = run_sync(run_jewelry_head_library_get(
            self._ctx(),
            json.dumps({"head_style": "full_bezel", "cut": "emerald", "stone_mm": 8.0}).encode(),
        ))
        assert result.get("error") is None, result
        assert result["prong_count"] == 0


# ---------------------------------------------------------------------------
# 7b. LLM tool runner: run_jewelry_place_prongs
# ---------------------------------------------------------------------------

class TestRunJewelryPlaceProngs:
    def _ctx(self):
        ctx, _, _ = make_ctx()
        return ctx

    def test_round_4_prong_even(self):
        result = run_sync(run_jewelry_place_prongs(
            self._ctx(),
            json.dumps({"cut": "round_brilliant", "stone_mm": 6.5, "prong_count": 4}).encode(),
        ))
        assert result.get("error") is None, result
        placements = result["placements"]
        assert len(placements) == 4
        angles = [p["angle_deg"] for p in placements]
        angles_sorted = sorted(angles)
        for i in range(4):
            diff = (angles_sorted[(i + 1) % 4] - angles_sorted[i] + 360) % 360
            assert abs(diff - 90.0) < 1e-4

    def test_princess_4_corner_claws(self):
        result = run_sync(run_jewelry_place_prongs(
            self._ctx(),
            json.dumps({"cut": "princess", "stone_mm": 5.5, "prong_count": 4}).encode(),
        ))
        assert result.get("error") is None, result
        angles = sorted(p["angle_deg"] for p in result["placements"])
        expected = sorted([45.0, 135.0, 225.0, 315.0])
        for got, exp in zip(angles, expected):
            assert abs(got - exp) < 1e-4

    def test_contact_points_on_round_girdle(self):
        result = run_sync(run_jewelry_place_prongs(
            self._ctx(),
            json.dumps({"cut": "round_brilliant", "stone_mm": 6.5, "prong_count": 6}).encode(),
        ))
        assert result.get("error") is None, result
        r = 3.25
        for p in result["placements"]:
            dist = math.sqrt(p["contact_x_mm"] ** 2 + p["contact_y_mm"] ** 2)
            assert abs(dist - r) < 1e-3, f"Contact point dist={dist:.4f} not on girdle r={r}"

    def test_bad_cut_bad_args(self):
        result = run_sync(run_jewelry_place_prongs(
            self._ctx(),
            json.dumps({"cut": "invalid_cut", "stone_mm": 6.5, "prong_count": 4}).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_prong_count_too_large(self):
        result = run_sync(run_jewelry_place_prongs(
            self._ctx(),
            json.dumps({"cut": "round_brilliant", "stone_mm": 6.5, "prong_count": 20}).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# 7c. LLM tool runner: run_jewelry_build_head
# ---------------------------------------------------------------------------

class TestRunJewelryBuildHead:
    def _setup(self):
        ctx, store, file_id = make_ctx()
        return ctx, store, file_id

    def test_happy_path_appends_node(self):
        ctx, store, file_id = self._setup()
        result = run_sync(run_jewelry_build_head(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_style": "four_prong_solitaire",
                "cut": "round_brilliant",
                "stone_mm": 6.5,
            }).encode(),
        ))
        assert result.get("error") is None, result
        assert result["op"] == "jewelry_head_wizard"
        # Node should have been appended to the store.
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1

    def test_prong_angles_in_result(self):
        ctx, _, file_id = self._setup()
        result = run_sync(run_jewelry_build_head(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_style": "six_prong_solitaire",
                "cut": "round_brilliant",
                "stone_mm": 6.5,
            }).encode(),
        ))
        assert result.get("error") is None, result
        assert len(result["prong_angles_deg"]) == 6

    def test_missing_file_id_bad_args(self):
        ctx, _, _ = self._setup()
        result = run_sync(run_jewelry_build_head(
            ctx,
            json.dumps({"head_style": "basket", "cut": "round_brilliant", "stone_mm": 6.5}).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_invalid_file_id_bad_args(self):
        ctx, _, _ = self._setup()
        result = run_sync(run_jewelry_build_head(
            ctx,
            json.dumps({
                "file_id": "not-a-uuid",
                "head_style": "basket",
                "cut": "round_brilliant",
                "stone_mm": 6.5,
            }).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_prong_wire_below_minimum_bad_args(self):
        ctx, _, file_id = self._setup()
        result = run_sync(run_jewelry_build_head(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_style": "four_prong_solitaire",
                "cut": "round_brilliant",
                "stone_mm": 6.5,
                "prong_wire_dia": 0.1,  # below _MIN_PRONG_WIRE_MM
            }).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_bad_head_style_bad_args(self):
        ctx, _, file_id = self._setup()
        result = run_sync(run_jewelry_build_head(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_style": "banana_prong",
                "cut": "round_brilliant",
                "stone_mm": 6.5,
            }).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# 7d. LLM tool runner: run_jewelry_ring_builder
# ---------------------------------------------------------------------------

class TestRunJewelryRingBuilder:
    def _setup(self):
        ctx, store, file_id = make_ctx()
        return ctx, store, file_id

    def test_happy_path_us7(self):
        ctx, store, file_id = self._setup()
        result = run_sync(run_jewelry_ring_builder(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_node_id": "hw-1",
                "band_width": 3.0,
                "band_thickness": 1.5,
                "ring_size": 7.0,
                "size_system": "us",
            }).encode(),
        ))
        assert result.get("error") is None, result
        assert result["op"] == "jewelry_ring_builder"
        expected_id = 11.63 + 0.8128 * 7.0
        assert abs(result["inner_dia_mm"] - expected_id) < 0.001

    def test_weight_returned_positive(self):
        ctx, _, file_id = self._setup()
        result = run_sync(run_jewelry_ring_builder(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_node_id": "hw-1",
                "band_width": 4.0,
                "band_thickness": 1.8,
                "ring_size": 8.0,
                "size_system": "us",
                "metal": "platinum",
            }).encode(),
        ))
        assert result.get("error") is None, result
        assert result["weight_g"] > 0.0

    def test_missing_head_node_id_bad_args(self):
        ctx, _, file_id = self._setup()
        result = run_sync(run_jewelry_ring_builder(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "band_width": 3.0,
                "band_thickness": 1.5,
                "ring_size": 7.0,
            }).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_invalid_size_system_bad_args(self):
        ctx, _, file_id = self._setup()
        result = run_sync(run_jewelry_ring_builder(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_node_id": "hw-1",
                "band_width": 3.0,
                "band_thickness": 1.5,
                "ring_size": 7.0,
                "size_system": "martian",
            }).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_invalid_metal_bad_args(self):
        ctx, _, file_id = self._setup()
        result = run_sync(run_jewelry_ring_builder(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_node_id": "hw-1",
                "band_width": 3.0,
                "band_thickness": 1.5,
                "ring_size": 7.0,
                "metal": "unobtanium",
            }).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_negative_band_width_bad_args(self):
        ctx, _, file_id = self._setup()
        result = run_sync(run_jewelry_ring_builder(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_node_id": "hw-1",
                "band_width": -2.0,
                "band_thickness": 1.5,
                "ring_size": 7.0,
            }).encode(),
        ))
        assert result.get("code") == "BAD_ARGS"

    def test_node_appended_to_store(self):
        ctx, store, file_id = self._setup()
        run_sync(run_jewelry_ring_builder(
            ctx,
            json.dumps({
                "file_id": str(file_id),
                "head_node_id": "hw-1",
                "band_width": 3.0,
                "band_thickness": 1.5,
                "ring_size": 7.0,
            }).encode(),
        ))
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1
        assert doc["features"][0]["op"] == "jewelry_ring_builder"
