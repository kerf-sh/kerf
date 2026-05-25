"""
walls_slabs.py — LLM tools for compound walls and floor/roof slabs.

Tools
-----
bim_make_wall   — create a compound-layered wall instance
bim_make_slab   — create a floor/roof slab instance from a boundary polygon
"""
from __future__ import annotations

import json

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_bim.tools._compat import ToolSpec, err_payload, ok_payload, ProjectCtx  # type: ignore


# ---------------------------------------------------------------------------
# bim_make_wall
# ---------------------------------------------------------------------------

_make_wall_spec = ToolSpec(
    name="bim_make_wall",
    description=(
        "Create a compound-layered wall instance.\n"
        "\n"
        "Supply either a preset_name (e.g. 'Ext - Single Brick 230') to get a\n"
        "pre-defined compound wall type, or provide layers to define a custom type.\n"
        "\n"
        "Wall geometry is defined by a start point [x, y] and end point [x, y] in\n"
        "metres, plus a height in metres.  All coordinates are in metres.\n"
        "\n"
        "Layer format: [[material_name, thickness_mm, function], ...]\n"
        "  function: 'structure' | 'finish1' | 'finish2' | 'substrate' |\n"
        "            'thermal' | 'membrane' | 'air_gap'\n"
        "\n"
        "Returns IFC-ready dict with layer breakdown, total thickness, and geometry."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "start_m": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Wall start point [x, y] in metres.",
            },
            "end_m": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "Wall end point [x, y] in metres.",
            },
            "height_m": {
                "type": "number",
                "description": "Wall height in metres (default 3.0).",
                "default": 3.0,
            },
            "preset_name": {
                "type": "string",
                "description": (
                    "Named preset type. One of: "
                    "'Ext - Single Brick 230', 'Ext - Brick Veneer Cavity 350', "
                    "'Int - Steel Stud 98', 'Ext - Tilt-Up Concrete 200', "
                    "'Int - AAC Block 200'."
                ),
            },
            "type_name": {
                "type": "string",
                "description": "Custom wall type name (used when layers are provided).",
                "default": "Custom Wall",
            },
            "layers": {
                "type": "array",
                "description": "Wall layers as [[material, thickness_mm, function], ...]. Required when preset_name is not given.",
                "items": {
                    "type": "array",
                    "items": [
                        {"type": "string", "description": "Material name"},
                        {"type": "number", "description": "Thickness in mm"},
                        {"type": "string", "description": "Layer function"},
                    ],
                    "minItems": 3,
                    "maxItems": 3,
                },
            },
            "level": {
                "type": "string",
                "description": "Storey level identifier (default 'L1').",
                "default": "L1",
            },
            "name": {
                "type": "string",
                "description": "Optional instance name.",
                "default": "",
            },
        },
        "required": ["start_m", "end_m"],
    },
)


async def run_bim_make_wall(params: dict, ctx: "ProjectCtx") -> str:
    try:
        from kerf_bim.walls import (
            make_compound_wall, make_wall_instance, wall_to_ifc_dict,
            PRESET_WALLS,
        )

        start = params.get("start_m")
        end = params.get("end_m")
        if not start or not end:
            return err_payload("start_m and end_m are required", "BAD_ARGS")

        # Convert metres → mm for internal API
        start_mm = [float(start[0]) * 1000.0, float(start[1]) * 1000.0]
        end_mm   = [float(end[0])   * 1000.0, float(end[1])   * 1000.0]
        height_mm = float(params.get("height_m", 3.0)) * 1000.0

        # Resolve wall type
        preset_name = params.get("preset_name")
        if preset_name:
            if preset_name not in PRESET_WALLS:
                available = list(PRESET_WALLS.keys())
                return err_payload(
                    f"preset_name {preset_name!r} not found. Available: {available}",
                    "BAD_ARGS",
                )
            wall_type = PRESET_WALLS[preset_name]
        else:
            raw_layers = params.get("layers")
            if not raw_layers:
                return err_payload(
                    "Either preset_name or layers is required", "BAD_ARGS"
                )
            layers = [(str(m), float(t), str(fn)) for m, t, fn in raw_layers]
            wall_type = make_compound_wall(
                name=str(params.get("type_name", "Custom Wall")),
                layers=layers,
            )

        instance = make_wall_instance(
            wall_type=wall_type,
            start=start_mm,
            end=end_mm,
            height=height_mm,
            level=str(params.get("level", "L1")),
            name=str(params.get("name", "")),
        )

        ifc_dict = wall_to_ifc_dict(instance)

        # Compute length in metres
        dx = end_mm[0] - start_mm[0]
        dy = end_mm[1] - start_mm[1]
        import math
        length_m = round(math.sqrt(dx * dx + dy * dy) / 1000.0, 4)

        return ok_payload({
            "ok": True,
            "type_name": wall_type.name,
            "n_layers": len(wall_type.layers),
            "total_thickness_mm": round(wall_type.total_thickness, 2),
            "length_m": length_m,
            "height_m": round(height_mm / 1000.0, 4),
            "layers": [
                {
                    "material": layer.material,
                    "thickness_mm": round(layer.thickness, 2),
                    "function": layer.function,
                }
                for layer in wall_type.layers
            ],
            "ifc_dict": ifc_dict,
        })
    except Exception as exc:
        return err_payload(str(exc), "BIM_WALL_ERROR")


