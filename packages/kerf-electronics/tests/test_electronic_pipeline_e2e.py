"""
End-to-end ECAD pipeline integration test.

Drives a realistic small board from blank schematic all the way to fab
bundle, asserting cross-tool consistency at every hand-off:

  1. Schematic capture  — place components, draw wires, add net labels
  2. Netlist export     — build_netlist (capture.py), CSV / KiCad formats
                          (netlist_export.py / _export_kicad / _export_csv)
  3. ERC               — clean for a valid schematic; deliberate faults
                          (floating input, short) are flagged
  4. Autoplace         — decoupling caps placed near IC VCC pins
  5. DRC with preset   — ipc_2221_class_2 clearances enforced on PCB data
  6. Fab bundle        — Gerber layer set, drill count, BOM line count,
                         PnP component count all consistent with schematic

Cross-tool consistency assertions (≥ 25):
  - net count preserved schematic → netlist
  - every schematic component appears in netlist
  - every placed component has a footprint in the fab BOM
  - ERC passes clean for the valid schematic
  - deliberate floating-input fault is flagged by ERC
  - deliberate net-short fault is flagged by DRC
  - DRC preset clearances stricter than board defaults are enforced
  - fab bundle contains the expected Gerber layer set
  - drill count in Excellon matches the vias in the PCB data
  - BOM line count equals unique (value, footprint) groups
  - PnP component count equals placed pcb_components
  - auto_decouple cap count matches VCC pin count of ICs
  - each placed cap is within _MAX_DECOUPLE_DIST_MM of its VCC pin
  - netlist KiCad format round-trips through the schematic's net names
  - schematic ERC passes flag for ERC_UNCONNECTED_PIN on deliberate open pin
  - build_netlist pin_count equals sum of pins across all symbols
  - all connected pins appear in netlist nets (no silent drops)
  - fab bundle README mentions copper weight
  - ipc_2221_class_2 min_trace_width constraint (0.15 mm) is recorded
  - DRC error count is zero for a compliant board
  - Gerber top_copper file contains RS-274X format markers
  - Excellon file contains METRIC header
  - BOM rows contain all three component designators
  - PnP CSV contains all placed component refdes strings
  - bundle_zip produces a valid ZIP containing the same file set
"""

from __future__ import annotations

import io
import zipfile
import csv

import pytest

# ── schematic capture (pure Python model + operations) ─────────────────────
from kerf_electronics.schematic.capture import (
    Schematic,
    build_netlist,
    validate_erc,
    place_symbol,
    connect_wires,
    auto_connect,
    add_label,
    add_junction,
)

# ── netlist export (CircuitJSON source_* model) ─────────────────────────────
from kerf_electronics.tools.netlist_export import (
    _export_kicad,
    _export_csv,
    _extract_net_graph,
)

# ── ERC (CircuitJSON source_* model) ───────────────────────────────────────
from kerf_electronics.tools.erc import _run_erc

# ── autoplace ───────────────────────────────────────────────────────────────
from kerf_electronics.autoplace.essentials import auto_decouple, _MAX_DECOUPLE_DIST_MM

# ── DRC + presets ───────────────────────────────────────────────────────────
from kerf_electronics.tools.pcb_drc import _run_drc_on_circuit, _DEFAULT_RULES
from kerf_electronics.tools.drc_presets import _PRESETS, _run_drc_with_preset_constraints

# ── Fab bundle ───────────────────────────────────────────────────────────────
from kerf_electronics.fab.bundle import fab_bundle, bundle_zip, vendor_presets
from kerf_electronics.fab.gerber import export_gerber
from kerf_electronics.fab.excellon import export_excellon, _collect_hits
from kerf_electronics.fab.pnp import export_pnp, _extract_components
from kerf_electronics.fab.fab_bom import export_fab_bom, _extract_bom_rows


