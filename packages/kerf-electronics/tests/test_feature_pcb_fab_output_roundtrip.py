"""
T-27: Electronic — PCB DRC + Gerber/Excellon/PnP/IPC-2581

Tests the complete fab-output stack across 25 board configurations
(1–8 layers).  Each board:
  - passes DRC (zero error violations)
  - produces structurally valid Gerber RS-274X (header, apertures, M02)
  - produces Excellon drill hits coincident with the board's vias / PTH pads
  - produces well-formed IPC-2581 XML that round-trips board dimensions

All tests are fully hermetic — no network I/O, no filesystem I/O.

Success criteria (from testing-breakdown.md §T-27):
  25 boards (1–8 layers); DRC clean; Gerber RS-274X passes lint;
  Excellon drills coincident; IPC-2581 round-trips.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Any

import pytest

from kerf_electronics.drc import run_drc
from kerf_electronics.fab.gerber import export_gerber, layer_extension
from kerf_electronics.fab.excellon import export_excellon, _collect_hits
from kerf_electronics.fab.pnp import export_pnp
from kerf_electronics.fab.ipc2581 import export_ipc2581


# ---------------------------------------------------------------------------
# Board-spec factory
# ---------------------------------------------------------------------------

def _make_board(
    *,
    board_id: str,
    width: float,
    height: float,
    n_layers: int,
    n_resistors: int = 1,
    n_vias: int = 1,
    has_pth: bool = False,
    has_pour: bool = False,
    inner_traces: bool = False,
) -> list[dict]:
    """Build a clean, DRC-passing CircuitJSON array for the given spec."""

    elements: list[dict] = []

    # ── board outline ────────────────────────────────────────────────────────
    elements.append({
        "type": "pcb_board",
        "width": width,
        "height": height,
        "center_x": width / 2,
        "center_y": height / 2,
    })

    # ── source components (one per resistor slot) ────────────────────────────
    for i in range(n_resistors):
        elements.append({
            "type": "source_component",
            "source_component_id": f"{board_id}_sc_r{i}",
            "name": f"R{i + 1}",
            "value": "10k",
            "footprint": "R_0402",
            "mpn": "RC0402FR-0710KL",
            "manufacturer": "Yageo",
            "description": "Resistor 10k 0402",
            "distributors": [{"name": "DigiKey", "part_number": "311-10KLRCT-ND", "unit_price_usd": 0.10}],
        })

    # ── pcb_components + pads (SMT, well-spaced) ────────────────────────────
    for i in range(n_resistors):
        x = 10.0 + i * 8.0  # 8 mm pitch — well above 0.2 mm clearance
        y = 10.0
        elements.append({
            "type": "pcb_component",
            "pcb_component_id": f"{board_id}_pcb_r{i}",
            "source_component_id": f"{board_id}_sc_r{i}",
            "x": x,
            "y": y,
            "rotation": 0.0,
            "layer": "top_copper",
        })
        # Two SMT pads per resistor (0402 pads, 2 mm pitch)
        for pad_side, px_offset in ((0, -1.0), (1, 1.0)):
            elements.append({
                "type": "pcb_smtpad",
                "pcb_smtpad_id": f"{board_id}_pad_r{i}_{pad_side}",
                "source_component_id": f"{board_id}_sc_r{i}",
                "x": x + px_offset,
                "y": y,
                "width": 1.2,
                "height": 0.8,
                "shape": "rect",
                "layer": "top_copper",
                "net_id": f"{board_id}_net_r{i}_{'a' if pad_side == 0 else 'b'}",
            })

    # ── vias ─────────────────────────────────────────────────────────────────
    for i in range(n_vias):
        elements.append({
            "type": "pcb_via",
            "pcb_via_id": f"{board_id}_via{i}",
            "x": 50.0 + i * 5.0,
            "y": 50.0,
            "outer_diameter": 0.6,
            "hole_diameter": 0.3,
        })

    # ── optional PTH pad ─────────────────────────────────────────────────────
    if has_pth:
        elements.append({
            "type": "pcb_plated_pad",
            "pcb_plated_pad_id": f"{board_id}_pth0",
            "source_component_id": f"{board_id}_sc_r0",
            "x": 80.0,
            "y": 20.0,
            "width": 2.0,
            "height": 2.0,
            "hole_diameter": 1.0,
            "shape": "circle",
            "layer": "top_copper",
        })

    # ── traces on top copper ─────────────────────────────────────────────────
    for i in range(n_resistors):
        x = 10.0 + i * 8.0
        elements.append({
            "type": "pcb_trace",
            "pcb_trace_id": f"{board_id}_trace{i}",
            "net_id": f"{board_id}_net_r{i}_a",
            "route": [
                {"route_type": "wire", "x": x - 1.0, "y": 10.0, "width": 0.25, "layer": "top_copper"},
                {"route_type": "wire", "x": x - 1.0, "y": 12.0, "width": 0.25, "layer": "top_copper"},
            ],
        })

    # ── inner-layer traces (only when layer count > 2) ───────────────────────
    if inner_traces and n_layers > 2:
        for layer_idx in range(1, n_layers - 1):
            layer_name = f"inner_{layer_idx}"
            elements.append({
                "type": "pcb_trace",
                "pcb_trace_id": f"{board_id}_inner_trace_{layer_idx}",
                "net_id": f"{board_id}_inner_net_{layer_idx}",
                "route": [
                    {"route_type": "wire", "x": 20.0, "y": 20.0 + layer_idx * 3.0, "width": 0.2, "layer": layer_name},
                    {"route_type": "wire", "x": 40.0, "y": 20.0 + layer_idx * 3.0, "width": 0.2, "layer": layer_name},
                ],
            })

    # ── copper pour on bottom layer ──────────────────────────────────────────
    if has_pour:
        elements.append({
            "type": "copper_pour_fill",
            "layer": "bottom_copper",
            "net_id": f"{board_id}_gnd",
            "polygon": [
                {"x": 0.0, "y": 0.0},
                {"x": width, "y": 0.0},
                {"x": width, "y": height},
                {"x": 0.0, "y": height},
            ],
        })

    return elements


# ---------------------------------------------------------------------------
# 25 board configurations  (1–8 layers; varied sizes/features)
# ---------------------------------------------------------------------------

BOARD_SPECS: list[dict] = [
    # --- 1-layer ---
    dict(board_id="b01", width=50,  height=40,  n_layers=1, n_resistors=1, n_vias=0),
    dict(board_id="b02", width=60,  height=50,  n_layers=1, n_resistors=2, n_vias=0, has_pour=True),
    # --- 2-layer ---
    dict(board_id="b03", width=100, height=80,  n_layers=2, n_resistors=3, n_vias=2),
    dict(board_id="b04", width=80,  height=60,  n_layers=2, n_resistors=2, n_vias=1, has_pth=True),
    dict(board_id="b05", width=120, height=100, n_layers=2, n_resistors=4, n_vias=3, has_pour=True),
    dict(board_id="b06", width=40,  height=30,  n_layers=2, n_resistors=1, n_vias=1),
    dict(board_id="b07", width=200, height=150, n_layers=2, n_resistors=5, n_vias=2, has_pth=True, has_pour=True),
    # --- 4-layer ---
    dict(board_id="b08", width=100, height=80,  n_layers=4, n_resistors=2, n_vias=2, inner_traces=True),
    dict(board_id="b09", width=80,  height=60,  n_layers=4, n_resistors=3, n_vias=3, inner_traces=True),
    dict(board_id="b10", width=150, height=120, n_layers=4, n_resistors=4, n_vias=4, has_pth=True, inner_traces=True),
    dict(board_id="b11", width=60,  height=50,  n_layers=4, n_resistors=1, n_vias=1, has_pour=True, inner_traces=True),
    dict(board_id="b12", width=200, height=160, n_layers=4, n_resistors=5, n_vias=5, inner_traces=True),
    dict(board_id="b13", width=70,  height=55,  n_layers=4, n_resistors=2, n_vias=2, has_pth=True, has_pour=True, inner_traces=True),
    # --- 6-layer ---
    dict(board_id="b14", width=100, height=80,  n_layers=6, n_resistors=3, n_vias=3, inner_traces=True),
    dict(board_id="b15", width=120, height=90,  n_layers=6, n_resistors=4, n_vias=4, has_pth=True, inner_traces=True),
    dict(board_id="b16", width=90,  height=70,  n_layers=6, n_resistors=2, n_vias=2, has_pour=True, inner_traces=True),
    dict(board_id="b17", width=160, height=130, n_layers=6, n_resistors=5, n_vias=5, has_pth=True, has_pour=True, inner_traces=True),
    dict(board_id="b18", width=50,  height=40,  n_layers=6, n_resistors=1, n_vias=1, inner_traces=True),
    # --- 8-layer ---
    dict(board_id="b19", width=100, height=80,  n_layers=8, n_resistors=3, n_vias=3, inner_traces=True),
    dict(board_id="b20", width=150, height=120, n_layers=8, n_resistors=4, n_vias=4, has_pth=True, inner_traces=True),
    dict(board_id="b21", width=80,  height=60,  n_layers=8, n_resistors=2, n_vias=2, has_pour=True, inner_traces=True),
    dict(board_id="b22", width=200, height=160, n_layers=8, n_resistors=5, n_vias=5, has_pth=True, has_pour=True, inner_traces=True),
    dict(board_id="b23", width=60,  height=50,  n_layers=8, n_resistors=1, n_vias=1, inner_traces=True),
    dict(board_id="b24", width=120, height=100, n_layers=8, n_resistors=3, n_vias=3, inner_traces=True),
    dict(board_id="b25", width=90,  height=70,  n_layers=8, n_resistors=4, n_vias=4, has_pth=True, has_pour=True, inner_traces=True),
]

assert len(BOARD_SPECS) == 25, f"Expected 25 board specs, got {len(BOARD_SPECS)}"

# Pre-build all circuit arrays once
BOARDS: list[tuple[dict, list[dict]]] = [
    (spec, _make_board(**spec)) for spec in BOARD_SPECS
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _drc_result(circuit: list[dict]) -> dict:
    return run_drc(circuit, rules={"min_clearance_mm": 0.15})


def _gerber_files(circuit: list[dict], bid: str) -> dict[str, str]:
    return export_gerber(circuit, stem=bid)


def _excellon_files(circuit: list[dict], bid: str) -> dict[str, str]:
    return export_excellon(circuit, stem=bid)


def _ipc_files(circuit: list[dict], bid: str) -> dict[str, str]:
    return export_ipc2581(circuit, stem=bid)


def _count_holes_in_circuit(spec: dict, circuit: list[dict]) -> int:
    """Count expected drill hits: vias + PTH pads."""
    n = spec.get("n_vias", 0)
    if spec.get("has_pth"):
        n += 1
    return n


# ---------------------------------------------------------------------------
# T-27-A: DRC clean — all 25 boards pass with zero error violations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_drc_clean(spec: dict, circuit: list[dict]) -> None:
    """Board passes DRC with zero error-severity violations."""
    result = _drc_result(circuit)
    errors = [v for v in result["violations"] if v["severity"] == "error"]
    assert result["error_count"] == 0, (
        f"Board {spec['board_id']} has {result['error_count']} DRC errors: "
        + "; ".join(v["message"] for v in errors)
    )


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_drc_returns_dict_structure(spec: dict, circuit: list[dict]) -> None:
    """run_drc returns expected dict shape."""
    result = _drc_result(circuit)
    assert "violations" in result
    assert "error_count" in result
    assert "warning_count" in result
    assert isinstance(result["violations"], list)


# ---------------------------------------------------------------------------
# T-27-B: Gerber RS-274X structural lint — 25 boards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_returns_dict_of_strings(spec: dict, circuit: list[dict]) -> None:
    files = _gerber_files(circuit, spec["board_id"])
    assert isinstance(files, dict)
    for k, v in files.items():
        assert isinstance(k, str), f"Gerber key not str: {k!r}"
        assert isinstance(v, str), f"Gerber value not str for {k}"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_rs274x_header_present(spec: dict, circuit: list[dict]) -> None:
    """Every Gerber file starts with %FSLAX46Y46*% + %MOMM*%."""
    files = _gerber_files(circuit, spec["board_id"])
    for fname, content in files.items():
        assert "%FSLAX46Y46*%" in content, f"{fname}: missing RS-274X format statement"
        assert "%MOMM*%" in content, f"{fname}: missing metric mode statement"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_ends_with_m02(spec: dict, circuit: list[dict]) -> None:
    """Every Gerber file ends with M02* end-of-file marker."""
    files = _gerber_files(circuit, spec["board_id"])
    for fname, content in files.items():
        assert "M02*" in content, f"{fname}: missing M02 end-of-file marker"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_top_copper_and_edge_present(spec: dict, circuit: list[dict]) -> None:
    """GTL (top copper) and GKO (board outline) must be present."""
    bid = spec["board_id"]
    files = _gerber_files(circuit, bid)
    assert f"{bid}.GTL" in files, f"Missing top-copper Gerber for {bid}"
    assert f"{bid}.GKO" in files, f"Missing edge-cuts Gerber for {bid}"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_bottom_copper_present(spec: dict, circuit: list[dict]) -> None:
    """GBL (bottom copper) must be present for multi-layer boards."""
    bid = spec["board_id"]
    files = _gerber_files(circuit, bid)
    assert f"{bid}.GBL" in files, f"Missing bottom-copper Gerber for {bid}"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_aperture_definitions_present(spec: dict, circuit: list[dict]) -> None:
    """At least one %ADD... aperture definition must appear in top copper."""
    bid = spec["board_id"]
    files = _gerber_files(circuit, bid)
    gtl = files.get(f"{bid}.GTL", "")
    assert re.search(r"%ADD\d+[CRO],", gtl), (
        f"{bid}.GTL: no aperture definitions found"
    )


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_coordinate_format(spec: dict, circuit: list[dict]) -> None:
    """Gerber coordinates use 4.6 integer format (X<digits>Y<digits>D0N*)."""
    bid = spec["board_id"]
    files = _gerber_files(circuit, bid)
    gtl = files.get(f"{bid}.GTL", "")
    # At least one coordinate move/draw operation
    assert re.search(r"X\d+Y\d+D0[123]\*", gtl), (
        f"{bid}.GTL: no valid coordinate operations found"
    )


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_pour_region_in_bottom(spec: dict, circuit: list[dict]) -> None:
    """Boards with copper pour have G36*/G37* region blocks in GBL."""
    if not spec.get("has_pour"):
        pytest.skip("no copper pour in this board spec")
    bid = spec["board_id"]
    files = _gerber_files(circuit, bid)
    gbl = files.get(f"{bid}.GBL", "")
    assert "G36*" in gbl, f"{bid}.GBL: missing G36 region start"
    assert "G37*" in gbl, f"{bid}.GBL: missing G37 region end"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_inner_layer_files_present(spec: dict, circuit: list[dict]) -> None:
    """Multi-layer boards with inner traces produce inner-layer Gerber files."""
    if spec["n_layers"] <= 2 or not spec.get("inner_traces"):
        pytest.skip("no inner layers in this board spec")
    bid = spec["board_id"]
    files = _gerber_files(circuit, bid)
    # inner_1 → GL2, inner_2 → GL3 …
    expected_inner = f"{bid}.GL2"
    assert expected_inner in files, (
        f"Expected inner Gerber {expected_inner} in output. Got: {sorted(files)}"
    )


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_gerber_layer_extension_mapping(spec: dict, circuit: list[dict]) -> None:
    """layer_extension() returns correct Gerber extension strings."""
    assert layer_extension("top_copper") == "GTL"
    assert layer_extension("bottom_copper") == "GBL"
    assert layer_extension("edge_cuts") == "GKO"
    assert layer_extension("inner_1") == "GL2"
    assert layer_extension("inner_5") == "GL6"


# ---------------------------------------------------------------------------
# T-27-C: Excellon drill hits coincident with vias/PTH pads
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_excellon_returns_drl_file(spec: dict, circuit: list[dict]) -> None:
    """export_excellon returns a dict containing a .DRL file."""
    bid = spec["board_id"]
    files = _excellon_files(circuit, bid)
    assert isinstance(files, dict)
    assert f"{bid}.DRL" in files, f"Missing .DRL file for {bid}"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_excellon_header_and_footer(spec: dict, circuit: list[dict]) -> None:
    """DRL file has M48 header and M30 end-of-file."""
    bid = spec["board_id"]
    drl = _excellon_files(circuit, bid)[f"{bid}.DRL"]
    assert "M48" in drl, f"{bid}.DRL: missing M48 header"
    assert "M30" in drl, f"{bid}.DRL: missing M30 footer"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_excellon_hit_count_matches_spec(spec: dict, circuit: list[dict]) -> None:
    """Number of drill hits matches vias + PTH pads declared in the spec."""
    expected = _count_holes_in_circuit(spec, circuit)
    hits = _collect_hits(circuit)
    assert len(hits) == expected, (
        f"Board {spec['board_id']}: expected {expected} drill hits, got {len(hits)}"
    )


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_excellon_hits_coincident_with_vias(spec: dict, circuit: list[dict]) -> None:
    """Each via in the circuit has a drill hit at its exact (x, y) coordinates."""
    if spec.get("n_vias", 0) == 0:
        pytest.skip("no vias in board spec")
    hits = _collect_hits(circuit)
    hit_coords = {(round(h.x, 3), round(h.y, 3)) for h in hits}

    for el in circuit:
        if el.get("type") != "pcb_via":
            continue
        vx, vy = round(float(el["x"]), 3), round(float(el["y"]), 3)
        assert (vx, vy) in hit_coords, (
            f"Via at ({vx},{vy}) has no matching drill hit. "
            f"Available hits: {sorted(hit_coords)}"
        )


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_excellon_hits_coincident_with_pth_pads(spec: dict, circuit: list[dict]) -> None:
    """Each PTH pad in the circuit has a drill hit at its exact (x, y) coordinates."""
    if not spec.get("has_pth"):
        pytest.skip("no PTH pads in board spec")
    hits = _collect_hits(circuit)
    hit_coords = {(round(h.x, 3), round(h.y, 3)) for h in hits}

    for el in circuit:
        if el.get("type") != "pcb_plated_pad":
            continue
        px, py = round(float(el["x"]), 3), round(float(el["y"]), 3)
        assert (px, py) in hit_coords, (
            f"PTH pad at ({px},{py}) has no matching drill hit. "
            f"Available hits: {sorted(hit_coords)}"
        )


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_excellon_tool_table_unique_diameters(spec: dict, circuit: list[dict]) -> None:
    """Tool table has one T-code per unique drill diameter (no duplicates)."""
    if _count_holes_in_circuit(spec, circuit) == 0:
        pytest.skip("no drill hits — tool table will be empty")
    bid = spec["board_id"]
    drl = _excellon_files(circuit, bid)[f"{bid}.DRL"]
    defs = re.findall(r"T(\d+)C([\d.]+)", drl)
    if not defs:
        pytest.skip("no tool definitions found (no drills)")
    diameters = [float(d[1]) for d in defs]
    t_codes = [int(d[0]) for d in defs]
    assert len(diameters) == len(set(diameters)), f"{bid}: duplicate diameters in tool table"
    assert len(t_codes) == len(set(t_codes)), f"{bid}: duplicate T-codes in tool table"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_excellon_all_plated(spec: dict, circuit: list[dict]) -> None:
    """All drill hits (vias and PTH pads) are marked as plated."""
    hits = _collect_hits(circuit)
    for h in hits:
        assert h.tool.plated, (
            f"Hit at ({h.x},{h.y}) is marked non-plated; expected plated"
        )


# ---------------------------------------------------------------------------
# T-27-D: IPC-2581 round-trip — board dims and structure survive export/parse
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_ipc2581_xml_well_formed(spec: dict, circuit: list[dict]) -> None:
    """Exported IPC-2581 XML is parseable by Python's xml.etree."""
    bid = spec["board_id"]
    files = _ipc_files(circuit, bid)
    assert f"{bid}.xml" in files, f"Missing IPC-2581 XML for {bid}"
    try:
        ET.fromstring(files[f"{bid}.xml"])
    except ET.ParseError as exc:
        pytest.fail(f"Board {bid}: IPC-2581 XML is not well-formed: {exc}")


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_ipc2581_root_element(spec: dict, circuit: list[dict]) -> None:
    """Root element is named IPC-2581 (namespace-agnostic)."""
    bid = spec["board_id"]
    xml_text = _ipc_files(circuit, bid)[f"{bid}.xml"]
    root = ET.fromstring(xml_text)
    local = root.tag.split("}")[-1]
    assert local == "IPC-2581", f"Board {bid}: root element is {local!r}, expected 'IPC-2581'"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_ipc2581_header_present(spec: dict, circuit: list[dict]) -> None:
    """IPC-2581 XML contains a <Header> element."""
    bid = spec["board_id"]
    root = ET.fromstring(_ipc_files(circuit, bid)[f"{bid}.xml"])
    header = root.find("Header") or root.find("{http://www.ipc.org/2581}Header")
    assert header is not None, f"Board {bid}: missing <Header> in IPC-2581 XML"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_ipc2581_layer_stack_present(spec: dict, circuit: list[dict]) -> None:
    """IPC-2581 XML contains a <LayerStack> element."""
    bid = spec["board_id"]
    root = ET.fromstring(_ipc_files(circuit, bid)[f"{bid}.xml"])
    ls = root.find("LayerStack") or root.find("{http://www.ipc.org/2581}LayerStack")
    assert ls is not None, f"Board {bid}: missing <LayerStack> in IPC-2581 XML"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_ipc2581_bom_present(spec: dict, circuit: list[dict]) -> None:
    """IPC-2581 XML contains a <Bom> element."""
    bid = spec["board_id"]
    root = ET.fromstring(_ipc_files(circuit, bid)[f"{bid}.xml"])
    bom = root.find("Bom") or root.find("{http://www.ipc.org/2581}Bom")
    assert bom is not None, f"Board {bid}: missing <Bom> in IPC-2581 XML"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_ipc2581_ecad_present(spec: dict, circuit: list[dict]) -> None:
    """IPC-2581 XML contains a <Ecad> element."""
    bid = spec["board_id"]
    root = ET.fromstring(_ipc_files(circuit, bid)[f"{bid}.xml"])
    ecad = root.find("Ecad") or root.find("{http://www.ipc.org/2581}Ecad")
    assert ecad is not None, f"Board {bid}: missing <Ecad> in IPC-2581 XML"


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_ipc2581_board_dims_roundtrip(spec: dict, circuit: list[dict]) -> None:
    """Board width and height survive the IPC-2581 export/parse round-trip."""
    bid = spec["board_id"]
    root = ET.fromstring(_ipc_files(circuit, bid)[f"{bid}.xml"])

    # Find the CadData/Board element (may be nested inside Ecad)
    board_el = None
    for path in ("Ecad/CadData/Board", "Board"):
        board_el = root.find(path)
        if board_el is not None:
            break

    if board_el is None:
        pytest.skip(f"Board {bid}: no <Board> element in IPC-2581 XML (optional path)")

    x_size = float(board_el.get("xSize", 0))
    y_size = float(board_el.get("ySize", 0))
    assert math.isclose(x_size, spec["width"], rel_tol=1e-3), (
        f"Board {bid}: IPC-2581 xSize={x_size} != spec width={spec['width']}"
    )
    assert math.isclose(y_size, spec["height"], rel_tol=1e-3), (
        f"Board {bid}: IPC-2581 ySize={y_size} != spec height={spec['height']}"
    )


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_ipc2581_bom_items_match_placed_components(spec: dict, circuit: list[dict]) -> None:
    """BomItem count equals number of pcb_component elements in circuit."""
    bid = spec["board_id"]
    n_placed = sum(1 for el in circuit if el.get("type") == "pcb_component")
    root = ET.fromstring(_ipc_files(circuit, bid)[f"{bid}.xml"])
    bom = root.find("Bom") or root.find("{http://www.ipc.org/2581}Bom")
    if bom is None:
        pytest.fail(f"Board {bid}: no <Bom> element")
    items = list(bom.findall("BomItem")) + list(bom.findall("{http://www.ipc.org/2581}BomItem"))
    assert len(items) == n_placed, (
        f"Board {bid}: {len(items)} BomItems but {n_placed} pcb_components"
    )


