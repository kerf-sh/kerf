"""test_netlist_export.py — pytest suite for netlist_export tools.

Tests are fully hermetic (no network I/O, no DB, no external processes).

Coverage:
  - KiCad S-expression format structural validity
  - OrCAD/PADS ASCII format structural validity
  - CSV format structural validity
  - All three formats tested against a shared fixture board
  - Extended ERC: single_node_net, power_pin_no_driver, conflicting_outputs
  - Extended ERC: deliberately-unconnected pin triggers erc_report error
  - LLM tool registration (export_netlist, erc_report)
  - Tool round-trip (encode/decode)
"""
import base64
import json
import re
import unittest

# Trigger @register decorators so tools appear in Registry
import kerf_electronics.tools.netlist_export  # noqa: F401

# Import pure functions directly for unit tests
from kerf_electronics.tools.netlist_export import (
    _export_kicad,
    _export_orcad_pads,
    _export_csv,
    _extract_net_graph,
    _run_erc_extended,
    _check_single_node_net,
    _check_power_pin_no_driver,
    _check_conflicting_outputs,
)


# ---------------------------------------------------------------------------
# Fixture circuit — a minimal but complete schematic with:
#   R1 (two passive pins): pin1 → VCC net, pin2 → GND net
#   U1 (MCU): VDD pin (power_in) on VCC net, GND pin (power_in) on GND net,
#             TX pin (output) on UART_TX net, RX pin (input) on UART_RX net
#   PWR (voltage regulator): OUT pin (power_out) on VCC net, GND pin (passive) on GND net
#
# This is a valid, connected circuit:
#   VCC: R1.pin1, U1.VDD, PWR.OUT  (3 nodes)
#   GND: R1.pin2, U1.GND, PWR.GND  (3 nodes)
#   UART_TX: U1.TX  (1 node — deliberately unconnected, triggers single_node_net)
#   UART_RX: U1.RX  (1 node — also unconnected)
# ---------------------------------------------------------------------------

_cid = [0]
_pid = [0]
_tid = [0]
_nid = [0]


def _reset():
    _cid[0] = _pid[0] = _tid[0] = _nid[0] = 0


def _comp(name, **kw):
    _cid[0] += 1
    return {"type": "source_component", "source_component_id": f"c{_cid[0]}", "name": name, **kw}


def _port(comp_id, name, pin_type="passive", **kw):
    _pid[0] += 1
    return {
        "type": "source_port",
        "source_port_id": f"p{_pid[0]}",
        "source_component_id": comp_id,
        "name": name,
        "pin_type": pin_type,
        **kw,
    }


def _trace(*port_ids, net_ids=None):
    _tid[0] += 1
    e = {
        "type": "source_trace",
        "source_trace_id": f"t{_tid[0]}",
        "connected_source_port_ids": list(port_ids),
    }
    if net_ids:
        e["connected_source_net_ids"] = net_ids
    return e


def _net(name, **kw):
    _nid[0] += 1
    return {"type": "source_net", "source_net_id": f"n{_nid[0]}", "name": name, **kw}


def _make_fixture():
    _reset()

    r1 = _comp("R1", value="10k", footprint="R_0402")
    u1 = _comp("U1", value="MCU32", footprint="QFP-48")
    pwr = _comp("VR1", value="LM7805", footprint="TO-220")

    # R1 pins
    r1_1 = _port(r1["source_component_id"], "1", "passive")
    r1_2 = _port(r1["source_component_id"], "2", "passive")

    # U1 pins
    u1_vdd = _port(u1["source_component_id"], "VDD", "power_in")
    u1_gnd = _port(u1["source_component_id"], "GND", "power_in")
    u1_tx  = _port(u1["source_component_id"], "TX",  "output")
    u1_rx  = _port(u1["source_component_id"], "RX",  "input")

    # PWR pins
    pwr_out = _port(pwr["source_component_id"], "OUT", "power_out")
    pwr_gnd = _port(pwr["source_component_id"], "GND", "passive")

    # Nets
    n_vcc = _net("VCC", is_power=True)
    n_gnd = _net("GND")
    n_tx  = _net("UART_TX")
    n_rx  = _net("UART_RX")

    # Traces: VCC connects R1.1, U1.VDD, PWR.OUT
    t_vcc = _trace(
        r1_1["source_port_id"],
        u1_vdd["source_port_id"],
        pwr_out["source_port_id"],
        net_ids=[n_vcc["source_net_id"]],
    )
    # GND connects R1.2, U1.GND, PWR.GND
    t_gnd = _trace(
        r1_2["source_port_id"],
        u1_gnd["source_port_id"],
        pwr_gnd["source_port_id"],
        net_ids=[n_gnd["source_net_id"]],
    )
    # TX and RX are deliberately left as single-node nets (no second connection)
    t_tx = _trace(u1_tx["source_port_id"], net_ids=[n_tx["source_net_id"]])
    t_rx = _trace(u1_rx["source_port_id"], net_ids=[n_rx["source_net_id"]])

    return [
        r1, u1, pwr,
        r1_1, r1_2, u1_vdd, u1_gnd, u1_tx, u1_rx, pwr_out, pwr_gnd,
        n_vcc, n_gnd, n_tx, n_rx,
        t_vcc, t_gnd, t_tx, t_rx,
    ]


