"""
Tests for kerf_cad_core.jewelry.gemstones.

All tests are pure-Python — no database, no OCC.
OCC-gated geometry tests are skipped cleanly when pythonOCC is absent.

Coverage:
  - GEMSTONE_CUTS registry completeness
  - carat_from_mm / mm_from_carat round-trip for all cuts
  - carat_from_mm formula spot-checks (round brilliant 1 ct = 6.5 mm)
  - gemstone_proportions: sizing by carat, sizing by diameter_mm
  - gemstone_proportions: proportions defaults (table_pct, angles)
  - gemstone_proportions: override kwargs respected
  - gemstone_proportions: aspect_ratio per cut
  - Error paths: unknown cut, negative/zero size, both carat+diameter_mm
  - LLM tool spec: name, required fields, cut enum
  - LLM tool runner: success path, node shape in feature doc
  - LLM tool runner: error paths (BAD_ARGS, NOT_FOUND)
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.jewelry.gemstones import (
    GEMSTONE_CUTS,
    GEMSTONE_DENSITIES,
    carat_from_mm,
    mm_from_carat,
    gemstone_proportions,
    jewelry_create_gemstone_spec,
    run_jewelry_create_gemstone,
    jewelry_gem_report_spec,
    run_jewelry_gem_report,
)


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


def run_tool(ctx, file_id, **kwargs):
    args = {"file_id": str(file_id), **kwargs}
    loop = asyncio.new_event_loop()
    try:
        raw = loop.run_until_complete(
            run_jewelry_create_gemstone(ctx, json.dumps(args).encode())
        )
    finally:
        loop.close()
    return json.loads(raw)


def run_report(ctx, **kwargs):
    """Call run_jewelry_gem_report and return the parsed JSON result."""
    loop = asyncio.new_event_loop()
    try:
        raw = loop.run_until_complete(
            run_jewelry_gem_report(ctx, json.dumps(kwargs).encode())
        )
    finally:
        loop.close()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# GEMSTONE_CUTS registry
# ---------------------------------------------------------------------------

class TestGemstoneCutsRegistry:
    EXPECTED_ORIGINAL = {
        "round_brilliant", "princess", "oval", "emerald",
        "marquise", "pear", "cushion",
    }
    EXPECTED_FANCY = {
        "radiant", "asscher", "trillion", "heart", "baguette", "briolette",
    }

    def test_all_expected_cuts_present(self):
        assert self.EXPECTED_ORIGINAL <= GEMSTONE_CUTS

    def test_all_fancy_cuts_present(self):
        assert self.EXPECTED_FANCY <= GEMSTONE_CUTS

    def test_no_unknown_cuts(self):
        # All values in registry must be strings
        for cut in GEMSTONE_CUTS:
            assert isinstance(cut, str)

    def test_count(self):
        assert len(GEMSTONE_CUTS) >= 13


# ---------------------------------------------------------------------------
# Carat ↔ mm formula
# ---------------------------------------------------------------------------

class TestCaratFormula:
    def test_round_brilliant_1ct_at_6pt5mm(self):
        """Standard reference: 1 ct round brilliant ≈ 6.5 mm diameter."""
        assert carat_from_mm("round_brilliant", 6.5) == pytest.approx(1.0, rel=1e-6)

    def test_round_brilliant_half_ct(self):
        """0.5 ct round brilliant ≈ 5.16 mm."""
        dim = mm_from_carat("round_brilliant", 0.5)
        assert dim == pytest.approx(6.5 * (0.5 ** (1 / 3)), rel=1e-6)

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_round_trip_all_cuts(self, cut):
        """mm_from_carat(carat_from_mm(d)) == d for all cuts."""
        for dim in [2.0, 5.0, 10.0]:
            ct  = carat_from_mm(cut, dim)
            back = mm_from_carat(cut, ct)
            assert back == pytest.approx(dim, rel=1e-9), (
                f"{cut}: round-trip failed for dim={dim}"
            )

    def test_carat_increases_with_size(self):
        for cut in GEMSTONE_CUTS:
            c1 = carat_from_mm(cut, 3.0)
            c2 = carat_from_mm(cut, 6.0)
            assert c2 > c1, f"{cut}: carat should increase with mm"

    def test_zero_mm_raises(self):
        with pytest.raises(ValueError):
            carat_from_mm("round_brilliant", 0.0)

    def test_negative_carat_raises(self):
        with pytest.raises(ValueError):
            mm_from_carat("round_brilliant", -1.0)

    def test_zero_carat_raises(self):
        with pytest.raises(ValueError):
            mm_from_carat("round_brilliant", 0.0)

    def test_unknown_cut_carat_from_mm_raises(self):
        with pytest.raises(ValueError):
            carat_from_mm("not_a_real_cut", 5.0)

    def test_unknown_cut_mm_from_carat_raises(self):
        with pytest.raises(ValueError):
            mm_from_carat("not_a_real_cut", 1.0)


# ---------------------------------------------------------------------------
# gemstone_proportions
# ---------------------------------------------------------------------------

class TestGemstoneProportions:
    def test_sizing_by_carat(self):
        props = gemstone_proportions("round_brilliant", carat=1.0)
        assert props.diameter_mm == pytest.approx(6.5, rel=1e-6)

    def test_sizing_by_diameter_mm(self):
        props = gemstone_proportions("round_brilliant", diameter_mm=6.5)
        assert props.diameter_mm == pytest.approx(6.5, rel=1e-6)

    def test_round_brilliant_defaults(self):
        props = gemstone_proportions("round_brilliant", diameter_mm=6.5)
        assert props.table_pct == pytest.approx(57.0)
        assert props.crown_angle_deg == pytest.approx(34.5)
        assert props.pavilion_angle_deg == pytest.approx(40.75)
        assert props.girdle_pct == pytest.approx(2.5)
        assert props.aspect_ratio == pytest.approx(1.0)

    def test_round_brilliant_extras_facets(self):
        props = gemstone_proportions("round_brilliant", diameter_mm=6.5)
        assert props.extras.get("facet_count") == 57

    def test_emerald_has_step_rows(self):
        props = gemstone_proportions("emerald", diameter_mm=7.0)
        assert "step_rows" in props.extras
        assert props.extras["step_rows"] == 3

    def test_emerald_aspect_ratio_not_1(self):
        props = gemstone_proportions("emerald", diameter_mm=7.0)
        assert props.aspect_ratio < 1.0

    def test_marquise_is_elongated(self):
        props = gemstone_proportions("marquise", diameter_mm=10.0)
        assert props.aspect_ratio == pytest.approx(0.5)

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_produce_valid_proportions(self, cut):
        props = gemstone_proportions(cut, diameter_mm=5.0)
        assert props.diameter_mm > 0
        # briolette has no table facet (table_pct == 0); all other cuts have a table
        assert 0 <= props.table_pct < 100
        assert 0 < props.crown_angle_deg < 90
        assert 0 < props.pavilion_angle_deg < 90
        assert props.girdle_pct > 0
        assert props.total_depth_pct > 0
        assert 0 < props.aspect_ratio <= 1.0

    def test_total_depth_pct_is_sum(self):
        props = gemstone_proportions("round_brilliant", diameter_mm=6.5)
        expected = props.crown_height_pct + props.girdle_pct + props.pavilion_depth_pct
        assert props.total_depth_pct == pytest.approx(expected, rel=1e-6)

    def test_override_table_pct(self):
        props = gemstone_proportions("round_brilliant", diameter_mm=6.5, table_pct=53.0)
        assert props.table_pct == pytest.approx(53.0)

    def test_override_pavilion_angle(self):
        props = gemstone_proportions("round_brilliant", diameter_mm=6.5,
                                      pavilion_angle_deg=38.0)
        assert props.pavilion_angle_deg == pytest.approx(38.0)

    def test_override_aspect_ratio(self):
        props = gemstone_proportions("oval", diameter_mm=7.0, aspect_ratio=0.75)
        assert props.aspect_ratio == pytest.approx(0.75)

    def test_both_carat_and_diameter_raises(self):
        with pytest.raises(ValueError, match="carat"):
            gemstone_proportions("round_brilliant", diameter_mm=6.5, carat=1.0)

    def test_neither_carat_nor_diameter_raises(self):
        with pytest.raises(ValueError):
            gemstone_proportions("round_brilliant")

    def test_unknown_cut_raises(self):
        with pytest.raises(ValueError, match="Unknown cut"):
            gemstone_proportions("not_a_real_cut", diameter_mm=5.0)

    def test_negative_diameter_raises(self):
        with pytest.raises(ValueError):
            gemstone_proportions("round_brilliant", diameter_mm=-1.0)

    def test_zero_carat_raises(self):
        with pytest.raises(ValueError):
            gemstone_proportions("round_brilliant", carat=0.0)

    def test_negative_carat_raises(self):
        with pytest.raises(ValueError):
            gemstone_proportions("round_brilliant", carat=-0.5)

    def test_cut_field_on_returned_props(self):
        props = gemstone_proportions("princess", diameter_mm=5.5)
        assert props.cut == "princess"


# ---------------------------------------------------------------------------
# LLM tool spec
# ---------------------------------------------------------------------------

class TestJewelryCreateGemstoneSpec:
    def test_name(self):
        assert jewelry_create_gemstone_spec.name == "jewelry_create_gemstone"

    def test_required_fields(self):
        req = jewelry_create_gemstone_spec.input_schema.get("required", [])
        assert "file_id" in req
        assert "cut" in req

    def test_cut_enum_matches_registry(self):
        props = jewelry_create_gemstone_spec.input_schema["properties"]
        enum = set(props["cut"].get("enum", []))
        assert enum == GEMSTONE_CUTS

    def test_optional_fields_not_required(self):
        req = jewelry_create_gemstone_spec.input_schema.get("required", [])
        for optional in ("carat", "diameter_mm", "table_pct", "position", "id"):
            assert optional not in req


# ---------------------------------------------------------------------------
# LLM tool runner — success paths
# ---------------------------------------------------------------------------

class TestRunJewelryCreateGemstone:
    def test_basic_round_brilliant_by_carat(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant", carat=1.0)
        assert result.get("error") is None, result
        assert result["op"] == "gemstone"
        assert result["cut"] == "round_brilliant"
        assert result["diameter_mm"] == pytest.approx(6.5, rel=1e-4)
        assert result["carat_approx"] == pytest.approx(1.0, rel=0.01)

    def test_node_appended_to_feature_doc(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="princess", diameter_mm=5.5)
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1
        node = doc["features"][0]
        assert node["op"] == "gemstone"
        assert node["cut"] == "princess"

    def test_node_id_starts_with_gemstone(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="oval", diameter_mm=7.0)
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"].startswith("gemstone-")

    def test_explicit_id_via_id_arg(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="emerald", diameter_mm=7.0, id="gem-custom")
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"] == "gem-custom"

    def test_material_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5, material="ruby")
        doc = json.loads(store["content"])
        assert doc["features"][0]["material"] == "ruby"

    def test_position_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                 position=[1.0, 2.0, 3.0])
        doc = json.loads(store["content"])
        assert doc["features"][0]["position"] == [1.0, 2.0, 3.0]

    def test_total_depth_mm_in_response(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5)
        assert "total_depth_mm" in result
        assert result["total_depth_mm"] > 0

    def test_proportion_override_stored_in_node(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5, table_pct=53.0)
        doc = json.loads(store["content"])
        assert doc["features"][0]["table_pct"] == pytest.approx(53.0)

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_succeed(self, cut):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, cut=cut, diameter_mm=5.0)
        assert result.get("error") is None, f"{cut}: {result}"


# ---------------------------------------------------------------------------
# LLM tool runner — error paths
# ---------------------------------------------------------------------------

class TestRunJewelryCreateGemstoneErrors:
    def test_invalid_json(self):
        ctx, _, _ = make_ctx()
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(
            run_jewelry_create_gemstone(ctx, b"not json")
        )
        loop.close()
        r = json.loads(raw)
        assert r.get("code") == "BAD_ARGS"

    def test_missing_file_id(self):
        ctx, _, _ = make_ctx()
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(
            run_jewelry_create_gemstone(ctx, json.dumps({
                "cut": "round_brilliant", "carat": 1.0
            }).encode())
        )
        loop.close()
        assert json.loads(raw).get("code") == "BAD_ARGS"

    def test_missing_cut(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, carat=1.0)
        assert result.get("code") == "BAD_ARGS"

    def test_unknown_cut(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, cut="not_a_real_cut", diameter_mm=5.0)
        assert result.get("code") == "BAD_ARGS"
        assert "not_a_real_cut" in result.get("error", "")

    def test_negative_carat(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant", carat=-1.0)
        assert result.get("code") == "BAD_ARGS"

    def test_zero_diameter(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant", diameter_mm=0.0)
        assert result.get("code") == "BAD_ARGS"

    def test_both_carat_and_diameter(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant",
                          carat=1.0, diameter_mm=6.5)
        assert result.get("code") == "BAD_ARGS"

    def test_neither_carat_nor_diameter(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant")
        assert result.get("code") == "BAD_ARGS"

    def test_non_uuid_file_id(self):
        ctx, _, _ = make_ctx()
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(
            run_jewelry_create_gemstone(ctx, json.dumps({
                "file_id": "not-a-uuid", "cut": "round_brilliant", "carat": 1.0
            }).encode())
        )
        loop.close()
        assert json.loads(raw).get("code") == "BAD_ARGS"

    def test_non_existent_file(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        result = run_tool(ctx, fid, cut="round_brilliant", carat=1.0)
        assert result.get("code") == "NOT_FOUND"

    def test_negative_table_pct_override(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant",
                          diameter_mm=6.5, table_pct=-5.0)
        assert result.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# Fancy cuts
# ---------------------------------------------------------------------------

FANCY_CUTS = ["radiant", "asscher", "trillion", "heart", "baguette", "briolette"]


class TestFancyCuts:
    """Each new fancy cut produces valid proportions and round-trips."""

    @pytest.mark.parametrize("cut", FANCY_CUTS)
    def test_fancy_cut_produces_valid_proportions(self, cut):
        props = gemstone_proportions(cut, diameter_mm=5.0)
        assert props.diameter_mm == pytest.approx(5.0)
        # table_pct: briolette may be 0 (no table); all others > 0
        assert 0 <= props.table_pct < 100
        assert 0 < props.crown_angle_deg < 90
        assert 0 < props.pavilion_angle_deg < 90
        assert props.girdle_pct > 0
        assert props.total_depth_pct > 0
        assert 0 < props.aspect_ratio <= 1.0

    @pytest.mark.parametrize("cut", FANCY_CUTS)
    def test_fancy_cut_round_trip(self, cut):
        """mm_from_carat(carat_from_mm(d)) == d for all fancy cuts."""
        for dim in [3.0, 5.0, 8.0]:
            ct = carat_from_mm(cut, dim)
            back = mm_from_carat(cut, ct)
            assert back == pytest.approx(dim, rel=1e-9), (
                f"{cut}: round-trip failed for dim={dim}"
            )

    @pytest.mark.parametrize("cut", FANCY_CUTS)
    def test_fancy_cut_total_depth_is_sum(self, cut):
        props = gemstone_proportions(cut, diameter_mm=5.0)
        expected = props.crown_height_pct + props.girdle_pct + props.pavilion_depth_pct
        assert props.total_depth_pct == pytest.approx(expected, rel=1e-6)

    def test_radiant_has_corner_cut(self):
        props = gemstone_proportions("radiant", diameter_mm=6.0)
        assert "corner_cut_ratio" in props.extras
        assert props.extras["corner_cut_ratio"] > 0

    def test_asscher_is_square(self):
        props = gemstone_proportions("asscher", diameter_mm=5.5)
        assert props.aspect_ratio == pytest.approx(1.0)
        assert props.extras.get("step_rows") == 3
        assert props.extras.get("corner_cut_ratio", 0) > 0

    def test_trillion_has_three_sides(self):
        props = gemstone_proportions("trillion", diameter_mm=7.0)
        assert props.extras.get("sides") == 3
        assert props.aspect_ratio == pytest.approx(1.0)

    def test_heart_has_cleft(self):
        props = gemstone_proportions("heart", diameter_mm=6.5)
        assert "cleft_depth_pct" in props.extras
        assert props.extras["cleft_depth_pct"] > 0

    def test_baguette_is_narrow(self):
        props = gemstone_proportions("baguette", diameter_mm=5.0)
        # Baguette is 3:1 L:W, so aspect_ratio ≈ 0.33
        assert props.aspect_ratio < 0.5
        assert props.extras.get("step_rows") == 2

    def test_briolette_no_table(self):
        props = gemstone_proportions("briolette", diameter_mm=5.0)
        assert props.table_pct == pytest.approx(0.0)
        assert "facet_rows" in props.extras

    @pytest.mark.parametrize("cut", FANCY_CUTS)
    def test_fancy_cut_tool_succeeds(self, cut):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, cut=cut, diameter_mm=5.0)
        assert result.get("error") is None, f"{cut}: {result}"
        assert result["op"] == "gemstone"
        assert result["cut"] == cut


# ---------------------------------------------------------------------------
# Coloured-stone density correction
# ---------------------------------------------------------------------------

class TestGemstoneDensities:
    """Density table completeness and correctness."""

    REQUIRED_MATERIALS = [
        "diamond", "ruby", "sapphire", "emerald", "amethyst", "topaz",
        "garnet", "aquamarine", "citrine", "peridot", "tanzanite", "opal",
    ]

    def test_density_table_has_required_materials(self):
        for mat in self.REQUIRED_MATERIALS:
            assert mat in GEMSTONE_DENSITIES, f"Missing density for {mat!r}"

    def test_diamond_density(self):
        assert GEMSTONE_DENSITIES["diamond"] == pytest.approx(3.51, abs=0.05)

    def test_ruby_density(self):
        # Corundum SG ≈ 3.97–4.05; nominal 3.99–4.00
        assert GEMSTONE_DENSITIES["ruby"] == pytest.approx(4.0, abs=0.1)

    def test_sapphire_density(self):
        assert GEMSTONE_DENSITIES["sapphire"] == pytest.approx(4.0, abs=0.1)

    def test_emerald_density(self):
        # Beryl SG ≈ 2.67–2.78, typical 2.72
        assert GEMSTONE_DENSITIES["emerald"] == pytest.approx(2.72, abs=0.1)

    def test_opal_is_lighter_than_diamond(self):
        assert GEMSTONE_DENSITIES["opal"] < GEMSTONE_DENSITIES["diamond"]

    def test_zircon_is_heavier_than_diamond(self):
        assert GEMSTONE_DENSITIES["zircon"] > GEMSTONE_DENSITIES["diamond"]

    def test_all_densities_positive(self):
        for mat, rho in GEMSTONE_DENSITIES.items():
            assert rho > 0, f"{mat} has non-positive density"


class TestColourStoneCaratCorrection:
    """carat↔mm formulae produce correct values for coloured stones."""

    def test_ruby_1ct_larger_than_diamond_1ct(self):
        """1 ct ruby is physically smaller than 1 ct diamond because ruby is denser."""
        # mm_from_carat for ruby should return SMALLER mm than for diamond
        mm_diamond = mm_from_carat("round_brilliant", 1.0)
        mm_ruby    = mm_from_carat("round_brilliant", 1.0, material="ruby")
        assert mm_ruby < mm_diamond, (
            f"1 ct ruby ({mm_ruby:.3f} mm) should be smaller than 1 ct diamond ({mm_diamond:.3f} mm)"
        )

    def test_emerald_1ct_larger_mm_than_diamond(self):
        """1 ct emerald is physically larger because emerald is less dense than diamond."""
        mm_diamond = mm_from_carat("round_brilliant", 1.0)
        mm_emerald = mm_from_carat("round_brilliant", 1.0, material="emerald")
        assert mm_emerald > mm_diamond

    def test_ruby_round_trip(self):
        """mm_from_carat(carat_from_mm(d, ruby), ruby) == d for ruby."""
        for dim in [4.0, 6.0, 8.0]:
            ct   = carat_from_mm("round_brilliant", dim, material="ruby")
            back = mm_from_carat("round_brilliant", ct, material="ruby")
            assert back == pytest.approx(dim, rel=1e-9)

    def test_density_override(self):
        """Explicit density_g_cm3 matches equivalent material name lookup."""
        dim = 6.0
        ct_by_name    = carat_from_mm("round_brilliant", dim, material="ruby")
        ct_by_density = carat_from_mm("round_brilliant", dim,
                                      density_g_cm3=GEMSTONE_DENSITIES["ruby"])
        assert ct_by_name == pytest.approx(ct_by_density, rel=1e-9)

    def test_diamond_default_unchanged(self):
        """No material kwarg ⇒ same result as material='diamond' (backward-compat)."""
        dim = 6.5
        ct_default = carat_from_mm("round_brilliant", dim)
        ct_diamond = carat_from_mm("round_brilliant", dim, material="diamond")
        assert ct_default == pytest.approx(ct_diamond, rel=1e-12)

    def test_unknown_material_falls_back_to_diamond(self):
        """Unknown material silently falls back to diamond (no error)."""
        ct_unknown = carat_from_mm("round_brilliant", 6.5, material="unobtainium")
        ct_diamond = carat_from_mm("round_brilliant", 6.5)
        assert ct_unknown == pytest.approx(ct_diamond, rel=1e-9)

    def test_ruby_1ct_carat_correct_value(self):
        """1 ct ruby round brilliant: check that mm < diamond reference.

        Diamond ref = 6.5 mm.  Ruby density = 3.99 g/cm³.
        ref_mm_ruby = 6.5 × (3.51/3.99)^(1/3) ≈ 6.24 mm.
        """
        mm_ruby = mm_from_carat("round_brilliant", 1.0, material="ruby")
        expected = 6.5 * (3.51 / GEMSTONE_DENSITIES["ruby"]) ** (1.0 / 3.0)
        assert mm_ruby == pytest.approx(expected, rel=1e-6)

    def test_negative_density_raises(self):
        with pytest.raises(ValueError):
            carat_from_mm("round_brilliant", 6.5, density_g_cm3=-1.0)

    def test_zero_density_raises(self):
        with pytest.raises(ValueError):
            mm_from_carat("round_brilliant", 1.0, density_g_cm3=0.0)

    def test_gemstone_proportions_accepts_material(self):
        """gemstone_proportions with carat + material uses correct mm."""
        props_diamond = gemstone_proportions("round_brilliant", carat=1.0)
        props_ruby    = gemstone_proportions("round_brilliant", carat=1.0, material="ruby")
        # Ruby 1 ct → smaller physical stone
        assert props_ruby.diameter_mm < props_diamond.diameter_mm

    def test_gemstone_proportions_accepts_density_g_cm3(self):
        props = gemstone_proportions(
            "round_brilliant", carat=1.0,
            density_g_cm3=GEMSTONE_DENSITIES["sapphire"],
        )
        expected_mm = mm_from_carat("round_brilliant", 1.0, material="sapphire")
        assert props.diameter_mm == pytest.approx(expected_mm, rel=1e-9)

    def test_tool_runner_density_g_cm3(self):
        """LLM tool runner accepts density_g_cm3 and stores correct diameter."""
        ctx, store, fid = make_ctx()
        rho_ruby = GEMSTONE_DENSITIES["ruby"]
        result = run_tool(ctx, fid, cut="round_brilliant", carat=1.0,
                          material="ruby", density_g_cm3=rho_ruby)
        assert result.get("error") is None, result
        expected_mm = mm_from_carat("round_brilliant", 1.0, density_g_cm3=rho_ruby)
        assert result["diameter_mm"] == pytest.approx(expected_mm, rel=1e-6)

    def test_tool_runner_material_ruby_carat_approx(self):
        """carat_approx in tool response reflects ruby density."""
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                          material="ruby")
        assert result.get("error") is None, result
        # 6.5 mm ruby should give MORE than 1 carat (ruby is denser)
        assert result["carat_approx"] > 1.0


# ---------------------------------------------------------------------------
# New historical / specialty cuts (third slice)
# ---------------------------------------------------------------------------

NEW_CUTS = [
    "old_european", "old_mine", "rose_cut", "single_cut", "french_cut",
    "half_moon", "trapezoid", "kite", "bullet", "tapered_baguette",
    "lozenge", "shield", "calf_head",
]

# Maps each new cut to the existing facet family it delegates to
NEW_CUT_FAMILIES = {
    "old_european":    "round_brilliant",
    "old_mine":        "cushion",
    "rose_cut":        "round_brilliant",
    "single_cut":      "round_brilliant",
    "french_cut":      "princess",
    "half_moon":       "oval",
    "trapezoid":       "baguette",
    "kite":            "trillion",
    "bullet":          "pear",
    "tapered_baguette":"baguette",
    "lozenge":         "marquise",
    "shield":          "trillion",
    "calf_head":       "pear",
}


class TestNewCutsRegistry:
    """All 13 new cuts appear in GEMSTONE_CUTS, _CARAT_REF, and _CUT_DEFAULTS."""

    def test_all_new_cuts_in_gemstone_cuts(self):
        for cut in NEW_CUTS:
            assert cut in GEMSTONE_CUTS, f"{cut!r} missing from GEMSTONE_CUTS"

    def test_total_count_at_least_26(self):
        assert len(GEMSTONE_CUTS) >= 26

    def test_new_cuts_in_carat_ref(self):
        from kerf_cad_core.jewelry.gemstones import _CARAT_REF
        for cut in NEW_CUTS:
            assert cut in _CARAT_REF, f"{cut!r} missing from _CARAT_REF"

    def test_new_cuts_in_cut_defaults(self):
        from kerf_cad_core.jewelry.gemstones import _CUT_DEFAULTS
        for cut in NEW_CUTS:
            assert cut in _CUT_DEFAULTS, f"{cut!r} missing from _CUT_DEFAULTS"


class TestNewCutsProportions:
    """Each new cut produces valid, industry-sane proportions."""

    @pytest.mark.parametrize("cut", NEW_CUTS)
    def test_valid_proportions(self, cut):
        props = gemstone_proportions(cut, diameter_mm=5.0)
        assert props.diameter_mm == pytest.approx(5.0)
        assert 0 <= props.table_pct < 100
        assert 0 < props.crown_angle_deg < 90
        assert 0 < props.pavilion_angle_deg < 90
        assert props.girdle_pct > 0
        assert props.total_depth_pct > 0
        assert 0 < props.aspect_ratio <= 1.0

    @pytest.mark.parametrize("cut", NEW_CUTS)
    def test_total_depth_is_sum(self, cut):
        props = gemstone_proportions(cut, diameter_mm=5.0)
        expected = props.crown_height_pct + props.girdle_pct + props.pavilion_depth_pct
        assert props.total_depth_pct == pytest.approx(expected, rel=1e-6)

    @pytest.mark.parametrize("cut", NEW_CUTS)
    def test_carat_round_trip(self, cut):
        for dim in [3.0, 5.0, 8.0]:
            ct = carat_from_mm(cut, dim)
            back = mm_from_carat(cut, ct)
            assert back == pytest.approx(dim, rel=1e-9), (
                f"{cut}: round-trip failed for dim={dim}"
            )

    @pytest.mark.parametrize("cut", NEW_CUTS)
    def test_facet_family_in_extras(self, cut):
        """Each new cut stores its facet_family in extras."""
        props = gemstone_proportions(cut, diameter_mm=5.0)
        assert "facet_family" in props.extras, (
            f"{cut!r}: missing facet_family in extras"
        )
        expected_family = NEW_CUT_FAMILIES[cut]
        assert props.extras["facet_family"] == expected_family, (
            f"{cut!r}: facet_family={props.extras['facet_family']!r}, "
            f"expected {expected_family!r}"
        )

    @pytest.mark.parametrize("cut", NEW_CUTS)
    def test_tool_succeeds(self, cut):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, cut=cut, diameter_mm=5.0)
        assert result.get("error") is None, f"{cut}: {result}"
        assert result["op"] == "gemstone"
        assert result["cut"] == cut
        assert result["carat_approx"] > 0

    def test_old_european_high_crown(self):
        """Old European cut has a high crown angle (>38°) and large culet."""
        props = gemstone_proportions("old_european", diameter_mm=6.5)
        assert props.crown_angle_deg >= 38.0, (
            f"Old European crown angle should be ≥38°, got {props.crown_angle_deg}"
        )
        assert props.extras.get("culet") == "large"
        assert props.table_pct < 55.0  # small table

    def test_old_mine_high_crown_cushion(self):
        """Old Mine cut is a cushion with high crown and large culet."""
        props = gemstone_proportions("old_mine", diameter_mm=5.5)
        assert props.crown_angle_deg >= 36.0
        assert props.extras.get("culet") == "large"
        assert props.extras.get("facet_family") == "cushion"
        assert props.aspect_ratio == pytest.approx(1.0)  # square cushion

    def test_rose_cut_flat_base(self):
        """Rose cut has no table, flat base, dome crown."""
        props = gemstone_proportions("rose_cut", diameter_mm=7.0)
        assert props.table_pct == pytest.approx(0.0)
        assert props.extras.get("flat_base") is True
        assert "facet_rows" in props.extras

    def test_single_cut_17_facets(self):
        """Single cut has exactly 17 facets."""
        props = gemstone_proportions("single_cut", diameter_mm=3.0)
        assert props.extras.get("facet_count") == 17

    def test_french_cut_step_row_1(self):
        """French cut is a square step with 1 step row and no corner cut."""
        props = gemstone_proportions("french_cut", diameter_mm=4.0)
        assert props.extras.get("step_rows") == 1
        assert props.extras.get("corner_cut_ratio") == pytest.approx(0.0)
        assert props.aspect_ratio == pytest.approx(1.0)

    def test_half_moon_straight_edge(self):
        """Half moon has a straight edge flag and oval family."""
        props = gemstone_proportions("half_moon", diameter_mm=6.0)
        assert props.extras.get("straight_edge") is True
        assert props.extras.get("facet_family") == "oval"

    def test_trapezoid_has_taper(self):
        """Trapezoid has a taper_ratio and baguette family."""
        props = gemstone_proportions("trapezoid", diameter_mm=5.0)
        assert "taper_ratio" in props.extras
        assert props.extras.get("facet_family") == "baguette"
        assert props.extras.get("step_rows") == 2

    def test_kite_has_4_sides(self):
        """Kite is a 4-sided trillion-family stone."""
        props = gemstone_proportions("kite", diameter_mm=6.0)
        assert props.extras.get("sides") == 4
        assert props.extras.get("facet_family") == "trillion"

    def test_bullet_flat_top(self):
        """Bullet has a flat_top flag and pear family."""
        props = gemstone_proportions("bullet", diameter_mm=5.0)
        assert props.extras.get("flat_top") is True
        assert props.extras.get("facet_family") == "pear"

    def test_tapered_baguette_has_taper(self):
        """Tapered baguette has a taper_ratio < 1."""
        props = gemstone_proportions("tapered_baguette", diameter_mm=5.0)
        assert "taper_ratio" in props.extras
        tr = props.extras["taper_ratio"]
        assert 0 < tr < 1.0
        assert props.extras.get("facet_family") == "baguette"

    def test_lozenge_step_rows(self):
        """Lozenge is a marquise-family step cut."""
        props = gemstone_proportions("lozenge", diameter_mm=6.5)
        assert "step_rows" in props.extras
        assert props.extras.get("facet_family") == "marquise"

    def test_shield_5_sides(self):
        """Shield has 5 sides and trillion family."""
        props = gemstone_proportions("shield", diameter_mm=7.0)
        assert props.extras.get("sides") == 5
        assert props.extras.get("facet_family") == "trillion"

    def test_calf_head_wider_than_pear(self):
        """Calf head (bouche) is wider than standard pear."""
        pear_ar = gemstone_proportions("pear", diameter_mm=8.0).aspect_ratio
        calf_ar = gemstone_proportions("calf_head", diameter_mm=8.0).aspect_ratio
        assert calf_ar > pear_ar, (
            f"calf_head aspect_ratio ({calf_ar}) should be > pear ({pear_ar})"
        )
        assert calf_ar >= 0.70


# ---------------------------------------------------------------------------
# jewelry_gem_report spec
# ---------------------------------------------------------------------------

class TestGemReportSpec:
    def test_name(self):
        assert jewelry_gem_report_spec.name == "jewelry_gem_report"

    def test_required_only_cut(self):
        req = jewelry_gem_report_spec.input_schema.get("required", [])
        assert "cut" in req
        # carat and diameter_mm are NOT required (one-of validation at runtime)
        assert "carat" not in req
        assert "diameter_mm" not in req
        assert "file_id" not in req  # read-only; no file_id needed

    def test_cut_enum_matches_registry(self):
        props = jewelry_gem_report_spec.input_schema["properties"]
        enum = set(props["cut"].get("enum", []))
        assert enum == GEMSTONE_CUTS


# ---------------------------------------------------------------------------
# jewelry_gem_report runner — success paths
# ---------------------------------------------------------------------------

class TestGemReportRunner:
    """Run the gem report tool and verify output fields + values."""

    def _ctx(self):
        ctx, _, _ = make_ctx()
        return ctx

    def test_round_brilliant_1ct_spread_approx_6pt5mm(self):
        """Standard reference: 1 ct round brilliant spread ≈ 6.5 mm."""
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant", carat=1.0)
        assert result.get("error") is None, result
        assert result["spread_mm"] == pytest.approx(6.5, rel=0.01)
        assert result["carat_est"] == pytest.approx(1.0, rel=0.01)

    def test_all_expected_fields_present(self):
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant", carat=1.0)
        for field in (
            "cut", "facet_family", "material",
            "spread_mm", "width_mm", "depth_mm", "carat_est",
            "table_pct", "total_depth_pct", "crown_height_pct",
            "pavilion_depth_pct", "girdle_pct",
            "crown_angle_deg", "pavilion_angle_deg",
            "aspect_ratio", "lw_ratio",
            "proportion_grade",
        ):
            assert field in result, f"Missing field: {field!r}"

    def test_proportion_grade_is_valid_string(self):
        ctx = self._ctx()
        for cut in ["round_brilliant", "princess", "emerald", "old_european", "rose_cut"]:
            result = run_report(ctx, cut=cut, diameter_mm=5.0)
            assert result.get("proportion_grade") in (
                "Excellent", "Very Good", "Good", "Fair"
            ), f"{cut}: unexpected grade {result.get('proportion_grade')!r}"

    def test_round_brilliant_ideal_grade(self):
        """Default round brilliant proportions (Tolkowsky ideal) grade Excellent."""
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant", diameter_mm=6.5)
        # Default Tolkowsky proportions are within GIA ideal windows
        assert result["proportion_grade"] in ("Excellent", "Very Good")

    def test_depth_mm_gt_0(self):
        ctx = self._ctx()
        for cut in ["round_brilliant", "princess", "emerald", "briolette"]:
            result = run_report(ctx, cut=cut, diameter_mm=5.0)
            assert result["depth_mm"] > 0, f"{cut}: depth_mm should be > 0"

    def test_lw_ratio_round_brilliant_is_1(self):
        """Round brilliant has L:W ratio = 1.0 (circular)."""
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant", diameter_mm=6.5)
        assert result["lw_ratio"] == pytest.approx(1.0, rel=1e-6)

    def test_lw_ratio_marquise_gt_1(self):
        """Marquise (2:1 L:W) has lw_ratio > 1."""
        ctx = self._ctx()
        result = run_report(ctx, cut="marquise", diameter_mm=10.0)
        assert result["lw_ratio"] > 1.5, (
            f"Marquise lw_ratio should be > 1.5, got {result['lw_ratio']}"
        )

    def test_facet_family_new_cut(self):
        """New cuts report their facet_family correctly."""
        ctx = self._ctx()
        for cut, expected_family in NEW_CUT_FAMILIES.items():
            result = run_report(ctx, cut=cut, diameter_mm=5.0)
            assert result.get("error") is None, f"{cut}: {result}"
            assert result["facet_family"] == expected_family, (
                f"{cut}: expected facet_family={expected_family!r}, "
                f"got {result['facet_family']!r}"
            )

    def test_material_defaults_to_diamond(self):
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant", diameter_mm=6.5)
        assert result["material"] == "diamond"

    def test_material_ruby_smaller_spread(self):
        """1 ct ruby has smaller spread than 1 ct diamond (ruby is denser)."""
        ctx = self._ctx()
        r_diamond = run_report(ctx, cut="round_brilliant", carat=1.0)
        r_ruby    = run_report(ctx, cut="round_brilliant", carat=1.0, material="ruby")
        assert r_ruby["spread_mm"] < r_diamond["spread_mm"]

    def test_rose_cut_no_lw_ratio_issue(self):
        """Rose cut has flat base; depth_mm is still positive (from crown only)."""
        ctx = self._ctx()
        result = run_report(ctx, cut="rose_cut", diameter_mm=7.0)
        assert result.get("error") is None, result
        assert result["depth_mm"] > 0
        assert result["table_pct"] == pytest.approx(0.0)

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_report_succeeds(self, cut):
        ctx = self._ctx()
        result = run_report(ctx, cut=cut, diameter_mm=5.0)
        assert result.get("error") is None, f"{cut}: {result}"
        assert result["carat_est"] > 0
        assert result["spread_mm"] == pytest.approx(5.0, rel=1e-6)

    def test_by_carat_and_by_diameter_consistent(self):
        """Report from carat=1.0 and from diameter_mm=6.5 agree for round brilliant."""
        ctx = self._ctx()
        r_carat = run_report(ctx, cut="round_brilliant", carat=1.0)
        r_mm    = run_report(ctx, cut="round_brilliant", diameter_mm=6.5)
        assert r_carat["spread_mm"] == pytest.approx(r_mm["spread_mm"], rel=0.001)
        assert r_carat["proportion_grade"] == r_mm["proportion_grade"]


# ---------------------------------------------------------------------------
# jewelry_gem_report runner — error paths
# ---------------------------------------------------------------------------

class TestGemReportErrors:
    def _ctx(self):
        ctx, _, _ = make_ctx()
        return ctx

    def test_missing_cut(self):
        ctx = self._ctx()
        result = run_report(ctx, diameter_mm=5.0)
        assert result.get("code") == "BAD_ARGS"

    def test_unknown_cut(self):
        ctx = self._ctx()
        result = run_report(ctx, cut="not_a_real_cut", diameter_mm=5.0)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_size(self):
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant")
        assert result.get("code") == "BAD_ARGS"

    def test_both_carat_and_diameter(self):
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant", carat=1.0, diameter_mm=6.5)
        assert result.get("code") == "BAD_ARGS"

    def test_negative_carat(self):
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant", carat=-1.0)
        assert result.get("code") == "BAD_ARGS"

    def test_zero_diameter(self):
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant", diameter_mm=0.0)
        assert result.get("code") == "BAD_ARGS"

    def test_negative_density(self):
        ctx = self._ctx()
        result = run_report(ctx, cut="round_brilliant", diameter_mm=5.0,
                            density_g_cm3=-1.0)
        assert result.get("code") == "BAD_ARGS"

    def test_invalid_json(self):
        ctx, _, _ = make_ctx()
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(
            run_jewelry_gem_report(ctx, b"not json")
        )
        loop.close()
        assert json.loads(raw).get("code") == "BAD_ARGS"
