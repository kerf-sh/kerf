"""
T-30: Electronic — 3D board STEP export + IDF MCAD

25 board scenarios spanning:
  - Pure resistor/capacitor boards (SMT only)
  - Boards with PTH components (through-hole)
  - Mixed top + bottom side placement
  - Boards with explicit polygon outlines (non-rectangular)
  - Boards with mounting holes
  - High-density boards (many components)
  - Minimal boards (no components, no holes)
  - Boards with various footprint families (connectors, BGAs, QFNs)

Success criteria (from testing-breakdown.md §T-30):
  - 25 boards
  - STEP solid valid (ISO-10303-21 header; non-empty file; substrate_volume > 0)
  - Component placement matches PnP: (x, y, rotation, side) agree
    between _collect_placed_components (used by board_step + IDF) and
    pnp._extract_components
  - IDF round-trip: export_idf → parse .emn outline → outline matches
    _board_outline_vertices; hole count matches; placement count matches

All tests are fully hermetic — no network, no filesystem I/O beyond tmp files.
STEP file tests are skipped automatically when pythonOCC is not installed.
"""
from __future__ import annotations

import os
import re
import tempfile
from copy import deepcopy
from typing import Any

import pytest

from kerf_electronics.fab.board_step import (
    _OCC_AVAILABLE,
    _board_outline_vertices,
    _collect_holes,
    _collect_placed_components,
)
from kerf_electronics.fab.pnp import _extract_components as pnp_extract
from kerf_electronics.tools.idf_export import export_idf


# ---------------------------------------------------------------------------
# Board factory helpers
# ---------------------------------------------------------------------------

def _src(sid: str, name: str, fp: str, value: str = "1k") -> dict:
    return {
        "type": "source_component",
        "source_component_id": sid,
        "name": name,
        "value": value,
        "footprint": fp,
    }


def _pcb(sid: str, x: float, y: float, rotation: float = 0.0,
         layer: str = "top_copper") -> dict:
    return {
        "type": "pcb_component",
        "pcb_component_id": f"pcb_{sid}",
        "source_component_id": sid,
        "x": x,
        "y": y,
        "rotation": rotation,
        "layer": layer,
    }


def _via(vid: str, x: float, y: float, d: float = 0.3) -> dict:
    return {
        "type": "pcb_via",
        "pcb_via_id": vid,
        "x": x,
        "y": y,
        "outer_diameter": d * 2,
        "hole_diameter": d,
    }


def _pth(pid: str, x: float, y: float, d: float = 0.8) -> dict:
    return {
        "type": "pcb_plated_pad",
        "pcb_plated_pad_id": pid,
        "x": x,
        "y": y,
        "width": 1.6,
        "height": 1.6,
        "hole_diameter": d,
        "shape": "circle",
        "layer": "top_copper",
    }


def _mhole(mid: str, x: float, y: float, d: float = 3.2) -> dict:
    return {
        "type": "pcb_mounting_hole",
        "pcb_mounting_hole_id": mid,
        "x": x,
        "y": y,
        "hole_diameter": d,
    }


def _board_rect(w: float, h: float) -> dict:
    return {
        "type": "pcb_board",
        "width": w,
        "height": h,
        "center_x": w / 2,
        "center_y": h / 2,
    }


def _board_polygon(vertices: list[tuple[float, float]]) -> dict:
    return {
        "type": "pcb_outline_path",
        "route": [{"x": x, "y": y} for x, y in vertices],
    }


# ---------------------------------------------------------------------------
# 25 board fixtures
# ---------------------------------------------------------------------------

def _make_board_01() -> list[dict]:
    """Simple 2-resistor SMT board, 50×30 mm."""
    cj = [_board_rect(50, 30)]
    cj += [_src("r1", "R1", "R_0402"), _src("r2", "R2", "R_0402")]
    cj += [_pcb("r1", 10, 10), _pcb("r2", 20, 10)]
    cj += [_via("v1", 5, 5), _via("v2", 45, 25)]
    return cj


def _make_board_02() -> list[dict]:
    """IC board with SOIC-8 and bypass caps, 60×40 mm."""
    cj = [_board_rect(60, 40)]
    cj += [
        _src("u1", "U1", "SOIC-8", "LM358"),
        _src("c1", "C1", "C_0402", "100nF"),
        _src("c2", "C2", "C_0402", "100nF"),
    ]
    cj += [
        _pcb("u1", 30, 20),
        _pcb("c1", 15, 20),
        _pcb("c2", 45, 20),
    ]
    cj += [_via("v1", 10, 10), _pth("pth1", 5, 35, 1.0)]
    return cj


