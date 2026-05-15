"""
Tests for T-9 / T-10 / T-11 / T-12 — PCB fabrication output writers.

Tests are fully hermetic (no network I/O).  A single fixture board is
shared across all test classes; individual tests verify structural properties
of the generated files rather than byte-exact output so the tests remain
stable when formatting details evolve.
"""

import base64
import io
import json
import re
import unittest
import xml.etree.ElementTree as ET
import zipfile

# Import the tools module at module level so @register decorators fire
# and the tools appear in the Registry (same pattern as test_pcb_drc.py)
import kerf_electronics.tools.fab  # noqa: F401

# ─── Fixture board ─────────────────────────────────────────────────────────────
# A minimal but representative two-layer board with:
#   - 1 pcb_board element (100 × 80 mm)
#   - 2 source_components (R1 resistor, U1 IC)
#   - 2 pcb_components (R1 top, U1 top)
#   - 2 SMT pads (one per component)
#   - 1 plated pad (through-hole component hole)
#   - 1 via
#   - 1 trace segment
#   - 1 copper pour fill


FIXTURE_CIRCUIT_JSON = [
    {
        "type": "pcb_board",
        "width": 100.0,
        "height": 80.0,
        "center_x": 50.0,
        "center_y": 40.0,
    },
    # ── source components ──────────────────────────────────────────────────────
    {
        "type": "source_component",
        "source_component_id": "sc_r1",
        "name": "R1",
        "value": "10k",
        "footprint": "R_0402",
        "mpn": "RC0402FR-0710KL",
        "manufacturer": "Yageo",
        "description": "Resistor 10k 1% 0402",
        "distributors": [
            {"name": "DigiKey", "part_number": "311-10KLRCT-ND", "unit_price_usd": 0.10},
            {"name": "Mouser", "part_number": "603-RC0402FR-0710KL", "unit_price_usd": 0.12},
        ],
    },
    {
        "type": "source_component",
        "source_component_id": "sc_u1",
        "name": "U1",
        "value": "ATmega328P",
        "footprint": "TQFP-32",
        "mpn": "ATMEGA328P-AU",
        "manufacturer": "Microchip",
        "description": "8-bit MCU 32KB Flash",
        "distributors": [
            {"name": "DigiKey", "part_number": "ATMEGA328P-AU-ND", "unit_price_usd": 2.50},
        ],
    },
    # ── pcb components ──────────────────────────────────────────────────────────
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
    # ── SMT pad (R1) ───────────────────────────────────────────────────────────
    {
        "type": "pcb_smtpad",
        "pcb_smtpad_id": "pad_r1_1",
        "source_component_id": "sc_r1",
        "x": 19.5,
        "y": 30.0,
        "width": 1.2,
        "height": 0.8,
        "shape": "rect",
        "layer": "top_copper",
    },
    # ── plated through-hole pad (U1 pin 1, acts as a PTH test) ────────────────
    {
        "type": "pcb_plated_pad",
        "pcb_plated_pad_id": "pad_u1_1",
        "source_component_id": "sc_u1",
        "x": 58.0,
        "y": 38.0,
        "width": 1.6,
        "height": 1.6,
        "hole_diameter": 0.8,
        "shape": "circle",
        "layer": "top_copper",
    },
    # ── via ────────────────────────────────────────────────────────────────────
    {
        "type": "pcb_via",
        "pcb_via_id": "via_1",
        "x": 40.0,
        "y": 35.0,
        "outer_diameter": 0.6,
        "hole_diameter": 0.3,
    },
    # ── trace segment ──────────────────────────────────────────────────────────
    {
        "type": "pcb_trace",
        "pcb_trace_id": "trace_1",
        "net_id": "GND",
        "route": [
            {"route_type": "wire", "x": 20.0, "y": 30.0, "width": 0.25, "layer": "top_copper"},
            {"route_type": "wire", "x": 40.0, "y": 30.0, "width": 0.25, "layer": "top_copper"},
        ],
    },
    # ── copper pour fill ───────────────────────────────────────────────────────
    {
        "type": "copper_pour_fill",
        "layer": "bottom_copper",
        "net_id": "GND",
        "polygon": [
            {"x": 0.0, "y": 0.0},
            {"x": 100.0, "y": 0.0},
            {"x": 100.0, "y": 80.0},
            {"x": 0.0, "y": 80.0},
        ],
    },
    # ── second resistor (same value+footprint as R1, for BOM grouping test) ───
    {
        "type": "source_component",
        "source_component_id": "sc_r2",
        "name": "R2",
        "value": "10k",
        "footprint": "R_0402",
        "mpn": "RC0402FR-0710KL",
        "manufacturer": "Yageo",
        "description": "Resistor 10k 1% 0402",
        "distributors": [
            {"name": "DigiKey", "part_number": "311-10KLRCT-ND", "unit_price_usd": 0.10},
        ],
    },
    {
        "type": "pcb_component",
        "pcb_component_id": "pcb_r2",
        "source_component_id": "sc_r2",
        "x": 22.0,
        "y": 30.0,
        "rotation": 0.0,
        "layer": "top_copper",
    },
    {
        "type": "pcb_smtpad",
        "pcb_smtpad_id": "pad_r2_1",
        "source_component_id": "sc_r2",
        "x": 22.5,
        "y": 30.0,
        "width": 1.2,
        "height": 0.8,
        "shape": "rect",
        "layer": "top_copper",
    },
]


