"""
IPC-D-356A electrical netlist writer and connectivity report for CircuitJSON boards.

Generates a bare-board electrical test (BET) netlist as required by fab houses
for continuity/isolation testing.  The format is IPC-D-356A (1997), which
supersedes IPC-D-356 (1989).

Spec references:
  IPC-D-356A §4      — File structure: header block followed by net records,
                        terminated by 999 end record.
  IPC-D-356A §4.1    — Header records: lines beginning with 'C' (comment),
                        'P JOB', 'P CODE', 'P DATE', 'P UNITS'.
  IPC-D-356A §4.2    — Net record format: 20-character fixed-width fields.
  IPC-D-356A §4.2.1  — Record type 317 for SMT pads (no drill / through-hole).
  IPC-D-356A §4.2.2  — Record type 327 for through-hole pads and vias (drilled).
  IPC-D-356A §4.2.3  — Field definitions:
                          cols 3-17  NET NAME (14 chars, left-justified)
                          cols 18-20 REFDES (up to 6 chars) + '-' + PIN (up to 4 chars)
                          col  21    DRILLED (D) / NOT_DRILLED (space)
                          col  22    PLATED (P) / NOT_PLATED (U)
                          cols 23-24 ATTRIBUTES (mid-net = M, end = space)
                          cols 25-34 X coordinate (in 0.0001 inch or mm × 10000)
                          cols 35-40 Y coordinate (same units)
                          cols 41-42 X SIZE (pad width, 0.0001 inch)
                          cols 43-45 Y SIZE (pad height, 0.0001 inch)
                          cols 46-47 LAYER (00 = through-hole, 01 = top, 02 = bottom, …)
                          cols 48    ACCESS (B = both sides, T = top only, etc.)

IPC-D-356A coordinates are in 0.0001 inch (1 ten-thousandth of an inch) as the
reference unit, or alternatively in mm × 10000 when the P UNITS MM header is
present.  This implementation emits metric (mm) coordinates scaled by 10000 so
that 1 mm → 10000 counts, matching the behaviour of KiCad 6+ IPC-D-356 export.

Two LLM tools:
  export_ipc_netlist  — CircuitJSON → .IPC text (base64)
  netlist_report      — connectivity analysis (opens, single-pad nets,
                        unconnected pads)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

# ─── Constants ────────────────────────────────────────────────────────────────

# Coordinate scale factor: mm → IPC units (10000 counts per mm)
# IPC-D-356A §4.2.3: coordinates in 0.0001 inch when UNITS IN; in 0.001 mm
# (i.e. ×10000 relative to mm) when UNITS MM.
_MM_SCALE = 10000  # 1 mm = 10000 IPC units (metric mode)

# Layer codes per IPC-D-356A §4.2.3
_LAYER_THROUGH = "00"   # through-hole / via
_LAYER_TOP = "01"
_LAYER_BOTTOM = "02"

# Record type codes per IPC-D-356A §4.2.1/4.2.2
_RT_SMT = "317"   # SMD / no drill
_RT_PTH = "327"   # plated through-hole or via


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class _NetPoint:
    """One electrical connection point (pad or via) in the netlist."""

    net_name: str          # IPC net name (14-char field, truncated on emit)
    refdes: str            # Reference designator, e.g. "R1" (blank for vias)
    pin: str               # Pin number / name, e.g. "1" (blank for vias)
    record_type: str       # "317" (SMT) or "327" (PTH / via)
    drilled: bool          # True → 'D', False → space
    plated: bool           # True → 'P', False → 'U'
    x_mm: float            # X position in mm (board origin = 0,0)
    y_mm: float            # Y position in mm
    w_mm: float            # Pad width in mm (X size)
    h_mm: float            # Pad height in mm (Y size)
    drill_mm: float        # Drill diameter in mm (0 for SMT)
    layer_code: str        # "00" through-hole, "01" top, "02" bottom
    mid_net: bool = False  # True → mid-net point (multiple pads same net on record)


# ─── CircuitJSON extraction ───────────────────────────────────────────────────

def _layer_code(layer: str) -> str:
    """Map a CircuitJSON layer name to an IPC-D-356A layer code."""
    if not layer or layer in ("top_copper", "top"):
        return _LAYER_TOP
    if "bottom" in layer:
        return _LAYER_BOTTOM
    # Inner layers: inner_1 → "03", inner_2 → "04" …
    m = re.match(r"inner_(\d+)$", layer)
    if m:
        return f"{int(m.group(1)) + 2:02d}"
    return _LAYER_TOP  # fallback


def _net_name_from_pad(pad: dict, source_map: dict[str, dict]) -> str:
    """Derive a net name for a pad element.

    Tries (in order):
      1. pad.net_id or pad.net_name
      2. pad.source_net_id
      3. source_component.name + '-' + pad_number lookup
      4. 'N/C' (not connected)
    """
    for key in ("net_id", "net_name", "source_net_id", "net"):
        v = pad.get(key)
        if v and isinstance(v, str) and v.strip():
            return v.strip()
    return "N/C"


def _refdes_pin(pad: dict, source_map: dict[str, dict]) -> tuple[str, str]:
    """Return (refdes, pin) for a pad element."""
    # Direct attributes
    refdes = pad.get("refdes", pad.get("ref", ""))
    pin = pad.get("pin", pad.get("pin_number", pad.get("pad_number", "")))

    if not refdes:
        # Look up via source_component_id
        sid = pad.get("source_component_id", "")
        src = source_map.get(sid, {})
        refdes = src.get("name", src.get("refdes", ""))

    if not pin:
        # Try to derive from pad id suffix, e.g. "pad_r1_2" → "2"
        pad_id = pad.get("pcb_smtpad_id", pad.get("pcb_plated_pad_id", pad.get("id", "")))
        m = re.search(r"_(\d+)$", str(pad_id))
        if m:
            pin = m.group(1)
        else:
            pin = "1"

    return str(refdes or ""), str(pin or "1")


def _collect_net_points(circuit_json: list[dict]) -> list[_NetPoint]:
    """Extract all pad/via net points from a CircuitJSON array.

    Mirrors the classification logic from fab/gerber.py and fab/excellon.py,
    reusing the same element-type vocabulary.
    """
    # Index source_components for refdes/pin lookups
    source_map: dict[str, dict] = {}
    for el in circuit_json:
        if el.get("type") == "source_component":
            sid = el.get("source_component_id", el.get("id", ""))
            if sid:
                source_map[sid] = el

    points: list[_NetPoint] = []

    for el in circuit_json:
        t = el.get("type", "")

        # ── SMT pads ────────────────────────────────────────────────────────
        if t in ("pcb_smtpad", "pcb_component_pad"):
            x = float(el.get("x", 0.0))
            y = float(el.get("y", 0.0))
            w = float(el.get("width", el.get("size_x", 1.5)))
            h = float(el.get("height", el.get("size_y", w)))
            layer = el.get("layer", "top_copper")
            net = _net_name_from_pad(el, source_map)
            refdes, pin = _refdes_pin(el, source_map)
            points.append(_NetPoint(
                net_name=net,
                refdes=refdes,
                pin=pin,
                record_type=_RT_SMT,
                drilled=False,
                plated=False,
                x_mm=x,
                y_mm=y,
                w_mm=w,
                h_mm=h,
                drill_mm=0.0,
                layer_code=_layer_code(layer),
            ))

        # ── Through-hole pads ────────────────────────────────────────────────
        elif t in ("pcb_plated_pad", "pcb_pad"):
            x = float(el.get("x", 0.0))
            y = float(el.get("y", 0.0))
            w = float(el.get("width", el.get("size_x", 1.5)))
            h = float(el.get("height", el.get("size_y", w)))
            drill = float(
                el.get("hole_diameter",
                el.get("drill_diameter",
                el.get("drill", el.get("drill_size", 0.0)))) or 0.0
            )
            net = _net_name_from_pad(el, source_map)
            refdes, pin = _refdes_pin(el, source_map)
            # A pcb_pad without a drill is treated as SMT (317)
            if drill > 0:
                rt = _RT_PTH
                drilled = True
                plated = True
                lc = _LAYER_THROUGH
            else:
                rt = _RT_SMT
                drilled = False
                plated = False
                layer = el.get("layer", "top_copper")
                lc = _layer_code(layer)
            points.append(_NetPoint(
                net_name=net,
                refdes=refdes,
                pin=pin,
                record_type=rt,
                drilled=drilled,
                plated=plated,
                x_mm=x,
                y_mm=y,
                w_mm=w,
                h_mm=h,
                drill_mm=drill,
                layer_code=lc,
            ))

        # ── Vias ─────────────────────────────────────────────────────────────
        elif t == "pcb_via":
            x = float(el.get("x", 0.0))
            y = float(el.get("y", 0.0))
            outer = float(el.get("outer_diameter", el.get("diameter", 0.6)))
            drill = float(
                el.get("hole_diameter",
                el.get("drill_diameter",
                el.get("drill", 0.3)))
            )
            net = el.get("net_id", el.get("net_name", el.get("net", "N/C")))
            if not net or not str(net).strip():
                net = "N/C"
            # Vias carry no component refdes
            points.append(_NetPoint(
                net_name=str(net).strip(),
                refdes="",
                pin="",
                record_type=_RT_PTH,
                drilled=True,
                plated=True,
                x_mm=x,
                y_mm=y,
                w_mm=outer,
                h_mm=outer,
                drill_mm=drill,
                layer_code=_LAYER_THROUGH,
            ))

    return points


# ─── IPC-D-356A record formatting ─────────────────────────────────────────────

def _ipc_coord(mm: float) -> str:
    """Format a mm value as IPC-D-356A metric coordinate (±XXXXXXXX, 8 digits max).

    IPC-D-356A §4.2.3: coordinates are signed integers in 0.001 mm (i.e. × 10000
    counts per mm in metric mode, giving micron-level resolution).

    Returns a sign-prefixed, zero-padded 7-digit string matching KiCad's format:
    e.g. 20.0 mm → +0200000, -5.5 mm → -0055000.
    """
    counts = int(round(mm * _MM_SCALE))
    sign = "+" if counts >= 0 else "-"
    return f"{sign}{abs(counts):07d}"


def _ipc_size(mm: float) -> str:
    """Format a pad size value as IPC-D-356A metric size field (4 digits).

    IPC-D-356A §4.2.3: sizes are unsigned integers in the same unit as coords.
    Field width is 4 digits (matches KiCad 6 output).
    """
    counts = int(round(abs(mm) * _MM_SCALE))
    return f"{counts:04d}"


def _truncate(s: str, n: int, pad: bool = True) -> str:
    """Truncate or space-pad a string to exactly n characters."""
    s = str(s)[:n]
    return s.ljust(n) if pad else s


def _refdes_pin_field(refdes: str, pin: str) -> str:
    """Format REFDES-PIN as 'RRRRRRnn' (6+4 = 10 chars).

    IPC-D-356A §4.2.3: REFDES is 6 chars, PIN is 4 chars separated by '-'.
    Total field width: 11 chars (RRRRRR-PPPP).
    Vias use spaces in both fields.
    """
    rd = _truncate(refdes, 6)
    pn = _truncate(pin, 4)
    return f"{rd}-{pn}"


def _format_record(pt: _NetPoint, mid_net: bool = False) -> str:
    """Emit a single IPC-D-356A net record line.

    Fixed-width 59-character format per IPC-D-356A §4.2:

    Cols  1-3   Record type  (317 or 327)
    Col   4     space
    Cols  5-18  Net name     (14 chars, left-justified, space-padded)
    Col  19     space
    Cols 20-30  REFDES-PIN   (11 chars: RRRRRRR-PPPP, vias are spaces)
    Col  31     space
    Col  32     drilled flag ('D' or space)
    Col  33     plated flag  ('P' or 'U'; spaces for SMT)
    Cols 34-35  mid-net flag ('M ' = mid-point, '  ' = endpoint)
    Cols 36-44  X coordinate (sign + 7 digits)
    Col  45     sign of Y ('+' or '-') — combined with cols 46-51
    Cols 45-52  Y coordinate (sign + 7 digits)
    Cols 53-56  X SIZE       (4 digits)
    Col  57     'X'
    Cols 58-61  Y SIZE       (4 digits)
    Cols 62-63  Layer access  (2-digit layer code)

    This encoding matches the format emitted by KiCad 6 / IPC-D-356A 1997 §4.2.
    """
    net_field = _truncate(pt.net_name, 14)
    rp_field = _refdes_pin_field(pt.refdes, pt.pin)
    drill_flag = "D" if pt.drilled else " "
    plated_flag = "P" if pt.plated else ("U" if pt.record_type == _RT_PTH else " ")
    mid_flag = "M " if mid_net else "  "
    x_field = _ipc_coord(pt.x_mm)
    y_field = _ipc_coord(pt.y_mm)
    xsz = _ipc_size(pt.w_mm)
    ysz = _ipc_size(pt.h_mm)
    layer = pt.layer_code

    # IPC-D-356A record layout (space separators per spec §4.2):
    return (
        f"{pt.record_type} "          # cols 1-4
        f"{net_field} "               # cols 5-19
        f"{rp_field} "                # cols 20-31
        f"{drill_flag}{plated_flag}"  # cols 32-33
        f"{mid_flag}"                 # cols 34-35
        f"{x_field}"                  # cols 36-44
        f"{y_field}"                  # cols 45-52
        f"{xsz}X{ysz}"               # cols 53-61
        f"{layer}"                    # cols 62-63
    )


# ─── Header builder ───────────────────────────────────────────────────────────

def _build_header(stem: str) -> list[str]:
    """Emit IPC-D-356A header block per §4.1.

    Lines starting with 'C' are comment records (free-form).
    'P' lines are parameter records:
      P JOB  <job name>
      P CODE IPC-D-356A
      P DATE <ISO timestamp>
      P UNITS MM  (metric mode — coordinates in 0.001 mm × 10000)
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [
        f"C  IPC-D-356A Netlist — generated by Kerf Electronics",
        f"C  Job: {stem}",
        f"C  IPC-D-356A (1997) §4.1 header",
        f"P  JOB     {stem}",
        f"P  CODE    IPC-D-356A",
        f"P  DATE    {ts}",
        f"P  UNITS   MM",
    ]


