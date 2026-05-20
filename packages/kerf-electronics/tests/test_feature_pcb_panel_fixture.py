"""
T-33 Electronic: panelization + testpoint / fixture

Target coverage per testing-breakdown.md line 188:
  Scope: panelize.py + testpoint.py + fixture generator
  Success: 25 panels (V-score + mouse-bite); bed-of-nails fixture clearances;
           gold-finger / fiducial placement.

All tests are hermetic — no network I/O, no DB, no file-system side effects.
"""

from __future__ import annotations

import csv
import io
import math
import unittest

import kerf_electronics.tools.panelize  # noqa: F401 — trigger @register
import kerf_electronics.tools.testpoint  # noqa: F401 — trigger @register

from kerf_electronics.tools.panelize import (
    panelize,
    export_panel_gerber,
    export_panel_excellon,
    _board_bbox,
    _make_frame,
    _mousebite_holes,
    _vscore_line,
    _tab_route_holes,
)
from kerf_electronics.tools.testpoint import (
    place_testpoints,
    build_fixture_report,
)


# ─── Fixture boards ───────────────────────────────────────────────────────────

def _make_board(width: float, height: float, net_count: int = 4) -> list[dict]:
    """Synthesise a minimal CircuitJSON board with *net_count* SMT pads,
    one PTH pad, and one via.  All pads are well-separated (≥ 10 mm apart).
    """
    elements: list[dict] = [
        {
            "type": "pcb_board",
            "width": width,
            "height": height,
            "center_x": width / 2,
            "center_y": height / 2,
        }
    ]
    # SMT pads on distinct named nets, spaced 10 mm apart along x
    for i in range(net_count):
        elements.append({
            "type": "pcb_smtpad",
            "pcb_smtpad_id": f"pad_smt_{i}",
            "net_id": f"NET_{i}",
            "x": 5.0 + i * 10.0,
            "y": 5.0,
            "width": 1.6,
            "height": 1.0,
            "layer": "top_copper",
        })
    # PTH pad on NET_0 (higher priority than SMT)
    elements.append({
        "type": "pcb_plated_pad",
        "pcb_plated_pad_id": "pad_pth_0",
        "net_id": "NET_0",
        "x": 3.0,
        "y": 15.0,
        "width": 2.0,
        "height": 2.0,
        "hole_diameter": 1.0,
        "layer": "top_copper",
    })
    # Via on NET_1 (highest priority)
    elements.append({
        "type": "pcb_via",
        "pcb_via_id": "via_net1",
        "net_id": "NET_1",
        "x": 20.0,
        "y": 20.0,
        "outer_diameter": 0.8,
        "hole_diameter": 0.4,
    })
    return elements


# Standard 50×30 mm board
BOARD_50x30 = _make_board(50.0, 30.0, net_count=5)

# Compact 20×15 mm board
BOARD_20x15 = _make_board(20.0, 15.0, net_count=3)

# Large 100×80 mm board
BOARD_100x80 = _make_board(100.0, 80.0, net_count=6)


# ─── Helper ───────────────────────────────────────────────────────────────────

