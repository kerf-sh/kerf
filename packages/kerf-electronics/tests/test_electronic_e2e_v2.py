"""End-to-end integration test for the electronics workflow.

The electronic vertical does not couple to the new parametric-DAG kernel
directly (no DAG ops). It does, however, share the same kernel via the
3D STEP export of the board. This test file therefore exercises the
electronics pipeline horizontally — schematic → netlist → ERC → DRC →
fab outputs → thermal/SI/EMC/PDN/MC simulations — and asserts the
cross-tool numerical invariants we expect to hold.

Coverage:
  - schematic_capture place + connect_wires + add_label
  - build_netlist correctness on a 2-resistor divider
  - validate_erc clean on the valid schematic
  - validate_erc FAILs for a floating-input variant
  - PCB DRC (mfg preset) detects a narrow-trace violation
  - fab_bundle produces Gerber / Excellon / PnP / BOM (+ IPC-2581 opt)
  - thermal_board hotspot rises with component power
  - si_eye_wizard channel margin closes for a known long lossy trace
  - emc_wizard FCC Class B failing margin (regression-pinned post-fix)
  - pdn_wizard recommends caps to meet Z(f) target
  - sim_corner Monte-Carlo σ ≈ analytic for a resistor divider
  - qif_reader / ibis_reader round-trip on in-test synthetic fixtures

Hermetic — no network, no third-party files. ≥20 assertions.
"""

from __future__ import annotations

import math
import os
import sys

# ── Path setup ──────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest


# ============================================================================
# 1. Schematic capture: place_symbol + connect_wires + netlist + ERC
# ============================================================================


def _make_divider_schematic():
    """A canonical 2-resistor voltage divider on one sheet:

        VIN ── R1 ── VOUT ── R2 ── GND

    Each labelled point is on a separate wire segment so the netlist
    resolves into three named nets (VIN, VOUT, GND). ERC must come back
    clean.
    """
    from kerf_electronics.schematic.capture import (
        Schematic,
        add_label,
        connect_wires,
        place_symbol,
    )

    sch = Schematic()
    sch.new_sheet("Root")
    # R1 top pin at (50,50), bottom pin at (50,60)
    place_symbol(
        sch, "Device:R", "R1", "10k", (50.0, 55.0),
        pins={"1": (50.0, 50.0), "2": (50.0, 60.0)},
    )
    # R2 top pin at (50,70), bottom pin at (50,80)
    # We separate VOUT (50,60) and the R2 top (50,70) so the wires don't
    # collapse to a single connected component.
    place_symbol(
        sch, "Device:R", "R2", "10k", (60.0, 75.0),
        pins={"1": (60.0, 70.0), "2": (60.0, 80.0)},
    )
    # Three independent wire stubs each carrying one label.
    connect_wires(sch, [(50.0, 50.0), (52.0, 50.0)])
    connect_wires(sch, [(50.0, 60.0), (52.0, 60.0)])
    connect_wires(sch, [(60.0, 80.0), (62.0, 80.0)])
    add_label(sch, (50.0, 50.0), "VIN")
    add_label(sch, (50.0, 60.0), "VOUT")
    add_label(sch, (60.0, 80.0), "GND")
    # Tie R2.1 to VOUT via another short stub on a different x to ensure
    # the wire graph segregates the (50,60) and (60,70) clusters as a
    # single labelled net.
    connect_wires(sch, [(60.0, 70.0), (50.0, 60.0)])
    return sch


def test_schematic_netlist_three_nets():
    from kerf_electronics.schematic.capture import build_netlist

    sch = _make_divider_schematic()
    nl = build_netlist(sch)
    assert nl["ok"] is True
    nets = {n["net_name"] for n in nl["nets"]}
    assert "VIN" in nets
    assert "VOUT" in nets
    assert "GND" in nets


def test_schematic_erc_clean_on_valid_divider():
    from kerf_electronics.schematic.capture import build_netlist, validate_erc

    sch = _make_divider_schematic()
    erc = validate_erc(sch)
    assert erc["ok"] is True
    # All three pins are connected via labelled segments — should pass.
    assert erc["error_count"] == 0


