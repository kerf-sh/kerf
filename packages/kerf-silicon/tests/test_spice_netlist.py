"""
test_spice_netlist.py — tests for kerf_silicon.bridges.spice_netlist.

Test inventory
--------------
1.  test_mosfet_nmos_line             — NMOS element line format
2.  test_mosfet_pmos_line             — PMOS element line format
3.  test_mosfet_default_dimensions    — default W/L values (500n / 1000n, 130n)
4.  test_vdc_line                     — DC voltage source format
5.  test_vpulse_line                  — PULSE source format
6.  test_cap_line                     — capacitor format
7.  test_res_line                     — resistor format
8.  test_build_transient_deck_minimal — deck has title + .TRAN + .end
9.  test_build_transient_deck_probes  — .PRINT line injected when probes given
10. test_build_transient_deck_models  — model lines injected before .TRAN
11. test_build_dc_deck_minimal        — DC deck has .DC directive + .end
12. test_parse_ngspice_output_basic   — two-column parse → dict with time key
13. test_parse_ngspice_output_three_cols — three-column table parsed correctly
14. test_parse_ngspice_output_empty   — empty string → empty dict
15. test_parse_ngspice_output_noise   — lines with warnings/notes skipped
16. test_is_valid_spice_deck_valid    — well-formed deck passes
17. test_is_valid_spice_deck_no_analysis — deck without .TRAN/.DC fails
18. test_is_valid_spice_deck_no_end   — deck without .end fails
19. test_is_valid_spice_deck_empty    — empty string fails
20. test_has_subckt_true              — .SUBCKT detected
21. test_has_subckt_false             — no .SUBCKT returns False
22. test_has_model_true               — .MODEL detected
23. test_has_model_false              — no .MODEL returns False
24. test_extract_probe_nodes          — .PRINT nodes extracted
25. test_fixture_inverter_valid       — inverter.cir passes is_valid_spice_deck
26. test_fixture_inverter_has_model   — inverter.cir has .MODEL directives
27. test_fixture_inverter_has_transient — inverter.cir has .TRAN directive
28. test_fixture_nand2_valid          — nand2.cir passes is_valid_spice_deck
29. test_fixture_nand2_has_model      — nand2.cir has .MODEL directives
30. test_fixture_nand2_has_transient  — nand2.cir has .TRAN directive
31. test_fixture_nand2_four_mosfets   — nand2.cir contains four M lines
32. test_fixture_inverter_print_nodes — .PRINT V(vin) and V(vout) present
"""

import os
import re
import math

import pytest

