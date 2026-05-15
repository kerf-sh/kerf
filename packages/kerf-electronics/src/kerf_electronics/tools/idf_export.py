"""
IDF 3.0 board export for CircuitJSON boards (ECAD↔MCAD handoff).

Implements the IDF 3.0 format as defined by the ProSTEP IDF 3.0 specification:
  .emn  (Electronic Manufacturing Netlist) — board outline, cutouts, drilled holes
  .emp  (Electronic Manufacturing Part)    — component outlines and heights

Two files are emitted for each export:
  <stem>.emn  — board file
  <stem>.emp  — library file

IDF 3.0 record vocabulary used:
  .emn sections:
    .HEADER        — file type, version, date, board name, units
    .BOARD_OUTLINE — board edge-cuts polygon (outline + optional cutouts/holes)
    .DRILLED_HOLES — via and mounting-hole coordinates + diameters
    .PLACEMENT     — component placement: refdes, package, x, y, rotation, side

  .emp sections:
    .HEADER        — file type, version, date
    .ELECTRICAL    — one section per unique package: outline box + height

Units: millimetres throughout (UNIT MM in header).

Geometry reuse
--------------
All geometry extraction is delegated to board_step helpers:
  _board_outline_vertices   → board outline polygon (edge_cuts)
  _collect_holes            → via / PTH / mounting holes (x, y, diameter)
  _collect_placed_components→ placed component list with footprint + body sizes
  _estimate_body_size       → parametric body dimensions from footprint name

This intentionally reuses board_step's extraction verbatim so the same
CircuitJSON read of pcb_board / pcb_outline_path / pcb_via / pcb_plated_pad /
pcb_hole / pcb_mounting_hole / pcb_component / source_component always
yields consistent geometry across STEP and IDF exports.

IDF 3.0 outline loop convention:
  First loop (index 0) = board boundary (clockwise when viewed from above).
  Additional loops = cutout islands (counter-clockwise).
  Each vertex line:  <x_mm>  <y_mm>  <arc_angle_deg>
  Arc angle 0.0 means straight segment to next vertex.
  Loop is terminated by a line whose X Y equals the first point of the loop.

Component outline convention (.ELECTRICAL):
  A rectangular outline centred at (0, 0) is emitted for each unique package.
  Height is taken from _estimate_body_size (same values used by board_step).
  The outline is labelled with the footprint name.

Placement convention (.PLACEMENT in .emn):
  Each placed component is listed as:
  <refdes>  <package>  <x_mm>  <y_mm>  <z_mm>  <rotation_deg>  <side>

  z_mm = 0.0 for top-side components (board surface), negative for bottom-side
  (placed below board) — matching board_step's z_offset logic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

# Reuse board_step geometry extraction — do NOT re-derive.
from kerf_electronics.fab.board_step import (
    _board_outline_vertices,
    _collect_holes,
    _collect_placed_components,
)


# ─── IDF record formatting helpers ───────────────────────────────────────────

def _idf_timestamp() -> str:
    """Return current UTC time formatted for IDF 3.0 HEADER (YYYY/MM/DD.HH:MM:SS)."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y/%m/%d.%H:%M:%S")


def _fmt(v: float, decimals: int = 6) -> str:
    """Format a float with up to *decimals* decimal places, stripping trailing zeros."""
    s = f"{v:.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


# ─── .emn builder ────────────────────────────────────────────────────────────

