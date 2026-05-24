"""
roof_geometry.py — LLM tool for parametric roof geometry (GK-P49).

Exposes make_roof() (hip/gable/shed/mono) as bim.roof_geometry.
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

make_roof_spec = ToolSpec(
    name="bim_make_roof",
    description=(
        "Generate parametric B-rep roof geometry (hip, gable, shed, or mono-pitch) "
        "from a rectangular footprint, pitch angle, and overhang.  Returns body "
        "face count, ridge elevation, IFC dict, and a serialisable geometry summary.  "
        "Roof types: 'hip' (four sloped faces), 'gable' (two slopes + gable ends), "
        "'shed'/'mono' (single slope lean-to).\n"
        "\n"
        "Returns:\n"
        "  ok           : bool\n"
        "  roof_type    : str\n"
        "  faces_count  : int\n"
        "  ridge_z_mm   : float\n"
        "  ridge_pts    : list of [x,y,z]\n"
        "  ifc_dict     : IfcRoof property dict\n"
        "\n"
        "Errors: {ok:false, reason} for invalid inputs."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "roof_type": {
                "type": "string",
                "enum": ["hip", "gable", "shed", "mono"],
                "description": "Roof type.",
                "default": "gable",
            },
            "x_min": {"type": "number", "description": "Footprint x_min (mm).", "default": 0.0},
            "y_min": {"type": "number", "description": "Footprint y_min (mm).", "default": 0.0},
            "x_max": {"type": "number", "description": "Footprint x_max (mm).", "default": 10000.0},
            "y_max": {"type": "number", "description": "Footprint y_max (mm).", "default": 6000.0},
            "base_z": {"type": "number", "description": "Plate elevation (mm).", "default": 3000.0},
            "pitch_deg": {
                "type": "number",
                "description": "Roof pitch angle in degrees [1, 89].",
                "default": 30.0,
            },
            "overhang": {
                "type": "number",
                "description": "Horizontal overhang beyond wall plate (mm).",
                "default": 600.0,
            },
            "material": {
                "type": "string",
                "description": "Roof material identifier.",
                "default": "roof_tile",
            },
        },
        "required": [],
    },
)


async def run_bim_make_roof(params: dict, ctx: "ProjectCtx") -> str:
    try:
        from kerf_bim.roof_geometry import RoofParams, make_roof

        roof_params = RoofParams(
            roof_type=params.get("roof_type", "gable"),
            x_min=float(params.get("x_min", 0.0)),
            y_min=float(params.get("y_min", 0.0)),
            x_max=float(params.get("x_max", 10000.0)),
            y_max=float(params.get("y_max", 6000.0)),
            base_z=float(params.get("base_z", 3000.0)),
            pitch_deg=float(params.get("pitch_deg", 30.0)),
            overhang=float(params.get("overhang", 600.0)),
            material=str(params.get("material", "roof_tile")),
        )

        rg = make_roof(roof_params)

        ridge_pts_out = [
            [float(p[0]), float(p[1]), float(p[2])]
            for p in rg.ridge_pts
        ]

        return ok_payload({
            "ok": True,
            "roof_type": rg.params.roof_type,
            "faces_count": rg.faces_count,
            "ridge_z_mm": round(rg.ridge_z, 4),
            "ridge_pts": ridge_pts_out,
            "ifc_dict": rg.ifc_dict,
        })
    except Exception as exc:
        return err_payload(str(exc), "BIM_ROOF_ERROR")


# TOOLS list consumed by plugin._register_tools
TOOLS = [
    ("bim_make_roof", make_roof_spec, run_bim_make_roof),
]
