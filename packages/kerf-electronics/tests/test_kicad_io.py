"""test_kicad_io.py — pytest suite for the KiCad ↔ Circuit-JSON bridge.

Tests are fully hermetic: no network, no disk I/O beyond loading the JSON
fixture, no optional dependencies.

Coverage:
  - S-expression lexer: tokenise, parse, balanced parens
  - circuit_json_to_kicad_pcb: layers, nets, footprints, segments
  - circuit_json_to_kicad_sch: header, symbols, wires, labels
  - kicad_pcb_to_circuit_json: nets, components, traces recovered
  - Round-trip oracle (fixture → kicad_pcb → circuit_json):
      * source_component count preserved (2)
      * net count preserved (≥ 3)
      * footprint refs R1 and R2 present
"""

from __future__ import annotations

import json
import os
import unittest

from kerf_electronics.kicad_io import (
    _tokenize,
    _parse_sexpr,
    circuit_json_to_kicad_pcb,
    circuit_json_to_kicad_sch,
    kicad_pcb_to_circuit_json,
)

# ─── Fixture ──────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIXTURE_PATH = os.path.join(_HERE, "fixtures", "two_resistors_circuit.json")

with open(_FIXTURE_PATH, encoding="utf-8") as _f:
    FIXTURE: list = json.load(_f)


# ─── Lexer tests ──────────────────────────────────────────────────────────────

class TestTokenize(unittest.TestCase):

    def test_empty_string(self):
        self.assertEqual(_tokenize(""), [])

    def test_parens(self):
        self.assertEqual(_tokenize("()"), ["(", ")"])

    def test_bare_atoms(self):
        tokens = _tokenize("(kicad_pcb version 1)")
        self.assertEqual(tokens, ["(", "kicad_pcb", "version", "1", ")"])

    def test_quoted_string(self):
        tokens = _tokenize('(name "hello world")')
        self.assertIn('"hello world"', tokens)

    def test_escaped_quote_in_string(self):
        tokens = _tokenize(r'(x "a\"b")')
        # The atom for the quoted string should contain the raw inner text
        quoted = [t for t in tokens if t.startswith('"')]
        self.assertEqual(len(quoted), 1)
        self.assertIn("a", quoted[0])

    def test_nested(self):
        tokens = _tokenize("(a (b c) d)")
        self.assertEqual(tokens.count("("), 2)
        self.assertEqual(tokens.count(")"), 2)


class TestParseSexpr(unittest.TestCase):

    def test_simple_list(self):
        node = _parse_sexpr("(kicad_pcb)")
        self.assertIsInstance(node, list)
        self.assertEqual(node[0], "kicad_pcb")

    def test_nested_list(self):
        node = _parse_sexpr("(a (b c))")
        self.assertEqual(node[0], "a")
        self.assertIsInstance(node[1], list)
        self.assertEqual(node[1][0], "b")

    def test_quoted_value(self):
        node = _parse_sexpr('(ref "R1")')
        self.assertEqual(node[1], "R1")

    def test_empty_input(self):
        result = _parse_sexpr("")
        self.assertFalse(result)

    def test_parens_balanced(self):
        """Parse then re-render: paren count must balance."""
        text = circuit_json_to_kicad_pcb(FIXTURE)
        self.assertEqual(text.count("("), text.count(")"))


# ─── circuit_json_to_kicad_pcb tests ─────────────────────────────────────────

