"""
Hermetic tests for kerf_cad_core.gcode — G-code post-processing & toolpath utilities.

Coverage:
  post.parse_gcode           — round-trip, modal state, comments, incremental
  post.arc_to_polyline       — chord error bound, CW vs CCW, full circle
  post.toolpath_stats        — length accounting, counts
  post.cycle_time            — hand-calc comparison (constant accel model)
  post.bounding_box          — min/max/extent
  post.clamp_feedrate        — clamp logic
  post.override_feedrate     — scale logic
  post.expand_drill_cycles   — G81/G82/G83 expansion
  post.transform_program     — translate/rotate/scale/mirror
  post.renumber_lines        — N-word stripping + renumbering
  post.apply_header_footer   — string prepend/append
  post.backplot_points       — sampling
  tools.*                    — LLM wrapper happy-path + error paths

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.gcode.post import (
    parse_gcode,
    arc_to_polyline,
    toolpath_stats,
    cycle_time,
    bounding_box,
    clamp_feedrate,
    override_feedrate,
    reduce_arcs_to_lines,
    fit_lines_to_arcs,
    expand_drill_cycles,
    transform_program,
    renumber_lines,
    apply_header_footer,
    backplot_points,
)
from kerf_cad_core.gcode.tools import (
    run_gcode_parse,
    run_gcode_stats,
    run_gcode_cycle_time,
    run_gcode_bounding_box,
    run_gcode_clamp_feedrate,
    run_gcode_override_feedrate,
    run_gcode_expand_drills,
    run_gcode_transform,
    run_gcode_renumber,
    run_gcode_backplot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


REL = 1e-9   # tight float tolerance for geometry checks


# ===========================================================================
# 1. parse_gcode — basic linear moves
# ===========================================================================

class TestParseGcodeLinear:

    _PROG = """\
G21 G90
G0 X10 Y0 Z0
G1 X20 Y0 Z0 F500
G1 X20 Y10 Z0
"""

    def test_segment_count(self):
        r = parse_gcode(self._PROG)
        motion_segs = [s for s in r["segments"] if s["type"] in ("rapid", "feed")]
        assert len(motion_segs) == 3

    def test_rapid_type(self):
        r = parse_gcode(self._PROG)
        segs = [s for s in r["segments"] if s["type"] == "rapid"]
        assert len(segs) == 1
        assert segs[0]["motion"] == "G0"

    def test_feed_type(self):
        r = parse_gcode(self._PROG)
        segs = [s for s in r["segments"] if s["type"] == "feed"]
        assert len(segs) == 2

    def test_absolute_endpoints(self):
        r = parse_gcode(self._PROG)
        feed_segs = [s for s in r["segments"] if s["type"] == "feed"]
        # second feed should go from (20,0,0) to (20,10,0)
        s = feed_segs[1]
        assert abs(s["start"][0] - 20.0) < REL
        assert abs(s["start"][1] - 0.0) < REL
        assert abs(s["end"][1] - 10.0) < REL

    def test_feedrate_propagation(self):
        r = parse_gcode(self._PROG)
        feed_segs = [s for s in r["segments"] if s["type"] == "feed"]
        # F500 set on first G1; should propagate to second G1
        assert feed_segs[0]["f"] == 500.0
        assert feed_segs[1]["f"] == 500.0

    def test_final_pos(self):
        r = parse_gcode(self._PROG)
        assert abs(r["final_pos"][0] - 20.0) < REL
        assert abs(r["final_pos"][1] - 10.0) < REL

    def test_units_mm(self):
        r = parse_gcode(self._PROG)
        assert r["units"] == "G21"

    def test_no_warnings_clean_program(self):
        r = parse_gcode(self._PROG)
        assert r["warnings"] == []


# ===========================================================================
# 2. parse_gcode — incremental mode (G91)
# ===========================================================================

class TestParseGcodeIncremental:

    _PROG = """\