# ─── T-9: Gerber RS-274X writer ───────────────────────────────────────────────

class TestGerberWriter(unittest.TestCase):

    def setUp(self):
        from kerf_electronics.fab.gerber import export_gerber
        self.export = export_gerber
        self.files = export_gerber(FIXTURE_CIRCUIT_JSON, stem="test_board")

    def test_returns_dict_of_strings(self):
        self.assertIsInstance(self.files, dict)
        for k, v in self.files.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

    def test_top_copper_layer_present(self):
        self.assertIn("test_board.GTL", self.files)

    def test_bottom_copper_layer_present(self):
        self.assertIn("test_board.GBL", self.files)

    def test_board_outline_layer_present(self):
        self.assertIn("test_board.GKO", self.files)

    def test_silk_layers_present(self):
        self.assertIn("test_board.GTO", self.files)
        self.assertIn("test_board.GBO", self.files)

    def test_mask_layers_present(self):
        self.assertIn("test_board.GTS", self.files)
        self.assertIn("test_board.GBS", self.files)

    def test_gerber_header_present(self):
        gtl = self.files["test_board.GTL"]
        self.assertIn("%FSLAX46Y46*%", gtl)
        self.assertIn("%MOMM*%", gtl)

    def test_gerber_ends_with_m02(self):
        for fname, content in self.files.items():
            self.assertIn("M02*", content, f"{fname} missing M02 end-of-file marker")

    def test_aperture_definitions_present(self):
        gtl = self.files["test_board.GTL"]
        # At least one %ADD... aperture definition must exist
        self.assertRegex(gtl, r"%ADD\d+[CRO],")

    def test_flash_operations_present_for_pad(self):
        # D03 = flash
        gtl = self.files["test_board.GTL"]
        self.assertIn("D03*", gtl)

    def test_draw_operations_present_for_trace(self):
        # D01 = draw (interpolate)
        gtl = self.files["test_board.GTL"]
        self.assertIn("D01*", gtl)

    def test_copper_pour_region_in_bottom_layer(self):
        gbl = self.files["test_board.GBL"]
        self.assertIn("G36*", gbl)
        self.assertIn("G37*", gbl)

    def test_board_outline_draw_in_gko(self):
        gko = self.files["test_board.GKO"]
        self.assertIn("D01*", gko)

    def test_coordinate_format(self):
        # Coordinates must be large integers (4.6 = *1e6)
        gtl = self.files["test_board.GTL"]
        # e.g. X20000000 for x=20mm
        self.assertRegex(gtl, r"X\d+Y\d+D0[123]\*")

    def test_empty_circuit_produces_minimal_gerbers(self):
        files = self.export([], stem="empty")
        self.assertIn("empty.GTL", files)
        self.assertIn("empty.GKO", files)
        for f in files.values():
            self.assertIn("M02*", f)

    def test_layer_extension_inner(self):
        from kerf_electronics.fab.gerber import layer_extension
        self.assertEqual(layer_extension("inner_1"), "GL2")
        self.assertEqual(layer_extension("inner_3"), "GL4")

    def test_layer_extension_standard(self):
        from kerf_electronics.fab.gerber import layer_extension
        self.assertEqual(layer_extension("top_copper"), "GTL")
        self.assertEqual(layer_extension("edge_cuts"), "GKO")


# ─── T-10: Excellon drill writer ─────────────────────────────────────────────