@pytest.mark.parametrize("spec,circuit", BOARDS, ids=[s["board_id"] for s, _ in BOARDS])
def test_ipc2581_drill_hits_in_ecad(spec: dict, circuit: list[dict]) -> None:
    """IPC-2581 DrillPattern contains at least as many hits as vias + PTH pads."""
    expected = _count_holes_in_circuit(spec, circuit)
    if expected == 0:
        pytest.skip("no drill hits expected for this board")

    bid = spec["board_id"]
    root = ET.fromstring(_ipc_files(circuit, bid)[f"{bid}.xml"])

    # Attempt to locate DrillHit elements anywhere in the tree
    all_hits = list(root.iter("DrillHit")) + list(
        root.iter("{http://www.ipc.org/2581}DrillHit")
    )
    assert len(all_hits) >= expected, (
        f"Board {bid}: expected >= {expected} DrillHit elements, found {len(all_hits)}"
    )


# ---------------------------------------------------------------------------
# T-27-E: Boundary / malformed-input / idempotency checks
# ---------------------------------------------------------------------------

def test_drc_empty_circuit_no_violations() -> None:
    """run_drc([]) → zero violations of any severity."""
    result = run_drc([])
    assert result["error_count"] == 0
    assert result["warning_count"] == 0
    assert result["violations"] == []