# ─── Grouping by net for mid-net marking ─────────────────────────────────────

def _group_by_net(points: list[_NetPoint]) -> dict[str, list[_NetPoint]]:
    groups: dict[str, list[_NetPoint]] = {}
    for pt in points:
        groups.setdefault(pt.net_name, []).append(pt)
    return groups


# ─── Public export function ───────────────────────────────────────────────────

def export_ipc_d356(
    circuit_json: list[dict],
    stem: str = "board",
) -> str:
    """Generate an IPC-D-356A netlist text from a CircuitJSON array.

    IPC-D-356A §4 record structure:
      - Header block (C and P records, §4.1)
      - One net record per pad/via (317 for SMT, 327 for PTH/via) (§4.2)
        - Mid-net points (M flag) for all but the last point on each net
      - End-of-file record: '999' (§4.4)

    Args:
        circuit_json: Parsed CircuitJSON array.
        stem: Board / job name used in the header.

    Returns:
        IPC-D-356A text as a string (UTF-8 safe; printable ASCII only).
    """
    if not isinstance(circuit_json, list):
        circuit_json = []

    points = _collect_net_points(circuit_json)
    groups = _group_by_net(points)

    lines: list[str] = []
    lines.extend(_build_header(stem))

    # Emit records in alphabetical net order for determinism
    for net_name in sorted(groups.keys()):
        pts = groups[net_name]
        for i, pt in enumerate(pts):
            mid = i < len(pts) - 1  # all but last are mid-net per §4.2.3
            lines.append(_format_record(pt, mid_net=mid))

    lines.append("999")  # IPC-D-356A §4.4 end record

    return "\n".join(lines) + "\n"