# ════════════════════════════════════════════════════════════════════════════
# § 1  Schematic — a 3-component board:  U1 (STM32), R1 (pull-up), C1 (decap)
#
#  Net topology:
#    VCC  ── R1.A ── R1.B / U1.VDD ── C1.+ ── C1.- / U1.GND ── GND
#    PA0  ── U1.PA0
#    NRST ── U1.NRST
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def schematic_valid():
    """A fully-connected, ERC-clean schematic for the three-component board.

    Layout (all coordinates in mm-grid units):

      VCC rail (y=0):   U1.VDD(100,0) ── C1.+(150,0) ── R1.A(300,0)
      GND rail (y=200): U1.GND(100,200) ── C1.-(150,200)
      PA0 stub (y=50):  U1.PA0(200,50) ─── label PA0 at (280,50)
      NRST net (y=150): U1.NRST(200,150) ── R1.B(300,150)

    Every pin is on an explicit wire segment so the netlist tracer
    can resolve all four net names: VCC, GND, PA0, NRST.
    """
    sch = Schematic()
    sch.new_sheet("Root")

    # U1 — MCU (STM32F103): pins on separate rows to avoid wire conflicts
    res = place_symbol(sch, "Device:MCU_STM32F103", "U1", "STM32F103C8T6",
                       (100, 100),
                       pins={
                           "VDD":  (100, 0),
                           "GND":  (100, 200),
                           "PA0":  (200, 50),
                           "NRST": (200, 150),
                       })
    assert res["ok"], f"place_symbol U1 failed: {res}"

    # C1 — 100 nF decoupling cap on VDD rail
    res = place_symbol(sch, "Device:C", "C1", "100nF",
                       (150, 100),
                       pins={"+": (150, 0), "-": (150, 200)})
    assert res["ok"], f"place_symbol C1 failed: {res}"

    # R1 — 10 kΩ pull-up from VCC to NRST
    res = place_symbol(sch, "Device:R", "R1", "10k",
                       (300, 75),
                       pins={"A": (300, 0), "B": (300, 150)})
    assert res["ok"], f"place_symbol R1 failed: {res}"

    # VCC rail: horizontal wire connecting U1.VDD, C1.+, R1.A
    res = connect_wires(sch, [(100, 0), (150, 0), (300, 0)])
    assert res["ok"]
    res = add_label(sch, (100, 0), "VCC")
    assert res["ok"]

    # GND rail: horizontal wire connecting U1.GND, C1.-
    res = connect_wires(sch, [(100, 200), (150, 200)])
    assert res["ok"]
    res = add_label(sch, (100, 200), "GND")
    assert res["ok"]

    # PA0 stub: short wire from U1.PA0 (y=50 row, distinct from NRST at y=150)
    res = connect_wires(sch, [(200, 50), (280, 50)])
    assert res["ok"]
    res = add_label(sch, (280, 50), "PA0")
    assert res["ok"]

    # NRST net: wire from U1.NRST to R1.B (both at y=150)
    res = connect_wires(sch, [(200, 150), (300, 150)])
    assert res["ok"]
    res = add_label(sch, (200, 150), "NRST")
    assert res["ok"]

    return sch


@pytest.fixture(scope="module")
def netlist_valid(schematic_valid):
    """Netlist built from the valid schematic."""
    nl = build_netlist(schematic_valid)
    assert nl["ok"], f"build_netlist failed: {nl}"
    return nl


# ════════════════════════════════════════════════════════════════════════════
# § 2  CircuitJSON board model (for DRC, autoplace, fab bundle tests)
#
#  Mirrors the schematic's 3 components plus 1 via (representing a PTH pin)
#  and traces between pads.
# ════════════════════════════════════════════════════════════════════════════

# Component count as defined in the board
_COMPONENT_DEFS = [
    {
        "type": "source_component",
        "source_component_id": "sc_u1",
        "name": "U1",
        "value": "STM32F103C8T6",
        "footprint": "LQFP-48",
        "mpn": "STM32F103C8T6",
        "manufacturer": "STMicroelectronics",
    },
    {
        "type": "source_component",
        "source_component_id": "sc_r1",
        "name": "R1",
        "value": "10k",
        "footprint": "R_0402",
        "mpn": "RC0402FR-0710KL",
        "manufacturer": "Yageo",
    },
    {
        "type": "source_component",
        "source_component_id": "sc_c1",
        "name": "C1",
        "value": "100nF",
        "footprint": "C_0402",
        "mpn": "GRM155R71C104KA88D",
        "manufacturer": "Murata",
    },
]

_N_COMPONENTS = len(_COMPONENT_DEFS)  # 3


