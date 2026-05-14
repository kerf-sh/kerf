import json
import uuid

try:
    from tools.registry import ToolSpec, err_payload, ok_payload, register
    from tools.context import ProjectCtx
except ImportError:
    from kerf_fem._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx


fem_run_spec = ToolSpec(
    name="fem_run",
    description="Run a finite-element stress analysis on a STEP file. Returns max von-Mises stress, displacement, FoS, and modal frequencies.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "material_props": {
                "type": "object",
                "properties": {
                    "E": {"type": "number"},
                    "nu": {"type": "number"},
                    "rho": {"type": "number"},
                    "yield_strength": {"type": "number"},
                },
                "required": ["E", "nu", "rho", "yield_strength"],
            },
            "boundary_conditions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["fixed", "displacement"]},
                        "face_tags": {"type": "array", "items": {"type": "number"}},
                        "ux": {"type": "number"},
                        "uy": {"type": "number"},
                        "uz": {"type": "number"},
                    },
                    "required": ["type", "face_tags"],
                },
            },
            "loads": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["pressure", "force"]},
                        "face_tags": {"type": "array", "items": {"type": "number"}},
                        "value": {"type": "number"},
                    },
                    "required": ["type", "face_tags", "value"],
                },
            },
            "mesh_size": {"type": "number"},
            "solver": {"type": "string", "enum": ["fenicsx", "calculix"]},
            "analysis_type": {"type": "string", "enum": ["linear_static", "modal", "thermal"]},
        },
        "required": ["file_id", "material_props", "boundary_conditions", "loads"],
    },
)


@register(fem_run_spec, write=True)
async def run_fem_run(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    material_props = a.get("material_props")
    boundary_conditions = a.get("boundary_conditions", [])
    loads = a.get("loads", [])

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if not material_props:
        return err_payload("material_props is required", "BAD_ARGS")
    if not boundary_conditions:
        return err_payload("at least one boundary_conditions entry is required", "BAD_ARGS")
    if not loads:
        return err_payload("at least one load entry is required", "BAD_ARGS")

    spec = {
        "material_props": material_props,
        "boundary_conditions": boundary_conditions,
        "loads": loads,
        "mesh_size": a.get("mesh_size", 0.01),
        "solver": a.get("solver", "fenicsx"),
        "analysis_type": a.get("analysis_type", "linear_static"),
    }
    spec_json = json.dumps(spec)

    row = await ctx.pool.fetchrow(
        """INSERT INTO fem_jobs (file_id, project_id, input_spec)
           VALUES ($1, $2, $3)
           ON CONFLICT (file_id) WHERE status IN ('queued', 'running')
           DO UPDATE SET input_spec = $3, status = 'queued', error = NULL,
               started_at = NULL, finished_at = NULL
           RETURNING id""",
        file_id, ctx.project_id, spec_json,
    )

    if not row:
        return err_payload("failed to enqueue FEM job", "ERROR")

    return ok_payload({
        "job_id": str(row["id"]),
        "status": "queued",
        "message": "FEM job enqueued. Poll fem_job_status(file_id) for results.",
    })


fem_job_status_spec = ToolSpec(
    name="fem_job_status",
    description="Poll the status of a FEM analysis job. Returns the job status, and when complete the result JSON.",
    input_schema={
        "type": "object",
        "properties": {"file_id": {"type": "string"}},
        "required": ["file_id"],
    },
)


@register(fem_job_status_spec)
async def run_fem_job_status(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    row = await ctx.pool.fetchrow(
        """SELECT status, result_json, error FROM fem_jobs
           WHERE file_id = $1 AND project_id = $2
           ORDER BY created_at DESC LIMIT 1""",
        file_id, ctx.project_id,
    )

    if not row:
        return err_payload("fem job not found", "NOT_FOUND")

    resp = {"file_id": file_id, "status": row["status"]}
    if row["status"] == "done" and row["result_json"]:
        try:
            result = json.loads(row["result_json"])
            resp["result"] = result
        except Exception:
            pass
    elif row["status"] == "error" and row["error"]:
        resp["error"] = row["error"]

    return ok_payload(resp)