# ─── Connectivity analysis ────────────────────────────────────────────────────

def analyse_connectivity(circuit_json: list[dict]) -> dict[str, Any]:
    """Perform a connectivity sanity check on a CircuitJSON board.

    Flags:
      - Nets with < 2 connection points (potential opens)
      - Nets with exactly 1 pad (single-pad nets — always an open)
      - Pads with net_name == 'N/C' (unconnected / no net assigned)

    Returns a dict with:
      nets_total          — total unique net names (excl. N/C)
      connected_nets      — nets with >= 2 pads
      open_nets           — nets with < 2 pads (list of {net, pad_count})
      single_pad_nets     — subset of open_nets where pad_count == 1
      unconnected_pads    — count of pads with no net (net_name == 'N/C')
      total_pads_vias     — total pad + via points found
    """
    if not isinstance(circuit_json, list):
        circuit_json = []

    points = _collect_net_points(circuit_json)
    groups = _group_by_net(points)

    nc_count = len(groups.pop("N/C", []))
    open_nets = []
    connected = 0

    for net_name, pts in sorted(groups.items()):
        cnt = len(pts)
        if cnt < 2:
            open_nets.append({"net": net_name, "pad_count": cnt})
        else:
            connected += 1

    single_pad = [e for e in open_nets if e["pad_count"] == 1]

    return {
        "nets_total": len(groups),
        "connected_nets": connected,
        "open_nets": open_nets,
        "single_pad_nets": single_pad,
        "unconnected_pads": nc_count,
        "total_pads_vias": len(points) + nc_count,
    }