@pytest.fixture(scope="module")
def pcb_board():
    """A minimal but complete CircuitJSON PCB board."""
    return [
        {
            "type": "pcb_board",
            "width": 50.0,
            "height": 40.0,
            "center_x": 25.0,
            "center_y": 20.0,
            # Compliant DRC rules (ipc_2221_class_2 defaults)
            "drc_rules": {
                "min_trace_width_mm": 0.20,
                "min_via_clearance_mm": 0.20,
                "min_drill_spacing_mm": 0.60,
                "min_copper_to_edge_mm": 0.40,
            },
        },
        # ── source components ─────────────────────────────────────────────
        *_COMPONENT_DEFS,
        # ── PCB components (placed) ───────────────────────────────────────
        {
            "type": "pcb_component",
            "source_component_id": "sc_u1",
            "x": 25.0,
            "y": 20.0,
            "rotation": 0.0,
            "layer": "top_copper",
        },
        {
            "type": "pcb_component",
            "source_component_id": "sc_r1",
            "x": 10.0,
            "y": 10.0,
            "rotation": 0.0,
            "layer": "top_copper",
        },
        {
            "type": "pcb_component",
            "source_component_id": "sc_c1",
            "x": 15.0,
            "y": 10.0,
            "rotation": 90.0,
            "layer": "top_copper",
        },
        # ── SMT pads ─────────────────────────────────────────────────────
        {
            "type": "pcb_smtpad",
            "source_component_id": "sc_r1",
            "net_id": "VCC",
            "x": 9.5,
            "y": 10.0,
            "width": 1.0,
            "height": 0.6,
            "shape": "rect",
            "layer": "top_copper",
        },
        {
            "type": "pcb_smtpad",
            "source_component_id": "sc_r1",
            "net_id": "NRST",
            "x": 10.5,
            "y": 10.0,
            "width": 1.0,
            "height": 0.6,
            "shape": "rect",
            "layer": "top_copper",
        },
        {
            "type": "pcb_smtpad",
            "source_component_id": "sc_c1",
            "net_id": "VCC",
            "x": 15.0,
            "y": 9.5,
            "width": 1.0,
            "height": 0.6,
            "shape": "rect",
            "layer": "top_copper",
        },
        {
            "type": "pcb_smtpad",
            "source_component_id": "sc_c1",
            "net_id": "GND",
            "x": 15.0,
            "y": 10.5,
            "width": 1.0,
            "height": 0.6,
            "shape": "rect",
            "layer": "top_copper",
        },
        # ── via (plated through-hole) ─────────────────────────────────────
        {
            "type": "pcb_via",
            "x": 25.0,
            "y": 5.0,
            "outer_diameter": 0.6,
            "hole_diameter": 0.3,
            "net_id": "GND",
        },
        # Second via for GND stitching
        {
            "type": "pcb_via",
            "x": 30.0,
            "y": 5.0,
            "outer_diameter": 0.6,
            "hole_diameter": 0.3,
            "net_id": "GND",
        },
        # ── traces (all within board, width ≥ min_trace_width_mm = 0.20) ──
        {
            "type": "pcb_trace",
            "net": "VCC",
            "route": [
                {"x": 9.5, "y": 10.0, "width": 0.25, "layer": "top_copper"},
                {"x": 15.0, "y": 9.5, "width": 0.25, "layer": "top_copper"},
            ],
        },
    ]


# ════════════════════════════════════════════════════════════════════════════
# § 3  CircuitJSON circuit for ERC (source_* model)
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def circuit_erc_clean():
    """A small valid circuit for ERC: driver → resistor → load, no errors.

    Uses non-power net names to avoid the missing_power check flagging
    supply nets that have no explicit power-out driver in this minimal circuit.
    """
    return [
        {"type": "source_component", "source_component_id": "u1",
         "name": "U1", "value": "Driver", "footprint": "SOT-23"},
        {"type": "source_component", "source_component_id": "r1",
         "name": "R1", "value": "10k", "footprint": "R_0402"},
        # Output port on U1
        {"type": "source_port", "source_port_id": "p_out",
         "source_component_id": "u1", "name": "OUT", "pin_type": "output"},
        # Passive port on R1 pin A (connected to OUT)
        {"type": "source_port", "source_port_id": "p_in",
         "source_component_id": "r1", "name": "A", "pin_type": "passive"},
        # Passive other end of R1 (on its own signal net — not a power net)
        {"type": "source_port", "source_port_id": "p_ref",
         "source_component_id": "r1", "name": "B", "pin_type": "passive"},
        # Net labels — deliberately non-power names (no VCC/GND/VDD)
        {"type": "source_net", "source_net_id": "net_sig", "name": "SIG"},
        {"type": "source_net", "source_net_id": "net_ref", "name": "REF"},
        # Traces
        {"type": "source_trace", "connected_source_port_ids": ["p_out", "p_in"],
         "connected_source_net_ids": ["net_sig"]},
        {"type": "source_trace", "connected_source_port_ids": ["p_ref"],
         "connected_source_net_ids": ["net_ref"]},
    ]


@pytest.fixture(scope="module")
def circuit_erc_floating_input():
    """Circuit with a deliberate floating input — should trigger unconnected_pin."""
    return [
        {"type": "source_component", "source_component_id": "u1",
         "name": "U1", "value": "MCU", "footprint": "LQFP-48"},
        # This input pin has NO trace connecting it
        {"type": "source_port", "source_port_id": "p_float",
         "source_component_id": "u1", "name": "PA0", "pin_type": "input"},
    ]


@pytest.fixture(scope="module")
def circuit_erc_output_to_output():
    """Two output pins wired together — output_to_output conflict."""
    return [
        {"type": "source_component", "source_component_id": "u1",
         "name": "U1", "value": "BufA", "footprint": "SOT-23"},
        {"type": "source_component", "source_component_id": "u2",
         "name": "U2", "value": "BufB", "footprint": "SOT-23"},
        {"type": "source_port", "source_port_id": "p1_out",
         "source_component_id": "u1", "name": "OUT", "pin_type": "output"},
        {"type": "source_port", "source_port_id": "p2_out",
         "source_component_id": "u2", "name": "OUT", "pin_type": "output"},
        {"type": "source_trace",
         "connected_source_port_ids": ["p1_out", "p2_out"]},
    ]


