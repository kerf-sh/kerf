"""
Tests for kerf_cad_core.jewelry.chain

Pure-Python section (always runs):
  - compute_chain_params: all link styles, length sources, validation
  - compute_clasp_params: all clasp styles, validation
  - chain_length_to_link_count / link_count_to_chain_length round-trips
  - standard_length_names: sanity
  - LLM tool specs: names, required fields, enums
  - LLM tool runner jewelry_create_chain: success paths, node shape, error paths
  - LLM tool runner jewelry_chain_length: success paths, error paths
  - v2 link styles: rolo, bismark, wheat, herringbone, omega, popcorn, ball, singapore
  - v2 sizing: anklet, men's, choker standard lengths
  - gauge_preset table
  - chain_weight_estimate: sane values, formula, validation
  - graduated flag
  - aliases: belcher, spiga, bead, bead_chain

OCC-gated section:
  - Skipped cleanly when pythonOCC absent.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.jewelry.chain import (
    _VALID_LINK_STYLES,
    _VALID_CLASP_STYLES,
    _STANDARD_LENGTHS_MM,
    _STYLE_ALIASES,
    GAUGE_PRESETS,
    compute_chain_params,
    compute_clasp_params,
    chain_length_to_link_count,
    chain_weight_estimate,
    link_count_to_chain_length,
    link_pitch,
    standard_length_names,
    jewelry_create_chain_spec,
    jewelry_chain_length_spec,
    run_jewelry_create_chain,
    run_jewelry_chain_length,
    # v3 composed pieces
    tennis_bracelet_spec,
    station_necklace_spec,
    lariat_spec,
    charm_bracelet_spec,
    multi_strand_spec,
    extender_chain_spec,
    run_jewelry_create_tennis_bracelet,
    run_jewelry_create_station_necklace,
    run_jewelry_create_lariat,
    run_jewelry_create_charm_bracelet,
    run_jewelry_create_multi_strand,
    run_jewelry_create_extender_chain,
    _tennis_bracelet_spec_obj,
    _station_necklace_spec_obj,
    _lariat_spec_obj,
    _charm_bracelet_spec_obj,
    _multi_strand_spec_obj,
    _extender_chain_spec_obj,
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


def run_create(ctx, file_id, **kwargs):
    args = {"file_id": str(file_id), **kwargs}
    return run_sync(run_jewelry_create_chain(ctx, json.dumps(args).encode()))


def run_length(**kwargs):
    ctx, _, _ = make_ctx()
    return run_sync(run_jewelry_chain_length(ctx, json.dumps(kwargs).encode()))


# ---------------------------------------------------------------------------
# compute_chain_params — basic per-style smoke tests
# ---------------------------------------------------------------------------

class TestComputeChainParamsStyles:
    """Every link style should produce a valid spec from minimal inputs."""

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_style_link_count(self, style):
        p = compute_chain_params(style, wire_gauge_mm=1.0, link_count=100)
        assert p["style"] == style
        assert p["link_count"] == 100
        assert p["link_length_mm"] > 0
        assert p["link_width_mm"] > 0
        assert p["link_pitch_mm"] > 0
        assert p["total_length_mm"] > 0
        assert p["wire_gauge_mm"] == pytest.approx(1.0)
        assert "link_hints" in p
        assert p["open_ends"] is True

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_style_total_length(self, style):
        p = compute_chain_params(style, wire_gauge_mm=1.2, total_length_mm=450.0)
        assert p["link_count"] >= 1
        # Actual length should be within one pitch of the target
        assert abs(p["total_length_mm"] - p["link_count"] * p["link_pitch_mm"]) < 1e-3

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_style_standard_length(self, style):
        p = compute_chain_params(
            style, wire_gauge_mm=1.0, standard_length="bracelet_7in"
        )
        assert p["link_count"] >= 1
        assert p["total_length_mm"] > 0

    def test_link_hints_type_key(self):
        """Each style's link_hints dict should have a 'type' key."""
        for style in _VALID_LINK_STYLES:
            p = compute_chain_params(style, wire_gauge_mm=1.0, link_count=10)
            hints = p["link_hints"]
            assert "type" in hints, f"Style {style!r}: missing 'type' in link_hints"


class TestComputeChainParamsLinkDimDefaults:
    def test_cable_defaults_reasonable(self):
        p = compute_chain_params("cable", wire_gauge_mm=1.0, link_count=50)
        # Default multiplier: length 3.5×, width 2.5×
        assert abs(p["link_length_mm"] - 3.5) < 0.01
        assert abs(p["link_width_mm"] - 2.5) < 0.01

    def test_explicit_link_dims_used(self):
        p = compute_chain_params(
            "cable", wire_gauge_mm=1.0,
            link_length_mm=5.0, link_width_mm=3.0,
            link_count=50
        )
        assert p["link_length_mm"] == pytest.approx(5.0)
        assert p["link_width_mm"] == pytest.approx(3.0)


class TestComputeChainParamsCurbVariants:
    def test_curb_diamond_cut_hint(self):
        p = compute_chain_params(
            "curb", wire_gauge_mm=1.2, link_count=60, diamond_cut=True
        )
        assert p["link_hints"]["diamond_cut"] is True
        assert p["link_hints"]["diamond_facets"] == 4

    def test_curb_flat_hint(self):
        p = compute_chain_params(
            "curb", wire_gauge_mm=1.2, link_count=60, flat=True
        )
        assert p["link_hints"]["flat_face"] is True
        assert p["link_hints"]["flat_ratio"] == pytest.approx(0.6)

    def test_alias_anchor_normalises_to_mariner(self):
        p = compute_chain_params("anchor", wire_gauge_mm=1.5, link_count=30)
        assert p["style"] == "mariner"


class TestComputeChainParamsFigaro:
    def test_figaro_long_link_ratio_stored(self):
        p = compute_chain_params(
            "figaro", wire_gauge_mm=1.0, link_count=40, long_link_ratio=3.0
        )
        hints = p["link_hints"]
        assert hints["type"] == "figaro"
        assert hints["long_link_length_mm"] == pytest.approx(
            p["link_length_mm"] * 3.0, rel=1e-3
        )


class TestComputeChainParamsRope:
    def test_rope_twist_angle_stored(self):
        p = compute_chain_params(
            "rope", wire_gauge_mm=0.8, link_count=200, twist_angle_deg=60.0
        )
        assert p["link_hints"]["twist_angle_deg"] == pytest.approx(60.0)


class TestComputeChainParamsValidation:
    def test_unknown_style_raises(self):
        with pytest.raises(ValueError, match="Unknown chain style"):
            compute_chain_params("curly", wire_gauge_mm=1.0, link_count=10)

    def test_zero_gauge_raises(self):
        with pytest.raises(ValueError, match="wire_gauge_mm must be > 0"):
            compute_chain_params("cable", wire_gauge_mm=0, link_count=10)

    def test_negative_gauge_raises(self):
        with pytest.raises(ValueError, match="wire_gauge_mm must be > 0"):
            compute_chain_params("cable", wire_gauge_mm=-1.0, link_count=10)

    def test_unrealistic_gauge_raises(self):
        with pytest.raises(ValueError, match="unrealistically large"):
            compute_chain_params("cable", wire_gauge_mm=25.0, link_count=10)

    def test_zero_link_length_raises(self):
        with pytest.raises(ValueError, match="link_length_mm must be > 0"):
            compute_chain_params(
                "cable", wire_gauge_mm=1.0, link_length_mm=0, link_count=10
            )

    def test_link_length_less_than_gauge_raises(self):
        with pytest.raises(ValueError, match="link_length_mm"):
            compute_chain_params(
                "cable", wire_gauge_mm=2.0, link_length_mm=1.0, link_count=10
            )

    def test_no_length_source_raises(self):
        with pytest.raises(ValueError, match="One of link_count"):
            compute_chain_params("cable", wire_gauge_mm=1.0)

    def test_two_length_sources_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            compute_chain_params(
                "cable", wire_gauge_mm=1.0,
                link_count=10, total_length_mm=200.0
            )

    def test_all_three_length_sources_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            compute_chain_params(
                "cable", wire_gauge_mm=1.0,
                link_count=10, total_length_mm=200.0, standard_length="bracelet_7in"
            )

    def test_zero_total_length_raises(self):
        with pytest.raises(ValueError, match="total_length_mm must be > 0"):
            compute_chain_params("cable", wire_gauge_mm=1.0, total_length_mm=0)

    def test_zero_link_count_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            compute_chain_params("cable", wire_gauge_mm=1.0, link_count=0)

    def test_unknown_standard_length_raises(self):
        with pytest.raises(ValueError, match="Unknown standard_length"):
            compute_chain_params("cable", wire_gauge_mm=1.0, standard_length="necklace_99in")

    def test_alias_accepted(self):
        """'anchor' is an alias for 'mariner' and must not raise."""
        p = compute_chain_params("anchor", wire_gauge_mm=1.0, link_count=10)
        assert p["style"] == "mariner"


# ---------------------------------------------------------------------------
# compute_clasp_params
# ---------------------------------------------------------------------------

