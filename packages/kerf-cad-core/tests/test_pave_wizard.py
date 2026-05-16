"""
Tests for kerf_cad_core.jewelry.pave_wizard.

All tests are pure-Python — no database, no OCCT.

Coverage (≥30 tests):
  1.  compute_pave_placements / grid layout: stone count vs analytic estimate
  2.  compute_pave_placements / hex layout: stone count vs analytic estimate
  3.  compute_pave_placements / flow_line layout: count vs simple estimate
  4.  No overlap (grid): pairwise centre distance ≥ stone_diameter + stone_spacing
  5.  No overlap (hex): same check
  6.  No overlap (flow_line): same check
  7.  All seats inside surface domain with edge margin (grid)
  8.  All seats inside surface domain with edge margin (hex)
  9.  Edge margin = 0 does not crash; placement within region
  10. Empty region (edge_margin > half dimension) returns no placements
  11. Stone too large for region returns empty list
  12. Hex layout uses smaller row pitch than grid (denser rows)
  13. Shared-bead count: each 2×2 cluster of grid stones → one bead minimum
  14. Shared-bead count satisfies expected lattice lower/upper bounds
  15. Fishtail: exactly 2 beads per stone
  16. U-cut: exactly 2 beads per stone
  17. Channel: exactly 1 bead per stone
  18. Seat cutters: one per stone placement
  19. Seat cutter depth ≈ diameter × _SEAT_DEPTH_FACTOR
  20. Seat cutter radius_top = stone_diameter / 2
  21. Seat cutter normal stored from placement
  22. Coverage fraction is in (0, 100]
  23. Coverage increases with smaller stone_spacing
  24. Stats: total_carat = stone_count × carat_from_mm(stone_diameter)
  25. Stats: metal_removed_mm3 > 0 when placements exist
  26. LLM tool spec: name and required fields
  27. LLM tool spec: layout enum and bead_style enum
  28. LLM tool runner: success path — ok payload with correct keys
  29. LLM tool runner: stone_count in payload matches placements
  30. LLM tool runner: BAD_ARGS on missing file_id
  31. LLM tool runner: BAD_ARGS on non-positive stone_diameter
  32. LLM tool runner: BAD_ARGS on invalid layout
  33. LLM tool runner: BAD_ARGS on invalid bead_style
  34. LLM tool runner: NOT_FOUND when file missing
  35. LLM tool runner: node appended to feature doc
  36. Stats tool: returns correct stone_count from stored node
  37. Update tool: re-runs with new layout, stone_count changes
  38. Update tool: NOT_FOUND for unknown node_id
  39. Surface samples: placements use interpolated z / normal
  40. Shared-bead bead count ≤ stone_count (beads shared, never exceed stones)
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.jewelry.pave_wizard import (
    _SEAT_DEPTH_FACTOR,
    _VALID_BEAD_STYLES,
    _VALID_LAYOUTS,
    _pave_wizard_spec,
    _pave_wizard_stats_spec,
    _pave_wizard_update_spec,
    build_pave_wizard_node,
    compute_bead_positions,
    compute_pave_placements,
    compute_stats,
    run_pave_wizard,
    run_pave_wizard_stats,
    run_pave_wizard_update,
)
from kerf_cad_core.jewelry.gemstones import carat_from_mm


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


def run_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def call_tool(runner, ctx, file_id, **kwargs):
    a = {"file_id": str(file_id), **kwargs}
    raw = run_sync(runner(ctx, json.dumps(a).encode()))
    return json.loads(raw)


def call_tool_no_file(runner, ctx, **kwargs):
    raw = run_sync(runner(ctx, json.dumps(kwargs).encode()))
    return json.loads(raw)


def centre_dist_xy(p, q):
    """Use stored x,y coordinates (mm) — avoids u/v rounding artefacts."""
    dx = p["x"] - q["x"]
    dy = p["y"] - q["y"]
    return math.sqrt(dx * dx + dy * dy)


def centre_dist(p, q, region_width, region_height):
    dx = (p["u"] - q["u"]) * region_width
    dy = (p["v"] - q["v"]) * region_height
    return math.sqrt(dx * dx + dy * dy)


# Flat-surface analytic grid stone count helper.
def analytic_grid_count(rw, rh, sd, ss, em):
    pitch = sd + ss
    usable_w = rw - 2 * em
    usable_h = rh - 2 * em
    if usable_w <= 0 or usable_h <= 0:
        return 0
    return max(1, int(math.floor(usable_w / pitch))) * max(1, int(math.floor(usable_h / pitch)))


def analytic_hex_rows(rw, rh, sd, ss, em):
    pitch = sd + ss
    row_pitch = pitch * math.sqrt(3) / 2
    usable_h = rh - 2 * em
    if usable_h <= 0:
        return 0
    return max(1, int(math.floor(usable_h / row_pitch)))


# ---------------------------------------------------------------------------
# 1. Grid layout stone count vs analytic estimate
# ---------------------------------------------------------------------------

class TestGridCount:
    def test_count_matches_analytic(self):
        rw, rh, sd, ss, em = 10.0, 8.0, 1.5, 0.15, 0.3
        places = compute_pave_placements(rw, rh, sd, ss, em, layout="grid")
        expected = analytic_grid_count(rw, rh, sd, ss, em)
        assert len(places) == expected

    def test_count_increases_with_smaller_spacing(self):
        rw, rh, sd, em = 12.0, 10.0, 1.5, 0.3
        p1 = compute_pave_placements(rw, rh, sd, 0.3, em, layout="grid")
        p2 = compute_pave_placements(rw, rh, sd, 0.15, em, layout="grid")
        assert len(p2) >= len(p1)

    def test_count_positive_for_reasonable_params(self):
        places = compute_pave_placements(20.0, 10.0, 2.0, 0.2, 0.4, layout="grid")
        assert len(places) > 0


# ---------------------------------------------------------------------------
# 2. Hex layout stone count vs analytic estimate
# ---------------------------------------------------------------------------

class TestHexCount:
    def test_count_plausible(self):
        rw, rh, sd, ss, em = 10.0, 8.0, 1.5, 0.15, 0.3
        places = compute_pave_placements(rw, rh, sd, ss, em, layout="hex")
        # Hex should produce at least as many as grid (more rows possible).
        grid_places = compute_pave_placements(rw, rh, sd, ss, em, layout="grid")
        assert len(places) >= len(grid_places) - 2  # allow ±2 for boundary effects

    def test_hex_row_count(self):
        rw, rh, sd, ss, em = 10.0, 8.0, 1.5, 0.15, 0.3
        places = compute_pave_placements(rw, rh, sd, ss, em, layout="hex")
        rows_present = len(set(p["row"] for p in places))
        expected_rows = analytic_hex_rows(rw, rh, sd, ss, em)
        assert rows_present == expected_rows

    def test_odd_rows_offset_from_even(self):
        places = compute_pave_placements(10.0, 10.0, 1.5, 0.15, 0.3, layout="hex")
        even_us = [p["u"] for p in places if p["row"] % 2 == 0 and p["col"] == 0]
        odd_us = [p["u"] for p in places if p["row"] % 2 == 1 and p["col"] == 0]
        if even_us and odd_us:
            # Odd rows are offset: their first stone has larger u than even rows.
            assert odd_us[0] > even_us[0]


# ---------------------------------------------------------------------------
# 3. Flow-line layout
# ---------------------------------------------------------------------------

class TestFlowLine:
    def test_count_positive(self):
        places = compute_pave_placements(10.0, 8.0, 1.5, 0.15, 0.3, layout="flow_line")
        assert len(places) > 0

    def test_count_comparable_to_grid(self):
        rw, rh, sd, ss, em = 10.0, 8.0, 1.5, 0.15, 0.3
        fl = compute_pave_placements(rw, rh, sd, ss, em, layout="flow_line")
        gr = compute_pave_placements(rw, rh, sd, ss, em, layout="grid")
        # Should be within a factor of 2 of grid.
        assert len(fl) > 0
        assert len(fl) <= len(gr) * 2 + 2


# ---------------------------------------------------------------------------
# 4-6. No-overlap checks
# ---------------------------------------------------------------------------

class TestNoOverlap:
    def _check_no_overlap(self, places, sd, ss, rw, rh):
        min_dist = sd + ss
        for i in range(len(places)):
            for j in range(i + 1, len(places)):
                # Use stored x,y (mm) for accuracy; avoids u/v rounding artefacts.
                d = centre_dist_xy(places[i], places[j])
                assert d >= min_dist - 1e-3, (
                    f"Overlap between stone {i} and {j}: dist={d:.4f}, "
                    f"required >= {min_dist:.4f}"
                )

    def test_no_overlap_grid(self):
        rw, rh, sd, ss, em = 12.0, 10.0, 1.5, 0.15, 0.3
        places = compute_pave_placements(rw, rh, sd, ss, em, layout="grid")
        self._check_no_overlap(places, sd, ss, rw, rh)

    def test_no_overlap_hex(self):
        rw, rh, sd, ss, em = 12.0, 10.0, 1.5, 0.15, 0.3
        places = compute_pave_placements(rw, rh, sd, ss, em, layout="hex")
        self._check_no_overlap(places, sd, ss, rw, rh)

    def test_no_overlap_flow_line(self):
        rw, rh, sd, ss, em = 12.0, 10.0, 1.5, 0.15, 0.3
        places = compute_pave_placements(rw, rh, sd, ss, em, layout="flow_line")
        self._check_no_overlap(places, sd, ss, rw, rh)


# ---------------------------------------------------------------------------
# 7-8. All seats inside surface domain with edge margin
# ---------------------------------------------------------------------------

class TestInsideDomain:
    def _check_inside(self, places, rw, rh, sd, em):
        r = sd / 2
        for i, p in enumerate(places):
            # Use stored mm coordinates (accurate; no u/v round-trip error).
            px = p["x"]
            py = p["y"]
            assert px - r >= em - 1e-3, f"Stone {i} too close to left edge"
            assert px + r <= rw - em + 1e-3, f"Stone {i} too close to right edge"
            assert py - r >= em - 1e-3, f"Stone {i} too close to bottom edge"
            assert py + r <= rh - em + 1e-3, f"Stone {i} too close to top edge"

    def test_inside_domain_grid(self):
        rw, rh, sd, ss, em = 12.0, 10.0, 1.5, 0.15, 0.3
        places = compute_pave_placements(rw, rh, sd, ss, em, layout="grid")
        self._check_inside(places, rw, rh, sd, em)

    def test_inside_domain_hex(self):
        rw, rh, sd, ss, em = 12.0, 10.0, 1.5, 0.15, 0.3
        places = compute_pave_placements(rw, rh, sd, ss, em, layout="hex")
        self._check_inside(places, rw, rh, sd, em)


# ---------------------------------------------------------------------------
# 9-11. Edge / boundary cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_edge_margin_no_crash(self):
        places = compute_pave_placements(10.0, 8.0, 1.5, 0.2, 0.0, layout="grid")
        assert isinstance(places, list)

    def test_large_edge_margin_empty(self):
        # Edge margin consumes entire region.
        places = compute_pave_placements(5.0, 5.0, 1.5, 0.15, 3.0, layout="grid")
        assert places == []

    def test_stone_too_large_empty(self):
        # Stone larger than usable area.
        places = compute_pave_placements(3.0, 3.0, 5.0, 0.15, 0.3, layout="grid")
        assert places == []


# ---------------------------------------------------------------------------
# 12. Hex denser than grid
# ---------------------------------------------------------------------------

class TestHexDenser:
    def test_hex_more_rows_than_grid(self):
        rw, rh, sd, ss, em = 10.0, 10.0, 1.5, 0.15, 0.3
        hex_rows = len(set(p["row"] for p in compute_pave_placements(rw, rh, sd, ss, em, layout="hex")))
        grid_rows = len(set(p["row"] for p in compute_pave_placements(rw, rh, sd, ss, em, layout="grid")))
        assert hex_rows >= grid_rows


# ---------------------------------------------------------------------------
# 13-14. Shared-bead count
# ---------------------------------------------------------------------------

class TestSharedBeadCount:
    def _make_placements(self, rw=10.0, rh=8.0, sd=1.5, ss=0.15, em=0.3, layout="grid"):
        return compute_pave_placements(rw, rh, sd, ss, em, layout=layout)

    def test_bead_count_lower_bound(self):
        places = self._make_placements()
        beads = compute_bead_positions(places, 1.5, 0.15, "shared_bead")
        # At minimum one bead per 2×2 cluster; upper bound = stone_count.
        assert len(beads) >= 1
        assert len(beads) <= len(places)

    def test_bead_count_expected_lattice(self):
        # A 3×3 grid of stones produces 2×2=4 cluster origins → 4 shared beads.
        rw, rh, sd, ss, em = 10.0, 10.0, 1.5, 0.15, 0.3
        places = [
            {"u": 0.15, "v": 0.15, "x": 1.5, "y": 1.5, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 0, "col": 0, "warn": ""},
            {"u": 0.35, "v": 0.15, "x": 3.5, "y": 1.5, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 0, "col": 1, "warn": ""},
            {"u": 0.55, "v": 0.15, "x": 5.5, "y": 1.5, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 0, "col": 2, "warn": ""},
            {"u": 0.15, "v": 0.35, "x": 1.5, "y": 3.5, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 1, "col": 0, "warn": ""},
            {"u": 0.35, "v": 0.35, "x": 3.5, "y": 3.5, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 1, "col": 1, "warn": ""},
            {"u": 0.55, "v": 0.35, "x": 5.5, "y": 3.5, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 1, "col": 2, "warn": ""},
            {"u": 0.15, "v": 0.55, "x": 1.5, "y": 5.5, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 2, "col": 0, "warn": ""},
            {"u": 0.35, "v": 0.55, "x": 3.5, "y": 5.5, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 2, "col": 1, "warn": ""},
            {"u": 0.55, "v": 0.55, "x": 5.5, "y": 5.5, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 2, "col": 2, "warn": ""},
        ]
        beads = compute_bead_positions(places, 1.5, 0.15, "shared_bead")
        # 3×3 grid → (3-1)×(3-1) = 4 shared beads.
        assert len(beads) == 4


# ---------------------------------------------------------------------------
# 15-17. Per-stone bead counts (fishtail, u_cut, channel)
# ---------------------------------------------------------------------------

class TestPerStoneBead:
    def _make_two_stones(self):
        return [
            {"u": 0.2, "v": 0.2, "x": 2.0, "y": 2.0, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 0, "col": 0, "warn": ""},
            {"u": 0.6, "v": 0.6, "x": 6.0, "y": 6.0, "z": 0.0,
             "nx": 0.0, "ny": 0.0, "nz": 1.0, "row": 1, "col": 1, "warn": ""},
        ]

    def test_fishtail_two_beads_per_stone(self):
        places = self._make_two_stones()
        beads = compute_bead_positions(places, 1.5, 0.15, "fishtail")
        assert len(beads) == 4  # 2 stones × 2 beads

    def test_u_cut_two_beads_per_stone(self):
        places = self._make_two_stones()
        beads = compute_bead_positions(places, 1.5, 0.15, "u_cut")
        assert len(beads) == 4

    def test_channel_one_bead_per_stone(self):
        places = self._make_two_stones()
        beads = compute_bead_positions(places, 1.5, 0.15, "channel")
        assert len(beads) == 2


# ---------------------------------------------------------------------------
# 18-21. Seat cutters
# ---------------------------------------------------------------------------

class TestSeatCutters:
    def test_one_seat_per_stone(self):
        node = build_pave_wizard_node(
            "wiz-1", 10.0, 8.0, 1.5, 0.15, 0.3, layout="grid"
        )
        assert len(node["seat_cutters"]) == node["stats"]["stone_count"]

    def test_seat_depth_correct(self):
        node = build_pave_wizard_node("wiz-1", 10.0, 8.0, 1.5, 0.15, 0.3, layout="grid")
        expected_depth = 1.5 * _SEAT_DEPTH_FACTOR
        for cutter in node["seat_cutters"]:
            assert math.isclose(cutter["depth"], expected_depth, rel_tol=1e-4)

    def test_seat_radius_top_correct(self):
        node = build_pave_wizard_node("wiz-1", 10.0, 8.0, 1.5, 0.15, 0.3, layout="grid")
        for cutter in node["seat_cutters"]:
            assert math.isclose(cutter["radius_top"], 0.75, rel_tol=1e-4)

    def test_seat_normal_stored(self):
        node = build_pave_wizard_node("wiz-1", 10.0, 8.0, 1.5, 0.15, 0.3)
        # On a flat surface (no samples), all normals should be [0,0,1].
        for cutter in node["seat_cutters"]:
            assert cutter["normal"] == [0.0, 0.0, 1.0]


# ---------------------------------------------------------------------------
# 22-24. Coverage
# ---------------------------------------------------------------------------

class TestCoverage:
    def test_coverage_in_valid_range(self):
        node = build_pave_wizard_node("wiz-1", 10.0, 8.0, 1.5, 0.15, 0.3)
        assert 0 < node["stats"]["coverage_pct"] <= 100

    def test_coverage_increases_smaller_spacing(self):
        n1 = build_pave_wizard_node("w1", 10.0, 8.0, 1.5, 0.4, 0.3)
        n2 = build_pave_wizard_node("w2", 10.0, 8.0, 1.5, 0.15, 0.3)
        assert n2["stats"]["coverage_pct"] >= n1["stats"]["coverage_pct"]

    def test_hex_coverage_at_least_as_grid(self):
        h = build_pave_wizard_node("wh", 10.0, 8.0, 1.5, 0.15, 0.3, layout="hex")
        g = build_pave_wizard_node("wg", 10.0, 8.0, 1.5, 0.15, 0.3, layout="grid")
        # Hex packing should achieve at least the coverage of grid.
        assert h["stats"]["coverage_pct"] >= g["stats"]["coverage_pct"] - 1.0


# ---------------------------------------------------------------------------
# 25. Stats: carat + metal removed
# ---------------------------------------------------------------------------

class TestStats:
    def test_total_carat_matches_per_stone(self):
        sd = 1.5
        node = build_pave_wizard_node("wiz-1", 10.0, 8.0, sd, 0.15, 0.3, layout="grid")
        n = node["stats"]["stone_count"]
        expected = round(n * carat_from_mm("round_brilliant", sd), 4)
        assert math.isclose(node["stats"]["total_carat"], expected, rel_tol=1e-3)

    def test_metal_removed_positive(self):
        node = build_pave_wizard_node("wiz-1", 10.0, 8.0, 1.5, 0.15, 0.3)
        assert node["stats"]["metal_removed_mm3"] > 0

    def test_stats_zero_when_empty(self):
        stats = compute_stats([], 1.5, 10.0, 8.0)
        assert stats["stone_count"] == 0
        assert stats["total_carat"] == 0.0
        assert stats["metal_removed_mm3"] == 0.0
        assert stats["coverage_pct"] == 0.0


# ---------------------------------------------------------------------------
# 26-27. ToolSpec schema
# ---------------------------------------------------------------------------

class TestToolSpecs:
    def test_wizard_name(self):
        assert _pave_wizard_spec.name == "jewelry_pave_wizard"

    def test_wizard_required_fields(self):
        req = _pave_wizard_spec.input_schema["required"]
        for f in ["file_id", "region_width", "region_height", "stone_diameter",
                  "stone_spacing", "edge_margin"]:
            assert f in req

    def test_wizard_layout_enum(self):
        props = _pave_wizard_spec.input_schema["properties"]
        enum = set(props["layout"].get("enum", []))
        assert enum == _VALID_LAYOUTS

    def test_wizard_bead_style_enum(self):
        props = _pave_wizard_spec.input_schema["properties"]
        enum = set(props["bead_style"].get("enum", []))
        assert enum == _VALID_BEAD_STYLES

    def test_wizard_optional_not_required(self):
        req = _pave_wizard_spec.input_schema["required"]
        for f in ["layout", "bead_style", "cut", "samples", "id"]:
            assert f not in req

    def test_stats_spec_name(self):
        assert _pave_wizard_stats_spec.name == "jewelry_pave_wizard_stats"

    def test_update_spec_name(self):
        assert _pave_wizard_update_spec.name == "jewelry_pave_wizard_update"


# ---------------------------------------------------------------------------
# 28-35. LLM tool runners
# ---------------------------------------------------------------------------

class TestRunPaveWizard:
    def test_success_ok_payload(self):
        ctx, store, fid = make_ctx()
        result = call_tool(run_pave_wizard, ctx, fid,
                           region_width=10.0, region_height=8.0,
                           stone_diameter=1.5, stone_spacing=0.15,
                           edge_margin=0.3)
        assert "error" not in result
        assert result["op"] == "jewelry_pave_wizard"
        assert "stone_count" in result
        assert "total_carat" in result
        assert "coverage_pct" in result
        assert "bead_count" in result

    def test_stone_count_in_payload_matches_placements(self):
        ctx, store, fid = make_ctx()
        result = call_tool(run_pave_wizard, ctx, fid,
                           region_width=10.0, region_height=8.0,
                           stone_diameter=1.5, stone_spacing=0.15,
                           edge_margin=0.3, layout="grid")
        doc = json.loads(store["content"])
        node = doc["features"][-1]
        assert len(node["placements"]) == result["stone_count"]

    def test_bad_args_missing_file_id(self):
        ctx, store, fid = make_ctx()
        raw = run_sync(run_pave_wizard(ctx, json.dumps({
            "region_width": 10.0, "region_height": 8.0,
            "stone_diameter": 1.5, "stone_spacing": 0.15, "edge_margin": 0.3,
        }).encode()))
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_bad_args_non_positive_stone_diameter(self):
        ctx, store, fid = make_ctx()
        result = call_tool(run_pave_wizard, ctx, fid,
                           region_width=10.0, region_height=8.0,
                           stone_diameter=-1.5, stone_spacing=0.15,
                           edge_margin=0.3)
        assert result.get("code") == "BAD_ARGS"

    def test_bad_args_invalid_layout(self):
        ctx, store, fid = make_ctx()
        result = call_tool(run_pave_wizard, ctx, fid,
                           region_width=10.0, region_height=8.0,
                           stone_diameter=1.5, stone_spacing=0.15,
                           edge_margin=0.3, layout="diagonal")
        assert result.get("code") == "BAD_ARGS"

    def test_bad_args_invalid_bead_style(self):
        ctx, store, fid = make_ctx()
        result = call_tool(run_pave_wizard, ctx, fid,
                           region_width=10.0, region_height=8.0,
                           stone_diameter=1.5, stone_spacing=0.15,
                           edge_margin=0.3, bead_style="prong_ring")
        assert result.get("code") == "BAD_ARGS"

    def test_not_found_missing_file(self):
        ctx, store, fid = make_ctx(kind="NOT_FOUND")
        result = call_tool(run_pave_wizard, ctx, fid,
                           region_width=10.0, region_height=8.0,
                           stone_diameter=1.5, stone_spacing=0.15,
                           edge_margin=0.3)
        assert result.get("code") == "NOT_FOUND"

    def test_node_appended_to_feature_doc(self):
        ctx, store, fid = make_ctx()
        call_tool(run_pave_wizard, ctx, fid,
                  region_width=10.0, region_height=8.0,
                  stone_diameter=1.5, stone_spacing=0.15, edge_margin=0.3)
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1
        assert doc["features"][0]["op"] == "jewelry_pave_wizard"


# ---------------------------------------------------------------------------
# 36-37. Stats & update tools
# ---------------------------------------------------------------------------

class TestStatsAndUpdateTools:
    def test_stats_tool_returns_stone_count(self):
        ctx, store, fid = make_ctx()
        r = call_tool(run_pave_wizard, ctx, fid,
                      region_width=10.0, region_height=8.0,
                      stone_diameter=1.5, stone_spacing=0.15,
                      edge_margin=0.3, layout="grid")
        node_id = r["id"]
        sr = call_tool(run_pave_wizard_stats, ctx, fid, node_id=node_id)
        assert "error" not in sr
        assert sr["stone_count"] == r["stone_count"]

    def test_update_tool_changes_stone_count(self):
        ctx, store, fid = make_ctx()
        r1 = call_tool(run_pave_wizard, ctx, fid,
                       region_width=10.0, region_height=8.0,
                       stone_diameter=1.5, stone_spacing=0.15,
                       edge_margin=0.3, layout="grid")
        node_id = r1["id"]
        # Increase spacing — stone_count should decrease or stay same.
        r2 = call_tool(run_pave_wizard_update, ctx, fid,
                       node_id=node_id, stone_spacing=0.5)
        assert "error" not in r2
        assert r2["stone_count"] <= r1["stone_count"]

    def test_update_not_found_node_id(self):
        ctx, store, fid = make_ctx()
        r = call_tool(run_pave_wizard_update, ctx, fid,
                      node_id="nonexistent-node-id", stone_spacing=0.2)
        assert r.get("code") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 39. Surface samples: interpolated z / normal
# ---------------------------------------------------------------------------

class TestSurfaceSamples:
    def test_samples_affect_z(self):
        """Placements on a curved surface should reflect interpolated z values."""
        # Build a sample grid on a dome: z = height * (1 - (u-0.5)^2 - (v-0.5)^2)
        samples = []
        for ui in [0.0, 0.25, 0.5, 0.75, 1.0]:
            for vi in [0.0, 0.25, 0.5, 0.75, 1.0]:
                z = 3.0 * (1 - (ui - 0.5) ** 2 - (vi - 0.5) ** 2)
                # Approximate normal (unnormalised; will be normalised in helper).
                nz = 1.0
                samples.append({
                    "u": ui, "v": vi,
                    "x": ui * 10.0, "y": vi * 8.0, "z": z,
                    "nx": 0.0, "ny": 0.0, "nz": nz,
                })

        places = compute_pave_placements(
            10.0, 8.0, 1.5, 0.15, 0.3, layout="grid", samples=samples
        )
        # At least some placements should have z > 0 (on the dome).
        zs = [p["z"] for p in places]
        assert max(zs) > 0.0

    def test_flat_surface_all_z_zero(self):
        """No samples → flat plane; all z values are zero."""
        places = compute_pave_placements(10.0, 8.0, 1.5, 0.15, 0.3, layout="grid")
        for p in places:
            assert p["z"] == 0.0


# ---------------------------------------------------------------------------
# 40. shared_bead never exceeds stone_count
# ---------------------------------------------------------------------------

class TestBeadCountSanity:
    def test_shared_bead_never_exceeds_stone_count(self):
        rw, rh, sd, ss, em = 15.0, 12.0, 1.5, 0.15, 0.3
        places = compute_pave_placements(rw, rh, sd, ss, em, layout="hex")
        beads = compute_bead_positions(places, sd, ss, "shared_bead")
        assert len(beads) <= len(places)