class TestExcellonWriter(unittest.TestCase):

    def setUp(self):
        from kerf_electronics.fab.excellon import export_excellon
        self.export = export_excellon
        self.files = export_excellon(FIXTURE_CIRCUIT_JSON, stem="test_board")

    def test_returns_dict_of_strings(self):
        self.assertIsInstance(self.files, dict)

    def test_plated_drill_file_present(self):
        self.assertIn("test_board.DRL", self.files)

    def test_excellon_header_present(self):
        drl = self.files["test_board.DRL"]
        self.assertIn("M48", drl)
        self.assertIn("METRIC,TZ", drl)

    def test_excellon_footer_present(self):
        drl = self.files["test_board.DRL"]
        self.assertIn("M30", drl)

    def test_tool_table_entries_present(self):
        drl = self.files["test_board.DRL"]
        # T01C... pattern for tool definition
        self.assertRegex(drl, r"T\d+C[\d.]+")

    def test_distinct_tool_per_unique_diameter(self):
        """Each unique drill diameter must have exactly one T-code."""
        drl = self.files["test_board.DRL"]
        # Find all tool definitions (in header block before %)
        defs = re.findall(r"T(\d+)C([\d.]+)", drl)
        tool_nums = [int(d[0]) for d in defs]
        diameters = [float(d[1]) for d in defs]
        # No duplicate diameters in the tool table
        self.assertEqual(len(diameters), len(set(diameters)))
        # No duplicate T-codes
        self.assertEqual(len(tool_nums), len(set(tool_nums)))

    def test_drill_hits_present(self):
        drl = self.files["test_board.DRL"]
        # X...Y... coordinate lines after header
        hits = re.findall(r"X-?\d+Y-?\d+$", drl, re.MULTILINE)
        self.assertGreater(len(hits), 0)

    def test_via_and_pth_pad_both_captured(self):
        """Fixture has 1 via + 1 PTH pad = at least 2 drill hits."""
        drl = self.files["test_board.DRL"]
        hits = re.findall(r"X-?\d+Y-?\d+$", drl, re.MULTILINE)
        self.assertGreaterEqual(len(hits), 2)

    def test_empty_circuit_produces_empty_drl(self):
        files = self.export([], stem="empty")
        self.assertIn("empty.DRL", files)
        drl = files["empty.DRL"]
        self.assertIn("M48", drl)
        self.assertIn("M30", drl)

    def test_collect_hits_via(self):
        from kerf_electronics.fab.excellon import _collect_hits
        circuit = [{"type": "pcb_via", "x": 10.0, "y": 5.0, "hole_diameter": 0.3}]
        hits = _collect_hits(circuit)
        self.assertEqual(len(hits), 1)
        self.assertAlmostEqual(hits[0].tool.diameter_mm, 0.3)
        self.assertTrue(hits[0].tool.plated)

    def test_collect_hits_smt_pad_excluded(self):
        from kerf_electronics.fab.excellon import _collect_hits
        circuit = [{"type": "pcb_smtpad", "x": 10.0, "y": 5.0, "width": 1.2, "height": 0.8}]
        hits = _collect_hits(circuit)
        self.assertEqual(len(hits), 0)

    def test_coordinate_format_3_3(self):
        """3.3 format: 10mm → 10000, not 10000000."""
        from kerf_electronics.fab.excellon import _fmt
        self.assertEqual(_fmt(10.0), "10000")
        self.assertEqual(_fmt(0.3), "300")
        self.assertEqual(_fmt(0.0), "0")


# ─── T-11: Pick-and-place + fab BOM ───────────────────────────────────────────

