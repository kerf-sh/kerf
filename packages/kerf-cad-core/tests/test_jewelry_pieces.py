"""
Tests for kerf_cad_core.jewelry.pieces

Pure-Python section (always runs):
  - Each piece builder → valid spec + attach_points
  - Pair pieces (earrings, cufflink) emit mirrored left+right pairs
  - Validation rejects bad input
  - Plugin loader sees the module (import via importlib)

OCC-gated section:
  - Skipped cleanly when pythonOCC is absent.
  - When OCC present: structural smoke test only (no geometry eval here;
    the occtWorker JS tests cover the actual tessellation).
"""

from __future__ import annotations

import asyncio
import importlib
import json
import math
import uuid

import pytest

from kerf_cad_core.jewelry.pieces import (
    # pendant
    PendantSpec,
    compute_pendant_params,
    jewelry_create_pendant_spec,
    run_jewelry_create_pendant,
    _VALID_PENDANT_STYLES,
    _VALID_PENDANT_OUTLINE_SHAPES,
    _VALID_BAIL_TYPES,
    # earrings
    EarringSpec,
    compute_earring_params,
    jewelry_create_earrings_spec,
    run_jewelry_create_earrings,
    _VALID_EARRING_STYLES,
    # brooch
    BroochSpec,
    compute_brooch_params,
    jewelry_create_brooch_spec,
    run_jewelry_create_brooch,
    _VALID_BROOCH_SHAPES,
    # cufflink
    CufflinkSpec,
    compute_cufflink_params,
    jewelry_create_cufflink_spec,
    run_jewelry_create_cufflink,
    _VALID_CUFFLINK_BACK_STYLES,
    # bangle
    BangleSpec,
    compute_bangle_params,
    jewelry_create_bangle_spec,
    run_jewelry_create_bangle,
    _VALID_BANGLE_FORMS,
    _VALID_BANGLE_CROSS_SECTIONS,
    _VALID_WRIST_SIZE_SYSTEMS,
    _US_BANGLE_SIZES,
    _bangle_inner_diameter_mm,
)

_PI = math.pi


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as test_jewelry_ring.py)
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
# OCC skip marker
# ---------------------------------------------------------------------------

try:
    from kerf_cad_core.occ_helpers import _OCC_AVAILABLE as _OCC
except ImportError:
    _OCC = False

pytestmark_occ = pytest.mark.skipif(
    not _OCC,
    reason="pythonOCC not installed; install with: conda install -c conda-forge pythonocc-core"
)


# ===========================================================================
# PENDANT
# ===========================================================================

class TestPendantSpec:

    def test_defaults_validate(self):
        spec = PendantSpec()
        spec.validate()

    def test_to_dict_has_required_keys(self):
        spec = PendantSpec()
        d = spec.to_dict()
        for key in ("style", "outline_shape", "width_mm", "height_mm",
                    "thickness_mm", "attach_points", "composite_ops"):
            assert key in d, f"Missing key: {key}"

    def test_attach_points_contains_bail(self):
        spec = PendantSpec()
        d = spec.to_dict()
        bail_aps = [ap for ap in d["attach_points"] if ap["type"] == "bail_hole"]
        assert len(bail_aps) == 1
        assert bail_aps[0]["role"] == "bail"

    def test_centre_stone_attach_point_present(self):
        spec = PendantSpec(centre_stone_diameter_mm=6.0)
        d = spec.to_dict()
        stone_aps = [ap for ap in d["attach_points"] if ap["type"] == "stone_seat"]
        assert any(ap["role"] == "centre_stone" for ap in stone_aps)

    def test_no_stone_no_stone_seat(self):
        spec = PendantSpec(centre_stone_diameter_mm=0.0)
        d = spec.to_dict()
        stone_aps = [ap for ap in d["attach_points"] if ap["role"] == "centre_stone"]
        assert len(stone_aps) == 0

    def test_halo_stone_attach_points(self):
        spec = PendantSpec(
            style="halo",
            centre_stone_diameter_mm=6.0,
            halo_stone_diameter_mm=2.0,
            halo_stone_count=8,
        )
        d = spec.to_dict()
        halo_aps = [ap for ap in d["attach_points"] if "halo_stone" in ap["role"]]
        assert len(halo_aps) == 8

    def test_halo_stone_count_too_small_raises(self):
        spec = PendantSpec(halo_stone_diameter_mm=2.0, halo_stone_count=2)
        with pytest.raises(ValueError, match="halo_stone_count"):
            spec.validate()

    def test_locket_has_composite_op(self):
        spec = PendantSpec(style="locket")
        d = spec.to_dict()
        assert "locket_hinge" in d["composite_ops"]
        assert "locket_hinge_side" in d

    def test_invalid_style_raises(self):
        spec = PendantSpec(style="necklace")
        with pytest.raises(ValueError, match="pendant.style"):
            spec.validate()

    def test_invalid_outline_shape_raises(self):
        spec = PendantSpec(outline_shape="blob")
        with pytest.raises(ValueError, match="pendant.outline_shape"):
            spec.validate()

    def test_invalid_bail_type_raises(self):
        spec = PendantSpec(bail_type="wire")
        with pytest.raises(ValueError, match="pendant.bail_type"):
            spec.validate()

    def test_zero_width_raises(self):
        spec = PendantSpec(width_mm=0.0)
        with pytest.raises(ValueError, match="pendant.width_mm"):
            spec.validate()

    def test_zero_height_raises(self):
        spec = PendantSpec(height_mm=0.0)
        with pytest.raises(ValueError, match="pendant.height_mm"):
            spec.validate()

    def test_negative_thickness_raises(self):
        spec = PendantSpec(thickness_mm=-1.0)
        with pytest.raises(ValueError, match="pendant.thickness_mm"):
            spec.validate()

    def test_bail_loop_id_auto_derived(self):
        spec = PendantSpec(bail_wire_gauge_mm=1.0, bail_loop_id_mm=0.0)
        d = spec.to_dict()
        assert d["bail_loop_inner_diameter_mm"] == pytest.approx(3.0, abs=0.01)

    def test_bail_loop_id_explicit(self):
        spec = PendantSpec(bail_wire_gauge_mm=1.0, bail_loop_id_mm=5.0)
        d = spec.to_dict()
        assert d["bail_loop_inner_diameter_mm"] == pytest.approx(5.0, abs=0.01)

    def test_attach_point_normal_for_bail(self):
        spec = PendantSpec()
        d = spec.to_dict()
        bail_ap = next(ap for ap in d["attach_points"] if ap["type"] == "bail_hole")
        assert bail_ap["normal"] == [0.0, 1.0, 0.0]

    def test_attach_point_normal_for_stone_seat(self):
        spec = PendantSpec(centre_stone_diameter_mm=5.0)
        d = spec.to_dict()
        stone_ap = next(ap for ap in d["attach_points"] if ap["role"] == "centre_stone")
        assert stone_ap["normal"] == [0.0, 0.0, 1.0]