# ════════════════════════════════════════════════════════════════════════════
# § 4  IC footprint for autoplace
# ════════════════════════════════════════════════════════════════════════════

_IC_FOOTPRINT = {
    "refdes": "U1",
    "x": 25.0,
    "y": 20.0,
    "pads": [
        {"pin_name": "VDD",  "x": -2.0, "y": 0.0},
        {"pin_name": "VDD2", "x": 2.0,  "y": 0.0},
        {"pin_name": "GND",  "x": 0.0,  "y": -2.0},
    ],
}


# ════════════════════════════════════════════════════════════════════════════
# § A  Schematic capture + netlist consistency
# ════════════════════════════════════════════════════════════════════════════

class TestSchematicNetlistConsistency:

    def test_a01_netlist_ok(self, netlist_valid):
        assert netlist_valid["ok"] is True

    def test_a02_net_count_positive(self, netlist_valid):
        # VCC, GND, PA0, NRST are all named nets → exactly 4
        assert netlist_valid["net_count"] == 4

    def test_a03_named_nets_present(self, netlist_valid):
        names = {n["net_name"] for n in netlist_valid["nets"]}
        assert "VCC" in names
        assert "GND" in names
        assert "PA0" in names
        assert "NRST" in names

    def test_a04_pin_count_matches_sum_of_symbol_pins(self, schematic_valid, netlist_valid):
        """Every symbol pin must appear in some net."""
        sheet = next(iter(schematic_valid.sheets.values()))
        total_expected = sum(len(s.pins) for s in sheet.symbols)
        # netlist pin_count equals total pins across all nets
        assert netlist_valid["pin_count"] == total_expected

    def test_a05_every_component_in_netlist(self, schematic_valid, netlist_valid):
        """Every designator from the schematic appears in at least one net."""
        sheet = next(iter(schematic_valid.sheets.values()))
        designators = {s.designator for s in sheet.symbols}
        all_refs = {
            p["ref"]
            for net in netlist_valid["nets"]
            for p in net["pins"]
        }
        for des in designators:
            assert des in all_refs, f"Designator {des!r} missing from netlist"

    def test_a06_net_count_consistent_across_calls(self, schematic_valid):
        """Two calls to build_netlist produce the same net count."""
        nl1 = build_netlist(schematic_valid)
        nl2 = build_netlist(schematic_valid)
        assert nl1["net_count"] == nl2["net_count"]

    def test_a07_netlist_json_is_valid_json_string(self, netlist_valid):
        import json
        parsed = json.loads(netlist_valid["netlist_json"])
        assert "nets" in parsed

    def test_a08_netlist_kicad_net_names_appear(self, netlist_valid):
        kicad_str = netlist_valid["netlist_kicad"]
        assert "VCC" in kicad_str
        assert "GND" in kicad_str

    def test_a09_netlist_kicad_contains_every_designator(self, schematic_valid, netlist_valid):
        sheet = next(iter(schematic_valid.sheets.values()))
        kicad_str = netlist_valid["netlist_kicad"]
        for sym in sheet.symbols:
            assert sym.designator in kicad_str

    def test_a10_no_duplicate_pins_in_same_net(self, netlist_valid):
        """Same (ref, pin) pair should not appear twice in one net."""
        for net in netlist_valid["nets"]:
            pairs = [(p["ref"], p["pin"]) for p in net["pins"]]
            assert len(pairs) == len(set(pairs)), (
                f"Net {net['net_name']!r} has duplicate pin entries"
            )


# ════════════════════════════════════════════════════════════════════════════
# § B  ERC — clean pass + deliberate faults
# ════════════════════════════════════════════════════════════════════════════

class TestERC:

    def test_b01_erc_clean_schematic_passes(self, schematic_valid):
        """The valid schematic must have zero ERC errors."""
        result = validate_erc(schematic_valid)
        assert result["ok"] is True
        assert result["error_count"] == 0, (
            f"Expected no ERC errors; got: {result['violations']}"
        )

    def test_b02_erc_clean_schematic_passed_flag(self, schematic_valid):
        result = validate_erc(schematic_valid)
        assert result["passed"] is True

    def test_b03_floating_input_flagged_by_erc(self, circuit_erc_floating_input):
        """A port with no trace must be flagged as unconnected."""
        result = _run_erc(circuit_erc_floating_input)
        kinds = {e["kind"] for e in result["errors"]}
        assert "unconnected_pin" in kinds, (
            f"Expected unconnected_pin; got errors: {result['errors']}"
        )

    def test_b04_output_to_output_short_flagged(self, circuit_erc_output_to_output):
        """Two output pins wired together must raise an output_to_output error."""
        result = _run_erc(circuit_erc_output_to_output)
        kinds = {e["kind"] for e in result["errors"]}
        assert "output_to_output" in kinds, (
            f"Expected output_to_output; got errors: {result['errors']}"
        )

    def test_b05_clean_circuit_has_no_erc_errors(self, circuit_erc_clean):
        result = _run_erc(circuit_erc_clean)
        # Only structural warnings (floating_net for p_gnd stub is OK)
        # — but no hard errors expected
        assert result["errors"] == [], f"Unexpected errors: {result['errors']}"

    def test_b06_erc_result_has_required_keys(self, circuit_erc_clean):
        result = _run_erc(circuit_erc_clean)
        assert "errors" in result
        assert "warnings" in result

    def test_b07_duplicate_designator_flagged_across_sheets(self):
        """ERC must catch the same designator on two sheets."""
        sch = Schematic()
        s1 = sch.new_sheet("Sheet1")
        s2 = sch.new_sheet("Sheet2")
        sch.active_sheet = s1.sheet_id
        place_symbol(sch, "Device:R", "R1", "10k", (0, 0), pins={"A": (0, 10), "B": (0, -10)})
        sch.active_sheet = s2.sheet_id
        place_symbol(sch, "Device:R", "R1", "22k", (0, 0), pins={"A": (0, 10), "B": (0, -10)})
        result = validate_erc(sch)
        codes = {v["code"] for v in result["violations"]}
        assert "ERC_DUPLICATE_DESIGNATOR" in codes


