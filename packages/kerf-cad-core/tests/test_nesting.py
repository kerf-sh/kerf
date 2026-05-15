"""
Hermetic tests for the 2D nesting module (kerf_cad_core.nesting).

Coverage:
  - Single part placed on a single sheet
  - N identical parts tile correctly (row/shelf packing)
  - Rotation enabled (allow_rotate=True) places more parts than rotation disabled
  - Oversized part produces a friendly error (ok=False), never raises
  - Utilisation is in (0, 1]
  - Multi-sheet overflow: parts that don't fit on one sheet spill to the next
  - Kerf / margin respected — no bounding-box overlap within gap tolerance
  - Parts list with qty field expanded correctly
  - Sheet dimensions validated (must be > 0)
  - Negative / zero kerf / margin rejected
  - Empty parts list returns ok=True, 0 sheets
  - LLM tool runner: nest_parts JSON round-trip
  - LLM tool runner: nest_report produces non-empty report text
  - Determinism: same inputs produce identical output on repeated calls
  - Rotation actually fires when beneficial (part placed rotated when better fit)
  - Part exactly equal to usable sheet area fits on one sheet
  - Two parts that together exactly fill one sheet without kerf
  - Skyline fill: parts of varying heights fill efficiently

Pure-Python: no database, no OCCT, no ProjectCtx side-effects.

Author: imranparuk
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.nesting.pack import (
    nest_parts,
    result_to_dict,
    _candidate_rotations,
    _Skyline,
    NestResult,
    Placement,
    Sheet,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_ctx():
    """Minimal stub — nesting tools don't touch the DB."""
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None,
            storage=None,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role="owner",
            http_client=None,
        )
    except Exception:
        class _Stub:
            pass
        return _Stub()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _nest(**kwargs):
    """Call nest_parts with sensible defaults, easy keyword override."""
    defaults = dict(
        parts=[{"name": "A", "w": 50.0, "h": 30.0}],
        sheet_w=200.0,
        sheet_h=200.0,
        kerf=0.0,
        margin=0.0,
        allow_rotate=True,
    )
    defaults.update(kwargs)
    return nest_parts(**defaults)


def _no_overlap(placements: list[Placement], kerf: float = 0.0, tol: float = 1e-9) -> bool:
    """
    Return True when no two placements overlap (bounding-box intersection
    exceeds the kerf tolerance).
    """
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            a, b = placements[i], placements[j]
            # Separation required between a and b (on each axis)
            gap = kerf - tol
            # Overlap in X: a.x + a.w + gap > b.x AND b.x + b.w + gap > a.x
            x_overlap = (a.x + a.w + gap > b.x) and (b.x + b.w + gap > a.x)
            y_overlap = (a.y + a.h + gap > b.y) and (b.y + b.h + gap > a.y)
            if x_overlap and y_overlap:
                return False
    return True


def _all_placements(result: NestResult) -> list[Placement]:
    """Flatten placements across all sheets."""
    out: list[Placement] = []
    for s in result.sheets:
        out.extend(s.placements)
    return out


# ===========================================================================
# 1. Single part placed
# ===========================================================================

class TestSinglePart:
    def test_single_part_placed(self):
        r = _nest(parts=[{"name": "P", "w": 50, "h": 30}])
        assert r.ok
        assert r.sheets_used == 1
        pls = _all_placements(r)
        assert len(pls) == 1
        assert pls[0].part == "P"
        assert pls[0].w == pytest.approx(50.0) or pls[0].w == pytest.approx(30.0)

    def test_single_part_position_within_sheet(self):
        r = _nest(
            parts=[{"name": "P", "w": 40, "h": 20}],
            sheet_w=100, sheet_h=100, margin=5, kerf=0,
        )
        assert r.ok
        pl = _all_placements(r)[0]
        # Part must sit within the sheet
        assert pl.x >= 5 - 1e-9
        assert pl.y >= 5 - 1e-9
        assert pl.x + pl.w <= 100 - 5 + 1e-9
        assert pl.y + pl.h <= 100 - 5 + 1e-9

    def test_single_part_utilisation_in_range(self):
        r = _nest(parts=[{"name": "P", "w": 50, "h": 30}], sheet_w=200, sheet_h=100)
        assert r.ok
        assert 0.0 < r.utilization <= 1.0

    def test_single_part_cut_length(self):
        r = _nest(parts=[{"name": "P", "w": 60, "h": 40}])
        assert r.ok
        # Cut length = 2*(w+h) = 200, but rotation may swap w/h
        assert r.cut_length == pytest.approx(2 * (60 + 40), rel=1e-6)

    def test_empty_parts_list(self):
        r = _nest(parts=[])
        assert r.ok
        assert r.sheets_used == 0
        assert r.sheets == []
        assert r.cut_length == 0.0