class TestComputeClaspParams:
    @pytest.mark.parametrize("style", sorted(_VALID_CLASP_STYLES))
    def test_all_clasps_produce_valid_spec(self, style):
        p = compute_clasp_params(style, wire_gauge_mm=1.0)
        assert p["op"] == "clasp"
        assert p["style"] == style
        assert p["wire_gauge_mm"] == pytest.approx(1.0)
        assert "clasp_hints" in p
        assert p["clasp_hints"]["type"] == style

    def test_lobster_clasp_body_dims(self):
        p = compute_clasp_params("lobster", wire_gauge_mm=1.0)
        hints = p["clasp_hints"]
        assert hints["body_length_mm"] > 0
        assert hints["body_width_mm"] > 0

    def test_spring_ring_outer_gt_inner(self):
        p = compute_clasp_params("spring_ring", wire_gauge_mm=1.0)
        hints = p["clasp_hints"]
        assert hints["outer_diameter_mm"] > hints["inner_diameter_mm"]

    def test_toggle_bar_longer_than_ring_id(self):
        p = compute_clasp_params("toggle", wire_gauge_mm=1.0)
        hints = p["clasp_hints"]
        assert hints["bar_length_mm"] > hints["ring_inner_diameter_mm"]

    def test_box_clasp_all_dims_positive(self):
        p = compute_clasp_params("box_clasp", wire_gauge_mm=1.0)
        hints = p["clasp_hints"]
        assert hints["box_length_mm"] > 0
        assert hints["box_width_mm"] > 0
        assert hints["box_height_mm"] > 0

    def test_unknown_clasp_raises(self):
        with pytest.raises(ValueError, match="Unknown clasp style"):
            compute_clasp_params("hook", wire_gauge_mm=1.0)

    def test_zero_gauge_raises(self):
        with pytest.raises(ValueError, match="wire_gauge_mm must be > 0"):
            compute_clasp_params("lobster", wire_gauge_mm=0)


# ---------------------------------------------------------------------------
# Length ↔ link-count round-trips
# ---------------------------------------------------------------------------

class TestLengthLinkCountRoundTrip:
    """Round-trip: length → count → length should recover within one pitch."""

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_round_trip_via_total_length(self, style):
        gauge = 1.0
        target_mm = 450.0
        p = compute_chain_params(style, wire_gauge_mm=gauge, total_length_mm=target_mm)
        pitch = p["link_pitch_mm"]
        # Recover length from link_count
        back_mm = link_count_to_chain_length(p["link_count"], pitch)
        # Should be within one pitch of the target
        assert abs(back_mm - target_mm) <= pitch + 1e-6, (
            f"style={style}: target={target_mm}, back={back_mm}, pitch={pitch}"
        )

    def test_direct_to_count(self):
        count = chain_length_to_link_count(total_length_mm=180.0, link_pitch_mm=3.0)
        assert count == 60

    def test_direct_to_length(self):
        length = link_count_to_chain_length(link_count=60, link_pitch_mm=3.0)
        assert length == pytest.approx(180.0)

    def test_round_trip_exact(self):
        pitch = 2.5
        n = 72
        length = link_count_to_chain_length(n, pitch)
        back_n = chain_length_to_link_count(length, pitch)
        assert back_n == n

    def test_chain_length_to_link_count_zero_length_raises(self):
        with pytest.raises(ValueError, match="total_length_mm must be > 0"):
            chain_length_to_link_count(0.0, 3.0)

    def test_chain_length_to_link_count_zero_pitch_raises(self):
        with pytest.raises(ValueError, match="link_pitch_mm must be > 0"):
            chain_length_to_link_count(180.0, 0.0)

    def test_link_count_to_chain_length_zero_count_raises(self):
        with pytest.raises(ValueError, match="link_count must be >= 1"):
            link_count_to_chain_length(0, 3.0)

    def test_link_count_to_chain_length_zero_pitch_raises(self):
        with pytest.raises(ValueError, match="link_pitch_mm must be > 0"):
            link_count_to_chain_length(10, 0.0)

    def test_minimum_count_is_one(self):
        """Very short total length should still yield at least 1 link."""
        count = chain_length_to_link_count(0.1, 100.0)
        assert count == 1


class TestStandardLengths:
    def test_bracelet_7in_is_177_8mm(self):
        assert _STANDARD_LENGTHS_MM["bracelet_7in"] == pytest.approx(177.8)

    def test_princess_18in_is_457_2mm(self):
        assert _STANDARD_LENGTHS_MM["princess_18in"] == pytest.approx(457.2)

    def test_bracelet_18cm_is_180mm(self):
        assert _STANDARD_LENGTHS_MM["bracelet_18cm"] == pytest.approx(180.0)

    def test_standard_length_names_sorted(self):
        names = standard_length_names()
        assert names == sorted(names)

    def test_all_standard_lengths_positive(self):
        for name, mm in _STANDARD_LENGTHS_MM.items():
            assert mm > 0, f"Standard length {name!r} = {mm} is not positive"


# ---------------------------------------------------------------------------
# link_pitch — per-style sanity checks
# ---------------------------------------------------------------------------

class TestLinkPitch:
    def test_cable_pitch_positive(self):
        p = link_pitch("cable", 3.5, 2.5, 1.0)
        assert p > 0

    def test_box_pitch_half_link_length(self):
        # Box pitch = max(link_length/2, wire_gauge*1.1)
        # With link_length=4.0, gauge=1.0: max(2.0, 1.1) = 2.0
        p = link_pitch("box", 4.0, 2.0, 1.0)
        assert p == pytest.approx(2.0)

    def test_pitch_never_less_than_gauge(self):
        for style in _VALID_LINK_STYLES:
            gauge = 1.0
            llen = gauge * 3.5
            lwid = gauge * 2.5
            p = link_pitch(style, llen, lwid, gauge)
            assert p >= gauge * 1.0, (
                f"style={style}: pitch={p} < gauge × 1.0"
            )


# ---------------------------------------------------------------------------
# ToolSpec declarations
# ---------------------------------------------------------------------------

class TestToolSpecs:
    def test_create_chain_spec_name(self):
        assert jewelry_create_chain_spec.name == "jewelry_create_chain"

    def test_create_chain_required_fields(self):
        req = set(jewelry_create_chain_spec.input_schema["required"])
        assert "file_id" in req
        assert "style" in req
        assert "wire_gauge_mm" in req

    def test_create_chain_style_enum_complete(self):
        props = jewelry_create_chain_spec.input_schema["properties"]
        assert set(props["style"]["enum"]) == _VALID_LINK_STYLES

    def test_create_chain_clasp_style_enum_complete(self):
        props = jewelry_create_chain_spec.input_schema["properties"]
        assert set(props["clasp_style"]["enum"]) == _VALID_CLASP_STYLES

    def test_chain_length_spec_name(self):
        assert jewelry_chain_length_spec.name == "jewelry_chain_length"

    def test_chain_length_required_fields(self):
        req = set(jewelry_chain_length_spec.input_schema["required"])
        assert "style" in req
        assert "wire_gauge_mm" in req

    def test_chain_length_style_enum_complete(self):
        props = jewelry_chain_length_spec.input_schema["properties"]
        assert set(props["style"]["enum"]) == _VALID_LINK_STYLES


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_chain — success paths
# ---------------------------------------------------------------------------

class TestCreateChainTool:
    def test_cable_bracelet_7in(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0,
                       standard_length="bracelet_7in")
        assert "error" not in r, r
        assert r["op"] == "chain_assembly"
        assert r["style"] == "cable"
        assert r["link_count"] >= 1
        assert r["total_length_mm"] > 0

    def test_node_appended_to_feature_doc(self):
        ctx, store, fid = make_ctx()
        run_create(ctx, fid, style="curb", wire_gauge_mm=1.2, link_count=60)
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1
        node = doc["features"][0]
        assert node["op"] == "chain_assembly"
        assert node["style"] == "curb"

    def test_node_id_starts_with_chain_assembly(self):
        ctx, store, fid = make_ctx()
        run_create(ctx, fid, style="box", wire_gauge_mm=1.5, link_count=50)
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"].startswith("chain_assembly-")

    def test_explicit_node_id(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="rope", wire_gauge_mm=0.8,
                       link_count=200, id="my-chain-1")
        assert "error" not in r
        assert r["id"] == "my-chain-1"

    def test_second_node_increments_id(self):
        ctx, store, fid = make_ctx()
        run_create(ctx, fid, style="cable", wire_gauge_mm=1.0, link_count=50)
        r2 = run_create(ctx, fid, style="mariner", wire_gauge_mm=1.0, link_count=30)
        assert "error" not in r2
        assert r2["id"] == "chain_assembly-2"

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_all_styles_succeed(self, style):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style=style, wire_gauge_mm=1.0, link_count=50)
        assert "error" not in r, f"style={style!r}: {r}"

    def test_with_clasp_inline(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0,
                       standard_length="bracelet_7in", clasp_style="lobster")
        assert "error" not in r, r
        assert r["clasp"] == "lobster"
        doc = json.loads(store["content"])
        node = doc["features"][0]
        clasp = node.get("clasp")
        assert clasp is not None
        assert clasp["style"] == "lobster"
        assert clasp["op"] == "clasp"
        assert "clasp_hints" in clasp

    @pytest.mark.parametrize("clasp", sorted(_VALID_CLASP_STYLES))
    def test_all_clasps_inline(self, clasp):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0,
                       link_count=60, clasp_style=clasp)
        assert "error" not in r, f"clasp={clasp!r}: {r}"
        assert r["clasp"] == clasp

    def test_no_clasp_null_in_node(self):
        ctx, store, fid = make_ctx()
        run_create(ctx, fid, style="cable", wire_gauge_mm=1.0, link_count=50)
        doc = json.loads(store["content"])
        assert doc["features"][0]["clasp"] is None

    def test_total_length_mm_used(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="figaro", wire_gauge_mm=1.0,
                       total_length_mm=180.0)
        assert "error" not in r
        assert r["link_count"] >= 1

    def test_diamond_cut_curb(self):
        ctx, store, fid = make_ctx()
        run_create(ctx, fid, style="curb", wire_gauge_mm=1.3,
                   link_count=60, diamond_cut=True)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["link_hints"]["diamond_cut"] is True

    def test_alias_anchor_stored_as_mariner(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="anchor", wire_gauge_mm=1.5, link_count=30)
        assert "error" not in r
        doc = json.loads(store["content"])
        assert doc["features"][0]["style"] == "mariner"

    def test_node_contains_all_spec_keys(self):
        ctx, store, fid = make_ctx()
        run_create(ctx, fid, style="byzantine", wire_gauge_mm=1.0, link_count=40)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        for key in ("op", "style", "wire_gauge_mm", "link_length_mm",
                    "link_width_mm", "link_count", "link_hints",
                    "total_length_mm", "link_pitch_mm", "open_ends", "clasp"):
            assert key in node, f"Missing key {key!r} in chain_assembly node"


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_chain — error paths
# ---------------------------------------------------------------------------

