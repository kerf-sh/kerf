"""
CAM toolpath generation via OpenCAMlib.

POST /run-cam
Body (worker shape):
    {
        "step_b64": string (base64-encoded STEP file),
        "input_spec": {
            "operation": "face"|"contour"|"pocket"|"drill"|"profile",
            "tool_diameter": float (mm),
            "step_over": float (mm),
            "step_down": float (mm),
            "feed_rate": float (mm/min),
            "spindle_speed": float (RPM),
            "coolant": bool
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
import json
import math
import tempfile
from pathlib import Path
from typing import Optional, List

router = APIRouter()


class CAMOperation(BaseModel):
    type: str
    tool_diameter: float
    step_down: float
    step_over: float
    feed_rate: float
    spindle_rpm: int
    coolant: str = "flood"


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
        # Map from cam_worker.py shape → CAMOperation shape
        operations = [CAMOperation(
            type=spec.get("operation", "profile"),
            tool_diameter=float(spec.get("tool_diameter", 3.0)),
            step_down=float(spec.get("step_down", 0.5)),
            step_over=float(spec.get("step_over", 0.5)),
            feed_rate=float(spec.get("feed_rate", 1000.0)),
            spindle_rpm=int(spec.get("spindle_speed", 10000)),
            coolant="flood" if spec.get("coolant", True) else "off",
        )]
    else:
        raise HTTPException(status_code=400, detail="either operations or input_spec required")

    try:
        import opencamlib as ocl  # noqa: F401 — presence check only
        _ocl_available = True
    except ImportError:
        _ocl_available = False

    warnings = []
    errors = []
    toolpath_length = 0.0
    estimated_time = 0.0

    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = Path(tmpdir) / "input.step"
        step_path.write_bytes(step_bytes)

        if not _ocl_available:
            # Graceful fallback: generate a mock bounding-box toolpath
            # TODO: when opencamlib is available, replace with real STEP→STL→OCL pipeline
            warnings.append("opencamlib not installed — returning mock scaffold toolpath. "
                            "Install: pip install opencamlib (or build from source: "
                            "https://github.com/aewallin/opencamlib)")
            g_code, toolpath_length, estimated_time = _mock_toolpath(operations)
        else:
            try:
                g_code, toolpath_length, estimated_time = generate_toolpaths(
                    str(step_path), operations, req.post_processor
                )
            except Exception as e:
                errors.append(str(e))
                g_code = ""

        # Write G-code to tmpdir and encode
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


def _mock_toolpath(operations: List[CAMOperation]):
    """Return a mock 10x10 grid toolpath for testing without opencamlib."""
    lines = ["; MOCK toolpath — opencamlib not installed", "G90 G54", "G17"]
    total_length = 0.0
    feed = operations[0].feed_rate if operations else 1000.0
    step_over = operations[0].step_over if operations else 0.5

    for i, op in enumerate(operations):
        lines.append(f"; Operation {i + 1}: {op.type} (mock)")
        lines.append(f"M6 T{i + 1}")
        lines.append(f"G0 Z50.0")
        lines.append(f"S{op.spindle_rpm} M3")
        # 10x10mm grid
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


def generate_toolpaths(step_path: str, operations: List[CAMOperation], post_processor: str):
    """Generate real toolpaths via opencamlib.

    NOTE: opencamlib works with STL meshes, not STEP files directly.
    In production this requires a STEP→STL conversion step (e.g. via pythonOCC
    or FreeCAD). For now we generate a scaffold waterline toolpath on a simple
    placeholder surface and TODO the STEP→STL pipeline.
    """
    import opencamlib as ocl

    # TODO: convert STEP → STL via pythonOCC before loading into ocl
    # For now, create a simple flat surface as a proxy
    # stl_path = convert_step_to_stl(step_path)  # not yet implemented
    # mid = ocl.STLObj(); mid.readFile(stl_path)

    toolpaths = []
    total_length = 0.0

    for op in operations:
        tool = ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0)
        op_type = op.type.lower()

        # Use a simple adaptive dropcutter on a placeholder flat surface
        # Real implementation needs the STL loaded from the converted STEP
        clpoints = _run_ocl_op(op_type, tool, op)
        toolpaths.append(clpoints)
        # Approximate length from point count * step_over
        total_length += len(clpoints) * (op.step_over / 1000.0)

    feed = operations[0].feed_rate if operations else 1000.0
    estimated_time = (total_length / (feed / 60000.0)) if feed > 0 else 0.0

    g_code = _emit_gcode(toolpaths, operations, post_processor)
    return g_code, total_length, estimated_time


def _run_ocl_op(op_type: str, tool, op: CAMOperation):
    """Run an opencamlib operation, returning a list of CL points."""
    import opencamlib as ocl

    # Placeholder: return empty list until STEP→STL conversion is wired up
    # Real: lw = ocl.Waterline(stl_surface); lw.setTool(tool); lw.run(); return lw.getCLPoints()
    return []


def _emit_gcode(toolpaths, operations: List[CAMOperation], post_processor: str) -> str:
    lines = [
        f"; Generated by pyworker CAM",
        f"; Post-processor: {post_processor}",
        "G90 G54",
        "G17",
    ]

    for i, (tp, op) in enumerate(zip(toolpaths, operations)):
        lines.append(f"; Operation {i + 1}: {op.type}")
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
