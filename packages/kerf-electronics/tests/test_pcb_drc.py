"""
Tests for kerf_electronics/tools/pcb_drc.py — run_pcb_drc and set_drc_rule tools.
"""
import json
import unittest

from kerf_electronics.tools.pcb_drc import _run_drc_on_circuit, _DEFAULT_RULES
from tools.registry import Registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_board(**kw):
    return {"type": "pcb_board", "width": 50, "height": 50, **kw}


def make_trace(tid, width, points):
    return {
        "type": "pcb_trace",
        "pcb_trace_id": tid,
        "route_thickness_mm": width,
        "route": [{"x": x, "y": y} for x, y in points],
    }


def make_via(vid, x, y, outer=0.6, drill=0.3):
    return {
        "type": "pcb_via",
        "pcb_via_id": vid,
        "x": x,
        "y": y,
        "outer_diameter": outer,
        "hole_diameter": drill,
    }


def make_pad(pid, x, y, w=1.5, h=1.5, net=None):
    p = {"type": "pcb_smtpad", "pcb_smtpad_id": pid, "x": x, "y": y, "width": w, "height": h}
    if net:
        p["net_id"] = net
    return p


def make_silk(x, y):
    return {"type": "pcb_silkscreen_text", "x": x, "y": y, "text": "REF1"}


async def call_tool(name, payload):
    from tools.registry import Registry
    tool = next(t for t in Registry if t.spec.name == name)
    return json.loads(await tool.run(None, json.dumps(payload).encode()))


# ---------------------------------------------------------------------------
# Tests: _run_drc_on_circuit (unit-level, no async)
# ---------------------------------------------------------------------------

class TestDRCEngine(unittest.TestCase):

    def test_empty_circuit_returns_no_violations(self):
        r = _run_drc_on_circuit([])
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["warnings"], [])

    def test_non_list_circuit_returns_no_violations(self):
        r = _run_drc_on_circuit(None)
        self.assertEqual(r["errors"], [])

    # -- trace width --

    def test_trace_width_below_min_is_error(self):
        circuit = [make_board(), make_trace("t1", 0.10, [(5, 5), (10, 5)])]
        r = _run_drc_on_circuit(circuit)
        kinds = [e["kind"] for e in r["errors"]]
        self.assertIn("trace_too_narrow", kinds)

    def test_trace_width_at_min_is_ok(self):
        circuit = [make_board(), make_trace("t1", _DEFAULT_RULES["min_trace_width_mm"], [(5, 5), (10, 5)])]
        r = _run_drc_on_circuit(circuit)
        self.assertFalse(any(e["kind"] == "trace_too_narrow" for e in r["errors"]))

    def test_custom_min_trace_width_respected(self):
        circuit = [
            make_board(drc_rules={"min_trace_width_mm": 0.08}),
            make_trace("t1", 0.10, [(5, 5), (10, 5)]),  # 0.10 >= 0.08 → ok
        ]
        r = _run_drc_on_circuit(circuit)
        self.assertFalse(any(e["kind"] == "trace_too_narrow" for e in r["errors"]))

    # -- via clearance --

    def test_vias_too_close_is_error(self):
        circuit = [make_board(), make_via("v1", 0, 0, 0.6, 0.3), make_via("v2", 0.4, 0, 0.6, 0.3)]
        r = _run_drc_on_circuit(circuit)
        self.assertTrue(any(e["kind"] == "via_clearance" for e in r["errors"]))

    def test_vias_far_apart_no_error(self):
        circuit = [make_board(), make_via("v1", 0, 0), make_via("v2", 5, 0)]
        r = _run_drc_on_circuit(circuit)
        self.assertFalse(any(e["kind"] == "via_clearance" for e in r["errors"]))

    # -- drill spacing --

    def test_drills_overlapping_is_error(self):
        circuit = [make_board(), make_via("v1", 0, 0, 0.6, 0.3), make_via("v2", 0.2, 0, 0.6, 0.3)]
        r = _run_drc_on_circuit(circuit)
        self.assertTrue(any(e["kind"] == "drill_spacing" for e in r["errors"]))

    # -- silk on pad --

    def test_silk_on_pad_center_is_warning(self):
        circuit = [make_board(), make_pad("p1", 5, 5, 2, 2), make_silk(5, 5)]
        r = _run_drc_on_circuit(circuit)
        self.assertTrue(any(w["kind"] == "silk_on_pad" for w in r["warnings"]))

    def test_silk_far_from_pad_no_warning(self):
        circuit = [make_board(), make_pad("p1", 0, 0, 1, 1), make_silk(10, 10)]
        r = _run_drc_on_circuit(circuit)
        self.assertFalse(any(w["kind"] == "silk_on_pad" for w in r["warnings"]))

    # -- copper to edge --

    def test_trace_too_close_to_edge_is_warning(self):
        circuit = [make_board(), make_trace("t1", 0.2, [(0.1, 25), (5, 25)])]
        r = _run_drc_on_circuit(circuit)
        self.assertTrue(any(w["kind"] == "copper_to_edge" for w in r["warnings"]))

    def test_trace_safely_inside_no_edge_warning(self):
        circuit = [make_board(), make_trace("t1", 0.2, [(5, 5), (45, 5)])]
        r = _run_drc_on_circuit(circuit)
        self.assertFalse(any(w["kind"] == "copper_to_edge" for w in r["warnings"]))

    # -- dangling trace --

    def test_trace_both_ends_unconnected_is_dangling(self):
        circuit = [make_board(), make_trace("t1", 0.2, [(5, 5), (10, 5)])]
        r = _run_drc_on_circuit(circuit)
        self.assertTrue(any(e["kind"] == "dangling_trace" for e in r["errors"]))

    def test_trace_connecting_two_pads_not_dangling(self):
        circuit = [
            make_board(),
            make_pad("p1", 0, 0),
            make_pad("p2", 10, 0),
            make_trace("t1", 0.2, [(0, 0), (10, 0)]),
        ]
        r = _run_drc_on_circuit(circuit)
        self.assertFalse(any(e["kind"] == "dangling_trace" for e in r["errors"]))

    # -- net short --

    def test_cross_net_trace_is_short(self):
        circuit = [
            make_board(),
            make_pad("p1", 0, 0, net="VCC"),
            make_pad("p2", 10, 0, net="GND"),
            make_trace("t1", 0.2, [(0, 0), (10, 0)]),
        ]
        r = _run_drc_on_circuit(circuit)
        self.assertTrue(any(e["kind"] == "net_short" for e in r["errors"]))
        short_msg = next(e["message"] for e in r["errors"] if e["kind"] == "net_short")
        self.assertIn("GND", short_msg)
        self.assertIn("VCC", short_msg)

    def test_same_net_trace_no_short(self):
        circuit = [
            make_board(),
            make_pad("p1", 0, 0, net="GND"),
            make_pad("p2", 10, 0, net="GND"),
            make_trace("t1", 0.2, [(0, 0), (10, 0)]),
        ]
        r = _run_drc_on_circuit(circuit)
        self.assertFalse(any(e["kind"] == "net_short" for e in r["errors"]))