class TestCreateChainToolErrors:
    def test_missing_file_id(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_chain(
            ctx, json.dumps({"style": "cable", "wire_gauge_mm": 1.0,
                             "link_count": 50}).encode()
        ))
        assert "error" in r

    def test_missing_style(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, wire_gauge_mm=1.0, link_count=50)
        assert "error" in r

    def test_missing_wire_gauge(self):
        ctx, _, fid = make_ctx()
        r = run_sync(run_jewelry_create_chain(
            ctx, json.dumps({"file_id": str(fid), "style": "cable",
                             "link_count": 50}).encode()
        ))
        assert "error" in r

    def test_invalid_style(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, style="chain_mail", wire_gauge_mm=1.0, link_count=50)
        assert "error" in r

    def test_invalid_clasp_style(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0,
                       link_count=50, clasp_style="hook_and_eye")
        assert "error" in r

    def test_no_length_source(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0)
        assert "error" in r

    def test_two_length_sources(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0,
                       link_count=50, total_length_mm=200.0)
        assert "error" in r

    def test_invalid_file_id_uuid(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_chain(
            ctx, json.dumps({"file_id": "not-a-uuid", "style": "cable",
                             "wire_gauge_mm": 1.0, "link_count": 50}).encode()
        ))
        assert "error" in r

    def test_file_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0, link_count=50)
        assert "error" in r

    def test_zero_wire_gauge(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=0, link_count=50)
        assert "error" in r

    def test_negative_wire_gauge(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=-1.0, link_count=50)
        assert "error" in r

    def test_invalid_json(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_chain(ctx, b"not json!"))
        assert "error" in r

    def test_zero_link_count(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0, link_count=0)
        assert "error" in r

    def test_zero_total_length(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0, total_length_mm=0)
        assert "error" in r

    def test_unknown_standard_length(self):
        ctx, _, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0,
                       standard_length="necklace_99in")
        assert "error" in r


# ---------------------------------------------------------------------------
# LLM tool: jewelry_chain_length — success paths
# ---------------------------------------------------------------------------

class TestChainLengthTool:
    def test_standard_length_to_link_count(self):
        r = run_length(style="cable", wire_gauge_mm=1.0,
                       standard_length="bracelet_7in")
        assert "error" not in r, r
        assert r["link_count"] >= 1
        assert r["actual_total_length_mm"] > 0
        assert r["standard_length"] == "bracelet_7in"

    def test_total_length_to_link_count(self):
        r = run_length(style="curb", wire_gauge_mm=1.2, total_length_mm=457.2)
        assert "error" not in r, r
        assert r["link_count"] >= 1

    def test_link_count_to_length(self):
        r = run_length(style="box", wire_gauge_mm=1.5, link_count=100)
        assert "error" not in r, r
        assert r["total_length_mm"] > 0
        assert r["link_pitch_mm"] > 0

    def test_round_trip_via_tool(self):
        """length → count → length round-trip via the tool."""
        r1 = run_length(style="cable", wire_gauge_mm=1.0,
                        total_length_mm=180.0)
        assert "error" not in r1
        pitch = r1["link_pitch_mm"]
        count = r1["link_count"]
        r2 = run_length(style="cable", wire_gauge_mm=1.0,
                        link_count=count)
        assert "error" not in r2
        # Actual length should be within one pitch of target
        assert abs(r2["total_length_mm"] - 180.0) <= pitch + 1e-6


# ---------------------------------------------------------------------------
# LLM tool: jewelry_chain_length — error paths
# ---------------------------------------------------------------------------

class TestChainLengthToolErrors:
    def test_missing_style(self):
        r = run_length(wire_gauge_mm=1.0, link_count=50)
        assert "error" in r

    def test_missing_wire_gauge(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_chain_length(
            ctx, json.dumps({"style": "cable", "link_count": 50}).encode()
        ))
        assert "error" in r

    def test_invalid_style(self):
        r = run_length(style="chain_mail", wire_gauge_mm=1.0, link_count=50)
        assert "error" in r

    def test_no_length_source(self):
        r = run_length(style="cable", wire_gauge_mm=1.0)
        assert "error" in r

    def test_two_length_sources(self):
        r = run_length(style="cable", wire_gauge_mm=1.0,
                       link_count=50, total_length_mm=200.0)
        assert "error" in r

    def test_zero_wire_gauge(self):
        r = run_length(style="cable", wire_gauge_mm=0, link_count=50)
        assert "error" in r

    def test_negative_total_length(self):
        r = run_length(style="cable", wire_gauge_mm=1.0, total_length_mm=-10.0)
        assert "error" in r

    def test_zero_link_count(self):
        r = run_length(style="cable", wire_gauge_mm=1.0, link_count=0)
        assert "error" in r

    def test_unknown_standard_length(self):
        r = run_length(style="cable", wire_gauge_mm=1.0,
                       standard_length="necklace_99in")
        assert "error" in r

    def test_invalid_json(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_chain_length(ctx, b"bad json"))
        assert "error" in r


# ---------------------------------------------------------------------------
# v2: New link styles
# ---------------------------------------------------------------------------

_NEW_STYLES = [
    "rolo", "bismark", "wheat", "herringbone",
    "omega", "popcorn", "ball", "singapore",
]


class TestNewLinkStyles:
    """Each new style must produce a valid chain spec with correct link_hints."""

    @pytest.mark.parametrize("style", _NEW_STYLES)
    def test_style_produces_spec(self, style):
        p = compute_chain_params(style, wire_gauge_mm=1.0, link_count=50)
        assert p["style"] == style
        assert p["link_count"] == 50
        assert p["link_length_mm"] > 0
        assert p["link_width_mm"] > 0
        assert p["link_pitch_mm"] > 0
        assert p["total_length_mm"] > 0
        assert "link_hints" in p

    @pytest.mark.parametrize("style", _NEW_STYLES)
    def test_link_hints_has_type_key(self, style):
        p = compute_chain_params(style, wire_gauge_mm=1.0, link_count=10)
        assert p["link_hints"]["type"] == style, (
            f"style={style!r}: link_hints['type'] expected {style!r}, "
            f"got {p['link_hints'].get('type')!r}"
        )

    @pytest.mark.parametrize("style", _NEW_STYLES)
    def test_style_total_length(self, style):
        p = compute_chain_params(style, wire_gauge_mm=1.2, total_length_mm=450.0)
        assert p["link_count"] >= 1
        assert abs(p["total_length_mm"] - p["link_count"] * p["link_pitch_mm"]) < 1e-3

    @pytest.mark.parametrize("style", _NEW_STYLES)
    def test_pitch_positive(self, style):
        p = compute_chain_params(style, wire_gauge_mm=1.0, link_count=30)
        assert p["link_pitch_mm"] > 0

    def test_rolo_has_inner_diameter(self):
        p = compute_chain_params("rolo", wire_gauge_mm=1.5, link_count=40)
        h = p["link_hints"]
        assert "inner_diameter_mm" in h
        assert h["inner_diameter_mm"] > 0

    def test_rolo_alternating_rotation(self):
        p = compute_chain_params("rolo", wire_gauge_mm=1.0, link_count=40)
        h = p["link_hints"]
        assert h["alternating_rotation_deg"] == 90

    def test_bismark_rows_default(self):
        p = compute_chain_params("bismark", wire_gauge_mm=1.0, link_count=40)
        h = p["link_hints"]
        assert h["rows"] == 2

    def test_bismark_rows_custom(self):
        p = compute_chain_params("bismark", wire_gauge_mm=1.0, link_count=40, rows=3)
        h = p["link_hints"]
        assert h["rows"] == 3

    def test_wheat_helix_radius_mult(self):
        p = compute_chain_params("wheat", wire_gauge_mm=1.0, link_count=50)
        h = p["link_hints"]
        assert "helix_radius_mult" in h
        assert h["helix_radius_mult"] > 0

    def test_herringbone_layer_count(self):
        p = compute_chain_params("herringbone", wire_gauge_mm=1.0, link_count=30)
        h = p["link_hints"]
        assert h["layer_count"] == 2
        assert h["surface_width_mm"] > 0

    def test_omega_plate_width_wider_than_gauge(self):
        p = compute_chain_params("omega", wire_gauge_mm=1.0, link_count=40)
        h = p["link_hints"]
        assert h["plate_width_mm"] > 1.0   # wider than wire gauge
        assert h["plate_curvature"] == "convex"

    def test_popcorn_sphere_diameter_positive(self):
        p = compute_chain_params("popcorn", wire_gauge_mm=1.5, link_count=30)
        h = p["link_hints"]
        assert h["sphere_diameter_mm"] > 0
        assert h["neck_diameter_mm"] > 0

    def test_ball_bead_diameter_positive(self):
        p = compute_chain_params("ball", wire_gauge_mm=1.5, link_count=30)
        h = p["link_hints"]
        assert h["bead_diameter_mm"] > 0
        assert h["neck_diameter_mm"] > 0
        assert h["neck_length_mm"] > 0

    def test_singapore_has_twist(self):
        p = compute_chain_params("singapore", wire_gauge_mm=1.0, link_count=50)
        h = p["link_hints"]
        assert h["twist_deg"] == 90
        assert "diagonal_angle_deg" in h

    def test_new_styles_in_valid_set(self):
        for s in _NEW_STYLES:
            assert s in _VALID_LINK_STYLES


