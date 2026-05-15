"""
Tests for kerf_electronics/tools/panelize.py — PCB panelisation.

Coverage:
  - core panelize() function (array geometry, separation, frame)
  - all three separation methods: mousebites, vscore, tab_route
  - alternating_rotate flag
  - export_panel_gerber / export_panel_excellon wrappers
  - LLM tools: panelize_board, panel_info
"""

import json
import math
import unittest
import io
import zipfile

# Trigger @register decorators
import kerf_electronics.tools.panelize  # noqa: F401

from kerf_electronics.tools.panelize import (
    panelize,
    export_panel_gerber,
    export_panel_excellon,
    _board_bbox,
    _mousebite_holes,
    _vscore_line,
    _tab_route_holes,
    _make_frame,
)


# ─── Fixture board ─────────────────────────────────────────────────────────────
# 50 × 30 mm board, centred at (25, 15)

FIXTURE_BOARD = [
    {
        "type": "pcb_board",
        "width": 50.0,
        "height": 30.0,
        "center_x": 25.0,
        "center_y": 15.0,
    },
    {
        "type": "pcb_smtpad",
        "pcb_smtpad_id": "pad_1",
        "x": 10.0,
        "y": 10.0,
        "width": 1.5,
        "height": 1.0,
        "shape": "rect",
        "layer": "top_copper",
    },
    {
        "type": "pcb_via",
        "pcb_via_id": "via_1",
        "x": 25.0,
        "y": 15.0,
        "outer_diameter": 0.6,
        "hole_diameter": 0.3,
    },
    {
        "type": "pcb_trace",
        "pcb_trace_id": "trace_1",
        "route": [
            {"x": 10.0, "y": 10.0, "width": 0.25, "layer": "top_copper"},
            {"x": 25.0, "y": 15.0, "width": 0.25, "layer": "top_copper"},
        ],
    },
]


# ─── board_bbox helper ────────────────────────────────────────────────────────

class TestBoardBbox(unittest.TestCase):

    def test_extracts_from_pcb_board(self):
        x0, y0, x1, y1 = _board_bbox(FIXTURE_BOARD)
        self.assertAlmostEqual(x0, 0.0)
        self.assertAlmostEqual(y0, 0.0)
        self.assertAlmostEqual(x1, 50.0)
        self.assertAlmostEqual(y1, 30.0)

    def test_fallback_from_element_coords(self):
        circuit = [
            {"type": "pcb_smtpad", "x": 5.0, "y": 3.0},
            {"type": "pcb_smtpad", "x": 15.0, "y": 12.0},
        ]
        x0, y0, x1, y1 = _board_bbox(circuit)
        self.assertAlmostEqual(x0, 5.0)
        self.assertAlmostEqual(y0, 3.0)
        self.assertAlmostEqual(x1, 15.0)
        self.assertAlmostEqual(y1, 12.0)


# ─── separation feature generators ───────────────────────────────────────────

class TestMousebiteHoles(unittest.TestCase):

    def test_returns_holes_list(self):
        holes = _mousebite_holes(0, 0, 0, 30.0, hole_diameter=0.8, hole_pitch=1.2)
        self.assertIsInstance(holes, list)
        self.assertGreater(len(holes), 0)

    def test_all_holes_have_correct_diameter(self):
        holes = _mousebite_holes(0, 0, 0, 30.0, hole_diameter=0.8, hole_pitch=1.2)
        for h in holes:
            self.assertEqual(h["type"], "_mousebite_hole")
            self.assertAlmostEqual(h["diameter"], 0.8)

    def test_holes_span_length(self):
        holes = _mousebite_holes(0, 0, 0, 30.0, hole_diameter=0.8, hole_pitch=1.2)
        ys = [h["y"] for h in holes]
        self.assertAlmostEqual(min(ys), 0.0, places=3)
        self.assertAlmostEqual(max(ys), 30.0, places=3)

    def test_horizontal_holes(self):
        holes = _mousebite_holes(0, 10, 50.0, 10, hole_diameter=0.8, hole_pitch=1.2)
        xs = [h["x"] for h in holes]
        self.assertAlmostEqual(min(xs), 0.0, places=3)
        self.assertAlmostEqual(max(xs), 50.0, places=3)
        for h in holes:
            self.assertAlmostEqual(h["y"], 10.0, places=3)

    def test_single_hole_for_short_segment(self):
        holes = _mousebite_holes(0, 0, 0, 0.5, hole_diameter=0.8, hole_pitch=1.2)
        self.assertEqual(len(holes), 1)


