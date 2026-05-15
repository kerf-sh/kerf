"""
Tests for kerf_cad_core.jewelry.gem_seat.

All tests are pure-Python — no database, no OCC.
OCC-gated geometry tests are skipped cleanly when pythonOCC is absent.

Coverage:
  - seat_geometry(): dimensions, clearances, through-hole
  - seat_geometry(): total_cutter_depth_mm accumulates all layers
  - seat_geometry(): edge cases (zero clearances allowed)
  - LLM tool spec: name, required fields, cut enum
  - LLM tool runner: success path, node shape in feature doc
  - LLM tool runner: auto_cut_host_id chains a boolean cut node
  - LLM tool runner: error paths (BAD_ARGS, NOT_FOUND)
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.jewelry.gem_seat import (
    seat_geometry,
    jewelry_cut_gem_seat_spec,
    run_jewelry_cut_gem_seat,
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


def run_tool(ctx, file_id, **kwargs):
    args = {"file_id": str(file_id), **kwargs}
    loop = asyncio.new_event_loop()
    try:
        raw = loop.run_until_complete(
            run_jewelry_cut_gem_seat(ctx, json.dumps(args).encode())
        )
    finally:
        loop.close()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# seat_geometry() — pure-math tests (no OCC, no DB)
# ---------------------------------------------------------------------------

class TestSeatGeometry:
    def _props(self, cut="round_brilliant", diameter_mm=6.5):
        return gemstone_proportions(cut, diameter_mm=diameter_mm)

    def test_girdle_radius_includes_clearance(self):
        props = self._props()
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
        props = self._props()
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
        props = self._props()
        cc = 0.10
        gp = props.girdle_pct
        sa = 0.02
        cr = 0.30
        geom = seat_geometry(
            cut="round_brilliant",
            diameter_mm=props.diameter_mm,
            pavilion_angle_deg=props.pavilion_angle_deg,
            pavilion_depth_pct=props.pavilion_depth_pct,
            girdle_pct=gp,
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
        props = self._props()
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
        props = self._props()
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
        props = self._props()
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
        props = self._props()
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
        props = self._props()
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
        props = self._props()
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
# LLM tool spec
# ---------------------------------------------------------------------------

class TestJewelryCutGemSeatSpec:
    def test_name(self):
        assert jewelry_cut_gem_seat_spec.name == "jewelry_cut_gem_seat"

    def test_required_fields(self):
        req = jewelry_cut_gem_seat_spec.input_schema.get("required", [])
        assert "file_id" in req
        assert "cut" in req

    def test_cut_enum_matches_registry(self):
        props = jewelry_cut_gem_seat_spec.input_schema["properties"]
        enum = set(props["cut"].get("enum", []))
        assert enum == GEMSTONE_CUTS

    def test_optional_clearance_fields_present(self):
        props = jewelry_cut_gem_seat_spec.input_schema["properties"]
        for field in ("girdle_clearance_mm", "culet_clearance_mm",
                      "crown_relief_mm", "through_hole"):
            assert field in props


# ---------------------------------------------------------------------------
# LLM tool runner — success paths
# ---------------------------------------------------------------------------

class TestRunJewelryCutGemSeat:
    def test_basic_round_brilliant_by_carat(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant", carat=1.0)
        assert result.get("error") is None, result
        assert result["op"] == "gem_seat"
        assert result["cut"] == "round_brilliant"
        assert result["diameter_mm"] == pytest.approx(6.5, rel=1e-4)
        assert result["total_cutter_depth_mm"] > 0

    def test_node_appended_to_feature_doc(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="princess", diameter_mm=5.5)
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1
        node = doc["features"][0]
        assert node["op"] == "gem_seat"

    def test_node_id_starts_with_gem_seat(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="oval", diameter_mm=7.0)
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"].startswith("gem_seat-")

    def test_explicit_id_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="emerald", diameter_mm=7.0, id="seat-custom")
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"] == "seat-custom"

    def test_geometry_keys_stored_in_node(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        for key in ("girdle_radius_mm", "pavilion_depth_mm", "total_cutter_depth_mm"):
            assert key in node, f"Missing key: {key}"

    def test_through_hole_stored_when_true(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                 through_hole=True, through_hole_radius_mm=0.5)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["through_hole"] is True
        assert node["through_hole_radius_mm"] == pytest.approx(0.5)

    def test_position_stored_in_node(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                 position=[0.0, 0.0, 5.0])
        doc = json.loads(store["content"])
        assert doc["features"][0]["position"] == [0.0, 0.0, 5.0]

    def test_auto_cut_appends_boolean_node(self):
        """auto_cut_host_id chains a boolean cut node."""
        # Pre-populate a host node so the feature doc has content
        initial_doc = {
            "version": 1,
            "features": [{"id": "sweep1-1", "op": "sweep1",
                           "profile_sketch_path": "/p.sketch",
                           "path_sketch_path": "/r.sketch"}],
        }
        ctx, store, fid = make_ctx(json.dumps(initial_doc))
        result = run_tool(ctx, fid, cut="round_brilliant", carat=1.0,
                          auto_cut_host_id="sweep1-1")
        assert result.get("error") is None, result
        assert "seat_id" in result
        assert "boolean_id" in result

        doc = json.loads(store["content"])
        # Should have: original sweep1-1 + gem_seat + boolean
        ops = [n["op"] for n in doc["features"]]
        assert "gem_seat" in ops
        assert "boolean" in ops

        bool_node = next(n for n in doc["features"] if n["op"] == "boolean")
        assert bool_node["kind"] == "cut"
        assert bool_node["target_a_id"] == "sweep1-1"
        assert bool_node["target_b_id"] == result["seat_id"]

    @pytest.mark.parametrize("cut", list(GEMSTONE_CUTS))
    def test_all_cuts_succeed(self, cut):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, cut=cut, diameter_mm=5.0)
        assert result.get("error") is None, f"{cut}: {result}"


# ---------------------------------------------------------------------------
# LLM tool runner — error paths
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
        result = run_tool(ctx, fid, cut="kite", diameter_mm=5.0)
        assert result.get("code") == "BAD_ARGS"

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
            run_jewelry_cut_gem_seat(ctx, json.dumps({
                "file_id": "bad-uuid", "cut": "round_brilliant", "carat": 1.0
            }).encode())
        )
        loop.close()
        assert json.loads(raw).get("code") == "BAD_ARGS"

    def test_non_existent_file(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        result = run_tool(ctx, fid, cut="round_brilliant", carat=1.0)
        assert result.get("code") == "NOT_FOUND"

    def test_negative_girdle_clearance(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                          girdle_clearance_mm=-0.1)
        assert result.get("code") == "BAD_ARGS"

    def test_negative_through_hole_radius(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, cut="round_brilliant", diameter_mm=6.5,
                          through_hole=True, through_hole_radius_mm=-0.5)
        assert result.get("code") == "BAD_ARGS"