class TestPnPWriter(unittest.TestCase):

    def setUp(self):
        from kerf_electronics.fab.pnp import export_pnp
        self.export = export_pnp
        self.files = export_pnp(FIXTURE_CIRCUIT_JSON, stem="test_board")

    def test_top_and_bottom_csvs_returned(self):
        self.assertIn("test_board-top-pnp.csv", self.files)
        self.assertIn("test_board-bottom-pnp.csv", self.files)

    def test_csv_has_header(self):
        top_csv = self.files["test_board-top-pnp.csv"]
        first_line = top_csv.splitlines()[0]
        self.assertIn("Designator", first_line)
        self.assertIn("MidX(mm)", first_line)
        self.assertIn("Rotation(deg)", first_line)

    def test_placed_components_present_in_top_csv(self):
        top_csv = self.files["test_board-top-pnp.csv"]
        lines = top_csv.strip().splitlines()
        # header + 3 components (R1, R2, U1) on top side
        self.assertGreaterEqual(len(lines) - 1, 2)

    def test_all_components_have_coordinates(self):
        top_csv = self.files["test_board-top-pnp.csv"]
        lines = top_csv.strip().splitlines()[1:]  # skip header
        for line in lines:
            fields = line.split(",")
            # MidX and MidY are fields 3 and 4
            float(fields[3])  # must parse as float
            float(fields[4])

    def test_empty_circuit_returns_empty_rows(self):
        files = self.export([], stem="empty")
        top_csv = files["empty-top-pnp.csv"]
        lines = top_csv.strip().splitlines()
        # Only the header row
        self.assertEqual(len(lines), 1)

    def test_rotation_present(self):
        top_csv = self.files["test_board-top-pnp.csv"]
        lines = top_csv.strip().splitlines()
        # U1 has rotation=90 — check it appears somewhere
        self.assertTrue(any("90.00" in line for line in lines))

    def test_extract_components_returns_placed_only(self):
        from kerf_electronics.fab.pnp import _extract_components
        # source_component without matching pcb_component → not placed
        circuit = [
            {"type": "source_component", "source_component_id": "sc1", "name": "R99", "value": "1k", "footprint": "R_0402"},
            # No pcb_component for sc1
        ]
        comps = _extract_components(circuit)
        # When no pcb_components exist at all, placed_ids is empty →
        # _extract_components returns empty (no pcb_component elements present)
        self.assertEqual(len(comps), 0)


class TestFabBomWriter(unittest.TestCase):

    def setUp(self):
        from kerf_electronics.fab.fab_bom import export_fab_bom
        self.export = export_fab_bom
        self.files = export_fab_bom(FIXTURE_CIRCUIT_JSON, stem="test_board")

    def test_bom_csv_returned(self):
        self.assertIn("test_board-bom.csv", self.files)

    def test_bom_header_correct(self):
        bom_csv = self.files["test_board-bom.csv"]
        first_line = bom_csv.splitlines()[0]
        self.assertIn("Item", first_line)
        self.assertIn("Qty", first_line)
        self.assertIn("Refdes", first_line)
        self.assertIn("Value", first_line)
        self.assertIn("Footprint", first_line)

    def test_r1_and_r2_grouped_together(self):
        """R1 and R2 share value=10k + footprint=R_0402 → one BOM row, Qty=2."""
        bom_csv = self.files["test_board-bom.csv"]
        lines = bom_csv.strip().splitlines()[1:]
        # Find the 10k row
        ten_k_rows = [l for l in lines if "10k" in l]
        self.assertEqual(len(ten_k_rows), 1, "R1 and R2 should be grouped into one row")
        row = ten_k_rows[0]
        fields = row.split(",")
        qty_idx = 1  # "Qty" is second column
        self.assertEqual(fields[qty_idx].strip(), "2")

    def test_u1_in_separate_row(self):
        bom_csv = self.files["test_board-bom.csv"]
        self.assertIn("ATmega328P", bom_csv)

    def test_distributor_present(self):
        bom_csv = self.files["test_board-bom.csv"]
        self.assertIn("DigiKey", bom_csv)

    def test_empty_circuit_returns_header_only(self):
        files = self.export([], stem="empty")
        bom_csv = files["empty-bom.csv"]
        lines = bom_csv.strip().splitlines()
        self.assertEqual(len(lines), 1)  # header only

    def test_pick_cheapest_distributor(self):
        from kerf_electronics.fab.fab_bom import _pick_cheapest_distributor
        src = {
            "distributors": [
                {"name": "Mouser", "part_number": "M1", "unit_price_usd": 0.50},
                {"name": "DigiKey", "part_number": "D1", "unit_price_usd": 0.10},
            ]
        }
        name, pn = _pick_cheapest_distributor(src)
        self.assertEqual(name, "DigiKey")
        self.assertEqual(pn, "D1")


# ─── T-12: IPC-2581 XML writer ────────────────────────────────────────────────