class TestComputePendantParams:

    def test_basic_defaults(self):
        p = compute_pendant_params()
        assert p["style"] == "solitaire_drop"
        assert p["outline_shape"] == "teardrop"
        assert len(p["attach_points"]) >= 1

    def test_charm_style_no_stone_required(self):
        p = compute_pendant_params(style="charm", centre_stone_diameter_mm=0.0)
        assert p["style"] == "charm"
        assert "centre_stone_diameter_mm" not in p

    def test_cluster_style(self):
        p = compute_pendant_params(
            style="cluster",
            centre_stone_diameter_mm=5.0,
            halo_stone_diameter_mm=2.0,
            halo_stone_count=6,
        )
        assert p["halo_stone_count"] == 6

    def test_invalid_style_raises(self):
        with pytest.raises(ValueError):
            compute_pendant_params(style="tiara")

    def test_invalid_bail_raises(self):
        with pytest.raises(ValueError):
            compute_pendant_params(bail_type="staple")


class TestRunJewelryCreatePendant:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_sync(run_jewelry_create_pendant(ctx, json.dumps(args).encode()))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "pendant"
        assert r["id"] == "pendant-1"

    def test_node_appended_to_doc(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        ops = [f["op"] for f in doc["features"]]
        assert "pendant" in ops

    def test_attach_points_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert isinstance(r["attach_points"], list)
        assert len(r["attach_points"]) >= 1

    def test_missing_file_id_returns_error(self):
        ctx, store, fid = make_ctx()
        args = {}
        r = run_sync(run_jewelry_create_pendant(ctx, json.dumps(args).encode()))
        assert r.get("code") == "BAD_ARGS"

    def test_not_a_uuid_returns_error(self):
        ctx, store, fid = make_ctx()
        args = {"file_id": "not-a-valid-uuid-at-all"}
        r = run_sync(run_jewelry_create_pendant(ctx, json.dumps(args).encode()))
        assert r.get("code") == "BAD_ARGS"

    def test_bad_style_returns_error(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, style="tiara")
        assert r.get("code") == "BAD_ARGS"

    def test_bad_file_id_format_error(self):
        ctx, store, fid = make_ctx()
        args = {"file_id": "not-a-uuid"}
        r = run_sync(run_jewelry_create_pendant(ctx, json.dumps(args).encode()))
        assert r.get("code") == "BAD_ARGS"

    def test_halo_style_with_stones(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid,
                       style="halo",
                       centre_stone_diameter_mm=6.0,
                       halo_stone_diameter_mm=2.0,
                       halo_stone_count=8)
        assert "error" not in r
        halo_aps = [ap for ap in r["attach_points"] if "halo_stone" in ap.get("role", "")]
        assert len(halo_aps) == 8

    def test_sequential_node_ids(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        ids = [f["id"] for f in doc["features"]]
        assert "pendant-1" in ids
        assert "pendant-2" in ids


# ===========================================================================
# EARRINGS
# ===========================================================================

class TestEarringSpec:

    def test_stud_defaults_validate(self):
        spec = EarringSpec(style="stud")
        spec.validate()

    def test_drop_defaults_validate(self):
        spec = EarringSpec(style="drop")
        spec.validate()

    def test_hoop_defaults_validate(self):
        spec = EarringSpec(style="hoop")
        spec.validate()

    def test_huggie_defaults_validate(self):
        spec = EarringSpec(style="huggie")
        spec.validate()

    def test_chandelier_defaults_validate(self):
        spec = EarringSpec(style="chandelier")
        spec.validate()

    def test_pair_emitted(self):
        spec = EarringSpec(style="stud")
        d = spec.to_dict()
        assert "left" in d["pair"]
        assert "right" in d["pair"]

    def test_attach_points_have_side(self):
        spec = EarringSpec(style="stud")
        d = spec.to_dict()
        sides = {ap["side"] for ap in d["attach_points"]}
        assert "left" in sides
        assert "right" in sides

    def test_stud_has_post_attach_point(self):
        spec = EarringSpec(style="stud")
        d = spec.to_dict()
        post_aps = [ap for ap in d["attach_points"] if ap["type"] == "post"]
        assert len(post_aps) == 2  # one per side

    def test_stud_has_butterfly_back_attach_point(self):
        spec = EarringSpec(style="stud")
        d = spec.to_dict()
        butterfly_aps = [ap for ap in d["attach_points"]
                         if ap.get("finding_mount_hint") == "post_butterfly"]
        assert len(butterfly_aps) == 2  # one per side

    def test_drop_has_ear_wire_attach_point(self):
        spec = EarringSpec(style="drop")
        d = spec.to_dict()
        ew_aps = [ap for ap in d["attach_points"] if ap["type"] == "ear_wire"]
        assert len(ew_aps) >= 2  # one per side

    def test_hoop_has_hinge_and_clasp(self):
        spec = EarringSpec(style="hoop", hoop_inner_diameter_mm=16.0)
        d = spec.to_dict()
        hinge_aps = [ap for ap in d["attach_points"] if ap["type"] == "hinge"]
        clasp_aps = [ap for ap in d["attach_points"] if ap["type"] == "clasp_mount"]
        assert len(hinge_aps) == 2  # one per side
        assert len(clasp_aps) == 2

    def test_pair_mirrors_x_position(self):
        """Left ear X positions should be negated relative to right."""
        spec = EarringSpec(style="stud")
        d = spec.to_dict()
        right_aps = [ap for ap in d["attach_points"] if ap.get("side") == "right"]
        left_aps = [ap for ap in d["attach_points"] if ap.get("side") == "left"]
        assert len(right_aps) == len(left_aps)
        for r_ap, l_ap in zip(right_aps, left_aps):
            rx, lx = r_ap["position"][0], l_ap["position"][0]
            assert abs(rx + lx) < 1e-3, (
                f"X should be mirrored: right={rx}, left={lx}"
            )

    def test_chandelier_has_tier_connectors(self):
        spec = EarringSpec(style="chandelier", tier_count=3)
        d = spec.to_dict()
        tier_aps = [ap for ap in d["attach_points"]
                    if "tier_" in ap.get("role", "")]
        # 3 tiers × 2 sides = 6
        assert len(tier_aps) == 6

    def test_chandelier_tier_count_out_of_range_raises(self):
        spec = EarringSpec(style="chandelier", tier_count=6)
        with pytest.raises(ValueError, match="tier_count"):
            spec.validate()

    def test_invalid_style_raises(self):
        spec = EarringSpec(style="clip_on")
        with pytest.raises(ValueError, match="earring.style"):
            spec.validate()

    def test_zero_face_diameter_raises(self):
        spec = EarringSpec(face_diameter_mm=0.0)
        with pytest.raises(ValueError, match="earring.face_diameter_mm"):
            spec.validate()

    def test_stone_seat_present_when_stone_set(self):
        spec = EarringSpec(style="stud", stone_diameter_mm=4.0, stone_count=1)
        d = spec.to_dict()
        stone_aps = [ap for ap in d["attach_points"] if ap["type"] == "stone_seat"]
        assert len(stone_aps) == 2  # one per side

    def test_no_stone_seat_when_stone_diameter_zero(self):
        spec = EarringSpec(style="stud", stone_diameter_mm=0.0)
        d = spec.to_dict()
        stone_aps = [ap for ap in d["attach_points"] if ap["type"] == "stone_seat"]
        assert len(stone_aps) == 0

    def test_hoop_outer_diameter_computed(self):
        spec = EarringSpec(style="hoop", hoop_inner_diameter_mm=16.0, wire_gauge_mm=1.0)
        d = spec.to_dict()
        assert d["hoop_outer_diameter_mm"] == pytest.approx(18.0, abs=0.01)


class TestComputeEarringParams:

    def test_stud_defaults(self):
        p = compute_earring_params(style="stud")
        assert p["style"] == "stud"
        assert "left" in p["pair"]
        assert "right" in p["pair"]

    def test_drop_has_drop_length(self):
        p = compute_earring_params(style="drop", drop_length_mm=25.0)
        assert p["drop_length_mm"] == pytest.approx(25.0, abs=0.01)

    def test_hoop_has_inner_diameter(self):
        p = compute_earring_params(style="hoop", hoop_inner_diameter_mm=20.0)
        assert p["hoop_inner_diameter_mm"] == pytest.approx(20.0, abs=0.01)

    def test_invalid_style_raises(self):
        with pytest.raises(ValueError):
            compute_earring_params(style="torpedo")


class TestRunJewelryCreateEarrings:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_sync(run_jewelry_create_earrings(ctx, json.dumps(args).encode()))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "earrings"
        assert r["id"] == "earrings-1"

    def test_pair_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "left" in r["pair"]
        assert "right" in r["pair"]

    def test_node_appended(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "earrings"

    def test_missing_file_id_error(self):
        ctx, store, fid = make_ctx()
        r = run_sync(run_jewelry_create_earrings(ctx, json.dumps({}).encode()))
        assert r.get("code") == "BAD_ARGS"

    def test_bad_style_error(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, style="torpedo")
        assert r.get("code") == "BAD_ARGS"

    def test_hoop_style(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, style="hoop", hoop_inner_diameter_mm=18.0)
        assert "error" not in r
        assert r["op"] == "earrings"

    def test_chandelier_style(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, style="chandelier", tier_count=2, drop_length_mm=30.0)
        assert "error" not in r


# ===========================================================================
# BROOCH
# ===========================================================================

class TestBroochSpec:

    def test_defaults_validate(self):
        spec = BroochSpec()
        spec.validate()

    def test_to_dict_has_required_keys(self):
        spec = BroochSpec()
        d = spec.to_dict()
        for key in ("shape", "width_mm", "height_mm", "thickness_mm",
                    "attach_points", "composite_ops"):
            assert key in d, f"Missing key: {key}"

    def test_stone_attach_points_count(self):
        spec = BroochSpec(stone_diameter_mm=4.0, stone_count=3)
        d = spec.to_dict()
        stone_aps = [ap for ap in d["attach_points"] if ap["type"] == "stone_seat"]
        assert len(stone_aps) == 3

    def test_pin_mount_hint_present(self):
        spec = BroochSpec()
        d = spec.to_dict()
        pin_aps = [ap for ap in d["attach_points"]
                   if ap["type"] == "pin_mount" and ap["role"] == "pin_finding"]
        assert len(pin_aps) == 1
        assert pin_aps[0]["finding_mount_hint"] == "pin_stem"

    def test_joint_and_catch_hints_present(self):
        spec = BroochSpec()
        d = spec.to_dict()
        roles = {ap["role"] for ap in d["attach_points"] if ap["type"] == "pin_mount"}
        assert "pin_joint" in roles
        assert "pin_catch" in roles

    def test_safety_catch_propagated(self):
        spec = BroochSpec(safety_catch=True)
        d = spec.to_dict()
        pin_ap = next(ap for ap in d["attach_points"]
                      if ap["role"] == "pin_finding")
        assert pin_ap["safety_catch"] is True

    def test_pin_stem_length_auto(self):
        spec = BroochSpec(width_mm=40.0, pin_stem_length_mm=0.0)
        d = spec.to_dict()
        assert d["pin_stem_length_mm"] == pytest.approx(44.0, abs=0.1)

    def test_pin_stem_length_explicit(self):
        spec = BroochSpec(width_mm=40.0, pin_stem_length_mm=50.0)
        d = spec.to_dict()
        assert d["pin_stem_length_mm"] == pytest.approx(50.0, abs=0.01)

    def test_no_stone_no_stone_seat(self):
        spec = BroochSpec(stone_diameter_mm=0.0, stone_count=0)
        d = spec.to_dict()
        stone_aps = [ap for ap in d["attach_points"] if ap["type"] == "stone_seat"]
        assert len(stone_aps) == 0

    def test_invalid_shape_raises(self):
        spec = BroochSpec(shape="triangle")
        with pytest.raises(ValueError, match="brooch.shape"):
            spec.validate()

    def test_zero_width_raises(self):
        spec = BroochSpec(width_mm=0.0)
        with pytest.raises(ValueError, match="brooch.width_mm"):
            spec.validate()

    def test_stone_count_zero_with_stone_diameter_raises(self):
        spec = BroochSpec(stone_diameter_mm=4.0, stone_count=0)
        with pytest.raises(ValueError, match="stone_count"):
            spec.validate()


class TestComputeBroochParams:

    def test_basic_defaults(self):
        p = compute_brooch_params()
        assert p["shape"] == "oval"
        assert len(p["attach_points"]) >= 3  # stones + pin mounts

    def test_floral_shape(self):
        p = compute_brooch_params(shape="floral")
        assert p["shape"] == "floral"

    def test_invalid_shape_raises(self):
        with pytest.raises(ValueError):
            compute_brooch_params(shape="rhombus")


class TestRunJewelryCreateBrooch:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_sync(run_jewelry_create_brooch(ctx, json.dumps(args).encode()))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "brooch"
        assert r["id"] == "brooch-1"

    def test_node_appended(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "brooch"

    def test_missing_file_id_error(self):
        ctx, store, fid = make_ctx()
        r = run_sync(run_jewelry_create_brooch(ctx, json.dumps({}).encode()))
        assert r.get("code") == "BAD_ARGS"

    def test_bad_shape_error(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, shape="rhombus")
        assert r.get("code") == "BAD_ARGS"

    def test_attach_points_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert isinstance(r["attach_points"], list)
        assert len(r["attach_points"]) >= 3

    def test_safety_catch_false(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, safety_catch=False)
        assert "error" not in r
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["safety_catch"] is False


# ===========================================================================
# CUFFLINK
# ===========================================================================

class TestCufflinkSpec:

    def test_defaults_validate(self):
        spec = CufflinkSpec()
        spec.validate()

    def test_to_dict_has_required_keys(self):
        spec = CufflinkSpec()
        d = spec.to_dict()
        for key in ("pair", "face_diameter_mm", "face_thickness_mm",
                    "post_length_mm", "post_diameter_mm",
                    "back_style", "back_diameter_mm",
                    "attach_points", "composite_ops"):
            assert key in d, f"Missing key: {key}"

    def test_pair_emitted(self):
        spec = CufflinkSpec()
        d = spec.to_dict()
        assert "left" in d["pair"]
        assert "right" in d["pair"]

    def test_attach_points_have_side(self):
        spec = CufflinkSpec()
        d = spec.to_dict()
        sides = {ap["side"] for ap in d["attach_points"]}
        assert "left" in sides
        assert "right" in sides

    def test_pair_mirrors_x_position(self):
        spec = CufflinkSpec()
        d = spec.to_dict()
        right_aps = [ap for ap in d["attach_points"] if ap.get("side") == "right"]
        left_aps = [ap for ap in d["attach_points"] if ap.get("side") == "left"]
        assert len(right_aps) == len(left_aps)
        for r_ap, l_ap in zip(right_aps, left_aps):
            rx, lx = r_ap["position"][0], l_ap["position"][0]
            assert abs(rx + lx) < 1e-3, (
                f"X should be mirrored: right={rx}, left={lx}"
            )

    def test_post_stem_attach_point(self):
        spec = CufflinkSpec()
        d = spec.to_dict()
        post_aps = [ap for ap in d["attach_points"]
                    if ap["type"] == "post" and ap["role"] == "post_stem"]
        assert len(post_aps) == 2  # one per side

    def test_back_element_attach_point(self):
        spec = CufflinkSpec()
        d = spec.to_dict()
        back_aps = [ap for ap in d["attach_points"]
                    if ap["role"] == "back_element"]
        assert len(back_aps) == 2
        assert back_aps[0]["back_style"] == "toggle"

    def test_chain_back_has_chain_length(self):
        spec = CufflinkSpec(back_style="chain", chain_length_mm=10.0)
        d = spec.to_dict()
        assert d["chain_length_mm"] == pytest.approx(10.0, abs=0.01)
        back_aps = [ap for ap in d["attach_points"] if ap["role"] == "back_element"]
        assert all("chain_length_mm" in ap for ap in back_aps)

    def test_stone_seat_present_when_set(self):
        spec = CufflinkSpec(stone_diameter_mm=8.0)
        d = spec.to_dict()
        stone_aps = [ap for ap in d["attach_points"] if ap["type"] == "stone_seat"]
        assert len(stone_aps) == 2

    def test_no_stone_when_zero(self):
        spec = CufflinkSpec(stone_diameter_mm=0.0)
        d = spec.to_dict()
        stone_aps = [ap for ap in d["attach_points"] if ap["type"] == "stone_seat"]
        assert len(stone_aps) == 0

    def test_invalid_back_style_raises(self):
        spec = CufflinkSpec(back_style="velcro")
        with pytest.raises(ValueError, match="cufflink.back_style"):
            spec.validate()

    def test_zero_face_diameter_raises(self):
        spec = CufflinkSpec(face_diameter_mm=0.0)
        with pytest.raises(ValueError, match="cufflink.face_diameter_mm"):
            spec.validate()

    def test_zero_post_length_raises(self):
        spec = CufflinkSpec(post_length_mm=0.0)
        with pytest.raises(ValueError, match="cufflink.post_length_mm"):
            spec.validate()

    def test_all_back_styles_valid(self):
        for style in _VALID_CUFFLINK_BACK_STYLES:
            spec = CufflinkSpec(back_style=style)
            spec.validate()


class TestComputeCufflinkParams:

    def test_defaults(self):
        p = compute_cufflink_params()
        assert "left" in p["pair"]
        assert "right" in p["pair"]

    def test_whale_back(self):
        p = compute_cufflink_params(back_style="whale_back")
        assert p["back_style"] == "whale_back"

    def test_invalid_back_raises(self):
        with pytest.raises(ValueError):
            compute_cufflink_params(back_style="velcro")


class TestRunJewelryCreateCufflink:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_sync(run_jewelry_create_cufflink(ctx, json.dumps(args).encode()))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "cufflink"
        assert r["id"] == "cufflink-1"

    def test_pair_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "left" in r["pair"]
        assert "right" in r["pair"]

    def test_node_appended(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "cufflink"

    def test_missing_file_id_error(self):
        ctx, store, fid = make_ctx()
        r = run_sync(run_jewelry_create_cufflink(ctx, json.dumps({}).encode()))
        assert r.get("code") == "BAD_ARGS"

    def test_bad_back_style_error(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, back_style="velcro")
        assert r.get("code") == "BAD_ARGS"

    def test_chain_back_stored(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, back_style="chain", chain_length_mm=12.0)
        assert "error" not in r
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["back_style"] == "chain"
        assert node["chain_length_mm"] == pytest.approx(12.0, abs=0.01)


# ===========================================================================
# BANGLE
# ===========================================================================

class TestBangleInnerDiameter:

    def test_us_medium(self):
        d = _bangle_inner_diameter_mm("M", "us")
        assert d == pytest.approx(63.5, abs=0.1)

    def test_us_case_insensitive(self):
        d_upper = _bangle_inner_diameter_mm("XS", "us")
        d_lower = _bangle_inner_diameter_mm("xs", "us")
        assert d_upper == pytest.approx(d_lower, abs=0.01)

    def test_mm_circumference(self):
        circ = 200.0
        d = _bangle_inner_diameter_mm(circ, "mm")
        assert d == pytest.approx(circ / _PI, abs=0.01)

    def test_inches_circumference(self):
        circ_in = 7.87  # 200 mm
        d = _bangle_inner_diameter_mm(circ_in, "inches")
        assert d == pytest.approx((circ_in * 25.4) / _PI, abs=0.1)

    def test_invalid_system_raises(self):
        with pytest.raises(ValueError):
            _bangle_inner_diameter_mm("M", "uk")

    def test_invalid_us_size_raises(self):
        with pytest.raises(ValueError):
            _bangle_inner_diameter_mm("XXXL", "us")

    def test_zero_mm_circumference_raises(self):
        with pytest.raises(ValueError):
            _bangle_inner_diameter_mm(0.0, "mm")


class TestBangleSpec:

    def test_closed_defaults_validate(self):
        spec = BangleSpec(form="closed")
        spec.validate()

    def test_open_cuff_defaults_validate(self):
        spec = BangleSpec(form="open_cuff")
        spec.validate()

    def test_to_dict_has_required_keys(self):
        id_mm = _bangle_inner_diameter_mm("M", "us")
        spec = BangleSpec(form="closed")
        d = spec.to_dict(id_mm)
        for key in ("form", "inner_diameter_mm", "outer_diameter_mm",
                    "cross_section", "band_width_mm", "thickness_mm",
                    "attach_points", "composite_ops"):
            assert key in d, f"Missing key: {key}"

    def test_outer_diameter_is_inner_plus_twice_thickness(self):
        id_mm = _bangle_inner_diameter_mm("M", "us")
        spec = BangleSpec(form="closed", thickness_mm=2.5)
        d = spec.to_dict(id_mm)
        assert d["outer_diameter_mm"] == pytest.approx(id_mm + 5.0, abs=0.01)

    def test_closed_no_hinge_no_attach_points(self):
        id_mm = _bangle_inner_diameter_mm("M", "us")
        spec = BangleSpec(form="closed", hinge_style="none", clasp_hint="none")
        d = spec.to_dict(id_mm)
        assert d["attach_points"] == []

    def test_closed_with_hinge_has_hinge_attach_point(self):
        id_mm = _bangle_inner_diameter_mm("M", "us")
        spec = BangleSpec(form="closed", hinge_style="box_hinge", clasp_hint="box_clasp")
        d = spec.to_dict(id_mm)
        hinge_aps = [ap for ap in d["attach_points"] if ap["type"] == "hinge"]
        clasp_aps = [ap for ap in d["attach_points"] if ap["type"] == "clasp_mount"]
        assert len(hinge_aps) == 1
        assert len(clasp_aps) == 1

    def test_open_cuff_has_two_end_attach_points(self):
        id_mm = _bangle_inner_diameter_mm("M", "us")
        spec = BangleSpec(form="open_cuff", opening_angle_deg=60.0)
        d = spec.to_dict(id_mm)
        end_aps = [ap for ap in d["attach_points"] if ap["type"] == "clasp_mount"]
        assert len(end_aps) == 2

    def test_open_cuff_stores_arc_deg(self):
        id_mm = _bangle_inner_diameter_mm("M", "us")
        spec = BangleSpec(form="open_cuff", opening_angle_deg=60.0)
        d = spec.to_dict(id_mm)
        assert d["arc_deg"] == pytest.approx(300.0, abs=0.01)

    def test_invalid_form_raises(self):
        spec = BangleSpec(form="twisted")
        with pytest.raises(ValueError, match="bangle.form"):
            spec.validate()

    def test_invalid_cross_section_raises(self):
        spec = BangleSpec(cross_section="triangle")
        with pytest.raises(ValueError, match="bangle.cross_section"):
            spec.validate()

    def test_zero_band_width_raises(self):
        spec = BangleSpec(band_width_mm=0.0)
        with pytest.raises(ValueError, match="bangle.band_width_mm"):
            spec.validate()

    def test_zero_thickness_raises(self):
        spec = BangleSpec(thickness_mm=0.0)
        with pytest.raises(ValueError, match="bangle.thickness_mm"):
            spec.validate()

    def test_opening_angle_too_large_raises(self):
        spec = BangleSpec(form="open_cuff", opening_angle_deg=130.0)
        with pytest.raises(ValueError, match="opening_angle_deg"):
            spec.validate()

    def test_invalid_hinge_style_raises(self):
        spec = BangleSpec(hinge_style="spring")
        with pytest.raises(ValueError, match="bangle.hinge_style"):
            spec.validate()

    def test_invalid_clasp_hint_raises(self):
        spec = BangleSpec(clasp_hint="glue")
        with pytest.raises(ValueError, match="bangle.clasp_hint"):
            spec.validate()

    def test_all_cross_sections_valid(self):
        id_mm = _bangle_inner_diameter_mm("M", "us")
        for cs in _VALID_BANGLE_CROSS_SECTIONS:
            spec = BangleSpec(form="closed", cross_section=cs)
            spec.validate()
            d = spec.to_dict(id_mm)
            assert d["cross_section"] == cs


class TestComputeBangleParams:

    def test_us_size_m(self):
        p = compute_bangle_params(wrist_size="M", wrist_size_system="us")
        assert p["inner_diameter_mm"] == pytest.approx(63.5, abs=0.1)
        assert "wrist_circumference_mm" in p

    def test_mm_system(self):
        p = compute_bangle_params(wrist_size=200.0, wrist_size_system="mm")
        expected_id = 200.0 / _PI
        assert p["inner_diameter_mm"] == pytest.approx(expected_id, abs=0.1)

    def test_open_cuff(self):
        p = compute_bangle_params(form="open_cuff", wrist_size="L",
                                  opening_angle_deg=45.0)
        assert p["form"] == "open_cuff"
        assert "arc_deg" in p
        assert p["arc_deg"] == pytest.approx(315.0, abs=0.01)

    def test_closed_with_hinge(self):
        p = compute_bangle_params(form="closed", wrist_size="M",
                                  hinge_style="box_hinge", clasp_hint="magnetic")
        assert "hinge_style" in p
        assert p["hinge_style"] == "box_hinge"
        assert p["clasp_hint"] == "magnetic"

    def test_invalid_wrist_size_raises(self):
        with pytest.raises(ValueError):
            compute_bangle_params(wrist_size="XXXL", wrist_size_system="us")

    def test_invalid_form_raises(self):
        with pytest.raises(ValueError):
            compute_bangle_params(form="twisted", wrist_size="M")


class TestRunJewelryCreateBangle:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_sync(run_jewelry_create_bangle(ctx, json.dumps(args).encode()))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "bangle"
        assert r["id"] == "bangle-1"

    def test_node_appended(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "bangle"

    def test_inner_diameter_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, wrist_size="M", wrist_size_system="us")
        assert r["inner_diameter_mm"] == pytest.approx(63.5, abs=0.1)

    def test_wrist_circumference_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, wrist_size="M", wrist_size_system="us")
        assert "wrist_circumference_mm" in r

    def test_missing_file_id_error(self):
        ctx, store, fid = make_ctx()
        r = run_sync(run_jewelry_create_bangle(ctx, json.dumps({}).encode()))
        assert r.get("code") == "BAD_ARGS"

    def test_bad_form_error(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, form="twisted")
        assert r.get("code") == "BAD_ARGS"

    def test_bad_cross_section_error(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, cross_section="triangle")
        assert r.get("code") == "BAD_ARGS"

    def test_bad_file_id_format_error(self):
        ctx, store, fid = make_ctx()
        args = {"file_id": "not-a-uuid"}
        r = run_sync(run_jewelry_create_bangle(ctx, json.dumps(args).encode()))
        assert r.get("code") == "BAD_ARGS"

    def test_open_cuff(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, form="open_cuff", opening_angle_deg=45.0)
        assert "error" not in r
        assert r["op"] == "bangle"

    def test_inches_wrist_size(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, wrist_size=7.87, wrist_size_system="inches")
        assert "error" not in r

    def test_sequential_ids(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        ids = [f["id"] for f in doc["features"]]
        assert "bangle-1" in ids
        assert "bangle-2" in ids


# ===========================================================================
# Plugin loader
# ===========================================================================

class TestPluginLoader:

    def test_module_importable(self):
        """The module must be importable (registers @register decorators)."""
        mod = importlib.import_module("kerf_cad_core.jewelry.pieces")
        assert hasattr(mod, "run_jewelry_create_pendant")
        assert hasattr(mod, "run_jewelry_create_earrings")
        assert hasattr(mod, "run_jewelry_create_brooch")
        assert hasattr(mod, "run_jewelry_create_cufflink")
        assert hasattr(mod, "run_jewelry_create_bangle")

    def test_tool_specs_have_names(self):
        from kerf_cad_core.jewelry.pieces import (
            jewelry_create_pendant_spec,
            jewelry_create_earrings_spec,
            jewelry_create_brooch_spec,
            jewelry_create_cufflink_spec,
            jewelry_create_bangle_spec,
        )
        assert jewelry_create_pendant_spec.name == "jewelry_create_pendant"
        assert jewelry_create_earrings_spec.name == "jewelry_create_earrings"
        assert jewelry_create_brooch_spec.name == "jewelry_create_brooch"
        assert jewelry_create_cufflink_spec.name == "jewelry_create_cufflink"
        assert jewelry_create_bangle_spec.name == "jewelry_create_bangle"

    def test_tool_specs_have_input_schema(self):
        from kerf_cad_core.jewelry.pieces import (
            jewelry_create_pendant_spec,
            jewelry_create_earrings_spec,
            jewelry_create_brooch_spec,
            jewelry_create_cufflink_spec,
            jewelry_create_bangle_spec,
        )
        for spec in [
            jewelry_create_pendant_spec,
            jewelry_create_earrings_spec,
            jewelry_create_brooch_spec,
            jewelry_create_cufflink_spec,
            jewelry_create_bangle_spec,
        ]:
            assert "file_id" in spec.input_schema["properties"], \
                f"{spec.name} missing file_id in schema"
            assert "file_id" in spec.input_schema["required"], \
                f"{spec.name} file_id not in required"

    def test_pieces_in_plugin_tool_modules(self):
        """Verify plugin.py lists kerf_cad_core.jewelry.pieces."""
        from kerf_cad_core.plugin import _TOOL_MODULES
        assert "kerf_cad_core.jewelry.pieces" in _TOOL_MODULES


# ===========================================================================
# OCC-gated section (skipped when OCC absent)
# ===========================================================================

@pytestmark_occ
class TestPiecesOCCGated:
    """Smoke tests that require pythonOCC.

    These only verify the node spec structure produced by the builders
    matches what the occtWorker would expect.  Full tessellation is
    tested in the JS occtWorker test suite.
    """

    def test_pendant_composite_ops_present(self):
        p = compute_pendant_params()
        assert "pendant_frame" in p["composite_ops"]
        assert "bail_mount" in p["composite_ops"]

    def test_earrings_composite_ops_present(self):
        p = compute_earring_params(style="stud")
        assert "earring_face" in p["composite_ops"]

    def test_brooch_composite_ops_present(self):
        p = compute_brooch_params()
        assert "brooch_frame" in p["composite_ops"]

    def test_cufflink_composite_ops_present(self):
        p = compute_cufflink_params()
        assert "cufflink_face" in p["composite_ops"]

    def test_bangle_composite_ops_present(self):
        p = compute_bangle_params()
        assert "bangle_sweep" in p["composite_ops"]