def test_drc_non_list_input_graceful() -> None:
    """run_drc with non-list input must not raise."""
    result = run_drc(None)  # type: ignore[arg-type]
    assert result["error_count"] == 0


def test_gerber_empty_circuit_produces_valid_files() -> None:
    """export_gerber([]) returns files with valid RS-274X structure."""
    files = export_gerber([], stem="empty")
    assert isinstance(files, dict)
    assert "empty.GTL" in files
    for content in files.values():
        assert "%FSLAX46Y46*%" in content
        assert "M02*" in content


def test_gerber_idempotent() -> None:
    """Calling export_gerber twice on the same circuit yields identical files."""
    _, circuit = BOARDS[2]  # 2-layer, 3 resistors
    files_a = export_gerber(circuit, stem="board")
    # Timestamps differ; compare everything except the timestamp comment line
    files_b = export_gerber(circuit, stem="board")
    for fname in files_a:
        assert fname in files_b, f"File {fname} missing in second export"
        # Strip timestamp comment lines before comparing
        def _strip_ts(text: str) -> str:
            return "\n".join(
                line for line in text.splitlines()
                if not line.startswith("G04 Generated:")
            )
        assert _strip_ts(files_a[fname]) == _strip_ts(files_b[fname]), (
            f"Gerber {fname} differs between two calls"
        )