class TestVscoreLine(unittest.TestCase):

    def test_returns_dict_with_coordinates(self):
        line = _vscore_line(10.0, 0.0, 10.0, 30.0)
        self.assertEqual(line["type"], "_vscore_line")
        self.assertAlmostEqual(line["x0"], 10.0)
        self.assertAlmostEqual(line["y0"], 0.0)
        self.assertAlmostEqual(line["x1"], 10.0)
        self.assertAlmostEqual(line["y1"], 30.0)


class TestTabRouteHoles(unittest.TestCase):

    def test_returns_features(self):
        feats = _tab_route_holes(0, 0, 0, 30.0, tab_width_mm=3.0, tab_count=2, hole_diameter=0.8)
        self.assertIsInstance(feats, list)
        self.assertGreater(len(feats), 0)

    def test_tab_count_segments(self):
        feats = _tab_route_holes(0, 0, 0, 30.0, tab_width_mm=3.0, tab_count=2, hole_diameter=0.8)
        tab_segs = [f for f in feats if f["type"] == "_tab_segment"]
        self.assertEqual(len(tab_segs), 2)

    def test_breakaway_holes_per_tab(self):
        feats = _tab_route_holes(0, 0, 0, 30.0, tab_width_mm=3.0, tab_count=2, hole_diameter=0.8)
        holes = [f for f in feats if f["type"] == "_mousebite_hole"]
        # 2 holes per tab × 2 tabs = 4 holes
        self.assertEqual(len(holes), 4)

    def test_zero_tab_count_returns_empty(self):
        feats = _tab_route_holes(0, 0, 0, 30.0, tab_count=0)
        self.assertEqual(len(feats), 0)


class TestMakeFrame(unittest.TestCase):

    def test_returns_dict_with_required_keys(self):
        f = _make_frame(0, 0, 100, 60, rail_width=5.0)
        for k in ("outline", "panel_x0", "panel_y0", "panel_x1", "panel_y1",
                  "tooling_holes", "fiducials"):
            self.assertIn(k, f)

    def test_panel_larger_than_array(self):
        f = _make_frame(0, 0, 100, 60, rail_width=5.0)
        self.assertAlmostEqual(f["panel_x0"], -5.0)
        self.assertAlmostEqual(f["panel_y0"], -5.0)
        self.assertAlmostEqual(f["panel_x1"], 105.0)
        self.assertAlmostEqual(f["panel_y1"], 65.0)

    def test_tooling_holes_present(self):
        f = _make_frame(0, 0, 100, 60, rail_width=5.0)
        self.assertGreaterEqual(len(f["tooling_holes"]), 4)

    def test_fiducials_present(self):
        f = _make_frame(0, 0, 100, 60, rail_width=5.0)
        self.assertGreaterEqual(len(f["fiducials"]), 3)

    def test_outline_four_corners(self):
        f = _make_frame(0, 0, 100, 60, rail_width=5.0)
        self.assertEqual(len(f["outline"]), 4)


# ─── core panelize() ─────────────────────────────────────────────────────────