G21 G91
G1 X10 Y0 Z0 F200
G1 X10 Y5 Z0
"""

    def test_incremental_accumulates(self):
        r = parse_gcode(self._PROG)
        feed_segs = [s for s in r["segments"] if s["type"] == "feed"]
        # second move: start=(10,0,0) end=(20,5,0)
        assert abs(feed_segs[1]["end"][0] - 20.0) < REL
        assert abs(feed_segs[1]["end"][1] - 5.0) < REL

    def test_final_pos_incremental(self):
        r = parse_gcode(self._PROG)
        assert abs(r["final_pos"][0] - 20.0) < REL
        assert abs(r["final_pos"][1] - 5.0) < REL


# ===========================================================================
# 3. parse_gcode — comments
# ===========================================================================

class TestParseGcodeComments:

    def test_paren_comment_stripped(self):
        prog = "G1 X10 Y0 F100 (this is a comment)\n"
        r = parse_gcode(prog)
        segs = [s for s in r["segments"] if s["type"] == "feed"]
        assert len(segs) == 1
        assert segs[0]["comment"] == "this is a comment"

    def test_semicolon_comment_stripped(self):
        prog = "G1 X5 F100 ; move to X5\n"
        r = parse_gcode(prog)
        segs = [s for s in r["segments"] if s["type"] == "feed"]
        assert len(segs) == 1

    def test_pure_comment_line(self):
        prog = "(program start)\nG1 X1 F100\n"
        r = parse_gcode(prog)
        comment_segs = [s for s in r["segments"] if s["type"] == "comment"]
        assert len(comment_segs) == 1


# ===========================================================================
# 4. parse_gcode — arc (G2/G3)
# ===========================================================================

class TestParseGcodeArc:

    _QUARTER_CW = "G21 G90\nG2 X10 Y10 I10 J0 F300\n"  # quarter arc CW from (0,0) centre (10,0)

    def test_arc_type(self):
        r = parse_gcode(self._QUARTER_CW)
        arcs = [s for s in r["segments"] if s["type"] == "arc"]
        assert len(arcs) == 1

    def test_arc_has_polyline(self):
        r = parse_gcode(self._QUARTER_CW, chord_tol=0.1)
        arcs = [s for s in r["segments"] if s["type"] == "arc"]
        assert len(arcs[0]["polyline"]) >= 1

    def test_arc_radius_correct(self):
        r = parse_gcode(self._QUARTER_CW)
        arcs = [s for s in r["segments"] if s["type"] == "arc"]
        assert abs(arcs[0]["radius"] - 10.0) < 1e-6

    def test_arc_motion_g2(self):
        r = parse_gcode(self._QUARTER_CW)
        arcs = [s for s in r["segments"] if s["type"] == "arc"]
        assert arcs[0]["motion"] == "G2"

    def test_arc_motion_g3(self):
        prog = "G21 G90\nG3 X10 Y10 I10 J0 F300\n"
        r = parse_gcode(prog)
        arcs = [s for s in r["segments"] if s["type"] == "arc"]
        assert arcs[0]["motion"] == "G3"


# ===========================================================================
# 5. arc_to_polyline — chord error bound
# ===========================================================================

class TestArcToPolyline:

    def test_chord_error_within_tol(self):
        """Every chord in the polyline must have sag ≤ chord_tol."""
        cx, cy = 0.0, 0.0
        r = 50.0
        chord_tol = 0.05
        pts = arc_to_polyline(cx, cy, r, 0.0, math.pi / 2, False, chord_tol)
        pts.append((cx + r * math.cos(math.pi / 2), cy + r * math.sin(math.pi / 2)))

        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            # midpoint of chord
            mx = (p1[0] + p2[0]) / 2
            my = (p1[1] + p2[1]) / 2
            # distance from arc centre to midpoint
            mid_r = math.hypot(mx - cx, my - cy)
            sag = abs(r - mid_r)
            assert sag <= chord_tol * 1.001, f"sag {sag:.6f} > tol {chord_tol}"

    def test_full_circle_no_gaps(self):
        """Full circle: start ≈ end angle after full sweep."""
        pts = arc_to_polyline(0.0, 0.0, 10.0, 0.0, 0.0, False, 0.1)
        # all points should be approximately on the circle
        for p in pts:
            assert abs(math.hypot(p[0], p[1]) - 10.0) < 0.2

    def test_cw_vs_ccw_different_sweeps(self):
        r = 10.0
        pts_cw = arc_to_polyline(0, 0, r, 0, math.pi / 2, True, 0.1)
        pts_ccw = arc_to_polyline(0, 0, r, 0, math.pi / 2, False, 0.1)
        # CW quarter arc goes the long way (270°), CCW the short way (90°)
        assert len(pts_cw) > len(pts_ccw)

    def test_returns_empty_for_zero_radius(self):
        pts = arc_to_polyline(0, 0, 0.0, 0, math.pi, False, 0.01)
        assert pts == []

    def test_finer_tol_more_points(self):
        pts_coarse = arc_to_polyline(0, 0, 20.0, 0, math.pi, False, 1.0)
        pts_fine = arc_to_polyline(0, 0, 20.0, 0, math.pi, False, 0.1)
        assert len(pts_fine) >= len(pts_coarse)


# ===========================================================================
# 6. toolpath_stats
# ===========================================================================

class TestToolpathStats:

    _PROG = """\
