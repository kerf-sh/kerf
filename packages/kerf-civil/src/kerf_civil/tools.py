"""
LLM tool specifications and handlers for the civil engineering plugin.

Tools exposed:
  - civil_horizontal_alignment  — compute curve geometry for a compound alignment
  - civil_vertical_alignment    — compute grade and profile data
  - civil_corridor_sections     — sweep typical section, return cross-section data
  - civil_earthwork_volume      — average-end-area earthwork volumes
"""

from __future__ import annotations

import json
import math

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_civil._compat import ToolSpec, err_payload, ok_payload, ProjectCtx


# ---------------------------------------------------------------------------
# Tool: civil_horizontal_alignment
# ---------------------------------------------------------------------------

civil_horizontal_alignment_spec = ToolSpec(
    name="civil_horizontal_alignment",
    description=(
        "Compute geometry for a compound horizontal alignment consisting of tangents, "
        "circular arcs, and clothoid spirals.  Returns arc lengths, bearings, K values, "
        "and AASHTO superelevation for each element."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "elements": {
                "type": "array",
                "description": "Ordered list of alignment elements.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["tangent", "arc", "spiral"],
                        },
                        "length": {"type": "number", "description": "Length (m) — tangent or spiral"},
                        "radius": {"type": "number", "description": "Radius (m) — arc or spiral end radius"},
                        "delta_deg": {"type": "number", "description": "Deflection angle (degrees) — arc only"},
                        "turn_right": {"type": "boolean", "description": "Turn direction — arc/spiral"},
                    },
                    "required": ["type"],
                },
            },
            "design_speed_mph": {
                "type": "integer",
                "description": "Design speed (mph) for AASHTO superelevation lookup.",
                "default": 60,
            },
        },
        "required": ["elements"],
    },
)


async def run_civil_horizontal_alignment(params: dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_civil.horizontal_alignment import (
            HorizontalAlignment,
            aashto_superelevation,
        )
        import math

        design_speed = params.get("design_speed_mph", 60)
        ha = HorizontalAlignment()
        results = []

        for elem in params.get("elements", []):
            etype = elem["type"]
            if etype == "tangent":
                length = float(elem.get("length", 0))
                ha.add_tangent(length)
                results.append({
                    "type": "tangent",
                    "length_m": length,
                    "arc_length_m": length,
                })
            elif etype == "arc":
                radius = float(elem["radius"])
                delta_deg = float(elem["delta_deg"])
                delta_rad = math.radians(delta_deg)
                turn_right = elem.get("turn_right", True)
                if not turn_right:
                    delta_rad = -abs(delta_rad)
                ha.add_arc(radius, delta_rad)
                arc_len = radius * abs(delta_rad)
                # AASHTO superelevation lookup (convert radius m → ft)
                radius_ft = radius * 3.28084
                e_pct = aashto_superelevation(design_speed, radius_ft)
                results.append({
                    "type": "arc",
                    "radius_m": radius,
                    "delta_deg": delta_deg,
                    "arc_length_m": round(arc_len, 4),
                    "chord_length_m": round(2 * radius * math.sin(abs(delta_rad) / 2), 4),
                    "tangent_length_m": round(radius * math.tan(abs(delta_rad) / 2), 4),
                    "superelevation_pct": round(e_pct, 2),
                })
            elif etype == "spiral":
                length = float(elem["length"])
                radius = float(elem["radius"])
                turn_right = elem.get("turn_right", True)
                ha.add_spiral(length, radius, turn_right)
                theta_s = length / (2.0 * radius)
                A = math.sqrt(radius * length)
                results.append({
                    "type": "spiral",
                    "length_m": length,
                    "radius_end_m": radius,
                    "clothoid_parameter_A": round(A, 4),
                    "end_angle_deg": round(math.degrees(theta_s), 4),
                    "turn_right": turn_right,
                })

        return ok_payload({
            "elements": results,
            "total_length_m": round(ha.total_length(), 4),
        })
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_HA_ERROR")


# ---------------------------------------------------------------------------
# Tool: civil_vertical_alignment
# ---------------------------------------------------------------------------

civil_vertical_alignment_spec = ToolSpec(
    name="civil_vertical_alignment",
    description=(
        "Design a vertical alignment from a sequence of grades and parabolic "
        "vertical curves.  Returns K-values, high/low-point locations, and "
        "elevation profiles."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "datum_elev_m": {
                "type": "number",
                "description": "Starting elevation (metres).",
                "default": 0.0,
            },
            "initial_grade_pct": {
                "type": "number",
                "description": "Initial grade (%).",
                "default": 0.0,
            },
            "elements": {
                "type": "array",
                "description": "Ordered list of tangent and curve elements.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["tangent", "curve"]},
                        "length": {"type": "number", "description": "Horizontal length (m)"},
                        "grade_out_pct": {
                            "type": "number",
                            "description": "Outgoing grade (%) — curves only",
                        },
                    },
                    "required": ["type", "length"],
                },
            },
        },
        "required": ["elements"],
    },
)


