"""
curtain_wall_geom.py — LLM tool for curtain-wall B-rep geometry (GK-P49).

Exposes curtain_wall_geometry() as bim.curtain_wall_geom, returning
mullion and panel Body counts + geometry metadata.
"""
from __future__ import annotations

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_civil._compat import ToolSpec, err_payload, ok_payload, ProjectCtx  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# ToolSpec
# ---------------------------------------------------------------------------

curtain_wall_geom_spec = ToolSpec(
    name="bim_curtain_wall_geometry",
    description=(
        "Compute B-rep mullion and panel solids for a curtain wall from a "
        "base-curve start/end point, height, grid divisions, and panel type.  "
        "Returns mullion and panel Body counts and grid dimensions.\n"
        "\n"
        "Returns:\n"
        "  ok             : bool\n"
        "  u_count        : int  (panel columns)\n"
        "  v_count        : int  (panel rows)\n"
        "  mullion_count  : int  (total mullion + rail solids)\n"
        "  panel_count    : int  (total panel solids)\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "start_pt": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y] start of base curve in mm.",
            },
            "end_pt": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y] end of base curve in mm.",
            },
            "base_z": {
                "type": "number",
                "description": "Z elevation of wall base (mm).",
                "default": 0.0,
            },
            "height_mm": {
                "type": "number",
                "description": "Wall height (mm).",
                "default": 3000.0,
            },
            "u_divisions": {
                "type": "array",
                "description": "Division specs for u-direction (along base curve).",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["count", "spacing"]},
                        "value": {},
                    },
                    "required": ["type", "value"],
                },
                "default": [{"type": "count", "value": 4}],
            },
            "v_divisions": {
                "type": "array",
                "description": "Division specs for v-direction (height).",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["count", "spacing"]},
                        "value": {},
                    },
                    "required": ["type", "value"],
                },
                "default": [{"type": "count", "value": 3}],
            },
            "mullion_size_mm": {
                "type": "number",
                "description": "Mullion cross-section size (mm).",
                "default": 50.0,
            },
            "panel_kind": {
                "type": "string",
                "enum": ["glass", "solid", "opening"],
                "description": "Panel type.",
                "default": "glass",
            },
        },
        "required": ["start_pt", "end_pt"],
    },
)


async def run_bim_curtain_wall_geometry(params: dict, ctx: "ProjectCtx") -> str:
    try:
        from kerf_bim.curtain_wall_geom import curtain_wall_geometry

        start_pt = params.get("start_pt", [0.0, 0.0])
        end_pt = params.get("end_pt", [6000.0, 0.0])

        if not isinstance(start_pt, (list, tuple)) or len(start_pt) < 2:
            return err_payload("start_pt must be [x, y]", "BAD_ARGS")
        if not isinstance(end_pt, (list, tuple)) or len(end_pt) < 2:
            return err_payload("end_pt must be [x, y]", "BAD_ARGS")

        doc = {
            "height_mm": float(params.get("height_mm", 3000.0)),
            "u_divisions": params.get("u_divisions", [{"type": "count", "value": 4}]),
            "v_divisions": params.get("v_divisions", [{"type": "count", "value": 3}]),
            "mullion_type": {"size_mm": float(params.get("mullion_size_mm", 50.0))},
            "panel_type": {"kind": params.get("panel_kind", "glass")},
        }

        result = curtain_wall_geometry(
            doc,
            start_pt=list(start_pt[:2]),
            end_pt=list(end_pt[:2]),
            base_z=float(params.get("base_z", 0.0)),
        )

        return ok_payload({
            "ok": True,
            "u_count": result.u_count,
            "v_count": result.v_count,
            "mullion_count": result.mullion_count,
            "panel_count": result.panel_count,
        })
    except Exception as exc:
        return err_payload(str(exc), "BIM_CURTAIN_WALL_GEOM_ERROR")


# TOOLS list consumed by plugin._register_tools
TOOLS = [
    ("bim_curtain_wall_geometry", curtain_wall_geom_spec, run_bim_curtain_wall_geometry),
]