# ---------------------------------------------------------------------------
# v2: Style aliases (new)
# ---------------------------------------------------------------------------

class TestNewStyleAliases:
    def test_belcher_resolves_to_rolo(self):
        p = compute_chain_params("belcher", wire_gauge_mm=1.0, link_count=20)
        assert p["style"] == "rolo"

    def test_spiga_resolves_to_wheat(self):
        p = compute_chain_params("spiga", wire_gauge_mm=1.0, link_count=20)
        assert p["style"] == "wheat"

    def test_bead_resolves_to_ball(self):
        p = compute_chain_params("bead", wire_gauge_mm=1.0, link_count=20)
        assert p["style"] == "ball"

    def test_bead_chain_resolves_to_ball(self):
        p = compute_chain_params("bead_chain", wire_gauge_mm=1.0, link_count=20)
        assert p["style"] == "ball"


# ---------------------------------------------------------------------------
# v2: Pitch round-trips for new styles
# ---------------------------------------------------------------------------

class TestNewStylePitchRoundTrip:
    @pytest.mark.parametrize("style", _NEW_STYLES)
    def test_round_trip_new_style(self, style):
        gauge = 1.0
        target_mm = 450.0
        p = compute_chain_params(style, wire_gauge_mm=gauge, total_length_mm=target_mm)
        pitch = p["link_pitch_mm"]
        back_mm = link_count_to_chain_length(p["link_count"], pitch)
        assert abs(back_mm - target_mm) <= pitch + 1e-6, (
            f"style={style}: target={target_mm}, back={back_mm}, pitch={pitch}"
        )


# ---------------------------------------------------------------------------
# v2: Sizing — anklet, men's, choker standard lengths
# ---------------------------------------------------------------------------

class TestV2StandardLengths:
    def test_anklet_9in(self):
        assert _STANDARD_LENGTHS_MM["anklet_9in"] == pytest.approx(228.6)

    def test_anklet_10in(self):
        assert _STANDARD_LENGTHS_MM["anklet_10in"] == pytest.approx(254.0)

    def test_anklet_11in(self):
        assert _STANDARD_LENGTHS_MM["anklet_11in"] == pytest.approx(279.4)

    def test_mens_24in(self):
        assert _STANDARD_LENGTHS_MM["mens_24in"] == pytest.approx(609.6)

    def test_mens_30in(self):
        assert _STANDARD_LENGTHS_MM["mens_30in"] == pytest.approx(762.0)

    def test_choker_14in(self):
        assert _STANDARD_LENGTHS_MM["choker_14in"] == pytest.approx(355.6)

    def test_choker_16in(self):
        assert _STANDARD_LENGTHS_MM["choker_16in"] == pytest.approx(406.4)

    def test_necklace_55cm(self):
        assert _STANDARD_LENGTHS_MM["necklace_55cm"] == pytest.approx(550.0)

    def test_necklace_70cm(self):
        assert _STANDARD_LENGTHS_MM["necklace_70cm"] == pytest.approx(700.0)

    def test_all_anklets_in_range(self):
        anklets = {k: v for k, v in _STANDARD_LENGTHS_MM.items()
                   if k.startswith("anklet_")}
        assert len(anklets) >= 5
        for name, mm in anklets.items():
            assert 220 <= mm <= 300, f"{name}: {mm} mm out of anklet range"

    def test_all_mens_lengths_ge_508mm(self):
        mens = {k: v for k, v in _STANDARD_LENGTHS_MM.items()
                if k.startswith("mens_")}
        assert len(mens) >= 6
        for name, mm in mens.items():
            assert mm >= 508.0, f"{name}: {mm} mm is shorter than 20in"

    def test_all_standard_lengths_positive(self):
        for name, mm in _STANDARD_LENGTHS_MM.items():
            assert mm > 0, f"Standard length {name!r} = {mm} is not positive"

    def test_standard_length_names_sorted(self):
        names = standard_length_names()
        assert names == sorted(names)

    @pytest.mark.parametrize("std_len", ["anklet_9in", "anklet_10in", "mens_24in",
                                          "choker_14in", "necklace_70cm"])
    def test_new_standard_lengths_work_with_compute(self, std_len):
        p = compute_chain_params("cable", wire_gauge_mm=1.0,
                                 standard_length=std_len)
        assert p["link_count"] >= 1
        assert p["total_length_mm"] > 0


# ---------------------------------------------------------------------------
# v2: Gauge presets
# ---------------------------------------------------------------------------

class TestGaugePresets:
    def test_all_styles_have_presets(self):
        for style in _VALID_LINK_STYLES:
            assert style in GAUGE_PRESETS, f"Style {style!r} missing from GAUGE_PRESETS"
            p = GAUGE_PRESETS[style]
            assert "fine" in p
            assert "medium" in p
            assert "heavy" in p

    def test_fine_lt_medium_lt_heavy(self):
        for style, p in GAUGE_PRESETS.items():
            assert p["fine"] < p["medium"], (
                f"{style}: fine ({p['fine']}) >= medium ({p['medium']})"
            )
            assert p["medium"] < p["heavy"], (
                f"{style}: medium ({p['medium']}) >= heavy ({p['heavy']})"
            )

    def test_all_preset_gauges_positive(self):
        for style, p in GAUGE_PRESETS.items():
            for weight, mm in p.items():
                assert mm > 0, f"{style}/{weight}: gauge {mm} is not positive"

    def test_gauge_preset_overrides_wire_gauge(self):
        # With gauge_preset='medium' for cable, wire_gauge should be 1.0
        p = compute_chain_params("cable", wire_gauge_mm=99.0,
                                 gauge_preset="medium", link_count=50)
        assert p["wire_gauge_mm"] == pytest.approx(GAUGE_PRESETS["cable"]["medium"])

    def test_gauge_preset_fine(self):
        p = compute_chain_params("rope", wire_gauge_mm=1.0,
                                 gauge_preset="fine", link_count=100)
        assert p["wire_gauge_mm"] == pytest.approx(GAUGE_PRESETS["rope"]["fine"])

    def test_gauge_preset_heavy(self):
        p = compute_chain_params("mariner", wire_gauge_mm=1.0,
                                 gauge_preset="heavy", link_count=30)
        assert p["wire_gauge_mm"] == pytest.approx(GAUGE_PRESETS["mariner"]["heavy"])

    def test_invalid_gauge_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown gauge_preset"):
            compute_chain_params("cable", wire_gauge_mm=1.0,
                                 gauge_preset="extra_heavy", link_count=10)

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_all_styles_accept_gauge_preset(self, style):
        p = compute_chain_params(style, wire_gauge_mm=1.0,
                                 gauge_preset="medium", link_count=30)
        assert p["wire_gauge_mm"] == pytest.approx(GAUGE_PRESETS[style]["medium"])


# ---------------------------------------------------------------------------
# v2: chain_weight_estimate
# ---------------------------------------------------------------------------

