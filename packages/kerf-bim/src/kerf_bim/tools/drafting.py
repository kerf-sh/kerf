"""
drafting.py — LLM tools for architectural drafting geometry (GK-P49).

Exposes:
  bim_hatch_region    — 2D pattern fill inside a closed loop
  bim_section_fill    — filled section graphics from a mesh/surface + plane
  bim_make2d_from_brep — auto hidden-line projection from a B-rep Body
"""
from __future__ import annotations

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_civil._compat import ToolSpec, err_payload, ok_payload, ProjectCtx  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Tool: bim_hatch_region
# ---------------------------------------------------------------------------

bim_hatch_region_spec = ToolSpec(
    name="bim_hatch_region",
    description=(
        "Fill a closed 2D planar region (rectangle or polygon) with an "
        "architectural hatch pattern.  Supported patterns: ansi31 (general "
        "45° hatching), concrete, brick, earth, wood, sand, insulation, steel, "
        "glass.  Returns clipped hatch line segments in 2D.\n"
        "\n"
        "Returns:\n"
        "  ok          : bool\n"
        "  pattern     : str   (resolved pattern key)\n"
        "  line_count  : int\n"
        "  lines       : list of {start:[u,v], end:[u,v]}\n"
        "\n"
        "Errors: {ok:false, reason}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "boundary": {
                "type": "array",
                "description": "Closed polygon as [[x,y,z], ...] (at least 3 points; z=0 for 2D use).",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                },
            },
            "pattern": {
                "type": "string",
                "description": "Hatch pattern name (default 'ansi31').",
                "default": "ansi31",
            },
            "angle": {
                "type": "number",
                "description": "Base hatch line angle in degrees.",
                "default": 45.0,
            },
            "scale": {
                "type": "number",
                "description": "Hatch spacing (units of the loop coordinate system).",
                "default": 1.0,
            },
        },
        "required": ["boundary"],
    },
)


async def run_bim_hatch_region(params: dict, ctx: "ProjectCtx") -> str:
    try:
        import numpy as np
        from kerf_cad_core.geom.brep import Vertex, Edge, Coedge, Loop, Line3  # type: ignore
        from kerf_cad_core.geom.region2d import hatch_region  # type: ignore

        boundary = params.get("boundary")
        if not boundary or len(boundary) < 3:
            return err_payload("boundary must have at least 3 points", "BAD_ARGS")

        scale = float(params.get("scale", 1.0))
        if scale <= 0:
            return err_payload("scale must be > 0", "BAD_ARGS")

        pts = [np.array([float(c) for c in pt[:3]], dtype=float) for pt in boundary]
        # Build a Loop from the polygon
        n = len(pts)
        coedges = []
        for i in range(n):
            p0, p1 = pts[i], pts[(i + 1) % n]
            v0, v1 = Vertex(p0), Vertex(p1)
            e = Edge(Line3(p0=p0, p1=p1), 0.0, 1.0, v0, v1)
            coedges.append(Coedge(edge=e, orientation=True))
        loop = Loop(coedges=coedges, is_outer=True)

        hatch = hatch_region(
            loop,
            pattern=str(params.get("pattern", "ansi31")),
            angle=float(params.get("angle", 45.0)),
            scale=scale,
        )

        return ok_payload({
            "ok": True,
            "pattern": hatch.pattern,
            "line_count": len(hatch.lines),
            "lines": [
                {"start": list(ln.start), "end": list(ln.end)}
                for ln in hatch.lines
            ],
        })
    except Exception as exc:
        return err_payload(str(exc), "BIM_HATCH_ERROR")


# ---------------------------------------------------------------------------
# Tool: bim_section_fill
# ---------------------------------------------------------------------------

bim_section_fill_spec = ToolSpec(
    name="bim_section_fill",
    description=(
        "Section a triangle mesh with a plane and fill the resulting loops "
        "with an architectural hatch pattern.  Produces filled section "
        "graphics as per BIM construction drawings.\n"
        "\n"
        "Returns:\n"
        "  ok           : bool\n"
        "  loop_count   : int\n"
        "  fills        : list of {loop_index, line_count, pattern, lines}\n"
        "  plane_normal : [nx, ny, nz]\n"
        "  plane_d      : float\n"
        "\n"
        "Errors: {ok:false, reason}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "vertices": {
                "type": "array",
                "description": "List of [x,y,z] mesh vertices.",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                },
            },
            "triangles": {
                "type": "array",
                "description": "List of [i,j,k] triangle index triples.",
                "items": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "plane_normal": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[nx, ny, nz] cutting plane normal.",
            },
            "plane_point": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[px, py, pz] a point on the cutting plane.",
                "default": [0.0, 0.0, 0.0],
            },
            "material": {
                "type": "string",
                "description": "BIM material identifier (e.g. 'brick_clay').  Overrides pattern.",
                "default": "",
            },
            "pattern": {
                "type": "string",
                "description": "Explicit hatch pattern name if material is empty.",
                "default": "ansi31",
            },
            "angle": {"type": "number", "default": 45.0},
            "scale": {"type": "number", "default": 1.0},
        },
        "required": ["vertices", "triangles", "plane_normal"],
    },
)


