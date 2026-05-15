"""
Testpoint auto-placement and bed-of-nails fixture report for CircuitJSON boards.

Manufacturing test (ICT / bed-of-nails) needs one accessible probe point per net.
This module:

  1. Reuses _collect_net_points from ipc_netlist.py to extract all pad/via
     candidates from a CircuitJSON board (no re-invention of extraction logic).
  2. Selects a single "best" probe candidate per net using a priority ranking:
       a. Via on access_side (probes everywhere, no component risk)
       b. PTH pad on access_side
       c. SMT pad on access_side
       d. SMT/PTH pad on opposite side (fallback — fixture can probe reverse)
     Within each tier, the largest pad wins (easier probe registration).
  3. Enforces a minimum probe pitch (default 2.54 mm / 100-mil grid) using a
     simple greedy grid-snap: each selected probe position is snapped to the
     nearest grid intersection, and a position is rejected if it sits within
     min_spacing_mm of an already-placed probe.  Nets whose only candidate
     conflicts with existing probes are flagged as unreachable.
  4. Generates a bed-of-nails fixture report:
       - probe_list: [{net, x_mm, y_mm, side, pad_type, probe_dia_mm, refdes, pin}]
       - unreachable_nets: [{net, reason}]
       - coverage_pct: (reachable nets / total named nets) * 100
       - drill_csv: CSV text (net, x_mm, y_mm, side, probe_dia_mm) for CNC drill
         or fixture-shop submission

Two @register LLM tools:
  generate_testpoints  — place probes, return probe list + unreachable nets
  fixture_report       — full fixture report including coverage % + drill CSV
"""

from __future__ import annotations

import csv
import io
import json
import math
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

# Reuse extraction from ipc_netlist — single source of truth for pad/via parsing
from kerf_electronics.tools.ipc_netlist import _collect_net_points, _NetPoint

# ─── Constants ────────────────────────────────────────────────────────────────

# Default probe grid pitch (100-mil / 2.54 mm — standard ICT fixture grid)
_DEFAULT_PITCH_MM = 2.54

# Default access side
_DEFAULT_ACCESS_SIDE = "top"

# Minimum probe diameter (mm) derived from pad size: clamped to this range
_PROBE_DIA_MIN_MM = 0.5
_PROBE_DIA_MAX_MM = 2.5

# Layer-code → side mapping (from ipc_netlist layer codes)
_LAYER_TO_SIDE: dict[str, str] = {
    "01": "top",
    "02": "bottom",
    "00": "both",  # through-hole / via — accessible from both sides
}


# ─── Probe selection model ────────────────────────────────────────────────────

def _side_of(pt: _NetPoint) -> str:
    """Map a _NetPoint layer_code to a physical side string."""
    return _LAYER_TO_SIDE.get(pt.layer_code, "top")


def _probe_dia(pt: _NetPoint) -> float:
    """Choose a probe tip diameter based on pad size.

    Convention (IPC-9252 / common fixture practice):
      - Use min(pad_width, pad_height) / 2, clamped to [0.5, 2.5] mm.
    Via outer diameters and pad sizes drive this; larger pads allow larger
    (more reliable) probes.
    """
    smaller_dim = min(pt.w_mm, pt.h_mm)
    raw = smaller_dim / 2.0
    return max(_PROBE_DIA_MIN_MM, min(_PROBE_DIA_MAX_MM, raw))


def _priority(pt: _NetPoint, access_side: str) -> int:
    """Lower score = higher priority for probe selection.

    Priority tiers (lower = preferred):
      0 — via on preferred side (both-side access)
      1 — PTH pad (both-side access)
      2 — SMT pad on preferred/access side
      3 — SMT pad on opposite side (fallback)
      9 — N/C (skip entirely)
    """
    if pt.net_name == "N/C":
        return 9
    side = _side_of(pt)
    is_via = pt.refdes == "" and pt.pin == "" and pt.record_type == "327"
    is_pth = pt.drilled and pt.plated
    if side == "both":
        if is_via:
            return 0
        if is_pth:
            return 1
        return 2  # unusual (PTH not-plated?) — treat as ok
    if side == access_side:
        return 2
    return 3  # wrong side — possible but less preferred


