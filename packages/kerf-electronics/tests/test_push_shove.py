"""Verification suite for kerf_electronics.routing.push_shove (T-102).

Targets the core geometry algorithm module directly (the existing
test_routing / test_shove_router suites cover the tools/ LLM wrappers,
not this module).
"""
from __future__ import annotations

import math

import pytest

from kerf_electronics.routing.push_shove import (
    push_shove_segment,
    route_diff_pair,
    tune_diff_pair_skew,
    validate_diff_pair,
)


def _seg(sid, net, x0, y0, x1, y1, layer="top_copper", width=0.2):
    return {
        "id": sid, "net_id": net, "layer": layer, "width_mm": width,
        "start": {"x": x0, "y": y0}, "end": {"x": x1, "y": y1},
    }


def _seg_gap(a, b):
    """Perpendicular gap between two parallel horizontal segments."""
    return abs(a["start"]["y"] - b["start"]["y"])


# ---------------------------------------------------------------------------
# push_shove_segment
# ---------------------------------------------------------------------------


def test_far_segment_not_shoved():
    existing = [_seg("e1", "GND", 0, 50, 10, 50)]
    new = _seg("n1", "SIG", 0, 0, 10, 0)
    res = push_shove_segment(existing, new, {}, {"clearance_mm": 0.2})
    assert res["conflicts_resolved"] == 0
    assert res["shoved_segments"][0]["start"]["y"] == 50


def test_close_segment_is_shoved_clear():
    existing = [_seg("e1", "GND", 0, 0.1, 10, 0.1)]
    new = _seg("n1", "SIG", 0, 0, 10, 0, width=0.2)
    rules = {"clearance_mm": 0.5}
    res = push_shove_segment(existing, new, {}, rules)
    assert res["conflicts_resolved"] == 1
    moved = res["shoved_segments"][0]
    required = 0.5 + 0.2 / 2 + 0.2 / 2
    assert _seg_gap(moved, new) >= required - 1e-6


def test_same_net_not_shoved():
    existing = [_seg("e1", "SIG", 0, 0.05, 10, 0.05)]
    new = _seg("n1", "SIG", 0, 0, 10, 0)
    res = push_shove_segment(existing, new, {}, {"clearance_mm": 0.5})
    assert res["conflicts_resolved"] == 0


def test_other_layer_not_shoved():
    existing = [_seg("e1", "GND", 0, 0.05, 10, 0.05, layer="bottom_copper")]
    new = _seg("n1", "SIG", 0, 0, 10, 0, layer="top_copper")
    res = push_shove_segment(existing, new, {}, {"clearance_mm": 0.5})
    assert res["conflicts_resolved"] == 0


def test_input_segments_not_mutated():
    existing = [_seg("e1", "GND", 0, 0.05, 10, 0.05)]
    new = _seg("n1", "SIG", 0, 0, 10, 0)
    push_shove_segment(existing, new, {}, {"clearance_mm": 0.5})
    assert existing[0]["start"]["y"] == 0.05  # original untouched


def test_min_trace_spacing_fallback_used():
    existing = [_seg("e1", "GND", 0, 0.05, 10, 0.05)]
    new = _seg("n1", "SIG", 0, 0, 10, 0)
    res = push_shove_segment(
        existing, new, {}, {"min_trace_spacing_mm": 0.4}
    )
    assert res["conflicts_resolved"] == 1


# ---------------------------------------------------------------------------
# route_diff_pair
# ---------------------------------------------------------------------------


def test_route_straight_pair_offsets_by_spacing():
    sp, sn, vias = route_diff_pair(
        "D+", "D-", {"x": 0, "y": 0}, {"x": 10, "y": 0}, 0.2,
        {"default_layer": "top_copper"},
    )
    assert len(sp) == 1 and len(sn) == 1
    assert vias == []
    assert sp[0]["net_id"] == "D+"
    assert sn[0]["net_id"] == "D-"
    # centre-to-centre separation == spacing
    gap = abs(sp[0]["start"]["y"] - sn[0]["start"]["y"])
    assert gap == pytest.approx(0.2, abs=1e-6)


def test_route_l_shaped_pair_has_two_legs():
    sp, sn, vias = route_diff_pair(
        "D+", "D-", {"x": 0, "y": 0}, {"x": 10, "y": 8}, 0.25, {}
    )
    assert len(sp) == 2 and len(sn) == 2
    assert vias == []


# ---------------------------------------------------------------------------
# tune_diff_pair_skew
# ---------------------------------------------------------------------------


def test_skew_already_matched_is_noop():
    pair = {
        "segs_pos": [_seg("p", "D+", 0, 0, 10, 0)],
        "segs_neg": [_seg("n", "D-", 0, 1, 10, 1)],
    }
    out = tune_diff_pair_skew(pair, target_length_diff_mm=0.0)
    assert out["delta_mm"] == pytest.approx(0.0, abs=1e-6)
    assert out["length_pos_mm"] == pytest.approx(10.0)
    assert out["length_neg_mm"] == pytest.approx(10.0)


def test_skew_lengthens_shorter_conductor():
    pair = {
        "segs_pos": [_seg("p", "D+", 0, 0, 12, 0)],   # 12 mm
        "segs_neg": [_seg("n", "D-", 0, 1, 10, 1)],   # 10 mm
    }
    out = tune_diff_pair_skew(pair, target_length_diff_mm=0.0)
    # neg is shorter → it must get lengthened toward pos
    assert out["length_neg_mm"] > 10.0
    assert out["delta_mm"] < 2.0  # skew reduced from the original 2 mm
    assert set(out) >= {
        "segs_pos", "segs_neg", "length_pos_mm", "length_neg_mm", "delta_mm",
    }


# ---------------------------------------------------------------------------
# validate_diff_pair
# ---------------------------------------------------------------------------


def test_validate_well_formed_pair_ok():
    sp, sn, _ = route_diff_pair(
        "D+", "D-", {"x": 0, "y": 0}, {"x": 10, "y": 0}, 0.2,
        {"default_layer": "top_copper"},
    )
    res = validate_diff_pair(
        sp, sn, {"coupling_spacing_mm": 0.2, "skew_max_mm": 0.1}
    )
    assert res["ok"] is True
    assert res["violations"] == []


def test_validate_too_close_flags_spacing():
    sp = [_seg("p", "D+", 0, 0, 10, 0)]
    sn = [_seg("n", "D-", 0, 0.05, 10, 0.05)]
    res = validate_diff_pair(sp, sn, {"coupling_spacing_mm": 0.2})
    assert res["ok"] is False
    assert any(v["type"] == "spacing_too_close" for v in res["violations"])


def test_validate_length_mismatch_flagged():
    sp = [_seg("p", "D+", 0, 0, 10, 0)]       # 10 mm
    sn = [_seg("n", "D-", 0, 0.2, 12, 0.2)]   # 12 mm, coupling ok
    res = validate_diff_pair(
        sp, sn, {"coupling_spacing_mm": 0.2, "skew_max_mm": 0.1}
    )
    assert res["ok"] is False
    assert any(v["type"] == "length_mismatch" for v in res["violations"])


def test_validate_too_many_vias_flagged():
    vias = [
        {"id": f"v{i}", "type": "via", "net_id": "D+", "layer": "top_copper",
         "start": {"x": 1, "y": 1}, "end": {"x": 1, "y": 1}}
        for i in range(5)
    ]
    res = validate_diff_pair(vias, [], {"max_vias": 4})
    assert res["ok"] is False
    assert any(v["type"] == "too_many_vias" for v in res["violations"])
