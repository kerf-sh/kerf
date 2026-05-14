"""test_erc.py — pytest suite for the ERC engine and LLM tool."""
import importlib.util
import sys
import unittest

# Load tools.erc directly (avoids triggering the full tools package init
# which requires a live DB/env config for unrelated modules).
_spec = importlib.util.spec_from_file_location(
    "tools.erc", "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-electronics/src/kerf_electronics/tools/erc.py"
)
_mod = importlib.util.module_from_spec(_spec)

# Stub the registry dependency so the @register decorator doesn't fail.
# Preserve any pre-existing real module so we don't poison sys.modules for
# other test files collected in the same session.
import types
_reg_stub = types.ModuleType("tools.registry")
_reg_stub.ToolSpec   = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: __import__("json").dumps({"error": msg, "code": code})
_reg_stub.ok_payload  = lambda v: __import__("json").dumps(v)
_reg_stub.register    = lambda spec, write=False: (lambda fn: fn)
_prev_registry = sys.modules.get("tools.registry")
sys.modules["tools.registry"] = _reg_stub

_spec.loader.exec_module(_mod)
_run_erc = _mod._run_erc

# Restore the real tools.registry (or remove the stub) so subsequent imports
# in other test files see the proper module.
if _prev_registry is not None:
    sys.modules["tools.registry"] = _prev_registry
else:
    del sys.modules["tools.registry"]


# ---------------------------------------------------------------------------
# Minimal builders
# ---------------------------------------------------------------------------

_cid = _pid = _tid = _nid = 0


def _reset():
    global _cid, _pid, _tid, _nid
    _cid = _pid = _tid = _nid = 0


def _comp(name, **kw):
    global _cid
    _cid += 1
    return {"type": "source_component", "source_component_id": f"c{_cid}", "name": name, **kw}


def _port(comp_id, name, pin_type="passive", **kw):
    global _pid
    _pid += 1
    return {"type": "source_port", "source_port_id": f"p{_pid}",
            "source_component_id": comp_id, "name": name, "pin_type": pin_type, **kw}


def _trace(*port_ids, net_ids=None):
    global _tid
    _tid += 1
    e = {"type": "source_trace", "source_trace_id": f"t{_tid}",
         "connected_source_port_ids": list(port_ids)}
    if net_ids:
        e["connected_source_net_ids"] = net_ids
    return e


def _net(name, **kw):
    global _nid
    _nid += 1
    return {"type": "source_net", "source_net_id": f"n{_nid}", "name": name, **kw}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestErcEmpty(unittest.TestCase):
    def test_empty_circuit(self):
        r = _run_erc([])
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["warnings"], [])

    def test_none_style_elements_skipped(self):
        r = _run_erc([None, {"type": "other"}])
        self.assertEqual(r["errors"], [])


class TestUnconnectedPin(unittest.TestCase):
    def setUp(self): _reset()

    def test_unconnected_port_flagged(self):
        c  = _comp("R1")
        p1 = _port(c["source_component_id"], "pin1")
        p2 = _port(c["source_component_id"], "pin2")
        t  = _trace(p1["source_port_id"])        # p2 has no trace
        r  = _run_erc([c, p1, p2, t])
        kinds = [e["kind"] for e in r["errors"]]
        self.assertIn("unconnected_pin", kinds)

    def test_connected_port_clean(self):
        c  = _comp("R1")
        p1 = _port(c["source_component_id"], "pin1")
        p2 = _port(c["source_component_id"], "pin2")
        t  = _trace(p1["source_port_id"], p2["source_port_id"])
        r  = _run_erc([c, p1, p2, t])
        self.assertFalse(any(e["kind"] == "unconnected_pin" for e in r["errors"]))


class TestDuplicateRefdes(unittest.TestCase):
    def setUp(self): _reset()

    def test_duplicate_flagged(self):
        c1 = _comp("U1")
        c2 = _comp("U1")
        r  = _run_erc([c1, c2])
        self.assertTrue(any(e["kind"] == "duplicate_refdes" for e in r["errors"]))

    def test_unique_refdes_clean(self):
        c1 = _comp("U1")
        c2 = _comp("U2")
        r  = _run_erc([c1, c2])
        self.assertFalse(any(e["kind"] == "duplicate_refdes" for e in r["errors"]))


class TestConflictingNetLabel(unittest.TestCase):
    def setUp(self): _reset()

    def test_merged_nets_with_different_names(self):
        n1 = _net("VCC")
        n2 = _net("GND")
        t  = _trace(net_ids=[n1["source_net_id"], n2["source_net_id"]])
        r  = _run_erc([n1, n2, t])
        self.assertTrue(any(e["kind"] == "conflicting_net_label" for e in r["errors"]))

    def test_separate_nets_clean(self):
        n1 = _net("VCC")
        n2 = _net("GND")
        r  = _run_erc([n1, n2])
        self.assertFalse(any(e["kind"] == "conflicting_net_label" for e in r["errors"]))