def _grid_snap(val: float, pitch: float) -> float:
    """Snap a coordinate to the nearest grid point at given pitch."""
    if pitch <= 0:
        return val
    return round(round(val / pitch) * pitch, 6)


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


# ─── Core placement algorithm ─────────────────────────────────────────────────

def place_testpoints(
    circuit_json: list[dict],
    access_side: str = _DEFAULT_ACCESS_SIDE,
    min_spacing_mm: float = _DEFAULT_PITCH_MM,
) -> dict[str, Any]:
    """Auto-place one probe point per net using pad/via candidates.

    Algorithm:
    1. Extract all pad/via points via _collect_net_points (reused from
       ipc_netlist, same CircuitJSON vocabulary).
    2. Group by net name; skip N/C.
    3. For each net, rank candidates by priority tier + descending pad size.
    4. Pick the highest-priority candidate that fits on the probe grid
       (min_spacing_mm clearance from already-placed probes).
       - Snap each candidate to the nearest grid position.
       - If snapped position is within min_spacing_mm of any placed probe,
         try the next candidate.
       - If all candidates fail → flag net as unreachable.
    5. Return placed probes + unreachable nets + coverage stats.

    Returns a dict with:
      probes         — list of probe dicts
      unreachable    — list of {net, reason} for unplaceable nets
      net_count      — total named nets (excl. N/C)
      placed_count   — probes placed
      coverage_pct   — placed_count / net_count * 100
    """
    if not isinstance(circuit_json, list):
        circuit_json = []

    all_pts = _collect_net_points(circuit_json)

    # Group by net name, skip N/C
    by_net: dict[str, list[_NetPoint]] = {}
    for pt in all_pts:
        if pt.net_name == "N/C":
            continue
        by_net.setdefault(pt.net_name, []).append(pt)

    # Sort nets deterministically
    net_names = sorted(by_net.keys())
    net_count = len(net_names)

    placed: list[dict] = []  # {net, x_mm, y_mm, snapped_x, snapped_y, side, pad_type, probe_dia_mm, refdes, pin}
    placed_positions: list[tuple[float, float]] = []  # (snapped_x, snapped_y)
    unreachable: list[dict] = []

    for net in net_names:
        candidates = sorted(
            by_net[net],
            key=lambda p: (_priority(p, access_side), -max(p.w_mm, p.h_mm)),
        )

        placed_probe = False
        for pt in candidates:
            prio = _priority(pt, access_side)
            # N/C guard (should not reach here but belt-and-braces)
            if prio == 9:
                continue

            sx = _grid_snap(pt.x_mm, min_spacing_mm)
            sy = _grid_snap(pt.y_mm, min_spacing_mm)

            # Check spacing against all already-placed probes
            conflict = any(
                _dist(sx, sy, px, py) < min_spacing_mm * 0.999
                for px, py in placed_positions
            )
            if conflict:
                continue

            # This candidate is acceptable
            side = _side_of(pt)
            if side == "both":
                side = access_side  # vias / PTH — probe from preferred side

            is_via = pt.refdes == "" and pt.pin == ""
            pad_type = "via" if is_via else ("pth" if pt.drilled else "smt")

            placed.append({
                "net": net,
                "x_mm": round(pt.x_mm, 4),
                "y_mm": round(pt.y_mm, 4),
                "snapped_x_mm": sx,
                "snapped_y_mm": sy,
                "side": side,
                "pad_type": pad_type,
                "probe_dia_mm": round(_probe_dia(pt), 3),
                "refdes": pt.refdes,
                "pin": pt.pin,
            })
            placed_positions.append((sx, sy))
            placed_probe = True
            break

        if not placed_probe:
            # Determine reason: no candidates at all, or all conflicted
            if not candidates:
                reason = "no_pads"
            else:
                reason = "spacing_conflict"
            unreachable.append({"net": net, "reason": reason})

    coverage_pct = (len(placed) / net_count * 100.0) if net_count > 0 else 0.0

    return {
        "probes": placed,
        "unreachable": unreachable,
        "net_count": net_count,
        "placed_count": len(placed),
        "coverage_pct": round(coverage_pct, 1),
    }