async def run_civil_vertical_alignment(params: dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_civil.vertical_alignment import VerticalAlignment

        va = VerticalAlignment()
        va.set_datum(elev=params.get("datum_elev_m", 0.0), grade_pct=params.get("initial_grade_pct", 0.0))
        results = []

        for elem in params.get("elements", []):
            etype = elem["type"]
            length = float(elem["length"])
            if etype == "tangent":
                va.add_tangent(length)
                results.append({"type": "tangent", "length_m": length})
            elif etype == "curve":
                grade_out = float(elem["grade_out_pct"])
                from kerf_civil.vertical_alignment import ParabolicCurve
                # Current state — peek at last grade
                g_in = va._current_grade_pct
                va.add_curve(length, grade_out)
                # Recover the curve we just appended
                c = va.elements[-1]
                info: dict = {
                    "type": "curve",
                    "length_m": length,
                    "grade_in_pct": g_in,
                    "grade_out_pct": grade_out,
                    "A_pct": round(c.A, 4),
                    "K_value": round(c.K_value(), 4),
                    "curve_type": "crest" if c.is_crest() else "sag",
                    "elev_bvc_m": round(c.elev_bvc, 4),
                    "elev_evc_m": round(c.elev_evc(), 4),
                }
                x_hp = c.high_low_point_x()
                if x_hp is not None:
                    info["high_low_point_x_m"] = round(x_hp, 4)
                    info["high_low_point_elev_m"] = round(c.high_low_point_elev(), 4)
                results.append(info)

        return ok_payload({
            "elements": results,
            "total_length_m": round(va.total_length(), 4),
            "end_elev_m": round(va._current_elev, 4),
        })
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_VA_ERROR")


# ---------------------------------------------------------------------------
# Tool: civil_corridor_sections
# ---------------------------------------------------------------------------

civil_corridor_sections_spec = ToolSpec(
    name="civil_corridor_sections",
    description=(
        "Sweep a typical section along a combined horizontal+vertical alignment "
        "to generate cross-sections at a specified interval."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alignment_length_m": {
                "type": "number",
                "description": "Total alignment length (m).",
            },
            "interval_m": {
                "type": "number",
                "description": "Station interval for cross-sections (m).",
                "default": 20.0,
            },
            "lane_width_m": {"type": "number", "default": 3.65},
            "shoulder_width_m": {"type": "number", "default": 2.4},
            "lanes_each_side": {"type": "integer", "default": 1},
            "crown_slope_pct": {"type": "number", "default": 2.0},
            "grade_pct": {
                "type": "number",
                "description": "Constant vertical grade (%) for a simple uniform profile.",
                "default": 0.0,
            },
            "datum_elev_m": {"type": "number", "default": 0.0},
        },
        "required": ["alignment_length_m"],
    },
)


async def run_civil_corridor_sections(params: dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        from kerf_civil.vertical_alignment import VerticalAlignment
        from kerf_civil.corridor import TypicalSection, Corridor

        L = float(params["alignment_length_m"])
        interval = float(params.get("interval_m", 20.0))
        grade = float(params.get("grade_pct", 0.0))
        datum = float(params.get("datum_elev_m", 0.0))

        ha = HorizontalAlignment()
        ha.add_tangent(L)

        va = VerticalAlignment()
        va.set_datum(elev=datum, grade_pct=grade)
        va.add_tangent(L)

        ts = TypicalSection(
            lane_width=float(params.get("lane_width_m", 3.65)),
            shoulder_width=float(params.get("shoulder_width_m", 2.4)),
            lanes_each_side=int(params.get("lanes_each_side", 1)),
            crown_slope_pct=float(params.get("crown_slope_pct", 2.0)),
        )

        corridor = Corridor(h_alignment=ha, v_alignment=va, typical_section=ts)
        sections = corridor.cross_sections(interval)

        out = []
        for xs in sections:
            out.append({
                "station_m": round(xs.station, 3),
                "cl_elev_m": round(xs.cl_elevation, 4),
                "points": [
                    {"offset_m": round(p.offset, 3), "elev_m": round(p.elevation, 4), "label": p.label}
                    for p in xs.points
                ],
            })

        return ok_payload({"cross_sections": out, "count": len(out)})
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_CORRIDOR_ERROR")


# ---------------------------------------------------------------------------
# Tool: civil_earthwork_volume
# ---------------------------------------------------------------------------

civil_earthwork_volume_spec = ToolSpec(
    name="civil_earthwork_volume",
    description=(
        "Compute cut and fill earthwork volumes from cross-sectional area data "
        "using the Average End Area method."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stations_m": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Station chainages (m), strictly increasing.",
            },
            "cut_areas_m2": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Cut cross-sectional area (m²) at each station.",
            },
            "fill_areas_m2": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Fill cross-sectional area (m²) at each station.",
            },
            "swell_factor": {
                "type": "number",
                "description": "Swell factor for mass haul (default 1.25).",
                "default": 1.25,
            },
        },
        "required": ["stations_m", "cut_areas_m2", "fill_areas_m2"],
    },
)


async def run_civil_earthwork_volume(params: dict, ctx: ProjectCtx) -> str:
    try:
        from kerf_civil.earthwork import (
            average_end_area_volume_variable,
            mass_haul,
        )

        stations = params["stations_m"]
        cut_areas = params["cut_areas_m2"]
        fill_areas = params["fill_areas_m2"]
        swell_factor = float(params.get("swell_factor", 1.25))

        total_cut = average_end_area_volume_variable(cut_areas, stations)
        total_fill = average_end_area_volume_variable(fill_areas, stations)

        mh = mass_haul(stations, cut_areas, fill_areas, swell_factor)
        final_mass = mh[-1].mass_ordinate if mh else 0.0

        return ok_payload({
            "total_cut_m3": round(total_cut, 3),
            "total_fill_m3": round(total_fill, 3),
            "net_mass_ordinate_m3": round(final_mass, 3),
            "mass_haul": [
                {
                    "station_m": o.station,
                    "mass_ordinate_m3": round(o.mass_ordinate, 3),
                }
                for o in mh
            ],
        })
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_EARTHWORK_ERROR")
