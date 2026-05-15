"""
Pick-and-place (P&P / centroid) CSV writer for CircuitJSON boards.

Generates IPC-7711B-compatible centroid CSVs from the pcb_component and
source_component elements of a CircuitJSON array.

Output columns (one CSV per side — top/bottom):
  Designator, Value, Footprint, MidX(mm), MidY(mm), Ref X, Ref Y,
  Rotation(deg), Layer

CircuitJSON element types used:
  source_component  → refdes (name), value, mpn, footprint metadata
  pcb_component     → x, y, rotation, layer (links via source_component_id)
"""

from __future__ import annotations

import csv
import io
from typing import Any


# ─── data extraction ─────────────────────────────────────────────────────────

def _extract_components(circuit_json: list[dict]) -> list[dict]:
    """Return a list of merged component dicts with placement + metadata."""
    # Index source_components by source_component_id
    source: dict[str, dict] = {}
    for el in circuit_json:
        if el.get("type") == "source_component":
            sid = el.get("source_component_id", el.get("id", ""))
            if sid:
                source[sid] = el

    components: list[dict] = []
    for el in circuit_json:
        if el.get("type") != "pcb_component":
            continue
        sid = el.get("source_component_id", "")
        src = source.get(sid, {})

        refdes = src.get("name", src.get("refdes", el.get("name", sid or "?")))
        value = src.get("value", src.get("part_value", ""))
        footprint = src.get("footprint", src.get("ftype", el.get("footprint", "")))
        mpn = src.get("mpn", src.get("manufacturer_part_number", ""))

        x = float(el.get("x", 0.0))
        y = float(el.get("y", 0.0))
        rotation = float(el.get("rotation", 0.0))

        # Determine side from layer attribute
        layer_attr = el.get("layer", "top_copper")
        if "bottom" in layer_attr or el.get("side", "") == "bottom":
            side = "bottom"
        else:
            side = "top"

        components.append({
            "refdes": refdes,
            "value": value,
            "footprint": footprint,
            "mpn": mpn,
            "x": x,
            "y": y,
            "rotation": rotation,
            "side": side,
        })

    # Sort for determinism: side, then refdes
    components.sort(key=lambda c: (c["side"], c["refdes"]))
    return components


# ─── CSV generator ────────────────────────────────────────────────────────────

_HEADER = [
    "Designator",
    "Value",
    "Footprint",
    "MidX(mm)",
    "MidY(mm)",
    "Rotation(deg)",
    "Layer",
    "MPN",
]


def _render_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_HEADER, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "Designator": r["refdes"],
            "Value": r["value"],
            "Footprint": r["footprint"],
            "MidX(mm)": f"{r['x']:.4f}",
            "MidY(mm)": f"{r['y']:.4f}",
            "Rotation(deg)": f"{r['rotation']:.2f}",
            "Layer": "Top" if r["side"] == "top" else "Bottom",
            "MPN": r["mpn"],
        })
    return buf.getvalue()


# ─── Public API ───────────────────────────────────────────────────────────────

def export_pnp(
    circuit_json: list[dict],
    stem: str = "board",
) -> dict[str, str]:
    """Generate pick-and-place CSVs from a CircuitJSON array.

    Returns:
        dict of {filename: csv_text}
        Both top and bottom CSVs are always returned (may be empty except
        for the header row if no components exist on that side).
    """
    if not isinstance(circuit_json, list):
        circuit_json = []

    components = _extract_components(circuit_json)

    top_rows = [c for c in components if c["side"] == "top"]
    bottom_rows = [c for c in components if c["side"] == "bottom"]

    return {
        f"{stem}-top-pnp.csv": _render_csv(top_rows),
        f"{stem}-bottom-pnp.csv": _render_csv(bottom_rows),
    }