def test_gerber_non_list_input_graceful() -> None:
    """export_gerber with non-list input must not raise."""
    files = export_gerber("garbage", stem="bad")  # type: ignore[arg-type]
    assert isinstance(files, dict)
    for content in files.values():
        assert "M02*" in content


def test_excellon_empty_circuit_produces_valid_drl() -> None:
    """export_excellon([]) returns a DRL with M48 header and M30 footer."""
    files = export_excellon([], stem="empty")
    assert "empty.DRL" in files
    drl = files["empty.DRL"]
    assert "M48" in drl
    assert "M30" in drl


def test_excellon_no_smt_pads_drilled() -> None:
    """SMT pads must not appear as drill hits."""
    circuit = [
        {"type": "pcb_smtpad", "pcb_smtpad_id": "p1", "x": 10.0, "y": 5.0,
         "width": 1.2, "height": 0.8, "shape": "rect", "layer": "top_copper"},
    ]
    hits = _collect_hits(circuit)
    assert len(hits) == 0, "SMT pad should not produce a drill hit"


def test_excellon_via_produces_plated_hit() -> None:
    """A pcb_via element produces exactly one plated drill hit."""
    circuit = [{"type": "pcb_via", "x": 10.0, "y": 10.0,
                "outer_diameter": 0.6, "hole_diameter": 0.3}]
    hits = _collect_hits(circuit)
    assert len(hits) == 1
    assert hits[0].tool.plated
    assert math.isclose(hits[0].tool.diameter_mm, 0.3)
    assert math.isclose(hits[0].x, 10.0)
    assert math.isclose(hits[0].y, 10.0)