class TestCircuitJsonToKicadPcb(unittest.TestCase):

    def setUp(self):
        self.text = circuit_json_to_kicad_pcb(FIXTURE)

    def test_returns_string(self):
        self.assertIsInstance(self.text, str)

    def test_non_empty(self):
        self.assertGreater(len(self.text), 0)

    def test_starts_with_kicad_pcb(self):
        self.assertTrue(self.text.strip().startswith("(kicad_pcb"))

    def test_version_field(self):
        self.assertIn("version 20211014", self.text)

    def test_generator_field(self):
        self.assertIn("kerf_electronics", self.text)

    def test_layers_section_present(self):
        self.assertIn("(layers", self.text)

    def test_fcu_layer_present(self):
        self.assertIn("F.Cu", self.text)

    def test_bcu_layer_present(self):
        self.assertIn("B.Cu", self.text)

    def test_edge_cuts_layer_present(self):
        self.assertIn("Edge.Cuts", self.text)

    def test_net_section_present(self):
        self.assertIn("(net", self.text)

    def test_vcc_net_present(self):
        self.assertIn("VCC", self.text)

    def test_gnd_net_present(self):
        self.assertIn("GND", self.text)

    def test_mid_net_present(self):
        self.assertIn("MID", self.text)

    def test_footprint_section_present(self):
        self.assertIn("(footprint", self.text)

    def test_r1_ref_present(self):
        self.assertIn("R1", self.text)

    def test_r2_ref_present(self):
        self.assertIn("R2", self.text)

    def test_r0402_footprint_present(self):
        self.assertIn("R_0402", self.text)

    def test_segment_present(self):
        self.assertIn("(segment", self.text)

    def test_balanced_parens(self):
        self.assertEqual(self.text.count("("), self.text.count(")"))

    def test_empty_circuit_safe(self):
        text = circuit_json_to_kicad_pcb([])
        self.assertIsInstance(text, str)
        self.assertIn("kicad_pcb", text)
        self.assertEqual(text.count("("), text.count(")"))

    def test_none_circuit_safe(self):
        text = circuit_json_to_kicad_pcb(None)  # type: ignore[arg-type]
        self.assertIsInstance(text, str)


# ─── circuit_json_to_kicad_sch tests ─────────────────────────────────────────

class TestCircuitJsonToKicadSch(unittest.TestCase):

    def setUp(self):
        self.text = circuit_json_to_kicad_sch(FIXTURE)

    def test_returns_string(self):
        self.assertIsInstance(self.text, str)

    def test_non_empty(self):
        self.assertGreater(len(self.text), 0)

    def test_starts_with_kicad_sch(self):
        self.assertTrue(self.text.strip().startswith("(kicad_sch"))

    def test_version_field(self):
        self.assertIn("version 20211123", self.text)

    def test_generator_field(self):
        self.assertIn("kerf_electronics", self.text)

    def test_lib_symbols_section(self):
        self.assertIn("(lib_symbols", self.text)

    def test_r1_ref_in_sch(self):
        self.assertIn("R1", self.text)

    def test_r2_ref_in_sch(self):
        self.assertIn("R2", self.text)

    def test_resistor_value_in_sch(self):
        self.assertIn("10k", self.text)

    def test_label_for_vcc(self):
        self.assertIn("VCC", self.text)

    def test_label_for_gnd(self):
        self.assertIn("GND", self.text)

    def test_balanced_parens(self):
        self.assertEqual(self.text.count("("), self.text.count(")"))

    def test_empty_circuit_safe(self):
        text = circuit_json_to_kicad_sch([])
        self.assertIsInstance(text, str)
        self.assertIn("kicad_sch", text)
        self.assertEqual(text.count("("), text.count(")"))


# ─── kicad_pcb_to_circuit_json tests ─────────────────────────────────────────

class TestKicadPcbToCircuitJson(unittest.TestCase):

    def setUp(self):
        self.pcb_text = circuit_json_to_kicad_pcb(FIXTURE)
        self.recovered = kicad_pcb_to_circuit_json(self.pcb_text)

    def test_returns_list(self):
        self.assertIsInstance(self.recovered, list)

    def test_non_empty(self):
        self.assertGreater(len(self.recovered), 0)

    def test_has_source_component_entries(self):
        comps = [e for e in self.recovered if e.get("type") == "source_component"]
        self.assertGreater(len(comps), 0)

    def test_has_pcb_component_entries(self):
        pcbs = [e for e in self.recovered if e.get("type") == "pcb_component"]
        self.assertGreater(len(pcbs), 0)

    def test_has_source_net_entries(self):
        nets = [e for e in self.recovered if e.get("type") == "source_net"]
        self.assertGreater(len(nets), 0)

    def test_net_vcc_recovered(self):
        nets = [e for e in self.recovered if e.get("type") == "source_net"]
        names = {n["name"] for n in nets}
        self.assertIn("VCC", names)

    def test_net_gnd_recovered(self):
        nets = [e for e in self.recovered if e.get("type") == "source_net"]
        names = {n["name"] for n in nets}
        self.assertIn("GND", names)

    def test_empty_string_safe(self):
        result = kicad_pcb_to_circuit_json("")
        self.assertIsInstance(result, list)

    def test_malformed_input_safe(self):
        result = kicad_pcb_to_circuit_json("(kicad_pcb (net 1 )")
        self.assertIsInstance(result, list)


