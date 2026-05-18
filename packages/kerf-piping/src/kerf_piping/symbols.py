"""
ISA 5.1 P&ID symbol library and 2D layout exporter.

Provides:
  - Symbol definitions for equipment and instrument bubbles per ISA 5.1.
  - ``pid_diagram_dxf``  — exports a PIDDiagram to DXF (requires ezdxf).
  - ``pid_diagram_svg``  — exports a PIDDiagram to SVG (pure Python, no deps).

The DXF / SVG output is a schematic layout; it is not to scale but represents
the connectivity and symbol types of the P&ID.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from kerf_piping.pid import (
    PIDDiagram,
    PIDComponent,
    Vessel,
    Pump,
    HeatExchanger,
    Valve,
    Instrument,
    Pipe,
)


# ---------------------------------------------------------------------------
# ISA 5.1 symbol catalogue
# ---------------------------------------------------------------------------

class SymbolShape(str):
    """ISA 5.1 symbol shape identifiers."""
    CIRCLE = "circle"                    # instrument bubble
    DASHED_CIRCLE = "dashed_circle"      # shared display instrument
    SQUARE = "square"                    # PLC/DCS function
    DIAMOND = "diamond"                  # valve actuator
    HEXAGON = "hexagon"                  # safety instrument
    VESSEL_VERTICAL = "vessel_v"
    VESSEL_HORIZONTAL = "vessel_h"
    PUMP_CENTRIFUGAL = "pump_centrifugal"
    PUMP_PD = "pump_pd"
    HX_SHELL_TUBE = "hx_shell_tube"
    VALVE_GATE = "valve_gate"
    VALVE_GLOBE = "valve_globe"
    VALVE_BALL = "valve_ball"
    VALVE_CHECK = "valve_check"
    VALVE_BUTTERFLY = "valve_butterfly"
    VALVE_CONTROL = "valve_control"
    VALVE_RELIEF = "valve_relief"


_COMPONENT_SYMBOL: dict[type, str] = {
    Vessel: SymbolShape.VESSEL_VERTICAL,
    Pump: SymbolShape.PUMP_CENTRIFUGAL,
    HeatExchanger: SymbolShape.HX_SHELL_TUBE,
    Instrument: SymbolShape.CIRCLE,
}

from kerf_piping.pid import ValveType

_VALVE_SYMBOL: dict[str, str] = {
    ValveType.GATE.value: SymbolShape.VALVE_GATE,
    ValveType.GLOBE.value: SymbolShape.VALVE_GLOBE,
    ValveType.BALL.value: SymbolShape.VALVE_BALL,
    ValveType.CHECK.value: SymbolShape.VALVE_CHECK,
    ValveType.BUTTERFLY.value: SymbolShape.VALVE_BUTTERFLY,
    ValveType.CONTROL.value: SymbolShape.VALVE_CONTROL,
    ValveType.RELIEF.value: SymbolShape.VALVE_RELIEF,
}


def symbol_for(comp: PIDComponent) -> str:
    if isinstance(comp, Valve):
        return _VALVE_SYMBOL.get(comp.valve_type.value, SymbolShape.VALVE_GATE)
    return _COMPONENT_SYMBOL.get(type(comp), SymbolShape.CIRCLE)


# ---------------------------------------------------------------------------
# 2D schematic layout (auto-place)
# ---------------------------------------------------------------------------

_LAYOUT_STEP_X = 80.0   # mm between component centres in schematic
_LAYOUT_STEP_Y = 80.0


def _auto_layout(diagram: PIDDiagram) -> dict[str, tuple[float, float]]:
    """
    Assign 2D schematic positions to components in a left-to-right row.
    Returns { tag: (cx, cy) }.
    """
    positions: dict[str, tuple[float, float]] = {}
    for i, tag in enumerate(diagram.components):
        positions[tag] = (50.0 + i * _LAYOUT_STEP_X, 100.0)
    return positions


# ---------------------------------------------------------------------------
# SVG exporter (pure Python, no external deps)
# ---------------------------------------------------------------------------

def pid_diagram_svg(
    diagram: PIDDiagram,
    *,
    width: int = 800,
    height: int = 300,
    title: Optional[str] = None,
) -> str:
    """
    Export a PIDDiagram as an SVG string.

    The output is a simple schematic: equipment boxes/circles connected by
    pipe lines.  Suitable for embedding in HTML or saving to .svg.
    """
    title = title or diagram.name
    positions = _auto_layout(diagram)

    lines: list[str] = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">')
    lines.append(f'  <title>{title}</title>')
    lines.append(
        '  <style>'
        'text{font-family:monospace;font-size:10px;fill:#222;}'
        '.pipe{stroke:#555;stroke-width:2;fill:none;}'
        '.vessel{stroke:#003366;stroke-width:2;fill:#e8f0ff;}'
        '.pump{stroke:#006600;stroke-width:2;fill:#e8ffe8;}'
        '.hx{stroke:#660066;stroke-width:2;fill:#f8e8f8;}'
        '.valve{stroke:#883300;stroke-width:2;fill:#fff0e0;}'
        '.instr{stroke:#333;stroke-width:1.5;fill:#fffff0;}'
        '</style>'
    )

    # Draw pipes (lines between component centres)
    for pipe in diagram.pipes.values():
        if pipe.from_equipment in positions and pipe.to_equipment in positions:
            x1, y1 = positions[pipe.from_equipment]
            x2, y2 = positions[pipe.to_equipment]
            dn = int(pipe.diameter_mm)
            lines.append(
                f'  <line class="pipe" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
                f'<title>{pipe.tag or pipe.id[:8]} DN{dn}</title>'
                f'</line>'
            )

    # Draw components
    for tag, comp in diagram.components.items():
        if tag not in positions:
            continue
        cx, cy = positions[tag]
        sym = symbol_for(comp)

        if sym == SymbolShape.VESSEL_VERTICAL:
            w, h = 30, 50
            lines.append(
                f'  <rect class="vessel" x="{cx-w//2}" y="{cy-h//2}" width="{w}" height="{h}" rx="5"/>'
            )
        elif sym == SymbolShape.PUMP_CENTRIFUGAL:
            r = 18
            lines.append(
                f'  <circle class="pump" cx="{cx}" cy="{cy}" r="{r}"/>'
            )
        elif sym == SymbolShape.HX_SHELL_TUBE:
            w, h = 50, 25
            lines.append(
                f'  <rect class="hx" x="{cx-w//2}" y="{cy-h//2}" width="{w}" height="{h}" rx="8"/>'
            )
        elif "valve" in sym:
            w, h = 18, 14
            lines.append(
                f'  <rect class="valve" x="{cx-w//2}" y="{cy-h//2}" width="{w}" height="{h}"/>'
            )
        elif sym == SymbolShape.CIRCLE:
            lines.append(
                f'  <circle class="instr" cx="{cx}" cy="{cy}" r="14"/>'
            )
        else:
            lines.append(
                f'  <circle class="instr" cx="{cx}" cy="{cy}" r="14"/>'
            )

        # Tag label
        lines.append(
            f'  <text x="{cx}" y="{cy + 30}" text-anchor="middle">{tag}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DXF exporter (requires ezdxf)
# ---------------------------------------------------------------------------

def pid_diagram_dxf(
    diagram: PIDDiagram,
    *,
    title: Optional[str] = None,
) -> "Any":  # returns an ezdxf Drawing object
    """
    Export a PIDDiagram to a DXF drawing (ezdxf.Drawing).

    Requires ezdxf to be installed::

        pip install kerf-piping[dxf]

    Returns the ezdxf Drawing object.  Save with::

        doc = pid_diagram_dxf(diagram)
        doc.saveas("my_pid.dxf")

    Layers
    ------
    PID_PIPE        Pipe lines (colour 1 = red).
    PID_EQUIPMENT   Equipment outlines (colour 5 = blue).
    PID_TEXT        Tags and annotations (colour 7 = white/black).
    """
    try:
        import ezdxf
    except ImportError as exc:
        raise ImportError(
            "ezdxf is required for DXF export. "
            "Install it with: pip install kerf-piping[dxf]"
        ) from exc

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Layers
    doc.layers.new("PID_PIPE",       dxfattribs={"color": 1})
    doc.layers.new("PID_EQUIPMENT",  dxfattribs={"color": 5})
    doc.layers.new("PID_TEXT",       dxfattribs={"color": 7})

    title_str = title or diagram.name
    msp.add_text(
        title_str,
        dxfattribs={"layer": "PID_TEXT", "height": 5.0, "insert": (0, -10)},
    )

    positions = _auto_layout(diagram)

    # Pipes
    for pipe in diagram.pipes.values():
        if pipe.from_equipment in positions and pipe.to_equipment in positions:
            x1, y1 = positions[pipe.from_equipment]
            x2, y2 = positions[pipe.to_equipment]
            msp.add_line(
                (x1, y1),
                (x2, y2),
                dxfattribs={"layer": "PID_PIPE"},
            )

    # Equipment
    for tag, comp in diagram.components.items():
        if tag not in positions:
            continue
        cx, cy = positions[tag]
        sym = symbol_for(comp)

        if sym == SymbolShape.VESSEL_VERTICAL:
            w, h = 15, 25
            msp.add_lwpolyline(
                [
                    (cx - w, cy - h),
                    (cx + w, cy - h),
                    (cx + w, cy + h),
                    (cx - w, cy + h),
                ],
                close=True,
                dxfattribs={"layer": "PID_EQUIPMENT"},
            )
        elif sym == SymbolShape.PUMP_CENTRIFUGAL:
            msp.add_circle(
                (cx, cy), 12, dxfattribs={"layer": "PID_EQUIPMENT"}
            )
        elif sym == SymbolShape.HX_SHELL_TUBE:
            w, h = 25, 12
            msp.add_lwpolyline(
                [
                    (cx - w, cy - h),
                    (cx + w, cy - h),
                    (cx + w, cy + h),
                    (cx - w, cy + h),
                ],
                close=True,
                dxfattribs={"layer": "PID_EQUIPMENT"},
            )
        elif "valve" in sym:
            msp.add_circle(
                (cx, cy), 8, dxfattribs={"layer": "PID_EQUIPMENT"}
            )
        else:
            msp.add_circle(
                (cx, cy), 10, dxfattribs={"layer": "PID_EQUIPMENT"}
            )

        # Tag text
        msp.add_text(
            tag,
            dxfattribs={"layer": "PID_TEXT", "height": 4.0, "insert": (cx - 10, cy - 20)},
        )

    return doc