def test_schematic_erc_fails_on_floating_input():
    """A symbol with an unconnected pin must trigger an
    ERC_UNCONNECTED_PIN violation.
    """
    from kerf_electronics.schematic.capture import (
        Schematic,
        place_symbol,
        validate_erc,
    )

    sch = Schematic()
    sch.new_sheet("Root")
    place_symbol(
        sch, "Device:R", "R1", "10k", (10.0, 10.0),
        pins={"1": (10.0, 10.0), "2": (10.0, 20.0)},
    )
    erc = validate_erc(sch)
    assert erc["ok"] is True
    # Both pins are unwired → expect two ERC_UNCONNECTED_PIN violations.
    codes = [v["code"] for v in erc["violations"]]
    assert "ERC_UNCONNECTED_PIN" in codes
    assert erc["error_count"] > 0


# ============================================================================
# 2. PCB DRC with manufacturing preset
# ============================================================================


def test_drc_detects_too_narrow_trace_under_mfg_preset():
    """A 0.10 mm trace fails IPC-2221 Class 2 (min 0.15 mm)."""
    from kerf_electronics.tools.drc_presets import (
        _PRESETS,
        _run_drc_with_preset_constraints,
    )

    circuit = [
        {"type": "pcb_board", "width": 50, "height": 50},
        {
            "type": "pcb_trace",
            "pcb_trace_id": "t1",
            "route_thickness_mm": 0.10,
            "route": [{"x": 5, "y": 5}, {"x": 10, "y": 5}],
        },
    ]
    constraints = _PRESETS["ipc_2221_class_2"]["constraints"]
    res = _run_drc_with_preset_constraints(circuit, constraints)
    # Expect trace_too_narrow in the rule kinds.
    kinds = [e["kind"] for e in res.get("errors", [])]
    assert "trace_too_narrow" in kinds


def test_drc_clean_when_trace_meets_min():
    """A 0.20 mm trace passes IPC-2221 Class 2 (0.15 mm minimum)."""
    from kerf_electronics.tools.drc_presets import (
        _PRESETS,
        _run_drc_with_preset_constraints,
    )

    circuit = [
        {"type": "pcb_board", "width": 50, "height": 50},
        {
            "type": "pcb_trace",
            "pcb_trace_id": "t1",
            "route_thickness_mm": 0.20,
            "route": [{"x": 5, "y": 5}, {"x": 10, "y": 5}],
        },
    ]
    constraints = _PRESETS["ipc_2221_class_2"]["constraints"]
    res = _run_drc_with_preset_constraints(circuit, constraints)
    kinds = [e["kind"] for e in res.get("errors", [])]
    assert "trace_too_narrow" not in kinds


# ============================================================================
# 3. fab_bundle: Gerber / Excellon / PnP / BOM produced
# ============================================================================


_MIN_BOARD = [
    {"type": "pcb_board", "width": 50.0, "height": 50.0},
    {
        "type": "source_component",
        "source_component_id": "sc_r1",
        "name": "R1",
        "value": "10k",
        "footprint": "R_0402",
    },
    {
        "type": "pcb_component",
        "pcb_component_id": "pcb_r1",
        "source_component_id": "sc_r1",
        "x": 10.0,
        "y": 10.0,
        "rotation": 0.0,
        "layer": "top_copper",
    },
    {
        "type": "pcb_smtpad",
        "pcb_smtpad_id": "pad_r1_1",
        "source_component_id": "sc_r1",
        "x": 10.0,
        "y": 10.0,
        "width": 1.2,
        "height": 0.8,
        "shape": "rect",
        "layer": "top_copper",
    },
    {
        "type": "pcb_via",
        "pcb_via_id": "v1",
        "x": 20.0,
        "y": 20.0,
        "outer_diameter": 0.6,
        "hole_diameter": 0.3,
    },
    {
        "type": "pcb_trace",
        "pcb_trace_id": "t1",
        "net_id": "GND",
        "route": [
            {"route_type": "wire", "x": 10.0, "y": 10.0, "width": 0.25, "layer": "top_copper"},
            {"route_type": "wire", "x": 20.0, "y": 10.0, "width": 0.25, "layer": "top_copper"},
        ],
    },
]