def _build_emn(
    circuit_json: list[dict],
    stem: str,
    board_thickness_mm: float,
) -> str:
    """Build the IDF 3.0 .emn board file text."""

    outline = _board_outline_vertices(circuit_json)
    holes = _collect_holes(circuit_json)
    components = _collect_placed_components(circuit_json)

    ts = _idf_timestamp()
    lines: list[str] = []

    # ── HEADER ───────────────────────────────────────────────────────────────
    lines += [
        ".HEADER",
        f"BOARD_FILE 3.0 \"{stem}\" {ts} 1",
        f"\"kerf-electronics\" 1.0",
        f"\"{stem}\" MM",
        ".END_HEADER",
        "",
    ]

    # ── BOARD_OUTLINE ────────────────────────────────────────────────────────
    # IDF 3.0 §4.3: thickness on same line as .BOARD_OUTLINE keyword
    lines += [
        f".BOARD_OUTLINE MCAD",
        f"{_fmt(board_thickness_mm)}",
        "0",  # loop index 0 = board boundary
    ]
    # Emit outline vertices; IDF loops are closed by repeating the first point
    if outline:
        for x, y in outline:
            lines.append(f"{_fmt(x)} {_fmt(y)} 0.0")
        # Close the loop
        x0, y0 = outline[0]
        lines.append(f"{_fmt(x0)} {_fmt(y0)} 0.0")
    lines += [".END_BOARD_OUTLINE", ""]

    # ── DRILLED_HOLES ────────────────────────────────────────────────────────
    # IDF 3.0 §4.5: one hole per line:
    #   <diameter> <x> <y> PTH|NPTH  <refdes|BOARD> <pin|NOPIN> <via|unm|tooling>
    if holes:
        lines.append(".DRILLED_HOLES")
        for x, y, diameter in holes:
            lines.append(
                f"{_fmt(diameter)} {_fmt(x)} {_fmt(y)} PTH BOARD NOPIN VIA"
            )
        lines += [".END_DRILLED_HOLES", ""]

    # ── PLACEMENT ────────────────────────────────────────────────────────────
    # IDF 3.0 §4.6: <refdes> <package> <x> <y> <z> <rotation> <TOP|BOTTOM>
    if components:
        lines.append(".PLACEMENT")
        for comp in components:
            # z_mm = 0 on top side; below board on bottom side
            z_mm = 0.0 if comp["side"] == "top" else -comp["body_z"]
            side_str = "TOP" if comp["side"] == "top" else "BOTTOM"
            package = comp["footprint"] or comp["refdes"] or "UNKNOWN"
            lines.append(
                f"\"{comp['refdes']}\" \"{package}\" "
                f"{_fmt(comp['x'])} {_fmt(comp['y'])} {_fmt(z_mm)} "
                f"{_fmt(comp['rotation_deg'])} {side_str}"
            )
        lines += [".END_PLACEMENT", ""]

    return "\n".join(lines) + "\n"


# ─── .emp builder ────────────────────────────────────────────────────────────

def _build_emp(
    circuit_json: list[dict],
    stem: str,
) -> str:
    """Build the IDF 3.0 .emp component library file text."""

    components = _collect_placed_components(circuit_json)

    ts = _idf_timestamp()
    lines: list[str] = []

    # ── HEADER ───────────────────────────────────────────────────────────────
    lines += [
        ".HEADER",
        f"LIBRARY_FILE 3.0 \"{stem}\" {ts} 1",
        f"\"kerf-electronics\" 1.0",
        ".END_HEADER",
        "",
    ]

    # Collect unique packages (footprint → body dimensions)
    seen: dict[str, tuple[float, float, float]] = {}
    for comp in components:
        pkg = comp["footprint"] or comp["refdes"] or "UNKNOWN"
        if pkg not in seen:
            seen[pkg] = (comp["body_w"], comp["body_h"], comp["body_z"])

    # ── .ELECTRICAL per unique package ───────────────────────────────────────
    # IDF 3.0 §5.2: .ELECTRICAL <package_name> <part_number> MM
    #                <height>
    #                <loop_index>
    #                <x> <y> <arc_angle>   (outline vertices)
    for pkg, (bw, bh, bz) in sorted(seen.items()):
        hw = bw / 2.0
        hh = bh / 2.0
        lines += [
            f".ELECTRICAL",
            f"\"{pkg}\" \"\" MM",
            f"{_fmt(bz)}",
            "0",  # outline loop index
        ]
        # Rectangular outline centred at origin (clockwise)
        rect = [
            (-hw, -hh),
            ( hw, -hh),
            ( hw,  hh),
            (-hw,  hh),
        ]
        for x, y in rect:
            lines.append(f"{_fmt(x)} {_fmt(y)} 0.0")
        # Close loop
        x0, y0 = rect[0]
        lines.append(f"{_fmt(x0)} {_fmt(y0)} 0.0")
        lines += [".END_ELECTRICAL", ""]

    return "\n".join(lines) + "\n"


# ─── Public API ───────────────────────────────────────────────────────────────

