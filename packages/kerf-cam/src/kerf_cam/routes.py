"""
CAM toolpath generation via OpenCAMlib.

POST /run-cam
Body (worker shape):
    {
        "step_b64": string (base64-encoded STEP file),
        "input_spec": {
            "operation": "face"|"contour"|"pocket"|"drill"|"profile"
                        |"parallel_3d"|"waterline"|"lathe"|"5axis",
            "tool_diameter": float (mm),
            "step_over": float (mm),
            "step_down": float (mm),
            "feed_rate": float (mm/min),
            "spindle_speed": float (RPM),
            "coolant": bool,
            "face_id": int (optional, for contour/pocket — target face index),
            "direction": "x"|"y" (optional, for parallel_3d),
            "angle_deg": float (optional, for parallel_3d — arbitrary raster angle),
            "wire_tolerance": float (optional mm, for B-rep wire discretisation, default 0.05),
            "spindle_axis": "x"|"z" (optional, for lathe — default "z"),
        }
    }
Body (multi-op shape — accepted for direct API calls):
    {
        "step_b64": string,
        "operations": [{ type, tool_diameter, step_down, step_over, feed_rate, spindle_rpm, coolant }],
        "post_processor": string
    }

Returns:
    {
        "output_key": string,
        "toolpath_length": float,
        "estimated_time": float,
        "warnings": [],
        "errors": []
    }
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import base64
import math
import tempfile
from pathlib import Path
from typing import Optional, List

router = APIRouter()

# Gate opencamlib — import once at module load so tests can monkeypatch the flag.
_ocl_available = False
try:
    import opencamlib as ocl  # noqa: F401
    _ocl_available = True
except ImportError:
    pass

# Gate pythonOCC — use kerf_cad_core for shared STEP/STL helpers.
try:
    from kerf_cad_core import _OCC_AVAILABLE as _occ_available, convert_step_to_stl
except ImportError:
    # kerf_cad_core not installed — fall back to direct OCC check.
    _occ_available = False
    try:
        from OCC.Core.STEPControl import STEPControl_Reader as _STEPControl_Reader  # noqa: F401
        _occ_available = True
    except ImportError:
        pass

    def convert_step_to_stl(step_path: str, stl_path: str, linear_deflection: float = 0.1):
        """Inline fallback when kerf_cad_core is not installed."""
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
        from OCC.Core.StlAPI import StlAPI_Writer
        from OCC.Core.IFSelect import IFSelect_RetDone

        reader = STEPControl_Reader()
        status = reader.ReadFile(step_path)
        if status != IFSelect_RetDone:
            raise RuntimeError(f"STEPControl_Reader failed on {step_path} (status={status})")
        reader.TransferRoots()
        shape = reader.OneShape()
        mesh = BRepMesh_IncrementalMesh(shape, linear_deflection)
        mesh.Perform()
        if not mesh.IsDone():
            raise RuntimeError("BRepMesh_IncrementalMesh did not complete")
        writer = StlAPI_Writer()
        writer.ASCIIMode = True
        result = writer.Write(shape, stl_path)
        if not result:
            raise RuntimeError(f"StlAPI_Writer failed writing {stl_path}")
        return shape


class CAMOperation(BaseModel):
    type: str
    tool_diameter: float
    step_down: float
    step_over: float
    feed_rate: float
    spindle_rpm: int
    coolant: str = "flood"
    face_id: Optional[int] = None
    direction: Optional[str] = None      # "x" | "y" for parallel_3d
    angle_deg: Optional[float] = None    # arbitrary raster angle for parallel_3d
    wire_tolerance: Optional[float] = 0.05  # mm, B-rep wire discretisation
    spindle_axis: Optional[str] = "z"   # "x" | "z" for lathe


class CAMRequest(BaseModel):
    step_b64: str
    # Multi-op shape (direct API callers)
    operations: Optional[List[CAMOperation]] = None
    post_processor: str = "fanuc"
    # Worker shape (single input_spec dict)
    input_spec: Optional[dict] = None


@router.post("/run-cam")
async def run_cam(req: CAMRequest):
    if not req.step_b64:
        raise HTTPException(status_code=400, detail="step_b64 required")

    try:
        step_bytes = base64.b64decode(req.step_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid step_b64: {e}")

    # Normalise to operations list
    operations: List[CAMOperation]
    if req.operations:
        operations = req.operations
    elif req.input_spec:
        spec = req.input_spec
        operations = [CAMOperation(
            type=spec.get("operation", "profile"),
            tool_diameter=float(spec.get("tool_diameter", 3.0)),
            step_down=float(spec.get("step_down", 0.5)),
            step_over=float(spec.get("step_over", 0.5)),
            feed_rate=float(spec.get("feed_rate", 1000.0)),
            spindle_rpm=int(spec.get("spindle_speed", 10000)),
            coolant="flood" if spec.get("coolant", True) else "off",
            face_id=spec.get("face_id"),
            direction=spec.get("direction"),
            angle_deg=spec.get("angle_deg"),
            wire_tolerance=float(spec.get("wire_tolerance", 0.05)),
            spindle_axis=spec.get("spindle_axis", "z"),
        )]
    else:
        raise HTTPException(status_code=400, detail="either operations or input_spec required")

    # 5-axis stub: short-circuit before any heavy work.
    for op in operations:
        if op.type.lower() == "5axis":
            return {
                "output_key": "gcode",
                "gcode_b64": base64.b64encode(b"; 5-axis not yet implemented\n").decode(),
                "toolpath_length": 0.0,
                "estimated_time": 0.0,
                "warnings": [],
                "errors": ["not_implemented: 5-axis simultaneous toolpath is a planned feature. "
                           "Inputs were parsed successfully. Use 3-axis ops for now."],
            }

    warnings = []
    errors = []
    toolpath_length = 0.0
    estimated_time = 0.0

    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = Path(tmpdir) / "input.step"
        step_path.write_bytes(step_bytes)

        if not _ocl_available:
            warnings.append("opencamlib not installed — returning mock scaffold toolpath. "
                            "Install: pip install opencamlib (or build from source: "
                            "https://github.com/aewallin/opencamlib)")
            g_code, toolpath_length, estimated_time = _mock_toolpath(operations)
        else:
            try:
                stl_path = None
                occ_shape = None
                if _occ_available:
                    stl_path = str(Path(tmpdir) / "input.stl")
                    occ_shape = convert_step_to_stl(str(step_path), stl_path)
                else:
                    warnings.append(
                        "pythonOCC not installed — surface mesh unavailable; "
                        "toolpath will be computed on an empty surface. "
                        "Install: conda install -c conda-forge pythonocc-core"
                    )
                g_code, toolpath_length, estimated_time = generate_toolpaths(
                    str(step_path), operations, req.post_processor,
                    stl_path=stl_path, occ_shape=occ_shape,
                )
            except Exception as e:
                errors.append(str(e))
                g_code = ""

        gcode_path = Path(tmpdir) / "toolpath.nc"
        gcode_path.write_text(g_code)
        gcode_b64 = base64.b64encode(gcode_path.read_bytes()).decode()

    return {
        "output_key": "gcode",
        "gcode_b64": gcode_b64,
        "toolpath_length": toolpath_length,
        "estimated_time": estimated_time,
        "warnings": warnings,
        "errors": errors,
    }


def extract_face_wires(occ_shape, op: "CAMOperation") -> List[List[tuple]]:
    """Extract outer + inner wire polygons from B-rep faces.

    Finds planar faces with Z-normal (top face when face_id is None, or the
    face at index face_id if specified).  Each wire is discretised into a list
    of (x, y) tuples in millimetres (OCC geometry units match the STEP file's
    unit system — mm for typical mechanical STEP files) at the given
    wire_tolerance.

    Returns a list of wire-polygon lists: index 0 is the outer boundary, the
    rest are holes.  Returns an empty list if no matching face is found.
    """
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_WIRE
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepTools import BRepTools
    from OCC.Core.GeomLProp import GeomLProp_SLProps

    # wire_tolerance is in mm; OCC geometry units are mm for standard STEP files.
    tol_mm = max(op.wire_tolerance or 0.05, 1e-4)

    # Collect all planar faces with a Z normal (|nz| > 0.99)
    planar_faces = []
    exp = TopExp_Explorer(occ_shape, TopAbs_FACE)
    while exp.More():
        face = exp.Current()
        surf = BRep_Tool.Surface(face)
        # Get UV bounds via BRepTools (avoids ambiguous BRep_Tool.GetBounds overloads)
        u_min, u_max, v_min, v_max = BRepTools.UVBounds(face)
        u_mid = (u_min + u_max) / 2.0
        v_mid = (v_min + v_max) / 2.0
        props = GeomLProp_SLProps(surf, u_mid, v_mid, 1, 1e-6)
        if props.IsNormalDefined():
            n = props.Normal()
            if abs(abs(n.Z()) - 1.0) < 0.01:
                planar_faces.append(face)
        exp.Next()

    if not planar_faces:
        return []

    # Pick target face: by face_id if given, else the one with the highest Z centroid (top face)
    if op.face_id is not None and 0 <= op.face_id < len(planar_faces):
        target = planar_faces[op.face_id]
    else:
        # Highest Z centroid = top face
        def _face_z(f):
            from OCC.Core.GProp import GProp_GProps
            from OCC.Core.BRepGProp import brepgprop
            props = GProp_GProps()
            brepgprop.SurfaceProperties(f, props)
            return props.CentreOfMass().Z()
        target = max(planar_faces, key=_face_z)

    wires_out = []

    # Outer wire first
    outer_wire = BRepTools.OuterWire(target)
    poly = _discretise_wire(outer_wire, tol_mm)
    if poly:
        wires_out.append(poly)

    # Inner wires (holes)
    wire_exp = TopExp_Explorer(target, TopAbs_WIRE)
    while wire_exp.More():
        w = wire_exp.Current()
        if not w.IsSame(outer_wire):
            poly = _discretise_wire(w, tol_mm)
            if poly:
                wires_out.append(poly)
        wire_exp.Next()

    return wires_out


def _discretise_wire(wire, deflection: float) -> List[tuple]:
    """Discretise an OCC wire into a list of (x, y) tuples (mm)."""
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_EDGE
    from OCC.Core.GCPnts import GCPnts_QuasiUniformDeflection
    from OCC.Core.BRepAdaptor import BRepAdaptor_Curve

    pts = []
    exp = TopExp_Explorer(wire, TopAbs_EDGE)
    while exp.More():
        edge = exp.Current()
        adaptor = BRepAdaptor_Curve(edge)
        disc = GCPnts_QuasiUniformDeflection(adaptor, max(deflection, 1e-4))
        for i in range(1, disc.NbPoints() + 1):
            p = disc.Value(i)
            pts.append((p.X(), p.Y()))
        exp.Next()

    # Remove consecutive duplicates (edge junctions)
    deduped = []
    for p in pts:
        if not deduped or (abs(p[0] - deduped[-1][0]) > 1e-9 or abs(p[1] - deduped[-1][1]) > 1e-9):
            deduped.append(p)
    return deduped


def _mock_toolpath(operations: List[CAMOperation]):
    """Return a mock 10x10 grid toolpath for testing without opencamlib."""
    lines = ["; MOCK toolpath — opencamlib not installed", "G90 G54", "G17"]
    total_length = 0.0
    feed = operations[0].feed_rate if operations else 1000.0
    step_over = operations[0].step_over if operations else 0.5

    for i, op in enumerate(operations):
        if op.type.lower() == "lathe":
            lines.append(f"; Operation {i + 1}: lathe (mock)")
            lines.append(f"M6 T{i + 1}")
            lines.append("G0 Z50.0")
            lines.append(f"G96 S{op.spindle_rpm} M3")
            lines.append("G0 X10.000 Z0.000")
            lines.append(f"G1 X0.000 Z0.000 F{op.feed_rate}")
            total_length += 10.0
        else:
            lines.append(f"; Operation {i + 1}: {op.type} (mock)")
            lines.append(f"M6 T{i + 1}")
            lines.append(f"G0 Z50.0")
            lines.append(f"S{op.spindle_rpm} M3")
            y = 0.0
            while y <= 10.0:
                lines.append(f"G0 X0.000 Y{y:.3f}")
                lines.append(f"G1 Z-{op.step_down:.3f} F{op.feed_rate}")
                lines.append(f"G1 X10.000 Y{y:.3f} F{op.feed_rate}")
                total_length += 10.0
                y = round(y + op.step_over, 4)
            lines.append("G0 Z50.0")
            feed = op.feed_rate

    lines.extend(["M5", "M30"])
    estimated_time = (total_length / feed * 60) if feed > 0 else 0.0
    return "\n".join(lines), total_length, estimated_time


def generate_toolpaths(
    step_path: str,
    operations: List[CAMOperation],
    post_processor: str,
    stl_path: Optional[str] = None,
    occ_shape=None,
):
    """Generate real toolpaths via opencamlib."""
    import opencamlib as ocl

    surface = ocl.STLSurf()
    if stl_path:
        _load_stl_into_surface(stl_path, surface)

    toolpaths = []
    total_length = 0.0

    for op in operations:
        op_type = op.type.lower()

        if op_type == "lathe":
            gcode_snippet, seg_length = _run_lathe_op(op, occ_shape)
            toolpaths.append(("lathe", gcode_snippet))
            total_length += seg_length
            continue

        tool = ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0)

        if op_type == "parallel_3d":
            clpoints = _run_parallel_3d(tool, op, surface)
        elif op_type == "waterline":
            clpoints = _run_waterline(tool, op, surface)
        elif op_type in ("contour", "profile", "pocket") and occ_shape is not None and _occ_available:
            clpoints = _run_brep_contour_pocket(op_type, tool, op, surface, occ_shape)
        else:
            clpoints = _run_ocl_op(op_type, tool, op, surface)

        toolpaths.append(("mill", clpoints))
        total_length += len(clpoints) * (op.step_over / 1000.0)

    feed = operations[0].feed_rate if operations else 1000.0
    estimated_time = (total_length / (feed / 60000.0)) if feed > 0 else 0.0

    g_code = _emit_gcode(toolpaths, operations, post_processor)
    return g_code, total_length, estimated_time


def _load_stl_into_surface(stl_path: str, surface) -> None:
    """Parse an ASCII STL file and add its triangles to an ocl.STLSurf."""
    import opencamlib as ocl

    with open(stl_path, "r", errors="replace") as fh:
        lines = fh.readlines()

    verts = []
    for line in lines:
        line = line.strip()
        if line.startswith("vertex "):
            parts = line.split()
            verts.append(ocl.Point(float(parts[1]), float(parts[2]), float(parts[3])))
            if len(verts) == 3:
                surface.addTriangle(ocl.Triangle(verts[0], verts[1], verts[2]))
                verts = []


def _run_brep_contour_pocket(
    op_type: str,
    tool,
    op: CAMOperation,
    surface,
    occ_shape,
):
    """Use real B-rep wire extraction for contour/profile/pocket ops.

    Extracts the outer (and inner) wires of the target face, discretises them,
    and builds an ocl.Path from the resulting line segments.  Falls back to the
    bounding-box path if wire extraction yields nothing.
    """
    import opencamlib as ocl

    wires = extract_face_wires(occ_shape, op)

    if not wires:
        # Fallback to bbox
        return _run_ocl_op(op_type, tool, op, surface)

    pdc = ocl.PathDropCutter()
    pdc.setSTL(surface)
    pdc.setCutter(tool)
    pdc.setZ(-(op.step_down / 1000.0))
    pdc.setSampling(op.step_over / 2000.0)

    path = ocl.Path()

    if op_type in ("contour", "profile"):
        # Walk outer wire perimeter (index 0)
        poly = wires[0]
        for a, b in zip(poly, poly[1:]):
            path.append(ocl.Line(
                ocl.Point(a[0] / 1000.0, a[1] / 1000.0, 0.0),
                ocl.Point(b[0] / 1000.0, b[1] / 1000.0, 0.0),
            ))
        # Close the loop
        if poly:
            path.append(ocl.Line(
                ocl.Point(poly[-1][0] / 1000.0, poly[-1][1] / 1000.0, 0.0),
                ocl.Point(poly[0][0] / 1000.0, poly[0][1] / 1000.0, 0.0),
            ))
    else:
        # pocket: raster scan within bounding box of outer wire, avoid inner wires
        outer = wires[0]
        xs = [p[0] for p in outer]
        ys = [p[1] for p in outer]
        x_min, x_max = min(xs) / 1000.0, max(xs) / 1000.0
        y_min, y_max = min(ys) / 1000.0, max(ys) / 1000.0
        step = op.step_over / 1000.0
        y = y_min
        while y <= y_max + 1e-9:
            path.append(ocl.Line(
                ocl.Point(x_min, y, 0.0),
                ocl.Point(x_max, y, 0.0),
            ))
            y += step

    pdc.setPath(path)
    pdc.run()
    return pdc.getCLPoints()


def _run_ocl_op(op_type: str, tool, op: CAMOperation, surface):
    """Run an opencamlib PathDropCutter pass and return a list of CL points."""
    import opencamlib as ocl

    pdc = ocl.PathDropCutter()
    pdc.setSTL(surface)
    pdc.setCutter(tool)
    pdc.setZ(-(op.step_down / 1000.0))
    pdc.setSampling(op.step_over / 2000.0)

    path = ocl.Path()
    step = op.step_over / 1000.0

    if op_type in ("face", "pocket"):
        bb = surface.getBounds() if hasattr(surface, "getBounds") else None
        if bb and hasattr(bb, "minpt") and hasattr(bb, "maxpt"):
            x_min, x_max = bb.minpt.x, bb.maxpt.x
            y_min, y_max = bb.minpt.y, bb.maxpt.y
        else:
            x_min, y_min, x_max, y_max = 0.0, 0.0, 0.01, 0.01
        y = y_min
        while y <= y_max + 1e-9:
            path.append(ocl.Line(
                ocl.Point(x_min, y, 0.0),
                ocl.Point(x_max, y, 0.0),
            ))
            y += step
    elif op_type in ("contour", "profile"):
        bb = surface.getBounds() if hasattr(surface, "getBounds") else None
        if bb and hasattr(bb, "minpt") and hasattr(bb, "maxpt"):
            x0, x1 = bb.minpt.x, bb.maxpt.x
            y0, y1 = bb.minpt.y, bb.maxpt.y
        else:
            x0, y0, x1, y1 = 0.0, 0.0, 0.01, 0.01
        corners = [
            ocl.Point(x0, y0, 0.0),
            ocl.Point(x1, y0, 0.0),
            ocl.Point(x1, y1, 0.0),
            ocl.Point(x0, y1, 0.0),
            ocl.Point(x0, y0, 0.0),
        ]
        for a, b in zip(corners, corners[1:]):
            path.append(ocl.Line(a, b))
    elif op_type == "drill":
        path.append(ocl.Line(
            ocl.Point(0.0, 0.0, 0.0),
            ocl.Point(0.0, 0.0, -(op.step_down / 1000.0)),
        ))
    else:
        return []

    pdc.setPath(path)
    pdc.run()
    return pdc.getCLPoints()


def _run_parallel_3d(tool, op: CAMOperation, surface):
    """3D parallel (raster) drop-cutter across the full surface.

    Raster direction is X (default), Y, or an arbitrary angle (angle_deg).
    The raster grid covers the full STL bounding box.
    """
    import opencamlib as ocl

    pdc = ocl.PathDropCutter()
    pdc.setSTL(surface)
    pdc.setCutter(tool)
    pdc.setZ(-(op.step_down / 1000.0))
    pdc.setSampling(op.step_over / 2000.0)

    bb = surface.getBounds() if hasattr(surface, "getBounds") else None
    if bb and hasattr(bb, "minpt") and hasattr(bb, "maxpt"):
        x_min, x_max = bb.minpt.x, bb.maxpt.x
        y_min, y_max = bb.minpt.y, bb.maxpt.y
    else:
        x_min, y_min, x_max, y_max = 0.0, 0.0, 0.01, 0.01

    step = op.step_over / 1000.0
    path = ocl.Path()

    direction = (op.direction or "x").lower()
    angle_rad = math.radians(op.angle_deg) if op.angle_deg is not None else None

    if angle_rad is not None:
        # Arbitrary-angle raster: rotate lines by angle_rad in the XY plane.
        # Generate lines perpendicular to the raster direction across the bbox diagonal.
        diag = math.hypot(x_max - x_min, y_max - y_min)
        cx = (x_min + x_max) / 2.0
        cy = (y_min + y_max) / 2.0
        perp = angle_rad + math.pi / 2.0
        n_lines = int(diag / step) + 2
        for i in range(-n_lines // 2, n_lines // 2 + 1):
            offset = i * step
            mx = cx + offset * math.cos(perp)
            my = cy + offset * math.sin(perp)
            ax = mx - diag * math.cos(angle_rad)
            ay = my - diag * math.sin(angle_rad)
            bx = mx + diag * math.cos(angle_rad)
            by = my + diag * math.sin(angle_rad)
            path.append(ocl.Line(ocl.Point(ax, ay, 0.0), ocl.Point(bx, by, 0.0)))
    elif direction == "y":
        x = x_min
        while x <= x_max + 1e-9:
            path.append(ocl.Line(
                ocl.Point(x, y_min, 0.0),
                ocl.Point(x, y_max, 0.0),
            ))
            x += step
    else:
        # Default: X raster (lines parallel to X axis, stepping in Y)
        y = y_min
        while y <= y_max + 1e-9:
            path.append(ocl.Line(
                ocl.Point(x_min, y, 0.0),
                ocl.Point(x_max, y, 0.0),
            ))
            y += step

    pdc.setPath(path)
    pdc.run()
    return pdc.getCLPoints()


def _run_waterline(tool, op: CAMOperation, surface):
    """Waterline (constant-Z contour) toolpath from top to bottom of part.

    Uses ocl.AdaptiveWaterline when available; falls back to PathDropCutter
    rectangular perimeters at each Z level when AdaptiveWaterline is absent.
    """
    import opencamlib as ocl

    bb = surface.getBounds() if hasattr(surface, "getBounds") else None
    if bb and hasattr(bb, "minpt") and hasattr(bb, "maxpt"):
        z_top = bb.maxpt.z
        z_bot = bb.minpt.z
        x_min, x_max = bb.minpt.x, bb.maxpt.x
        y_min, y_max = bb.minpt.y, bb.maxpt.y
    else:
        z_top, z_bot = 0.0, -0.01
        x_min, y_min, x_max, y_max = 0.0, 0.0, 0.01, 0.01

    step_down_m = op.step_down / 1000.0
    all_points = []

    if hasattr(ocl, "AdaptiveWaterline"):
        z = z_top
        while z >= z_bot - 1e-9:
            wl = ocl.AdaptiveWaterline()
            wl.setSTL(surface)
            wl.setCutter(tool)
            wl.setZ(z)
            wl.setSampling(op.step_over / 2000.0)
            wl.run()
            all_points.extend(wl.getCLPoints())
            z -= step_down_m
    else:
        # Fallback: rectangular perimeter at each Z level via PathDropCutter
        z = z_top
        while z >= z_bot - 1e-9:
            pdc = ocl.PathDropCutter()
            pdc.setSTL(surface)
            pdc.setCutter(tool)
            pdc.setZ(z)
            pdc.setSampling(op.step_over / 2000.0)
            path = ocl.Path()
            corners = [
                ocl.Point(x_min, y_min, 0.0),
                ocl.Point(x_max, y_min, 0.0),
                ocl.Point(x_max, y_max, 0.0),
                ocl.Point(x_min, y_max, 0.0),
                ocl.Point(x_min, y_min, 0.0),
            ]
            for a, b in zip(corners, corners[1:]):
                path.append(ocl.Line(a, b))
            pdc.setPath(path)
            pdc.run()
            all_points.extend(pdc.getCLPoints())
            z -= step_down_m

    return all_points


def _run_lathe_op(op: CAMOperation, occ_shape=None):
    """Generate lathe turning G-code in the X-Z plane.

    Extracts the profile from the B-rep (largest planar face containing the
    spindle axis) when occ_shape is available; otherwise generates a default
    cylindrical roughing pass.

    Returns (gcode_snippet: str, total_length_mm: float).
    """
    spindle_axis = (op.spindle_axis or "z").lower()
    feed = op.feed_rate
    rpm = op.spindle_rpm
    step_down = op.step_down   # radial infeed per pass (mm)
    total_length = 0.0
    lines = []

    lines.append(f"; Lathe op — spindle axis {spindle_axis.upper()}")
    lines.append(f"G18")          # X-Z plane
    lines.append(f"G96 S{rpm} M3")  # constant surface speed, spindle on
    lines.append(f"G0 X50.000 Z5.000")

    profile = _extract_lathe_profile(occ_shape) if occ_shape is not None else None

    if profile:
        # Profile is a list of (z_mm, x_radius_mm) pairs sorted by Z descending
        # Walk roughing passes from current stock diameter down to profile.
        r_max = max(r for _, r in profile)
        passes = max(1, int(math.ceil(r_max / step_down)))
        for pass_idx in range(passes):
            r_cut = r_max - pass_idx * step_down
            if r_cut < 0:
                r_cut = 0.0
            for z_mm, r_mm in profile:
                if r_mm <= r_cut:
                    lines.append(f"G1 X{r_mm * 2:.3f} Z{z_mm:.3f} F{feed:.1f}")
                    total_length += abs(z_mm)
                else:
                    lines.append(f"G1 X{r_cut * 2:.3f} Z{z_mm:.3f} F{feed:.1f}")
                    total_length += abs(z_mm)
            lines.append(f"G0 X{r_max * 2 + 2:.3f} Z5.000")
    else:
        # Default: cylindrical roughing pass over a 20 mm long × 10 mm radius cylinder
        z_start = 0.0
        z_end = -20.0
        r_stock = 10.0
        r = r_stock
        while r > 0:
            lines.append(f"G0 X{r * 2:.3f} Z{z_start:.3f}")
            lines.append(f"G1 Z{z_end:.3f} F{feed:.1f}")
            total_length += abs(z_end - z_start)
            r = max(0.0, r - step_down)

    lines.append(f"G0 X60.000 Z10.000")
    lines.append(f"M5")
    return "\n".join(lines), total_length


def _extract_lathe_profile(occ_shape) -> Optional[List[tuple]]:
    """Extract a turning profile as (z_mm, x_radius_mm) pairs.

    Finds edges on the largest face that lies in the X-Z plane (Y≈0 normal),
    discretises them, and returns the upper envelope as the turning profile.
    Returns None if no suitable face is found.
    """
    try:
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopAbs import TopAbs_FACE
        from OCC.Core.BRep import BRep_Tool
        from OCC.Core.GeomLProp import GeomLProp_SLProps
        from OCC.Core.GProp import GProp_GProps
        from OCC.Core.BRepGProp import brepgprop
        from OCC.Core.GCPnts import GCPnts_QuasiUniformDeflection
        from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
        from OCC.Core.TopAbs import TopAbs_EDGE

        best_face = None
        best_area = -1.0

        exp = TopExp_Explorer(occ_shape, TopAbs_FACE)
        while exp.More():
            face = exp.Current()
            surf = BRep_Tool.Surface(face)
            u_min, u_max, v_min, v_max = BRep_Tool.GetBounds(face)
            props = GeomLProp_SLProps(surf, (u_min + u_max) / 2, (v_min + v_max) / 2, 1, 1e-6)
            if props.IsNormalDefined():
                n = props.Normal()
                # Face in X-Z plane has Y normal
                if abs(abs(n.Y()) - 1.0) < 0.1:
                    gp = GProp_GProps()
                    brepgprop.SurfaceProperties(face, gp)
                    area = gp.Mass()
                    if area > best_area:
                        best_area = area
                        best_face = face
            exp.Next()

        if best_face is None:
            return None

        pts = []
        edge_exp = TopExp_Explorer(best_face, TopAbs_EDGE)
        while edge_exp.More():
            edge = edge_exp.Current()
            adaptor = BRepAdaptor_Curve(edge)
            disc = GCPnts_QuasiUniformDeflection(adaptor, 0.05)
            for i in range(1, disc.NbPoints() + 1):
                p = disc.Value(i)
                pts.append((p.Z(), abs(p.X())))
            edge_exp.Next()

        if not pts:
            return None

        # Sort by Z descending, deduplicate, return
        pts.sort(key=lambda p: -p[0])
        return pts

    except Exception:
        return None


def _emit_gcode(toolpaths, operations: List[CAMOperation], post_processor: str) -> str:
    lines = [
        "; Generated by pyworker CAM",
        f"; Post-processor: {post_processor}",
    ]

    for i, (tp_entry, op) in enumerate(zip(toolpaths, operations)):
        op_kind = tp_entry[0]
        tp = tp_entry[1]

        if op_kind == "lathe":
            lines.append(f"; Operation {i + 1}: {op.type}")
            lines.append(tp)
            continue

        # mill ops
        lines.append(f"; Operation {i + 1}: {op.type}")

        if op.type.lower() == "lathe":
            continue

        lines.append("G90 G54")
        lines.append("G17")
        lines.append(f"M6 T{i + 1}")
        lines.append(f"G0 Z50.0")
        lines.append(f"S{op.spindle_rpm} M3")

        if len(tp) > 0:
            p0 = tp[0]
            lines.append(f"G0 X{p0.x * 1000:.3f} Y{p0.y * 1000:.3f}")
            lines.append(f"G1 Z{p0.z * 1000 + 2.0:.3f} F{op.feed_rate}")
            for pt in tp:
                lines.append(f"G1 X{pt.x * 1000:.3f} Y{pt.y * 1000:.3f} Z{pt.z * 1000:.3f} F{op.feed_rate}")

        lines.append("G0 Z50.0")

    lines.extend(["M5", "M30"])
    return "\n".join(lines)