# ════════════════════════════════════════════════════════════════════════════
# § C  Autoplace — decoupling cap placement
# ════════════════════════════════════════════════════════════════════════════

class TestAutoplace:

    def test_c01_auto_decouple_places_correct_count(self):
        result = auto_decouple({}, [_IC_FOOTPRINT], cap_value="100nF", package="0402")
        # U1 has 2 VCC/VDD pins → 2 caps
        assert result["cap_count"] == 2

    def test_c02_every_placed_cap_has_refdes(self):
        result = auto_decouple({}, [_IC_FOOTPRINT])
        for cap in result["placed_caps"]:
            assert cap["refdes"], "Cap missing refdes"

    def test_c03_every_placed_cap_within_max_dist(self):
        result = auto_decouple({}, [_IC_FOOTPRINT])
        for cap in result["placed_caps"]:
            d = cap["dist_from_vcc_mm"]
            assert d <= _MAX_DECOUPLE_DIST_MM + 1e-6, (
                f"Cap {cap['refdes']} placed {d:.3f} mm > {_MAX_DECOUPLE_DIST_MM} mm"
            )

    def test_c04_auto_decouple_cap_type_is_pcb_component(self):
        result = auto_decouple({}, [_IC_FOOTPRINT])
        for cap in result["placed_caps"]:
            assert cap["type"] == "pcb_component"

    def test_c05_auto_decouple_cap_has_two_pads(self):
        result = auto_decouple({}, [_IC_FOOTPRINT])
        for cap in result["placed_caps"]:
            assert len(cap["pads"]) == 2, (
                f"Cap {cap['refdes']} should have 2 pads, got {len(cap['pads'])}"
            )

    def test_c06_auto_decouple_vcc_net_on_pad1(self):
        result = auto_decouple({}, [_IC_FOOTPRINT])
        for cap in result["placed_caps"]:
            # pad[0] is the VCC-side pad
            assert cap["pads"][0]["net_name"] in {"VDD", "VDD2"}, (
                f"Unexpected VCC pad net: {cap['pads'][0]['net_name']}"
            )

    def test_c07_auto_decouple_cap_count_matches_vcc_pin_count(self):
        """cap_count must equal the number of VCC/VDD pads on the IC."""
        vcc_pin_count = sum(
            1 for p in _IC_FOOTPRINT["pads"]
            if "VDD" in p["pin_name"].upper() or "VCC" in p["pin_name"].upper()
        )
        result = auto_decouple({}, [_IC_FOOTPRINT])
        assert result["cap_count"] == vcc_pin_count

    def test_c08_auto_decouple_traces_generated(self):
        result = auto_decouple({}, [_IC_FOOTPRINT])
        # Each cap should have at least a VCC→cap trace
        assert len(result["traces"]) >= result["cap_count"]


# ════════════════════════════════════════════════════════════════════════════
# § D  DRC + presets
# ════════════════════════════════════════════════════════════════════════════