def build_fixture_report(
    circuit_json: list[dict],
    access_side: str = _DEFAULT_ACCESS_SIDE,
    min_spacing_mm: float = _DEFAULT_PITCH_MM,
    stem: str = "board",
) -> dict[str, Any]:
    """Generate a full bed-of-nails fixture report.

    Calls place_testpoints, then adds:
      - drill_csv: CSV text for submitting probe positions to fixture shop
      - summary: human-readable text block
    """
    result = place_testpoints(circuit_json, access_side=access_side, min_spacing_mm=min_spacing_mm)

    probes = result["probes"]

    # Build drill/probe CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Net", "X_mm", "Y_mm", "Side", "Probe_dia_mm", "Pad_type", "Refdes", "Pin"])
    for p in probes:
        writer.writerow([
            p["net"],
            p["snapped_x_mm"],
            p["snapped_y_mm"],
            p["side"],
            p["probe_dia_mm"],
            p["pad_type"],
            p["refdes"],
            p["pin"],
        ])
    drill_csv = buf.getvalue()

    unreachable = result["unreachable"]
    coverage_pct = result["coverage_pct"]

    summary_lines = [
        f"Bed-of-nails fixture report: {stem}",
        f"  Access side    : {access_side}",
        f"  Probe pitch    : {min_spacing_mm} mm",
        f"  Total nets     : {result['net_count']}",
        f"  Probes placed  : {result['placed_count']}",
        f"  Unreachable    : {len(unreachable)}",
        f"  Coverage       : {coverage_pct:.1f}%",
    ]
    if unreachable:
        summary_lines.append("  Unreachable nets:")
        for u in unreachable:
            summary_lines.append(f"    {u['net']}: {u['reason']}")
    summary = "\n".join(summary_lines)

    return {
        "probes": probes,
        "unreachable": unreachable,
        "net_count": result["net_count"],
        "placed_count": result["placed_count"],
        "coverage_pct": coverage_pct,
        "drill_csv": drill_csv,
        "summary": summary,
        "stem": stem,
        "access_side": access_side,
        "min_spacing_mm": min_spacing_mm,
    }


# ─── LLM tool: generate_testpoints ───────────────────────────────────────────

generate_testpoints_spec = ToolSpec(
    name="generate_testpoints",
    description=(
        "Auto-place one probe point per net for ICT (in-circuit test) / bed-of-nails "
        "fixture planning from a CircuitJSON board. "
        "Candidates are existing pads and vias — no new copper is added. "
        "Prefers vias (accessible from both sides), then PTH pads, then SMT pads on "
        "the chosen access side. Snaps probe positions to a min_spacing grid "
        "(default 2.54 mm / 100-mil) and enforces minimum probe-to-probe clearance. "
        "Returns a probe list (net, X/Y, side, probe diameter, pad type) and a list "
        "of nets with no accessible probe point. "
        "Use fixture_report to get the full report including coverage % and drill CSV."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array from the active board file.",
                "items": {"type": "object"},
            },
            "access_side": {
                "type": "string",
                "enum": ["top", "bottom"],
                "description": (
                    "Which board side the fixture accesses. "
                    "Default 'top'. Through-hole pads/vias are reachable from either side."
                ),
            },
            "min_spacing_mm": {
                "type": "number",
                "description": (
                    "Minimum centre-to-centre probe spacing in mm. "
                    "Standard ICT grid is 2.54 mm (100 mil). "
                    "Tighter fixtures can use 1.27 mm (50 mil)."
                ),
            },
        },
        "required": ["circuit_json"],
    },
)


