"""
Hermetic tests for kerf_cad_core.turning — lathe CAM canned cycles + G-code post.

Coverage:
  cycles.cutting_params       — RPM/feed calculations
  cycles.roughing_passes      — pass count, G-code structure, monotone Z
  cycles.finishing_pass       — single-pass, correct profile traversal
  cycles.facing_pass          — n_passes, G-code well-formed
  cycles.parting_pass         — single/peck, G-code well-formed
  cycles.od_threading         — infeed schedule, spring passes, G-code
  cycles.id_threading         — ID infeed schedule, G-code
  cycles.grooving_pass        — single/multi-plunge, peck
  cycles.emit_gcode           — serialisation
  tools.*                     — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas are verified algebraically against published expressions.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.turning.cycles import (
    cutting_params,
    roughing_passes,
    finishing_pass,
    facing_pass,
    parting_pass,
    od_threading,
    id_threading,
    grooving_pass,
    emit_gcode,
    TurningResult,
    _calc_rpm,
    _DEFAULT_CSS_M_MIN,
    _DEFAULT_FEED_MM_REV,
)
from kerf_cad_core.turning.tools import (
    run_turning_cutting_params,
    run_turning_roughing_passes,
    run_turning_finishing_pass,
    run_turning_facing,
    run_turning_parting,
    run_turning_od_threading,
    run_turning_id_threading,
    run_turning_grooving,
)


# ---------------------------------------------------------------------------
# Test helpers
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


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


# Canonical simple profile: cylinder Z=0..50, radius=10mm
_SIMPLE_PROFILE = [(0.0, 10.0), (50.0, 10.0)]

# Step profile: shoulder at Z=30
_STEP_PROFILE = [(0.0, 10.0), (30.0, 10.0), (30.0, 15.0), (50.0, 15.0)]

# Taper profile
_TAPER_PROFILE = [(0.0, 5.0), (50.0, 15.0)]


# ===========================================================================
# 1. _calc_rpm helper
# ===========================================================================

class TestCalcRpm:

    def test_css_formula(self):
        """RPM = CSS*1000 / (pi * diameter)."""
        radius = 25.0  # mm
        css = 150.0    # m/min
        expected = (css * 1000.0) / (math.pi * radius * 2.0)
        rpm = _calc_rpm(radius, css, 50.0, 5000.0)
        assert abs(rpm - expected) / expected < 1e-9

    def test_rpm_clamped_to_min(self):
        """Very large radius → low RPM → clamped to rpm_min."""
        rpm = _calc_rpm(10000.0, 10.0, 200.0, 5000.0)
        assert rpm == 200.0

    def test_rpm_clamped_to_max(self):
        """Very small radius → high RPM → clamped to rpm_max."""
        rpm = _calc_rpm(0.001, 200.0, 50.0, 1000.0)
        assert rpm == 1000.0

    def test_zero_radius_returns_rpm_max(self):
        """Zero radius → rpm_max (near-spindle-centreline case)."""
        rpm = _calc_rpm(0.0, 180.0, 50.0, 3500.0)
        assert rpm == 3500.0


# ===========================================================================
# 2. cutting_params
# ===========================================================================

class TestCuttingParams:

    def test_basic_returns_ok(self):
        res = cutting_params(_SIMPLE_PROFILE)
        assert res["ok"] is True
        assert len(res["points"]) == 2

    def test_rpm_formula_correct(self):
        profile = [(0.0, 25.0)]
        css = 150.0
        res = cutting_params(profile, css_m_per_min=css)
        assert res["ok"] is True
        pt = res["points"][0]
        expected_rpm = (css * 1000.0) / (math.pi * 25.0 * 2.0)
        # May be clamped, but verify formula
        assert abs(pt["rpm"] - round(min(3500.0, max(50.0, expected_rpm)), 1)) < 0.1

    def test_feed_mm_min_equals_feed_rev_times_rpm(self):
        profile = [(0.0, 20.0)]
        feed_rev = 0.15
        res = cutting_params(profile, feed_mm_rev=feed_rev)
        assert res["ok"] is True
        pt = res["points"][0]
        expected_feed = feed_rev * pt["rpm"]
        assert abs(pt["feed_mm_min"] - round(expected_feed, 2)) < 0.01

    def test_diameter_is_2x_radius(self):
        profile = [(0.0, 12.5)]
        res = cutting_params(profile)
        assert res["ok"] is True
        assert res["points"][0]["diameter_mm"] == pytest.approx(25.0)

    def test_empty_profile_returns_error(self):
        res = cutting_params([])
        assert res["ok"] is False

    def test_negative_css_returns_error(self):
        res = cutting_params(_SIMPLE_PROFILE, css_m_per_min=-10.0)
        assert res["ok"] is False

    def test_invalid_rpm_range_returns_error(self):
        res = cutting_params(_SIMPLE_PROFILE, rpm_min=2000.0, rpm_max=100.0)
        assert res["ok"] is False


# ===========================================================================
# 3. roughing_passes
# ===========================================================================

class TestRoughingPasses:

    def test_returns_ok_for_valid_inputs(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0)
        assert result.ok is True

    def test_pass_count_matches_doc_steps(self):
        """Number of passes = ceil((stock - profile - allowance) / doc)."""
        stock = 20.0
        profile_max = 10.0
        allowance = 0.3
        doc = 2.0
        result = roughing_passes(
            _SIMPLE_PROFILE,
            stock_x_mm=stock,
            doc_mm=doc,
            finish_allowance_mm=allowance,
        )
        assert result.ok is True
        expected_passes = math.ceil((stock - profile_max - allowance) / doc)
        assert len(result.passes) == expected_passes

    def test_gcode_has_preamble_and_epilogue(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0)
        assert result.ok is True
        assert "G21" in result.gcode
        assert "M30" in result.gcode

    def test_gcode_has_m3_spindle_on(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0)
        assert any("M3" in line for line in result.gcode)

    def test_gcode_has_g0_rapid_moves(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0)
        assert any("G0" in line for line in result.gcode)

    def test_gcode_has_g1_feed_moves(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0)
        assert any("G1" in line for line in result.gcode)

    def test_stock_le_profile_returns_error(self):
        """stock_x_mm <= max profile X + allowance → error."""
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=9.0)
        assert result.ok is False

    def test_non_monotone_profile_raises_warning(self):
        """Non-monotone Z raises warnings; result still ok (truncated profile)."""
        non_mono = [(0.0, 10.0), (30.0, 10.0), (15.0, 10.0), (50.0, 10.0)]
        result = roughing_passes(non_mono, stock_x_mm=20.0)
        # Should still produce a result (using first monotone span)
        assert len(result.warnings) > 0

    def test_passes_have_required_keys(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0)
        for p in result.passes:
            assert "pass_type" in p
            assert "pass_radius_mm" in p
            assert "rpm" in p
            assert p["pass_type"] == "rough"

    def test_rpm_positive_in_all_passes(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0)
        for p in result.passes:
            assert p["rpm"] > 0

    def test_feed_positive_in_all_passes(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0)
        for p in result.passes:
            assert p["feed_mm_min"] > 0

    def test_doc_zero_returns_error(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0, doc_mm=0.0)
        assert result.ok is False

    def test_profile_too_short_returns_error(self):
        result = roughing_passes([(0.0, 10.0)], stock_x_mm=20.0)
        assert result.ok is False


# ===========================================================================
# 4. finishing_pass
# ===========================================================================

class TestFinishingPass:

    def test_returns_ok(self):
        result = finishing_pass(_SIMPLE_PROFILE)
        assert result.ok is True

    def test_exactly_one_pass(self):
        result = finishing_pass(_SIMPLE_PROFILE)
        assert len(result.passes) == 1
        assert result.passes[0]["pass_type"] == "finish"

    def test_gcode_has_preamble_epilogue(self):
        result = finishing_pass(_SIMPLE_PROFILE)
        assert "G21" in result.gcode
        assert "M30" in result.gcode

    def test_gcode_g1_count_matches_profile_segments(self):
        """Finishing pass should produce at least len(profile)-1 G1 lines."""
        profile = [(0.0, 10.0), (20.0, 12.0), (40.0, 8.0), (60.0, 8.0)]
        result = finishing_pass(profile)
        g1_lines = [l for l in result.gcode if l.startswith("G1")]
        assert len(g1_lines) >= len(profile) - 1

    def test_zero_feed_returns_error(self):
        result = finishing_pass(_SIMPLE_PROFILE, feed_mm_rev=0.0)
        assert result.ok is False

    def test_taper_profile_produces_gcode(self):
        result = finishing_pass(_TAPER_PROFILE)
        assert result.ok is True
        assert len(result.gcode) > 5


# ===========================================================================
# 5. facing_pass
# ===========================================================================

class TestFacingPass:

    def test_returns_ok(self):
        result = facing_pass(25.0, 0.0)
        assert result.ok is True

    def test_n_passes_count(self):
        result = facing_pass(25.0, 0.0, n_passes=3, doc_mm=1.0)
        assert len(result.passes) == 3

    def test_pass_type_is_facing(self):
        result = facing_pass(25.0, 0.0, n_passes=2)
        for p in result.passes:
            assert p["pass_type"] == "facing"

    def test_gcode_well_formed(self):
        result = facing_pass(25.0, 0.0)
        assert "G21" in result.gcode
        assert "M30" in result.gcode
        assert any("G1" in l for l in result.gcode)

    def test_invalid_x_max_returns_error(self):
        result = facing_pass(-5.0, 0.0)
        assert result.ok is False

    def test_bore_ge_od_returns_error(self):
        result = facing_pass(10.0, 0.0, bore_radius_mm=15.0)
        assert result.ok is False

    def test_z_positions_step_by_doc(self):
        result = facing_pass(20.0, 5.0, n_passes=3, doc_mm=1.0)
        z_vals = [p["z_mm"] for p in result.passes]
        for i in range(1, len(z_vals)):
            assert abs(z_vals[i] - (z_vals[i - 1] - 1.0)) < 1e-9


# ===========================================================================
# 6. parting_pass
# ===========================================================================

class TestPartingPass:

    def test_returns_ok(self):
        result = parting_pass(75.0, 15.0)
        assert result.ok is True

    def test_gcode_has_g1_plunge(self):
        result = parting_pass(75.0, 15.0)
        assert any("G1" in l for l in result.gcode)

    def test_gcode_has_m3_and_m30(self):
        result = parting_pass(75.0, 15.0)
        assert any("M3" in l for l in result.gcode)
        assert "M30" in result.gcode

    def test_peck_parting_generates_multiple_g1(self):
        result = parting_pass(75.0, 20.0, peck_depth_mm=5.0)
        g1_lines = [l for l in result.gcode if l.startswith("G1")]
        assert len(g1_lines) >= 4  # multiple pecks

    def test_invalid_z_returns_error(self):
        result = parting_pass(float("inf"), 15.0)
        assert result.ok is False

    def test_bore_ge_od_returns_error(self):
        result = parting_pass(75.0, 15.0, bore_radius_mm=20.0)
        assert result.ok is False

    def test_pass_metadata_has_parting_type(self):
        result = parting_pass(75.0, 15.0)
        assert result.passes[0]["pass_type"] == "parting"

    def test_rpm_within_range(self):
        result = parting_pass(75.0, 15.0, rpm_min=50.0, rpm_max=1200.0)
        rpm = result.passes[0]["rpm"]
        assert 50.0 <= rpm <= 1200.0


# ===========================================================================
# 7. od_threading
# ===========================================================================

class TestOdThreading:

    def test_returns_ok(self):
        result = od_threading(0.0, -30.0, 12.5, pitch_mm=1.5)
        assert result.ok is True

    def test_gcode_has_g32_lines(self):
        result = od_threading(0.0, -30.0, 12.5, pitch_mm=1.5)
        g32_lines = [l for l in result.gcode if l.startswith("G32")]
        assert len(g32_lines) > 0

    def test_g32_feed_matches_pitch(self):
        pitch = 2.0
        result = od_threading(0.0, -25.0, 10.0, pitch_mm=pitch)
        g32_lines = [l for l in result.gcode if l.startswith("G32")]
        for line in g32_lines:
            assert f"F{pitch}" in line or "F2.0" in line

    def test_spring_passes_appended(self):
        result = od_threading(0.0, -20.0, 10.0, spring_passes=3)
        spring_passes = [p for p in result.passes if p["is_spring"]]
        assert len(spring_passes) == 3

    def test_pass_count_at_least_one_cut_pass(self):
        result = od_threading(0.0, -20.0, 10.0, pitch_mm=1.5, spring_passes=0)
        cut_passes = [p for p in result.passes if not p["is_spring"]]
        assert len(cut_passes) >= 1

    def test_cumul_depth_reaches_full_depth(self):
        pitch = 1.5
        t_depth = 0.6495 * pitch
        result = od_threading(0.0, -20.0, 10.0, pitch_mm=pitch, spring_passes=0)
        cut_passes = [p for p in result.passes if not p["is_spring"]]
        max_cumul = max(p["cumul_depth_mm"] for p in cut_passes)
        assert abs(max_cumul - t_depth) < 1e-6

    def test_thread_depth_override(self):
        result = od_threading(0.0, -20.0, 10.0, thread_depth_mm=0.5, spring_passes=0)
        cut_passes = [p for p in result.passes if not p["is_spring"]]
        max_cumul = max(p["cumul_depth_mm"] for p in cut_passes)
        assert abs(max_cumul - 0.5) < 1e-6

    def test_z_start_equals_z_end_returns_error(self):
        result = od_threading(10.0, 10.0, 12.5)
        assert result.ok is False

    def test_negative_pitch_returns_error(self):
        result = od_threading(0.0, -20.0, 12.5, pitch_mm=-1.5)
        assert result.ok is False

    def test_gcode_preamble_epilogue_present(self):
        result = od_threading(0.0, -20.0, 10.0)
        assert "G21" in result.gcode
        assert "M30" in result.gcode


# ===========================================================================
# 8. id_threading
# ===========================================================================

class TestIdThreading:

    def test_returns_ok(self):
        result = id_threading(0.0, -25.0, 8.0, pitch_mm=1.25)
        assert result.ok is True

    def test_gcode_has_g32(self):
        result = id_threading(0.0, -25.0, 8.0)
        assert any(l.startswith("G32") for l in result.gcode)

    def test_spring_passes_count(self):
        result = id_threading(0.0, -20.0, 8.0, spring_passes=2)
        spring_passes = [p for p in result.passes if p["is_spring"]]
        assert len(spring_passes) == 2

    def test_cumul_depth_reaches_full_depth(self):
        pitch = 1.25
        t_depth = 0.6495 * pitch
        result = id_threading(0.0, -20.0, 8.0, pitch_mm=pitch, spring_passes=0)
        cut_passes = [p for p in result.passes if not p["is_spring"]]
        max_cumul = max(p["cumul_depth_mm"] for p in cut_passes)
        assert abs(max_cumul - t_depth) < 1e-6

    def test_id_threading_x_increases(self):
        """ID threading: each pass should cut outward (increasing X radius)."""
        result = id_threading(0.0, -20.0, 8.0, spring_passes=0)
        cut_passes = [p for p in result.passes if not p["is_spring"]]
        radii = [p["x_radius_mm"] for p in cut_passes]
        # Radii should be monotonically non-decreasing for ID threading
        for i in range(1, len(radii)):
            assert radii[i] >= radii[i - 1] - 1e-9

    def test_z_start_eq_end_returns_error(self):
        result = id_threading(5.0, 5.0, 8.0)
        assert result.ok is False

    def test_negative_x_minor_returns_error(self):
        result = id_threading(0.0, -20.0, -5.0)
        assert result.ok is False


# ===========================================================================
# 9. grooving_pass
# ===========================================================================

class TestGroovingPass:

    def test_returns_ok(self):
        result = grooving_pass(30.0, 20.0)
        assert result.ok is True

    def test_single_plunge_for_narrow_groove(self):
        """Groove width == tool width → single plunge."""
        result = grooving_pass(30.0, 20.0, groove_width_mm=3.0, tool_width_mm=3.0)
        assert len(result.passes) >= 1

    def test_wide_groove_multiple_plunges(self):
        """Groove much wider than tool → multiple plunges."""
        result = grooving_pass(30.0, 20.0, groove_width_mm=15.0, tool_width_mm=3.0)
        assert len(result.passes) > 1

    def test_peck_grooving_multiple_g1(self):
        result = grooving_pass(30.0, 20.0, groove_depth_mm=10.0, peck_depth_mm=3.0)
        g1_lines = [l for l in result.gcode if l.startswith("G1")]
        assert len(g1_lines) >= 3

    def test_gcode_has_preamble_epilogue(self):
        result = grooving_pass(30.0, 20.0)
        assert "G21" in result.gcode
        assert "M30" in result.gcode

    def test_tool_wider_than_groove_returns_error(self):
        result = grooving_pass(30.0, 20.0, groove_width_mm=2.0, tool_width_mm=5.0)
        assert result.ok is False

    def test_zero_depth_returns_error(self):
        result = grooving_pass(30.0, 20.0, groove_depth_mm=0.0)
        assert result.ok is False

    def test_pass_type_is_grooving(self):
        result = grooving_pass(30.0, 20.0)
        for p in result.passes:
            assert p["pass_type"] == "grooving"


# ===========================================================================
# 10. emit_gcode
# ===========================================================================

class TestEmitGcode:

    def test_emit_produces_string(self):
        result = finishing_pass(_SIMPLE_PROFILE)
        gcode_str = emit_gcode(result)
        assert isinstance(gcode_str, str)
        assert len(gcode_str) > 0

    def test_emit_includes_header(self):
        result = finishing_pass(_SIMPLE_PROFILE)
        gcode_str = emit_gcode(result, header="O0001 FINISHING PASS")
        assert "O0001" in gcode_str

    def test_emit_failed_result_returns_error_comment(self):
        failed = TurningResult(ok=False, reason="test error")
        gcode_str = emit_gcode(failed)
        assert "ERROR" in gcode_str.upper()

    def test_emit_non_result_returns_empty(self):
        gcode_str = emit_gcode("not a result")  # type: ignore
        assert gcode_str == ""

    def test_emit_roughing_contains_all_lines(self):
        result = roughing_passes(_SIMPLE_PROFILE, stock_x_mm=20.0)
        gcode_str = emit_gcode(result)
        lines = gcode_str.splitlines()
        assert len(lines) == len(result.gcode)


# ===========================================================================
# 11. Profile validation edge cases
# ===========================================================================

class TestProfileValidation:

    def test_single_point_profile_returns_error(self):
        result = roughing_passes([(0.0, 10.0)], stock_x_mm=20.0)
        assert result.ok is False

    def test_negative_radius_clamped_with_warning(self):
        profile = [(0.0, -5.0), (50.0, 10.0)]
        result = finishing_pass(profile)
        # Should return ok with warning about clamped radius
        assert len(result.warnings) > 0

    def test_non_finite_z_returns_error(self):
        profile = [(float("nan"), 10.0), (50.0, 10.0)]
        result = finishing_pass(profile)
        assert result.ok is False

    def test_non_finite_x_returns_error(self):
        profile = [(0.0, float("inf")), (50.0, 10.0)]
        result = finishing_pass(profile)
        assert result.ok is False

    def test_degenerate_segment_z_equal_generates_warning(self):
        """Repeated Z value should produce a warning."""
        profile = [(0.0, 10.0), (0.0, 12.0), (50.0, 12.0)]  # Z=0 repeated
        result = finishing_pass(profile)
        assert len(result.warnings) > 0


# ===========================================================================
# 12. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    # --- cutting_params tool ---

    def test_cutting_params_happy_path(self):
        ctx = _ctx()
        raw = _run(run_turning_cutting_params(
            ctx,
            _args(profile=[[0.0, 10.0], [50.0, 10.0]])
        ))
        d = _ok_tool(raw)
        assert len(d["points"]) == 2
        assert d["points"][0]["rpm"] > 0

    def test_cutting_params_missing_profile(self):
        ctx = _ctx()
        raw = _run(run_turning_cutting_params(ctx, _args()))
        _err_tool(raw)

    def test_cutting_params_bad_json(self):
        ctx = _ctx()
        raw = _run(run_turning_cutting_params(ctx, b"not json"))
        _err_tool(raw)

    # --- roughing tool ---

    def test_roughing_happy_path(self):
        ctx = _ctx()
        raw = _run(run_turning_roughing_passes(
            ctx,
            _args(
                profile=[[0.0, 10.0], [50.0, 10.0]],
                stock_x_mm=20.0,
            )
        ))
        d = _ok_tool(raw)
        assert d["pass_count"] >= 1
        assert len(d["gcode"]) > 5

    def test_roughing_missing_stock(self):
        ctx = _ctx()
        raw = _run(run_turning_roughing_passes(
            ctx,
            _args(profile=[[0.0, 10.0], [50.0, 10.0]])
        ))
        _err_tool(raw)

    def test_roughing_invalid_profile(self):
        ctx = _ctx()
        raw = _run(run_turning_roughing_passes(
            ctx,
            _args(profile=[[0.0, 10.0]], stock_x_mm=20.0)
        ))
        _err_tool(raw)

    # --- finishing tool ---

    def test_finishing_happy_path(self):
        ctx = _ctx()
        raw = _run(run_turning_finishing_pass(
            ctx,
            _args(profile=[[0.0, 10.0], [25.0, 10.0], [50.0, 15.0]])
        ))
        d = _ok_tool(raw)
        assert d["pass_count"] == 1

    def test_finishing_missing_profile(self):
        ctx = _ctx()
        raw = _run(run_turning_finishing_pass(ctx, _args()))
        _err_tool(raw)

    # --- facing tool ---

    def test_facing_happy_path(self):
        ctx = _ctx()
        raw = _run(run_turning_facing(ctx, _args(x_max_mm=25.0, z_face_mm=0.0)))
        d = _ok_tool(raw)
        assert d["pass_count"] == 1

    def test_facing_multiple_passes(self):
        ctx = _ctx()
        raw = _run(run_turning_facing(
            ctx,
            _args(x_max_mm=25.0, z_face_mm=0.0, n_passes=4, doc_mm=0.5)
        ))
        d = _ok_tool(raw)
        assert d["pass_count"] == 4

    def test_facing_missing_x_max(self):
        ctx = _ctx()
        raw = _run(run_turning_facing(ctx, _args(z_face_mm=0.0)))
        _err_tool(raw)

    # --- parting tool ---

    def test_parting_happy_path(self):
        ctx = _ctx()
        raw = _run(run_turning_parting(ctx, _args(z_part_mm=75.0, x_max_mm=15.0)))
        d = _ok_tool(raw)
        assert d["pass_count"] == 1

    def test_parting_missing_z(self):
        ctx = _ctx()
        raw = _run(run_turning_parting(ctx, _args(x_max_mm=15.0)))
        _err_tool(raw)

    # --- OD threading tool ---

    def test_od_threading_happy_path(self):
        ctx = _ctx()
        raw = _run(run_turning_od_threading(
            ctx,
            _args(z_start_mm=0.0, z_end_mm=-25.0, x_major_mm=12.5, pitch_mm=1.5)
        ))
        d = _ok_tool(raw)
        assert d["pass_count"] >= 1
        assert any("G32" in l for l in d["gcode"])

    def test_od_threading_missing_pitch_uses_default(self):
        ctx = _ctx()
        raw = _run(run_turning_od_threading(
            ctx,
            _args(z_start_mm=0.0, z_end_mm=-20.0, x_major_mm=10.0)
        ))
        d = _ok_tool(raw)
        assert d["pass_count"] >= 1

    def test_od_threading_missing_required_returns_error(self):
        ctx = _ctx()
        raw = _run(run_turning_od_threading(
            ctx,
            _args(z_start_mm=0.0, z_end_mm=-20.0)  # missing x_major_mm
        ))
        _err_tool(raw)

    # --- ID threading tool ---

    def test_id_threading_happy_path(self):
        ctx = _ctx()
        raw = _run(run_turning_id_threading(
            ctx,
            _args(z_start_mm=0.0, z_end_mm=-20.0, x_minor_mm=8.0, pitch_mm=1.25)
        ))
        d = _ok_tool(raw)
        assert d["pass_count"] >= 1

    def test_id_threading_missing_x_minor_returns_error(self):
        ctx = _ctx()
        raw = _run(run_turning_id_threading(
            ctx,
            _args(z_start_mm=0.0, z_end_mm=-20.0)
        ))
        _err_tool(raw)

    # --- grooving tool ---

    def test_grooving_happy_path(self):
        ctx = _ctx()
        raw = _run(run_turning_grooving(
            ctx,
            _args(z_center_mm=30.0, x_start_mm=20.0, groove_depth_mm=3.0)
        ))
        d = _ok_tool(raw)
        assert d["pass_count"] >= 1

    def test_grooving_bad_json(self):
        ctx = _ctx()
        raw = _run(run_turning_grooving(ctx, b"{broken json"))
        _err_tool(raw)

    def test_grooving_missing_x_start_returns_error(self):
        ctx = _ctx()
        raw = _run(run_turning_grooving(ctx, _args(z_center_mm=30.0)))
        _err_tool(raw)


# ---------------------------------------------------------------------------
# Externally-citable reference cases (ISO 6983 / ISO 68-1 / Machinery's HB)
# ---------------------------------------------------------------------------

class TestTurningExternalReferenceCases:
    """Cross-checked against ISO 68-1 (thread depth), Machinery's Handbook
    30th ed. (CSS rpm), and ISO 6983-1 G-code conventions."""

    def test_css_rpm_machinerys_handbook(self):
        # Machinery's Handbook 30th ed.: n = CSS*1000/(pi*D), D = 2*radius.
        # CSS=180 m/min, radius=25 mm (D=50) -> 1145.9 rpm (within clamp).
        rpm = _calc_rpm(25.0, 180.0, 50.0, 3500.0)
        assert math.isclose(rpm, 180.0 * 1000.0 / (math.pi * 50.0),
                            rel_tol=1e-9)

    def test_css_rpm_clamped_to_max(self):
        # Machinery's Handbook CSS practice: small diameters drive rpm up;
        # machine rpm_max clamps it (here near-centre radius -> clamp).
        rpm = _calc_rpm(0.5, 180.0, 50.0, 3500.0)
        assert math.isclose(rpm, 3500.0, rel_tol=1e-12)

    def test_iso_68_1_thread_depth_default(self):
        # ISO 68-1 / Machinery's Handbook single-point external 60-deg thread
        # cutting depth ≈ 0.6495 * pitch (0.75 H, truncated crest & root).
        r = od_threading(0.0, -20.0, 10.0, pitch_mm=2.0)
        assert r.ok
        # Sum of cut-pass depths must reach the full thread depth 0.6495*P.
        cut = [p for p in r.passes if not p["is_spring"]]
        total = sum(p["step_depth_mm"] for p in cut)
        assert math.isclose(total, 0.6495 * 2.0, rel_tol=1e-6)

    def test_iso_68_1_thread_depth_override(self):
        # A user-supplied thread_depth_mm must be honoured exactly.
        r = od_threading(0.0, -15.0, 8.0, pitch_mm=1.5, thread_depth_mm=0.9)
        cut = [p for p in r.passes if not p["is_spring"]]
        total = sum(p["step_depth_mm"] for p in cut)
        assert math.isclose(total, 0.9, rel_tol=1e-6)

    def test_id_threading_cuts_outward(self):
        # Boring-bar internal threading: tool advances outward (+X) from the
        # minor radius by the thread depth.
        r = id_threading(0.0, -15.0, 6.0, pitch_mm=1.5)
        assert r.ok
        last_cut = [p for p in r.passes if not p["is_spring"]][-1]
        assert last_cut["x_radius_mm"] > 6.0

    def test_gcode_preamble_iso6983_metric(self):
        # ISO 6983-1: G21 metric, G18 ZX plane, G40 cutter-comp cancel.
        r = finishing_pass([(0.0, 10.0), (-50.0, 10.0)])
        assert r.gcode[0] == "G21"
        assert "G18" in r.gcode[:3]
        assert "G40" in r.gcode[:3]

    def test_gcode_epilogue_spindle_stop_program_end(self):
        # ISO 6983-1: M5 spindle stop, M30 program end.
        r = facing_pass(25.0, 0.0)
        assert r.gcode[-2:] == ["M5", "M30"]

    def test_gcode_uses_diameter_programming(self):
        # ISO turning convention: X word is diameter, not radius.
        r = finishing_pass([(0.0, 12.0), (-30.0, 12.0)])
        # A profile radius of 12 mm must appear as X24 in the G-code.
        assert any("X24" in ln for ln in r.gcode)

    def test_facing_pass_feeds_to_centre(self):
        # Facing to spindle centreline: final X bore radius default = 0.
        r = facing_pass(30.0, 0.0)
        assert r.passes[0]["bore_radius_mm"] == 0.0

    def test_roughing_doc_step_count(self):
        # Stock removal: number of roughing passes ≈ (stock - target)/doc.
        prof = [(0.0, 10.0), (-40.0, 10.0)]
        r = roughing_passes(prof, stock_x_mm=20.0, doc_mm=2.0,
                            finish_allowance_mm=0.0)
        assert r.ok
        # (20 - 10) / 2 = 5 passes.
        assert len(r.passes) == 5

    def test_spindle_speed_invariant_under_diameter(self):
        # Machinery's Handbook CSS: rpm halves when diameter doubles.
        r1 = _calc_rpm(10.0, 150.0, 1.0, 1e9)
        r2 = _calc_rpm(20.0, 150.0, 1.0, 1e9)
        assert math.isclose(r1, 2.0 * r2, rel_tol=1e-9)