class TestPanelizeCore(unittest.TestCase):

    def setUp(self):
        self.panel = panelize(FIXTURE_BOARD, cols=2, rows=2, gap_x_mm=2.0, gap_y_mm=2.0)

    def test_returns_dict(self):
        self.assertIsInstance(self.panel, dict)

    def test_instance_count(self):
        self.assertEqual(len(self.panel["instances"]), 4)

    def test_instance_structure(self):
        for inst in self.panel["instances"]:
            for k in ("col", "row", "origin_x", "origin_y", "rotated180", "circuit_json"):
                self.assertIn(k, inst)

    def test_board_dimensions(self):
        self.assertAlmostEqual(self.panel["board_w"], 50.0)
        self.assertAlmostEqual(self.panel["board_h"], 30.0)

    def test_array_width(self):
        # 2 cols × 50mm + 1 gap × 2mm = 102mm
        expected_w = 2 * 50.0 + 1 * 2.0
        self.assertAlmostEqual(self.panel["array_x1"] - self.panel["array_x0"], expected_w)

    def test_array_height(self):
        expected_h = 2 * 30.0 + 1 * 2.0
        self.assertAlmostEqual(self.panel["array_y1"] - self.panel["array_y0"], expected_h)

    def test_panel_larger_than_array_when_frame(self):
        self.assertLess(self.panel["panel_x0"], self.panel["array_x0"])
        self.assertLess(self.panel["panel_y0"], self.panel["array_y0"])
        self.assertGreater(self.panel["panel_x1"], self.panel["array_x1"])
        self.assertGreater(self.panel["panel_y1"], self.panel["array_y1"])

    def test_panel_outline_present(self):
        self.assertIsInstance(self.panel["panel_outline"], list)
        self.assertGreaterEqual(len(self.panel["panel_outline"]), 4)

    def test_frame_present_by_default(self):
        self.assertIsNotNone(self.panel["frame"])

    def test_no_frame_when_disabled(self):
        p = panelize(FIXTURE_BOARD, cols=2, rows=2, add_frame=False)
        self.assertIsNone(p["frame"])
        # Panel outline equals array outline
        self.assertAlmostEqual(p["panel_x0"], p["array_x0"])

    def test_col_row_indices(self):
        positions = {(i["col"], i["row"]) for i in self.panel["instances"]}
        expected = {(0, 0), (1, 0), (0, 1), (1, 1)}
        self.assertEqual(positions, expected)

    def test_origin_coordinates(self):
        inst_00 = next(i for i in self.panel["instances"] if i["col"] == 0 and i["row"] == 0)
        inst_10 = next(i for i in self.panel["instances"] if i["col"] == 1 and i["row"] == 0)
        # col=1 should be offset by pitch_x = 50+2 = 52
        self.assertAlmostEqual(inst_10["origin_x"] - inst_00["origin_x"], 52.0)

    def test_instance_circuit_json_not_empty(self):
        for inst in self.panel["instances"]:
            self.assertGreater(len(inst["circuit_json"]), 0)

    def test_via_coordinates_translated(self):
        """Via in col=1 row=0 should be offset by pitch_x from col=0 row=0."""
        inst_00 = next(i for i in self.panel["instances"] if i["col"] == 0 and i["row"] == 0)
        inst_10 = next(i for i in self.panel["instances"] if i["col"] == 1 and i["row"] == 0)

        via_00 = next(e for e in inst_00["circuit_json"] if e.get("type") == "pcb_via")
        via_10 = next(e for e in inst_10["circuit_json"] if e.get("type") == "pcb_via")
        dx = via_10["x"] - via_00["x"]
        self.assertAlmostEqual(dx, 52.0)  # pitch_x = 50+2


class TestPanelize1x1(unittest.TestCase):

    def test_single_board_panel(self):
        p = panelize(FIXTURE_BOARD, cols=1, rows=1)
        self.assertEqual(len(p["instances"]), 1)
        # No separation features for 1×1
        self.assertEqual(len(p["separation_features"]), 0)