def _make_board_03() -> list[dict]:
    """Microcontroller board with TQFP-32, 80×60 mm, mix of SMT and PTH."""
    cj = [_board_rect(80, 60)]
    cj += [
        _src("u1", "U1", "TQFP-32", "ATmega328P"),
        _src("r1", "R1", "R_0603", "10k"),
        _src("c1", "C1", "C_0805", "10uF"),
        _src("j1", "J1", "USB-C", "USB-C"),
    ]
    cj += [
        _pcb("u1", 40, 30),
        _pcb("r1", 10, 10, rotation=45),
        _pcb("c1", 70, 10),
        _pcb("j1", 40, 55),
    ]
    cj += [
        _via("v1", 5, 5), _via("v2", 75, 55),
        _pth("pth1", 5, 30, 1.0), _pth("pth2", 75, 30, 1.0),
        _mhole("mh1", 5, 5, 3.2), _mhole("mh2", 75, 55, 3.2),
    ]
    return cj


def _make_board_04() -> list[dict]:
    """Bottom-side populated board — all components on bottom_copper."""
    cj = [_board_rect(40, 30)]
    cj += [_src("r1", "R1", "R_0402"), _src("r2", "R2", "R_0603")]
    cj += [
        _pcb("r1", 10, 10, layer="bottom_copper"),
        _pcb("r2", 30, 20, layer="bottom_copper"),
    ]
    return cj


def _make_board_05() -> list[dict]:
    """Mixed top + bottom placement."""
    cj = [_board_rect(60, 50)]
    cj += [
        _src("r1", "R1", "R_0402"),
        _src("c1", "C1", "C_0402"),
        _src("u1", "U1", "QFN-16"),
        _src("r2", "R2", "R_0805"),
    ]
    cj += [
        _pcb("r1", 10, 10, layer="top_copper"),
        _pcb("c1", 25, 10, layer="bottom_copper"),
        _pcb("u1", 30, 25, layer="top_copper", rotation=90),
        _pcb("r2", 50, 40, layer="bottom_copper"),
    ]
    cj += [_via("v1", 5, 5), _via("v2", 55, 45)]
    return cj


def _make_board_06() -> list[dict]:
    """Explicit polygon outline (L-shaped board approximation, 5 vertices)."""
    verts = [(0, 0), (80, 0), (80, 40), (40, 40), (40, 80), (0, 80)]
    cj = [_board_polygon(verts)]
    cj += [_src("r1", "R1", "R_0402")]
    cj += [_pcb("r1", 20, 20)]
    return cj


def _make_board_07() -> list[dict]:
    """No components, no holes — minimal bare board."""
    return [_board_rect(100, 80)]


def _make_board_08() -> list[dict]:
    """High-density: 10 resistors in a line."""
    cj = [_board_rect(120, 20)]
    for i in range(10):
        sid = f"r{i}"
        cj.append(_src(sid, f"R{i+1}", "R_0402"))
        cj.append(_pcb(sid, 10 + i * 11, 10))
    cj.append(_via("v1", 5, 5))
    return cj


def _make_board_09() -> list[dict]:
    """BGA component + decoupling caps."""
    cj = [_board_rect(70, 70)]
    cj += [
        _src("u1", "U1", "BGA-64", "FPGA"),
        _src("c1", "C1", "C_0201"),
        _src("c2", "C2", "C_0201"),
        _src("c3", "C3", "C_0201"),
        _src("c4", "C4", "C_0201"),
    ]
    cj += [
        _pcb("u1", 35, 35),
        _pcb("c1", 20, 35),
        _pcb("c2", 50, 35),
        _pcb("c3", 35, 20),
        _pcb("c4", 35, 50),
    ]
    cj += [_via(f"v{i}", 5 + i * 5, 5) for i in range(8)]
    return cj


def _make_board_10() -> list[dict]:
    """All four mounting holes at corners."""
    cj = [_board_rect(100, 80)]
    cj += [
        _mhole("mh1", 5, 5, 3.2),
        _mhole("mh2", 95, 5, 3.2),
        _mhole("mh3", 95, 75, 3.2),
        _mhole("mh4", 5, 75, 3.2),
    ]
    cj += [_src("u1", "U1", "SOIC-16"), _pcb("u1", 50, 40)]
    return cj


def _make_board_11() -> list[dict]:
    """Thin board (0.8 mm thickness variant test only)."""
    cj = [_board_rect(30, 20)]
    cj += [_src("r1", "R1", "R_1206")]
    cj += [_pcb("r1", 15, 10)]
    return cj


def _make_board_12() -> list[dict]:
    """QFN-48 IC with many bypass vias."""
    cj = [_board_rect(50, 50)]
    cj += [_src("u1", "U1", "QFN-48", "STM32F4")]
    cj += [_pcb("u1", 25, 25)]
    cj += [_via(f"v{i}", 5 + i * 4, 5) for i in range(10)]
    return cj


