"""
kerf_plc.ld.renderer — SVG renderer for IEC 61131-3 Ladder Diagram programs.

Renders a LadderProgram to an SVG string using the standard IEC 61131-3
graphical symbol set for contacts, coils, and function blocks.

Symbol geometry (all dimensions in px, scalable via `cell_w`/`cell_h`):

  Contact NO  -| |-   two vertical bars with a gap
  Contact NC  -|/|-   same but with a diagonal slash
  Coil        -( )-   two half-circles
  Coil S/R    -(S)-   coil with a letter inside
  FB block    [TON]   rectangle with instance + type label

Layout:
  • Each rung occupies one horizontal band.
  • Left power rail: vertical line on the far left.
  • Right power rail: vertical line on the far right.
  • Parallel branches are stacked vertically and joined at branch junctions.
  • The output (coil/fb) is always the rightmost element before the right rail.
"""
from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from typing import NamedTuple

from kerf_plc.ld.schema import (
    COIL_TYPES,
    CONTACT_TYPES,
    FB_TYPE,
    Element,
    LadderProgram,
    Rung,
)


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

CELL_W = 80       # px width of one element cell
CELL_H = 60       # px height of one rung (single-branch)
RAIL_W = 6        # width of the power rails
PADDING_X = 20    # left/right outer margin
PADDING_Y = 30    # top outer margin
LABEL_H = 18      # px reserved for rung label text above the rung
COMMENT_H = 14    # px reserved for rung comment text (0 if no comment)
RAIL_COLOR = "#4a9eff"
WIRE_COLOR = "#c9d1d9"
CONTACT_COLOR = "#82aaff"
COIL_COLOR = "#c792ea"
FB_COLOR = "#ffcb6b"
TEXT_COLOR = "#c9d1d9"
LABEL_COLOR = "#546e7a"
COMMENT_COLOR = "#636e7b"
BG_COLOR = "#0d1117"
GRID_COLOR = "#1a2030"


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------

def _svg_el(tag: str, **attribs) -> ET.Element:
    el = ET.Element(tag)
    for k, v in attribs.items():
        el.set(k.replace("_", "-"), str(v))
    return el


def _text(parent: ET.Element, x: float, y: float, txt: str,
          fill: str = TEXT_COLOR, font_size: int = 11,
          anchor: str = "middle", font_weight: str = "normal") -> ET.Element:
    el = ET.SubElement(parent, "text", x=str(x), y=str(y),
                       fill=fill, **{
                           "font-size": str(font_size),
                           "font-family": "JetBrains Mono, ui-monospace, monospace",
                           "text-anchor": anchor,
                           "dominant-baseline": "central",
                           "font-weight": font_weight,
                       })
    el.text = html.escape(txt)
    return el


def _line(parent: ET.Element, x1: float, y1: float,
          x2: float, y2: float, stroke: str = WIRE_COLOR,
          stroke_width: float = 1.5) -> ET.Element:
    return ET.SubElement(parent, "line",
                         x1=str(x1), y1=str(y1), x2=str(x2), y2=str(y2),
                         stroke=stroke, **{"stroke-width": str(stroke_width)})


# ---------------------------------------------------------------------------
# Element symbol drawers
# ---------------------------------------------------------------------------

def _draw_contact_no(g: ET.Element, cx: float, cy: float, var: str) -> None:
    """Draw -| |-  normally-open contact centred at (cx, cy)."""
    bar_h = CELL_H * 0.35
    bar_gap = 8
    # Left wire → left bar
    _line(g, cx - CELL_W / 2, cy, cx - bar_gap, cy)
    # Right bar → right wire
    _line(g, cx + bar_gap, cy, cx + CELL_W / 2, cy)
    # Left vertical bar
    _line(g, cx - bar_gap, cy - bar_h, cx - bar_gap, cy + bar_h, CONTACT_COLOR, 2)
    # Right vertical bar
    _line(g, cx + bar_gap, cy - bar_h, cx + bar_gap, cy + bar_h, CONTACT_COLOR, 2)
    _text(g, cx, cy - bar_h - 8, var, CONTACT_COLOR, 10)