class TestPanelizeAlternatingRotate(unittest.TestCase):

    def test_alternating_rotate_flag_set(self):
        p = panelize(FIXTURE_BOARD, cols=2, rows=2, alternating_rotate=True)
        self.assertTrue(p["alternating_rotate"])

    def test_some_instances_rotated(self):
        p = panelize(FIXTURE_BOARD, cols=2, rows=2, alternating_rotate=True)
        rotated = [i for i in p["instances"] if i["rotated180"]]
        not_rotated = [i for i in p["instances"] if not i["rotated180"]]
        # chequerboard: 2 rotated, 2 not for 2×2
        self.assertEqual(len(rotated), 2)
        self.assertEqual(len(not_rotated), 2)

    def test_rotated_pad_position(self):
        """SMT pad (off-centre) in a rotated instance should be mirrored, not simply shifted."""
        p = panelize(FIXTURE_BOARD, cols=2, rows=1, alternating_rotate=True)
        inst_0 = next(i for i in p["instances"] if i["col"] == 0)  # not rotated
        inst_1 = next(i for i in p["instances"] if i["col"] == 1)  # rotated

        pad_0 = next(e for e in inst_0["circuit_json"] if e.get("type") == "pcb_smtpad")
        pad_1 = next(e for e in inst_1["circuit_json"] if e.get("type") == "pcb_smtpad")

        # In inst_0, pad is at x=10 within its slot (not at centre x=25).
        # After 180° rotation within inst_1's slot, the x should be mirrored:
        #   mirror_x = 2*slot_centre_x - original_local_x = 2*25 - 10 = 40, then + pitch_x offset
        # So it should NOT be naive_x = pad_0.x + pitch_x.
        pitch_x = 52.0
        naive_x = pad_0["x"] + pitch_x
        self.assertNotAlmostEqual(pad_1["x"], naive_x, places=2)


# ─── separation: mousebites ───────────────────────────────────────────────────

class TestMousebitesSeparation(unittest.TestCase):

    def setUp(self):
        self.panel = panelize(
            FIXTURE_BOARD, cols=2, rows=2,
            gap_x_mm=2.0, gap_y_mm=2.0,
            separation="mousebites",
            mousebite_hole_diameter=0.8,
            mousebite_hole_pitch=1.2,
            add_frame=False,
        )

    def test_separation_features_not_empty(self):
        self.assertGreater(len(self.panel["separation_features"]), 0)

    def test_all_features_are_mousebite_holes(self):
        for f in self.panel["separation_features"]:
            self.assertEqual(f["type"], "_mousebite_hole")

    def test_holes_have_correct_diameter(self):
        for f in self.panel["separation_features"]:
            self.assertAlmostEqual(f["diameter"], 0.8)

    def test_hole_positions_in_gap_region_vertical(self):
        """Vertical gap holes (between col 0 and col 1) should have x ≈ 51."""
        # gap centre for vertical gap: col0 width + gap/2 = 50 + 1 = 51
        v_holes = [f for f in self.panel["separation_features"] if abs(f["x"] - 51.0) < 0.5]
        self.assertGreater(len(v_holes), 0)

    def test_hole_positions_in_gap_region_horizontal(self):
        """Horizontal gap holes should have y ≈ 31."""
        h_holes = [f for f in self.panel["separation_features"] if abs(f["y"] - 31.0) < 0.5]
        self.assertGreater(len(h_holes), 0)


# ─── separation: vscore ───────────────────────────────────────────────────────