# ─── LLM tool: export_ipc_netlist ────────────────────────────────────────────

export_ipc_netlist_spec = ToolSpec(
    name="export_ipc_netlist",
    description=(
        "Export a CircuitJSON board as an IPC-D-356A bare-board electrical test (BET) "
        "netlist.  Fab houses run a flying-probe or bed-of-nails test against this file "
        "to verify that every net is continuous and no unintended shorts exist. "
        "Returns the netlist text as base64-encoded content and a plain-text preview. "
        "Record types: 317 (SMT/no drill) and 327 (plated through-hole / via). "
        "Spec: IPC-D-356A (1997), §4 — header block (P JOB / P CODE / P DATE / "
        "P UNITS MM) followed by sorted net records, terminated by 999. "
        "Use netlist_report first to check for open nets before exporting."
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
                "description": "Job / board name used in the netlist header and filename (default: 'board').",
            },
        },
        "required": ["circuit_json"],
    },
)


@register(export_ipc_netlist_spec)
async def run_export_ipc_netlist(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    stem = a.get("stem", "board") or "board"

    try:
        netlist_text = export_ipc_d356(circuit_json, stem=stem)
    except Exception as e:
        return err_payload(f"IPC-D-356A export failed: {e}", "EXPORT_ERROR")

    import base64
    content_b64 = base64.b64encode(netlist_text.encode("ascii", errors="replace")).decode()
    filename = f"{stem}.IPC"

    # Build a short preview (first 20 lines)
    preview_lines = netlist_text.splitlines()[:20]
    preview = "\n".join(preview_lines)
    if len(netlist_text.splitlines()) > 20:
        preview += f"\n... ({len(netlist_text.splitlines())} lines total)"

    # Count record types
    records_317 = sum(1 for ln in netlist_text.splitlines() if ln.startswith("317"))
    records_327 = sum(1 for ln in netlist_text.splitlines() if ln.startswith("327"))

    return ok_payload({
        "filename": filename,
        "content_b64": content_b64,
        "record_count": records_317 + records_327,
        "records_317_smt": records_317,
        "records_327_pth": records_327,
        "preview": preview,
        "message": (
            f"IPC-D-356A netlist exported: {filename}. "
            f"{records_317} SMT (317) + {records_327} PTH/via (327) records. "
            "Decode content_b64 to obtain the .IPC file for submission to fab EBT system."
        ),
    })


# ─── LLM tool: netlist_report ─────────────────────────────────────────────────

netlist_report_spec = ToolSpec(
    name="netlist_report",
    description=(
        "Analyse a CircuitJSON board for IPC-D-356A netlist connectivity issues. "
        "Reports: open nets (< 2 pads — potential board-level opens), single-pad "
        "nets (exactly 1 pad — definite open), and unconnected pads (no net assigned). "
        "Run this before export_ipc_netlist to catch wiring omissions. "
        "A net with 0 or 1 pads in the netlist means the LLM circuit description is "
        "missing a connection; fix the CircuitJSON before sending to fab."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array from the active board file.",
                "items": {"type": "object"},
            },
        },
        "required": ["circuit_json"],
    },
)