def _make_board_13() -> list[dict]:
    """Connector-heavy board: USB-A, USB-C, JST-PH-2."""
    cj = [_board_rect(80, 30)]
    cj += [
        _src("j1", "J1", "USB-A"),
        _src("j2", "J2", "USB-C"),
        _src("j3", "J3", "JST-PH-2"),
    ]
    cj += [
        _pcb("j1", 10, 15),
        _pcb("j2", 40, 15),
        _pcb("j3", 70, 15),
    ]
    cj += [_pth("p1", 10, 5, 1.5), _pth("p2", 40, 5, 1.5)]
    return cj


def _make_board_14() -> list[dict]:
    """Resistor ladder: 8 resistors at various rotations."""
    cj = [_board_rect(90, 20)]
    angles = [0, 45, 90, 135, 180, 225, 270, 315]
    for i, angle in enumerate(angles):
        sid = f"r{i}"
        cj.append(_src(sid, f"R{i+1}", "R_0402"))
        cj.append(_pcb(sid, 5 + i * 11, 10, rotation=float(angle)))
    return cj


def _make_board_15() -> list[dict]:
    """Double-sided with vias and PTH at different densities."""
    cj = [_board_rect(100, 100)]
    for i in range(4):
        sid = f"u{i}"
        layer = "top_copper" if i % 2 == 0 else "bottom_copper"
        cj.append(_src(sid, f"U{i+1}", "SOT-23", "2N3904"))
        cj.append(_pcb(sid, 20 + i * 20, 50, layer=layer))
    cj += [_via(f"v{i}", 10 + i * 10, 10) for i in range(8)]
    cj += [_pth(f"p{i}", 10 + i * 20, 90, 1.0) for i in range(4)]
    return cj


def _make_board_16() -> list[dict]:
    """Very large board: 300×200 mm with sparse placement."""
    cj = [_board_rect(300, 200)]
    cj += [_src("u1", "U1", "TQFP-100")]
    cj += [_pcb("u1", 150, 100)]
    cj += [_mhole(f"mh{i}", pos[0], pos[1], 4.0)
           for i, pos in enumerate([(10, 10), (290, 10), (290, 190), (10, 190)])]
    return cj


def _make_board_17() -> list[dict]:
    """Very small board: 10×8 mm with one component."""
    cj = [_board_rect(10, 8)]
    cj += [_src("r1", "R1", "R_0201")]
    cj += [_pcb("r1", 5, 4)]
    return cj


def _make_board_18() -> list[dict]:
    """Hexagonal polygon outline (6 vertices)."""
    import math
    r = 40.0
    cx, cy = 50.0, 50.0
    verts = [
        (cx + r * math.cos(math.pi / 3 * i), cy + r * math.sin(math.pi / 3 * i))
        for i in range(6)
    ]
    cj = [_board_polygon(verts)]
    cj += [_src("r1", "R1", "R_0402")]
    cj += [_pcb("r1", cx, cy)]
    return cj


def _make_board_19() -> list[dict]:
    """No placement at all — only vias and holes."""
    cj = [_board_rect(50, 50)]
    cj += [_via(f"v{i}", 5 + i * 10, 25) for i in range(4)]
    cj += [_mhole(f"mh{i}", pos[0], pos[1]) for i, pos in enumerate([(5, 5), (45, 45)])]
    return cj


def _make_board_20() -> list[dict]:
    """SOT-23-5 and SOT-23-6 mixed (prefix-match size heuristic)."""
    cj = [_board_rect(40, 20)]
    cj += [
        _src("q1", "Q1", "SOT-23-5", "LMV321"),
        _src("q2", "Q2", "SOT-23-6", "MAX9634"),
    ]
    cj += [
        _pcb("q1", 10, 10),
        _pcb("q2", 30, 10),
    ]
    return cj


def _make_board_21() -> list[dict]:
    """Mixed PTH + via + mounting hole drill matrix."""
    cj = [_board_rect(60, 60)]
    cj += [_src("r1", "R1", "R_0603"), _src("c1", "C1", "C_1206")]
    cj += [_pcb("r1", 20, 30), _pcb("c1", 40, 30)]
    cj += [
        _pth("p1", 10, 10, 0.8), _pth("p2", 50, 10, 1.2),
        _via("v1", 30, 10, 0.3), _via("v2", 30, 50, 0.4),
        _mhole("mh1", 5, 55, 3.2),
    ]
    return cj


def _make_board_22() -> list[dict]:
    """LGA package and BGA-100."""
    cj = [_board_rect(80, 80)]
    cj += [
        _src("u1", "U1", "LGA-16", "MPU6050"),
        _src("u2", "U2", "BGA-100", "Zynq7010"),
    ]
    cj += [
        _pcb("u1", 20, 40),
        _pcb("u2", 60, 40),
    ]
    cj += [_via(f"v{i}", 5 + i * 6, 5) for i in range(12)]
    return cj