class TestVscoreSeparation(unittest.TestCase):

    def setUp(self):
        self.panel = panelize(
            FIXTURE_BOARD, cols=2, rows=2,
            gap_x_mm=2.0, gap_y_mm=2.0,
            separation="vscore",
            add_frame=False,
        )

    def test_separation_features_not_empty(self):
        self.assertGreater(len(self.panel["separation_features"]), 0)

    def test_all_features_are_vscore_lines(self):
        for f in self.panel["separation_features"]:
            self.assertEqual(f["type"], "_vscore_line")

    def test_vscore_line_count_2x2(self):
        # 2×2: 1 vertical gap + 1 horizontal gap = 2 vscore lines
        self.assertEqual(len(self.panel["separation_features"]), 2)

    def test_vscore_line_has_coordinates(self):
        for line in self.panel["separation_features"]:
            for k in ("x0", "y0", "x1", "y1"):
                self.assertIn(k, line)

    def test_vscore_3x1(self):
        p = panelize(FIXTURE_BOARD, cols=3, rows=1, separation="vscore", add_frame=False)
        # 2 vertical gaps, 0 horizontal = 2 vscore lines
        self.assertEqual(len(p["separation_features"]), 2)

    def test_vscore_1x3(self):
        p = panelize(FIXTURE_BOARD, cols=1, rows=3, separation="vscore", add_frame=False)
        # 0 vertical, 2 horizontal = 2 vscore lines
        self.assertEqual(len(p["separation_features"]), 2)


# ─── separation: tab_route ────────────────────────────────────────────────────

class TestTabRouteSeparation(unittest.TestCase):

    def setUp(self):
        self.panel = panelize(
            FIXTURE_BOARD, cols=2, rows=2,
            gap_x_mm=2.0, gap_y_mm=2.0,
            separation="tab_route",
            tab_width_mm=3.0,
            tab_count=2,
            tab_hole_diameter=0.8,
            add_frame=False,
        )

    def test_separation_features_not_empty(self):
        self.assertGreater(len(self.panel["separation_features"]), 0)

    def test_tab_segments_present(self):
        tabs = [f for f in self.panel["separation_features"] if f["type"] == "_tab_segment"]
        self.assertGreater(len(tabs), 0)

    def test_breakaway_holes_present(self):
        holes = [f for f in self.panel["separation_features"] if f["type"] == "_mousebite_hole"]
        self.assertGreater(len(holes), 0)

    def test_tab_count_per_gap(self):
        # 2 gaps × 2 tabs each = 4 tab segments
        tabs = [f for f in self.panel["separation_features"] if f["type"] == "_tab_segment"]
        self.assertEqual(len(tabs), 4)

    def test_breakaway_holes_count(self):
        # 2 holes per tab, 4 tabs = 8 holes
        holes = [f for f in self.panel["separation_features"] if f["type"] == "_mousebite_hole"]
        self.assertEqual(len(holes), 8)

    def test_tab_segment_has_coordinates(self):
        for tab in [f for f in self.panel["separation_features"] if f["type"] == "_tab_segment"]:
            for k in ("x0", "y0", "x1", "y1"):
                self.assertIn(k, tab)


# ─── export_panel_gerber ──────────────────────────────────────────────────────

class TestExportPanelGerber(unittest.TestCase):

    def setUp(self):
        self.panel = panelize(FIXTURE_BOARD, cols=2, rows=2, separation="mousebites")
        self.gerber = export_panel_gerber(self.panel, stem="panel_test")

    def test_returns_dict(self):
        self.assertIsInstance(self.gerber, dict)

    def test_edge_cuts_layer_present(self):
        self.assertIn("panel_test.GKO", self.gerber)

    def test_top_copper_layer_present(self):
        self.assertIn("panel_test.GTL", self.gerber)

    def test_gerber_header(self):
        for content in self.gerber.values():
            self.assertIn("%FSLAX46Y46*%", content)
            self.assertIn("%MOMM*%", content)
            self.assertIn("M02*", content)

    def test_gerber_has_draw_operations(self):
        """Traces from all instances should appear in top copper."""
        gtl = self.gerber["panel_test.GTL"]
        self.assertIn("D01*", gtl)

    def test_edge_cuts_outline_in_gko(self):
        gko = self.gerber["panel_test.GKO"]
        self.assertIn("D01*", gko)

    def test_vscore_lines_in_edge_cuts(self):
        panel = panelize(FIXTURE_BOARD, cols=2, rows=1, separation="vscore", add_frame=False)
        gerber = export_panel_gerber(panel, stem="vs_test")
        gko = gerber["vs_test.GKO"]
        # vscore lines are emitted as draw operations on edge_cuts
        self.assertIn("D01*", gko)

    def test_multiple_instances_pads_in_copper(self):
        """All 4 board instances should contribute pad flashes to top copper."""
        gtl = self.gerber["panel_test.GTL"]
        # D03* = flash; we expect multiple flashes (4 instances × at least 1 pad)
        flash_count = gtl.count("D03*")
        self.assertGreaterEqual(flash_count, 4)