def export_idf(
    circuit_json: list[dict],
    stem: str = "board",
    board_thickness_mm: float = 1.6,
) -> dict[str, str]:
    """Export IDF 3.0 board and library files from a CircuitJSON board.

    Reuses board_step geometry extraction for outline, holes and component
    placement so both exports are always consistent.

    Args:
        circuit_json: Parsed CircuitJSON array (tscircuit PCB data model).
        stem:         Output filename stem (no extension).
        board_thickness_mm: PCB substrate thickness in mm (default 1.6).

    Returns:
        dict mapping filename → file text content:
          ``<stem>.emn``  — IDF 3.0 board file (outline + placement)
          ``<stem>.emp``  — IDF 3.0 library file (component outlines + heights)
    """
    if not isinstance(circuit_json, list):
        circuit_json = []

    emn_text = _build_emn(circuit_json, stem, board_thickness_mm)
    emp_text = _build_emp(circuit_json, stem)

    return {
        f"{stem}.emn": emn_text,
        f"{stem}.emp": emp_text,
    }


# ─── LLM tool: export_idf ────────────────────────────────────────────────────

export_idf_spec = ToolSpec(
    name="export_idf",
    description=(
        "Export a CircuitJSON PCB board as an IDF 3.0 ECAD↔MCAD exchange package. "
        "Returns two files: a board file (.emn) containing the board outline, drilled "
        "holes and component placement, and a library file (.emp) containing the component "
        "outlines and heights.  These files are consumed by mechanical CAD tools "
        "(SolidWorks, CATIA, PTC Creo, Autodesk Inventor) for enclosure design, "
        "collision detection and mechanical DFM review. "
        "IDF 3.0 sections emitted: BOARD_OUTLINE (edge-cuts polygon), DRILLED_HOLES "
        "(vias + mounting holes), PLACEMENT (component x/y/rotation/side), and "
        "ELECTRICAL entries (.emp) for each unique package with bounding-box outline "
        "and body height derived from the footprint name. "
        "All geometry is consistent with export_board_step (same board_step extraction). "
        "Use this tool when the mechanical team needs board dimensions and keep-out "
        "clearances; use export_board_step when a full 3D solid model is required. "
        "No extra dependencies — pure Python."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array from the active board file.",
                "items": {"type": "object"},
            },
            "stem": {
                "type": "string",
                "description": (
                    "Base filename stem used for both output files (default: 'board'). "
                    "Produces <stem>.emn and <stem>.emp."
                ),
            },
            "board_thickness_mm": {
                "type": "number",
                "description": (
                    "PCB substrate thickness in millimetres (default: 1.6 mm). "
                    "Common values: 0.8, 1.0, 1.2, 1.6, 2.0."
                ),
            },
        },
        "required": ["circuit_json"],
    },
)


@register(export_idf_spec)
async def run_export_idf(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    stem = a.get("stem", "board") or "board"
    board_thickness_mm = float(a.get("board_thickness_mm", 1.6))

    try:
        files = export_idf(circuit_json, stem=stem, board_thickness_mm=board_thickness_mm)
    except Exception as e:
        return err_payload(f"IDF export failed: {e}", "EXPORT_ERROR")

    import base64

    emn_filename = f"{stem}.emn"
    emp_filename = f"{stem}.emp"
    emn_text = files.get(emn_filename, "")
    emp_text = files.get(emp_filename, "")

    emn_b64 = base64.b64encode(emn_text.encode("ascii", errors="replace")).decode()
    emp_b64 = base64.b64encode(emp_text.encode("ascii", errors="replace")).decode()

    # Count placements in .emn
    placement_count = sum(
        1 for ln in emn_text.splitlines()
        if ln.startswith('"') and not ln.startswith('".END')
    )
    hole_count = sum(
        1 for ln in emn_text.splitlines()
        if ln.strip() and ln[0].isdigit() and "PTH" in ln
    )
    package_count = emp_text.count(".ELECTRICAL\n") + emp_text.count(".ELECTRICAL\r\n")

    return ok_payload({
        "emn_filename": emn_filename,
        "emp_filename": emp_filename,
        "emn_b64": emn_b64,
        "emp_b64": emp_b64,
        "emn_size_bytes": len(emn_text.encode()),
        "emp_size_bytes": len(emp_text.encode()),
        "placement_count": placement_count,
        "hole_count": hole_count,
        "package_count": package_count,
        "message": (
            f"IDF 3.0 export complete: {emn_filename} + {emp_filename}. "
            f"{placement_count} component placement(s), "
            f"{hole_count} drilled hole(s), "
            f"{package_count} unique package outline(s) in library. "
            "Decode emn_b64 / emp_b64 to obtain the IDF files for your MCAD tool."
        ),
    })