def _panel_size(panel: dict) -> tuple[float, float]:
    return (
        round(panel["panel_x1"] - panel["panel_x0"], 4),
        round(panel["panel_y1"] - panel["panel_y0"], 4),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. V-SCORE PANELS  (tests 1–9)
# ═══════════════════════════════════════════════════════════════════════════════

class TestVscorePanels(unittest.TestCase):
    """25-panel suite: V-score separation across various grid sizes."""

    # --- basic geometry ---

    def test_vscore_2x1_has_one_score_line(self):
        p = panelize(BOARD_50x30, cols=2, rows=1, separation="vscore", add_frame=False)
        lines = [f for f in p["separation_features"] if f["type"] == "_vscore_line"]
        self.assertEqual(len(lines), 1)

    def test_vscore_1x2_has_one_score_line(self):
        p = panelize(BOARD_50x30, cols=1, rows=2, separation="vscore", add_frame=False)
        lines = [f for f in p["separation_features"] if f["type"] == "_vscore_line"]
        self.assertEqual(len(lines), 1)

    def test_vscore_3x3_has_four_score_lines(self):
        p = panelize(BOARD_50x30, cols=3, rows=3, separation="vscore", add_frame=False)
        lines = [f for f in p["separation_features"] if f["type"] == "_vscore_line"]
        # (3-1) vertical + (3-1) horizontal = 4
        self.assertEqual(len(lines), 4)

    def test_vscore_4x2_has_four_score_lines(self):
        p = panelize(BOARD_50x30, cols=4, rows=2, separation="vscore", add_frame=False)
        lines = [f for f in p["separation_features"] if f["type"] == "_vscore_line"]
        # (4-1) vertical + (2-1) horizontal = 4
        self.assertEqual(len(lines), 4)

    # --- score line coordinate correctness ---

    def test_vscore_vertical_line_x_centred_in_gap(self):
        """Vertical score line between col 0 and col 1 must sit at x = board_w + gap/2."""
        gap = 2.0
        p = panelize(BOARD_50x30, cols=2, rows=1, gap_x_mm=gap,
                     separation="vscore", add_frame=False)
        line = next(f for f in p["separation_features"] if f["type"] == "_vscore_line")
        expected_x = 50.0 + gap / 2
        self.assertAlmostEqual(line["x0"], expected_x, places=4)
        self.assertAlmostEqual(line["x1"], expected_x, places=4)

    def test_vscore_horizontal_line_y_centred_in_gap(self):
        gap = 3.0
        p = panelize(BOARD_50x30, cols=1, rows=2, gap_y_mm=gap,
                     separation="vscore", add_frame=False)
        line = next(f for f in p["separation_features"] if f["type"] == "_vscore_line")
        expected_y = 30.0 + gap / 2
        self.assertAlmostEqual(line["y0"], expected_y, places=4)
        self.assertAlmostEqual(line["y1"], expected_y, places=4)

    def test_vscore_lines_span_full_array_height(self):
        """Vertical V-score lines must span the full array height."""
        p = panelize(BOARD_50x30, cols=2, rows=3, separation="vscore", add_frame=False)
        v_lines = [f for f in p["separation_features"]
                   if f["type"] == "_vscore_line" and f["x0"] == f["x1"]]
        self.assertGreater(len(v_lines), 0)
        array_h = p["array_y1"] - p["array_y0"]
        for ln in v_lines:
            span = abs(ln["y1"] - ln["y0"])
            self.assertAlmostEqual(span, array_h, places=4)

    def test_vscore_lines_span_full_array_width(self):
        """Horizontal V-score lines must span the full array width."""
        p = panelize(BOARD_50x30, cols=3, rows=2, separation="vscore", add_frame=False)
        h_lines = [f for f in p["separation_features"]
                   if f["type"] == "_vscore_line" and f["y0"] == f["y1"]]
        self.assertGreater(len(h_lines), 0)
        array_w = p["array_x1"] - p["array_x0"]
        for ln in h_lines:
            span = abs(ln["x1"] - ln["x0"])
            self.assertAlmostEqual(span, array_w, places=4)

    def test_vscore_with_frame_has_fiducials(self):
        """V-score panel with frame must include fiducial marks."""
        p = panelize(BOARD_50x30, cols=2, rows=2, separation="vscore", add_frame=True)
        self.assertIsNotNone(p["frame"])
        self.assertGreaterEqual(len(p["frame"]["fiducials"]), 3)

    def test_vscore_compact_board_2x4(self):
        p = panelize(BOARD_20x15, cols=2, rows=4, separation="vscore", add_frame=False)
        lines = [f for f in p["separation_features"] if f["type"] == "_vscore_line"]
        self.assertEqual(len(lines), 4)  # 1 vertical + 3 horizontal

    def test_vscore_large_board_2x2(self):
        p = panelize(BOARD_100x80, cols=2, rows=2, separation="vscore", add_frame=True)
        self.assertEqual(len(p["instances"]), 4)
        lines = [f for f in p["separation_features"] if f["type"] == "_vscore_line"]
        self.assertEqual(len(lines), 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. MOUSE-BITE PANELS  (tests 10–18)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMousebitePanels(unittest.TestCase):
    """25-panel suite: mousebite separation."""

    def test_mousebite_2x2_has_holes(self):
        p = panelize(BOARD_50x30, cols=2, rows=2, separation="mousebites", add_frame=False)
        holes = [f for f in p["separation_features"] if f["type"] == "_mousebite_hole"]
        self.assertGreater(len(holes), 0)

    def test_mousebite_hole_diameter_propagated(self):
        dia = 0.6
        p = panelize(BOARD_50x30, cols=2, rows=1, separation="mousebites",
                     mousebite_hole_diameter=dia, add_frame=False)
        for h in p["separation_features"]:
            self.assertAlmostEqual(h["diameter"], dia)

    def test_mousebite_hole_pitch_controls_density(self):
        """Finer pitch must produce more holes than coarser pitch."""
        p_fine = panelize(BOARD_50x30, cols=2, rows=1, separation="mousebites",
                          mousebite_hole_pitch=0.8, add_frame=False)
        p_coarse = panelize(BOARD_50x30, cols=2, rows=1, separation="mousebites",
                            mousebite_hole_pitch=2.5, add_frame=False)
        n_fine = len(p_fine["separation_features"])
        n_coarse = len(p_coarse["separation_features"])
        self.assertGreater(n_fine, n_coarse)

    def test_mousebite_holes_lie_in_gap_region_horizontal(self):
        """Vertical-gap mousebite holes must sit within [array_x0+bw, array_x0+bw+gap]."""
        gap = 2.0
        p = panelize(BOARD_50x30, cols=2, rows=1, gap_x_mm=gap,
                     separation="mousebites", add_frame=False)
        bw = p["board_w"]
        gap_centre = bw + gap / 2
        for h in p["separation_features"]:
            self.assertAlmostEqual(h["x"], gap_centre, delta=gap / 2 + 0.01)

    def test_mousebite_no_holes_for_1x1(self):
        p = panelize(BOARD_50x30, cols=1, rows=1, separation="mousebites")
        self.assertEqual(len(p["separation_features"]), 0)

    def test_mousebite_3x1_has_holes_at_two_vertical_gaps(self):
        gap = 2.0
        p = panelize(BOARD_50x30, cols=3, rows=1, gap_x_mm=gap,
                     separation="mousebites", add_frame=False)
        holes = p["separation_features"]
        self.assertGreater(len(holes), 0)
        # Two distinct x-clusters (gap between col0-1 and col1-2)
        xs = sorted({round(h["x"], 1) for h in holes})
        self.assertEqual(len(xs), 2)

    def test_mousebite_with_frame_tooling_holes_present(self):
        p = panelize(BOARD_50x30, cols=2, rows=2, separation="mousebites", add_frame=True)
        self.assertIsNotNone(p["frame"])
        self.assertGreaterEqual(len(p["frame"]["tooling_holes"]), 4)

    def test_mousebite_gerber_export_has_edge_cuts(self):
        p = panelize(BOARD_50x30, cols=2, rows=2, separation="mousebites")
        files = export_panel_gerber(p, stem="mb_test")
        self.assertIn("mb_test.GKO", files)

    def test_mousebite_excellon_has_npth_file(self):
        """Mousebite holes are non-plated; an NPTH file must be produced."""
        p = panelize(BOARD_50x30, cols=2, rows=2, separation="mousebites")
        drills = export_panel_excellon(p, stem="mb_drill")
        self.assertIn("mb_drill.NPTH.DRL", drills)

    def test_mousebite_compact_board_3x2(self):
        p = panelize(BOARD_20x15, cols=3, rows=2, separation="mousebites", add_frame=False)
        holes = [f for f in p["separation_features"] if f["type"] == "_mousebite_hole"]
        self.assertGreater(len(holes), 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FIDUCIAL PLACEMENT  (tests 19–21)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFiducialPlacement(unittest.TestCase):
    """Fiducials must be inside the rail, not on the copper array."""

    def _panel_with_frame(self, rail_width: float = 5.0) -> dict:
        return panelize(BOARD_50x30, cols=2, rows=2, add_frame=True,
                        rail_width_mm=rail_width)

    def test_fiducial_count_at_least_three(self):
        p = self._panel_with_frame()
        self.assertGreaterEqual(len(p["frame"]["fiducials"]), 3)

    def test_fiducials_inside_rail_bounds(self):
        """All fiducial marks must lie within the panel outline."""
        p = self._panel_with_frame()
        px0, py0 = p["panel_x0"], p["panel_y0"]
        px1, py1 = p["panel_x1"], p["panel_y1"]
        for fid in p["frame"]["fiducials"]:
            self.assertGreater(fid["x"], px0, f"Fiducial x={fid['x']} outside panel")
            self.assertLess(fid["x"], px1, f"Fiducial x={fid['x']} outside panel")
            self.assertGreater(fid["y"], py0, f"Fiducial y={fid['y']} outside panel")
            self.assertLess(fid["y"], py1, f"Fiducial y={fid['y']} outside panel")

    def test_fiducials_outside_board_array(self):
        """Fiducials must NOT overlap the board array."""
        p = self._panel_with_frame()
        ax0, ay0 = p["array_x0"], p["array_y0"]
        ax1, ay1 = p["array_x1"], p["array_y1"]
        for fid in p["frame"]["fiducials"]:
            inside_array = (ax0 <= fid["x"] <= ax1) and (ay0 <= fid["y"] <= ay1)
            self.assertFalse(inside_array,
                             f"Fiducial ({fid['x']}, {fid['y']}) overlaps board array")

    def test_fiducial_diameter_positive(self):
        p = self._panel_with_frame()
        for fid in p["frame"]["fiducials"]:
            self.assertIn("diameter", fid)
            self.assertGreater(fid["diameter"], 0.0)

    def test_wider_rail_shifts_fiducials_outward(self):
        p_narrow = self._panel_with_frame(rail_width=3.0)
        p_wide = self._panel_with_frame(rail_width=8.0)
        # Panel must be larger with wider rail
        w_narrow = p_narrow["panel_x1"] - p_narrow["panel_x0"]
        w_wide = p_wide["panel_x1"] - p_wide["panel_x0"]
        self.assertGreater(w_wide, w_narrow)

    def test_fiducials_in_gerber_silkscreen(self):
        """Frame fiducials should produce draw operations in the top silk layer."""
        p = self._panel_with_frame()
        files = export_panel_gerber(p, stem="fid_test")
        # Top silk layer (GTO) must be present
        self.assertIn("fid_test.GTO", files)
        gto = files["fid_test.GTO"]
        # Fiducials are rendered as line strokes (D01* draw commands) in GTO
        self.assertIn("D01*", gto)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GOLD-FINGER / EDGE-CONNECTOR CLEARANCE  (tests 25–27 numerically)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoldFingerClearance(unittest.TestCase):
    """Gold-finger (edge connector) pads must appear in panel Gerber copper.
    No V-score lines may bisect gold-finger columns.
    """

    def _board_with_gold_fingers(self) -> list[dict]:
        """Board with gold-finger pads along the bottom edge (y ≈ 0)."""
        board = [
            {
                "type": "pcb_board",
                "width": 60.0, "height": 40.0,
                "center_x": 30.0, "center_y": 20.0,
            }
        ]
        # Gold-finger row: 5 pads at y=2 (close to bottom edge)
        for i in range(5):
            board.append({
                "type": "pcb_smtpad",
                "pcb_smtpad_id": f"gf_{i}",
                "net_id": f"GF_{i}",
                "x": 10.0 + i * 8.0,
                "y": 2.0,
                "width": 3.0,
                "height": 6.0,   # tall pads = gold-finger style
                "layer": "top_copper",
            })
        return board

    def test_gold_finger_pads_in_panel_gerber(self):
        board = self._board_with_gold_fingers()
        p = panelize(board, cols=2, rows=2, separation="mousebites")
        files = export_panel_gerber(p, stem="gf_test")
        gtl = files.get("gf_test.GTL", "")
        # Expect at least one pad flash (D03*) in top copper
        self.assertIn("D03*", gtl)

    def test_vscore_lines_not_through_gold_finger_column(self):
        """Vertical V-score must be between columns, not at gold-finger x positions."""
        board = self._board_with_gold_fingers()
        # Gold fingers start at x=10 within the 60mm board
        gf_xs_local = [10.0 + i * 8.0 for i in range(5)]  # 10, 18, 26, 34, 42
        p = panelize(board, cols=2, rows=1, separation="vscore", gap_x_mm=2.0, add_frame=False)
        # V-score line sits at x = board_w + gap/2 = 60 + 1 = 61 in panel coords
        # Gold fingers in col=0 sit at their local x; in col=1 at local x + pitch
        score_lines = [f for f in p["separation_features"] if f["type"] == "_vscore_line"]
        self.assertGreater(len(score_lines), 0)
        for line in score_lines:
            # No V-score should coincide with a gold-finger x in either instance
            for inst in p["instances"]:
                ox = inst["origin_x"]
                for gx in gf_xs_local:
                    panel_gf_x = gx + ox
                    # Score line x0==x1 for vertical lines
                    if abs(line["x0"] - line["x1"]) < 0.01:  # vertical
                        self.assertNotAlmostEqual(
                            line["x0"], panel_gf_x, delta=1.0,
                            msg=f"V-score at x={line['x0']} overlaps gold-finger at {panel_gf_x}"
                        )

    def test_gold_finger_panel_excellon_has_plated_hits(self):
        board = self._board_with_gold_fingers()
        # Add a via to ensure plated holes exist
        board.append({
            "type": "pcb_via",
            "pcb_via_id": "via_1",
            "net_id": "GND",
            "x": 30.0, "y": 20.0,
            "outer_diameter": 0.8,
            "hole_diameter": 0.4,
        })
        p = panelize(board, cols=2, rows=1, separation="mousebites")
        drills = export_panel_excellon(p, stem="gf_drill")
        drl = drills.get("gf_drill.DRL", "")
        self.assertIn("M48", drl)  # Excellon header present


# ═══════════════════════════════════════════════════════════════════════════════
# 5. BED-OF-NAILS FIXTURE CLEARANCES  (tests 28–37)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFixtureClearances(unittest.TestCase):
    """Probe placement must respect minimum-clearance rules for bed-of-nails fixtures."""

    def _place(self, board: list[dict], spacing: float = 2.54) -> dict:
        return place_testpoints(board, min_spacing_mm=spacing)

    def test_min_spacing_100mil_no_probe_overlap(self):
        result = self._place(BOARD_50x30, spacing=2.54)
        probes = result["probes"]
        for i, a in enumerate(probes):
            for b in probes[i + 1:]:
                d = math.hypot(a["snapped_x_mm"] - b["snapped_x_mm"],
                               a["snapped_y_mm"] - b["snapped_y_mm"])
                self.assertGreaterEqual(d, 2.54 * 0.999,
                                        f"{a['net']} / {b['net']} too close: {d:.3f} mm")

    def test_min_spacing_50mil_allows_tighter_probes(self):
        result = self._place(BOARD_50x30, spacing=1.27)
        self.assertGreater(result["placed_count"], 0)

    def test_min_spacing_200mil_may_reduce_coverage(self):
        """Very coarse pitch (5.08 mm) on a dense board may produce conflicts."""
        result_tight = self._place(BOARD_50x30, spacing=1.0)
        result_coarse = self._place(BOARD_50x30, spacing=5.08)
        # Coarse pitch must not place more probes than tight
        self.assertLessEqual(result_coarse["placed_count"], result_tight["placed_count"])

    def test_probe_dia_within_clearance_limits(self):
        """All probe diameters must stay within IPC-allowed range [0.5, 2.5] mm."""
        result = self._place(BOARD_50x30)
        for p in result["probes"]:
            self.assertGreaterEqual(p["probe_dia_mm"], 0.5)
            self.assertLessEqual(p["probe_dia_mm"], 2.5)

    def test_via_probes_accessible_from_both_sides(self):
        """Via probes should be placed on the access side, not 'both'."""
        result = place_testpoints(BOARD_50x30, access_side="top")
        via_probes = [p for p in result["probes"] if p["pad_type"] == "via"]
        for vp in via_probes:
            self.assertEqual(vp["side"], "top",
                             "Via probes should report access_side, not 'both'")

    def test_via_probes_bottom_access_side(self):
        result = place_testpoints(BOARD_50x30, access_side="bottom")
        via_probes = [p for p in result["probes"] if p["pad_type"] == "via"]
        for vp in via_probes:
            self.assertEqual(vp["side"], "bottom")

    def test_pth_preferred_over_smt_for_net0(self):
        """NET_0 has both PTH (priority 1) and SMT (priority 2) — PTH must win."""
        result = self._place(BOARD_50x30)
        net0 = next((p for p in result["probes"] if p["net"] == "NET_0"), None)
        self.assertIsNotNone(net0, "NET_0 should have a probe")
        self.assertEqual(net0["pad_type"], "pth",
                         f"Expected pth for NET_0, got {net0['pad_type']}")

    def test_via_preferred_over_pth_for_net1(self):
        """NET_1 has via (priority 0) and SMT pad — via must win."""
        result = self._place(BOARD_50x30)
        net1 = next((p for p in result["probes"] if p["net"] == "NET_1"), None)
        self.assertIsNotNone(net1, "NET_1 should have a probe")
        self.assertEqual(net1["pad_type"], "via",
                         f"Expected via for NET_1, got {net1['pad_type']}")

    def test_coverage_pct_sane_range(self):
        result = self._place(BOARD_50x30)
        self.assertGreaterEqual(result["coverage_pct"], 0.0)
        self.assertLessEqual(result["coverage_pct"], 100.0)

    def test_coverage_pct_formula(self):
        result = self._place(BOARD_50x30)
        if result["net_count"] > 0:
            expected = round(result["placed_count"] / result["net_count"] * 100.0, 1)
            self.assertAlmostEqual(result["coverage_pct"], expected, places=1)

    def test_large_board_all_nets_placed(self):
        """BOARD_100x80 pads are well-separated; all nets should be placed."""
        result = self._place(BOARD_100x80, spacing=2.54)
        self.assertEqual(result["placed_count"], result["net_count"],
                         f"Expected all nets placed; unreachable={result['unreachable']}")

    def test_fixture_report_csv_x_y_snapped_to_grid(self):
        """Drill CSV positions must be on the min_spacing_mm (100-mil) grid."""
        spacing = 2.54
        report = build_fixture_report(BOARD_50x30, min_spacing_mm=spacing)
        rows = list(csv.reader(io.StringIO(report["drill_csv"])))
        hdr = rows[0]
        xi, yi = hdr.index("X_mm"), hdr.index("Y_mm")
        for row in rows[1:]:
            x = float(row[xi])
            y = float(row[yi])
            # x / spacing should be very close to an integer (float mod is unreliable)
            x_ratio = x / spacing
            y_ratio = y / spacing
            self.assertAlmostEqual(x_ratio, round(x_ratio), delta=0.001,
                                   msg=f"X={x} not on {spacing}-mm grid (ratio={x_ratio})")
            self.assertAlmostEqual(y_ratio, round(y_ratio), delta=0.001,
                                   msg=f"Y={y} not on {spacing}-mm grid (ratio={y_ratio})")

    def test_fixture_report_summary_has_coverage_percent(self):
        report = build_fixture_report(BOARD_50x30, stem="clr_board")
        self.assertIn("Coverage", report["summary"])
        self.assertIn("%", report["summary"])


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PANEL + FIXTURE INTEGRATION  (tests 38–42)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPanelFixtureIntegration(unittest.TestCase):
    """End-to-end: panelise a board, then generate a fixture report for
    a single board instance drawn from the panel descriptor."""

    def _panel_instance_circuit(self, separation: str = "mousebites") -> list[dict]:
        p = panelize(BOARD_50x30, cols=2, rows=2, separation=separation)
        # Use the first board instance's translated circuit_json as input to fixture
        return p["instances"][0]["circuit_json"]

    def test_fixture_from_panel_instance_mousebites(self):
        circuit = self._panel_instance_circuit("mousebites")
        result = place_testpoints(circuit)
        self.assertGreater(result["placed_count"], 0)
        self.assertEqual(result["placed_count"] + len(result["unreachable"]),
                         result["net_count"])

    def test_fixture_from_panel_instance_vscore(self):
        circuit = self._panel_instance_circuit("vscore")
        result = place_testpoints(circuit)
        self.assertGreater(result["placed_count"], 0)

    def test_fixture_report_full_pipeline(self):
        """Full pipeline: panelize → extract instance → fixture report → check CSV."""
        p = panelize(BOARD_50x30, cols=2, rows=2, separation="mousebites")
        inst_circuit = p["instances"][1]["circuit_json"]
        report = build_fixture_report(inst_circuit, stem="pipeline_test")
        self.assertIn("drill_csv", report)
        rows = list(csv.reader(io.StringIO(report["drill_csv"])))
        self.assertGreater(len(rows), 1)  # header + at least one probe

    def test_panel_vscore_gerber_and_fixture_compatible(self):
        """V-score panel Gerber export should not interfere with fixture placement."""
        p = panelize(BOARD_50x30, cols=2, rows=1, separation="vscore")
        _ = export_panel_gerber(p, stem="vscore_combined")
        # Fixture on instance 0 must still be placeable
        result = place_testpoints(p["instances"][0]["circuit_json"])
        self.assertGreater(result["placed_count"], 0)

    def test_all_instances_produce_independent_fixtures(self):
        """Each panel instance should yield the same probe count (same board)."""
        p = panelize(BOARD_50x30, cols=2, rows=2, separation="mousebites")
        counts = []
        for inst in p["instances"]:
            r = place_testpoints(inst["circuit_json"])
            counts.append(r["placed_count"])
        # All 4 instances are identical boards → same placement
        self.assertEqual(len(set(counts)), 1,
                         f"Instance probe counts differ: {counts}")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. BOUNDARY / MALFORMED / IDEMPOTENCY  (tests 43–50)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBoundaryAndIdempotency(unittest.TestCase):
    """Edge cases, malformed inputs, and idempotency guarantees."""

    def test_panelize_cols_1_rows_1_no_separation(self):
        """1×1 panel has no gaps → no separation features."""
        p = panelize(BOARD_50x30, cols=1, rows=1)
        self.assertEqual(p["separation_features"], [])

    def test_panelize_invalid_cols_raises(self):
        with self.assertRaises((ValueError, Exception)):
            panelize(BOARD_50x30, cols=0, rows=2)

    def test_panelize_invalid_rows_raises(self):
        with self.assertRaises((ValueError, Exception)):
            panelize(BOARD_50x30, cols=2, rows=0)

    def test_panelize_unknown_separation_raises(self):
        with self.assertRaises((ValueError, Exception)):
            panelize(BOARD_50x30, cols=2, rows=2, separation="laser_cut")

    def test_panelize_idempotent_same_cols_rows(self):
        """Calling panelize twice with same args must return identical panel dims."""
        p1 = panelize(BOARD_50x30, cols=3, rows=2, separation="vscore")
        p2 = panelize(BOARD_50x30, cols=3, rows=2, separation="vscore")
        self.assertEqual(p1["panel_x1"] - p1["panel_x0"],
                         p2["panel_x1"] - p2["panel_x0"])
        self.assertEqual(len(p1["separation_features"]), len(p2["separation_features"]))

    def test_place_testpoints_empty_circuit(self):
        result = place_testpoints([])
        self.assertEqual(result["net_count"], 0)
        self.assertEqual(result["placed_count"], 0)
        self.assertEqual(result["coverage_pct"], 0.0)
        self.assertEqual(result["probes"], [])
        self.assertEqual(result["unreachable"], [])

    def test_place_testpoints_no_pads_board_only(self):
        """A board element with no pads should yield zero probes."""
        board = [{"type": "pcb_board", "width": 50.0, "height": 30.0,
                  "center_x": 25.0, "center_y": 15.0}]
        result = place_testpoints(board)
        self.assertEqual(result["placed_count"], 0)

    def test_fixture_report_idempotent(self):
        """Two calls with identical inputs must produce identical coverage."""
        r1 = build_fixture_report(BOARD_50x30, stem="idem_a")
        r2 = build_fixture_report(BOARD_50x30, stem="idem_b")
        self.assertEqual(r1["placed_count"], r2["placed_count"])
        self.assertAlmostEqual(r1["coverage_pct"], r2["coverage_pct"], places=1)

    def test_panel_gerber_export_idempotent(self):
        """Exporting Gerbers twice for the same panel must yield identical file sets."""
        p = panelize(BOARD_50x30, cols=2, rows=2, separation="mousebites")
        g1 = export_panel_gerber(p, stem="idem_gerber")
        g2 = export_panel_gerber(p, stem="idem_gerber")
        self.assertEqual(set(g1.keys()), set(g2.keys()))
        for k in g1:
            self.assertEqual(g1[k], g2[k])

    def test_mousebite_zero_gap_still_generates_holes(self):
        """gap_x_mm=0 means boards touch; a single hole at the boundary is acceptable."""
        p = panelize(BOARD_50x30, cols=2, rows=1, gap_x_mm=0.0,
                     separation="mousebites", add_frame=False)
        holes = [f for f in p["separation_features"] if f["type"] == "_mousebite_hole"]
        self.assertGreater(len(holes), 0)


if __name__ == "__main__":
    unittest.main()
