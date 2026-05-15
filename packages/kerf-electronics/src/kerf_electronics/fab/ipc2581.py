"""
IPC-2581 XML writer for CircuitJSON boards.

Generates a minimal but structurally valid IPC-2581 Rev B XML document from
a CircuitJSON array.  The output covers:

  <Header>       — step name, timestamp, units
  <Content>      — layer stack (LayerFeature list)
  <Bom>          — BomItem list (one entry per placed source_component)
  <Ecad>         — Board outline, component placements, drill patterns

IPC-2581 schema reference: IPC-2581B (2012).  The subset emitted here is
validated in tests against the structural invariants (required elements, XML
well-formedness, numeric attributes) rather than the full XSD (which requires
a proprietary schema file).

Units: millimetres throughout.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any


# ─── helpers ──────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mm(v: float) -> str:
    return f"{v:.6f}"


def _deg(v: float) -> str:
    return f"{v:.4f}"


# ─── layer classification ─────────────────────────────────────────────────────

def _layer_side(name: str) -> str:
    if "top" in name:
        return "TOP"
    if "bottom" in name:
        return "BOTTOM"
    return "INTERNAL"


def _layer_function(name: str) -> str:
    if "copper" in name or name.startswith("inner"):
        return "CONDUCTOR"
    if "mask" in name:
        return "SOLDERMASK"
    if "silk" in name:
        return "SILKSCREEN"
    if "paste" in name:
        return "PASTE"
    if "drill" in name:
        return "HOLE"
    if "edge" in name or "outline" in name:
        return "BOARD_OUTLINE"
    return "CONDUCTOR"


# ─── data extraction (mirrors pnp.py / fab_bom.py) ──────────────────────────

def _collect_source_components(circuit_json: list[dict]) -> dict[str, dict]:
    src: dict[str, dict] = {}
    for el in circuit_json:
        if el.get("type") == "source_component":
            sid = el.get("source_component_id", el.get("id", ""))
            if sid:
                src[sid] = el
    return src


def _collect_pcb_components(circuit_json: list[dict]) -> list[dict]:
    return [el for el in circuit_json if el.get("type") == "pcb_component"]


def _collect_layers(circuit_json: list[dict]) -> list[str]:
    """Return an ordered list of unique layer names mentioned in the design."""
    seen: list[str] = []
    order = [
        "top_copper", "top_silk", "top_mask", "top_paste",
        "bottom_copper", "bottom_silk", "bottom_mask", "bottom_paste",
        "edge_cuts",
    ]
    for name in order:
        seen.append(name)
    # Add any inner layers found in traces / pads
    for el in circuit_json:
        for key in ("layer", "route"):
            val = el.get(key)
            if isinstance(val, str) and val not in seen:
                seen.append(val)
            elif isinstance(val, list):
                for pt in val:
                    if isinstance(pt, dict):
                        lname = pt.get("layer", "")
                        if lname and lname not in seen:
                            seen.append(lname)
    return seen


def _board_dims(circuit_json: list[dict]) -> tuple[float, float]:
    for el in circuit_json:
        if el.get("type") in ("pcb_board", "board"):
            w = float(el.get("width", 100.0))
            h = float(el.get("height", 100.0))
            return w, h
    return 100.0, 100.0


def _outline_vertices(circuit_json: list[dict], w: float, h: float) -> list[tuple[float, float]]:
    for el in circuit_json:
        if el.get("type") == "pcb_outline_path":
            pts = el.get("route", el.get("points", []))
            if len(pts) >= 3:
                return [(float(p.get("x", 0)), float(p.get("y", 0))) for p in pts]
    # Fall back to bounding rect
    return [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]


# ─── XML builders ─────────────────────────────────────────────────────────────

def _build_header(root: ET.Element, step_name: str) -> None:
    hdr = ET.SubElement(root, "Header")
    ET.SubElement(hdr, "StepRef", name=step_name)
    spec = ET.SubElement(hdr, "Spec")
    spec.text = "IPC-2581B"
    units = ET.SubElement(hdr, "Units")
    units.text = "MM"
    ts_el = ET.SubElement(hdr, "Date")
    ts_el.text = _ts()


def _build_layer_stack(root: ET.Element, layers: list[str]) -> None:
    ecad = ET.SubElement(root, "LayerStack")
    for idx, name in enumerate(layers):
        lf = ET.SubElement(ecad, "LayerFeature",
                           name=name,
                           side=_layer_side(name),
                           function=_layer_function(name),
                           sequence=str(idx))
        # Thickness placeholder (0.035 mm for copper, 0.1 for others)
        thick = "0.035" if _layer_function(name) == "CONDUCTOR" else "0.100"
        lf.set("thickness", thick)


def _build_bom(root: ET.Element,
               pcb_components: list[dict],
               source_map: dict[str, dict]) -> None:
    bom_el = ET.SubElement(root, "Bom")
    ET.SubElement(bom_el, "BomHeader", units="MM", created=_ts())

    for comp in pcb_components:
        sid = comp.get("source_component_id", "")
        src = source_map.get(sid, {})
        refdes = src.get("name", src.get("refdes", sid or "?"))
        value = src.get("value", src.get("part_value", ""))
        footprint = src.get("footprint", "")
        mpn = src.get("mpn", src.get("manufacturer_part_number", ""))
        description = src.get("description", "")

        bom_item = ET.SubElement(bom_el, "BomItem",
                                 refDes=refdes,
                                 quantity="1",
                                 mpn=mpn,
                                 value=value,
                                 footprint=footprint)
        if description:
            bom_item.set("description", description)


def _build_ecad(root: ET.Element,
                circuit_json: list[dict],
                pcb_components: list[dict],
                source_map: dict[str, dict],
                step_name: str) -> None:
    ecad_el = ET.SubElement(root, "Ecad")
    step_el = ET.SubElement(ecad_el, "CadData")

    w, h = _board_dims(circuit_json)
    board_el = ET.SubElement(step_el, "Board",
                             xSize=_mm(w), ySize=_mm(h))

    # Outline
    outline_verts = _outline_vertices(circuit_json, w, h)
    outline_el = ET.SubElement(board_el, "Outline")
    poly_el = ET.SubElement(outline_el, "Polygon")
    for (vx, vy) in outline_verts:
        ET.SubElement(poly_el, "Vertex", x=_mm(vx), y=_mm(vy))
    # Close
    if outline_verts:
        ET.SubElement(poly_el, "Vertex", x=_mm(outline_verts[0][0]), y=_mm(outline_verts[0][1]))

    # Component placements
    placements_el = ET.SubElement(step_el, "ComponentPlacement")
    for comp in pcb_components:
        sid = comp.get("source_component_id", "")
        src = source_map.get(sid, {})
        refdes = src.get("name", src.get("refdes", sid or "?"))
        x = float(comp.get("x", 0.0))
        y = float(comp.get("y", 0.0))
        rot = float(comp.get("rotation", 0.0))
        layer_attr = comp.get("layer", "top_copper")
        side = "TOP" if "bottom" not in layer_attr else "BOTTOM"

        pl_el = ET.SubElement(placements_el, "Placement",
                              refDes=refdes,
                              x=_mm(x),
                              y=_mm(y),
                              rotation=_deg(rot),
                              side=side)

    # Drill patterns (vias + plated pads)
    drill_el = ET.SubElement(step_el, "DrillPattern")
    for el in circuit_json:
        t = el.get("type", "")
        if t == "pcb_via":
            hd = float(el.get("hole_diameter", el.get("drill_diameter", 0.3)))
            od = float(el.get("outer_diameter", el.get("diameter", 0.6)))
            vx = float(el.get("x", 0.0))
            vy = float(el.get("y", 0.0))
            ET.SubElement(drill_el, "DrillHit",
                          x=_mm(vx), y=_mm(vy),
                          drillDiameter=_mm(hd),
                          padDiameter=_mm(od),
                          plated="true")
        elif t in ("pcb_plated_pad", "pcb_pad"):
            drill = el.get("hole_diameter", el.get("drill_diameter", 0.0))
            if drill and float(drill) > 0:
                ET.SubElement(drill_el, "DrillHit",
                              x=_mm(float(el.get("x", 0.0))),
                              y=_mm(float(el.get("y", 0.0))),
                              drillDiameter=_mm(float(drill)),
                              padDiameter=_mm(float(el.get("width", 1.5))),
                              plated="true")


# ─── Public API ───────────────────────────────────────────────────────────────

def export_ipc2581(
    circuit_json: list[dict],
    stem: str = "board",
    step_name: str | None = None,
) -> dict[str, str]:
    """Generate an IPC-2581 XML document from a CircuitJSON array.

    Returns:
        dict of {filename: xml_text}
    """
    if not isinstance(circuit_json, list):
        circuit_json = []

    if step_name is None:
        step_name = stem

    source_map = _collect_source_components(circuit_json)
    pcb_components = _collect_pcb_components(circuit_json)
    layers = _collect_layers(circuit_json)

    root = ET.Element("IPC-2581", {
        "xmlns": "http://www.ipc.org/2581",
        "revision": "B",
        "schemaVersion": "1.4",
        "units": "MM",
    })

    _build_header(root, step_name)
    _build_layer_stack(root, layers)
    _build_bom(root, pcb_components, source_map)
    _build_ecad(root, circuit_json, pcb_components, source_map, step_name)

    ET.indent(root, space="  ")
    xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=False)
    xml_text = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes + "\n"

    return {f"{stem}.xml": xml_text}
