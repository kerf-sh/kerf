"""
Tests for kerf_cad_core.jewelry.setter_checklist

Pure-Python: no OCC, no database, no project context required.
All tests run hermetically.

Coverage:
  - Center stone sequenced before accent stones
  - Halo stones sequenced last
  - Three-stone: centre first, sides before accents
  - Side stones ordered by size (largest first within same role)
  - Prong workflow steps differ from bezel steps
  - Bezel steps differ from channel steps
  - Pavé steps differ from prong steps
  - Channel sequence logic (lay all stones, tap rails, mill, polish)
  - Per-stone instructions match setting type
  - Tool inventory aggregates uniquely across all steps
  - Tool inventory is sorted
  - time_estimate_total sums correctly
  - time_estimate_total returns total_hr
  - Large stone (> 4 mm) gets higher time estimate than small stone
  - QC checkpoint count >= 2 per step
  - Common pitfalls list non-empty for every supported type
  - Large carat diamond with prong → pitfall mentions carat
  - Brittle stone (emerald) with prong → pitfall mentions emerald
  - Small pavé stone (< 1.5 mm) → pitfall mentions magnification
  - tool_inventory called on empty checklist returns empty list
  - time_estimate_total called on empty checklist returns zero
  - Invalid piece (not a dict) returns error dict
  - Missing stones key returns error dict
  - Unknown setting_type gracefully falls back to prong
  - Unknown role gracefully falls back to accent
  - sequence_rank is 1-based and monotonically increasing
  - LLM tool run_jewelry_setter_checklist happy path
  - LLM tool returns error when piece missing
  - LLM tool run_jewelry_tool_inventory happy path
  - LLM tool run_jewelry_time_estimate_total happy path
  - LLM tool returns error when checklist missing
"""

from __future__ import annotations

import asyncio
import json

import pytest

