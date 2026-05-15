"""
Tests for IDF 3.0 ECAD↔MCAD board export.

Exercises the pure-Python export_idf() function and the export_idf LLM tool.
All tests are hermetic — no network, no disk I/O, no optional dependencies.

Coverage:
  - _build_emn / _build_emp: record structure, section keywords, loop closure
  - export_idf: returns .emn and .emp keys; correct content structure
  - Fixture board: board outline, 2 holes, 2 placed components, unique packages
  - LLM tool: registered; accepts circuit_json; bad-args guard
  - Empty circuit: safe fallback (default 100×100 outline, no holes, no components)
"""

from __future__ import annotations

import base64
import json
import unittest

# Side-effect import: fires @register decorators for export_idf tool
import kerf_electronics.tools.idf_export  # noqa: F401

from kerf_electronics.tools.idf_export import (
    _build_emn,
    _build_emp,
    export_idf,
)


# ─── Shared fixture ────────────────────────────────────────────────────────────
# Same board used by test_board_step.py — consistent geometry across exporters.

FIXTURE_CIRCUIT_JSON = [
    {
        "type": "pcb_board",
        "width": 100.0,
        "height": 80.0,
        "center_x": 50.0,
        "center_y": 40.0,
    },
    {
        "type": "source_component",
        "source_component_id": "sc_r1",
        "name": "R1",
        "value": "10k",
        "footprint": "R_0402",
    },
    {
        "type": "source_component",
        "source_component_id": "sc_u1",
        "name": "U1",
        "value": "ATmega328P",
        "footprint": "TQFP-32",
    },
    {
        "type": "pcb_component",
        "pcb_component_id": "pcb_r1",
        "source_component_id": "sc_r1",
        "x": 20.0,
        "y": 30.0,
        "rotation": 0.0,
        "layer": "top_copper",
    },
    {
        "type": "pcb_component",
        "pcb_component_id": "pcb_u1",
        "source_component_id": "sc_u1",
        "x": 60.0,
        "y": 40.0,
        "rotation": 90.0,
        "layer": "top_copper",
    },
    {
        "type": "pcb_via",
        "pcb_via_id": "via_1",
        "x": 40.0,
        "y": 35.0,
        "outer_diameter": 0.6,
        "hole_diameter": 0.3,
    },
    {
        "type": "pcb_plated_pad",
        "pcb_plated_pad_id": "pad_pth_1",
        "source_component_id": "sc_u1",
        "x": 58.0,
        "y": 38.0,
        "width": 1.6,
        "height": 1.6,
        "hole_diameter": 0.8,
        "shape": "circle",
        "layer": "top_copper",
    },
]


# ─── .emn structure tests ──────────────────────────────────────────────────────

