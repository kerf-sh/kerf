"""
site_geometry.py — LLM tools for BIM site geometry (GK-P49).

Exposes:
  bim_toposolid_to_brep  — Toposolid.to_brep(): TIN terrain → closed B-rep Body
  bim_cut_fill_volume    — cut_fill_volume(): earthwork volume between two terrains
"""
from __future__ import annotations

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_civil._compat import ToolSpec, err_payload, ok_payload, ProjectCtx  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Tool: bim_toposolid_to_brep
# ---------------------------------------------------------------------------

bim_toposolid_to_brep_spec = ToolSpec(
    name="bim_toposolid_to_brep",
    description=(
        "Build a closed B-rep Body from a triangulated terrain (Toposolid). "
        "The body consists of a TIN top surface, vertical side faces, and a "
        "flat base face.  Returns face count and body shell statistics.\n"
        "\n"
        "Returns:\n"
        "  ok            : bool\n"
        "  face_count    : int\n"
        "  simplex_count : int   (TIN triangles)\n"
        "  shell_closed  : bool\n"
        "\n"
        "Errors: {ok:false, reason}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "points": {
                "type": "array",
                "description": "Elevation control points as [[x,y,z], ...] (min 3).",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                },
            },
            "boundary": {
                "type": "array",
                "description": "Site boundary polygon as [[x,y], ...] (optional).",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                },
                "default": [],
            },
            "material": {
                "type": "string",
                "description": "Terrain material (default 'soil').",
                "default": "soil",
            },
            "thickness": {
                "type": "number",
                "description": "Solid depth below lowest terrain point (m).",
                "default": 1.0,
            },
        },
        "required": ["points"],
    },
)


async def run_bim_toposolid_to_brep(params: dict, ctx: "ProjectCtx") -> str:
    try:
        from kerf_bim.site import Toposolid

        points_raw = params.get("points", [])
        if len(points_raw) < 3:
            return err_payload("points must have at least 3 entries", "BAD_ARGS")

        points = [(float(p[0]), float(p[1]), float(p[2])) for p in points_raw]

        boundary_raw = params.get("boundary", [])
        if boundary_raw:
            boundary = [(float(b[0]), float(b[1])) for b in boundary_raw]
        else:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            boundary = [
                (min(xs), min(ys)),
                (max(xs), min(ys)),
                (max(xs), max(ys)),
                (min(xs), max(ys)),
            ]

        ts = Toposolid(
            boundary=boundary,
            points=points,
            material=str(params.get("material", "soil")),
            thickness=float(params.get("thickness", 1.0)),
        )

        body = ts.to_brep()

        # Count faces across all shells/solids
        face_count = 0
        shell_closed = False
        for shell in getattr(body, "shells", []):
            face_count += len(shell.faces)
            if shell.is_closed:
                shell_closed = True
        for solid in getattr(body, "solids", []):
            for shell in solid.shells:
                face_count += len(shell.faces)
                if shell.is_closed:
                    shell_closed = True

        return ok_payload({
            "ok": True,
            "face_count": face_count,
            "simplex_count": len(ts.simplices),
            "shell_closed": shell_closed,
        })
    except Exception as exc:
        return err_payload(str(exc), "BIM_TOPOSOLID_BREP_ERROR")


# ---------------------------------------------------------------------------
# Tool: bim_cut_fill_volume
# ---------------------------------------------------------------------------

bim_cut_fill_volume_spec = ToolSpec(
    name="bim_cut_fill_volume",
    description=(
        "Compute cut and fill earthwork volumes between two terrain surfaces "
        "(existing vs proposed) using grid-difference integration.  "
        "cut = material removed, fill = material added, net = fill - cut.\n"
        "\n"
        "Returns:\n"
        "  ok       : bool\n"
        "  cut      : float  (m³)\n"
        "  fill     : float  (m³)\n"
        "  net      : float  (m³, positive = net fill)\n"
        "\n"
        "Errors: {ok:false, reason}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "existing_points": {
                "type": "array",
                "description": "Existing terrain control points [[x,y,z], ...] (min 3).",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                },
            },
            "proposed_points": {
                "type": "array",
                "description": "Proposed terrain control points [[x,y,z], ...] (min 3).",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                },
            },
            "grid_spacing": {
                "type": "number",
                "description": "Integration grid cell size (m).  Smaller = more accurate.",
                "default": 1.0,
            },
        },
        "required": ["existing_points", "proposed_points"],
    },
)


async def run_bim_cut_fill_volume(params: dict, ctx: "ProjectCtx") -> str:
    try:
        from kerf_bim.site import Toposolid, cut_fill_volume

        def _make_ts(pts_raw):
            if len(pts_raw) < 3:
                raise ValueError("terrain points must have at least 3 entries")
            pts = [(float(p[0]), float(p[1]), float(p[2])) for p in pts_raw]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bnd = [
                (min(xs), min(ys)),
                (max(xs), min(ys)),
                (max(xs), max(ys)),
                (min(xs), max(ys)),
            ]
            return Toposolid(boundary=bnd, points=pts)

        ts_existing = _make_ts(params.get("existing_points", []))
        ts_proposed = _make_ts(params.get("proposed_points", []))

        grid_spacing = float(params.get("grid_spacing", 1.0))
        if grid_spacing <= 0:
            return err_payload("grid_spacing must be > 0", "BAD_ARGS")

        result = cut_fill_volume(ts_existing, ts_proposed, grid_spacing=grid_spacing)

        return ok_payload({
            "ok": True,
            "cut": round(result["cut"], 6),
            "fill": round(result["fill"], 6),
            "net": round(result["net"], 6),
        })
    except Exception as exc:
        return err_payload(str(exc), "BIM_CUT_FILL_ERROR")


# TOOLS list consumed by plugin._register_tools
TOOLS = [
    ("bim_toposolid_to_brep", bim_toposolid_to_brep_spec, run_bim_toposolid_to_brep),
    ("bim_cut_fill_volume",   bim_cut_fill_volume_spec,   run_bim_cut_fill_volume),
]