FIXTURE_CIRCUIT = _make_fixture()


# ---------------------------------------------------------------------------
# Helper: a minimal circuit with conflicting outputs
# ---------------------------------------------------------------------------

def _make_conflict_circuit():
    """Two output-type pins on the same net."""
    _reset()
    c1 = _comp("U1")
    c2 = _comp("U2")
    p1 = _port(c1["source_component_id"], "OUT1", "output")
    p2 = _port(c2["source_component_id"], "OUT2", "output")
    t = _trace(p1["source_port_id"], p2["source_port_id"])
    return [c1, c2, p1, p2, t]


# ---------------------------------------------------------------------------
# Net graph extraction
# ---------------------------------------------------------------------------

class TestExtractNetGraph(unittest.TestCase):

    def setUp(self):
        self.graph = _extract_net_graph(FIXTURE_CIRCUIT)

    def test_returns_required_keys(self):
        for key in ("nets", "net_ports", "components", "ports"):
            self.assertIn(key, self.graph)

    def test_three_components_present(self):
        self.assertEqual(len(self.graph["components"]), 3)

    def test_component_refdes_present(self):
        names = {c["name"] for c in self.graph["components"].values()}
        self.assertIn("R1", names)
        self.assertIn("U1", names)
        self.assertIn("VR1", names)

    def test_vcc_net_has_three_nodes(self):
        nets = self.graph["nets"]
        net_ports = self.graph["net_ports"]
        vcc_root = next((r for r, n in nets.items() if n == "VCC"), None)
        self.assertIsNotNone(vcc_root, "VCC net not found in graph")
        self.assertEqual(len(net_ports.get(vcc_root, [])), 3)

    def test_gnd_net_has_three_nodes(self):
        nets = self.graph["nets"]
        net_ports = self.graph["net_ports"]
        gnd_root = next((r for r, n in nets.items() if n == "GND"), None)
        self.assertIsNotNone(gnd_root, "GND net not found in graph")
        self.assertEqual(len(net_ports.get(gnd_root, [])), 3)


# ---------------------------------------------------------------------------
# KiCad S-expression format
# ---------------------------------------------------------------------------

class TestExportKicad(unittest.TestCase):

    def setUp(self):
        self.text = _export_kicad(FIXTURE_CIRCUIT, stem="fixture_board")

    def test_returns_string(self):
        self.assertIsInstance(self.text, str)

    def test_root_export_tag(self):
        """Must start with (export …)."""
        self.assertTrue(self.text.strip().startswith("(export"))

    def test_version_field(self):
        self.assertIn('(version "1")', self.text)

    def test_design_source(self):
        self.assertIn("fixture_board", self.text)

    def test_tool_field(self):
        self.assertIn('"Kerf Electronics"', self.text)

    def test_components_section(self):
        self.assertIn("(components", self.text)

    def test_each_component_has_ref(self):
        for refdes in ("R1", "U1", "VR1"):
            self.assertIn(f"(ref {refdes})", self.text)

    def test_nets_section(self):
        self.assertIn("(nets", self.text)

    def test_net_names_present(self):
        for name in ("VCC", "GND", "UART_TX", "UART_RX"):
            self.assertIn(name, self.text)

    def test_node_entries_present(self):
        self.assertIn("(node", self.text)

    def test_closing_paren_balanced(self):
        """S-expression must have balanced parentheses."""
        self.assertEqual(self.text.count("("), self.text.count(")"))

    def test_empty_circuit(self):
        text = _export_kicad([], stem="empty")
        self.assertIn("(export", text)
        self.assertIn("(components", text)
        self.assertIn("(nets", text)
        # Balanced parens even for empty
        self.assertEqual(text.count("("), text.count(")"))


