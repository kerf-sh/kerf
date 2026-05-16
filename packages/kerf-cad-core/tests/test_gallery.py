"""
Tests for kerf_cad_core.jewelry.gallery

Coverage (≥ 30 hermetic pure-Python tests):
  - basket_geometry: prong-count → rail/strut count topology
  - basket_geometry: height/diameter exact values
  - basket_geometry: rail position counts match rail_count
  - basket_geometry: prong angular spacing (360 / N degrees)
  - basket_geometry: taper changes base radius
  - basket_geometry: splay_angle_deg increases prong_length_mm
  - basket_geometry: scallop_count defaults and overrides
  - basket_geometry: diagonal struts topology
  - basket_geometry: invalid prong count, taper out-of-range, unknown cutout style
  - under_bezel_gallery_geometry: inner/outer radii, circumference
  - under_bezel_gallery_geometry: invalid border style raises
  - cathedral_shoulder_geometry: arch_rise default, arch_length positive
  - cathedral_shoulder_geometry: shoulder_pair_count always 2
  - cathedral_shoulder_geometry: arch_rib_count > 2 raises
  - trellis_shoulder_geometry: diagonal_length and total wire
  - trellis_shoulder_geometry: bay_count == prong_count
  - trellis_shoulder_geometry: cross_count > 4 raises
  - peg_head_adapter_geometry: peg_inner < peg_outer
  - basket_metal_volume_mm3: Σ wire segment volumes within tolerance
  - basket_metal_volume_mm3: more rails → larger volume
  - basket_metal_volume_mm3: more prongs → larger volume
  - basket_surface_area_mm2: positive and proportional to prong count
  - metal_weight_grams: basic formula (gold 18k density check)
  - metal_weight_grams: negative volume raises
  - min_wire_diameter_check: returns None when wire is adequate
  - min_wire_diameter_check: returns warning string when wire too thin
  - min_wire_diameter_check: threshold boundary (0.75 ct)
  - LLM tool spec names + required fields
  - LLM tool run_jewelry_build_basket_gallery: success path, node in feature
  - LLM tool run_jewelry_build_basket_gallery: BAD_ARGS paths
  - LLM tool run_jewelry_estimate_gallery_metal: volume/weight/warning
  - LLM tool run_jewelry_build_under_bezel_gallery: success path
  - LLM tool run_jewelry_build_cathedral_shoulders: success path
  - LLM tool run_jewelry_build_trellis_shoulders: success path
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.jewelry.gallery import (
    _MIN_WIRE_TABLE,
    _VALID_BORDER_STYLES,
    _VALID_CUTOUT_STYLES,
    _VALID_SHOULDER_STYLES,
    basket_geometry,
    basket_metal_volume_mm3,
    basket_surface_area_mm2,
    cathedral_shoulder_geometry,
    metal_weight_grams,
    min_wire_diameter_check,
    peg_head_adapter_geometry,
    trellis_shoulder_geometry,
    under_bezel_gallery_geometry,
    # Tool specs
    jewelry_build_basket_gallery_spec,
    jewelry_build_cathedral_shoulders_spec,
    jewelry_build_trellis_shoulders_spec,
    jewelry_build_under_bezel_gallery_spec,
    jewelry_estimate_gallery_metal_spec,
    # Tool runners
    run_jewelry_build_basket_gallery,
    run_jewelry_build_cathedral_shoulders,
    run_jewelry_build_trellis_shoulders,
    run_jewelry_build_under_bezel_gallery,
    run_jewelry_estimate_gallery_metal,
)

_PI = math.pi


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(initial_content: str = "", kind: str = "feature"):
    store = {
        "content": initial_content or json.dumps({"version": 1, "features": []}),
        "kind": kind,
    }
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            if store["kind"] == "NOT_FOUND":
                return None
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            if args:
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


def build_basket(ctx, file_id, **kwargs):
    args = {"file_id": str(file_id), **kwargs}
    return run_sync(run_jewelry_build_basket_gallery(ctx, json.dumps(args).encode()))


def build_under_bezel(ctx, file_id, **kwargs):
    args = {"file_id": str(file_id), **kwargs}
    return run_sync(run_jewelry_build_under_bezel_gallery(ctx, json.dumps(args).encode()))


def build_cathedral(ctx, file_id, **kwargs):
    args = {"file_id": str(file_id), **kwargs}
    return run_sync(run_jewelry_build_cathedral_shoulders(ctx, json.dumps(args).encode()))


def build_trellis(ctx, file_id, **kwargs):
    args = {"file_id": str(file_id), **kwargs}
    return run_sync(run_jewelry_build_trellis_shoulders(ctx, json.dumps(args).encode()))


def estimate_metal(**kwargs):
    ctx, _, _ = make_ctx()
    return run_sync(run_jewelry_estimate_gallery_metal(ctx, json.dumps(kwargs).encode()))


# ---------------------------------------------------------------------------
# basket_geometry: topology
# ---------------------------------------------------------------------------

class TestBasketTopology:
    @pytest.mark.parametrize("n", [3, 4, 5, 6, 8])
    def test_prong_count_matches_positions(self, n):
        b = basket_geometry(n, stone_diameter_mm=6.5, wire_diameter_mm=1.0, basket_height_mm=4.0)
        assert len(b["prong_positions_deg"]) == n

    @pytest.mark.parametrize("n", [3, 4, 6])
    def test_prong_angular_spacing(self, n):
        b = basket_geometry(n, stone_diameter_mm=6.5, wire_diameter_mm=1.0, basket_height_mm=4.0)
        expected_step = 360.0 / n
        positions = b["prong_positions_deg"]
        for i in range(1, len(positions)):
            assert positions[i] == pytest.approx(i * expected_step, abs=1e-3)

    @pytest.mark.parametrize("rc", [1, 2, 3, 4])
    def test_rail_count_matches_positions(self, rc):
        b = basket_geometry(4, stone_diameter_mm=6.5, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, rail_count=rc)
        assert b["rail_count"] == rc
        assert len(b["rail_positions_mm"]) == rc

    def test_diagonal_struts_disabled_by_default(self):
        b = basket_geometry(4, stone_diameter_mm=6.5, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)
        assert b["strut_count_per_bay"] == 0
        assert b["diagonal_struts"] is False

    def test_diagonal_struts_enabled(self):
        b = basket_geometry(4, stone_diameter_mm=6.5, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, diagonal_struts=True)
        assert b["diagonal_struts"] is True
        assert b["strut_count_per_bay"] >= 1

    def test_strut_count_explicit(self):
        b = basket_geometry(6, stone_diameter_mm=6.5, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, diagonal_struts=True, strut_count=2)
        assert b["strut_count_per_bay"] == 2

    def test_scallop_count_default(self):
        # Default scallop_count = prong_count // 2
        b = basket_geometry(6, stone_diameter_mm=6.5, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)
        assert b["scallop_count_per_bay"] == 3

    def test_scallop_count_override(self):
        b = basket_geometry(4, stone_diameter_mm=6.5, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, scallop_count=5)
        assert b["scallop_count_per_bay"] == 5

    def test_op_field(self):
        b = basket_geometry(4, stone_diameter_mm=6.5, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)
        assert b["op"] == "jewelry_gallery_basket"


# ---------------------------------------------------------------------------
# basket_geometry: exact geometry
# ---------------------------------------------------------------------------

class TestBasketGeometry:
    def test_head_outer_radius(self):
        # head_outer_radius = stone_diameter/2 + wire_diameter
        b = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)
        assert b["head_outer_radius_mm"] == pytest.approx(4.0, abs=1e-4)

    def test_base_radius_no_taper(self):
        b = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, taper_ratio=0.0)
        assert b["base_outer_radius_mm"] == pytest.approx(b["head_outer_radius_mm"], abs=1e-4)

    def test_base_radius_with_taper(self):
        b = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, taper_ratio=0.5)
        # base = head * (1 - 0.5 * 0.5) = head * 0.75
        head = b["head_outer_radius_mm"]
        expected_base = head * 0.75
        assert b["base_outer_radius_mm"] == pytest.approx(expected_base, abs=1e-4)

    def test_prong_length_no_splay(self):
        b = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, splay_angle_deg=0.0)
        # With 0 splay, prong_length == basket_height (cos(0) == 1)
        assert b["prong_length_mm"] == pytest.approx(4.0, abs=1e-4)

    def test_prong_length_increases_with_splay(self):
        b0 = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                             basket_height_mm=4.0, splay_angle_deg=0.0)
        b5 = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                             basket_height_mm=4.0, splay_angle_deg=10.0)
        assert b5["prong_length_mm"] > b0["prong_length_mm"]

    def test_single_rail_at_midpoint(self):
        b = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, rail_count=1)
        # Single rail at 50% of basket height
        assert b["rail_positions_mm"][0] == pytest.approx(2.0, abs=1e-4)

    def test_total_rail_length_positive(self):
        b = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)
        assert b["total_rail_length_mm"] > 0

    def test_stone_diameter_passthrough(self):
        b = basket_geometry(4, stone_diameter_mm=7.25, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)
        assert b["stone_diameter_mm"] == pytest.approx(7.25, abs=1e-4)


# ---------------------------------------------------------------------------
# basket_geometry: validation
# ---------------------------------------------------------------------------

class TestBasketValidation:
    def test_prong_count_too_low_raises(self):
        with pytest.raises(ValueError, match="prong_count"):
            basket_geometry(2, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)

    def test_prong_count_too_high_raises(self):
        with pytest.raises(ValueError, match="prong_count"):
            basket_geometry(13, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)

    def test_taper_ratio_ge_one_raises(self):
        with pytest.raises(ValueError, match="taper_ratio"):
            basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, taper_ratio=1.0)

    def test_unknown_cutout_style_raises(self):
        with pytest.raises(ValueError, match="cutout_style"):
            basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, cutout_style="diamond")

    def test_rail_count_too_high_raises(self):
        with pytest.raises(ValueError, match="rail_count"):
            basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0, rail_count=7)


# ---------------------------------------------------------------------------
# under_bezel_gallery_geometry
# ---------------------------------------------------------------------------

class TestUnderBezelGallery:
    def test_inner_outer_radii(self):
        g = under_bezel_gallery_geometry(
            stone_diameter_mm=6.0,
            wall_thickness_mm=1.0,
            gallery_height_mm=2.0,
        )
        assert g["inner_radius_mm"] == pytest.approx(3.0, abs=1e-4)
        assert g["outer_radius_mm"] == pytest.approx(4.0, abs=1e-4)

    def test_circumference(self):
        g = under_bezel_gallery_geometry(
            stone_diameter_mm=6.0,
            wall_thickness_mm=1.0,
            gallery_height_mm=2.0,
        )
        expected_circ = 2 * _PI * 4.0
        assert g["circumference_mm"] == pytest.approx(expected_circ, abs=1e-3)

    def test_invalid_border_style_raises(self):
        with pytest.raises(ValueError, match="border_style"):
            under_bezel_gallery_geometry(
                stone_diameter_mm=6.0,
                wall_thickness_mm=1.0,
                gallery_height_mm=2.0,
                border_style="diamonds",
            )

    def test_op_field(self):
        g = under_bezel_gallery_geometry(
            stone_diameter_mm=6.0,
            wall_thickness_mm=1.0,
            gallery_height_mm=2.0,
        )
        assert g["op"] == "jewelry_gallery_under_bezel"

    def test_scallop_count_passthrough(self):
        g = under_bezel_gallery_geometry(
            stone_diameter_mm=6.0,
            wall_thickness_mm=1.0,
            gallery_height_mm=2.0,
            scallop_count=16,
        )
        assert g["scallop_count"] == 16


# ---------------------------------------------------------------------------
# cathedral_shoulder_geometry
# ---------------------------------------------------------------------------

class TestCathedralShoulders:
    def test_shoulder_pair_count_always_two(self):
        c = cathedral_shoulder_geometry(
            prong_count=4,
            stone_diameter_mm=6.0,
            wire_diameter_mm=1.0,
            basket_height_mm=4.0,
            shank_width_mm=3.0,
        )
        assert c["shoulder_pair_count"] == 2

    def test_arch_rise_default(self):
        c = cathedral_shoulder_geometry(
            prong_count=4,
            stone_diameter_mm=6.0,
            wire_diameter_mm=1.0,
            basket_height_mm=4.0,
            shank_width_mm=3.0,
        )
        assert c["arch_rise_mm"] == pytest.approx(4.0 * 0.6, abs=1e-4)

    def test_arch_rise_explicit(self):
        c = cathedral_shoulder_geometry(
            prong_count=4,
            stone_diameter_mm=6.0,
            wire_diameter_mm=1.0,
            basket_height_mm=4.0,
            shank_width_mm=3.0,
            arch_rise_mm=2.5,
        )
        assert c["arch_rise_mm"] == pytest.approx(2.5, abs=1e-4)

    def test_arch_length_positive(self):
        c = cathedral_shoulder_geometry(
            prong_count=4,
            stone_diameter_mm=6.0,
            wire_diameter_mm=1.0,
            basket_height_mm=4.0,
            shank_width_mm=3.0,
        )
        assert c["arch_length_mm"] > 0

    def test_arch_rib_count_too_large_raises(self):
        with pytest.raises(ValueError, match="arch_rib_count"):
            cathedral_shoulder_geometry(
                prong_count=4,
                stone_diameter_mm=6.0,
                wire_diameter_mm=1.0,
                basket_height_mm=4.0,
                shank_width_mm=3.0,
                arch_rib_count=3,
            )

    def test_op_field(self):
        c = cathedral_shoulder_geometry(
            prong_count=4,
            stone_diameter_mm=6.0,
            wire_diameter_mm=1.0,
            basket_height_mm=4.0,
            shank_width_mm=3.0,
        )
        assert c["op"] == "jewelry_gallery_cathedral"


# ---------------------------------------------------------------------------
# trellis_shoulder_geometry
# ---------------------------------------------------------------------------

class TestTrellisShoulders:
    @pytest.mark.parametrize("n", [3, 4, 6])
    def test_bay_count_equals_prong_count(self, n):
        t = trellis_shoulder_geometry(
            prong_count=n,
            stone_diameter_mm=6.0,
            wire_diameter_mm=1.0,
            basket_height_mm=4.0,
        )
        assert t["bay_count"] == n

    def test_diagonal_length_positive(self):
        t = trellis_shoulder_geometry(
            prong_count=4,
            stone_diameter_mm=6.0,
            wire_diameter_mm=1.0,
            basket_height_mm=4.0,
        )
        assert t["diagonal_length_mm"] > 0

    def test_total_trellis_wire_proportional_to_prong_count(self):
        t4 = trellis_shoulder_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0, basket_height_mm=4.0)
        t6 = trellis_shoulder_geometry(6, stone_diameter_mm=6.0, wire_diameter_mm=1.0, basket_height_mm=4.0)
        # More prongs → more total wire (bays scale with prong_count)
        assert t6["total_trellis_wire_mm"] > t4["total_trellis_wire_mm"]

    def test_cross_count_too_large_raises(self):
        with pytest.raises(ValueError, match="cross_count"):
            trellis_shoulder_geometry(
                prong_count=4,
                stone_diameter_mm=6.0,
                wire_diameter_mm=1.0,
                basket_height_mm=4.0,
                cross_count=5,
            )

    def test_op_field(self):
        t = trellis_shoulder_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                                      basket_height_mm=4.0)
        assert t["op"] == "jewelry_gallery_trellis"


# ---------------------------------------------------------------------------
# peg_head_adapter_geometry
# ---------------------------------------------------------------------------

class TestPegHeadAdapter:
    def test_peg_inner_lt_outer(self):
        p = peg_head_adapter_geometry(
            stone_diameter_mm=6.0,
            wire_diameter_mm=0.8,
            adapter_height_mm=2.0,
            shank_bore_diameter_mm=4.0,
        )
        assert p["peg_inner_diameter_mm"] < p["peg_outer_diameter_mm"]

    def test_peg_outer_matches_shank_bore(self):
        p = peg_head_adapter_geometry(
            stone_diameter_mm=6.0,
            wire_diameter_mm=0.8,
            adapter_height_mm=2.0,
            shank_bore_diameter_mm=3.5,
        )
        assert p["peg_outer_diameter_mm"] == pytest.approx(3.5, abs=1e-4)


# ---------------------------------------------------------------------------
# basket_metal_volume_mm3
# ---------------------------------------------------------------------------

class TestMetalVolume:
    def test_volume_positive(self):
        b = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)
        vol = basket_metal_volume_mm3(b)
        assert vol > 0

    def test_more_rails_increases_volume(self):
        b1 = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                             basket_height_mm=4.0, rail_count=1)
        b3 = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                             basket_height_mm=4.0, rail_count=3)
        assert basket_metal_volume_mm3(b3) > basket_metal_volume_mm3(b1)

    def test_more_prongs_increases_volume(self):
        b4 = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                             basket_height_mm=4.0)
        b6 = basket_geometry(6, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                             basket_height_mm=4.0)
        assert basket_metal_volume_mm3(b6) > basket_metal_volume_mm3(b4)

    def test_volume_formula_manual(self):
        # 4 prongs, 1 rail, no struts, no splay → easy manual check
        wd = 1.0
        prong_len = 4.0  # basket_height with 0 splay
        stone_d = 6.0
        b = basket_geometry(4, stone_diameter_mm=stone_d, wire_diameter_mm=wd,
                            basket_height_mm=prong_len, splay_angle_deg=0.0,
                            rail_count=1, diagonal_struts=False)
        vol = basket_metal_volume_mm3(b)
        r = wd / 2.0
        # 4 prong cylinders
        prong_vol = 4 * _PI * r * r * prong_len
        # 1 rail at mid-radius (head and base same when no taper)
        mid_r = b["head_outer_radius_mm"]  # = stone_d/2 + wd = 4.0
        rail_circ = 2 * _PI * mid_r
        rail_vol = _PI * r * r * rail_circ
        expected = prong_vol + rail_vol  # struts = 0
        assert vol == pytest.approx(expected, rel=1e-3)


# ---------------------------------------------------------------------------
# basket_surface_area_mm2
# ---------------------------------------------------------------------------

class TestSurfaceArea:
    def test_surface_area_positive(self):
        b = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                            basket_height_mm=4.0)
        sa = basket_surface_area_mm2(b)
        assert sa > 0

    def test_surface_area_proportional_to_prong_count(self):
        b4 = basket_geometry(4, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                             basket_height_mm=4.0)
        b8 = basket_geometry(8, stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                             basket_height_mm=4.0)
        assert basket_surface_area_mm2(b8) > basket_surface_area_mm2(b4)


# ---------------------------------------------------------------------------
# metal_weight_grams
# ---------------------------------------------------------------------------

class TestMetalWeight:
    def test_18k_gold_density(self):
        # 1000 mm³ × 15.53 g/cm³ / 1000 = 15.53 g
        wt = metal_weight_grams(1000.0, 15.53)
        assert wt == pytest.approx(15.53, rel=1e-5)

    def test_negative_volume_raises(self):
        with pytest.raises(ValueError, match="volume_mm3"):
            metal_weight_grams(-1.0, 15.53)

    def test_zero_density_raises(self):
        with pytest.raises(ValueError, match="density_g_cm3"):
            metal_weight_grams(1000.0, 0.0)


# ---------------------------------------------------------------------------
# min_wire_diameter_check
# ---------------------------------------------------------------------------

class TestMinWireDiameterCheck:
    def test_adequate_wire_returns_none(self):
        # 1.0 mm wire for 0.5 ct stone (threshold 0.9 mm)
        result = min_wire_diameter_check(1.0, 0.5)
        assert result is None

    def test_thin_wire_returns_warning(self):
        # 0.7 mm wire for 0.5 ct stone (threshold 0.9 mm)
        result = min_wire_diameter_check(0.7, 0.5)
        assert result is not None
        assert "0.9" in result

    def test_boundary_at_0_75_ct(self):
        # Just below 0.75 ct uses threshold 0.9; at 0.75 uses 1.0
        warn_below = min_wire_diameter_check(0.95, 0.74)
        warn_at = min_wire_diameter_check(0.95, 0.75)
        # Below 0.75 ct: 0.9 mm threshold, 0.95 >= 0.9 → None
        assert warn_below is None
        # At 0.75 ct: 1.0 mm threshold, 0.95 < 1.0 → warning
        assert warn_at is not None

    def test_large_stone_uses_highest_threshold(self):
        # 5 ct stone uses 1.2 mm threshold
        warn = min_wire_diameter_check(1.1, 5.0)
        assert warn is not None
        assert "1.2" in warn

    def test_adequate_wire_large_stone_returns_none(self):
        warn = min_wire_diameter_check(1.3, 5.0)
        assert warn is None


# ---------------------------------------------------------------------------
# LLM tool specs
# ---------------------------------------------------------------------------

class TestToolSpecs:
    def test_basket_spec_name(self):
        assert jewelry_build_basket_gallery_spec.name == "jewelry_build_basket_gallery"

    def test_basket_spec_required_fields(self):
        req = jewelry_build_basket_gallery_spec.input_schema["required"]
        assert "file_id" in req
        assert "prong_count" in req
        assert "stone_diameter_mm" in req
        assert "wire_diameter_mm" in req
        assert "basket_height_mm" in req

    def test_under_bezel_spec_name(self):
        assert jewelry_build_under_bezel_gallery_spec.name == "jewelry_build_under_bezel_gallery"

    def test_cathedral_spec_name(self):
        assert jewelry_build_cathedral_shoulders_spec.name == "jewelry_build_cathedral_shoulders"

    def test_trellis_spec_name(self):
        assert jewelry_build_trellis_shoulders_spec.name == "jewelry_build_trellis_shoulders"

    def test_estimate_spec_name(self):
        assert jewelry_estimate_gallery_metal_spec.name == "jewelry_estimate_gallery_metal"


# ---------------------------------------------------------------------------
# LLM tool runners
# ---------------------------------------------------------------------------

class TestRunBasketGallery:
    def test_success_path(self):
        ctx, store, fid = make_ctx()
        r = build_basket(ctx, fid, prong_count=4, stone_diameter_mm=6.5,
                         wire_diameter_mm=1.0, basket_height_mm=4.0)
        assert "error" not in r, r
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1
        assert doc["features"][0]["op"] == "jewelry_gallery_basket"

    def test_node_id_in_response(self):
        ctx, _, fid = make_ctx()
        r = build_basket(ctx, fid, prong_count=4, stone_diameter_mm=6.5,
                         wire_diameter_mm=1.0, basket_height_mm=4.0)
        assert "error" not in r, r
        assert "node_id" in r

    def test_missing_required_returns_bad_args(self):
        ctx, _, fid = make_ctx()
        r = build_basket(ctx, fid, stone_diameter_mm=6.5,
                         wire_diameter_mm=1.0, basket_height_mm=4.0)
        assert "error" in r
        assert r["code"] == "BAD_ARGS"

    def test_invalid_file_id_returns_bad_args(self):
        ctx, _, _ = make_ctx()
        args = {"file_id": "not-a-uuid", "prong_count": 4,
                "stone_diameter_mm": 6.5, "wire_diameter_mm": 1.0,
                "basket_height_mm": 4.0}
        r = run_sync(run_jewelry_build_basket_gallery(ctx, json.dumps(args).encode()))
        assert "error" in r
        assert r["code"] == "BAD_ARGS"

    def test_not_found_file(self):
        ctx, store, fid = make_ctx(kind="NOT_FOUND")
        r = build_basket(ctx, fid, prong_count=4, stone_diameter_mm=6.5,
                         wire_diameter_mm=1.0, basket_height_mm=4.0)
        assert "error" in r
        assert r["code"] == "NOT_FOUND"

    def test_wire_warning_emitted_when_too_thin(self):
        ctx, _, fid = make_ctx()
        r = build_basket(ctx, fid, prong_count=4, stone_diameter_mm=6.5,
                         wire_diameter_mm=0.5, basket_height_mm=4.0,
                         stone_carat=2.0)
        assert "error" not in r, r
        assert "warnings" in r
        assert len(r["warnings"]) > 0

    def test_no_warning_when_wire_adequate(self):
        ctx, _, fid = make_ctx()
        r = build_basket(ctx, fid, prong_count=4, stone_diameter_mm=6.5,
                         wire_diameter_mm=1.2, basket_height_mm=4.0,
                         stone_carat=1.0)
        assert "error" not in r, r
        # warnings key absent or empty
        assert not r.get("warnings")


class TestRunUnderBezelGallery:
    def test_success_path(self):
        ctx, store, fid = make_ctx()
        r = build_under_bezel(ctx, fid, stone_diameter_mm=6.0,
                              wall_thickness_mm=1.0, gallery_height_mm=2.0)
        assert "error" not in r, r
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "jewelry_gallery_under_bezel"

    def test_missing_field_returns_bad_args(self):
        ctx, _, fid = make_ctx()
        r = build_under_bezel(ctx, fid, stone_diameter_mm=6.0,
                              wall_thickness_mm=1.0)
        assert "error" in r
        assert r["code"] == "BAD_ARGS"


class TestRunCathedralShoulders:
    def test_success_path(self):
        ctx, store, fid = make_ctx()
        r = build_cathedral(ctx, fid, prong_count=4, stone_diameter_mm=6.0,
                            wire_diameter_mm=1.0, basket_height_mm=4.0,
                            shank_width_mm=3.0)
        assert "error" not in r, r
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "jewelry_gallery_cathedral"


class TestRunTrellisShoulders:
    def test_success_path(self):
        ctx, store, fid = make_ctx()
        r = build_trellis(ctx, fid, prong_count=4, stone_diameter_mm=6.0,
                          wire_diameter_mm=1.0, basket_height_mm=4.0)
        assert "error" not in r, r
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "jewelry_gallery_trellis"


class TestRunEstimateGalleryMetal:
    def test_volume_and_surface_area_returned(self):
        r = estimate_metal(prong_count=4, stone_diameter_mm=6.0,
                           wire_diameter_mm=1.0, basket_height_mm=4.0)
        assert "error" not in r, r
        assert r["volume_mm3"] > 0
        assert r["surface_area_mm2"] > 0

    def test_weight_returned_when_density_provided(self):
        r = estimate_metal(prong_count=4, stone_diameter_mm=6.0,
                           wire_diameter_mm=1.0, basket_height_mm=4.0,
                           density_g_cm3=15.53)
        assert "error" not in r, r
        assert "weight_grams" in r
        assert r["weight_grams"] > 0

    def test_structural_warning_when_wire_too_thin(self):
        r = estimate_metal(prong_count=4, stone_diameter_mm=6.0,
                           wire_diameter_mm=0.6, basket_height_mm=4.0,
                           stone_carat=1.5)
        assert "error" not in r, r
        assert "structural_warning" in r

    def test_missing_required_returns_bad_args(self):
        r = estimate_metal(stone_diameter_mm=6.0, wire_diameter_mm=1.0,
                           basket_height_mm=4.0)
        assert "error" in r
        assert r["code"] == "BAD_ARGS"