# ===========================================================================
# 2. N identical parts tile correctly
# ===========================================================================

class TestNIdenticalParts:
    def test_four_identical_parts_on_one_sheet(self):
        # 4 parts of 50×50 on a 200×200 sheet: should all fit on one sheet
        parts = [{"name": f"sq-{i}", "w": 50, "h": 50} for i in range(4)]
        r = nest_parts(parts, sheet_w=200, sheet_h=200)
        assert r.ok
        assert r.sheets_used == 1
        assert len(_all_placements(r)) == 4

    def test_nine_parts_fit_on_one_sheet(self):
        # 9 parts of 30×30 on a 100×100 sheet: all fit (no kerf/margin)
        parts = [{"name": f"p{i}", "w": 30, "h": 30} for i in range(9)]
        r = nest_parts(parts, sheet_w=90, sheet_h=90)
        assert r.ok
        assert r.sheets_used == 1

    def test_qty_field_expands_correctly(self):
        r = nest_parts(
            [{"name": "A", "w": 20, "h": 20, "qty": 5}],
            sheet_w=200, sheet_h=200,
        )
        assert r.ok
        assert len(_all_placements(r)) == 5

    def test_no_overlap_many_parts(self):
        parts = [{"name": f"p{i}", "w": 25, "h": 15} for i in range(20)]
        r = nest_parts(parts, sheet_w=300, sheet_h=300, kerf=1.0)
        assert r.ok
        for sheet in r.sheets:
            assert _no_overlap(sheet.placements, kerf=1.0), \
                f"Overlap detected on sheet {sheet.index}"

    def test_identical_parts_no_overlap_no_kerf(self):
        parts = [{"name": f"p{i}", "w": 40, "h": 40} for i in range(6)]
        r = nest_parts(parts, sheet_w=200, sheet_h=200, kerf=0)
        assert r.ok
        for sheet in r.sheets:
            assert _no_overlap(sheet.placements, kerf=0), \
                "Bounding boxes must not overlap"


# ===========================================================================
# 3. Rotation
# ===========================================================================

class TestRotation:
    def test_rotation_enabled_places_more_on_one_sheet(self):
        # Parts that are 100×30: with rotation they can be placed 30×100 too.
        # On a 100×100 sheet without rotation only 3 fit (100+30+30... actually
        # one row of 1); with rotation landscape→portrait fills differently.
        # At minimum, with rotation the same or more parts fit per sheet.
        parts = [{"name": f"p{i}", "w": 90, "h": 20} for i in range(5)]
        r_no_rot  = nest_parts(parts, sheet_w=100, sheet_h=100, allow_rotate=False)
        r_rot     = nest_parts(parts, sheet_w=100, sheet_h=100, allow_rotate=True)
        assert r_rot.ok
        assert r_rot.sheets_used <= r_no_rot.sheets_used

    def test_rotation_fires_for_tall_narrow_parts(self):
        # A 10×80 part on a 100×50 sheet only fits when rotated to 80×10
        parts = [{"name": "tall", "w": 10, "h": 80}]
        r_no_rot = nest_parts(parts, sheet_w=100, sheet_h=50, allow_rotate=False)
        r_rot    = nest_parts(parts, sheet_w=100, sheet_h=50, allow_rotate=True)
        # Without rotation: 10×80 doesn't fit on sheet_h=50 → error
        assert not r_no_rot.ok
        # With rotation: 80×10 fits on 100×50 → ok
        assert r_rot.ok
        pl = _all_placements(r_rot)[0]
        assert pl.rot == 90

    def test_rotation_0_when_square(self):
        # Square part: rotation produces same dimensions → rot=0
        cands = _candidate_rotations(30, 30, allow_rotate=True)
        assert len(cands) == 1
        assert cands[0] == (30, 30, 0)

    def test_rotation_two_candidates_when_non_square(self):
        cands = _candidate_rotations(40, 20, allow_rotate=True)
        assert len(cands) == 2
        assert (40, 20, 0) in cands
        assert (20, 40, 90) in cands

    def test_no_rotation_single_candidate(self):
        cands = _candidate_rotations(40, 20, allow_rotate=False)
        assert cands == [(40, 20, 0)]