# ---------------------------------------------------------------------------
# OrCAD/PADS ASCII format
# ---------------------------------------------------------------------------

class TestExportOrcadPads(unittest.TestCase):

    def setUp(self):
        self.text = _export_orcad_pads(FIXTURE_CIRCUIT, stem="fixture_board")

    def test_returns_string(self):
        self.assertIsInstance(self.text, str)

    def test_header_line_contains_stem(self):
        first_line = self.text.splitlines()[0]
        self.assertIn("fixture_board", first_line)

    def test_part_section_marker(self):
        self.assertIn("*PART*", self.text)

    def test_net_section_marker(self):
        self.assertIn("*NET*", self.text)

    def test_end_marker(self):
        lines = [l.strip() for l in self.text.splitlines() if l.strip()]
        self.assertEqual(lines[-1], "*END*")

    def test_signal_markers_present(self):
        self.assertIn("*SIGNAL*", self.text)

    def test_signal_names_present(self):
        for name in ("VCC", "GND", "UART_TX", "UART_RX"):
            self.assertIn(f"*SIGNAL* {name}", self.text)

    def test_component_refdes_in_part_section(self):
        for refdes in ("R1", "U1", "VR1"):
            self.assertIn(refdes, self.text)

    def test_node_format_refdes_dot_pin(self):
        """Nodes must appear as REFDES.pin notation."""
        node_re = re.compile(r'\w+\.\w+')
        found = node_re.search(self.text)
        self.assertIsNotNone(found, "No REFDES.pin nodes found in PADS output")

    def test_empty_circuit(self):
        text = _export_orcad_pads([], stem="empty")
        self.assertIn("*PART*", text)
        self.assertIn("*NET*", text)
        self.assertIn("*END*", text)


# ---------------------------------------------------------------------------
# CSV format
# ---------------------------------------------------------------------------

class TestExportCsv(unittest.TestCase):

    def setUp(self):
        self.text = _export_csv(FIXTURE_CIRCUIT, stem="fixture_board")

    def test_returns_string(self):
        self.assertIsInstance(self.text, str)

    def test_header_row(self):
        first_line = self.text.splitlines()[0]
        self.assertEqual(first_line, "net_name,refdes,pin,pin_type")

    def test_vcc_rows_present(self):
        vcc_rows = [l for l in self.text.splitlines() if l.startswith("VCC,")]
        # VCC has 3 nodes: R1.1, U1.VDD, VR1.OUT
        self.assertEqual(len(vcc_rows), 3)

    def test_gnd_rows_present(self):
        gnd_rows = [l for l in self.text.splitlines() if l.startswith("GND,")]
        self.assertEqual(len(gnd_rows), 3)

    def test_uart_tx_row_present(self):
        tx_rows = [l for l in self.text.splitlines() if l.startswith("UART_TX,")]
        self.assertEqual(len(tx_rows), 1)

    def test_four_columns_per_row(self):
        import csv, io
        reader = csv.reader(io.StringIO(self.text))
        rows = list(reader)
        for row in rows:
            self.assertEqual(len(row), 4, f"Expected 4 columns, got {len(row)} in: {row}")

    def test_pin_type_column_non_empty(self):
        import csv, io
        reader = csv.reader(io.StringIO(self.text))
        rows = list(reader)[1:]  # skip header
        for row in rows:
            self.assertTrue(row[3].strip(), f"pin_type is empty for row: {row}")

    def test_empty_circuit(self):
        text = _export_csv([], stem="empty")
        lines = text.splitlines()
        self.assertEqual(lines[0], "net_name,refdes,pin,pin_type")
        # Only the header row for empty circuit
        self.assertEqual(len(lines), 1)


# ---------------------------------------------------------------------------
# Extended ERC checks (pure function tests)
# ---------------------------------------------------------------------------