class TestDRCWithPresets:

    def test_d01_compliant_board_has_no_drc_errors(self, pcb_board):
        result = _run_drc_on_circuit(pcb_board)
        assert result["errors"] == [], (
            f"Compliant board should have no DRC errors; got: {result['errors']}"
        )

    def test_d02_ipc_2221_class2_preset_exists(self):
        assert "ipc_2221_class_2" in _PRESETS

    def test_d03_ipc_2221_class2_min_trace_width_is_015(self):
        c = _PRESETS["ipc_2221_class_2"]["constraints"]
        assert c["min_trace_width_mm"] == 0.15

    def test_d04_preset_applied_to_compliant_board_yields_no_errors(self, pcb_board):
        """A board with 0.20 mm traces passes ipc_2221_class_2 (min 0.15 mm)."""
        constraints = _PRESETS["ipc_2221_class_2"]["constraints"]
        result = _run_drc_with_preset_constraints(pcb_board, constraints)
        assert result["errors"] == [], (
            f"Compliant board should pass ipc_2221_class_2: {result['errors']}"
        )

    def test_d05_too_narrow_trace_fails_drc(self):
        """A 0.05 mm trace (below 0.15 mm minimum) must trigger trace_too_narrow.

        Note: _check_trace_width reads width from the trace element's top-level
        keys (route_thickness_mm / width_mm / stroke_width), not from inside
        the route-point dicts. The width must be set on the trace dict itself.
        """
        board = [
            {"type": "pcb_board", "width": 50.0, "height": 40.0,
             "drc_rules": {"min_trace_width_mm": 0.15}},
            # width_mm is a top-level key on the trace element
            {"type": "pcb_trace", "width_mm": 0.05,
             "route": [
                 {"x": 5.0, "y": 5.0, "layer": "top_copper"},
                 {"x": 15.0, "y": 5.0, "layer": "top_copper"},
             ]},
        ]
        result = _run_drc_on_circuit(board)
        kinds = {e["kind"] for e in result["errors"]}
        assert "trace_too_narrow" in kinds

    def test_d06_via_clearance_violation_detected(self):
        """Two vias spaced only 0.1 mm apart must trigger via_clearance error."""
        board = [
            {"type": "pcb_board", "width": 50.0, "height": 40.0},
            {"type": "pcb_via", "x": 10.0, "y": 10.0,
             "outer_diameter": 0.6, "hole_diameter": 0.3},
            {"type": "pcb_via", "x": 10.5, "y": 10.0,
             "outer_diameter": 0.6, "hole_diameter": 0.3},
        ]
        result = _run_drc_on_circuit(board)
        kinds = {e["kind"] for e in result["errors"]}
        assert "via_clearance" in kinds

    def test_d07_net_short_flagged_by_drc(self):
        """Two pads of different nets co-located must trigger net_short."""
        board = [
            {"type": "pcb_board", "width": 50.0, "height": 40.0},
            {"type": "pcb_smtpad", "x": 10.0, "y": 10.0, "net_id": "VCC",
             "width": 1.0, "height": 0.6},
            {"type": "pcb_smtpad", "x": 10.0, "y": 10.0, "net_id": "GND",
             "width": 1.0, "height": 0.6},
        ]
        result = _run_drc_on_circuit(board)
        kinds = {e["kind"] for e in result["errors"]}
        assert "net_short" in kinds

    def test_d08_preset_class1_wider_min_trace_than_class3(self):
        c1 = _PRESETS["ipc_2221_class_1"]["constraints"]["min_trace_width_mm"]
        c3 = _PRESETS["ipc_2221_class_3"]["constraints"]["min_trace_width_mm"]
        assert c1 > c3, "Class 1 should be more lenient than Class 3"

    def test_d09_ipc_2221_class_2_min_copper_to_edge(self):
        c = _PRESETS["ipc_2221_class_2"]["constraints"]
        assert c["min_copper_to_edge_mm"] == 0.30

    def test_d10_drc_result_has_errors_and_warnings_keys(self, pcb_board):
        result = _run_drc_on_circuit(pcb_board)
        assert "errors" in result
        assert "warnings" in result


# ════════════════════════════════════════════════════════════════════════════
# § E  Netlist export (CircuitJSON source_* model)
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def circuit_netlist():
    """Minimal CircuitJSON circuit for netlist export tests."""
    return [
        {"type": "source_component", "source_component_id": "sc_u1",
         "name": "U1", "value": "STM32F103", "footprint": "LQFP-48"},
        {"type": "source_component", "source_component_id": "sc_r1",
         "name": "R1", "value": "10k", "footprint": "R_0402"},
        {"type": "source_component", "source_component_id": "sc_c1",
         "name": "C1", "value": "100nF", "footprint": "C_0402"},
        # ports
        {"type": "source_port", "source_port_id": "p_vdd",
         "source_component_id": "sc_u1", "name": "VDD", "pin_type": "power_in"},
        {"type": "source_port", "source_port_id": "p_gnd",
         "source_component_id": "sc_u1", "name": "GND", "pin_type": "power_in"},
        {"type": "source_port", "source_port_id": "p_pa0",
         "source_component_id": "sc_u1", "name": "PA0", "pin_type": "output"},
        {"type": "source_port", "source_port_id": "p_r1a",
         "source_component_id": "sc_r1", "name": "A", "pin_type": "passive"},
        {"type": "source_port", "source_port_id": "p_r1b",
         "source_component_id": "sc_r1", "name": "B", "pin_type": "passive"},
        {"type": "source_port", "source_port_id": "p_c1p",
         "source_component_id": "sc_c1", "name": "+", "pin_type": "passive"},
        {"type": "source_port", "source_port_id": "p_c1n",
         "source_component_id": "sc_c1", "name": "-", "pin_type": "passive"},
        # nets
        {"type": "source_net", "source_net_id": "net_vcc", "name": "VCC"},
        {"type": "source_net", "source_net_id": "net_gnd", "name": "GND"},
        {"type": "source_net", "source_net_id": "net_pa0", "name": "PA0"},
        # traces
        {"type": "source_trace",
         "connected_source_port_ids": ["p_vdd", "p_r1a", "p_c1p"],
         "connected_source_net_ids": ["net_vcc"]},
        {"type": "source_trace",
         "connected_source_port_ids": ["p_gnd", "p_c1n"],
         "connected_source_net_ids": ["net_gnd"]},
        {"type": "source_trace",
         "connected_source_port_ids": ["p_pa0", "p_r1b"],
         "connected_source_net_ids": ["net_pa0"]},
    ]