class TestChainWeightEstimate:
    # 18-karat yellow gold density ≈ 15.5 g/cm³ (industry standard)
    GOLD_18K = 15.5
    # Sterling silver ≈ 10.3 g/cm³
    SILVER_925 = 10.3

    def test_cable_bracelet_weight_positive(self):
        w = chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                  total_length_mm=177.8,
                                  density_g_per_cm3=self.GOLD_18K)
        assert w > 0

    def test_weight_scales_with_length(self):
        w1 = chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                   total_length_mm=177.8,
                                   density_g_per_cm3=self.GOLD_18K)
        w2 = chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                   total_length_mm=355.6,
                                   density_g_per_cm3=self.GOLD_18K)
        assert abs(w2 - 2 * w1) < 0.01  # doubling length doubles weight

    def test_weight_scales_with_density(self):
        w_gold = chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                       total_length_mm=450.0,
                                       density_g_per_cm3=self.GOLD_18K)
        w_silver = chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                          total_length_mm=450.0,
                                          density_g_per_cm3=self.SILVER_925)
        # Gold is heavier than silver → gold weight should exceed silver weight
        assert w_gold > w_silver
        # Ratio should match density ratio within rounding
        assert abs(w_gold / w_silver - self.GOLD_18K / self.SILVER_925) < 0.01

    def test_formula_manual_check(self):
        """Manual: cable fill=0.55, gauge=1.0, length=100, density=1.0 g/cm³.

        The return value is rounded to 3 decimal places, so tolerance is 0.001.
        """
        import math as _math
        gauge = 1.0
        fill = 0.55
        length = 100.0
        density = 1.0
        expected = _math.pi * (gauge / 2) ** 2 * fill * length * density * 1e-3
        w = chain_weight_estimate("cable", wire_gauge_mm=gauge,
                                   total_length_mm=length,
                                   density_g_per_cm3=density)
        # Result is rounded to 3 dp so max rounding error is 0.0005
        assert abs(w - expected) < 0.001

    def test_fill_factor_override(self):
        w_default = chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                           total_length_mm=200.0,
                                           density_g_per_cm3=self.GOLD_18K)
        w_full = chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                        total_length_mm=200.0,
                                        density_g_per_cm3=self.GOLD_18K,
                                        fill_factor=1.0)
        # fill_factor=1.0 should give a heavier result than the default (< 1.0)
        assert w_full > w_default

    def test_alias_accepted(self):
        """Aliases should resolve correctly in weight estimate."""
        w_belcher = chain_weight_estimate("belcher", wire_gauge_mm=1.5,
                                           total_length_mm=450.0,
                                           density_g_per_cm3=self.GOLD_18K)
        w_rolo = chain_weight_estimate("rolo", wire_gauge_mm=1.5,
                                        total_length_mm=450.0,
                                        density_g_per_cm3=self.GOLD_18K)
        assert abs(w_belcher - w_rolo) < 1e-6

    def test_typical_bracelet_weight_range(self):
        """18k gold cable bracelet ~1–5 g is a physically realistic range."""
        w = chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                   total_length_mm=177.8,
                                   density_g_per_cm3=self.GOLD_18K)
        assert 0.5 < w < 10.0, f"Bracelet weight {w:.3f} g outside plausible range"

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_all_styles_return_positive_weight(self, style):
        w = chain_weight_estimate(style, wire_gauge_mm=1.0,
                                   total_length_mm=450.0,
                                   density_g_per_cm3=self.GOLD_18K)
        assert w > 0, f"style={style!r}: weight={w}"

    def test_zero_gauge_raises(self):
        with pytest.raises(ValueError, match="wire_gauge_mm must be > 0"):
            chain_weight_estimate("cable", wire_gauge_mm=0,
                                   total_length_mm=200.0,
                                   density_g_per_cm3=self.GOLD_18K)

    def test_zero_length_raises(self):
        with pytest.raises(ValueError, match="total_length_mm must be > 0"):
            chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                   total_length_mm=0,
                                   density_g_per_cm3=self.GOLD_18K)

    def test_zero_density_raises(self):
        with pytest.raises(ValueError, match="density_g_per_cm3 must be > 0"):
            chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                   total_length_mm=200.0,
                                   density_g_per_cm3=0)

    def test_invalid_style_raises(self):
        with pytest.raises(ValueError, match="Unknown chain style"):
            chain_weight_estimate("chain_mail", wire_gauge_mm=1.0,
                                   total_length_mm=200.0,
                                   density_g_per_cm3=self.GOLD_18K)

    def test_invalid_fill_factor_raises(self):
        with pytest.raises(ValueError, match="fill_factor must be in"):
            chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                   total_length_mm=200.0,
                                   density_g_per_cm3=self.GOLD_18K,
                                   fill_factor=1.5)

    def test_fill_factor_zero_raises(self):
        with pytest.raises(ValueError, match="fill_factor must be in"):
            chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                   total_length_mm=200.0,
                                   density_g_per_cm3=self.GOLD_18K,
                                   fill_factor=0)

    def test_bismark_heavier_than_cable(self):
        """Bismark is multi-row so its fill factor is higher → heavier per mm."""
        w_bismark = chain_weight_estimate("bismark", wire_gauge_mm=1.0,
                                           total_length_mm=450.0,
                                           density_g_per_cm3=self.GOLD_18K)
        w_cable = chain_weight_estimate("cable", wire_gauge_mm=1.0,
                                         total_length_mm=450.0,
                                         density_g_per_cm3=self.GOLD_18K)
        assert w_bismark > w_cable


# ---------------------------------------------------------------------------
# v2: graduated flag
# ---------------------------------------------------------------------------

class TestGraduatedFlag:
    def test_graduated_false_not_in_spec(self):
        p = compute_chain_params("cable", wire_gauge_mm=1.0, link_count=50)
        assert "graduated" not in p

    def test_graduated_true_in_spec(self):
        p = compute_chain_params("cable", wire_gauge_mm=1.0,
                                  link_count=50, graduated=True)
        assert p.get("graduated") is True

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_graduated_accepted_by_all_styles(self, style):
        p = compute_chain_params(style, wire_gauge_mm=1.0,
                                  link_count=30, graduated=True)
        assert p.get("graduated") is True

    def test_graduated_via_create_tool(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0,
                       link_count=50, graduated=True)
        assert "error" not in r
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node.get("graduated") is True

    def test_no_graduated_default_in_tool(self):
        ctx, store, fid = make_ctx()
        run_create(ctx, fid, style="cable", wire_gauge_mm=1.0, link_count=50)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert "graduated" not in node


# ---------------------------------------------------------------------------
# v2: gauge_preset via LLM tool
# ---------------------------------------------------------------------------

class TestGaugePresetViaTool:
    def test_gauge_preset_medium_via_tool(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0,
                       link_count=50, gauge_preset="medium")
        assert "error" not in r
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["wire_gauge_mm"] == pytest.approx(
            GAUGE_PRESETS["cable"]["medium"]
        )

    def test_invalid_gauge_preset_via_tool(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="cable", wire_gauge_mm=1.0,
                       link_count=50, gauge_preset="ultra_heavy")
        assert "error" in r

    def test_bismark_rows_via_tool(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="bismark", wire_gauge_mm=1.0,
                       link_count=40, rows=3)
        assert "error" not in r
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["link_hints"]["rows"] == 3


# ---------------------------------------------------------------------------
# v2: ToolSpec enum completeness for new styles
# ---------------------------------------------------------------------------

class TestV2ToolSpecEnums:
    def test_create_chain_style_enum_includes_new_styles(self):
        props = jewelry_create_chain_spec.input_schema["properties"]
        enum_set = set(props["style"]["enum"])
        for style in _NEW_STYLES:
            assert style in enum_set, f"New style {style!r} missing from enum"

    def test_chain_length_style_enum_includes_new_styles(self):
        props = jewelry_chain_length_spec.input_schema["properties"]
        enum_set = set(props["style"]["enum"])
        for style in _NEW_STYLES:
            assert style in enum_set, f"New style {style!r} missing from chain_length enum"

    def test_create_chain_has_gauge_preset_field(self):
        props = jewelry_create_chain_spec.input_schema["properties"]
        assert "gauge_preset" in props
        assert set(props["gauge_preset"]["enum"]) == {"fine", "medium", "heavy"}

    def test_create_chain_has_graduated_field(self):
        props = jewelry_create_chain_spec.input_schema["properties"]
        assert "graduated" in props
        assert props["graduated"]["type"] == "boolean"

    def test_create_chain_has_rows_field(self):
        props = jewelry_create_chain_spec.input_schema["properties"]
        assert "rows" in props
        assert props["rows"]["type"] == "integer"


# ---------------------------------------------------------------------------
# v2: new styles all succeed through create tool
# ---------------------------------------------------------------------------

class TestNewStylesViaTool:
    @pytest.mark.parametrize("style", _NEW_STYLES)
    def test_new_style_tool_success(self, style):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style=style, wire_gauge_mm=1.0, link_count=50)
        assert "error" not in r, f"style={style!r}: {r}"

    def test_rolo_anklet_via_tool(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="rolo", wire_gauge_mm=1.2,
                       standard_length="anklet_9in")
        assert "error" not in r

    def test_omega_mens_necklace_via_tool(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="omega", wire_gauge_mm=1.5,
                       standard_length="mens_24in")
        assert "error" not in r

    def test_herringbone_choker_via_tool(self):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style="herringbone", wire_gauge_mm=1.0,
                       standard_length="choker_16in")
        assert "error" not in r

    @pytest.mark.parametrize("alias,expected",
                              [("belcher", "rolo"), ("spiga", "wheat"),
                               ("bead", "ball"), ("bead_chain", "ball")])
    def test_alias_via_tool(self, alias, expected):
        ctx, store, fid = make_ctx()
        r = run_create(ctx, fid, style=alias, wire_gauge_mm=1.0, link_count=30)
        assert "error" not in r
        doc = json.loads(store["content"])
        assert doc["features"][0]["style"] == expected


# ---------------------------------------------------------------------------
# OCC-gated tests
# ---------------------------------------------------------------------------

try:
    from kerf_cad_core.occ_helpers import _OCC_AVAILABLE as _OCC
except ImportError:
    _OCC = False

pytestmark_occ = pytest.mark.skipif(
    not _OCC,
    reason="pythonOCC not installed; skip chain OCC smoke tests"
)


@pytestmark_occ
class TestChainOCC:
    """Structural checks when OCC is present — confirm spec keys are enough
    for the occtWorker to build the geometry."""

    def test_chain_assembly_node_has_required_worker_keys(self):
        p = compute_chain_params("cable", wire_gauge_mm=1.0, link_count=50)
        required = {
            "style", "wire_gauge_mm", "link_length_mm", "link_width_mm",
            "link_count", "link_hints", "total_length_mm", "link_pitch_mm",
            "open_ends",
        }
        missing = required - set(p.keys())
        assert not missing, f"Missing keys for worker: {missing}"

    def test_mariner_central_bar_spec(self):
        p = compute_chain_params("mariner", wire_gauge_mm=1.5, link_count=30)
        hints = p["link_hints"]
        assert hints["central_bar"] is True
        assert hints["central_bar_width_mm"] > 0
        assert hints["central_bar_diameter_mm"] > 0

    def test_snake_scale_wider_than_wire(self):
        p = compute_chain_params("snake", wire_gauge_mm=1.0, link_count=40)
        hints = p["link_hints"]
        assert hints["scale_width_mm"] > 1.0  # wider than wire gauge

    def test_byzantine_cluster_links_count(self):
        p = compute_chain_params("byzantine", wire_gauge_mm=0.9, link_count=60)
        hints = p["link_hints"]
        assert hints["cluster_links"] == 4