class TestSingleNodeNet(unittest.TestCase):
    """single_node_net warns when a traced net has exactly one port."""

    def _make(self):
        _reset()
        c = _comp("U1")
        p_lone = _port(c["source_component_id"], "NC_PIN", "passive")
        t = _trace(p_lone["source_port_id"])
        return [p_lone], [t]

    def test_single_node_flagged(self):
        ports, traces = self._make()
        warnings = _check_single_node_net(ports, traces)
        kinds = [w["kind"] for w in warnings]
        self.assertIn("single_node_net", kinds)

    def test_single_node_has_port_id(self):
        ports, traces = self._make()
        warnings = _check_single_node_net(ports, traces)
        single = [w for w in warnings if w["kind"] == "single_node_net"]
        self.assertTrue(all("port_id" in w for w in single))

    def test_two_port_trace_not_flagged(self):
        _reset()
        c1 = _comp("U1"); c2 = _comp("U2")
        p1 = _port(c1["source_component_id"], "OUT", "output")
        p2 = _port(c2["source_component_id"], "IN",  "input")
        t = _trace(p1["source_port_id"], p2["source_port_id"])
        warnings = _check_single_node_net([p1, p2], [t])
        self.assertFalse(any(w["kind"] == "single_node_net" for w in warnings))

    def test_fixture_circuit_has_single_node_nets(self):
        """UART_TX and UART_RX in fixture are single-node → must be flagged."""
        port_list = [e for e in FIXTURE_CIRCUIT if isinstance(e, dict) and e.get("type") == "source_port"]
        trace_list = [e for e in FIXTURE_CIRCUIT if isinstance(e, dict) and e.get("type") == "source_trace"]
        warnings = _check_single_node_net(port_list, trace_list)
        self.assertGreaterEqual(len([w for w in warnings if w["kind"] == "single_node_net"]), 2)


class TestPowerPinNoDriver(unittest.TestCase):
    """power_pin_no_driver errors when a power_in pin has no power_out driver."""

    def test_unsourced_power_in_flagged(self):
        _reset()
        c = _comp("U1")
        p = _port(c["source_component_id"], "VDD", "power_in")
        t = _trace(p["source_port_id"])
        errors = _check_power_pin_no_driver([p], [t])
        kinds = [e["kind"] for e in errors]
        self.assertIn("power_pin_no_driver", kinds)

    def test_sourced_power_in_clean(self):
        _reset()
        c1 = _comp("U1")
        c2 = _comp("VR1")
        p_in  = _port(c1["source_component_id"], "VDD", "power_in")
        p_out = _port(c2["source_component_id"], "OUT", "power_out")
        t = _trace(p_in["source_port_id"], p_out["source_port_id"])
        errors = _check_power_pin_no_driver([p_in, p_out], [t])
        self.assertFalse(any(e["kind"] == "power_pin_no_driver" for e in errors))

    def test_error_has_required_fields(self):
        _reset()
        c = _comp("U1")
        p = _port(c["source_component_id"], "VDD", "power_in")
        t = _trace(p["source_port_id"])
        errors = _check_power_pin_no_driver([p], [t])
        for e in errors:
            self.assertIn("kind", e)
            self.assertIn("severity", e)
            self.assertEqual(e["severity"], "error")
            self.assertIn("message", e)
            self.assertIn("port_id", e)


class TestConflictingOutputs(unittest.TestCase):
    """conflicting_outputs errors when two+ output pins share a net."""

    def test_two_outputs_flagged(self):
        circuit = _make_conflict_circuit()
        port_list = [e for e in circuit if e.get("type") == "source_port"]
        trace_list = [e for e in circuit if e.get("type") == "source_trace"]
        errors = _check_conflicting_outputs(port_list, trace_list)
        kinds = [e["kind"] for e in errors]
        self.assertIn("conflicting_outputs", kinds)

    def test_conflicting_outputs_has_drivers_list(self):
        circuit = _make_conflict_circuit()
        port_list = [e for e in circuit if e.get("type") == "source_port"]
        trace_list = [e for e in circuit if e.get("type") == "source_trace"]
        errors = _check_conflicting_outputs(port_list, trace_list)
        conflict = next(e for e in errors if e["kind"] == "conflicting_outputs")
        self.assertIn("drivers", conflict)
        self.assertGreaterEqual(len(conflict["drivers"]), 2)

    def test_output_to_input_no_conflict(self):
        _reset()
        c1 = _comp("U1"); c2 = _comp("U2")
        p1 = _port(c1["source_component_id"], "OUT", "output")
        p2 = _port(c2["source_component_id"], "IN",  "input")
        t = _trace(p1["source_port_id"], p2["source_port_id"])
        errors = _check_conflicting_outputs([p1, p2], [t])
        self.assertFalse(any(e["kind"] == "conflicting_outputs" for e in errors))

    def test_open_collector_excluded(self):
        _reset()
        c1 = _comp("U1"); c2 = _comp("U2")
        p1 = _port(c1["source_component_id"], "OC1", "output",
                   electrical_function="open_collector")
        p2 = _port(c2["source_component_id"], "OC2", "output",
                   electrical_function="open_collector")
        t = _trace(p1["source_port_id"], p2["source_port_id"])
        errors = _check_conflicting_outputs([p1, p2], [t])
        self.assertFalse(any(e["kind"] == "conflicting_outputs" for e in errors))