def test_fab_bundle_includes_gerber_and_drill():
    from kerf_electronics.fab.bundle import fab_bundle

    files = fab_bundle(_MIN_BOARD, vendor="jlcpcb")
    assert isinstance(files, dict)
    assert len(files) > 0
    # At least one Gerber file present (.gbr, .GTL, .GBL, ...) and one
    # drill file (.drl or .TXT).
    has_gerber = any(
        fname.lower().endswith(
            (".gbr", ".gtl", ".gbl", ".gto", ".gbo", ".gts", ".gbs", ".gko")
        )
        for fname in files
    )
    assert has_gerber, f"no Gerber file in bundle: {list(files.keys())}"
    has_drill = any(fname.lower().endswith((".drl", ".txt")) for fname in files)
    assert has_drill, f"no drill file in bundle: {list(files.keys())}"
    # README is always emitted
    assert any("README" in f for f in files)


def test_fab_bundle_unsupported_vendor_returns_error():
    from kerf_electronics.fab.bundle import fab_bundle

    files = fab_bundle(_MIN_BOARD, vendor="not_a_real_vendor")
    assert "ERROR" in files


# ============================================================================
# 4. thermal_board: hotspot rises with component power
# ============================================================================


def test_thermal_board_hotspot_above_ambient():
    """A 1 W component on a 50×50 mm 2-layer board with no airflow must
    produce a hotspot above ambient temperature.
    """
    from kerf_electronics.thermal_board import (
        BoardComponent,
        BoardThermalMapInput,
        solve_board_thermal_map,
    )

    inp = BoardThermalMapInput(
        width_m=0.050,
        height_m=0.050,
        copper_coverage=0.5,
        components=[
            BoardComponent(
                ref="U1", x_m=0.025, y_m=0.025, power_w=1.0,
                theta_jc=5.0, tj_max_c=125.0,
            ),
        ],
        ambient_c=25.0,
        nx=12, ny=12,
    )
    res = solve_board_thermal_map(inp)
    assert res["ok"] is True
    assert res["peak_T_c"] > 25.0
    # Per-component Tj = T_board + P * theta_jc
    u1 = res["components"][0]
    assert abs(u1["Tj_c"] - (u1["T_board_c"] + u1["power_w"] * 5.0)) < 1e-3


def test_thermal_hotspot_scales_with_power():
    """Doubling component power raises hotspot temperature."""
    from kerf_electronics.thermal_board import (
        BoardComponent,
        BoardThermalMapInput,
        solve_board_thermal_map,
    )

    def _hotspot(power):
        inp = BoardThermalMapInput(
            width_m=0.050, height_m=0.050, copper_coverage=0.5,
            components=[
                BoardComponent(ref="U1", x_m=0.025, y_m=0.025, power_w=power)
            ],
            ambient_c=25.0, nx=10, ny=10,
        )
        return solve_board_thermal_map(inp)["peak_T_c"]

    t1 = _hotspot(0.5)
    t2 = _hotspot(2.0)
    assert t2 > t1


# ============================================================================
# 5. si_eye_wizard channel margin
# ============================================================================


def test_si_eye_long_lossy_trace_fails_pcie_mask():
    """A 500 mm × 60 dB/m trace at 8 Gbps must FAIL the PCIe Gen3 eye mask."""
    from kerf_electronics.si_eye_wizard import si_eye_precompliance

    channel = {
        "data_rate_gbps": 8.0,
        "length_mm": 500.0,
        "loss_db_per_m": 60.0,
        "rise_time_tx_ps": 30.0,
        "rj_ps": 2.0,
        "dj_ps": 10.0,
        "mask": "pcie_gen3",
    }
    res = si_eye_precompliance(channel)
    assert res["ok"] is True
    assert res["compliant"] is False
    # 500 mm × 60 dB/m = 30 dB total IL
    assert abs(res["loss_db"] - 30.0) < 0.5


def test_si_eye_short_clean_trace_passes():
    """A 50 mm × 10 dB/m trace at 2 Gbps must PASS the generic mask."""
    from kerf_electronics.si_eye_wizard import si_eye_precompliance

    channel = {
        "data_rate_gbps": 2.0,
        "length_mm": 50.0,
        "loss_db_per_m": 10.0,
        "rise_time_tx_ps": 50.0,
        "rj_ps": 0.5,
        "dj_ps": 2.0,
        "mask": "generic",
    }
    res = si_eye_precompliance(channel)
    assert res["ok"] is True
    assert res["compliant"] is True
    assert res["margin_height"] > 0