# ─── Round-trip oracle ────────────────────────────────────────────────────────

class TestRoundTrip(unittest.TestCase):
    """Fixture → kicad_pcb → circuit_json: key properties preserved."""

    @classmethod
    def setUpClass(cls):
        cls.pcb_text  = circuit_json_to_kicad_pcb(FIXTURE)
        cls.recovered = kicad_pcb_to_circuit_json(cls.pcb_text)

    # ── source_component count ────────────────────────────────────────────────

    def test_two_source_components_preserved(self):
        """There must be exactly 2 source_component entries (R1, R2)."""
        comps = [e for e in self.recovered if e.get("type") == "source_component"]
        self.assertEqual(len(comps), 2,
                         f"Expected 2 source_components; got {len(comps)}: "
                         f"{[c.get('name') for c in comps]}")

    # ── net count ─────────────────────────────────────────────────────────────

    def test_at_least_three_nets_preserved(self):
        """VCC, MID, GND — at least 3 nets must be recovered."""
        nets = [e for e in self.recovered if e.get("type") == "source_net"]
        self.assertGreaterEqual(len(nets), 3,
                                f"Expected ≥ 3 nets; got {len(nets)}: "
                                f"{[n.get('name') for n in nets]}")

    # ── footprint refs ────────────────────────────────────────────────────────

    def test_r1_footprint_ref_preserved(self):
        """R1 must appear as a source_component name."""
        comps = [e for e in self.recovered if e.get("type") == "source_component"]
        refs = {c.get("name") for c in comps}
        self.assertIn("R1", refs, f"R1 not in recovered refs: {refs}")

    def test_r2_footprint_ref_preserved(self):
        """R2 must appear as a source_component name."""
        comps = [e for e in self.recovered if e.get("type") == "source_component"]
        refs = {c.get("name") for c in comps}
        self.assertIn("R2", refs, f"R2 not in recovered refs: {refs}")

    # ── position data ─────────────────────────────────────────────────────────

    def test_pcb_component_positions_preserved(self):
        """Positions from the fixture must survive the round-trip."""
        pcbs = [e for e in self.recovered if e.get("type") == "pcb_component"]
        xs = {p["x"] for p in pcbs}
        # Fixture has x=10.0 and x=35.0
        self.assertIn(10.0, xs, f"x=10.0 not found; got: {xs}")
        self.assertIn(35.0, xs, f"x=35.0 not found; got: {xs}")

    # ── layer mapping ─────────────────────────────────────────────────────────

    def test_top_copper_layer_preserved(self):
        """Components on top_copper must be recovered with top_copper layer."""
        pcbs = [e for e in self.recovered if e.get("type") == "pcb_component"]
        layers = {p.get("layer") for p in pcbs}
        self.assertIn("top_copper", layers, f"top_copper not in recovered layers: {layers}")

    # ── trace recovery ────────────────────────────────────────────────────────

    def test_pcb_trace_recovered(self):
        """At least one pcb_trace or source_trace must be recovered."""
        traces = [e for e in self.recovered
                  if e.get("type") in ("pcb_trace", "source_trace")]
        self.assertGreater(len(traces), 0,
                           "No traces recovered from round-trip")

    # ── footprint name preserved ──────────────────────────────────────────────

    def test_r0402_footprint_name_preserved(self):
        """R_0402 footprint name must survive the round-trip."""
        comps = [e for e in self.recovered if e.get("type") == "source_component"]
        footprints = {c.get("footprint") for c in comps}
        self.assertIn("R_0402", footprints,
                      f"R_0402 not in recovered footprints: {footprints}")


if __name__ == "__main__":
    unittest.main()