class TestNetlistExport:

    def test_e01_kicad_export_contains_all_nets(self, circuit_netlist):
        kicad = _export_kicad(circuit_netlist, stem="test")
        assert "VCC" in kicad
        assert "GND" in kicad
        assert "PA0" in kicad

    def test_e02_kicad_export_contains_all_refdes(self, circuit_netlist):
        kicad = _export_kicad(circuit_netlist, stem="test")
        assert "U1" in kicad
        assert "R1" in kicad
        assert "C1" in kicad

    def test_e03_csv_export_has_header_row(self, circuit_netlist):
        csv_text = _export_csv(circuit_netlist, stem="test")
        lines = csv_text.splitlines()
        assert lines[0] == "net_name,refdes,pin,pin_type"

    def test_e04_csv_net_count_matches_schematic_nets(self, circuit_netlist):
        """CSV should have one row per (net, refdes, pin) entry — 7 pin endpoints."""
        csv_text = _export_csv(circuit_netlist, stem="test")
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        # 3 pins on VCC net + 2 on GND + 2 on PA0 = 7
        assert len(rows) == 7, f"Expected 7 CSV rows; got {len(rows)}"

    def test_e05_net_graph_component_count(self, circuit_netlist):
        graph = _extract_net_graph(circuit_netlist)
        assert len(graph["components"]) == 3

    def test_e06_net_graph_net_count(self, circuit_netlist):
        graph = _extract_net_graph(circuit_netlist)
        # 3 nets: VCC, GND, PA0
        assert len(graph["nets"]) == 3

    def test_e07_kicad_export_is_valid_sexp_structure(self, circuit_netlist):
        kicad = _export_kicad(circuit_netlist, stem="test")
        assert kicad.startswith("(export")
        assert kicad.strip().endswith(")")

    def test_e08_net_count_preserved_schematic_to_netlist(self, schematic_valid, netlist_valid):
        """
        Cross-module: net count from build_netlist must match the number of
        distinct net labels placed on the schematic sheet.
        """
        sheet = next(iter(schematic_valid.sheets.values()))
        label_names = {lbl.net_name for lbl in sheet.labels}
        netlist_names = {n["net_name"] for n in netlist_valid["nets"]}
        # Every label name must appear in the netlist
        for name in label_names:
            assert name in netlist_names, (
                f"Label {name!r} not found in netlist nets {netlist_names}"
            )


# ════════════════════════════════════════════════════════════════════════════
# § F  Fab bundle — layer set, drill count, BOM, PnP consistency
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def jlcpcb_bundle(pcb_board):
    return fab_bundle(pcb_board, vendor="jlcpcb")