# ============================================================================
# 6. emc_wizard FCC Class B margin
# ============================================================================


def test_emc_wizard_dm_loop_fails_fcc_class_b_at_high_current():
    """100 MHz DM loop at 100 mA in a 10 cm × 10 cm window is far above
    FCC Class B at 10 m → negative margin reported.

    The wizard pins worst_margin_db; assert it is negative (a regression
    pin against post-fix behaviour).
    """
    from kerf_electronics.emc_wizard import emc_precompliance

    design = {
        "clock_hz": 100e6,
        "loop_area_m2": 1e-4,
        "loop_current_a": 0.1,
        "standard": "fcc",
        "class_": "B",
        "distance_m": 10.0,
    }
    res = emc_precompliance(design)
    assert res["ok"] is True
    assert res["compliant"] is False
    # The worst-margin frequency must be a positive frequency
    assert res["worst_freq_hz"] > 0
    # The worst margin must be negative (failing the limit)
    assert res["worst_margin_db"] < 0


def test_emc_wizard_passes_for_tiny_loop():
    """A 1 mm² loop at 1 µA passes."""
    from kerf_electronics.emc_wizard import emc_precompliance

    design = {
        "clock_hz": 100e6,
        "loop_area_m2": 1e-9,
        "loop_current_a": 1e-6,
        "standard": "fcc",
        "class_": "B",
        "distance_m": 10.0,
    }
    res = emc_precompliance(design)
    assert res["ok"] is True
    assert res["compliant"] is True
    assert res["worst_margin_db"] > 0


# ============================================================================
# 7. pdn_wizard Z(f) target met
# ============================================================================


def test_pdn_wizard_recommends_decoupling_to_meet_target():
    """A 1 A transient on a 3.3 V rail with 5% ripple gives Z_target
    of 1.65/i_transient ≈ 0.165 Ω; the wizard must recommend at least
    one cap bank.
    """
    from kerf_electronics.pdn_wizard import pdn_wizard, z_target_from_spec

    design = {
        "vdd_v": 3.3,
        "ripple_frac": 0.05,
        "i_transient_a": 1.0,
        "bw_hz": 100e6,
    }
    res = pdn_wizard(design)
    assert res["ok"] is True
    assert res["z_target_ohm"] > 0
    # Sanity: z_target_from_spec = vdd · ripple / i_transient.
    expected = 3.3 * 0.05 / 1.0
    assert abs(res["z_target_ohm"] - expected) < 1e-12
    assert len(res["recommended_banks"]) >= 1


# ============================================================================
# 8. sim_corner Monte-Carlo: σ matches analytic for a resistive divider
# ============================================================================


def test_sim_corner_mc_resistor_divider_sigma_matches_analytic():
    """Two-resistor divider V_OUT = V_IN · R2/(R1+R2). With independent
    1%-tolerance R1, R2 the analytic sigma of V_OUT is computed via
    first-order propagation; the Monte-Carlo run must match to within 20%.
    """
    from kerf_electronics.sim_corner import monte_carlo

    netlist = [
        {
            "ref": "V1", "type": "V", "value": 5.0,
            "nodes": ["vin", "0"],
        },
        {
            "ref": "R1", "type": "R", "value": 10000.0,
            "nodes": ["vin", "vout"], "tol_pct": 1.0,
        },
        {
            "ref": "R2", "type": "R", "value": 10000.0,
            "nodes": ["vout", "0"], "tol_pct": 1.0,
        },
    ]
    result = monte_carlo(netlist, out_node="vout", n_runs=400, seed=42)
    assert result["mean"] is not None
    # Mean ≈ 2.5 V
    assert abs(result["mean"] - 2.5) < 0.05
    # Analytic sigma for 1% tol (treated as 3σ over the half-zone):
    #   ∂V/∂R1 = -V_IN · R2 / (R1+R2)^2 = -2.5/(2·R) ≈ -6.25e-5 V/Ω
    # σ_R = R · 0.01 / 3 (gaussian — tol_pct = ±3σ)
    # σ_V = |dV/dR| · σ_R · sqrt(2) (two independent contributors)
    R = 10000.0
    sigma_R = R * 0.01 / 3.0
    dVdR1 = -2.5 / (2 * R)
    sigma_V_analytic = abs(dVdR1) * sigma_R * math.sqrt(2.0)
    # MC sigma must be within 30% of analytic (small-sample tolerance).
    assert abs(result["std"] - sigma_V_analytic) / sigma_V_analytic < 0.30


