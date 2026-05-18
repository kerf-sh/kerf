"""
kerf_piping LLM tools — P&ID routing + import.

Tools
-----
piping_route_isometric  Route a pipe between equipment nozzles and return fitting counts.
piping_import_pid       Parse a text-format P&ID specification into the data model.
piping_export_svg       Export a P&ID diagram as an SVG string.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_piping._compat import ToolSpec, err_payload, ok_payload, ProjectCtx


# ---------------------------------------------------------------------------
# piping_route_isometric
# ---------------------------------------------------------------------------

piping_route_isometric_spec = ToolSpec(
    name="piping_route_isometric",
    description=(
        "Route a pipe isometrically between two 3D nozzle positions using "
        "orthogonal (axis-aligned) segments. Returns the segment list, "
        "elbow count, tee count, and total straight pipe length. "
        "All positions in metres."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "start": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "[x, y, z] start nozzle position (metres).",
            },
            "end": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": "[x, y, z] end nozzle position (metres).",
            },
            "diameter_mm": {
                "type": "number",
                "description": "Nominal pipe diameter (mm). Default 50.",
            },
            "schedule": {
                "type": "string",
                "enum": ["40", "80", "160", "XS", "XXS"],
                "description": "Pipe schedule. Default '40'.",
            },
            "prefer_axis": {
                "type": "string",
                "enum": ["Z", "X", "Y"],
                "description": "Which axis to travel first. Default 'Z' (vertical first).",
            },
        },
        "required": ["start", "end"],
    },
)


async def run_piping_route_isometric(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_piping.pid import Point3, PipeSchedule
        from kerf_piping.isometric import (
            route_orthogonal,
            count_fittings,
            pipe_length,
            FittingType,
        )

        start_raw = args["start"]
        end_raw = args["end"]
        diam = float(args.get("diameter_mm", 50.0))
        sched_str = str(args.get("schedule", "40"))
        prefer = str(args.get("prefer_axis", "Z"))

        try:
            sched = PipeSchedule(sched_str)
        except ValueError:
            sched = PipeSchedule.SCH_40

        start = Point3(*[float(v) for v in start_raw])
        end = Point3(*[float(v) for v in end_raw])

        segments = route_orthogonal(
            start, end,
            diameter_mm=diam,
            schedule=sched,
            prefer_axis=prefer,
        )
        fc = count_fittings(segments)
        total_len = pipe_length(segments)

        serialised = [
            {
                "from": list(s.start.as_tuple()),
                "to": list(s.end.as_tuple()),
                "fitting": s.fitting.value,
                "length_m": round(s.length, 4),
                "direction": list(round(v, 4) for v in s.direction),
            }
            for s in segments
        ]

        payload = {
            "segment_count": len(segments),
            "elbows_90": fc.elbows_90,
            "elbows_45": fc.elbows_45,
            "tees": fc.tees,
            "total_pipe_length_m": round(total_len, 4),
            "diameter_mm": diam,
            "schedule": sched.value,
            "segments": serialised,
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "PIPING_ROUTE_ERROR")


# ---------------------------------------------------------------------------
# piping_import_pid
# ---------------------------------------------------------------------------

piping_import_pid_spec = ToolSpec(
    name="piping_import_pid",
    description=(
        "Parse a text-format P&ID specification into the Kerf P&ID data model. "
        "The input is a structured text description listing equipment items and "
        "pipe connections. Returns a summary of the parsed diagram. "
        "\n\nExpected text format (each line one directive):\n"
        "  VESSEL <tag> [type=<type>] [d=<m>] [L=<m>]\n"
        "  PUMP <tag> [type=<type>] [flow=<m3h>] [head=<m>]\n"
        "  HX <tag> [type=<type>] [duty=<kW>]\n"
        "  VALVE <tag> [type=<valve_type>] [dn=<mm>]\n"
        "  INSTRUMENT <tag>\n"
        "  PIPE <line_tag> <from_equip>.<from_nozzle> <to_equip>.<to_nozzle> "
        "[dn=<mm>] [sched=<sched>] [fluid=<fluid>]\n"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "P&ID specification text.",
            },
            "diagram_name": {
                "type": "string",
                "description": "Optional diagram name / drawing number.",
            },
        },
        "required": ["text"],
    },
)


async def run_piping_import_pid(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_piping.pid import (
            PIDDiagram, Vessel, Pump, HeatExchanger, Valve, Instrument,
            ValveType, Pipe, PipeSchedule,
        )

        text: str = args["text"]
        name: str = str(args.get("diagram_name", "P&ID-001"))

        diagram, warnings = _parse_pid_text(text, name)

        payload = {
            "diagram": diagram.summary(),
            "warnings": warnings,
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "PIPING_IMPORT_ERROR")


def _parse_pid_text(text: str, name: str) -> "tuple[PIDDiagram, list[str]]":
    """
    Parse a text P&ID specification.

    Returns (PIDDiagram, warnings).
    """
    from kerf_piping.pid import (
        PIDDiagram, Vessel, Pump, HeatExchanger, Valve, Instrument,
        ValveType, Pipe, PipeSchedule,
    )

    diagram = PIDDiagram(name)
    warnings: list[str] = []
    pipe_lines: list[str] = []  # defer pipe lines until all equipment is parsed

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        tokens = line.split()
        directive = tokens[0].upper()
        rest = tokens[1:]

        try:
            if directive == "VESSEL":
                kv = _parse_kv(rest[1:])
                comp = Vessel(
                    tag=rest[0],
                    vessel_type=kv.get("type", "drum"),
                    diameter_m=float(kv.get("d", 1.0)),
                    length_m=float(kv.get("l", 2.0)),
                )
                diagram.add_component(comp)

            elif directive == "PUMP":
                kv = _parse_kv(rest[1:])
                comp = Pump(
                    tag=rest[0],
                    pump_type=kv.get("type", "centrifugal"),
                    flow_m3h=float(kv.get("flow", 10.0)),
                    head_m=float(kv.get("head", 30.0)),
                )
                diagram.add_component(comp)

            elif directive == "HX":
                kv = _parse_kv(rest[1:])
                comp = HeatExchanger(
                    tag=rest[0],
                    hx_type=kv.get("type", "shell_tube"),
                    duty_kw=float(kv.get("duty", 500.0)),
                )
                diagram.add_component(comp)

            elif directive == "VALVE":
                kv = _parse_kv(rest[1:])
                vtype_str = kv.get("type", "gate").lower()
                try:
                    vtype = ValveType(vtype_str)
                except ValueError:
                    vtype = ValveType.GATE
                comp = Valve(
                    tag=rest[0],
                    valve_type=vtype,
                    diameter_mm=float(kv.get("dn", 50.0)),
                )
                diagram.add_component(comp)

            elif directive == "INSTRUMENT":
                comp = Instrument(tag=rest[0])
                diagram.add_component(comp)

            elif directive == "PIPE":
                pipe_lines.append(line)  # defer

            else:
                warnings.append(f"Unknown directive: {directive!r} — skipped")

        except (IndexError, ValueError, KeyError) as exc:
            warnings.append(f"Parse error on line {line!r}: {exc}")

    # Second pass: pipes
    for line in pipe_lines:
        tokens = line.split()
        rest = tokens[1:]
        try:
            pipe_tag = rest[0]
            from_str = rest[1]  # equip.nozzle
            to_str = rest[2]    # equip.nozzle
            kv = _parse_kv(rest[3:])

            from_eq, from_nz = from_str.split(".", 1)
            to_eq, to_nz = to_str.split(".", 1)

            sched_str = kv.get("sched", "40")
            try:
                sched = PipeSchedule(sched_str)
            except ValueError:
                sched = PipeSchedule.SCH_40

            pipe = Pipe(
                tag=pipe_tag,
                from_equipment=from_eq.upper(),
                from_nozzle=from_nz,
                to_equipment=to_eq.upper(),
                to_nozzle=to_nz,
                diameter_mm=float(kv.get("dn", 50.0)),
                schedule=sched,
                fluid=kv.get("fluid", "process"),
            )
            diagram.add_pipe(pipe)
        except (IndexError, ValueError, KeyError) as exc:
            warnings.append(f"Pipe parse error on line {line!r}: {exc}")

    return diagram, warnings


def _parse_kv(tokens: list[str]) -> dict[str, str]:
    """Parse key=value tokens into a dict."""
    result: dict[str, str] = {}
    for tok in tokens:
        if "=" in tok:
            k, v = tok.split("=", 1)
            result[k.strip().lower()] = v.strip()
    return result


# ---------------------------------------------------------------------------
# piping_export_svg
# ---------------------------------------------------------------------------

piping_export_svg_spec = ToolSpec(
    name="piping_export_svg",
    description=(
        "Export a P&ID text specification as an SVG schematic. "
        "Parses the text spec, then returns the SVG string."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "P&ID specification text (same format as piping_import_pid).",
            },
            "diagram_name": {
                "type": "string",
                "description": "Optional diagram name.",
            },
            "width": {
                "type": "integer",
                "description": "SVG canvas width in pixels. Default 800.",
            },
            "height": {
                "type": "integer",
                "description": "SVG canvas height in pixels. Default 300.",
            },
        },
        "required": ["text"],
    },
)


async def run_piping_export_svg(args: dict[str, Any], ctx: "ProjectCtx") -> str:
    try:
        from kerf_piping.symbols import pid_diagram_svg

        text: str = args["text"]
        name: str = str(args.get("diagram_name", "P&ID-001"))
        width: int = int(args.get("width", 800))
        height: int = int(args.get("height", 300))

        diagram, warnings = _parse_pid_text(text, name)
        svg = pid_diagram_svg(diagram, width=width, height=height)

        payload = {
            "svg": svg,
            "warnings": warnings,
            "component_count": len(diagram.components),
            "pipe_count": len(diagram.pipes),
        }
        return ok_payload(payload)
    except Exception as exc:
        return err_payload(str(exc), "PIPING_SVG_ERROR")