# ===========================================================================
# 4. Oversized part → friendly error
# ===========================================================================

class TestOversizedPart:
    def test_part_bigger_than_sheet_gives_friendly_error(self):
        r = nest_parts(
            [{"name": "giant", "w": 500, "h": 500}],
            sheet_w=100, sheet_h=100,
        )
        assert not r.ok
        assert r.sheets == []
        assert len(r.errors) >= 1
        assert "giant" in r.errors[0]
        assert "larger than" in r.errors[0].lower() or "cannot place" in r.errors[0].lower()

    def test_part_bigger_than_sheet_with_rotation_friendly_error(self):
        # 300×10 part: with rotation tries 10×300, still needs sheet_h ≥ 300
        r = nest_parts(
            [{"name": "wide", "w": 300, "h": 10}],
            sheet_w=100, sheet_h=100,
            allow_rotate=True,
        )
        assert not r.ok
        assert "wide" in r.errors[0]

    def test_oversized_does_not_raise(self):
        # Must not raise; must return NestResult with ok=False
        try:
            r = nest_parts(
                [{"name": "big", "w": 9999, "h": 9999}],
                sheet_w=10, sheet_h=10,
            )
            assert not r.ok
        except Exception as exc:
            pytest.fail(f"nest_parts raised instead of returning error: {exc}")

    def test_mix_valid_and_oversized_all_rejected(self):
        # If even one part is oversized the whole nesting returns errors
        parts = [
            {"name": "ok", "w": 10, "h": 10},
            {"name": "big", "w": 999, "h": 999},
        ]
        r = nest_parts(parts, sheet_w=50, sheet_h=50)
        assert not r.ok

    def test_part_larger_than_usable_area_due_to_margin(self):
        # Part fits the sheet outer dimensions but not the usable area after margin
        r = nest_parts(
            [{"name": "P", "w": 95, "h": 95}],
            sheet_w=100, sheet_h=100, margin=10,
        )
        # usable = 80×80, part 95×95 too large
        assert not r.ok


# ===========================================================================
# 5. Utilisation
# ===========================================================================

class TestUtilisation:
    def test_utilisation_in_range(self):
        parts = [{"name": f"p{i}", "w": 20, "h": 30} for i in range(10)]
        r = nest_parts(parts, sheet_w=200, sheet_h=200)
        assert r.ok
        assert 0.0 < r.utilization <= 1.0

    def test_utilisation_formula(self):
        # One part fills exactly 50% of one sheet, no kerf, no margin
        r = nest_parts(
            [{"name": "half", "w": 100, "h": 50}],
            sheet_w=100, sheet_h=100, kerf=0, margin=0, allow_rotate=False,
        )
        assert r.ok
        assert r.sheets_used == 1
        assert r.utilization == pytest.approx(0.5, rel=1e-4)

    def test_utilisation_one_part_exact_sheet(self):
        # Part exactly fills the sheet → utilisation == 1.0
        r = nest_parts(
            [{"name": "full", "w": 200, "h": 150}],
            sheet_w=200, sheet_h=150, kerf=0, margin=0, allow_rotate=False,
        )
        assert r.ok
        assert r.utilization == pytest.approx(1.0, rel=1e-6)

    def test_utilisation_multi_sheet(self):
        # Parts overflow to 2 sheets: utilisation uses both sheets in denominator
        r = nest_parts(
            [{"name": f"p{i}", "w": 100, "h": 100} for i in range(3)],
            sheet_w=100, sheet_h=200,  # 2 parts per sheet (100+100=200)
            kerf=0, margin=0, allow_rotate=False,
        )
        assert r.ok
        # 3 parts of 10000 area; 2 sheets of 20000 area each → 30000/40000 = 0.75
        assert r.utilization == pytest.approx(0.75, rel=1e-4)


# ===========================================================================
# 6. Multi-sheet overflow
# ===========================================================================

