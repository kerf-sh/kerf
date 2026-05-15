"""
T7 extension: 3-axis posts honour the Tool DB.

Tests cover all four 3-axis post-processors:
  LinuxCNC (linuxcnc_3x) · GRBL (grbl_3x) · Mach3 (mach3_3x) · Fanuc (fanuc_3x)

All tests are pure-Python — no DB, no opencamlib, no pythonOCC.
"""

from __future__ import annotations

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

import pytest

from kerf_cam.tool_db import parse_tool
from kerf_cam.posts_common import PostOpts3
from kerf_cam.posts.linuxcnc_3x import emit as lnx_emit
from kerf_cam.posts.grbl_3x import emit as grbl_emit
from kerf_cam.posts.mach3_3x import emit as mach3_emit
from kerf_cam.posts.fanuc_3x import emit as fanuc_emit


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _flat_end_tool() -> dict:
    return {
        "id": "T1",
        "name": "6mm carbide flat-end",
        "type": "flat_end",
        "diameter_mm": 6.0,
        "flute_count": 2,
        "material": "carbide",
        "spindle_rpm_min": 8000,
        "feed_rate_mm_min": 750.0,
        "plunge_rate_mm_min": 200.0,
    }


def _ball_end_tool() -> dict:
    return {
        "id": "T2",
        "name": "4mm ball-end",
        "type": "ball_end",
        "diameter_mm": 4.0,
        "ball_radius_mm": 2.0,
        "spindle_rpm_min": 12000,
        "feed_rate_mm_min": 600.0,
        "plunge_rate_mm_min": 150.0,
    }


def _pts(n: int = 3) -> list[dict]:
    """n synthetic CL points along X at Z=-1."""
    return [{"x": float(i) * 5.0, "y": 0.0, "z": -1.0} for i in range(n)]


# ---------------------------------------------------------------------------
# 1. LinuxCNC — basic structure
# ---------------------------------------------------------------------------

def test_linuxcnc_header_and_tape_markers():
    gcode = lnx_emit(_pts(), PostOpts3())
    assert gcode.startswith("%"), "should start with tape marker"
    assert gcode.endswith("%"), "should end with tape marker"
    assert "G90" in gcode
    assert "G21" in gcode
    assert "M30" in gcode


def test_linuxcnc_tool_comment_and_m6():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool, tool_number=1)
    gcode = lnx_emit(_pts(), opts)
    assert "tool: T1" in gcode
    assert "carbide" in gcode
    # M6 uses numeric tool_number (1), not tool.id ("T1")
    assert "M6 T1" in gcode


def test_linuxcnc_feeds_from_tool():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = lnx_emit(_pts(), opts)
    # Cut feed 750 and plunge feed 200 from tool
    assert "F750" in gcode
    assert "F200" in gcode


def test_linuxcnc_spindle_from_tool():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = lnx_emit(_pts(), opts)
    assert "S8000 M3" in gcode


def test_linuxcnc_postopts_overrides_tool_feed():
    """Explicit PostOpts3.feed_cut_mm_min must beat tool default."""
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool, feed_cut_mm_min=1234.0)
    gcode = lnx_emit(_pts(), opts)
    assert "F1234" in gcode
    assert "F750" not in gcode


# ---------------------------------------------------------------------------
# 2. GRBL — no real M6, comment-only
# ---------------------------------------------------------------------------

def test_grbl_no_bare_m6():
    """GRBL must not emit a bare M6 — only a comment."""
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = grbl_emit(_pts(), opts)
    for line in gcode.splitlines():
        stripped = line.strip()
        # A bare M6 would be a line that IS "M6" or starts with "M6 " outside a comment.
        if stripped.startswith("("):
            continue
        if stripped.startswith(";"):
            continue
        assert not (stripped == "M6" or stripped.startswith("M6 ")), (
            f"bare M6 found in GRBL output: {line!r}"
        )


def test_grbl_m6_comment_present():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool, tool_number=1)
    gcode = grbl_emit(_pts(), opts)
    # GRBL emits M6 as a comment using numeric tool_number
    assert "(M6 T1)" in gcode


def test_grbl_tool_comment_semicolon():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = grbl_emit(_pts(), opts)
    assert "; tool: T1" in gcode


def test_grbl_feeds_from_tool():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = grbl_emit(_pts(), opts)
    assert "F750" in gcode
    assert "F200" in gcode


# ---------------------------------------------------------------------------
# 3. Mach3 — parenthetical comments, T<n> M6 tool call
# ---------------------------------------------------------------------------

def test_mach3_tool_call_format():
    """Mach3 uses ``T<n> M6`` (tool request then execute)."""
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = mach3_emit(_pts(), opts)
    assert "T1 M6" in gcode