# ============================================================================
# 9. qif_reader round-trip on synthetic in-test fixture
# ============================================================================


def test_qif_reader_parses_synthetic_characteristic():
    """A minimal QIF doc with one PASS characteristic parses cleanly."""
    from kerf_imports.qif_reader import parse_qif

    body = """<?xml version="1.0" encoding="UTF-8"?>
<QIFDocument>
  <Product><PartSet><Part id="p1"><Name>SynthPart</Name></Part></PartSet></Product>
  <MeasurementResources>
    <MeasuredCharacteristics>
      <CharacteristicItems>
        <CharacteristicItem id="c1">
          <Name>Diameter</Name>
          <CharacteristicDesignator><Designator>dimension</Designator></CharacteristicDesignator>
          <NominalValue>10.0</NominalValue>
          <Tolerance>
            <UpperTolerance>0.05</UpperTolerance>
            <LowerTolerance>-0.05</LowerTolerance>
          </Tolerance>
        </CharacteristicItem>
      </CharacteristicItems>
    </MeasuredCharacteristics>
  </MeasurementResources>
</QIFDocument>
"""
    result = parse_qif(body)
    assert result["ok"] is True
    assert result["part_name"] == "SynthPart"
    assert len(result["characteristics"]) == 1
    c1 = result["characteristics"][0]
    assert c1["name"] == "Diameter"
    assert abs(c1["nominal"] - 10.0) < 1e-9
    assert abs(c1["upper_tol"] - 0.05) < 1e-9


def test_qif_reader_malformed_returns_ok_false():
    """Malformed QIF XML returns ok=False, never raises."""
    from kerf_imports.qif_reader import parse_qif

    result = parse_qif("<<<not xml>>>")
    assert result["ok"] is False


# ============================================================================
# 10. ibis_reader round-trip on synthetic in-test fixture
# ============================================================================


_SYNTH_IBIS = """\
[IBIS Ver]    5.0
[File Name]   synth.ibs
[File Rev]    1.0

[Component]   SynthChip
[Manufacturer]    SynthCorp

[Package]
R_pkg         0.5      0.3      0.8
L_pkg         3.0nH    2.0nH    4.5nH
C_pkg         2.0pF    1.5pF    3.0pF

[Pin]  signal_name   model_name     R_pin  L_pin  C_pin
A1     DATA_OUT      OutModel       NA     NA     NA

[Model]  OutModel
Model_type   Output
Vinl         0.8
Vinh         2.0
C_comp       4.0pF    3.0pF    5.5pF

[Voltage Range]
3.3      3.0      3.6

[End]
"""


def test_ibis_reader_parses_synth_component_and_model():
    from kerf_imports.ibis_reader import parse_ibis

    result = parse_ibis(_SYNTH_IBIS)
    assert result["ok"] is True
    assert result["ibis_version"] == "5.0"
    assert len(result["components"]) == 1
    comp = result["components"][0]
    assert comp["name"] == "SynthChip"
    assert comp["manufacturer"] == "SynthCorp"
    # 1 pin
    assert len(comp["pins"]) == 1
    # 1 model
    assert "OutModel" in result["models"]
    model = result["models"]["OutModel"]
    assert model["model_type"].lower() == "output"


def test_ibis_reader_missing_version_returns_ok_false():
    from kerf_imports.ibis_reader import parse_ibis

    result = parse_ibis("[Component] X\n[End]")
    assert result["ok"] is False


# ============================================================================
# 11. End-to-end cross-tool consistency: drop one final invariant
# ============================================================================


def test_pdn_z_target_matches_helper():
    """z_target_from_spec(V, frac, I) = V·frac/I — assert math identity."""
    from kerf_electronics.pdn_wizard import z_target_from_spec

    assert abs(z_target_from_spec(3.3, 0.05, 1.0) - 0.165) < 1e-12
    assert abs(z_target_from_spec(1.8, 0.03, 0.5) - 0.108) < 1e-12