class TestBuildEmn(unittest.TestCase):

    def _emn(self, circuit_json=None, stem="board", thickness=1.6) -> str:
        cj = circuit_json if circuit_json is not None else FIXTURE_CIRCUIT_JSON
        return _build_emn(cj, stem, thickness)

    # ── Header ────────────────────────────────────────────────────────────────

    def test_header_section_present(self):
        emn = self._emn()
        self.assertIn(".HEADER", emn)
        self.assertIn(".END_HEADER", emn)

    def test_header_contains_board_file(self):
        emn = self._emn()
        self.assertIn("BOARD_FILE 3.0", emn)

    def test_header_contains_mm_unit(self):
        emn = self._emn(stem="myboard")
        self.assertIn("MM", emn)
        self.assertIn("myboard", emn)

    # ── Board outline ─────────────────────────────────────────────────────────

    def test_board_outline_section_present(self):
        emn = self._emn()
        self.assertIn(".BOARD_OUTLINE", emn)
        self.assertIn(".END_BOARD_OUTLINE", emn)

    def test_board_thickness_in_outline(self):
        emn = self._emn(thickness=1.6)
        # The thickness value appears right after .BOARD_OUTLINE
        lines = emn.splitlines()
        idx = next(i for i, ln in enumerate(lines) if ln.startswith(".BOARD_OUTLINE"))
        thickness_line = lines[idx + 1].strip()
        self.assertAlmostEqual(float(thickness_line), 1.6, places=3)

    def test_board_outline_has_loop_index_0(self):
        emn = self._emn()
        lines = emn.splitlines()
        idx = next(i for i, ln in enumerate(lines) if ln.startswith(".BOARD_OUTLINE"))
        # loop index line is at idx+2
        loop_line = lines[idx + 2].strip()
        self.assertEqual(loop_line, "0")

    def test_board_outline_vertices_present(self):
        emn = self._emn()
        # For a 100×80 board starting at (0,0): expect vertices like "0 0 0.0"
        self.assertIn("0 0 0.0", emn)

    def test_board_outline_loop_closed(self):
        """First vertex should appear twice (at start and end of loop)."""
        emn = self._emn()
        lines = emn.splitlines()
        start = next(i for i, ln in enumerate(lines) if ln.startswith(".BOARD_OUTLINE"))
        end = next(i for i, ln in enumerate(lines) if ln.startswith(".END_BOARD_OUTLINE"))
        # Vertex lines have exactly 3 space-separated tokens: x y arc_angle
        vertex_lines = [
            ln for ln in lines[start:end]
            if ln and len(ln.split()) == 3
        ]
        # There should be at least 5 vertex lines (4 corners + closure)
        self.assertGreaterEqual(len(vertex_lines), 5)
        # First and last vertex must match
        self.assertEqual(vertex_lines[0], vertex_lines[-1])

    # ── Drilled holes ─────────────────────────────────────────────────────────

    def test_drilled_holes_section_present(self):
        emn = self._emn()
        self.assertIn(".DRILLED_HOLES", emn)
        self.assertIn(".END_DRILLED_HOLES", emn)

    def test_hole_records_count(self):
        # Fixture: 1 via (0.3 mm) + 1 PTH pad (0.8 mm) = 2 holes
        emn = self._emn()
        hole_lines = [
            ln for ln in emn.splitlines()
            if "PTH BOARD NOPIN VIA" in ln
        ]
        self.assertEqual(len(hole_lines), 2)

    def test_hole_diameter_present(self):
        emn = self._emn()
        # via hole diameter 0.3
        self.assertIn("0.3 ", emn)

    def test_hole_record_format(self):
        """Each hole line: <diameter> <x> <y> PTH BOARD NOPIN VIA"""
        emn = self._emn()
        for ln in emn.splitlines():
            if "PTH BOARD NOPIN VIA" in ln:
                parts = ln.strip().split()
                self.assertGreaterEqual(len(parts), 7)
                # First 3 parts are floats (diameter, x, y)
                for i in range(3):
                    float(parts[i])  # should not raise
                self.assertEqual(parts[3], "PTH")
                self.assertEqual(parts[4], "BOARD")
                self.assertEqual(parts[5], "NOPIN")
                self.assertEqual(parts[6], "VIA")

    # ── Placement ─────────────────────────────────────────────────────────────

    def test_placement_section_present(self):
        emn = self._emn()
        self.assertIn(".PLACEMENT", emn)
        self.assertIn(".END_PLACEMENT", emn)

    def test_placement_has_two_components(self):
        emn = self._emn()
        lines = emn.splitlines()
        start = next(i for i, ln in enumerate(lines) if ln == ".PLACEMENT")
        end = next(i for i, ln in enumerate(lines) if ln == ".END_PLACEMENT")
        placed = [ln for ln in lines[start + 1:end] if ln.strip().startswith('"')]
        self.assertEqual(len(placed), 2)

    def test_placement_contains_r1(self):
        emn = self._emn()
        self.assertIn('"R1"', emn)

    def test_placement_contains_u1(self):
        emn = self._emn()
        self.assertIn('"U1"', emn)

    def test_placement_top_side(self):
        emn = self._emn()
        # Both components are top_copper — should see TOP
        lines = [ln for ln in emn.splitlines() if '"R1"' in ln or '"U1"' in ln]
        for ln in lines:
            self.assertIn("TOP", ln)

    def test_placement_u1_rotation(self):
        emn = self._emn()
        # U1 has rotation=90 in fixture
        u1_line = next(ln for ln in emn.splitlines() if '"U1"' in ln)
        self.assertIn("90", u1_line)

    def test_no_placement_section_for_empty_circuit(self):
        emn = self._emn(circuit_json=[])
        self.assertNotIn(".PLACEMENT", emn)

    def test_no_holes_section_for_empty_circuit(self):
        emn = self._emn(circuit_json=[])
        self.assertNotIn(".DRILLED_HOLES", emn)


# ─── .emp structure tests ──────────────────────────────────────────────────────