# ---------------------------------------------------------------------------
# Extended ERC report engine
# ---------------------------------------------------------------------------

class TestRunErcExtended(unittest.TestCase):

    def setUp(self):
        self.result = _run_erc_extended(FIXTURE_CIRCUIT)

    def test_returns_errors_warnings_summary(self):
        for key in ("errors", "warnings", "summary"):
            self.assertIn(key, self.result)

    def test_summary_keys(self):
        s = self.result["summary"]
        for key in ("total_errors", "total_warnings", "checks_run"):
            self.assertIn(key, s)

    def test_checks_run_includes_extended(self):
        checks = self.result["summary"]["checks_run"]
        for check in ("single_node_net", "power_pin_no_driver", "conflicting_outputs"):
            self.assertIn(check, checks)

    def test_checks_run_includes_base(self):
        checks = self.result["summary"]["checks_run"]
        for check in ("unconnected_pin", "duplicate_refdes", "missing_power"):
            self.assertIn(check, checks)

    def test_single_node_net_warning_in_fixture(self):
        """UART_TX and UART_RX are single-node in the fixture."""
        kinds = [w["kind"] for w in self.result["warnings"]]
        self.assertIn("single_node_net", kinds)

    def test_deliberately_unconnected_pin_triggers_error(self):
        """A port not present in any trace triggers unconnected_pin error."""
        _reset()
        c = _comp("IC1")
        p1 = _port(c["source_component_id"], "A", "output")
        p2 = _port(c["source_component_id"], "B", "input")  # deliberately left unconnected
        t = _trace(p1["source_port_id"])  # only p1 is in a trace
        circuit = [c, p1, p2, t]
        result = _run_erc_extended(circuit)
        kinds = [e["kind"] for e in result["errors"]]
        self.assertIn("unconnected_pin", kinds,
                      "Deliberately unconnected pin B must trigger unconnected_pin error")

    def test_summary_totals_match_lists(self):
        s = self.result["summary"]
        self.assertEqual(s["total_errors"], len(self.result["errors"]))
        self.assertEqual(s["total_warnings"], len(self.result["warnings"]))

    def test_empty_circuit(self):
        r = _run_erc_extended([])
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["warnings"], [])
        self.assertIsInstance(r["summary"]["checks_run"], list)

    def test_all_error_entries_have_severity_error(self):
        for e in self.result["errors"]:
            self.assertEqual(e.get("severity"), "error", f"Entry missing severity=error: {e}")

    def test_all_warning_entries_have_severity_warning(self):
        for w in self.result["warnings"]:
            self.assertEqual(w.get("severity"), "warning", f"Entry missing severity=warning: {w}")


# ---------------------------------------------------------------------------
# LLM tool integration tests
# ---------------------------------------------------------------------------

class TestToolRegistration(unittest.IsolatedAsyncioTestCase):

    async def test_export_netlist_registered(self):
        from kerf_chat.tools.registry import Registry
        names = {t.spec.name for t in Registry}
        self.assertIn("export_netlist", names)

    async def test_erc_report_registered(self):
        from kerf_chat.tools.registry import Registry
        names = {t.spec.name for t in Registry}
        self.assertIn("erc_report", names)