@register(generate_testpoints_spec)
async def run_generate_testpoints(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    access_side = a.get("access_side", _DEFAULT_ACCESS_SIDE)
    if access_side not in ("top", "bottom"):
        return err_payload("access_side must be 'top' or 'bottom'", "BAD_ARGS")

    min_spacing_mm = float(a.get("min_spacing_mm", _DEFAULT_PITCH_MM))
    if min_spacing_mm <= 0:
        return err_payload("min_spacing_mm must be > 0", "BAD_ARGS")

    try:
        result = place_testpoints(
            circuit_json,
            access_side=access_side,
            min_spacing_mm=min_spacing_mm,
        )
    except Exception as e:
        return err_payload(f"testpoint placement failed: {e}", "PLACEMENT_ERROR")

    probes = result["probes"]
    unreachable = result["unreachable"]
    coverage_pct = result["coverage_pct"]

    message_parts = [
        f"Testpoints placed: {result['placed_count']} probes for "
        f"{result['net_count']} net(s). Coverage: {coverage_pct:.1f}%."
    ]
    if unreachable:
        message_parts.append(
            f"{len(unreachable)} net(s) have no accessible probe point: "
            + ", ".join(u["net"] for u in unreachable[:10])
            + ("..." if len(unreachable) > 10 else "")
            + ". Use fixture_report for details."
        )

    return ok_payload({
        "probe_count": result["placed_count"],
        "net_count": result["net_count"],
        "unreachable_count": len(unreachable),
        "coverage_pct": coverage_pct,
        "probes": probes,
        "unreachable_nets": unreachable,
        "access_side": access_side,
        "min_spacing_mm": min_spacing_mm,
        "message": " ".join(message_parts),
    })


# ─── LLM tool: fixture_report ─────────────────────────────────────────────────

fixture_report_spec = ToolSpec(
    name="fixture_report",
    description=(
        "Generate a complete bed-of-nails ICT fixture report from a CircuitJSON board. "
        "Includes: probe list (net, X/Y mm snapped to probe grid, side, probe diameter), "
        "list of unreachable nets (no accessible pad, or all pads conflict with spacing), "
        "coverage % (probed nets / total named nets), and a drill/probe CSV ready for "
        "fixture shop submission. "
        "Probe diameter is derived from pad size: min(w, h) / 2, clamped to 0.5–2.5 mm. "
        "Use generate_testpoints for a quick probe list; use this tool when the user needs "
        "the full fixture deliverable (coverage metric + drill CSV)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array from the active board file.",
                "items": {"type": "object"},
            },
            "access_side": {
                "type": "string",
                "enum": ["top", "bottom"],
                "description": (
                    "Which board side the fixture accesses. Default 'top'. "
                    "Through-hole pads/vias are accessible from either side."
                ),
            },
            "min_spacing_mm": {
                "type": "number",
                "description": (
                    "Minimum centre-to-centre probe spacing in mm (default 2.54 / 100 mil). "
                    "Must match the fixture's physical probe pitch capability."
                ),
            },
            "stem": {
                "type": "string",
                "description": "Board name used in the report header (default 'board').",
            },
        },
        "required": ["circuit_json"],
    },
)


@register(fixture_report_spec)
async def run_fixture_report(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    access_side = a.get("access_side", _DEFAULT_ACCESS_SIDE)
    if access_side not in ("top", "bottom"):
        return err_payload("access_side must be 'top' or 'bottom'", "BAD_ARGS")

    min_spacing_mm = float(a.get("min_spacing_mm", _DEFAULT_PITCH_MM))
    if min_spacing_mm <= 0:
        return err_payload("min_spacing_mm must be > 0", "BAD_ARGS")

    stem = a.get("stem", "board") or "board"

    try:
        report = build_fixture_report(
            circuit_json,
            access_side=access_side,
            min_spacing_mm=min_spacing_mm,
            stem=stem,
        )
    except Exception as e:
        return err_payload(f"fixture report failed: {e}", "REPORT_ERROR")

    csv_filename = f"{stem}-fixture-probes.csv"

    return ok_payload({
        "probe_count": report["placed_count"],
        "net_count": report["net_count"],
        "unreachable_count": len(report["unreachable"]),
        "coverage_pct": report["coverage_pct"],
        "probes": report["probes"],
        "unreachable_nets": report["unreachable"],
        "drill_csv": report["drill_csv"],
        "csv_filename": csv_filename,
        "summary": report["summary"],
        "access_side": access_side,
        "min_spacing_mm": min_spacing_mm,
        "message": (
            f"Fixture report for '{stem}': "
            f"{report['placed_count']}/{report['net_count']} net(s) probed "
            f"({report['coverage_pct']:.1f}% coverage). "
            f"{len(report['unreachable'])} net(s) unreachable. "
            f"Drill CSV ready as '{csv_filename}'."
        ),
    })