class TestBuildEmp(unittest.TestCase):

    def _emp(self, circuit_json=None, stem="board") -> str:
        cj = circuit_json if circuit_json is not None else FIXTURE_CIRCUIT_JSON
        return _build_emp(cj, stem)

    # ── Header ────────────────────────────────────────────────────────────────

    def test_header_present(self):
        emp = self._emp()
        self.assertIn(".HEADER", emp)
        self.assertIn(".END_HEADER", emp)

    def test_header_contains_library_file(self):
        emp = self._emp()
        self.assertIn("LIBRARY_FILE 3.0", emp)

    # ── ELECTRICAL sections ───────────────────────────────────────────────────

    def test_electrical_section_present(self):
        emp = self._emp()
        self.assertIn(".ELECTRICAL", emp)
        self.assertIn(".END_ELECTRICAL", emp)

    def test_two_unique_packages(self):
        # Fixture: R_0402 and TQFP-32 → 2 .ELECTRICAL sections
        emp = self._emp()
        count = emp.count(".ELECTRICAL\n")
        self.assertEqual(count, 2)

    def test_r0402_package_present(self):
        emp = self._emp()
        self.assertIn('"R_0402"', emp)

    def test_tqfp32_package_present(self):
        emp = self._emp()
        self.assertIn('"TQFP-32"', emp)

    def test_electrical_outline_loop_closed(self):
        """Each .ELECTRICAL section's outline loop must be closed."""
        emp = self._emp()
        lines = emp.splitlines()
        i = 0
        while i < len(lines):
            if lines[i] == ".ELECTRICAL":
                # Find matching .END_ELECTRICAL
                end = next(j for j in range(i + 1, len(lines)) if lines[j] == ".END_ELECTRICAL")
                # Collect vertex lines (lines after loop index '0')
                section = lines[i:end]
                # Find the '0' loop index line
                li = next(k for k, ln in enumerate(section) if ln.strip() == "0")
                # Vertex lines have exactly 3 space-separated tokens: x y arc_angle
                vertex_lines = [
                    ln for ln in section[li + 1:]
                    if ln and len(ln.split()) == 3
                ]
                # At least 5 lines (4 corners + closure)
                self.assertGreaterEqual(len(vertex_lines), 5, f"Short outline in .ELECTRICAL at line {i}")
                # First == last
                self.assertEqual(vertex_lines[0], vertex_lines[-1],
                                 f"Loop not closed in .ELECTRICAL at line {i}")
                i = end + 1
            else:
                i += 1

    def test_package_height_positive(self):
        """Height field in each .ELECTRICAL section must be a positive float."""
        emp = self._emp()
        lines = emp.splitlines()
        i = 0
        while i < len(lines):
            if lines[i] == ".ELECTRICAL":
                # height is 2 lines after .ELECTRICAL: skip package line, height line
                height_line = lines[i + 2].strip()
                self.assertGreater(float(height_line), 0.0,
                                   f"Non-positive height at line {i + 2}")
                i += 1
            else:
                i += 1

    def test_empty_circuit_emp_has_no_electrical(self):
        emp = self._emp(circuit_json=[])
        self.assertNotIn(".ELECTRICAL", emp)


# ─── export_idf public API ─────────────────────────────────────────────────────

class TestExportIdf(unittest.TestCase):

    def _export(self, circuit_json=None, **kwargs):
        cj = circuit_json if circuit_json is not None else FIXTURE_CIRCUIT_JSON
        return export_idf(cj, **kwargs)

    def test_returns_two_files(self):
        files = self._export()
        self.assertEqual(len(files), 2)

    def test_emn_key_present(self):
        files = self._export(stem="myboard")
        self.assertIn("myboard.emn", files)

    def test_emp_key_present(self):
        files = self._export(stem="myboard")
        self.assertIn("myboard.emp", files)

    def test_emn_is_nonempty_string(self):
        files = self._export()
        self.assertIsInstance(files["board.emn"], str)
        self.assertGreater(len(files["board.emn"]), 0)

    def test_emp_is_nonempty_string(self):
        files = self._export()
        self.assertIsInstance(files["board.emp"], str)
        self.assertGreater(len(files["board.emp"]), 0)

    def test_emn_has_all_required_sections(self):
        emn = self._export()["board.emn"]
        for kw in (".HEADER", ".END_HEADER", ".BOARD_OUTLINE", ".END_BOARD_OUTLINE"):
            self.assertIn(kw, emn, f"Missing section: {kw}")

    def test_emp_has_required_sections(self):
        emp = self._export()["board.emp"]
        for kw in (".HEADER", ".END_HEADER", ".ELECTRICAL", ".END_ELECTRICAL"):
            self.assertIn(kw, emp, f"Missing section: {kw}")

    def test_custom_thickness(self):
        emn = self._export(board_thickness_mm=0.8)["board.emn"]
        lines = emn.splitlines()
        idx = next(i for i, ln in enumerate(lines) if ln.startswith(".BOARD_OUTLINE"))
        thickness_line = lines[idx + 1].strip()
        self.assertAlmostEqual(float(thickness_line), 0.8, places=3)

    def test_empty_circuit_safe(self):
        files = export_idf([], stem="empty")
        self.assertIn("empty.emn", files)
        self.assertIn("empty.emp", files)
        # No placement or holes expected
        emn = files["empty.emn"]
        self.assertNotIn(".PLACEMENT", emn)
        self.assertNotIn(".DRILLED_HOLES", emn)

    def test_nonlist_circuit_json_safe(self):
        files = export_idf(None, stem="safe")  # type: ignore[arg-type]
        self.assertIn("safe.emn", files)

    def test_at_least_one_component_placed(self):
        files = self._export()
        emn = files["board.emn"]
        self.assertIn(".PLACEMENT", emn)
        placed = [ln for ln in emn.splitlines() if ln.strip().startswith('"')]
        self.assertGreaterEqual(len(placed), 1)


