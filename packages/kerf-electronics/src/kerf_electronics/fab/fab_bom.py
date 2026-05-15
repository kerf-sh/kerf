"""
Fab BOM (Bill of Materials) CSV writer for CircuitJSON boards.

Reuses the existing BOM rollup concept from kerf-chat/llm_docs/bom.md:
groups by (value, footprint) and rolls up refdes designators + quantities.

Output columns match the assembly-house requirements used by JLC / MacroFab:
  Item, Qty, Refdes, Value, Footprint, MPN, Manufacturer, Distributor,
  DistributorPN, Description

CircuitJSON element types used:
  source_component  → refdes, value, footprint, mpn, distributor info
  pcb_component     → placement (confirms component is physically placed)
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Any


# ─── grouping key ─────────────────────────────────────────────────────────────

def _group_key(src: dict) -> tuple[str, str]:
    value = src.get("value", src.get("part_value", "")).strip()
    footprint = src.get("footprint", src.get("ftype", "")).strip()
    return (value, footprint)


# ─── data extraction ─────────────────────────────────────────────────────────

def _extract_placed_refdes(circuit_json: list[dict]) -> set[str]:
    """Return the set of source_component_ids that have a pcb_component."""
    placed: set[str] = set()
    for el in circuit_json:
        if el.get("type") == "pcb_component":
            sid = el.get("source_component_id", el.get("id", ""))
            if sid:
                placed.add(sid)
    return placed


def _pick_cheapest_distributor(src: dict) -> tuple[str, str]:
    """Return (distributor_name, part_number) for cheapest entry."""
    distribs = src.get("distributors", [])
    if not distribs:
        return ("", "")
    # Sort by unit_price_usd ascending, picking lowest
    def price(d):
        try:
            return float(d.get("unit_price_usd", d.get("unit_price", 9999)))
        except (TypeError, ValueError):
            return 9999.0
    cheapest = min(distribs, key=price)
    name = cheapest.get("name", cheapest.get("distributor", ""))
    pn = cheapest.get("part_number", cheapest.get("distributor_part_number", ""))
    return (name, pn)


def _extract_bom_rows(circuit_json: list[dict]) -> list[dict]:
    """Extract one row per unique (value, footprint) group."""
    placed_ids = _extract_placed_refdes(circuit_json)

    # Index source_components
    source: dict[str, dict] = {}
    for el in circuit_json:
        if el.get("type") == "source_component":
            sid = el.get("source_component_id", el.get("id", ""))
            if sid:
                source[sid] = el

    # Build groups: key → list of source_component dicts for placed components
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for sid, src in source.items():
        if sid not in placed_ids and placed_ids:
            # If we have pcb_components at all, skip unplaced sources
            continue
        key = _group_key(src)
        groups[key].append((sid, src))

    rows = []
    for item_num, (key, entries) in enumerate(sorted(groups.items()), start=1):
        value, footprint = key
        refdes_list = sorted(
            src.get("name", src.get("refdes", sid))
            for sid, src in entries
        )
        qty = len(entries)

        # Take metadata from first entry
        _, first = entries[0]
        mpn = first.get("mpn", first.get("manufacturer_part_number", ""))
        manufacturer = first.get("manufacturer", "")
        description = first.get("description", first.get("part_description", ""))
        dist_name, dist_pn = _pick_cheapest_distributor(first)

        rows.append({
            "item": item_num,
            "qty": qty,
            "refdes": ", ".join(refdes_list),
            "value": value,
            "footprint": footprint,
            "mpn": mpn,
            "manufacturer": manufacturer,
            "distributor": dist_name,
            "distributor_pn": dist_pn,
            "description": description,
        })

    return rows


# ─── CSV renderer ─────────────────────────────────────────────────────────────

_HEADER = [
    "Item",
    "Qty",
    "Refdes",
    "Value",
    "Footprint",
    "MPN",
    "Manufacturer",
    "Distributor",
    "DistributorPN",
    "Description",
]


def _render_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_HEADER, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "Item": r["item"],
            "Qty": r["qty"],
            "Refdes": r["refdes"],
            "Value": r["value"],
            "Footprint": r["footprint"],
            "MPN": r["mpn"],
            "Manufacturer": r["manufacturer"],
            "Distributor": r["distributor"],
            "DistributorPN": r["distributor_pn"],
            "Description": r["description"],
        })
    return buf.getvalue()


# ─── Public API ───────────────────────────────────────────────────────────────

def export_fab_bom(
    circuit_json: list[dict],
    stem: str = "board",
) -> dict[str, str]:
    """Generate a fab BOM CSV from a CircuitJSON array.

    Returns:
        dict of {filename: csv_text}
    """
    if not isinstance(circuit_json, list):
        circuit_json = []

    rows = _extract_bom_rows(circuit_json)
    return {f"{stem}-bom.csv": _render_csv(rows)}