def _make_board_23() -> list[dict]:
    """All R_* SMT resistor footprint sizes represented."""
    fps = ["R_0201", "R_0402", "R_0603", "R_0805", "R_1206"]
    cj = [_board_rect(80, 15)]
    for i, fp in enumerate(fps):
        sid = f"r{i}"
        cj.append(_src(sid, f"R{i+1}", fp))
        cj.append(_pcb(sid, 10 + i * 14, 8))
    return cj


def _make_board_24() -> list[dict]:
    """All C_* SMT capacitor footprint sizes represented."""
    fps = ["C_0201", "C_0402", "C_0603", "C_0805", "C_1206"]
    cj = [_board_rect(80, 15)]
    for i, fp in enumerate(fps):
        sid = f"c{i}"
        cj.append(_src(sid, f"C{i+1}", fp))
        cj.append(_pcb(sid, 10 + i * 14, 8))
    return cj


def _make_board_25() -> list[dict]:
    """Stress test: 5 ICs + 10 passives + 4 vias + 2 PTH + 4 mounting holes."""
    cj = [_board_rect(120, 80)]
    ic_fps = ["SOIC-8", "SOIC-16", "TQFP-32", "QFN-32", "QFN-48"]
    for i, fp in enumerate(ic_fps):
        sid = f"u{i}"
        cj.append(_src(sid, f"U{i+1}", fp, "IC"))
        cj.append(_pcb(sid, 15 + i * 22, 40))
    for i in range(10):
        sid = f"r{i}"
        cj.append(_src(sid, f"R{i+1}", "R_0402"))
        cj.append(_pcb(sid, 10 + i * 11, 15, rotation=float(i * 36)))
    cj += [_via(f"v{i}", 5 + i * 20, 5) for i in range(4)]
    cj += [_pth(f"p{i}", 5 + i * 40, 75, 1.0) for i in range(2)]
    cj += [_mhole(f"mh{i}", pos[0], pos[1], 3.2)
           for i, pos in enumerate([(5, 5), (115, 5), (115, 75), (5, 75)])]
    return cj


ALL_BOARDS = [
    _make_board_01,
    _make_board_02,
    _make_board_03,
    _make_board_04,
    _make_board_05,
    _make_board_06,
    _make_board_07,
    _make_board_08,
    _make_board_09,
    _make_board_10,
    _make_board_11,
    _make_board_12,
    _make_board_13,
    _make_board_14,
    _make_board_15,
    _make_board_16,
    _make_board_17,
    _make_board_18,
    _make_board_19,
    _make_board_20,
    _make_board_21,
    _make_board_22,
    _make_board_23,
    _make_board_24,
    _make_board_25,
]

assert len(ALL_BOARDS) == 25, f"Expected 25 boards, got {len(ALL_BOARDS)}"

BOARD_IDS = [f"board{i+1:02d}" for i in range(25)]


# ---------------------------------------------------------------------------
# Geometry helpers for IDF round-trip verification
# ---------------------------------------------------------------------------

def _parse_emn_outline(emn: str) -> list[tuple[float, float]]:
    """Extract board outline vertices from .emn text (first loop, up to closure)."""
    lines = emn.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(".BOARD_OUTLINE"))
    except StopIteration:
        return []
    try:
        end = next(i for i, ln in enumerate(lines) if ln.startswith(".END_BOARD_OUTLINE"))
    except StopIteration:
        return []

    verts = []
    for ln in lines[start + 3:end]:  # skip thickness + loop-index lines
        parts = ln.strip().split()
        if len(parts) == 3:
            try:
                verts.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    # IDF loop is closed — drop the last vertex (duplicate of first)
    if len(verts) > 1 and verts[0] == verts[-1]:
        verts = verts[:-1]
    return verts


def _parse_emn_holes(emn: str) -> list[tuple[float, float, float]]:
    """Extract (diameter, x, y) hole tuples from .emn DRILLED_HOLES section."""
    holes = []
    in_section = False
    for ln in emn.splitlines():
        if ln.strip() == ".DRILLED_HOLES":
            in_section = True
            continue
        if ln.strip() == ".END_DRILLED_HOLES":
            break
        if in_section and "PTH BOARD NOPIN VIA" in ln:
            parts = ln.strip().split()
            if len(parts) >= 3:
                try:
                    holes.append((float(parts[0]), float(parts[1]), float(parts[2])))
                except ValueError:
                    continue
    return holes


def _parse_emn_placement(emn: str) -> list[str]:
    """Extract refdes list from .PLACEMENT section."""
    placed = []
    in_section = False
    for ln in emn.splitlines():
        if ln.strip() == ".PLACEMENT":
            in_section = True
            continue
        if ln.strip() == ".END_PLACEMENT":
            break
        if in_section and ln.strip().startswith('"'):
            # Extract refdes (first quoted token)
            m = re.match(r'"([^"]+)"', ln.strip())
            if m:
                placed.append(m.group(1))
    return placed