def test_mach3_tool_comment_paren():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = mach3_emit(_pts(), opts)
    # Mach3 uses parenthetical (upper-cased) comments
    assert "(TOOL: T1" in gcode


def test_mach3_no_tape_markers():
    """Mach3 does not need % tape markers."""
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = mach3_emit(_pts(), opts)
    assert "%" not in gcode


def test_mach3_feeds_from_tool():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = mach3_emit(_pts(), opts)
    assert "F750" in gcode
    assert "F200" in gcode


# ---------------------------------------------------------------------------
# 4. Fanuc — N-numbers, parenthetical comments
# ---------------------------------------------------------------------------

def test_fanuc_n_numbers_present():
    gcode = fanuc_emit(_pts(), PostOpts3())
    assert "N10 " in gcode


def test_fanuc_no_n_numbers():
    opts = PostOpts3(no_n_numbers=True)
    gcode = fanuc_emit(_pts(), opts)
    assert "N10 " not in gcode
    assert "G90" in gcode


def test_fanuc_tool_comment_paren():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = fanuc_emit(_pts(), opts)
    assert "(TOOL: T1" in gcode


def test_fanuc_m6_uses_tool_number():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool, tool_number=1)
    gcode = fanuc_emit(_pts(), opts)
    # M6 uses numeric tool_number, not tool.id
    assert "M6 T1" in gcode


def test_fanuc_feeds_from_tool():
    tool = parse_tool(_flat_end_tool())
    opts = PostOpts3(tool=tool)
    gcode = fanuc_emit(_pts(), opts)
    assert "F750" in gcode
    assert "F200" in gcode


# ---------------------------------------------------------------------------
# 5. Coolant handling across all posts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("emit_fn,m8_check,m7_check", [
    (lnx_emit,  lambda g: "M8" in g, lambda g: "M7" in g),
    (grbl_emit, lambda g: "(M8 FLOOD)" in g, lambda g: "(M7 MIST)" in g),
    (mach3_emit, lambda g: "M8" in g, lambda g: "M7" in g),
    (fanuc_emit, lambda g: "M8" in g, lambda g: "M7" in g),
])
def test_coolant_flood(emit_fn, m8_check, m7_check):
    opts = PostOpts3(coolant="flood")
    gcode = emit_fn(_pts(), opts)
    assert m8_check(gcode), "flood coolant (M8) not found"


@pytest.mark.parametrize("emit_fn,m8_check,m7_check", [
    (lnx_emit,  lambda g: "M8" in g, lambda g: "M7" in g),
    (grbl_emit, lambda g: "(M8 FLOOD)" in g, lambda g: "(M7 MIST)" in g),
    (mach3_emit, lambda g: "M8" in g, lambda g: "M7" in g),
    (fanuc_emit, lambda g: "M8" in g, lambda g: "M7" in g),
])
def test_coolant_mist(emit_fn, m8_check, m7_check):
    opts = PostOpts3(coolant="mist")
    gcode = emit_fn(_pts(), opts)
    assert m7_check(gcode), "mist coolant (M7) not found"


# ---------------------------------------------------------------------------
# 6. Per-point feed override
# ---------------------------------------------------------------------------

def test_linuxcnc_per_point_feed_override():
    pts = [
        {"x": 0.0, "y": 0.0, "z": -1.0, "feed": 400.0},
        {"x": 5.0, "y": 0.0, "z": -1.0},
    ]
    tool = parse_tool(_flat_end_tool())  # default cut feed = 750
    opts = PostOpts3(tool=tool)
    gcode = lnx_emit(pts, opts)
    lines = [l for l in gcode.splitlines() if l.startswith("G1 X")]
    assert "F400" in lines[0], "first G1 X line should have per-point F400"
    assert "F750" in lines[1], "second G1 X line should revert to tool default F750"


# ---------------------------------------------------------------------------
# 7. Empty CL points — all posts handle gracefully
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("emit_fn", [lnx_emit, grbl_emit, mach3_emit, fanuc_emit])
def test_empty_cl_points(emit_fn):
    gcode = emit_fn([], PostOpts3())
    assert "M30" in gcode
    assert not any(line.startswith("G1 X") for line in gcode.splitlines())


# ---------------------------------------------------------------------------
# 8. No tool attached — posts use default numbering / no comment
# ---------------------------------------------------------------------------

def test_linuxcnc_no_tool_uses_tool_number():
    opts = PostOpts3(tool_number=3)
    gcode = lnx_emit(_pts(), opts)
    assert "M6 T3" in gcode
    assert "tool:" not in gcode


def test_fanuc_no_tool_uses_tool_number():
    opts = PostOpts3(tool_number=2)
    gcode = fanuc_emit(_pts(), opts)
    assert "M6 T2" in gcode