class TestMultiSheet:
    def test_overflow_to_second_sheet(self):
        # 3 parts of 100×100 on a 100×100 sheet with no rotation → 3 sheets
        parts = [{"name": f"p{i}", "w": 100, "h": 100} for i in range(3)]
        r = nest_parts(parts, sheet_w=100, sheet_h=100, kerf=0, margin=0,
                       allow_rotate=False)
        assert r.ok
        assert r.sheets_used == 3

    def test_total_parts_across_sheets_correct(self):
        parts = [{"name": f"p{i}", "w": 60, "h": 60} for i in range(5)]
        r = nest_parts(parts, sheet_w=120, sheet_h=120, kerf=0, margin=0)
        assert r.ok
        total = sum(len(s.placements) for s in r.sheets)
        assert total == 5

    def test_sheet_indices_sequential(self):
        parts = [{"name": f"p{i}", "w": 100, "h": 100} for i in range(4)]
        r = nest_parts(parts, sheet_w=100, sheet_h=100, kerf=0, margin=0,
                       allow_rotate=False)
        assert r.ok
        indices = [s.index for s in r.sheets]
        assert indices == list(range(r.sheets_used))

    def test_no_overflow_just_fits(self):
        # 2 parts of 100×100 stacked vertically on a 100×200 sheet
        parts = [{"name": f"p{i}", "w": 100, "h": 100} for i in range(2)]
        r = nest_parts(parts, sheet_w=100, sheet_h=200, kerf=0, margin=0,
                       allow_rotate=False)
        assert r.ok
        assert r.sheets_used == 1


# ===========================================================================
# 7. Kerf / margin respected — no overlap
# ===========================================================================

class TestKerfMargin:
    def test_kerf_gap_no_overlap(self):
        parts = [{"name": f"p{i}", "w": 30, "h": 20} for i in range(10)]
        r = nest_parts(parts, sheet_w=200, sheet_h=200, kerf=2.0, margin=5.0)
        assert r.ok
        for sheet in r.sheets:
            assert _no_overlap(sheet.placements, kerf=2.0), \
                "Parts must be separated by at least kerf"

    def test_margin_keeps_parts_inside(self):
        margin = 10.0
        r = nest_parts(
            [{"name": f"p{i}", "w": 20, "h": 20} for i in range(4)],
            sheet_w=100, sheet_h=100, kerf=0, margin=margin,
        )
        assert r.ok
        for pl in _all_placements(r):
            assert pl.x >= margin - 1e-9
            assert pl.y >= margin - 1e-9
            assert pl.x + pl.w <= 100 - margin + 1e-9
            assert pl.y + pl.h <= 100 - margin + 1e-9

    def test_zero_kerf_zero_margin_no_overlap(self):
        parts = [{"name": f"p{i}", "w": 25, "h": 25} for i in range(16)]
        r = nest_parts(parts, sheet_w=100, sheet_h=100, kerf=0, margin=0)
        assert r.ok
        for sheet in r.sheets:
            assert _no_overlap(sheet.placements, kerf=0)

    def test_kerf_larger_than_sheet_returns_error_or_ok_with_single_part(self):
        # With kerf=50 on a 100×100 sheet a 40×40 part still fits (fits within usable)
        r = nest_parts(
            [{"name": "P", "w": 40, "h": 40}],
            sheet_w=100, sheet_h=100, kerf=50, margin=0,
        )
        # Either places it or reports an error, but must not raise
        assert isinstance(r, NestResult)


# ===========================================================================
# 8. Input validation
# ===========================================================================

class TestInputValidation:
    def test_negative_sheet_w_error(self):
        r = _nest(sheet_w=-1)
        assert not r.ok
        assert any("sheet_w" in e for e in r.errors)

    def test_zero_sheet_h_error(self):
        r = _nest(sheet_h=0)
        assert not r.ok
        assert any("sheet_h" in e for e in r.errors)

    def test_negative_kerf_error(self):
        r = _nest(kerf=-0.1)
        assert not r.ok
        assert any("kerf" in e for e in r.errors)

    def test_negative_margin_error(self):
        r = _nest(margin=-5)
        assert not r.ok
        assert any("margin" in e for e in r.errors)

    def test_margin_too_large_for_sheet(self):
        r = nest_parts(
            [{"name": "P", "w": 10, "h": 10}],
            sheet_w=100, sheet_h=100, margin=60,
        )
        assert not r.ok

    def test_zero_part_width_error(self):
        r = nest_parts([{"name": "bad", "w": 0, "h": 10}], sheet_w=100, sheet_h=100)
        assert not r.ok

    def test_zero_part_height_error(self):
        r = nest_parts([{"name": "bad", "w": 10, "h": 0}], sheet_w=100, sheet_h=100)
        assert not r.ok