class TestOutputToOutput(unittest.TestCase):
    def setUp(self): _reset()

    def test_two_outputs_tied(self):
        c1 = _comp("U1"); c2 = _comp("U2")
        p1 = _port(c1["source_component_id"], "OUT", "output")
        p2 = _port(c2["source_component_id"], "OUT", "output")
        t  = _trace(p1["source_port_id"], p2["source_port_id"])
        r  = _run_erc([c1, c2, p1, p2, t])
        self.assertTrue(any(e["kind"] == "output_to_output" for e in r["errors"]))

    def test_open_collector_excluded(self):
        c1 = _comp("U1"); c2 = _comp("U2")
        p1 = _port(c1["source_component_id"], "OC1", "output", electrical_function="open_collector")
        p2 = _port(c2["source_component_id"], "OC2", "output", electrical_function="open_collector")
        t  = _trace(p1["source_port_id"], p2["source_port_id"])
        r  = _run_erc([c1, c2, p1, p2, t])
        self.assertFalse(any(e["kind"] == "output_to_output" for e in r["errors"]))

    def test_output_to_input_clean(self):
        c1 = _comp("U1"); c2 = _comp("U2")
        p1 = _port(c1["source_component_id"], "OUT", "output")
        p2 = _port(c2["source_component_id"], "IN",  "input")
        t  = _trace(p1["source_port_id"], p2["source_port_id"])
        r  = _run_erc([c1, c2, p1, p2, t])
        self.assertFalse(any(e["kind"] == "output_to_output" for e in r["errors"]))


class TestMissingPower(unittest.TestCase):
    def setUp(self): _reset()

    def test_vcc_unsourced(self):
        n = _net("VCC", is_power=True)
        r = _run_erc([n])
        self.assertTrue(any(e["kind"] == "missing_power" for e in r["errors"]))

    def test_gnd_by_name_convention(self):
        n = _net("GND")
        r = _run_erc([n])
        self.assertTrue(any(e["kind"] == "missing_power" for e in r["errors"]))

    def test_sourced_power_net_clean(self):
        n  = _net("VCC", is_power=True)
        c  = _comp("PWR1")
        p  = _port(c["source_component_id"], "OUT", "power", source_net_id=n["source_net_id"])
        r  = _run_erc([n, c, p])
        self.assertFalse(any(e["kind"] == "missing_power" for e in r["errors"]))


class TestPinDirectionMismatch(unittest.TestCase):
    def setUp(self): _reset()

    def test_two_inputs_no_driver(self):
        c1 = _comp("U1"); c2 = _comp("U2")
        p1 = _port(c1["source_component_id"], "IN1", "input")
        p2 = _port(c2["source_component_id"], "IN2", "input")
        t  = _trace(p1["source_port_id"], p2["source_port_id"])
        r  = _run_erc([c1, c2, p1, p2, t])
        self.assertTrue(any(w["kind"] == "pin_direction_mismatch" for w in r["warnings"]))

    def test_with_driver_no_warning(self):
        c1 = _comp("U1"); c2 = _comp("U2"); c3 = _comp("U3")
        p1 = _port(c1["source_component_id"], "IN1", "input")
        p2 = _port(c2["source_component_id"], "IN2", "input")
        p3 = _port(c3["source_component_id"], "OUT", "output")
        t  = _trace(p1["source_port_id"], p2["source_port_id"], p3["source_port_id"])
        r  = _run_erc([c1, c2, c3, p1, p2, p3, t])
        self.assertFalse(any(w["kind"] == "pin_direction_mismatch" for w in r["warnings"]))


class TestFloatingNet(unittest.TestCase):
    def setUp(self): _reset()

    def test_single_port_trace_is_floating(self):
        c = _comp("R1")
        p = _port(c["source_component_id"], "pin1")
        t = _trace(p["source_port_id"])
        r = _run_erc([c, p, t])
        self.assertTrue(any(w["kind"] == "floating_net" for w in r["warnings"]))

    def test_two_port_trace_not_floating(self):
        c1 = _comp("R1"); c2 = _comp("R2")
        p1 = _port(c1["source_component_id"], "pin1")
        p2 = _port(c2["source_component_id"], "pin1")
        t  = _trace(p1["source_port_id"], p2["source_port_id"])
        r  = _run_erc([c1, c2, p1, p2, t])
        self.assertFalse(any(w["kind"] == "floating_net" for w in r["warnings"]))


class TestBidirectionalPromiscuity(unittest.TestCase):
    def setUp(self): _reset()

    def test_four_bidir_ports_warns(self):
        elements = []
        pids = []
        for i in range(1, 5):
            c = _comp(f"U{i}")
            p = _port(c["source_component_id"], f"SDA{i}", "bidirectional")
            elements += [c, p]
            pids.append(p["source_port_id"])
        t = _trace(*pids)
        r = _run_erc(elements + [t])
        self.assertTrue(any(w["kind"] == "bidirectional_promiscuity" for w in r["warnings"]))

    def test_three_bidir_ports_clean(self):
        elements = []
        pids = []
        for i in range(1, 4):
            c = _comp(f"U{i}")
            p = _port(c["source_component_id"], f"SDA{i}", "bidirectional")
            elements += [c, p]
            pids.append(p["source_port_id"])
        t = _trace(*pids)
        r = _run_erc(elements + [t])
        self.assertFalse(any(w["kind"] == "bidirectional_promiscuity" for w in r["warnings"]))


class TestSeverityField(unittest.TestCase):
    def setUp(self): _reset()

    def test_all_errors_have_severity_error(self):
        c1 = _comp("U1"); c2 = _comp("U1")   # duplicate
        r = _run_erc([c1, c2])
        self.assertTrue(all(e["severity"] == "error" for e in r["errors"]))

    def test_all_warnings_have_severity_warning(self):
        c1 = _comp("U1"); c2 = _comp("U2")
        p1 = _port(c1["source_component_id"], "IN1", "input")
        p2 = _port(c2["source_component_id"], "IN2", "input")
        t  = _trace(p1["source_port_id"], p2["source_port_id"])
        r  = _run_erc([c1, c2, p1, p2, t])
        self.assertTrue(all(w["severity"] == "warning" for w in r["warnings"]))


if __name__ == "__main__":
    unittest.main()