from kerf_cad_core.jewelry.setter_checklist import (
    setter_checklist,
    tool_inventory,
    time_estimate_total,
    _WORKFLOWS,
    _TOOLS,
    _QC,
    _PITFALLS,
    _VALID_SETTING_TYPES,
    _time_for_stone,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _call_tool(fn, **kwargs) -> dict:
    """Call a (ctx, args: bytes) -> str tool and return parsed JSON."""
    raw = _run(fn(None, json.dumps(kwargs).encode()))
    return json.loads(raw)


def _simple_piece(**kwargs):
    """Minimal valid piece with a single center stone."""
    stones = kwargs.pop("stones", [{
        "id": "c1",
        "setting_type": "prong",
        "role": "center",
        "size_mm": 6.5,
        "stone_type": "diamond",
        "carat": 1.0,
    }])
    return {"stones": stones, **kwargs}


# ---------------------------------------------------------------------------
# Sequencing tests
# ---------------------------------------------------------------------------

def test_center_before_accent():
    piece = {
        "stones": [
            {"id": "acc1", "setting_type": "prong", "role": "accent", "size_mm": 2.0, "stone_type": "diamond"},
            {"id": "ctr1", "setting_type": "prong", "role": "center", "size_mm": 6.5, "stone_type": "diamond"},
        ]
    }
    cl = setter_checklist(piece)
    ids = [s["stone_id"] for s in cl]
    assert ids.index("ctr1") < ids.index("acc1")


def test_halo_set_last():
    piece = {
        "stones": [
            {"id": "h1", "setting_type": "pave", "role": "halo", "size_mm": 1.2, "stone_type": "diamond"},
            {"id": "acc1", "setting_type": "prong", "role": "accent", "size_mm": 2.5, "stone_type": "diamond"},
            {"id": "ctr1", "setting_type": "prong", "role": "center", "size_mm": 6.5, "stone_type": "diamond"},
        ]
    }
    cl = setter_checklist(piece)
    ranks = {s["stone_id"]: s["sequence_rank"] for s in cl}
    assert ranks["ctr1"] < ranks["acc1"] < ranks["h1"]


def test_three_stone_center_first():
    piece = {
        "stones": [
            {"id": "side_r", "setting_type": "prong", "role": "side", "size_mm": 4.0, "stone_type": "diamond"},
            {"id": "center", "setting_type": "prong", "role": "center", "size_mm": 7.0, "stone_type": "diamond"},
            {"id": "side_l", "setting_type": "prong", "role": "side", "size_mm": 4.0, "stone_type": "diamond"},
        ]
    }
    cl = setter_checklist(piece)
    ranks = {s["stone_id"]: s["sequence_rank"] for s in cl}
    assert ranks["center"] < ranks["side_r"]
    assert ranks["center"] < ranks["side_l"]


def test_sides_before_accents():
    piece = {
        "stones": [
            {"id": "acc1", "setting_type": "pave", "role": "accent", "size_mm": 1.5, "stone_type": "diamond"},
            {"id": "side1", "setting_type": "prong", "role": "side", "size_mm": 3.5, "stone_type": "diamond"},
            {"id": "ctr1", "setting_type": "prong", "role": "center", "size_mm": 6.5, "stone_type": "diamond"},
        ]
    }
    cl = setter_checklist(piece)
    ranks = {s["stone_id"]: s["sequence_rank"] for s in cl}
    assert ranks["side1"] < ranks["acc1"]


def test_larger_side_before_smaller_side():
    piece = {
        "stones": [
            {"id": "small_side", "setting_type": "prong", "role": "side", "size_mm": 3.0, "stone_type": "diamond"},
            {"id": "large_side", "setting_type": "prong", "role": "side", "size_mm": 5.0, "stone_type": "diamond"},
        ]
    }
    cl = setter_checklist(piece)
    ranks = {s["stone_id"]: s["sequence_rank"] for s in cl}
    assert ranks["large_side"] < ranks["small_side"]


# ---------------------------------------------------------------------------
# Setting-style workflow tests
# ---------------------------------------------------------------------------

def test_prong_steps_differ_from_bezel():
    prong_steps = _WORKFLOWS["prong"]
    bezel_steps = _WORKFLOWS["bezel"]
    assert prong_steps != bezel_steps
    assert any("prong" in s.lower() or "burnish" in s.lower() for s in prong_steps)
    assert any("push" in s.lower() for s in bezel_steps)


def test_bezel_steps_differ_from_channel():
    bezel_steps = _WORKFLOWS["bezel"]
    channel_steps = _WORKFLOWS["channel"]
    assert bezel_steps != channel_steps
    assert any("rail" in s.lower() or "channel" in s.lower() for s in channel_steps)


def test_pave_steps_differ_from_prong():
    pave_steps = _WORKFLOWS["pave"]
    prong_steps = _WORKFLOWS["prong"]
    assert pave_steps != prong_steps
    assert any("bead" in s.lower() or "drill" in s.lower() for s in pave_steps)


def test_channel_sequence_contains_lay_and_tap():
    channel_steps = _WORKFLOWS["channel"]
    combined = " ".join(channel_steps).lower()
    assert "lay" in combined or "place" in combined
    assert "tap" in combined or "inward" in combined
    assert "mill" in combined or "flush" in combined


def test_instructions_match_setting_type_prong():
    piece = _simple_piece()
    cl = setter_checklist(piece)
    step = cl[0]
    assert step["setting_type"] == "prong"
    combined = " ".join(step["instructions"]).lower()
    assert "prong" in combined or "burnish" in combined or "seat" in combined


def test_instructions_match_setting_type_bezel():
    piece = {
        "stones": [{"id": "b1", "setting_type": "bezel", "role": "center", "size_mm": 6.0, "stone_type": "ruby"}]
    }
    cl = setter_checklist(piece)
    combined = " ".join(cl[0]["instructions"]).lower()
    assert "bezel" in combined or "push" in combined or "burnish" in combined


def test_instructions_match_setting_type_channel():
    piece = {
        "stones": [
            {"id": "r1", "setting_type": "channel", "role": "row", "size_mm": 2.0, "stone_type": "diamond"},
            {"id": "r2", "setting_type": "channel", "role": "row", "size_mm": 2.0, "stone_type": "diamond"},
        ]
    }
    cl = setter_checklist(piece)
    for step in cl:
        combined = " ".join(step["instructions"]).lower()
        assert "channel" in combined or "rail" in combined or "tap" in combined


# ---------------------------------------------------------------------------
# Tool inventory tests
# ---------------------------------------------------------------------------

def test_tool_inventory_aggregates_uniquely():
    piece = {
        "stones": [
            {"id": "c1", "setting_type": "prong", "role": "center", "size_mm": 6.5, "stone_type": "diamond"},
            {"id": "a1", "setting_type": "prong", "role": "accent", "size_mm": 2.0, "stone_type": "diamond"},
        ]
    }
    cl = setter_checklist(piece)
    inv = tool_inventory(cl)
    tools = inv["tools"]
    assert len(tools) == len(set(tools)), "tool inventory must be deduplicated"


def test_tool_inventory_is_sorted():
    piece = {
        "stones": [
            {"id": "c1", "setting_type": "pave", "role": "center", "size_mm": 3.0, "stone_type": "diamond"},
            {"id": "a1", "setting_type": "bezel", "role": "accent", "size_mm": 2.0, "stone_type": "ruby"},
        ]
    }
    cl = setter_checklist(piece)
    inv = tool_inventory(cl)
    tools = inv["tools"]
    assert tools == sorted(tools)


def test_tool_inventory_empty_checklist():
    result = tool_inventory([])
    assert result == {"tools": []}


# ---------------------------------------------------------------------------
# Time estimate tests
# ---------------------------------------------------------------------------

def test_time_estimate_sums_correctly():
    piece = {
        "stones": [
            {"id": "c1", "setting_type": "prong", "role": "center", "size_mm": 6.5, "stone_type": "diamond"},
            {"id": "a1", "setting_type": "bezel", "role": "accent", "size_mm": 4.0, "stone_type": "ruby"},
        ]
    }
    cl = setter_checklist(piece)
    result = time_estimate_total(cl)
    expected = sum(s["time_estimate_min"] for s in cl)
    assert abs(result["total_min"] - expected) < 0.01


def test_time_estimate_returns_total_hr():
    piece = _simple_piece()
    cl = setter_checklist(piece)
    result = time_estimate_total(cl)
    assert "total_hr" in result
    assert abs(result["total_hr"] - result["total_min"] / 60.0) < 0.001


def test_time_estimate_zero_for_empty():
    result = time_estimate_total([])
    assert result["total_min"] == 0.0
    assert result["total_hr"] == 0.0


def test_large_stone_higher_time_than_small():
    time_large = _time_for_stone("prong", 6.0)
    time_small = _time_for_stone("prong", 2.0)
    assert time_large > time_small


# ---------------------------------------------------------------------------
# QC checkpoint tests
# ---------------------------------------------------------------------------

def test_qc_checkpoints_min_two_per_step():
    for setting_type in _VALID_SETTING_TYPES:
        qc = _QC.get(setting_type, [])
        assert len(qc) >= 2, f"{setting_type} needs at least 2 QC checkpoints"


# ---------------------------------------------------------------------------
# Pitfalls tests
# ---------------------------------------------------------------------------

def test_pitfalls_non_empty_for_all_types():
    for setting_type in _VALID_SETTING_TYPES:
        pitfalls = _PITFALLS.get(setting_type, [])
        assert len(pitfalls) >= 1, f"{setting_type} must have at least one pitfall"


def test_large_carat_diamond_prong_pitfall():
    piece = {
        "stones": [{"id": "c1", "setting_type": "prong", "role": "center",
                    "size_mm": 7.0, "stone_type": "diamond", "carat": 2.0}]
    }
    cl = setter_checklist(piece)
    pitfalls_combined = " ".join(cl[0]["common_pitfalls"]).lower()
    assert "2.00 ct" in pitfalls_combined or "carat" in pitfalls_combined


def test_brittle_stone_prong_pitfall():
    piece = {
        "stones": [{"id": "e1", "setting_type": "prong", "role": "center",
                    "size_mm": 6.0, "stone_type": "emerald", "carat": 1.0}]
    }
    cl = setter_checklist(piece)
    pitfalls_combined = " ".join(cl[0]["common_pitfalls"]).lower()
    assert "emerald" in pitfalls_combined or "brittle" in pitfalls_combined


def test_tiny_pave_stone_magnification_pitfall():
    piece = {
        "stones": [{"id": "p1", "setting_type": "pave", "role": "halo",
                    "size_mm": 1.2, "stone_type": "diamond", "carat": 0.01}]
    }
    cl = setter_checklist(piece)
    pitfalls_combined = " ".join(cl[0]["common_pitfalls"]).lower()
    assert "magnif" in pitfalls_combined or "1.5 mm" in pitfalls_combined


# ---------------------------------------------------------------------------
# Structural / edge-case tests
# ---------------------------------------------------------------------------

def test_sequence_rank_monotonically_increasing():
    piece = {
        "stones": [
            {"id": "c1", "setting_type": "prong", "role": "center", "size_mm": 6.5, "stone_type": "diamond"},
            {"id": "s1", "setting_type": "prong", "role": "side", "size_mm": 4.0, "stone_type": "diamond"},
            {"id": "a1", "setting_type": "pave", "role": "accent", "size_mm": 2.0, "stone_type": "diamond"},
            {"id": "h1", "setting_type": "pave", "role": "halo", "size_mm": 1.2, "stone_type": "diamond"},
        ]
    }
    cl = setter_checklist(piece)
    ranks = [s["sequence_rank"] for s in cl]
    assert ranks == list(range(1, len(ranks) + 1))


def test_invalid_piece_not_dict():
    result = setter_checklist("not a dict")
    assert isinstance(result, dict)
    assert result.get("ok") is False


def test_missing_stones_key():
    result = setter_checklist({"piece_type": "ring"})
    assert isinstance(result, dict)
    assert result.get("ok") is False


def test_unknown_setting_type_fallback():
    piece = {
        "stones": [{"id": "x1", "setting_type": "glue", "role": "center",
                    "size_mm": 5.0, "stone_type": "diamond"}]
    }
    cl = setter_checklist(piece)
    assert isinstance(cl, list)
    assert cl[0]["setting_type"] == "prong"


def test_unknown_role_fallback():
    piece = {
        "stones": [{"id": "x1", "setting_type": "prong", "role": "mysterious",
                    "size_mm": 5.0, "stone_type": "diamond"}]
    }
    cl = setter_checklist(piece)
    assert isinstance(cl, list)
    assert cl[0]["role"] == "accent"


# ---------------------------------------------------------------------------
# LLM tool tests
# ---------------------------------------------------------------------------

def test_llm_setter_checklist_happy_path():
    from kerf_cad_core.jewelry.setter_checklist import run_jewelry_setter_checklist
    piece = _simple_piece()
    result = _call_tool(run_jewelry_setter_checklist, piece=piece)
    # ok_payload returns the data directly; error is signalled by "error" key.
    assert "error" not in result
    assert "checklist" in result
    assert result["step_count"] >= 1


def test_llm_setter_checklist_missing_piece():
    from kerf_cad_core.jewelry.setter_checklist import run_jewelry_setter_checklist
    result = _call_tool(run_jewelry_setter_checklist)
    assert "error" in result
    assert result.get("code") == "BAD_ARGS"


def test_llm_tool_inventory_happy_path():
    from kerf_cad_core.jewelry.setter_checklist import (
        run_jewelry_setter_checklist,
        run_jewelry_tool_inventory,
    )
    piece = _simple_piece()
    cl_result = _call_tool(run_jewelry_setter_checklist, piece=piece)
    checklist = cl_result["checklist"]
    inv_result = _call_tool(run_jewelry_tool_inventory, checklist=checklist)
    assert "error" not in inv_result
    assert "tools" in inv_result
    assert len(inv_result["tools"]) > 0


def test_llm_time_estimate_total_happy_path():
    from kerf_cad_core.jewelry.setter_checklist import (
        run_jewelry_setter_checklist,
        run_jewelry_time_estimate_total,
    )
    piece = _simple_piece()
    cl_result = _call_tool(run_jewelry_setter_checklist, piece=piece)
    checklist = cl_result["checklist"]
    t_result = _call_tool(run_jewelry_time_estimate_total, checklist=checklist)
    assert "error" not in t_result
    assert t_result["total_min"] > 0


def test_llm_time_estimate_missing_checklist():
    from kerf_cad_core.jewelry.setter_checklist import run_jewelry_time_estimate_total
    result = _call_tool(run_jewelry_time_estimate_total)
    assert "error" in result
    assert result.get("code") == "BAD_ARGS"