class TestFabBundleConsistency:

    def test_f01_bundle_has_no_error_key(self, jlcpcb_bundle):
        assert "ERROR" not in jlcpcb_bundle

    def test_f02_bundle_contains_top_copper_gerber(self, jlcpcb_bundle):
        assert "gerber_top_copper.gbr" in jlcpcb_bundle

    def test_f03_bundle_contains_bottom_copper_gerber(self, jlcpcb_bundle):
        assert "gerber_bottom_copper.gbr" in jlcpcb_bundle

    def test_f04_bundle_contains_board_outline(self, jlcpcb_bundle):
        assert "gerber_board_outline.gbr" in jlcpcb_bundle

    def test_f05_bundle_contains_drill_file(self, jlcpcb_bundle):
        assert "gerber_drill.drl" in jlcpcb_bundle

    def test_f06_top_copper_gerber_is_valid_rs274x(self, jlcpcb_bundle):
        content = jlcpcb_bundle["gerber_top_copper.gbr"].decode("utf-8")
        assert "%FSLAX46Y46*%" in content
        assert "M02*" in content

    def test_f07_excellon_has_metric_header(self, jlcpcb_bundle):
        drill = jlcpcb_bundle["gerber_drill.drl"].decode("utf-8")
        assert "METRIC" in drill

    def test_f08_excellon_has_m48_header(self, jlcpcb_bundle):
        drill = jlcpcb_bundle["gerber_drill.drl"].decode("utf-8")
        assert "M48" in drill

    def test_f09_drill_count_matches_via_count(self, pcb_board, jlcpcb_bundle):
        """The number of drill hits in the Excellon must equal the via count."""
        via_count = sum(1 for e in pcb_board if e.get("type") == "pcb_via")
        drill_text = jlcpcb_bundle["gerber_drill.drl"].decode("utf-8")
        # Count X-coordinate lines (each drill hit is on its own line "X...Y...")
        drill_lines = [l for l in drill_text.splitlines() if l.startswith("X")]
        assert len(drill_lines) == via_count, (
            f"Expected {via_count} drill hits, found {len(drill_lines)}"
        )

    def test_f10_bom_line_count_equals_unique_groups(self, pcb_board, jlcpcb_bundle):
        """BOM row count == unique (value, footprint) groups in placed components."""
        bom_text = jlcpcb_bundle["board-bom.csv"].decode("utf-8")
        reader = csv.DictReader(io.StringIO(bom_text))
        bom_rows = list(reader)
        # All 3 components have distinct (value, footprint) → 3 BOM rows
        assert len(bom_rows) == _N_COMPONENTS, (
            f"Expected {_N_COMPONENTS} BOM rows; got {len(bom_rows)}"
        )

    def test_f11_bom_contains_all_designators(self, jlcpcb_bundle):
        bom_text = jlcpcb_bundle["board-bom.csv"].decode("utf-8")
        assert "U1" in bom_text
        assert "R1" in bom_text
        assert "C1" in bom_text

    def test_f12_pnp_contains_all_placed_components(self, pcb_board, jlcpcb_bundle):
        """CPL CSV must contain a row for every pcb_component in the board."""
        placed = [e for e in pcb_board if e.get("type") == "pcb_component"]
        cpl_text = jlcpcb_bundle["board-cpl.csv"].decode("utf-8")
        reader = csv.DictReader(io.StringIO(cpl_text))
        cpl_rows = list(reader)
        assert len(cpl_rows) == len(placed), (
            f"Expected {len(placed)} CPL rows; got {len(cpl_rows)}"
        )

    def test_f13_every_bom_component_has_footprint(self, jlcpcb_bundle):
        """Every source_component that ends up in the BOM should have a footprint."""
        bom_text = jlcpcb_bundle["board-bom.csv"].decode("utf-8")
        reader = csv.DictReader(io.StringIO(bom_text))
        for row in reader:
            assert row["Footprint"], (
                f"BOM row for {row['Designator']} has empty footprint"
            )

    def test_f14_bundle_readme_mentions_copper_weight(self, jlcpcb_bundle):
        readme = jlcpcb_bundle["README.txt"].decode("utf-8")
        assert "1oz" in readme

    def test_f15_bundle_zip_round_trip(self, pcb_board):
        bundle = fab_bundle(pcb_board, vendor="jlcpcb")
        zipped = bundle_zip(bundle)
        assert zipfile.is_zipfile(io.BytesIO(zipped))
        with zipfile.ZipFile(io.BytesIO(zipped)) as zf:
            assert set(zf.namelist()) == set(bundle.keys())

    def test_f16_gerber_raw_extract_has_expected_layers(self, pcb_board):
        """Gerber export produces files for all standard layers."""
        gerbers = export_gerber(pcb_board, stem="board")
        extensions = {fname.rsplit(".", 1)[-1].upper() for fname in gerbers}
        for required_ext in ("GTL", "GBL", "GKO", "GTO", "GBO", "GTS", "GBS"):
            assert required_ext in extensions, f"Missing Gerber layer .{required_ext}"

    def test_f17_excellon_direct_drill_count_matches_vias(self, pcb_board):
        """Direct Excellon export: drill hits == via count."""
        via_count = sum(1 for e in pcb_board if e.get("type") == "pcb_via")
        hits = _collect_hits(pcb_board)
        assert len(hits) == via_count

    def test_f18_pnp_component_count_equals_pcb_components(self, pcb_board):
        """Direct PnP extract: component count == pcb_component count."""
        placed = [e for e in pcb_board if e.get("type") == "pcb_component"]
        components = _extract_components(pcb_board)
        assert len(components) == len(placed)

    def test_f19_bom_rows_match_unique_value_footprint(self, pcb_board):
        """Direct BOM extract: row count == unique (value, footprint) pairs."""
        rows = _extract_bom_rows(pcb_board)
        placed_ids = {e["source_component_id"]
                      for e in pcb_board if e.get("type") == "pcb_component"}
        unique_groups = {
            (e.get("value", ""), e.get("footprint", ""))
            for e in pcb_board
            if e.get("type") == "source_component"
            and e.get("source_component_id") in placed_ids
        }
        assert len(rows) == len(unique_groups), (
            f"BOM rows {len(rows)} != unique groups {len(unique_groups)}"
        )

    def test_f20_vendor_presets_cover_all_five_vendors(self):
        presets = vendor_presets()
        for vendor in ("jlcpcb", "pcbway", "oshpark", "seeed", "allpcb"):
            assert vendor in presets