async def run_bim_section_fill(params: dict, ctx: "ProjectCtx") -> str:
    try:
        from kerf_cad_core.geom.section_contour import section_fill  # type: ignore

        vertices = params.get("vertices", [])
        triangles = params.get("triangles", [])

        if not vertices or not triangles:
            return err_payload("vertices and triangles are required", "BAD_ARGS")

        plane_normal = params.get("plane_normal", [0.0, 0.0, 1.0])
        plane_point = params.get("plane_point", [0.0, 0.0, 0.0])

        import numpy as np
        n = np.array(plane_normal, dtype=float)
        p = np.array(plane_point, dtype=float)
        n_mag = float(np.linalg.norm(n))
        if n_mag < 1e-14:
            return err_payload("plane_normal must be non-zero", "BAD_ARGS")
        n = n / n_mag
        d = float(np.dot(n, p))

        mesh = (
            [[float(c) for c in v] for v in vertices],
            [[int(i) for i in t] for t in triangles],
        )

        result = section_fill(
            mesh,
            {"normal": list(n), "d": d},
            material=str(params.get("material", "")),
            pattern=str(params.get("pattern", "ansi31")),
            angle=float(params.get("angle", 45.0)),
            scale=float(params.get("scale", 1.0)),
        )

        return ok_payload(result)
    except Exception as exc:
        return err_payload(str(exc), "BIM_SECTION_FILL_ERROR")


# ---------------------------------------------------------------------------
# Tool: bim_make2d_from_brep
# ---------------------------------------------------------------------------

bim_make2d_from_brep_spec = ToolSpec(
    name="bim_make2d_from_brep",
    description=(
        "Auto-tessellate a B-rep Body and project it to a 2D hidden-line "
        "drawing (Rhino Make2D parity).  Accepts a mesh (vertices + triangles) "
        "in place of a live B-rep when called from the LLM context.  Returns "
        "separate visible and hidden polyline lists.\n"
        "\n"
        "Returns:\n"
        "  ok              : bool\n"
        "  visible_count   : int\n"
        "  hidden_count    : int\n"
        "  visible         : list of [[x,y],...] polylines\n"
        "  hidden          : list of [[x,y],...] polylines\n"
        "\n"
        "Errors: {ok:false, reason}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "vertices": {
                "type": "array",
                "description": "List of [x,y,z] mesh vertices.",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                },
            },
            "triangles": {
                "type": "array",
                "description": "List of [i,j,k] index triples.",
                "items": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "view_direction": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[dx,dy,dz] view direction vector (default isometric).",
                "default": [-1.0, -1.0, -1.0],
            },
            "scale": {
                "type": "number",
                "description": "Output scale factor.",
                "default": 1.0,
            },
        },
        "required": ["vertices", "triangles"],
    },
)


async def run_bim_make2d_from_brep(params: dict, ctx: "ProjectCtx") -> str:
    try:
        import numpy as np
        from kerf_cad_core.geom.make2d import make2d, Make2DInput, ViewParams  # type: ignore

        vertices = params.get("vertices", [])
        triangles = params.get("triangles", [])

        if not vertices or not triangles:
            return err_payload("vertices and triangles are required", "BAD_ARGS")

        verts_np = np.array([[float(c) for c in v] for v in vertices], dtype=float)
        tris_np = np.array([[int(i) for i in t] for t in triangles], dtype=int)

        view_dir = params.get("view_direction", [-1.0, -1.0, -1.0])
        view = ViewParams(direction=view_dir)

        mesh_input = Make2DInput(vertices=verts_np, triangles=tris_np)
        result = make2d(mesh_input, view, scale=float(params.get("scale", 1.0)))

        return ok_payload({
            "ok": True,
            "visible_count": len(result.visible),
            "hidden_count": len(result.hidden),
            "visible": [[[float(x), float(y)] for x, y in pl] for pl in result.visible],
            "hidden":  [[[float(x), float(y)] for x, y in pl] for pl in result.hidden],
        })
    except Exception as exc:
        return err_payload(str(exc), "BIM_MAKE2D_ERROR")


# TOOLS list consumed by plugin._register_tools
TOOLS = [
    ("bim_hatch_region",       bim_hatch_region_spec,       run_bim_hatch_region),
    ("bim_section_fill",       bim_section_fill_spec,       run_bim_section_fill),
    ("bim_make2d_from_brep",   bim_make2d_from_brep_spec,   run_bim_make2d_from_brep),
]