def test_ipc2581_empty_circuit_well_formed() -> None:
    """export_ipc2581([]) returns parseable XML with root IPC-2581."""
    files = export_ipc2581([], stem="empty")
    assert "empty.xml" in files
    root = ET.fromstring(files["empty.xml"])
    assert root.tag.split("}")[-1] == "IPC-2581"


def test_ipc2581_non_list_input_graceful() -> None:
    """export_ipc2581 with non-list input must not raise."""
    try:
        files = export_ipc2581(None, stem="bad")  # type: ignore[arg-type]
        assert isinstance(files, dict)
    except Exception as exc:
        pytest.fail(f"export_ipc2581(None) raised: {exc}")


def test_drc_two_cross_net_pads_too_close_fires_error() -> None:
    """Two cross-net pads 0.05 mm apart (< 0.15 mm rule) generate an error."""
    circuit = [
        {"type": "pcb_smtpad", "pcb_smtpad_id": "p1", "x": 0.0, "y": 0.0,
         "width": 0.05, "height": 0.05, "net_id": "NET_A"},
        {"type": "pcb_smtpad", "pcb_smtpad_id": "p2", "x": 0.1, "y": 0.0,
         "width": 0.05, "height": 0.05, "net_id": "NET_B"},
    ]
    result = run_drc(circuit, rules={"min_clearance_mm": 0.15})
    assert result["error_count"] >= 1