def _draw_contact_nc(g: ET.Element, cx: float, cy: float, var: str) -> None:
    """Draw -|/|-  normally-closed contact."""
    bar_h = CELL_H * 0.35
    bar_gap = 8
    _line(g, cx - CELL_W / 2, cy, cx - bar_gap, cy)
    _line(g, cx + bar_gap, cy, cx + CELL_W / 2, cy)
    _line(g, cx - bar_gap, cy - bar_h, cx - bar_gap, cy + bar_h, CONTACT_COLOR, 2)
    _line(g, cx + bar_gap, cy - bar_h, cx + bar_gap, cy + bar_h, CONTACT_COLOR, 2)
    # Diagonal slash
    _line(g, cx - bar_gap + 2, cy + bar_h - 2, cx + bar_gap - 2, cy - bar_h + 2,
          CONTACT_COLOR, 1.5)
    _text(g, cx, cy - bar_h - 8, var, CONTACT_COLOR, 10)


def _draw_contact_transition(g: ET.Element, cx: float, cy: float,
                              var: str, label: str) -> None:
    """Draw P/N transition contact."""
    bar_h = CELL_H * 0.35
    bar_gap = 8
    _line(g, cx - CELL_W / 2, cy, cx - bar_gap, cy)
    _line(g, cx + bar_gap, cy, cx + CELL_W / 2, cy)
    _line(g, cx - bar_gap, cy - bar_h, cx - bar_gap, cy + bar_h, CONTACT_COLOR, 2)
    _line(g, cx + bar_gap, cy - bar_h, cx + bar_gap, cy + bar_h, CONTACT_COLOR, 2)
    _text(g, cx, cy, label, CONTACT_COLOR, 12, font_weight="bold")
    _text(g, cx, cy - bar_h - 8, var, CONTACT_COLOR, 10)


def _draw_coil(g: ET.Element, cx: float, cy: float, var: str,
               label: str = "") -> None:
    """Draw -( )-  output coil."""
    r = CELL_H * 0.28
    # Wire stubs
    _line(g, cx - CELL_W / 2, cy, cx - r, cy)
    _line(g, cx + r, cy, cx + CELL_W / 2, cy)
    # Left arc (open to the left)
    arc_cmd = (
        f"M {cx - r} {cy - r} "
        f"A {r} {r} 0 0 0 {cx - r} {cy + r}"
    )
    arc_l = ET.SubElement(g, "path", d=arc_cmd,
                           fill="none", stroke=COIL_COLOR,
                           **{"stroke-width": "2"})
    # Right arc (open to the right)
    arc_r_cmd = (
        f"M {cx + r} {cy - r} "
        f"A {r} {r} 0 0 1 {cx + r} {cy + r}"
    )
    ET.SubElement(g, "path", d=arc_r_cmd,
                  fill="none", stroke=COIL_COLOR,
                  **{"stroke-width": "2"})
    if label:
        _text(g, cx, cy, label, COIL_COLOR, 11, font_weight="bold")
    _text(g, cx, cy - r - 8, var, COIL_COLOR, 10)


def _draw_fb_call(g: ET.Element, cx: float, cy: float,
                  fb_type: str, fb_instance: str,
                  fb_inputs: dict[str, str]) -> None:
    """Draw a function-block call box."""
    box_w = CELL_W - 8
    box_h = CELL_H - 8
    bx = cx - box_w / 2
    by = cy - box_h / 2
    # Wire stubs
    _line(g, cx - CELL_W / 2, cy, bx, cy)
    _line(g, bx + box_w, cy, cx + CELL_W / 2, cy)
    # Box
    ET.SubElement(g, "rect",
                  x=str(bx), y=str(by),
                  width=str(box_w), height=str(box_h),
                  fill="#1a2030", stroke=FB_COLOR,
                  **{"stroke-width": "1.5", "rx": "3"})
    _text(g, cx, by + box_h * 0.28, fb_type, FB_COLOR, 10, font_weight="bold")
    _text(g, cx, by + box_h * 0.55, fb_instance, TEXT_COLOR, 9)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _draw_element(g: ET.Element, elem: Element, cx: float, cy: float) -> None:
    if elem.type == "contact_no":
        _draw_contact_no(g, cx, cy, elem.var)
    elif elem.type == "contact_nc":
        _draw_contact_nc(g, cx, cy, elem.var)
    elif elem.type == "contact_pos":
        _draw_contact_transition(g, cx, cy, elem.var, "P")
    elif elem.type == "contact_neg":
        _draw_contact_transition(g, cx, cy, elem.var, "N")
    elif elem.type == "coil":
        _draw_coil(g, cx, cy, elem.var)
    elif elem.type == "coil_set":
        _draw_coil(g, cx, cy, elem.var, "S")
    elif elem.type == "coil_reset":
        _draw_coil(g, cx, cy, elem.var, "R")
    elif elem.type == "coil_pos":
        _draw_coil(g, cx, cy, elem.var, "P")
    elif elem.type == "coil_neg":
        _draw_coil(g, cx, cy, elem.var, "N")
    elif elem.type == FB_TYPE:
        _draw_fb_call(g, cx, cy, elem.fb_type, elem.fb_instance, elem.fb_inputs)