class TestIPC2581Writer(unittest.TestCase):

    def setUp(self):
        from kerf_electronics.fab.ipc2581 import export_ipc2581
        self.export = export_ipc2581
        self.files = export_ipc2581(FIXTURE_CIRCUIT_JSON, stem="test_board")

    def test_xml_file_returned(self):
        self.assertIn("test_board.xml", self.files)

    def test_xml_is_well_formed(self):
        xml_text = self.files["test_board.xml"]
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            self.fail(f"IPC-2581 XML is not well-formed: {e}")

    def test_root_element_is_ipc2581(self):
        xml_text = self.files["test_board.xml"]
        root = ET.fromstring(xml_text)
        self.assertEqual(root.tag.split("}")[-1], "IPC-2581")

    def test_header_element_present(self):
        xml_text = self.files["test_board.xml"]
        root = ET.fromstring(xml_text)
        # Header may be namespaced
        header = root.find("{http://www.ipc.org/2581}Header") or root.find("Header")
        self.assertIsNotNone(header, "IPC-2581 XML must contain a Header element")

    def test_layer_stack_present(self):
        xml_text = self.files["test_board.xml"]
        root = ET.fromstring(xml_text)
        ns = "http://www.ipc.org/2581"
        ls = root.find(f"{{{ns}}}LayerStack") or root.find("LayerStack")
        self.assertIsNotNone(ls, "IPC-2581 XML must contain a LayerStack element")

    def test_bom_element_present(self):
        xml_text = self.files["test_board.xml"]
        root = ET.fromstring(xml_text)
        ns = "http://www.ipc.org/2581"
        bom = root.find(f"{{{ns}}}Bom") or root.find("Bom")
        self.assertIsNotNone(bom, "IPC-2581 XML must contain a Bom element")

    def test_ecad_element_present(self):
        xml_text = self.files["test_board.xml"]
        root = ET.fromstring(xml_text)
        ns = "http://www.ipc.org/2581"
        ecad = root.find(f"{{{ns}}}Ecad") or root.find("Ecad")
        self.assertIsNotNone(ecad, "IPC-2581 XML must contain an Ecad element")

    def test_bom_items_match_placed_components(self):
        xml_text = self.files["test_board.xml"]
        root = ET.fromstring(xml_text)
        ns = "http://www.ipc.org/2581"
        bom = root.find(f"{{{ns}}}Bom") or root.find("Bom")
        items = list(bom.findall(f"{{{ns}}}BomItem") or bom.findall("BomItem"))
        # Fixture has 4 pcb_components (R1, R2, U1 + pad_u1_1 is not a pcb_component)
        # Actually 3 pcb_components: pcb_r1, pcb_r2, pcb_u1
        self.assertEqual(len(items), 3)

    def test_drill_hits_in_ecad(self):
        xml_text = self.files["test_board.xml"]
        root = ET.fromstring(xml_text)
        ns = "http://www.ipc.org/2581"
        ecad = root.find(f"{{{ns}}}Ecad") or root.find("Ecad")
        cad_data = ecad.find(f"{{{ns}}}CadData") or ecad.find("CadData")
        drill = cad_data.find(f"{{{ns}}}DrillPattern") or cad_data.find("DrillPattern")
        hits = list(
            drill.findall(f"{{{ns}}}DrillHit") or drill.findall("DrillHit")
        )
        # 1 via + 1 PTH pad = 2 drill hits
        self.assertGreaterEqual(len(hits), 2)

    def test_board_dimensions_in_ecad(self):
        xml_text = self.files["test_board.xml"]
        root = ET.fromstring(xml_text)
        ns = "http://www.ipc.org/2581"
        ecad = root.find(f"{{{ns}}}Ecad") or root.find("Ecad")
        cad_data = ecad.find(f"{{{ns}}}CadData") or ecad.find("CadData")
        board = cad_data.find(f"{{{ns}}}Board") or cad_data.find("Board")
        self.assertIsNotNone(board)
        xsize = float(board.get("xSize", 0))
        ysize = float(board.get("ySize", 0))
        self.assertAlmostEqual(xsize, 100.0, places=2)
        self.assertAlmostEqual(ysize, 80.0, places=2)

    def test_empty_circuit_xml_valid(self):
        files = self.export([], stem="empty")
        xml_text = files["empty.xml"]
        root = ET.fromstring(xml_text)
        self.assertEqual(root.tag.split("}")[-1], "IPC-2581")


# ─── T-12: export_fab_package zip bundle (via LLM tool) ──────────────────────