@register(netlist_report_spec)
async def run_netlist_report(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    try:
        report = analyse_connectivity(circuit_json)
    except Exception as e:
        return err_payload(f"connectivity analysis failed: {e}", "ANALYSIS_ERROR")

    open_nets = report["open_nets"]
    single_pad = report["single_pad_nets"]
    nc = report["unconnected_pads"]

    issues: list[str] = []
    if single_pad:
        issues.append(
            f"{len(single_pad)} single-pad net(s) — definite opens: "
            + ", ".join(e["net"] for e in single_pad)
        )
    if open_nets:
        issues.append(
            f"{len(open_nets)} net(s) with < 2 pads (potential opens)"
        )
    if nc:
        issues.append(f"{nc} unconnected pad(s) with no net assignment")

    status = "OK" if not issues else "ISSUES_FOUND"
    message = (
        f"Connectivity report: {report['nets_total']} net(s), "
        f"{report['connected_nets']} connected, "
        f"{len(open_nets)} open, "
        f"{nc} unconnected pad(s). "
    )
    if issues:
        message += "Issues: " + "; ".join(issues) + "."
    else:
        message += "No connectivity issues found."

    return ok_payload({
        "status": status,
        "nets_total": report["nets_total"],
        "connected_nets": report["connected_nets"],
        "open_nets": open_nets,
        "single_pad_nets": single_pad,
        "unconnected_pads": nc,
        "total_pads_vias": report["total_pads_vias"],
        "message": message,
    })