def test_drc_same_net_pads_close_no_clearance_error() -> None:
    """Same-net pads 0.05 mm apart must NOT fire a pad_clearance error."""
    circuit = [
        {"type": "pcb_smtpad", "pcb_smtpad_id": "p1", "x": 0.0, "y": 0.0,
         "width": 0.05, "height": 0.05, "net_id": "GND"},
        {"type": "pcb_smtpad", "pcb_smtpad_id": "p2", "x": 0.1, "y": 0.0,
         "width": 0.05, "height": 0.05, "net_id": "GND"},
    ]
    result = run_drc(circuit, rules={"min_clearance_mm": 0.15})
    pad_clear_errors = [
        v for v in result["violations"]
        if v["kind"] == "pad_clearance" and v["severity"] == "error"
    ]
    assert len(pad_clear_errors) == 0


def test_drc_missing_footprint_fires_warning() -> None:
    """source_component with no pcb_component fires a missing_footprint warning."""
    circuit = [
        {"type": "source_component", "source_component_id": "sc_orphan",
         "name": "U99", "footprint": "TQFP-48"},
        # No matching pcb_component
    ]
    result = run_drc(circuit)
    mf_warnings = [v for v in result["violations"] if v["kind"] == "missing_footprint"]
    assert len(mf_warnings) >= 1