# ===========================================================================
# v3 — Composed chain pieces
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers shared by composed-piece tests
# ---------------------------------------------------------------------------

def run_composed(runner, ctx, fid, **kwargs):
    """Run an async composed-piece runner and return the parsed JSON result."""
    args = {"file_id": str(fid), **kwargs}
    return run_sync(runner(ctx, json.dumps(args).encode()))


# ---------------------------------------------------------------------------
# Tennis bracelet
# ---------------------------------------------------------------------------

class TestTennisBraceletSpec:
    def test_stone_count_defaults(self):
        s = tennis_bracelet_spec(stone_count=20)
        assert s["op"] == "tennis_bracelet"
        assert s["stone_count"] == 20
        assert s["total_length_mm"] > 0
        assert s["stone_pitch_mm"] > s["stone_size_mm"]   # gap included
        assert "chains" in s and len(s["chains"]) == 1
        assert "stone_station_hints" in s
        assert s["stone_station_hints"]["station_type"] == "tennis_mount"

    def test_total_length_derives_count(self):
        s = tennis_bracelet_spec(stone_size_mm=3.0, total_length_mm=180.0)
        assert s["stone_count"] >= 1
        assert s["total_length_mm"] > 0

    def test_standard_length_bracelet(self):
        s = tennis_bracelet_spec(standard_length="bracelet_7in")
        assert s["stone_count"] >= 1

    def test_chain_sub_spec_reuses_compute_chain_params_keys(self):
        s = tennis_bracelet_spec(stone_count=15)
        chain = s["chains"][0]
        for key in ("style", "wire_gauge_mm", "link_count", "link_hints",
                    "total_length_mm", "link_pitch_mm", "open_ends"):
            assert key in chain, f"Missing key {key!r} in tennis chain sub-spec"

    def test_clasp_is_box_clasp_default(self):
        s = tennis_bracelet_spec(stone_count=10)
        assert s["clasp"]["style"] == "box_clasp"

    def test_clasp_style_override(self):
        s = tennis_bracelet_spec(stone_count=10, clasp_style="toggle")
        assert s["clasp"]["style"] == "toggle"

    def test_link_style_override(self):
        s = tennis_bracelet_spec(stone_count=10, link_style="rolo", wire_gauge_mm=0.9)
        assert s["chains"][0]["style"] == "rolo"

    def test_weight_positive(self):
        s = tennis_bracelet_spec(stone_count=20)
        assert s["estimated_weight_18k_gold_g"] > 0

    def test_no_length_source_raises(self):
        with pytest.raises(ValueError, match="required"):
            tennis_bracelet_spec()

    def test_two_length_sources_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            tennis_bracelet_spec(stone_count=10, total_length_mm=180.0)

    def test_zero_stone_size_raises(self):
        with pytest.raises(ValueError, match="stone_size_mm must be > 0"):
            tennis_bracelet_spec(stone_size_mm=0, stone_count=10)

    def test_gauge_preset_applied(self):
        s = tennis_bracelet_spec(stone_count=10, gauge_preset="heavy")
        chain = s["chains"][0]
        assert chain["wire_gauge_mm"] == pytest.approx(
            GAUGE_PRESETS["cable"]["heavy"]
        )

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_all_link_styles_succeed(self, style):
        s = tennis_bracelet_spec(stone_count=10, link_style=style, wire_gauge_mm=0.8)
        assert s["chains"][0]["style"] == _STYLE_ALIASES.get(style, style)


class TestTennisBraceletTool:
    def test_tool_success_stone_count(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_tennis_bracelet, ctx, fid, stone_count=20)
        assert "error" not in r, r
        assert r["op"] == "tennis_bracelet"
        assert r["stone_count"] == 20

    def test_node_appended(self):
        ctx, store, fid = make_ctx()
        run_composed(run_jewelry_create_tennis_bracelet, ctx, fid, stone_count=15)
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1
        assert doc["features"][0]["op"] == "tennis_bracelet"

    def test_tool_standard_length(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_tennis_bracelet, ctx, fid,
                         standard_length="bracelet_7in")
        assert "error" not in r

    def test_tool_missing_file_id(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_tennis_bracelet(
            ctx, json.dumps({"stone_count": 10}).encode()
        ))
        assert "error" in r

    def test_tool_file_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        r = run_composed(run_jewelry_create_tennis_bracelet, ctx, fid, stone_count=10)
        assert "error" in r

    def test_tool_invalid_json(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_tennis_bracelet(ctx, b"bad json"))
        assert "error" in r

    def test_tool_spec_name(self):
        assert _tennis_bracelet_spec_obj.name == "jewelry_create_tennis_bracelet"

    def test_tool_spec_has_file_id_required(self):
        assert "file_id" in _tennis_bracelet_spec_obj.input_schema["required"]


# ---------------------------------------------------------------------------
# Station necklace
# ---------------------------------------------------------------------------

class TestStationNecklaceSpec:
    def test_defaults(self):
        s = station_necklace_spec()
        assert s["op"] == "station_necklace"
        assert s["station_count"] == 5
        assert s["total_length_mm"] > 0
        assert len(s["chains"]) == 1
        assert "station_hints" in s
        assert s["station_hints"]["station_type"] == "bezel_or_prong"

    def test_standard_length_override(self):
        s = station_necklace_spec(standard_length="princess_18in")
        assert s["total_length_mm"] == pytest.approx(457.2, rel=1e-3)

    def test_total_length_override(self):
        s = station_necklace_spec(total_length_mm=400.0)
        assert s["total_length_mm"] == pytest.approx(400.0, rel=1e-3)

    def test_chain_sub_reuses_chain_params_keys(self):
        s = station_necklace_spec()
        chain = s["chains"][0]
        for key in ("style", "wire_gauge_mm", "link_count", "link_hints",
                    "total_length_mm", "link_pitch_mm", "open_ends"):
            assert key in chain

    def test_clasp_default_lobster(self):
        s = station_necklace_spec()
        assert s["clasp"]["style"] == "lobster"

    def test_station_count_stored(self):
        s = station_necklace_spec(station_count=7, station_spacing_mm=40.0)
        assert s["station_hints"]["station_count"] == 7

    def test_spacing_stored(self):
        s = station_necklace_spec(station_spacing_mm=60.0)
        assert s["station_hints"]["station_spacing_mm"] == pytest.approx(60.0)

    def test_zero_station_count_raises(self):
        with pytest.raises(ValueError, match="station_count"):
            station_necklace_spec(station_count=0)

    def test_zero_spacing_raises(self):
        with pytest.raises(ValueError, match="station_spacing_mm must be > 0"):
            station_necklace_spec(station_spacing_mm=0)

    def test_zero_stone_size_raises(self):
        with pytest.raises(ValueError, match="stone_size_mm must be > 0"):
            station_necklace_spec(stone_size_mm=0)

    def test_gauge_preset_applied(self):
        s = station_necklace_spec(gauge_preset="fine")
        assert s["chains"][0]["wire_gauge_mm"] == pytest.approx(
            GAUGE_PRESETS["cable"]["fine"]
        )

    def test_weight_positive(self):
        s = station_necklace_spec()
        assert s["estimated_weight_18k_gold_g"] > 0

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_carrier_styles_succeed(self, style):
        s = station_necklace_spec(carrier_style=style, wire_gauge_mm=0.7)
        assert s["chains"][0]["style"] == _STYLE_ALIASES.get(style, style)


class TestStationNecklaceTool:
    def test_tool_success_defaults(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_station_necklace, ctx, fid)
        assert "error" not in r, r
        assert r["op"] == "station_necklace"
        assert r["station_count"] == 5

    def test_node_appended(self):
        ctx, store, fid = make_ctx()
        run_composed(run_jewelry_create_station_necklace, ctx, fid, station_count=3)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "station_necklace"

    def test_tool_standard_length(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_station_necklace, ctx, fid,
                         standard_length="princess_18in", station_count=7)
        assert "error" not in r

    def test_tool_missing_file_id(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_station_necklace(
            ctx, json.dumps({"station_count": 5}).encode()
        ))
        assert "error" in r

    def test_tool_file_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        r = run_composed(run_jewelry_create_station_necklace, ctx, fid)
        assert "error" in r

    def test_tool_spec_name(self):
        assert _station_necklace_spec_obj.name == "jewelry_create_station_necklace"

    def test_tool_spec_has_file_id_required(self):
        assert "file_id" in _station_necklace_spec_obj.input_schema["required"]


# ---------------------------------------------------------------------------
# Lariat
# ---------------------------------------------------------------------------

