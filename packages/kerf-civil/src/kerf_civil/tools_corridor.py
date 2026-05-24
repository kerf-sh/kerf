"""
tools_corridor.py — LLM tools for corridor B-rep, volume, and IFC alignment (GK-P49).

Exposes:
  civil_corridor_brep        — Corridor.to_brep(): swept road solid
  civil_corridor_volume      — Corridor.volume(): pavement volume estimate
  civil_corridor_ifc_alignment — Corridor.ifc_alignment_dict()
"""
from __future__ import annotations

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_civil._compat import ToolSpec, err_payload, ok_payload, ProjectCtx  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Shared helper: build a Corridor from params
# ---------------------------------------------------------------------------

def _build_corridor(params: dict):
    from kerf_civil.horizontal_alignment import HorizontalAlignment
    from kerf_civil.vertical_alignment import VerticalAlignment
    from kerf_civil.corridor import TypicalSection, Corridor

    L = float(params.get("alignment_length_m", 200.0))
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
        cut_slope=float(params.get("cut_slope", 2.0)),
        fill_slope=float(params.get("fill_slope", 2.0)),
    )

    return Corridor(h_alignment=ha, v_alignment=va, typical_section=ts)


# ---------------------------------------------------------------------------
# Tool: civil_corridor_brep
# ---------------------------------------------------------------------------

civil_corridor_brep_spec = ToolSpec(
    name="civil_corridor_brep",
    description=(
        "Build a swept B-rep Body representing a straight road corridor.  "
        "The body is constructed by sweeping a typical cross-section along "
        "the alignment at regular station intervals.  Returns body face count "
        "and shell statistics.\n"
        "\n"
        "Returns:\n"
        "  ok          : bool\n"
        "  face_count  : int\n"
        "  shell_count : int\n"
        "\n"
        "Errors: {ok:false, reason}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alignment_length_m": {
                "type": "number",
                "description": "Total alignment length (m).",
                "default": 200.0,
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
            "grade_pct": {"type": "number", "default": 0.0},
            "datum_elev_m": {"type": "number", "default": 0.0},
            "cut_slope": {"type": "number", "default": 2.0},
            "fill_slope": {"type": "number", "default": 2.0},
        },
        "required": [],
    },
)


async def run_civil_corridor_brep(params: dict, ctx: "ProjectCtx") -> str:
    try:
        corridor = _build_corridor(params)
        interval = float(params.get("interval_m", 20.0))
        body = corridor.to_brep(interval=interval)

        face_count = 0
        shell_count = 0
        for shell in getattr(body, "shells", []):
            face_count += len(shell.faces)
            shell_count += 1
        for solid in getattr(body, "solids", []):
            for shell in solid.shells:
                face_count += len(shell.faces)
                shell_count += 1

        return ok_payload({
            "ok": True,
            "face_count": face_count,
            "shell_count": shell_count,
        })
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_CORRIDOR_BREP_ERROR")


# ---------------------------------------------------------------------------
# Tool: civil_corridor_volume
# ---------------------------------------------------------------------------

civil_corridor_volume_spec = ToolSpec(
    name="civil_corridor_volume",
    description=(
        "Estimate the pavement volume (m³) for a road corridor using "
        "prismatoid integration over the swept cross-section.  Assumes 0.5 m "
        "combined pavement + base course depth.\n"
        "\n"
        "Returns:\n"
        "  ok       : bool\n"
        "  volume_m3: float\n"
        "\n"
        "Errors: {ok:false, reason}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alignment_length_m": {"type": "number", "default": 200.0},
            "interval_m": {"type": "number", "default": 20.0},
            "lane_width_m": {"type": "number", "default": 3.65},
            "shoulder_width_m": {"type": "number", "default": 2.4},
            "lanes_each_side": {"type": "integer", "default": 1},
            "crown_slope_pct": {"type": "number", "default": 2.0},
            "grade_pct": {"type": "number", "default": 0.0},
            "datum_elev_m": {"type": "number", "default": 0.0},
        },
        "required": [],
    },
)


async def run_civil_corridor_volume(params: dict, ctx: "ProjectCtx") -> str:
    try:
        corridor = _build_corridor(params)
        interval = float(params.get("interval_m", 20.0))
        vol = corridor.volume(interval=interval)

        return ok_payload({
            "ok": True,
            "volume_m3": round(vol, 4),
        })
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_CORRIDOR_VOLUME_ERROR")


# ---------------------------------------------------------------------------
# Tool: civil_corridor_ifc_alignment
# ---------------------------------------------------------------------------

civil_corridor_ifc_alignment_spec = ToolSpec(
    name="civil_corridor_ifc_alignment",
    description=(
        "Return a minimal IfcAlignmentProduct dict for IFC export of a road "
        "corridor.  Includes total length, lane/shoulder widths, and slopes.\n"
        "\n"
        "Returns:\n"
        "  ok       : bool\n"
        "  ifc_dict : IfcAlignmentProduct dict\n"
        "\n"
        "Errors: {ok:false, reason}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "alignment_length_m": {"type": "number", "default": 200.0},
            "lane_width_m": {"type": "number", "default": 3.65},
            "shoulder_width_m": {"type": "number", "default": 2.4},
            "lanes_each_side": {"type": "integer", "default": 1},
            "crown_slope_pct": {"type": "number", "default": 2.0},
            "grade_pct": {"type": "number", "default": 0.0},
            "datum_elev_m": {"type": "number", "default": 0.0},
            "cut_slope": {"type": "number", "default": 2.0},
            "fill_slope": {"type": "number", "default": 2.0},
        },
        "required": [],
    },
)


async def run_civil_corridor_ifc_alignment(params: dict, ctx: "ProjectCtx") -> str:
    try:
        corridor = _build_corridor(params)
        ifc = corridor.ifc_alignment_dict()

        return ok_payload({
            "ok": True,
            "ifc_dict": ifc,
        })
    except Exception as exc:
        return err_payload(str(exc), "CIVIL_CORRIDOR_IFC_ERROR")


# TOOLS list consumed by plugin
TOOLS = [
    ("civil_corridor_brep",          civil_corridor_brep_spec,          run_civil_corridor_brep),
    ("civil_corridor_volume",        civil_corridor_volume_spec,        run_civil_corridor_volume),
    ("civil_corridor_ifc_alignment", civil_corridor_ifc_alignment_spec, run_civil_corridor_ifc_alignment),
]