# ---------------------------------------------------------------------------
# Rung renderer
# ---------------------------------------------------------------------------

class _RungLayout(NamedTuple):
    x: float          # left x of the rung area (inside rails)
    y: float          # top y
    width: float      # total rung width (inside rails)
    n_branches: int   # number of parallel branches
    n_contacts: int   # elements per branch (max)
    branch_height: float  # px height of each branch row


def _render_rung(svg: ET.Element, rung: Rung, layout: _RungLayout) -> None:
    """Render one rung into the svg group at the given layout position."""
    g = ET.SubElement(svg, "g")

    x0 = layout.x
    rung_y_center = layout.y + layout.n_branches * layout.branch_height / 2

    # ── Label / comment ───────────────────────────────────────────────────────
    if rung.label:
        _text(svg, x0, layout.y - LABEL_H + 4, rung.label, LABEL_COLOR, 10,
              anchor="start")
    if rung.comment:
        _text(svg, x0, layout.y - COMMENT_H + 2, f"(* {rung.comment} *)",
              COMMENT_COLOR, 9, anchor="start")

    # ── Left junction rail (vertical wire joining all branch starts) ──────────
    if layout.n_branches > 1:
        y_top = layout.y + layout.branch_height / 2
        y_bot = layout.y + (layout.n_branches - 1) * layout.branch_height + layout.branch_height / 2
        _line(g, x0, y_top, x0, y_bot, WIRE_COLOR, 1.5)

    # ── Contact columns ───────────────────────────────────────────────────────
    max_contacts = max((len(b) for b in rung.branches), default=0)

    for bi, branch in enumerate(rung.branches):
        by = layout.y + bi * layout.branch_height + layout.branch_height / 2
        branch_x0 = x0

        # Horizontal connecting wire for the full branch
        branch_x1 = x0 + max_contacts * CELL_W
        _line(g, branch_x0, by, branch_x1, by, WIRE_COLOR, 1.2)

        for ci, elem in enumerate(branch):
            cx = branch_x0 + ci * CELL_W + CELL_W / 2
            _draw_element(g, elem, cx, by)

    # ── Right junction rail ───────────────────────────────────────────────────
    junction_x = x0 + max_contacts * CELL_W
    if layout.n_branches > 1:
        y_top = layout.y + layout.branch_height / 2
        y_bot = layout.y + (layout.n_branches - 1) * layout.branch_height + layout.branch_height / 2
        _line(g, junction_x, y_top, junction_x, y_bot, WIRE_COLOR, 1.5)

    # ── Output element ────────────────────────────────────────────────────────
    output_cx = junction_x + CELL_W / 2
    if rung.output is not None:
        _line(g, junction_x, rung_y_center,
              junction_x + CELL_W / 2, rung_y_center, WIRE_COLOR, 1.2)
        _draw_element(g, rung.output, output_cx, rung_y_center)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_svg(prog: LadderProgram) -> str:
    """
    Render a LadderProgram to an SVG string.

    The SVG uses a fixed-width layout with:
      - A dark background (#0d1117)
      - IEC 61131-3 contact/coil symbol set
      - Left and right power rails
      - Parallel branches joined by junction rails

    Returns the SVG as a UTF-8 string.
    """
    # ── Pre-compute layout ────────────────────────────────────────────────────
    max_contacts = 0
    has_output = False
    for rung in prog.rungs:
        mc = max((len(b) for b in rung.branches), default=0)
        max_contacts = max(max_contacts, mc)
        if rung.output is not None:
            has_output = True

    content_cols = max_contacts + (1 if has_output else 0)
    content_w = content_cols * CELL_W

    # Total SVG width
    svg_w = PADDING_X * 2 + RAIL_W * 2 + content_w + 20  # 20 extra right margin

    # Compute per-rung heights
    rung_heights: list[float] = []
    for rung in prog.rungs:
        n_b = max(len(rung.branches), 1)
        extra = LABEL_H + (COMMENT_H if rung.comment else 0)
        rung_heights.append(extra + n_b * CELL_H + 12)

    svg_h = PADDING_Y + sum(rung_heights) + PADDING_Y

    # ── SVG root ──────────────────────────────────────────────────────────────
    svg = ET.Element("svg",
                     xmlns="http://www.w3.org/2000/svg",
                     width=str(svg_w),
                     height=str(svg_h),
                     viewBox=f"0 0 {svg_w} {svg_h}")

    # Background
    ET.SubElement(svg, "rect", x="0", y="0",
                  width=str(svg_w), height=str(svg_h), fill=BG_COLOR)

    # Program name header
    _text(svg, PADDING_X, PADDING_Y - 10,
          f"PROGRAM {prog.program}", RAIL_COLOR, 12,
          anchor="start", font_weight="bold")

    # Compute rail extents
    rail_left_x = PADDING_X + RAIL_W / 2
    rail_right_x = svg_w - PADDING_X - RAIL_W / 2
    content_x0 = PADDING_X + RAIL_W + 4

    total_rung_h = sum(rung_heights)
    rail_top = PADDING_Y
    rail_bottom = PADDING_Y + total_rung_h

    # Left power rail (L+)
    _line(svg, rail_left_x, rail_top, rail_left_x, rail_bottom,
          RAIL_COLOR, RAIL_W)
    _text(svg, rail_left_x, rail_top - 8, "L+", RAIL_COLOR, 9,
          anchor="middle")

    # Right power rail (L-)
    _line(svg, rail_right_x, rail_top, rail_right_x, rail_bottom,
          RAIL_COLOR, RAIL_W)
    _text(svg, rail_right_x, rail_top - 8, "L-", RAIL_COLOR, 9,
          anchor="middle")

    # ── Render each rung ──────────────────────────────────────────────────────
    y_cursor = PADDING_Y
    for i, rung in enumerate(prog.rungs):
        n_b = max(len(rung.branches), 1)
        extra = LABEL_H + (COMMENT_H if rung.comment else 0)
        rung_total_h = rung_heights[i]

        layout = _RungLayout(
            x=content_x0,
            y=y_cursor + extra,
            width=content_w,
            n_branches=n_b,
            n_contacts=max((len(b) for b in rung.branches), default=0),
            branch_height=CELL_H,
        )

        # Horizontal rung divider (between rungs)
        if i > 0:
            _line(svg, content_x0, y_cursor + 4,
                  rail_right_x, y_cursor + 4,
                  GRID_COLOR, 1)

        # Connect rung branches to left rail
        rung_y_center = layout.y + n_b * CELL_H / 2
        if n_b == 1:
            _line(svg, rail_left_x, rung_y_center, content_x0, rung_y_center)
        else:
            for bi in range(n_b):
                by = layout.y + bi * CELL_H + CELL_H / 2
                _line(svg, rail_left_x, by, content_x0, by)

        # Connect output to right rail
        output_x = content_x0 + max_contacts * CELL_W + CELL_W
        if rung.output is not None:
            _line(svg, output_x, rung_y_center, rail_right_x, rung_y_center)
        else:
            # No output: wire direct to rail
            _line(svg, content_x0 + max_contacts * CELL_W, rung_y_center,
                  rail_right_x, rung_y_center)

        _render_rung(svg, rung, layout)
        y_cursor += rung_total_h

    return ET.tostring(svg, encoding="unicode", xml_declaration=False)