class TestLariatSpec:
    def test_defaults(self):
        s = lariat_spec()
        assert s["op"] == "lariat"
        assert s["body_length_mm"] == pytest.approx(400.0)
        assert s["drop_length_mm"] == pytest.approx(80.0)
        assert len(s["chains"]) == 2   # body + drop
        assert s["clasp"] is None      # no traditional clasp

    def test_slide_hints(self):
        s = lariat_spec()
        sh = s["slide_hints"]
        assert sh["type"] == "slide"
        assert sh["slide_mechanism"] == "loop_slide"
        assert sh["inner_diameter_mm"] > 0

    def test_terminal_hints(self):
        s = lariat_spec(terminal_stone_mm=6.0)
        th = s["terminal_hints"]
        assert th["type"] == "stone_station"
        assert th["stone_size_mm"] == pytest.approx(6.0)

    def test_body_sub_spec_has_chain_keys(self):
        s = lariat_spec()
        body = s["chains"][0]
        for key in ("style", "wire_gauge_mm", "link_count", "link_hints",
                    "total_length_mm", "link_pitch_mm"):
            assert key in body

    def test_drop_sub_spec_exists(self):
        s = lariat_spec(drop_length_mm=100.0)
        drop = s["chains"][1]
        assert drop["total_length_mm"] > 0

    def test_different_body_drop_styles(self):
        s = lariat_spec(body_style="cable", drop_style="box", wire_gauge_mm=0.8)
        assert s["chains"][0]["style"] == "cable"
        assert s["chains"][1]["style"] == "box"

    def test_drop_defaults_to_body_style(self):
        s = lariat_spec(body_style="rope", wire_gauge_mm=0.8)
        assert s["chains"][0]["style"] == "rope"
        assert s["chains"][1]["style"] == "rope"

    def test_bail_slide_type(self):
        s = lariat_spec(slide_type="bail_slide")
        assert s["slide_hints"]["slide_mechanism"] == "bail_slide"

    def test_zero_body_length_raises(self):
        with pytest.raises(ValueError, match="body_length_mm must be > 0"):
            lariat_spec(body_length_mm=0)

    def test_zero_drop_length_raises(self):
        with pytest.raises(ValueError, match="drop_length_mm must be > 0"):
            lariat_spec(drop_length_mm=0)

    def test_zero_terminal_stone_raises(self):
        with pytest.raises(ValueError, match="terminal_stone_mm must be > 0"):
            lariat_spec(terminal_stone_mm=0)

    def test_gauge_preset_applied(self):
        s = lariat_spec(gauge_preset="medium")
        assert s["chains"][0]["wire_gauge_mm"] == pytest.approx(
            GAUGE_PRESETS["cable"]["medium"]
        )

    def test_weight_positive(self):
        s = lariat_spec()
        assert s["estimated_weight_18k_gold_g"] > 0

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_body_styles_succeed(self, style):
        s = lariat_spec(body_style=style, wire_gauge_mm=0.8)
        assert s["chains"][0]["style"] == _STYLE_ALIASES.get(style, style)


class TestLariatTool:
    def test_tool_success_defaults(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_lariat, ctx, fid)
        assert "error" not in r, r
        assert r["op"] == "lariat"
        assert r["body_length_mm"] == pytest.approx(400.0)

    def test_node_appended(self):
        ctx, store, fid = make_ctx()
        run_composed(run_jewelry_create_lariat, ctx, fid)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "lariat"
        # Two chain sub-specs stored
        assert len(doc["features"][0]["chains"]) == 2

    def test_tool_custom_lengths(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_lariat, ctx, fid,
                         body_length_mm=500.0, drop_length_mm=120.0)
        assert "error" not in r

    def test_tool_missing_file_id(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_lariat(ctx, json.dumps({}).encode()))
        assert "error" in r

    def test_tool_file_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        r = run_composed(run_jewelry_create_lariat, ctx, fid)
        assert "error" in r

    def test_tool_spec_name(self):
        assert _lariat_spec_obj.name == "jewelry_create_lariat"

    def test_tool_spec_has_file_id_required(self):
        assert "file_id" in _lariat_spec_obj.input_schema["required"]


# ---------------------------------------------------------------------------
# Charm bracelet
# ---------------------------------------------------------------------------

class TestCharmBraceletSpec:
    def test_defaults_with_length(self):
        s = charm_bracelet_spec(standard_length="bracelet_7in")
        assert s["op"] == "charm_bracelet"
        assert s["charm_count"] == 8
        assert len(s["chains"]) == 1
        assert "attach_hints" in s
        assert s["attach_hints"]["type"] == "jump_ring_attach"

    def test_attach_positions_count(self):
        s = charm_bracelet_spec(standard_length="bracelet_7in", charm_count=5)
        assert len(s["attach_hints"]["positions_mm"]) == 5

    def test_attach_positions_evenly_spaced(self):
        s = charm_bracelet_spec(total_length_mm=180.0, charm_count=3)
        positions = s["attach_hints"]["positions_mm"]
        assert len(positions) == 3
        # Positions should be > 0 and < total_length
        for pos in positions:
            assert 0 < pos < s["total_length_mm"]

    def test_chain_sub_reuses_chain_params_keys(self):
        s = charm_bracelet_spec(link_count=60)
        chain = s["chains"][0]
        for key in ("style", "wire_gauge_mm", "link_count", "link_hints",
                    "total_length_mm", "link_pitch_mm", "open_ends"):
            assert key in chain

    def test_clasp_default_lobster(self):
        s = charm_bracelet_spec(link_count=60)
        assert s["clasp"]["style"] == "lobster"

    def test_jump_ring_gauge_default(self):
        s = charm_bracelet_spec(link_count=60, wire_gauge_mm=1.2)
        jr = s["attach_hints"]["jump_ring_wire_gauge_mm"]
        assert abs(jr - 1.2 * 0.7) < 0.01

    def test_custom_jump_ring_gauge(self):
        s = charm_bracelet_spec(link_count=60, jump_ring_gauge_mm=0.5)
        assert s["attach_hints"]["jump_ring_wire_gauge_mm"] == pytest.approx(0.5)

    def test_rolo_default_style(self):
        s = charm_bracelet_spec(link_count=50)
        assert s["chains"][0]["style"] == "rolo"

    def test_no_length_raises(self):
        with pytest.raises(ValueError, match="required"):
            charm_bracelet_spec()

    def test_two_length_sources_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            charm_bracelet_spec(total_length_mm=180.0, link_count=60)

    def test_zero_charm_count_raises(self):
        with pytest.raises(ValueError, match="charm_count"):
            charm_bracelet_spec(link_count=60, charm_count=0)

    def test_gauge_preset(self):
        s = charm_bracelet_spec(link_count=50, gauge_preset="fine",
                                base_style="rolo")
        assert s["chains"][0]["wire_gauge_mm"] == pytest.approx(
            GAUGE_PRESETS["rolo"]["fine"]
        )

    def test_weight_positive(self):
        s = charm_bracelet_spec(link_count=60)
        assert s["estimated_weight_18k_gold_g"] > 0

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_base_styles_succeed(self, style):
        s = charm_bracelet_spec(base_style=style, wire_gauge_mm=1.0, link_count=50)
        assert s["chains"][0]["style"] == _STYLE_ALIASES.get(style, style)


class TestCharmBraceletTool:
    def test_tool_success_standard_length(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_charm_bracelet, ctx, fid,
                         standard_length="bracelet_7in")
        assert "error" not in r, r
        assert r["op"] == "charm_bracelet"
        assert r["charm_count"] == 8

    def test_node_appended(self):
        ctx, store, fid = make_ctx()
        run_composed(run_jewelry_create_charm_bracelet, ctx, fid, link_count=60)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "charm_bracelet"

    def test_tool_link_count(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_charm_bracelet, ctx, fid,
                         link_count=60, charm_count=6)
        assert "error" not in r
        assert r["charm_count"] == 6

    def test_tool_missing_file_id(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_charm_bracelet(
            ctx, json.dumps({"link_count": 60}).encode()
        ))
        assert "error" in r

    def test_tool_no_length_source(self):
        ctx, _, fid = make_ctx()
        r = run_composed(run_jewelry_create_charm_bracelet, ctx, fid)
        assert "error" in r

    def test_tool_file_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        r = run_composed(run_jewelry_create_charm_bracelet, ctx, fid, link_count=60)
        assert "error" in r

    def test_tool_spec_name(self):
        assert _charm_bracelet_spec_obj.name == "jewelry_create_charm_bracelet"

    def test_tool_spec_has_file_id_required(self):
        assert "file_id" in _charm_bracelet_spec_obj.input_schema["required"]


# ---------------------------------------------------------------------------
# Multi-strand
# ---------------------------------------------------------------------------

class TestMultiStrandSpec:
    def test_defaults_three_strands(self):
        s = multi_strand_spec(total_length_mm=450.0)
        assert s["op"] == "multi_strand"
        assert s["strand_count"] == 3
        assert len(s["chains"]) == 3

    def test_strand_styles_applied(self):
        s = multi_strand_spec(
            strand_count=2,
            strand_styles=["cable", "rope"],
            wire_gauge_mm=0.8,
            total_length_mm=450.0,
        )
        assert s["chains"][0]["style"] == "cable"
        assert s["chains"][1]["style"] == "rope"

    def test_strand_styles_padded(self):
        # Provide one style for 3 strands — last should be padded
        s = multi_strand_spec(
            strand_count=3,
            strand_styles=["box"],
            wire_gauge_mm=0.9,
            link_count=100,
        )
        assert all(c["style"] == "box" for c in s["chains"])

    def test_connector_hints(self):
        s = multi_strand_spec(total_length_mm=450.0)
        ch = s["connector_hints"]
        assert ch["type"] == "connector"
        assert ch["strand_count"] == 3

    def test_clasp_default_box_clasp(self):
        s = multi_strand_spec(total_length_mm=450.0)
        assert s["clasp"]["style"] == "box_clasp"

    def test_five_strands(self):
        s = multi_strand_spec(strand_count=5, link_count=150)
        assert len(s["chains"]) == 5

    def test_strand_count_one_raises(self):
        with pytest.raises(ValueError, match="strand_count must be an integer between"):
            multi_strand_spec(strand_count=1, total_length_mm=450.0)

    def test_strand_count_six_raises(self):
        with pytest.raises(ValueError, match="strand_count must be an integer between"):
            multi_strand_spec(strand_count=6, total_length_mm=450.0)

    def test_no_length_raises(self):
        with pytest.raises(ValueError, match="required"):
            multi_strand_spec()

    def test_two_length_sources_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            multi_strand_spec(total_length_mm=450.0, link_count=100)

    def test_each_chain_sub_has_chain_keys(self):
        s = multi_strand_spec(strand_count=2, total_length_mm=450.0)
        for chain in s["chains"]:
            for key in ("style", "wire_gauge_mm", "link_count", "link_hints",
                        "total_length_mm", "link_pitch_mm", "open_ends"):
                assert key in chain

    def test_gauge_preset(self):
        s = multi_strand_spec(strand_count=2, total_length_mm=450.0,
                               gauge_preset="fine")
        assert s["chains"][0]["wire_gauge_mm"] == pytest.approx(
            GAUGE_PRESETS["cable"]["fine"]
        )

    def test_weight_positive(self):
        s = multi_strand_spec(total_length_mm=450.0)
        assert s["estimated_weight_18k_gold_g"] > 0

    def test_connector_type_end_bar(self):
        s = multi_strand_spec(total_length_mm=450.0, connector_type="end_bar")
        assert s["connector_hints"]["connector_style"] == "end_bar"