# ---------------------------------------------------------------------------
# bim_make_slab
# ---------------------------------------------------------------------------

_make_slab_spec = ToolSpec(
    name="bim_make_slab",
    description=(
        "Create a floor or roof slab instance from a boundary polygon.\n"
        "\n"
        "Supply either a preset_name (e.g. 'RC Flat Slab 200') or provide layers\n"
        "to define a custom slab type.\n"
        "\n"
        "Boundary polygon: list of [x, y] vertices in metres (min 3 points).\n"
        "\n"
        "Layer format: [[material_name, thickness_mm, layer_function], ...]\n"
        "  layer function: 'structure' | 'substrate' | 'thermal' | 'finish' | 'membrane'\n"
        "  slab_function (type-level): 'floor' | 'roof' | 'foundation'\n"
        "\n"
        "Returns IFC-ready dict with total thickness, layer breakdown, and boundary."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "boundary_m": {
                "type": "array",
                "description": "Boundary polygon as [[x, y], ...] in metres (min 3 vertices).",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "minItems": 3,
            },
            "preset_name": {
                "type": "string",
                "description": (
                    "Named preset type. One of: "
                    "'RC Flat Slab 200', 'RC Slab + Screed 220', "
                    "'RC Slab + Raised Access Floor 250', 'RC Flat Roof 200 + Insulation', "
                    "'RC Ramp Slab 200 (5° slope)'."
                ),
            },
            "type_name": {
                "type": "string",
                "description": "Custom slab type name (used when layers are provided).",
                "default": "Custom Slab",
            },
            "layers": {
                "type": "array",
                "description": "Slab layers as [[material, thickness_mm, function], ...]. Required when preset_name is not given.",
                "items": {
                    "type": "array",
                    "items": [
                        {"type": "string"},
                        {"type": "number"},
                        {"type": "string"},
                    ],
                    "minItems": 3,
                    "maxItems": 3,
                },
            },
            "slab_function": {
                "type": "string",
                "enum": ["floor", "roof", "foundation"],
                "description": "Slab function for custom type (default 'floor').",
                "default": "floor",
            },
            "level": {
                "type": "string",
                "description": "Storey level identifier (default 'L1').",
                "default": "L1",
            },
            "name": {
                "type": "string",
                "description": "Optional instance name.",
                "default": "",
            },
        },
        "required": ["boundary_m"],
    },
)


async def run_bim_make_slab(params: dict, ctx: "ProjectCtx") -> str:
    try:
        from kerf_bim.slabs import (
            make_slab_type, make_slab_instance, slab_to_ifc_dict,
            PRESET_SLAB_TYPES,
        )

        boundary_m = params.get("boundary_m")
        if not boundary_m or len(boundary_m) < 3:
            return err_payload("boundary_m must have at least 3 vertices", "BAD_ARGS")

        # Convert metres → mm for internal API
        boundary_mm = [[float(pt[0]) * 1000.0, float(pt[1]) * 1000.0] for pt in boundary_m]

        # Resolve slab type
        preset_name = params.get("preset_name")
        if preset_name:
            if preset_name not in PRESET_SLAB_TYPES:
                available = list(PRESET_SLAB_TYPES.keys())
                return err_payload(
                    f"preset_name {preset_name!r} not found. Available: {available}",
                    "BAD_ARGS",
                )
            slab_type = PRESET_SLAB_TYPES[preset_name]
        else:
            raw_layers = params.get("layers")
            if not raw_layers:
                return err_payload(
                    "Either preset_name or layers is required", "BAD_ARGS"
                )
            layers = [(str(m), float(t), str(fn)) for m, t, fn in raw_layers]
            slab_type = make_slab_type(
                name=str(params.get("type_name", "Custom Slab")),
                layers=layers,
                function=str(params.get("slab_function", "floor")),
            )

        instance = make_slab_instance(
            slab_type=slab_type,
            boundary=boundary_mm,
            level=str(params.get("level", "L1")),
            name=str(params.get("name", "")),
        )

        ifc_dict = slab_to_ifc_dict(instance)

        return ok_payload({
            "ok": True,
            "type_name": slab_type.name,
            "n_layers": len(slab_type.layers),
            "total_thickness_mm": round(slab_type.total_thickness, 2),
            "function": slab_type.function,
            "n_boundary_pts": len(boundary_m),
            "layers": [
                {
                    "material": layer.material,
                    "thickness_mm": round(layer.thickness, 2),
                    "function": layer.function,
                }
                for layer in slab_type.layers
            ],
            "ifc_dict": ifc_dict,
        })
    except Exception as exc:
        return err_payload(str(exc), "BIM_SLAB_ERROR")


# ---------------------------------------------------------------------------
# TOOLS list consumed by plugin
# ---------------------------------------------------------------------------

TOOLS = [
    ("bim_make_wall", _make_wall_spec, run_bim_make_wall),
    ("bim_make_slab", _make_slab_spec, run_bim_make_slab),
]
