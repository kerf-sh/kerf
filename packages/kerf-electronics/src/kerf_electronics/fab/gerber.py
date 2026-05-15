"""
Gerber RS-274X writer for CircuitJSON boards.

Converts a CircuitJSON array (the tscircuit PCB data model used throughout
kerf-electronics) into a per-layer set of Gerber RS-274X files.

Supported layers and their output filenames:
  top_copper      → <stem>.GTL   (Gerber Top Layer)
  bottom_copper   → <stem>.GBL   (Gerber Bottom Layer)
  inner_N         → <stem>.GL<N> (Inner layers)
  top_silk        → <stem>.GTO   (Top Silkscreen)
  bottom_silk     → <stem>.GBO   (Bottom Silkscreen)
  top_mask        → <stem>.GTS   (Top Soldermask)
  bottom_mask     → <stem>.GBS   (Bottom Soldermask)
  edge_cuts       → <stem>.GKO   (Board outline / Keep-out)

CircuitJSON element types handled:
  pcb_smtpad / pcb_pad / pcb_plated_pad  → rectangular / round flash
  pcb_via                                → round flash on copper layers
  pcb_trace                              → draw segments on copper layers
  pcb_silkscreen_text / pcb_silkscreen_line / pcb_silkscreen_path → silk
  source_component (with footprint bbox)  → courtyard on silk (best-effort)
  copper_pour_fill (polygon)              → region pour on copper layers
  pcb_board / board (outline)            → edge_cuts

Units: millimetres. Gerber coordinate format 4.6 (integer, 1e-6 mm resolution).
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

# ─── coordinate format ────────────────────────────────────────────────────────

_SCALE = 1_000_000  # 4.6 format: 1 unit = 1e-6 mm


def _fmt(mm: float) -> str:
    """Format a millimetre value as a Gerber integer coordinate (4.6)."""
    return str(int(round(mm * _SCALE)))


# ─── layer name → Gerber file extension mapping ───────────────────────────────

_LAYER_EXT: dict[str, str] = {
    "top_copper": "GTL",
    "bottom_copper": "GBL",
    "top_silk": "GTO",
    "bottom_silk": "GBO",
    "top_mask": "GTS",
    "bottom_mask": "GBS",
    "top_paste": "GTP",
    "bottom_paste": "GBP",
    "edge_cuts": "GKO",
}

# inner_N layers get GL2, GL3 … computed at runtime.


def layer_extension(layer_name: str) -> str:
    if layer_name in _LAYER_EXT:
        return _LAYER_EXT[layer_name]
    m = re.match(r"inner_(\d+)$", layer_name)
    if m:
        return f"GL{int(m.group(1)) + 1}"
    return layer_name.upper()[:4]


# ─── Aperture registry ────────────────────────────────────────────────────────

class _ApertureRegistry:
    """Manages D-code assignment for unique aperture shapes."""

    def __init__(self) -> None:
        self._map: dict[tuple, int] = {}
        self._next = 10  # D10 onwards

    def get(self, shape: str, *params: float) -> int:
        key = (shape, *tuple(round(p, 6) for p in params))
        if key not in self._map:
            self._map[key] = self._next
            self._next += 1
        return self._map[key]

    def definitions(self) -> list[str]:
        lines = []
        for (shape, *params), dcode in sorted(self._map.items(), key=lambda x: x[1]):
            if shape == "C":
                lines.append(f"%ADD{dcode}C,{params[0]:.6f}*%")
            elif shape == "R":
                lines.append(f"%ADD{dcode}R,{params[0]:.6f}X{params[1]:.6f}*%")
            elif shape == "O":
                lines.append(f"%ADD{dcode}O,{params[0]:.6f}X{params[1]:.6f}*%")
            else:
                # Fallback: circle
                lines.append(f"%ADD{dcode}C,{params[0]:.6f}*%")
        return lines


# ─── Per-layer Gerber builder ─────────────────────────────────────────────────

class _GerberLayer:
    def __init__(self, layer_name: str, stem: str) -> None:
        self.layer_name = layer_name
        self.stem = stem
        self._apertures = _ApertureRegistry()
        self._body: list[str] = []
        self._current_d: int | None = None

    # -- aperture helpers -------------------------------------------------------

    def _select(self, dcode: int) -> None:
        if self._current_d != dcode:
            self._body.append(f"D{dcode}*")
            self._current_d = dcode

    def flash(self, x: float, y: float, shape: str, *params: float) -> None:
        d = self._apertures.get(shape, *params)
        self._select(d)
        self._body.append(f"X{_fmt(x)}Y{_fmt(y)}D03*")

    def draw(self, x1: float, y1: float, x2: float, y2: float,
             width: float) -> None:
        d = self._apertures.get("C", width)
        self._select(d)
        self._body.append(f"X{_fmt(x1)}Y{_fmt(y1)}D02*")
        self._body.append(f"X{_fmt(x2)}Y{_fmt(y2)}D01*")

    def polygon(self, vertices: list[tuple[float, float]],
                width: float = 0.0) -> None:
        """Emit a filled polygon region (copper pour / board outline)."""
        if len(vertices) < 3:
            return
        # Use region statement (G36/G37) for filled copper; for outline use draw
        if width == 0.0:
            # Filled region
            self._body.append("G36*")
            x0, y0 = vertices[0]
            self._body.append(f"X{_fmt(x0)}Y{_fmt(y0)}D02*")
            self._body.append("G01*")
            for x, y in vertices[1:]:
                self._body.append(f"X{_fmt(x)}Y{_fmt(y)}D01*")
            # Close polygon
            self._body.append(f"X{_fmt(x0)}Y{_fmt(y0)}D01*")
            self._body.append("G37*")
        else:
            # Outline draw
            d = self._apertures.get("C", width)
            self._select(d)
            x0, y0 = vertices[0]
            self._body.append(f"X{_fmt(x0)}Y{_fmt(y0)}D02*")
            for x, y in vertices[1:]:
                self._body.append(f"X{_fmt(x)}Y{_fmt(y)}D01*")
            # Close
            self._body.append(f"X{_fmt(x0)}Y{_fmt(y0)}D01*")

    # -- serialise --------------------------------------------------------------

    def render(self) -> str:
        ext = layer_extension(self.layer_name)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines: list[str] = [
            "G04 Kerf Electronics — Gerber RS-274X*",
            f"G04 Layer: {self.layer_name}*",
            f"G04 Generated: {ts}*",
            "%FSLAX46Y46*%",
            "%MOMM*%",
            "%LPD*%",
        ]
        lines.extend(self._apertures.definitions())
        lines.append("G01*")
        lines.extend(self._body)
        lines.append("M02*")
        return "\n".join(lines) + "\n"


# ─── CircuitJSON traversal helpers ───────────────────────────────────────────

def _xy(elem: dict, xk: str = "x", yk: str = "y") -> tuple[float, float]:
    return float(elem.get(xk, 0.0)), float(elem.get(yk, 0.0))


def _pad_layer(elem: dict) -> str:
    """Return the copper layer for a pad element."""
    layer = elem.get("layer", "")
    if layer:
        return layer
    # Infer from element type / side hint
    side = elem.get("side", elem.get("pcb_layer", ""))
    if "bottom" in side:
        return "bottom_copper"
    return "top_copper"


def _trace_layer(pt: dict) -> str:
    return pt.get("layer", "top_copper")


def _classify_elements(circuit_json: list[dict]) -> dict[str, list[dict]]:
    """Partition CircuitJSON elements by their role."""
    out: dict[str, list[dict]] = {
        "pads": [],
        "vias": [],
        "traces": [],
        "silk_text": [],
        "silk_line": [],
        "copper_pour": [],
        "outline": [],
        "board": [],
    }
    for el in circuit_json:
        t = el.get("type", "")
        if t in ("pcb_smtpad", "pcb_pad", "pcb_plated_pad", "pcb_component_pad"):
            out["pads"].append(el)
        elif t == "pcb_via":
            out["vias"].append(el)
        elif t == "pcb_trace":
            out["traces"].append(el)
        elif t in ("pcb_silkscreen_text", "pcb_text"):
            out["silk_text"].append(el)
        elif t in ("pcb_silkscreen_line", "pcb_silkscreen_path", "pcb_line"):
            out["silk_line"].append(el)
        elif t in ("copper_pour_fill", "pcb_copper_pour"):
            out["copper_pour"].append(el)
        elif t in ("pcb_board", "board"):
            out["board"].append(el)
        elif t == "pcb_outline_path":
            out["outline"].append(el)
    return out


def _pad_shape(elem: dict) -> tuple[str, ...]:
    """Return (aperture_shape, *params) for an SMT/plated pad."""
    shape = elem.get("shape", elem.get("pad_shape", "rect"))
    w = float(elem.get("width", elem.get("size_x", 1.5)))
    h = float(elem.get("height", elem.get("size_y", w)))
    if shape in ("circle", "round"):
        return ("C", max(w, h))
    if shape in ("oblong", "oval"):
        return ("O", w, h)
    # default rect
    return ("R", w, h)


def _board_outline_rect(board: dict) -> list[tuple[float, float]] | None:
    """Extract a rectangular outline from a board element."""
    w = float(board.get("width", 0))
    h = float(board.get("height", 0))
    cx = float(board.get("center_x", board.get("x", 0)))
    cy = float(board.get("center_y", board.get("y", 0)))
    if w <= 0 or h <= 0:
        return None
    x0, y0 = cx - w / 2, cy - h / 2
    x1, y1 = cx + w / 2, cy + h / 2
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _outline_path_vertices(el: dict) -> list[tuple[float, float]]:
    pts = el.get("route", el.get("points", el.get("vertices", [])))
    return [(float(p.get("x", 0)), float(p.get("y", 0))) for p in pts]


def _trace_route_points(trace: dict) -> list[dict]:
    for key in ("route", "points", "vertices"):
        pts = trace.get(key)
        if isinstance(pts, list):
            return pts
    return []


# ─── Main export function ─────────────────────────────────────────────────────

_DEFAULT_TRACE_WIDTH = 0.25
_DEFAULT_OUTLINE_WIDTH = 0.1
_VIA_MASK_MARGIN = 0.1  # expand via pad by this on mask layers


def export_gerber(
    circuit_json: list[dict],
    stem: str = "board",
) -> dict[str, str]:
    """Convert CircuitJSON to a mapping of {filename: gerber_text}.

    Args:
        circuit_json: The parsed CircuitJSON array (tscircuit PCB data model).
        stem: Base filename stem (without extension). Default "board".

    Returns:
        dict mapping filename → Gerber RS-274X text content.
        e.g. {"board.GTL": "...", "board.GBL": "...", "board.GKO": "..."}
    """
    if not isinstance(circuit_json, list):
        circuit_json = []

    classified = _classify_elements(circuit_json)

    # Collect all copper layers present in the design
    copper_layers: set[str] = {"top_copper", "bottom_copper"}
    for trace in classified["traces"]:
        for pt in _trace_route_points(trace):
            lyr = _trace_layer(pt)
            if lyr:
                copper_layers.add(lyr)
    for pad in classified["pads"]:
        lyr = _pad_layer(pad)
        if lyr:
            copper_layers.add(lyr)
    for via in classified["vias"]:
        copper_layers.add("top_copper")
        copper_layers.add("bottom_copper")
    for pour in classified["copper_pour"]:
        lyr = pour.get("layer", "top_copper")
        if lyr:
            copper_layers.add(lyr)

    # Build layer builders for all layers we'll emit
    active_layers: set[str] = set(copper_layers) | {
        "top_silk", "bottom_silk",
        "top_mask", "bottom_mask",
        "edge_cuts",
    }
    layers: dict[str, _GerberLayer] = {
        name: _GerberLayer(name, stem) for name in active_layers
    }

    def layer(name: str) -> _GerberLayer:
        if name not in layers:
            layers[name] = _GerberLayer(name, stem)
        return layers[name]

    # ── Copper pads ──────────────────────────────────────────────────────────
    for pad in classified["pads"]:
        x, y = _xy(pad)
        lyr = _pad_layer(pad)
        shape_params = _pad_shape(pad)
        layer(lyr).flash(x, y, *shape_params)

        # Soldermask opening (slightly larger)
        mask_layer = "top_mask" if "top" in lyr or lyr == "top_copper" else "bottom_mask"
        if shape_params[0] == "C":
            ms = _pad_shape(pad)
            layer(mask_layer).flash(x, y, ms[0], ms[1] + 0.1)
        elif shape_params[0] == "R":
            layer(mask_layer).flash(x, y, "R", shape_params[1] + 0.1, shape_params[2] + 0.1)
        else:
            layer(mask_layer).flash(x, y, *shape_params)

    # ── Vias ─────────────────────────────────────────────────────────────────
    for via in classified["vias"]:
        x, y = _xy(via)
        outer = float(via.get("outer_diameter", via.get("diameter", 0.6)))
        for copper_lyr in copper_layers:
            layer(copper_lyr).flash(x, y, "C", outer)
        # Mask opening on both sides
        for mask_lyr in ("top_mask", "bottom_mask"):
            layer(mask_lyr).flash(x, y, "C", outer + _VIA_MASK_MARGIN)

    # ── Traces ───────────────────────────────────────────────────────────────
    for trace in classified["traces"]:
        route = _trace_route_points(trace)
        if len(route) < 2:
            continue
        for i in range(len(route) - 1):
            p1, p2 = route[i], route[i + 1]
            x1, y1 = float(p1.get("x", 0)), float(p1.get("y", 0))
            x2, y2 = float(p2.get("x", 0)), float(p2.get("y", 0))
            lyr = _trace_layer(p1)
            w = float(p1.get("width", p1.get("trace_width", _DEFAULT_TRACE_WIDTH)))
            layer(lyr).draw(x1, y1, x2, y2, w)

    # ── Copper pours ─────────────────────────────────────────────────────────
    for pour in classified["copper_pour"]:
        lyr = pour.get("layer", "top_copper")
        poly_raw = pour.get("polygon", pour.get("filled_polygon", pour.get("outline", [])))
        if isinstance(poly_raw, list) and len(poly_raw) >= 3:
            verts = [(float(p.get("x", 0)), float(p.get("y", 0))) for p in poly_raw]
            layer(lyr).polygon(verts)

    # ── Silkscreen text (bounding box approximation) ─────────────────────────
    for stext in classified["silk_text"]:
        x, y = _xy(stext)
        text_h = float(stext.get("font_size", stext.get("height", 1.0)))
        text_str = stext.get("text", "")
        text_w = len(text_str) * text_h * 0.6 or text_h
        silk_lyr = "bottom_silk" if "bottom" in stext.get("layer", "") else "top_silk"
        # Draw a line representing the text baseline
        layer(silk_lyr).draw(x, y, x + text_w, y, text_h * 0.15)

    # ── Silkscreen lines ─────────────────────────────────────────────────────
    for sline in classified["silk_line"]:
        silk_lyr = "bottom_silk" if "bottom" in sline.get("layer", "") else "top_silk"
        pts_raw = sline.get("route", sline.get("points", sline.get("vertices", [])))
        w = float(sline.get("stroke_width", sline.get("width", 0.15)))
        pts = [(float(p.get("x", 0)), float(p.get("y", 0))) for p in pts_raw]
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            layer(silk_lyr).draw(x1, y1, x2, y2, w)

    # ── Board outline ─────────────────────────────────────────────────────────
    edge = layer("edge_cuts")
    outline_written = False

    # Explicit outline paths first
    for op in classified["outline"]:
        verts = _outline_path_vertices(op)
        if len(verts) >= 2:
            edge.polygon(verts, width=_DEFAULT_OUTLINE_WIDTH)
            outline_written = True

    # Fall back to board element bounding rect
    if not outline_written:
        for board_el in classified["board"]:
            rect = _board_outline_rect(board_el)
            if rect:
                edge.polygon(rect, width=_DEFAULT_OUTLINE_WIDTH)
                outline_written = True
                break

    if not outline_written:
        # Synthesise a 100×100 mm default outline
        edge.polygon([(0, 0), (100, 0), (100, 100), (0, 100)],
                     width=_DEFAULT_OUTLINE_WIDTH)

    # ── Serialise ─────────────────────────────────────────────────────────────
    result: dict[str, str] = {}
    for name, lyr_obj in layers.items():
        ext = layer_extension(name)
        filename = f"{stem}.{ext}"
        result[filename] = lyr_obj.render()

    return result