class TestMultiStrandTool:
    def test_tool_success_defaults(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_multi_strand, ctx, fid,
                         total_length_mm=450.0)
        assert "error" not in r, r
        assert r["op"] == "multi_strand"
        assert r["strand_count"] == 3

    def test_node_appended_three_chains(self):
        ctx, store, fid = make_ctx()
        run_composed(run_jewelry_create_multi_strand, ctx, fid, link_count=100)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["op"] == "multi_strand"
        assert len(node["chains"]) == 3

    def test_tool_standard_length(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_multi_strand, ctx, fid,
                         standard_length="princess_18in", strand_count=2)
        assert "error" not in r

    def test_tool_strand_count_too_low(self):
        ctx, _, fid = make_ctx()
        r = run_composed(run_jewelry_create_multi_strand, ctx, fid,
                         strand_count=1, total_length_mm=450.0)
        assert "error" in r

    def test_tool_no_length_source(self):
        ctx, _, fid = make_ctx()
        r = run_composed(run_jewelry_create_multi_strand, ctx, fid)
        assert "error" in r

    def test_tool_missing_file_id(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_multi_strand(
            ctx, json.dumps({"total_length_mm": 450.0}).encode()
        ))
        assert "error" in r

    def test_tool_file_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        r = run_composed(run_jewelry_create_multi_strand, ctx, fid,
                         total_length_mm=450.0)
        assert "error" in r

    def test_tool_spec_name(self):
        assert _multi_strand_spec_obj.name == "jewelry_create_multi_strand"

    def test_tool_spec_has_file_id_required(self):
        assert "file_id" in _multi_strand_spec_obj.input_schema["required"]

    def test_tool_strand_styles_list(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_multi_strand, ctx, fid,
                         strand_count=2,
                         strand_styles=["cable", "rope"],
                         total_length_mm=450.0)
        assert "error" not in r
        doc = json.loads(store["content"])
        assert doc["features"][0]["chains"][0]["style"] == "cable"
        assert doc["features"][0]["chains"][1]["style"] == "rope"


# ---------------------------------------------------------------------------
# Extender chain
# ---------------------------------------------------------------------------

class TestExtenderChainSpec:
    def test_defaults(self):
        s = extender_chain_spec()
        assert s["op"] == "extender_chain"
        assert s["loop_count"] == 5
        assert s["extender_length_mm"] > 0
        assert len(s["chains"]) == 1
        assert "loop_hints" in s
        assert s["loop_hints"]["type"] == "end_loops"

    def test_loop_positions_count(self):
        s = extender_chain_spec(loop_count=4)
        assert len(s["loop_hints"]["loop_positions_mm"]) == 4

    def test_loop_positions_within_length(self):
        s = extender_chain_spec(extender_length_mm=50.0, loop_count=5)
        for pos in s["loop_hints"]["loop_positions_mm"]:
            assert 0 < pos < s["extender_length_mm"]

    def test_custom_loop_spacing(self):
        s = extender_chain_spec(extender_length_mm=60.0, loop_count=3,
                                loop_spacing_mm=10.0)
        assert s["loop_spacing_mm"] == pytest.approx(10.0)

    def test_chain_sub_has_chain_keys(self):
        s = extender_chain_spec()
        chain = s["chains"][0]
        for key in ("style", "wire_gauge_mm", "link_count", "link_hints",
                    "total_length_mm", "link_pitch_mm", "open_ends"):
            assert key in chain

    def test_clasp_default_lobster(self):
        s = extender_chain_spec()
        assert s["clasp"]["style"] == "lobster"

    def test_clasp_override(self):
        s = extender_chain_spec(end_ring_style="spring_ring")
        assert s["clasp"]["style"] == "spring_ring"

    def test_zero_length_raises(self):
        with pytest.raises(ValueError, match="extender_length_mm must be > 0"):
            extender_chain_spec(extender_length_mm=0)

    def test_zero_loop_count_raises(self):
        with pytest.raises(ValueError, match="loop_count"):
            extender_chain_spec(loop_count=0)

    def test_zero_loop_spacing_raises(self):
        with pytest.raises(ValueError, match="loop_spacing_mm must be > 0"):
            extender_chain_spec(loop_spacing_mm=0)

    def test_gauge_preset(self):
        s = extender_chain_spec(gauge_preset="heavy")
        assert s["chains"][0]["wire_gauge_mm"] == pytest.approx(
            GAUGE_PRESETS["cable"]["heavy"]
        )

    def test_weight_positive(self):
        s = extender_chain_spec()
        assert s["estimated_weight_18k_gold_g"] > 0

    def test_loop_inner_diameter_positive(self):
        s = extender_chain_spec()
        assert s["loop_hints"]["loop_inner_diameter_mm"] > 0

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_extender_styles_succeed(self, style):
        s = extender_chain_spec(extender_style=style, wire_gauge_mm=0.7)
        assert s["chains"][0]["style"] == _STYLE_ALIASES.get(style, style)


class TestExtenderChainTool:
    def test_tool_success_defaults(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_extender_chain, ctx, fid)
        assert "error" not in r, r
        assert r["op"] == "extender_chain"
        assert r["loop_count"] == 5

    def test_node_appended(self):
        ctx, store, fid = make_ctx()
        run_composed(run_jewelry_create_extender_chain, ctx, fid)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "extender_chain"

    def test_tool_custom_params(self):
        ctx, store, fid = make_ctx()
        r = run_composed(run_jewelry_create_extender_chain, ctx, fid,
                         extender_length_mm=60.0, loop_count=6)
        assert "error" not in r
        assert r["loop_count"] == 6

    def test_tool_missing_file_id(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_extender_chain(ctx, json.dumps({}).encode()))
        assert "error" in r

    def test_tool_file_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        r = run_composed(run_jewelry_create_extender_chain, ctx, fid)
        assert "error" in r

    def test_tool_invalid_json(self):
        ctx, _, _ = make_ctx()
        r = run_sync(run_jewelry_create_extender_chain(ctx, b"bad json"))
        assert "error" in r

    def test_tool_spec_name(self):
        assert _extender_chain_spec_obj.name == "jewelry_create_extender_chain"

    def test_tool_spec_has_file_id_required(self):
        assert "file_id" in _extender_chain_spec_obj.input_schema["required"]

    def test_tool_zero_loop_count_error(self):
        ctx, _, fid = make_ctx()
        r = run_composed(run_jewelry_create_extender_chain, ctx, fid, loop_count=0)
        assert "error" in r


# ---------------------------------------------------------------------------
# Cross-piece: composed pieces reuse chain_assembly link hints
# ---------------------------------------------------------------------------

class TestComposedPiecesReuseChainAssembly:
    """Each composed piece must carry chain_assembly sub-specs with the
    standard chain_assembly key set (style, wire_gauge_mm, link_count,
    link_hints, total_length_mm, link_pitch_mm, open_ends)."""

    _REQUIRED_CHAIN_KEYS = {
        "style", "wire_gauge_mm", "link_count", "link_hints",
        "total_length_mm", "link_pitch_mm", "open_ends",
    }

    def _check_chains(self, spec: dict) -> None:
        chains = spec.get("chains", [])
        assert chains, "Expected at least one chain sub-spec"
        for i, chain in enumerate(chains):
            missing = self._REQUIRED_CHAIN_KEYS - set(chain.keys())
            assert not missing, (
                f"Chain[{i}] of {spec['op']!r} missing keys: {missing}"
            )
            # link_hints must have a type key
            assert "type" in chain["link_hints"], (
                f"Chain[{i}] of {spec['op']!r}: link_hints missing 'type'"
            )

    def test_tennis_bracelet_chains(self):
        self._check_chains(tennis_bracelet_spec(stone_count=10))

    def test_station_necklace_chains(self):
        self._check_chains(station_necklace_spec())

    def test_lariat_chains(self):
        self._check_chains(lariat_spec())

    def test_charm_bracelet_chains(self):
        self._check_chains(charm_bracelet_spec(link_count=50))

    def test_multi_strand_chains(self):
        self._check_chains(multi_strand_spec(total_length_mm=450.0))

    def test_extender_chain_chains(self):
        self._check_chains(extender_chain_spec())

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_tennis_all_styles_chain_keys(self, style):
        s = tennis_bracelet_spec(stone_count=5, link_style=style, wire_gauge_mm=0.8)
        self._check_chains(s)

    @pytest.mark.parametrize("style", sorted(_VALID_LINK_STYLES))
    def test_extender_all_styles_chain_keys(self, style):
        s = extender_chain_spec(extender_style=style, wire_gauge_mm=0.7)
        self._check_chains(s)