# ─── LLM tool tests ────────────────────────────────────────────────────────────

class TestExportIdfTool(unittest.IsolatedAsyncioTestCase):

    def _tool(self):
        from kerf_chat.tools.registry import Registry
        return next(t for t in Registry if t.spec.name == "export_idf")

    def test_tool_registered(self):
        from kerf_chat.tools.registry import Registry
        names = {t.spec.name for t in Registry}
        self.assertIn("export_idf", names)

    def test_spec_has_circuit_json_required(self):
        tool = self._tool()
        self.assertIn("circuit_json", tool.spec.input_schema["properties"])
        self.assertIn("circuit_json", tool.spec.input_schema["required"])

    def test_spec_has_stem_and_thickness(self):
        tool = self._tool()
        props = tool.spec.input_schema["properties"]
        self.assertIn("stem", props)
        self.assertIn("board_thickness_mm", props)

    async def test_tool_bad_args_returns_error(self):
        tool = self._tool()
        payload = json.dumps({"circuit_json": "not-an-array"}).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertIn("error", result)
        self.assertEqual(result.get("code"), "BAD_ARGS")

    async def test_tool_invalid_json_returns_error(self):
        tool = self._tool()
        result = json.loads(await tool.run(None, b"{bad json"))
        self.assertIn("error", result)
        self.assertEqual(result.get("code"), "BAD_ARGS")

    async def test_tool_success_returns_emn_b64(self):
        tool = self._tool()
        payload = json.dumps({
            "circuit_json": FIXTURE_CIRCUIT_JSON,
            "stem": "test_board",
        }).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertNotIn("error", result, result)
        self.assertIn("emn_b64", result)
        # Decode and verify content
        emn_text = base64.b64decode(result["emn_b64"]).decode()
        self.assertIn(".BOARD_OUTLINE", emn_text)
        self.assertIn(".PLACEMENT", emn_text)

    async def test_tool_success_returns_emp_b64(self):
        tool = self._tool()
        payload = json.dumps({
            "circuit_json": FIXTURE_CIRCUIT_JSON,
        }).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertIn("emp_b64", result)
        emp_text = base64.b64decode(result["emp_b64"]).decode()
        self.assertIn(".ELECTRICAL", emp_text)

    async def test_tool_filenames_match_stem(self):
        tool = self._tool()
        payload = json.dumps({
            "circuit_json": FIXTURE_CIRCUIT_JSON,
            "stem": "mcu_rev2",
        }).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertEqual(result.get("emn_filename"), "mcu_rev2.emn")
        self.assertEqual(result.get("emp_filename"), "mcu_rev2.emp")

    async def test_tool_placement_count(self):
        tool = self._tool()
        payload = json.dumps({"circuit_json": FIXTURE_CIRCUIT_JSON}).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertGreaterEqual(result.get("placement_count", 0), 1)

    async def test_tool_message_present(self):
        tool = self._tool()
        payload = json.dumps({"circuit_json": FIXTURE_CIRCUIT_JSON}).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertIn("message", result)
        self.assertIn("IDF 3.0", result["message"])

    async def test_tool_empty_circuit_no_error(self):
        tool = self._tool()
        payload = json.dumps({"circuit_json": []}).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertNotIn("error", result, result)
        self.assertIn("emn_b64", result)


if __name__ == "__main__":
    unittest.main()