# ---------------------------------------------------------------------------
# T-30 Section 1: Board outline extraction (25 boards, pure Python)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_board_outline_has_at_least_3_vertices(make_fn):
    """Every board must produce a valid polygon outline (>= 3 vertices)."""
    cj = make_fn()
    verts = _board_outline_vertices(cj)
    assert len(verts) >= 3, f"Expected >=3 outline vertices, got {len(verts)}"


@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_board_outline_has_positive_extent(make_fn):
    """Board outline must span a positive area (non-degenerate)."""
    cj = make_fn()
    verts = _board_outline_vertices(cj)
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    assert max(xs) - min(xs) > 0, "Board outline has zero x-extent"
    assert max(ys) - min(ys) > 0, "Board outline has zero y-extent"


# ---------------------------------------------------------------------------
# T-30 Section 2: Placement matches PnP (25 boards)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_placement_matches_pnp(make_fn):
    """_collect_placed_components and pnp._extract_components must agree.

    Both functions share the same CircuitJSON extraction contract.
    For every board: the refdes set, (x, y) positions, rotation values, and
    side assignments must be identical between the two implementations.
    """
    cj = make_fn()
    step_comps = _collect_placed_components(cj)
    pnp_comps = pnp_extract(cj)

    # Sort both by refdes for deterministic comparison
    step_by_ref = {c["refdes"]: c for c in step_comps}
    pnp_by_ref = {c["refdes"]: c for c in pnp_comps}

    # Refdes sets must match
    assert set(step_by_ref) == set(pnp_by_ref), (
        f"Refdes mismatch: step={set(step_by_ref)}, pnp={set(pnp_by_ref)}"
    )

    for refdes, sc in step_by_ref.items():
        pc = pnp_by_ref[refdes]
        assert abs(sc["x"] - pc["x"]) < 1e-6, (
            f"{refdes}: x mismatch step={sc['x']} pnp={pc['x']}"
        )
        assert abs(sc["y"] - pc["y"]) < 1e-6, (
            f"{refdes}: y mismatch step={sc['y']} pnp={pc['y']}"
        )
        assert abs(sc["rotation_deg"] - pc["rotation"]) < 1e-6, (
            f"{refdes}: rotation mismatch step={sc['rotation_deg']} pnp={pc['rotation']}"
        )
        assert sc["side"] == pc["side"], (
            f"{refdes}: side mismatch step={sc['side']} pnp={pc['side']}"
        )


# ---------------------------------------------------------------------------
# T-30 Section 3: IDF round-trip (25 boards)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_idf_export_produces_two_files(make_fn):
    """export_idf must return both .emn and .emp files."""
    cj = make_fn()
    files = export_idf(cj, stem="board")
    assert "board.emn" in files
    assert "board.emp" in files


@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_idf_emn_has_required_sections(make_fn):
    """Every .emn file must contain HEADER and BOARD_OUTLINE sections."""
    cj = make_fn()
    emn = export_idf(cj)["board.emn"]
    for kw in (".HEADER", ".END_HEADER", ".BOARD_OUTLINE", ".END_BOARD_OUTLINE"):
        assert kw in emn, f"Missing .emn section: {kw}"


@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_idf_outline_round_trip(make_fn):
    """IDF .emn outline vertex count and extent must match _board_outline_vertices."""
    cj = make_fn()
    expected_verts = _board_outline_vertices(cj)
    emn = export_idf(cj)["board.emn"]
    parsed_verts = _parse_emn_outline(emn)

    assert len(parsed_verts) == len(expected_verts), (
        f"Outline vertex count: expected {len(expected_verts)}, got {len(parsed_verts)}"
    )
    # Check bounding-box extent matches
    e_xs = [v[0] for v in expected_verts]
    e_ys = [v[1] for v in expected_verts]
    p_xs = [v[0] for v in parsed_verts]
    p_ys = [v[1] for v in parsed_verts]
    assert abs(max(p_xs) - min(p_xs) - (max(e_xs) - min(e_xs))) < 1e-4, (
        "IDF outline x-extent mismatch after round-trip"
    )
    assert abs(max(p_ys) - min(p_ys) - (max(e_ys) - min(e_ys))) < 1e-4, (
        "IDF outline y-extent mismatch after round-trip"
    )


@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_idf_hole_count_round_trip(make_fn):
    """Drilled hole count in .emn must match _collect_holes."""
    cj = make_fn()
    expected_holes = _collect_holes(cj)
    emn = export_idf(cj)["board.emn"]
    parsed_holes = _parse_emn_holes(emn)
    assert len(parsed_holes) == len(expected_holes), (
        f"Hole count: expected {len(expected_holes)}, got {len(parsed_holes)}"
    )


