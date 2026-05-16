"""
Hermetic tests for kerf_cad_core.jewelry.cam_wax — wax-routing CAM planner.

Coverage (≥ 25 tests):
  plan_wax_routing — input validation, roughing pass count, finishing coverage,
                     cycle-time monotonicity in volume, tool-list completeness,
                     collision / clamp warnings, 4-axis vs 5-axis RTCP,
                     pendant / ring / setting piece types, error paths.
  _plan_roughing   — pass count vs Z-extent and step_down_mm
  _plan_finishing  — stepover vs tool diameter, bore passes for rings
  _estimate_cycle_time — monotone in stock volume
  _check_clamp_proximity — warning conditions
  _select_tools    — priority selection from mixed library
  _parse_tool_library / _parse_machine / _parse_stock — validation

All tests are pure-Python and hermetic: no OCC, no DB, no network.

Author: imranparuk
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.jewelry.cam_wax import (
    plan_wax_routing,
    _plan_roughing,
    _plan_finishing,
    _estimate_cycle_time,
    _check_clamp_proximity,
    _select_tools,
    _parse_tool_library,
    _parse_machine,
    _parse_stock,
    _ToolEntry,
    _StockBlock,
    _MachineKinematics,
    _ROUGH_STEPDWN_DEFAULT,
    _FINISH_STEPOVER_FRAC,
    _CLAMP_CLEARANCE_MM,
    _PRONG_TILT_DEG,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

RING_PIECE = {
    "type": "ring",
    "inner_diameter_mm": 17.5,
    "height_mm": 8.0,
    "width_mm": 20.0,
    "depth_mm": 20.0,
}

PENDANT_PIECE = {
    "type": "pendant",
    "height_mm": 12.0,
    "width_mm": 25.0,
    "depth_mm": 15.0,
}

SETTING_PIECE = {
    "type": "setting",
    "has_prongs": True,
    "height_mm": 6.0,
    "width_mm": 10.0,
    "depth_mm": 10.0,
}

STOCK_20x20x15 = {"width_mm": 20.0, "depth_mm": 20.0, "height_mm": 15.0}
STOCK_30x30x20 = {"width_mm": 30.0, "depth_mm": 30.0, "height_mm": 20.0}
STOCK_40x40x30 = {"width_mm": 40.0, "depth_mm": 40.0, "height_mm": 30.0}

MACHINE_4AXIS = {"type": "4axis_indexed", "pivot_mm": 50.0}
MACHINE_5AXIS_TRUNNION = {
    "type": "5axis_trunnion",
    "pivot_mm": 60.0,
    "a_lo_deg": -120.0,
    "a_hi_deg": 30.0,
    "rapid_mm_min": 10000.0,
    "accel_mm_s2": 500.0,
}
MACHINE_5AXIS_HEAD = {
    "type": "5axis_head_head",
    "pivot_mm": 55.0,
    "rapid_mm_min": 8000.0,
    "accel_mm_s2": 400.0,
}

TOOL_FLAT_END = {
    "name": "flat_3mm",
    "type": "flat_end",
    "diameter_mm": 3.0,
    "flutes": 4,
    "stickout_mm": 20.0,
    "vc_m_min": 45.0,
    "chip_load_mm": 0.020,
}
TOOL_BALL_NOSE = {
    "name": "ball_1mm",
    "type": "ball_nose",
    "diameter_mm": 1.0,
    "flutes": 2,
    "stickout_mm": 15.0,
    "vc_m_min": 60.0,
    "chip_load_mm": 0.010,
}
TOOL_BALL_2MM = {
    "name": "ball_2mm",
    "type": "ball_nose",
    "diameter_mm": 2.0,
    "flutes": 2,
    "stickout_mm": 18.0,
    "vc_m_min": 55.0,
    "chip_load_mm": 0.012,
}
TOOL_FISHTAIL = {
    "name": "fish_1mm",
    "type": "fishtail",
    "diameter_mm": 1.0,
    "flutes": 2,
    "stickout_mm": 15.0,
    "vc_m_min": 50.0,
    "chip_load_mm": 0.015,
}

FULL_LIBRARY = [TOOL_FLAT_END, TOOL_BALL_NOSE, TOOL_FISHTAIL, TOOL_BALL_2MM]


# ---------------------------------------------------------------------------
# 1. plan_wax_routing — basic happy path (ring, 4-axis)
# ---------------------------------------------------------------------------

def test_plan_wax_routing_ring_4axis_ok():
    result = plan_wax_routing(
        RING_PIECE, MACHINE_4AXIS, FULL_LIBRARY, STOCK_20x20x15
    )
    assert result["ok"] is True
    assert "roughing_strategy" in result
    assert "finishing_strategy" in result
    assert "gcode_stubs" in result
    assert "cycle_time_s" in result
    assert "tool_list" in result
    assert "collision_warnings" in result
    assert result["machine_type"] == "4axis_indexed"


# ---------------------------------------------------------------------------
# 2. plan_wax_routing — pendant, 5-axis trunnion
# ---------------------------------------------------------------------------

def test_plan_wax_routing_pendant_5axis_ok():
    result = plan_wax_routing(
        PENDANT_PIECE, MACHINE_5AXIS_TRUNNION, FULL_LIBRARY, STOCK_30x30x20
    )
    assert result["ok"] is True
    assert result["machine_type"] == "5axis_trunnion"


# ---------------------------------------------------------------------------
# 3. plan_wax_routing — setting with prongs, 5-axis head-head
# ---------------------------------------------------------------------------

def test_plan_wax_routing_setting_5axis_head_ok():
    result = plan_wax_routing(
        SETTING_PIECE, MACHINE_5AXIS_HEAD, FULL_LIBRARY, STOCK_20x20x15
    )
    assert result["ok"] is True
    assert result["machine_type"] == "5axis_head_head"
    finish = result["finishing_strategy"]
    # Setting has prongs — prong_passes must be present
    assert len(finish.get("prong_passes", [])) >= 1


# ---------------------------------------------------------------------------
# 4. Roughing pass count matches Z-extent / step_down_mm
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("height_mm,step_down_mm,expected_min", [
    (10.0, 1.0,  10),
    (10.0, 0.5,  20),
    (10.0, 2.0,   5),
    (15.0, 0.8,  math.ceil(15.0 / 0.8)),
    (20.0, 1.5,  math.ceil(20.0 / 1.5)),
])
def test_roughing_pass_count_matches_z_extent(height_mm, step_down_mm, expected_min):
    stock = _StockBlock(width_mm=20.0, depth_mm=20.0, height_mm=height_mm)
    tool = _ToolEntry(
        name="t", tool_type="flat_end", diameter_mm=3.0, flutes=4,
        stickout_mm=20.0, vc_m_min=45.0, chip_load_mm=0.02,
    )
    machine = _MachineKinematics(machine_type="4axis_indexed", pivot_mm=50.0)
    piece = {"type": "ring", "height_mm": height_mm}
    plan = _plan_roughing(piece, stock, tool, step_down_mm, machine)
    assert plan["pass_count"] >= expected_min


# ---------------------------------------------------------------------------
# 5. Roughing pass count: actual step * passes covers full Z extent
# ---------------------------------------------------------------------------

def test_roughing_passes_cover_full_z_extent():
    stock = _StockBlock(width_mm=25.0, depth_mm=25.0, height_mm=12.0)
    tool = _ToolEntry(
        name="t", tool_type="flat_end", diameter_mm=3.0, flutes=4,
        stickout_mm=20.0, vc_m_min=45.0, chip_load_mm=0.02,
    )
    machine = _MachineKinematics(machine_type="4axis_indexed", pivot_mm=50.0)
    piece = {"type": "pendant", "height_mm": 12.0}
    plan = _plan_roughing(piece, stock, tool, 0.9, machine)
    actual_step = plan["step_down_mm"]
    n = plan["pass_count"]
    covered = actual_step * n
    assert abs(covered - 12.0) < 1e-3  # rounding to 4 dp may introduce sub-mm error


# ---------------------------------------------------------------------------
# 6. Finishing stepover is a fraction of tool diameter
# ---------------------------------------------------------------------------

def test_finishing_stepover_fraction_of_tool_diameter():
    stock = _StockBlock(width_mm=20.0, depth_mm=20.0, height_mm=10.0)
    tool = _ToolEntry(
        name="ball_1mm", tool_type="ball_nose", diameter_mm=1.0, flutes=2,
        stickout_mm=15.0, vc_m_min=60.0, chip_load_mm=0.01,
    )
    machine = _MachineKinematics(machine_type="5axis_trunnion", pivot_mm=50.0)
    piece = {"type": "pendant", "height_mm": 10.0, "width_mm": 20.0, "depth_mm": 20.0}
    plan = _plan_finishing(piece, stock, tool, machine)
    expected_stepover = tool.diameter_mm * _FINISH_STEPOVER_FRAC
    assert abs(plan["stepover_mm"] - expected_stepover) < 1e-9


# ---------------------------------------------------------------------------
# 7. Finishing pass count scales with surface width
# ---------------------------------------------------------------------------

def test_finishing_pass_count_scales_with_width():
    stock_small = _StockBlock(width_mm=10.0, depth_mm=10.0, height_mm=10.0)
    stock_large = _StockBlock(width_mm=30.0, depth_mm=30.0, height_mm=10.0)
    tool = _ToolEntry(
        name="b", tool_type="ball_nose", diameter_mm=1.0, flutes=2,
        stickout_mm=15.0, vc_m_min=60.0, chip_load_mm=0.01,
    )
    machine = _MachineKinematics(machine_type="5axis_trunnion", pivot_mm=50.0)
    piece_small = {"type": "pendant", "width_mm": 10.0, "depth_mm": 10.0, "height_mm": 10.0}
    piece_large = {"type": "pendant", "width_mm": 30.0, "depth_mm": 30.0, "height_mm": 10.0}
    plan_s = _plan_finishing(piece_small, stock_small, tool, machine)
    plan_l = _plan_finishing(piece_large, stock_large, tool, machine)
    assert plan_l["n_surface_passes"] > plan_s["n_surface_passes"]


# ---------------------------------------------------------------------------
# 8. Cycle time is monotone in stock volume
# ---------------------------------------------------------------------------

def test_cycle_time_monotone_in_volume():
    """Larger stock → more material → longer cycle time."""
    tool = _ToolEntry(
        name="r", tool_type="flat_end", diameter_mm=3.0, flutes=4,
        stickout_mm=20.0, vc_m_min=45.0, chip_load_mm=0.02,
    )
    finish_tool = _ToolEntry(
        name="f", tool_type="ball_nose", diameter_mm=1.0, flutes=2,
        stickout_mm=15.0, vc_m_min=60.0, chip_load_mm=0.01,
    )
    machine = _MachineKinematics(machine_type="5axis_trunnion", pivot_mm=50.0)

    stocks = [
        _StockBlock(15.0, 15.0, 10.0),
        _StockBlock(20.0, 20.0, 15.0),
        _StockBlock(30.0, 30.0, 20.0),
    ]
    times = []
    for s in stocks:
        piece = {"type": "pendant", "width_mm": s.width_mm, "depth_mm": s.depth_mm, "height_mm": s.height_mm}
        rough = _plan_roughing(piece, s, tool, 0.8, machine)
        finish = _plan_finishing(piece, s, finish_tool, machine)
        t = _estimate_cycle_time(rough, finish, machine, s)
        times.append(t)

    assert times[1] > times[0]
    assert times[2] > times[1]


# ---------------------------------------------------------------------------
# 9. Tool list contains every requested tool type
# ---------------------------------------------------------------------------

def test_tool_list_contains_all_requested_tools():
    result = plan_wax_routing(
        RING_PIECE, MACHINE_4AXIS, FULL_LIBRARY, STOCK_20x20x15
    )
    assert result["ok"] is True
    tool_names = {t["name"] for t in result["tool_list"]}
    # flat_end for roughing, ball_nose for finishing, fishtail for undercuts
    assert any(t["type"] == "flat_end" for t in result["tool_list"])
    assert any(t["type"] == "ball_nose" for t in result["tool_list"])
    assert any(t["type"] == "fishtail" for t in result["tool_list"])


# ---------------------------------------------------------------------------
# 10. Collision / clamp warning fires when piece is placed near clamp
# ---------------------------------------------------------------------------

def test_collision_warning_fires_near_clamp():
    stock = _StockBlock(width_mm=20.0, depth_mm=20.0, height_mm=15.0)
    # piece placed right at stock edge (y_offset=0, depth=18mm → rear gap = 2mm < 3mm)
    piece = {
        "type": "ring",
        "height_mm": 8.0,
        "width_mm": 20.0,
        "depth_mm": 18.0,  # leaves only 2mm at rear
        "y_offset_mm": 0.0,
    }
    warnings = _check_clamp_proximity(piece, stock, clamp_clearance_mm=3.0)
    assert len(warnings) > 0
    assert any("clamp_proximity" in w for w in warnings)


# ---------------------------------------------------------------------------
# 11. No collision warning when piece is well-centred in stock
# ---------------------------------------------------------------------------

def test_no_collision_warning_centred_piece():
    stock = _StockBlock(width_mm=40.0, depth_mm=40.0, height_mm=20.0)
    piece = {
        "type": "pendant",
        "height_mm": 12.0,
        "width_mm": 20.0,
        "depth_mm": 20.0,
        "y_offset_mm": 10.0,   # 10mm from front, 10mm at rear
    }
    warnings = _check_clamp_proximity(piece, stock, clamp_clearance_mm=3.0)
    assert len(warnings) == 0


# ---------------------------------------------------------------------------
# 12. Ring near clamp fires height warning
# ---------------------------------------------------------------------------

def test_ring_height_clamp_warning():
    stock = _StockBlock(width_mm=20.0, depth_mm=20.0, height_mm=10.0)
    piece = {
        "type": "ring",
        "height_mm": 8.5,   # leaves only 1.5mm above ring < 3mm
        "width_mm": 18.0,
        "depth_mm": 18.0,
        "y_offset_mm": 5.0,
    }
    warnings = _check_clamp_proximity(piece, stock, clamp_clearance_mm=3.0)
    assert any("ring height" in w for w in warnings)


# ---------------------------------------------------------------------------
# 13. 4-axis indexed produces bore passes at 0, 90, 180, 270 degrees
# ---------------------------------------------------------------------------

def test_4axis_indexed_bore_passes_at_quadrants():
    stock = _StockBlock(width_mm=20.0, depth_mm=20.0, height_mm=15.0)
    tool = _ToolEntry(
        name="b", tool_type="ball_nose", diameter_mm=1.0, flutes=2,
        stickout_mm=15.0, vc_m_min=60.0, chip_load_mm=0.01,
    )
    machine = _MachineKinematics(machine_type="4axis_indexed", pivot_mm=50.0)
    piece = {"type": "ring", "inner_diameter_mm": 17.5, "height_mm": 10.0, "width_mm": 20.0, "depth_mm": 20.0}
    plan = _plan_finishing(piece, stock, tool, machine)
    bore_passes = plan["bore_passes"]
    assert len(bore_passes) == 4
    angles = {bp["a_angle_deg"] for bp in bore_passes}
    assert angles == {0.0, 90.0, 180.0, 270.0}


# ---------------------------------------------------------------------------
# 14. True 5-axis trunnion produces continuous bore passes (not indexed)
# ---------------------------------------------------------------------------

def test_5axis_trunnion_bore_passes_continuous():
    stock = _StockBlock(width_mm=22.0, depth_mm=22.0, height_mm=15.0)
    tool = _ToolEntry(
        name="b", tool_type="ball_nose", diameter_mm=1.0, flutes=2,
        stickout_mm=15.0, vc_m_min=60.0, chip_load_mm=0.01,
    )
    machine = _MachineKinematics(machine_type="5axis_trunnion", pivot_mm=60.0)
    piece = {"type": "ring", "inner_diameter_mm": 17.5, "height_mm": 10.0, "width_mm": 22.0, "depth_mm": 22.0}
    plan = _plan_finishing(piece, stock, tool, machine)
    bore_passes = plan["bore_passes"]
    assert all(bp["pass_type"] == "bore_5axis_continuous" for bp in bore_passes)


# ---------------------------------------------------------------------------
# 15. 4-axis vs true-5-axis produces different RTCP outputs
# ---------------------------------------------------------------------------

def test_4axis_vs_5axis_different_rtcp_outputs():
    piece = {
        "type": "ring",
        "inner_diameter_mm": 17.5,
        "height_mm": 10.0,
        "width_mm": 20.0,
        "depth_mm": 20.0,
    }
    result_4 = plan_wax_routing(
        piece, MACHINE_4AXIS, FULL_LIBRARY, STOCK_20x20x15
    )
    result_5 = plan_wax_routing(
        piece, MACHINE_5AXIS_TRUNNION, FULL_LIBRARY, STOCK_20x20x15
    )
    rtcp_4 = result_4["finishing_strategy"]["rtcp"]
    rtcp_5 = result_5["finishing_strategy"]["rtcp"]
    assert rtcp_4.get("rtcp") is False     # 4-axis indexed — no RTCP
    assert rtcp_5.get("rtcp") is True      # 5-axis — RTCP enabled


# ---------------------------------------------------------------------------
# 16. Error: missing required fields in piece
# ---------------------------------------------------------------------------

def test_error_missing_piece_type_still_succeeds():
    """Piece without type should still plan (defaults to pendant-like)."""
    piece = {"height_mm": 8.0, "width_mm": 20.0, "depth_mm": 20.0}
    result = plan_wax_routing(piece, MACHINE_4AXIS, [TOOL_FLAT_END], STOCK_20x20x15)
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# 17. Error: empty tool_library
# ---------------------------------------------------------------------------

def test_error_empty_tool_library():
    result = plan_wax_routing(RING_PIECE, MACHINE_4AXIS, [], STOCK_20x20x15)
    assert result["ok"] is False
    assert "tool_library" in result["reason"]


# ---------------------------------------------------------------------------
# 18. Error: invalid machine type
# ---------------------------------------------------------------------------

def test_error_invalid_machine_type():
    machine = {"type": "3axis_router"}
    result = plan_wax_routing(RING_PIECE, machine, FULL_LIBRARY, STOCK_20x20x15)
    assert result["ok"] is False
    assert "3axis_router" in result["reason"]


# ---------------------------------------------------------------------------
# 19. Error: negative stock dimension
# ---------------------------------------------------------------------------

def test_error_negative_stock_dimension():
    bad_stock = {"width_mm": -5.0, "depth_mm": 20.0, "height_mm": 15.0}
    result = plan_wax_routing(RING_PIECE, MACHINE_4AXIS, FULL_LIBRARY, bad_stock)
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# 20. Error: invalid tool type in library
# ---------------------------------------------------------------------------

def test_error_invalid_tool_type():
    bad_tool = {
        "name": "bad",
        "type": "laser_cutter",
        "diameter_mm": 3.0,
        "flutes": 4,
        "stickout_mm": 20.0,
    }
    result = plan_wax_routing(RING_PIECE, MACHINE_4AXIS, [bad_tool], STOCK_20x20x15)
    assert result["ok"] is False
    assert "laser_cutter" in result["reason"]


# ---------------------------------------------------------------------------
# 21. Error: missing tool diameter
# ---------------------------------------------------------------------------

def test_error_missing_tool_diameter():
    bad_tool = {"name": "x", "type": "ball_nose", "flutes": 2, "stickout_mm": 15.0}
    _, errors = _parse_tool_library([bad_tool])
    assert any("diameter_mm" in e for e in errors)


# ---------------------------------------------------------------------------
# 22. G-code stubs contain essential structure
# ---------------------------------------------------------------------------

def test_gcode_stubs_contain_required_structure():
    result = plan_wax_routing(
        RING_PIECE, MACHINE_4AXIS, FULL_LIBRARY, STOCK_20x20x15
    )
    assert result["ok"] is True
    gcode = "\n".join(result["gcode_stubs"])
    assert "G21" in gcode          # metric
    assert "M30" in gcode          # end of program
    assert "T1 M6" in gcode        # tool change
    assert "S" in gcode            # spindle speed


# ---------------------------------------------------------------------------
# 23. Tool selection: largest flat-end for roughing, smallest ball-nose for finish
# ---------------------------------------------------------------------------

def test_tool_selection_priority():
    library = [
        _ToolEntry("big_flat", "flat_end", 6.0, 4, 25.0, 45.0, 0.02),
        _ToolEntry("small_flat", "flat_end", 3.0, 4, 20.0, 45.0, 0.02),
        _ToolEntry("big_ball", "ball_nose", 2.0, 2, 18.0, 60.0, 0.012),
        _ToolEntry("small_ball", "ball_nose", 0.8, 2, 12.0, 60.0, 0.008),
        _ToolEntry("fish", "fishtail", 1.0, 2, 15.0, 50.0, 0.015),
    ]
    stock = _StockBlock(20.0, 20.0, 15.0)
    rough, finish, undercut = _select_tools(library, RING_PIECE, stock)
    assert rough.name == "big_flat"
    assert finish.name == "small_ball"
    assert undercut is not None
    assert undercut.tool_type == "fishtail"


# ---------------------------------------------------------------------------
# 24. Cycle time > 0 for non-trivial stock
# ---------------------------------------------------------------------------

def test_cycle_time_positive():
    result = plan_wax_routing(
        RING_PIECE, MACHINE_5AXIS_TRUNNION, FULL_LIBRARY, STOCK_30x30x20
    )
    assert result["ok"] is True
    assert result["cycle_time_s"] > 0.0


# ---------------------------------------------------------------------------
# 25. Roughing pass count is exactly ceil(z_extent / step_down)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("z_extent,step_down", [
    (7.5, 0.8),
    (10.0, 1.0),
    (13.3, 0.75),
    (5.0, 2.5),
])
def test_roughing_pass_count_exact_ceil(z_extent, step_down):
    stock = _StockBlock(width_mm=20.0, depth_mm=20.0, height_mm=z_extent)
    tool = _ToolEntry("t", "flat_end", 3.0, 4, 20.0, 45.0, 0.02)
    machine = _MachineKinematics("4axis_indexed", 50.0)
    piece = {"type": "pendant", "height_mm": z_extent}
    plan = _plan_roughing(piece, stock, tool, step_down, machine)
    expected = math.ceil(z_extent / step_down)
    assert plan["pass_count"] == expected


# ---------------------------------------------------------------------------
# 26. Passes list length matches pass_count
# ---------------------------------------------------------------------------

def test_roughing_passes_list_length_matches_pass_count():
    stock = _StockBlock(20.0, 20.0, 12.0)
    tool = _ToolEntry("t", "flat_end", 3.0, 4, 20.0, 45.0, 0.02)
    machine = _MachineKinematics("5axis_trunnion", 50.0)
    piece = {"type": "ring", "height_mm": 12.0}
    plan = _plan_roughing(piece, stock, tool, 0.8, machine)
    assert len(plan["passes"]) == plan["pass_count"]


# ---------------------------------------------------------------------------
# 27. Parse machine: valid types accepted, invalid rejected
# ---------------------------------------------------------------------------

def test_parse_machine_valid_types():
    for mtype in ("4axis_indexed", "5axis_trunnion", "5axis_head_head"):
        machine, err = _parse_machine({"type": mtype, "pivot_mm": 50.0})
        assert err is None
        assert machine.machine_type == mtype


def test_parse_machine_invalid_type():
    _, err = _parse_machine({"type": "6axis_robot"})
    assert err is not None
    assert "6axis_robot" in err


# ---------------------------------------------------------------------------
# 28. Parse stock: valid and invalid
# ---------------------------------------------------------------------------

def test_parse_stock_valid():
    stock, err = _parse_stock({"width_mm": 20.0, "depth_mm": 15.0, "height_mm": 10.0})
    assert err is None
    assert stock.volume_mm3 == pytest.approx(20.0 * 15.0 * 10.0)


def test_parse_stock_zero_dimension():
    _, err = _parse_stock({"width_mm": 0.0, "depth_mm": 15.0, "height_mm": 10.0})
    assert err is not None


# ---------------------------------------------------------------------------
# 29. Finishing: has_bore_finishing only for rings with adequate inner diameter
# ---------------------------------------------------------------------------

def test_finishing_bore_only_for_rings():
    stock = _StockBlock(22.0, 22.0, 15.0)
    tool = _ToolEntry("b", "ball_nose", 1.0, 2, 15.0, 60.0, 0.01)
    machine = _MachineKinematics("5axis_trunnion", 60.0)

    ring_piece = {"type": "ring", "inner_diameter_mm": 17.5, "height_mm": 10.0, "width_mm": 22.0, "depth_mm": 22.0}
    pendant_piece = {"type": "pendant", "height_mm": 10.0, "width_mm": 22.0, "depth_mm": 22.0}

    plan_ring = _plan_finishing(ring_piece, stock, tool, machine)
    plan_pendant = _plan_finishing(pendant_piece, stock, tool, machine)

    assert plan_ring["has_bore_finishing"] is True
    assert plan_pendant["has_bore_finishing"] is False


# ---------------------------------------------------------------------------
# 30. Error: step_down_mm must be positive
# ---------------------------------------------------------------------------

def test_error_nonpositive_step_down():
    result = plan_wax_routing(
        RING_PIECE, MACHINE_4AXIS, FULL_LIBRARY, STOCK_20x20x15,
        step_down_mm=0.0,
    )
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# 31. plan_wax_routing never raises on adversarial input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("piece,machine,tools,stock", [
    (None, MACHINE_4AXIS, FULL_LIBRARY, STOCK_20x20x15),
    (RING_PIECE, None, FULL_LIBRARY, STOCK_20x20x15),
    (RING_PIECE, MACHINE_4AXIS, None, STOCK_20x20x15),
    (RING_PIECE, MACHINE_4AXIS, FULL_LIBRARY, None),
    ({}, {}, [{}], {}),
])
def test_plan_wax_routing_never_raises(piece, machine, tools, stock):
    result = plan_wax_routing(piece, machine, tools or [], stock or {})
    assert isinstance(result, dict)
    assert "ok" in result
