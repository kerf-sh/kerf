import json
import math
import uuid
from tools.registry import ToolSpec, err_payload, ok_payload, register
from tools.context import ProjectCtx
from db.queries import files as file_queries


compare_models_spec = ToolSpec(
    name="compare_models",
    description="Compare two mesh files (STL, OBJ, etc. stored as JSON with vertices/indices) to compute geometric deviation. Returns max/mean deviation and per-vertex delta. Used for inspection (e.g., verifying 3D-printed part vs source model).",
    input_schema={
        "type": "object",
        "properties": {
            "file_id_a": {"type": "string", "description": "UUID of the first mesh file."},
            "file_id_b": {"type": "string", "description": "UUID of the second mesh file."},
            "tolerance_mm": {"type": "number", "description": "Tolerance threshold in mm for percent_within_tolerance (default: 0.1)."},
            "sampling": {"type": "number", "description": "Sampling factor 0-1 to reduce computation (default: 1)."},
        },
        "required": ["file_id_a", "file_id_b"],
    },
)


def _compare_mesh_data(mesh_a, mesh_b, tolerance=0.1, sampling=1.0):
    verts_a = mesh_a.get("vertices", [])
    verts_b = mesh_b.get("vertices", [])

    if not verts_a or not verts_b:
        return {"summary": {"max_deviation": 0, "mean_deviation": 0, "percent_within_tolerance": 100}, "deviations": []}

    if sampling < 1.0:
        step = max(1, int(1 / sampling))
        verts_a = verts_a[::step]

    deviations = []
    sum_deviation = 0.0
    max_deviation = 0.0
    within_tolerance = 0

    for ax, ay, az in verts_a:
        min_dist_sq = math.inf
        for bx, by, bz in verts_b:
            dx = ax - bx
            dy = ay - by
            dz = az - bz
            dist_sq = dx * dx + dy * dy + dz * dz
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
        delta = math.sqrt(min_dist_sq)
        deviations.append({"x": ax, "y": ay, "z": az, "delta": delta})
        sum_deviation += delta
        if delta > max_deviation:
            max_deviation = delta
        if delta <= tolerance:
            within_tolerance += 1

    count = len(verts_a)
    return {
        "summary": {
            "max_deviation": max_deviation,
            "mean_deviation": sum_deviation / count,
            "percent_within_tolerance": (within_tolerance / count) * 100,
        },
        "deviations": deviations,
    }


@register(compare_models_spec)
async def run_compare_models(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    fid_a = a.get("file_id_a", "")
    fid_b = a.get("file_id_b", "")
    tolerance = a.get("tolerance_mm", 0.1)
    sampling = a.get("sampling", 1.0)

    if not fid_a:
        return err_payload("file_id_a is required", "BAD_ARGS")
    if not fid_b:
        return err_payload("file_id_b is required", "BAD_ARGS")

    try:
        uid_a = uuid.UUID(fid_a)
        uid_b = uuid.UUID(fid_b)
    except Exception:
        return err_payload("file_id_a and file_id_b must be valid UUIDs", "BAD_UUID")

    row_a = await file_queries.get_file(ctx.pool, uid_a)
    if not row_a:
        return err_payload("file_id_a not found", "NOT_FOUND")
    row_b = await file_queries.get_file(ctx.pool, uid_b)
    if not row_b:
        return err_payload("file_id_b not found", "NOT_FOUND")

    try:
        mesh_a = json.loads(row_a["content"] or "{}")
        mesh_b = json.loads(row_b["content"] or "{}")
    except Exception as e:
        return err_payload(f"failed to parse mesh JSON: {e}", "BAD_CONTENT")

    result = _compare_mesh_data(mesh_a, mesh_b, tolerance, sampling)
    return ok_payload(result)