@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_idf_placement_count_round_trip(make_fn):
    """Placement count in .emn must match _collect_placed_components."""
    cj = make_fn()
    expected = _collect_placed_components(cj)
    emn = export_idf(cj)["board.emn"]
    parsed = _parse_emn_placement(emn)
    assert len(parsed) == len(expected), (
        f"Placement count: expected {len(expected)}, got {len(parsed)}"
    )


@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_idf_loop_closed_in_emn(make_fn):
    """The BOARD_OUTLINE loop in .emn must be explicitly closed."""
    cj = make_fn()
    emn = export_idf(cj)["board.emn"]
    lines = emn.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(".BOARD_OUTLINE"))
        end = next(i for i, ln in enumerate(lines) if ln.startswith(".END_BOARD_OUTLINE"))
    except StopIteration:
        pytest.fail("Missing .BOARD_OUTLINE section")
    vertex_lines = [
        ln for ln in lines[start:end]
        if ln and len(ln.split()) == 3
    ]
    assert len(vertex_lines) >= 5, (
        f"Expected >=5 vertex lines (4 corners + closure), got {len(vertex_lines)}"
    )
    assert vertex_lines[0] == vertex_lines[-1], "BOARD_OUTLINE loop is not closed"


@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_idf_emp_package_per_unique_footprint(make_fn):
    """emp must contain exactly one .ELECTRICAL section per unique footprint."""
    cj = make_fn()
    components = _collect_placed_components(cj)
    unique_fps = {c["footprint"] or c["refdes"] or "UNKNOWN" for c in components}
    emp = export_idf(cj)["board.emp"]
    electrical_count = emp.count(".ELECTRICAL\n")
    assert electrical_count == len(unique_fps), (
        f"Expected {len(unique_fps)} .ELECTRICAL sections, got {electrical_count}"
    )


# ---------------------------------------------------------------------------
# T-30 Section 4: STEP export (25 boards, skipped if OCC absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _OCC_AVAILABLE, reason="pythonOCC not installed")
@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_step_file_produced_and_valid(make_fn):
    """STEP export produces a non-empty file with ISO-10303-21 header."""
    from kerf_electronics.fab.board_step import export_board_step

    cj = make_fn()
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tmp:
        path = tmp.name
    try:
        result = export_board_step(cj, path)
        assert os.path.isfile(path), "STEP file not created"
        assert os.path.getsize(path) > 0, "STEP file is empty"
        # Read first 512 bytes for STEP header check
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            header = fh.read(512)
        assert "ISO-10303-21" in header, "STEP file missing ISO-10303-21 header"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.mark.skipif(not _OCC_AVAILABLE, reason="pythonOCC not installed")