# ---------------------------------------------------------------------------
# Tests: run_pcb_drc tool (async)
# ---------------------------------------------------------------------------

class TestRunPcbDrcTool(unittest.IsolatedAsyncioTestCase):

    async def test_tool_registered(self):
        names = [t.spec.name for t in Registry]
        self.assertIn("run_pcb_drc", names)
        self.assertIn("set_drc_rule", names)

    async def test_tool_returns_summary(self):
        payload = {
            "circuit_json": [
                make_board(),
                make_trace("t1", 0.10, [(5, 5), (10, 5)]),
            ]
        }
        result = await call_tool("run_pcb_drc", payload)
        self.assertIn("errors", result)
        self.assertIn("warnings", result)
        self.assertIn("summary", result)
        self.assertIsInstance(result["summary"]["error_count"], int)
        self.assertIsInstance(result["summary"]["warning_count"], int)

    async def test_tool_bad_args_returns_error(self):
        result = await call_tool("run_pcb_drc", {"circuit_json": "not-a-list"})
        self.assertIn("error", result)

    async def test_set_drc_rule_updates_board(self):
        circuit = [make_board()]
        result = await call_tool("set_drc_rule", {
            "circuit_json": circuit,
            "rule_name": "min_trace_width_mm",
            "value": 0.25,
        })
        self.assertIn("circuit_json", result)
        board = next(e for e in result["circuit_json"] if e["type"] == "pcb_board")
        self.assertEqual(board["drc_rules"]["min_trace_width_mm"], 0.25)

    async def test_set_drc_rule_invalid_name(self):
        result = await call_tool("set_drc_rule", {
            "circuit_json": [make_board()],
            "rule_name": "nonexistent_rule",
            "value": 0.5,
        })
        self.assertIn("error", result)

    async def test_set_drc_rule_negative_value_rejected(self):
        result = await call_tool("set_drc_rule", {
            "circuit_json": [make_board()],
            "rule_name": "min_trace_width_mm",
            "value": -0.1,
        })
        self.assertIn("error", result)

    async def test_set_drc_rule_creates_board_if_missing(self):
        result = await call_tool("set_drc_rule", {
            "circuit_json": [],
            "rule_name": "min_trace_width_mm",
            "value": 0.20,
        })
        boards = [e for e in result["circuit_json"] if e["type"] == "pcb_board"]
        self.assertEqual(len(boards), 1)
        self.assertEqual(boards[0]["drc_rules"]["min_trace_width_mm"], 0.20)


if __name__ == "__main__":
    unittest.main()
