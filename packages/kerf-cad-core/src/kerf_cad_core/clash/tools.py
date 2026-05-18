"""
kerf_cad_core.clash.tools — LLM tool wrapper for cross-discipline clash detection.

Tool
----
clash_detect
    Detect spatial clashes (hard interference, clearance violations, coincident
    placements) between a list of component instances.  Each component is
    described by its placed bounding box, optional triangle mesh, and optional
    discipline tag for cross-discipline reporting.

Input schema
------------
{
  "components": [
    {
      "instance_id": "column-1",
      "discipline": "structural",                  // optional; e.g. structural/mep/architectural
      "transform": [16 floats, row-major 4x4],     // optional; identity if omitted
      "bbox_min": [x, y, z],                       // local-frame AABB min (mm)
      "bbox_max": [x, y, z],                       // local-frame AABB max (mm)
      "triangles": [[[x,y,z],[x,y,z],[x,y,z]],...] // optional mesh
    },
    ...
  ],
  "min_clearance": 1.0   // minimum required gap in mm (default 0)
}

Output payload
--------------
{
  "ok": bool,
  "clashes": [
    {"a": "id-a", "b": "id-b",
     "discipline_a": "structural", "discipline_b": "mep",
     "discipline_pair": "mep vs structural",
     "type": "hard"|"clearance"|"coincident",
     "depth": float}
  ],
  "clash_count": int,
  "by_discipline_pair": {
    "mep vs structural": {"hard": 1, "clearance": 0, "coincident": 0, "total": 1}
  },
  "errors": [str, ...]
}

Author: imranparuk
"""

from __future__ import annotations

import json

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
from kerf_core.utils.context import ProjectCtx  # type: ignore[import]

from kerf_cad_core.clash.detect import clash_detect as _clash_detect


# ---------------------------------------------------------------------------
# Tool spec
# ---------------------------------------------------------------------------

_spec = ToolSpec(
    name="clash_detect",
    description=(
        "Detect spatial clashes between a list of component instances placed "
        "in an assembly. "
        "Returns hard clashes (volume interpenetration), clearance violations "
        "(gap < min_clearance), and coincident/duplicate placements.\n"
        "\n"
        "Supports cross-discipline reporting: tag each component with a "
        "'discipline' string (e.g. 'structural', 'mep', 'architectural', "
        "'civil', 'mechanical', 'electrical') to get a by_discipline_pair "
        "summary grouped by discipline combination.\n"
        "\n"
        "Each component needs:\n"
        "  instance_id  — unique string identifier\n"
        "  discipline   — optional discipline tag for cross-discipline reporting\n"
        "  bbox_min     — local-frame bounding box min corner [x,y,z] (mm)\n"
        "  bbox_max     — local-frame bounding box max corner [x,y,z] (mm)\n"
        "  transform    — optional 4×4 row-major matrix (16 floats); "
        "identity if omitted\n"
        "  triangles    — optional list of triangles [[v0,v1,v2],...] in local "
        "frame for mesh-level narrow-phase intersection\n"
        "\n"
        "min_clearance  — required separation gap in mm (default 0; only hard "
        "clashes reported).\n"
        "\n"
        "Never raises; errors are returned in the 'errors' field."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "description": "List of component shape descriptors.",
                "items": {
                    "type": "object",
                    "properties": {
                        "instance_id": {"type": "string"},
                        "discipline": {
                            "type": "string",
                            "description": (
                                "Optional discipline tag for cross-discipline "
                                "reporting, e.g. 'structural', 'mep', "
                                "'architectural', 'civil', 'mechanical', "
                                "'electrical'."
                            ),
                        },
                        "transform": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "16-float row-major 4x4 transform. Identity if omitted.",
                        },
                        "bbox_min": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Local-frame AABB min corner [x,y,z] in mm.",
                        },
                        "bbox_max": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Local-frame AABB max corner [x,y,z] in mm.",
                        },
                        "triangles": {
                            "type": "array",
                            "description": "Optional triangle mesh [[v0,v1,v2],...] in local frame.",
                        },
                    },
                    "required": ["instance_id", "bbox_min", "bbox_max"],
                },
            },
            "min_clearance": {
                "type": "number",
                "description": (
                    "Minimum required separation gap in mm (default 0). "
                    "Components closer than this are reported as clearance violations."
                ),
            },
        },
        "required": ["components"],
    },
)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

@register(_spec, write=False)
async def run_clash_detect(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    raw_components = a.get("components")
    if raw_components is None:
        return err_payload("components is required", "BAD_ARGS")
    if not isinstance(raw_components, list):
        return err_payload("components must be a list", "BAD_ARGS")

    min_clearance = a.get("min_clearance", 0.0)

    result = _clash_detect(raw_components, min_clearance=min_clearance)

    return ok_payload({
        "ok": result["ok"],
        "clashes": result["clashes"],
        "clash_count": len(result["clashes"]),
        "by_discipline_pair": result.get("by_discipline_pair", {}),
        "errors": result["errors"],
    })


__all__ = ["run_clash_detect"]