@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_step_substrate_volume_positive(make_fn):
    """STEP export result must report positive substrate volume."""
    from kerf_electronics.fab.board_step import export_board_step

    cj = make_fn()
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tmp:
        path = tmp.name
    try:
        result = export_board_step(cj, path)
        assert result["substrate_volume"] > 0, (
            f"substrate_volume={result['substrate_volume']}, expected >0"
        )
        assert result["occ_available"] is True
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.mark.skipif(not _OCC_AVAILABLE, reason="pythonOCC not installed")
@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_step_component_count_matches(make_fn):
    """STEP component_count must equal _collect_placed_components count."""
    from kerf_electronics.fab.board_step import export_board_step

    cj = make_fn()
    expected = len(_collect_placed_components(cj))
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tmp:
        path = tmp.name
    try:
        result = export_board_step(cj, path)
        assert result["component_count"] == expected, (
            f"component_count: expected {expected}, got {result['component_count']}"
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.mark.skipif(not _OCC_AVAILABLE, reason="pythonOCC not installed")
@pytest.mark.parametrize("make_fn", ALL_BOARDS, ids=BOARD_IDS)
def test_step_hole_count_matches(make_fn):
    """STEP hole_count must equal _collect_holes count."""
    from kerf_electronics.fab.board_step import export_board_step

    cj = make_fn()
    expected = len(_collect_holes(cj))
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tmp:
        path = tmp.name
    try:
        result = export_board_step(cj, path)
        assert result["hole_count"] == expected, (
            f"hole_count: expected {expected}, got {result['hole_count']}"
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.mark.skipif(not _OCC_AVAILABLE, reason="pythonOCC not installed")
def test_step_custom_thickness_volume():
    """Custom board_thickness_mm is reflected in substrate_volume."""
    from kerf_electronics.fab.board_step import export_board_step

    # Board 01: 50×30, thickness 0.8 mm → approx volume = 50*30*0.8 = 1200
    cj = _make_board_01()
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tmp:
        path = tmp.name
    try:
        result = export_board_step(cj, path, board_thickness_mm=0.8)
        assert abs(result["substrate_volume"] - 1200.0) < 5.0, (
            f"substrate_volume {result['substrate_volume']} not close to 1200 mm³"
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# T-30 Section 5: Boundary / malformed / idempotency cases
# ---------------------------------------------------------------------------

def test_empty_circuit_json_safe_step_geometry():
    """Empty list → 100×100 default outline; no holes; no components."""
    verts = _board_outline_vertices([])
    holes = _collect_holes([])
    comps = _collect_placed_components([])
    assert len(verts) == 4, "Empty circuit should produce 4-vertex default board"
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    assert abs(max(xs) - min(xs) - 100.0) < 1e-6
    assert abs(max(ys) - min(ys) - 100.0) < 1e-6
    assert holes == []
    assert comps == []


def test_none_circuit_json_idf_safe():
    """None passed as circuit_json must not raise."""
    files = export_idf(None, stem="safe")  # type: ignore[arg-type]
    assert "safe.emn" in files
    assert "safe.emp" in files


def test_non_list_circuit_json_idf_safe():
    """Non-list circuit_json (string/int) must not raise."""
    for bad in ("not_a_list", 42, {"type": "pcb_board"}):
        files = export_idf(bad, stem="safe")  # type: ignore[arg-type]
        assert "safe.emn" in files


def test_zero_size_board_element_uses_fallback():
    """A pcb_board with zero width/height should fall through to 100×100 fallback."""
    cj = [{"type": "pcb_board", "width": 0, "height": 0}]
    verts = _board_outline_vertices(cj)
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    assert abs(max(xs) - min(xs) - 100.0) < 1e-6


def test_outline_path_with_only_2_points_falls_back_to_board_element():
    """An outline_path with < 3 points should be ignored; board element used."""
    cj = [
        {"type": "pcb_board", "width": 50, "height": 40, "center_x": 25, "center_y": 20},
        {"type": "pcb_outline_path", "route": [{"x": 0, "y": 0}, {"x": 10, "y": 0}]},
    ]
    verts = _board_outline_vertices(cj)
    xs = [v[0] for v in verts]
    assert abs(max(xs) - min(xs) - 50.0) < 1e-6, (
        "Degenerate outline_path should fall back to pcb_board element"
    )


def test_hole_with_zero_diameter_excluded():
    """Holes with diameter == 0 must not appear in _collect_holes."""
    cj = [
        {"type": "pcb_via", "x": 5, "y": 5, "hole_diameter": 0.0},
        {"type": "pcb_hole", "x": 10, "y": 10, "hole_diameter": 0.0},
        {"type": "pcb_via", "x": 20, "y": 20, "hole_diameter": 0.3},
    ]
    holes = _collect_holes(cj)
    assert len(holes) == 1
    assert abs(holes[0][2] - 0.3) < 1e-6


def test_pcb_component_without_source_component_included():
    """pcb_component without a matching source_component should still be placed."""
    cj = [
        {"type": "pcb_component", "pcb_component_id": "pc1",
         "source_component_id": "", "x": 5.0, "y": 5.0, "rotation": 0.0,
         "layer": "top_copper"},
    ]
    comps = _collect_placed_components(cj)
    assert len(comps) == 1
    assert comps[0]["side"] == "top"
    assert abs(comps[0]["x"] - 5.0) < 1e-6


def test_idf_idempotency_double_export():
    """Calling export_idf twice on the same circuit produces identical output."""
    cj = _make_board_03()
    files1 = export_idf(cj, stem="board", board_thickness_mm=1.6)
    files2 = export_idf(cj, stem="board", board_thickness_mm=1.6)
    # emn files may differ by timestamp — compare everything except the timestamp line
    def strip_ts(text: str) -> str:
        return re.sub(r"\d{4}/\d{2}/\d{2}\.\d{2}:\d{2}:\d{2}", "TS", text)
    assert strip_ts(files1["board.emn"]) == strip_ts(files2["board.emn"]), (
        "IDF .emn output not idempotent (ignoring timestamp)"
    )
    assert strip_ts(files1["board.emp"]) == strip_ts(files2["board.emp"]), (
        "IDF .emp output not idempotent (ignoring timestamp)"
    )


def test_step_raises_when_occ_absent():
    """export_board_step must raise RuntimeError with install hint when OCC absent."""
    import unittest.mock as mock
    import kerf_electronics.fab.board_step as bs
    from kerf_electronics.fab.board_step import export_board_step

    with mock.patch.object(bs, "_OCC_AVAILABLE", False):
        with pytest.raises(RuntimeError, match="pythonOCC not installed"):
            export_board_step([], "/tmp/no_occ_test.step")


def test_idf_thickness_boundary_1mm():
    """1.0 mm custom thickness round-trips through .emn without loss."""
    cj = _make_board_01()
    emn = export_idf(cj, board_thickness_mm=1.0)["board.emn"]
    lines = emn.splitlines()
    idx = next(i for i, ln in enumerate(lines) if ln.startswith(".BOARD_OUTLINE"))
    thickness_val = float(lines[idx + 1].strip())
    assert abs(thickness_val - 1.0) < 1e-4, (
        f"Thickness round-trip failed: expected 1.0, got {thickness_val}"
    )


def test_idf_thickness_boundary_2mm():
    """2.0 mm custom thickness round-trips through .emn without loss."""
    cj = _make_board_01()
    emn = export_idf(cj, board_thickness_mm=2.0)["board.emn"]
    lines = emn.splitlines()
    idx = next(i for i, ln in enumerate(lines) if ln.startswith(".BOARD_OUTLINE"))
    thickness_val = float(lines[idx + 1].strip())
    assert abs(thickness_val - 2.0) < 1e-4


def test_idf_negative_thickness_stored_as_passed():
    """Negative thickness (malformed input) is stored as-is (no clamp in spec)."""
    cj = [_board_rect(20, 20)]
    emn = export_idf(cj, board_thickness_mm=-0.1)["board.emn"]
    lines = emn.splitlines()
    idx = next(i for i, ln in enumerate(lines) if ln.startswith(".BOARD_OUTLINE"))
    thickness_val = float(lines[idx + 1].strip())
    assert abs(thickness_val - (-0.1)) < 1e-4


def test_idf_stem_used_in_header():
    """Custom stem appears in both .emn and .emp filenames and headers."""
    cj = _make_board_02()
    stem = "custom_board_rev3"
    files = export_idf(cj, stem=stem)
    assert f"{stem}.emn" in files
    assert f"{stem}.emp" in files
    assert stem in files[f"{stem}.emn"]
    assert stem in files[f"{stem}.emp"]


def test_pcb_hole_type_collected():
    """pcb_hole type elements are collected by _collect_holes."""
    cj = [{"type": "pcb_hole", "x": 15.0, "y": 25.0, "hole_diameter": 2.5}]
    holes = _collect_holes(cj)
    assert len(holes) == 1
    assert abs(holes[0][0] - 15.0) < 1e-6
    assert abs(holes[0][1] - 25.0) < 1e-6
    assert abs(holes[0][2] - 2.5) < 1e-6


def test_pth_with_drill_diameter_alias():
    """pcb_plated_pad with 'drill_diameter' alias is collected."""
    cj = [
        {"type": "pcb_plated_pad", "x": 10.0, "y": 10.0,
         "drill_diameter": 1.2, "layer": "top_copper"},
    ]
    holes = _collect_holes(cj)
    assert len(holes) == 1
    assert abs(holes[0][2] - 1.2) < 1e-6


def test_outline_points_alias():
    """pcb_outline_path with 'points' key (alias for 'route') is accepted."""
    cj = [
        {
            "type": "pcb_outline_path",
            "points": [
                {"x": 0, "y": 0}, {"x": 30, "y": 0},
                {"x": 30, "y": 20}, {"x": 0, "y": 20},
            ],
        }
    ]
    verts = _board_outline_vertices(cj)
    xs = [v[0] for v in verts]
    assert abs(max(xs) - 30.0) < 1e-6


def test_outline_vertices_alias():
    """pcb_outline_path with 'vertices' key (alias for 'route') is accepted."""
    cj = [
        {
            "type": "pcb_outline_path",
            "vertices": [
                {"x": 0, "y": 0}, {"x": 25, "y": 0},
                {"x": 25, "y": 15}, {"x": 0, "y": 15},
            ],
        }
    ]
    verts = _board_outline_vertices(cj)
    xs = [v[0] for v in verts]
    assert abs(max(xs) - 25.0) < 1e-6


def test_bottom_side_z_offset_in_idf():
    """Bottom-side components must have z_mm < 0 in IDF placement."""
    cj = [
        _board_rect(40, 30),
        _src("r1", "R1", "R_0402"),
        _pcb("r1", 20, 15, layer="bottom_copper"),
    ]
    emn = export_idf(cj)["board.emn"]
    # Find placement line for R1
    r1_line = next((ln for ln in emn.splitlines() if '"R1"' in ln), None)
    assert r1_line is not None, "R1 not found in .PLACEMENT"
    assert "BOTTOM" in r1_line, "Bottom-side component should be marked BOTTOM in IDF"
    # z_mm field (3rd numeric token in the placement record)
    parts = r1_line.split()
    # format: "R1" "footprint" x y z rot SIDE
    # tokens after stripping quotes are: refdes package x y z rotation side
    # Find the BOTTOM token index
    bottom_idx = parts.index("BOTTOM")
    z_val = float(parts[bottom_idx - 2])
    assert z_val < 0, (
        f"Bottom-side component z_mm should be negative, got {z_val}"
    )