from kerf_silicon.bridges.spice_netlist import (
    mosfet_nmos,
    mosfet_pmos,
    vdc,
    vpulse,
    cap,
    res,
    build_transient_deck,
    build_dc_deck,
    parse_ngspice_output,
    is_valid_spice_deck,
    has_subckt,
    has_model,
    extract_probe_nodes,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_INVERTER = os.path.join(_FIXTURES, "inverter.cir")
_NAND2 = os.path.join(_FIXTURES, "nand2.cir")


# ---------------------------------------------------------------------------
# 1–7. Element line helpers
# ---------------------------------------------------------------------------

def test_mosfet_nmos_line():
    line = mosfet_nmos("n1", "vout", "vin", "0", "0", "NMOS_130N")
    assert line.startswith("Mn1")
    assert "NMOS_130N" in line
    assert "W=" in line
    assert "L=" in line


def test_mosfet_pmos_line():
    line = mosfet_pmos("p1", "vout", "vin", "vdd", "vdd", "PMOS_130N")
    assert line.startswith("Mp1")
    assert "PMOS_130N" in line
    assert "W=" in line and "L=" in line


def test_mosfet_default_dimensions():
    nmos_line = mosfet_nmos("n1", "d", "g", "s", "b", "NMOS")
    assert "W=500n" in nmos_line
    assert "L=130n" in nmos_line

    pmos_line = mosfet_pmos("p1", "d", "g", "s", "b", "PMOS")
    assert "W=1000n" in pmos_line
    assert "L=130n" in pmos_line


def test_mosfet_custom_dimensions():
    line = mosfet_nmos("n2", "d", "g", "s", "b", "NMOS", W_nm=800, L_nm=180)
    assert "W=800n" in line
    assert "L=180n" in line


def test_vdc_line():
    line = vdc("dd", "vdd", "0", 1.8)
    assert line.startswith("Vdd")
    assert "DC" in line
    assert "1.8" in line


def test_vpulse_line():
    line = vpulse("in", "vin", "0", 0.0, 1.8, 1.0, 0.1, 0.1, 9.9, 20.0)
    assert line.startswith("Vin")
    assert "PULSE" in line
    assert "1.8" in line
    # All times should have 'n' suffix
    assert "1n" in line or "1.0n" in line


def test_cap_line():
    line = cap("load", "vout", "0", 10e-15)
    assert line.startswith("Cload")
    assert "vout" in line
    # Value should be formatted as a float
    assert re.search(r"\d", line)


def test_res_line():
    line = res("1k", "a", "b", 1000.0)
    assert line.startswith("R1k")
    assert "1000" in line or "1e+03" in line or "1e3" in line


# ---------------------------------------------------------------------------
# 8–11. Deck builders
# ---------------------------------------------------------------------------

def test_build_transient_deck_minimal():
    deck = build_transient_deck(
        "Test deck",
        ["Vdd vdd 0 DC 1.8"],
        t_step_ns=0.1,
        t_stop_ns=10.0,
    )
    assert deck.startswith("Test deck")
    assert ".TRAN" in deck
    assert ".end" in deck.lower()


def test_build_transient_deck_tran_values():
    deck = build_transient_deck(
        "Tran values test",
        [],
        t_step_ns=0.5,
        t_stop_ns=20.0,
    )
    # Should contain the time step and stop time
    assert "0.5n" in deck or "5e-01n" in deck
    assert "20n" in deck or "20.0n" in deck


def test_build_transient_deck_probes():
    deck = build_transient_deck(
        "Probe test",
        [],
        t_step_ns=1.0,
        t_stop_ns=10.0,
        probes=["V(vout)", "V(vin)"],
    )
    assert ".PRINT TRAN" in deck
    assert "V(vout)" in deck
    assert "V(vin)" in deck


def test_build_transient_deck_models():
    models = [".MODEL NMOS_TEST NMOS (LEVEL=1 VTH0=0.5)"]
    deck = build_transient_deck(
        "Model test",
        [],
        t_step_ns=1.0,
        t_stop_ns=10.0,
        models=models,
    )
    assert ".MODEL NMOS_TEST" in deck
    # Model line should appear before .TRAN
    model_pos = deck.find(".MODEL NMOS_TEST")
    tran_pos = deck.find(".TRAN")
    assert model_pos < tran_pos


def test_build_transient_deck_ends_with_newline():
    deck = build_transient_deck("Test", [], 1.0, 10.0)
    assert deck.endswith("\n")


def test_build_dc_deck_minimal():
    deck = build_dc_deck(
        "DC sweep",
        ["Vdd vdd 0 DC 1.8"],
        source_name="Vin",
        vstart=0.0,
        vstop=1.8,
        vstep=0.01,
    )
    assert ".DC" in deck
    assert "Vin" in deck
    assert ".end" in deck.lower()


def test_build_dc_deck_values():
    deck = build_dc_deck("DC", [], "Vx", 0.0, 3.3, 0.1)
    assert "3.3" in deck
    assert "0.1" in deck


def test_build_dc_deck_probes():
    deck = build_dc_deck("DC", [], "Vin", 0, 1.8, 0.01, probes=["V(out)"])
    assert ".PRINT DC" in deck
    assert "V(out)" in deck


# ---------------------------------------------------------------------------
# 12–15. parse_ngspice_output
# ---------------------------------------------------------------------------

_TWO_COL_OUTPUT = """\
Index   time        V(vout)
------  ----------  ----------
0       0.000000e+00  1.800000e+00
1       1.000000e-09  1.750000e+00
2       2.000000e-09  1.200000e+00
3       3.000000e-09  5.000000e-01
"""


def test_parse_ngspice_output_basic():
    result = parse_ngspice_output(_TWO_COL_OUTPUT)
    assert "time" in result
    assert "v(vout)" in result
    assert len(result["time"]) == 4
    assert len(result["v(vout)"]) == 4
    assert math.isclose(result["time"][0], 0.0)
    assert math.isclose(result["time"][1], 1e-9)
    assert math.isclose(result["v(vout)"][0], 1.8)


def test_parse_ngspice_output_three_cols():
    text = """\
Index   time        V(vout)     V(vin)
------  ----------  ----------  ----------
0       0.000e+00   1.800e+00   0.000e+00
1       1.000e-09   1.750e+00   1.800e+00
"""
    result = parse_ngspice_output(text)
    assert "time" in result
    assert "v(vout)" in result
    assert "v(vin)" in result
    assert len(result["time"]) == 2
    assert math.isclose(result["v(vin)"][1], 1.8)


def test_parse_ngspice_output_empty():
    result = parse_ngspice_output("")
    assert result == {}


def test_parse_ngspice_output_noise():
    """Lines starting with Note:/Warning:/Error: should be skipped."""
    text = """\
Note: Doing real analysis
Warning: some model issue
Index   time        V(out)
------  ----------  ----------
0       0.000e+00   0.900e+00
"""
    result = parse_ngspice_output(text)
    assert "time" in result
    assert len(result["time"]) == 1


def test_parse_ngspice_output_no_headers():
    """Two-column data with no alpha headers -> some columns returned with values."""
    text = """\
0.000e+00   1.800e+00
1.000e-09   1.750e+00
2.000e-09   1.200e+00
"""
    result = parse_ngspice_output(text)
    # Without a header row, the parser uses the first token-row as headers or
    # positional keys.  Either way we should have some data back.
    assert result, "expected non-empty result for headerless numeric data"
    # All values must be floats
    for key, vals in result.items():
        for v in vals:
            assert isinstance(v, float), f"value {v!r} under key {key!r} is not float"


# ---------------------------------------------------------------------------
# 16–19. is_valid_spice_deck
# ---------------------------------------------------------------------------

_MINIMAL_VALID_DECK = """\
Minimal test circuit
R1 1 2 1k
V1 1 0 DC 1
.TRAN 1n 10n
.end
"""


def test_is_valid_spice_deck_valid():
    ok, reason = is_valid_spice_deck(_MINIMAL_VALID_DECK)
    assert ok, f"Expected valid, got: {reason}"


def test_is_valid_spice_deck_no_analysis():
    deck = "No analysis\nR1 1 2 1k\n.end\n"
    ok, reason = is_valid_spice_deck(deck)
    assert not ok
    assert "analysis" in reason.lower()


def test_is_valid_spice_deck_no_end():
    deck = "No end line\nR1 1 2 1k\n.TRAN 1n 10n\n"
    ok, reason = is_valid_spice_deck(deck)
    assert not ok
    assert ".end" in reason.lower()


def test_is_valid_spice_deck_empty():
    ok, reason = is_valid_spice_deck("")
    assert not ok
    assert reason


def test_is_valid_spice_deck_dc():
    deck = "DC sweep test\nV1 1 0 DC 0\n.DC V1 0 1.8 0.01\n.end\n"
    ok, reason = is_valid_spice_deck(deck)
    assert ok, f"DC deck should be valid: {reason}"


# ---------------------------------------------------------------------------
# 20–23. has_subckt / has_model
# ---------------------------------------------------------------------------

def test_has_subckt_true():
    deck = "Title\n.SUBCKT INV in out vdd gnd\n.ENDS INV\n.TRAN 1n 10n\n.end\n"
    assert has_subckt(deck)


def test_has_subckt_false():
    assert not has_subckt(_MINIMAL_VALID_DECK)


def test_has_model_true():
    deck = "Title\n.MODEL NMOS1 NMOS (LEVEL=1)\n.TRAN 1n 10n\n.end\n"
    assert has_model(deck)


def test_has_model_false():
    assert not has_model(_MINIMAL_VALID_DECK)


# ---------------------------------------------------------------------------
# 24. extract_probe_nodes
# ---------------------------------------------------------------------------

def test_extract_probe_nodes():
    deck = "Title\nR1 1 2 1k\n.TRAN 1n 10n\n.PRINT TRAN V(vout) V(vin)\n.end\n"
    nodes = extract_probe_nodes(deck)
    assert "V(vout)" in nodes
    assert "V(vin)" in nodes


def test_extract_probe_nodes_empty():
    nodes = extract_probe_nodes(_MINIMAL_VALID_DECK)
    assert nodes == []


def test_extract_probe_nodes_multiple_print():
    deck = (
        "Title\n.TRAN 1n 10n\n"
        ".PRINT TRAN V(a)\n"
        ".PRINT TRAN V(b) V(c)\n"
        ".end\n"
    )
    nodes = extract_probe_nodes(deck)
    assert "V(a)" in nodes
    assert "V(b)" in nodes
    assert "V(c)" in nodes


# ---------------------------------------------------------------------------
# 25–32. Fixture file tests
# ---------------------------------------------------------------------------

def _read_fixture(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_fixture_inverter_valid():
    text = _read_fixture(_INVERTER)
    ok, reason = is_valid_spice_deck(text)
    assert ok, f"inverter.cir should be valid SPICE: {reason}"


def test_fixture_inverter_has_model():
    text = _read_fixture(_INVERTER)
    assert has_model(text), "inverter.cir must contain .MODEL directives"


def test_fixture_inverter_has_transient():
    text = _read_fixture(_INVERTER)
    assert re.search(r"^\.TRAN\b", text, re.IGNORECASE | re.MULTILINE), (
        "inverter.cir must contain a .TRAN directive"
    )


def test_fixture_inverter_print_nodes():
    text = _read_fixture(_INVERTER)
    nodes = extract_probe_nodes(text)
    assert any("vout" in n.lower() for n in nodes), (
        "inverter.cir .PRINT must include V(vout)"
    )
    assert any("vin" in n.lower() for n in nodes), (
        "inverter.cir .PRINT must include V(vin)"
    )


def test_fixture_inverter_two_mosfets():
    text = _read_fixture(_INVERTER)
    mosfet_lines = [l for l in text.splitlines()
                    if re.match(r"^M[a-zA-Z0-9_]+\s", l.strip())]
    assert len(mosfet_lines) == 2, (
        f"inverter.cir must have 2 MOSFET lines, found {len(mosfet_lines)}"
    )


def test_fixture_nand2_valid():
    text = _read_fixture(_NAND2)
    ok, reason = is_valid_spice_deck(text)
    assert ok, f"nand2.cir should be valid SPICE: {reason}"


def test_fixture_nand2_has_model():
    text = _read_fixture(_NAND2)
    assert has_model(text), "nand2.cir must contain .MODEL directives"


def test_fixture_nand2_has_transient():
    text = _read_fixture(_NAND2)
    assert re.search(r"^\.TRAN\b", text, re.IGNORECASE | re.MULTILINE), (
        "nand2.cir must contain a .TRAN directive"
    )


def test_fixture_nand2_four_mosfets():
    text = _read_fixture(_NAND2)
    mosfet_lines = [l for l in text.splitlines()
                    if re.match(r"^M[a-zA-Z0-9_]+\s", l.strip())]
    assert len(mosfet_lines) == 4, (
        f"nand2.cir must have 4 MOSFET lines (2P + 2N), found {len(mosfet_lines)}"
    )


def test_fixture_nand2_print_nodes():
    text = _read_fixture(_NAND2)
    nodes = extract_probe_nodes(text)
    assert any("vout" in n.lower() for n in nodes), (
        "nand2.cir .PRINT must include V(vout)"
    )