class TestFabPackageZip(unittest.TestCase):

    def setUp(self):
        from kerf_electronics.fab.gerber import export_gerber
        from kerf_electronics.fab.excellon import export_excellon
        from kerf_electronics.fab.pnp import export_pnp
        from kerf_electronics.fab.fab_bom import export_fab_bom
        from kerf_electronics.fab.ipc2581 import export_ipc2581

        self.gerber_files = export_gerber(FIXTURE_CIRCUIT_JSON, stem="board")
        self.drill_files = export_excellon(FIXTURE_CIRCUIT_JSON, stem="board")
        self.pnp_files = export_pnp(FIXTURE_CIRCUIT_JSON, stem="board")
        self.bom_files = export_fab_bom(FIXTURE_CIRCUIT_JSON, stem="board")
        self.ipc_files = export_ipc2581(FIXTURE_CIRCUIT_JSON, stem="board")

        # Build the zip manually (mirrors run_export_fab_package logic)
        import io, zipfile
        all_files = {}
        all_files.update(self.gerber_files)
        all_files.update(self.drill_files)
        all_files.update(self.pnp_files)
        all_files.update(self.bom_files)
        all_files.update(self.ipc_files)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fname, content in sorted(all_files.items()):
                zf.writestr(fname, content.encode("utf-8"))
        self.zip_bytes = buf.getvalue()
        self.all_files = all_files

    def test_zip_is_valid(self):
        buf = io.BytesIO(self.zip_bytes)
        self.assertTrue(zipfile.is_zipfile(buf))

    def test_zip_contains_gerbers(self):
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
            names = zf.namelist()
        gerber_count = sum(1 for n in names if n.endswith(
            (".GTL", ".GBL", ".GTO", ".GBO", ".GTS", ".GBS", ".GKO", ".GTP", ".GBP")))
        self.assertGreater(gerber_count, 0)

    def test_zip_contains_drill(self):
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
            names = zf.namelist()
        drill_count = sum(1 for n in names if n.endswith(".DRL"))
        self.assertGreater(drill_count, 0)

    def test_zip_contains_pnp(self):
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
            names = zf.namelist()
        pnp_count = sum(1 for n in names if "pnp" in n and n.endswith(".csv"))
        self.assertGreater(pnp_count, 0)

    def test_zip_contains_bom(self):
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
            names = zf.namelist()
        bom_count = sum(1 for n in names if "bom" in n and n.endswith(".csv"))
        self.assertGreater(bom_count, 0)

    def test_zip_contains_ipc2581(self):
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
            names = zf.namelist()
        ipc_count = sum(1 for n in names if n.endswith(".xml"))
        self.assertGreater(ipc_count, 0)

    def test_ipc2581_in_zip_is_valid_xml(self):
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
            xml_names = [n for n in zf.namelist() if n.endswith(".xml")]
            self.assertTrue(xml_names)
            xml_text = zf.read(xml_names[0]).decode("utf-8")
        root = ET.fromstring(xml_text)
        self.assertEqual(root.tag.split("}")[-1], "IPC-2581")

    def test_gerber_content_in_zip_has_rs274x_header(self):
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes)) as zf:
            gtl_names = [n for n in zf.namelist() if n.endswith(".GTL")]
            self.assertTrue(gtl_names)
            gtl = zf.read(gtl_names[0]).decode("utf-8")
        self.assertIn("%FSLAX46Y46*%", gtl)


class TestFabToolRegistered(unittest.IsolatedAsyncioTestCase):

    async def test_export_gerber_tool_registered(self):
        from kerf_chat.tools.registry import Registry
        names = {t.spec.name for t in Registry}
        self.assertIn("export_gerber", names)

    async def test_export_fab_package_tool_registered(self):
        from kerf_chat.tools.registry import Registry
        names = {t.spec.name for t in Registry}
        self.assertIn("export_fab_package", names)

    async def test_export_gerber_tool_runs(self):
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "export_gerber")
        payload = json.dumps({
            "circuit_json": FIXTURE_CIRCUIT_JSON,
            "stem": "tool_test",
        }).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertFalse("error" in result, result)
        self.assertIn("layers", result)
        self.assertGreater(result["layer_count"], 0)

    async def test_export_fab_package_tool_runs(self):
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "export_fab_package")
        payload = json.dumps({
            "circuit_json": FIXTURE_CIRCUIT_JSON,
            "stem": "pkg_test",
        }).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertFalse("error" in result, result)
        self.assertIn("zip_b64", result)
        zip_bytes = base64.b64decode(result["zip_b64"])
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(zip_bytes)))
        self.assertIn("manifest", result)

    async def test_export_fab_package_bad_args(self):
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "export_fab_package")
        payload = json.dumps({"circuit_json": "not-an-array"}).encode()
        result = json.loads(await tool.run(None, payload))
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