class TestExportNetlistTool(unittest.IsolatedAsyncioTestCase):

    async def _run(self, payload: dict) -> dict:
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "export_netlist")
        raw = await tool.run(None, json.dumps(payload).encode())
        return json.loads(raw)

    async def test_kicad_format_returns_content(self):
        result = await self._run({"circuit_json": FIXTURE_CIRCUIT, "format": "kicad"})
        self.assertNotIn("error", result, result)
        self.assertIn("content_b64", result)
        text = base64.b64decode(result["content_b64"]).decode("utf-8")
        self.assertIn("(export", text)

    async def test_orcad_pads_format_returns_content(self):
        result = await self._run({"circuit_json": FIXTURE_CIRCUIT, "format": "orcad_pads"})
        self.assertNotIn("error", result, result)
        text = base64.b64decode(result["content_b64"]).decode("utf-8")
        self.assertIn("*PART*", text)
        self.assertIn("*NET*", text)
        self.assertIn("*END*", text)

    async def test_csv_format_returns_content(self):
        result = await self._run({"circuit_json": FIXTURE_CIRCUIT, "format": "csv"})
        self.assertNotIn("error", result, result)
        text = base64.b64decode(result["content_b64"]).decode("utf-8")
        self.assertTrue(text.startswith("net_name,refdes,pin,pin_type"))

    async def test_kicad_filename_extension(self):
        result = await self._run({"circuit_json": FIXTURE_CIRCUIT, "format": "kicad", "stem": "myboard"})
        self.assertEqual(result["filename"], "myboard.net")

    async def test_csv_filename_extension(self):
        result = await self._run({"circuit_json": FIXTURE_CIRCUIT, "format": "csv", "stem": "myboard"})
        self.assertEqual(result["filename"], "myboard.csv")

    async def test_invalid_format_returns_error(self):
        result = await self._run({"circuit_json": FIXTURE_CIRCUIT, "format": "eagle"})
        self.assertIn("error", result)

    async def test_non_array_circuit_json_returns_error(self):
        result = await self._run({"circuit_json": {}, "format": "csv"})
        self.assertIn("error", result)

    async def test_empty_circuit_all_formats(self):
        for fmt in ("kicad", "orcad_pads", "csv"):
            result = await self._run({"circuit_json": [], "format": fmt})
            self.assertNotIn("error", result, f"Format {fmt} failed on empty circuit: {result}")

    async def test_line_count_in_result(self):
        result = await self._run({"circuit_json": FIXTURE_CIRCUIT, "format": "kicad"})
        self.assertIn("line_count", result)
        self.assertGreater(result["line_count"], 0)

    async def test_preview_present(self):
        result = await self._run({"circuit_json": FIXTURE_CIRCUIT, "format": "kicad"})
        self.assertIn("preview", result)
        self.assertIsInstance(result["preview"], str)


class TestErcReportTool(unittest.IsolatedAsyncioTestCase):

    async def _run(self, circuit) -> dict:
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "erc_report")
        raw = await tool.run(None, json.dumps({"circuit_json": circuit}).encode())
        return json.loads(raw)

    async def test_returns_structured_report(self):
        result = await self._run(FIXTURE_CIRCUIT)
        self.assertNotIn("error", result, result)
        for key in ("errors", "warnings", "summary"):
            self.assertIn(key, result)

    async def test_summary_checks_run_present(self):
        result = await self._run(FIXTURE_CIRCUIT)
        self.assertIsInstance(result["summary"]["checks_run"], list)
        self.assertGreater(len(result["summary"]["checks_run"]), 5)

    async def test_single_node_net_flagged_via_tool(self):
        result = await self._run(FIXTURE_CIRCUIT)
        kinds = [w["kind"] for w in result["warnings"]]
        self.assertIn("single_node_net", kinds)

    async def test_deliberately_unconnected_pin_via_tool(self):
        """A deliberately-unconnected pin must appear in erc_report errors."""
        _reset()
        c = _comp("IC1")
        p1 = _port(c["source_component_id"], "A", "output")
        p2 = _port(c["source_component_id"], "UNCONNECTED", "input")
        t = _trace(p1["source_port_id"])
        circuit = [c, p1, p2, t]
        result = await self._run(circuit)
        kinds = [e["kind"] for e in result["errors"]]
        self.assertIn("unconnected_pin", kinds,
                      f"Expected unconnected_pin error. Got: {kinds}")

    async def test_non_array_circuit_json_returns_error(self):
        from kerf_chat.tools.registry import Registry
        tool = next(t for t in Registry if t.spec.name == "erc_report")
        raw = await tool.run(None, json.dumps({"circuit_json": "bad"}).encode())
        result = json.loads(raw)
        self.assertIn("error", result)

    async def test_empty_circuit_no_errors(self):
        result = await self._run([])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["warnings"], [])


if __name__ == "__main__":
    unittest.main()