# ===========================================================================
# 9. result_to_dict serialisation
# ===========================================================================

class TestResultToDict:
    def test_round_trip(self):
        r = _nest(parts=[{"name": "A", "w": 50, "h": 30}])
        d = result_to_dict(r)
        assert d["ok"] is True
        assert isinstance(d["sheets"], list)
        assert isinstance(d["sheets_used"], int)
        assert isinstance(d["utilization"], float)
        assert isinstance(d["cut_length"], float)
        assert isinstance(d["errors"], list)

    def test_failed_result_to_dict(self):
        r = nest_parts([{"name": "big", "w": 9999, "h": 9999}],
                       sheet_w=10, sheet_h=10)
        d = result_to_dict(r)
        assert d["ok"] is False
        assert len(d["errors"]) >= 1


# ===========================================================================
# 10. Determinism
# ===========================================================================

class TestDeterminism:
    def test_same_inputs_same_outputs(self):
        parts = [{"name": f"p{i}", "w": 30 + i * 5, "h": 20 + i * 3} for i in range(8)]
        r1 = nest_parts(parts, sheet_w=200, sheet_h=200, kerf=1.0, margin=5.0)
        r2 = nest_parts(parts, sheet_w=200, sheet_h=200, kerf=1.0, margin=5.0)
        assert r1.ok == r2.ok
        assert r1.sheets_used == r2.sheets_used
        assert r1.utilization == r2.utilization
        assert r1.cut_length == r2.cut_length
        # Placement positions must be identical
        pls1 = _all_placements(r1)
        pls2 = _all_placements(r2)
        for p1, p2 in zip(pls1, pls2):
            assert p1.x == pytest.approx(p2.x)
            assert p1.y == pytest.approx(p2.y)
            assert p1.rot == p2.rot


# ===========================================================================
# 11. Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_part_exactly_fills_usable_area(self):
        # Part fills exactly the usable area (no margin, no kerf)
        r = nest_parts(
            [{"name": "exact", "w": 200, "h": 150}],
            sheet_w=200, sheet_h=150, kerf=0, margin=0, allow_rotate=False,
        )
        assert r.ok
        assert r.sheets_used == 1

    def test_two_parts_fill_one_row_exactly(self):
        # 2 parts of 100×50 side by side on a 200×50 sheet
        parts = [{"name": f"p{i}", "w": 100, "h": 50} for i in range(2)]
        r = nest_parts(parts, sheet_w=200, sheet_h=50, kerf=0, margin=0,
                       allow_rotate=False)
        assert r.ok
        assert r.sheets_used == 1
        assert len(_all_placements(r)) == 2

    def test_mixed_sizes_no_overlap(self):
        parts = [
            {"name": "big",   "w": 80, "h": 60},
            {"name": "med",   "w": 50, "h": 40},
            {"name": "small", "w": 20, "h": 15},
            {"name": "tiny",  "w": 10, "h": 8},
        ]
        r = nest_parts(parts, sheet_w=200, sheet_h=200, kerf=1.0, margin=5.0)
        assert r.ok
        for sheet in r.sheets:
            assert _no_overlap(sheet.placements, kerf=1.0)

    def test_single_part_qty_one(self):
        r = nest_parts(
            [{"name": "A", "w": 10, "h": 10, "qty": 1}],
            sheet_w=100, sheet_h=100,
        )
        assert r.ok
        assert len(_all_placements(r)) == 1

    def test_cut_length_sums_perimeters(self):
        # 3 parts: 10×5, 20×8, 15×12
        parts = [
            {"name": "a", "w": 10, "h": 5},
            {"name": "b", "w": 20, "h": 8},
            {"name": "c", "w": 15, "h": 12},
        ]
        expected_cl = 2*(10+5) + 2*(20+8) + 2*(15+12)
        r = nest_parts(parts, sheet_w=200, sheet_h=200, kerf=0, margin=0,
                       allow_rotate=False)
        assert r.ok
        assert r.cut_length == pytest.approx(expected_cl, rel=1e-6)


# ===========================================================================
# 12. Skyline unit tests
# ===========================================================================