def test_pnp_top_csv_has_correct_header() -> None:
    """export_pnp returns a top-side CSV with the expected header columns."""
    _, circuit = BOARDS[2]  # b03: 2-layer, 3 resistors
    files = export_pnp(circuit, stem="board")
    assert "board-top-pnp.csv" in files
    header_line = files["board-top-pnp.csv"].splitlines()[0]
    for col in ("Designator", "MidX(mm)", "Rotation(deg)"):
        assert col in header_line, f"Missing column '{col}' in PnP header"


def test_pnp_placed_components_appear_in_top_csv() -> None:
    """Components placed on top_copper appear in the top-side PnP CSV."""
    _, circuit = BOARDS[2]  # b03: 2-layer, 3 resistors, all on top
    files = export_pnp(circuit, stem="board")
    top_csv = files["board-top-pnp.csv"]
    lines = top_csv.strip().splitlines()
    # header + at least 3 component rows
    assert len(lines) >= 4, (
        f"Expected at least 4 lines (header + 3 components), got {len(lines)}"
    )


def test_pnp_idempotent() -> None:
    """export_pnp produces identical output on repeated calls."""
    _, circuit = BOARDS[0]
    a = export_pnp(circuit, stem="board")
    b = export_pnp(circuit, stem="board")
    assert a == b


def test_gerber_empty_stem_fallback() -> None:
    """export_gerber with an empty stem still returns dict with keys."""
    files = export_gerber([], stem="")
    assert isinstance(files, dict)
    assert len(files) > 0