# ─── export_panel_excellon ────────────────────────────────────────────────────

class TestExportPanelExcellon(unittest.TestCase):

    def setUp(self):
        self.panel = panelize(FIXTURE_BOARD, cols=2, rows=2, separation="mousebites")
        self.drill = export_panel_excellon(self.panel, stem="panel_test")

    def test_returns_dict(self):
        self.assertIsInstance(self.drill, dict)

    def test_plated_drill_file_present(self):
        self.assertIn("panel_test.DRL", self.drill)

    def test_excellon_header(self):
        drl = self.drill["panel_test.DRL"]
        self.assertIn("M48", drl)
        self.assertIn("METRIC,TZ", drl)
        self.assertIn("M30", drl)

    def test_mousebite_holes_in_drill(self):
        """Mousebite holes should appear in the non-plated drill file."""
        # NPTH file produced when non-plated holes exist
        npth_key = "panel_test.NPTH.DRL"
        self.assertIn(npth_key, self.drill)

    def test_tooling_holes_in_drill(self):
        """Frame tooling holes (non-plated) should be in NPTH file."""
        npth = self.drill.get("panel_test.NPTH.DRL", "")
        self.assertIn("M48", npth)

    def test_all_instance_vias_captured(self):
        """4 instances × 1 via each = 4 vias in plated drill."""
        import re
        drl = self.drill["panel_test.DRL"]
        hits = re.findall(r"X-?\d+Y-?\d+$", drl, re.MULTILINE)
        self.assertGreaterEqual(len(hits), 4)


# ─── LLM tool: panelize_board ─────────────────────────────────────────────────

class TestPanelizeBoardTool(unittest.IsolatedAsyncioTestCase):

    async def _call(self, payload: dict) -> dict:
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "panelize_board")
        result_str = await tool.run(None, json.dumps(payload).encode())
        return json.loads(result_str)

    async def test_tool_registered(self):
        from kerf_chat.tools.registry import Registry
        names = {t.spec.name for t in Registry}
        self.assertIn("panelize_board", names)

    async def test_basic_2x2_mousebites(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
            "separation": "mousebites",
        })
        self.assertNotIn("error", result)
        self.assertEqual(result["cols"], 2)
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["instance_count"], 4)
        self.assertGreater(result["separation_feature_count"], 0)
        self.assertIn("panel_descriptor", result)

    async def test_vscore_separation(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
            "separation": "vscore",
        })
        self.assertNotIn("error", result)
        self.assertEqual(result["separation"], "vscore")
        self.assertGreater(result["separation_feature_count"], 0)

    async def test_tab_route_separation(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
            "separation": "tab_route",
        })
        self.assertNotIn("error", result)
        self.assertEqual(result["separation"], "tab_route")
        self.assertGreater(result["separation_feature_count"], 0)

    async def test_panel_descriptor_in_response(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
        })
        pd = result["panel_descriptor"]
        self.assertIn("instances", pd)
        self.assertEqual(len(pd["instances"]), 4)

    async def test_panel_descriptor_instances_have_circuit_json(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
        })
        for inst in result["panel_descriptor"]["instances"]:
            self.assertIn("circuit_json", inst)
            self.assertGreater(len(inst["circuit_json"]), 0)

    async def test_zip_in_response(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
        })
        import base64
        self.assertIn("zip_b64", result)
        zip_bytes = base64.b64decode(result["zip_b64"])
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(zip_bytes)))

    async def test_zip_contains_gerbers(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
        })
        import base64
        zip_bytes = base64.b64decode(result["zip_b64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        gerber_count = sum(1 for n in names if n.endswith(
            (".GTL", ".GBL", ".GKO", ".GTO", ".GBO", ".GTS", ".GBS")))
        self.assertGreater(gerber_count, 0)

    async def test_frame_present(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
            "add_frame": True,
        })
        self.assertIsNotNone(result["frame"])
        self.assertGreater(result["frame"]["tooling_holes"], 0)
        self.assertGreater(result["frame"]["fiducials"], 0)

    async def test_no_frame(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
            "add_frame": False,
        })
        self.assertIsNone(result["frame"])

    async def test_bad_args_not_array(self):
        result = await self._call({"circuit_json": "not_an_array"})
        self.assertIn("error", result)

    async def test_bad_separation(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "separation": "unknown_method",
        })
        self.assertIn("error", result)

    async def test_message_field_present(self):
        result = await self._call({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
        })
        self.assertIn("message", result)