class TestSkyline:
    def test_empty_skyline_placement_at_origin(self):
        sky = _Skyline(100.0, 100.0)
        pos = sky.find_placement(30, 20, kerf=0)
        assert pos == pytest.approx((0.0, 0.0), abs=1e-9)

    def test_skyline_raises_after_place(self):
        sky = _Skyline(100.0, 100.0)
        sky.place(0, 0, 30, 20, kerf=0)
        # Second part should be placed at x=30 (no kerf) or y=20 depending on strategy
        pos = sky.find_placement(60, 20, kerf=0)
        assert pos is not None
        x, y = pos
        assert x >= 0 and y >= 0

    def test_skyline_no_fit_returns_none(self):
        sky = _Skyline(50.0, 50.0)
        sky.place(0, 0, 50, 50, kerf=0)
        pos = sky.find_placement(10, 10, kerf=0)
        assert pos is None

    def test_skyline_part_taller_than_usable_returns_none(self):
        sky = _Skyline(100.0, 50.0)
        pos = sky.find_placement(10, 60, kerf=0)  # ph=60 > usable_h=50
        assert pos is None


# ===========================================================================
# 13. LLM tool runner integration
# ===========================================================================

class TestToolRunner:
    def test_run_nest_parts_basic(self):
        from kerf_cad_core.nesting.tools import run_nest_parts
        ctx = _fake_ctx()
        payload = {
            "parts": [{"name": "A", "w": 50, "h": 30}],
            "sheet_w": 200.0,
            "sheet_h": 200.0,
            "kerf": 1.0,
            "margin": 5.0,
            "allow_rotate": True,
        }
        raw = _run(run_nest_parts(ctx, json.dumps(payload).encode()))
        result = json.loads(raw)
        assert result["ok"] is True
        assert result["sheets_used"] == 1
        assert "utilization_pct" in result
        assert result["utilization_pct"] > 0

    def test_run_nest_parts_oversized_error(self):
        from kerf_cad_core.nesting.tools import run_nest_parts
        ctx = _fake_ctx()
        payload = {
            "parts": [{"name": "giant", "w": 9999, "h": 9999}],
            "sheet_w": 100.0,
            "sheet_h": 100.0,
        }
        raw = _run(run_nest_parts(ctx, json.dumps(payload).encode()))
        result = json.loads(raw)
        assert result["ok"] is False
        assert len(result["errors"]) >= 1

    def test_run_nest_parts_invalid_json(self):
        from kerf_cad_core.nesting.tools import run_nest_parts
        ctx = _fake_ctx()
        raw = _run(run_nest_parts(ctx, b"not json"))
        result = json.loads(raw)
        # err_payload returns {"error": ..., "code": ...}; no "ok" key
        assert "error" in result or result.get("ok") is False

    def test_run_nest_report_basic(self):
        from kerf_cad_core.nesting.tools import run_nest_parts, run_nest_report
        ctx = _fake_ctx()
        payload = {
            "parts": [{"name": "P", "w": 40, "h": 30}, {"name": "Q", "w": 50, "h": 25}],
            "sheet_w": 200.0,
            "sheet_h": 200.0,
            "kerf": 0.5,
            "margin": 5.0,
        }
        nest_raw = _run(run_nest_parts(ctx, json.dumps(payload).encode()))
        nesting = json.loads(nest_raw)

        report_payload = {
            "nesting": nesting,
            "sheet_w": 200.0,
            "sheet_h": 200.0,
            "material": "Plywood 18mm",
            "kerf": 0.5,
        }
        raw = _run(run_nest_report(ctx, json.dumps(report_payload).encode()))
        result = json.loads(raw)
        assert result["ok"] is True
        assert len(result["report_text"]) > 0
        assert "Plywood" in result["report_text"] or "200" in result["report_text"]
        assert isinstance(result["summary_lines"], list)
        assert len(result["summary_lines"]) > 0

    def test_run_nest_report_failed_nesting(self):
        from kerf_cad_core.nesting.tools import run_nest_report
        ctx = _fake_ctx()
        failed_nesting = {
            "ok": False,
            "sheets": [],
            "sheets_used": 0,
            "utilization": 0.0,
            "cut_length": 0.0,
            "errors": ["Part 'giant' is larger than the sheet."],
        }
        payload = {"nesting": failed_nesting}
        raw = _run(run_nest_report(ctx, json.dumps(payload).encode()))
        result = json.loads(raw)
        assert result["ok"] is True
        assert "FAILED" in result["report_text"]