G21 G90
G0 X0 Y0 Z10
G0 X10 Y0 Z10
G1 X10 Y10 Z0 F500
"""

    def test_rapid_length(self):
        r = parse_gcode(self._PROG)
        stats = toolpath_stats(r["segments"])
        # first rapid: (0,0,0)→(0,0,10) = 10
        # second rapid: (0,0,10)→(10,0,10) = 10
        assert abs(stats["rapid_length"] - 20.0) < 1e-6

    def test_feed_length(self):
        r = parse_gcode(self._PROG)
        stats = toolpath_stats(r["segments"])
        # G1 from (10,0,10) to (10,10,0): sqrt(0+100+100) = sqrt(200)
        expected = math.sqrt(200.0)
        assert abs(stats["feed_length"] - expected) < 1e-6

    def test_total_length(self):
        r = parse_gcode(self._PROG)
        stats = toolpath_stats(r["segments"])
        assert abs(stats["total_length"] - (20.0 + math.sqrt(200.0))) < 1e-6

    def test_counts(self):
        r = parse_gcode(self._PROG)
        stats = toolpath_stats(r["segments"])
        assert stats["rapid_count"] == 2
        assert stats["feed_count"] == 1

    def test_ok_flag(self):
        r = parse_gcode(self._PROG)
        stats = toolpath_stats(r["segments"])
        assert stats["ok"] is True


# ===========================================================================
# 7. cycle_time — hand-calc verification
# ===========================================================================

class TestCycleTime:

    def test_constant_feed_no_accel(self):
        """With accel=0, cycle time = dist / (F/60)."""
        prog = "G21 G90\nG1 X100 F600\n"  # 100 mm at 600 mm/min = 10 s
        r = parse_gcode(prog)
        t = cycle_time(r["segments"], rapid_rate=10000.0, accel=0.0)
        assert abs(t["feed_s"] - 10.0) < 1e-6

    def test_trapezoidal_short_move(self):
        """Short move (triangular profile): t = 2*sqrt(d/a).

        d=3mm (< 2*d_ramp=5mm), a=500mm/s², F=3000mm/min → v=50mm/s
        d_ramp = v²/(2a) = 2500/1000 = 2.5 mm  →  2*d_ramp=5mm > d=3mm → triangular
        t = 2*sqrt(3/500) s
        """
        prog = "G21 G90\nG1 X3 F3000\n"
        r = parse_gcode(prog)
        t = cycle_time(r["segments"], rapid_rate=10000.0, accel=500.0)
        expected = 2.0 * math.sqrt(3.0 / 500.0)
        assert abs(t["feed_s"] - expected) < 1e-6

    def test_trapezoidal_long_move(self):
        """Long move (trapezoidal profile).

        d=200mm, a=500mm/s², F=3000mm/min → v=50mm/s
        d_ramp = 50²/(2*500) = 2.5 mm
        t_ramp = 2*2.5/50 = 0.1 s
        t_cruise = (200-5)/50 = 3.9 s
        total = 4.0 s
        """
        prog = "G21 G90\nG1 X200 F3000\n"
        r = parse_gcode(prog)
        t = cycle_time(r["segments"], rapid_rate=10000.0, accel=500.0)
        v = 3000.0 / 60.0  # 50 mm/s
        d_ramp = v * v / (2 * 500.0)
        t_ramp = 2 * d_ramp / v
        t_cruise = (200.0 - 2 * d_ramp) / v
        expected = t_ramp + t_cruise
        assert abs(t["feed_s"] - expected) < 1e-6

    def test_rapid_uses_rapid_rate(self):
        prog = "G21 G90\nG0 X600\n"  # 600mm at 10000mm/min = 3.6s (if accel=0)
        r = parse_gcode(prog)
        t = cycle_time(r["segments"], rapid_rate=10000.0, accel=0.0)
        expected = 600.0 / (10000.0 / 60.0)
        assert abs(t["rapid_s"] - expected) < 1e-6

    def test_dwell_contributes_to_total(self):
        prog = "G4 P1000\n"  # 1000 ms dwell
        r = parse_gcode(prog)
        t = cycle_time(r["segments"], rapid_rate=10000.0, accel=500.0)
        assert abs(t["total_s"] - 1.0) < 1e-6

    def test_ok_flag(self):
        r = parse_gcode("G1 X10 F100\n")
        t = cycle_time(r["segments"])
        assert t["ok"] is True


# ===========================================================================
# 8. bounding_box
# ===========================================================================

class TestBoundingBox:

    def test_basic_bbox(self):
        prog = "G21 G90\nG0 X0 Y0 Z0\nG1 X100 Y50 Z-10 F500\n"
        r = parse_gcode(prog)
        bb = bounding_box(r["segments"])
        assert bb["ok"] is True
        assert abs(bb["xmin"] - 0.0) < REL
        assert abs(bb["xmax"] - 100.0) < REL
        assert abs(bb["ymax"] - 50.0) < REL
        assert abs(bb["zmin"] - (-10.0)) < REL

    def test_extents(self):
        prog = "G21 G90\nG0 X0 Y0 Z0\nG1 X100 Y50 Z-10 F500\n"
        r = parse_gcode(prog)
        bb = bounding_box(r["segments"])
        assert abs(bb["dx"] - 100.0) < REL
        assert abs(bb["dy"] - 50.0) < REL
        assert abs(bb["dz"] - 10.0) < REL

    def test_empty_returns_error(self):
        bb = bounding_box([])
        assert bb["ok"] is False

    def test_single_segment(self):
        """A single rapid from (0,0,0) to (5,5,5): dx=dy=dz=5."""
        prog = "G21 G90\nG0 X5 Y5 Z5\n"
        r = parse_gcode(prog)
        bb = bounding_box(r["segments"])
        assert bb["ok"] is True
        assert abs(bb["xmin"] - 0.0) < REL
        assert abs(bb["xmax"] - 5.0) < REL


# ===========================================================================
# 9. clamp_feedrate
# ===========================================================================

class TestClampFeedrate:

    def test_clamp_above_max(self):
        prog = "G21 G90\nG1 X10 F2000\n"
        r = parse_gcode(prog)
        clamped = clamp_feedrate(r["segments"], f_min=100, f_max=800)
        feed_segs = [s for s in clamped if s["type"] == "feed"]
        assert feed_segs[0]["f"] == 800.0

    def test_clamp_below_min(self):
        prog = "G21 G90\nG1 X10 F50\n"
        r = parse_gcode(prog)
        clamped = clamp_feedrate(r["segments"], f_min=100, f_max=800)
        feed_segs = [s for s in clamped if s["type"] == "feed"]
        assert feed_segs[0]["f"] == 100.0

    def test_clamp_in_range_unchanged(self):
        prog = "G21 G90\nG1 X10 F500\n"
        r = parse_gcode(prog)
        clamped = clamp_feedrate(r["segments"], f_min=100, f_max=800)
        feed_segs = [s for s in clamped if s["type"] == "feed"]
        assert feed_segs[0]["f"] == 500.0

    def test_rapid_not_affected(self):
        prog = "G21 G90\nG0 X10\n"
        r = parse_gcode(prog)
        original_f = r["segments"][0]["f"]
        clamped = clamp_feedrate(r["segments"], f_min=100, f_max=800)
        assert clamped[0]["f"] == original_f


# ===========================================================================
# 10. override_feedrate
# ===========================================================================

class TestOverrideFeedrate:

    def test_scale_80_percent(self):
        prog = "G21 G90\nG1 X10 F1000\n"
        r = parse_gcode(prog)
        overridden = override_feedrate(r["segments"], 0.8)
        feed_segs = [s for s in overridden if s["type"] == "feed"]
        assert abs(feed_segs[0]["f"] - 800.0) < REL

    def test_scale_120_percent(self):
        prog = "G21 G90\nG1 X10 F500\n"
        r = parse_gcode(prog)
        overridden = override_feedrate(r["segments"], 1.2)
        feed_segs = [s for s in overridden if s["type"] == "feed"]
        assert abs(feed_segs[0]["f"] - 600.0) < REL


# ===========================================================================
# 11. expand_drill_cycles
# ===========================================================================

class TestExpandDrillCycles:

    def test_g81_expands_to_rapid_feed_retract(self):
        prog = "G21 G90\nG0 X10 Y10 Z5\nG81 X10 Y10 Z-20 R2 F150\n"
        r = parse_gcode(prog)
        expanded = expand_drill_cycles(r["segments"])
        types = [s["type"] for s in expanded]
        # Should have: rapid (to XY), rapid (to R-plane), feed (to depth), rapid (retract)
        assert "feed" in types
        assert types.count("rapid") >= 3

    def test_g81_depth_correct(self):
        prog = "G21 G90\nG81 X0 Y0 Z-15 R2 F100\n"
        r = parse_gcode(prog)
        expanded = expand_drill_cycles(r["segments"])
        feed_segs = [s for s in expanded if s["type"] == "feed"]
        # feed segment should go to Z=-15
        assert any(abs(s["end"][2] - (-15.0)) < 1e-6 for s in feed_segs)

    def test_g82_includes_dwell(self):
        prog = "G21 G90\nG82 X0 Y0 Z-10 R2 F100\n"
        r = parse_gcode(prog)
        expanded = expand_drill_cycles(r["segments"])
        types = [s["type"] for s in expanded]
        assert "dwell" in types

    def test_g83_multiple_pecks(self):
        prog = "G21 G90\nG83 X0 Y0 Z-30 R5 Q10 F80\n"
        r = parse_gcode(prog)
        expanded = expand_drill_cycles(r["segments"])
        feed_segs = [s for s in expanded if s["type"] == "feed"]
        # 30mm depth / 10mm peck = 3 pecks
        assert len(feed_segs) >= 3

    def test_no_drill_cycles_unchanged(self):
        prog = "G21 G90\nG0 X10\nG1 X20 F200\n"
        r = parse_gcode(prog)
        expanded = expand_drill_cycles(r["segments"])
        assert len(expanded) == len(r["segments"])

    def test_g83_final_depth_reached(self):
        prog = "G21 G90\nG83 X0 Y0 Z-20 R0 Q5 F100\n"
        r = parse_gcode(prog)
        expanded = expand_drill_cycles(r["segments"])
        feed_segs = [s for s in expanded if s["type"] == "feed"]
        z_depths = [s["end"][2] for s in feed_segs]
        assert any(abs(z - (-20.0)) < 1e-6 for z in z_depths)


# ===========================================================================
# 12. transform_program
# ===========================================================================

class TestTransformProgram:

    def test_translate(self):
        prog = "G21 G90\nG1 X10 Y5 Z0 F200\n"
        r = parse_gcode(prog)
        transformed = transform_program(r["segments"], translate=(100.0, 50.0, 0.0))
        feed_segs = [s for s in transformed if s["type"] == "feed"]
        assert abs(feed_segs[0]["end"][0] - 110.0) < 1e-6
        assert abs(feed_segs[0]["end"][1] - 55.0) < 1e-6

    def test_scale(self):
        prog = "G21 G90\nG1 X10 Y0 F200\n"
        r = parse_gcode(prog)
        transformed = transform_program(r["segments"], scale=2.0)
        feed_segs = [s for s in transformed if s["type"] == "feed"]
        assert abs(feed_segs[0]["end"][0] - 20.0) < 1e-6

    def test_rotate_90_deg(self):
        prog = "G21 G90\nG1 X10 Y0 F200\n"
        r = parse_gcode(prog)
        transformed = transform_program(r["segments"], rotate_deg=90.0)
        feed_segs = [s for s in transformed if s["type"] == "feed"]
        end = feed_segs[0]["end"]
        # (10,0) rotated 90° CCW = (0, 10)
        assert abs(end[0] - 0.0) < 1e-6
        assert abs(end[1] - 10.0) < 1e-6

    def test_mirror_x(self):
        prog = "G21 G90\nG1 X10 Y5 F200\n"
        r = parse_gcode(prog)
        transformed = transform_program(r["segments"], mirror_axis="X")
        feed_segs = [s for s in transformed if s["type"] == "feed"]
        assert abs(feed_segs[0]["end"][0] - (-10.0)) < 1e-6
        assert abs(feed_segs[0]["end"][1] - 5.0) < 1e-6

    def test_mirror_y(self):
        prog = "G21 G90\nG1 X10 Y5 F200\n"
        r = parse_gcode(prog)
        transformed = transform_program(r["segments"], mirror_axis="Y")
        feed_segs = [s for s in transformed if s["type"] == "feed"]
        assert abs(feed_segs[0]["end"][0] - 10.0) < 1e-6
        assert abs(feed_segs[0]["end"][1] - (-5.0)) < 1e-6


# ===========================================================================
# 13. renumber_lines
# ===========================================================================

class TestRenumberLines:

    def test_basic_renumber(self):
        prog = "G21\nG90\nG1 X10\n"
        result = renumber_lines(prog, start=10, step=10)
        lines = [l for l in result.splitlines() if l.strip()]
        assert lines[0].startswith("N10 ")
        assert lines[1].startswith("N20 ")
        assert lines[2].startswith("N30 ")

    def test_strips_existing_n_words(self):
        prog = "N100 G21\nN200 G1 X10\n"
        result = renumber_lines(prog, start=5, step=5)
        lines = [l for l in result.splitlines() if l.strip()]
        assert lines[0].startswith("N5 ")
        assert lines[1].startswith("N10 ")

    def test_blank_lines_preserved(self):
        prog = "G21\n\nG1 X10\n"
        result = renumber_lines(prog, start=10, step=10)
        # blank lines should remain blank in output
        raw_lines = result.splitlines()
        blank_count = sum(1 for l in raw_lines if not l.strip())
        assert blank_count >= 1

    def test_step_parameter(self):
        prog = "G0\nG1 X1\nG1 X2\n"
        result = renumber_lines(prog, start=100, step=5)
        lines = [l for l in result.splitlines() if l.strip()]
        assert lines[0].startswith("N100 ")
        assert lines[1].startswith("N105 ")
        assert lines[2].startswith("N110 ")


# ===========================================================================
# 14. apply_header_footer
# ===========================================================================

class TestApplyHeaderFooter:

    def test_header_prepended(self):
        result = apply_header_footer("G1 X10", header="%\nO0001")
        assert result.startswith("%\nO0001\n")

    def test_footer_appended(self):
        result = apply_header_footer("G1 X10", footer="M30\n%")
        assert result.endswith("M30\n%")

    def test_no_header_footer(self):
        result = apply_header_footer("G1 X10")
        assert result == "G1 X10"

    def test_both_header_and_footer(self):
        result = apply_header_footer("G1 X10", header="% START", footer="M30")
        assert result.startswith("% START")
        assert result.endswith("M30")


# ===========================================================================
# 15. backplot_points
# ===========================================================================

class TestBackplotPoints:

    def test_returns_list_of_tuples(self):
        prog = "G21 G90\nG0 X0 Y0 Z0\nG1 X50 Y50 Z0 F300\n"
        r = parse_gcode(prog)
        pts = backplot_points(r["segments"])
        assert isinstance(pts, list)
        assert all(len(p) == 3 for p in pts)

    def test_max_points_respected(self):
        prog = "\n".join(f"G1 X{i} F300" for i in range(200))
        r = parse_gcode(prog)
        pts = backplot_points(r["segments"], max_points=50)
        assert len(pts) <= 50

    def test_includes_arc_polyline(self):
        prog = "G21 G90\nG3 X10 Y0 I5 J0 F300\n"
        r = parse_gcode(prog, chord_tol=0.5)
        pts = backplot_points(r["segments"], max_points=0)
        assert len(pts) >= 2


# ===========================================================================
# 16. Tool wrappers — happy path
# ===========================================================================

class TestToolsHappyPath:

    def test_gcode_parse_tool(self):
        ctx = _ctx()
        raw = _run(run_gcode_parse(ctx, _args(gcode="G21\nG1 X10 F100\n")))
        d = _ok(raw)
        assert "segments" in d

    def test_gcode_stats_tool(self):
        ctx = _ctx()
        raw = _run(run_gcode_stats(ctx, _args(gcode="G21\nG1 X10 F100\n")))
        d = _ok(raw)
        assert "total_length" in d

    def test_gcode_cycle_time_tool(self):
        ctx = _ctx()
        raw = _run(run_gcode_cycle_time(
            ctx, _args(gcode="G21\nG1 X100 F600\n", rapid_rate=10000, accel=0)
        ))
        d = _ok(raw)
        assert abs(d["feed_s"] - 10.0) < 1e-3

    def test_gcode_bounding_box_tool(self):
        ctx = _ctx()
        raw = _run(run_gcode_bounding_box(
            ctx, _args(gcode="G21 G90\nG0 X0 Y0 Z0\nG1 X100 Y50 Z-5 F200\n")
        ))
        d = _ok(raw)
        assert abs(d["xmax"] - 100.0) < 1e-6

    def test_gcode_clamp_feedrate_tool(self):
        ctx = _ctx()
        raw = _run(run_gcode_clamp_feedrate(
            ctx, _args(gcode="G21 G90\nG1 X10 F2000\n", f_min=100, f_max=800)
        ))
        d = _ok(raw)
        segs = d["segments"]
        feed_segs = [s for s in segs if s["type"] == "feed"]
        assert feed_segs[0]["f"] == 800.0

    def test_gcode_override_feedrate_tool(self):
        ctx = _ctx()
        raw = _run(run_gcode_override_feedrate(
            ctx, _args(gcode="G21 G90\nG1 X10 F1000\n", factor=0.5)
        ))
        d = _ok(raw)
        segs = d["segments"]
        feed_segs = [s for s in segs if s["type"] == "feed"]
        assert abs(feed_segs[0]["f"] - 500.0) < REL

    def test_gcode_expand_drills_tool(self):
        ctx = _ctx()
        raw = _run(run_gcode_expand_drills(
            ctx, _args(gcode="G21 G90\nG81 X0 Y0 Z-10 R2 F100\n")
        ))
        d = _ok(raw)
        segs = d["segments"]
        assert any(s["type"] == "feed" for s in segs)

    def test_gcode_transform_tool_translate(self):
        ctx = _ctx()
        raw = _run(run_gcode_transform(
            ctx, _args(gcode="G21 G90\nG1 X10 Y0 F200\n", translate=[5, 0, 0])
        ))
        d = _ok(raw)
        segs = d["segments"]
        feed_segs = [s for s in segs if s["type"] == "feed"]
        assert abs(feed_segs[0]["end"][0] - 15.0) < 1e-6

    def test_gcode_renumber_tool(self):
        ctx = _ctx()
        raw = _run(run_gcode_renumber(
            ctx, _args(gcode="G21\nG1 X10\n", start=10, step=10)
        ))
        d = _ok(raw)
        lines = [l for l in d["gcode"].splitlines() if l.strip()]
        assert lines[0].startswith("N10 ")

    def test_gcode_backplot_tool(self):
        ctx = _ctx()
        raw = _run(run_gcode_backplot(
            ctx, _args(gcode="G21 G90\nG1 X10 F100\nG1 X20 F100\n", max_points=100)
        ))
        d = _ok(raw)
        assert "points" in d
        assert isinstance(d["points"], list)


# ===========================================================================
# 17. Tool wrappers — error paths
# ===========================================================================

class TestToolsErrorPaths:

    def test_parse_missing_gcode(self):
        ctx = _ctx()
        raw = _run(run_gcode_parse(ctx, _args()))
        _err(raw)

    def test_stats_missing_gcode(self):
        ctx = _ctx()
        raw = _run(run_gcode_stats(ctx, _args()))
        _err(raw)

    def test_clamp_missing_f_min(self):
        ctx = _ctx()
        raw = _run(run_gcode_clamp_feedrate(
            ctx, _args(gcode="G1 X10 F100", f_max=800)
        ))
        _err(raw)

    def test_clamp_f_min_gt_f_max(self):
        ctx = _ctx()
        raw = _run(run_gcode_clamp_feedrate(
            ctx, _args(gcode="G1 X10 F100", f_min=900, f_max=800)
        ))
        _err(raw)

    def test_override_zero_factor(self):
        ctx = _ctx()
        raw = _run(run_gcode_override_feedrate(
            ctx, _args(gcode="G1 X10 F100", factor=0.0)
        ))
        _err(raw)

    def test_transform_invalid_scale(self):
        ctx = _ctx()
        raw = _run(run_gcode_transform(
            ctx, _args(gcode="G1 X10 F100", scale=-1.0)
        ))
        _err(raw)

    def test_renumber_bad_step(self):
        ctx = _ctx()
        raw = _run(run_gcode_renumber(
            ctx, _args(gcode="G1 X10", step=0)
        ))
        _err(raw)

    def test_bad_json(self):
        ctx = _ctx()
        raw = _run(run_gcode_parse(ctx, b"not json {"))
        _err(raw)


# ===========================================================================
# Multi-G-per-block parsing (fix: dict overwrite dropped all but last G word)
# ===========================================================================

class TestParseGcodeMultiGPerBlock:
    """Verify that multiple G-codes on a single block are all honoured.

    Before the fix, _parse_words stored only the last G value, so a line like
    'G17 G90 G0 X10' would lose G17 and G90 entirely (dict key overwrite).
    After the fix G is stored as a list and the modal update loop processes
    all of them.
    """

    def test_plane_and_distance_and_motion_on_one_line(self):
        """G17 G90 G0 X10 — all three modal G-codes must be applied."""
        prog = "G17 G90 G0 X10\n"
        result = parse_gcode(prog)
        assert result["ok"] is True
        segs = result["segments"]
        # Should produce at least one rapid segment (G0 with X10 from origin)
        rapids = [s for s in segs if s["type"] == "rapid"]
        assert len(rapids) >= 1, "G0 X10 should produce a rapid segment"
        assert rapids[0]["end"][0] == pytest.approx(10.0)
        assert rapids[0]["plane"] == "G17"
        assert rapids[0]["distance_mode"] == "G90"

    def test_units_and_absolute_on_setup_line(self):
        """G21 G90 on the same block — both must be applied before the move."""
        prog = "G21 G90\nG0 X5\n"
        result = parse_gcode(prog)
        assert result["ok"] is True
        segs = [s for s in result["segments"] if s["type"] == "rapid"]
        assert len(segs) >= 1
        assert segs[0]["units"] == "G21"
        assert segs[0]["distance_mode"] == "G90"

    def test_plane_switch_and_move_same_line(self):
        """G18 G1 X5 Z3 — plane switch (XZ) and feed move on same block."""
        prog = "G21 G90\nG18 G1 X5 Z3 F200\n"
        result = parse_gcode(prog)
        assert result["ok"] is True
        feeds = [s for s in result["segments"] if s["type"] == "feed"]
        assert len(feeds) >= 1
        assert feeds[0]["plane"] == "G18", (
            f"Expected plane G18 from same-block G18 G1, got {feeds[0]['plane']}"
        )