# ─── LLM tool: panel_info ────────────────────────────────────────────────────

class TestPanelInfoTool(unittest.IsolatedAsyncioTestCase):

    async def _call_panelize(self, payload: dict) -> dict:
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "panelize_board")
        result_str = await tool.run(None, json.dumps(payload).encode())
        return json.loads(result_str)

    async def _call_info(self, panel_descriptor: dict) -> dict:
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "panel_info")
        result_str = await tool.run(None, json.dumps({"panel_descriptor": panel_descriptor}).encode())
        return json.loads(result_str)

    async def test_tool_registered(self):
        from kerf_chat.tools.registry import Registry
        names = {t.spec.name for t in Registry}
        self.assertIn("panel_info", names)

    async def test_info_returns_correct_dimensions(self):
        p_result = await self._call_panelize({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
        })
        info = await self._call_info(p_result["panel_descriptor"])
        self.assertNotIn("error", info)
        self.assertEqual(info["cols"], 2)
        self.assertEqual(info["rows"], 2)
        self.assertEqual(info["instance_count"], 4)
        self.assertAlmostEqual(info["board_w_mm"], 50.0, places=2)
        self.assertAlmostEqual(info["board_h_mm"], 30.0, places=2)

    async def test_info_lists_instances(self):
        p_result = await self._call_panelize({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
        })
        info = await self._call_info(p_result["panel_descriptor"])
        self.assertEqual(len(info["instances"]), 4)
        for inst in info["instances"]:
            for k in ("col", "row", "origin_x", "origin_y", "rotated180"):
                self.assertIn(k, inst)

    async def test_info_separation_by_type(self):
        p_result = await self._call_panelize({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
            "separation": "vscore",
        })
        info = await self._call_info(p_result["panel_descriptor"])
        types = info["separation_features_by_type"]
        self.assertIn("_vscore_line", types)

    async def test_info_frame_summary(self):
        p_result = await self._call_panelize({
            "circuit_json": FIXTURE_BOARD,
            "cols": 2, "rows": 2,
            "add_frame": True,
        })
        info = await self._call_info(p_result["panel_descriptor"])
        self.assertIsNotNone(info["frame"])
        self.assertGreater(info["frame"]["tooling_holes"], 0)

    async def test_info_bad_descriptor(self):
        info = await self._call_info({"bad": "descriptor"})
        self.assertIn("error", info)

    async def test_info_not_object(self):
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "panel_info")
        result_str = await tool.run(None, json.dumps({"panel_descriptor": "not_a_dict"}).encode())
        result = json.loads(result_str)
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
