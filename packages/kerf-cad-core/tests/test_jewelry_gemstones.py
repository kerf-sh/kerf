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
    carat_from_mm,
    mm_from_carat,
    gemstone_proportions,
    jewelry_create_gemstone_spec,
    run_jewelry_create_gemstone,
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


# ---------------------------------------------------------------------------
# GEMSTONE_CUTS registry
# ---------------------------------------------------------------------------

class TestGemstoneCutsRegistry:
    EXPECTED = {
        "round_brilliant", "princess", "oval", "emerald",
        "marquise", "pear", "cushion",
    }

    def test_all_expected_cuts_present(self):
        assert self.EXPECTED <= GEMSTONE_CUTS

    def test_no_unknown_cuts(self):
        # All values in registry must be strings
        for cut in GEMSTONE_CUTS:
            assert isinstance(cut, str)

    def test_count(self):
        assert len(GEMSTONE_CUTS) >= 7


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
            carat_from_mm("kite", 5.0)

    def test_unknown_cut_mm_from_carat_raises(self):
        with pytest.raises(ValueError):
            mm_from_carat("kite", 1.0)


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
        assert 0 < props.table_pct < 100
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
            gemstone_proportions("kite", diameter_mm=5.0)

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
        result = run_tool(ctx, fid, cut="kite", diameter_mm=5.0)
        assert result.get("code") == "BAD_ARGS"
        assert "kite" in result.get("error", "")

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
